from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256


class EvidenceAuthority(StrEnum):
    PRIMARY_OBSERVED = "PRIMARY_OBSERVED"
    AGGREGATED_OBSERVED = "AGGREGATED_OBSERVED"
    INFERRED_MODEL = "INFERRED_MODEL"


class LiquidityMetricKind(StrEnum):
    CEX_BID_DEPTH_USD = "CEX_BID_DEPTH_USD"
    CEX_ASK_DEPTH_USD = "CEX_ASK_DEPTH_USD"
    LARGE_LIMIT_BID_USD = "LARGE_LIMIT_BID_USD"
    LARGE_LIMIT_ASK_USD = "LARGE_LIMIT_ASK_USD"
    OPEN_INTEREST_USD = "OPEN_INTEREST_USD"
    OPEN_INTEREST_DELTA_USD = "OPEN_INTEREST_DELTA_USD"
    OPEN_INTEREST_VELOCITY_USD_PER_MIN = "OPEN_INTEREST_VELOCITY_USD_PER_MIN"
    FUNDING_RATE = "FUNDING_RATE"
    BASIS_BPS = "BASIS_BPS"
    TAKER_BUY_SELL_RATIO = "TAKER_BUY_SELL_RATIO"
    EXECUTED_LONG_LIQUIDATIONS_USD = "EXECUTED_LONG_LIQUIDATIONS_USD"
    EXECUTED_SHORT_LIQUIDATIONS_USD = "EXECUTED_SHORT_LIQUIDATIONS_USD"
    XRPL_AMM_XRP_RESERVE = "XRPL_AMM_XRP_RESERVE"
    XRPL_AMM_QUOTE_RESERVE = "XRPL_AMM_QUOTE_RESERVE"
    XRPL_DEX_BID_FUNDED = "XRPL_DEX_BID_FUNDED"
    XRPL_DEX_ASK_FUNDED = "XRPL_DEX_ASK_FUNDED"
    XRPL_AMM_SLIPPAGE_10K_BPS = "XRPL_AMM_SLIPPAGE_10K_BPS"
    XRPL_DEX_SPREAD_BPS = "XRPL_DEX_SPREAD_BPS"
    EXCHANGE_INFLOW_XRP = "EXCHANGE_INFLOW_XRP"
    EXCHANGE_OUTFLOW_XRP = "EXCHANGE_OUTFLOW_XRP"
    ETF_NET_FLOW_USD = "ETF_NET_FLOW_USD"
    WHALE_LONG_USD = "WHALE_LONG_USD"
    WHALE_SHORT_USD = "WHALE_SHORT_USD"


