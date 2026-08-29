from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[1]


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_mutation_policy_parser_passes_and_fails_threshold(tmp_path: Path) -> None:
    xml = tmp_path / "mutmut.xml"
    xml.write_text(
        '<testsuites><testsuite tests="10" failures="1" errors="0" skipped="0"/></testsuites>',
        encoding="utf-8",
    )
    report = tmp_path / "report.json"
    passed = run_script(
        "scripts/check_mutation_score.py",
        str(xml),
        "--threshold",
        "90",
        "--report",
        str(report),
    )
    assert passed.returncode == 0, passed.stderr
    assert json.loads(report.read_text())["mutation_score"] == 90.0

    failed = run_script(
        "scripts/check_mutation_score.py",
        str(xml),
        "--threshold",
        "91",
        "--report",
        str(report),
    )
    assert failed.returncode == 1


def test_mutation_policy_parser_rejects_empty_report(tmp_path: Path) -> None:
    empty = tmp_path / "empty.xml"
    empty.write_text("<testsuites></testsuites>", encoding="utf-8")
    result = run_script("scripts/check_mutation_score.py", str(empty))
    assert result.returncode != 0


def test_quality_evidence_aggregates_known_inputs(tmp_path: Path) -> None:
    coverage = tmp_path / "coverage.json"
    coverage.write_text('{"status":"PASS","global":{"line":100,"branch":100}}', encoding="utf-8")
    diff = tmp_path / "diff.json"
    diff.write_text('{"total_percent_covered":100}', encoding="utf-8")
    mutation = tmp_path / "mutation.json"
    mutation.write_text('{"status":"PASS","mutation_score":92}', encoding="utf-8")
    flake = tmp_path / "flake.json"
    flake.write_text('{"status":"PASS","failing_seeds":[]}', encoding="utf-8")
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        '<testsuites><testsuite tests="220" failures="0" errors="0" skipped="1"/></testsuites>',
        encoding="utf-8",
    )
    wheel = tmp_path / "pkg.whl"
    wheel.write_bytes(b"wheel")
    output = tmp_path / "quality.json"

    result = run_script(
        "scripts/quality_evidence.py",
        "--coverage",
        str(coverage),
        "--diff-coverage",
        str(diff),
        "--mutation",
        str(mutation),
        "--flake",
        str(flake),
        "--pytest-junit",
        str(junit),
        "--wheel",
        str(wheel),
        "--python-versions",
        "3.11,3.12,3.13",
        "--runner-minutes",
        "3.5",
        "--output",
        str(output),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text())
    assert payload["pytest"]["tests"] == 220
    assert payload["changed_line_coverage"] == 100.0
    assert payload["mutation"]["mutation_score"] == 92
    assert payload["validated_python_versions"] == ["3.11", "3.12", "3.13"]
    assert payload["paid_api_calls"] == 0
    assert payload["production_ready"] is False
    assert len(payload["wheel_sha256"]) == 64


def test_flake_gate_rejects_invalid_run_count() -> None:
    result = run_script("scripts/run_flake_gate.py", "--runs", "0")
    assert result.returncode != 0
    assert "between 1 and 25" in result.stderr
