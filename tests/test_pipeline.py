from __future__ import annotations

import json
from pathlib import Path

from xrp_regime_engine.models import DataFlag, RegimeSnapshot
from xrp_regime_engine.pipeline import run_demo
from xrp_regime_engine.storage import SQLiteStore


def test_demo_pipeline_writes_auditable_synthetic_outputs(tmp_path: Path) -> None:
    output = tmp_path / "demo"
    result = run_demo(output)

    assert result["snapshots"] == 4
    assert result["backtest"]["probability_calibrated"] is False
    expected = {
        "alerts.json",
        "backtest.json",
        "engine.sqlite3",
        "explanation.md",
        "features.json",
        "provider_health.json",
        "regime_snapshot.json",
    }
    assert expected.issubset({path.name for path in output.iterdir()})

    snapshots = [
        RegimeSnapshot.model_validate(item)
        for item in json.loads((output / "regime_snapshot.json").read_text(encoding="utf-8"))
    ]
    assert {snapshot.horizon.value for snapshot in snapshots} == {"1h", "4h", "1d", "1w"}
    assert all(DataFlag.SYNTHETIC in snapshot.data_flags for snapshot in snapshots)
    assert all(snapshot.output_blocked is False for snapshot in snapshots)

    explanation = (output / "explanation.md").read_text(encoding="utf-8")
    assert "not a calibrated probability" in explanation
    assert "synthetic" in explanation.lower()

    store = SQLiteStore(output / "engine.sqlite3")
    assert store.schema_version() == 1
    assert store.latest_snapshot("XRP", "1d") is not None
    assert store.audit_event_count() == 5
