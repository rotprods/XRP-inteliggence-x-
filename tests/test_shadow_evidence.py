from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.consensus import ConsensusResult
from xrp_regime_engine.models import DataFlag
from xrp_regime_engine.shadow_evidence import (
    IndependentPriceAnchor,
    build_shadow_evidence_vector,
)
from xrp_regime_engine.stream_alignment import CrossStreamAlignment
from xrp_regime_engine.temporal_alignment import AlignedTemporalWindow
from xrp_regime_engine.temporal_flow import TemporalFlowWindow
from xrp_regime_engine.trade_attribution import DepthTradeCompatibility

NOW = datetime(2026, 9, 21, 8, 0, tzinfo=UTC)
PREDICTION = NOW + timedelta(seconds=60)


def _consensus(
    *,
    valid: bool = True,
    value: float | None = 1.4,
    providers: tuple[str, ...] = ("binance", "kucoin"),
    provider_count: int = 2,
    flags: tuple[DataFlag, ...] = (),
) -> ConsensusResult:
    return ConsensusResult(
        value=value,
        provider_count=provider_count,
        input_provider_count=len(providers),
        rejected_provider_count=max(len(providers) - provider_count, 0),
        relative_spread=0.001,
        agreement_score=0.95,
        freshness_score=0.9,
        valid=valid,
        providers=providers,
        flags=flags,
    )


def _anchor(**overrides: object) -> IndependentPriceAnchor:
    values: dict[str, object] = {
        "asset": "XRP_USDT",
        "observed_at": NOW + timedelta(seconds=55),
        "available_at": NOW + timedelta(seconds=56),
        "fetched_at": NOW + timedelta(seconds=57),
        "consensus": _consensus(),
    }
    values.update(overrides)
    return IndependentPriceAnchor(**values)  # type: ignore[arg-type]


def _window() -> TemporalFlowWindow:
    return TemporalFlowWindow(
        symbol="XRPUSDT",
        prediction_time=PREDICTION,
        window_seconds=60,
        sample_count=10,
        first_observed_at=NOW,
        last_observed_at=NOW + timedelta(seconds=58),
        mid_return_bps=12.0,
        mean_depth_imbalance_25bps=0.2,
        aggressive_buy_notional=600.0,
        aggressive_sell_notional=400.0,
        cvd_quote=200.0,
        taker_imbalance=0.2,
        open_interest_delta_pct=0.01,
        funding_delta_bps=0.2,
        basis_delta_bps=1.5,
        last_sample_age_seconds=2.0,
        freshness_limit_seconds=15,
        ingestion_lag_seconds=0.1,
        ingestion_lag_limit_seconds=5,
        regime_eligible=True,
        quality_flags=(),
        execution_weight=0.0,
    )


def _aligned(*, eligible: bool = True) -> AlignedTemporalWindow:
    alignment = CrossStreamAlignment(
        symbol="XRPUSDT",
        prediction_time=PREDICTION,
        depth_age_seconds=1.0,
        agg_trades_age_seconds=1.0,
        open_interest_age_seconds=2.0,
        funding_age_seconds=2.0,
        basis_age_seconds=2.0,
        max_observed_skew_seconds=1.0,
        point_in_time_eligible=eligible,
        evidence_eligible=eligible,
        regime_eligible=False,
        quality_flags=("ALIGNED",),
        execution_weight=0.0,
    )
    return AlignedTemporalWindow(
        alignment=alignment,
        window=_window() if eligible else None,
        evidence_eligible=eligible,
        quality_flags=("ALIGNED",),
        execution_weight=0.0,
    )


