from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from xrp_regime_engine.providers.base import ProviderError
from xrp_regime_engine.providers.binance import BinanceSpotProvider
from xrp_regime_engine.providers.coinbase import CoinbaseExchangeProvider
from xrp_regime_engine.providers.fred import FredProvider
from xrp_regime_engine.providers.kraken import KrakenSpotProvider
from xrp_regime_engine.providers.xrpl import XRPLProvider

pytestmark = [pytest.mark.contract, pytest.mark.security]


def mock(payload: object, status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda request: httpx.Response(
            status,
            json=payload,
            headers={"content-type": "application/json"},
        )
    )


@pytest.mark.parametrize(
    ("factory", "asset", "interval", "bad_limit"),
    [
        (lambda: BinanceSpotProvider("https://data-api.binance.vision", transport=mock([])), "XRP_USDT", "1h", 0),
        (lambda: CoinbaseExchangeProvider("https://api.exchange.coinbase.com", transport=mock([])), "XRP_USD", "1h", 301),
        (lambda: KrakenSpotProvider("https://api.kraken.com", transport=mock({"error": [], "result": {"X": [], "last": 0}})), "XRP_USD", "1h", 721),
    ],
)
@pytest.mark.asyncio
async def test_exchange_adapters_reject_invalid_limits(factory, asset: str, interval: str, bad_limit: int) -> None:
    provider = factory()
    try:
        with pytest.raises(ProviderError, match="limit"):
            await provider.fetch_candles(asset, interval, bad_limit)
    finally:
        await provider.aclose()


@pytest.mark.parametrize(
    ("factory", "asset", "interval"),
    [
        (lambda: BinanceSpotProvider("https://data-api.binance.vision", transport=mock([])), "NOPE", "1h"),
        (lambda: CoinbaseExchangeProvider("https://api.exchange.coinbase.com", transport=mock([])), "NOPE", "1h"),
        (lambda: KrakenSpotProvider("https://api.kraken.com", transport=mock({"error": [], "result": {"X": [], "last": 0}})), "NOPE", "1h"),
    ],
)
@pytest.mark.asyncio
async def test_exchange_adapters_reject_unsupported_assets(factory, asset: str, interval: str) -> None:
    provider = factory()
    try:
        with pytest.raises(ProviderError, match="unsupported asset/interval"):
            await provider.fetch_candles(asset, interval, 1)
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_binance_rejects_wrong_root_malformed_and_invalid_numeric() -> None:
    for payload, message in [
        ({"bad": True}, "unexpected payload"),
        ([[1, 2]], "malformed kline"),
        ([[0, "bad", "1", "1", "1", "1", 1]], "malformed kline"),
    ]:
        provider = BinanceSpotProvider("https://data-api.binance.vision", transport=mock(payload))
        try:
            with pytest.raises(ProviderError, match=message):
                await provider.fetch_candles("XRP_USDT", "1h", 1)
        finally:
            await provider.aclose()


@pytest.mark.asyncio
async def test_binance_skips_open_future_candle() -> None:
    now = datetime.now(UTC)
    payload = [[int(now.timestamp() * 1000), "1", "1.1", "0.9", "1", "1", int((now + timedelta(hours=1)).timestamp() * 1000)]]
    provider = BinanceSpotProvider("https://data-api.binance.vision", transport=mock(payload))
    try:
        assert await provider.fetch_candles("XRP_USDT", "1h", 1) == []
        assert provider.health_path() == "/api/v3/ping"
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_coinbase_rejects_wrong_root_malformed_and_invalid_numeric() -> None:
    payloads = [
        ({"bad": True}, "unexpected payload"),
        ([[1, 2]], "malformed candle"),
        ([[0, 0.9, 1.1, "bad", 1.0, 1]], "malformed candle"),
    ]
    for payload, message in payloads:
        provider = CoinbaseExchangeProvider("https://api.exchange.coinbase.com", transport=mock(payload))
        try:
            with pytest.raises(ProviderError, match=message):
                await provider.fetch_candles("XRP_USD", "1h", 1)
        finally:
            await provider.aclose()


