from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

from xrp_regime_engine.historical_backfill import BackfillWindow
from xrp_regime_engine.historical_spot_adapters import (
    BinanceKlineAdapter,
    CoinbaseCandleAdapter,
    HistoricalHTTPClient,
    historical_allowed_hosts,
)
from xrp_regime_engine.live_provider_plane import ProviderProtocolError, ProviderUnavailable


UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def public_resolver(host: str, port: int) -> tuple[str, ...]:
    del host, port
    return ("8.8.8.8",)


def test_historical_http_client_accepts_list_root_and_retries() -> None:
    attempts = 0
    sleeps: list[float] = []
    ticks = iter((1.0, 1.1, 2.0, 2.2))

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"error": "maintenance"}, request=request)
        return httpx.Response(200, json=[[1, 2, 3]], request=request)

    client = HistoricalHTTPClient(
        allowed_hosts=("api.example.test",),
        max_attempts=2,
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        clock=lambda: BASE,
        monotonic=lambda: next(ticks),
    )
    payload = client.get_json_value("https://api.example.test/history", params={"symbol": "XRP"})
    assert payload.data == [[1, 2, 3]]
    assert payload.attempts == 2
    assert payload.latency_ms == pytest.approx(200.0)
    assert sleeps == [1.0]
    assert "symbol=XRP" in payload.source_url


def test_historical_http_client_rejects_protocol_errors() -> None:
    responses = (
        httpx.Response(302, headers={"location": "https://api.example.test/other"}),
        httpx.Response(200, text="not-json", headers={"content-type": "text/plain"}),
        httpx.Response(200, content=b"", headers={"content-type": "application/json"}),
    )
    for response in responses:
        def handler(request: httpx.Request, response: httpx.Response = response) -> httpx.Response:
            return httpx.Response(
                response.status_code,
                content=response.content,
                headers=response.headers,
                request=request,
            )

        client = HistoricalHTTPClient(
            allowed_hosts=("api.example.test",),
            max_attempts=1,
            resolver=public_resolver,
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(ProviderUnavailable):
            client.get_json_value("https://api.example.test/history")


def test_coinbase_adapter_builds_close_available_candles() -> None:
    first_epoch = int(BASE.timestamp())
    second_epoch = int((BASE + timedelta(hours=1)).timestamp())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.exchange.coinbase.com"
        assert request.url.params["granularity"] == "3600"
        return httpx.Response(
            200,
            json=[
                [second_epoch, "1.0", "1.3", "1.1", "1.2", "100"],
                [first_epoch, "0.9", "1.2", "1.0", "1.1", "90"],
            ],
            request=request,
        )

    client = HistoricalHTTPClient(
        allowed_hosts=("api.exchange.coinbase.com",),
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
        clock=lambda: BASE + timedelta(days=1),
    )
    adapter = CoinbaseCandleAdapter(client, interval_seconds=3600)
    window = BackfillWindow(BASE, BASE + timedelta(hours=2), 3600)
    page = adapter.fetch_page(window, adapter.initial_cursor(window))
    assert page.completed is True
    assert page.next_cursor is None
    assert [record.record_id for record in page.records] == [
        f"XRP-USD:3600:{first_epoch}",
        f"XRP-USD:3600:{second_epoch}",
    ]
    assert page.records[0].available_at == BASE + timedelta(hours=1)
    assert page.records[0].values["quote_asset"] == "USD"
    assert json.loads(page.raw_payload)[0][0] == second_epoch


def test_coinbase_adapter_paginates_large_window() -> None:
    client = HistoricalHTTPClient(
        allowed_hosts=("api.exchange.coinbase.com",),
        resolver=public_resolver,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=[], request=request)
        ),
        clock=lambda: BASE + timedelta(days=30),
    )
    adapter = CoinbaseCandleAdapter(client, interval_seconds=3600)
    window = BackfillWindow(BASE, BASE + timedelta(hours=600), 3600)
    page = adapter.fetch_page(window, adapter.initial_cursor(window))
    assert page.completed is False
    assert page.next_cursor == {"start": (BASE + timedelta(hours=300)).isoformat()}


def test_binance_adapter_builds_usdt_candles_available_after_close() -> None:
    open_ms = int(BASE.timestamp() * 1000)
    close_ms = open_ms + 3_599_999

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.binance.com"
        assert request.url.params["symbol"] == "XRPUSDT"
        assert request.url.params["interval"] == "1h"
        return httpx.Response(
            200,
            json=[
                [
                    open_ms,
                    "1.0",
                    "1.2",
                    "0.9",
                    "1.1",
                    "100",
                    close_ms,
                    "0",
                    1,
                    "0",
                    "0",
                    "0",
                ]
            ],
            request=request,
        )

    client = HistoricalHTTPClient(
        allowed_hosts=("api.binance.com",),
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
        clock=lambda: BASE + timedelta(days=1),
    )
    adapter = BinanceKlineAdapter(client, interval_seconds=3600)
    window = BackfillWindow(BASE, BASE + timedelta(hours=2), 3600)
    page = adapter.fetch_page(window, adapter.initial_cursor(window))
    assert page.completed is True
    assert page.records[0].record_id == f"XRP-USDT:3600:{open_ms}"
    assert page.records[0].available_at == BASE + timedelta(hours=1)
    assert page.records[0].values["quote_asset"] == "USDT"
    assert page.attributes["quality_flags"] == ["STABLECOIN_QUOTE"]


def test_adapters_reject_interval_and_cursor_mismatch() -> None:
    client = HistoricalHTTPClient(
        allowed_hosts=historical_allowed_hosts(),
        resolver=public_resolver,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=[], request=request)
        ),
    )
    with pytest.raises(ValueError, match="unsupported"):
        CoinbaseCandleAdapter(client, interval_seconds=120)
    with pytest.raises(ValueError, match="unsupported"):
        BinanceKlineAdapter(client, interval_seconds=120)
    adapter = CoinbaseCandleAdapter(client, interval_seconds=3600)
    window = BackfillWindow(BASE, BASE + timedelta(hours=2), 3600)
    with pytest.raises(ValueError, match="cursor"):
        adapter.fetch_page(window, {"start": "invalid"})
    with pytest.raises(ValueError, match="interval"):
        adapter.initial_cursor(BackfillWindow(BASE, BASE + timedelta(hours=2), 300))


def test_coinbase_and_binance_payload_validation() -> None:
    cases = (
        (CoinbaseCandleAdapter, {"unexpected": "object"}, "root must be an array"),
        (CoinbaseCandleAdapter, [[1, 2]], "malformed"),
        (BinanceKlineAdapter, {"unexpected": "object"}, "root must be an array"),
        (BinanceKlineAdapter, [[1, 2]], "malformed"),
    )
    for adapter_type, body, message in cases:
        endpoint_host = (
            "api.exchange.coinbase.com"
            if adapter_type is CoinbaseCandleAdapter
            else "api.binance.com"
        )
        client = HistoricalHTTPClient(
            allowed_hosts=(endpoint_host,),
            resolver=public_resolver,
            transport=httpx.MockTransport(
                lambda request, body=body: httpx.Response(200, json=body, request=request)
            ),
            clock=lambda: BASE + timedelta(days=1),
        )
        adapter = adapter_type(client, interval_seconds=3600)
        window = BackfillWindow(BASE, BASE + timedelta(hours=2), 3600)
        with pytest.raises(ProviderProtocolError, match=message):
            adapter.fetch_page(window, adapter.initial_cursor(window))
