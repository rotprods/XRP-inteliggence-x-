from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import ipaddress
import json
import socket
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlencode, urlparse

import httpx


class ProviderError(RuntimeError):
    """Base error for the read-only provider plane."""


class ProviderUnavailable(ProviderError):
    """Provider could not be reached or its circuit is open."""


class ProviderProtocolError(ProviderError):
    """Provider returned a payload that violates the expected contract."""


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def require_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def default_resolver(host: str, port: int) -> tuple[str, ...]:
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return tuple(sorted({entry[4][0] for entry in addresses}))


def validate_public_https_url(
    url: str,
    *,
    allowed_hosts: Iterable[str],
    resolver: Callable[[str, int], Sequence[str]] = default_resolver,
) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("provider URL must use HTTPS")
    if not parsed.hostname:
        raise ValueError("provider URL must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("credentials are forbidden in provider URLs")
    if parsed.port not in {None, 443}:
        raise ValueError("provider URL may only use the standard HTTPS port")

    host = parsed.hostname.lower().rstrip(".")
    allowlist = {item.lower().rstrip(".") for item in allowed_hosts}
    if host not in allowlist:
        raise ValueError(f"provider host is not allowlisted: {host}")

    resolved = tuple(resolver(host, 443))
    if not resolved:
        raise ValueError(f"provider host did not resolve: {host}")
    for raw_address in resolved:
        address = ipaddress.ip_address(raw_address)
        if any(
            (
                address.is_private,
                address.is_loopback,
                address.is_link_local,
                address.is_multicast,
                address.is_reserved,
                address.is_unspecified,
            )
        ):
            raise ValueError(f"provider host resolved to a forbidden address: {address}")
    return url


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 60.0
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    opened_at: datetime | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def before_request(self, *, now: datetime | None = None) -> None:
        current = require_aware_utc(now or utc_now())
        with self._lock:
            if self.state != CircuitState.OPEN:
                return
            assert self.opened_at is not None
            elapsed = (current - self.opened_at).total_seconds()
            if elapsed < self.recovery_timeout_seconds:
                raise ProviderUnavailable("provider circuit is open")
            self.state = CircuitState.HALF_OPEN

    def record_success(self) -> None:
        with self._lock:
            self.state = CircuitState.CLOSED
            self.consecutive_failures = 0
            self.opened_at = None

    def record_failure(self, *, now: datetime | None = None) -> None:
        current = require_aware_utc(now or utc_now())
        with self._lock:
            self.consecutive_failures += 1
            if self.state == CircuitState.HALF_OPEN or self.consecutive_failures >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = current


@dataclass(frozen=True, slots=True)
class FetchedJSON:
    url: str
    status_code: int
    received_at: datetime
    latency_ms: float
    payload_sha256: str
    payload_size_bytes: int
    data: Mapping[str, Any]
    attempts: int


class ReadOnlyJSONClient:
    """Small GET-only HTTP client with SSRF, size, retry and circuit gates."""

    def __init__(
        self,
        *,
        allowed_hosts: Iterable[str],
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        max_payload_bytes: int = 2_000_000,
        resolver: Callable[[str, int], Sequence[str]] = default_resolver,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        circuit_breakers: Mapping[str, CircuitBreaker] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if max_payload_bytes <= 0:
            raise ValueError("max_payload_bytes must be positive")
        self.allowed_hosts = tuple(sorted({host.lower().rstrip(".") for host in allowed_hosts}))
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.max_payload_bytes = max_payload_bytes
        self.resolver = resolver
        self.transport = transport
        self.sleep = sleep
        self.clock = clock
        self.monotonic = monotonic
        self.circuit_breakers = dict(circuit_breakers or {})

    def _breaker(self, host: str) -> CircuitBreaker:
        return self.circuit_breakers.setdefault(host, CircuitBreaker())

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return min(30.0, max(0.0, float(retry_after)))
                except ValueError:
                    pass
        return min(8.0, float(2 ** (attempt - 1)))

    def get_json(self, url: str, *, params: Mapping[str, str] | None = None) -> FetchedJSON:
        validate_public_https_url(url, allowed_hosts=self.allowed_hosts, resolver=self.resolver)
        parsed = urlparse(url)
        assert parsed.hostname is not None
        host = parsed.hostname.lower().rstrip(".")
        breaker = self._breaker(host)
        breaker.before_request(now=self.clock())

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            response: httpx.Response | None = None
            started = self.monotonic()
            try:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                    headers={
                        "accept": "application/json",
                        "user-agent": "xrp-regime-engine/0.4-readonly",
                    },
                ) as client:
                    response = client.get(url, params=dict(params or {}))
                latency_ms = max(0.0, (self.monotonic() - started) * 1000.0)

                if response.is_redirect:
                    raise ProviderProtocolError("redirects are forbidden for provider requests")
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    raise ProviderUnavailable(f"transient provider status: {response.status_code}")
                if response.status_code != 200:
                    raise ProviderProtocolError(f"unexpected provider status: {response.status_code}")

                raw = response.content
                if len(raw) > self.max_payload_bytes:
                    raise ProviderProtocolError("provider payload exceeds the configured size limit")
                media_type = response.headers.get("content-type", "").lower()
                if "json" not in media_type:
                    raise ProviderProtocolError(f"provider response is not JSON: {media_type or 'missing'}")
                try:
                    decoded = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ProviderProtocolError("provider returned malformed JSON") from exc
                if not isinstance(decoded, Mapping):
                    raise ProviderProtocolError("provider JSON root must be an object")

                breaker.record_success()
                return FetchedJSON(
                    url=str(response.request.url),
                    status_code=response.status_code,
                    received_at=require_aware_utc(self.clock()),
                    latency_ms=latency_ms,
                    payload_sha256=sha256(raw).hexdigest(),
                    payload_size_bytes=len(raw),
                    data=decoded,
                    attempts=attempt,
                )
            except (httpx.HTTPError, ProviderError, ValueError) as exc:
                last_error = exc
                breaker.record_failure(now=self.clock())
                if attempt >= self.max_attempts or isinstance(exc, ProviderProtocolError):
                    break
                self.sleep(self._retry_delay(response, attempt))
                breaker.before_request(now=self.clock())

        raise ProviderUnavailable(f"provider request failed after {self.max_attempts} attempt(s): {last_error}")


@dataclass(frozen=True, slots=True)
class ProviderQuote:
    provider: str
    base_asset: str
    quote_asset: str
    price: Decimal
    observed_at: datetime
    received_at: datetime
    source_url: str
    payload_sha256: str
    latency_ms: float
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            price = Decimal(self.price)
        except InvalidOperation as exc:
            raise ValueError("invalid quote price") from exc
        if price <= 0:
            raise ValueError("quote price must be positive")
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "observed_at", require_aware_utc(self.observed_at))
        object.__setattr__(self, "received_at", require_aware_utc(self.received_at))
        if self.observed_at > self.received_at + timedelta(seconds=5):
            raise ValueError("quote observed_at is implausibly in the future")

    @property
    def symbol(self) -> str:
        return f"{self.base_asset}-{self.quote_asset}"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["price"] = str(self.price)
        payload["observed_at"] = self.observed_at.isoformat()
        payload["received_at"] = self.received_at.isoformat()
        return payload


