from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.depth_dynamics import DepthDynamics
from xrp_regime_engine.derivatives import DerivativesRiskState
from xrp_regime_engine.flow_regime import FlowRegimeLabel, classify_flow_regime
from xrp_regime_engine.local_book import BookSequenceError, DepthDelta, LocalOrderBook
from xrp_regime_engine.market_state import MarketStateLabel, classify_market_state
from xrp_regime_engine.microstructure import BookLevel, MicrostructureState
from xrp_regime_engine.order_flow import AggregateTrade, OrderFlowState, compute_order_flow
from xrp_regime_engine.trade_attribution import reconcile_depth_with_order_flow

NOW = datetime(2026, 9, 21, 7, 0, tzinfo=UTC)


def _micro(
    imbalance: float = 0.0,
    *,
    microprice: float = 1.4,
    mid_price: float = 1.4,
) -> MicrostructureState:
    return MicrostructureState(
        symbol="XRPUSDT",
        observed_at=NOW,
        mid_price=mid_price,
        spread_bps=1.0,
        microprice=microprice,
        imbalance_10bps=imbalance,
        imbalance_25bps=imbalance,
        imbalance_50bps=imbalance,
        imbalance_100bps=imbalance,
        bid_notional_100bps=1_000_000.0,
        ask_notional_100bps=1_000_000.0,
    )


def _flow(imbalance: float = 0.0) -> OrderFlowState:
    return OrderFlowState(
        symbol="XRPUSDT",
        observed_at=NOW,
        aggressive_buy_notional=600.0,
        aggressive_sell_notional=400.0,
        cvd_quote=200.0,
        taker_imbalance=imbalance,
        trade_count=10,
    )


def _derivatives(*flags: str) -> DerivativesRiskState:
    return DerivativesRiskState(
        symbol="XRPUSDT",
        observed_at=NOW,
        funding_rate=0.001,
        basis_bps=5.0,
        open_interest=1_000_000.0,
        quality_flags=flags,
    )


def _complete_depth() -> DepthDynamics:
    return DepthDynamics(
        symbol="XRPUSDT",
        observed_at=NOW + timedelta(seconds=1),
        first_update_id=10,
        final_update_id=11,
        elapsed_seconds=1.0,
        bid_added_notional=0.0,
        bid_removed_notional=600.0,
        ask_added_notional=0.0,
        ask_removed_notional=400.0,
        bid_net_notional=-600.0,
        ask_net_notional=-400.0,
        gross_churn_notional=1000.0,
        churn_quote_per_second=1000.0,
        trade_attribution_confirmed=False,
        quality_flags=("TRADE_ATTRIBUTION_REQUIRED",),
        first_observed_at=NOW,
        last_observed_at=NOW + timedelta(seconds=1),
        first_available_at=NOW + timedelta(milliseconds=10),
        last_available_at=NOW + timedelta(seconds=1, milliseconds=10),
        first_fetched_at=NOW + timedelta(milliseconds=20),
        last_fetched_at=NOW + timedelta(seconds=1, milliseconds=20),
        provenance_complete=True,
        execution_weight=0.0,
    )


def _complete_flow() -> OrderFlowState:
    return OrderFlowState(
        symbol="XRPUSDT",
        observed_at=NOW + timedelta(seconds=1),
        aggressive_buy_notional=300.0,
        aggressive_sell_notional=500.0,
        cvd_quote=-200.0,
        taker_imbalance=-0.25,
        trade_count=10,
        first_observed_at=NOW,
        last_observed_at=NOW + timedelta(seconds=1),
        first_available_at=NOW + timedelta(milliseconds=15),
        last_available_at=NOW + timedelta(seconds=1, milliseconds=15),
        first_fetched_at=NOW + timedelta(milliseconds=25),
        last_fetched_at=NOW + timedelta(seconds=1, milliseconds=25),
        provenance_complete=True,
    )


def _reconcile(depth: DepthDynamics) -> None:
    reconcile_depth_with_order_flow(
        depth,
        _complete_flow(),
        prediction_time=NOW + timedelta(seconds=2),
    )


def _delta(
    first_update_id: int = 101,
    final_update_id: int = 101,
    *,
    bids: tuple[BookLevel, ...] = (),
    asks: tuple[BookLevel, ...] = (),
    observed_at: datetime = NOW,
    available_at: datetime | None = None,
    fetched_at: datetime | None = None,
) -> DepthDelta:
    return DepthDelta(
        first_update_id=first_update_id,
        final_update_id=final_update_id,
        observed_at=observed_at,
        bids=bids,
        asks=asks,
        available_at=available_at,
        fetched_at=fetched_at,
    )


