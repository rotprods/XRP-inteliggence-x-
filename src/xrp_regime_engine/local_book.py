from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from xrp_regime_engine.microstructure import BookLevel, OrderBookSnapshot


class BookSequenceError(RuntimeError):
    """Raised when a diff-depth stream cannot be safely reconciled."""


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


@dataclass(frozen=True)
class DepthDelta:
    first_update_id: int
    final_update_id: int
    observed_at: datetime
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    available_at: datetime | None = None
    fetched_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.first_update_id > self.final_update_id:
            raise ValueError("first_update_id cannot exceed final_update_id")
        _require_aware(self.observed_at, "observed_at")
        if (self.available_at is None) != (self.fetched_at is None):
            raise ValueError("available_at and fetched_at must be provided together")
        if self.available_at is not None and self.fetched_at is not None:
            _require_aware(self.available_at, "available_at")
            _require_aware(self.fetched_at, "fetched_at")
            if not self.observed_at <= self.available_at <= self.fetched_at:
                raise ValueError("depth timestamps must satisfy observed <= available <= fetched")


@dataclass
class LocalOrderBook:
    symbol: str
    last_update_id: int
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    synchronized: bool = False
    observed_at: datetime | None = None
    available_at: datetime | None = None
    fetched_at: datetime | None = None

    @classmethod
    def from_snapshot(cls, snapshot: OrderBookSnapshot) -> LocalOrderBook:
        return cls(
            symbol=snapshot.symbol,
            last_update_id=snapshot.last_update_id,
            bids={level.price: level.quantity for level in snapshot.bids},
            asks={level.price: level.quantity for level in snapshot.asks},
            synchronized=False,
            observed_at=snapshot.observed_at,
            available_at=None,
            fetched_at=snapshot.fetched_at,
        )

    @staticmethod
    def _apply_side(side: dict[float, float], updates: tuple[BookLevel, ...]) -> None:
        for level in updates:
            if level.quantity == 0:
                side.pop(level.price, None)
            else:
                side[level.price] = level.quantity

    def apply_first_delta(self, delta: DepthDelta) -> None:
        target = self.last_update_id + 1
        if not (delta.first_update_id <= target <= delta.final_update_id):
            raise BookSequenceError("first diff event does not bridge REST snapshot")
        self._apply(delta)
        self.synchronized = True

    def apply_delta(self, delta: DepthDelta) -> None:
        if not self.synchronized:
            raise BookSequenceError("book is not synchronized")
        if delta.final_update_id <= self.last_update_id:
            return
        if delta.first_update_id > self.last_update_id + 1:
            self.synchronized = False
            raise BookSequenceError("depth sequence gap; resnapshot required")
        self._apply(delta)

    def _apply(self, delta: DepthDelta) -> None:
        self._apply_side(self.bids, delta.bids)
        self._apply_side(self.asks, delta.asks)
        self.last_update_id = delta.final_update_id
        self.observed_at = delta.observed_at
        self.available_at = delta.available_at
        self.fetched_at = delta.fetched_at
        if not self.bids or not self.asks or max(self.bids) >= min(self.asks):
            self.synchronized = False
            raise BookSequenceError("invalid local book after depth update")

    def top(self, levels: int = 100) -> tuple[tuple[BookLevel, ...], tuple[BookLevel, ...]]:
        if not self.synchronized:
            raise BookSequenceError("book is not synchronized")
        if levels < 1:
            raise ValueError("levels must be positive")
        bids = tuple(
            BookLevel(price, quantity)
            for price, quantity in sorted(self.bids.items(), reverse=True)[:levels]
        )
        asks = tuple(
            BookLevel(price, quantity) for price, quantity in sorted(self.asks.items())[:levels]
        )
        return bids, asks
