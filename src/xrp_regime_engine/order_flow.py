from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


@dataclass(frozen=True)
class AggregateTrade:
    trade_id: int
    price: float
    quantity: float
    observed_at: datetime
    buyer_is_maker: bool
    available_at: datetime | None = None
    fetched_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.price) or self.price <= 0:
            raise ValueError("trade price must be finite and positive")
        if not isfinite(self.quantity) or self.quantity <= 0:
            raise ValueError("trade quantity must be finite and positive")
        _require_aware(self.observed_at, "observed_at")
        if (self.available_at is None) != (self.fetched_at is None):
            raise ValueError("available_at and fetched_at must be provided together")
        if self.available_at is not None and self.fetched_at is not None:
            _require_aware(self.available_at, "available_at")
            _require_aware(self.fetched_at, "fetched_at")
            if not self.observed_at <= self.available_at <= self.fetched_at:
                raise ValueError("trade timestamps must satisfy observed <= available <= fetched")

    @property
    def quote_notional(self) -> float:
        return self.price * self.quantity

    @property
    def aggressive_side(self) -> str:
        return "sell" if self.buyer_is_maker else "buy"


@dataclass(frozen=True)
class OrderFlowState:
    symbol: str
    observed_at: datetime
    aggressive_buy_notional: float
    aggressive_sell_notional: float
    cvd_quote: float
    taker_imbalance: float
    trade_count: int
    first_observed_at: datetime | None = None
    last_observed_at: datetime | None = None
    first_available_at: datetime | None = None
    last_available_at: datetime | None = None
    first_fetched_at: datetime | None = None
    last_fetched_at: datetime | None = None
    provenance_complete: bool = False


def compute_order_flow(symbol: str, trades: tuple[AggregateTrade, ...]) -> OrderFlowState:
    if not trades:
        raise ValueError("order flow requires trades")
    ordered = sorted(trades, key=lambda trade: (trade.observed_at, trade.trade_id))
    buys = sum(t.quote_notional for t in ordered if not t.buyer_is_maker)
    sells = sum(t.quote_notional for t in ordered if t.buyer_is_maker)
    total = buys + sells
    provenance_complete = all(
        trade.available_at is not None and trade.fetched_at is not None for trade in ordered
    )
    available = [trade.available_at for trade in ordered if trade.available_at is not None]
    fetched = [trade.fetched_at for trade in ordered if trade.fetched_at is not None]
    return OrderFlowState(
        symbol=symbol,
        observed_at=ordered[-1].observed_at,
        aggressive_buy_notional=buys,
        aggressive_sell_notional=sells,
        cvd_quote=buys - sells,
        taker_imbalance=0.0 if total == 0 else (buys - sells) / total,
        trade_count=len(ordered),
        first_observed_at=ordered[0].observed_at,
        last_observed_at=ordered[-1].observed_at,
        first_available_at=min(available) if provenance_complete else None,
        last_available_at=max(available) if provenance_complete else None,
        first_fetched_at=min(fetched) if provenance_complete else None,
        last_fetched_at=max(fetched) if provenance_complete else None,
        provenance_complete=provenance_complete,
    )
