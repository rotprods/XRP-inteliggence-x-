from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from xrp_regime_engine.research_horizon import ResearchHorizon

REQUIRED_QUANTILES: tuple[float, ...] = (0.10, 0.25, 0.50, 0.75, 0.90)


class FoldPlanLike(Protocol):
    fold_id: str
    horizon: ResearchHorizon
    cutoff_at: datetime
    train_feature_row_ids: tuple[str, ...]
    test_feature_row_ids: tuple[str, ...]
    test_prediction_start: datetime
    test_prediction_end: datetime


class FutureReturnLabelLike(Protocol):
    label_id: str
    feature_row_id: str
    prediction_time: datetime
    horizon: ResearchHorizon
    label_end_at: datetime
    resolved_at: datetime
    future_return: float


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _nonempty(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _sha_prefixed(value: str, prefix: str, field: str) -> str:
    if not value.startswith(prefix):
        raise ValueError(f"{field} must use {prefix}<digest>")
    digest = value.removeprefix(prefix)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"{field} digest must be lowercase SHA-256")
    return value


def _finite(value: float, field: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field} must be finite")
    return numeric


def _training_digest(feature_ids: Sequence[str]) -> str:
    ordered = tuple(feature_ids)
    if not ordered:
        raise ValueError("training feature set cannot be empty")
    if len(ordered) != len(set(ordered)):
        raise ValueError("training feature ids must be unique")
    return sha256(_canonical(list(ordered)).encode()).hexdigest()


def _normalize_quantiles(
    values: Mapping[float, float],
) -> tuple[tuple[float, float], ...]:
    keys = tuple(sorted(float(key) for key in values))
    if keys != REQUIRED_QUANTILES:
        raise ValueError(
            "return distribution must provide exactly P10/P25/P50/P75/P90"
        )
    normalized = tuple(
        (key, _finite(values[key], f"quantile {key}")) for key in keys
    )
    quantile_values = [value for _, value in normalized]
    if quantile_values != sorted(quantile_values):
        raise ValueError("return quantiles must be non-decreasing")
    return normalized


