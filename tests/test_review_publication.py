import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/review-publication.sh"
FAKE_GH = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

path = Path(os.environ["GH_FIXTURE"])
fixture = json.loads(path.read_text())
args = sys.argv[1:]
method = args[args.index("--method") + 1] if "--method" in args else "GET"
endpoint = next((arg for arg in args if arg.startswith("repos/")), None)
call = {"method": method, "endpoint": endpoint, "args": args}
if "--input" in args:
    call["request"] = json.loads(Path(args[args.index("--input") + 1]).read_text())
fixture["calls"].append(call)
response = fixture["responses"].pop(0) if fixture["responses"] else {}
path.write_text(json.dumps(fixture))
if not args or args[0] != "api" or (method, endpoint) != (
    response.get("method"), response.get("endpoint")
):
    sys.exit("Unexpected gh call: " + repr(call))
if "error" in response:
    print(response["error"], file=sys.stderr)
else:
    print(json.dumps(response["body"]))
sys.exit(response.get("status", 0))
"""


class ReviewPublicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="review-publication-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        gh = self.directory / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.fixture = self.directory / "fixture.json"
        self.output = self.directory / "outputs"
        self.request = self.directory / "request.json"
        self.endpoint = "repos/example/repo/pulls/7"
        self.env = os.environ.copy()
        for name in (
            "GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN", "GITHUB_OUTPUT",
            "GITHUB_ENV", "GITHUB_PATH", "GITHUB_STATE", "GITHUB_STEP_SUMMARY",
        ):
            self.env.pop(name, None)
        self.env.update(
            PATH=f"{self.directory}{os.pathsep}{self.env['PATH']}",
            GH_FIXTURE=str(self.fixture),
            GITHUB_REPOSITORY="example/repo",
            PR_NUMBER="7",
            PR_HEAD_SHA="a" * 40,
            REVIEW_MARKER="factory-review:123:1",
            REVIEWER_LOGIN="reviewer[bot]",
        )
        self.pr = {
            "state": "open", "draft": False,
            "head": {"sha": self.env["PR_HEAD_SHA"], "repo": {"full_name": "example/repo"}},
            "base": {"repo": {"full_name": "example/repo"}},
            "user": {"login": "author"},
        }
        self.payload = {
            "event": "APPROVE",
            "commit_id": self.env["PR_HEAD_SHA"],
            "body": f"## TL;DR\nClean `{self.env['PR_HEAD_SHA']}`.\n"
                    f"<!-- {self.env['REVIEW_MARKER']} -->\n",
        }
        self.request.write_text(json.dumps(self.payload))

    def review(self, **changes):
        return {
            "id": 42, "user": {"login": self.env["REVIEWER_LOGIN"]},
            "commit_id": self.payload["commit_id"], "body": self.payload["body"],
            "state": "APPROVED" if self.payload["event"] == "APPROVE" else "COMMENTED",
            "html_url": "https://github.com/example/repo/pull/7#pullrequestreview-42",
            **changes,
        }

    def reviews(self, *pages, **changes):
        return {"method": "GET", "endpoint": self.endpoint + "/reviews",
                "body": list(pages) or [[]], **changes}

    def live_pr(self, **changes):
        return {"method": "GET", "endpoint": self.endpoint, "body": self.pr, **changes}

    def post(self, **changes):
        return {"method": "POST", "endpoint": self.endpoint + "/reviews",
                "body": self.review(), **changes}

    def run_helper(self, mode, responses, **environment):
        self.fixture.write_text(json.dumps({"responses": responses, "calls": []}))
        args = ["bash", str(SCRIPT), mode]
        if mode == "publish":
            args += [str(self.request), str(self.output)]
        result = subprocess.run(
            args, env={**self.env, **environment}, capture_output=True, text=True, check=False,
        )
        fixture = json.loads(self.fixture.read_text())
        self.assertEqual(fixture["responses"], [], result.stderr)
        for call in fixture["calls"]:
            if call["method"] == "GET" and call["endpoint"].endswith("/reviews"):
                self.assertIn("--paginate", call["args"])
                self.assertIn("--slurp", call["args"])
        self.calls = fixture["calls"]
        return result

    def outputs(self):
        return dict(line.split("=", 1) for line in self.output.read_text().splitlines())

    def assert_failed(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.outputs().get("review_failed"), "true")
        self.assertNotEqual(self.outputs().get("skipped"), "true")

    def test_false_live_eligibility_never_posts_and_can_skip(self):
        variants = [
            {"state": "closed"}, {"draft": True},
            {"head": {**self.pr["head"], "sha": "b" * 40}},
            {"head": {**self.pr["head"], "repo": {"full_name": "other/repo"}}},
            {"head": {**self.pr["head"], "repo": None}},
        ]
        for change in variants:
            with self.subTest(change=change):
                result = self.run_helper("publish", [
                    self.reviews(), self.live_pr(body={**self.pr, **change}),
                ])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.outputs(), {"skipped": "true"})
                self.assertTrue(all(call["method"] == "GET" for call in self.calls))
        result = self.run_helper("verify", [], REVIEW_SKIPPED="true")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_success_and_retry_reuse_exact_review_without_duplicate(self):
        for event in ("APPROVE", "COMMENT"):
            with self.subTest(event=event):
                self.output.write_text("")
                self.payload["event"] = event
                if event == "COMMENT":
                    self.payload["comments"] = [
                        {"path": "a.txt", "line": 1, "side": "RIGHT", "body": "Actionable finding"}
                    ]
                self.request.write_text(json.dumps(self.payload))
                result = self.run_helper("publish", [
                    self.reviews(), self.live_pr(), self.post(),
                    self.reviews([], [self.review()]),
                ])
                self.assertEqual(result.returncode, 0, result.stderr)
                posts = [call for call in self.calls if call["method"] == "POST"]
                self.assertEqual([call["request"] for call in posts], [self.payload])
                self.assertEqual(self.outputs(), {"review_attempted": "true"})
                result = self.run_helper("publish", [self.reviews([], [self.review()])])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(all(call["method"] == "GET" for call in self.calls))
                result = self.run_helper("verify", [self.reviews([], [self.review()])],
                                         REVIEW_ATTEMPTED="true")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejection_remains_failure_even_if_worker_claims_skip(self):
        result = self.run_helper("publish", [
            self.reviews(), self.live_pr(),
            self.post(status=1, error="HTTP 422: pull request has been updated"),
            self.reviews(),
        ])
        self.assert_failed(result)
        self.assertEqual(self.outputs()["review_attempted"], "true")
        result = self.run_helper("verify", [self.reviews()], REVIEW_SKIPPED="true",
                                 REVIEW_ATTEMPTED="true", REVIEW_FAILED="true")
        self.assertNotEqual(result.returncode, 0)
        result = self.run_helper("publish", [self.reviews()])
        self.assert_failed(result)
        self.assertTrue(all(call["method"] == "GET" for call in self.calls))

    def test_uncertain_but_accepted_submission_is_reconciled_without_erasing_error(self):
        result = self.run_helper("publish", [
            self.reviews(), self.live_pr(), self.post(status=1, error="connection reset"),
            self.reviews([self.review()]),
        ])
        self.assert_failed(result)
        self.assertIn(self.review()["html_url"], result.stdout)
        result = self.run_helper("publish", [self.reviews([self.review()])])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.outputs()["review_failed"], "true")
        result = self.run_helper("verify", [self.reviews([self.review()])],
                                 REVIEW_SKIPPED="true", REVIEW_ATTEMPTED="true",
                                 REVIEW_FAILED="true")
        self.assertNotEqual(result.returncode, 0)

    def test_attempt_flag_alone_prevents_missing_receipt_skip(self):
        result = self.run_helper("verify", [self.reviews()], REVIEW_SKIPPED="true",
                                 REVIEW_ATTEMPTED="true")
        self.assertNotEqual(result.returncode, 0)

    def test_initial_read_error_cannot_become_successful_skip(self):
        result = self.run_helper("publish", [
            self.reviews(status=1, error="HTTP 403"),
        ])
        self.assert_failed(result)
        self.assertNotIn("review_attempted", self.outputs())
        result = self.run_helper("verify", [self.reviews()],
                                 REVIEW_SKIPPED="true", REVIEW_FAILED="true")
        self.assertNotEqual(result.returncode, 0)

    def test_incomplete_eligibility_and_read_failure_are_not_stale(self):
        for response in (
            self.live_pr(body={}),
            self.live_pr(body={**self.pr, "base": {}}),
            self.live_pr(status=1, error="HTTP 403"),
        ):
            with self.subTest(response=response):
                self.output.write_text("")
                result = self.run_helper("publish", [self.reviews(), response])
                self.assert_failed(result)
                self.assertNotIn("review_attempted", self.outputs())

    def test_invalid_request_and_self_approval_never_post(self):
        self.request.write_text(json.dumps({**self.payload, "commit_id": "b" * 40}))
        self.assert_failed(self.run_helper("publish", []))
        self.request.write_text(json.dumps(self.payload))
        self.pr["user"]["login"] = self.env["REVIEWER_LOGIN"]
        self.assert_failed(self.run_helper("publish", [self.reviews(), self.live_pr()]))
        self.assertTrue(all(call["method"] == "GET" for call in self.calls))

    def test_pending_or_conflicting_existing_review_prevents_post(self):
        for review in (
            self.review(state="PENDING", body=""),
            self.review(body=self.payload["body"] + "different"),
            self.review(commit_id="b" * 40),
        ):
            with self.subTest(review=review):
                self.output.write_text("")
                result = self.run_helper("publish", [self.reviews([], [review])])
                self.assert_failed(result)
                self.assertEqual(self.outputs()["review_attempted"], "true")

    def test_success_response_requires_exact_readback(self):
        for reviews in (
            [], [self.review(body=self.payload["body"].rstrip("\n"))],
            [self.review(user={"login": "other"})], [self.review(commit_id="b" * 40)],
            [self.review(state="PENDING")], [self.review(), self.review(id=43)],
        ):
            with self.subTest(reviews=reviews):
                self.output.write_text("")
                result = self.run_helper("publish", [
                    self.reviews(), self.live_pr(), self.post(), self.reviews(reviews),
                ])
                self.assert_failed(result)

    def test_post_reconciliation_read_failure_preserves_attempt(self):
        result = self.run_helper("publish", [
            self.reviews(), self.live_pr(), self.post(),
            self.reviews(status=1, error="HTTP 502"),
        ])
        self.assert_failed(result)
        self.assertEqual(self.outputs()["review_attempted"], "true")

    def test_receipt_requires_all_existing_contract_fields(self):
        for changes in (
            {"user": {"login": "other"}}, {"commit_id": "b" * 40}, {"state": "PENDING"},
            {"body": self.env["PR_HEAD_SHA"]}, {"body": self.env["REVIEW_MARKER"]},
        ):
            with self.subTest(changes=changes):
                result = self.run_helper("verify", [self.reviews([self.review(**changes)])])
                self.assertNotEqual(result.returncode, 0)

    def test_replacement_head_uses_its_own_marker_and_assessment(self):
        previous = self.review()
        self.env.update(PR_HEAD_SHA="b" * 40, REVIEW_MARKER="factory-review:124:1")
        self.pr["head"]["sha"] = self.env["PR_HEAD_SHA"]
        self.payload.update(commit_id=self.env["PR_HEAD_SHA"],
                            body=f"{self.env['PR_HEAD_SHA']} {self.env['REVIEW_MARKER']}")
        self.request.write_text(json.dumps(self.payload))
        result = self.run_helper("publish", [
            self.reviews([previous]), self.live_pr(), self.post(),
            self.reviews([previous], [self.review()]),
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call["request"] for call in self.calls if call["method"] == "POST"],
                         [self.payload])


if __name__ == "__main__":
    unittest.main()
