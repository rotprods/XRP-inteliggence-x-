from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.depth_dynamics import DepthDynamics
from xrp_regime_engine.order_flow import OrderFlowState
from xrp_regime_engine.trade_attribution import reconcile_depth_with_order_flow

NOW = datetime(2026, 9, 21, 2, 0, tzinfo=UTC)


def depth(
    *,
    bid_removed: float = 600.0,
    ask_removed: float = 400.0,
    elapsed_seconds: float = 1.0,
) -> DepthDynamics:
    return DepthDynamics(
        symbol="XRPUSDT",
        observed_at=NOW,
        first_update_id=10,
        final_update_id=11,
        elapsed_seconds=elapsed_seconds,
        bid_added_notional=0.0,
        bid_removed_notional=bid_removed,
        ask_added_notional=0.0,
        ask_removed_notional=ask_removed,
        bid_net_notional=-bid_removed,
        ask_net_notional=-ask_removed,
        gross_churn_notional=bid_removed + ask_removed,
        churn_quote_per_second=(bid_removed + ask_removed) / elapsed_seconds,
        trade_attribution_confirmed=False,
        quality_flags=("TRADE_ATTRIBUTION_REQUIRED",),
        execution_weight=0.0,
    )


def flow(
    *,
    aggressive_buy: float = 300.0,
    aggressive_sell: float = 500.0,
    observed_at: datetime = NOW,
    symbol: str = "XRPUSDT",
) -> OrderFlowState:
    total = aggressive_buy + aggressive_sell
    cvd = aggressive_buy - aggressive_sell
    return OrderFlowState(
        symbol=symbol,
        observed_at=observed_at,
        aggressive_buy_notional=aggressive_buy,
        aggressive_sell_notional=aggressive_sell,
        cvd_quote=cvd,
        taker_imbalance=0.0 if total == 0 else cvd / total,
        trade_count=10,
    )


def complete_depth() -> DepthDynamics:
    return DepthDynamics(
        symbol="XRPUSDT",
        observed_at=NOW + timedelta(seconds=1),
        first_update_id=10,
        final_update_id=11,
        elapsed_seconds=1.0,
        bid_added_notional=0.0,
        bid_removed_notional=600.0,
        ask_added_notional=0.0,
        ask_removed_notional=400.0,
        bid_net_notional=-600.0,
        ask_net_notional=-400.0,
        gross_churn_notional=1000.0,
        churn_quote_per_second=1000.0,
        trade_attribution_confirmed=False,
        quality_flags=("TRADE_ATTRIBUTION_REQUIRED",),
        first_observed_at=NOW,
        last_observed_at=NOW + timedelta(seconds=1),
        first_available_at=NOW + timedelta(milliseconds=10),
        last_available_at=NOW + timedelta(seconds=1, milliseconds=10),
        first_fetched_at=NOW + timedelta(milliseconds=20),
        last_fetched_at=NOW + timedelta(seconds=1, milliseconds=20),
        provenance_complete=True,
        execution_weight=0.0,
    )


def complete_flow() -> OrderFlowState:
    return OrderFlowState(
        symbol="XRPUSDT",
        observed_at=NOW + timedelta(seconds=1),
        aggressive_buy_notional=300.0,
        aggressive_sell_notional=500.0,
        cvd_quote=-200.0,
        taker_imbalance=-0.25,
        trade_count=10,
        first_observed_at=NOW,
        last_observed_at=NOW + timedelta(seconds=1),
        first_available_at=NOW + timedelta(milliseconds=15),
        last_available_at=NOW + timedelta(seconds=1, milliseconds=15),
        first_fetched_at=NOW + timedelta(milliseconds=25),
        last_fetched_at=NOW + timedelta(seconds=1, milliseconds=25),
        provenance_complete=True,
    )


def test_aligned_streams_emit_compatibility_not_causal_attribution() -> None:
    state = reconcile_depth_with_order_flow(depth(), flow(), flow_window_seconds=1.0)
    assert state.evidence_eligible is True
    assert state.regime_eligible is False
    assert state.point_in_time_eligible is False
    assert state.bid_trade_compatible_notional == 500.0
    assert state.ask_trade_compatible_notional == 300.0
    assert state.trade_compatible_removed_notional == 800.0
    assert state.removal_candidate_residual_notional == 200.0
    assert state.unmatched_aggressive_trade_notional == 0.0
    assert state.removal_coverage_ratio == pytest.approx(0.8)
    assert state.causal_attribution_confirmed is False
    assert "TRADE_CONSUMPTION_COMPATIBLE_ONLY" in state.quality_flags
    assert "POINT_IN_TIME_PROVENANCE_INCOMPLETE" in state.quality_flags
    assert "CALLER_WINDOW_FALLBACK" in state.quality_flags
    assert "REMOVAL_CANDIDATE_RESIDUAL" in state.quality_flags
    assert state.execution_weight == 0.0


def test_complete_provenance_derives_windows_but_requires_prediction_time() -> None:
    state = reconcile_depth_with_order_flow(complete_depth(), complete_flow())
    assert state.depth_window_seconds == 1.0
    assert state.flow_window_seconds == 1.0
    assert state.window_skew_seconds == 0.0
    assert state.point_in_time_eligible is False
    assert state.regime_eligible is False
    assert "POINT_IN_TIME_PROVENANCE_COMPLETE_SHADOW_ONLY" in state.quality_flags
    assert "PREDICTION_TIME_REQUIRED" in state.quality_flags
    assert "CALLER_WINDOW_FALLBACK" not in state.quality_flags
    assert state.execution_weight == 0.0