def _compatibility(**overrides: object) -> DepthTradeCompatibility:
    values: dict[str, object] = {
        "symbol": "XRPUSDT",
        "observed_at": NOW + timedelta(seconds=58),
        "prediction_time": PREDICTION,
        "event_end_skew_seconds": 0.1,
        "window_skew_seconds": 0.1,
        "depth_window_seconds": 1.0,
        "flow_window_seconds": 1.0,
        "point_in_time_eligible": True,
        "bid_removed_notional": 100.0,
        "ask_removed_notional": 100.0,
        "aggressive_buy_notional": 90.0,
        "aggressive_sell_notional": 80.0,
        "bid_trade_compatible_notional": 80.0,
        "ask_trade_compatible_notional": 90.0,
        "trade_compatible_removed_notional": 170.0,
        "removal_candidate_residual_notional": 30.0,
        "unmatched_aggressive_trade_notional": 0.0,
        "removal_coverage_ratio": 0.85,
        "evidence_eligible": True,
        "regime_eligible": False,
        "causal_attribution_confirmed": False,
        "quality_flags": ("TRADE_CONSUMPTION_COMPATIBLE_ONLY",),
        "execution_weight": 0.0,
    }
    values.update(overrides)
    return DepthTradeCompatibility(**values)  # type: ignore[arg-type]


def test_builds_uncalibrated_non_executable_vector_with_independent_anchor() -> None:
    vector = build_shadow_evidence_vector(_aligned(), independent_anchor=_anchor())
    assert vector is not None
    assert vector.independent_price == pytest.approx(1.4)
    assert vector.independent_provider_count == 2
    assert vector.independent_external_provider_count == 1
    assert vector.calibrated is False
    assert vector.probability is None
    assert vector.decision_authority is False
    assert vector.execution_weight == 0.0
    assert "UNCALIBRATED_SHADOW_ONLY" in vector.quality_flags


def test_blocked_alignment_and_future_anchor_fail_closed() -> None:
    assert (
        build_shadow_evidence_vector(
            _aligned(eligible=False), independent_anchor=_anchor()
        )
        is None
    )
    assert (
        build_shadow_evidence_vector(
            _aligned(),
            independent_anchor=_anchor(fetched_at=PREDICTION + timedelta(seconds=1)),
        )
        is None
    )


@pytest.mark.parametrize(
    "consensus",
    (
        _consensus(valid=False),
        _consensus(value=None),
        _consensus(provider_count=1),
        _consensus(providers=("binance", "binance_microstructure")),
    ),
)
def test_invalid_or_non_independent_consensus_fails_closed(consensus: ConsensusResult) -> None:
    assert (
        build_shadow_evidence_vector(
            _aligned(),
            independent_anchor=_anchor(consensus=consensus),
        )
        is None
    )


def test_anchor_validation_and_asset_mismatch_fail_closed() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _anchor(observed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="observed <= available <= fetched"):
        _anchor(available_at=NOW)
    with pytest.raises(ValueError, match="asset is required"):
        _anchor(asset="")
    with pytest.raises(ValueError, match="source_family is required"):
        _anchor(source_family="")
    with pytest.raises(ValueError, match="asset must match"):
        build_shadow_evidence_vector(_aligned(), independent_anchor=_anchor(asset="BTC_USDT"))


def test_compatibility_must_match_and_be_point_in_time_eligible() -> None:
    with pytest.raises(ValueError, match="symbol must match"):
        build_shadow_evidence_vector(
            _aligned(),
            independent_anchor=_anchor(),
            compatibility=_compatibility(symbol="BTCUSDT"),
        )
    with pytest.raises(ValueError, match="prediction_time must match"):
        build_shadow_evidence_vector(
            _aligned(),
            independent_anchor=_anchor(),
            compatibility=_compatibility(prediction_time=PREDICTION - timedelta(seconds=1)),
        )
    assert (
        build_shadow_evidence_vector(
            _aligned(),
            independent_anchor=_anchor(),
            compatibility=_compatibility(point_in_time_eligible=False),
        )
        is None
    )


def test_compatible_depth_trade_evidence_is_carried_without_causal_or_probability_claim() -> None:
    vector = build_shadow_evidence_vector(
        _aligned(),
        independent_anchor=_anchor(consensus=_consensus(flags=(DataFlag.OUTLIER,))),
        compatibility=_compatibility(),
    )
    assert vector is not None
    assert vector.depth_trade_coverage_ratio == pytest.approx(0.85)
    assert vector.removal_candidate_residual_notional == pytest.approx(30.0)
    assert "TRADE_CONSUMPTION_COMPATIBLE_ONLY" in vector.quality_flags
    assert "CONSENSUS_OUTLIER" in vector.quality_flags
    assert vector.probability is None
    assert vector.decision_authority is False
    assert vector.execution_weight == 0.0
