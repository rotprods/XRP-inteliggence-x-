from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from xrp_regime_engine.models import AssetObservation, Candle, ProviderHealth, Provenance
from xrp_regime_engine.providers.base import MarketDataProvider, ProviderError


class XRPLProvider(MarketDataProvider):
    name = "xrpl"
    allowed_hosts = frozenset({"s1.ripple.com", "s2.ripple.com", "xrplcluster.com"})
    allowed_methods = frozenset({"GET", "POST"})
    allowed_rpc_methods = frozenset(
        {"server_info", "ledger", "ledger_data", "book_offers", "amm_info", "account_lines"}
    )

    async def rpc(
        self, method: str, params: list[dict[str, Any]] | None = None
    ) -> tuple[dict[str, Any], str]:
        if method not in self.allowed_rpc_methods:
            raise ProviderError(f"XRPL RPC method {method!r} is not allowlisted")
        payload, _, digest = await self._request_json(
            "POST", "/", json_body={"method": method, "params": params or [{}]}
        )
        if not isinstance(payload, dict):
            raise ProviderError("XRPL returned an unexpected JSON root")
        result = payload.get("result", {})
        if not isinstance(result, dict):
            raise ProviderError("XRPL returned an unexpected result payload")
        if result.get("status") == "error":
            raise ProviderError("XRPL returned an RPC error")
        return result, digest

    async def health(self) -> ProviderHealth:
        checked_at = datetime.now(UTC)
        try:
            payload, latency, _ = await self._request_json(
                "POST", "/", json_body={"method": "server_info", "params": [{}]}
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
                raise ProviderError("XRPL returned an unexpected health payload")
            return ProviderHealth(
                provider=self.name,
                checked_at=checked_at,
                status="ok",
                latency_ms=latency,
                freshness_score=1.0,
                agreement_score=1.0,
            )
        except ProviderError as exc:
            return ProviderHealth(
                provider=self.name,
                checked_at=checked_at,
                status="down",
                freshness_score=0.0,
                agreement_score=0.0,
                error=str(exc),
            )

    async def server_metrics(self) -> list[AssetObservation]:
        result, digest = await self.rpc("server_info")
        now = datetime.now(UTC)
        info = result.get("info", {})
        if not isinstance(info, dict):
            raise ProviderError("XRPL server_info payload is malformed")
        validated = info.get("validated_ledger", {})
        if not isinstance(validated, dict):
            validated = {}
        values = {
            "validated_ledger_age": float(validated.get("age", 0)),
            "load_factor": float(info.get("load_factor", 1)),
            "peers": float(info.get("peers", 0)),
        }
        observations: list[AssetObservation] = []
        for metric, value in values.items():
            provenance = Provenance(
                provider=self.name,
                source_uri=self.base_url,
                observed_at=now,
                available_at=now,
                fetched_at=now,
                payload_hash=digest,
            )
            observations.append(
                AssetObservation(
                    asset="XRPL",
                    metric=metric,
                    value=value,
                    unit="native",
                    observed_at=now,
                    available_at=now,
                    provenance=provenance,
                )
            )
        return observations

    async def fetch_candles(
        self, asset: str, interval: str, limit: int = 300
    ) -> list[Candle]:
        raise ProviderError("XRPL adapter provides ledger metrics, not exchange OHLC candles")
