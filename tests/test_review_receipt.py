import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/pr-review.yml"
GUIDE = ROOT / "docs/factory/pr-review.md"
FAKE_GH = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

Path("gh-args.json").write_text(json.dumps(sys.argv[1:]))
print(os.environ["GH_RESPONSE"])
sys.exit(int(os.environ["GH_STATUS"]))
"""


class ReviewReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="review-receipt-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        gh = self.directory / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.env = os.environ.copy()
        for name in (
            "GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN", "GITHUB_OUTPUT",
            "GITHUB_ENV", "GITHUB_PATH", "GITHUB_STATE", "GITHUB_STEP_SUMMARY",
            "GITHUB_ARTIFACTS", "GITHUB_ARTIFACTS_LIST",
        ):
            self.env.pop(name, None)
        self.env.update(
            PATH=f"{self.directory}{os.pathsep}{self.env['PATH']}",
            GITHUB_REPOSITORY="example/repo",
            PR_NUMBER="7",
            PR_HEAD_SHA="a" * 40,
            REVIEW_MARKER="factory-review:123:1",
            REVIEWER_LOGIN="reviewer[bot]",
            REVIEW_RECEIPT="",
        )
        self.review = {
            "user": {"login": self.env["REVIEWER_LOGIN"]},
            "commit_id": self.env["PR_HEAD_SHA"],
            "body": f"{self.env['PR_HEAD_SHA']}\n{self.env['REVIEW_MARKER']}\n",
            "state": "APPROVED",
        }
        self.step = WORKFLOW.read_text().split("- name: Verify review was posted\n", 1)[1]
        block = re.search(r"(?m)^( +)run: \|\n((?:\1 +.*\n|\n)+)", self.step)
        self.assertIsNotNone(block, "Receipt must have a literal Bash run block")
        self.command = textwrap.dedent(block[2])

    def receipt(self, pages, receipt_state="", status=0, raw=None):
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", self.command],
            cwd=self.directory,
            env={
                **self.env, "GH_RESPONSE": json.dumps(pages) if raw is None else raw,
                "GH_STATUS": str(status), "REVIEW_RECEIPT": receipt_state,
            },
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(json.loads((self.directory / "gh-args.json").read_text()), [
            "api", "--paginate", "--slurp", "repos/example/repo/pulls/7/reviews",
        ])
        return result

    def test_matching_receipt_passes_including_recovered_read(self):
        for state in ("APPROVED", "COMMENTED"):
            for receipt_state in ("", "required"):
                with self.subTest(state=state, receipt_state=receipt_state):
                    result = self.receipt([[], [{**self.review, "state": state}]], receipt_state)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejected_or_uncertain_post_stays_failed_after_reconciliation(self):
        for pages in ([[]], [[self.review]]):
            with self.subTest(pages=pages):
                self.assertNotEqual(self.receipt(pages, "failed").returncode, 0)

    def test_required_receipt_cannot_pass_without_all_contract_fields(self):
        for changes in (
            {"user": {"login": "other"}}, {"commit_id": "b" * 40},
            {"state": "PENDING"}, {"state": "DISMISSED"},
            {"body": self.env["PR_HEAD_SHA"]}, {"body": self.env["REVIEW_MARKER"]},
            {"body": None},
        ):
            with self.subTest(changes=changes):
                result = self.receipt([[{**self.review, **changes}]], "required")
                self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(self.receipt([[]], "required").returncode, 0)

    def test_read_failure_and_invalid_response_are_not_success(self):
        for pages in ([[]], [[self.review]]):
            with self.subTest(pages=pages):
                self.assertNotEqual(self.receipt(pages, "required", status=1).returncode, 0)
        self.assertNotEqual(self.receipt(None, "required", raw="not JSON").returncode, 0)

    def test_replacement_head_needs_its_own_receipt(self):
        self.env.update(PR_HEAD_SHA="b" * 40, REVIEW_MARKER="factory-review:124:1")
        self.assertNotEqual(self.receipt([[self.review]], "required").returncode, 0)
        replacement = {
            **self.review, "commit_id": self.env["PR_HEAD_SHA"],
            "body": f"{self.env['PR_HEAD_SHA']}\n{self.env['REVIEW_MARKER']}\n",
        }
        self.assertEqual(self.receipt([[self.review], [replacement]], "required").returncode, 0)

    def test_unknown_publication_state_fails(self):
        self.assertNotEqual(self.receipt([[self.review]], "unknown").returncode, 0)

    def test_publication_example_preserves_failed_attempt(self):
        publication = GUIDE.read_text().split("## Publication\n", 1)[1].split("## Skip and report", 1)[0]
        example = re.search(r"```sh\n(.*?)```", publication, re.DOTALL)
        self.assertIsNotNone(example)
        command = example[1].replace('"$GITHUB_ENV"', '"receipt-state"')
        state = self.directory / "receipt-state"
        calls = self.directory / "gh-args.json"

        def publish(status):
            return subprocess.run(
                ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", command],
                cwd=self.directory,
                env={**self.env, "GH_RESPONSE": "{}", "GH_STATUS": str(status)},
                capture_output=True, text=True, check=False,
            )

        self.assertNotEqual(publish(0).returncode, 0)
        self.assertFalse(calls.exists(), "Unreadable history must stop before POST")
        state.write_text("UNRELATED=preserved\n")
        self.assertNotEqual(publish(1).returncode, 0)
        self.assertEqual(json.loads(calls.read_text()), [
            "api", "--method", "POST", "repos/example/repo/pulls/7/reviews",
            "--input", "review.json",
        ])
        failed = state.read_text()
        self.assertEqual(failed, "UNRELATED=preserved\nREVIEW_RECEIPT=required\nREVIEW_RECEIPT=failed\n")
        calls.unlink()
        self.assertNotEqual(publish(0).returncode, 0)
        self.assertFalse(calls.exists(), "A rejected or uncertain POST must not be repeated")
        self.assertEqual(state.read_text(), failed)

    def test_condition_preserves_success_prerequisite_and_receipt_triggers(self):
        condition = self.step.split("if:", 1)[1].split("shell:", 1)[0].strip()
        condition = condition.removeprefix(">-").strip()
        condition = condition.removeprefix("${{").removesuffix("}}").strip()
        self.assertEqual({" ".join(term.split()) for term in condition.split("||")}, {
            "steps.worker.outputs.skipped != 'true'", "env.REVIEW_RECEIPT != ''",
        }, "Receipt gate must retain implicit success() and both receipt triggers")


if __name__ == "__main__":
    unittest.main()
