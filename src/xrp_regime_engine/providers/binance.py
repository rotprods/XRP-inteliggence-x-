from __future__ import annotations

from datetime import UTC, datetime

from xrp_regime_engine.models import Candle, Provenance
from xrp_regime_engine.providers.base import MarketDataProvider, ProviderError


class BinanceSpotProvider(MarketDataProvider):
    name = "binance_spot"
    allowed_hosts = frozenset({"data-api.binance.vision", "api.binance.com"})
    symbols = {
        "XRP_USDT": "XRPUSDT",
        "BTC_USDT": "BTCUSDT",
        "ETH_USDT": "ETHUSDT",
    }
    intervals = {"1m": "1m", "5m": "5m", "1h": "1h", "4h": "4h", "1d": "1d"}

    def health_path(self) -> str:
        return "/api/v3/ping"

    async def fetch_candles(self, asset: str, interval: str, limit: int = 300) -> list[Candle]:
        symbol = self.symbols.get(asset)
        provider_interval = self.intervals.get(interval)
        if not symbol or not provider_interval:
            raise ProviderError(f"unsupported asset/interval: {asset}/{interval}")
        if not 1 <= limit <= 1000:
            raise ProviderError("limit must be between 1 and 1000")

        payload, _, digest = await self._request_json(
            "GET",
            "/api/v3/klines",
            params={"symbol": symbol, "interval": provider_interval, "limit": limit},
        )
        if not isinstance(payload, list):
            raise ProviderError("Binance returned an unexpected payload")

        fetched = datetime.now(UTC)
        candles: list[Candle] = []
        try:
            for row in payload:
                if not isinstance(row, list) or len(row) < 7:
                    raise ProviderError("Binance returned a malformed kline")
                open_time = datetime.fromtimestamp(float(row[0]) / 1000, tz=UTC)
                close_time = datetime.fromtimestamp(float(row[6]) / 1000, tz=UTC)
                if close_time > fetched:
                    continue
                provenance = Provenance(
                    provider=self.name,
                    source_uri=f"{self.base_url}/api/v3/klines",
                    observed_at=close_time,
                    available_at=close_time,
                    fetched_at=fetched,
                    payload_hash=digest,
                )
                candles.append(
                    Candle(
                        asset=asset,
                        interval=interval,
                        open_time=open_time,
                        close_time=close_time,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                        provenance=provenance,
                    )
                )
        except (TypeError, ValueError, IndexError) as exc:
            raise ProviderError("Binance returned a malformed kline") from exc
        return candles
