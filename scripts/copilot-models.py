#!/usr/bin/env python3
"""Discover Copilot models and check Factory profiles without running a prompt."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import threading


DISCOVERY_TIMEOUT_SECONDS = 60


def rpc(process, request_id, method):
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": {}}
    ).encode()
    process.stdin.write(f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload)
    process.stdin.flush()
    while True:
        headers = {}
        while True:
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("Copilot closed the discovery stream or timed out")
            if line == b"\r\n":
                break
            name, value = line.decode("ascii").split(":", 1)
            headers[name.lower()] = value.strip()
        length = int(headers["content-length"])
        if not 0 < length <= 10_000_000:
            raise ValueError("Invalid Copilot response length")
        response = json.loads(process.stdout.read(length))
        if response.get("id") != request_id:
            continue
        if "error" in response:
            raise RuntimeError(f"Copilot {method} failed: {response['error']}")
        return response["result"]


def model_index(catalog):
    models = catalog["models"]
    if not isinstance(models, list) or not models:
        raise ValueError("Copilot returned no model catalog")
    indexed = {}
    for model in models:
        model_id = model["id"]
        if not isinstance(model_id, str) or not model_id or model_id in indexed:
            raise ValueError("Copilot returned an invalid or duplicate model ID")
        indexed[model_id] = model
    return indexed


def discover():
    env = os.environ.copy()
    if not env.get("COPILOT_GITHUB_TOKEN"):
        raise ValueError("COPILOT_GITHUB_TOKEN is required for model discovery")
    process = subprocess.Popen(
        ["copilot", "--headless", "--stdio", "--no-auto-update", "--log-level", "error"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env=env,
    )
    timer = threading.Timer(DISCOVERY_TIMEOUT_SECONDS, process.kill)
    timer.start()
    try:
        status = rpc(process, 1, "status.get")
        if status.get("protocolVersion") != 3 or not status.get("version"):
            raise ValueError(f"Unsupported Copilot discovery protocol: {status}")
        result = rpc(process, 2, "models.list")
        catalog = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "cli_version": status["version"],
            "protocol_version": status["protocolVersion"],
            "models": result["models"],
        }
        model_index(catalog)
        return catalog
    finally:
        timer.cancel()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()


def validate_profiles(profiles, catalog):
    if not isinstance(profiles, dict) or "default" not in profiles:
        raise ValueError("Profiles must include 'default'")
    models = model_index(catalog)
    for name, profile in profiles.items():
        if not isinstance(profile, dict) or set(profile) != {
            "model", "reasoningEffort", "longContext"
        }:
            raise ValueError(f"{name}: expected model, reasoningEffort, and longContext")
        if not isinstance(profile["model"], str) or profile["model"] not in models:
            raise ValueError(f"{name}: model is not in the discovered catalog")
        model = models[profile["model"]]
        if model.get("policy", {}).get("state") not in (None, "enabled"):
            raise ValueError(f"{name}: model is not enabled by Copilot policy")
        supports = model.get("capabilities", {}).get("supports", {})
        if supports.get("tool_calls") is not True:
            raise ValueError(f"{name}: model has no verified tool-call support")
        if (
            supports.get("reasoningEffort") is not True
            or profile["reasoningEffort"] not in model.get("supportedReasoningEfforts", [])
        ):
            raise ValueError(f"{name}: unsupported reasoning effort")
        if not isinstance(profile["longContext"], bool):
            raise ValueError(f"{name}: longContext must be a boolean")
        if profile["longContext"]:
            tier = model.get("billing", {}).get("tokenPrices", {}).get("longContext", {})
            limit = tier.get("maxPromptTokens") if isinstance(tier, dict) else None
            if type(limit) is not int or limit <= 0:
                raise ValueError(f"{name}: no verified Copilot long-context tier")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, help="Use a catalog from this run")
    parser.add_argument("--check-config", type=Path, help="Validate a model-config.json")
    args = parser.parse_args()
    try:
        catalog = json.loads(args.catalog.read_text()) if args.catalog else discover()
        model_index(catalog)
        if args.check_config:
            profiles = json.loads(args.check_config.read_text())
            validate_profiles(profiles, catalog)
            print(f"Validated {len(profiles)} profiles", file=sys.stderr)
        print(json.dumps(catalog, indent=2))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(f"Error: Copilot model discovery/validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
