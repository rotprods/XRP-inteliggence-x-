from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from scripts.build_research_snapshot_v05 import load_profile
from xrp_regime_engine.historical_store import HistoricalRecord, PointInTimeCatalog
from xrp_regime_engine.research_snapshot import ResearchSnapshotBuilder


UTC = timezone.utc
DECISION = datetime(2026, 1, 10, 12, tzinfo=UTC)


def test_load_profile_builds_typed_unique_requirements(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "profile",
                        "requirements": [
                            {
                                "dataset": "xrp",
                                "lookback_seconds": 3600,
                                "minimum_records": 1,
                                "maximum_latest_age_seconds": 60,
                                "required": True,
                            },
                            {
                                "dataset": "cocoa",
                                "lookback_seconds": 86400,
                                "minimum_records": 0,
                                "maximum_latest_age_seconds": 86400,
                                "required": False,
                                "weight": 0.0,
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    requirements = load_profile(path, "profile")
    assert [item.dataset for item in requirements] == ["xrp", "cocoa"]
    assert requirements[0].required is True
    assert requirements[1].required is False


def test_load_profile_rejects_missing_profile_or_requirements(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"profiles": []}), encoding="utf-8")
    with pytest.raises(SystemExit, match="not registered"):
        load_profile(path, "missing")
    path.write_text(json.dumps({"profiles": [{"id": "empty", "requirements": []}]}), encoding="utf-8")
    with pytest.raises(SystemExit, match="no requirements"):
        load_profile(path, "empty")


def test_profile_requirements_drive_real_point_in_time_snapshot(tmp_path: Path) -> None:
    profile = tmp_path / "profiles.json"
    profile.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "xrp",
                        "requirements": [
                            {
                                "dataset": "xrp_usd",
                                "lookback_seconds": 86400,
                                "minimum_records": 1,
                                "maximum_latest_age_seconds": 7200,
                                "required": True,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    catalog = PointInTimeCatalog(tmp_path / "catalog.sqlite")
    record = HistoricalRecord(
        dataset="xrp_usd",
        record_id="xrp-1",
        observed_at=DECISION - timedelta(hours=1),
        available_at=DECISION,
        source="coinbase",
        revision=0,
        values={"close": 1.2},
        raw_payload_sha256="a" * 64,
    )
    catalog.add(record, partition_path="p")
    snapshot = ResearchSnapshotBuilder(catalog).build(
        decision_time=DECISION,
        requirements=load_profile(profile, "xrp"),
    )
    assert snapshot.record_count == 1
    assert snapshot.datasets[0].records[0].record_id == "xrp-1"
