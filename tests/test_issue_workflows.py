"""Execute real triage shell steps with a read-only gh double.

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

    def run_step(self, script, responses, *, event_name="issues", login="contributor"):
        # Keep scratch files inside the repository, never in the system temp dir.
        with tempfile.TemporaryDirectory(prefix=".issue-workflows-", dir=ROOT / "tests") as directory:
            work = Path(directory)
            (work / "gh").write_text(f"#!{sys.executable}\n" + GH_DOUBLE)
            (work / "gh").chmod(0o700)
            (work / "responses.json").write_text(json.dumps(responses))
            (work / "event.json").write_text(json.dumps({
                "comment": {"user": {"login": login}},
                "issue": issue(),
            }))
            (work / "output").touch()
            env = {
                **os.environ,
                "PATH": str(work) + os.pathsep + os.environ["PATH"],
                "MOCK_GH_ROOT": str(work),
                "GITHUB_REPOSITORY": "example/repository",
                "ISSUE_NUMBER": "26",
                "TRACKING_LABEL": TRACKING,
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
                ["bash", "--noprofile", "--norc", "-euo", "pipefail", "-c", script],
                cwd=work, env=env, text=True, capture_output=True, timeout=10,
            )
            calls = work / "calls.jsonl"
            actual = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
            self.assertNotIn("UNEXPECTED GH CALL", result.stderr, result.stderr)
            self.assertEqual(actual, [item["args"] for item in responses], result.stderr)
            return result, (work / "output").read_text()

    def verify_result(self, decision, parent=None, children=None, comments=None):
        responses = [response(
            ISSUE_API + "/comments",
            [[comment(decision)]] if comments is None else comments,
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
        self.assert_ok(self.verify_result("reply", comments=[[plan], [comment("reply")]]))
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
        for explanation in (
            "Please clarify the expected behavior.",
            "API failure after the plan and decomposed label; child #27 remains pending.",
        ):
            with self.subTest(explanation=explanation):
                result = self.verify_result("reply", comments=[[
                    comment(body=f"<!-- {MARKER} -->\n<!-- factory-triage:reply -->\n{explanation}")
                ]])
                self.assert_ok(result)
                self.assertIn("no completed handoff or decomposition claimed", result.stdout)

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
            "native children": [
                response(ISSUE_API + "/comments", [[comment("decomposed")]], paginated=True),
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
        self.assertIn("github.event.label.name == 'factory-triage-pending'", self.triage)
        self.assertIn("github.event.action != 'unlabeled'", self.triage)
        self.assertIn("github.event.issue.state == 'open'", self.triage)
        self.assertIn("!github.event.issue.pull_request", self.triage)
        for label in ("triaged", "factory-triage-pending"):
            self.assertIn(f"!contains(github.event.issue.labels.*.name, '{label}')", self.triage)
        self.assertNotIn("!contains(github.event.issue.labels.*.name, 'decomposed')", self.triage)
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
        for label in ("decomposed", "factory-triage-pending"):
            self.assertIn(
                f"!contains(github.event.issue.labels.*.name, '{label}')",
                self.implementation,
            )


if __name__ == "__main__":
    unittest.main()
