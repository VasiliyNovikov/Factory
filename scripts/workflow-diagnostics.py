#!/usr/bin/env python3
"""Collect a diagnostics window and verify Copilot's coverage and issue receipts."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlencode


OLDER_ACTIVITY_LOOKBACK_DAYS = 90


def api(endpoint, *, actions=False, paginate=False):
    env = os.environ.copy()
    if actions:
        env["GH_TOKEN"] = env["GITHUB_TOKEN"]
    command = ["gh", "api", endpoint]
    if paginate:
        command += ["--paginate", "--slurp"]
    return json.loads(subprocess.check_output(command, env=env, text=True))


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def previous_run(repository, current, branch):
    page = 1
    while True:
        # Unfiltered workflow history avoids the filtered search's 1,000-run cap.
        response = api(
            f"repos/{repository}/actions/workflows/{current['workflow_id']}/runs"
            f"?per_page=100&page={page}",
            actions=True,
        )
        candidates = [
            run for run in response["workflow_runs"]
            if run["run_number"] < current["run_number"]
            and run["head_branch"] == branch
            and run["event"] in ("schedule", "workflow_dispatch")
        ]
        if candidates:
            return max(candidates, key=lambda run: run["run_number"])
        if len(response["workflow_runs"]) < 100:
            return None
        page += 1


def window_runs(repository, start, end):
    query = urlencode({"created": f"{iso(start)}..{iso(end)}", "per_page": 100})
    endpoint = f"repos/{repository}/actions/runs?{query}"
    first = api(endpoint, actions=True)
    # GitHub caps filtered run searches at 1,000 results. Split before paging.
    if first["total_count"] >= 1000:
        if start >= end:
            raise ValueError("At least 1,000 runs in one second; cannot collect a complete window")
        middle = start + timedelta(seconds=int((end - start).total_seconds()) // 2)
        runs = (
            window_runs(repository, start, middle)
            + window_runs(repository, middle + timedelta(seconds=1), end)
        )
    elif first["total_count"] <= 100:
        runs = first["workflow_runs"]
    else:
        pages = api(endpoint, actions=True, paginate=True)
        runs = [run for page in pages for run in page["workflow_runs"]]
    if len({run["id"] for run in runs}) != first["total_count"]:
        raise ValueError("Run history changed or was truncated during collection; retry diagnostics")
    return runs


def older_activity_runs(repository, start, end):
    # The API has no updated-at filter. Bound the creation search instead of
    # scanning all retained history for completed or rerun activity.
    oldest = start - timedelta(days=OLDER_ACTIVITY_LOOKBACK_DAYS)
    runs = window_runs(repository, oldest, start)
    return [
        run for run in runs
        if oldest <= timestamp(run["created_at"]) <= start
        and start <= timestamp(run["updated_at"]) < end
    ]


def summarize(run):
    keys = (
        "id", "run_number", "run_attempt", "workflow_id", "name", "path",
        "event", "status", "conclusion", "html_url", "head_branch", "head_sha",
        "created_at", "run_started_at", "updated_at",
    )
    return {key: run[key] for key in keys}


def collect(directory):
    repository = os.environ["GITHUB_REPOSITORY"]
    current = api(
        f"repos/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}", actions=True
    )
    if current["head_branch"] != os.environ["DEFAULT_BRANCH"]:
        raise ValueError("Diagnostics must run on the default branch")
    previous = previous_run(repository, current, os.environ["DEFAULT_BRANCH"])
    groups = {}
    if previous is not None:
        runs = window_runs(
            repository, timestamp(previous["created_at"]), timestamp(current["created_at"])
        )
        # IDs break ties within GitHub's second-resolution timestamps. Rerunning
        # an invocation keeps its original boundary and excludes its own run ID.
        runs = [
            run for run in runs
            if (previous["created_at"], previous["id"])
            <= (run["created_at"], run["id"])
            < (current["created_at"], current["id"])
        ]
        if previous["id"] not in {run["id"] for run in runs}:
            raise ValueError("The previous diagnostics run is missing from the collected window")
        runs += [
            run for run in older_activity_runs(
                repository, timestamp(previous["created_at"]), timestamp(current["created_at"])
            )
            if (run["created_at"], run["id"]) < (previous["created_at"], previous["id"])
        ]
        if len(runs) != len({run["id"] for run in runs}):
            raise ValueError("Duplicate runs in collected history; retry diagnostics")
        for run in sorted(runs, key=lambda run: (run["created_at"], run["id"])):
            group = groups.setdefault(run["workflow_id"], {
                "workflow_id": run["workflow_id"],
                "name": run["name"],
                "path": run["path"],
                "runs": [],
            })
            group["runs"].append(summarize(run))
    manifest = {
        "repository": repository,
        "current_run": summarize(current),
        "previous_run": summarize(previous) if previous else None,
        "older_activity_lookback_days": OLDER_ACTIVITY_LOOKBACK_DAYS,
        "workflows": list(groups.values()),
    }
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"analyze={'true' if previous else 'false'}\n")
        output.write(f"manifest_sha256={manifest_sha256}\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
        if previous:
            summary.write(
                f"Diagnostics window: [{previous['id']}]({previous['html_url']}) "
                f"(inclusive) to [{current['id']}]({current['html_url']}) (exclusive).\n\n"
                f"Supplemental older-activity lookback: {OLDER_ACTIVITY_LOOKBACK_DAYS} days "
                "before the window start.\n\n"
                f"Collected {sum(len(group['runs']) for group in groups.values())} runs "
                f"across {len(groups)} workflows.\n"
            )
        else:
            summary.write("Initial diagnostics boundary established; no analysis or issue creation.\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_issue_labels(repository, number, issue):
    labels = issue.get("labels")
    require(
        isinstance(labels, list)
        and all(isinstance(label, dict) and isinstance(label.get("name"), str)
                and label["name"] for label in labels),
        f"Issue #{number} has invalid labels",
    )
    factory = os.environ["FACTORY_LOGIN"]
    tracking = f"factory-issue-{number}"
    ready = False
    active_labels = set()
    observed_labels = set()
    # Triage may have labeled the issue before this audit, especially on a retry.
    pages = api(f"repos/{repository}/issues/{number}/timeline?per_page=100", paginate=True)
    for page in pages:
        for event in page:
            if event["event"] == "commented":
                body = event["body"] or ""
                if (
                    event["user"]["login"] == factory
                    and "<!-- factory-triage:ready -->" in body
                    and "<!-- factory-triage:reply -->" not in body
                    and re.search(r"<!-- factory-triage-run:[1-9][0-9]*:[1-9][0-9]* -->", body)
                ):
                    ready = True
            elif event["event"] == "labeled":
                name = event["label"]["name"]
                actor = (event.get("actor") or {}).get("login")
                require(
                    isinstance(actor, str) and actor,
                    f"Issue #{number} has an unknown label actor",
                )
                require(
                    actor != factory
                    or (ready and (name == tracking
                                   or (name == "triaged" and tracking in active_labels))),
                    f"Issue #{number} has Factory-applied labels without a valid triage handoff",
                )
                active_labels.add(name)
                observed_labels.add(name)
            elif event["event"] == "unlabeled":
                active_labels.discard(event["label"]["name"])
    require(
        {label["name"] for label in labels} <= observed_labels,
        f"Issue #{number} has incomplete label history; retry verification",
    )


def verify(directory):
    manifest_bytes = (directory / "manifest.json").read_bytes()
    require(
        hashlib.sha256(manifest_bytes).hexdigest() == os.environ.get("MANIFEST_SHA256"),
        "Diagnostics manifest does not match the collected SHA-256",
    )
    manifest = json.loads(manifest_bytes)
    report = json.loads((directory / "report.json").read_text())
    current = manifest["current_run"]
    require(
        report["run_id"] == current["id"]
        and report["run_attempt"] == current["run_attempt"],
        "Report belongs to a different diagnostics invocation",
    )
    require(report["errors"] == [], f"Incomplete diagnostics: {report['errors']}")
    expected = {
        group["workflow_id"]: {run["id"] for run in group["runs"]}
        for group in manifest["workflows"]
    }
    unavailable = report.get("unavailable_evidence")
    require(isinstance(unavailable, list), "Unavailable evidence must be a list")
    unavailable_workflows = set()
    for evidence in unavailable:
        require(
            isinstance(evidence, dict)
            and type(evidence.get("workflow_id")) is int
            and evidence["workflow_id"] in expected
            and type(evidence.get("run_id")) is int
            and evidence["run_id"] in expected[evidence["workflow_id"]]
            and evidence.get("reason") in (
                "expired_logs", "superseded_attempt_logs", "unfinished_run",
            )
            and isinstance(evidence.get("details"), str) and evidence["details"].strip(),
            "Unavailable evidence must identify a collected workflow/run, "
            "an expected reason, and details",
        )
        unavailable_workflows.add(evidence["workflow_id"])
    analyses = report["analyses"]
    require(
        len(analyses) == len(expected)
        and {analysis["workflow_id"] for analysis in analyses} == set(expected),
        "Report must cover each workflow exactly once",
    )
    agent_ids = set()
    for analysis in analyses:
        require(
            (analysis["complete"] is True
             or (analysis["complete"] is False
                 and analysis["workflow_id"] in unavailable_workflows))
            and len(analysis["run_ids"]) == len(expected[analysis["workflow_id"]])
            and set(analysis["run_ids"]) == expected[analysis["workflow_id"]],
            f"Incomplete run coverage for workflow {analysis['workflow_id']}",
        )
        require(
            isinstance(analysis["subagent_id"], str) and analysis["subagent_id"].strip()
            and isinstance(analysis["summary"], str) and analysis["summary"].strip(),
            "Each workflow needs a subagent receipt and an evidence-based summary",
        )
        agent_ids.add(analysis["subagent_id"])
    require(len(agent_ids) == len(expected), "Use a separate subagent for each workflow")
    require(
        isinstance(report["duplicates"], list)
        and all(isinstance(url, str) and re.fullmatch(
            re.escape(f"{os.environ['GITHUB_SERVER_URL']}/{manifest['repository']}")
            + r"/(?:issues|pull)/[1-9][0-9]*",
            url,
        ) for url in report["duplicates"]),
        "Duplicate findings must link existing repository issues or PRs",
    )
    issues = report["created_issues"]
    require(
        isinstance(issues, list)
        and all(type(number) is int and number > 0 for number in issues)
        and len(issues) == len(set(issues)),
        "Created issue receipts must be unique positive issue numbers",
    )
    marker = f"<!-- factory-diagnostics:{current['id']}:{current['run_attempt']} -->"
    issue_urls = []
    for number in issues:
        issue = api(f"repos/{manifest['repository']}/issues/{number}")
        require(
            "pull_request" not in issue
            and issue["user"]["login"] == os.environ["FACTORY_LOGIN"]
            and marker in (issue["body"] or ""),
            f"Issue #{number} is not a Factory-authored receipt from this attempt",
        )
        verify_issue_labels(manifest["repository"], number, issue)
        issue_urls.append(issue["html_url"])
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
        summary.write("\n## Diagnostics results\n\n")
        if unavailable:
            summary.write("**Verified with evidence limitations**, not a clean result.\n\n")
        for analysis in analyses:
            summary.write(f"- Workflow {analysis['workflow_id']}: {analysis['summary']}\n")
        summary.write(f"\nCreated issues: {', '.join(issue_urls) or 'none'}.\n\n")
        summary.write(f"Existing findings: {', '.join(report['duplicates']) or 'none'}.\n")
        if unavailable:
            summary.write("\n## Unavailable evidence\n\n")
            for evidence in unavailable:
                run_url = (
                    f"{os.environ['GITHUB_SERVER_URL']}/{manifest['repository']}"
                    f"/actions/runs/{evidence['run_id']}"
                )
                summary.write(
                    f"- Workflow {evidence['workflow_id']}, "
                    f"[run {evidence['run_id']}]({run_url}) "
                    f"({evidence['reason']}): {evidence['details']}\n"
                )
    if unavailable:
        print(
            f"::warning::Diagnostics verified with {len(unavailable)} expected evidence gap(s); "
            "see the job summary."
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("collect", "verify"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        {"collect": collect, "verify": verify}[args.command](args.directory)
    except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Workflow diagnostics failed: {error}") from error


if __name__ == "__main__":
    main()
