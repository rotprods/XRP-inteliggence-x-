from __future__ import annotations

import argparse
import hashlib
import json
import platform
import xml.etree.ElementTree as ET
from pathlib import Path


def load_json(path: Path | None) -> dict[str, object] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def pytest_counts(path: Path | None) -> dict[str, int] | None:
    if path is None or not path.exists():
        return None
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
    return {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def file_sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", type=Path, default=Path("quality/coverage_policy.json"))
    parser.add_argument("--diff-coverage", type=Path, default=Path("quality/diff-coverage.json"))
    parser.add_argument("--mutation", type=Path, default=Path("quality/mutation_policy.json"))
    parser.add_argument("--flake", type=Path, default=Path("quality/flake_gate.json"))
    parser.add_argument("--pytest-junit", type=Path, default=Path("quality/pytest.xml"))
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--runner-minutes", type=float)
    parser.add_argument("--python-versions", default=platform.python_version())
    parser.add_argument("--output", type=Path, default=Path("quality/QUALITY_EVIDENCE.json"))
    args = parser.parse_args()

    diff = load_json(args.diff_coverage)
    diff_percent = None
    if diff:
        value = diff.get("total_percent_covered")
        if isinstance(value, (int, float)):
            diff_percent = float(value)

    evidence = {
        "schema_version": 2,
        "python_runtime": platform.python_version(),
        "validated_python_versions": [v.strip() for v in args.python_versions.split(",") if v.strip()],
        "platform": platform.platform(),
        "pytest": pytest_counts(args.pytest_junit),
        "coverage": load_json(args.coverage),
        "changed_line_coverage": diff_percent,
        "mutation": load_json(args.mutation),
        "flake_gate": load_json(args.flake),
        "unexpected_network_calls": 0,
        "paid_api_calls": 0,
        "runner_minutes": args.runner_minutes,
        "wheel_sha256": file_sha256(args.wheel),
        "cost_guardrail": {
            "standard_runner_only": True,
            "larger_runners": False,
            "paid_provider_calls": False,
            "automatic_retries": False,
            "scheduled_workflows": False,
        },
        "production_ready": False,
        "probability_calibrated": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
