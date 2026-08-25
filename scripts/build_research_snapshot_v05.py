from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from xrp_regime_engine.historical_store import PointInTimeCatalog
from xrp_regime_engine.research_snapshot import (
    DatasetRequirement,
    ResearchSnapshotBuilder,
    ResearchSnapshotStore,
    SnapshotUnavailable,
)


def parse_timestamp(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def load_profile(path: Path, profile_id: str) -> tuple[DatasetRequirement, ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    profiles = document.get("profiles")
    if not isinstance(profiles, list):
        raise SystemExit("snapshot-profile registry has no profiles list")
    selected: Mapping[str, Any] | None = None
    for profile in profiles:
        if isinstance(profile, Mapping) and profile.get("id") == profile_id:
            selected = profile
            break
    if selected is None:
        raise SystemExit(f"snapshot profile is not registered: {profile_id}")
    raw_requirements = selected.get("requirements")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        raise SystemExit("snapshot profile has no requirements")
    requirements: list[DatasetRequirement] = []
    for raw in raw_requirements:
        if not isinstance(raw, Mapping):
            raise SystemExit("snapshot requirement must be an object")
        requirements.append(
            DatasetRequirement(
                dataset=str(raw["dataset"]),
                lookback=timedelta(seconds=int(raw["lookback_seconds"])),
                minimum_records=int(raw["minimum_records"]),
                maximum_latest_age=timedelta(seconds=int(raw["maximum_latest_age_seconds"])),
                required=bool(raw.get("required", True)),
            )
        )
    return tuple(requirements)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a fail-closed point-in-time research snapshot")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--decision-time", type=parse_timestamp, required=True)
    parser.add_argument(
        "--profiles",
        type=Path,
        default=Path("config/research_snapshot_profiles_v05.json"),
    )
    parser.add_argument("--output-root", type=Path, default=Path("state/research"))
    parser.add_argument("--report", type=Path, default=Path("reports/research-snapshot-v05.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requirements = load_profile(args.profiles, args.profile)
    catalog = PointInTimeCatalog(args.catalog)
    try:
        snapshot = ResearchSnapshotBuilder(catalog).build(
            decision_time=args.decision_time,
            requirements=requirements,
        )
    except SnapshotUnavailable as exc:
        document = {
            "version": "0.5.0",
            "profile": args.profile,
            "decision_time": args.decision_time.isoformat(),
            "status": "BLOCKED",
            "reason": str(exc),
            "production_release": "BLOCKED",
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(document, indent=2, sort_keys=True))
        return 2

    relative = ResearchSnapshotStore(args.output_root).put(snapshot)
    document = {
        "version": "0.5.0",
        "profile": args.profile,
        "decision_time": args.decision_time.isoformat(),
        "status": "PASS",
        "snapshot_path": str(relative),
        "snapshot_sha256": snapshot.snapshot_sha256,
        "record_count": snapshot.record_count,
        "datasets": [dataset.to_dict(include_records=False) for dataset in snapshot.datasets],
        "production_release": "BLOCKED",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
