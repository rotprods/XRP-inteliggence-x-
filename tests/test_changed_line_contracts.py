from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from math import nan

import httpx
import pytest

from xrp_regime_engine.depth_dynamics import DepthDynamics, apply_delta_with_dynamics
from xrp_regime_engine.derivatives import (
    FundingState,
    OpenInterestState,
    assess_derivatives_risk,
)
from xrp_regime_engine.local_book import BookSequenceError, DepthDelta, LocalOrderBook
from xrp_regime_engine.microstructure import (
    BookLevel,
    MicrostructureState,
    OrderBookSnapshot,
    compute_microstructure,
)
from xrp_regime_engine.order_flow import OrderFlowState
from xrp_regime_engine.providers.base import ProviderError
from xrp_regime_engine.providers.binance_futures import BinanceFuturesProvider
from xrp_regime_engine.providers.binance_microstructure import BinanceMicrostructureProvider
from xrp_regime_engine.stream_alignment import (
    CrossStreamFreshnessPolicy,
    assess_cross_stream_alignment,
)
from xrp_regime_engine.temporal_alignment import build_aligned_temporal_window
from xrp_regime_engine.temporal_flow import TemporalFlowSample, build_temporal_window
from xrp_regime_engine.trade_attribution import (
    _require_present_aware,
    reconcile_depth_with_order_flow,
)

T0 = datetime(2026, 9, 21, 7, 0, tzinfo=UTC)


def _depth(
    *,
    observed_at: datetime | None = None,
    available_at: datetime | None = None,
    fetched_at: datetime | None = None,
    provenance_complete: bool = True,
    symbol: str = "XRPUSDT",
) -> DepthDynamics:
    observed = observed_at or T0 + timedelta(seconds=8)
    available = available_at if available_at is not None else observed + timedelta(milliseconds=100)
    fetched = fetched_at if fetched_at is not None else observed + timedelta(milliseconds=200)
    return DepthDynamics(
        symbol=symbol,
        observed_at=observed,
        first_update_id=1,
        final_update_id=2,
        elapsed_seconds=1.0,
        bid_added_notional=100.0,
        bid_removed_notional=50.0,
        ask_added_notional=25.0,
        ask_removed_notional=75.0,
        bid_net_notional=50.0,
        ask_net_notional=-50.0,
        gross_churn_notional=250.0,
        churn_quote_per_second=250.0,
        trade_attribution_confirmed=False,
        quality_flags=("TRADE_ATTRIBUTION_REQUIRED",),
        first_observed_at=observed - timedelta(seconds=1),
        last_observed_at=observed,
        first_available_at=(
            None if not provenance_complete else observed - timedelta(milliseconds=900)
        ),
        last_available_at=None if not provenance_complete else available,
        first_fetched_at=(
            None if not provenance_complete else observed - timedelta(milliseconds=800)
        ),
        last_fetched_at=None if not provenance_complete else fetched,
        provenance_complete=provenance_complete,
        execution_weight=0.0,
    )


def _flow(
    *,
    observed_at: datetime | None = None,
    symbol: str = "XRPUSDT",
) -> OrderFlowState:
    observed = observed_at or T0 + timedelta(seconds=8)
    return OrderFlowState(
        symbol=symbol,
        observed_at=observed,
        aggressive_buy_notional=600.0,
        aggressive_sell_notional=400.0,
        cvd_quote=200.0,
        taker_imbalance=0.2,
        trade_count=10,
        first_observed_at=observed - timedelta(seconds=1),
        last_observed_at=observed,
        first_available_at=observed - timedelta(milliseconds=900),
        last_available_at=observed + timedelta(milliseconds=100),
        first_fetched_at=observed - timedelta(milliseconds=800),
        last_fetched_at=observed + timedelta(milliseconds=200),
        provenance_complete=True,
    )


