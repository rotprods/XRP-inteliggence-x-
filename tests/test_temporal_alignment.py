from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.depth_dynamics import DepthDynamics
from xrp_regime_engine.derivatives import FundingState, OpenInterestState
from xrp_regime_engine.order_flow import OrderFlowState
from xrp_regime_engine.temporal_alignment import build_aligned_temporal_window
from xrp_regime_engine.temporal_flow import TemporalFlowSample

T0 = datetime(2026, 9, 21, 4, 0, tzinfo=UTC)


def depth() -> DepthDynamics:
    observed = T0 + timedelta(seconds=8)
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


def flow() -> OrderFlowState:
    observed = T0 + timedelta(seconds=8)
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


def funding(*, complete: bool = True) -> FundingState:
    observed = T0 + timedelta(seconds=8)
    return FundingState(
        symbol="XRPUSDT",
        observed_at=observed,
        mark_price=1.401,
        index_price=1.400,
        funding_rate=0.0001,
        next_funding_at=T0 + timedelta(hours=8),
        available_at=observed + timedelta(milliseconds=100) if complete else None,
        fetched_at=observed + timedelta(milliseconds=200),
        payload_sha256="a" * 64,
    )


def open_interest() -> OpenInterestState:
    observed = T0 + timedelta(seconds=8)
    return OpenInterestState(
        symbol="XRPUSDT",
        observed_at=observed,
        open_interest=100_000_000.0,
        available_at=observed + timedelta(milliseconds=100),
        fetched_at=observed + timedelta(milliseconds=200),
        payload_sha256="b" * 64,
    )


def sample(seconds: int, *, symbol: str = "XRPUSDT") -> TemporalFlowSample:
    observed = T0 + timedelta(seconds=seconds)
    return TemporalFlowSample(
        symbol=symbol,
        observed_at=observed,
        available_at=observed + timedelta(milliseconds=100),
        fetched_at=observed + timedelta(milliseconds=200),
        mid_price=1.4,
        depth_imbalance_25bps=0.2,
        aggressive_buy_notional=100.0,
        aggressive_sell_notional=50.0,
        open_interest=100_000_000.0,
        funding_rate=0.0001,
        basis_bps=2.0,
    )


def test_complete_alignment_exposes_only_eligible_temporal_window() -> None:
    result = build_aligned_temporal_window(
        samples=(sample(-40), sample(8)),
        depth=depth(),
        order_flow=flow(),
        funding=funding(),
        open_interest=open_interest(),
        prediction_time=T0 + timedelta(seconds=10),
        window_seconds=60,
    )
    assert result.evidence_eligible is True
    assert result.window is not None
    assert result.alignment.evidence_eligible is True
    assert result.execution_weight == 0.0


def test_incomplete_derivative_provenance_blocks_window() -> None:
    result = build_aligned_temporal_window(
        samples=(sample(-40), sample(8)),
        depth=depth(),
        order_flow=flow(),
        funding=funding(complete=False),
        open_interest=open_interest(),
        prediction_time=T0 + timedelta(seconds=10),
        window_seconds=60,
    )
    assert result.evidence_eligible is False
    assert result.window is None
    assert "FUNDING_PROVENANCE_INCOMPLETE" in result.quality_flags
    assert "BASIS_PROVENANCE_INCOMPLETE" in result.quality_flags


def test_sparse_temporal_window_is_blocked_after_alignment_passes() -> None:
    result = build_aligned_temporal_window(
        samples=(sample(8),),
        depth=depth(),
        order_flow=flow(),
        funding=funding(),
        open_interest=open_interest(),
        prediction_time=T0 + timedelta(seconds=10),
        window_seconds=60,
    )
    assert result.alignment.evidence_eligible is True
    assert result.evidence_eligible is False
    assert result.window is None
    assert "SPARSE_WINDOW" in result.quality_flags
    assert "TEMPORAL_WINDOW_INELIGIBLE" in result.quality_flags


def test_temporal_symbol_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="symbol must match"):
        build_aligned_temporal_window(
            samples=(sample(-40, symbol="BTCUSDT"), sample(8, symbol="BTCUSDT")),
            depth=depth(),
            order_flow=flow(),
            funding=funding(),
            open_interest=open_interest(),
            prediction_time=T0 + timedelta(seconds=10),
            window_seconds=60,
        )
