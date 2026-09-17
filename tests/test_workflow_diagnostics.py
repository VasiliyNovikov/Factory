import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workflow-diagnostics.py"
SPEC = importlib.util.spec_from_file_location("workflow_diagnostics", SCRIPT)
diagnostics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostics)

REPOSITORY = "example/factory"
SERVER = "https://github.example"
START = "2026-09-16T08:00:00Z"
END = "2026-09-17T08:00:00Z"


def make_run(run_id, **overrides):
    run = {
        "id": run_id,
        "run_number": run_id,
        "run_attempt": 1,
        "workflow_id": 7,
        "name": "Diagnostics",
        "path": ".github/workflows/workflow-diagnostics.yml",
        "event": "schedule",
        "status": "completed",
        "conclusion": "success",
        "html_url": f"{SERVER}/{REPOSITORY}/actions/runs/{run_id}",
        "head_branch": "main",
        "head_sha": "a" * 40,
        "created_at": START,
        "run_started_at": START,
        "updated_at": START,
    }
    run.update(overrides)
    return run


def run_page(runs, total=None):
    return {
        "total_count": len(runs) if total is None else total,
        "workflow_runs": runs,
    }


def paginated_responses(runs):
    return [
        run_page(runs[:100], total=len(runs)),
        [
            run_page(runs[offset:offset + 100], total=len(runs))
            for offset in range(0, len(runs), 100)
        ],
    ]