def _book(*, synchronized: bool = False) -> LocalOrderBook:
    return LocalOrderBook(
        symbol="XRPUSDT",
        last_update_id=100,
        bids={1.400: 100.0},
        asks={1.401: 100.0},
        synchronized=synchronized,
        observed_at=NOW,
    )


def test_flow_no_data_preserves_flow_identity_when_depth_missing() -> None:
    state = classify_flow_regime(None, _flow(), None)
    assert state.label == FlowRegimeLabel.NO_DATA
    assert state.symbol == "XRPUSDT"
    assert state.observed_at == NOW


def test_flow_no_data_uses_derivatives_when_both_spot_streams_missing() -> None:
    state = classify_flow_regime(None, None, _derivatives())
    assert state.label == FlowRegimeLabel.NO_DATA
    assert state.symbol == "XRPUSDT"
    assert state.observed_at == NOW


def test_absorption_with_positive_funding_is_long_crowding() -> None:
    state = classify_flow_regime(
        _micro(0.4, microprice=1.401),
        _flow(-0.3),
        _derivatives("ELEVATED_POSITIVE_FUNDING"),
    )
    assert state.label == FlowRegimeLabel.LONG_CROWDING
    assert state.confidence == 0.55
    assert state.execution_weight == 0.0


def test_wide_basis_caps_flow_confidence_without_changing_label() -> None:
    state = classify_flow_regime(
        _micro(0.4, microprice=1.401),
        _flow(0.3),
        _derivatives("WIDE_MARK_INDEX_BASIS"),
    )
    assert state.label == FlowRegimeLabel.SPOT_LED_DEMAND
    assert state.confidence == 0.50
    assert "WIDE_MARK_INDEX_BASIS" in state.reasons


def test_neutral_flow_stays_mixed_with_explicit_no_edge_reason() -> None:
    state = classify_flow_regime(_micro(), _flow(), None)
    assert state.label == FlowRegimeLabel.MIXED
    assert state.reasons == ("NO_CONFLUENT_FLOW_EDGE",)


def test_positive_funding_does_not_relabel_sell_pressure() -> None:
    state = classify_flow_regime(
        _micro(-0.4, microprice=1.399),
        _flow(-0.3),
        _derivatives("ELEVATED_POSITIVE_FUNDING"),
    )
    assert state.label == FlowRegimeLabel.SELL_PRESSURE
    assert "ELEVATED_POSITIVE_FUNDING" in state.reasons


def test_market_no_data_uses_derivative_identity() -> None:
    state = classify_market_state(None, _derivatives())
    assert state.label == MarketStateLabel.NO_DATA
    assert state.symbol == "XRPUSDT"
    assert state.observed_at == NOW


def test_market_neutral_depth_is_balanced_with_no_edge_reason() -> None:
    state = classify_market_state(_micro(), None)
    assert state.label == MarketStateLabel.BALANCED
    assert state.reasons == ("NO_STRONG_MICROSTRUCTURE_EDGE",)


def test_market_wide_basis_is_recorded_without_directional_promotion() -> None:
    state = classify_market_state(_micro(), _derivatives("WIDE_MARK_INDEX_BASIS"))
    assert state.label == MarketStateLabel.BALANCED
    assert state.confidence == 0.45
    assert state.reasons == ("WIDE_MARK_INDEX_BASIS",)


def test_positive_funding_does_not_relabel_distribution() -> None:
    state = classify_market_state(
        _micro(-0.4, microprice=1.399),
        _derivatives("ELEVATED_POSITIVE_FUNDING"),
    )
    assert state.label == MarketStateLabel.DISTRIBUTION
    assert "ELEVATED_POSITIVE_FUNDING" in state.reasons


def test_bid_imbalance_without_supportive_microprice_stays_balanced() -> None:
    state = classify_market_state(_micro(0.4, microprice=1.4), None)
    assert state.label == MarketStateLabel.BALANCED


