import json
from pathlib import Path
import re
import sys


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def patch_locations(patch):
    if not isinstance(patch, str) or not patch:
        raise ValueError("No text patch is available for this file")
    locations = {}
    positions = set()
    old_remaining = new_remaining = hunk = 0
    first_header = None
    lines = patch.split("\n")
    if lines[-1] == "":
        lines.pop()
    for position, text in enumerate(lines):
        header = HUNK.match(text)
        if header:
            if old_remaining or new_remaining:
                raise ValueError("The file patch is incomplete")
            old_line, old_count, new_line, new_count = header.groups()
            old_line, new_line = int(old_line), int(new_line)
            old_remaining = int(old_count) if old_count is not None else 1
            new_remaining = int(new_count) if new_count is not None else 1
            hunk += 1
            if first_header is None:
                first_header = position
            continue
        if text == r"\ No newline at end of file":
            continue
        if not hunk or not text or text[0] not in " +-":
            raise ValueError("The file patch is not a complete unified diff")
        if text[0] in " -":
            if old_remaining <= 0:
                raise ValueError("The file patch has inconsistent old-line counts")
            if text[0] == "-":
                locations["LEFT", old_line] = (hunk, position)
            old_line += 1
            old_remaining -= 1
        if text[0] in " +":
            if new_remaining <= 0:
                raise ValueError("The file patch has inconsistent new-line counts")
            locations["RIGHT", new_line] = (hunk, position)
            new_line += 1
            new_remaining -= 1
        positions.add(position - first_header)
    if not hunk or old_remaining or new_remaining:
        raise ValueError("The file patch is incomplete")
    return locations, positions


def validate(comments, pages):
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ValueError("Expected paginated PR file arrays")
    files = {}
    for page in pages:
        for file in page:
            if not isinstance(file, dict) or not isinstance(file.get("filename"), str):
                raise ValueError("Invalid PR file response")
            files[file["filename"]] = file.get("patch")
    for index, comment in enumerate(comments, 1):
        prefix = f"Inline comment {index}"
        if not isinstance(comment, dict):
            raise ValueError(f"{prefix} must be an object")
        path, body = comment.get("path"), comment.get("body")
        if not isinstance(path, str) or path not in files:
            raise ValueError(f"{prefix} must name a file in the PR diff")
        if not isinstance(body, str) or not body.strip():
            raise ValueError(f"{prefix} must have a nonempty body")
        locations, positions = patch_locations(files[path])
        if "position" in comment:
            if any(key in comment for key in ("line", "side", "start_line", "start_side")):
                raise ValueError(f"{prefix} must not mix position and line coordinates")
            position = comment["position"]
            if type(position) is not int or position not in positions:
                raise ValueError(f"{prefix} position is outside the PR diff")
            continue
        side, line = comment.get("side", "RIGHT"), comment.get("line")
        if side not in ("LEFT", "RIGHT") or type(line) is not int or line <= 0:
            raise ValueError(f"{prefix} needs a positive line and LEFT or RIGHT side")
        end = locations.get((side, line))
        if end is None:
            raise ValueError(f"{prefix} line is outside the {side} side of the PR diff")
        if "start_line" in comment:
            start_side = comment.get("start_side")
            start_line = comment["start_line"]
            if (start_side not in ("LEFT", "RIGHT") or type(start_line) is not int
                    or start_line <= 0):
                raise ValueError(f"{prefix} has invalid range start coordinates")
            start = locations.get((start_side, start_line))
            if start is None or start[0] != end[0] or start[1] >= end[1]:
                raise ValueError(f"{prefix} range must run forward within one diff hunk")
        elif "start_side" in comment:
            raise ValueError(f"{prefix} start_side requires start_line")


if __name__ == "__main__":
    try:
        request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        validate(request["comments"], json.load(sys.stdin))
    except (OSError, ValueError) as exc:
        sys.exit(f"Error: {exc}")
