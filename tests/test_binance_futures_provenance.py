from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from xrp_regime_engine.providers.base import ProviderError
from xrp_regime_engine.providers.binance_futures import BinanceFuturesProvider

OBSERVED = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def _provider(handler: Callable[[httpx.Request], httpx.Response]) -> BinanceFuturesProvider:
    return BinanceFuturesProvider(
        "https://fapi.binance.com",
        transport=httpx.MockTransport(handler),
        max_attempts=1,
    )


@pytest.mark.asyncio
async def test_funding_captures_local_fetch_time_without_inventing_availability() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/fapi/v1/premiumIndex"
        return httpx.Response(
            200,
            json={
                "symbol": "XRPUSDT",
                "markPrice": "1.42",
                "indexPrice": "1.419",
                "lastFundingRate": "0.0001",
                "nextFundingTime": int(
                    (OBSERVED + timedelta(hours=8)).timestamp() * 1000
                ),
                "time": int(OBSERVED.timestamp() * 1000),
            },
            headers={"content-type": "application/json"},
        )

    provider = _provider(handler)
    before = datetime.now(UTC)
    try:
        state = await provider.fetch_funding()
    finally:
        await provider.aclose()
    after = datetime.now(UTC)

    assert state.fetched_at is not None
    assert before <= state.fetched_at <= after
    assert state.available_at is None
    assert state.provenance_complete is False
    assert state.payload_sha256 is not None
    assert len(state.payload_sha256) == 64


@pytest.mark.asyncio
async def test_open_interest_captures_local_fetch_time_without_inventing_availability() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/fapi/v1/openInterest"
        return httpx.Response(
            200,
            json={
                "symbol": "XRPUSDT",
                "openInterest": "123456.7",
                "time": int(OBSERVED.timestamp() * 1000),
            },
            headers={"content-type": "application/json"},
        )

    provider = _provider(handler)
    before = datetime.now(UTC)
    try:
        state = await provider.fetch_open_interest()
    finally:
        await provider.aclose()
    after = datetime.now(UTC)

    assert state.fetched_at is not None
    assert before <= state.fetched_at <= after
    assert state.available_at is None
    assert state.provenance_complete is False
    assert state.payload_sha256 is not None
    assert len(state.payload_sha256) == 64


@pytest.mark.asyncio
async def test_future_exchange_timestamp_fails_closed_against_ingestion_clock() -> None:
    future = datetime.now(UTC) + timedelta(hours=1)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/fapi/v1/openInterest"
        return httpx.Response(
            200,
            json={
                "symbol": "XRPUSDT",
                "openInterest": "1",
                "time": int(future.timestamp() * 1000),
            },
            headers={"content-type": "application/json"},
        )

    provider = _provider(handler)
    try:
        with pytest.raises(ProviderError, match="malformed open-interest data"):
            await provider.fetch_open_interest()
    finally:
        await provider.aclose()
