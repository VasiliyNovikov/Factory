import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/pr-review.yml"
REPO = "example/factory"
PR = f"repos/{REPO}/pulls/41"
LABEL = f"repos/{REPO}/issues/41/labels/factory-review-requested"
LABELS = f"repos/{REPO}/issues/41/labels"
SHA = "a" * 40
MARKER = "factory-review:123:1"


def workflow_step(name):
    lines = WORKFLOW.read_text().splitlines()
    start = lines.index(f"      - name: {name}")
    run = next(i for i in range(start + 1, len(lines)) if lines[i] == "        run: |")
    end = run + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith("          ")):
        end += 1
    return textwrap.dedent("\n".join(lines[run + 1:end]))


class ReviewWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.pr = {
            "state": "open",
            "draft": False,
            "head": {"sha": SHA, "repo": {"full_name": REPO}},
            "user": {"login": "factory-identity[bot]"},
            "body": "Corrected description",
            "labels": [{"name": "triaged"}, {"name": "factory-review-requested"}],
        }
        self.event = {
            "action": "labeled",
            "pull_request": copy.deepcopy(self.pr),
            "label": {"name": "factory-review-requested"},
            "sender": {"login": "factory-identity[bot]"},
        }
        self.review = {
            "user": {"login": "github-actions[bot]"},
            "commit_id": SHA,
            "state": "APPROVED",
            "body": f"Independent assessment.\n<!-- {MARKER} -->",
            "html_url": "https://github.com/example/factory/pull/41#pullrequestreview-1",
        }
        fake_gh = self.directory / "gh"
        fake_gh.write_text(textwrap.dedent("""\
            #!/usr/bin/env python3
            import json
            import os
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            method = args[args.index("--method") + 1] if "--method" in args else "GET"
            endpoint = next(arg for arg in args if arg.startswith("repos/"))
            key = method + " " + endpoint
            with open(os.environ["FAKE_GH_CALLS"], "a") as calls:
                calls.write(key + "\\n")
            fixture = json.loads(Path(os.environ["FAKE_GH_FIXTURE"]).read_text())
            if key == fixture["failure"]:
                sys.exit("GitHub API request failed")
            if key not in fixture["responses"]:
                sys.exit("Unexpected GitHub operation: " + key)
            print(json.dumps(fixture["responses"][key]))
        """))
        fake_gh.chmod(0o755)

    def execute(self, step, *, reviews=None, failure=None, remaining_labels=None):
        responses = {
            f"GET {PR}": self.pr,
            f"GET {PR}/reviews": [reviews if reviews is not None else [self.review]],
            f"DELETE {LABEL}": [],
            f"GET {LABELS}": [remaining_labels if remaining_labels is not None else [{"name": "triaged"}]],
        }
        fixture = self.directory / "fixture.json"
        fixture.write_text(json.dumps({"responses": responses, "failure": failure}))
        event = self.directory / "event.json"
        event.write_text(json.dumps(self.event))
        output = self.directory / "output"
        output.write_text("")
        calls = self.directory / "calls"
        calls.write_text("")
        env = dict(os.environ, PATH=f"{self.directory}:{os.environ['PATH']}",
                   GH_TOKEN="test-only", GITHUB_TOKEN="test-only",
                   GITHUB_REPOSITORY=REPO, GITHUB_EVENT_PATH=str(event),
                   GITHUB_OUTPUT=str(output), PR_NUMBER="41", PR_HEAD_SHA=SHA,
                   REVIEW_MARKER=MARKER, FAKE_GH_FIXTURE=str(fixture),
                   FAKE_GH_CALLS=str(calls))
        result = subprocess.run(["bash", "-euo", "pipefail", "-c", workflow_step(step)],
                                env=env, text=True, capture_output=True)
        return result, output.read_text(), calls.read_text().splitlines()

    def test_unchanged_head_followup_can_comment_or_approve(self):
        for state in ("COMMENTED", "APPROVED"):
            with self.subTest(state=state):
                self.review["state"] = state
                result, output, calls = self.execute("Check live review eligibility")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, "ready=true\n")
                self.assertEqual(calls, [f"GET {PR}"])
                result, _, _ = self.execute("Verify review was posted")
                self.assertEqual(result.returncode, 0, result.stderr)
                verified = json.loads(result.stdout)
                self.assertEqual(verified["state"], state)
                self.assertEqual(verified["commit_id"], SHA)
                result, _, calls = self.execute("Acknowledge review request")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [f"GET {PR}", f"DELETE {LABEL}", f"GET {LABELS}"])

    def test_description_correction_and_existing_commit_events(self):
        self.event["changes"] = {"body": {"from": "Old description"}}
        for action in ("edited", "opened", "synchronize", "reopened", "ready_for_review"):
            with self.subTest(action=action):
                self.event["action"] = action
                result, output, _ = self.execute("Check live review eligibility")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, "ready=true\n")

    def test_stale_ineligible_and_duplicate_events_do_not_enter_review(self):
        original_pr, original_event = copy.deepcopy(self.pr), copy.deepcopy(self.event)
        cases = [
            ({"state": "closed"}, {}),
            ({"draft": True}, {}),
            ({"head": {"sha": "b" * 40, "repo": {"full_name": REPO}}}, {}),
            ({"head": {"sha": SHA, "repo": {"full_name": "someone/fork"}}}, {}),
            ({"labels": [{"name": "triaged"}]}, {}),
            ({}, {"sender": {"login": "someone"}}),
            ({}, {"label": {"name": "triaged"}}),
            ({}, {"action": "edited", "changes": {"title": {"from": "Old title"}}}),
            ({}, {"action": "edited", "changes": {"body": {"from": self.pr["body"]}}}),
            ({"body": "A newer correction"}, {"action": "edited", "changes": {"body": {"from": "Old"}}}),
        ]
        for pr_change, event_change in cases:
            with self.subTest(pr=pr_change, event=event_change):
                self.pr = dict(copy.deepcopy(original_pr), **pr_change)
                self.event = dict(copy.deepcopy(original_event), **event_change)
                result, output, calls = self.execute("Check live review eligibility")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, "")
                self.assertEqual(calls, [f"GET {PR}"])

    def test_api_failures_are_not_successful_skips(self):
        for step, endpoint in (
            ("Check live review eligibility", f"GET {PR}"),
            ("Verify review was posted", f"GET {PR}/reviews"),
            ("Acknowledge review request", f"DELETE {LABEL}"),
            ("Acknowledge review request", f"GET {LABELS}"),
        ):
            with self.subTest(step=step, endpoint=endpoint):
                result, output, _ = self.execute(step, failure=endpoint)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, "")

    def test_result_requires_identity_commit_marker_and_submitted_state(self):
        invalid = [
            dict(self.review, user={"login": "someone"}),
            dict(self.review, commit_id="b" * 40),
            dict(self.review, body="factory-review:122:1"),
            dict(self.review, state="PENDING"),
            dict(self.review, state="DISMISSED"),
        ]
        for reviews in ([], [self.review, self.review], *[[review] for review in invalid]):
            with self.subTest(reviews=reviews):
                result, _, calls = self.execute("Verify review was posted", reviews=reviews)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(f"DELETE {LABEL}", calls)

    def test_self_approval_is_rejected_but_comment_is_allowed(self):
        self.pr["user"]["login"] = "github-actions[bot]"
        result, _, _ = self.execute("Verify review was posted")
        self.assertNotEqual(result.returncode, 0)
        self.review["state"] = "COMMENTED"
        result, _, _ = self.execute("Verify review was posted")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_revision_change_blocks_verification_and_acknowledgement(self):
        self.pr["head"]["sha"] = "b" * 40
        for step in ("Verify review was posted", "Acknowledge review request"):
            with self.subTest(step=step):
                result, _, calls = self.execute(step)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, [f"GET {PR}"])

    def test_acknowledgement_preserves_other_labels_and_checks_removal(self):
        self.pr["labels"] = [{"name": "triaged"}]
        result, _, calls = self.execute("Acknowledge review request")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [f"GET {PR}"])
        self.pr["labels"].append({"name": "factory-review-requested"})
        result, _, _ = self.execute("Acknowledge review request", remaining_labels=self.pr["labels"])
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
