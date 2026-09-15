
import pytest
from copy import deepcopy

from xrp_regime_engine.demo import DEMO_SUPPLEMENTAL_FEATURES, generate_demo_frame
from xrp_regime_engine.features import compute_features
from xrp_regime_engine.models import Horizon, RegimeLabel
from xrp_regime_engine.regime import score_regime


def _demo_features() -> dict[str, float | None]:
    return compute_features(
        generate_demo_frame(), supplemental=DEMO_SUPPLEMENTAL_FEATURES
    )


def test_regime_snapshot_is_bounded_and_semantically_split() -> None:
    snapshot = score_regime(_demo_features(), Horizon.D1)
    assert 0 <= snapshot.bull_score <= 100
    assert 0 <= snapshot.confidence <= 1
    assert 0 <= snapshot.data_confidence <= 1
    assert 0 <= snapshot.model_confidence <= 1
    assert 0 <= snapshot.directional_conviction <= 1
    assert snapshot.regime in set(RegimeLabel)
    assert snapshot.key_drivers
    assert snapshot.output_blocked is False


def test_low_quality_degrades_output_without_changing_direction_score() -> None:
    high_quality = _demo_features()
    low_quality = deepcopy(high_quality)
    low_quality.update(provider_agreement=0.1, freshness_score=0.1, source_coverage=0.1)
    high_snapshot = score_regime(high_quality, Horizon.D1)
    low_snapshot = score_regime(low_quality, Horizon.D1)
    assert low_snapshot.regime is RegimeLabel.DEGRADED
    assert low_snapshot.output_blocked is True
    assert low_snapshot.bull_score == high_snapshot.bull_score
    assert low_snapshot.data_confidence < high_snapshot.data_confidence


def test_missing_supplemental_data_blocks_output() -> None:
    snapshot = score_regime(compute_features(generate_demo_frame()), Horizon.D1)
    assert snapshot.regime is RegimeLabel.DEGRADED
    assert snapshot.output_blocked is True
    assert snapshot.block_reasons


def test_snapshot_hashes_are_deterministic_and_input_sensitive() -> None:
    features = _demo_features()
    first = score_regime(features, Horizon.D1)
    second = score_regime(deepcopy(features), Horizon.D1)

    assert first.policy_version
    assert len(first.policy_digest) == 64
    assert len(first.feature_hash) == 64
    assert first.policy_digest == second.policy_digest
    assert first.feature_hash == second.feature_hash
    assert first.feature_values == second.feature_values

    changed = deepcopy(features)
    assert changed["xrp_return_7d"] is not None
    changed["xrp_return_7d"] = float(changed["xrp_return_7d"]) + 0.01
    changed_snapshot = score_regime(changed, Horizon.D1)
    assert changed_snapshot.feature_hash != first.feature_hash


def test_scale_rejects_non_positive_width() -> None:
    from xrp_regime_engine import regime

    with pytest.raises(ValueError, match="width must be positive"):
        regime._scale(1.0, width=0)


def test_historical_analogues_ignore_missing_and_empty_feature_sets() -> None:
    from xrp_regime_engine import regime

    assert regime.historical_analogues({}) == []
    partial = regime.historical_analogues({"xrp_return_30d": None, "btc_return_30d": -0.3})
    assert partial


def test_low_directional_coverage_blocks_output() -> None:
    from xrp_regime_engine.regime import score_regime
    from xrp_regime_engine.models import Horizon, DataFlag

    features = {
        "provider_agreement": 1.0,
        "freshness_score": 1.0,
        "source_coverage": 1.0,
        "feature_cadence_seconds": 86400.0,
        "xrp_return_7d": 0.1,
    }
    snapshot = score_regime(features, Horizon.D1)
    assert snapshot.output_blocked
    assert DataFlag.MISSING in snapshot.data_flags
    assert any("directional feature coverage" in reason for reason in snapshot.block_reasons)


def test_strong_bear_regime_is_reachable_with_complete_extreme_features() -> None:
    from xrp_regime_engine.regime import score_regime
    from xrp_regime_engine.models import Horizon, RegimeLabel

    features = {
        "feature_cadence_seconds": 86400.0,
        "provider_agreement": 1.0,
        "freshness_score": 1.0,
        "source_coverage": 1.0,
        "ndx_return_20d": -1.0,
        "dxy_return_20d": 1.0,
        "us10y_change_20d": 5.0,
        "vix_z_20d": 10.0,
        "btc_return_7d": -1.0,
        "btc_return_30d": -1.0,
        "eth_btc_return_7d": -1.0,
        "btc_dominance_change_20d": 1.0,
        "xrp_return_7d": -1.0,
        "xrp_return_30d": -1.0,
        "xrp_btc_return_7d": -1.0,
        "xrp_btc_return_30d": -1.0,
        "xrp_ma100_distance": -1.0,
        "funding_z": 2.5,
        "oi_price_divergence": 2.0,
        "liquidation_impulse": -1.0,
        "xrpl_activity_z": -2.0,
        "xrp_rsi_14": 10.0,
        "xrp_ma20_distance": -1.0,
        "xrp_vol_30d": 0.1,
    }
    snapshot = score_regime(features, Horizon.D1)
    assert snapshot.output_blocked is False
    assert snapshot.regime in {RegimeLabel.BEARISH, RegimeLabel.STRONG_BEAR}
    assert snapshot.bull_score < 43
