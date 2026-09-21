from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import cast

from xrp_regime_engine.future_labels_v1 import FutureOutcomeLabel
from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow
from xrp_regime_engine.research_horizon import ResearchHorizon


class WalkForwardMode(StrEnum):
    EXPANDING = "expanding"
    ROLLING = "rolling"


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


@dataclass(frozen=True, slots=True)
class LabeledFeatureRow:
    feature: HistoricalFeatureRow
    label: FutureOutcomeLabel

    def __post_init__(self) -> None:
        if self.feature.feature_row_id != self.label.feature_row_id:
            raise ValueError("feature and label must reference the same feature_row_id")
        if self.feature.prediction_time != self.label.prediction_time:
            raise ValueError("feature and label prediction_time must match")
        if self.feature.horizon is not self.label.horizon:
            raise ValueError("feature and label horizon must match")
        if self.label.label_end_at <= self.feature.prediction_time:
            raise ValueError("label horizon must end after prediction_time")
        if self.label.resolved_at < self.label.label_end_at:
            raise ValueError("label cannot resolve before label_end_at")


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    min_train_size: int
    test_size: int = 1
    step_size: int | None = None
    mode: WalkForwardMode = WalkForwardMode.EXPANDING
    max_train_size: int | None = None
    embargo: timedelta = timedelta(0)

    def __post_init__(self) -> None:
        if self.min_train_size < 1:
            raise ValueError("min_train_size must be positive")
        if self.test_size < 1:
            raise ValueError("test_size must be positive")
        step = self.test_size if self.step_size is None else self.step_size
        if step < self.test_size:
            raise ValueError("step_size must be >= test_size to prevent overlapping test folds")
        if self.embargo < timedelta(0):
            raise ValueError("embargo cannot be negative")
        if self.mode is WalkForwardMode.EXPANDING and self.max_train_size is not None:
            raise ValueError("max_train_size is only valid in rolling mode")
        if self.mode is WalkForwardMode.ROLLING:
            if self.max_train_size is None:
                raise ValueError("rolling mode requires max_train_size")
            if self.max_train_size < self.min_train_size:
                raise ValueError("max_train_size must be >= min_train_size")

    @property
    def effective_step_size(self) -> int:
        return self.test_size if self.step_size is None else self.step_size


@dataclass(frozen=True, slots=True)
class WalkForwardFoldPlan:
    fold_id: str
    fold_index: int
    horizon: ResearchHorizon
    mode: WalkForwardMode
    cutoff_at: datetime
    embargo_seconds: float
    purged_count: int
    train_feature_row_ids: tuple[str, ...]
    train_label_ids: tuple[str, ...]
    test_feature_row_ids: tuple[str, ...]
    test_label_ids: tuple[str, ...]
    train_prediction_start: datetime
    train_prediction_end: datetime
    test_prediction_start: datetime
    test_prediction_end: datetime

    def to_payload(self) -> dict[str, object]:
        return {
            "fold_id": self.fold_id,
            "fold_index": self.fold_index,
            "horizon": self.horizon.value,
            "mode": self.mode.value,
            "cutoff_at": self.cutoff_at.isoformat(),
            "embargo_seconds": self.embargo_seconds,
            "purged_count": self.purged_count,
            "train_feature_row_ids": list(self.train_feature_row_ids),
            "train_label_ids": list(self.train_label_ids),
            "test_feature_row_ids": list(self.test_feature_row_ids),
            "test_label_ids": list(self.test_label_ids),
            "train_prediction_start": self.train_prediction_start.isoformat(),
            "train_prediction_end": self.train_prediction_end.isoformat(),
            "test_prediction_start": self.test_prediction_start.isoformat(),
            "test_prediction_end": self.test_prediction_end.isoformat(),
        }