class ApiTests(unittest.TestCase):
    def test_actions_credentials_are_isolated_from_app_credentials(self):
        environment = {
            "GH_TOKEN": "factory-app-token",
            "GITHUB_TOKEN": "actions-token",
            "UNRELATED": "preserved",
        }
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch.object(
                diagnostics.subprocess, "check_output", return_value='{"ok": true}'
            ) as check_output,
        ):
            self.assertEqual(diagnostics.api("actions-endpoint", actions=True), {"ok": True})
            self.assertEqual(diagnostics.api("issue-endpoint"), {"ok": True})
            actions_call, app_call = check_output.call_args_list
            self.assertEqual(actions_call.args[0], ["gh", "api", "actions-endpoint"])
            self.assertEqual(actions_call.kwargs["env"]["GH_TOKEN"], "actions-token")
            self.assertEqual(actions_call.kwargs["env"]["UNRELATED"], "preserved")
            self.assertIs(actions_call.kwargs["text"], True)
            self.assertEqual(app_call.kwargs["env"]["GH_TOKEN"], "factory-app-token")
            self.assertEqual(dict(os.environ), environment)

    def test_paginated_api_uses_slurp_and_preserves_pages(self):
        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "actions-token"}, clear=True),
            mock.patch.object(
                diagnostics.subprocess, "check_output", return_value='[{"page": 1}, {"page": 2}]'
            ) as check_output,
        ):
            self.assertEqual(
                diagnostics.api("endpoint", actions=True, paginate=True),
                [{"page": 1}, {"page": 2}],
            )
            self.assertEqual(
                check_output.call_args.args[0],
                ["gh", "api", "endpoint", "--paginate", "--slurp"],
            )

    def test_actions_api_does_not_fall_back_to_app_token(self):
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": "app-token"}, clear=True),
            mock.patch.object(diagnostics.subprocess, "check_output") as check_output,
        ):
            with self.assertRaises(KeyError):
                diagnostics.api("endpoint", actions=True)
            check_output.assert_not_called()

    def test_api_errors_are_not_converted_to_empty_history(self):
        with mock.patch.object(
            diagnostics.subprocess,
            "check_output",
            side_effect=subprocess.CalledProcessError(1, ["gh", "api"]),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                diagnostics.api("endpoint")


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(
            prefix=".workflow-diagnostics-", dir=Path(__file__).resolve().parent
        )
        self.addCleanup(workspace.cleanup)
        self.directory = Path(workspace.name)
        self.summary = self.directory / "summary.txt"
        self.output = self.directory / "output.txt"
        environment = mock.patch.dict(
            os.environ,
            {
                "GITHUB_REPOSITORY": REPOSITORY,
                "GITHUB_RUN_ID": "200",
                "DEFAULT_BRANCH": "main",
                "GITHUB_STEP_SUMMARY": str(self.summary),
                "GITHUB_OUTPUT": str(self.output),
                "GITHUB_SERVER_URL": SERVER,
                "FACTORY_LOGIN": "factory[bot]",
                "GITHUB_TOKEN": "actions-token",
                "GH_TOKEN": "app-token",
            },
            clear=True,
        )
        environment.start()
        self.addCleanup(environment.stop)
        api_patch = mock.patch.object(diagnostics, "api", autospec=True)
        self.api = api_patch.start()
        self.addCleanup(api_patch.stop)
        self.current = make_run(200, run_number=20, created_at=END)
        self.previous = make_run(100, run_number=19)

    def read_manifest(self):
        return json.loads((self.directory / "manifest.json").read_text())


class PreviousRunTests(DiagnosticsTests):
    def test_previous_accepts_manual_and_scheduled_runs_with_any_conclusion(self):
        for event in ("schedule", "workflow_dispatch"):
            for conclusion in ("success", "failure", "cancelled", None):
                with self.subTest(event=event, conclusion=conclusion):
                    candidate = make_run(
                        100, run_number=19, event=event, conclusion=conclusion
                    )
                    self.api.return_value = run_page([candidate])
                    self.assertEqual(
                        diagnostics.previous_run(REPOSITORY, self.current, "main"),
                        candidate,
                    )

    def test_previous_ignores_other_events_branches_current_and_newer_runs(self):
        older_rerun = make_run(
            90, run_number=18, run_attempt=5, updated_at="2026-09-18T12:00:00Z"
        )
        candidates = [
            make_run(210, run_number=21),
            dict(self.current, run_attempt=1),
            make_run(198, run_number=19, head_branch="feature"),
            make_run(197, run_number=19, event="push"),
            make_run(196, run_number=19, event="pull_request"),
            older_rerun,
            self.previous,
        ]
        self.api.return_value = run_page(candidates)
        self.assertEqual(
            diagnostics.previous_run(
                REPOSITORY, dict(self.current, run_attempt=3), "main"
            ),
            self.previous,
        )

    def test_previous_pages_unfiltered_history_past_a_thousand_runs(self):
        full_page = [
            make_run(index, run_number=19, head_branch="feature")
            for index in range(100)
        ]
        self.api.side_effect = (
            [run_page(full_page, total=1101)] * 11
            + [run_page([self.previous], total=1101)]
        )
        self.assertEqual(
            diagnostics.previous_run(REPOSITORY, self.current, "main"), self.previous
        )
        self.assertEqual(self.api.call_count, 12)
        for page_number, call in enumerate(self.api.call_args_list, start=1):
            endpoint = urlsplit(call.args[0])
            self.assertEqual(
                endpoint.path, f"repos/{REPOSITORY}/actions/workflows/7/runs"
            )
            self.assertEqual(
                parse_qs(endpoint.query),
                {"per_page": ["100"], "page": [str(page_number)]},
            )
            self.assertEqual(call.kwargs, {"actions": True})

    def test_previous_stops_on_empty_page(self):
        self.api.side_effect = [
            run_page([make_run(index, event="push") for index in range(100)]),
            run_page([]),
        ]
        self.assertIsNone(diagnostics.previous_run(REPOSITORY, self.current, "main"))
        self.assertEqual(self.api.call_count, 2)


class WindowRunTests(DiagnosticsTests):
    def window(self, start=START, end=END):
        return diagnostics.window_runs(
            REPOSITORY, diagnostics.timestamp(start), diagnostics.timestamp(end)
        )

    def assert_window_query(self, call, start, end, *, paginated=False):
        endpoint = urlsplit(call.args[0])
        self.assertEqual(endpoint.path, f"repos/{REPOSITORY}/actions/runs")
        self.assertEqual(
            parse_qs(endpoint.query),
            {"created": [f"{start}..{end}"], "per_page": ["100"]},
        )
        self.assertEqual(
            call.kwargs,
            {"actions": True, **({"paginate": True} if paginated else {})},
        )

    def test_small_windows_need_one_query_including_zero_and_exactly_100(self):
        for count in (0, 1, 100):
            with self.subTest(count=count):
                runs = [make_run(index) for index in range(count)]
                self.api.reset_mock()
                self.api.return_value = run_page(runs)
                self.assertEqual(self.window(), runs)
                self.api.assert_called_once()
                self.assert_window_query(self.api.call_args, START, END)

    def test_multiple_pages_include_all_workflows_events_and_conclusions(self):
        runs = [
            make_run(index, workflow_id=index % 3, event="push", conclusion="failure")
            for index in range(205)
        ]
        self.api.side_effect = [
            run_page(runs[:100], total=205),
            [run_page(runs[:100]), run_page(runs[100:200]), run_page(runs[200:])],
        ]
        self.assertEqual(self.window(), runs)
        self.assertEqual(self.api.call_count, 2)
        self.assert_window_query(self.api.call_args_list[0], START, END)
        self.assert_window_query(self.api.call_args_list[1], START, END, paginated=True)

    def test_saturated_queries_split_into_disjoint_inclusive_seconds(self):
        for total in (1000, 1001):
            with self.subTest(total=total):
                self.api.reset_mock()
                left = [make_run(index) for index in range(500)]
                right = [
                    make_run(index, created_at="2026-09-16T08:00:02Z")
                    for index in range(500, total)
                ]
                self.api.side_effect = [
                    run_page([], total=total),
                    *paginated_responses(left),
                    *paginated_responses(right),
                ]
                self.assertEqual(self.window(START, "2026-09-16T08:00:03Z"), left + right)
                self.assertEqual(self.api.call_count, 5)
                self.assert_window_query(
                    self.api.call_args_list[1], START, "2026-09-16T08:00:01Z"
                )
                self.assert_window_query(
                    self.api.call_args_list[3],
                    "2026-09-16T08:00:02Z",
                    "2026-09-16T08:00:03Z",
                )

    def test_saturated_children_are_split_recursively(self):
        runs = [
            make_run(index, created_at=f"2026-09-16T08:00:0{index // 500}Z")
            for index in range(2000)
        ]
        self.api.side_effect = [
            run_page([], total=2000),
            run_page([], total=1000),
            *paginated_responses(runs[:500]),
            *paginated_responses(runs[500:1000]),
            run_page([], total=1000),
            *paginated_responses(runs[1000:1500]),
            *paginated_responses(runs[1500:]),
        ]
        self.assertEqual(self.window(START, "2026-09-16T08:00:03Z"), runs)
        self.assertEqual(self.api.call_count, 11)
        self.assert_window_query(self.api.call_args_list[2], START, START)
        self.assert_window_query(
            self.api.call_args_list[4], "2026-09-16T08:00:01Z", "2026-09-16T08:00:01Z"
        )
        self.assert_window_query(
            self.api.call_args_list[7], "2026-09-16T08:00:02Z", "2026-09-16T08:00:02Z"
        )
        self.assert_window_query(
            self.api.call_args_list[9], "2026-09-16T08:00:03Z", "2026-09-16T08:00:03Z"
        )

    def test_split_history_changes_are_rejected(self):
        for count in (999, 1001):
            with self.subTest(count=count):
                runs = [make_run(index) for index in range(count)]
                self.api.side_effect = [
                    run_page([], total=1000),
                    *paginated_responses(runs[:499]),
                    *paginated_responses(runs[499:]),
                ]
                with self.assertRaisesRegex(ValueError, "changed or was truncated"):
                    self.window()

    def test_split_history_count_uses_distinct_run_ids(self):
        runs = [make_run(index) for index in range(999)]
        self.api.side_effect = [
            run_page([], total=1000),
            *paginated_responses(runs[:500]),
            *paginated_responses(runs[499:]),
        ]
        with self.assertRaisesRegex(ValueError, "changed or was truncated"):
            self.window()

    def test_nested_split_history_changes_are_rejected(self):
        runs = [make_run(index) for index in range(1000)]
        self.api.side_effect = [
            run_page([], total=1000),
            run_page([], total=1000),
            *paginated_responses(runs[:499]),
            *paginated_responses(runs[499:999]),
            run_page(runs[999:]),
        ]
        with self.assertRaisesRegex(ValueError, "changed or was truncated"):
            self.window(START, "2026-09-16T08:00:03Z")
        self.assertEqual(self.api.call_count, 6)

    def test_saturated_single_second_is_an_explicit_error(self):
        for total in (1000, 1001):
            with self.subTest(total=total):
                self.api.reset_mock()
                self.api.return_value = run_page([], total=total)
                with self.assertRaisesRegex(ValueError, "1,000 runs in one second"):
                    self.window(START, START)
                self.api.assert_called_once()

    def test_missing_or_duplicate_history_is_rejected(self):
        responses = (
            run_page([make_run(100)], total=2),
            run_page([make_run(100), make_run(100)], total=2),
        )
        for response in responses:
            with self.subTest(response=response):
                self.api.return_value = response
                with self.assertRaisesRegex(ValueError, "changed or was truncated"):
                    self.window()

    def test_truncated_paginated_history_is_rejected(self):
        runs = [make_run(index) for index in range(100)]
        self.api.side_effect = [
            run_page(runs, total=101),
            [run_page(runs), run_page([runs[-1]])],
        ]
        with self.assertRaisesRegex(ValueError, "changed or was truncated"):
            self.window()


class CollectTests(DiagnosticsTests):
    def setUp(self):
        super().setUp()
        older_patch = mock.patch.object(
            diagnostics, "older_activity_runs", autospec=True, return_value=[]
        )
        self.older_activity = older_patch.start()
        self.addCleanup(older_patch.stop)

    def collect_runs(self, runs, *, current=None, older_runs=()):
        self.older_activity.return_value = list(older_runs)
        self.api.side_effect = [
            current or self.current,
            run_page([self.previous]),
            run_page(runs),
        ]
        diagnostics.collect(self.directory)
        return self.read_manifest()

    def test_first_run_establishes_boundary_without_querying_a_window(self):
        self.api.side_effect = [self.current, run_page([])]
        with mock.patch.object(diagnostics, "window_runs") as window:
            diagnostics.collect(self.directory)
        window.assert_not_called()
        self.older_activity.assert_not_called()
        self.assertEqual(self.api.call_count, 2)
        manifest = self.read_manifest()
        self.assertIsNone(manifest["previous_run"])
        self.assertEqual(manifest["workflows"], [])
        self.assertEqual(manifest["current_run"], self.current)
        self.assertEqual(self.output.read_text(), "analyze=false\n")
        self.assertIn("no analysis or issue creation", self.summary.read_text())

    def test_non_default_branch_is_rejected_before_history_lookup(self):
        self.api.return_value = dict(self.current, head_branch="feature")
        with self.assertRaisesRegex(ValueError, "default branch"):
            diagnostics.collect(self.directory)
        self.api.assert_called_once()
        self.assertFalse((self.directory / "manifest.json").exists())

    def test_timestamp_ties_include_previous_and_exclude_current(self):
        runs = [
            make_run(201, created_at=END),
            make_run(99),
            self.current,
            make_run(199, created_at=END),
            make_run(101),
            self.previous,
        ]
        manifest = self.collect_runs(runs)
        self.assertEqual(
            [run["id"] for group in manifest["workflows"] for run in group["runs"]],
            [100, 101, 199],
        )
        self.assertEqual(manifest["previous_run"], self.previous)
        self.assertEqual(self.output.read_text(), "analyze=true\n")
        self.assertIn("Collected 3 runs across 1 workflows", self.summary.read_text())
        self.assertIn("(inclusive)", self.summary.read_text())
        self.assertIn("(exclusive)", self.summary.read_text())

    def test_reruns_preserve_original_window_and_exclude_the_current_run(self):
        runs = [
            self.previous,
            make_run(150, created_at="2026-09-16T12:00:00Z"),
            self.current,
            make_run(250, created_at="2026-09-17T12:00:00Z"),
        ]
        initial = self.collect_runs(runs)
        rerun = dict(
            self.current,
            run_attempt=3,
            run_started_at="2026-09-18T08:00:00Z",
            updated_at="2026-09-18T08:01:00Z",
        )
        repeated = self.collect_runs(runs, current=rerun)
        self.assertEqual(initial["previous_run"], repeated["previous_run"])
        self.assertEqual(initial["workflows"], repeated["workflows"])
        self.assertEqual(repeated["current_run"]["run_attempt"], 3)
        self.assertEqual(
            parse_qs(urlsplit(self.api.call_args.args[0]).query)["created"],
            [f"{START}..{END}"],
        )

    def test_older_run_completed_or_rerun_in_window_is_included(self):
        older = make_run(
            50,
            workflow_id=8,
            created_at="2026-09-15T08:00:00Z",
            run_started_at="2026-09-16T10:00:00Z",
            updated_at="2026-09-16T10:01:00Z",
            run_attempt=2,
        )
        manifest = self.collect_runs([self.previous], older_runs=[older])
        self.assertEqual(
            [run["id"] for group in manifest["workflows"] for run in group["runs"]],
            [50, 100],
        )
        self.older_activity.assert_called_once_with(
            REPOSITORY, diagnostics.timestamp(START), diagnostics.timestamp(END)
        )

    def test_older_activity_breaks_creation_time_ties_without_duplicate_overlap(self):
        before_previous = make_run(99, updated_at="2026-09-16T12:00:00Z")
        after_previous = make_run(101, updated_at="2026-09-16T12:00:00Z")
        manifest = self.collect_runs(
            [before_previous, self.previous, after_previous, self.current],
            older_runs=[before_previous, self.previous, after_previous],
        )
        self.assertEqual(
            manifest["workflows"][0]["runs"],
            [before_previous, self.previous, after_previous],
        )
        self.assertIn("Collected 3 runs across 1 workflows", self.summary.read_text())

    def test_duplicate_runs_are_rejected_before_publishing_manifest(self):
        self.api.side_effect = [
            self.current,
            run_page([self.previous]),
            run_page([self.previous, self.previous], total=1),
        ]
        with self.assertRaisesRegex(ValueError, "Duplicate runs"):
            diagnostics.collect(self.directory)
        self.assertFalse((self.directory / "manifest.json").exists())

    def test_collection_keeps_every_workflow_event_and_conclusion(self):
        conclusions = (
            "success", "failure", "cancelled", "skipped", "neutral",
            "timed_out", "action_required", "stale", "startup_failure", None,
        )
        runs = [self.previous] + [
            make_run(
                110 + index,
                workflow_id=30 + index,
                name=f"Workflow {index}",
                path=f".github/workflows/workflow-{index}.yml",
                event=("push", "pull_request", "workflow_dispatch")[index % 3],
                conclusion=conclusion,
                status="in_progress" if conclusion is None else "completed",
                head_branch="feature",
            )
            for index, conclusion in enumerate(conclusions)
        ]
        manifest = self.collect_runs(list(reversed(runs)))
        self.assertEqual(len(manifest["workflows"]), len(runs))
        for group, run in zip(manifest["workflows"], runs):
            self.assertEqual(group["workflow_id"], run["workflow_id"])
            self.assertEqual(group["name"], run["name"])
            self.assertEqual(group["path"], run["path"])
            self.assertEqual(group["runs"], [run])

    def test_missing_previous_run_is_an_explicit_error(self):
        with self.assertRaisesRegex(ValueError, "previous diagnostics run is missing"):
            self.collect_runs([make_run(101), self.current])
        self.assertFalse((self.directory / "manifest.json").exists())
        self.assertFalse(self.output.exists())

    def test_api_failure_does_not_publish_a_partial_manifest(self):
        self.api.side_effect = [
            self.current,
            run_page([self.previous]),
            subprocess.CalledProcessError(1, ["gh", "api"]),
        ]
        with self.assertRaises(subprocess.CalledProcessError):
            diagnostics.collect(self.directory)
        self.assertFalse((self.directory / "manifest.json").exists())
        self.assertFalse(self.output.exists())

    def test_changed_split_history_does_not_publish_a_partial_manifest(self):
        left = [self.previous] + [make_run(index) for index in range(1000, 1498)]
        right = [self.current] + [
            make_run(index, created_at="2026-09-17T02:00:00Z")
            for index in range(2000, 2499)
        ]
        self.api.side_effect = [
            self.current,
            run_page([self.previous]),
            run_page([], total=1000),
            *paginated_responses(left),
            *paginated_responses(right),
        ]
        with self.assertRaisesRegex(ValueError, "changed or was truncated"):
            diagnostics.collect(self.directory)
        self.older_activity.assert_not_called()
        self.assertFalse((self.directory / "manifest.json").exists())
        self.assertFalse(self.output.exists())
        self.assertFalse(self.summary.exists())


class OlderActivityRunTests(DiagnosticsTests):
    def test_unfiltered_pages_include_old_activity_with_half_open_update_window(self):
        old_created = "2026-09-15T08:00:00Z"
        runs = [
            make_run(50, created_at=old_created, updated_at=START),
            make_run(51, created_at=old_created, updated_at="2026-09-16T12:00:00Z"),
            make_run(52, created_at=old_created, updated_at=END),
            make_run(53, created_at=old_created, updated_at=old_created),
            make_run(101, created_at=START, updated_at="2026-09-16T12:00:00Z"),
            make_run(
                102,
                created_at="2026-09-16T08:00:01Z",
                updated_at="2026-09-16T12:00:00Z",
            ),
        ]
        self.api.return_value = [run_page(runs[:2]), run_page(runs[2:])]
        self.assertEqual(
            diagnostics.older_activity_runs(
                REPOSITORY, diagnostics.timestamp(START), diagnostics.timestamp(END)
            ),
            runs[:2] + [runs[4]],
        )
        self.api.assert_called_once_with(
            f"repos/{REPOSITORY}/actions/runs?per_page=100",
            actions=True,
            paginate=True,
        )


class VerifyTests(DiagnosticsTests):
    def setUp(self):
        super().setUp()
        self.manifest = {
            "repository": REPOSITORY,
            "current_run": dict(self.current, run_attempt=2),
            "previous_run": self.previous,
            "workflows": [
                {"workflow_id": 7, "runs": [self.previous, make_run(101)]},
                {"workflow_id": 8, "runs": [make_run(150, workflow_id=8)]},
            ],
        }
        self.report = {
            "run_id": 200,
            "run_attempt": 2,
            "errors": [],
            "analyses": [
                {
                    "workflow_id": 7,
                    "run_ids": [100, 101],
                    "complete": True,
                    "subagent_id": "diagnostics-agent-7",
                    "summary": "Both runs completed successfully; no actionable finding.",
                },
                {
                    "workflow_id": 8,
                    "run_ids": [150],
                    "complete": True,
                    "subagent_id": "diagnostics-agent-8",
                    "summary": "The workflow completed successfully; no actionable finding.",
                },
            ],
            "duplicates": [],
            "created_issues": [],
        }

    def verify_report(self):
        (self.directory / "manifest.json").write_text(json.dumps(self.manifest))
        (self.directory / "report.json").write_text(json.dumps(self.report))
        diagnostics.verify(self.directory)

    def assert_rejected(self, message):
        with self.assertRaisesRegex(ValueError, message):
            self.verify_report()
        self.assertFalse(self.summary.exists())

    def issue(self, number=42, **overrides):
        issue = {
            "user": {"login": "factory[bot]"},
            "body": "Actionable finding.\n<!-- factory-diagnostics:200:2 -->",
            "html_url": f"{SERVER}/{REPOSITORY}/issues/{number}",
        }
        issue.update(overrides)
        return issue

    def test_clean_report_requires_no_issue_and_writes_evidence_summary(self):
        self.summary.write_text("Existing collection summary.\n")
        self.verify_report()
        self.api.assert_not_called()
        summary = self.summary.read_text()
        self.assertTrue(summary.startswith("Existing collection summary.\n"))
        self.assertIn("## Diagnostics results", summary)
        for analysis in self.report["analyses"]:
            self.assertIn(
                f"Workflow {analysis['workflow_id']}: {analysis['summary']}", summary
            )
        self.assertIn("Created issues: none.", summary)
        self.assertIn("Existing findings: none.", summary)

    def test_report_for_another_run_or_attempt_is_rejected(self):
        for field, value in (("run_id", 199), ("run_attempt", 1)):
            with self.subTest(field=field):
                original = self.report[field]
                self.report[field] = value
                self.assert_rejected("different diagnostics invocation")
                self.report[field] = original
        self.api.assert_not_called()

    def test_errors_are_rejected_even_with_complete_coverage(self):
        for errors in (["Failed to fetch a log"], None, ""):
            with self.subTest(errors=errors):
                self.report["errors"] = errors
                self.assert_rejected("Incomplete diagnostics")
        self.api.assert_not_called()

    def test_complete_must_be_literal_true_for_every_workflow(self):
        for complete in (False, None, 1, "true"):
            with self.subTest(complete=complete):
                self.report["analyses"][1]["complete"] = complete
                self.assert_rejected("Incomplete run coverage")

    def test_workflow_coverage_cannot_be_missing_duplicate_or_unexpected(self):
        original = copy.deepcopy(self.report["analyses"])
        for analyses in (
            original[:1],
            [original[0], original[0]],
            original + [original[0]],
            [original[0], dict(original[1], workflow_id=999)],
        ):
            with self.subTest(analyses=analyses):
                self.report["analyses"] = analyses
                self.assert_rejected("each workflow exactly once")

    def test_run_coverage_cannot_be_missing_duplicate_or_unexpected(self):
        for run_ids in ([100], [100, 100], [100, 101, 101], [100, 999], []):
            with self.subTest(run_ids=run_ids):
                self.report["analyses"][0]["run_ids"] = run_ids
                self.assert_rejected("Incomplete run coverage")

    def test_report_order_does_not_affect_coverage(self):
        self.report["analyses"][0]["run_ids"].reverse()
        self.report["analyses"].reverse()
        self.verify_report()
        self.api.assert_not_called()

    def test_subagent_receipts_and_evidence_summaries_cannot_be_empty(self):
        for field in ("subagent_id", "summary"):
            for value in ("", " \n", None, 7):
                with self.subTest(field=field, value=value):
                    original = self.report["analyses"][0][field]
                    self.report["analyses"][0][field] = value
                    self.assert_rejected("subagent receipt and an evidence-based summary")
                    self.report["analyses"][0][field] = original

    def test_each_workflow_requires_a_unique_subagent(self):
        self.report["analyses"][1]["subagent_id"] = self.report["analyses"][0]["subagent_id"]
        self.assert_rejected("separate subagent")

    def test_valid_issue_receipts_use_app_api_and_appear_in_summary(self):
        self.report["created_issues"] = [42, 43]
        self.report["duplicates"] = [f"{SERVER}/{REPOSITORY}/issues/10"]
        self.api.side_effect = [self.issue(42), self.issue(43)]
        self.verify_report()
        self.assertEqual(
            self.api.call_args_list,
            [
                mock.call(f"repos/{REPOSITORY}/issues/42"),
                mock.call(f"repos/{REPOSITORY}/issues/43"),
            ],
        )
        summary = self.summary.read_text()
        self.assertIn(
            f"Created issues: {SERVER}/{REPOSITORY}/issues/42, "
            f"{SERVER}/{REPOSITORY}/issues/43.",
            summary,
        )
        self.assertIn(f"Existing findings: {SERVER}/{REPOSITORY}/issues/10.", summary)

    def test_issue_receipt_requires_app_author_run_attempt_marker_and_not_a_pr(self):
        self.report["created_issues"] = [42]
        invalid_issues = (
            self.issue(user={"login": "someone-else"}),
            self.issue(body="Missing marker"),
            self.issue(body=None),
            self.issue(body="<!-- factory-diagnostics:199:2 -->"),
            self.issue(body="<!-- factory-diagnostics:200:1 -->"),
            self.issue(pull_request={"url": "https://api.example/pulls/42"}),
        )
        for issue in invalid_issues:
            with self.subTest(issue=issue):
                self.api.return_value = issue
                self.assert_rejected("not a Factory-authored receipt from this attempt")

    def test_issue_receipts_require_unique_positive_integer_numbers(self):
        for issues in (None, "42", [True], ["42"], [0], [-1], [1.5], [42, 42]):
            with self.subTest(issues=issues):
                self.report["created_issues"] = issues
                self.assert_rejected("unique positive issue numbers")
        self.api.assert_not_called()

    def test_unavailable_issue_receipt_fails_without_publishing_results(self):
        self.report["created_issues"] = [42]
        self.api.side_effect = subprocess.CalledProcessError(1, ["gh", "api"])
        with self.assertRaises(subprocess.CalledProcessError):
            self.verify_report()
        self.assertFalse(self.summary.exists())

    def test_duplicate_findings_must_belong_to_this_repository(self):
        for duplicates in (
            None,
            "not a list",
            [42],
            [f"{SERVER}/other/repository/issues/10"],
            [f"{SERVER}/{REPOSITORY}-other/issues/10"],
            [f"https://elsewhere.example/{REPOSITORY}/issues/10"],
            [f"{SERVER}/{REPOSITORY}/actions/runs/10"],
            [f"{SERVER}/{REPOSITORY}/issues/0"],
            [f"{SERVER}/{REPOSITORY}/issues/10/unrelated"],
        ):
            with self.subTest(duplicates=duplicates):
                self.report["duplicates"] = duplicates
                self.assert_rejected("link existing repository issues or PRs")


class MainTests(unittest.TestCase):
    def test_cli_surfaces_expected_failures_with_diagnostics_context(self):
        errors = (
            ValueError("incomplete history"),
            KeyError("workflow_runs"),
            OSError("cannot read report"),
            subprocess.CalledProcessError(1, ["gh", "api"]),
        )
        for error in errors:
            with self.subTest(error=error):
                with (
                    mock.patch("sys.argv", [str(SCRIPT), "collect", "unused"]),
                    mock.patch.object(diagnostics, "collect", side_effect=error),
                ):
                    with self.assertRaisesRegex(SystemExit, "Workflow diagnostics failed:"):
                        diagnostics.main()


if __name__ == "__main__":
    unittest.main()