def _funding(*, observed_at: datetime | None = None, symbol: str = "XRPUSDT") -> FundingState:
    observed = observed_at or T0 + timedelta(seconds=8)
    return FundingState(
        symbol=symbol,
        observed_at=observed,
        mark_price=1.401,
        index_price=1.4,
        funding_rate=0.0001,
        next_funding_at=T0 + timedelta(hours=8),
        available_at=observed + timedelta(milliseconds=100),
        fetched_at=observed + timedelta(milliseconds=200),
        payload_sha256="a" * 64,
    )


def _open_interest(
    *, observed_at: datetime | None = None, symbol: str = "XRPUSDT"
) -> OpenInterestState:
    observed = observed_at or T0 + timedelta(seconds=8)
    return OpenInterestState(
        symbol=symbol,
        observed_at=observed,
        open_interest=100_000_000.0,
        available_at=observed + timedelta(milliseconds=100),
        fetched_at=observed + timedelta(milliseconds=200),
        payload_sha256="b" * 64,
    )


def _sample(
    observed_at: datetime,
    *,
    symbol: str = "XRPUSDT",
    available_at: datetime | None = None,
    fetched_at: datetime | None = None,
    mid_price: float = 1.4,
    imbalance: float = 0.2,
    buy: float = 100.0,
    sell: float = 80.0,
    open_interest: float | None = 100.0,
) -> TemporalFlowSample:
    available = available_at or observed_at + timedelta(milliseconds=10)
    fetched = fetched_at or observed_at + timedelta(milliseconds=20)
    return TemporalFlowSample(
        symbol=symbol,
        observed_at=observed_at,
        available_at=available,
        fetched_at=fetched,
        mid_price=mid_price,
        depth_imbalance_25bps=imbalance,
        aggressive_buy_notional=buy,
        aggressive_sell_notional=sell,
        open_interest=open_interest,
        funding_rate=0.0001,
        basis_bps=5.0,
    )


def _futures_provider(
    handler: Callable[[httpx.Request], httpx.Response],
) -> BinanceFuturesProvider:
    return BinanceFuturesProvider(
        "https://fapi.binance.com",
        transport=httpx.MockTransport(handler),
        max_attempts=1,
    )


def _spot_provider(
    handler: Callable[[httpx.Request], httpx.Response],
) -> BinanceMicrostructureProvider:
    return BinanceMicrostructureProvider(
        "https://data-api.binance.vision",
        transport=httpx.MockTransport(handler),
        max_attempts=1,
    )


def test_depth_dynamics_rejects_invalid_gap_unsynced_and_missing_clock() -> None:
    book = LocalOrderBook(
        symbol="XRPUSDT",
        last_update_id=100,
        bids={1.4: 10.0},
        asks={1.401: 10.0},
        synchronized=True,
        observed_at=T0,
    )
    delta = DepthDelta(101, 101, T0 + timedelta(seconds=1), (), ())
    with pytest.raises(ValueError, match="finite and positive"):
        apply_delta_with_dynamics(book, delta, max_event_gap_seconds=0.0)

    book.synchronized = False
    with pytest.raises(BookSequenceError, match="not synchronized"):
        apply_delta_with_dynamics(book, delta)

    book.synchronized = True
    book.observed_at = None
    with pytest.raises(BookSequenceError, match="missing observed_at"):
        apply_delta_with_dynamics(book, delta)
    assert book.synchronized is False


