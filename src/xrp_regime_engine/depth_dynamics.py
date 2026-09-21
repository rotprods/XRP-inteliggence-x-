from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from xrp_regime_engine.local_book import BookSequenceError, DepthDelta, LocalOrderBook
from xrp_regime_engine.microstructure import BookLevel


@dataclass(frozen=True)
class DepthDynamics:
    symbol: str
    observed_at: datetime
    first_update_id: int
    final_update_id: int
    elapsed_seconds: float
    bid_added_notional: float
    bid_removed_notional: float
    ask_added_notional: float
    ask_removed_notional: float
    bid_net_notional: float
    ask_net_notional: float
    gross_churn_notional: float
    churn_quote_per_second: float
    trade_attribution_confirmed: bool
    quality_flags: tuple[str, ...]
    execution_weight: float = 0.0


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _level_changes(
    before: dict[float, float], updates: tuple[BookLevel, ...]
) -> tuple[float, float]:
    seen: set[float] = set()
    added = 0.0
    removed = 0.0
    for level in updates:
        if level.price in seen:
            raise ValueError("depth delta contains duplicate price level")
        seen.add(level.price)
        previous_quantity = before.get(level.price, 0.0)
        quantity_delta = level.quantity - previous_quantity
        notional_delta = level.price * quantity_delta
        if notional_delta > 0:
            added += notional_delta
        elif notional_delta < 0:
            removed += -notional_delta
    return added, removed


def apply_delta_with_dynamics(
    book: LocalOrderBook,
    delta: DepthDelta,
    *,
    max_event_gap_seconds: float = 2.0,
) -> DepthDynamics | None:
    """Apply one synchronized depth delta and return observational liquidity dynamics.

    The accounting describes quantity added to or removed from displayed depth. It does
    not infer cancellation, spoofing, trade consumption, support, resistance, or a
    trading signal. Causal attribution requires contemporaneous trade-flow evidence.
    """
    if not isfinite(max_event_gap_seconds) or max_event_gap_seconds <= 0:
        raise ValueError("max_event_gap_seconds must be finite and positive")
    if not book.synchronized:
        raise BookSequenceError("book is not synchronized")
    _require_aware(delta.observed_at, "delta.observed_at")
    if book.observed_at is None:
        book.synchronized = False
        raise BookSequenceError("synchronized book is missing observed_at")
    _require_aware(book.observed_at, "book.observed_at")

    if delta.final_update_id <= book.last_update_id:
        return None

    elapsed_seconds = (delta.observed_at - book.observed_at).total_seconds()
    if elapsed_seconds <= 0:
        book.synchronized = False
        raise BookSequenceError("depth event time must advance monotonically")
    if elapsed_seconds > max_event_gap_seconds:
        book.synchronized = False
        raise BookSequenceError("depth event time gap; resnapshot required")

    try:
        bid_added, bid_removed = _level_changes(book.bids, delta.bids)
        ask_added, ask_removed = _level_changes(book.asks, delta.asks)
    except ValueError:
        book.synchronized = False
        raise

    book.apply_delta(delta)

    gross_churn = bid_added + bid_removed + ask_added + ask_removed
    flags: list[str] = ["TRADE_ATTRIBUTION_REQUIRED"]
    if gross_churn == 0:
        flags.append("NO_DISPLAYED_DEPTH_CHANGE")

    return DepthDynamics(
        symbol=book.symbol,
        observed_at=delta.observed_at,
        first_update_id=delta.first_update_id,
        final_update_id=delta.final_update_id,
        elapsed_seconds=elapsed_seconds,
        bid_added_notional=bid_added,
        bid_removed_notional=bid_removed,
        ask_added_notional=ask_added,
        ask_removed_notional=ask_removed,
        bid_net_notional=bid_added - bid_removed,
        ask_net_notional=ask_added - ask_removed,
        gross_churn_notional=gross_churn,
        churn_quote_per_second=gross_churn / elapsed_seconds,
        trade_attribution_confirmed=False,
        quality_flags=tuple(flags),
        execution_weight=0.0,
    )
