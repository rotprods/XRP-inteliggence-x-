from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import httpx
import pytest

from xrp_regime_engine.models import Candle
from xrp_regime_engine.providers.base import MarketDataProvider, ProviderError, RawJsonEvidence


class StubProvider(MarketDataProvider):
    name = "test_provider"
    allowed_hosts = frozenset({"api.test.invalid"})
    allowed_methods = frozenset({"GET", "POST"})

    async def fetch_candles(self, asset: str, interval: str, limit: int = 300) -> list[Candle]:
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


def test_raw_json_evidence_fails_closed_on_digest_time_and_latency_corruption() -> None:
    raw = b'{"ok":true}'
    digest = hashlib.sha256(raw).hexdigest()

    with pytest.raises(ValueError, match="payload_sha256"):
        RawJsonEvidence(
            payload={"ok": True},
            raw_payload=raw,
            latency_ms=1.0,
            payload_sha256="0" * 64,
            fetched_at=datetime.now(UTC),
        )

    with pytest.raises(ValueError, match="payload does not match raw_payload"):
        RawJsonEvidence(
            payload={"ok": False},
            raw_payload=raw,
            latency_ms=1.0,
            payload_sha256=digest,
            fetched_at=datetime.now(UTC),
        )

    malformed_raw = b"not-json"
    with pytest.raises(ValueError, match="valid JSON"):
        RawJsonEvidence(
            payload={},
            raw_payload=malformed_raw,
            latency_ms=1.0,
            payload_sha256=hashlib.sha256(malformed_raw).hexdigest(),
            fetched_at=datetime.now(UTC),
        )

    scalar_raw = b"42"
    with pytest.raises(ValueError, match="object or array"):
        RawJsonEvidence(
            payload={},
            raw_payload=scalar_raw,
            latency_ms=1.0,
            payload_sha256=hashlib.sha256(scalar_raw).hexdigest(),
            fetched_at=datetime.now(UTC),
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        RawJsonEvidence(
            payload={"ok": True},
            raw_payload=raw,
            latency_ms=1.0,
            payload_sha256=digest,
            fetched_at=datetime.now(),
        )

    with pytest.raises(ValueError, match="latency_ms"):
        RawJsonEvidence(
            payload={"ok": True},
            raw_payload=raw,
            latency_ms=-0.001,
            payload_sha256=digest,
            fetched_at=datetime.now(UTC),
        )

    with pytest.raises(ValueError, match="raw_payload"):
        RawJsonEvidence(
            payload={},
            raw_payload=b"",
            latency_ms=0.0,
            payload_sha256=hashlib.sha256(b"").hexdigest(),
            fetched_at=datetime.now(UTC),
        )


def test_raw_json_evidence_normalizes_fetch_time_to_utc() -> None:
    raw = b'{"ok":true}'
    evidence = RawJsonEvidence(
        payload={"ok": True},
        raw_payload=raw,
        latency_ms=0.0,
        payload_sha256=hashlib.sha256(raw).hexdigest(),
        fetched_at=datetime.now().astimezone(),
    )
    assert evidence.fetched_at.tzinfo is UTC


@pytest.mark.asyncio
async def test_request_hashes_raw_payload_and_reuses_safe_transport() -> None:
    raw = b'{"ok":true}'

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.test.invalid"
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

    provider = StubProvider("https://api.test.invalid", transport=httpx.MockTransport(handler))
    try:
        payload, latency, digest = await provider._request_json("GET", "/health")
    finally:
        await provider.aclose()
    assert payload == {"ok": True}
    assert latency >= 0
    assert digest == hashlib.sha256(raw).hexdigest()


@pytest.mark.asyncio
async def test_request_evidence_preserves_exact_raw_bytes_and_fetch_time_without_repr_leak() -> None:
    raw = b'{"ok":true,"sequence":7}'

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.test.invalid"
        assert request.url.params["symbol"] == "XRPUSD"
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

    provider = StubProvider("https://api.test.invalid", transport=httpx.MockTransport(handler))
    before = datetime.now(UTC)
    try:
        evidence = await provider._request_json_evidence(
            "GET",
            "/history",
            params={"symbol": "XRPUSD"},
        )
    finally:
        after = datetime.now(UTC)
        await provider.aclose()

    assert evidence.payload == {"ok": True, "sequence": 7}
    assert evidence.raw_payload == raw
    assert evidence.payload_sha256 == hashlib.sha256(raw).hexdigest()
    assert evidence.latency_ms >= 0
    assert before <= evidence.fetched_at <= after
    rendered = repr(evidence)
    assert '"ok"' not in rendered
    assert "XRPUSD" not in rendered


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
        raise httpx.ConnectError("failed api_key=SUPER_SECRET", request=request)

    provider = StubProvider(
        "https://api.test.invalid",
        max_attempts=1,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ProviderError) as exc_info:
            await provider._request_json("GET", "/error", params={"api_key": "SUPER_SECRET"})
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
