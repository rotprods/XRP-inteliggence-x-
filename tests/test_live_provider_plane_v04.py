from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import socket

import httpx
import pytest

from xrp_regime_engine.live_provider_plane import (
    BinanceXRPUSDTAdapter,
    CircuitBreaker,
    CircuitState,
    CoinbaseXRPUSDAdapter,
    KrakenXRPUSDAdapter,
    KuCoinXRPUSDTAdapter,
    LiveProviderPlane,
    ProviderProtocolError,
    ProviderUnavailable,
    ReadOnlyJSONClient,
    validate_public_https_url,
)


UTC = timezone.utc


def public_resolver(host: str, port: int) -> tuple[str, ...]:
    del host, port
    return ("8.8.8.8",)


def private_resolver(host: str, port: int) -> tuple[str, ...]:
    del host, port
    return ("127.0.0.1",)


def test_url_validation_is_https_allowlisted_and_ssrf_safe() -> None:
    assert (
        validate_public_https_url(
            "https://api.example.test/ticker",
            allowed_hosts=("api.example.test",),
            resolver=public_resolver,
        )
        == "https://api.example.test/ticker"
    )
    with pytest.raises(ValueError, match="HTTPS"):
        validate_public_https_url(
            "http://api.example.test/ticker",
            allowed_hosts=("api.example.test",),
            resolver=public_resolver,
        )
    with pytest.raises(ValueError, match="not allowlisted"):
        validate_public_https_url(
            "https://other.example.test/ticker",
            allowed_hosts=("api.example.test",),
            resolver=public_resolver,
        )
    with pytest.raises(ValueError, match="forbidden address"):
        validate_public_https_url(
            "https://api.example.test/ticker",
            allowed_hosts=("api.example.test",),
            resolver=private_resolver,
        )
    with pytest.raises(ValueError, match="credentials"):
        validate_public_https_url(
            "https://user:pass@api.example.test/ticker",
            allowed_hosts=("api.example.test",),
            resolver=public_resolver,
        )


def test_circuit_breaker_opens_and_recovers() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=60)
    breaker.record_failure(now=now)
    assert breaker.state is CircuitState.OPEN
    with pytest.raises(ProviderUnavailable, match="circuit is open"):
        breaker.before_request(now=now + timedelta(seconds=30))
    breaker.before_request(now=now + timedelta(seconds=61))
    assert breaker.state is CircuitState.HALF_OPEN
    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED
    assert breaker.consecutive_failures == 0


def test_client_retries_transient_status_and_hashes_payload() -> None:
    attempts = 0
    sleeps: list[float] = []
    ticks = iter((10.0, 10.1, 11.0, 11.2))
    now = datetime(2026, 1, 1, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"error": "maintenance"}, request=request)
        return httpx.Response(200, json={"price": "1.25"}, request=request)

    client = ReadOnlyJSONClient(
        allowed_hosts=("api.example.test",),
        max_attempts=2,
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        clock=lambda: now,
        monotonic=lambda: next(ticks),
    )
    result = client.get_json("https://api.example.test/ticker")
    assert result.attempts == 2
    assert result.data == {"price": "1.25"}
    assert result.payload_sha256
    assert result.latency_ms == pytest.approx(200.0)
    assert sleeps == [1.0]


def test_client_rejects_redirect_non_json_and_oversized_payload() -> None:
    cases = (
        httpx.Response(302, headers={"location": "https://api.example.test/other"}),
        httpx.Response(200, text="not json", headers={"content-type": "text/plain"}),
        httpx.Response(200, content=b"{\"value\":\"123456789\"}", headers={"content-type": "application/json"}),
    )
    for index, response in enumerate(cases):
        response.request = httpx.Request("GET", "https://api.example.test/ticker")
        client = ReadOnlyJSONClient(
            allowed_hosts=("api.example.test",),
            max_attempts=1,
            max_payload_bytes=10 if index == 2 else 1_000,
            resolver=public_resolver,
            transport=httpx.MockTransport(lambda request, response=response: response),
        )
        with pytest.raises(ProviderUnavailable):
            client.get_json("https://api.example.test/ticker")


def test_coinbase_adapter_parses_price_and_timestamp() -> None:
    adapter = CoinbaseXRPUSDAdapter()
    payload = {"price": "1.2345", "time": "2026-01-01T12:00:00Z"}
    assert adapter.parse_price(payload) == Decimal("1.2345")
    assert adapter.observed_at(payload, fallback=datetime(2025, 1, 1, tzinfo=UTC)) == datetime(
        2026, 1, 1, 12, tzinfo=UTC
    )
    with pytest.raises(ProviderProtocolError):
        adapter.parse_price({})


def test_kraken_adapter_parses_dynamic_result_key() -> None:
    adapter = KrakenXRPUSDAdapter()
    payload = {"error": [], "result": {"XXRPZUSD": {"c": ["1.111", "42"]}}}
    assert adapter.parse_price(payload) == Decimal("1.111")
    with pytest.raises(ProviderProtocolError):
        adapter.parse_price({"error": ["service unavailable"], "result": {}})


def test_kucoin_adapter_preserves_usdt_quote_and_time() -> None:
    adapter = KuCoinXRPUSDTAdapter()
    payload = {"code": "200000", "data": {"price": "1.222", "time": 1767268800000}}
    assert adapter.parse_price(payload) == Decimal("1.222")
    assert adapter.quote_asset == "USDT"
    assert "STABLECOIN_QUOTE" in adapter.quality_flags
    assert adapter.observed_at(payload, fallback=datetime(2025, 1, 1, tzinfo=UTC)).tzinfo is UTC


def test_binance_adapter_preserves_usdt_quote() -> None:
    adapter = BinanceXRPUSDTAdapter()
    assert adapter.parse_price({"symbol": "XRPUSDT", "price": "1.333"}) == Decimal("1.333")
    assert adapter.quote_asset == "USDT"


def test_provider_plane_isolates_provider_failures_and_never_mixes_quote_currencies() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.exchange.coinbase.com":
            return httpx.Response(
                200,
                json={"price": "1.20", "time": now.isoformat()},
                request=request,
            )
        return httpx.Response(500, json={"error": "maintenance"}, request=request)

    client = ReadOnlyJSONClient(
        allowed_hosts=("api.exchange.coinbase.com", "api.binance.com"),
        max_attempts=1,
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
        clock=lambda: now,
    )
    plane = LiveProviderPlane(client, (CoinbaseXRPUSDAdapter(), BinanceXRPUSDTAdapter()))
    probes = plane.probe()
    assert [probe.status for probe in probes] == ["HEALTHY", "FAILED"]
    quotes = plane.healthy_quotes(probes)
    assert len(quotes) == 1
    assert quotes[0].symbol == "XRP-USD"


def test_default_dns_resolver_contract_is_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.4.4", 443)),
        ],
    )
    assert validate_public_https_url(
        "https://api.example.test/ticker",
        allowed_hosts=("api.example.test",),
    )
