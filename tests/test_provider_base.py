from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from xrp_regime_engine.models import Candle
from xrp_regime_engine.providers.base import MarketDataProvider, ProviderError


class StubProvider(MarketDataProvider):
    name = "test_provider"
    allowed_hosts = frozenset({"api.test.invalid"})
    allowed_methods = frozenset({"GET", "POST"})

    async def fetch_candles(
        self, asset: str, interval: str, limit: int = 300
    ) -> list[Candle]:
        return []


@pytest.mark.parametrize(
    "url",
    [
        "http://api.test.invalid",
        "https://user:password@api.test.invalid",
        "https://127.0.0.1",
        "https://169.254.169.254",
        "https://evil.invalid",
    ],
)
def test_base_url_validation_is_fail_closed(url: str) -> None:
    with pytest.raises(ValueError):
        StubProvider(url)


@pytest.mark.asyncio
async def test_request_hashes_raw_payload_and_reuses_safe_transport() -> None:
    raw = b'{"ok":true}'

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.test.invalid"
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

    provider = StubProvider(
        "https://api.test.invalid", transport=httpx.MockTransport(handler)
    )
    try:
        payload, latency, digest = await provider._request_json("GET", "/health")
    finally:
        await provider.aclose()
    assert payload == {"ok": True}
    assert latency >= 0
    assert digest == hashlib.sha256(raw).hexdigest()


@pytest.mark.asyncio
async def test_transient_429_retries_with_bounded_attempts() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                json={"error": "rate limited"},
                headers={"content-type": "application/json", "retry-after": "0"},
            )
        return httpx.Response(200, json={"ok": True})

    provider = StubProvider(
        "https://api.test.invalid",
        max_attempts=2,
        retry_base_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        payload, _, _ = await provider._request_json("GET", "/retry")
    finally:
        await provider.aclose()
    assert payload == {"ok": True}
    assert calls == 2


@pytest.mark.asyncio
async def test_oversized_and_non_json_responses_are_rejected() -> None:
    responses = iter(
        [
            httpx.Response(
                200,
                content=b"{}",
                headers={"content-type": "application/json", "content-length": "999"},
            ),
            httpx.Response(200, content=b"hello", headers={"content-type": "text/plain"}),
        ]
    )

    provider = StubProvider(
        "https://api.test.invalid",
        max_attempts=1,
        max_response_bytes=10,
        transport=httpx.MockTransport(lambda request: next(responses)),
    )
    try:
        with pytest.raises(ProviderError, match="oversized"):
            await provider._request_json("GET", "/large")
        with pytest.raises(ProviderError, match="content type"):
            await provider._request_json("GET", "/text")
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_transport_errors_do_not_leak_query_secrets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "failed api_key=SUPER_SECRET", request=request
        )

    provider = StubProvider(
        "https://api.test.invalid",
        max_attempts=1,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ProviderError) as exc_info:
            await provider._request_json(
                "GET", "/error", params={"api_key": "SUPER_SECRET"}
            )
    finally:
        await provider.aclose()
    assert "SUPER_SECRET" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_method_and_path_cannot_escape_policy() -> None:
    provider = StubProvider(
        "https://api.test.invalid",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    )
    try:
        with pytest.raises(ProviderError, match="not allowed"):
            await provider._request_json("DELETE", "/orders")
        with pytest.raises(ProviderError, match="paths must be absolute"):
            await provider._request_json("GET", "https://evil.invalid/data")
    finally:
        await provider.aclose()

@pytest.mark.asyncio
async def test_health_reports_ok_and_down_without_raising() -> None:
    responses = iter(
        [
            httpx.Response(200, json={"status": "ok"}),
            httpx.Response(503, json={"error": "down"}),
        ]
    )
    provider = StubProvider(
        "https://api.test.invalid",
        max_attempts=1,
        transport=httpx.MockTransport(lambda request: next(responses)),
    )
    try:
        healthy = await provider.health()
        down = await provider.health()
    finally:
        await provider.aclose()
    assert healthy.status == "ok"
    assert healthy.freshness_score == 1.0
    assert down.status == "down"
    assert down.error is not None


def test_provider_configuration_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="timeout"):
        StubProvider("https://api.test.invalid", timeout=0)
    with pytest.raises(ValueError, match="max_attempts"):
        StubProvider("https://api.test.invalid", max_attempts=0)
    with pytest.raises(ValueError, match="max_response_bytes"):
        StubProvider("https://api.test.invalid", max_response_bytes=0)
    with pytest.raises(ValueError, match="retry_base_seconds"):
        StubProvider("https://api.test.invalid", retry_base_seconds=-1)
