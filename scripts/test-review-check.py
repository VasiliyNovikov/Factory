#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess
import sys
import tempfile


launcher = Path(__file__).resolve().with_name("review-check.sh")
removed = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "COPILOT_GITHUB_TOKEN",
    "GITHUB_OUTPUT",
    "GITHUB_ENV",
    "GITHUB_PATH",
    "GITHUB_STATE",
    "GITHUB_STEP_SUMMARY",
)
coordinator_names = set(os.environ)
environment = os.environ.copy()
environment.update(dict.fromkeys(removed, "presence-only-fixture"))
environment["REVIEW_CHECK_PASSTHROUGH"] = "kept"
probe = """
import os
import sys

present = [name for name in sys.argv[1:] if name in os.environ]
assert not present, "Unexpected inherited variables: " + ", ".join(present)
assert os.environ.get("REVIEW_CHECK_PASSTHROUGH") == "kept"
print("Absent: " + ", ".join(sys.argv[1:]))
"""
probe_command = [sys.executable, "-c", probe, *removed]
expected = "Absent: " + ", ".join(removed) + "\n"


def run(command, **kwargs):
    return subprocess.run(
        [str(launcher), *command],
        env=environment,
        capture_output=True,
        text=True,
        **kwargs,
    )


direct = run(probe_command, check=True)
assert direct.stdout == expected
pipeline = run(
    ["bash", "-c", 'set -euo pipefail; "$@" | { "$@"; cat; }', "probe", *probe_command],
    check=True,
)
assert pipeline.stdout == expected * 2

with tempfile.TemporaryDirectory(prefix="review-check-") as directory:
    workspace = Path(directory)
    source = workspace / "source probe"
    installed = workspace / "installed probe"
    source.write_text(f"#!{sys.executable}\n{probe}")
    source.chmod(0o755)
    installation = run(
        [
            "bash", "-c",
            'set -euo pipefail; "$1" "${@:3}"; '
            'install -m 755 -- "$1" "$2"; "$2" "${@:3}"',
            "install-probe", str(source), str(installed), *removed,
        ],
        check=True,
    )
    assert installed.is_file()
    assert installation.stdout == expected * 2

    forwarding = run(
        [
            sys.executable, "-c",
            'import os, sys; assert sys.argv[1:] == ["two words", "*", "", "--flag"]; '
            'assert os.getcwd() == sys.stdin.readline().rstrip("\\n"); '
            'print("stdout preserved"); print("stderr preserved", file=sys.stderr)',
            "two words", "*", "", "--flag",
        ],
        cwd=workspace,
        input=str(workspace) + "\n",
        check=True,
    )
    assert forwarding.stdout == "stdout preserved\n"
    assert forwarding.stderr == "stderr preserved\n"

coordinator = subprocess.run(
    [
        "bash", "-c",
        'set -euo pipefail; launcher=$1; python=$2; probe=$3; shift 3; '
        '"$launcher" "$python" -c "$probe" "$@"; '
        'for name; do [[ -v "$name" ]] || { printf "Missing: %s\\n" "$name" >&2; exit 1; }; done',
        "coordinator", str(launcher), sys.executable, probe, *removed,
    ],
    env=environment,
    capture_output=True,
    text=True,
    check=True,
)
assert coordinator.stdout == expected
assert set(os.environ) == coordinator_names
assert run(["bash", "-c", "exit 37"]).returncode == 37
missing = run(["factory-review-check-nonexistent-command"])
assert missing.returncode == 127
assert missing.stderr
empty = run([])
assert empty.returncode != 0
assert empty.stdout == ""
assert "Usage:" in empty.stderr

print("PASS: direct check, both pipeline stages, and local installation: " + expected.strip())
print("PASS: coordinator retains all eight variable names; unrelated environment preserved")
print("PASS: arguments, working directory, stdin/stdout/stderr, exit status, and usage errors")
