from datetime import UTC, datetime
from pathlib import Path

from xrp_regime_engine.demo import DEMO_SUPPLEMENTAL_FEATURES, generate_demo_frame
from xrp_regime_engine.features import compute_features
from xrp_regime_engine.models import Horizon, ProviderHealth
from xrp_regime_engine.regime import score_regime
from xrp_regime_engine.storage import SCHEMA_VERSION, SQLiteStore


def _snapshot():
    return score_regime(
        compute_features(generate_demo_frame(), supplemental=DEMO_SUPPLEMENTAL_FEATURES),
        Horizon.D1,
    )


def test_round_trip_and_schema_metadata(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "engine.sqlite3")
    snapshot = _snapshot()
    store.save_snapshot(snapshot)
    loaded = store.latest_snapshot("XRP", "1d")
    assert loaded is not None
    assert loaded.bull_score == snapshot.bull_score
    assert loaded.data_confidence == snapshot.data_confidence
    assert store.schema_version() == SCHEMA_VERSION
    assert store.audit_event_count() == 1


def test_idempotent_snapshot_and_health_upserts(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "engine.sqlite3")
    snapshot = _snapshot()
    store.save_snapshot(snapshot)
    store.save_snapshot(snapshot)

    checked_at = datetime.now(UTC)
    health = ProviderHealth(
        provider="coinbase",
        checked_at=checked_at,
        status="ok",
        freshness_score=1.0,
        agreement_score=1.0,
    )
    store.save_health(health)
    updated = health.model_copy(update={"status": "degraded", "freshness_score": 0.5})
    store.save_health(updated)

    latest = store.latest_health()
    assert len(latest) == 1
    assert latest[0].status == "degraded"
    assert store.audit_event_count() == 4
