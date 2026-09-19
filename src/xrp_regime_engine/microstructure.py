from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True)
class BookLevel:
    price: float
    quantity: float

    def __post_init__(self) -> None:
        if not isfinite(self.price) or self.price <= 0:
            raise ValueError("price must be finite and positive")
        if not isfinite(self.quantity) or self.quantity < 0:
            raise ValueError("quantity must be finite and non-negative")


@dataclass(frozen=True)
class OrderBookSnapshot:
    symbol: str
    last_update_id: int
    observed_at: datetime
    fetched_at: datetime
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    provider: str
    payload_hash: str

    def __post_init__(self) -> None:
        if not self.bids or not self.asks:
            raise ValueError("order book requires bids and asks")
        if self.bids[0].price >= self.asks[0].price:
            raise ValueError("crossed or locked order book")
        if self.observed_at > self.fetched_at:
            raise ValueError("observed_at cannot be later than fetched_at")


@dataclass(frozen=True)
class MicrostructureState:
    symbol: str
    observed_at: datetime
    mid_price: float
    spread_bps: float
    microprice: float
    imbalance_10bps: float
    imbalance_25bps: float
    imbalance_50bps: float
    imbalance_100bps: float
    bid_notional_100bps: float
    ask_notional_100bps: float
    quality_flags: tuple[str, ...] = ()


def _notional_within(levels: tuple[BookLevel, ...], mid: float, bps: float, bid: bool) -> float:
    bound = mid * (1 - bps / 10_000) if bid else mid * (1 + bps / 10_000)
    if bid:
        selected = (level for level in levels if level.price >= bound)
    else:
        selected = (level for level in levels if level.price <= bound)
    return sum(level.price * level.quantity for level in selected)


def _imbalance(bid_notional: float, ask_notional: float) -> float:
    total = bid_notional + ask_notional
    return 0.0 if total == 0 else (bid_notional - ask_notional) / total


def compute_microstructure(snapshot: OrderBookSnapshot) -> MicrostructureState:
    best_bid = snapshot.bids[0]
    best_ask = snapshot.asks[0]
    mid = (best_bid.price + best_ask.price) / 2
    spread_bps = (best_ask.price - best_bid.price) / mid * 10_000

    top_quantity = best_bid.quantity + best_ask.quantity
    microprice = (
        mid
        if top_quantity == 0
        else (best_ask.price * best_bid.quantity + best_bid.price * best_ask.quantity)
        / top_quantity
    )

    notionals: dict[float, tuple[float, float]] = {}
    for bps in (10.0, 25.0, 50.0, 100.0):
        notionals[bps] = (
            _notional_within(snapshot.bids, mid, bps, True),
            _notional_within(snapshot.asks, mid, bps, False),
        )

    flags: list[str] = []
    if spread_bps > 20:
        flags.append("WIDE_SPREAD")
    if snapshot.fetched_at.tzinfo is None or snapshot.observed_at.tzinfo is None:
        flags.append("NAIVE_TIMESTAMP")

    return MicrostructureState(
        symbol=snapshot.symbol,
        observed_at=snapshot.observed_at,
        mid_price=mid,
        spread_bps=spread_bps,
        microprice=microprice,
        imbalance_10bps=_imbalance(*notionals[10.0]),
        imbalance_25bps=_imbalance(*notionals[25.0]),
        imbalance_50bps=_imbalance(*notionals[50.0]),
        imbalance_100bps=_imbalance(*notionals[100.0]),
        bid_notional_100bps=notionals[100.0][0],
        ask_notional_100bps=notionals[100.0][1],
        quality_flags=tuple(flags),
    )
