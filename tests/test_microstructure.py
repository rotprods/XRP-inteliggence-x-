from datetime import UTC, datetime

import httpx
import pytest

from xrp_regime_engine.microstructure import (
    BookLevel,
    OrderBookSnapshot,
    compute_microstructure,
)
from xrp_regime_engine.providers.base import ProviderError
from xrp_regime_engine.providers.binance_microstructure import BinanceMicrostructureProvider

NOW = datetime(2026, 9, 19, 11, 0, tzinfo=UTC)


def _snapshot() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="XRPUSDT",
        last_update_id=42,
        observed_at=NOW,
        fetched_at=NOW,
        bids=(BookLevel(1.4000, 1000), BookLevel(1.3990, 2000)),
        asks=(BookLevel(1.4010, 500), BookLevel(1.4020, 1000)),
        provider="fixture",
        payload_hash="0" * 64,
    )


def test_microstructure_computes_bounded_imbalance_and_microprice() -> None:
    state = compute_microstructure(_snapshot())
    assert -1 <= state.imbalance_10bps <= 1
    assert -1 <= state.imbalance_100bps <= 1
    assert 1.4000 <= state.microprice <= 1.4010
    assert state.bid_notional_100bps > state.ask_notional_100bps


def test_crossed_book_fails_closed() -> None:
    with pytest.raises(ValueError, match="crossed"):
        OrderBookSnapshot(
            symbol="XRPUSDT",
            last_update_id=1,
            observed_at=NOW,
            fetched_at=NOW,
            bids=(BookLevel(1.41, 1),),
            asks=(BookLevel(1.40, 1),),
            provider="fixture",
            payload_hash="0" * 64,
        )


@pytest.mark.asyncio
async def test_binance_depth_adapter_is_read_only_and_parses_snapshot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v3/depth"
        assert request.url.params["symbol"] == "XRPUSDT"
        return httpx.Response(
            200,
            json={
                "lastUpdateId": 99,
                "bids": [["1.4000", "100.0"], ["1.3990", "200.0"]],
                "asks": [["1.4010", "90.0"], ["1.4020", "120.0"]],
            },
            headers={"content-type": "application/json"},
        )

    provider = BinanceMicrostructureProvider(
        "https://api.binance.com",
        transport=httpx.MockTransport(handler),
        max_attempts=1,
    )
    try:
        snapshot = await provider.fetch_order_book(limit=100)
    finally:
        await provider.aclose()
    assert snapshot.symbol == "XRPUSDT"
    assert snapshot.last_update_id == 99
    assert snapshot.bids[0].price == 1.4
    assert snapshot.asks[0].price == 1.401


@pytest.mark.asyncio
async def test_invalid_depth_limit_fails_before_network() -> None:
    provider = BinanceMicrostructureProvider(
        "https://api.binance.com",
        transport=httpx.MockTransport(lambda request: pytest.fail("network should not run")),
    )
    try:
        with pytest.raises(ProviderError, match="depth limit"):
            await provider.fetch_order_book(limit=123)
    finally:
        await provider.aclose()
