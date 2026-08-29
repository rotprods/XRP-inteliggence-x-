from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from xrp_regime_engine.models import AssetObservation, Candle, Provenance
from xrp_regime_engine.providers.base import MarketDataProvider, ProviderError


class FredProvider(MarketDataProvider):
    name = "fred"
    allowed_hosts = frozenset({"api.stlouisfed.org"})

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.stlouisfed.org",
        **provider_kwargs: Any,
    ) -> None:
        if not api_key:
            raise ValueError("FRED API key is required")
        super().__init__(base_url, **provider_kwargs)
        self.api_key = api_key

    def health_path(self) -> str:
        return "/fred/series"

    async def fetch_series(
        self, series_id: str, start: str | None = None
    ) -> list[AssetObservation]:
        if not series_id:
            raise ProviderError("series_id is required")
        params = {"series_id": series_id, "api_key": self.api_key, "file_type": "json"}
        if start:
            params["observation_start"] = start
        payload, _, digest = await self._request_json(
            "GET", "/fred/series/observations", params=params
        )
        if not isinstance(payload, dict):
            raise ProviderError("FRED returned an unexpected payload")

        fetched = datetime.now(UTC)
        observations: list[AssetObservation] = []
        for row in payload.get("observations", []):
            if not isinstance(row, dict) or row.get("value") in {None, "."}:
                continue
            try:
                observed = datetime.fromisoformat(str(row["date"])).replace(tzinfo=UTC)
                realtime_start_raw = str(row.get("realtime_start") or row["date"])
                realtime_start = datetime.fromisoformat(realtime_start_raw).replace(tzinfo=UTC)
                available = max(observed, realtime_start)
                value = float(row["value"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderError("FRED returned a malformed observation") from exc

            provenance = Provenance(
                provider=self.name,
                source_uri=f"{self.base_url}/fred/series/observations",
                observed_at=observed,
                available_at=available,
                fetched_at=fetched,
                payload_hash=digest,
            )
            observations.append(
                AssetObservation(
                    asset=series_id,
                    metric="level",
                    value=value,
                    unit="native",
                    observed_at=observed,
                    available_at=available,
                    provenance=provenance,
                    metadata={
                        "availability_precision": "date",
                        "realtime_start": realtime_start_raw,
                        "realtime_end": row.get("realtime_end"),
                    },
                )
            )
        return observations

    async def fetch_candles(
        self, asset: str, interval: str, limit: int = 300
    ) -> list[Candle]:
        raise ProviderError("FRED provides economic observations, not OHLC candles")
