from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.depth_dynamics import DepthDynamics
from xrp_regime_engine.derivatives import FundingState, OpenInterestState
from xrp_regime_engine.order_flow import OrderFlowState
from xrp_regime_engine.stream_alignment import (
    CrossStreamFreshnessPolicy,
    assess_cross_stream_alignment,
)

T0 = datetime(2026, 9, 21, 4, 0, tzinfo=UTC)


def depth(seconds: int = 8) -> DepthDynamics:
    observed = T0 + timedelta(seconds=seconds)
    return DepthDynamics(
        symbol="XRPUSDT",
        observed_at=observed,
        first_update_id=1,
        final_update_id=2,
        elapsed_seconds=1.0,
        bid_added_notional=100.0,
        bid_removed_notional=50.0,
        ask_added_notional=25.0,
        ask_removed_notional=75.0,
        bid_net_notional=50.0,
        ask_net_notional=-50.0,
        gross_churn_notional=250.0,
        churn_quote_per_second=250.0,
        trade_attribution_confirmed=False,
        quality_flags=("TRADE_ATTRIBUTION_REQUIRED",),
        first_observed_at=observed - timedelta(seconds=1),
        last_observed_at=observed,
        first_available_at=observed - timedelta(milliseconds=900),
        last_available_at=observed + timedelta(milliseconds=100),
        first_fetched_at=observed - timedelta(milliseconds=800),
        last_fetched_at=observed + timedelta(milliseconds=200),
        provenance_complete=True,
        execution_weight=0.0,
    )


def flow(seconds: int = 8) -> OrderFlowState:
    observed = T0 + timedelta(seconds=seconds)
    return OrderFlowState(
        symbol="XRPUSDT",
        observed_at=observed,
        aggressive_buy_notional=600.0,
        aggressive_sell_notional=400.0,
        cvd_quote=200.0,
        taker_imbalance=0.2,
        trade_count=10,
        first_observed_at=observed - timedelta(seconds=1),
        last_observed_at=observed,
        first_available_at=observed - timedelta(milliseconds=900),
        last_available_at=observed + timedelta(milliseconds=100),
        first_fetched_at=observed - timedelta(milliseconds=800),
        last_fetched_at=observed + timedelta(milliseconds=200),
        provenance_complete=True,
    )


def funding(seconds: int = 8) -> FundingState:
    observed = T0 + timedelta(seconds=seconds)
    return FundingState(
        symbol="XRPUSDT",
        observed_at=observed,
        mark_price=1.401,
        index_price=1.400,
        funding_rate=0.0001,
        next_funding_at=T0 + timedelta(hours=8),
        available_at=observed + timedelta(milliseconds=100),
        fetched_at=observed + timedelta(milliseconds=200),
        payload_sha256="a" * 64,
    )


def open_interest(seconds: int = 8) -> OpenInterestState:
    observed = T0 + timedelta(seconds=seconds)
    return OpenInterestState(
        symbol="XRPUSDT",
        observed_at=observed,
        open_interest=100_000_000.0,
        available_at=observed + timedelta(milliseconds=100),
        fetched_at=observed + timedelta(milliseconds=200),
        payload_sha256="b" * 64,
    )


def test_complete_aligned_streams_pass_point_in_time_gate_only() -> None:
    result = assess_cross_stream_alignment(
        depth=depth(),
        order_flow=flow(),
        funding=funding(),
        open_interest=open_interest(),
        prediction_time=T0 + timedelta(seconds=10),
    )
    assert result.point_in_time_eligible is True
    assert result.evidence_eligible is True
    assert result.regime_eligible is False
    assert result.quality_flags == ()
    assert result.execution_weight == 0.0


def test_incomplete_funding_and_basis_provenance_fail_closed() -> None:
    incomplete = FundingState(
        symbol="XRPUSDT",
        observed_at=T0 + timedelta(seconds=8),
        mark_price=1.401,
        index_price=1.400,
        funding_rate=0.0001,
        next_funding_at=T0 + timedelta(hours=8),
        payload_sha256="c" * 64,
    )
    result = assess_cross_stream_alignment(
        depth=depth(),
        order_flow=flow(),
        funding=incomplete,
        open_interest=open_interest(),
        prediction_time=T0 + timedelta(seconds=10),
    )
    assert result.point_in_time_eligible is False
    assert "FUNDING_PROVENANCE_INCOMPLETE" in result.quality_flags
    assert "BASIS_PROVENANCE_INCOMPLETE" in result.quality_flags


def test_future_fetched_open_interest_is_blocked() -> None:
    observed = T0 + timedelta(seconds=8)
    future_fetch = OpenInterestState(
        symbol="XRPUSDT",
        observed_at=observed,
        open_interest=100_000_000.0,
        available_at=observed + timedelta(milliseconds=100),
        fetched_at=T0 + timedelta(seconds=11),
    )
    result = assess_cross_stream_alignment(
        depth=depth(),
        order_flow=flow(),
        funding=funding(),
        open_interest=future_fetch,
        prediction_time=T0 + timedelta(seconds=10),
    )
    assert result.point_in_time_eligible is False
    assert "OPEN_INTEREST_FUTURE_KNOWLEDGE" in result.quality_flags


def test_stale_open_interest_is_blocked() -> None:
    stale = open_interest(seconds=-30)
    result = assess_cross_stream_alignment(
        depth=depth(),
        order_flow=flow(),
        funding=funding(),
        open_interest=stale,
        prediction_time=T0 + timedelta(seconds=10),
    )
    assert result.point_in_time_eligible is False
    assert "OPEN_INTEREST_STALE" in result.quality_flags


def test_cross_stream_skew_is_blocked_independently_of_stream_age() -> None:
    policy = CrossStreamFreshnessPolicy(max_observed_skew_seconds=1.0)
    result = assess_cross_stream_alignment(
        depth=depth(seconds=8),
        order_flow=flow(seconds=9),
        funding=funding(seconds=7),
        open_interest=open_interest(seconds=8),
        prediction_time=T0 + timedelta(seconds=10),
        policy=policy,
    )
    assert result.point_in_time_eligible is False
    assert result.max_observed_skew_seconds == pytest.approx(2.0)
    assert "CROSS_STREAM_MISALIGNED" in result.quality_flags


def test_mixed_symbols_are_rejected() -> None:
    other = OpenInterestState(
        symbol="BTCUSDT",
        observed_at=T0 + timedelta(seconds=8),
        open_interest=1.0,
        available_at=T0 + timedelta(seconds=8, milliseconds=100),
        fetched_at=T0 + timedelta(seconds=8, milliseconds=200),
    )
    with pytest.raises(ValueError, match="mix symbols"):
        assess_cross_stream_alignment(
            depth=depth(),
            order_flow=flow(),
            funding=funding(),
            open_interest=other,
            prediction_time=T0 + timedelta(seconds=10),
        )


def test_derivatives_reject_invalid_provenance_and_digest() -> None:
    observed = T0 + timedelta(seconds=8)
    with pytest.raises(ValueError, match="available_at cannot precede"):
        OpenInterestState(
            symbol="XRPUSDT",
            observed_at=observed,
            open_interest=1.0,
            available_at=observed - timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="SHA-256"):
        FundingState(
            symbol="XRPUSDT",
            observed_at=observed,
            mark_price=1.401,
            index_price=1.400,
            funding_rate=0.0,
            next_funding_at=T0 + timedelta(hours=8),
            payload_sha256="not-a-digest",
        )
