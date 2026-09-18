import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/pr-review.yml"
IMPLEMENTATION = WORKFLOW.with_name("issue-implementation.yml")
REPO = "example/factory"
PR = f"repos/{REPO}/pulls/41"
LABEL = f"repos/{REPO}/issues/41/labels/factory-review-requested"
LABELS = f"repos/{REPO}/issues/41/labels"
SHA = "a" * 40
MARKER = "factory-review:123:1"


def workflow_step(name, workflow=WORKFLOW):
    lines = workflow.read_text().splitlines()
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
            "updated_at": "2026-09-18T12:00:00Z",
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
            "submitted_at": "2026-09-18T11:59:00Z",
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

    def execute(self, step, *, reviews=None, failure=None, remaining_labels=None,
                requested="true", workflow=WORKFLOW):
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
                   REVIEW_MARKER=MARKER, REVIEW_REQUESTED=requested, FAKE_GH_FIXTURE=str(fixture),
                   FAKE_GH_CALLS=str(calls))
        result = subprocess.run(["bash", "-euo", "pipefail", "-c", workflow_step(step, workflow)],
                                env=env, text=True, capture_output=True)
        return result, output.read_text(), calls.read_text().splitlines()

    def test_unchanged_head_followup_can_comment_or_approve(self):
        for state in ("COMMENTED", "APPROVED"):
            with self.subTest(state=state):
                self.review["state"] = state
                result, output, calls = self.execute("Check live review eligibility")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, "ready=true\nrequested=true\n")
                self.assertEqual(calls, [f"GET {PR}"])
                result, output, _ = self.execute("Verify review was posted")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, "posted=true\n")
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
                self.assertEqual(output, "ready=true\nrequested=true\n")

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
            ({"labels": []}, {"action": "edited", "changes": {"body": {"from": self.pr["body"]}}}),
            ({"labels": [], "body": "A newer correction"},
             {"action": "edited", "changes": {"body": {"from": "Old"}}}),
        ]
        for pr_change, event_change in cases:
            with self.subTest(pr=pr_change, event=event_change):
                self.pr = dict(copy.deepcopy(original_pr), **pr_change)
                self.event = dict(copy.deepcopy(original_event), **event_change)
                result, output, calls = self.execute("Check live review eligibility")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, "")
                self.assertEqual(calls, [f"GET {PR}"])

    def test_queued_events_only_skip_assessments_that_cover_the_event(self):
        self.pr["labels"] = []
        self.event["changes"] = {"body": {"from": "Old description"}}
        later_review = dict(self.review, submitted_at="2026-09-18T12:00:01Z")
        cases = [
            ([], True),
            ([self.review], True),
            ([dict(later_review, submitted_at=self.pr["updated_at"])], True),
            ([later_review], False),
            ([dict(later_review, commit_id="b" * 40)], True),
            ([dict(later_review, user={"login": "someone"})], True),
            ([dict(later_review, body="Unrelated review")], True),
            ([dict(later_review, state="PENDING")], True),
        ]
        for action in ("edited", "synchronize"):
            self.event["action"] = action
            for reviews, ready in cases:
                with self.subTest(action=action, reviews=reviews):
                    result, output, calls = self.execute("Check live review eligibility", reviews=reviews)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(output, "ready=true\nrequested=false\n" if ready else "")
                    self.assertEqual(calls, [f"GET {PR}", f"GET {PR}/reviews"])
        result, output, _ = self.execute("Check live review eligibility", failure=f"GET {PR}/reviews")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, "")

    def test_surviving_event_services_live_request_missing_from_its_payload(self):
        self.event["pull_request"]["labels"] = []
        self.event["changes"] = {"body": {"from": "An older description"}}
        self.event["pull_request"]["body"] = "A superseded description"
        for action in ("synchronize", "edited"):
            with self.subTest(action=action):
                self.event["action"] = action
                result, output, _ = self.execute("Check live review eligibility")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, "ready=true\nrequested=true\n")
                result, output, _ = self.execute("Verify review was posted")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, "posted=true\n")
                result, _, calls = self.execute("Acknowledge review request", requested="true")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"DELETE {LABEL}", calls)

    def test_api_failures_are_not_successful_skips(self):
        for step, endpoint in (
            ("Check live review eligibility", f"GET {PR}"),
            ("Verify review was posted", f"GET {PR}"),
            ("Verify review was posted", f"GET {PR}/reviews"),
            ("Acknowledge review request", f"GET {PR}"),
            ("Acknowledge review request", f"DELETE {LABEL}"),
            ("Acknowledge review request", f"GET {LABELS}"),
        ):
            with self.subTest(step=step, endpoint=endpoint):
                result, output, _ = self.execute(step, failure=endpoint)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, "")

    def test_malformed_pr_responses_are_failures_not_superseded_skips(self):
        self.event["workflow_run"] = {"head_sha": SHA, "pull_requests": [{"number": 41}]}
        for pr in (None, [], {}, dict(self.pr, head={"repo": {"full_name": REPO}})):
            self.pr = pr
            for step, workflow in (("Check live review eligibility", WORKFLOW),
                                   ("Verify review was posted", WORKFLOW),
                                   ("Check completed review revision", IMPLEMENTATION)):
                with self.subTest(pr=pr, step=step):
                    result, output, calls = self.execute(step, workflow=workflow)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(output, "")
                    self.assertEqual(calls, [f"GET {PR}"])

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
                result, output, calls = self.execute("Verify review was posted", reviews=reviews)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, "")
                self.assertNotIn(f"DELETE {LABEL}", calls)

    def test_self_approval_is_rejected_but_comment_is_allowed(self):
        self.pr["user"]["login"] = "github-actions[bot]"
        result, _, _ = self.execute("Verify review was posted")
        self.assertNotEqual(result.returncode, 0)
        self.review["state"] = "COMMENTED"
        result, _, _ = self.execute("Verify review was posted")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_superseded_review_skips_without_verifying_or_acknowledging(self):
        original = copy.deepcopy(self.pr)
        for change in ({"head": {"sha": "b" * 40, "repo": {"full_name": REPO}}},
                       {"state": "closed"}, {"draft": True}):
            with self.subTest(change=change):
                self.pr = dict(copy.deepcopy(original), **change)
                result, output, calls = self.execute("Verify review was posted")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("::notice::", result.stdout)
                self.assertEqual(output, "")
                self.assertEqual(calls, [f"GET {PR}"])
                result, _, calls = self.execute("Acknowledge review request")
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

    def test_acknowledgement_does_not_consume_a_later_request(self):
        self.event["action"] = "opened"
        self.event["pull_request"]["labels"] = [{"name": "triaged"}]
        self.pr["labels"] = [{"name": "triaged"}]
        result, output, _ = self.execute("Check live review eligibility")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, "ready=true\nrequested=false\n")
        self.pr["labels"].append({"name": "factory-review-requested"})
        result, _, calls = self.execute("Acknowledge review request", requested="false")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [f"GET {PR}"])

    def test_completed_review_revision_filter_preserves_head_merge_and_routing_fallback(self):
        self.event = {"workflow_run": {"head_sha": SHA, "pull_requests": [{"number": 41}]}}
        for head, merge, stale in ((SHA, "c" * 40, False), ("b" * 40, SHA, False),
                                   ("b" * 40, "c" * 40, True)):
            with self.subTest(head=head, merge=merge):
                self.pr["head"]["sha"] = head
                self.pr["merge_commit_sha"] = merge
                result, output, calls = self.execute("Check completed review revision",
                                                     workflow=IMPLEMENTATION)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, "stale=true\n" if stale else "")
                self.assertEqual(calls, [f"GET {PR}"])
        result, _, _ = self.execute("Check completed review revision", workflow=IMPLEMENTATION,
                                    failure=f"GET {PR}")
        self.assertNotEqual(result.returncode, 0)
        for associations in ([], [{"number": 41}, {"number": 42}]):
            self.event["workflow_run"]["pull_requests"] = associations
            result, output, calls = self.execute("Check completed review revision",
                                                 workflow=IMPLEMENTATION)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output, "")
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
