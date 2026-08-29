from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from xrp_regime_engine.alerts import AlertRegistry
from xrp_regime_engine.backtest import expanding_walk_forward
from xrp_regime_engine.demo import DEMO_SUPPLEMENTAL_FEATURES, generate_demo_frame
from xrp_regime_engine.features import compute_features
from xrp_regime_engine.models import DataFlag, Horizon, ProviderHealth
from xrp_regime_engine.regime import score_regime
from xrp_regime_engine.storage import SQLiteStore


def run_demo(output: str | Path) -> dict[str, object]:
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)
    frame = generate_demo_frame()
    features = compute_features(frame, supplemental=DEMO_SUPPLEMENTAL_FEATURES)
    snapshots = [
        score_regime(features, horizon, input_flags=[DataFlag.SYNTHETIC])
        for horizon in Horizon
    ]
    db_path = output_path / "engine.sqlite3"
    store = SQLiteStore(db_path)
    health = [
        ProviderHealth(
            provider="demo_consensus",
            checked_at=datetime.now(UTC),
            status="synthetic",
            latency_ms=0.0,
            last_observation_at=frame.index[-1].to_pydatetime(),
            freshness_score=0.98,
            agreement_score=0.96,
        )
    ]
    for item in health:
        store.save_health(item)
    for snapshot in snapshots:
        store.save_snapshot(snapshot)
    backtest = expanding_walk_forward(frame, supplemental=DEMO_SUPPLEMENTAL_FEATURES)
    alerts = []
    registry = AlertRegistry()
    for snapshot in snapshots:
        alerts.extend(registry.evaluate(snapshot))

    (output_path / "features.json").write_text(
        json.dumps(features, indent=2), encoding="utf-8"
    )
    (output_path / "regime_snapshot.json").write_text(
        json.dumps([snapshot.model_dump(mode="json") for snapshot in snapshots], indent=2),
        encoding="utf-8",
    )
    (output_path / "provider_health.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in health], indent=2),
        encoding="utf-8",
    )
    (output_path / "backtest.json").write_text(
        json.dumps(backtest.__dict__, indent=2), encoding="utf-8"
    )
    (output_path / "alerts.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in alerts], indent=2),
        encoding="utf-8",
    )

    primary = next(snapshot for snapshot in snapshots if snapshot.horizon is Horizon.D1)
    explanation = "\n".join(
        [
            "# XRP Demo Regime Explanation",
            "",
            f"Generated: {primary.generated_at.isoformat()}",
            f"Regime: **{primary.regime.value}**",
            f"Bull score: **{primary.bull_score:.2f}/100**",
            f"Operational confidence: **{primary.confidence:.2%}**",
            f"Data confidence: **{primary.data_confidence:.2%}**",
            f"Model confidence: **{primary.model_confidence:.2%}**",
            f"Directional conviction: **{primary.directional_conviction:.2%}**",
            "",
            "## Drivers",
            *[f"- {driver}" for driver in primary.key_drivers],
            "",
            "## Invalidations",
            *[f"- {item}" for item in primary.invalidations],
            "",
            "> Demo data and supplemental inputs are synthetic. Confidence is operational, not a calibrated probability of correctness.",
        ]
    )
    (output_path / "explanation.md").write_text(explanation + "\n", encoding="utf-8")
    return {
        "output": str(output_path),
        "snapshots": len(snapshots),
        "backtest": backtest.__dict__,
        "alerts": len(alerts),
    }