def test_depth_dynamics_rejects_naive_book_clock_and_marks_no_change() -> None:
    naive_book = LocalOrderBook(
        symbol="XRPUSDT",
        last_update_id=100,
        bids={1.4: 10.0},
        asks={1.401: 10.0},
        synchronized=True,
        observed_at=T0.replace(tzinfo=None),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        apply_delta_with_dynamics(
            naive_book,
            DepthDelta(101, 101, T0 + timedelta(seconds=1), (), ()),
        )

    book = LocalOrderBook(
        symbol="XRPUSDT",
        last_update_id=100,
        bids={1.4: 10.0},
        asks={1.401: 10.0},
        synchronized=True,
        observed_at=T0,
    )
    result = apply_delta_with_dynamics(
        book,
        DepthDelta(101, 101, T0 + timedelta(seconds=1), (), ()),
    )
    assert result is not None
    assert result.gross_churn_notional == 0.0
    assert "NO_DISPLAYED_DEPTH_CHANGE" in result.quality_flags
    assert "POINT_IN_TIME_PROVENANCE_INCOMPLETE" in result.quality_flags


def test_derivative_models_fail_closed_on_numeric_time_and_digest_edges() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        OpenInterestState("XRPUSDT", T0.replace(tzinfo=None), 1.0)
    with pytest.raises(ValueError, match="finite and non-negative"):
        OpenInterestState("XRPUSDT", T0, -1.0)
    with pytest.raises(ValueError, match="cannot precede observed_at"):
        OpenInterestState("XRPUSDT", T0, 1.0, fetched_at=T0 - timedelta(seconds=1))
    with pytest.raises(ValueError, match="cannot follow fetched_at"):
        OpenInterestState(
            "XRPUSDT",
            T0,
            1.0,
            available_at=T0 + timedelta(seconds=2),
            fetched_at=T0 + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="SHA-256"):
        OpenInterestState("XRPUSDT", T0, 1.0, payload_sha256="A" * 64)
    with pytest.raises(ValueError, match="derivatives values must be finite"):
        FundingState("XRPUSDT", T0, 1.4, 1.4, nan, T0 + timedelta(hours=8))
    with pytest.raises(ValueError, match="must be positive"):
        FundingState("XRPUSDT", T0, 0.0, 1.4, 0.0, T0 + timedelta(hours=8))
    with pytest.raises(ValueError, match="timezone-aware"):
        FundingState("XRPUSDT", T0, 1.4, 1.4, 0.0, T0.replace(tzinfo=None))


def test_derivatives_risk_covers_positive_negative_basis_and_missing_oi() -> None:
    positive = FundingState(
        "XRPUSDT",
        T0,
        1.01,
        1.0,
        0.001,
        T0 + timedelta(hours=8),
    )
    positive_risk = assess_derivatives_risk(positive)
    assert set(positive_risk.quality_flags) == {
        "ELEVATED_POSITIVE_FUNDING",
        "WIDE_MARK_INDEX_BASIS",
        "OPEN_INTEREST_NO_DATA",
    }
    assert positive_risk.open_interest is None

    negative = FundingState(
        "XRPUSDT",
        T0,
        1.0,
        1.0,
        -0.001,
        T0 + timedelta(hours=8),
    )
    oi = OpenInterestState("XRPUSDT", T0, 123.0)
    negative_risk = assess_derivatives_risk(negative, oi)
    assert negative_risk.quality_flags == ("ELEVATED_NEGATIVE_FUNDING",)
    assert negative_risk.open_interest == 123.0


def test_microstructure_validation_and_quality_flag_edges() -> None:
    with pytest.raises(ValueError, match="price must be finite and positive"):
        BookLevel(0.0, 1.0)
    with pytest.raises(ValueError, match="quantity must be finite and non-negative"):
        BookLevel(1.0, -1.0)

    with pytest.raises(ValueError, match="requires bids and asks"):
        OrderBookSnapshot("XRPUSDT", 1, T0, T0, (), (BookLevel(1.1, 1.0),), "fixture", "0" * 64)
    with pytest.raises(ValueError, match="later than fetched_at"):
        OrderBookSnapshot(
            "XRPUSDT",
            1,
            T0 + timedelta(seconds=1),
            T0,
            (BookLevel(1.0, 1.0),),
            (BookLevel(1.1, 1.0),),
            "fixture",
            "0" * 64,
        )

    naive = T0.replace(tzinfo=None)
    snapshot = OrderBookSnapshot(
        "XRPUSDT",
        1,
        naive,
        naive,
        (BookLevel(1.0, 0.0),),
        (BookLevel(1.01, 0.0),),
        "fixture",
        "0" * 64,
    )
    state = compute_microstructure(snapshot)
    assert state.microprice == state.mid_price
    assert "WIDE_SPREAD" in state.quality_flags
    assert "NAIVE_TIMESTAMP" in state.quality_flags


@pytest.mark.asyncio
async def test_futures_provider_contract_edges_are_hermetic() -> None:
    def non_dict(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], headers={"content-type": "application/json"})

    provider = _futures_provider(non_dict)
    try:
        assert provider.health_path() == "/fapi/v1/ping"
        with pytest.raises(ProviderError, match="does not expose candles"):
            await provider.fetch_candles("XRP_USDT", "1m")
        with pytest.raises(ProviderError, match="unsupported asset"):
            await provider.fetch_funding("DOGE_USDT")
        with pytest.raises(ProviderError, match="unsupported asset"):
            await provider.fetch_open_interest("DOGE_USDT")
        with pytest.raises(ProviderError, match="unexpected premium-index"):
            await provider.fetch_funding()
        with pytest.raises(ProviderError, match="unexpected open-interest"):
            await provider.fetch_open_interest()
    finally:
        await provider.aclose()

    def malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={}, headers={"content-type": "application/json"})

    provider = _futures_provider(malformed)
    try:
        with pytest.raises(ProviderError, match="malformed premium-index"):
            await provider.fetch_funding()
        with pytest.raises(ProviderError, match="malformed open-interest"):
            await provider.fetch_open_interest()
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_spot_microstructure_provider_contract_edges_are_hermetic() -> None:
    def non_dict(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], headers={"content-type": "application/json"})

    provider = _spot_provider(non_dict)
    try:
        assert provider.health_path() == "/api/v3/ping"
        with pytest.raises(ProviderError, match="does not expose candles"):
            await provider.fetch_candles("XRP_USDT", "1m")
        with pytest.raises(ProviderError, match="unsupported asset"):
            await provider.fetch_order_book("DOGE_USDT")
        with pytest.raises(ProviderError, match="unsupported Binance depth limit"):
            await provider.fetch_order_book(limit=7)
        with pytest.raises(ProviderError, match="unexpected depth payload"):
            await provider.fetch_order_book()
    finally:
        await provider.aclose()

    def malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"lastUpdateId": 1, "bids": "bad", "asks": []},
            headers={"content-type": "application/json"},
        )

    provider = _spot_provider(malformed)
    try:
        with pytest.raises(ProviderError, match="malformed depth data"):
            await provider.fetch_order_book()
    finally:
        await provider.aclose()


