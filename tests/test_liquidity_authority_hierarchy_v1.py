from datetime import UTC, datetime, timedelta
from hashlib import sha256

from xrp_regime_engine.liquidity_breakout_context_v1 import (
    LiquidityBreakoutPosture,
    assess_liquidity_breakout_context,
)
from xrp_regime_engine.liquidity_liquidation_plane_v1 import (
    EvidenceAuthority,
    LiquidityMetricKind,
    LiquidityObservation,
    build_liquidity_liquidation_state,
)

T0 = datetime(2026, 9, 22, 15, 0, tzinfo=UTC)
PAYLOAD = sha256(b"authority-tier-adversarial").hexdigest()


def observation(
    ident: str,
    metric: LiquidityMetricKind,
    value: float,
    *,
    provider: str = "Binance",
    venue: str | None = None,
    authority: EvidenceAuthority = EvidenceAuthority.PRIMARY_OBSERVED,
) -> LiquidityObservation:
    return LiquidityObservation(
        observation_id=ident,
        provider=provider,
        venue=venue or provider,
        symbol="XRPUSDT",
        metric=metric,
        value=value,
        unit="USD",
        observed_at=T0 - timedelta(seconds=10),
        available_at=T0 - timedelta(seconds=9),
        fetched_at=T0 - timedelta(seconds=8),
        authority=authority,
        source_id=f"source:{ident}",
        payload_sha256=PAYLOAD,
        confidence=0.95,
        model_id="adversarial-model-v1" if authority is EvidenceAuthority.INFERRED_MODEL else None,
    )


def independent_primary_depth() -> tuple[LiquidityObservation, ...]:
    return (
        observation("binance-bid", LiquidityMetricKind.CEX_BID_DEPTH_USD, 2_000_000),
        observation("binance-ask", LiquidityMetricKind.CEX_ASK_DEPTH_USD, 1_000_000),
        observation(
            "kraken-bid",
            LiquidityMetricKind.CEX_BID_DEPTH_USD,
            1_000_000,
            provider="Kraken",
        ),
        observation(
            "kraken-ask",
            LiquidityMetricKind.CEX_ASK_DEPTH_USD,
            1_000_000,
            provider="Kraken",
        ),
    )


def build(*observations: LiquidityObservation):
    return build_liquidity_liquidation_state(
        symbol="XRPUSDT",
        reference_price=1.56,
        prediction_time=T0,
        observations=observations,
        liquidation_clusters=(),
    )


def test_primary_metric_wins_over_conflicting_aggregated_value() -> None:
    state = build(
        *independent_primary_depth(),
        observation("primary-oi", LiquidityMetricKind.OPEN_INTEREST_USD, 50_000_000),
        observation(
            "aggregate-oi",
            LiquidityMetricKind.OPEN_INTEREST_USD,
            500_000_000,
            provider="CoinGlass",
            venue="MULTI",
            authority=EvidenceAuthority.AGGREGATED_OBSERVED,
        ),
    )

    assert state.open_interest_usd == 50_000_000
    assert "AUTHORITY_FALLBACK:OPEN_INTEREST_USD:AGGREGATED_OBSERVED" not in state.quality_flags
    assert "PRIMARY_MARKET_AUTHORITY_FALLBACK" not in state.quality_flags
    assert state.point_in_time_eligible is True


def test_primary_metric_wins_over_conflicting_inferred_value() -> None:
    state = build(
        *independent_primary_depth(),
        observation("primary-taker", LiquidityMetricKind.TAKER_BUY_SELL_RATIO, 1.25),
        observation(
            "inferred-taker",
            LiquidityMetricKind.TAKER_BUY_SELL_RATIO,
            9.0,
            provider="ModelVendor",
            venue="MODEL",
            authority=EvidenceAuthority.INFERRED_MODEL,
        ),
    )

    assert state.taker_buy_sell_ratio == 1.25
    assert "AUTHORITY_FALLBACK:TAKER_BUY_SELL_RATIO:INFERRED_MODEL" not in state.quality_flags
    assert state.point_in_time_eligible is True


def test_aggregate_only_primary_market_metric_is_explicit_fallback_and_fails_closed() -> None:
    state = build(
        *independent_primary_depth(),
        observation(
            "aggregate-oi",
            LiquidityMetricKind.OPEN_INTEREST_USD,
            54_000_000,
            provider="CoinGlass",
            venue="MULTI",
            authority=EvidenceAuthority.AGGREGATED_OBSERVED,
        ),
    )

    assert state.open_interest_usd == 54_000_000
    assert "AUTHORITY_FALLBACK:OPEN_INTEREST_USD:AGGREGATED_OBSERVED" in state.quality_flags
    assert "PRIMARY_MARKET_AUTHORITY_FALLBACK" in state.quality_flags
    assert state.point_in_time_eligible is False
    assert assess_liquidity_breakout_context(state).posture is LiquidityBreakoutPosture.NO_DATA


def test_inferred_only_primary_market_metric_cannot_promote_breakout_posture() -> None:
    state = build(
        *independent_primary_depth(),
        observation(
            "model-taker",
            LiquidityMetricKind.TAKER_BUY_SELL_RATIO,
            10.0,
            provider="ModelVendor",
            venue="MODEL",
            authority=EvidenceAuthority.INFERRED_MODEL,
        ),
    )

    assert state.taker_buy_sell_ratio == 10.0
    assert "AUTHORITY_FALLBACK:TAKER_BUY_SELL_RATIO:INFERRED_MODEL" in state.quality_flags
    assert "PRIMARY_MARKET_AUTHORITY_FALLBACK" in state.quality_flags
    assert state.point_in_time_eligible is False
    context = assess_liquidity_breakout_context(state)
    assert context.posture is LiquidityBreakoutPosture.NO_DATA
    assert context.decision_authority is False
    assert context.execution_weight == 0.0


def test_inferred_context_metric_is_explicit_without_poisoning_primary_market_eligibility() -> None:
    state = build(
        *independent_primary_depth(),
        observation(
            "model-whale",
            LiquidityMetricKind.WHALE_LONG_USD,
            2_000_000,
            provider="ModelVendor",
            venue="MODEL",
            authority=EvidenceAuthority.INFERRED_MODEL,
        ),
    )

    assert state.whale_long_usd == 2_000_000
    assert "AUTHORITY_FALLBACK:WHALE_LONG_USD:INFERRED_MODEL" in state.quality_flags
    assert "PRIMARY_MARKET_AUTHORITY_FALLBACK" not in state.quality_flags
    assert state.point_in_time_eligible is True