@dataclass(frozen=True, slots=True)
class OOSReturnDistributionCandidate:
    distribution_id: str
    distribution_sha256: str
    fold_id: str
    feature_row_id: str
    prediction_time: datetime
    horizon: ResearchHorizon
    model_id: str
    model_version: str
    model_training_cutoff: datetime
    training_feature_digest: str
    training_sample_count: int
    source_snapshot_ids: tuple[str, ...]
    quantiles: tuple[tuple[float, float], ...]
    distribution_calibrated: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0

    @classmethod
    def build(
        cls,
        *,
        fold: FoldPlanLike,
        feature_row_id: str,
        prediction_time: datetime,
        horizon: ResearchHorizon,
        model_id: str,
        model_version: str,
        model_training_cutoff: datetime,
        source_snapshot_ids: Sequence[str],
        quantiles: Mapping[float, float],
    ) -> OOSReturnDistributionCandidate:
        feature_id = _sha_prefixed(
            feature_row_id,
            "feature:sha256:",
            "feature_row_id",
        )
        prediction = _utc(prediction_time, "prediction_time")
        cutoff = _utc(model_training_cutoff, "model_training_cutoff")
        fold_cutoff = _utc(fold.cutoff_at, "fold.cutoff_at")
        test_start = _utc(
            fold.test_prediction_start,
            "fold.test_prediction_start",
        )
        test_end = _utc(
            fold.test_prediction_end,
            "fold.test_prediction_end",
        )
        if horizon is not fold.horizon:
            raise ValueError("distribution horizon must match fold horizon")
        if feature_id not in fold.test_feature_row_ids:
            raise ValueError("feature_row_id is not part of the fold test set")
        if not test_start <= prediction <= test_end:
            raise ValueError("prediction_time must lie inside fold test interval")
        if cutoff > fold_cutoff:
            raise ValueError("model_training_cutoff cannot exceed fold cutoff")
        training_digest = _training_digest(fold.train_feature_row_ids)
        snapshots = tuple(
            sorted(
                {
                    _sha_prefixed(
                        item,
                        "snapshot:sha256:",
                        "source_snapshot_id",
                    )
                    for item in source_snapshot_ids
                }
            )
        )
        if not snapshots:
            raise ValueError("at least one source snapshot is required")
        normalized_quantiles = _normalize_quantiles(quantiles)
        material: dict[str, object] = {
            "fold_id": _nonempty(fold.fold_id, "fold_id"),
            "feature_row_id": feature_id,
            "prediction_time": prediction.isoformat(),
            "horizon": horizon.value,
            "model_id": _nonempty(model_id, "model_id"),
            "model_version": _nonempty(model_version, "model_version"),
            "model_training_cutoff": cutoff.isoformat(),
            "training_feature_digest": training_digest,
            "training_sample_count": len(fold.train_feature_row_ids),
            "source_snapshot_ids": list(snapshots),
            "quantiles": [
                [level, value] for level, value in normalized_quantiles
            ],
            "distribution_calibrated": False,
            "decision_authority": False,
            "execution_weight": 0.0,
        }
        digest = sha256(_canonical(material).encode()).hexdigest()
        return cls(
            distribution_id=f"oos-return-distribution:sha256:{digest}",
            distribution_sha256=digest,
            fold_id=str(material["fold_id"]),
            feature_row_id=feature_id,
            prediction_time=prediction,
            horizon=horizon,
            model_id=str(material["model_id"]),
            model_version=str(material["model_version"]),
            model_training_cutoff=cutoff,
            training_feature_digest=training_digest,
            training_sample_count=len(fold.train_feature_row_ids),
            source_snapshot_ids=snapshots,
            quantiles=normalized_quantiles,
        )

    def quantile(self, level: float) -> float:
        for candidate_level, value in self.quantiles:
            if candidate_level == level:
                return value
        raise KeyError(level)


@dataclass(frozen=True, slots=True)
class ResolvedReturnDistribution:
    distribution_id: str
    label_id: str
    feature_row_id: str
    prediction_time: datetime
    horizon: ResearchHorizon
    label_end_at: datetime
    resolved_at: datetime
    actual_return: float
    quantiles: tuple[tuple[float, float], ...]


def resolve_return_distribution(
    distribution: OOSReturnDistributionCandidate,
    label: FutureReturnLabelLike,
) -> ResolvedReturnDistribution:
    if distribution.feature_row_id != label.feature_row_id:
        raise ValueError("distribution and label feature_row_id must match")
    if distribution.prediction_time != _utc(
        label.prediction_time,
        "label.prediction_time",
    ):
        raise ValueError("distribution and label prediction_time must match")
    if distribution.horizon is not label.horizon:
        raise ValueError("distribution and label horizon must match")
    label_end = _utc(label.label_end_at, "label.label_end_at")
    resolved = _utc(label.resolved_at, "label.resolved_at")
    if resolved < label_end:
        raise ValueError(
            "distribution outcome cannot resolve before label_end_at"
        )
    actual = _finite(label.future_return, "future_return")
    return ResolvedReturnDistribution(
        distribution_id=distribution.distribution_id,
        label_id=_nonempty(label.label_id, "label_id"),
        feature_row_id=distribution.feature_row_id,
        prediction_time=distribution.prediction_time,
        horizon=distribution.horizon,
        label_end_at=label_end,
        resolved_at=resolved,
        actual_return=actual,
        quantiles=distribution.quantiles,
    )


def _pinball(actual: float, forecast: float, quantile: float) -> float:
    error = actual - forecast
    return (
        quantile * error
        if error >= 0
        else (quantile - 1.0) * error
    )


@dataclass(frozen=True, slots=True)
class QuantileEvidence:
    quantile: float
    mean_pinball_loss: float
    empirical_coverage: float
    coverage_error: float


