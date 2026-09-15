from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, strategies as st  # type: ignore[import-not-found]

from xrp_regime_engine.consensus import consensus_close
from xrp_regime_engine.models import Candle, Horizon, Provenance
from xrp_regime_engine.regime import score_regime

pytestmark = [pytest.mark.property, pytest.mark.unit]
NOW = datetime(2026, 8, 28, 9, tzinfo=UTC)


def candle(provider: str, close: float) -> Candle:
    return Candle(
        asset="XRP_USD",
        interval="1h",
        open_time=NOW - timedelta(hours=1),
        close_time=NOW,
        open=close,
        high=close * 1.001,
        low=close * 0.999,
        close=close,
        volume=1,
        provenance=Provenance(
            provider=provider,
            observed_at=NOW,
            available_at=NOW,
            fetched_at=NOW,
        ),
    )


@given(st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False))
def test_single_provider_never_becomes_valid_consensus(price: float) -> None:
    result = consensus_close([candle("a", price)], now=NOW)
    assert result.valid is False
    assert result.value is None
    assert result.provider_count == 1


@given(
    center=st.floats(min_value=0.1, max_value=1000, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=0.0, max_value=0.005, allow_nan=False, allow_infinity=False),
)
def test_provider_permutation_preserves_consensus(center: float, delta: float) -> None:
    candles = [
        candle("a", center),
        candle("b", center * (1 + delta)),
        candle("c", center * (1 - delta)),
    ]
    left = consensus_close(candles, now=NOW)
    right = consensus_close(list(reversed(candles)), now=NOW)
    assert left.valid == right.valid
    assert left.value == right.value
    assert left.provider_count == right.provider_count


@given(
    macro=st.floats(min_value=-1, max_value=1, allow_nan=False, allow_infinity=False),
    crypto=st.floats(min_value=-1, max_value=1, allow_nan=False, allow_infinity=False),
    xrp=st.floats(min_value=-1, max_value=1, allow_nan=False, allow_infinity=False),
)
def test_regime_scores_always_respect_numeric_bounds(macro: float, crypto: float, xrp: float) -> None:
    features = {
        "feature_cadence_seconds": 86400.0,
        "provider_agreement": 1.0,
        "freshness_score": 1.0,
        "source_coverage": 1.0,
        "ndx_return_20d": macro,
        "dxy_return_20d": -macro,
        "us10y_change_20d": -macro,
        "vix_z_20d": -macro,
        "btc_return_7d": crypto,
        "btc_return_30d": crypto,
        "eth_btc_return_7d": crypto,
        "btc_dominance_change_20d": -crypto,
        "xrp_return_7d": xrp,
        "xrp_return_30d": xrp,
        "xrp_btc_return_7d": xrp,
        "xrp_btc_return_30d": xrp,
        "xrp_ma100_distance": xrp,
        "funding_z": 0.0,
        "oi_price_divergence": 0.0,
        "liquidation_impulse": 0.0,
        "xrpl_activity_z": 0.0,
        "xrp_rsi_14": 50.0,
        "xrp_ma20_distance": 0.0,
        "xrp_vol_30d": 0.2,
    }
    snapshot = score_regime(features, Horizon.D1)
    assert 0 <= snapshot.bull_score <= 100
    assert 0 <= snapshot.bear_score <= 100
    assert snapshot.bull_score + snapshot.bear_score == pytest.approx(100.0, abs=0.02)
    assert 0 <= snapshot.confidence <= 1
    assert 0 <= snapshot.data_confidence <= 1
    assert 0 <= snapshot.model_confidence <= 1
    assert 0 <= snapshot.directional_conviction <= 1


@given(st.lists(st.floats(min_value=0.1, max_value=10, allow_nan=False, allow_infinity=False), min_size=2, max_size=6))
def test_duplicate_provider_cannot_inflate_independent_coverage(prices: list[float]) -> None:
    candles = [candle("same-provider", value) for value in prices]
    result = consensus_close(candles, now=NOW)
    assert result.input_provider_count == 1
    assert result.provider_count <= 1
    assert result.valid is False


