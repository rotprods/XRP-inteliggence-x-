from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from xrp_regime_engine.historical_quality import (
    QualitySeverity,
    QualityStatus,
    analyze_candle_records,
)
from xrp_regime_engine.historical_store import HistoricalRecord


UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def candle(
    index: int,
    *,
    observed_at: datetime | None = None,
    available_at: datetime | None = None,
    revision: int = 0,
    source: str = "coinbase",
    open_price: str = "1.0",
    high_price: str = "1.2",
    low_price: str = "0.9",
    close_price: str = "1.1",
    volume: str = "100",
) -> HistoricalRecord:
    observed = observed_at or BASE + timedelta(hours=index)
    return HistoricalRecord(
        dataset="xrp_usd_spot_3600s",
        record_id=f"candle-{index}",
        observed_at=observed,
        available_at=available_at or observed + timedelta(hours=1),
        source=source,
        revision=revision,
        values={
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume,
        },
        raw_payload_sha256=(source[0] * 64),
    )


def issue_codes(report) -> set[str]:
    return {issue.code for issue in report.issues}


def test_complete_valid_dataset_passes() -> None:
    report = analyze_candle_records(
        [candle(0), candle(1), candle(2)],
        window_start=BASE,
        window_end=BASE + timedelta(hours=3),
        interval_seconds=3600,
    )
    assert report.status is QualityStatus.PASS
    assert report.coverage_ratio == 1.0
    assert report.missing_points == 0
    assert report.invalid_ohlc_records == 0
    assert report.early_availability_records == 0
    assert report.availability_lag_seconds_median == 3600
    assert report.source_count == 1
    assert report.to_dict()["status"] == "PASS"


def test_empty_dataset_fails_with_no_data() -> None:
    report = analyze_candle_records(
        [],
        window_start=BASE,
        window_end=BASE + timedelta(hours=3),
        interval_seconds=3600,
    )
    assert report.status is QualityStatus.FAIL
    assert report.expected_points == 3
    assert report.missing_points == 3
    assert issue_codes(report) == {"NO_DATA"}


def test_missing_intervals_fail_or_warn_by_allowed_ratio() -> None:
    strict = analyze_candle_records(
        [candle(0), candle(2)],
        window_start=BASE,
        window_end=BASE + timedelta(hours=3),
        interval_seconds=3600,
    )
    assert strict.status is QualityStatus.FAIL
    assert strict.missing_points == 1
    assert strict.issues[0].severity is QualitySeverity.ERROR

    tolerant = analyze_candle_records(
        [candle(0), candle(2)],
        window_start=BASE,
        window_end=BASE + timedelta(hours=3),
        interval_seconds=3600,
        allowed_missing_ratio=0.34,
    )
    assert tolerant.status is QualityStatus.DEGRADED
    assert tolerant.issues[0].severity is QualitySeverity.WARN


def test_off_grid_timestamp_is_error() -> None:
    report = analyze_candle_records(
        [candle(0), candle(1, observed_at=BASE + timedelta(hours=1, minutes=1))],
        window_start=BASE,
        window_end=BASE + timedelta(hours=2),
        interval_seconds=3600,
        allowed_missing_ratio=1.0,
    )
    assert report.status is QualityStatus.FAIL
    assert "OFF_GRID_TIMESTAMPS" in issue_codes(report)
    assert report.off_grid_points == 1


def test_duplicate_observation_selects_latest_revision_and_degrades() -> None:
    original = candle(0, revision=0, close_price="1.0", source="coinbase")
    revised = HistoricalRecord(
        dataset=original.dataset,
        record_id=original.record_id,
        observed_at=original.observed_at,
        available_at=original.available_at + timedelta(minutes=10),
        source="kraken",
        revision=1,
        values={"open": "1", "high": "1.3", "low": "0.9", "close": "1.2", "volume": "100"},
        raw_payload_sha256="k" * 64,
    )
    report = analyze_candle_records(
        [original, revised],
        window_start=BASE,
        window_end=BASE + timedelta(hours=1),
        interval_seconds=3600,
    )
    assert report.status is QualityStatus.DEGRADED
    assert report.duplicate_observation_points == 1
    assert report.revision_records == 1
    assert report.source_count == 2
    assert report.raw_payload_count == 2
    assert "MULTIPLE_RECORDS_PER_OBSERVATION" in issue_codes(report)