def join_labeled_rows(
    features: Sequence[HistoricalFeatureRow],
    labels: Sequence[FutureOutcomeLabel],
) -> tuple[LabeledFeatureRow, ...]:
    if not features:
        raise ValueError("features cannot be empty")
    if not labels:
        raise ValueError("labels cannot be empty")

    feature_by_id: dict[str, HistoricalFeatureRow] = {}
    for feature in features:
        if feature.feature_row_id in feature_by_id:
            raise ValueError(f"duplicate feature_row_id: {feature.feature_row_id}")
        feature_by_id[feature.feature_row_id] = feature

    label_by_feature_id: dict[str, FutureOutcomeLabel] = {}
    for label in labels:
        if label.feature_row_id in label_by_feature_id:
            raise ValueError(f"duplicate label for feature_row_id: {label.feature_row_id}")
        label_by_feature_id[label.feature_row_id] = label

    feature_ids = set(feature_by_id)
    label_feature_ids = set(label_by_feature_id)
    missing_labels = sorted(feature_ids - label_feature_ids)
    orphan_labels = sorted(label_feature_ids - feature_ids)
    if missing_labels or orphan_labels:
        details: list[str] = []
        if missing_labels:
            details.append(f"missing labels for {missing_labels!r}")
        if orphan_labels:
            details.append(f"orphan labels for {orphan_labels!r}")
        raise ValueError("; ".join(details))

    joined = tuple(
        LabeledFeatureRow(
            feature=feature_by_id[feature_id],
            label=label_by_feature_id[feature_id],
        )
        for feature_id in feature_by_id
    )
    ordered = tuple(
        sorted(joined, key=lambda row: (row.feature.prediction_time, row.feature.feature_row_id))
    )
    horizons = {row.feature.horizon for row in ordered}
    if len(horizons) != 1:
        raise ValueError("walk-forward rows must contain exactly one research horizon")
    prediction_times = [row.feature.prediction_time for row in ordered]
    if len(prediction_times) != len(set(prediction_times)):
        raise ValueError("prediction_time values must be unique within a horizon")
    return ordered


def build_walk_forward_folds(
    rows: Sequence[LabeledFeatureRow],
    *,
    config: WalkForwardConfig,
) -> tuple[WalkForwardFoldPlan, ...]:
    if not rows:
        raise ValueError("rows cannot be empty")

    ordered = tuple(
        sorted(rows, key=lambda row: (row.feature.prediction_time, row.feature.feature_row_id))
    )
    feature_ids = [row.feature.feature_row_id for row in ordered]
    if len(feature_ids) != len(set(feature_ids)):
        raise ValueError("feature_row_id values must be unique")
    horizons = {row.feature.horizon for row in ordered}
    if len(horizons) != 1:
        raise ValueError("walk-forward rows must contain exactly one research horizon")
    horizon = next(iter(horizons))
    prediction_times = [row.feature.prediction_time for row in ordered]
    if len(prediction_times) != len(set(prediction_times)):
        raise ValueError("prediction_time values must be unique within a horizon")

    folds: list[WalkForwardFoldPlan] = []
    test_start = config.min_train_size
    fold_index = 0
    while test_start + config.test_size <= len(ordered):
        test_rows = ordered[test_start : test_start + config.test_size]
        test_prediction_start = test_rows[0].feature.prediction_time
        cutoff_at = _utc(test_prediction_start - config.embargo, "cutoff_at")

        preceding = ordered[:test_start]
        eligible_train = tuple(row for row in preceding if row.label.resolved_at < cutoff_at)
        purged_count = len(preceding) - len(eligible_train)

        if config.mode is WalkForwardMode.ROLLING:
            max_train_size = cast(int, config.max_train_size)
            eligible_train = eligible_train[-max_train_size:]

        if len(eligible_train) >= config.min_train_size:
            train_feature_ids = tuple(row.feature.feature_row_id for row in eligible_train)
            train_label_ids = tuple(row.label.label_id for row in eligible_train)
            test_feature_ids = tuple(row.feature.feature_row_id for row in test_rows)
            test_label_ids = tuple(row.label.label_id for row in test_rows)
            material: dict[str, object] = {
                "fold_index": fold_index,
                "horizon": horizon.value,
                "mode": config.mode.value,
                "cutoff_at": cutoff_at.isoformat(),
                "embargo_seconds": config.embargo.total_seconds(),
                "train_feature_row_ids": list(train_feature_ids),
                "train_label_ids": list(train_label_ids),
                "test_feature_row_ids": list(test_feature_ids),
                "test_label_ids": list(test_label_ids),
            }
            digest = sha256(_canonical(material).encode()).hexdigest()
            folds.append(
                WalkForwardFoldPlan(
                    fold_id=f"walk-forward-fold:sha256:{digest}",
                    fold_index=fold_index,
                    horizon=horizon,
                    mode=config.mode,
                    cutoff_at=cutoff_at,
                    embargo_seconds=config.embargo.total_seconds(),
                    purged_count=purged_count,
                    train_feature_row_ids=train_feature_ids,
                    train_label_ids=train_label_ids,
                    test_feature_row_ids=test_feature_ids,
                    test_label_ids=test_label_ids,
                    train_prediction_start=eligible_train[0].feature.prediction_time,
                    train_prediction_end=eligible_train[-1].feature.prediction_time,
                    test_prediction_start=test_rows[0].feature.prediction_time,
                    test_prediction_end=test_rows[-1].feature.prediction_time,
                )
            )
            fold_index += 1

        test_start += config.effective_step_size

    if not folds:
        raise ValueError("no leakage-safe walk-forward folds can be built")
    return tuple(folds)
