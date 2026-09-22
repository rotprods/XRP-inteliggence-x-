from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from xrp_regime_engine.liquidity_liquidation_plane_v1 import LiquidityLiquidationState


class LiquidityBreakoutPosture(StrEnum):
    NO_DATA = "NO_DATA"
    SPOT_SUPPORTIVE = "SPOT_SUPPORTIVE"
    LEVERAGE_LED = "LEVERAGE_LED"
    SHORT_LIQUIDATION_FUEL = "SHORT_LIQUIDATION_FUEL"
    FRAGILE = "FRAGILE"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True, slots=True)
class LiquidityBreakoutPolicy:
    minimum_depth_imbalance: float = 0.10
    minimum_taker_buy_sell_ratio: float = 1.10
    dangerous_positive_funding_rate: float = 0.0005
    dangerous_basis_bps: float = 25.0
    liquidation_bias_threshold: float = 0.20
    nearby_cluster_distance_pct: float = 0.02
    maximum_amm_slippage_10k_bps: float = 50.0
    maximum_dex_spread_bps: float = 50.0

    def __post_init__(self) -> None:
        if not -1 <= self.minimum_depth_imbalance <= 1:
            raise ValueError("minimum_depth_imbalance must be within [-1, 1]")
        if self.minimum_taker_buy_sell_ratio <= 0:
            raise ValueError("minimum_taker_buy_sell_ratio must be positive")
        if self.dangerous_positive_funding_rate < 0:
            raise ValueError("dangerous_positive_funding_rate cannot be negative")
        if self.dangerous_basis_bps < 0:
            raise ValueError("dangerous_basis_bps cannot be negative")
        if not 0 <= self.liquidation_bias_threshold <= 1:
            raise ValueError("liquidation_bias_threshold must be within [0, 1]")
        if not 0 < self.nearby_cluster_distance_pct <= 1:
            raise ValueError("nearby_cluster_distance_pct must be within (0, 1]")
        if self.maximum_amm_slippage_10k_bps < 0:
            raise ValueError("maximum_amm_slippage_10k_bps cannot be negative")
        if self.maximum_dex_spread_bps < 0:
            raise ValueError("maximum_dex_spread_bps cannot be negative")


