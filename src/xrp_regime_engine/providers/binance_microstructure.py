from __future__ import annotations

from datetime import UTC, datetime

from xrp_regime_engine.microstructure import BookLevel, OrderBookSnapshot
from xrp_regime_engine.models import Candle
from xrp_regime_engine.providers.base import MarketDataProvider, ProviderError


class BinanceMicrostructureProvider(MarketDataProvider):
    """Read-only Binance Spot microstructure provider. Never submits orders."""

    name = "binance_microstructure"
    allowed_hosts = frozenset({"data-api.binance.vision", "api.binance.com"})
    symbols = {"XRP_USDT": "XRPUSDT", "BTC_USDT": "BTCUSDT", "ETH_USDT": "ETHUSDT"}
    depth_limits = frozenset({5, 10, 20, 50, 100, 500, 1000, 5000})

    def health_path(self) -> str:
        return "/api/v3/ping"

    async def fetch_candles(
        self, asset: str, interval: str, limit: int = 300
    ) -> list[Candle]:
        raise ProviderError("microstructure provider does not expose candles")

    async def fetch_order_book(
        self, asset: str = "XRP_USDT", limit: int = 1000
    ) -> OrderBookSnapshot:
        symbol = self.symbols.get(asset)
        if symbol is None:
            raise ProviderError(f"unsupported asset: {asset}")
        if limit not in self.depth_limits:
            raise ProviderError("unsupported Binance depth limit")

        payload, _, digest = await self._request_json(
            "GET", "/api/v3/depth", params={"symbol": symbol, "limit": limit}
        )
        if not isinstance(payload, dict):
            raise ProviderError("Binance returned an unexpected depth payload")

        fetched_at = datetime.now(UTC)
        try:
            update_id = int(payload["lastUpdateId"])
            raw_bids = payload["bids"]
            raw_asks = payload["asks"]
            if not isinstance(raw_bids, list) or not isinstance(raw_asks, list):
                raise TypeError
            bids = tuple(BookLevel(float(row[0]), float(row[1])) for row in raw_bids)
            asks = tuple(BookLevel(float(row[0]), float(row[1])) for row in raw_asks)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("Binance returned malformed depth data") from exc

        return OrderBookSnapshot(
            symbol=symbol,
            last_update_id=update_id,
            observed_at=fetched_at,
            fetched_at=fetched_at,
            bids=bids,
            asks=asks,
            provider=self.name,
            payload_hash=digest,
        )