class LiquidationClusterSide(StrEnum):
    LONGS_LIQUIDATE_BELOW = "LONGS_LIQUIDATE_BELOW"
    SHORTS_LIQUIDATE_ABOVE = "SHORTS_LIQUIDATE_ABOVE"


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _finite(value: float, field: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _nonempty(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _sha(value: str, field: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return normalized


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


@dataclass(frozen=True, slots=True)
class LiquidityObservation:
    observation_id: str
    provider: str
    venue: str
    symbol: str
    metric: LiquidityMetricKind
    value: float
    unit: str
    observed_at: datetime
    available_at: datetime
    fetched_at: datetime
    authority: EvidenceAuthority
    source_id: str
    payload_sha256: str
    confidence: float = 1.0
    pool_id: str | None = None
    model_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _nonempty(self.provider, "provider"))
        object.__setattr__(self, "venue", _nonempty(self.venue, "venue"))
        object.__setattr__(self, "symbol", _nonempty(self.symbol, "symbol"))
        object.__setattr__(self, "unit", _nonempty(self.unit, "unit"))
        object.__setattr__(self, "source_id", _nonempty(self.source_id, "source_id"))
        object.__setattr__(self, "payload_sha256", _sha(self.payload_sha256, "payload_sha256"))
        observed = _utc(self.observed_at, "observed_at")
        available = _utc(self.available_at, "available_at")
        fetched = _utc(self.fetched_at, "fetched_at")
        if not observed <= available <= fetched:
            raise ValueError("observation timestamps must satisfy observed_at <= available_at <= fetched_at")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "fetched_at", fetched)
        object.__setattr__(self, "value", _finite(self.value, "value"))
        confidence = _finite(self.confidence, "confidence")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be within [0, 1]")
        object.__setattr__(self, "confidence", confidence)
        if self.authority is EvidenceAuthority.INFERRED_MODEL and not self.model_id:
            raise ValueError("INFERRED_MODEL observation requires model_id")
        if self.model_id is not None:
            object.__setattr__(self, "model_id", _nonempty(self.model_id, "model_id"))


@dataclass(frozen=True, slots=True)
class LiquidationCluster:
    cluster_id: str
    provider: str
    symbol: str
    side: LiquidationClusterSide
    lower_price: float
    upper_price: float
    estimated_notional_usd: float
    observed_at: datetime
    available_at: datetime
    fetched_at: datetime
    model_id: str
    source_id: str
    payload_sha256: str
    confidence: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _nonempty(self.provider, "provider"))
        object.__setattr__(self, "symbol", _nonempty(self.symbol, "symbol"))
        object.__setattr__(self, "model_id", _nonempty(self.model_id, "model_id"))
        object.__setattr__(self, "source_id", _nonempty(self.source_id, "source_id"))
        object.__setattr__(self, "payload_sha256", _sha(self.payload_sha256, "payload_sha256"))
        lower = _finite(self.lower_price, "lower_price")
        upper = _finite(self.upper_price, "upper_price")
        notional = _finite(self.estimated_notional_usd, "estimated_notional_usd")
        if lower <= 0 or upper <= 0 or upper < lower:
            raise ValueError("liquidation cluster prices are invalid")
        if notional < 0:
            raise ValueError("estimated_notional_usd cannot be negative")
        confidence = _finite(self.confidence, "confidence")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be within [0, 1]")
        observed = _utc(self.observed_at, "observed_at")
        available = _utc(self.available_at, "available_at")
        fetched = _utc(self.fetched_at, "fetched_at")
        if not observed <= available <= fetched:
            raise ValueError("cluster timestamps must satisfy observed_at <= available_at <= fetched_at")
        object.__setattr__(self, "lower_price", lower)
        object.__setattr__(self, "upper_price", upper)
        object.__setattr__(self, "estimated_notional_usd", notional)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "fetched_at", fetched)


