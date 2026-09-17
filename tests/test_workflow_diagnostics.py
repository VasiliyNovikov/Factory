import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/workflow-diagnostics.yml").read_text()


def step_script(name):
    step = WORKFLOW.split(f"      - name: {name}\n", 1)[1].split("\n      - name:", 1)[0]
    style, block = step.split("\n        run: ", 1)[1].split("\n", 1)
    block = textwrap.dedent(block)
    if style == "|":
        return block
    if style == ">-":
        return " ".join(block.splitlines())
    raise AssertionError(f"Unsupported run style: {style}")


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(prefix=".diagnostics-", dir=ROOT / "tests")
        self.addCleanup(workspace.cleanup)
        self.directory = Path(workspace.name)
        self.report_path = self.directory / "workflow-diagnostics/report.json"
        self.report_path.parent.mkdir()
        self.summary = self.directory / "summary"
        self.calls = self.directory / "calls"
        self.report = {
            "run_id": 200,
            "run_attempt": 2,
            "outcome": "analyzed",
            "summary": "Inspected the preceding diagnostics run and Tests; no new findings.",
            "created_issues": [],
            "unavailable_evidence": [],
            "errors": [],
        }
        self.issue = {
            "user": {"login": "factory-identity[bot]"},
            "body": "Finding.\n<!-- factory-diagnostics:200:2 -->",
            "labels": [],
        }
        self.issue_pages = [[]]
        self.list_call = [
            "api", "--paginate", "--slurp",
            "repos/example/factory/issues?state=all&creator=factory-identity[bot]&per_page=100",
        ]
        self.env = {
            "PATH": f"{self.directory}:{os.environ['PATH']}",
            "RUNNER_TEMP": str(self.directory),
            "GITHUB_STEP_SUMMARY": str(self.summary),
            "GITHUB_REPOSITORY": "example/factory",
            "GITHUB_RUN_ID": "200",
            "GITHUB_RUN_ATTEMPT": "3",
            "REPORT_ATTEMPT": "2",
            "GH_TOKEN": "read-only-app-token",
            "FACTORY_LOGIN": "factory-identity[bot]",
            "CALLS": str(self.calls),
        }
        gh = self.directory / "gh"
        gh.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "assert os.environ['GH_TOKEN'] == 'read-only-app-token'\n"
            "assert 'GITHUB_TOKEN' not in os.environ\n"
            "assert sys.argv[1] == 'api'\n"
            "with open(os.environ['CALLS'], 'a') as calls:\n"
            "    calls.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "if sys.argv[2:4] == ['--paginate', '--slurp']:\n"
            "    assert sys.argv[4:] == ['repos/example/factory/issues?state=all&creator=factory-identity[bot]&per_page=100']\n"
            "    print(os.environ['ISSUE_PAGES'])\n"
            "    if os.environ.get('LIST_FAIL') == 'true':\n"
            "        sys.exit('HTTP 403: issue listing interrupted')\n"
            "    sys.exit(0)\n"
            "assert sys.argv[2:] in (['repos/example/factory/issues/42'], ['repos/example/factory/issues/43'])\n"
            "if os.environ.get('API_FAIL') == 'true' or sys.argv[2].endswith('/' + os.environ.get('FAIL_ISSUE', '')):\n"
            "    sys.exit('HTTP 403: issue receipt unavailable')\n"
            "print(os.environ['ISSUE'])\n"
        )
        gh.chmod(0o755)

    def verify(self, *, raw=None, missing=False):
        self.summary.unlink(missing_ok=True)
        self.calls.unlink(missing_ok=True)
        self.report_path.unlink(missing_ok=True)
        if not missing:
            self.report_path.write_text(json.dumps(self.report) if raw is None else raw)
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c",
             step_script("Verify diagnostics result")],
            env={
                **self.env, "ISSUE": json.dumps(self.issue),
                "ISSUE_PAGES": json.dumps(self.issue_pages),
            },
            text=True, capture_output=True,
        )

    def assert_rejected(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("::error::", result.stdout)
        self.assertFalse(self.summary.exists(), "do not publish success after a failed check")

    def test_analyzed_report_with_no_findings_needs_no_issue(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.report["summary"], self.summary.read_text())
        self.assertIn("Created issues: []", self.summary.read_text())
        self.assertEqual([json.loads(line) for line in self.calls.read_text().splitlines()],
                         [self.list_call])

    def test_first_run_report_is_accepted_without_issues_or_gaps(self):
        self.report["outcome"] = "initialized"
        self.report["summary"] = "Initial boundary established; no analysis or issue creation."
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Outcome: initialized", self.summary.read_text())
        self.assertEqual([json.loads(line) for line in self.calls.read_text().splitlines()],
                         [self.list_call])
        for field in ("created_issues", "unavailable_evidence"):
            with self.subTest(field=field):
                self.report[field] = [42] if field == "created_issues" else ["gap"]
                self.assert_rejected(self.verify())
                self.report[field] = []

    def test_report_matches_producing_attempt_not_verification_retry(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        for field, value in (("run_id", 201), ("run_attempt", 3), ("run_id", "200")):
            with self.subTest(field=field, value=value):
                original = self.report[field]
                self.report[field] = value
                self.assert_rejected(self.verify())
                self.report[field] = original
        self.env["REPORT_ATTEMPT"] = ""
        self.assert_rejected(self.verify())

    def test_incomplete_or_error_reports_fail_even_without_findings(self):
        for outcome, errors in (
            ("incomplete", []), ("clean", []), (None, []),
            ("analyzed", ["HTTP 403"]), ("analyzed", "not an array"),
            ("initialized", ["history unavailable"]),
        ):
            with self.subTest(outcome=outcome, errors=errors):
                self.report.update(outcome=outcome, errors=errors)
                self.assert_rejected(self.verify())
                self.assertFalse(self.calls.exists())

    def test_missing_malformed_or_multiple_reports_fail(self):
        self.assert_rejected(self.verify(missing=True))
        valid = json.dumps(self.report)
        for raw in ("", "{broken", "null", "[]", valid + "\n" + valid):
            with self.subTest(raw=raw):
                self.assert_rejected(self.verify(raw=raw))
        for field in self.report:
            with self.subTest(missing_field=field):
                self.assert_rejected(self.verify(raw=json.dumps(
                    {key: value for key, value in self.report.items() if key != field}
                )))

    def test_summary_must_be_nonempty_text(self):
        for summary in ("", " \n\t ", None, [], 42):
            with self.subTest(summary=summary):
                self.report["summary"] = summary
                self.assert_rejected(self.verify())

    def test_issue_numbers_must_be_unique_positive_integers(self):
        for issues in (None, "42", [True], ["42"], [0], [-1], [1.5], [42, 42]):
            with self.subTest(issues=issues):
                self.report["created_issues"] = issues
                self.assert_rejected(self.verify())
                self.assertFalse(self.calls.exists())

    def test_expected_gaps_are_visible_not_a_clean_result(self):
        gap = "Expired logs confirmed for https://github.com/example/factory/actions/runs/100."
        self.report["unavailable_evidence"] = [gap]
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("::warning::", result.stdout)
        self.assertIn("not a clean result", self.summary.read_text())
        self.assertIn(gap, self.summary.read_text())
        self.report["errors"] = ["subagent did not finish"]
        self.assert_rejected(self.verify())

    def test_gaps_require_an_array_of_nonempty_descriptions(self):
        for gaps in (None, "gap", [""], ["  "], [42], [{}]):
            with self.subTest(gaps=gaps):
                self.report["unavailable_evidence"] = gaps
                self.assert_rejected(self.verify())

    def test_receipts_use_read_only_app_access_and_allow_later_triage_labels(self):
        self.report["created_issues"] = [42]
        self.issue["labels"] = [{"name": "factory-issue-42"}, {"name": "triaged"}]
        self.issue_pages = [[{**self.issue, "number": 42}]]
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [json.loads(line) for line in self.calls.read_text().splitlines()],
            [["api", "repos/example/factory/issues/42"], self.list_call],
        )
        self.assertIn("Created issues: [42]", self.summary.read_text())

    def test_wrong_author_marker_or_pr_receipts_fail(self):
        self.report["created_issues"] = [42]
        original = self.issue.copy()
        for fields in (
            {"user": {"login": "someone-else"}},
            {"body": None}, {"body": "No marker"},
            {"body": "<!-- factory-diagnostics:200:3 -->"},
            {"body": "<!-- factory-diagnostics:201:2 -->"},
            {"pull_request": {"url": "https://github.com/example/factory/pull/42"}},
        ):
            with self.subTest(fields=fields):
                self.issue = {**original, **fields}
                self.assert_rejected(self.verify())

    def test_receipt_api_failures_are_not_reported_as_success(self):
        self.report["created_issues"] = [42]
        self.env["API_FAIL"] = "true"
        result = self.verify()
        self.assert_rejected(result)
        self.assertIn("HTTP 403", result.stderr)

    def test_every_created_issue_is_checked_before_publishing_results(self):
        self.report["created_issues"] = [42, 43]
        self.issue_pages = [[{**self.issue, "number": 43}], [{**self.issue, "number": 42}]]
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls.read_text().splitlines()), 3)
        self.env["FAIL_ISSUE"] = "43"
        self.assert_rejected(self.verify())
        self.assertEqual(len(self.calls.read_text().splitlines()), 2)

    def test_unreported_marked_issues_fail_for_analyzed_and_initialized_reports(self):
        self.issue_pages = [[{**self.issue, "number": 42}]]
        for outcome in ("analyzed", "initialized"):
            with self.subTest(outcome=outcome):
                self.report["outcome"] = outcome
                result = self.verify()
                self.assert_rejected(result)
                self.assertIn("do not match created_issues", result.stdout)

    def test_unreported_closed_issue_on_later_page_is_rejected(self):
        self.report["created_issues"] = [42]
        self.issue_pages = [
            [{**self.issue, "number": 42}],
            [{**self.issue, "number": 43, "state": "closed"}],
        ]
        self.assert_rejected(self.verify())

    def test_listing_must_contain_every_reported_issue(self):
        self.report["created_issues"] = [42]
        self.assert_rejected(self.verify())

    def test_listing_ignores_other_attempts_authors_and_pull_requests(self):
        self.issue_pages = [[
            {**self.issue, "number": 41, "body": "<!-- factory-diagnostics:200:1 -->"},
            {**self.issue, "number": 42, "body": "<!-- factory-diagnostics:201:2 -->"},
            {**self.issue, "number": 43, "user": {"login": "someone-else"}},
            {**self.issue, "number": 44, "pull_request": {"url": "example"}},
            {**self.issue, "number": 45, "body": None},
        ]]
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_listing_failure_with_valid_partial_output_is_not_success(self):
        self.env["LIST_FAIL"] = "true"
        result = self.verify()
        self.assert_rejected(result)
        self.assertIn("Could not list Factory issue receipts", result.stdout)
        self.assertIn("HTTP 403", result.stderr)

    def test_initial_report_is_fail_closed_and_identifies_the_producing_attempt(self):
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c",
             step_script("Initialize diagnostics report")],
            env={**self.env, "DIAGNOSTICS_DIR": str(self.report_path.parent)},
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.report = json.loads(self.report_path.read_text())
        self.assertEqual((self.report["run_id"], self.report["run_attempt"]), (200, 3))
        self.assertEqual(self.report["outcome"], "incomplete")
        self.assertTrue(self.report["summary"])
        self.assertTrue(self.report["errors"])
        self.assertEqual(self.report["created_issues"], [])
        self.env["REPORT_ATTEMPT"] = "3"
        self.assert_rejected(self.verify())
        self.assertFalse(self.calls.exists())


