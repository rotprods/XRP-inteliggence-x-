from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.depth_dynamics import apply_delta_with_dynamics
from xrp_regime_engine.local_book import BookSequenceError, DepthDelta, LocalOrderBook
from xrp_regime_engine.microstructure import BookLevel, OrderBookSnapshot

NOW = datetime(2026, 9, 21, 1, 0, tzinfo=UTC)


def _book() -> LocalOrderBook:
    snapshot = OrderBookSnapshot(
        symbol="XRPUSDT",
        last_update_id=100,
        observed_at=NOW,
        fetched_at=NOW,
        bids=(BookLevel(1.400, 100), BookLevel(1.399, 200)),
        asks=(BookLevel(1.401, 100), BookLevel(1.402, 200)),
        provider="fixture",
        payload_hash="0" * 64,
    )
    book = LocalOrderBook.from_snapshot(snapshot)
    book.apply_first_delta(
        DepthDelta(
            101,
            101,
            NOW + timedelta(milliseconds=100),
            (BookLevel(1.400, 100),),
            (BookLevel(1.401, 100),),
        )
    )
    return book


def test_depth_dynamics_account_added_removed_notional_without_causal_claim() -> None:
    book = _book()
    state = apply_delta_with_dynamics(
        book,
        DepthDelta(
            102,
            102,
            NOW + timedelta(milliseconds=200),
            (BookLevel(1.400, 125), BookLevel(1.399, 150)),
            (BookLevel(1.401, 80), BookLevel(1.403, 40)),
        ),
    )
    assert state is not None
    assert state.bid_added_notional == pytest.approx(1.400 * 25)
    assert state.bid_removed_notional == pytest.approx(1.399 * 50)
    assert state.ask_removed_notional == pytest.approx(1.401 * 20)
    assert state.ask_added_notional == pytest.approx(1.403 * 40)
    assert state.gross_churn_notional > 0
    assert state.churn_quote_per_second > 0
    assert state.trade_attribution_confirmed is False
    assert "TRADE_ATTRIBUTION_REQUIRED" in state.quality_flags
    assert state.execution_weight == 0.0


def test_stale_delta_is_ignored_without_rewriting_book() -> None:
    book = _book()
    before = (book.last_update_id, dict(book.bids), dict(book.asks), book.observed_at)
    state = apply_delta_with_dynamics(
        book,
        DepthDelta(
            100,
            101,
            NOW + timedelta(milliseconds=200),
            (BookLevel(1.400, 1),),
            (),
        ),
    )
    assert state is None
    assert (book.last_update_id, book.bids, book.asks, book.observed_at) == before
    assert book.synchronized


def test_sequence_gap_fails_closed_via_local_book_contract() -> None:
    book = _book()
    with pytest.raises(BookSequenceError, match="resnapshot"):
        apply_delta_with_dynamics(
            book,
            DepthDelta(
                104,
                104,
                NOW + timedelta(milliseconds=200),
                (BookLevel(1.400, 90),),
                (),
            ),
        )
    assert not book.synchronized


def test_large_event_time_gap_invalidates_book_before_metrics() -> None:
    book = _book()
    with pytest.raises(BookSequenceError, match="time gap"):
        apply_delta_with_dynamics(
            book,
            DepthDelta(
                102,
                102,
                NOW + timedelta(seconds=3),
                (BookLevel(1.400, 90),),
                (),
            ),
            max_event_gap_seconds=2.0,
        )
    assert not book.synchronized


def test_non_monotonic_event_time_invalidates_book() -> None:
    book = _book()
    with pytest.raises(BookSequenceError, match="monotonically"):
        apply_delta_with_dynamics(
            book,
            DepthDelta(
                102,
                102,
                NOW + timedelta(milliseconds=50),
                (BookLevel(1.400, 90),),
                (),
            ),
        )
    assert not book.synchronized


def test_duplicate_price_level_invalidates_book_before_mutation() -> None:
    book = _book()
    with pytest.raises(ValueError, match="duplicate price"):
        apply_delta_with_dynamics(
            book,
            DepthDelta(
                102,
                102,
                NOW + timedelta(milliseconds=200),
                (BookLevel(1.400, 90), BookLevel(1.400, 80)),
                (),
            ),
        )
    assert not book.synchronized
    assert book.last_update_id == 101
