from __future__ import annotations

from datetime import UTC, datetime, timedelta

from xrp_regime_engine.models import Candle, Provenance
from xrp_regime_engine.providers.base import MarketDataProvider, ProviderError


class CoinbaseExchangeProvider(MarketDataProvider):
    name = "coinbase_exchange"
    allowed_hosts = frozenset({"api.exchange.coinbase.com"})
    symbols = {"XRP_USD": "XRP-USD", "BTC_USD": "BTC-USD", "ETH_USD": "ETH-USD"}
    granularities = {"1m": 60, "5m": 300, "1h": 3600, "4h": 14400, "1d": 86400}

    def health_path(self) -> str:
        return "/time"

    async def fetch_candles(self, asset: str, interval: str, limit: int = 300) -> list[Candle]:
        product = self.symbols.get(asset)
        granularity = self.granularities.get(interval)
        if not product or not granularity:
            raise ProviderError(f"unsupported asset/interval: {asset}/{interval}")
        if not 1 <= limit <= 300:
            raise ProviderError("limit must be between 1 and 300")

        payload, _, digest = await self._request_json(
            "GET", f"/products/{product}/candles", params={"granularity": granularity}
        )
        if not isinstance(payload, list):
            raise ProviderError("Coinbase returned an unexpected payload")

        fetched = datetime.now(UTC)
        candles: list[Candle] = []
        try:
            for row in sorted(payload, key=lambda item: item[0])[-limit:]:
                if not isinstance(row, list) or len(row) < 6:
                    raise ProviderError("Coinbase returned a malformed candle")
                open_time = datetime.fromtimestamp(float(row[0]), tz=UTC)
                close_time = open_time + timedelta(seconds=granularity)
                if close_time > fetched:
                    continue
                provenance = Provenance(
                    provider=self.name,
                    source_uri=f"{self.base_url}/products/{product}/candles",
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
                        low=float(row[1]),
                        high=float(row[2]),
                        open=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                        provenance=provenance,
                    )
                )
        except (TypeError, ValueError, IndexError) as exc:
            raise ProviderError("Coinbase returned a malformed candle") from exc
        return candles