@dataclass(frozen=True, slots=True)
class LiquidityBreakoutContext:
    context_id: str
    context_sha256: str
    liquidity_state_id: str
    posture: LiquidityBreakoutPosture
    spot_support_confirmed: bool | None
    leverage_expansion: bool | None
    funding_dangerous: bool | None
    short_liquidation_fuel_present: bool | None
    long_liquidation_flush_risk: bool | None
    onchain_liquidity_healthy: bool | None
    support: tuple[str, ...]
    contradictions: tuple[str, ...]
    missing: tuple[str, ...]
    decision_authority: bool = False
    execution_weight: float = 0.0


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def assess_liquidity_breakout_context(
    state: LiquidityLiquidationState,
    *,
    policy: LiquidityBreakoutPolicy | None = None,
) -> LiquidityBreakoutContext:
    selected = policy or LiquidityBreakoutPolicy()
    support: list[str] = []
    contradictions: list[str] = []
    missing: list[str] = []

    if state.cex_depth_imbalance is None:
        depth_support: bool | None = None
        missing.append("CEX_DEPTH_IMBALANCE")
    else:
        depth_support = state.cex_depth_imbalance >= selected.minimum_depth_imbalance
        if depth_support:
            support.append("BID_DEPTH_IMBALANCE_SUPPORTIVE")
        else:
            contradictions.append("BID_DEPTH_IMBALANCE_NOT_SUPPORTIVE")

    if state.taker_buy_sell_ratio is None:
        taker_support: bool | None = None
        missing.append("TAKER_BUY_SELL_RATIO")
    else:
        taker_support = state.taker_buy_sell_ratio >= selected.minimum_taker_buy_sell_ratio
        if taker_support:
            support.append("TAKER_FLOW_BUY_DOMINANT")
        else:
            contradictions.append("TAKER_FLOW_NOT_BUY_DOMINANT")

    spot_support_confirmed = (
        depth_support and taker_support
        if depth_support is not None and taker_support is not None
        else None
    )

    if state.open_interest_delta_usd is None or state.open_interest_velocity_usd_per_min is None:
        leverage_expansion: bool | None = None
        missing.append("OPEN_INTEREST_DELTA_OR_VELOCITY")
    else:
        leverage_expansion = (
            state.open_interest_delta_usd > 0 and state.open_interest_velocity_usd_per_min > 0
        )
        if leverage_expansion:
            support.append("OPEN_INTEREST_EXPANDING")
        else:
            support.append("NO_OPEN_INTEREST_EXPANSION")

    if state.funding_rate is None and state.basis_bps is None:
        funding_dangerous: bool | None = None
        missing.append("FUNDING_AND_BASIS")
    else:
        funding_dangerous = (
            state.funding_rate is not None
            and state.funding_rate > selected.dangerous_positive_funding_rate
        ) or (state.basis_bps is not None and state.basis_bps > selected.dangerous_basis_bps)
        if funding_dangerous:
            contradictions.append("FUNDING_OR_BASIS_CROWDED")
        else:
            support.append("FUNDING_AND_BASIS_NOT_DANGEROUS")

    if (
        state.inferred_liquidation_bias is None
        or state.nearest_short_liquidation_distance_pct is None
    ):
        short_fuel: bool | None = None
        missing.append("SHORT_LIQUIDATION_CLUSTER")
    else:
        short_fuel = (
            state.inferred_liquidation_bias >= selected.liquidation_bias_threshold
            and state.nearest_short_liquidation_distance_pct <= selected.nearby_cluster_distance_pct
        )
        if short_fuel:
            support.append("INFERRED_SHORT_LIQUIDATION_FUEL_NEARBY")

    if (
        state.inferred_liquidation_bias is None
        or state.nearest_long_liquidation_distance_pct is None
    ):
        long_flush: bool | None = None
        missing.append("LONG_LIQUIDATION_CLUSTER")
    else:
        long_flush = (
            state.inferred_liquidation_bias <= -selected.liquidation_bias_threshold
            and state.nearest_long_liquidation_distance_pct <= selected.nearby_cluster_distance_pct
        )
        if long_flush:
            contradictions.append("INFERRED_LONG_LIQUIDATION_FLUSH_RISK_NEARBY")

    if state.xrpl_amm_slippage_10k_bps is None or state.xrpl_dex_spread_bps is None:
        onchain_healthy: bool | None = None
        missing.append("XRPL_EFFECTIVE_LIQUIDITY")
    else:
        onchain_healthy = (
            state.xrpl_amm_slippage_10k_bps <= selected.maximum_amm_slippage_10k_bps
            and state.xrpl_dex_spread_bps <= selected.maximum_dex_spread_bps
        )
        if onchain_healthy:
            support.append("XRPL_EFFECTIVE_LIQUIDITY_HEALTHY")
        else:
            contradictions.append("XRPL_EFFECTIVE_LIQUIDITY_THIN")

    if not state.point_in_time_eligible:
        posture = LiquidityBreakoutPosture.NO_DATA
        contradictions.append("LIQUIDITY_PLANE_NOT_POINT_IN_TIME_ELIGIBLE")
    elif long_flush is True or (leverage_expansion is True and funding_dangerous is True):
        posture = LiquidityBreakoutPosture.FRAGILE
    elif spot_support_confirmed is True and leverage_expansion is True:
        posture = LiquidityBreakoutPosture.LEVERAGE_LED
    elif spot_support_confirmed is True and short_fuel is True:
        posture = LiquidityBreakoutPosture.SHORT_LIQUIDATION_FUEL
    elif (
        spot_support_confirmed is True
        and leverage_expansion is False
        and funding_dangerous is False
    ):
        posture = LiquidityBreakoutPosture.SPOT_SUPPORTIVE
    else:
        posture = LiquidityBreakoutPosture.NEUTRAL

    payload = {
        "liquidity_state_id": state.state_id,
        "posture": posture.value,
        "spot_support_confirmed": spot_support_confirmed,
        "leverage_expansion": leverage_expansion,
        "funding_dangerous": funding_dangerous,
        "short_liquidation_fuel_present": short_fuel,
        "long_liquidation_flush_risk": long_flush,
        "onchain_liquidity_healthy": onchain_healthy,
        "support": sorted(set(support)),
        "contradictions": sorted(set(contradictions)),
        "missing": sorted(set(missing)),
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(payload).encode()).hexdigest()
    return LiquidityBreakoutContext(
        context_id=f"liquidity-breakout-context:sha256:{digest}",
        context_sha256=digest,
        liquidity_state_id=state.state_id,
        posture=posture,
        spot_support_confirmed=spot_support_confirmed,
        leverage_expansion=leverage_expansion,
        funding_dangerous=funding_dangerous,
        short_liquidation_fuel_present=short_fuel,
        long_liquidation_flush_risk=long_flush,
        onchain_liquidity_healthy=onchain_healthy,
        support=tuple(sorted(set(support))),
        contradictions=tuple(sorted(set(contradictions))),
        missing=tuple(sorted(set(missing))),
    )