def test_alignment_policy_no_data_invalid_provenance_and_future_knowledge_edges() -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        CrossStreamFreshnessPolicy(depth_max_age_seconds=0.0)
    with pytest.raises(ValueError, match="timezone-aware"):
        assess_cross_stream_alignment(
            depth=None,
            order_flow=None,
            funding=None,
            open_interest=None,
            prediction_time=T0.replace(tzinfo=None),
        )

    empty = assess_cross_stream_alignment(
        depth=None,
        order_flow=None,
        funding=None,
        open_interest=None,
        prediction_time=T0 + timedelta(seconds=10),
    )
    assert empty.symbol == "UNKNOWN"
    assert empty.point_in_time_eligible is False
    assert {
        "DEPTH_NO_DATA",
        "AGG_TRADES_NO_DATA",
        "OPEN_INTEREST_NO_DATA",
        "FUNDING_NO_DATA",
        "BASIS_NO_DATA",
    }.issubset(empty.quality_flags)

    observed = T0 + timedelta(seconds=8)
    invalid = _depth(
        observed_at=observed,
        available_at=observed - timedelta(milliseconds=1),
        fetched_at=observed + timedelta(milliseconds=200),
    )
    invalid_result = assess_cross_stream_alignment(
        depth=invalid,
        order_flow=None,
        funding=None,
        open_interest=None,
        prediction_time=T0 + timedelta(seconds=10),
    )
    assert "DEPTH_PROVENANCE_INVALID" in invalid_result.quality_flags

    future_observed = T0 + timedelta(seconds=11)
    future = _depth(observed_at=future_observed)
    future_result = assess_cross_stream_alignment(
        depth=future,
        order_flow=None,
        funding=None,
        open_interest=None,
        prediction_time=T0 + timedelta(seconds=10),
    )
    assert "DEPTH_FUTURE_KNOWLEDGE" in future_result.quality_flags

    current = T0 + timedelta(seconds=8)
    future_fetch = _depth(
        observed_at=current,
        available_at=T0 + timedelta(seconds=11),
        fetched_at=T0 + timedelta(seconds=12),
    )
    future_fetch_result = assess_cross_stream_alignment(
        depth=future_fetch,
        order_flow=None,
        funding=None,
        open_interest=None,
        prediction_time=T0 + timedelta(seconds=10),
    )
    assert "DEPTH_FUTURE_KNOWLEDGE" in future_fetch_result.quality_flags


