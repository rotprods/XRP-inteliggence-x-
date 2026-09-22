from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.liquidity_liquidation_plane_v1 import (
    EvidenceAuthority,
    LiquidationCluster,
    LiquidationClusterSide,
    LiquidityMetricKind,
    LiquidityObservation,
    LiquidityPlanePolicy,
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
    venue: str = "Binance",
    authority: EvidenceAuthority = EvidenceAuthority.PRIMARY_OBSERVED,
    observed_at: datetime = T0 - timedelta(seconds=10),
    available_at: datetime = T0 - timedelta(seconds=9),
    fetched_at: datetime = T0 - timedelta(seconds=8),
    model_id: str | None = None,
    pool_id: str | None = None,
) -> LiquidityObservation:
    return LiquidityObservation(
        observation_id=ident,
        provider=provider,
        venue=venue,
        symbol="XRPUSDT",
        metric=metric,
        value=value,
        unit="USD",
        observed_at=observed_at,
        available_at=available_at,
        fetched_at=fetched_at,
        authority=authority,
        source_id=f"source:{ident}",
        payload_sha256=PAYLOAD,
        confidence=0.95,
        pool_id=pool_id,
        model_id=model_id,
    )


def cluster(
    ident: str,
    side: LiquidationClusterSide,
    *,
    lower: float,
    upper: float,
    notional: float,
    confidence: float = 0.8,
    provider: str = "CoinGlass",
    observed_at: datetime = T0 - timedelta(seconds=20),
) -> LiquidationCluster:
    return LiquidationCluster(
        cluster_id=ident,
        provider=provider,
        symbol="XRPUSDT",
        side=side,
        lower_price=lower,
        upper_price=upper,
        estimated_notional_usd=notional,
        observed_at=observed_at,
        available_at=observed_at + timedelta(seconds=1),
        fetched_at=observed_at + timedelta(seconds=2),
        model_id="coinglass-heatmap-model3",
        source_id=f"source:{ident}",
        payload_sha256=PAYLOAD,
        confidence=confidence,
    )


def test_inferred_observation_requires_model_id() -> None:
    with pytest.raises(ValueError, match="requires model_id"):
        obs(
            "x",
            LiquidityMetricKind.WHALE_LONG_USD,
            1_000,
            authority=EvidenceAuthority.INFERRED_MODEL,
        )


def test_observation_and_cluster_temporal_contracts_fail_closed() -> None:
    with pytest.raises(ValueError, match="timestamps"):
        obs(
            "x",
            LiquidityMetricKind.OPEN_INTEREST_USD,
            100,
            observed_at=T0,
            available_at=T0 - timedelta(seconds=1),
            fetched_at=T0,
        )

    with pytest.raises(ValueError, match="cluster timestamps"):
        LiquidationCluster(
            cluster_id="c",
            provider="CoinGlass",
            symbol="XRPUSDT",
            side=LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
            lower_price=1.7,
            upper_price=1.8,
            estimated_notional_usd=1_000,
            observed_at=T0,
            available_at=T0 - timedelta(seconds=1),
            fetched_at=T0,
            model_id="m",
            source_id="s",
            payload_sha256=PAYLOAD,
            confidence=0.5,
        )


