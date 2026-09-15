from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from xrp_regime_engine.providers.base import ProviderError
from xrp_regime_engine.providers.kucoin import KuCoinSpotProvider

pytestmark = [pytest.mark.contract, pytest.mark.security]


def mock(payload: object, status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda request: httpx.Response(
            status,
            json=payload,
            headers={"content-type": "application/json"},
        )
    )


@pytest.mark.asyncio
async def test_kucoin_normalizes_current_unified_kline_contract() -> None:
    start = datetime.now(UTC) - timedelta(hours=3)
    payload = {
        "code": "200000",
        "data": [
            [str(int(start.timestamp())), "1.00", "1.01", "1.02", "0.99", "100", "101"],
            [
                str(int((start + timedelta(hours=1)).timestamp())),
                "1.01",
                "1.02",
                "1.03",
                "1.00",
                "120",
                "122",
            ],
        ],
    }
    provider = KuCoinSpotProvider("https://api.kucoin.com", transport=mock(payload))
    try:
        rows = await provider.fetch_candles("XRP_USDT", "1h", 2)
    finally:
        await provider.aclose()
    assert len(rows) == 2
    assert rows[0].asset == "XRP_USDT"
    assert rows[0].open == 1.0
    assert rows[0].close == 1.01
    assert rows[0].high == 1.02
    assert rows[0].low == 0.99
    assert rows[0].provenance.provider == "kucoin_spot"
    assert rows[0].provenance.payload_hash


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "unexpected payload"),
        ({"code": "400000", "data": []}, "unexpected payload"),
        ({"code": "200000", "data": {}}, "malformed kline data"),
        ({"code": "200000", "data": [["1", "2"]]}, "malformed kline"),
        ({"code": "200000", "data": ["not-a-row"]}, "malformed kline"),
        (
            {
                "code": "200000",
                "data": [["bad", "1", "1", "1", "1", "1", "1"]],
            },
            "malformed kline",
        ),
    ],
)
async def test_kucoin_rejects_malformed_payloads(payload: object, message: str) -> None:
    provider = KuCoinSpotProvider("https://api.kucoin.com", transport=mock(payload))
    try:
        with pytest.raises(ProviderError, match=message):
            await provider.fetch_candles("XRP_USDT", "1h", 1)
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_kucoin_skips_future_open_candle_and_slices_limit() -> None:
    now = datetime.now(UTC)
    past = now - timedelta(hours=4)
    future = now + timedelta(hours=1)
    payload = {
        "code": "200000",
        "data": [
            [str(int(past.timestamp())), "1", "1", "1", "1", "1", "1"],
            [str(int((past + timedelta(hours=1)).timestamp())), "2", "2", "2", "2", "1", "1"],
            [str(int(future.timestamp())), "3", "3", "3", "3", "1", "1"],
        ],
    }
    provider = KuCoinSpotProvider("https://api.kucoin.com", transport=mock(payload))
    try:
        rows = await provider.fetch_candles("XRP_USDT", "1h", 1)
    finally:
        await provider.aclose()
    assert len(rows) == 1
    assert rows[0].close == 2


@pytest.mark.asyncio
async def test_kucoin_rejects_unsupported_asset_interval_and_limit() -> None:
    provider = KuCoinSpotProvider("https://api.kucoin.com", transport=mock({"code": "200000", "data": []}))
    try:
        with pytest.raises(ProviderError, match="unsupported asset/interval"):
            await provider.fetch_candles("XRP_USD", "1h", 1)
        with pytest.raises(ProviderError, match="unsupported asset/interval"):
            await provider.fetch_candles("XRP_USDT", "2h", 1)
        with pytest.raises(ProviderError, match="limit"):
            await provider.fetch_candles("XRP_USDT", "1h", 0)
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_kucoin_health_is_fail_closed() -> None:
    open_provider = KuCoinSpotProvider(
        "https://api.kucoin.com",
        transport=mock({"code": "200000", "data": {"serverStatus": "open"}}),
    )
    try:
        health = await open_provider.health()
        assert health.status == "ok"
        assert health.error is None
        assert open_provider.health_path() == "/api/ua/v1/server/status"
    finally:
        await open_provider.aclose()

    closed_provider = KuCoinSpotProvider(
        "https://api.kucoin.com",
        transport=mock({"code": "200000", "data": {"serverStatus": "closed"}}),
    )
    try:
        health = await closed_provider.health()
        assert health.status == "down"
        assert health.error
    finally:
        await closed_provider.aclose()

    for payload in ([], {"code": "500000", "data": {}}, {"code": "200000", "data": []}):
        malformed_provider = KuCoinSpotProvider(
            "https://api.kucoin.com",
            transport=mock(payload),
        )
        try:
            health = await malformed_provider.health()
            assert health.status == "down"
            assert health.error and "health payload" in health.error
        finally:
            await malformed_provider.aclose()
