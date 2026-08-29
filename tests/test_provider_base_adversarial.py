from __future__ import annotations

import socket
from typing import Any

import httpx
import pytest

from xrp_regime_engine.models import Candle
from xrp_regime_engine.providers.base import MarketDataProvider, ProviderError, RetryableProviderError

pytestmark = [pytest.mark.contract, pytest.mark.security]


class StubProvider(MarketDataProvider):
    name = "stub"
    allowed_hosts = frozenset({"api.test.invalid"})
    allowed_methods = frozenset({"GET", "POST"})

    async def fetch_candles(self, asset: str, interval: str, limit: int = 300) -> list[Candle]:
        return []


class LiteralProvider(MarketDataProvider):
    name = "literal"
    allowed_hosts = frozenset()

    async def fetch_candles(self, asset: str, interval: str, limit: int = 300) -> list[Candle]:
        return []


def provider(handler: Any, **kwargs: Any) -> StubProvider:
    return StubProvider(
        "https://api.test.invalid",
        transport=httpx.MockTransport(handler),
        retry_base_seconds=0,
        **kwargs,
    )


@pytest.mark.parametrize(
    "url",
    [
        "https:///missing-host",
        "https://api.test.invalid?token=x",
        "https://api.test.invalid/#frag",
    ],
)
def test_base_url_rejects_missing_host_query_or_fragment(url: str) -> None:
    with pytest.raises(ValueError):
        StubProvider(url)


def test_public_literal_ip_can_be_used_only_by_unrestricted_provider() -> None:
    item = LiteralProvider(
        "https://8.8.8.8",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    )
    assert item.base_url == "https://8.8.8.8"


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, None), ("bad", None), ("-4", 0.0), ("999", 30.0), ("2.5", 2.5)],
)
def test_retry_after_parser_is_bounded(header: str | None, expected: float | None) -> None:
    headers = {} if header is None else {"retry-after": header}
    response = httpx.Response(429, headers=headers)
    assert StubProvider._retry_after_seconds(response) == expected


@pytest.mark.asyncio
async def test_bounded_body_rejects_invalid_content_length() -> None:
    item = provider(lambda request: httpx.Response(200, content=b"{}", headers={"content-type": "application/json", "content-length": "bad"}), max_response_bytes=10)
    try:
        with pytest.raises(ProviderError, match="invalid content-length"):
            await item._request_json("GET", "/x")
    finally:
        await item.aclose()


@pytest.mark.asyncio
async def test_streamed_body_limit_is_enforced_without_content_length() -> None:
    item = provider(lambda request: httpx.Response(200, content=b"01234567890", headers={"content-type": "application/json"}), max_response_bytes=10)
    try:
        with pytest.raises(ProviderError, match="oversized"):
            await item._request_json("GET", "/x")
    finally:
        await item.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [b"not-json", b"1", b"null", b'"hello"'])
async def test_malformed_or_scalar_json_is_rejected(raw: bytes) -> None:
    item = provider(lambda request: httpx.Response(200, content=raw, headers={"content-type": "application/json"}))
    try:
        with pytest.raises(ProviderError):
            await item._request_json("GET", "/x")
    finally:
        await item.aclose()


@pytest.mark.asyncio
async def test_non_retryable_4xx_stops_after_one_attempt() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403, json={"error": "forbidden"})

    item = provider(handler, max_attempts=5)
    try:
        with pytest.raises(ProviderError, match="HTTP 403"):
            await item._request_json("GET", "/x")
    finally:
        await item.aclose()
    assert calls == 1


@pytest.mark.asyncio
async def test_retryable_5xx_exhausts_bounded_attempts() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "down"})

    item = provider(handler, max_attempts=3)
    try:
        with pytest.raises(ProviderError, match="transient HTTP 503"):
            await item._request_json("GET", "/x")
    finally:
        await item.aclose()
    assert calls == 3


