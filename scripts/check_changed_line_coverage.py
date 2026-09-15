from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(diff: str) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            result.setdefault(current, set())
            continue
        match = HUNK_RE.match(line)
        if current is None or match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count > 0:
            result[current].update(range(start, start + count))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Require coverage on every changed executable line")
    parser.add_argument("coverage_json", type=Path, nargs="?", default=Path("coverage.json"))
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--threshold", type=float, default=100.0)
    parser.add_argument("--report", type=Path, default=Path("quality/changed_line_coverage.json"))
    args = parser.parse_args()

    completed = subprocess.run(
        [
            "git",
            "diff",
            "--unified=0",
            "--no-ext-diff",
            args.base,
            "--",
            "src/xrp_regime_engine/*.py",
            "src/xrp_regime_engine/**/*.py",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    changes = changed_lines(completed.stdout)
    untracked = subprocess.run(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "src/xrp_regime_engine",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for raw_path in untracked.stdout.splitlines():
        path = Path(raw_path)
        if path.suffix != ".py" or not path.is_file():
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        changes.setdefault(raw_path, set()).update(range(1, line_count + 1))

    coverage = json.loads(args.coverage_json.read_text(encoding="utf-8"))

    changed_executable = 0
    covered = 0
    missing: dict[str, list[int]] = {}
    per_file: dict[str, dict[str, object]] = {}
    for path, lines in sorted(changes.items()):
        file_data = coverage.get("files", {}).get(path)
        if not isinstance(file_data, dict):
            continue
        executed = set(file_data.get("executed_lines", []))
        missing_lines = set(file_data.get("missing_lines", []))
        executable = executed | missing_lines
        relevant = sorted(lines & executable)
        uncovered = sorted(set(relevant) & missing_lines)
        changed_executable += len(relevant)
        covered += len(relevant) - len(uncovered)
        if uncovered:
            missing[path] = uncovered
        per_file[path] = {
            "changed_executable_lines": len(relevant),
            "missing_lines": uncovered,
        }

    percent = 100.0 if changed_executable == 0 else 100.0 * covered / changed_executable
    status = "PASS" if percent >= args.threshold and not missing else "FAIL"
    report = {
        "status": status,
        "base": args.base,
        "threshold": args.threshold,
        "total_percent_covered": round(percent, 4),
        "changed_executable_lines": changed_executable,
        "covered_changed_lines": covered,
        "missing": missing,
        "files": per_file,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
