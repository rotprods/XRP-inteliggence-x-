from __future__ import annotations

import hashlib
import json
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


def _request_fingerprint(
    *,
    method: str = "GET",
    canonical_uri: str = "https://api.test.invalid/history",
    body_sha256: str | None = None,
) -> str:
    material = json.dumps(
        {
            "method": method,
            "canonical_uri": canonical_uri,
            "body_sha256": body_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(material).hexdigest()


def _evidence(
    *,
    payload: dict[str, object] | list[object] | None = None,
    raw: bytes = b'{"ok":true}',
    latency_ms: float = 1.0,
    fetched_at: datetime | None = None,
    request_method: str = "GET",
    canonical_uri: str = "https://api.test.invalid/history",
    request_body_sha256: str | None = None,
    request_fingerprint: str | None = None,
) -> RawJsonEvidence:
    actual_payload: dict[str, object] | list[object] = {"ok": True} if payload is None else payload
    fingerprint = request_fingerprint or _request_fingerprint(
        method=request_method,
        canonical_uri=canonical_uri,
        body_sha256=request_body_sha256,
    )
    return RawJsonEvidence(
        payload=actual_payload,
        raw_payload=raw,
        latency_ms=latency_ms,
        payload_sha256=hashlib.sha256(raw).hexdigest(),
        fetched_at=fetched_at or datetime.now(UTC),
        request_method=request_method,
        canonical_uri=canonical_uri,
        request_body_sha256=request_body_sha256,
        request_fingerprint=fingerprint,
    )


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


def test_raw_json_evidence_fails_closed_on_digest_time_latency_and_request_corruption() -> None:
    raw = b'{"ok":true}'
    digest = hashlib.sha256(raw).hexdigest()
    fingerprint = _request_fingerprint()

    with pytest.raises(ValueError, match="payload_sha256"):
        RawJsonEvidence(
            payload={"ok": True},
            raw_payload=raw,
            latency_ms=1.0,
            payload_sha256="0" * 64,
            fetched_at=datetime.now(UTC),
            request_method="GET",
            canonical_uri="https://api.test.invalid/history",
            request_fingerprint=fingerprint,
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        RawJsonEvidence(
            payload={"ok": True},
            raw_payload=raw,
            latency_ms=1.0,
            payload_sha256=digest,
            fetched_at=datetime.now(),
            request_method="GET",
            canonical_uri="https://api.test.invalid/history",
            request_fingerprint=fingerprint,
        )

    for bad_latency in (-0.001, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="latency_ms"):
            RawJsonEvidence(
                payload={"ok": True},
                raw_payload=raw,
                latency_ms=bad_latency,
                payload_sha256=digest,
                fetched_at=datetime.now(UTC),
                request_method="GET",
                canonical_uri="https://api.test.invalid/history",
                request_fingerprint=fingerprint,
            )

    with pytest.raises(ValueError, match="raw_payload"):
        RawJsonEvidence(
            payload={},
            raw_payload=b"",
            latency_ms=0.0,
            payload_sha256=hashlib.sha256(b"").hexdigest(),
            fetched_at=datetime.now(UTC),
            request_method="GET",
            canonical_uri="https://api.test.invalid/history",
            request_fingerprint=fingerprint,
        )

    with pytest.raises(ValueError, match="request_fingerprint"):
        RawJsonEvidence(
            payload={"ok": True},
            raw_payload=raw,
            latency_ms=1.0,
            payload_sha256=digest,
            fetched_at=datetime.now(UTC),
            request_method="GET",
            canonical_uri="https://api.test.invalid/history",
            request_fingerprint="0" * 64,
        )


def test_raw_json_evidence_binds_parsed_payload_to_exact_raw_json() -> None:
    with pytest.raises(ValueError, match="payload does not match"):
        _evidence(payload={"ok": False})

    duplicate_key_raw = b'{"ok":true,"ok":false}'
    with pytest.raises(ValueError, match="duplicate-key-free JSON"):
        _evidence(payload={"ok": False}, raw=duplicate_key_raw)

    scalar_raw = b"7"
    with pytest.raises(ValueError, match="object or array"):
        _evidence(payload=[], raw=scalar_raw)

    nonfinite_raw = b'{"value":NaN}'
    with pytest.raises(ValueError, match="duplicate-key-free JSON"):
        _evidence(payload={"value": 0}, raw=nonfinite_raw)


def test_raw_json_evidence_normalizes_fetch_time_to_utc() -> None:
    evidence = _evidence(fetched_at=datetime.now().astimezone(), latency_ms=0.0)
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
async def test_request_evidence_preserves_exact_raw_bytes_fetch_time_and_request_identity() -> None:
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
    assert evidence.request_method == "GET"
    assert evidence.canonical_uri == "https://api.test.invalid/history?symbol=XRPUSD"
    assert evidence.request_body_sha256 is None
    assert evidence.request_fingerprint == _request_fingerprint(
        canonical_uri="https://api.test.invalid/history?symbol=XRPUSD"
    )
    rendered = repr(evidence)
    assert '"ok"' not in rendered
    assert "XRPUSD" not in rendered


@pytest.mark.asyncio
async def test_request_identity_is_stable_redacted_and_semantics_sensitive() -> None:
    raw = b'{"ok":true}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

    provider = StubProvider("https://api.test.invalid", transport=httpx.MockTransport(handler))
    try:
        first = await provider._request_json_evidence(
            "GET",
            "/history",
            params={"symbol": "XRPUSD", "limit": 5, "api_key": "SUPER_SECRET"},
        )
        reordered = await provider._request_json_evidence(
            "GET",
            "/history",
            params={"api_key": "DIFFERENT_SECRET", "limit": 5, "symbol": "XRPUSD"},
        )
        changed = await provider._request_json_evidence(
            "GET",
            "/history",
            params={"symbol": "BTCUSD", "limit": 5, "api_key": "SUPER_SECRET"},
        )
    finally:
        await provider.aclose()

    assert first.canonical_uri == reordered.canonical_uri
    assert first.request_fingerprint == reordered.request_fingerprint
    assert "SUPER_SECRET" not in first.canonical_uri
    assert "DIFFERENT_SECRET" not in reordered.canonical_uri
    assert "%3Credacted%3E" in first.canonical_uri
    assert changed.request_fingerprint != first.request_fingerprint


@pytest.mark.asyncio
async def test_post_request_identity_binds_canonical_json_body_without_exposing_body() -> None:
    raw = b'{"result":"ok"}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

    provider = StubProvider("https://api.test.invalid", transport=httpx.MockTransport(handler))
    body = {"method": "ledger", "params": [{"ledger_index": "validated"}]}
    expected_body_hash = hashlib.sha256(
        json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    try:
        evidence = await provider._request_json_evidence("POST", "/", json_body=body)
    finally:
        await provider.aclose()

    assert evidence.request_method == "POST"
    assert evidence.request_body_sha256 == expected_body_hash
    assert evidence.request_fingerprint == _request_fingerprint(
        method="POST",
        canonical_uri="https://api.test.invalid/",
        body_sha256=expected_body_hash,
    )
    rendered = repr(evidence)
    assert "ledger_index" not in rendered
    assert "validated" not in rendered


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