@pytest.mark.asyncio
async def test_transport_failure_is_sanitized_and_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise OSError("secret=SHOULD_NOT_ESCAPE")

    item = provider(handler, max_attempts=2)
    try:
        with pytest.raises(ProviderError) as exc:
            await item._request_json("GET", "/x")
    finally:
        await item.aclose()
    assert calls == 2
    assert "SHOULD_NOT_ESCAPE" not in str(exc.value)
    assert "transport failure" in str(exc.value)


@pytest.mark.asyncio
async def test_context_manager_closes_client() -> None:
    item = provider(lambda request: httpx.Response(200, json={"ok": True}))
    async with item as entered:
        assert entered is item
    assert item._client.is_closed


@pytest.mark.asyncio
async def test_dns_resolution_failures_are_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    item = StubProvider("https://api.test.invalid")
    try:
        monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("dns")))
        with pytest.raises(RetryableProviderError, match="DNS resolution failed"):
            await item._resolve_public_addresses("api.test.invalid")

        monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [])
        with pytest.raises(RetryableProviderError, match="no addresses"):
            await item._resolve_public_addresses("api.test.invalid")

        monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))])
        with pytest.raises(ProviderError, match="non-public"):
            await item._resolve_public_addresses("api.test.invalid")

        monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("not-an-ip", 443))])
        with pytest.raises(ProviderError, match="invalid IP"):
            await item._resolve_public_addresses("api.test.invalid")
    finally:
        await item.aclose()


@pytest.mark.asyncio
async def test_dns_public_results_are_sorted_and_deduplicated(monkeypatch: pytest.MonkeyPatch) -> None:
    item = StubProvider("https://api.test.invalid")
    try:
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *args, **kwargs: [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            ],
        )
        assert await item._resolve_public_addresses("api.test.invalid") == ("1.1.1.1", "8.8.8.8")
    finally:
        await item.aclose()


@pytest.mark.asyncio
async def test_target_url_cannot_escape_allowlisted_host() -> None:
    item = provider(lambda request: httpx.Response(200, json={}))
    try:
        with pytest.raises(ProviderError, match="escaped"):
            item._target_url("/https://evil.invalid")
    finally:
        await item.aclose()


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


@pytest.mark.asyncio
async def test_streamed_body_exceeding_limit_without_content_length_is_rejected() -> None:
    item = provider(lambda request: httpx.Response(200, stream=ChunkStream([b"12345", b"678901"]), headers={"content-type": "application/json"}), max_response_bytes=10)
    try:
        with pytest.raises(ProviderError, match="oversized"):
            await item._request_json("GET", "/stream")
    finally:
        await item.aclose()


@pytest.mark.asyncio
async def test_retry_paths_honor_positive_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(value: float) -> None:
        sleeps.append(value)

    monkeypatch.setattr("xrp_regime_engine.providers.base.asyncio.sleep", fake_sleep)

    calls = 0
    def transient(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"error": "rate"}, headers={"retry-after": "0.01"})
        return httpx.Response(200, json={"ok": True})

    item = StubProvider("https://api.test.invalid", max_attempts=2, retry_base_seconds=0.01, transport=httpx.MockTransport(transient))
    try:
        await item._request_json("GET", "/x")
    finally:
        await item.aclose()
    assert sleeps == [0.01]

    calls = 0
    sleeps.clear()
    def broken(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"ok": True})

    item = StubProvider("https://api.test.invalid", max_attempts=2, retry_base_seconds=0.01, transport=httpx.MockTransport(broken))
    try:
        await item._request_json("GET", "/x")
    finally:
        await item.aclose()
    assert sleeps == [0.01]


@pytest.mark.asyncio
async def test_base_abstract_fetch_body_is_explicitly_not_implemented() -> None:
    item = provider(lambda request: httpx.Response(200, json={}))
    try:
        with pytest.raises(NotImplementedError):
            await MarketDataProvider.fetch_candles(item, "XRP_USD", "1h")
    finally:
        await item.aclose()
