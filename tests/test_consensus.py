from datetime import UTC, datetime, timedelta

from xrp_regime_engine.consensus import consensus_close
from xrp_regime_engine.models import Candle, DataFlag, Provenance


def candle(provider: str, close: float, age_hours: int = 0) -> Candle:
    now = datetime.now(UTC)
    close_time = now - timedelta(hours=age_hours)
    provenance = Provenance(provider=provider, observed_at=close_time, available_at=close_time)
    return Candle(
        asset="XRP_USD",
        interval="1h",
        open_time=close_time - timedelta(hours=1),
        close_time=close_time,
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=100,
        provenance=provenance,
    )


def test_consensus_rejects_outlier() -> None:
    result = consensus_close([candle("a", 1.30), candle("b", 1.31), candle("c", 2.50)])
    assert result.valid is True
    assert result.value is not None
    assert 1.29 < result.value < 1.32
    assert DataFlag.OUTLIER in result.flags
    assert result.rejected_provider_count == 1


def test_consensus_fails_closed_when_stale() -> None:
    result = consensus_close(
        [candle("a", 1.30, 5), candle("b", 1.31, 5)],
        max_age_seconds=3600,
    )
    assert result.valid is False
    assert result.value is None
    assert DataFlag.STALE in result.flags


def test_consensus_fails_closed_with_single_provider() -> None:
    result = consensus_close([candle("a", 1.30)])
    assert result.valid is False
    assert result.value is None
    assert DataFlag.MISSING in result.flags


def test_two_source_conflict_is_not_averaged() -> None:
    result = consensus_close([candle("a", 1.00), candle("b", 2.00)])
    assert result.valid is False
    assert result.value is None
    assert DataFlag.CONFLICT in result.flags


def test_duplicate_provider_does_not_inflate_coverage() -> None:
    result = consensus_close([candle("a", 1.30), candle("a", 1.31)])
    assert result.input_provider_count == 1
    assert result.valid is False