class QuoteAdapter(Protocol):
    provider: str
    base_asset: str
    quote_asset: str
    url: str

    def parse_price(self, payload: Mapping[str, Any]) -> Decimal: ...

    def observed_at(self, payload: Mapping[str, Any], *, fallback: datetime) -> datetime: ...


class BaseQuoteAdapter:
    provider = ""
    base_asset = "XRP"
    quote_asset = "USD"
    url = ""
    quality_flags: tuple[str, ...] = ()

    def observed_at(self, payload: Mapping[str, Any], *, fallback: datetime) -> datetime:
        del payload
        return fallback

    def fetch(self, client: ReadOnlyJSONClient) -> ProviderQuote:
        fetched = client.get_json(self.url)
        price = self.parse_price(fetched.data)
        observed = self.observed_at(fetched.data, fallback=fetched.received_at)
        return ProviderQuote(
            provider=self.provider,
            base_asset=self.base_asset,
            quote_asset=self.quote_asset,
            price=price,
            observed_at=observed,
            received_at=fetched.received_at,
            source_url=fetched.url,
            payload_sha256=fetched.payload_sha256,
            latency_ms=fetched.latency_ms,
            quality_flags=self.quality_flags,
        )


class CoinbaseXRPUSDAdapter(BaseQuoteAdapter):
    provider = "coinbase"
    quote_asset = "USD"
    url = "https://api.exchange.coinbase.com/products/XRP-USD/ticker"

    def parse_price(self, payload: Mapping[str, Any]) -> Decimal:
        try:
            return Decimal(str(payload["price"]))
        except (KeyError, InvalidOperation) as exc:
            raise ProviderProtocolError("Coinbase ticker has no valid price") from exc

    def observed_at(self, payload: Mapping[str, Any], *, fallback: datetime) -> datetime:
        raw = payload.get("time")
        if not raw:
            return fallback
        try:
            return require_aware_utc(datetime.fromisoformat(str(raw).replace("Z", "+00:00")))
        except ValueError as exc:
            raise ProviderProtocolError("Coinbase ticker has an invalid timestamp") from exc


