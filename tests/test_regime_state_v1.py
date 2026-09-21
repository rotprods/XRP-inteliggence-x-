from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.historical_contract import EligibilityClass
from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow
from xrp_regime_engine.regime_state_v1 import (
    CanonicalRegime,
    RegimeClassifierPolicy,
    RegimeSignalSpec,
    canonical_regime_policy,
    classify_regime,
)
from xrp_regime_engine.research_horizon import ResearchHorizon

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def feature_from_signals(
    index: int,
    overrides: dict[str, float] | None = None,
    *,
    omit: tuple[str, ...] = (),
    horizon: ResearchHorizon = ResearchHorizon.H1,
    provider_universe_version: str = "providers-v1",
) -> HistoricalFeatureRow:
    policy = canonical_regime_policy()
    desired = {spec.signal: 0.0 for spec in policy.specs}
    desired.update(overrides or {})
    families: dict[str, dict[str, float]] = {}
    for spec in policy.specs:
        if spec.signal in omit:
            continue
        family, name = spec.feature_key.split(".", 1)
        raw = spec.center + (desired[spec.signal] * spec.scale / spec.direction)
        families.setdefault(family, {})[name] = raw
    snapshot = sha256(f"regime:{index}".encode()).hexdigest()
    prediction = T0 + timedelta(days=index)
    return HistoricalFeatureRow.build(
        feature_time=prediction,
        prediction_time=prediction,
        horizon=horizon,
        feature_schema_version="features-v1",
        provider_universe_version=provider_universe_version,
        eligibility_class=EligibilityClass.STRICT_REPLAY,
        source_snapshot_ids=(f"snapshot:sha256:{snapshot}",),
        feature_families=families,
    )


@pytest.mark.parametrize(
    ("signals", "expected"),
    [
        ({"breakout": -0.8}, CanonicalRegime.FAILED_BREAKOUT),
        ({"deleveraging": 0.8}, CanonicalRegime.DELEVERAGING),
        (
            {"trend": -0.8, "volatility": 0.8, "drawdown_stress": 0.8},
            CanonicalRegime.CAPITULATION,
        ),
        (
            {"crowding": 0.8, "leverage": 0.8},
            CanonicalRegime.LONG_CROWDING,
        ),
        ({"distribution": 0.8}, CanonicalRegime.DISTRIBUTION),
        (
            {"breakout": 0.8, "trend": 0.5},
            CanonicalRegime.BREAKOUT,
        ),
        (
            {"trend": 0.5, "spot_flow": 0.6, "leverage": 0.1},
            CanonicalRegime.SPOT_LED_EXPANSION,
        ),
        (
            {"trend": 0.5, "leverage": 0.7, "crowding": 0.1},
            CanonicalRegime.LEVERAGED_EXPANSION,
        ),
        (
            {"trend": 0.2, "drawdown_stress": 0.5},
            CanonicalRegime.RECOVERY,
        ),
        (
            {"trend": 0.2, "relative_strength": 0.2, "liquidity": 0.5},
            CanonicalRegime.RISK_ON,
        ),
        (
            {"trend": 0.1, "spot_flow": 0.2, "leverage": 0.0},
            CanonicalRegime.ACCUMULATION,
        ),
        ({}, CanonicalRegime.NO_DATA),
    ],
)
def test_canonical_regime_rules(
    signals: dict[str, float],
    expected: CanonicalRegime,
) -> None:
    state = classify_regime(feature_from_signals(1, signals))
    assert state.regime is expected
    assert state.decision_authority is False
    assert state.execution_weight == 0
    if expected is CanonicalRegime.NO_DATA:
        assert state.confidence == 0
    else:
        assert 0 < state.confidence <= 1


def test_regime_state_is_deterministic_and_content_addressed() -> None:
    item = feature_from_signals(
        2,
        {"trend": 0.5, "spot_flow": 0.7, "leverage": 0.1},
    )
    first = classify_regime(item)
    second = classify_regime(item)
    assert first == second
    assert first.state_id == f"regime-state:sha256:{first.state_sha256}"
    assert first.policy_id.startswith("regime-policy:sha256:")
    assert first.signal_map()["trend"] == pytest.approx(0.5)
    assert first.provider_universe_version == "providers-v1"


