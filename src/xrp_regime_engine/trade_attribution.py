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
    depth_window_seconds: float
    flow_window_seconds: float
    point_in_time_eligible: bool
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


def _derived_window_seconds(
    first: datetime | None,
    last: datetime | None,
    *,
    field: str,
) -> float | None:
    if first is None or last is None:
        return None
    _require_aware(first, f"{field}.first_observed_at")
    _require_aware(last, f"{field}.last_observed_at")
    seconds = (last - first).total_seconds()
    _require_positive_finite(seconds, f"{field}.derived_window_seconds")
    return seconds


def _complete_provenance(
    *,
    declared_complete: bool,
    first_observed_at: datetime | None,
    last_observed_at: datetime | None,
    first_available_at: datetime | None,
    last_available_at: datetime | None,
    first_fetched_at: datetime | None,
    last_fetched_at: datetime | None,
    field: str,
) -> bool:
    values = (
        first_observed_at,
        last_observed_at,
        first_available_at,
        last_available_at,
        first_fetched_at,
        last_fetched_at,
    )
    present = all(value is not None for value in values)
    if declared_complete and not present:
        raise ValueError(f"{field} declares complete provenance without a complete envelope")
    if not declared_complete:
        return False
    assert all(value is not None for value in values)
    for name, value in (
        ("first_observed_at", first_observed_at),
        ("last_observed_at", last_observed_at),
        ("first_available_at", first_available_at),
        ("last_available_at", last_available_at),
        ("first_fetched_at", first_fetched_at),
        ("last_fetched_at", last_fetched_at),
    ):
        assert value is not None
        _require_aware(value, f"{field}.{name}")
    assert first_observed_at is not None
    assert last_observed_at is not None
    assert first_available_at is not None
    assert last_available_at is not None
    assert first_fetched_at is not None
    assert last_fetched_at is not None
    if first_observed_at > last_observed_at:
        raise ValueError(f"{field} observed envelope is reversed")
    if first_available_at > last_available_at:
        raise ValueError(f"{field} available envelope is reversed")
    if first_fetched_at > last_fetched_at:
        raise ValueError(f"{field} fetched envelope is reversed")
    if first_observed_at > first_available_at or last_observed_at > last_available_at:
        raise ValueError(f"{field} availability precedes observation")
    if first_available_at > first_fetched_at or last_available_at > last_fetched_at:
        raise ValueError(f"{field} fetch precedes availability")
    return True


def reconcile_depth_with_order_flow(
    dynamics: DepthDynamics,
    flow: OrderFlowState,
    *,
    flow_window_seconds: float | None = None,
    max_event_end_skew_seconds: float = 0.5,
    max_window_skew_seconds: float = 0.5,
) -> DepthTradeCompatibility:
    """Compare displayed-depth removal with contemporaneous aggressive trade flow.

    This is compatibility accounting, not causal attribution. Complete provenance lets
    V2 derive both observed windows from stream envelopes instead of trusting a caller-
    supplied duration. It still does not prove cancellation, trade consumption, spoofing,
    support/resistance, or predictive direction; regime authority remains disabled.
    """
    for field, value in (
        ("max_event_end_skew_seconds", max_event_end_skew_seconds),
        ("max_window_skew_seconds", max_window_skew_seconds),
        ("dynamics.elapsed_seconds", dynamics.elapsed_seconds),
    ):
        _require_positive_finite(value, field)
    if flow_window_seconds is not None:
        _require_positive_finite(flow_window_seconds, "flow_window_seconds")
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

    depth_window = _derived_window_seconds(
        dynamics.first_observed_at,
        dynamics.last_observed_at,
        field="dynamics",
    )
    flow_window = _derived_window_seconds(
        flow.first_observed_at,
        flow.last_observed_at,
        field="flow",
    )
    provenance_window_derived = depth_window is not None and flow_window is not None
    if depth_window is None:
        depth_window = dynamics.elapsed_seconds
    if flow_window is None:
        if flow_window_seconds is None:
            raise ValueError("flow window provenance unavailable; explicit fallback is required")
        flow_window = flow_window_seconds

    depth_provenance = _complete_provenance(
        declared_complete=dynamics.provenance_complete,
        first_observed_at=dynamics.first_observed_at,
        last_observed_at=dynamics.last_observed_at,
        first_available_at=dynamics.first_available_at,
        last_available_at=dynamics.last_available_at,
        first_fetched_at=dynamics.first_fetched_at,
        last_fetched_at=dynamics.last_fetched_at,
        field="dynamics",
    )
    flow_provenance = _complete_provenance(
        declared_complete=flow.provenance_complete,
        first_observed_at=flow.first_observed_at,
        last_observed_at=flow.last_observed_at,
        first_available_at=flow.first_available_at,
        last_available_at=flow.last_available_at,
        first_fetched_at=flow.first_fetched_at,
        last_fetched_at=flow.last_fetched_at,
        field="flow",
    )
    provenance_complete = depth_provenance and flow_provenance

    depth_end = dynamics.last_observed_at or dynamics.observed_at
    flow_end = flow.last_observed_at or flow.observed_at
    event_end_skew = abs((flow_end - depth_end).total_seconds())
    window_skew = abs(flow_window - depth_window)
    flags: list[str] = ["CAUSAL_ATTRIBUTION_UNPROVEN"]
    if provenance_complete and provenance_window_derived:
        flags.append("POINT_IN_TIME_PROVENANCE_COMPLETE_SHADOW_ONLY")
        if flow_window_seconds is not None:
            flags.append("CALLER_WINDOW_IGNORED")
    else:
        flags.append("POINT_IN_TIME_PROVENANCE_INCOMPLETE")
        if not provenance_window_derived:
            flags.append("CALLER_WINDOW_FALLBACK")

    aligned = True
    if event_end_skew > max_event_end_skew_seconds:
        flags.append("CROSS_STREAM_END_TIME_MISALIGNED")
        aligned = False
    if window_skew > max_window_skew_seconds:
        flags.append("CROSS_STREAM_WINDOW_MISALIGNED")
        aligned = False

    observed_at = max(depth_end, flow_end)
    point_in_time_eligible = aligned and provenance_complete and provenance_window_derived
    if not aligned:
        return DepthTradeCompatibility(
            symbol=dynamics.symbol,
            observed_at=observed_at,
            event_end_skew_seconds=event_end_skew,
            window_skew_seconds=window_skew,
            depth_window_seconds=depth_window,
            flow_window_seconds=flow_window,
            point_in_time_eligible=False,
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
        depth_window_seconds=depth_window,
        flow_window_seconds=flow_window,
        point_in_time_eligible=point_in_time_eligible,
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
