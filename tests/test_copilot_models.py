import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "copilot_models", Path(__file__).resolve().parents[1] / "scripts/copilot-models.py"
)
models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models)

MODEL = {
    "id": "supported",
    "policy": {"state": "enabled"},
    "capabilities": {"supports": {"tool_calls": True, "reasoningEffort": True}},
    "supportedReasoningEfforts": ["high", "max"],
    "billing": {"tokenPrices": {"longContext": {"maxPromptTokens": 1000000}}},
}
CATALOG = {"models": [MODEL]}
PROFILES = {
    "default": {"model": "supported", "reasoningEffort": "max", "longContext": True}
}
REAL_POPEN = subprocess.Popen


def frame(value):
    body = json.dumps(value).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


class CopilotModelsTests(unittest.TestCase):
    def test_valid_profiles_and_optional_policy(self):
        models.validate_profiles(PROFILES, CATALOG)
        catalog = copy.deepcopy(CATALOG)
        del catalog["models"][0]["policy"]
        models.validate_profiles(PROFILES, catalog)

    def test_unsupported_profile_settings(self):
        for field, value in [
            ("model", "unavailable"),
            ("model", {}),
            ("reasoningEffort", "impossible"),
            ("reasoningEffort", None),
            ("longContext", "false"),
            ("longContext", 1),
        ]:
            with self.subTest(field=field, value=value):
                profiles = copy.deepcopy(PROFILES)
                profiles["default"][field] = value
                with self.assertRaises(ValueError):
                    models.validate_profiles(profiles, CATALOG)

    def test_invalid_profile_schema(self):
        for profiles in [
            {},
            [],
            {"other": PROFILES["default"]},
            {"default": {}},
            {"default": {**PROFILES["default"], "typo": True}},
        ]:
            with self.subTest(profiles=profiles), self.assertRaises(ValueError):
                models.validate_profiles(profiles, CATALOG)

    def test_unavailable_capabilities(self):
        for field, value in [
            ("policy", {"state": "disabled"}),
            ("capabilities", {"supports": {"tool_calls": False, "reasoningEffort": True}}),
            ("capabilities", {"supports": {"tool_calls": True, "reasoningEffort": False}}),
            ("supportedReasoningEfforts", []),
            ("billing", {}),
        ]:
            with self.subTest(field=field, value=value):
                catalog = copy.deepcopy(CATALOG)
                catalog["models"][0][field] = value
                with self.assertRaises(ValueError):
                    models.validate_profiles(PROFILES, catalog)

    def test_default_context_needs_no_long_tier(self):
        catalog = copy.deepcopy(CATALOG)
        catalog["models"][0]["billing"] = {}
        profiles = copy.deepcopy(PROFILES)
        profiles["default"]["longContext"] = False
        models.validate_profiles(profiles, catalog)

    def test_invalid_long_context_metadata(self):
        for tier in [None, {}, {"maxPromptTokens": 0}, {"maxPromptTokens": True},
                     {"maxPromptTokens": "1000000"}]:
            with self.subTest(tier=tier), self.assertRaises(ValueError):
                catalog = copy.deepcopy(CATALOG)
                catalog["models"][0]["billing"]["tokenPrices"]["longContext"] = tier
                models.validate_profiles(PROFILES, catalog)

    def test_invalid_catalog(self):
        for entries in [[], [MODEL, MODEL], [{"id": ""}], None]:
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                models.model_index({"models": entries})

    def test_rpc_skips_notifications(self):
        process = SimpleNamespace(
            stdin=io.BytesIO(),
            stdout=io.BytesIO(
                frame({"jsonrpc": "2.0", "method": "notice"})
                + frame({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
            ),
        )
        self.assertEqual(models.rpc(process, 1, "models.list"), {"ok": True})
        self.assertIn(b'"method": "models.list"', process.stdin.getvalue())

    def test_rpc_failures(self):
        for output, error in [
            (frame({"id": 1, "error": {"message": "denied"}}), RuntimeError),
            (b"", RuntimeError),
            (b"Content-Length: -1\r\n\r\n", ValueError),
            (b"Content-Length: 10000001\r\n\r\n", ValueError),
            (b"Content-Length: 1\r\n\r\n{", ValueError),
        ]:
            with self.subTest(output=output), self.assertRaises(error):
                process = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(output))
                models.rpc(process, 1, "models.list")

    def discover_with_server(self, output, timeout=2):
        processes = []

        def spawn(args, **kwargs):
            self.assertIn("--headless", args)
            self.assertIn("--stdio", args)
            self.assertNotIn("--prompt", args)
            server = (
                f"import sys,time;sys.stdout.buffer.write({output!r});"
                "sys.stdout.flush();time.sleep(10)"
            )
            process = REAL_POPEN([sys.executable, "-c", server], **kwargs)
            processes.append(process)
            return process

        try:
            with (
                patch.object(models.subprocess, "Popen", side_effect=spawn),
                patch.object(models, "DISCOVERY_TIMEOUT_SECONDS", timeout),
                patch.dict(os.environ, {"COPILOT_GITHUB_TOKEN": "fixture-only"}),
            ):
                return models.discover()
        finally:
            self.assertTrue(all(process.poll() is not None for process in processes))

    def test_discovery_output_and_cleanup(self):
        result = self.discover_with_server(
            frame({"id": 1, "result": {"version": "fixture", "protocolVersion": 3}})
            + frame({"id": 2, "result": CATALOG})
        )
        self.assertEqual(result["models"], [MODEL])
        self.assertEqual(result["cli_version"], "fixture")
        self.assertIn("collected_at", result)

    def test_unknown_protocol(self):
        with self.assertRaises(ValueError):
            self.discover_with_server(
                frame({"id": 1, "result": {"version": "future", "protocolVersion": 999}})
            )

    def test_timeout_and_cleanup(self):
        start = time.monotonic()
        with self.assertRaises(RuntimeError):
            self.discover_with_server(b"", timeout=0.1)
        self.assertLess(time.monotonic() - start, 5)

    def test_explicit_model_credential_required(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            models.discover()

    def test_failed_validation_has_no_catalog_output(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps(CATALOG))
            config = Path(directory) / "config.json"
            config.write_text("{}")
            stdout, stderr = io.StringIO(), io.StringIO()
            with (
                patch.object(
                    sys, "argv",
                    ["copilot-models.py", "--catalog", str(catalog), "--check-config", str(config)],
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                self.assertEqual(models.main(), 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("Error:", stderr.getvalue())

    def test_failed_discovery_has_no_catalog_output(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(sys, "argv", ["copilot-models.py"]),
            patch.object(models, "discover", side_effect=RuntimeError("denied")),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(models.main(), 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("denied", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
