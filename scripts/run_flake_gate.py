from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the critical hermetic suite under fixed randomized seeds")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("quality/flake_gate.json"))
    parser.add_argument("--selection", default="not live and not slow")
    parser.add_argument("--base-seed", type=int, default=41000)
    args = parser.parse_args()
    if args.runs < 1 or args.runs > 25:
        raise SystemExit("--runs must be between 1 and 25")

    base_env = os.environ.copy()
    base_env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": "src",
            "TZ": "UTC",
        }
    )
    attempts: list[dict[str, object]] = []
    started = time.monotonic()
    for offset in range(args.runs):
        seed = args.base_seed + offset
        env = dict(base_env)
        env["Q1_TEST_ORDER_SEED"] = str(seed)
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-m",
            args.selection,
            "--ignore=tests/test_quality_tooling.py",
        ]
        attempt_started = time.monotonic()
        completed = subprocess.run(
            command,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45,
            check=False,
        )
        attempts.append(
            {
                "seed": seed,
                "returncode": completed.returncode,
                "seconds": round(time.monotonic() - attempt_started, 3),
            }
        )
        if completed.returncode != 0:
            break

    failures = [attempt for attempt in attempts if attempt["returncode"] != 0]
    report = {
        "status": "PASS" if not failures and len(attempts) == args.runs else "FAIL",
        "requested_runs": args.runs,
        "executed_runs": len(attempts),
        "selection": args.selection,
        "seconds": round(time.monotonic() - started, 3),
        "attempts": attempts,
        "failing_seeds": [attempt["seed"] for attempt in failures],
        "retry_until_green": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