def test_complete_provenance_becomes_point_in_time_eligible_only_after_fetch() -> None:
    state = reconcile_depth_with_order_flow(
        complete_depth(),
        complete_flow(),
        prediction_time=NOW + timedelta(seconds=2),
    )
    assert state.point_in_time_eligible is True
    assert state.regime_eligible is False
    assert state.evidence_eligible is True
    assert "FUTURE_KNOWLEDGE_BLOCKED" not in state.quality_flags
    assert state.execution_weight == 0.0


def test_complete_provenance_ignores_conflicting_caller_window() -> None:
    state = reconcile_depth_with_order_flow(
        complete_depth(),
        complete_flow(),
        flow_window_seconds=99.0,
        prediction_time=NOW + timedelta(seconds=2),
    )
    assert state.flow_window_seconds == 1.0
    assert state.point_in_time_eligible is True
    assert "CALLER_WINDOW_IGNORED" in state.quality_flags
    assert "CROSS_STREAM_WINDOW_MISALIGNED" not in state.quality_flags


def test_future_fetched_data_is_blocked_at_prediction_time() -> None:
    state = reconcile_depth_with_order_flow(
        complete_depth(),
        complete_flow(),
        prediction_time=NOW + timedelta(seconds=1, milliseconds=10),
    )
    assert state.point_in_time_eligible is False
    assert state.evidence_eligible is False
    assert state.trade_compatible_removed_notional is None
    assert state.removal_candidate_residual_notional is None
    assert "FUTURE_KNOWLEDGE_BLOCKED" in state.quality_flags
    assert state.execution_weight == 0.0


def test_end_time_misalignment_fails_closed_without_pairing_notionals() -> None:
    state = reconcile_depth_with_order_flow(
        depth(),
        flow(observed_at=NOW + timedelta(seconds=2)),
        flow_window_seconds=1.0,
    )
    assert state.evidence_eligible is False
    assert state.regime_eligible is False
    assert state.point_in_time_eligible is False
    assert state.trade_compatible_removed_notional is None
    assert state.removal_candidate_residual_notional is None
    assert "CROSS_STREAM_END_TIME_MISALIGNED" in state.quality_flags
    assert "POINT_IN_TIME_PROVENANCE_INCOMPLETE" in state.quality_flags
    assert state.execution_weight == 0.0


def test_window_misalignment_fails_closed() -> None:
    state = reconcile_depth_with_order_flow(depth(), flow(), flow_window_seconds=3.0)
    assert state.evidence_eligible is False
    assert state.regime_eligible is False
    assert state.removal_coverage_ratio is None
    assert "CROSS_STREAM_WINDOW_MISALIGNED" in state.quality_flags


def test_aggressive_trade_excess_is_separated_from_displayed_removal() -> None:
    state = reconcile_depth_with_order_flow(
        depth(bid_removed=100.0, ask_removed=100.0),
        flow(aggressive_buy=300.0, aggressive_sell=400.0),
        flow_window_seconds=1.0,
    )
    assert state.trade_compatible_removed_notional == 200.0
    assert state.removal_candidate_residual_notional == 0.0
    assert state.unmatched_aggressive_trade_notional == 500.0
    assert state.regime_eligible is False
    assert "AGGRESSIVE_TRADE_EXCEEDS_DISPLAYED_REMOVAL" in state.quality_flags


def test_zero_depth_removal_has_no_coverage_ratio() -> None:
    state = reconcile_depth_with_order_flow(
        depth(bid_removed=0.0, ask_removed=0.0),
        flow(aggressive_buy=0.0, aggressive_sell=0.0),
        flow_window_seconds=1.0,
    )
    assert state.removal_coverage_ratio is None
    assert state.regime_eligible is False
    assert "NO_DISPLAYED_DEPTH_REMOVAL" in state.quality_flags


def test_symbol_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="same symbol"):
        reconcile_depth_with_order_flow(depth(), flow(symbol="BTCUSDT"), flow_window_seconds=1.0)


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        reconcile_depth_with_order_flow(
            depth(),
            flow(observed_at=NOW.replace(tzinfo=None)),
            flow_window_seconds=1.0,
        )


def test_declared_complete_without_envelope_is_rejected() -> None:
    incomplete = flow()
    invalid = OrderFlowState(
        symbol=incomplete.symbol,
        observed_at=incomplete.observed_at,
        aggressive_buy_notional=incomplete.aggressive_buy_notional,
        aggressive_sell_notional=incomplete.aggressive_sell_notional,
        cvd_quote=incomplete.cvd_quote,
        taker_imbalance=incomplete.taker_imbalance,
        trade_count=incomplete.trade_count,
        provenance_complete=True,
    )
    with pytest.raises(ValueError, match="complete provenance"):
        reconcile_depth_with_order_flow(complete_depth(), invalid, flow_window_seconds=1.0)


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("nan")])
def test_invalid_alignment_policy_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        reconcile_depth_with_order_flow(
            depth(),
            flow(),
            flow_window_seconds=value,
        )


def test_invalid_observed_notional_is_rejected() -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        reconcile_depth_with_order_flow(
            depth(bid_removed=-1.0),
            flow(),
            flow_window_seconds=1.0,
        )
