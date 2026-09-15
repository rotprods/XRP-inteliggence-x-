from __future__ import annotations

import math
from datetime import UTC

import numpy as np
import pandas as pd
import pytest

from xrp_regime_engine import features as f
from xrp_regime_engine.demo import generate_demo_frame

pytestmark = [pytest.mark.unit, pytest.mark.temporal]


def series(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype="float64")


def test_return_and_change_reject_insufficient_or_zero_base() -> None:
    assert f._return(series([1.0]), 1) is None
    assert f._return(series([0.0, 1.0]), 1) is None
    assert f._absolute_change(series([1.0]), 1) is None


def test_zscore_insufficient_and_constant() -> None:
    assert f._zscore(series([1.0, 2.0]), 3) is None
    assert f._zscore(series([2.0] * 5), 5) == 0.0


def test_rsi_extremes_and_insufficient() -> None:
    assert f._rsi(series([1.0] * 10), 14) is None
    assert f._rsi(series([float(i) for i in range(1, 17)]), 14) == 100.0
    assert f._rsi(series([float(i) for i in range(17, 0, -1)]), 14) == 0.0


def test_beta_and_corr_fail_closed_on_insufficient_or_zero_variance() -> None:
    a = series([1, 2, 3, 4])
    b = series([1, 1, 1, 1])
    assert f._beta(a, b, window=3) is None
    assert f._corr(a.head(2), b.head(2), window=3) is None


def test_distance_and_drawdown_edge_cases() -> None:
    assert f._distance_to_mean(series([1.0]), 2) is None
    assert f._distance_to_mean(series([-1.0, 1.0]), 2) is None
    assert f._drawdown(series([1.0]), 2) is None
    assert f._drawdown(series([-2.0, -1.0]), 2) is None


def test_interval_and_annualized_volatility_edge_cases() -> None:
    assert f._median_interval_seconds(pd.Index([1, 2, 3])) is None
    duplicate = pd.DatetimeIndex([pd.Timestamp("2026-01-01", tz=UTC)] * 3)
    assert f._median_interval_seconds(duplicate) is None
    assert f._periods_per_year(pd.Index([1])) is None
    idx = pd.date_range("2026-01-01", periods=10, freq="D", tz=UTC)
    assert f._annualized_volatility(series(list(range(1, 11))), idx, window=30) is None


def test_validate_frame_rejects_empty_non_datetime_non_monotonic_duplicates_and_wrong_cadence() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        f._validate_frame(pd.DataFrame())
    with pytest.raises(ValueError, match="DatetimeIndex"):
        f._validate_frame(pd.DataFrame({"x": [1, 2, 3]}))

    frame = generate_demo_frame(10)
    with pytest.raises(ValueError, match="timezone-aware"):
        f._validate_frame(frame.set_axis(frame.index.tz_localize(None)))
    with pytest.raises(ValueError, match="monotonic"):
        f._validate_frame(frame.iloc[::-1])

    duplicated = pd.concat([frame.iloc[:3], frame.iloc[2:]])
    with pytest.raises(ValueError, match="duplicates"):
        f._validate_frame(duplicated)

    hourly = frame.copy()
    hourly.index = pd.date_range("2026-01-01", periods=len(hourly), freq="h", tz=UTC)
    with pytest.raises(ValueError, match="daily cadence only"):
        f._validate_frame(hourly)


def test_validate_frame_requires_all_assets() -> None:
    frame = generate_demo_frame(10).drop(columns=["GOLD"])
    with pytest.raises(ValueError, match="missing required assets"):
        f._validate_frame(frame)


def test_unknown_supplemental_feature_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown supplemental"):
        f.compute_features(generate_demo_frame(), supplemental={"made_up": 1.0})


def test_non_finite_supplemental_becomes_none() -> None:
    features = f.compute_features(generate_demo_frame(), supplemental={"funding_z": math.inf})
    assert features["funding_z"] is None


def test_clean_drops_non_numeric_nan_and_infinity() -> None:
    cleaned = f._clean(pd.Series(["1", "bad", np.inf, -np.inf, np.nan, 2]))
    assert cleaned.tolist() == [1.0, 2.0]


def test_zscore_non_finite_std_fails_closed() -> None:
    extreme = pd.Series([1e308, -1e308] * 10, dtype="float64")
    with pytest.warns(RuntimeWarning):
        assert f._zscore(extreme, 20) is None


def test_validate_frame_with_two_rows_hits_cadence_guard() -> None:
    with pytest.raises(ValueError, match="at least three"):
        f._validate_frame(generate_demo_frame(2))
