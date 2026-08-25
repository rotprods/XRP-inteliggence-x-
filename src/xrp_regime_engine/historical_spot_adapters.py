from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlparse

import httpx

from xrp_regime_engine.historical_backfill import (
    BackfillPage,
    BackfillWindow,
    NormalizedPageRecord,
)
from xrp_regime_engine.live_provider_plane import (
    ProviderProtocolError,
    ProviderUnavailable,
    default_resolver,
    require_aware_utc,
    validate_public_https_url,
)


@dataclass(frozen=True, slots=True)
class HistoricalHTTPPayload:
    raw_payload: bytes
    data: Any
    source_url: str
    received_at: datetime
    attempts: int
    latency_ms: float


class HistoricalHTTPClient:
    """GET-only JSON client for historical list or object payloads."""

    def __init__(
        self,
        *,
        allowed_hosts: Iterable[str],
        timeout_seconds: float = 15.0,
        max_attempts: int = 3,
        max_payload_bytes: int = 10_000_000,
        resolver: Callable[[str, int], Sequence[str]] = default_resolver,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if timeout_seconds <= 0 or max_attempts <= 0 or max_payload_bytes <= 0:
            raise ValueError("HTTP limits must be positive")
        self.allowed_hosts = tuple(sorted({host.lower().rstrip(".") for host in allowed_hosts}))
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.max_payload_bytes = max_payload_bytes
        self.resolver = resolver
        self.transport = transport
        self.sleep = sleep
        self.clock = clock
        self.monotonic = monotonic

    def get_json_value(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> HistoricalHTTPPayload:
        validate_public_https_url(url, allowed_hosts=self.allowed_hosts, resolver=self.resolver)
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            started = self.monotonic()
            response: httpx.Response | None = None
            try:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                    headers={
                        "accept": "application/json",
                        "user-agent": "xrp-regime-engine/0.5-historical-readonly",
                    },
                ) as client:
                    response = client.get(url, params=dict(params or {}))
                latency_ms = max(0.0, (self.monotonic() - started) * 1000.0)
                if response.is_redirect:
                    raise ProviderProtocolError("redirects are forbidden")
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    raise ProviderUnavailable(f"transient historical-provider status: {response.status_code}")
                if response.status_code != 200:
                    raise ProviderProtocolError(
                        f"unexpected historical-provider status: {response.status_code}"
                    )
                raw = response.content
                if not raw or len(raw) > self.max_payload_bytes:
                    raise ProviderProtocolError("historical payload is empty or exceeds its size limit")
                if "json" not in response.headers.get("content-type", "").lower():
                    raise ProviderProtocolError("historical provider did not return JSON")
                try:
                    decoded = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ProviderProtocolError("historical provider returned malformed JSON") from exc
                if not isinstance(decoded, (Mapping, list)):
                    raise ProviderProtocolError("historical JSON root must be an object or array")
                return HistoricalHTTPPayload(
                    raw_payload=raw,
                    data=decoded,
                    source_url=str(response.request.url),
                    received_at=require_aware_utc(self.clock()),
                    attempts=attempt,
                    latency_ms=latency_ms,
                )
            except (httpx.HTTPError, ProviderProtocolError, ProviderUnavailable) as exc:
                last_error = exc
                if attempt >= self.max_attempts or isinstance(exc, ProviderProtocolError):
                    break
                retry_after = response.headers.get("retry-after") if response is not None else None
                try:
                    delay = min(30.0, max(0.0, float(retry_after))) if retry_after else 2 ** (attempt - 1)
                except ValueError:
                    delay = 2 ** (attempt - 1)
                self.sleep(float(delay))
        raise ProviderUnavailable(
            f"historical request failed after {self.max_attempts} attempt(s): {last_error}"
        )


class CoinbaseCandleAdapter:
    provider = "coinbase"
    source = "coinbase_exchange"
    schema_version = "candle.v1"
    base_asset = "XRP"
    quote_asset = "USD"
    endpoint = "https://api.exchange.coinbase.com/products/XRP-USD/candles"
    supported_intervals = {60, 300, 900, 3600, 21600, 86400}
    page_limit = 300

    def __init__(self, client: HistoricalHTTPClient, *, interval_seconds: int = 3600) -> None:
        if interval_seconds not in self.supported_intervals:
            raise ValueError("Coinbase interval is unsupported")
        self.client = client
        self.interval_seconds = interval_seconds
        self.dataset = f"xrp_usd_spot_{interval_seconds}s"

    def initial_cursor(self, window: BackfillWindow) -> Mapping[str, Any]:
        self._validate_window(window)
        return {"start": window.start.isoformat()}

    def _validate_window(self, window: BackfillWindow) -> None:
        if window.interval_seconds != self.interval_seconds:
            raise ValueError("window interval does not match Coinbase adapter interval")

    def fetch_page(self, window: BackfillWindow, cursor: Mapping[str, Any]) -> BackfillPage:
        self._validate_window(window)
        try:
            page_start = require_aware_utc(datetime.fromisoformat(str(cursor["start"])))
        except (KeyError, ValueError) as exc:
            raise ValueError("Coinbase cursor has no valid start timestamp") from exc
        if page_start < window.start or page_start >= window.end:
            raise ValueError("Coinbase cursor is outside the backfill window")
        page_end = min(
            page_start + timedelta(seconds=self.interval_seconds * self.page_limit),
            window.end,
        )
        payload = self.client.get_json_value(
            self.endpoint,
            params={
                "start": page_start.isoformat().replace("+00:00", "Z"),
                "end": page_end.isoformat().replace("+00:00", "Z"),
                "granularity": self.interval_seconds,
            },
        )
        if not isinstance(payload.data, list):
            raise ProviderProtocolError("Coinbase candles root must be an array")

        records: list[NormalizedPageRecord] = []
        for item in payload.data:
            if not isinstance(item, list) or len(item) < 6:
                raise ProviderProtocolError("Coinbase candle is malformed")
            try:
                epoch_seconds = int(item[0])
                observed = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
                values = {
                    "open": str(Decimal(str(item[3]))),
                    "high": str(Decimal(str(item[2]))),
                    "low": str(Decimal(str(item[1]))),
                    "close": str(Decimal(str(item[4]))),
                    "volume": str(Decimal(str(item[5]))),
                    "base_asset": self.base_asset,
                    "quote_asset": self.quote_asset,
                    "interval_seconds": self.interval_seconds,
                }
            except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
                raise ProviderProtocolError("Coinbase candle contains invalid values") from exc
            if observed < window.start or observed >= window.end:
                continue
            records.append(
                NormalizedPageRecord(
                    record_id=f"XRP-USD:{self.interval_seconds}:{epoch_seconds}",
                    observed_at=observed,
                    available_at=observed + timedelta(seconds=self.interval_seconds),
                    values=values,
                )
            )

        completed = page_end >= window.end
        return BackfillPage(
            raw_payload=payload.raw_payload,
            source_url=payload.source_url,
            received_at=payload.received_at,
            records=tuple(sorted(records, key=lambda record: record.observed_at)),
            next_cursor=None if completed else {"start": page_end.isoformat()},
            completed=completed,
            attributes={
                "adapter": "coinbase-candles",
                "page_start": page_start.isoformat(),
                "page_end": page_end.isoformat(),
                "latency_ms": payload.latency_ms,
                "attempts": payload.attempts,
            },
        )


class BinanceKlineAdapter:
    provider = "binance"
    source = "binance_spot"
    schema_version = "candle.v1"
    base_asset = "XRP"
    quote_asset = "USDT"
    endpoint = "https://api.binance.com/api/v3/klines"
    interval_names = {
        60: "1m",
        300: "5m",
        900: "15m",
        3600: "1h",
        14400: "4h",
        86400: "1d",
    }
    page_limit = 1000

    def __init__(self, client: HistoricalHTTPClient, *, interval_seconds: int = 3600) -> None:
        if interval_seconds not in self.interval_names:
            raise ValueError("Binance interval is unsupported")
        self.client = client
        self.interval_seconds = interval_seconds
        self.dataset = f"xrp_usdt_spot_{interval_seconds}s"

    def initial_cursor(self, window: BackfillWindow) -> Mapping[str, Any]:
        self._validate_window(window)
        return {"start_ms": int(window.start.timestamp() * 1000)}

    def _validate_window(self, window: BackfillWindow) -> None:
        if window.interval_seconds != self.interval_seconds:
            raise ValueError("window interval does not match Binance adapter interval")

    def fetch_page(self, window: BackfillWindow, cursor: Mapping[str, Any]) -> BackfillPage:
        self._validate_window(window)
        try:
            start_ms = int(cursor["start_ms"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Binance cursor has no valid start_ms") from exc
        window_start_ms = int(window.start.timestamp() * 1000)
        window_end_ms = int(window.end.timestamp() * 1000)
        if start_ms < window_start_ms or start_ms >= window_end_ms:
            raise ValueError("Binance cursor is outside the backfill window")

        interval_ms = self.interval_seconds * 1000
        request_end_ms = min(window_end_ms - 1, start_ms + self.page_limit * interval_ms - 1)
        payload = self.client.get_json_value(
            self.endpoint,
            params={
                "symbol": "XRPUSDT",
                "interval": self.interval_names[self.interval_seconds],
                "startTime": start_ms,
                "endTime": request_end_ms,
                "limit": self.page_limit,
            },
        )
        if not isinstance(payload.data, list):
            raise ProviderProtocolError("Binance klines root must be an array")

        records: list[NormalizedPageRecord] = []
        last_open_ms: int | None = None
        for item in payload.data:
            if not isinstance(item, list) or len(item) < 7:
                raise ProviderProtocolError("Binance kline is malformed")
            try:
                open_ms = int(item[0])
                close_ms = int(item[6])
                observed = datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc)
                available = datetime.fromtimestamp((close_ms + 1) / 1000.0, tz=timezone.utc)
                values = {
                    "open": str(Decimal(str(item[1]))),
                    "high": str(Decimal(str(item[2]))),
                    "low": str(Decimal(str(item[3]))),
                    "close": str(Decimal(str(item[4]))),
                    "volume": str(Decimal(str(item[5]))),
                    "base_asset": self.base_asset,
                    "quote_asset": self.quote_asset,
                    "interval_seconds": self.interval_seconds,
                }
            except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
                raise ProviderProtocolError("Binance kline contains invalid values") from exc
            if observed < window.start or observed >= window.end:
                continue
            last_open_ms = max(last_open_ms or open_ms, open_ms)
            records.append(
                NormalizedPageRecord(
                    record_id=f"XRP-USDT:{self.interval_seconds}:{open_ms}",
                    observed_at=observed,
                    available_at=available,
                    values=values,
                )
            )

        if last_open_ms is None:
            next_start_ms = request_end_ms + 1
        else:
            next_start_ms = last_open_ms + interval_ms
        completed = next_start_ms >= window_end_ms or len(payload.data) < self.page_limit
        return BackfillPage(
            raw_payload=payload.raw_payload,
            source_url=payload.source_url,
            received_at=payload.received_at,
            records=tuple(sorted(records, key=lambda record: record.observed_at)),
            next_cursor=None if completed else {"start_ms": next_start_ms},
            completed=completed,
            attributes={
                "adapter": "binance-klines",
                "request_start_ms": start_ms,
                "request_end_ms": request_end_ms,
                "latency_ms": payload.latency_ms,
                "attempts": payload.attempts,
                "quality_flags": ["STABLECOIN_QUOTE"],
            },
        )


def historical_allowed_hosts() -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                urlparse(CoinbaseCandleAdapter.endpoint).hostname or "",
                urlparse(BinanceKlineAdapter.endpoint).hostname or "",
            }
        )
    )
