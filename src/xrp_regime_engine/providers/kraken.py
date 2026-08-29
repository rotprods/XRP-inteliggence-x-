from __future__ import annotations

from datetime import UTC, datetime, timedelta

from xrp_regime_engine.models import Candle, Provenance
from xrp_regime_engine.providers.base import MarketDataProvider, ProviderError


class KrakenSpotProvider(MarketDataProvider):
    name = "kraken_spot"
    allowed_hosts = frozenset({"api.kraken.com"})
    symbols = {"XRP_USD": "XRPUSD", "BTC_USD": "XBTUSD", "ETH_USD": "ETHUSD"}
    intervals = {"1m": 1, "5m": 5, "1h": 60, "4h": 240, "1d": 1440}

    def health_path(self) -> str:
        return "/0/public/Time"

    async def fetch_candles(self, asset: str, interval: str, limit: int = 300) -> list[Candle]:
        pair = self.symbols.get(asset)
        minutes = self.intervals.get(interval)
        if not pair or not minutes:
            raise ProviderError(f"unsupported asset/interval: {asset}/{interval}")
        if not 1 <= limit <= 720:
            raise ProviderError("limit must be between 1 and 720")

        payload, _, digest = await self._request_json(
            "GET", "/0/public/OHLC", params={"pair": pair, "interval": minutes}
        )
        if not isinstance(payload, dict):
            raise ProviderError("Kraken returned an unexpected payload")
        if payload.get("error"):
            raise ProviderError("Kraken returned an API error")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ProviderError("Kraken returned a malformed result")
        keys = [key for key in result if key != "last"]
        if len(keys) != 1 or not isinstance(result[keys[0]], list):
            raise ProviderError("Kraken returned an ambiguous OHLC result")

        fetched = datetime.now(UTC)
        candles: list[Candle] = []
        try:
            for row in result[keys[0]][-limit:]:
                if not isinstance(row, list) or len(row) < 7:
                    raise ProviderError("Kraken returned a malformed candle")
                open_time = datetime.fromtimestamp(float(row[0]), tz=UTC)
                close_time = open_time + timedelta(minutes=minutes)
                if close_time > fetched:
                    continue
                provenance = Provenance(
                    provider=self.name,
                    source_uri=f"{self.base_url}/0/public/OHLC",
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
                        volume=float(row[6]),
                        provenance=provenance,
                    )
                )
        except (TypeError, ValueError, IndexError) as exc:
            raise ProviderError("Kraken returned a malformed candle") from exc
        return candles
