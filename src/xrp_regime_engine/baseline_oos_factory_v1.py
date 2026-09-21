from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from xrp_regime_engine.baseline_models_v1 import (
    BaselineKind,
    BaselineTrainingPolicy,
    binary_event_actual,
    fit_baseline_model,
)
from xrp_regime_engine.calibration_evidence_v1 import (
    CalibrationEvidenceV1,
    build_calibration_evidence,
    join_resolved_predictions,
)
from xrp_regime_engine.future_labels_v1 import FutureOutcomeLabel
from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow
from xrp_regime_engine.oos_predictions_v1 import (
    OOSPrediction,
    ResolvedOOSOutcome,
    resolve_oos_outcome,
)
from xrp_regime_engine.walk_forward_v1 import (
    LabeledFeatureRow,
    WalkForwardFoldPlan,
    join_labeled_rows,
)


class BaselineSkillState(StrEnum):
    REFERENCE_BASELINE = "REFERENCE_BASELINE"
    ELIGIBLE_CHALLENGER = "ELIGIBLE_CHALLENGER"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class BaselineSkillPolicy:
    min_oos_predictions: int = 50
    min_class_count: int = 5
    min_brier_improvement: float = 0.0
    max_log_loss_regression: float = 0.0

    def __post_init__(self) -> None:
        if self.min_oos_predictions < 1 or self.min_class_count < 1:
            raise ValueError("baseline skill sample thresholds must be positive")
        if self.min_brier_improvement < 0 or self.max_log_loss_regression < 0:
            raise ValueError("baseline skill tolerances cannot be negative")


@dataclass(frozen=True, slots=True)
class BaselineModelSkill:
    kind: BaselineKind
    state: BaselineSkillState
    evidence_id: str
    sample_count: int
    positive_count: int
    negative_count: int
    brier_score: float
    log_loss: float
    brier_improvement_vs_b0: float
    log_loss_delta_vs_b0: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BaselineOOSRun:
    run_id: str
    run_sha256: str
    event_key: str
    horizon: str
    model_kinds: tuple[BaselineKind, ...]
    fold_ids: tuple[str, ...]
    predictions: tuple[OOSPrediction, ...]
    outcomes: tuple[ResolvedOOSOutcome, ...]
    skills: tuple[BaselineModelSkill, ...]
    development_challenger: BaselineKind | None
    final_holdout_untouched: bool = True
    probability_calibrated: bool = False
    production_ready: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _validate_folds(
    folds: Sequence[WalkForwardFoldPlan],
) -> tuple[WalkForwardFoldPlan, ...]:
    if not folds:
        raise ValueError("walk-forward folds cannot be empty")
    ordered = tuple(sorted(folds, key=lambda item: item.fold_index))
    ids = [item.fold_id for item in ordered]
    if len(ids) != len(set(ids)):
        raise ValueError("walk-forward fold_id values must be unique")
    if len({item.horizon for item in ordered}) != 1:
        raise ValueError("baseline OOS run cannot mix horizons")
    if [item.fold_index for item in ordered] != list(range(len(ordered))):
        raise ValueError("walk-forward fold_index values must be contiguous from zero")
    return ordered


def _rows_by_feature_id(
    features: Sequence[HistoricalFeatureRow],
    labels: Sequence[FutureOutcomeLabel],
) -> dict[str, LabeledFeatureRow]:
    rows = join_labeled_rows(features, labels)
    return {item.feature.feature_row_id: item for item in rows}


def _fold_rows(
    fold: WalkForwardFoldPlan,
    rows: dict[str, LabeledFeatureRow],
) -> tuple[tuple[LabeledFeatureRow, ...], tuple[LabeledFeatureRow, ...]]:
    try:
        train = tuple(rows[item] for item in fold.train_feature_row_ids)
        test = tuple(rows[item] for item in fold.test_feature_row_ids)
    except KeyError as exc:
        raise ValueError(f"fold references unknown feature_row_id: {exc.args[0]}") from exc
    if not train or not test:
        raise ValueError("fold requires non-empty train and test rows")
    for row in train:
        if row.label.resolved_at >= fold.cutoff_at:
            raise ValueError("training label is unresolved at fold cutoff")
    for row in test:
        if row.feature.horizon is not fold.horizon:
            raise ValueError("test row horizon does not match fold horizon")
    return train, test


def _skill_entry(
    kind: BaselineKind,
    evidence: CalibrationEvidenceV1,
    b0: CalibrationEvidenceV1,
    policy: BaselineSkillPolicy,
) -> BaselineModelSkill:
    brier_improvement = b0.brier_score - evidence.brier_score
    log_loss_delta = evidence.log_loss - b0.log_loss
    if kind is BaselineKind.B0_BASE_RATE:
        return BaselineModelSkill(
            kind=kind,
            state=BaselineSkillState.REFERENCE_BASELINE,
            evidence_id=evidence.evidence_id,
            sample_count=evidence.sample_count,
            positive_count=evidence.positive_count,
            negative_count=evidence.negative_count,
            brier_score=evidence.brier_score,
            log_loss=evidence.log_loss,
            brier_improvement_vs_b0=0.0,
            log_loss_delta_vs_b0=0.0,
            reasons=(),
        )

    reasons: list[str] = []
    if evidence.sample_count < policy.min_oos_predictions:
        reasons.append("INSUFFICIENT_OOS_SAMPLE")
    if evidence.positive_count < policy.min_class_count:
        reasons.append("INSUFFICIENT_POSITIVE_CLASS")
    if evidence.negative_count < policy.min_class_count:
        reasons.append("INSUFFICIENT_NEGATIVE_CLASS")
    if brier_improvement < policy.min_brier_improvement:
        reasons.append("NO_BRIER_IMPROVEMENT")
    if log_loss_delta > policy.max_log_loss_regression:
        reasons.append("LOG_LOSS_REGRESSION")
    state = (
        BaselineSkillState.ELIGIBLE_CHALLENGER
        if not reasons
        else BaselineSkillState.REJECTED
    )
    return BaselineModelSkill(
        kind=kind,
        state=state,
        evidence_id=evidence.evidence_id,
        sample_count=evidence.sample_count,
        positive_count=evidence.positive_count,
        negative_count=evidence.negative_count,
        brier_score=evidence.brier_score,
        log_loss=evidence.log_loss,
        brier_improvement_vs_b0=brier_improvement,
        log_loss_delta_vs_b0=log_loss_delta,
        reasons=tuple(reasons),
    )


