from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Threshold:
    line: float
    branch: float


GLOBAL = Threshold(line=95.0, branch=92.0)
CRITICAL = Threshold(line=98.0, branch=95.0)
CRITICAL_SUFFIXES = {
    "src/xrp_regime_engine/models.py",
    "src/xrp_regime_engine/consensus.py",
    "src/xrp_regime_engine/features.py",
    "src/xrp_regime_engine/regime.py",
    "src/xrp_regime_engine/backtest.py",
    "src/xrp_regime_engine/storage.py",
    "src/xrp_regime_engine/api.py",
    "src/xrp_regime_engine/providers/base.py",
    "src/xrp_regime_engine/providers/binance.py",
    "src/xrp_regime_engine/providers/coinbase.py",
    "src/xrp_regime_engine/providers/kraken.py",
    "src/xrp_regime_engine/providers/kucoin.py",
    "src/xrp_regime_engine/providers/fred.py",
    "src/xrp_regime_engine/providers/xrpl.py",
}


def percentage(covered: int, total: int) -> float:
    return 100.0 if total == 0 else covered * 100.0 / total


def metrics(summary: dict[str, int | float]) -> tuple[float, float]:
    line = percentage(int(summary["covered_lines"]), int(summary["num_statements"]))
    branch = percentage(int(summary.get("covered_branches", 0)), int(summary.get("num_branches", 0)))
    return line, branch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage_json", type=Path, nargs="?", default=Path("coverage.json"))
    parser.add_argument("--report", type=Path, default=Path("quality/coverage_policy.json"))
    args = parser.parse_args()

    payload = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    failures: list[str] = []
    files: dict[str, dict[str, object]] = {}

    total_line, total_branch = metrics(payload["totals"])
    if total_line < GLOBAL.line:
        failures.append(f"global line coverage {total_line:.2f}% < {GLOBAL.line:.2f}%")
    if total_branch < GLOBAL.branch:
        failures.append(f"global branch coverage {total_branch:.2f}% < {GLOBAL.branch:.2f}%")

    for path, data in payload["files"].items():
        if path not in CRITICAL_SUFFIXES:
            continue
        line, branch = metrics(data["summary"])
        files[path] = {"line": round(line, 4), "branch": round(branch, 4)}
        if line < CRITICAL.line:
            failures.append(f"{path} line coverage {line:.2f}% < {CRITICAL.line:.2f}%")
        if branch < CRITICAL.branch:
            failures.append(f"{path} branch coverage {branch:.2f}% < {CRITICAL.branch:.2f}%")

    result = {
        "status": "PASS" if not failures else "FAIL",
        "global": {"line": round(total_line, 4), "branch": round(total_branch, 4)},
        "thresholds": {
            "global_line": GLOBAL.line,
            "global_branch": GLOBAL.branch,
            "critical_line": CRITICAL.line,
            "critical_branch": CRITICAL.branch,
        },
        "critical_modules": files,
        "failures": failures,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
