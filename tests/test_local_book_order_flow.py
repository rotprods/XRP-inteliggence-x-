from datetime import UTC, datetime, timedelta

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
        book.apply_first_delta(DepthDelta(102, 103, NOW, (BookLevel(1.400, 90),), ()))


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
    assert flow.provenance_complete is False


def test_aggregate_trade_provenance_envelope_is_derived_from_events() -> None:
    trades = (
        AggregateTrade(
            1,
            1.40,
            100,
            NOW,
            buyer_is_maker=False,
            available_at=NOW + timedelta(milliseconds=10),
            fetched_at=NOW + timedelta(milliseconds=20),
        ),
        AggregateTrade(
            2,
            1.41,
            50,
            NOW + timedelta(seconds=1),
            buyer_is_maker=True,
            available_at=NOW + timedelta(seconds=1, milliseconds=10),
            fetched_at=NOW + timedelta(seconds=1, milliseconds=20),
        ),
    )
    flow = compute_order_flow("XRPUSDT", trades)
    assert flow.provenance_complete is True
    assert flow.first_observed_at == NOW
    assert flow.last_observed_at == NOW + timedelta(seconds=1)
    assert flow.first_available_at == NOW + timedelta(milliseconds=10)
    assert flow.last_fetched_at == NOW + timedelta(seconds=1, milliseconds=20)


def test_partial_trade_provenance_is_rejected() -> None:
    with pytest.raises(ValueError, match="provided together"):
        AggregateTrade(
            1,
            1.40,
            100,
            NOW,
            buyer_is_maker=False,
            available_at=NOW + timedelta(milliseconds=10),
        )