class WorkflowTests(unittest.TestCase):
    def test_schedule_dispatch_default_branch_and_serialization(self):
        self.assertIn("schedule:\n    - cron: '0 0 * * *'\n  workflow_dispatch:", WORKFLOW)
        self.assertIn("group: workflow-diagnostics\n  cancel-in-progress: false", WORKFLOW)
        self.assertIn(
            "if: github.ref == format('refs/heads/{0}', github.event.repository.default_branch)",
            WORKFLOW,
        )
        self.assertIn("timeout-minutes: 30", WORKFLOW)

    def test_verifier_is_isolated_inline_and_read_only(self):
        diagnose, verify = WORKFLOW.split("\n  verify:\n")
        self.assertIn("needs: diagnose", verify)
        self.assertIn("!cancelled() && needs.diagnose.result != 'skipped'", verify)
        self.assertIn("permissions:\n      actions: read\n", verify)
        self.assertIn("permission-issues: read", verify)
        for unexpected in (
            "actions/checkout", "scripts/", "copilot", "permission-issues: write",
            "GITHUB_TOKEN:", "manifest_sha256",
        ):
            self.assertNotIn(unexpected, verify)
        self.assertIn("permission-issues: write", diagnose)
        self.assertIn("permission-pull-requests: read", diagnose)
        self.assertIn("persist-credentials: false", diagnose)
        self.assertIn("if: always()\n        uses: actions/upload-artifact@v4", diagnose)
        self.assertNotIn("runner.temp", diagnose.split("    steps:\n", 1)[0])
        self.assertIn(
            "env:\n          DIAGNOSTICS_DIR: ${{ runner.temp }}/workflow-diagnostics", diagnose
        )
        self.assertFalse((ROOT / "scripts/workflow-diagnostics.py").exists())

    def test_report_is_seeded_before_setup_and_handoff_paths_agree(self):
        diagnose, verify = WORKFLOW.split("\n  verify:\n")
        self.assertLess(diagnose.index("- name: Initialize diagnostics report"),
                        diagnose.index("- name: Check out invocation revision"))
        self.assertIn("if-no-files-found: error", diagnose)
        directories = re.findall(r"^          DIAGNOSTICS_DIR: (.+)$", diagnose, re.MULTILINE)
        self.assertEqual(len(directories), 2)
        self.assertEqual(directories[0], directories[1])
        upload = re.search(r"^          path: (.+)$", diagnose, re.MULTILINE)[1]
        download = re.search(r"^          path: (.+)$", verify, re.MULTILINE)[1]
        report = re.search(r'^          report="(.+)"$', verify, re.MULTILINE)[1]
        self.assertEqual(upload, f"{directories[0]}/report.json")
        self.assertEqual(download, directories[0])
        self.assertEqual(report.replace("${RUNNER_TEMP}", "${{ runner.temp }}"), upload)
        self.assertIn('> "$DIAGNOSTICS_DIR/report.json"',
                      step_script("Initialize diagnostics report"))

    def test_script_steps_use_explicit_bash_to_match_executed_tests(self):
        for name in ("Initialize diagnostics report", "Analyze workflows with parallel Copilot subagents",
                     "Verify diagnostics result"):
            with self.subTest(step=name):
                step = WORKFLOW.split(f"      - name: {name}\n", 1)[1].split("\n      - name:", 1)[0]
                self.assertIn("        shell: bash", step.splitlines())

    def test_artifact_and_report_attempt_use_the_producing_jobs_saved_outputs(self):
        diagnose, verify = WORKFLOW.split("\n  verify:\n")
        output = re.search(r"^      artifact_name: (.+)$", diagnose, re.MULTILINE)[1]
        upload = re.search(r"^          name: (.+)$", diagnose, re.MULTILINE)[1]
        download = re.search(r"^          name: (.+)$", verify, re.MULTILINE)[1]
        self.assertEqual(output, upload)
        self.assertEqual(download, "${{ needs.diagnose.outputs.artifact_name }}")
        self.assertIn("report_attempt: ${{ github.run_attempt }}", diagnose)
        self.assertIn("REPORT_ATTEMPT: ${{ needs.diagnose.outputs.report_attempt }}", verify)
        self.assertNotIn("${{ github.run_attempt }}", verify)
        for producer_attempt, verifier_attempt in ((1, 1), (1, 2), (2, 3), (3, 3)):
            with self.subTest(producer=producer_attempt, verifier=verifier_attempt):
                saved = output.replace("${{ github.run_id }}", "200").replace(
                    "${{ github.run_attempt }}", str(producer_attempt)
                )
                selected = download.replace("${{ needs.diagnose.outputs.artifact_name }}", saved)
                self.assertEqual(selected, f"workflow-diagnostics-200-{producer_attempt}")

    def test_workflow_run_router_checks_origin_and_branch_before_setup(self):
        workflow = (ROOT / ".github/workflows/issue-implementation.yml").read_text()
        route = workflow.split("\n  route:\n", 1)[1].split("\n  implement:\n", 1)[0]
        condition = re.search(r"^    if: >-\n(.*?)^    runs-on:", route, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(condition, "eligibility must gate the entire routing job")
        condition = " ".join(condition[1].split())
        self.assertIn(
            "(github.event_name != 'workflow_run' || "
            "(github.event.workflow_run.head_repository.full_name == github.repository && "
            "startsWith(github.event.workflow_run.head_branch, 'factory/issue-') && ",
            condition,
        )
        for name in ("issue-implementation", "issue-triage", "workflow-diagnostics"):
            self.assertIn(
                f"github.event.workflow_run.path != '.github/workflows/{name}.yml'", condition
            )
        self.assertNotIn(".github/workflows/tests.yml", condition)

    def test_fork_pull_requests_keep_read_only_test_coverage(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text()
        self.assertIn("on:\n  pull_request:\n  push:\n    branches: [master]\n", workflow)
        self.assertNotRegex(workflow, r"(?m)^\s+if:")
        self.assertNotIn("secrets.", workflow)
        self.assertIn("permissions:\n      contents: read\n", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("run: python3 -m unittest discover -s tests -v", workflow)

    def test_real_harness_receives_one_prompt_with_window_and_handoff_contracts(self):
        with tempfile.TemporaryDirectory(prefix=".prompt-", dir=ROOT / "tests") as directory:
            directory = Path(directory)
            arguments_file = directory / "arguments.json"
            copilot = directory / "copilot"
            copilot.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "with open(os.environ['ARGUMENTS_FILE'], 'w') as output:\n"
                "    json.dump(sys.argv[1:], output)\n"
                "sys.exit(int(os.environ.get('COPILOT_EXIT', '0')))\n"
            )
            copilot.chmod(0o755)
            env = {
                "PATH": f"{directory}:{os.environ['PATH']}",
                "ARGUMENTS_FILE": str(arguments_file),
                "DIAGNOSTICS_DIR": str(directory / "evidence"),
                "GITHUB_REPOSITORY": "example/factory",
                "GITHUB_RUN_ID": "200",
                "GITHUB_RUN_ATTEMPT": "3",
                "DEFAULT_BRANCH": "main",
                "FACTORY_LOGIN": "factory-identity[bot]",
            }
            result = subprocess.run(
                ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c",
                 step_script("Initialize diagnostics report")],
                cwd=ROOT, text=True, capture_output=True, env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report_path = directory / "evidence/report.json"
            initial_report = report_path.read_text()
            for exit_code in (0, 23):
                with self.subTest(copilot_exit=exit_code):
                    result = subprocess.run(
                        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c",
                         step_script("Analyze workflows with parallel Copilot subagents")],
                        cwd=ROOT, text=True, capture_output=True,
                        env={**env, "COPILOT_EXIT": str(exit_code)},
                    )
                    self.assertEqual(result.returncode, exit_code, result.stderr)
                    self.assertEqual(report_path.read_text(), initial_report)
            arguments = json.loads(arguments_file.read_text())
        self.assertEqual(arguments.count("--prompt"), 1)
        prompt = arguments[arguments.index("--prompt") + 1]
        for required in (
            "GH_TOKEN to GITHUB_TOKEN on that command", "Never change credentials globally",
            "main schedule or workflow_dispatch", "largest run_number strictly below",
            "If none exists after checking all pages", "do not analyze runs or logs",
            "launch subagents, or create issues", "API failure is not an empty history",
            "write an initialized report and stop",
            "previous (created_at, id) inclusive to current exclusive",
            "Rerunning an invocation must keep that original window",
            "ALL workflows and branches", "90 days", "1000 results", "including the parent",
            "one read-only Copilot subagent per workflow", "concurrently",
            "wait for every result", "issues AND PRs in all states",
            "Create issues without labels", "check the creation response for no labels",
            "<!-- factory-diagnostics:200:3 -->", "If there are no actionable findings",
            "Never assume an unexplained HTTP 404 means expiration",
            "including on partial failure",
        ):
            with self.subTest(required=required):
                self.assertIn(required, prompt)
        report = json.loads(prompt.split("Its exact shape is: ", 1)[1].split(". Use outcome", 1)[0])
        self.assertEqual((report["run_id"], report["run_attempt"]), (200, 3))
        self.assertEqual(report["outcome"], "incomplete")
        self.assertNotIn("workflow-diagnostics.py", prompt)


if __name__ == "__main__":
    unittest.main()