@dataclass(frozen=True, slots=True)
class ReturnDistributionEvidenceV1:
    evidence_id: str
    evidence_sha256: str
    horizon: ResearchHorizon
    sample_count: int
    evaluation_start: datetime
    evaluation_end: datetime
    quantile_evidence: tuple[QuantileEvidence, ...]
    interval_50_coverage: float
    interval_80_coverage: float
    median_absolute_error: float
    distribution_calibrated: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0


def build_return_distribution_evidence(
    rows: Sequence[ResolvedReturnDistribution],
) -> ReturnDistributionEvidenceV1:
    if not rows:
        raise ValueError("resolved return distributions cannot be empty")
    ordered = tuple(
        sorted(
            rows,
            key=lambda item: (
                item.prediction_time,
                item.distribution_id,
            ),
        )
    )
    horizons = {item.horizon for item in ordered}
    if len(horizons) != 1:
        raise ValueError("distribution evidence must contain one horizon")
    for item in ordered:
        _utc(item.prediction_time, "prediction_time")
        _utc(item.resolved_at, "resolved_at")
        _finite(item.actual_return, "actual_return")
        if tuple(level for level, _ in item.quantiles) != REQUIRED_QUANTILES:
            raise ValueError(
                "resolved row quantiles do not match canonical levels"
            )
        values = [value for _, value in item.quantiles]
        if values != sorted(values):
            raise ValueError("resolved row contains crossing quantiles")

    q_evidence: list[QuantileEvidence] = []
    for level in REQUIRED_QUANTILES:
        forecasts = [dict(item.quantiles)[level] for item in ordered]
        actuals = [item.actual_return for item in ordered]
        pinball = sum(
            _pinball(actual, forecast, level)
            for actual, forecast in zip(
                actuals,
                forecasts,
                strict=True,
            )
        ) / len(ordered)
        empirical = sum(
            1
            for actual, forecast in zip(
                actuals,
                forecasts,
                strict=True,
            )
            if actual <= forecast
        ) / len(ordered)
        q_evidence.append(
            QuantileEvidence(
                quantile=level,
                mean_pinball_loss=pinball,
                empirical_coverage=empirical,
                coverage_error=empirical - level,
            )
        )

    interval_50 = sum(
        1
        for item in ordered
        if dict(item.quantiles)[0.25]
        <= item.actual_return
        <= dict(item.quantiles)[0.75]
    ) / len(ordered)
    interval_80 = sum(
        1
        for item in ordered
        if dict(item.quantiles)[0.10]
        <= item.actual_return
        <= dict(item.quantiles)[0.90]
    ) / len(ordered)
    median_mae = sum(
        abs(
            item.actual_return
            - dict(item.quantiles)[0.50]
        )
        for item in ordered
    ) / len(ordered)

    material: dict[str, object] = {
        "horizon": ordered[0].horizon.value,
        "distribution_ids": [
            item.distribution_id for item in ordered
        ],
        "sample_count": len(ordered),
        "evaluation_start": ordered[0].prediction_time.isoformat(),
        "evaluation_end": ordered[-1].prediction_time.isoformat(),
        "quantile_evidence": [
            {
                "quantile": item.quantile,
                "mean_pinball_loss": item.mean_pinball_loss,
                "empirical_coverage": item.empirical_coverage,
                "coverage_error": item.coverage_error,
            }
            for item in q_evidence
        ],
        "interval_50_coverage": interval_50,
        "interval_80_coverage": interval_80,
        "median_absolute_error": median_mae,
        "distribution_calibrated": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return ReturnDistributionEvidenceV1(
        evidence_id=f"return-distribution-evidence:sha256:{digest}",
        evidence_sha256=digest,
        horizon=ordered[0].horizon,
        sample_count=len(ordered),
        evaluation_start=ordered[0].prediction_time,
        evaluation_end=ordered[-1].prediction_time,
        quantile_evidence=tuple(q_evidence),
        interval_50_coverage=interval_50,
        interval_80_coverage=interval_80,
        median_absolute_error=median_mae,
    )
