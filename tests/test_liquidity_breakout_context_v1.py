from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.liquidity_breakout_context_v1 import (
    LiquidityBreakoutPolicy,
    LiquidityBreakoutPosture,
    assess_liquidity_breakout_context,
)
from xrp_regime_engine.liquidity_liquidation_plane_v1 import (
    EvidenceAuthority,
    LiquidationCluster,
    LiquidationClusterSide,
    LiquidityMetricKind,
    LiquidityObservation,
    build_liquidity_liquidation_state,
)

T0 = datetime(2026, 9, 22, 15, 0, tzinfo=UTC)
PAYLOAD = sha256(b"payload").hexdigest()


def obs(
    ident: str,
    metric: LiquidityMetricKind,
    value: float,
    *,
    provider: str = "Binance",
) -> LiquidityObservation:
    return LiquidityObservation(
        observation_id=ident,
        provider=provider,
        venue=provider,
        symbol="XRPUSDT",
        metric=metric,
        value=value,
        unit="USD",
        observed_at=T0 - timedelta(seconds=10),
        available_at=T0 - timedelta(seconds=9),
        fetched_at=T0 - timedelta(seconds=8),
        authority=EvidenceAuthority.PRIMARY_OBSERVED,
        source_id=f"source:{ident}",
        payload_sha256=PAYLOAD,
    )


def cluster(
    ident: str,
    side: LiquidationClusterSide,
    lower: float,
    upper: float,
    notional: float,
) -> LiquidationCluster:
    return LiquidationCluster(
        cluster_id=ident,
        provider="CoinGlass",
        symbol="XRPUSDT",
        side=side,
        lower_price=lower,
        upper_price=upper,
        estimated_notional_usd=notional,
        observed_at=T0 - timedelta(seconds=20),
        available_at=T0 - timedelta(seconds=19),
        fetched_at=T0 - timedelta(seconds=18),
        model_id="heatmap-model3",
        source_id=f"source:{ident}",
        payload_sha256=PAYLOAD,
        confidence=0.9,
    )


def state(
    *,
    bid: float = 2_000_000,
    ask: float = 1_000_000,
    taker: float = 1.25,
    oi_delta: float | None = -1_000_000,
    oi_velocity: float | None = -100_000,
    funding: float | None = 0.0001,
    basis: float | None = 10,
    slippage: float | None = 20,
    dex_spread: float | None = 20,
    clusters: tuple[LiquidationCluster, ...] = (),
    second_provider: bool = True,
):
    observations = [
        obs("bid", LiquidityMetricKind.CEX_BID_DEPTH_USD, bid),
        obs("ask", LiquidityMetricKind.CEX_ASK_DEPTH_USD, ask),
        obs("taker", LiquidityMetricKind.TAKER_BUY_SELL_RATIO, taker),
    ]
    if second_provider:
        observations.append(
            obs(
                "kraken-depth",
                LiquidityMetricKind.CEX_BID_DEPTH_USD,
                250_000,
                provider="Kraken",
            )
        )
    if oi_delta is not None:
        observations.append(
            obs(
                "oi-delta",
                LiquidityMetricKind.OPEN_INTEREST_DELTA_USD,
                oi_delta,
            )
        )
    if oi_velocity is not None:
        observations.append(
            obs(
                "oi-velocity",
                LiquidityMetricKind.OPEN_INTEREST_VELOCITY_USD_PER_MIN,
                oi_velocity,
            )
        )
    if funding is not None:
        observations.append(obs("funding", LiquidityMetricKind.FUNDING_RATE, funding))
    if basis is not None:
        observations.append(obs("basis", LiquidityMetricKind.BASIS_BPS, basis))
    if slippage is not None:
        observations.append(
            obs(
                "slippage",
                LiquidityMetricKind.XRPL_AMM_SLIPPAGE_10K_BPS,
                slippage,
                provider="XRPL",
            )
        )
    if dex_spread is not None:
        observations.append(
            obs(
                "dex-spread",
                LiquidityMetricKind.XRPL_DEX_SPREAD_BPS,
                dex_spread,
                provider="XRPL",
            )
        )
    return build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=tuple(observations),
        liquidation_clusters=clusters,
    )


def test_spot_supportive_requires_flow_depth_and_no_leverage_expansion() -> None:
    context = assess_liquidity_breakout_context(state())
    assert context.posture is LiquidityBreakoutPosture.SPOT_SUPPORTIVE
    assert context.spot_support_confirmed is True
    assert context.leverage_expansion is False
    assert context.funding_dangerous is False
    assert context.onchain_liquidity_healthy is True
    assert "BID_DEPTH_IMBALANCE_SUPPORTIVE" in context.support
    assert "TAKER_FLOW_BUY_DOMINANT" in context.support
    assert context.decision_authority is False
    assert context.execution_weight == 0.0


