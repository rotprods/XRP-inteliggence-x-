from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.liquidity_breakout_context_v1 import (
    LiquidityBreakoutPolicy,
    assess_liquidity_breakout_context,
)
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
PAYLOAD = sha256(b"adversarial-payload").hexdigest()


def _observation(
    ident: str,
    *,
    provider: str = "Binance",
    venue: str | None = None,
    symbol: str = "XRPUSDT",
    metric: LiquidityMetricKind = LiquidityMetricKind.OPEN_INTEREST_USD,
    value: float = 1_000_000.0,
    observed_at: datetime = T0 - timedelta(seconds=10),
    available_at: datetime = T0 - timedelta(seconds=9),
    fetched_at: datetime = T0 - timedelta(seconds=8),
    confidence: float = 1.0,
    payload_sha256: str = PAYLOAD,
) -> LiquidityObservation:
    return LiquidityObservation(
        observation_id=ident,
        provider=provider,
        venue=venue or provider,
        symbol=symbol,
        metric=metric,
        value=value,
        unit="USD",
        observed_at=observed_at,
        available_at=available_at,
        fetched_at=fetched_at,
        authority=EvidenceAuthority.PRIMARY_OBSERVED,
        source_id=f"source:{ident}",
        payload_sha256=payload_sha256,
        confidence=confidence,
    )


def _cluster(ident: str, *, symbol: str = "XRPUSDT") -> LiquidationCluster:
    return LiquidationCluster(
        cluster_id=ident,
        provider="CoinGlass",
        symbol=symbol,
        side=LiquidationClusterSide.SHORTS_LIQUIDATE_ABOVE,
        lower_price=1.60,
        upper_price=1.65,
        estimated_notional_usd=1_000_000.0,
        observed_at=T0 - timedelta(seconds=20),
        available_at=T0 - timedelta(seconds=19),
        fetched_at=T0 - timedelta(seconds=18),
        model_id="heatmap-v1",
        source_id=f"source:{ident}",
        payload_sha256=PAYLOAD,
        confidence=0.9,
    )


def test_breakout_policy_rejects_remaining_unsafe_thresholds() -> None:
    with pytest.raises(ValueError, match="dangerous_positive_funding_rate"):
        LiquidityBreakoutPolicy(dangerous_positive_funding_rate=-1)
    with pytest.raises(ValueError, match="maximum_amm_slippage_10k_bps"):
        LiquidityBreakoutPolicy(maximum_amm_slippage_10k_bps=-1)
    with pytest.raises(ValueError, match="maximum_dex_spread_bps"):
        LiquidityBreakoutPolicy(maximum_dex_spread_bps=-1)


def test_breakout_context_marks_missing_depth_and_taker_explicitly() -> None:
    state = build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=(
            _observation("binance-oi"),
            _observation("kraken-oi", provider="Kraken"),
        ),
        liquidation_clusters=(),
    )
    assert state.point_in_time_eligible is True
    assert state.cex_depth_imbalance is None
    assert state.taker_buy_sell_ratio is None

    context = assess_liquidity_breakout_context(state)
    assert "CEX_DEPTH_IMBALANCE" in context.missing
    assert "TAKER_BUY_SELL_RATIO" in context.missing
    assert context.spot_support_confirmed is None
    assert context.decision_authority is False
    assert context.execution_weight == 0.0


def test_observation_validation_rejects_invalid_primitive_inputs() -> None:
    naive = datetime(2026, 9, 22, 15, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        _observation(
            "naive-time",
            observed_at=naive,
            available_at=naive + timedelta(seconds=1),
            fetched_at=naive + timedelta(seconds=2),
        )
    with pytest.raises(ValueError, match="finite"):
        _observation("nan-value", value=float("nan"))
    with pytest.raises(ValueError, match="provider is required"):
        _observation("empty-provider", provider=" ")
    with pytest.raises(ValueError, match="SHA-256"):
        _observation("bad-digest", payload_sha256="bad")
    with pytest.raises(ValueError, match="confidence"):
        _observation("bad-confidence", confidence=2.0)


def test_plane_policy_rejects_remaining_invalid_thresholds() -> None:
    with pytest.raises(ValueError, match="max_cluster_age_seconds"):
        LiquidityPlanePolicy(max_cluster_age_seconds=0)
    with pytest.raises(ValueError, match="minimum_primary_market_venue_count"):
        LiquidityPlanePolicy(minimum_primary_market_venue_count=0)


def test_build_rejects_nonpositive_reference_price() -> None:
    with pytest.raises(ValueError, match="reference_price must be positive"):
        build_liquidity_liquidation_state(
            symbol="XRPUSDT",
            reference_price=0,
            prediction_time=T0,
            observations=(),
            liquidation_clusters=(),
        )


def test_foreign_symbol_evidence_is_ignored_before_aggregation() -> None:
    state = build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=(
            _observation("binance-oi"),
            _observation("kraken-oi", provider="Kraken"),
            _observation("btc-oi", provider="Coinbase", symbol="BTCUSD"),
        ),
        liquidation_clusters=(_cluster("btc-cluster", symbol="BTCUSDT"),),
    )
    assert state.point_in_time_eligible is True
    assert state.observed_provider_set == ("Binance", "Kraken")
    assert state.inferred_count == 0
    assert "Coinbase" not in state.observed_provider_set
    assert "CoinGlass" not in state.inferred_provider_set


def test_builder_rejects_corrupted_future_observed_at_defense_in_depth() -> None:
    future_observation = _observation("corrupted-observation")
    object.__setattr__(future_observation, "observed_at", T0 + timedelta(seconds=1))

    future_cluster = _cluster("corrupted-cluster")
    object.__setattr__(future_cluster, "observed_at", T0 + timedelta(seconds=1))

    state = build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=(
            _observation("binance-oi"),
            _observation("kraken-oi", provider="Kraken"),
            future_observation,
        ),
        liquidation_clusters=(future_cluster,),
    )
    assert state.point_in_time_eligible is True
    assert "FUTURE_OBSERVATION_REJECTED" in state.quality_flags
    assert "FUTURE_CLUSTER_REJECTED" in state.quality_flags
    assert state.primary_observed_count == 2
    assert state.inferred_count == 0