@given(
    open_price=st.floats(min_value=0.0001, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    close_ratio=st.floats(min_value=0.5, max_value=1.5, allow_nan=False, allow_infinity=False),
    padding=st.floats(min_value=0.0, max_value=0.25, allow_nan=False, allow_infinity=False),
)
def test_valid_ohlc_geometry_round_trips(open_price: float, close_ratio: float, padding: float) -> None:
    close_price = open_price * close_ratio
    low = min(open_price, close_price) * (1 - padding)
    # Keep strict positivity even when Hypothesis picks padding very close to one.
    low = max(low, min(open_price, close_price) * 0.001)
    high = max(open_price, close_price) * (1 + padding)
    item = Candle(
        asset="XRP_USD",
        interval="1h",
        open_time=NOW - timedelta(hours=1),
        close_time=NOW,
        open=open_price,
        high=high,
        low=low,
        close=close_price,
        volume=0.0,
        provenance=Provenance(
            provider="generated",
            observed_at=NOW,
            available_at=NOW,
            fetched_at=NOW,
        ),
    )
    assert item.low <= min(item.open, item.close)
    assert item.high >= max(item.open, item.close)


@given(
    prices=st.lists(
        st.floats(min_value=0.1, max_value=1000, allow_nan=False, allow_infinity=False),
        min_size=2,
        max_size=6,
    )
)
def test_consensus_never_counts_duplicate_provider_as_independent(prices: list[float]) -> None:
    duplicated = [candle("same", price) for price in prices]
    duplicated.append(candle("other", prices[0]))
    result = consensus_close(duplicated, now=NOW, max_relative_spread=10.0)
    assert result.input_provider_count == 2
    assert result.provider_count <= 2


@given(
    future_seconds=st.integers(min_value=1, max_value=86_400),
    price=st.floats(min_value=0.1, max_value=1000, allow_nan=False, allow_infinity=False),
)
def test_future_candle_can_never_produce_valid_consensus(future_seconds: int, price: float) -> None:
    future = NOW + timedelta(seconds=future_seconds)
    future_candle = Candle(
        asset="XRP_USD",
        interval="1h",
        open_time=future - timedelta(hours=1),
        close_time=future,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1,
        provenance=Provenance(
            provider="future",
            observed_at=future,
            available_at=future,
            fetched_at=future,
        ),
    )
    result = consensus_close([future_candle, candle("current", price)], now=NOW)
    assert result.valid is False
    assert result.value is None


@given(
    quality=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_data_quality_changes_confidence_not_directional_score(quality: float) -> None:
    base = {
        "feature_cadence_seconds": 86400.0,
        "provider_agreement": 1.0,
        "freshness_score": 1.0,
        "source_coverage": 1.0,
        "ndx_return_20d": 0.03,
        "dxy_return_20d": -0.01,
        "us10y_change_20d": -0.01,
        "vix_z_20d": -0.2,
        "btc_return_7d": 0.04,
        "btc_return_30d": 0.10,
        "eth_btc_return_7d": 0.01,
        "btc_dominance_change_20d": -0.01,
        "xrp_return_7d": 0.05,
        "xrp_return_30d": 0.15,
        "xrp_btc_return_7d": 0.02,
        "xrp_btc_return_30d": 0.08,
        "xrp_ma100_distance": 0.05,
        "funding_z": 0.0,
        "oi_price_divergence": 0.0,
        "liquidation_impulse": 0.0,
        "xrpl_activity_z": 0.0,
        "xrp_rsi_14": 55.0,
        "xrp_ma20_distance": 0.02,
        "xrp_vol_30d": 0.2,
    }
    reference = score_regime(base, Horizon.D1)
    degraded = dict(base)
    degraded.update(
        provider_agreement=quality,
        freshness_score=quality,
        source_coverage=quality,
    )
    candidate = score_regime(degraded, Horizon.D1)
    assert candidate.bull_score == reference.bull_score
    assert candidate.data_confidence <= reference.data_confidence
