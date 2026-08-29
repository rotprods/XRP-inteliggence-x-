from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from xrp_regime_engine.providers.binance import BinanceSpotProvider
from xrp_regime_engine.providers.coinbase import CoinbaseExchangeProvider
from xrp_regime_engine.providers.fred import FredProvider
from xrp_regime_engine.providers.kraken import KrakenSpotProvider
from xrp_regime_engine.providers.base import ProviderError


def _milliseconds(value: datetime) -> int:
    return int(value.timestamp() * 1000)


@pytest.mark.asyncio
async def test_binance_keeps_usdt_semantics_separate_from_usd() -> None:
    now = datetime.now(UTC)
    open_time = now - timedelta(hours=2)
    close_time = now - timedelta(hours=1)
    payload = [
        [
            _milliseconds(open_time),
            "1.0",
            "1.2",
            "0.9",
            "1.1",
            "100",
            _milliseconds(close_time),
        ]
    ]
    provider = BinanceSpotProvider(
        "https://data-api.binance.vision",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )
    try:
        candles = await provider.fetch_candles("XRP_USDT", "1h", 1)
        with pytest.raises(ProviderError):
            await provider.fetch_candles("XRP_USD", "1h", 1)
    finally:
        await provider.aclose()
    assert len(candles) == 1
    assert candles[0].asset == "XRP_USDT"


@pytest.mark.asyncio
async def test_coinbase_and_kraken_parse_closed_usd_candles() -> None:
    open_time = datetime.now(UTC) - timedelta(hours=2)
    coinbase_payload = [
        [int(open_time.timestamp()), 0.9, 1.2, 1.0, 1.1, 100.0]
    ]
    coinbase = CoinbaseExchangeProvider(
        "https://api.exchange.coinbase.com",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=coinbase_payload)
        ),
    )
    try:
        coinbase_candles = await coinbase.fetch_candles("XRP_USD", "1h", 1)
    finally:
        await coinbase.aclose()

    kraken_payload = {
        "error": [],
        "result": {
            "XXRPZUSD": [
                [
                    int(open_time.timestamp()),
                    "1.0",
                    "1.2",
                    "0.9",
                    "1.1",
                    "1.05",
                    "100",
                    5,
                ]
            ],
            "last": int(open_time.timestamp()),
        },
    }
    kraken = KrakenSpotProvider(
        "https://api.kraken.com",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=kraken_payload)
        ),
    )
    try:
        kraken_candles = await kraken.fetch_candles("XRP_USD", "1h", 1)
    finally:
        await kraken.aclose()

    assert coinbase_candles[0].close == 1.1
    assert kraken_candles[0].close == 1.1


@pytest.mark.asyncio
async def test_fred_uses_realtime_start_as_date_precision_availability() -> None:
    payload = {
        "observations": [
            {
                "date": "2020-01-01",
                "realtime_start": "2020-02-01",
                "realtime_end": "2020-12-31",
                "value": "4.25",
            }
        ]
    }
    fred = FredProvider(
        "test-key",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )
    try:
        observations = await fred.fetch_series("DGS10")
    finally:
        await fred.aclose()
    assert observations[0].available_at.date().isoformat() == "2020-02-01"
    assert observations[0].metadata["availability_precision"] == "date"
