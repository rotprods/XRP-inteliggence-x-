from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import math
import socket
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, ClassVar
from urllib.parse import urlsplit

import httpx

from xrp_regime_engine.models import Candle, ProviderHealth


class ProviderError(RuntimeError):
    """Provider failure safe to expose without credentials or raw payloads."""


class RetryableProviderError(ProviderError):
    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _decode_json_root(raw_payload: bytes) -> dict[str, Any] | list[Any]:
    try:
        payload = json.loads(
            raw_payload,
            object_pairs_hook=_reject_duplicate_json_pairs,
            parse_constant=_reject_nonfinite_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("raw_payload must contain valid duplicate-key-free JSON") from exc
    if not isinstance(payload, (dict, list)):
        raise ValueError("raw_payload JSON root must be an object or array")
    return payload


def _is_sensitive_query_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(
        token in normalized
        for token in ("api_key", "apikey", "token", "secret", "signature", "password", "credential")
    )


def _request_identity(
    method: str,
    target: httpx.URL,
    *,
    params: dict[str, Any] | None,
    json_body: dict[str, Any] | None,
) -> tuple[str, str | None, str]:
    query_items = list(target.params.multi_items())
    if params:
        query_items.extend(httpx.QueryParams(params).multi_items())
    sanitized_items = sorted(
        (
            key,
            "<redacted>" if _is_sensitive_query_key(key) else value,
        )
        for key, value in query_items
    )
    canonical_target = target.copy_with(query=None)
    if sanitized_items:
        canonical_target = canonical_target.copy_merge_params(sanitized_items)
    canonical_uri = str(canonical_target)

    body_sha256: str | None = None
    if json_body is not None:
        try:
            body_material = json.dumps(
                json_body,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
        except (TypeError, ValueError) as exc:
            raise ProviderError("request body is not canonical JSON") from exc
        body_sha256 = hashlib.sha256(body_material).hexdigest()

    request_material = json.dumps(
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
    return canonical_uri, body_sha256, hashlib.sha256(request_material).hexdigest()


@dataclass(frozen=True, slots=True)
class RawJsonEvidence:
    """Exact bounded public-response evidence captured at the transport boundary.

    Parsed/raw provider payloads and sanitized request identity are excluded from ``repr`` so callers
    do not accidentally copy provider content or query material into logs. The object is internally
    self-validating: parsed content must equal the exact raw JSON bytes, and the request fingerprint
    must match method + sanitized canonical URI + canonical request-body digest.
    """

    payload: dict[str, Any] | list[Any] = field(repr=False)
    raw_payload: bytes = field(repr=False)
    latency_ms: float
    payload_sha256: str
    fetched_at: datetime
    request_method: str
    canonical_uri: str = field(repr=False)
    request_body_sha256: str | None = field(default=None, repr=False)
    request_fingerprint: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not math.isfinite(self.latency_ms) or self.latency_ms < 0:
            raise ValueError("latency_ms must be finite and non-negative")
        if not self.raw_payload:
            raise ValueError("raw_payload cannot be empty")
        expected_digest = hashlib.sha256(self.raw_payload).hexdigest()
        if self.payload_sha256 != expected_digest:
            raise ValueError("payload_sha256 does not match raw_payload")
        decoded = _decode_json_root(self.raw_payload)
        if decoded != self.payload:
            raise ValueError("payload does not match raw_payload JSON")
        if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() is None:
            raise ValueError("fetched_at must be timezone-aware")
        object.__setattr__(self, "fetched_at", self.fetched_at.astimezone(UTC))

        method = self.request_method.upper().strip()
        if not method:
            raise ValueError("request_method is required")
        object.__setattr__(self, "request_method", method)

        parsed_uri = urlsplit(self.canonical_uri)
        if parsed_uri.scheme != "https" or not parsed_uri.hostname:
            raise ValueError("canonical_uri must be an absolute HTTPS URI")
        if parsed_uri.username or parsed_uri.password or parsed_uri.fragment:
            raise ValueError("canonical_uri cannot contain credentials or a fragment")

        if self.request_body_sha256 is not None:
            if len(self.request_body_sha256) != 64 or any(
                char not in "0123456789abcdef" for char in self.request_body_sha256
            ):
                raise ValueError("request_body_sha256 must be a lowercase SHA-256 digest")
        material = json.dumps(
            {
                "method": method,
                "canonical_uri": self.canonical_uri,
                "body_sha256": self.request_body_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        expected_request_fingerprint = hashlib.sha256(material).hexdigest()
        if self.request_fingerprint != expected_request_fingerprint:
            raise ValueError("request_fingerprint does not match request identity")


class MarketDataProvider(ABC):
    name: str
    allowed_hosts: ClassVar[frozenset[str]] = frozenset()
    allowed_methods: ClassVar[frozenset[str]] = frozenset({"GET"})

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        max_attempts: int = 3,
        *,
        max_response_bytes: int = 2_000_000,
        retry_base_seconds: float = 0.2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        if retry_base_seconds < 0:
            raise ValueError("retry_base_seconds cannot be negative")

        self.base_url = self._validate_base_url(base_url)
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.max_response_bytes = max_response_bytes
        self.retry_base_seconds = retry_base_seconds
        self._transport_injected = transport is not None
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers={"User-Agent": "xrp-regime-engine/0.2"},
        )

    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https":
            raise ValueError("provider base URL must use HTTPS")
        if not parsed.hostname:
            raise ValueError("provider base URL must include a hostname")
        if parsed.username or parsed.password:
            raise ValueError("provider base URL cannot contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("provider base URL cannot contain query or fragment data")
        host = parsed.hostname.lower().rstrip(".")
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None and not literal.is_global:
            raise ValueError("provider base URL cannot target a non-public IP address")
        if cls.allowed_hosts and host not in cls.allowed_hosts:
            raise ValueError(f"host {host!r} is not allowlisted for {cls.__name__}")
        path = parsed.path.rstrip("/")
        authority = host if parsed.port is None else f"{host}:{parsed.port}"
        return f"https://{authority}{path}"

    async def __aenter__(self) -> MarketDataProvider:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _resolve_public_addresses(self, hostname: str) -> tuple[str, ...]:
        if self._transport_injected:
            return ("203.0.113.1",)
        try:
            results = await asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                None,
                socket.AF_UNSPEC,
                socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise RetryableProviderError("DNS resolution failed") from exc
        addresses = tuple(sorted({str(item[4][0]) for item in results}))
        if not addresses:
            raise RetryableProviderError("DNS resolution returned no addresses")
        for address in addresses:
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError as exc:
                raise ProviderError("DNS returned an invalid IP address") from exc
            if not parsed.is_global:
                raise ProviderError("DNS resolved provider host to a non-public address")
        return addresses

    def _target_url(self, path: str) -> httpx.URL:
        if not path.startswith("/"):
            raise ProviderError("provider paths must be absolute within the allowlisted host")
        target = self._client.base_url.join(path.lstrip("/"))
        base = urlsplit(self.base_url)
        if target.scheme != "https" or target.host != base.hostname:
            raise ProviderError("request target escaped the allowlisted provider host")
        return target

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        value = response.headers.get("retry-after")
        if value is None:
            return None
        try:
            return max(0.0, min(float(value), 30.0))
        except ValueError:
            return None

    async def _read_bounded_body(self, response: httpx.Response) -> bytes:
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_response_bytes:
                    raise ProviderError(f"oversized response from {self.name}")
            except ValueError:
                raise ProviderError(f"invalid content-length from {self.name}") from None

        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > self.max_response_bytes:
                raise ProviderError(f"oversized response from {self.name}")
        return bytes(body)

    async def _request_json_evidence(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> RawJsonEvidence:
        """Return parsed JSON plus exact bounded response/request provenance evidence.

        The response bytes and parsed payload are bound together, and the evidence also binds the
        response to a sanitized canonical request identity without exposing credential values. The
        method remains protected: provider adapters may consume the evidence, while public callers
        continue using typed provider methods.
        """

        method = method.upper()
        if method not in self.allowed_methods:
            raise ProviderError(f"HTTP method {method} is not allowed for {self.name}")
        target = self._target_url(path)
        canonical_uri, request_body_sha256, request_fingerprint = _request_identity(
            method,
            target,
            params=params,
            json_body=json_body,
        )
        await self._resolve_public_addresses(target.host)

        last_error = "unknown provider failure"
        for attempt in range(1, self.max_attempts + 1):
            started = time.perf_counter()
            try:
                async with self._client.stream(
                    method,
                    target,
                    params=params,
                    json=json_body,
                ) as response:
                    latency = (time.perf_counter() - started) * 1000
                    if response.status_code == 429 or 500 <= response.status_code < 600:
                        raise RetryableProviderError(
                            f"transient HTTP {response.status_code} from {self.name}",
                            retry_after=self._retry_after_seconds(response),
                        )
                    if response.status_code >= 400:
                        raise ProviderError(f"HTTP {response.status_code} from {self.name}")
                    content_type = response.headers.get("content-type", "").lower()
                    if "json" not in content_type:
                        raise ProviderError(f"unexpected content type from {self.name}")
                    raw = await self._read_bounded_body(response)
                    fetched_at = datetime.now(UTC)

                try:
                    payload = _decode_json_root(raw)
                except ValueError as exc:
                    raise ProviderError(f"malformed JSON from {self.name}") from exc
                digest = hashlib.sha256(raw).hexdigest()
                return RawJsonEvidence(
                    payload=payload,
                    raw_payload=raw,
                    latency_ms=latency,
                    payload_sha256=digest,
                    fetched_at=fetched_at,
                    request_method=method,
                    canonical_uri=canonical_uri,
                    request_body_sha256=request_body_sha256,
                    request_fingerprint=request_fingerprint,
                )
            except RetryableProviderError as exc:
                last_error = str(exc)
                if attempt < self.max_attempts:
                    delay = (
                        exc.retry_after
                        if exc.retry_after is not None
                        else self.retry_base_seconds * (2 ** (attempt - 1))
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
            except ProviderError as exc:
                last_error = str(exc)
                break
            except (httpx.HTTPError, OSError, ValueError) as exc:
                # Never propagate raw URLs or query parameters, which may contain keys.
                last_error = f"{type(exc).__name__}: transport failure"
                if attempt < self.max_attempts and self.retry_base_seconds > 0:
                    await asyncio.sleep(self.retry_base_seconds * (2 ** (attempt - 1)))

        raise ProviderError(f"{self.name} request failed: {last_error}")

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[Any, float, str]:
        evidence = await self._request_json_evidence(
            method,
            path,
            params=params,
            json_body=json_body,
        )
        return evidence.payload, evidence.latency_ms, evidence.payload_sha256

    @abstractmethod
    async def fetch_candles(self, asset: str, interval: str, limit: int = 300) -> list[Candle]:
        raise NotImplementedError

    async def health(self) -> ProviderHealth:
        now = datetime.now(UTC)
        try:
            _, latency, _ = await self._request_json("GET", self.health_path())
            return ProviderHealth(
                provider=self.name,
                checked_at=now,
                status="ok",
                latency_ms=latency,
                freshness_score=1.0,
                agreement_score=1.0,
            )
        except ProviderError as exc:
            return ProviderHealth(
                provider=self.name,
                checked_at=now,
                status="down",
                freshness_score=0.0,
                agreement_score=0.0,
                error=str(exc),
            )

    def health_path(self) -> str:
        return "/"