def test_leverage_led_when_oi_delta_and_velocity_expand() -> None:
    context = assess_liquidity_breakout_context(
        state(
            oi_delta=5_000_000,
            oi_velocity=500_000,
        )
    )
    assert context.posture is LiquidityBreakoutPosture.LEVERAGE_LED
    assert context.leverage_expansion is True
    assert "OPEN_INTEREST_EXPANDING" in context.support


def test_leverage_plus_dangerous_funding_is_fragile() -> None:
    context = assess_liquidity_breakout_context(
        state(
            oi_delta=5_000_000,
            oi_velocity=500_000,
            funding=0.001,
            basis=40,
        )
    )
    assert context.posture is LiquidityBreakoutPosture.FRAGILE
    assert context.funding_dangerous is True
    assert "FUNDING_OR_BASIS_CROWDED" in context.contradictions


def test_short_liquidation_fuel_is_model_derived_not_execution_authority() -> None:
    context = assess_liquidity_breakout_context(
        state(
            clusters=(
                cluster(
                    "short",
                    LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
                    1.57,
                    1.59,
                    10_000_000,
                ),
                cluster(
                    "long",
                    LiquidationClusterSide.LONGS_LIQUIDATE_BELOW,
                    1.40,
                    1.42,
                    1_000_000,
                ),
            )
        )
    )
    assert context.posture is LiquidityBreakoutPosture.SHORT_LIQUIDATION_FUEL
    assert context.short_liquidation_fuel_present is True
    assert "INFERRED_SHORT_LIQUIDATION_FUEL_NEARBY" in context.support
    assert context.decision_authority is False


def test_nearby_long_liquidation_cluster_creates_fragility() -> None:
    context = assess_liquidity_breakout_context(
        state(
            clusters=(
                cluster(
                    "long",
                    LiquidationClusterSide.LONGS_LIQUIDATE_BELOW,
                    1.53,
                    1.55,
                    12_000_000,
                ),
                cluster(
                    "short",
                    LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
                    1.80,
                    1.85,
                    1_000_000,
                ),
            )
        )
    )
    assert context.posture is LiquidityBreakoutPosture.FRAGILE
    assert context.long_liquidation_flush_risk is True
    assert "INFERRED_LONG_LIQUIDATION_FLUSH_RISK_NEARBY" in context.contradictions


def test_thin_xrpl_effective_liquidity_is_a_contradiction() -> None:
    context = assess_liquidity_breakout_context(
        state(
            slippage=100,
            dex_spread=90,
        )
    )
    assert context.onchain_liquidity_healthy is False
    assert "XRPL_EFFECTIVE_LIQUIDITY_THIN" in context.contradictions


def test_missing_metrics_are_explicit() -> None:
    context = assess_liquidity_breakout_context(
        state(
            oi_delta=None,
            oi_velocity=None,
            funding=None,
            basis=None,
            slippage=None,
            dex_spread=None,
        )
    )
    assert context.leverage_expansion is None
    assert context.funding_dangerous is None
    assert context.onchain_liquidity_healthy is None
    assert "OPEN_INTEREST_DELTA_OR_VELOCITY" in context.missing
    assert "FUNDING_AND_BASIS" in context.missing
    assert "XRPL_EFFECTIVE_LIQUIDITY" in context.missing


def test_insufficient_observed_provider_coverage_forces_no_data() -> None:
    context = assess_liquidity_breakout_context(state(second_provider=False))
    assert context.posture is LiquidityBreakoutPosture.NO_DATA
    assert "LIQUIDITY_PLANE_NOT_POINT_IN_TIME_ELIGIBLE" in context.contradictions


def test_non_supportive_flow_is_neutral_not_bullish() -> None:
    context = assess_liquidity_breakout_context(
        state(
            bid=500_000,
            ask=2_000_000,
            taker=0.8,
        )
    )
    assert context.spot_support_confirmed is False
    assert context.posture is LiquidityBreakoutPosture.NEUTRAL
    assert "BID_DEPTH_IMBALANCE_NOT_SUPPORTIVE" in context.contradictions
    assert "TAKER_FLOW_NOT_BUY_DOMINANT" in context.contradictions


def test_policy_validation_fail_closed() -> None:
    with pytest.raises(ValueError, match="minimum_depth_imbalance"):
        LiquidityBreakoutPolicy(minimum_depth_imbalance=2)
    with pytest.raises(ValueError, match="positive"):
        LiquidityBreakoutPolicy(minimum_taker_buy_sell_ratio=0)
    with pytest.raises(ValueError, match="cannot be negative"):
        LiquidityBreakoutPolicy(dangerous_basis_bps=-1)
    with pytest.raises(ValueError, match="within \[0, 1\]"):
        LiquidityBreakoutPolicy(liquidation_bias_threshold=2)
    with pytest.raises(ValueError, match="nearby_cluster_distance_pct"):
        LiquidityBreakoutPolicy(nearby_cluster_distance_pct=0)
