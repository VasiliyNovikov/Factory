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
            "updated_at": "2026-09-18T12:00:00Z",
            "labels": [{"name": "triaged"}],
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

    def execute(self, *, result="reviewed", requested="true", reviews=None,
                failure=None, overrides=None):
        responses = {
            f"GET {PR}": self.pr,
            f"GET {PR}/reviews": [reviews if reviews is not None else [self.review]],
        }
        responses.update(overrides or {})
        fixture = self.directory / "fixture.json"
        fixture.write_text(json.dumps({"responses": responses, "failure": failure}))
        event = self.directory / "event.json"
        event.write_text(json.dumps(self.event))
        calls = self.directory / "calls"
        calls.write_text("")
        env = dict(os.environ, PATH=f"{self.directory}:{os.environ['PATH']}",
                   GH_TOKEN="test-only", GITHUB_TOKEN="test-only",
                   GITHUB_REPOSITORY=REPO, GITHUB_EVENT_PATH=str(event),
                   PR_NUMBER="41", PR_HEAD_SHA=SHA, REVIEW_RESULT=result,
                   REVIEW_MARKER=MARKER, REVIEW_REQUESTED=requested, FAKE_GH_FIXTURE=str(fixture),
                   FAKE_GH_CALLS=str(calls))
        process = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", workflow_step("Verify review result")],
            env=env, text=True, capture_output=True)
        return process, calls.read_text().splitlines()

    def test_unchanged_head_followup_can_comment_or_approve(self):
        for state in ("COMMENTED", "APPROVED"):
            with self.subTest(state=state):
                self.review["state"] = state
                result, calls = self.execute()
                self.assertEqual(result.returncode, 0, result.stderr)
                verified = json.loads(result.stdout)
                self.assertEqual(verified["outcome"], "reviewed")
                self.assertEqual(verified["state"], state)
                self.assertEqual(verified["commit_id"], SHA)
                self.assertEqual(calls, [f"GET {PR}", f"GET {PR}/reviews"])

    def test_duplicate_skip_requires_a_covering_review_without_a_captured_request(self):
        self.event["changes"] = {"body": {"from": "Old description"}}
        later_review = dict(self.review, submitted_at="2026-09-18T12:00:01Z")
        cases = [
            ([], False),
            ([self.review], False),
            ([dict(later_review, submitted_at=self.pr["updated_at"])], False),
            ([later_review], True),
            ([dict(later_review, commit_id="b" * 40)], False),
            ([dict(later_review, user={"login": "someone"})], False),
            ([dict(later_review, body="Unrelated review")], False),
            ([dict(later_review, state="PENDING")], False),
            ([dict(later_review, submitted_at=None)], False),
            ([dict(later_review, submitted_at={})], False),
        ]
        for action in ("edited", "synchronize"):
            self.event["action"] = action
            for reviews, allowed in cases:
                with self.subTest(action=action, reviews=reviews):
                    result, calls = self.execute(result="skipped", requested="false", reviews=reviews)
                    self.assertEqual(result.returncode == 0, allowed, result.stderr)
                    if allowed:
                        self.assertEqual(json.loads(result.stdout), {"outcome": "skipped"})
                    self.assertEqual(calls, [f"GET {PR}", f"GET {PR}/reviews"])
        result, _ = self.execute(result="skipped", reviews=[later_review])
        self.assertNotEqual(result.returncode, 0)
        for updated_at in (None, ""):
            with self.subTest(updated_at=updated_at):
                self.event["pull_request"]["updated_at"] = updated_at
                result, _ = self.execute(result="skipped", requested="false", reviews=[later_review])
                self.assertNotEqual(result.returncode, 0)

    def test_surviving_event_can_verify_request_missing_from_its_payload(self):
        self.event["pull_request"]["labels"] = []
        self.event["changes"] = {"body": {"from": "An older description"}}
        self.event["pull_request"]["body"] = "A superseded description"
        for action in ("synchronize", "edited"):
            with self.subTest(action=action):
                self.event["action"] = action
                result, calls = self.execute()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["outcome"], "reviewed")
                self.assertEqual(calls, [f"GET {PR}", f"GET {PR}/reviews"])

    def test_api_failures_are_not_successful_skips(self):
        for outcome in ("reviewed", "skipped"):
            for endpoint in (f"GET {PR}", f"GET {PR}/reviews"):
                with self.subTest(outcome=outcome, endpoint=endpoint):
                    result, _ = self.execute(result=outcome, requested="false", failure=endpoint)
                    self.assertNotEqual(result.returncode, 0)

    def test_malformed_api_responses_fail_instead_of_skipping(self):
        cases = [
            (f"GET {PR}", None),
            (f"GET {PR}", []),
            (f"GET {PR}", {}),
            (f"GET {PR}", dict(self.pr, head={"repo": {"full_name": REPO}})),
            (f"GET {PR}", dict(self.pr, user=None)),
            (f"GET {PR}", dict(self.pr, labels=None)),
            (f"GET {PR}/reviews", None),
            (f"GET {PR}/reviews", {}),
            (f"GET {PR}/reviews", [None]),
        ]
        for endpoint, response in cases:
            for outcome in ("reviewed", "skipped"):
                with self.subTest(endpoint=endpoint, response=response, outcome=outcome):
                    result, _ = self.execute(result=outcome, requested="false",
                                             overrides={endpoint: response})
                    self.assertNotEqual(result.returncode, 0)

    def test_result_requires_identity_commit_exact_marker_and_submitted_state(self):
        invalid = [
            dict(self.review, user={"login": "someone"}),
            dict(self.review, commit_id="b" * 40),
            dict(self.review, body="factory-review:122:1"),
            dict(self.review, body="<!-- factory-review:123:10 -->"),
            dict(self.review, state="PENDING"),
            dict(self.review, state="DISMISSED"),
        ]
        for reviews in ([], [self.review, self.review], *[[review] for review in invalid]):
            with self.subTest(reviews=reviews):
                result, calls = self.execute(reviews=reviews)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, [f"GET {PR}", f"GET {PR}/reviews"])

    def test_self_approval_is_rejected_but_comment_is_allowed(self):
        self.pr["user"]["login"] = "github-actions[bot]"
        result, _ = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.review["state"] = "COMMENTED"
        result, _ = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_superseded_result_never_claims_a_verified_review_or_mutates_labels(self):
        original = copy.deepcopy(self.pr)
        for change in ({"head": {"sha": "b" * 40, "repo": {"full_name": REPO}}},
                       {"state": "closed"}, {"draft": True},
                       {"head": {"sha": SHA, "repo": {"full_name": "someone/fork"}}}):
            with self.subTest(change=change):
                self.pr = dict(copy.deepcopy(original), **change)
                result, calls = self.execute(reviews=[])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {"outcome": "superseded"})
                self.assertEqual(calls, [f"GET {PR}", f"GET {PR}/reviews"])

    def test_acknowledgement_is_required_only_for_captured_requests(self):
        self.pr["labels"].append({"name": "factory-review-requested"})
        result, _ = self.execute()
        self.assertNotEqual(result.returncode, 0)
        result, calls = self.execute(requested="false")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "reviewed")
        self.assertEqual(calls, [f"GET {PR}", f"GET {PR}/reviews"])

    def test_consumed_label_skip_requires_an_absent_request(self):
        result, _ = self.execute(result="skipped", requested="false", reviews=[])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"outcome": "skipped"})
        self.pr["labels"].append({"name": "factory-review-requested"})
        result, _ = self.execute(result="skipped", requested="false", reviews=[])
        self.assertNotEqual(result.returncode, 0)

    def test_description_skip_requires_unchanged_or_superseded_context(self):
        self.event["action"] = "edited"
        for previous, live in (("Corrected description", "Corrected description"),
                               ("Old description", "A newer correction")):
            with self.subTest(previous=previous, live=live):
                self.event["changes"] = {"body": {"from": previous}}
                self.pr["body"] = live
                result, _ = self.execute(result="skipped", requested="false", reviews=[])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {"outcome": "skipped"})
                result, _ = self.execute(result="skipped", requested="true", reviews=[])
                self.assertNotEqual(result.returncode, 0)

    def test_missing_result_or_capture_cannot_hide_incomplete_work(self):
        for head in (SHA, "b" * 40):
            self.pr["head"]["sha"] = head
            for outcome, requested in (("", "true"), ("failed", "false"),
                                        ("reviewed", ""), ("skipped", "unknown")):
                with self.subTest(head=head, outcome=outcome, requested=requested):
                    result, _ = self.execute(result=outcome, requested=requested)
                    self.assertNotEqual(result.returncode, 0)

    def test_all_review_pages_must_contain_exactly_one_run_result(self):
        for pages, allowed in (([[], [self.review]], True),
                               ([[self.review], [self.review]], False)):
            with self.subTest(pages=pages):
                result, _ = self.execute(overrides={f"GET {PR}/reviews": pages})
                self.assertEqual(result.returncode == 0, allowed, result.stderr)


if __name__ == "__main__":
    unittest.main()