def test_ask_imbalance_without_lower_microprice_stays_balanced() -> None:
    state = classify_market_state(_micro(-0.4, microprice=1.401), None)
    assert state.label == MarketStateLabel.BALANCED


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {"first_observed_at": NOW + timedelta(seconds=2)},
            "derived_window_seconds must be finite and positive",
        ),
        (
            {"first_available_at": NOW + timedelta(seconds=2)},
            "available envelope is reversed",
        ),
        (
            {"first_fetched_at": NOW + timedelta(seconds=2)},
            "fetched envelope is reversed",
        ),
        (
            {"first_available_at": NOW - timedelta(milliseconds=1)},
            "availability precedes observation",
        ),
        (
            {"first_fetched_at": NOW + timedelta(milliseconds=5)},
            "fetch precedes availability",
        ),
    ],
)
def test_reversed_or_impossible_depth_provenance_fails_closed(
    updates: dict[str, datetime],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _reconcile(replace(_complete_depth(), **updates))


def test_naive_complete_envelope_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _reconcile(replace(_complete_depth(), first_observed_at=NOW.replace(tzinfo=None)))


def test_missing_flow_window_fallback_is_rejected() -> None:
    incomplete_depth = replace(
        _complete_depth(),
        first_observed_at=None,
        last_observed_at=None,
        first_available_at=None,
        last_available_at=None,
        first_fetched_at=None,
        last_fetched_at=None,
        provenance_complete=False,
    )
    incomplete_flow = replace(
        _complete_flow(),
        first_observed_at=None,
        last_observed_at=None,
        first_available_at=None,
        last_available_at=None,
        first_fetched_at=None,
        last_fetched_at=None,
        provenance_complete=False,
    )
    with pytest.raises(ValueError, match="explicit fallback is required"):
        reconcile_depth_with_order_flow(incomplete_depth, incomplete_flow)


@pytest.mark.parametrize("price", [0.0, -1.0, float("inf"), float("nan")])
def test_trade_rejects_invalid_price(price: float) -> None:
    with pytest.raises(ValueError, match="price must be finite and positive"):
        AggregateTrade(1, price, 1.0, NOW, buyer_is_maker=False)


def test_trade_rejects_invalid_quantity_and_naive_observation() -> None:
    with pytest.raises(ValueError, match="quantity must be finite and positive"):
        AggregateTrade(1, 1.4, 0.0, NOW, buyer_is_maker=False)
    with pytest.raises(ValueError, match="timezone-aware"):
        AggregateTrade(1, 1.4, 1.0, NOW.replace(tzinfo=None), buyer_is_maker=False)


def test_trade_rejects_fetched_without_available_and_impossible_timestamp_order() -> None:
    with pytest.raises(ValueError, match="provided together"):
        AggregateTrade(
            1,
            1.4,
            1.0,
            NOW,
            buyer_is_maker=False,
            fetched_at=NOW + timedelta(milliseconds=20),
        )
    with pytest.raises(ValueError, match="observed <= available <= fetched"):
        AggregateTrade(
            1,
            1.4,
            1.0,
            NOW,
            buyer_is_maker=False,
            available_at=NOW - timedelta(milliseconds=1),
            fetched_at=NOW + timedelta(milliseconds=20),
        )


def test_trade_aggressor_side_and_empty_flow_contract() -> None:
    buy = AggregateTrade(1, 1.4, 1.0, NOW, buyer_is_maker=False)
    sell = AggregateTrade(2, 1.4, 1.0, NOW, buyer_is_maker=True)
    assert buy.aggressive_side == "buy"
    assert sell.aggressive_side == "sell"
    with pytest.raises(ValueError, match="requires trades"):
        compute_order_flow("XRPUSDT", ())


def test_depth_delta_rejects_reversed_ids_naive_time_and_partial_provenance() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        _delta(102, 101)
    with pytest.raises(ValueError, match="timezone-aware"):
        _delta(observed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="provided together"):
        _delta(fetched_at=NOW + timedelta(milliseconds=20))


def test_depth_delta_rejects_impossible_timestamp_order() -> None:
    with pytest.raises(ValueError, match="observed <= available <= fetched"):
        _delta(
            available_at=NOW - timedelta(milliseconds=1),
            fetched_at=NOW + timedelta(milliseconds=20),
        )


def test_local_book_requires_sync_for_delta_and_top() -> None:
    book = _book()
    with pytest.raises(BookSequenceError, match="not synchronized"):
        book.apply_delta(_delta())
    with pytest.raises(BookSequenceError, match="not synchronized"):
        book.top()


def test_local_book_ignores_stale_delta_and_validates_top_level_count() -> None:
    book = _book(synchronized=True)
    book.apply_delta(_delta(99, 100, bids=(BookLevel(1.399, 10.0),)))
    assert 1.399 not in book.bids
    with pytest.raises(ValueError, match="levels must be positive"):
        book.top(0)


def test_local_book_crossed_update_invalidates_sync() -> None:
    book = _book(synchronized=True)
    with pytest.raises(BookSequenceError, match="invalid local book"):
        book.apply_delta(_delta(bids=(BookLevel(1.402, 10.0),)))
    assert book.synchronized is False
