"""Execute real workflow shell steps with a strictly matched gh double.

The static contract tests inspect event filters and AI instructions only: they
do not establish that Copilot or GitHub carried out a decomposition correctly.
Run with: python3 -B -m unittest discover -s tests -v
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TRIAGE = ROOT / ".github/workflows/issue-triage.yml"
IMPLEMENTATION = ROOT / ".github/workflows/issue-implementation.yml"
LOGIN = "example-factory[bot]"
MARKER = "factory-triage-run:123:2"
TRACKING = "factory-issue-26"
ISSUE_API = "repos/example/repository/issues/26"


def step_run(path, name, style="|"):
    """Extract one named step with a strict, known workflow indentation."""
    lines = path.read_text().splitlines()
    starts = [i for i, line in enumerate(lines) if line == f"      - name: {name}"]
    if len(starts) != 1:
        raise AssertionError(f"Expected exactly one step named {name!r}")
    start = starts[0] + 1
    end = next(
        (i for i in range(start, len(lines))
         if lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) <= 6),
        len(lines),
    )
    runs = [i for i in range(start, end) if lines[i] == f"        run: {style}"]
    if len(runs) != 1:
        raise AssertionError(f"Expected one {style!r} run block in {name!r}")
    body = []
    for line in lines[runs[0] + 1:end]:
        if line.strip() and not line.startswith("          "):
            raise AssertionError(f"Unexpected run indentation in {name!r}: {line!r}")
        body.append(line[10:] if line.strip() else "")
    if not body or not any(body):
        raise AssertionError(f"Empty run block in {name!r}")
    return "\n".join(body) + "\n"


def issue(labels=(), *, number=26, state="open", children=0, pr=False):
    result = {
        "id": 10000 + number,
        "number": number,
        "state": state,
        "labels": [{"name": label} for label in labels],
        "sub_issues_summary": {"total": children},
    }
    if pr:
        result["pull_request"] = {"url": "https://example.invalid/pull/26"}
    return result


def factory_pr(**overrides):
    return {
        **issue([TRACKING, "triaged"], number=27, pr=True),
        "user": {"login": LOGIN},
        "merged": False,
        "head": {
            "ref": "factory/issue-26",
            "sha": "head-sha",
            "repo": {"full_name": "example/repository"},
        },
        "base": {"ref": "master", "repo": {"full_name": "example/repository"}},
        "merge_commit_sha": "merge-sha",
        **overrides,
    }


def implementation_event(*, source_pr=""):
    return {
        "repository": {"full_name": "example/repository"},
        "issue": issue(number=27, pr=True) if source_pr else issue(),
        "pull_request": factory_pr(),
        "workflow_run": {
            "head_repository": {"full_name": "example/repository"},
            "head_branch": "factory/issue-26",
            "head_sha": "head-sha",
            "pull_requests": [{"number": 27}],
        },
    }


def comment(decision="ready", *, login=LOGIN, marker=MARKER, body=None):
    return {
        "user": {"login": login},
        "body": (
            f"<!-- {marker} -->\n<!-- factory-triage:{decision} -->"
            if body is None else body
        ),
    }


def response(endpoint, value=None, *, paginated=False, error=False):
    return {
        "args": ["api"] + (["--paginate", "--slurp"] if paginated else []) + [endpoint],
        "value": value,
        "error": error,
    }


GH_DOUBLE = r"""
import json
import os
from pathlib import Path
import sys

root = Path(os.environ["MOCK_GH_ROOT"])
calls = root / "calls.jsonl"
previous = calls.read_text().splitlines() if calls.exists() else []
args = sys.argv[1:]
with calls.open("a") as log:
    log.write(json.dumps(args) + "\n")
responses = json.loads((root / "responses.json").read_text())
if len(previous) >= len(responses) or args != responses[len(previous)]["args"]:
    print("UNEXPECTED GH CALL: " + repr(args), file=sys.stderr)
    sys.exit(97)
item = responses[len(previous)]
if item["error"]:
    print("mock GitHub API unavailable", file=sys.stderr)
    sys.exit(1)
