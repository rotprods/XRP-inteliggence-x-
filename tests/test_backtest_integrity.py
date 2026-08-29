from __future__ import annotations

import pandas as pd
import pytest

from xrp_regime_engine import backtest
from xrp_regime_engine.demo import DEMO_SUPPLEMENTAL_FEATURES, generate_demo_frame

pytestmark = [pytest.mark.research, pytest.mark.temporal]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_train": 29},
        {"step": 0},
        {"forward": 0},
    ],
)
def test_walk_forward_rejects_invalid_windows(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="min_train, step and forward"):
        backtest.expanding_walk_forward(generate_demo_frame(500), **kwargs)


def test_walk_forward_rejects_insufficient_outcomes() -> None:
    with pytest.raises(ValueError, match="not enough observations"):
        backtest.expanding_walk_forward(generate_demo_frame(365), min_train=365)


def test_walk_forward_compute_features_never_receives_future_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = generate_demo_frame(430)
    original = backtest.compute_features
    seen_max: list[pd.Timestamp] = []

    def guarded(history: pd.DataFrame, *, supplemental=None):
        seen_max.append(history.index.max())
        # History slices must remain strict prefixes of the complete research frame.
        assert len(history) < len(frame)
        assert history.index.max() < frame.index[-1]
        return original(history, supplemental=supplemental)

    monkeypatch.setattr(backtest, "compute_features", guarded)
    result = backtest.expanding_walk_forward(
        frame,
        min_train=365,
        step=14,
        forward=7,
        supplemental=DEMO_SUPPLEMENTAL_FEATURES,
    )
    assert result.observations == len(seen_max)
    assert seen_max == sorted(seen_max)


def test_backtest_result_never_claims_calibration() -> None:
    result = backtest.expanding_walk_forward(
        generate_demo_frame(430),
        min_train=365,
        step=14,
        forward=7,
        supplemental=DEMO_SUPPLEMENTAL_FEATURES,
    )
    assert result.probability_calibrated is False


def test_point_in_time_mode_requires_availability() -> None:
    with pytest.raises(ValueError, match="requires available_at"):
        backtest.expanding_walk_forward(
            generate_demo_frame(430),
            min_train=365,
            step=14,
            forward=7,
            supplemental=DEMO_SUPPLEMENTAL_FEATURES,
            require_point_in_time=True,
        )


def test_point_in_time_availability_excludes_future_known_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = generate_demo_frame(430)
    availability = pd.Series(frame.index, index=frame.index)
    delayed_row = frame.index[364]
    availability.loc[delayed_row] = frame.index[400]
    original = backtest.compute_features
    histories: list[pd.DatetimeIndex] = []

    def guarded(history: pd.DataFrame, *, supplemental=None):
        histories.append(history.index)
        decision_time = history.index.max()
        assert all(availability.loc[row] <= decision_time for row in history.index)
        return original(history, supplemental=supplemental)

    monkeypatch.setattr(backtest, "compute_features", guarded)
    result = backtest.expanding_walk_forward(
        frame,
        min_train=365,
        step=14,
        forward=7,
        supplemental=DEMO_SUPPLEMENTAL_FEATURES,
        available_at=availability,
        require_point_in_time=True,
    )
    assert result.observations == len(histories)
    assert histories
    assert delayed_row not in histories[0]


def test_point_in_time_rejects_misaligned_invalid_or_impossible_availability() -> None:
    frame = generate_demo_frame(430)

    misaligned = pd.Series(frame.index[:-1], index=frame.index[:-1])
    with pytest.raises(ValueError, match="index must exactly match"):
        backtest.expanding_walk_forward(frame, available_at=misaligned)

    invalid = pd.Series(frame.index, index=frame.index, dtype="object")
    invalid.iloc[0] = "not-a-date"
    with pytest.raises(ValueError, match="missing or invalid"):
        backtest.expanding_walk_forward(frame, available_at=invalid)

    impossible = pd.Series(frame.index, index=frame.index)
    impossible.iloc[0] = frame.index[0] - pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="cannot precede observed_at"):
        backtest.expanding_walk_forward(frame, available_at=impossible)


def test_backtest_rejects_invalid_research_index_and_missing_target() -> None:
    frame = generate_demo_frame(430)
    with pytest.raises(ValueError, match="must contain XRP_USD"):
        backtest.expanding_walk_forward(frame.drop(columns=["XRP_USD"]))

    with pytest.raises(ValueError, match="DatetimeIndex"):
        backtest.expanding_walk_forward(frame.reset_index(drop=True))

    naive = frame.copy()
    naive.index = naive.index.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        backtest.expanding_walk_forward(naive)

    descending = frame.sort_index(ascending=False)
    with pytest.raises(ValueError, match="monotonic increasing"):
        backtest.expanding_walk_forward(descending)

    duplicate = pd.concat([frame.iloc[:1], frame]).sort_index()
    with pytest.raises(ValueError, match="unique"):
        backtest.expanding_walk_forward(duplicate)


def test_point_in_time_can_fail_for_insufficient_known_history() -> None:
    frame = generate_demo_frame(430)
    availability = pd.Series(frame.index + pd.Timedelta(days=100), index=frame.index)
    with pytest.raises(ValueError, match="not enough observations"):
        backtest.expanding_walk_forward(
            frame,
            min_train=365,
            step=14,
            forward=7,
            supplemental=DEMO_SUPPLEMENTAL_FEATURES,
            available_at=availability,
            require_point_in_time=True,
        )


def test_walk_forward_supports_rolling_window_and_embargo() -> None:
    frame = generate_demo_frame(500)
    expanding = backtest.expanding_walk_forward(
        frame,
        min_train=365,
        step=14,
        forward=7,
        embargo=7,
        supplemental=DEMO_SUPPLEMENTAL_FEATURES,
    )
    rolling = backtest.expanding_walk_forward(
        frame,
        min_train=365,
        train_window=365,
        step=14,
        forward=7,
        embargo=7,
        supplemental=DEMO_SUPPLEMENTAL_FEATURES,
    )
    assert expanding.observations == rolling.observations
    assert expanding.observations > 0


def test_walk_forward_rejects_invalid_embargo_or_rolling_window() -> None:
    frame = generate_demo_frame(500)
    with pytest.raises(ValueError, match="embargo"):
        backtest.expanding_walk_forward(frame, embargo=-1)
    with pytest.raises(ValueError, match="train_window"):
        backtest.expanding_walk_forward(frame, min_train=365, train_window=364)
