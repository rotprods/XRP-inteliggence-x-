from __future__ import annotations

from datetime import UTC, datetime

from xrp_regime_engine.derivatives import FundingState, OpenInterestState
from xrp_regime_engine.models import Candle
from xrp_regime_engine.providers.base import MarketDataProvider, ProviderError


class BinanceFuturesProvider(MarketDataProvider):
    """Read-only USD-M public market-data adapter."""

    name = "binance_usdm"
    allowed_hosts = frozenset({"fapi.binance.com"})
    symbols = {"XRP_USDT": "XRPUSDT", "BTC_USDT": "BTCUSDT", "ETH_USDT": "ETHUSDT"}

    def health_path(self) -> str:
        return "/fapi/v1/ping"

    async def fetch_candles(self, asset: str, interval: str, limit: int = 300) -> list[Candle]:
        raise ProviderError("futures microstructure provider does not expose candles")

    async def fetch_funding(self, asset: str = "XRP_USDT") -> FundingState:
        symbol = self.symbols.get(asset)
        if symbol is None:
            raise ProviderError(f"unsupported asset: {asset}")
        payload, _, _ = await self._request_json(
            "GET", "/fapi/v1/premiumIndex", params={"symbol": symbol}
        )
        if not isinstance(payload, dict):
            raise ProviderError("Binance returned unexpected premium-index data")
        try:
            observed_at = datetime.fromtimestamp(int(payload["time"]) / 1000, tz=UTC)
            next_funding = datetime.fromtimestamp(int(payload["nextFundingTime"]) / 1000, tz=UTC)
            return FundingState(
                symbol=symbol,
                observed_at=observed_at,
                mark_price=float(payload["markPrice"]),
                index_price=float(payload["indexPrice"]),
                funding_rate=float(payload["lastFundingRate"]),
                next_funding_at=next_funding,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Binance returned malformed premium-index data") from exc

    async def fetch_open_interest(self, asset: str = "XRP_USDT") -> OpenInterestState:
        symbol = self.symbols.get(asset)
        if symbol is None:
            raise ProviderError(f"unsupported asset: {asset}")
        payload, _, _ = await self._request_json(
            "GET", "/fapi/v1/openInterest", params={"symbol": symbol}
        )
        if not isinstance(payload, dict):
            raise ProviderError("Binance returned unexpected open-interest data")
        try:
            observed_at = datetime.fromtimestamp(int(payload["time"]) / 1000, tz=UTC)
            return OpenInterestState(
                symbol=symbol,
                observed_at=observed_at,
                open_interest=float(payload["openInterest"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Binance returned malformed open-interest data") from exc