print(json.dumps(item["value"]))
"""


class ShellStepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for command in ("bash", "jq"):
            if shutil.which(command) is None:
                raise RuntimeError(f"{command} is required to test the workflow shell steps")
        cls.eligibility = step_run(TRIAGE, "Check live triage eligibility")
        cls.verify = step_run(TRIAGE, "Verify triage result")
        cls.validate_route = step_run(IMPLEMENTATION, "Validate implementation route")
        cls.implementation_eligibility = step_run(IMPLEMENTATION, "Check implementation eligibility")
        cls.blocked_report = step_run(IMPLEMENTATION, "Report blocked implementation")
        cls.implementation_verify = step_run(IMPLEMENTATION, "Verify Factory result")

    def run_step(self, script, responses, *, event_name="issues", login="contributor",
                 source_pr="", tracking=TRACKING, issue_number="26", reply_number=None,
                 event_payload=None):
        # The gh shim must be executable even on systems with a noexec temp dir.
        with tempfile.TemporaryDirectory(prefix=".issue-workflows-", dir=ROOT / "tests") as directory:
            work = Path(directory)
            (work / "gh").write_text(f"#!{sys.executable}\n" + GH_DOUBLE)
            (work / "gh").chmod(0o700)
            (work / "responses.json").write_text(json.dumps(responses))
            (work / "event.json").write_text(json.dumps({
                **(implementation_event(source_pr=source_pr)
                   if event_payload is None else event_payload),
                "comment": {"user": {"login": login}},
            }))
            (work / "output").touch()
            env = {
                **os.environ,
                "PATH": str(work) + os.pathsep + os.environ["PATH"],
                "MOCK_GH_ROOT": str(work),
                "GITHUB_REPOSITORY": "example/repository",
                "GITHUB_SERVER_URL": "https://github.com",
                "GITHUB_RUN_ID": "123",
                "GITHUB_RUN_ATTEMPT": "2",
                "ISSUE_NUMBER": issue_number,
                "SOURCE_PR": source_pr,
                "REPLY_NUMBER": (source_pr or issue_number) if reply_number is None else reply_number,
                "TRACKING_LABEL": tracking,
                "DEFAULT_BRANCH": "master",
                "RESULT_MARKER": MARKER,
                "FACTORY_LOGIN": LOGIN,
                "GH_TOKEN": "not-a-real-token",
                "GITHUB_TOKEN": "not-a-real-token",
                "GITHUB_EVENT_NAME": event_name,
                "GITHUB_EVENT_PATH": str(work / "event.json"),
                "GITHUB_OUTPUT": str(work / "output"),
                "GH_PROMPT_DISABLED": "1",
            }
            result = subprocess.run(
                ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
                cwd=work, env=env, text=True, capture_output=True, timeout=10,
            )
            calls = work / "calls.jsonl"
            actual = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
            self.assertNotIn("UNEXPECTED GH CALL", result.stderr, result.stderr)
            self.assertEqual(actual, [item["args"] for item in responses], result.stderr)
            return result, (work / "output").read_text()

    def verify_result(self, decision, parent=None, children=None, comments=None):
        if comments is None:
            comments = [[comment(decision)]]
            if decision == "decomposed":
                comments[0].insert(0, comment(
                    body="<!-- factory-decomposition-plan -->\nExisting stable child keys.",
                ))
        responses = [response(
            ISSUE_API + "/comments",
            comments,
            paginated=True,
        )]
        if parent is not None:
            responses.append(response(ISSUE_API, parent))
        if children is not None:
            responses.append(response(ISSUE_API + "/sub_issues", children, paginated=True))
        return self.run_step(self.verify, responses)[0]

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_rejected(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_live_eligibility_uses_live_state_and_preserves_decomposed_repair(self):
        cases = {
            "ordinary": (issue(), True),
            "unrelated labels": (issue(["bug"]), True),
            "decomposed repair": (issue(["decomposed"]), True),
            "already triaged": (issue(["triaged"]), False),
            "closed after event": (issue(state="closed"), False),
            "pull request": (issue(pr=True), False),
            "pending child": (issue(["factory-triage-pending"]), False),
            "pending decomposed": (issue(["decomposed", "factory-triage-pending"]), False),
        }
        for name, (live_issue, eligible) in cases.items():
            with self.subTest(name=name):
                result, output = self.run_step(
                    self.eligibility, [response(ISSUE_API, live_issue)],
                    event_name="issue_comment",
                )
                self.assert_ok(result)
                self.assertEqual(output, "ready=true\n" if eligible else "")

    def test_factory_comments_skip_without_an_api_call_but_other_bots_do_not(self):
        result, output = self.run_step(
            self.eligibility, [], event_name="issue_comment", login=LOGIN,
        )
        self.assert_ok(result)
        self.assertEqual(output, "")
        for event, author in (("issue_comment", "another[bot]"), ("issues", LOGIN)):
            with self.subTest(event=event, author=author):
                result, output = self.run_step(
                    self.eligibility, [response(ISSUE_API, issue())],
                    event_name=event, login=author,
                )
                self.assert_ok(result)
                self.assertEqual(output, "ready=true\n")

    def test_eligibility_api_failure_does_not_emit_ready(self):
        result, output = self.run_step(self.eligibility, [response(ISSUE_API, error=True)])
        self.assert_rejected(result)
        self.assertEqual(output, "")

    def test_implementation_precondition_checks_original_issue_on_every_event_path(self):
        for event in ("issues", "issue_comment", "pull_request_review", "workflow_run"):
            with self.subTest(event=event):
                result, _ = self.run_step(self.implementation_eligibility, [
                    response(ISSUE_API, issue([TRACKING, "triaged", "bug"])),
                    response(ISSUE_API + "/comments", [[], []], paginated=True),
                ], event_name=event, source_pr="" if event == "issues" else "27")
                self.assert_ok(result)

    def test_implementation_precondition_rejects_unsafe_live_state_on_every_event_path(self):
        cases = {
            "closed": issue([TRACKING, "triaged"], state="closed"),
            "pull request": issue([TRACKING, "triaged"], pr=True),
            "missing triaged": issue([TRACKING]),
            "missing tracking": issue(["triaged"]),
            "wrong tracking": issue(["triaged", "factory-issue-27"]),
            "conflicting tracking": issue([TRACKING, "triaged", "factory-issue-27"]),
            "duplicate tracking": issue([TRACKING, TRACKING, "triaged"]),
            "decomposed": issue([TRACKING, "triaged", "decomposed"]),
            "pending": issue([TRACKING, "triaged", "factory-triage-pending"]),
            "native children": issue([TRACKING, "triaged"], children=1),
        }
        for event in ("issues", "issue_comment", "pull_request_review", "workflow_run"):
            for name, parent in cases.items():
                with self.subTest(event=event, state=name):
                    result, _ = self.run_step(self.implementation_eligibility, [
                        response(ISSUE_API, parent),
                    ], event_name=event, source_pr="" if event == "issues" else "27")
                    self.assert_rejected(result)
                    self.assertIn("Live issue is not eligible", result.stdout)

    def test_implementation_precondition_rejects_mismatched_routing_identity(self):
        result, _ = self.run_step(self.implementation_eligibility, [
            response(ISSUE_API, issue(["factory-issue-27", "triaged"])),
        ], tracking="factory-issue-27")
        self.assert_rejected(result)

    def test_implementation_route_accepts_issue_and_pr_event_destinations(self):
        for event, source_pr in (
            ("issues", ""), ("issue_comment", ""), ("issue_comment", "27"),
            ("pull_request_review", "27"), ("workflow_run", "27"),
        ):
            with self.subTest(event=event, source_pr=source_pr):
                responses = (
                    [response("repos/example/repository/pulls/27", factory_pr())]
                    if source_pr else []
                )
                result, _ = self.run_step(
                    self.validate_route, responses, event_name=event, source_pr=source_pr,
                )
                self.assert_ok(result)

    def test_invalid_routed_identifiers_cannot_reach_any_consumer(self):
        for field, error in (
            ("issue_number", "Routed issue number must be a positive integer"),
            ("reply_number", "Routed reply number must be a positive integer"),
            ("source_pr", "Routed source PR must be empty or a positive integer"),
        ):
            invalid = ("", "0", "026", "-26", "26/comments", "26?state=all", "26\n27",
                       "issue-26", " 26", "26 ", "+26", "26.0", "\u0662\u0666")
            if field == "source_pr":
                invalid = invalid[1:]
            for value in invalid:
                for consumer in (
                    self.implementation_eligibility, self.blocked_report, self.implementation_verify,
                ):
                    with self.subTest(field=field, value=value, consumer=consumer[:40]):
                        values = {field: value}
                        if field == "source_pr":
                            values["reply_number"] = "27"
                        result, _ = self.run_step(
                            self.validate_route + "\n" + consumer, [], **values,
                        )
                        self.assert_rejected(result)
                        self.assertIn(error, result.stdout)

    def test_inconsistent_routing_identity_is_rejected_before_api_calls(self):
        for values in (
            {"reply_number": "27"},
            {"source_pr": "27", "reply_number": "26"},
            {"source_pr": "27", "reply_number": "28"},
            {"tracking": "factory-issue-27"},
            {"tracking": "factory-issue-26\nfactory-issue-27"},
        ):
            with self.subTest(values=values):
                result, _ = self.run_step(
                    self.validate_route, [], **values,
                )
                self.assert_rejected(result)
                self.assertIn("Routed tracking label or reply destination is inconsistent", result.stdout)

    def test_routed_destinations_must_belong_to_the_triggering_event(self):
        cases = [
            ("issues", "27", implementation_event(source_pr="27")),
            ("issue_comment", "27", implementation_event()),
            ("issue_comment", "", implementation_event(source_pr="27")),
            ("pull_request_review", "", implementation_event()),
            ("pull_request_review", "28", implementation_event(source_pr="27")),
            ("workflow_run", "", implementation_event()),
            ("workflow_dispatch", "27", implementation_event(source_pr="27")),
        ]
        for overrides in (
            {"head_repository": {"full_name": "another/repository"}},
            {"head_branch": "factory/issue-28"},
            {"pull_requests": [{"number": 28}]},
            {"pull_requests": None},
        ):
            event = implementation_event(source_pr="27")
            event["workflow_run"].update(overrides)
            cases.append(("workflow_run", "27", event))
        wrong_repository = implementation_event()
        wrong_repository["repository"]["full_name"] = "another/repository"
        cases.append(("issues", "", wrong_repository))
        for event_name, source_pr, event in cases:
            with self.subTest(event=event_name, source_pr=source_pr, payload=event):
                result, _ = self.run_step(
                    self.validate_route, [], event_name=event_name,
                    source_pr=source_pr, event_payload=event,
                )
                self.assert_rejected(result)
                self.assertIn("Routed destination does not match the triggering event", result.stdout)

    def test_route_requires_an_eligible_live_source_pr(self):
        valid = factory_pr()
        for changes in (
            {"number": 28}, {"state": "closed"}, {"merged": True},
            {"user": {"login": "another[bot]"}},
            {"head": {**valid["head"], "repo": {"full_name": "another/repository"}}},
            {"head": {**valid["head"], "ref": "factory/issue-28"}},
            {"base": {**valid["base"], "ref": "other"}},
            {"base": {**valid["base"], "repo": {"full_name": "another/repository"}}},
            *({"labels": issue(labels)["labels"]} for labels in (
                [TRACKING], ["triaged"], ["factory-issue-28", "triaged"],
                [TRACKING, TRACKING, "triaged"], [TRACKING, "factory-issue-28", "triaged"],
                [TRACKING, "triaged", "decomposed"], [TRACKING, "triaged", "factory-triage-pending"],
            )),
        ):
            with self.subTest(changes=changes):
                result, _ = self.run_step(
                    self.validate_route, [
                        response("repos/example/repository/pulls/27", factory_pr(**changes)),
                    ], event_name="pull_request_review", source_pr="27",
                )
                self.assert_rejected(result)
                self.assertIn("Routed source PR is not eligible for this issue", result.stdout)

    def test_ci_routes_require_current_revision_with_or_without_explicit_association(self):
        for associations in ([], [{"number": 27}]):
            for revision in ("head-sha", "merge-sha", "stale-sha"):
                with self.subTest(associations=associations, revision=revision):
                    event = implementation_event(source_pr="27")
                    event["workflow_run"].update(
                        pull_requests=associations, head_sha=revision,
                    )
                    result, _ = self.run_step(
                        self.validate_route, [
                            response("repos/example/repository/pulls/27", factory_pr()),
                        ], event_name="workflow_run", source_pr="27", event_payload=event,
                    )
                    if revision == "stale-sha":
                        self.assert_rejected(result)
                        self.assertIn("CI revision no longer matches", result.stdout)
                    else:
                        self.assert_ok(result)

    def test_route_api_failure_cannot_reach_reporting_or_verification(self):
        for consumer in (self.blocked_report, self.implementation_verify):
            with self.subTest(consumer=consumer[:40]):
                result, _ = self.run_step(
                    self.validate_route + "\n" + consumer, [
                        response("repos/example/repository/pulls/27", error=True),
                    ], event_name="pull_request_review", source_pr="27",
                )
                self.assert_rejected(result)
                self.assertIn("mock GitHub API unavailable", result.stderr)

    def test_implementation_precondition_checks_factory_plans_on_all_comment_pages(self):
        for author in (LOGIN, "contributor", "another[bot]"):
            with self.subTest(author=author):
                result, _ = self.run_step(self.implementation_eligibility, [
                    response(ISSUE_API, issue([TRACKING, "triaged"])),
                    response(ISSUE_API + "/comments", [
                        [comment(body="Earlier discussion."), {"user": {"login": LOGIN}, "body": None}],
                        [comment(login=author, body="<!-- factory-decomposition-plan -->")],
                    ], paginated=True),
                ])
                if author == LOGIN:
                    self.assert_rejected(result)
                    self.assertIn("A planned decomposition cannot be implemented directly", result.stdout)
                else:
                    self.assert_ok(result)

    def test_implementation_precondition_api_failures_stop_implementation(self):
        for responses in (
            [response(ISSUE_API, error=True)],
            [response(ISSUE_API, issue([TRACKING, "triaged"])),
             response(ISSUE_API + "/comments", paginated=True, error=True)],
        ):
            with self.subTest(endpoint=responses[-1]["args"][-1]):
                result, _ = self.run_step(self.implementation_eligibility, responses)
                self.assert_rejected(result)
                self.assertIn("mock GitHub API unavailable", result.stderr)

    def test_blocked_implementation_reports_in_triggering_conversation_and_verifies_author(self):
        for source_pr in ("", "27"):
            with self.subTest(source_pr=source_pr):
                body = (
                    "Implementation blocked for #26: live eligibility failed or could not be verified. "
                    "No implementation or review-thread changes were attempted; feedback remains outstanding.\n\n"
                    "The issue must be open, have triaged and exactly its own tracking label, and have no "
                    "decomposed/pending state, native children, or Factory decomposition plan. "
                    "See the [failed eligibility check]"
                    "(https://github.com/example/repository/actions/runs/123/attempts/2) "
                    "for the rejected condition or API error.\n\n"
                    "[Issue](https://github.com/example/repository/issues/26)"
                )
                if source_pr:
                    body += " | [PR](https://github.com/example/repository/pull/27)"
                body += f"\n\n<!-- {MARKER} -->"
                endpoint = f"repos/example/repository/issues/{source_pr or '26'}/comments"
                posted = comment(body=body)
                post = {
                    "args": ["api", "--method", "POST", endpoint, "-f", f"body={body}",
                             "--jq", "{id, html_url, author: .user.login}"],
                    "value": posted,
                    "error": False,
                }
                result, _ = self.run_step(self.blocked_report, [post], source_pr=source_pr)
                self.assert_ok(result)
                for author in (LOGIN, "another[bot]"):
                    verified, _ = self.run_step(self.implementation_verify, [
                        response(endpoint, [[comment(login=author, body=body)]], paginated=True),
                    ], source_pr=source_pr)
                    if author == LOGIN:
                        self.assert_ok(verified)
                    else:
                        self.assert_rejected(verified)
                failed, _ = self.run_step(
                    self.blocked_report, [{**post, "error": True}], source_pr=source_pr,
                )
                self.assert_rejected(failed)
                self.assertIn("mock GitHub API unavailable", failed.stderr)

    def test_implementation_result_api_failure_is_not_verified(self):
        result, _ = self.run_step(self.implementation_verify, [
            response(ISSUE_API + "/comments", paginated=True, error=True),
        ])
        self.assert_rejected(result)
        self.assertIn("mock GitHub API unavailable", result.stderr)

    def test_ready_accepts_own_tracking_and_unrelated_labels(self):
        self.assert_ok(self.verify_result("ready", issue([TRACKING, "triaged", "bug"])))

    def test_ready_rejects_factory_decomposition_plans_on_any_comment_page(self):
        plan = comment(body="<!-- factory-decomposition-plan -->\nExisting stable child keys.")
        unrelated = comment(body="Earlier discussion.")
        for pages in (
            [[plan], [comment()]],
            [[unrelated] * 100, [plan], [comment()]],
        ):
            with self.subTest(plan_page=1 if pages[0] == [plan] else 2):
                result = self.verify_result("ready", comments=pages)
                self.assert_rejected(result)
                self.assertIn("A planned decomposition cannot be handed directly to implementation", result.stdout)

    def test_ready_ignores_decomposition_plan_markers_from_non_factory_authors(self):
        for author in ("contributor", "another[bot]"):
            with self.subTest(author=author):
                self.assert_ok(self.verify_result(
                    "ready", issue([TRACKING, "triaged"]),
                    comments=[
                        [comment(login=author, body="<!-- factory-decomposition-plan -->")],
                        [comment()],
                    ],
                ))

    def test_factory_decomposition_plan_still_allows_reply_or_completed_decomposition(self):
        plan = comment(body="<!-- factory-decomposition-plan -->\nExisting stable child keys.")
        self.assert_ok(self.verify_result(
            "reply", issue(["decomposed"], children=1), comments=[[plan], [comment("reply")]],
        ))
        self.assert_ok(self.verify_result(
            "decomposed", issue(["decomposed"], children=1), [[issue(number=27)]],
            comments=[[plan], [comment("decomposed")]],
        ))

    def test_ready_rejects_missing_conflicting_and_unsafe_handoffs(self):
        cases = {
            "missing tracking": issue(["triaged"]),
            "missing triaged": issue([TRACKING]),
            "wrong tracking": issue(["factory-issue-27", "triaged"]),
            "conflicting tracking": issue([TRACKING, "factory-issue-27", "triaged"]),
            "duplicate tracking": issue([TRACKING, TRACKING, "triaged"]),
            "decomposed": issue([TRACKING, "triaged", "decomposed"]),
            "pending": issue([TRACKING, "triaged", "factory-triage-pending"]),
            "closed": issue([TRACKING, "triaged"], state="closed"),
            "pull request": issue([TRACKING, "triaged"], pr=True),
            "one native child": issue([TRACKING, "triaged"], children=1),
            "multiple native children": issue([TRACKING, "triaged"], children=2),
        }
        for name, parent in cases.items():
            with self.subTest(name=name):
                self.assert_rejected(self.verify_result("ready", parent))

    def test_reply_accepts_clarification_or_partial_failure_without_claiming_success(self):
        for parent, explanation in (
            (issue(["bug"]), "Please clarify the expected behavior."),
            (issue([TRACKING]), "Adding triaged failed after the tracking label was verified."),
            (issue(["decomposed"], children=1),
             "API failure after the plan and decomposed label; child #27 remains pending."),
            (issue(state="closed"), "The issue was closed during assessment; no changes made."),
        ):
            with self.subTest(explanation=explanation):
                result = self.verify_result("reply", parent, comments=[[
                    comment(body=f"<!-- {MARKER} -->\n<!-- factory-triage:reply -->\n{explanation}")
                ]])
                self.assert_ok(result)
                self.assertIn("no completed handoff or decomposition claimed", result.stdout)

    def test_reply_rejects_a_live_implementation_handoff(self):
        for parent in (
            issue(["triaged"]),
            issue([TRACKING, "triaged"]),
            issue(["decomposed", "triaged"], children=1),
            issue(["triaged"], state="closed"),
        ):
            with self.subTest(parent=parent):
                result = self.verify_result("reply", parent)
                self.assert_rejected(result)
                self.assertIn("A reply requires the live issue to remain untriaged", result.stdout)

    def test_result_comment_pagination_ignores_other_runs_authors_and_null_bodies(self):
        pages = [
            [comment(marker="factory-triage-run:123:1"), comment(login="another[bot]"),
             {"user": {"login": LOGIN}, "body": None}],
            [comment()],
        ]
        self.assert_ok(self.verify_result("ready", issue([TRACKING, "triaged"]), comments=pages))

    def test_result_requires_exactly_one_factory_run_comment(self):
        cases = {
            "no comments": [[]],
            "no run marker": [[comment(body="<!-- factory-triage:ready -->")]],
            "old attempt": [[comment(marker="factory-triage-run:123:1")]],
            "wrong author": [[comment(login="another[bot]")]],
            "duplicate same page": [[comment(), comment()]],
            "duplicate across pages": [[comment()], [comment()]],
        }
        for name, comments in cases.items():
            with self.subTest(name=name):
                self.assert_rejected(self.verify_result("ready", comments=comments))

    def test_result_requires_one_and_only_one_decision_marker(self):
        for markers in (
            "",
            "<!-- factory-triage:unknown -->",
            "<!-- factory-triage:ready -->\n<!-- factory-triage:reply -->",
            "<!-- factory-triage:decomposed -->\n<!-- factory-triage:reply -->",
            "<!-- factory-triage:ready -->\n<!-- factory-triage:ready -->",
        ):
            with self.subTest(markers=markers):
                self.assert_rejected(self.verify_result(
                    "ready", comments=[[comment(body=f"<!-- {MARKER} -->\n{markers}")]],
                ))

    def test_decomposed_accepts_native_children_with_own_or_no_tracking(self):
        for labels in (["decomposed"], ["decomposed", TRACKING, "bug"]):
            with self.subTest(parent_labels=labels):
                self.assert_ok(self.verify_result(
                    "decomposed", issue(labels, children=3),
                    [[issue(number=27)],
                     [issue(["factory-issue-28", "triaged"], number=28),
                      issue(["decomposed"], number=29)]],
                ))

    def test_decomposed_requires_a_factory_decomposition_plan(self):
        cases = {
            "missing plan": [],
            "contributor plan": [
                comment(login="contributor", body="<!-- factory-decomposition-plan -->"),
            ],
            "other bot plan": [
                comment(login="another[bot]", body="<!-- factory-decomposition-plan -->"),
            ],
            "null Factory body": [{"user": {"login": LOGIN}, "body": None}],
        }
        for name, plan_comments in cases.items():
            with self.subTest(name=name):
                result = self.verify_result(
                    "decomposed", issue(["decomposed"], children=1),
                    comments=[[comment("decomposed")], plan_comments],
                )
                self.assert_rejected(result)
                self.assertIn(
                    "A decomposed result requires the durable Factory decomposition plan",
                    result.stdout,
                )

    def test_decomposed_accepts_factory_plans_on_any_comment_page(self):
        plan = comment(body="<!-- factory-decomposition-plan -->\nExisting stable child keys.")
        for plan_page in range(3):
            with self.subTest(plan_page=plan_page):
                pages = [[comment(body="Earlier discussion.")] * 100, [], [comment("decomposed")]]
                pages[plan_page].append(plan)
                self.assert_ok(self.verify_result(
                    "decomposed", issue(["decomposed"], children=1), [[issue(number=27)]],
                    comments=pages,
                ))

    def test_decomposed_rejects_unsafe_parent_states(self):
        cases = {
            "missing decomposed": issue(),
            "triaged": issue(["decomposed", "triaged"]),
            "closed": issue(["decomposed"], state="closed"),
            "pending": issue(["decomposed", "factory-triage-pending"]),
            "pull request": issue(["decomposed"], pr=True),
            "wrong tracking": issue(["decomposed", "factory-issue-27"]),
            "duplicate tracking": issue(["decomposed", TRACKING, TRACKING]),
        }
        for name, parent in cases.items():
            with self.subTest(name=name):
                self.assert_rejected(self.verify_result("decomposed", parent))

    def test_decomposed_requires_actual_native_children_not_just_a_summary(self):
        self.assert_rejected(self.verify_result(
            "decomposed", issue(["decomposed"], children=2), [[]],
        ))
        self.assert_ok(self.verify_result(
            "decomposed", issue(["decomposed"], children=1), [[], [issue(number=27)]],
        ))

    def test_decomposed_checks_every_child_on_every_page(self):
        cases = {
            "pending": issue(["factory-triage-pending"], number=28),
            "closed pending": issue(["factory-triage-pending"], number=28, state="closed"),
            "inherited parent tracking": issue([TRACKING], number=28),
            "other tracking": issue(["factory-issue-29"], number=28),
            "own and inherited tracking": issue(["factory-issue-28", TRACKING], number=28),
            "duplicate own tracking": issue(["factory-issue-28", "factory-issue-28"], number=28),
            "triaged without own tracking": issue(["triaged"], number=28),
            "triaged and decomposed": issue(["factory-issue-28", "triaged", "decomposed"], number=28),
            "triaged and decomposed without tracking": issue(["triaged", "decomposed"], number=28),
            "pull request": issue(number=28, pr=True),
        }
        for name, child in cases.items():
            with self.subTest(name=name):
                self.assert_rejected(self.verify_result(
                    "decomposed", issue(["decomposed"], children=2),
                    [[issue(number=27)], [child]],
                ))

    def test_result_api_failures_are_not_reported_as_verified(self):
        cases = {
            "comments": [response(ISSUE_API + "/comments", paginated=True, error=True)],
            "parent": [
                response(ISSUE_API + "/comments", [[comment()]], paginated=True),
                response(ISSUE_API, error=True),
            ],
            "reply parent": [
                response(ISSUE_API + "/comments", [[comment("reply")]], paginated=True),
                response(ISSUE_API, error=True),
            ],
            "native children": [
                response(ISSUE_API + "/comments", [[
                    comment(body="<!-- factory-decomposition-plan -->\nExisting stable child keys."),
                    comment("decomposed"),
                ]], paginated=True),
                response(ISSUE_API, issue(["decomposed"])),
                response(ISSUE_API + "/sub_issues", paginated=True, error=True),
            ],
        }
        for name, responses in cases.items():
            with self.subTest(name=name):
                result, _ = self.run_step(self.verify, responses)
                self.assert_rejected(result)
                self.assertIn("mock GitHub API unavailable", result.stderr)
                self.assertNotIn("Verified", result.stdout)


class StaticContractTests(unittest.TestCase):
    """Text contracts, not execution of GitHub events or AI instructions."""

    @classmethod
    def setUpClass(cls):
        cls.triage = TRIAGE.read_text()
        cls.implementation = IMPLEMENTATION.read_text()
        cls.triage_condition = cls.triage.split("  triage:\n    if: >-\n", 1)[1].split(
            "\n    runs-on:", 1,
        )[0]
        cls.route_condition = cls.implementation.split("  route:\n    if: >-\n", 1)[1].split(
            "\n    runs-on:", 1,
        )[0]
        cls.prompt = " ".join(step_run(TRIAGE, "Triage issue with Copilot", ">-").split())
        cls.route = " ".join(step_run(IMPLEMENTATION, "Route event with Copilot", ">-").split())
        cls.implement = " ".join(step_run(
            IMPLEMENTATION, "Reason about issue and implement or reply", ">-",
        ).split())

    def test_static_guidance_prefers_cohesive_bounded_work(self):
        guidance = " ".join((ROOT / "AGENTS.md").read_text().split())
        for text in (
            "Decompose code, documentation, workflows, issues, and PRs into cohesive",
            "Keep tightly coupled changes together and avoid fragmentation",
            "Give each issue and PR a bounded scope and verifiable acceptance criteria",
            "Make dependencies and shared context explicit",
            "use native sub-issues",
            "A decomposed parent tracks the whole outcome rather than receiving its own implementation handoff",
        ):
            with self.subTest(contract=text):
                self.assertIn(text, guidance)

    def test_static_child_release_event_and_queue_filters(self):
        self.assertRegex(self.triage, r"issues:\s+types: \[opened, unlabeled\]")
        self.assertIn("github.event.label.name == 'factory-triage-pending'", self.triage_condition)
        self.assertIn("github.event.action != 'unlabeled'", self.triage_condition)
        self.assertIn("github.event.issue.state == 'open'", self.triage_condition)
        self.assertIn("!github.event.issue.pull_request", self.triage_condition)
        for label in ("triaged", "factory-triage-pending"):
            self.assertIn(f"!contains(github.event.issue.labels.*.name, '{label}')", self.triage_condition)
        self.assertNotIn("!contains(github.event.issue.labels.*.name, 'decomposed')", self.triage_condition)
        self.assertIn("cancel-in-progress: false", self.triage)

    def test_static_durable_plan_protects_parent_before_creation_and_supports_retries(self):
        for text in (
            "First persist a parent comment marked <!-- factory-decomposition-plan -->",
            "stable per-child keys",
            "Reuse and reconcile an existing Factory plan",
            "Add decomposed to the parent and verify it BEFORE creating any children",
            "do not add triaged or a new tracking label to the parent",
            "issues in ALL states with pagination, not search alone",
            "<!-- factory-child:${GITHUB_REPOSITORY}#${ISSUE_NUMBER}:KEY -->",
            "${FACTORY_LOGIN} author",
            "failed link or a lost creation response",
            "Do not use replace_parent",
            "refresh all-state issues and recover the exact marker before retrying",
            "if the outcome cannot be established, stop and report it",
        ):
            with self.subTest(contract=text):
                self.assertIn(text, self.prompt)

    def test_static_native_api_uses_database_id_not_issue_number(self):
        for text in (
            "paginated GET repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/sub_issues",
            "POST repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/sub_issues",
            "integer sub_issue_id set to the child's database id, NOT its issue number",
            "GET repos/${GITHUB_REPOSITORY}/issues/CHILD_NUMBER/parent, checking the parent id",
            "For a child whose issue and repository access were verified, a /parent HTTP 404",
            "message 'No parent issue found' means it has no parent yet",
            "link the eligible child and re-check",
            "Other 404 responses, permission errors, and ambiguous failures are not evidence of missing parentage",
        ):
            with self.subTest(contract=text):
                self.assertIn(text, self.prompt)

    def test_static_cross_repository_children_require_explanation_not_assumed_triage(self):
        self.assertIn("existing native children in this repository covering that scope", self.prompt)
        self.assertIn(
            "explain cross-repository work rather than assuming it runs this triage",
            self.prompt,
        )
        self.assertIn("Create each genuinely missing child in this repository", self.prompt)

    def test_static_children_are_released_only_after_verified_setup_then_triaged_independently(self):
        for text in (
            "Include factory-triage-pending IN the creation request",
            "After ALL intended links, scopes, and dependency references are verified, remove",
            "factory-triage-pending from each open pending child using the App token",
            "A closed pending child still blocks completed setup",
            "report factory-triage:reply instead of clearing the label or claiming decomposition",
            "That unlabeled event starts normal child triage; do not triage children yourself",
            "Do not re-add pending to already released children",
            "Children may need clarification or further decomposition",
            "only their own normal ready path assigns factory-issue-CHILD_NUMBER",
            "verifies it, then adds triaged separately",
            "parent remains open and decomposed without triaged",
            "none is still pending before posting <!-- factory-triage:decomposed -->",
            "A partial failure gets factory-triage:reply",
            "exactly one decision marker in one new result comment",
        ):
            with self.subTest(contract=text):
                self.assertIn(text, self.prompt)

    def test_static_ready_handoff_and_existing_parent_safeguards(self):
        for text in (
            "as one cohesive implementation",
            "Avoid unnecessary fragmentation; keep tightly coupled work together",
            "Once there is a decomposed label, a Factory decomposition plan, or native sub-issues",
            "NEVER hand the parent directly to implementation",
            "add ${TRACKING_LABEL} FIRST and verify it is the only tracking label",
            "adding triaged in a separate request",
            "Recheck that no decomposition or pending state appeared",
        ):
            with self.subTest(contract=text):
                self.assertIn(text, self.prompt)

    def test_static_implementation_rejects_tracking_parents_in_all_feedback_paths(self):
        for prompt in (self.route, self.implement):
            for safeguard in ("decomposed", "factory-triage-pending", "native sub-issues",
                              "Factory decomposition plan"):
                with self.subTest(prompt=prompt[:50], safeguard=safeguard):
                    self.assertIn(safeguard, prompt)
        self.assertIn("including through PR or CI feedback", self.route)
        self.assertIn("check the original issue too", self.route)
        self.assertIn("Neither the issue nor PR may be decomposed or factory-triage-pending", self.implement)
        self.assertIn("instead of implementing it or removing its safeguards", self.implement)
        self.assertIn("Ignore ${FACTORY_LOGIN}'s own comments/reviews", self.route)

    def test_static_each_issue_event_clause_rejects_decomposed_and_pending_work(self):
        for event in ("issues", "issue_comment"):
            clause = self.route_condition.split(
                f"(github.event_name != '{event}' ||", 1,
            )[1].split("(github.event_name != ", 1)[0]
            for label in ("decomposed", "factory-triage-pending"):
                with self.subTest(event=event, label=label):
                    self.assertIn(f"!contains(github.event.issue.labels.*.name, '{label}')", clause)

    def test_static_workflow_runs_require_same_repository_before_routing(self):
        clause = " ".join(self.route_condition.split(
            "(github.event_name != 'workflow_run' ||", 1,
        )[1].split())
        self.assertTrue(clause.startswith(
            "(github.event.workflow_run.head_repository.full_name == github.repository &&"
        ), clause)
        self.assertIn(
            """contains(fromJSON('["failure", "timed_out"]'), github.event.workflow_run.conclusion)""",
            clause,
        )
        self.assertIn("github.event.workflow_run.conclusion == 'success'", clause)
        self.assertIn("github.event.workflow_run.path == '.github/workflows/pr-review.yml'", clause)

    def test_static_failed_precondition_blocks_agent_but_reports_and_verifies(self):
        validation = self.implementation.split(
            "      - name: Validate implementation route\n", 1,
        )[1].split("      - name:", 1)[0]
        self.assertIn("        id: validated-route\n", validation)
        self.assertLess(
            self.implementation.index("- name: Validate implementation route"),
            self.implementation.index("- name: Check implementation eligibility"),
        )
        self.assertLess(
            self.implementation.index("- name: Check implementation eligibility"),
            self.implementation.index("- name: Reason about issue and implement or reply"),
        )
        for name, condition in (
            ("Report blocked implementation",
             "if: failure() && steps.validated-route.outcome == 'success' && "
             "steps.eligibility.outcome == 'failure'"),
            ("Verify Factory result",
             "if: ${{ !cancelled() && steps.validated-route.outcome == 'success' && "
             "(success() || steps.eligibility.outcome == 'failure') }}"),
        ):
            with self.subTest(step=name):
                step = self.implementation.split(
                    f"      - name: {name}\n", 1,
                )[1].split("      - name:", 1)[0]
                self.assertIn(condition, step)

    def test_static_regression_suite_runs_in_ci(self):
        workflow = (ROOT / ".github/workflows/workflow-checks.yml").read_text()
        self.assertRegex(workflow, r"on:\s+pull_request:\s+push:\s+branches: \[master\]")
        self.assertIn("run: python3 -B -m unittest discover -s tests -v", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("persist-credentials: false", workflow)

    def test_static_regression_checks_cancel_superseded_runs_per_ref(self):
        workflow = (ROOT / ".github/workflows/workflow-checks.yml").read_text()
        self.assertIn(
            "\nconcurrency:\n"
            "  group: workflow-checks-${{ github.ref }}\n"
            "  cancel-in-progress: true\n",
            workflow,
        )

    def test_static_tested_steps_use_explicit_bash_failure_semantics(self):
        for path, names in (
            (TRIAGE, ("Check live triage eligibility", "Verify triage result")),
            (IMPLEMENTATION, ("Validate implementation route", "Check implementation eligibility",
                              "Report blocked implementation", "Verify Factory result")),
        ):
            for name in names:
                with self.subTest(workflow=path.name, step=name):
                    step = path.read_text().split(f"      - name: {name}\n", 1)[1].split(
                        "      - name:", 1,
                    )[0]
                    self.assertIn("        shell: bash\n", step)


if __name__ == "__main__":
    unittest.main()
