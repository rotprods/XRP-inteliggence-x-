from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow
from xrp_regime_engine.walk_forward_v1 import LabeledFeatureRow


class BaselineKind(StrEnum):
    B0_BASE_RATE = "B0_BASE_RATE"
    B1_PERSISTENCE = "B1_PERSISTENCE"
    B2_MOMENTUM = "B2_MOMENTUM"
    B3_MEAN_REVERSION = "B3_MEAN_REVERSION"
    B4_LOGISTIC_L2 = "B4_LOGISTIC_L2"


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _finite(value: float, field: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _probability(value: float, field: str) -> float:
    number = _finite(value, field)
    if not 0 <= number <= 1:
        raise ValueError(f"{field} must be within [0, 1]")
    return number


def _sigmoid(value: float) -> float:
    bounded = max(min(value, 35.0), -35.0)
    return 1.0 / (1.0 + math.exp(-bounded))


def _logit(value: float, epsilon: float = 1e-9) -> float:
    probability = min(max(value, epsilon), 1 - epsilon)
    return math.log(probability / (1 - probability))


def flatten_numeric_features(feature: HistoricalFeatureRow) -> dict[str, float]:
    flat: dict[str, float] = {}
    for family, values in sorted(feature.feature_families.items()):
        for name, value in sorted(values.items()):
            if value is None:
                continue
            number = _finite(value, f"{family}.{name}")
            flat[f"{family}.{name}"] = number
    return flat


def _feature_value(feature: HistoricalFeatureRow, key: str) -> float:
    try:
        family, name = key.split(".", 1)
    except ValueError as exc:
        raise ValueError("feature keys must use family.name") from exc
    values = feature.feature_families.get(family)
    if values is None or name not in values or values[name] is None:
        raise ValueError(f"required baseline feature is missing: {key}")
    return _finite(float(values[name]), key)


def binary_event_actual(event_key: str, row: LabeledFeatureRow) -> bool:
    label = row.label
    if event_key == "return_gt_0":
        return label.future_return > 0
    mappings = (
        ("touch_return_up:", label.positive_return_touches),
        ("touch_return_down:", label.negative_return_touches),
        ("touch_price:", label.absolute_price_touches),
    )
    for prefix, values in mappings:
        if event_key.startswith(prefix):
            key = event_key.removeprefix(prefix)
            if key not in values:
                raise ValueError(f"label does not contain event barrier {event_key!r}")
            return bool(values[key])
    raise ValueError(f"unsupported event_key: {event_key!r}")


@dataclass(frozen=True, slots=True)
class BaselineTrainingPolicy:
    smoothing: float = 1.0
    logistic_l2: float = 1.0
    logistic_learning_rate: float = 0.1
    logistic_iterations: int = 500

    def __post_init__(self) -> None:
        if _finite(self.smoothing, "smoothing") <= 0:
            raise ValueError("smoothing must be positive")
        if _finite(self.logistic_l2, "logistic_l2") < 0:
            raise ValueError("logistic_l2 cannot be negative")
        if not 0 < _finite(self.logistic_learning_rate, "logistic_learning_rate") <= 1:
            raise ValueError("logistic_learning_rate must be within (0, 1]")
        if self.logistic_iterations < 1:
            raise ValueError("logistic_iterations must be positive")


@dataclass(frozen=True, slots=True)
class FittedBaselineModel:
    fit_id: str
    kind: BaselineKind
    event_key: str
    feature_keys: tuple[str, ...]
    parameters: Mapping[str, float]
    training_feature_row_ids: tuple[str, ...]

    def predict(self, feature: HistoricalFeatureRow) -> float:
        if self.kind is BaselineKind.B0_BASE_RATE:
            return _probability(self.parameters["base_rate"], "base_rate")
        if self.kind is BaselineKind.B1_PERSISTENCE:
            previous = int(self.parameters["last_actual"])
            key = "rate_after_true" if previous else "rate_after_false"
            return _probability(self.parameters[key], key)
        if self.kind in {BaselineKind.B2_MOMENTUM, BaselineKind.B3_MEAN_REVERSION}:
            key = self.feature_keys[0]
            value = _feature_value(feature, key)
            mean = self.parameters["signal_mean"]
            scale = self.parameters["signal_scale"]
            z_score = (value - mean) / scale
            direction = 1.0 if self.kind is BaselineKind.B2_MOMENTUM else -1.0
            return _sigmoid(self.parameters["base_logit"] + direction * z_score)
        if self.kind is BaselineKind.B4_LOGISTIC_L2:
            linear = self.parameters["intercept"]
            for index, key in enumerate(self.feature_keys):
                value = _feature_value(feature, key)
                mean = self.parameters[f"mean_{index}"]
                scale = self.parameters[f"scale_{index}"]
                weight = self.parameters[f"weight_{index}"]
                linear += weight * ((value - mean) / scale)
            return _sigmoid(linear)
        raise ValueError(f"unsupported baseline kind: {self.kind}")


def _smoothed_rate(positives: int, total: int, smoothing: float) -> float:
    if total < 0 or positives < 0 or positives > total:
        raise ValueError("invalid binary counts")
    return (positives + smoothing) / (total + 2 * smoothing)


def _mean_scale(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        raise ValueError("feature values cannot be empty")
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    scale = math.sqrt(variance)
    return mean, scale if scale > 1e-12 else 1.0


def _fit_logistic(
    matrix: Sequence[Sequence[float]],
    outcomes: Sequence[bool],
    *,
    l2: float,
    learning_rate: float,
    iterations: int,
) -> tuple[float, tuple[float, ...]]:
    if not matrix or len(matrix) != len(outcomes):
        raise ValueError("logistic matrix/outcome dimensions are invalid")
    width = len(matrix[0])
    if width < 1 or any(len(row) != width for row in matrix):
        raise ValueError("logistic feature matrix must be rectangular and non-empty")
    weights = [0.0] * width
    positives = sum(1 for value in outcomes if value)
    intercept = _logit(_smoothed_rate(positives, len(outcomes), 1.0))
    count = len(outcomes)
    for _ in range(iterations):
        intercept_gradient = 0.0
        weight_gradients = [0.0] * width
        for row, actual in zip(matrix, outcomes, strict=True):
            predicted = _sigmoid(intercept + sum(w * x for w, x in zip(weights, row, strict=True)))
            error = predicted - (1.0 if actual else 0.0)
            intercept_gradient += error
            for index, value in enumerate(row):
                weight_gradients[index] += error * value
        intercept -= learning_rate * intercept_gradient / count
        for index in range(width):
            regularized = weight_gradients[index] / count + l2 * weights[index] / count
            weights[index] -= learning_rate * regularized
    return intercept, tuple(weights)


def fit_baseline_model(
    kind: BaselineKind,
    rows: Sequence[LabeledFeatureRow],
    *,
    event_key: str,
    feature_keys: Sequence[str],
    momentum_feature_key: str,
    policy: BaselineTrainingPolicy | None = None,
) -> FittedBaselineModel:
    if not rows:
        raise ValueError("baseline training rows cannot be empty")
    selected_policy = policy or BaselineTrainingPolicy()
    ordered = tuple(
        sorted(rows, key=lambda item: (item.feature.prediction_time, item.feature.feature_row_id))
    )
    ids = tuple(item.feature.feature_row_id for item in ordered)
    if len(ids) != len(set(ids)):
        raise ValueError("baseline training feature_row_id values must be unique")
    outcomes = tuple(binary_event_actual(event_key, item) for item in ordered)
    positives = sum(1 for value in outcomes if value)
    base_rate = _smoothed_rate(positives, len(outcomes), selected_policy.smoothing)
    parameters: dict[str, float] = {"base_rate": base_rate}
    used_features: tuple[str, ...] = ()

    if kind is BaselineKind.B1_PERSISTENCE:
        after_false_total = after_false_positive = 0
        after_true_total = after_true_positive = 0
        for previous, current in zip(outcomes, outcomes[1:], strict=False):
            if previous:
                after_true_total += 1
                after_true_positive += int(current)
            else:
                after_false_total += 1
                after_false_positive += int(current)
        parameters.update(
            {
                "rate_after_false": _smoothed_rate(
                    after_false_positive,
                    after_false_total,
                    selected_policy.smoothing,
                ),
                "rate_after_true": _smoothed_rate(
                    after_true_positive,
                    after_true_total,
                    selected_policy.smoothing,
                ),
                "last_actual": float(outcomes[-1]),
            }
        )
    elif kind in {BaselineKind.B2_MOMENTUM, BaselineKind.B3_MEAN_REVERSION}:
        values = tuple(_feature_value(item.feature, momentum_feature_key) for item in ordered)
        mean, scale = _mean_scale(values)
        parameters.update(
            {
                "signal_mean": mean,
                "signal_scale": scale,
                "base_logit": _logit(base_rate),
            }
        )
        used_features = (momentum_feature_key,)
    elif kind is BaselineKind.B4_LOGISTIC_L2:
        used_features = tuple(feature_keys)
        if not used_features:
            raise ValueError("B4 logistic requires at least one feature key")
        columns = [
            tuple(_feature_value(item.feature, key) for item in ordered)
            for key in used_features
        ]
        means_scales = tuple(_mean_scale(column) for column in columns)
        matrix = tuple(
            tuple(
                (columns[column_index][row_index] - means_scales[column_index][0])
                / means_scales[column_index][1]
                for column_index in range(len(columns))
            )
            for row_index in range(len(ordered))
        )
        intercept, weights = _fit_logistic(
            matrix,
            outcomes,
            l2=selected_policy.logistic_l2,
            learning_rate=selected_policy.logistic_learning_rate,
            iterations=selected_policy.logistic_iterations,
        )
        parameters["intercept"] = intercept
        for index, ((mean, scale), weight) in enumerate(zip(means_scales, weights, strict=True)):
            parameters[f"mean_{index}"] = mean
            parameters[f"scale_{index}"] = scale
            parameters[f"weight_{index}"] = weight
    elif kind is not BaselineKind.B0_BASE_RATE:
        raise ValueError(f"unsupported baseline kind: {kind}")

    material = {
        "kind": kind.value,
        "event_key": event_key,
        "feature_keys": list(used_features),
        "parameters": parameters,
        "training_feature_row_ids": list(ids),
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return FittedBaselineModel(
        fit_id=f"baseline-fit:sha256:{digest}",
        kind=kind,
        event_key=event_key,
        feature_keys=used_features,
        parameters=parameters,
        training_feature_row_ids=ids,
    )
