from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True)
class AggregateTrade:
    trade_id: int
    price: float
    quantity: float
    observed_at: datetime
    buyer_is_maker: bool

    def __post_init__(self) -> None:
        if not isfinite(self.price) or self.price <= 0:
            raise ValueError("trade price must be finite and positive")
        if not isfinite(self.quantity) or self.quantity <= 0:
            raise ValueError("trade quantity must be finite and positive")

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


def compute_order_flow(symbol: str, trades: tuple[AggregateTrade, ...]) -> OrderFlowState:
    if not trades:
        raise ValueError("order flow requires trades")
    buys = sum(t.quote_notional for t in trades if not t.buyer_is_maker)
    sells = sum(t.quote_notional for t in trades if t.buyer_is_maker)
    total = buys + sells
    return OrderFlowState(
        symbol=symbol,
        observed_at=max(t.observed_at for t in trades),
        aggressive_buy_notional=buys,
        aggressive_sell_notional=sells,
        cvd_quote=buys - sells,
        taker_imbalance=0.0 if total == 0 else (buys - sells) / total,
        trade_count=len(trades),
    )