@pytest.mark.parametrize(
    ("field_overrides", "message"),
    [
        ({"high_price": "0.8"}, "high below open/close"),
        ({"low_price": "1.15"}, "low above open/close"),
        ({"open_price": "0"}, "non-positive open"),
        ({"close_price": "-1"}, "non-positive close"),
        ({"volume": "-1"}, "negative volume"),
        ({"high_price": "not-a-number"}, "invalid numeric"),
        ({"high_price": "NaN"}, "non-finite numeric"),
    ],
)
def test_invalid_ohlcv_is_rejected(field_overrides, message) -> None:
    del message
    report = analyze_candle_records(
        [candle(0, **field_overrides)],
        window_start=BASE,
        window_end=BASE + timedelta(hours=1),
        interval_seconds=3600,
    )
    assert report.status is QualityStatus.FAIL
    assert report.invalid_ohlc_records == 1
    assert "INVALID_OHLCV" in issue_codes(report)


def test_early_availability_is_leakage_error_with_optional_tolerance() -> None:
    early = candle(0, available_at=BASE + timedelta(minutes=30))
    strict = analyze_candle_records(
        [early],
        window_start=BASE,
        window_end=BASE + timedelta(hours=1),
        interval_seconds=3600,
    )
    assert strict.status is QualityStatus.FAIL
    assert strict.early_availability_records == 1
    assert "EARLY_AVAILABILITY" in issue_codes(strict)

    tolerated = analyze_candle_records(
        [early],
        window_start=BASE,
        window_end=BASE + timedelta(hours=1),
        interval_seconds=3600,
        availability_tolerance_seconds=1800,
    )
    assert tolerated.status is QualityStatus.PASS


def test_records_outside_window_do_not_inflate_present_points() -> None:
    report = analyze_candle_records(
        [candle(0), candle(3)],
        window_start=BASE,
        window_end=BASE + timedelta(hours=1),
        interval_seconds=3600,
    )
    assert report.status is QualityStatus.PASS
    assert report.total_records == 2
    assert report.latest_records == 2
    assert report.present_points == 1


def test_configuration_and_dataset_mixing_are_rejected() -> None:
    with pytest.raises(ValueError, match="later"):
        analyze_candle_records([], window_start=BASE, window_end=BASE, interval_seconds=3600)
    with pytest.raises(ValueError, match="positive"):
        analyze_candle_records([], window_start=BASE, window_end=BASE + timedelta(hours=1), interval_seconds=0)
    with pytest.raises(ValueError, match="allowed_missing_ratio"):
        analyze_candle_records(
            [],
            window_start=BASE,
            window_end=BASE + timedelta(hours=1),
            interval_seconds=3600,
            allowed_missing_ratio=2,
        )
    with pytest.raises(ValueError, match="audit limit"):
        analyze_candle_records(
            [],
            window_start=BASE,
            window_end=BASE + timedelta(hours=3),
            interval_seconds=3600,
            max_expected_points=2,
        )
    other = HistoricalRecord(
        dataset="other",
        record_id="other",
        observed_at=BASE,
        available_at=BASE + timedelta(hours=1),
        source="source",
        revision=0,
        values={"open": 1, "high": 1, "low": 1, "close": 1, "volume": 0},
        raw_payload_sha256="o" * 64,
    )
    with pytest.raises(ValueError, match="mix datasets"):
        analyze_candle_records(
            [candle(0), other],
            window_start=BASE,
            window_end=BASE + timedelta(hours=1),
            interval_seconds=3600,
        )