def test_temporal_alignment_rejects_symbol_mismatch_after_alignment_passes() -> None:
    prediction = T0 + timedelta(seconds=10)
    samples = (
        _sample(T0 - timedelta(seconds=45), symbol="BTCUSDT"),
        _sample(T0 + timedelta(seconds=7), symbol="BTCUSDT"),
    )
    with pytest.raises(ValueError, match="symbol must match"):
        build_aligned_temporal_window(
            samples=samples,
            depth=_depth(),
            order_flow=_flow(),
            funding=_funding(),
            open_interest=_open_interest(),
            prediction_time=prediction,
            window_seconds=60,
        )


def test_temporal_sample_validation_and_window_selection_edges() -> None:
    with pytest.raises(ValueError, match="observed <= available <= fetched"):
        _sample(T0, available_at=T0 - timedelta(seconds=1), fetched_at=T0)
    with pytest.raises(ValueError, match="symbol is required"):
        _sample(T0, symbol="")
    with pytest.raises(ValueError, match="must be finite"):
        _sample(T0, buy=nan)
    with pytest.raises(ValueError, match="mid_price must be positive"):
        _sample(T0, mid_price=0.0)
    with pytest.raises(ValueError, match="within \[-1, 1\]"):
        _sample(T0, imbalance=2.0)
    with pytest.raises(ValueError, match="aggressive notionals must be non-negative"):
        _sample(T0, sell=-1.0)
    with pytest.raises(ValueError, match="open_interest must be non-negative"):
        _sample(T0, open_interest=-1.0)

    prediction = T0 + timedelta(seconds=60)
    with pytest.raises(ValueError, match="cannot mix symbols"):
        build_temporal_window(
            (
                _sample(T0 + timedelta(seconds=10), symbol="XRPUSDT"),
                _sample(T0 + timedelta(seconds=20), symbol="BTCUSDT"),
            ),
            prediction_time=prediction,
            window_seconds=60,
        )

    unavailable = _sample(
        T0 + timedelta(seconds=50),
        available_at=prediction + timedelta(seconds=1),
        fetched_at=prediction + timedelta(seconds=2),
    )
    assert (
        build_temporal_window(
            (unavailable,), prediction_time=prediction, window_seconds=60
        )
        is None
    )


def test_trade_attribution_present_helper_and_last_availability_order_fail_closed() -> None:
    with pytest.raises(ValueError, match="required"):
        _require_present_aware(None, "probe")

    depth = _depth()
    depth = replace(
        depth,
        first_available_at=depth.first_observed_at,
        last_available_at=depth.last_observed_at - timedelta(milliseconds=1),
    )
    with pytest.raises(ValueError, match="availability precedes observation"):
        reconcile_depth_with_order_flow(
            depth,
            _flow(),
            prediction_time=T0 + timedelta(seconds=10),
        )
