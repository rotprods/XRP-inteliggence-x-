from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from xrp_regime_engine.depth_dynamics import DepthDynamics
from xrp_regime_engine.order_flow import OrderFlowState


@dataclass(frozen=True)
class DepthTradeCompatibility:
    symbol: str
    observed_at: datetime
    event_end_skew_seconds: float
    window_skew_seconds: float
    bid_removed_notional: float
    ask_removed_notional: float
    aggressive_buy_notional: float
    aggressive_sell_notional: float
    bid_trade_compatible_notional: float | None
    ask_trade_compatible_notional: float | None
    trade_compatible_removed_notional: float | None
    removal_candidate_residual_notional: float | None
    unmatched_aggressive_trade_notional: float | None
    removal_coverage_ratio: float | None
    evidence_eligible: bool
    regime_eligible: bool
    causal_attribution_confirmed: bool
    quality_flags: tuple[str, ...]
    execution_weight: float = 0.0


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _require_positive_finite(value: float, field: str) -> None:
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{field} must be finite and positive")


def _require_non_negative_finite(value: float, field: str) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError(f"{field} must be finite and non-negative")


def reconcile_depth_with_order_flow(
    dynamics: DepthDynamics,
    flow: OrderFlowState,
    *,
    flow_window_seconds: float,
    max_event_end_skew_seconds: float = 0.5,
    max_window_skew_seconds: float = 0.5,
) -> DepthTradeCompatibility:
    """Compare displayed-depth removal with contemporaneous aggressive trade flow.

    This is compatibility accounting, not causal attribution. A quote-notional match
    cannot prove that a specific depth removal was executed rather than cancelled,
    replaced, or modified between observations. V1 lacks complete available/fetched
    timestamps for both streams, so the output is never regime-eligible.
    """
    for field, value in (
        ("flow_window_seconds", flow_window_seconds),
        ("max_event_end_skew_seconds", max_event_end_skew_seconds),
        ("max_window_skew_seconds", max_window_skew_seconds),
        ("dynamics.elapsed_seconds", dynamics.elapsed_seconds),
    ):
        _require_positive_finite(value, field)
    for field, value in (
        ("dynamics.bid_removed_notional", dynamics.bid_removed_notional),
        ("dynamics.ask_removed_notional", dynamics.ask_removed_notional),
        ("flow.aggressive_buy_notional", flow.aggressive_buy_notional),
        ("flow.aggressive_sell_notional", flow.aggressive_sell_notional),
    ):
        _require_non_negative_finite(value, field)
    _require_aware(dynamics.observed_at, "dynamics.observed_at")
    _require_aware(flow.observed_at, "flow.observed_at")
    if dynamics.symbol != flow.symbol:
        raise ValueError("depth dynamics and order flow must use the same symbol")

    event_end_skew = abs((flow.observed_at - dynamics.observed_at).total_seconds())
    window_skew = abs(flow_window_seconds - dynamics.elapsed_seconds)
    flags: list[str] = [
        "CAUSAL_ATTRIBUTION_UNPROVEN",
        "POINT_IN_TIME_PROVENANCE_INCOMPLETE",
    ]
    aligned = True
    if event_end_skew > max_event_end_skew_seconds:
        flags.append("CROSS_STREAM_END_TIME_MISALIGNED")
        aligned = False
    if window_skew > max_window_skew_seconds:
        flags.append("CROSS_STREAM_WINDOW_MISALIGNED")
        aligned = False

    observed_at = max(dynamics.observed_at, flow.observed_at)
    if not aligned:
        return DepthTradeCompatibility(
            symbol=dynamics.symbol,
            observed_at=observed_at,
            event_end_skew_seconds=event_end_skew,
            window_skew_seconds=window_skew,
            bid_removed_notional=dynamics.bid_removed_notional,
            ask_removed_notional=dynamics.ask_removed_notional,
            aggressive_buy_notional=flow.aggressive_buy_notional,
            aggressive_sell_notional=flow.aggressive_sell_notional,
            bid_trade_compatible_notional=None,
            ask_trade_compatible_notional=None,
            trade_compatible_removed_notional=None,
            removal_candidate_residual_notional=None,
            unmatched_aggressive_trade_notional=None,
            removal_coverage_ratio=None,
            evidence_eligible=False,
            regime_eligible=False,
            causal_attribution_confirmed=False,
            quality_flags=tuple(flags),
            execution_weight=0.0,
        )

    bid_compatible = min(dynamics.bid_removed_notional, flow.aggressive_sell_notional)
    ask_compatible = min(dynamics.ask_removed_notional, flow.aggressive_buy_notional)
    compatible_removed = bid_compatible + ask_compatible
    total_removed = dynamics.bid_removed_notional + dynamics.ask_removed_notional
    candidate_residual = max(dynamics.bid_removed_notional - bid_compatible, 0.0) + max(
        dynamics.ask_removed_notional - ask_compatible, 0.0
    )
    unmatched_trade = max(flow.aggressive_sell_notional - bid_compatible, 0.0) + max(
        flow.aggressive_buy_notional - ask_compatible, 0.0
    )
    coverage = None if total_removed == 0 else compatible_removed / total_removed

    flags.append("TRADE_CONSUMPTION_COMPATIBLE_ONLY")
    if total_removed == 0:
        flags.append("NO_DISPLAYED_DEPTH_REMOVAL")
    if candidate_residual > 0:
        flags.append("REMOVAL_CANDIDATE_RESIDUAL")
    if unmatched_trade > 0:
        flags.append("AGGRESSIVE_TRADE_EXCEEDS_DISPLAYED_REMOVAL")

    return DepthTradeCompatibility(
        symbol=dynamics.symbol,
        observed_at=observed_at,
        event_end_skew_seconds=event_end_skew,
        window_skew_seconds=window_skew,
        bid_removed_notional=dynamics.bid_removed_notional,
        ask_removed_notional=dynamics.ask_removed_notional,
        aggressive_buy_notional=flow.aggressive_buy_notional,
        aggressive_sell_notional=flow.aggressive_sell_notional,
        bid_trade_compatible_notional=bid_compatible,
        ask_trade_compatible_notional=ask_compatible,
        trade_compatible_removed_notional=compatible_removed,
        removal_candidate_residual_notional=candidate_residual,
        unmatched_aggressive_trade_notional=unmatched_trade,
        removal_coverage_ratio=coverage,
        evidence_eligible=True,
        regime_eligible=False,
        causal_attribution_confirmed=False,
        quality_flags=tuple(flags),
        execution_weight=0.0,
    )