def test_full_state_separates_observed_and_inferred_evidence() -> None:
    observations = (
        obs("bid", LiquidityMetricKind.CEX_BID_DEPTH_USD, 2_000_000),
        obs("ask", LiquidityMetricKind.CEX_ASK_DEPTH_USD, 1_000_000),
        obs("oi1", LiquidityMetricKind.OPEN_INTEREST_USD, 50_000_000),
        obs(
            "oi2",
            LiquidityMetricKind.OPEN_INTEREST_USD,
            54_000_000,
            provider="CoinGlass",
            venue="MULTI",
            authority=EvidenceAuthority.AGGREGATED_OBSERVED,
        ),
        obs(
            "kraken-oi-delta",
            LiquidityMetricKind.OPEN_INTEREST_DELTA_USD,
            0,
            provider="Kraken",
            venue="Kraken",
        ),
        obs("funding", LiquidityMetricKind.FUNDING_RATE, 0.0002),
        obs("basis", LiquidityMetricKind.BASIS_BPS, 12),
        obs("taker", LiquidityMetricKind.TAKER_BUY_SELL_RATIO, 1.25),
        obs(
            "longliq",
            LiquidityMetricKind.EXECUTED_LONG_LIQUIDATIONS_USD,
            300_000,
        ),
        obs(
            "shortliq",
            LiquidityMetricKind.EXECUTED_SHORT_LIQUIDATIONS_USD,
            900_000,
        ),
        obs(
            "ammxrp",
            LiquidityMetricKind.XRPL_AMM_XRP_RESERVE,
            5_000_000,
            provider="XRPL",
            venue="XRPL_AMM",
            pool_id="amm:1",
        ),
        obs(
            "ammquote",
            LiquidityMetricKind.XRPL_AMM_QUOTE_RESERVE,
            8_000_000,
            provider="XRPL",
            venue="XRPL_AMM",
            pool_id="amm:1",
        ),
        obs(
            "dexbid",
            LiquidityMetricKind.XRPL_DEX_BID_FUNDED,
            1_500_000,
            provider="XRPL",
            venue="XRPL_DEX",
        ),
        obs(
            "dexask",
            LiquidityMetricKind.XRPL_DEX_ASK_FUNDED,
            1_000_000,
            provider="XRPL",
            venue="XRPL_DEX",
        ),
        obs(
            "whale",
            LiquidityMetricKind.WHALE_LONG_USD,
            2_000_000,
            provider="CoinGlass",
            venue="MULTI",
            authority=EvidenceAuthority.INFERRED_MODEL,
            model_id="whale-model-v1",
        ),
    )
    clusters = (
        cluster(
            "long-near",
            LiquidationClusterSide.LONGS_LIQUIDATE_BELOW,
            lower=1.50,
            upper=1.52,
            notional=4_000_000,
        ),
        cluster(
            "short-near",
            LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
            lower=1.58,
            upper=1.60,
            notional=8_000_000,
        ),
        cluster(
            "short-far",
            LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
            lower=1.70,
            upper=1.75,
            notional=10_000_000,
        ),
    )

    state = build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=observations,
        liquidation_clusters=clusters,
    )

    assert state.point_in_time_eligible is True
    assert state.observed_provider_set == ("Binance", "CoinGlass", "Kraken", "XRPL")
    assert state.primary_market_venue_set == ("Binance", "Kraken")
    assert state.inferred_provider_set == ("CoinGlass",)
    assert state.cex_bid_depth_usd == pytest.approx(2_000_000)
    assert state.cex_ask_depth_usd == pytest.approx(1_000_000)
    assert state.cex_depth_imbalance == pytest.approx(1 / 3)
    assert state.open_interest_usd == pytest.approx(50_000_000)
    assert state.funding_rate == pytest.approx(0.0002)
    assert state.basis_bps == pytest.approx(12)
    assert state.taker_buy_sell_ratio == pytest.approx(1.25)
    assert state.executed_liquidation_imbalance == pytest.approx(0.5)
    assert state.xrpl_amm_xrp_reserve == pytest.approx(5_000_000)
    assert state.xrpl_amm_quote_reserve == pytest.approx(8_000_000)
    assert state.xrpl_dex_bid_funded == pytest.approx(1_500_000)
    assert state.xrpl_dex_ask_funded == pytest.approx(1_000_000)
    assert state.whale_long_usd == pytest.approx(2_000_000)
    assert state.nearest_long_liquidation_distance_pct == pytest.approx((1.56 - 1.52) / 1.56)
    assert state.nearest_short_liquidation_distance_pct == pytest.approx((1.58 - 1.56) / 1.56)
    assert state.inferred_liquidation_bias > 0
    assert state.cluster_to_observed_depth_ratio == pytest.approx(22_000_000 / 3_000_000)
    assert "INFERRED_MODEL_PRESENT" in state.quality_flags
    assert state.decision_authority is False
    assert state.execution_weight == 0.0

    band_2 = next(item for item in state.liquidation_bands if item.band_pct == 0.02)
    assert band_2.short_liquidation_notional_above_usd == pytest.approx(8_000_000)
    assert band_2.long_liquidation_notional_below_usd == pytest.approx(0)