@dataclass(frozen=True, slots=True)
class LiquidityPlanePolicy:
    max_observation_age_seconds: float = 180.0
    max_cluster_age_seconds: float = 300.0
    near_bands_pct: tuple[float, ...] = (0.01, 0.02, 0.05)
    minimum_cluster_confidence: float = 0.50
    minimum_observed_provider_count: int = 2

    def __post_init__(self) -> None:
        if _finite(self.max_observation_age_seconds, "max_observation_age_seconds") <= 0:
            raise ValueError("max_observation_age_seconds must be positive")
        if _finite(self.max_cluster_age_seconds, "max_cluster_age_seconds") <= 0:
            raise ValueError("max_cluster_age_seconds must be positive")
        if self.minimum_observed_provider_count < 1:
            raise ValueError("minimum_observed_provider_count must be positive")
        bands = tuple(sorted({_finite(value, "near_band") for value in self.near_bands_pct}))
        if not bands or any(value <= 0 or value > 1 for value in bands):
            raise ValueError("near_bands_pct must contain values within (0, 1]")
        object.__setattr__(self, "near_bands_pct", bands)
        confidence = _finite(self.minimum_cluster_confidence, "minimum_cluster_confidence")
        if not 0 <= confidence <= 1:
            raise ValueError("minimum_cluster_confidence must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class LiquidationBandExposure:
    band_pct: float
    long_liquidation_notional_below_usd: float
    short_liquidation_notional_above_usd: float


@dataclass(frozen=True, slots=True)
class LiquidityLiquidationState:
    state_id: str
    state_sha256: str
    symbol: str
    prediction_time: datetime
    reference_price: float
    observed_provider_set: tuple[str, ...]
    inferred_provider_set: tuple[str, ...]
    primary_observed_count: int
    aggregated_observed_count: int
    inferred_count: int
    stale_observation_count: int
    stale_cluster_count: int
    cex_bid_depth_usd: float | None
    cex_ask_depth_usd: float | None
    cex_depth_imbalance: float | None
    open_interest_usd: float | None
    open_interest_delta_usd: float | None
    open_interest_velocity_usd_per_min: float | None
    funding_rate: float | None
    basis_bps: float | None
    taker_buy_sell_ratio: float | None
    executed_long_liquidations_usd: float
    executed_short_liquidations_usd: float
    executed_liquidation_imbalance: float | None
    xrpl_amm_xrp_reserve: float
    xrpl_amm_quote_reserve: float
    xrpl_dex_bid_funded: float
    xrpl_dex_ask_funded: float
    xrpl_amm_slippage_10k_bps: float | None
    xrpl_dex_spread_bps: float | None
    exchange_inflow_xrp: float
    exchange_outflow_xrp: float
    etf_net_flow_usd: float
    whale_long_usd: float
    whale_short_usd: float
    liquidation_bands: tuple[LiquidationBandExposure, ...]
    nearest_long_liquidation_distance_pct: float | None
    nearest_short_liquidation_distance_pct: float | None
    inferred_liquidation_bias: float | None
    cluster_to_observed_depth_ratio: float | None
    point_in_time_eligible: bool
    quality_flags: tuple[str, ...]
    decision_authority: bool = False
    execution_weight: float = 0.0


def _robust_center(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _sum_metric(
    observations: Sequence[LiquidityObservation],
    metric: LiquidityMetricKind,
) -> float:
    return sum(item.value for item in observations if item.metric is metric)


def _center_metric(
    observations: Sequence[LiquidityObservation],
    metric: LiquidityMetricKind,
) -> float | None:
    return _robust_center([item.value for item in observations if item.metric is metric])


def _cluster_distance_pct(reference_price: float, cluster: LiquidationCluster) -> float:
    if cluster.side is LiquidationClusterSide.LONGS_LIQUIDATE_BELOW:
        anchor = cluster.upper_price
        return max(0.0, (reference_price - anchor) / reference_price)
    anchor = cluster.lower_price
    return max(0.0, (anchor - reference_price) / reference_price)


def build_liquidity_liquidation_state(
    *,
    symbol: str,
    reference_price: float,
    prediction_time: datetime,
    observations: Sequence[LiquidityObservation],
    liquidation_clusters: Sequence[LiquidationCluster],
    policy: LiquidityPlanePolicy | None = None,
) -> LiquidityLiquidationState:
    selected_policy = policy or LiquidityPlanePolicy()
    target_symbol = _nonempty(symbol, "symbol")
    price = _finite(reference_price, "reference_price")
    if price <= 0:
        raise ValueError("reference_price must be positive")
    prediction = _utc(prediction_time, "prediction_time")

    seen_observations: set[str] = set()
    eligible_observations: list[LiquidityObservation] = []
    stale_observation_count = 0
    quality_flags: list[str] = []
    for item in observations:
        if item.observation_id in seen_observations:
            raise ValueError("observation_id values must be unique")
        seen_observations.add(item.observation_id)
        if item.symbol != target_symbol:
            continue
        if item.available_at > prediction or item.fetched_at > prediction:
            quality_flags.append("FUTURE_OBSERVATION_REJECTED")
            continue
        age = (prediction - item.observed_at).total_seconds()
        if age < 0:
            quality_flags.append("FUTURE_OBSERVATION_REJECTED")
            continue
        if age > selected_policy.max_observation_age_seconds:
            stale_observation_count += 1
            continue
        eligible_observations.append(item)

    seen_clusters: set[str] = set()
    eligible_clusters: list[LiquidationCluster] = []
    stale_cluster_count = 0
    for cluster in liquidation_clusters:
        if cluster.cluster_id in seen_clusters:
            raise ValueError("cluster_id values must be unique")
        seen_clusters.add(cluster.cluster_id)
        if cluster.symbol != target_symbol:
            continue
        if cluster.available_at > prediction or cluster.fetched_at > prediction:
            quality_flags.append("FUTURE_CLUSTER_REJECTED")
            continue
        age = (prediction - cluster.observed_at).total_seconds()
        if age < 0:
            quality_flags.append("FUTURE_CLUSTER_REJECTED")
            continue
        if age > selected_policy.max_cluster_age_seconds:
            stale_cluster_count += 1
            continue
        if cluster.confidence < selected_policy.minimum_cluster_confidence:
            quality_flags.append("LOW_CONFIDENCE_CLUSTER_REJECTED")
            continue
        eligible_clusters.append(cluster)

    primary = [
        item
        for item in eligible_observations
        if item.authority is EvidenceAuthority.PRIMARY_OBSERVED
    ]
    aggregated = [
        item
        for item in eligible_observations
        if item.authority is EvidenceAuthority.AGGREGATED_OBSERVED
    ]
    inferred = [
        item
        for item in eligible_observations
        if item.authority is EvidenceAuthority.INFERRED_MODEL
    ]
    observed_providers = tuple(sorted({item.provider for item in (*primary, *aggregated)}))
    inferred_providers = tuple(
        sorted(
            {item.provider for item in inferred}
            | {item.provider for item in eligible_clusters}
        )
    )

    cex_bid_depth = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.CEX_BID_DEPTH_USD,
    )
    cex_ask_depth = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.CEX_ASK_DEPTH_USD,
    )
    total_depth = cex_bid_depth + cex_ask_depth
    depth_imbalance = (
        (cex_bid_depth - cex_ask_depth) / total_depth
        if total_depth > 0
        else None
    )

    executed_long = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.EXECUTED_LONG_LIQUIDATIONS_USD,
    )
    executed_short = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.EXECUTED_SHORT_LIQUIDATIONS_USD,
    )
    executed_total = executed_long + executed_short
    executed_imbalance = (
        (executed_short - executed_long) / executed_total
        if executed_total > 0
        else None
    )

    bands = []
    for band in selected_policy.near_bands_pct:
        long_below = sum(
            cluster.estimated_notional_usd
            for cluster in eligible_clusters
            if cluster.side is LiquidationClusterSide.LONGS_LIQUIDATE_BELOW
            and _cluster_distance_pct(price, cluster) <= band
        )
        short_above = sum(
            cluster.estimated_notional_usd
            for cluster in eligible_clusters
            if cluster.side is LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE
            and _cluster_distance_pct(price, cluster) <= band
        )
        bands.append(
            LiquidationBandExposure(
                band_pct=band,
                long_liquidation_notional_below_usd=long_below,
                short_liquidation_notional_above_usd=short_above,
            )
        )

    long_distances = [
        _cluster_distance_pct(price, cluster)
        for cluster in eligible_clusters
        if cluster.side is LiquidationClusterSide.LONGS_LIQUIDATE_BELOW
    ]
    short_distances = [
        _cluster_distance_pct(price, cluster)
        for cluster in eligible_clusters
        if cluster.side is LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE
    ]
    nearest_long = min(long_distances) if long_distances else None
    nearest_short = min(short_distances) if short_distances else None

    inferred_long_total = sum(
        cluster.estimated_notional_usd
        for cluster in eligible_clusters
        if cluster.side is LiquidationClusterSide.LONGS_LIQUIDATE_BELOW
    )
    inferred_short_total = sum(
        cluster.estimated_notional_usd
        for cluster in eligible_clusters
        if cluster.side is LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE
    )
    inferred_total = inferred_long_total + inferred_short_total
    inferred_bias = (
        (inferred_short_total - inferred_long_total) / inferred_total
        if inferred_total > 0
        else None
    )
    cluster_to_depth = (
        inferred_total / total_depth
        if inferred_total > 0 and total_depth > 0
        else None
    )

    open_interest_center = _center_metric(
        eligible_observations,
        LiquidityMetricKind.OPEN_INTEREST_USD,
    )
    open_interest_delta_center = _center_metric(
        eligible_observations,
        LiquidityMetricKind.OPEN_INTEREST_DELTA_USD,
    )
    open_interest_velocity_center = _center_metric(
        eligible_observations,
        LiquidityMetricKind.OPEN_INTEREST_VELOCITY_USD_PER_MIN,
    )
    funding_center = _center_metric(
        eligible_observations,
        LiquidityMetricKind.FUNDING_RATE,
    )
    basis_center = _center_metric(
        eligible_observations,
        LiquidityMetricKind.BASIS_BPS,
    )
    taker_ratio_center = _center_metric(
        eligible_observations,
        LiquidityMetricKind.TAKER_BUY_SELL_RATIO,
    )
    xrpl_amm_xrp_reserve = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.XRPL_AMM_XRP_RESERVE,
    )
    xrpl_amm_quote_reserve = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.XRPL_AMM_QUOTE_RESERVE,
    )
    xrpl_dex_bid_funded = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.XRPL_DEX_BID_FUNDED,
    )
    xrpl_dex_ask_funded = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.XRPL_DEX_ASK_FUNDED,
    )
    xrpl_amm_slippage_center = _center_metric(
        eligible_observations,
        LiquidityMetricKind.XRPL_AMM_SLIPPAGE_10K_BPS,
    )
    xrpl_dex_spread_center = _center_metric(
        eligible_observations,
        LiquidityMetricKind.XRPL_DEX_SPREAD_BPS,
    )
    exchange_inflow_xrp = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.EXCHANGE_INFLOW_XRP,
    )
    exchange_outflow_xrp = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.EXCHANGE_OUTFLOW_XRP,
    )
    etf_net_flow_usd = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.ETF_NET_FLOW_USD,
    )
    whale_long_usd = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.WHALE_LONG_USD,
    )
    whale_short_usd = _sum_metric(
        eligible_observations,
        LiquidityMetricKind.WHALE_SHORT_USD,
    )

    if len(observed_providers) < selected_policy.minimum_observed_provider_count:
        quality_flags.append("OBSERVED_PROVIDER_COVERAGE_INSUFFICIENT")
    if not eligible_clusters:
        quality_flags.append("LIQUIDATION_CLUSTER_NO_DATA")
    if not primary:
        quality_flags.append("PRIMARY_OBSERVED_NO_DATA")
    if inferred_providers:
        quality_flags.append("INFERRED_MODEL_PRESENT")
    if stale_observation_count:
        quality_flags.append("STALE_OBSERVATIONS_REJECTED")
    if stale_cluster_count:
        quality_flags.append("STALE_CLUSTERS_REJECTED")

    point_in_time_eligible = (
        len(observed_providers) >= selected_policy.minimum_observed_provider_count
        and bool(primary)
    )

    payload = {
        "symbol": target_symbol,
        "prediction_time": prediction.isoformat(),
        "reference_price": price,
        "observed_provider_set": list(observed_providers),
        "inferred_provider_set": list(inferred_providers),
        "primary_observed_count": len(primary),
        "aggregated_observed_count": len(aggregated),
        "inferred_count": len(inferred) + len(eligible_clusters),
        "stale_observation_count": stale_observation_count,
        "stale_cluster_count": stale_cluster_count,
        "cex_bid_depth_usd": cex_bid_depth if cex_bid_depth > 0 else None,
        "cex_ask_depth_usd": cex_ask_depth if cex_ask_depth > 0 else None,
        "cex_depth_imbalance": depth_imbalance,
        "open_interest_usd": open_interest_center,
        "open_interest_delta_usd": open_interest_delta_center,
        "open_interest_velocity_usd_per_min": open_interest_velocity_center,
        "funding_rate": funding_center,
        "basis_bps": basis_center,
        "taker_buy_sell_ratio": taker_ratio_center,
        "executed_long_liquidations_usd": executed_long,
        "executed_short_liquidations_usd": executed_short,
        "executed_liquidation_imbalance": executed_imbalance,
        "xrpl_amm_xrp_reserve": xrpl_amm_xrp_reserve,
        "xrpl_amm_quote_reserve": xrpl_amm_quote_reserve,
        "xrpl_dex_bid_funded": xrpl_dex_bid_funded,
        "xrpl_dex_ask_funded": xrpl_dex_ask_funded,
        "xrpl_amm_slippage_10k_bps": xrpl_amm_slippage_center,
        "xrpl_dex_spread_bps": xrpl_dex_spread_center,
        "exchange_inflow_xrp": exchange_inflow_xrp,
        "exchange_outflow_xrp": exchange_outflow_xrp,
        "etf_net_flow_usd": etf_net_flow_usd,
        "whale_long_usd": whale_long_usd,
        "whale_short_usd": whale_short_usd,
        "liquidation_bands": [
            {
                "band_pct": item.band_pct,
                "long_liquidation_notional_below_usd": item.long_liquidation_notional_below_usd,
                "short_liquidation_notional_above_usd": item.short_liquidation_notional_above_usd,
            }
            for item in bands
        ],
        "nearest_long_liquidation_distance_pct": nearest_long,
        "nearest_short_liquidation_distance_pct": nearest_short,
        "inferred_liquidation_bias": inferred_bias,
        "cluster_to_observed_depth_ratio": cluster_to_depth,
        "point_in_time_eligible": point_in_time_eligible,
        "quality_flags": sorted(set(quality_flags)),
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(payload).encode()).hexdigest()
    return LiquidityLiquidationState(
        state_id=f"liquidity-liquidation-state:sha256:{digest}",
        state_sha256=digest,
        symbol=target_symbol,
        prediction_time=prediction,
        reference_price=price,
        observed_provider_set=observed_providers,
        inferred_provider_set=inferred_providers,
        primary_observed_count=len(primary),
        aggregated_observed_count=len(aggregated),
        inferred_count=len(inferred) + len(eligible_clusters),
        stale_observation_count=stale_observation_count,
        stale_cluster_count=stale_cluster_count,
        cex_bid_depth_usd=cex_bid_depth if cex_bid_depth > 0 else None,
        cex_ask_depth_usd=cex_ask_depth if cex_ask_depth > 0 else None,
        cex_depth_imbalance=depth_imbalance,
        open_interest_usd=open_interest_center,
        open_interest_delta_usd=open_interest_delta_center,
        open_interest_velocity_usd_per_min=open_interest_velocity_center,
        funding_rate=funding_center,
        basis_bps=basis_center,
        taker_buy_sell_ratio=taker_ratio_center,
        executed_long_liquidations_usd=executed_long,
        executed_short_liquidations_usd=executed_short,
        executed_liquidation_imbalance=executed_imbalance,
        xrpl_amm_xrp_reserve=xrpl_amm_xrp_reserve,
        xrpl_amm_quote_reserve=xrpl_amm_quote_reserve,
        xrpl_dex_bid_funded=xrpl_dex_bid_funded,
        xrpl_dex_ask_funded=xrpl_dex_ask_funded,
        xrpl_amm_slippage_10k_bps=xrpl_amm_slippage_center,
        xrpl_dex_spread_bps=xrpl_dex_spread_center,
        exchange_inflow_xrp=exchange_inflow_xrp,
        exchange_outflow_xrp=exchange_outflow_xrp,
        etf_net_flow_usd=etf_net_flow_usd,
        whale_long_usd=whale_long_usd,
        whale_short_usd=whale_short_usd,
        liquidation_bands=tuple(bands),
        nearest_long_liquidation_distance_pct=nearest_long,
        nearest_short_liquidation_distance_pct=nearest_short,
        inferred_liquidation_bias=inferred_bias,
        cluster_to_observed_depth_ratio=cluster_to_depth,
        point_in_time_eligible=point_in_time_eligible,
        quality_flags=tuple(sorted(set(quality_flags))),
    )
