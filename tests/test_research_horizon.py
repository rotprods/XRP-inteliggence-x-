from datetime import UTC, datetime

import pytest

from xrp_regime_engine.research_horizon import ResearchHorizon, _add_months, horizon_end_at


def test_fixed_horizons() -> None:
    t = datetime(2026, 1, 2, 12, tzinfo=UTC)
    assert horizon_end_at(t, ResearchHorizon.H1).hour == 13
    assert horizon_end_at(t, ResearchHorizon.H4).hour == 16
    assert horizon_end_at(t, ResearchHorizon.D1).day == 3
    assert horizon_end_at(t, ResearchHorizon.W1).day == 9


def test_calendar_months_clamp_month_end() -> None:
    t = datetime(2026, 1, 31, 12, tzinfo=UTC)
    assert horizon_end_at(t, ResearchHorizon.M1) == datetime(2026, 2, 28, 12, tzinfo=UTC)
    assert horizon_end_at(t, ResearchHorizon.M3) == datetime(2026, 4, 30, 12, tzinfo=UTC)


def test_year_horizon_clamps_leap_day() -> None:
    t = datetime(2028, 2, 29, 12, tzinfo=UTC)
    assert horizon_end_at(t, ResearchHorizon.Y1) == datetime(2029, 2, 28, 12, tzinfo=UTC)


def test_naive_and_invalid_internal_months_fail() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        horizon_end_at(datetime(2026, 1, 1), ResearchHorizon.H1)
    with pytest.raises(ValueError, match="positive"):
        _add_months(datetime(2026, 1, 1, tzinfo=UTC), 0)
    with pytest.raises(ValueError, match="unsupported"):
        horizon_end_at(
            datetime(2026, 1, 1, tzinfo=UTC),
            "bad",  # type: ignore[arg-type]
        )
