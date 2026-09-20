from datetime import UTC, datetime

import pytest

from xrp_regime_engine.local_book import BookSequenceError, DepthDelta, LocalOrderBook
from xrp_regime_engine.microstructure import BookLevel, OrderBookSnapshot
from xrp_regime_engine.order_flow import AggregateTrade, compute_order_flow

NOW = datetime(2026, 9, 20, 20, 0, tzinfo=UTC)


def _snapshot() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="XRPUSDT",
        last_update_id=100,
        observed_at=NOW,
        fetched_at=NOW,
        bids=(BookLevel(1.400, 100), BookLevel(1.399, 200)),
        asks=(BookLevel(1.401, 100), BookLevel(1.402, 200)),
        provider="fixture",
        payload_hash="0" * 64,
    )


def test_first_delta_must_bridge_snapshot() -> None:
    book = LocalOrderBook.from_snapshot(_snapshot())
    with pytest.raises(BookSequenceError, match="bridge"):
        book.apply_first_delta(
            DepthDelta(102, 103, NOW, (BookLevel(1.400, 90),), ())
        )


def test_sequence_gap_fails_closed_and_requires_resnapshot() -> None:
    book = LocalOrderBook.from_snapshot(_snapshot())
    book.apply_first_delta(DepthDelta(100, 101, NOW, (BookLevel(1.400, 90),), ()))
    assert book.synchronized
    with pytest.raises(BookSequenceError, match="resnapshot"):
        book.apply_delta(DepthDelta(103, 104, NOW, (), (BookLevel(1.401, 0),)))
    assert not book.synchronized


def test_zero_quantity_removes_level_and_top_is_sorted() -> None:
    book = LocalOrderBook.from_snapshot(_snapshot())
    book.apply_first_delta(
        DepthDelta(
            101,
            101,
            NOW,
            (BookLevel(1.400, 0), BookLevel(1.398, 300)),
            (BookLevel(1.401, 80),),
        )
    )
    bids, asks = book.top()
    assert bids[0].price == 1.399
    assert asks[0].price == 1.401


def test_cvd_uses_aggressor_side_not_trade_sign_guessing() -> None:
    trades = (
        AggregateTrade(1, 1.40, 100, NOW, buyer_is_maker=False),
        AggregateTrade(2, 1.41, 50, NOW, buyer_is_maker=True),
    )
    flow = compute_order_flow("XRPUSDT", trades)
    assert flow.aggressive_buy_notional == pytest.approx(140)
    assert flow.aggressive_sell_notional == pytest.approx(70.5)
    assert flow.cvd_quote == pytest.approx(69.5)
    assert flow.taker_imbalance > 0