def test_missing_required_signal_and_low_coverage_fail_to_no_data() -> None:
    missing = classify_regime(feature_from_signals(3, {"trend": 0.5}, omit=("relative_strength",)))
    assert missing.regime is CanonicalRegime.NO_DATA
    assert any(reason.startswith("MISSING_REQUIRED_SIGNALS:") for reason in missing.reasons)

    sparse_policy = RegimeClassifierPolicy(
        specs=(
            RegimeSignalSpec("trend", "market.trailing_return_30d", scale=0.30),
            RegimeSignalSpec("relative_strength", "cross_asset.xrp_btc_return_30d", scale=0.25),
            RegimeSignalSpec("spot_flow", "microstructure.spot_flow_imbalance"),
        ),
        required_signals=("trend",),
        min_signal_coverage=1.0,
    )
    sparse = feature_from_signals(
        4,
        {"trend": 0.5},
        omit=("relative_strength", "spot_flow"),
    )
    state = classify_regime(sparse, policy=sparse_policy)
    assert state.regime is CanonicalRegime.NO_DATA
    assert "INSUFFICIENT_SIGNAL_COVERAGE" in state.reasons


def test_signal_spec_transform_clips_and_direction_can_invert() -> None:
    item = feature_from_signals(5, {"trend": 1.0})
    spec = RegimeSignalSpec(
        "inverse_trend",
        "market.trailing_return_30d",
        center=0,
        scale=0.01,
        direction=-1,
    )
    assert spec.transform(item) == -1.0

    missing = RegimeSignalSpec(
        "missing",
        "market.not_present",
    )
    assert missing.transform(item) is None


def test_policy_and_signal_validation_fail_closed() -> None:
    with pytest.raises(ValueError, match="scale"):
        RegimeSignalSpec("x", "market.x", scale=0)
    with pytest.raises(ValueError, match="direction"):
        RegimeSignalSpec("x", "market.x", direction=0)
    with pytest.raises(ValueError, match="signal specs"):
        RegimeClassifierPolicy(specs=(), required_signals=())
    with pytest.raises(ValueError, match="unique"):
        RegimeClassifierPolicy(
            specs=(
                RegimeSignalSpec("x", "market.x"),
                RegimeSignalSpec("x", "market.y"),
            ),
            required_signals=(),
        )
    with pytest.raises(ValueError, match="required_signals"):
        RegimeClassifierPolicy(
            specs=(RegimeSignalSpec("x", "market.x"),),
            required_signals=("y",),
        )
    with pytest.raises(ValueError, match="min_signal_coverage"):
        RegimeClassifierPolicy(
            specs=(RegimeSignalSpec("x", "market.x"),),
            required_signals=(),
            min_signal_coverage=0,
        )
    with pytest.raises(ValueError, match="negative regime thresholds"):
        RegimeClassifierPolicy(
            specs=(RegimeSignalSpec("x", "market.x"),),
            required_signals=(),
            failed_breakout_threshold=0.1,
        )


def test_signal_feature_key_requires_family_name() -> None:
    item = feature_from_signals(6)
    spec = RegimeSignalSpec("bad", "notdotted")
    with pytest.raises(ValueError, match="family.name"):
        spec.transform(item)


def test_missing_optional_signal_is_not_treated_as_neutral_evidence() -> None:
    item = feature_from_signals(
        7,
        {
            "trend": 0.5,
            "spot_flow": 0.7,
        },
        omit=("leverage",),
    )
    state = classify_regime(item)
    assert state.signal_coverage > 0.70
    assert state.regime is CanonicalRegime.NO_DATA
    assert "NO_RULE_WITH_SUFFICIENT_SEPARATION" in state.reasons



def test_regime_numeric_and_text_validators_fail_closed() -> None:
    with pytest.raises(ValueError, match="finite"):
        RegimeSignalSpec("x", "market.x", center=float("nan"))
    with pytest.raises(ValueError, match="signal"):
        RegimeSignalSpec(" ", "market.x")
    with pytest.raises(ValueError, match="feature_key"):
        RegimeSignalSpec("x", " ")
    with pytest.raises(ValueError, match=r"within \[0, 1\]"):
        RegimeClassifierPolicy(
            specs=(RegimeSignalSpec("x", "market.x"),),
            required_signals=(),
            breakout_threshold=2.0,
        )
