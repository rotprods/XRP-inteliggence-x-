from xrp_regime_engine.alerts import AlertRegistry
from xrp_regime_engine.demo import DEMO_SUPPLEMENTAL_FEATURES, generate_demo_frame
from xrp_regime_engine.features import compute_features
from xrp_regime_engine.models import Horizon
from xrp_regime_engine.regime import score_regime


def test_alert_deduplication() -> None:
    snapshot = score_regime(
        compute_features(generate_demo_frame(), supplemental=DEMO_SUPPLEMENTAL_FEATURES),
        Horizon.D1,
    )
    snapshot.distribution_risk = 90
    registry = AlertRegistry()
    assert len(registry.evaluate(snapshot)) >= 1
    assert registry.evaluate(snapshot) == []


def test_blocked_snapshot_emits_data_alert_only() -> None:
    snapshot = score_regime(compute_features(generate_demo_frame()), Horizon.D1)
    events = AlertRegistry().evaluate(snapshot)
    assert [event.rule_id for event in events] == ["data_degraded"]
