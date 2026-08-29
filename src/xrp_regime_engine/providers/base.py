from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import socket
import time
from abc import ABC, abstractmethod
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
        addresses = tuple(sorted({item[4][0] for item in results}))
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

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[Any, float, str]:
        method = method.upper()
        if method not in self.allowed_methods:
            raise ProviderError(f"HTTP method {method} is not allowed for {self.name}")
        target = self._target_url(path)
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

                try:
                    payload = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ProviderError(f"malformed JSON from {self.name}") from exc
                if not isinstance(payload, (dict, list)):
                    raise ProviderError(f"unexpected JSON root from {self.name}")
                digest = hashlib.sha256(raw).hexdigest()
                return payload, latency, digest
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