def test_future_data_never_contaminates_state() -> None:
    base = (
        obs("a", LiquidityMetricKind.CEX_BID_DEPTH_USD, 1_000_000),
        obs(
            "b",
            LiquidityMetricKind.CEX_ASK_DEPTH_USD,
            1_000_000,
            provider="Kraken",
            venue="Kraken",
        ),
    )
    future = obs(
        "future",
        LiquidityMetricKind.OPEN_INTEREST_USD,
        999_999_999,
        observed_at=T0 + timedelta(seconds=1),
        available_at=T0 + timedelta(seconds=2),
        fetched_at=T0 + timedelta(seconds=3),
    )

    first = build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=base,
        liquidation_clusters=(),
    )
    second = build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=(*base, future),
        liquidation_clusters=(),
    )

    assert first.open_interest_usd is None
    assert second.open_interest_usd is None
    assert second.cex_depth_imbalance == first.cex_depth_imbalance
    assert "FUTURE_OBSERVATION_REJECTED" in second.quality_flags


def test_low_confidence_and_future_clusters_are_rejected() -> None:
    observations = (
        obs("a", LiquidityMetricKind.CEX_BID_DEPTH_USD, 1_000_000),
        obs(
            "b",
            LiquidityMetricKind.CEX_ASK_DEPTH_USD,
            1_000_000,
            provider="Kraken",
            venue="Kraken",
        ),
    )
    low = cluster(
        "low",
        LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
        lower=1.58,
        upper=1.60,
        notional=99_000_000,
        confidence=0.1,
    )
    future = cluster(
        "future",
        LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
        lower=1.58,
        upper=1.60,
        notional=99_000_000,
        observed_at=T0 + timedelta(seconds=1),
    )

    state = build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=observations,
        liquidation_clusters=(low, future),
    )
    assert state.inferred_count == 0
    assert state.inferred_liquidation_bias is None
    assert "LOW_CONFIDENCE_CLUSTER_REJECTED" in state.quality_flags
    assert "FUTURE_CLUSTER_REJECTED" in state.quality_flags


def test_insufficient_observed_provider_coverage_fails_eligibility() -> None:
    state = build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=(obs("a", LiquidityMetricKind.CEX_BID_DEPTH_USD, 1_000_000),),
        liquidation_clusters=(),
    )
    assert state.point_in_time_eligible is False
    assert "OBSERVED_PROVIDER_COVERAGE_INSUFFICIENT" in state.quality_flags


def test_stale_observations_and_clusters_are_counted_not_used() -> None:
    stale_at = T0 - timedelta(minutes=10)
    state = build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=(
            obs(
                "stale",
                LiquidityMetricKind.CEX_BID_DEPTH_USD,
                9_000_000,
                observed_at=stale_at,
                available_at=stale_at + timedelta(seconds=1),
                fetched_at=stale_at + timedelta(seconds=2),
            ),
        ),
        liquidation_clusters=(
            cluster(
                "stale-cluster",
                LiquidationClusterSide.LONGS_LIQUIDATE_BELOW,
                lower=1.40,
                upper=1.45,
                notional=10_000_000,
                observed_at=stale_at,
            ),
        ),
    )
    assert state.stale_observation_count == 1
    assert state.stale_cluster_count == 1
    assert state.cex_bid_depth_usd is None
    assert "STALE_OBSERVATIONS_REJECTED" in state.quality_flags
    assert "STALE_CLUSTERS_REJECTED" in state.quality_flags


