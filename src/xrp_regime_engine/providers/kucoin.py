from __future__ import annotations

from datetime import UTC, datetime, timedelta

from xrp_regime_engine.models import Candle, ProviderHealth, Provenance
from xrp_regime_engine.providers.base import MarketDataProvider, ProviderError


class KuCoinSpotProvider(MarketDataProvider):
    """Read-only KuCoin spot adapter using the current Unified API market endpoints."""

    name = "kucoin_spot"
    allowed_hosts = frozenset({"api.kucoin.com", "api.kucoin.eu"})
    symbols = {
        "XRP_USDT": "XRP-USDT",
        "BTC_USDT": "BTC-USDT",
        "ETH_USDT": "ETH-USDT",
    }
    intervals: dict[str, tuple[str, int]] = {
        "1m": ("1min", 60),
        "5m": ("5min", 300),
        "1h": ("1hour", 3600),
        "4h": ("4hour", 14_400),
        "1d": ("1day", 86_400),
    }

    def health_path(self) -> str:
        return "/api/ua/v1/server/status"

    async def health(self) -> ProviderHealth:
        now = datetime.now(UTC)
        try:
            payload, latency, _ = await self._request_json(
                "GET",
                self.health_path(),
                params={"tradeType": "SPOT"},
            )
            if not isinstance(payload, dict) or payload.get("code") != "200000":
                raise ProviderError("KuCoin returned an unexpected health payload")
            data = payload.get("data")
            if not isinstance(data, dict):
                raise ProviderError("KuCoin returned an unexpected health payload")
            server_status = str(data.get("serverStatus", "")).lower()
            status = "ok" if server_status == "open" else "down"
            return ProviderHealth(
                provider=self.name,
                checked_at=now,
                status=status,
                latency_ms=latency,
                freshness_score=1.0 if status == "ok" else 0.0,
                agreement_score=1.0 if status == "ok" else 0.0,
                error=None if status == "ok" else "provider reports non-open service status",
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

    async def fetch_candles(self, asset: str, interval: str, limit: int = 300) -> list[Candle]:
        symbol = self.symbols.get(asset)
        interval_spec = self.intervals.get(interval)
        if not symbol or not interval_spec:
            raise ProviderError(f"unsupported asset/interval: {asset}/{interval}")
        if not 1 <= limit <= 1500:
            raise ProviderError("limit must be between 1 and 1500")

        provider_interval, interval_seconds = interval_spec
        fetched = datetime.now(UTC)
        end_at = int(fetched.timestamp())
        # Missing-tick intervals are possible, so request a wider deterministic window
        # and slice the normalized/sorted result to the caller's requested maximum.
        start_at = end_at - interval_seconds * max(limit * 2, 10)
        payload, _, digest = await self._request_json(
            "GET",
            "/api/ua/v1/market/kline",
            params={
                "tradeType": "SPOT",
                "symbol": symbol,
                "interval": provider_interval,
                "startAt": start_at,
                "endAt": end_at,
            },
        )
        if not isinstance(payload, dict) or payload.get("code") != "200000":
            raise ProviderError("KuCoin returned an unexpected payload")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise ProviderError("KuCoin returned malformed kline data")

        normalized: list[Candle] = []
        try:
            ordered = sorted(rows, key=lambda row: float(row[0]) if isinstance(row, list) else 0.0)
            for row in ordered:
                if not isinstance(row, list) or len(row) < 7:
                    raise ProviderError("KuCoin returned a malformed kline")
                open_time = datetime.fromtimestamp(float(row[0]), tz=UTC)
                close_time = open_time + timedelta(seconds=interval_seconds)
                if close_time > fetched:
                    continue
                provenance = Provenance(
                    provider=self.name,
                    source_uri=f"{self.base_url}/api/ua/v1/market/kline",
                    observed_at=close_time,
                    available_at=close_time,
                    fetched_at=fetched,
                    payload_hash=digest,
                )
                normalized.append(
                    Candle(
                        asset=asset,
                        interval=interval,
                        open_time=open_time,
                        close_time=close_time,
                        open=float(row[1]),
                        close=float(row[2]),
                        high=float(row[3]),
                        low=float(row[4]),
                        volume=float(row[5]),
                        provenance=provenance,
                    )
                )
        except (TypeError, ValueError, IndexError) as exc:
            raise ProviderError("KuCoin returned a malformed kline") from exc
        return normalized[-limit:]
