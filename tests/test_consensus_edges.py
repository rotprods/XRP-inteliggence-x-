from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.consensus import consensus_close
from xrp_regime_engine.models import Candle, DataFlag, Provenance

pytestmark = [pytest.mark.unit, pytest.mark.contract]

NOW = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)


def c(provider: str, close: float, *, minutes_ago: int = 0, asset: str = "XRP_USD", interval: str = "1h") -> Candle:
    close_time = NOW - timedelta(minutes=minutes_ago)
    return Candle(
        asset=asset,
        interval=interval,
        open_time=close_time - timedelta(hours=1),
        close_time=close_time,
        open=close,
        high=close * 1.001,
        low=close * 0.999,
        close=close,
        volume=1,
        provenance=Provenance(
            provider=provider,
            observed_at=close_time,
            available_at=close_time,
            fetched_at=NOW,
        ),
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "no candles"),
        ({"max_age_seconds": 0}, "max_age_seconds"),
        ({"min_provider_count": 1}, "min_provider_count"),
        ({"max_relative_spread": 0}, "spread thresholds"),
        ({"outlier_deviation": 0}, "spread thresholds"),
    ],
)
def test_consensus_rejects_invalid_configuration(kwargs: dict[str, float | int], message: str) -> None:
    candles = [] if not kwargs else [c("a", 1), c("b", 1)]
    with pytest.raises(ValueError, match=message):
        consensus_close(candles, now=NOW, **kwargs)


def test_mixed_asset_or_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="same asset"):
        consensus_close([c("a", 1), c("b", 1, asset="BTC_USD")], now=NOW)
    with pytest.raises(ValueError, match="same asset"):
        consensus_close([c("a", 1), c("b", 1, interval="4h")], now=NOW)


def test_alignment_conflict_blocks_value() -> None:
    result = consensus_close(
        [c("a", 1.0), c("b", 1.001, minutes_ago=10)],
        now=NOW,
        alignment_tolerance_seconds=300,
        max_age_seconds=3600,
    )
    assert result.valid is False
    assert result.value is None
    assert DataFlag.CONFLICT in result.flags


def test_duplicate_provider_uses_latest_close_time() -> None:
    result = consensus_close(
        [c("a", 99, minutes_ago=2), c("a", 1.0), c("b", 1.001)],
        now=NOW,
    )
    assert result.valid
    assert result.input_provider_count == 2
    assert result.value is not None and result.value < 1.01


def test_three_source_outlier_can_leave_insufficient_coverage() -> None:
    result = consensus_close(
        [c("a", 1.0), c("b", 2.0), c("c", 4.0)],
        now=NOW,
        min_provider_count=3,
        outlier_deviation=0.2,
    )
    assert not result.valid
    assert DataFlag.MISSING in result.flags


def test_stale_boundary_is_inclusive() -> None:
    result = consensus_close(
        [c("a", 1.0, minutes_ago=60), c("b", 1.001, minutes_ago=60)],
        now=NOW,
        max_age_seconds=3600,
    )
    assert result.valid
    assert DataFlag.STALE not in result.flags


def test_provider_order_does_not_change_consensus() -> None:
    candles = [c("a", 1.0), c("b", 1.001), c("c", 0.999)]
    left = consensus_close(candles, now=NOW)
    right = consensus_close(list(reversed(candles)), now=NOW)
    assert left.value == right.value
    assert left.provider_count == right.provider_count
    assert set(left.providers) == set(right.providers)


def test_older_duplicate_after_newer_is_ignored() -> None:
    newer = c("a", 1.0)
    older = c("a", 999.0, minutes_ago=1)
    result = consensus_close([newer, older, c("b", 1.001)], now=NOW)
    assert result.valid
    assert result.value is not None and result.value < 1.01


def test_consensus_rejects_future_market_data() -> None:
    future = NOW + timedelta(seconds=1)
    items = [c("a", 1.0), c("b", 1.001)]
    future_item = items[0].model_copy(
        update={
            "open_time": future - timedelta(hours=1),
            "close_time": future,
            "provenance": items[0].provenance.model_copy(
                update={"observed_at": future, "available_at": future, "fetched_at": future}
            ),
        }
    )
    result = consensus_close([future_item, items[1]], now=NOW)
    assert result.valid is False
    assert result.value is None
    assert DataFlag.INVALID in result.flags


def test_consensus_rejects_naive_now_and_negative_alignment_tolerance() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        consensus_close([c("a", 1.0), c("b", 1.001)], now=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="alignment_tolerance_seconds"):
        consensus_close(
            [c("a", 1.0), c("b", 1.001)],
            now=NOW,
            alignment_tolerance_seconds=-1,
        )