def test_duplicate_identity_and_policy_validation_fail_closed() -> None:
    duplicate = obs("same", LiquidityMetricKind.CEX_BID_DEPTH_USD, 1)
    with pytest.raises(ValueError, match="observation_id"):
        build_liquidity_liquidation_state(
            symbol="XRPUSDT",
            reference_price=1.56,
            prediction_time=T0,
            observations=(duplicate, duplicate),
            liquidation_clusters=(),
        )

    duplicate_cluster = cluster(
        "same-cluster",
        LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
        lower=1.6,
        upper=1.7,
        notional=100,
    )
    with pytest.raises(ValueError, match="cluster_id"):
        build_liquidity_liquidation_state(
            symbol="XRPUSDT",
            reference_price=1.56,
            prediction_time=T0,
            observations=(),
            liquidation_clusters=(duplicate_cluster, duplicate_cluster),
        )

    with pytest.raises(ValueError, match="positive"):
        LiquidityPlanePolicy(max_observation_age_seconds=0)
    with pytest.raises(ValueError, match="near_bands_pct"):
        LiquidityPlanePolicy(near_bands_pct=(0,))
    with pytest.raises(ValueError, match="minimum_observed_provider_count"):
        LiquidityPlanePolicy(minimum_observed_provider_count=0)
    with pytest.raises(ValueError, match="minimum_cluster_confidence"):
        LiquidityPlanePolicy(minimum_cluster_confidence=2)


def test_cluster_validation_fail_closed() -> None:
    with pytest.raises(ValueError, match="prices"):
        cluster(
            "bad",
            LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
            lower=2,
            upper=1,
            notional=1,
        )
    with pytest.raises(ValueError, match="cannot be negative"):
        cluster(
            "bad2",
            LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
            lower=1,
            upper=2,
            notional=-1,
        )
    with pytest.raises(ValueError, match="confidence"):
        cluster(
            "bad3",
            LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
            lower=1,
            upper=2,
            notional=1,
            confidence=2,
        )


def test_negative_non_negative_metric_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        obs(
            "bad-depth",
            LiquidityMetricKind.CEX_BID_DEPTH_USD,
            -1,
        )


def test_cluster_side_price_inconsistency_is_rejected_before_aggregation() -> None:
    observations = (
        obs("binance", LiquidityMetricKind.CEX_BID_DEPTH_USD, 1_000_000),
        obs(
            "kraken",
            LiquidityMetricKind.CEX_ASK_DEPTH_USD,
            1_000_000,
            provider="Kraken",
            venue="Kraken",
        ),
    )
    wrong_side = cluster(
        "wrong-side",
        LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
        lower=1.50,
        upper=1.55,
        notional=50_000_000,
    )
    state = build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=observations,
        liquidation_clusters=(wrong_side,),
    )
    assert state.inferred_count == 0
    assert state.inferred_liquidation_bias is None
    assert "CLUSTER_SIDE_PRICE_INCONSISTENT" in state.quality_flags


def test_xrpl_does_not_substitute_for_second_primary_market_venue() -> None:
    state = build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=(
            obs("binance", LiquidityMetricKind.CEX_BID_DEPTH_USD, 1_000_000),
            obs(
                "xrpl",
                LiquidityMetricKind.XRPL_AMM_XRP_RESERVE,
                5_000_000,
                provider="XRPL",
                venue="XRPL_AMM",
            ),
        ),
        liquidation_clusters=(),
    )
    assert state.observed_provider_set == ("Binance", "XRPL")
    assert state.primary_market_venue_set == ("Binance",)
    assert state.point_in_time_eligible is False
    assert "PRIMARY_MARKET_VENUE_COVERAGE_INSUFFICIENT" in state.quality_flags