@pytest.mark.asyncio
async def test_coinbase_skips_future_candle_and_health_path() -> None:
    future = datetime.now(UTC) + timedelta(hours=1)
    provider = CoinbaseExchangeProvider(
        "https://api.exchange.coinbase.com",
        transport=mock([[int(future.timestamp()), 0.9, 1.1, 1.0, 1.0, 1.0]]),
    )
    try:
        assert await provider.fetch_candles("XRP_USD", "1h", 1) == []
        assert provider.health_path() == "/time"
    finally:
        await provider.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "unexpected payload"),
        ({"error": ["bad"], "result": {}}, "API error"),
        ({"error": [], "result": []}, "malformed result"),
        ({"error": [], "result": {"A": [], "B": [], "last": 1}}, "ambiguous"),
        ({"error": [], "result": {"A": "bad", "last": 1}}, "ambiguous"),
        ({"error": [], "result": {"A": [[1, 2]], "last": 1}}, "malformed candle"),
        ({"error": [], "result": {"A": [[0, "bad", "1", "1", "1", "1", "1"]], "last": 1}}, "malformed candle"),
    ],
)
async def test_kraken_rejects_malformed_payloads(payload: object, message: str) -> None:
    provider = KrakenSpotProvider("https://api.kraken.com", transport=mock(payload))
    try:
        with pytest.raises(ProviderError, match=message):
            await provider.fetch_candles("XRP_USD", "1h", 1)
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_kraken_skips_future_candle_and_health_path() -> None:
    future = datetime.now(UTC) + timedelta(hours=1)
    payload = {"error": [], "result": {"A": [[int(future.timestamp()), "1", "1.1", "0.9", "1", "1", "1"]], "last": 0}}
    provider = KrakenSpotProvider("https://api.kraken.com", transport=mock(payload))
    try:
        assert await provider.fetch_candles("XRP_USD", "1h", 1) == []
        assert provider.health_path() == "/0/public/Time"
    finally:
        await provider.aclose()


def test_fred_requires_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        FredProvider("")


@pytest.mark.asyncio
async def test_fred_rejects_missing_series_wrong_root_and_malformed_observation() -> None:
    item = FredProvider("x", transport=mock({}))
    try:
        with pytest.raises(ProviderError, match="series_id"):
            await item.fetch_series("")
        assert item.health_path() == "/fred/series"
        with pytest.raises(ProviderError, match="economic observations"):
            await item.fetch_candles("X", "1d")
    finally:
        await item.aclose()

    wrong = FredProvider("x", transport=mock([]))
    try:
        with pytest.raises(ProviderError, match="unexpected payload"):
            await wrong.fetch_series("DGS10")
    finally:
        await wrong.aclose()

    malformed = FredProvider("x", transport=mock({"observations": [{"date": "bad", "value": "x"}]}))
    try:
        with pytest.raises(ProviderError, match="malformed observation"):
            await malformed.fetch_series("DGS10")
    finally:
        await malformed.aclose()


@pytest.mark.asyncio
async def test_fred_skips_missing_values_and_defaults_realtime_start() -> None:
    payload = {"observations": [
        {"date": "2020-01-01", "value": "."},
        {"date": "2020-01-02", "value": None},
        {"date": "2020-01-03", "value": "4.0"},
    ]}
    item = FredProvider("x", transport=mock(payload))
    try:
        result = await item.fetch_series("DGS10", start="2020-01-01")
    finally:
        await item.aclose()
    assert len(result) == 1
    assert result[0].observed_at.date().isoformat() == "2020-01-03"
    assert result[0].available_at == result[0].observed_at


@pytest.mark.asyncio
async def test_xrpl_rejects_malformed_roots_rpc_errors_and_bad_server_info() -> None:
    cases = [
        ([], "unexpected JSON root"),
        ({"result": []}, "unexpected result payload"),
        ({"result": {"status": "error"}}, "RPC error"),
    ]
    for payload, message in cases:
        item = XRPLProvider("https://s1.ripple.com:51234", transport=mock(payload))
        try:
            with pytest.raises(ProviderError, match=message):
                await item.rpc("server_info")
        finally:
            await item.aclose()

    item = XRPLProvider("https://s1.ripple.com:51234", transport=mock({"result": {"status": "success", "info": []}}))
    try:
        with pytest.raises(ProviderError, match="server_info payload is malformed"):
            await item.server_metrics()
    finally:
        await item.aclose()


@pytest.mark.asyncio
async def test_xrpl_health_ok_down_and_fetch_candles_blocked() -> None:
    ok = XRPLProvider("https://s1.ripple.com:51234", transport=mock({"result": {"info": {}}}))
    try:
        health = await ok.health()
        assert health.status == "ok"
        with pytest.raises(ProviderError, match="not exchange OHLC"):
            await ok.fetch_candles("XRP", "1h")
    finally:
        await ok.aclose()

    down = XRPLProvider("https://s1.ripple.com:51234", max_attempts=1, transport=mock({"error": True}, status=503))
    try:
        health = await down.health()
        assert health.status == "down"
        assert health.error
    finally:
        await down.aclose()


@pytest.mark.asyncio
async def test_xrpl_health_rejects_unexpected_health_payload() -> None:
    item = XRPLProvider("https://s1.ripple.com:51234", transport=mock([]))
    try:
        health = await item.health()
        assert health.status == "down"
        assert health.error and "unexpected health payload" in health.error
    finally:
        await item.aclose()


@pytest.mark.asyncio
async def test_xrpl_server_metrics_tolerates_non_mapping_validated_ledger() -> None:
    payload = {"result": {"status": "success", "info": {"validated_ledger": [], "load_factor": 1, "peers": 2}}}
    item = XRPLProvider("https://s1.ripple.com:51234", transport=mock(payload))
    try:
        metrics = await item.server_metrics()
    finally:
        await item.aclose()
    values = {row.metric: row.value for row in metrics}
    assert values["validated_ledger_age"] == 0
