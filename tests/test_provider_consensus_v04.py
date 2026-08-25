from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from xrp_regime_engine.provider_consensus import (
    ConsensusUnavailable,
    ProviderObservation,
    build_consensus,
)


UTC = timezone.utc
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


def observation(
    provider: str,
    price: str,
    *,
    symbol: str = "XRP-USD",
    received_at: datetime = NOW,
) -> ProviderObservation:
    return ProviderObservation(
        provider=provider,
        symbol=symbol,
        price=Decimal(price),
        observed_at=received_at,
        received_at=received_at,
        payload_sha256=(provider * 64)[:64],
    )


def test_consensus_uses_independent_fresh_sources_and_rejects_outlier() -> None:
    result = build_consensus(
        (
            observation("coinbase", "1.000"),
            observation("kraken", "1.004"),
            observation("outlier", "2.000"),
        ),
        now=NOW,
    )
    assert result.symbol == "XRP-USD"
    assert result.providers == ("coinbase", "kraken")
    assert result.observation_count == 2
    assert result.price == Decimal("1.002")
    assert 0.0 <= result.confidence <= 1.0
    assert "outlier:outlier" in result.rejected


def test_consensus_rejects_duplicate_provider_without_double_counting() -> None:
    result = build_consensus(
        (
            observation("coinbase", "1.000"),
            observation("coinbase", "1.001"),
            observation("kraken", "1.002"),
        ),
        now=NOW,
    )
    assert result.providers == ("coinbase", "kraken")
    assert result.observation_count == 2
    assert "coinbase:duplicate" in result.rejected


def test_consensus_rejects_stale_future_and_symbol_mismatch() -> None:
    result = build_consensus(
        (
            observation("coinbase", "1.000"),
            observation("kraken", "1.002"),
            observation("stale", "1.001", received_at=NOW - timedelta(minutes=5)),
            observation("future", "1.001", received_at=NOW + timedelta(minutes=1)),
            observation("wrong", "1.001", symbol="XRP-USDT"),
        ),
        now=NOW,
        max_age_seconds=60,
    )
    assert result.providers == ("coinbase", "kraken")
    assert "stale:stale-or-future" in result.rejected
    assert "future:stale-or-future" in result.rejected
    assert "wrong:symbol-mismatch" in result.rejected


def test_consensus_fails_closed_with_one_source() -> None:
    with pytest.raises(ConsensusUnavailable, match="insufficient independent fresh sources"):
        build_consensus((observation("coinbase", "1.0"),), now=NOW)


def test_consensus_fails_closed_after_outlier_rejection() -> None:
    with pytest.raises(ConsensusUnavailable, match="after outlier rejection"):
        build_consensus(
            (observation("coinbase", "1.0"), observation("kraken", "2.0")),
            now=NOW,
            max_relative_deviation=Decimal("0.01"),
        )


def test_consensus_fails_closed_when_remaining_spread_is_too_wide() -> None:
    with pytest.raises(ConsensusUnavailable, match="provider disagreement"):
        build_consensus(
            (observation("coinbase", "1.00"), observation("kraken", "1.04")),
            now=NOW,
            max_relative_deviation=Decimal("0.10"),
            max_spread_ratio=Decimal("0.01"),
        )


def test_observation_requires_positive_price_and_aware_timestamps() -> None:
    with pytest.raises(ValueError, match="price must be positive"):
        observation("coinbase", "0")
    with pytest.raises(ValueError, match="timezone-aware"):
        ProviderObservation(
            provider="coinbase",
            symbol="XRP-USD",
            price=Decimal("1"),
            observed_at=datetime(2026, 1, 1),
            received_at=datetime(2026, 1, 1),
            payload_sha256="a" * 64,
        )


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="minimum_sources"):
        build_consensus(
            (observation("coinbase", "1"), observation("kraken", "1")),
            now=NOW,
            minimum_sources=1,
        )