def run_baseline_oos_factory(
    *,
    features: Sequence[HistoricalFeatureRow],
    labels: Sequence[FutureOutcomeLabel],
    folds: Sequence[WalkForwardFoldPlan],
    event_key: str,
    feature_keys: Sequence[str],
    momentum_feature_key: str,
    model_kinds: Sequence[BaselineKind] = tuple(BaselineKind),
    training_policy: BaselineTrainingPolicy | None = None,
    skill_policy: BaselineSkillPolicy | None = None,
) -> BaselineOOSRun:
    if not event_key.strip():
        raise ValueError("event_key is required")
    ordered_folds = _validate_folds(folds)
    rows = _rows_by_feature_id(features, labels)
    kinds = tuple(dict.fromkeys(model_kinds))
    if not kinds:
        raise ValueError("at least one baseline model kind is required")
    if BaselineKind.B0_BASE_RATE not in kinds:
        raise ValueError("B0_BASE_RATE reference is mandatory")
    selected_skill_policy = skill_policy or BaselineSkillPolicy()
    selected_training_policy = training_policy or BaselineTrainingPolicy()

    predictions: list[OOSPrediction] = []
    outcomes: list[ResolvedOOSOutcome] = []
    for fold in ordered_folds:
        train_rows, test_rows = _fold_rows(fold, rows)
        for kind in kinds:
            model = fit_baseline_model(
                kind,
                train_rows,
                event_key=event_key,
                feature_keys=feature_keys,
                momentum_feature_key=momentum_feature_key,
                policy=selected_training_policy,
            )
            for row in test_rows:
                score = model.predict(row.feature)
                prediction = OOSPrediction.build(
                    fold=fold,
                    feature_row_id=row.feature.feature_row_id,
                    prediction_time=row.feature.prediction_time,
                    horizon=row.feature.horizon,
                    event_key=event_key,
                    model_id=f"baseline:{kind.value}",
                    model_version="baseline-v1",
                    model_training_cutoff=fold.cutoff_at,
                    feature_schema_version=row.feature.feature_schema_version,
                    provider_universe_version=row.feature.provider_universe_version,
                    source_snapshot_ids=row.feature.source_snapshot_ids,
                    raw_score=score,
                )
                outcome = resolve_oos_outcome(prediction, row.label)
                predictions.append(prediction)
                outcomes.append(outcome)

    evidence_by_kind: dict[BaselineKind, CalibrationEvidenceV1] = {}
    for kind in kinds:
        model_id = f"baseline:{kind.value}"
        model_predictions = tuple(item for item in predictions if item.model_id == model_id)
        prediction_ids = {item.prediction_id for item in model_predictions}
        model_outcomes = tuple(item for item in outcomes if item.prediction_id in prediction_ids)
        resolved = join_resolved_predictions(model_predictions, model_outcomes)
        actual_rate = sum(1 for item in resolved if item.actual) / len(resolved)
        evidence_by_kind[kind] = build_calibration_evidence(
            resolved,
            reference_base_rate=actual_rate,
        )

    b0 = evidence_by_kind[BaselineKind.B0_BASE_RATE]
    skills = tuple(
        _skill_entry(kind, evidence_by_kind[kind], b0, selected_skill_policy)
        for kind in kinds
    )
    eligible = [
        item
        for item in skills
        if item.state is BaselineSkillState.ELIGIBLE_CHALLENGER
    ]
    development_challenger = (
        min(eligible, key=lambda item: (item.brier_score, item.log_loss, item.kind.value)).kind
        if eligible
        else None
    )
    material: dict[str, object] = {
        "event_key": event_key,
        "horizon": ordered_folds[0].horizon.value,
        "model_kinds": [item.value for item in kinds],
        "fold_ids": [item.fold_id for item in ordered_folds],
        "prediction_ids": [item.prediction_id for item in predictions],
        "outcome_ids": [item.outcome_id for item in outcomes],
        "skills": [
            {
                "kind": item.kind.value,
                "state": item.state.value,
                "evidence_id": item.evidence_id,
                "brier_score": item.brier_score,
                "log_loss": item.log_loss,
                "reasons": list(item.reasons),
            }
            for item in skills
        ],
        "development_challenger": (
            development_challenger.value if development_challenger is not None else None
        ),
        "final_holdout_untouched": True,
        "probability_calibrated": False,
        "production_ready": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return BaselineOOSRun(
        run_id=f"baseline-oos-run:sha256:{digest}",
        run_sha256=digest,
        event_key=event_key,
        horizon=ordered_folds[0].horizon.value,
        model_kinds=kinds,
        fold_ids=tuple(item.fold_id for item in ordered_folds),
        predictions=tuple(predictions),
        outcomes=tuple(outcomes),
        skills=skills,
        development_challenger=development_challenger,
    )
