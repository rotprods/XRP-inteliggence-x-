from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence

from xrp_regime_engine.historical_store import HistoricalRecord, utc


class QualityStatus(StrEnum):
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    FAIL = "FAIL"


class QualitySeverity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    severity: QualitySeverity
    message: str
    record_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "record_ids": list(self.record_ids),
        }


@dataclass(frozen=True, slots=True)
class CandleQualityReport:
    dataset: str
    status: QualityStatus
    window_start: datetime
    window_end: datetime
    interval_seconds: int
    total_records: int
    latest_records: int
    expected_points: int
    present_points: int
    missing_points: int
    coverage_ratio: float
    off_grid_points: int
    duplicate_observation_points: int
    revision_records: int
    invalid_ohlc_records: int
    early_availability_records: int
    source_count: int
    raw_payload_count: int
    availability_lag_seconds_min: float | None
    availability_lag_seconds_median: float | None
    availability_lag_seconds_mean: float | None
    availability_lag_seconds_max: float | None
    issues: tuple[QualityIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["window_start"] = self.window_start.isoformat()
        payload["window_end"] = self.window_end.isoformat()
        payload["issues"] = [issue.to_dict() for issue in self.issues]
        return payload


def _decimal(values: Mapping[str, Any], key: str) -> Decimal:
    try:
        result = Decimal(str(values[key]))
    except (KeyError, InvalidOperation) as exc:
        raise ValueError(f"missing or invalid candle field: {key}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite candle field: {key}")
    return result


def _latest_by_observation(
    records: Sequence[HistoricalRecord],
) -> tuple[dict[datetime, HistoricalRecord], int, int]:
    grouped: dict[datetime, list[HistoricalRecord]] = {}
    for record in records:
        grouped.setdefault(record.observed_at, []).append(record)
    selected: dict[datetime, HistoricalRecord] = {}
    duplicate_points = 0
    revision_records = 0
    for observed_at, rows in grouped.items():
        if len(rows) > 1:
            duplicate_points += 1
            revision_records += len(rows) - 1
        selected[observed_at] = max(
            rows,
            key=lambda row: (
                row.available_at,
                row.revision,
                row.source,
                row.canonical_sha256,
            ),
        )
    return selected, duplicate_points, revision_records


def analyze_candle_records(
    records: Iterable[HistoricalRecord],
    *,
    window_start: datetime,
    window_end: datetime,
    interval_seconds: int,
    allowed_missing_ratio: float = 0.0,
    availability_tolerance_seconds: float = 0.0,
    max_expected_points: int = 2_000_000,
) -> CandleQualityReport:
    start = utc(window_start)
    end = utc(window_end)
    if end <= start:
        raise ValueError("window_end must be later than window_start")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    if not 0.0 <= allowed_missing_ratio <= 1.0:
        raise ValueError("allowed_missing_ratio must be within [0, 1]")
    if availability_tolerance_seconds < 0:
        raise ValueError("availability_tolerance_seconds cannot be negative")

    rows = tuple(records)
    if not rows:
        issue = QualityIssue("NO_DATA", QualitySeverity.ERROR, "dataset has no historical records")
        expected = int((end - start).total_seconds() // interval_seconds)
        return CandleQualityReport(
            dataset="UNKNOWN",
            status=QualityStatus.FAIL,
            window_start=start,
            window_end=end,
            interval_seconds=interval_seconds,
            total_records=0,
            latest_records=0,
            expected_points=expected,
            present_points=0,
            missing_points=expected,
            coverage_ratio=0.0,
            off_grid_points=0,
            duplicate_observation_points=0,
            revision_records=0,
            invalid_ohlc_records=0,
            early_availability_records=0,
            source_count=0,
            raw_payload_count=0,
            availability_lag_seconds_min=None,
            availability_lag_seconds_median=None,
            availability_lag_seconds_mean=None,
            availability_lag_seconds_max=None,
            issues=(issue,),
        )

    datasets = {row.dataset for row in rows}
    if len(datasets) != 1:
        raise ValueError("quality analysis cannot mix datasets")
    dataset = next(iter(datasets))
    expected_points = int((end - start).total_seconds() // interval_seconds)
    if expected_points > max_expected_points:
        raise ValueError("expected point count exceeds the configured audit limit")

    latest, duplicate_points, revision_records = _latest_by_observation(rows)
    expected_timestamps = {
        start + timedelta(seconds=index * interval_seconds)
        for index in range(expected_points)
    }
    present_timestamps = {
        observed_at for observed_at in latest if start <= observed_at < end
    }
    missing_timestamps = sorted(expected_timestamps - present_timestamps)
    off_grid = sorted(
        observed_at
        for observed_at in present_timestamps
        if (observed_at - start).total_seconds() % interval_seconds != 0
    )

    invalid_records: list[str] = []
    early_records: list[str] = []
    availability_lags: list[float] = []
    for observed_at, record in sorted(latest.items()):
        if not start <= observed_at < end:
            continue
        lag = (record.available_at - record.observed_at).total_seconds()
        availability_lags.append(lag)
        earliest_valid = interval_seconds - availability_tolerance_seconds
        if lag < earliest_valid:
            early_records.append(record.record_id)
        try:
            open_price = _decimal(record.values, "open")
            high_price = _decimal(record.values, "high")
            low_price = _decimal(record.values, "low")
            close_price = _decimal(record.values, "close")
            volume = _decimal(record.values, "volume")
            valid = (
                low_price > 0
                and open_price > 0
                and close_price > 0
                and high_price > 0
                and volume >= 0
                and low_price <= min(open_price, close_price)
                and max(open_price, close_price) <= high_price
            )
        except ValueError:
            valid = False
        if not valid:
            invalid_records.append(record.record_id)

    coverage_ratio = (
        len(expected_timestamps & present_timestamps) / expected_points
        if expected_points
        else 1.0
    )
    issues: list[QualityIssue] = []
    if missing_timestamps:
        preview = tuple(timestamp.isoformat() for timestamp in missing_timestamps[:20])
        severity = (
            QualitySeverity.ERROR
            if len(missing_timestamps) / max(expected_points, 1) > allowed_missing_ratio
            else QualitySeverity.WARN
        )
        issues.append(
            QualityIssue(
                "MISSING_INTERVALS",
                severity,
                f"{len(missing_timestamps)} expected candle interval(s) are missing",
                preview,
            )
        )
    if off_grid:
        issues.append(
            QualityIssue(
                "OFF_GRID_TIMESTAMPS",
                QualitySeverity.ERROR,
                f"{len(off_grid)} candle timestamp(s) are not aligned to the configured interval",
                tuple(timestamp.isoformat() for timestamp in off_grid[:20]),
            )
        )
    if duplicate_points:
        issues.append(
            QualityIssue(
                "MULTIPLE_RECORDS_PER_OBSERVATION",
                QualitySeverity.WARN,
                f"{duplicate_points} observation timestamp(s) have multiple revisions/sources",
            )
        )
    if invalid_records:
        issues.append(
            QualityIssue(
                "INVALID_OHLCV",
                QualitySeverity.ERROR,
                f"{len(invalid_records)} latest candle record(s) violate OHLCV constraints",
                tuple(invalid_records[:20]),
            )
        )
    if early_records:
        issues.append(
            QualityIssue(
                "EARLY_AVAILABILITY",
                QualitySeverity.ERROR,
                f"{len(early_records)} candle record(s) were available before interval close",
                tuple(early_records[:20]),
            )
        )

    if any(issue.severity == QualitySeverity.ERROR for issue in issues):
        status = QualityStatus.FAIL
    elif issues:
        status = QualityStatus.DEGRADED
    else:
        status = QualityStatus.PASS

    return CandleQualityReport(
        dataset=dataset,
        status=status,
        window_start=start,
        window_end=end,
        interval_seconds=interval_seconds,
        total_records=len(rows),
        latest_records=len(latest),
        expected_points=expected_points,
        present_points=len(expected_timestamps & present_timestamps),
        missing_points=len(missing_timestamps),
        coverage_ratio=coverage_ratio,
        off_grid_points=len(off_grid),
        duplicate_observation_points=duplicate_points,
        revision_records=revision_records,
        invalid_ohlc_records=len(invalid_records),
        early_availability_records=len(early_records),
        source_count=len({row.source for row in rows}),
        raw_payload_count=len({row.raw_payload_sha256 for row in rows}),
        availability_lag_seconds_min=min(availability_lags) if availability_lags else None,
        availability_lag_seconds_median=median(availability_lags) if availability_lags else None,
        availability_lag_seconds_mean=mean(availability_lags) if availability_lags else None,
        availability_lag_seconds_max=max(availability_lags) if availability_lags else None,
        issues=tuple(issues),
    )
