from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class ResearchHorizon(StrEnum):
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"
    M1 = "1m"
    M3 = "3m"
    Y1 = "1y"


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _add_months(value: datetime, months: int) -> datetime:
    if months <= 0:
        raise ValueError("months must be positive")
    zero_based = value.month - 1 + months
    year = value.year + zero_based // 12
    month = zero_based % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def horizon_end_at(prediction_time: datetime, horizon: ResearchHorizon) -> datetime:
    prediction = _utc(prediction_time, "prediction_time")
    if horizon is ResearchHorizon.H1:
        return prediction + timedelta(hours=1)
    if horizon is ResearchHorizon.H4:
        return prediction + timedelta(hours=4)
    if horizon is ResearchHorizon.D1:
        return prediction + timedelta(days=1)
    if horizon is ResearchHorizon.W1:
        return prediction + timedelta(weeks=1)
    if horizon is ResearchHorizon.M1:
        return _add_months(prediction, 1)
    if horizon is ResearchHorizon.M3:
        return _add_months(prediction, 3)
    if horizon is ResearchHorizon.Y1:
        try:
            return prediction.replace(year=prediction.year + 1)
        except ValueError:
            return prediction.replace(year=prediction.year + 1, day=28)
    raise ValueError("unsupported research horizon")