class KrakenXRPUSDAdapter(BaseQuoteAdapter):
    provider = "kraken"
    quote_asset = "USD"
    url = "https://api.kraken.com/0/public/Ticker?pair=XRPUSD"

    def parse_price(self, payload: Mapping[str, Any]) -> Decimal:
        errors = payload.get("error")
        if isinstance(errors, list) and errors:
            raise ProviderProtocolError(f"Kraken error: {errors}")
        result = payload.get("result")
        if not isinstance(result, Mapping) or not result:
            raise ProviderProtocolError("Kraken ticker has no result object")
        ticker = next(iter(result.values()))
        if not isinstance(ticker, Mapping):
            raise ProviderProtocolError("Kraken ticker result is malformed")
        close = ticker.get("c")
        try:
            return Decimal(str(close[0]))
        except (TypeError, IndexError, InvalidOperation) as exc:
            raise ProviderProtocolError("Kraken ticker has no valid close price") from exc


class KuCoinXRPUSDTAdapter(BaseQuoteAdapter):
    provider = "kucoin"
    quote_asset = "USDT"
    url = "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=XRP-USDT"
    quality_flags = ("STABLECOIN_QUOTE",)

    def parse_price(self, payload: Mapping[str, Any]) -> Decimal:
        if payload.get("code") not in {None, "200000"}:
            raise ProviderProtocolError(f"KuCoin error code: {payload.get('code')}")
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ProviderProtocolError("KuCoin ticker has no data object")
        try:
            return Decimal(str(data["price"]))
        except (KeyError, InvalidOperation) as exc:
            raise ProviderProtocolError("KuCoin ticker has no valid price") from exc

    def observed_at(self, payload: Mapping[str, Any], *, fallback: datetime) -> datetime:
        data = payload.get("data")
        if not isinstance(data, Mapping) or data.get("time") is None:
            return fallback
        try:
            return datetime.fromtimestamp(int(data["time"]) / 1000.0, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ProviderProtocolError("KuCoin ticker has an invalid timestamp") from exc


class BinanceXRPUSDTAdapter(BaseQuoteAdapter):
    provider = "binance"
    quote_asset = "USDT"
    url = "https://api.binance.com/api/v3/ticker/price?symbol=XRPUSDT"
    quality_flags = ("STABLECOIN_QUOTE",)

    def parse_price(self, payload: Mapping[str, Any]) -> Decimal:
        try:
            return Decimal(str(payload["price"]))
        except (KeyError, InvalidOperation) as exc:
            raise ProviderProtocolError("Binance ticker has no valid price") from exc


@dataclass(frozen=True, slots=True)
class ProviderProbe:
    provider: str
    symbol: str
    status: str
    checked_at: datetime
    quote: ProviderQuote | None = None
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "symbol": self.symbol,
            "status": self.status,
            "checked_at": self.checked_at.isoformat(),
            "quote": self.quote.to_dict() if self.quote else None,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


class LiveProviderPlane:
    def __init__(self, client: ReadOnlyJSONClient, adapters: Iterable[BaseQuoteAdapter]) -> None:
        self.client = client
        self.adapters = tuple(adapters)
        if not self.adapters:
            raise ValueError("at least one provider adapter is required")

    def probe(self) -> tuple[ProviderProbe, ...]:
        results: list[ProviderProbe] = []
        for adapter in self.adapters:
            checked_at = require_aware_utc(self.client.clock())
            try:
                quote = adapter.fetch(self.client)
                results.append(
                    ProviderProbe(
                        provider=adapter.provider,
                        symbol=quote.symbol,
                        status="HEALTHY",
                        checked_at=checked_at,
                        quote=quote,
                    )
                )
            except Exception as exc:  # provider isolation boundary
                results.append(
                    ProviderProbe(
                        provider=adapter.provider,
                        symbol=f"{adapter.base_asset}-{adapter.quote_asset}",
                        status="FAILED",
                        checked_at=checked_at,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )
        return tuple(results)

    @staticmethod
    def healthy_quotes(probes: Iterable[ProviderProbe]) -> tuple[ProviderQuote, ...]:
        return tuple(probe.quote for probe in probes if probe.status == "HEALTHY" and probe.quote is not None)


DEFAULT_ADAPTERS: tuple[BaseQuoteAdapter, ...] = (
    CoinbaseXRPUSDAdapter(),
    KrakenXRPUSDAdapter(),
    KuCoinXRPUSDTAdapter(),
    BinanceXRPUSDTAdapter(),
)

DEFAULT_ALLOWED_HOSTS = tuple(sorted({urlparse(adapter.url).hostname or "" for adapter in DEFAULT_ADAPTERS}))


def probe_to_json(probes: Iterable[ProviderProbe]) -> str:
    return json.dumps([probe.to_dict() for probe in probes], indent=2, sort_keys=True) + "\n"


def build_url(base_url: str, params: Mapping[str, str]) -> str:
    """Deterministic helper for registry/reporting; HTTP calls still pass params separately."""

    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode(sorted(params.items()))}"
