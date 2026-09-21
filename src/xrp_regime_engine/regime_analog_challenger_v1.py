from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from hashlib import sha256
from typing import cast

from xrp_regime_engine.baseline_models_v1 import BaselineKind, binary_event_actual
from xrp_regime_engine.baseline_oos_factory_v1 import (
    BaselineOOSRun,
    BaselineSkillState,
)
from xrp_regime_engine.calibration_evidence_v1 import (
    CalibrationEvidenceV1,
    build_calibration_evidence,
    join_resolved_predictions,
)
from xrp_regime_engine.future_labels_v1 import FutureOutcomeLabel
from xrp_regime_engine.historical_analog_v1 import (
    AnalogSearchConfig,
    AnalogSearchStatus,
    DistanceMetric,
    HistoricalAnalogMatch,
    run_analog_sensitivity,
    search_historical_analogs,
)
from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow
from xrp_regime_engine.oos_predictions_v1 import (
    FoldPlanLike,
    FutureOutcomeLabelLike,
    OOSPrediction,
    ResolvedOOSOutcome,
    resolve_oos_outcome,
)
from xrp_regime_engine.regime_state_v1 import (
    RegimeClassifierPolicy,
    RegimeState,
    canonical_regime_policy,
    classify_regime,
)
from xrp_regime_engine.research_horizon import ResearchHorizon
from xrp_regime_engine.walk_forward_v1 import (
    LabeledFeatureRow,
    WalkForwardFoldPlan,
    join_labeled_rows,
)


class RegimeAnalogSkillState(StrEnum):
    ELIGIBLE_REGIME_CHALLENGER = "ELIGIBLE_REGIME_CHALLENGER"
    NO_DEMONSTRATED_REGIME_SKILL = "NO_DEMONSTRATED_REGIME_SKILL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class RegimeAnalogChallengerPolicy:
    analog_config: AnalogSearchConfig = field(
        default_factory=lambda: AnalogSearchConfig(
            k=5,
            min_history=10,
            same_regime_only=True,
        )
    )
    prior_strength: float = 1.0
    require_stable_sensitivity: bool = True
    sensitivity_metrics: tuple[DistanceMetric, ...] = tuple(DistanceMetric)
    ablation_sets: tuple[tuple[str, ...], ...] = ((), ("relative_strength",))
    lookbacks: tuple[timedelta | None, ...] = (None,)
    provider_universe_filters: tuple[tuple[str, ...], ...] = ((),)
    min_ready_sensitivity_scenarios: int = 3
    min_top_k_overlap: float = 0.40
    min_top_regime_agreement: float = 0.60
    min_oos_predictions: int = 30
    min_class_count: int = 5
    max_suppressed_fraction: float = 0.50
    min_brier_improvement: float = 0.0
    max_log_loss_regression: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.prior_strength) or self.prior_strength < 0:
            raise ValueError("prior_strength must be finite and non-negative")
        if self.min_ready_sensitivity_scenarios < 1:
            raise ValueError("min_ready_sensitivity_scenarios must be positive")
        for name, value in (
            ("min_top_k_overlap", self.min_top_k_overlap),
            ("min_top_regime_agreement", self.min_top_regime_agreement),
            ("max_suppressed_fraction", self.max_suppressed_fraction),
        ):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and within [0, 1]")
        if self.min_oos_predictions < 1 or self.min_class_count < 1:
            raise ValueError("skill sample thresholds must be positive")
        if self.min_brier_improvement < 0 or self.max_log_loss_regression < 0:
            raise ValueError("skill tolerances cannot be negative")
        if not self.sensitivity_metrics:
            raise ValueError("sensitivity_metrics cannot be empty")
        if not self.ablation_sets or not self.lookbacks or not self.provider_universe_filters:
            raise ValueError("sensitivity scenario axes cannot be empty")


@dataclass(frozen=True, slots=True)
class AnalogPredictionLineage:
    prediction_id: str
    fold_id: str
    feature_row_id: str
    query_state_id: str
    analog_report_id: str
    sensitivity_report_id: str | None
    matched_state_ids: tuple[str, ...]
    matched_feature_row_ids: tuple[str, ...]
    model_fit_id: str


@dataclass(frozen=True, slots=True)
class AnalogSuppression:
    fold_id: str
    feature_row_id: str
    query_state_id: str
    analog_report_id: str | None
    sensitivity_report_id: str | None
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegimeAnalogOOSRun:
    run_id: str
    run_sha256: str
    dataset_version_id: str
    event_key: str
    horizon: ResearchHorizon
    fold_ids: tuple[str, ...]
    model_fit_ids: tuple[str, ...]
    predictions: tuple[OOSPrediction, ...]
    outcomes: tuple[ResolvedOOSOutcome, ...]
    lineages: tuple[AnalogPredictionLineage, ...]
    suppressions: tuple[AnalogSuppression, ...]
    analog_evidence: CalibrationEvidenceV1 | None
    comparator_kind: BaselineKind | None
    comparator_evidence: CalibrationEvidenceV1 | None
    state: RegimeAnalogSkillState
    reasons: tuple[str, ...]
    brier_improvement_vs_baseline: float | None
    log_loss_delta_vs_baseline: float | None
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


def _config_payload(config: AnalogSearchConfig) -> dict[str, object]:
    return {
        "k": config.k,
        "min_history": config.min_history,
        "metric": config.metric.value,
        "same_regime_only": config.same_regime_only,
        "signal_keys": list(config.signal_keys),
        "excluded_signals": list(config.excluded_signals),
        "max_lookback_seconds": (
            config.max_lookback.total_seconds() if config.max_lookback is not None else None
        ),
        "provider_universe_versions": list(config.provider_universe_versions),
    }


def _validate_baseline_run(
    baseline_run: BaselineOOSRun,
    folds: Sequence[WalkForwardFoldPlan],
    event_key: str,
) -> tuple[WalkForwardFoldPlan, ...]:
    if not baseline_run.final_holdout_untouched:
        raise ValueError("baseline run must preserve final holdout")
    if (
        baseline_run.probability_calibrated
        or baseline_run.production_ready
        or baseline_run.decision_authority
        or baseline_run.execution_weight != 0.0
    ):
        raise ValueError("baseline run must remain non-authoritative")
    if not baseline_run.dataset_version_id.startswith("dataset-version:sha256:"):
        raise ValueError("baseline run lacks DatasetVersion identity")
    if baseline_run.event_key != event_key:
        raise ValueError("baseline run event_key mismatch")
    if not folds:
        raise ValueError("folds cannot be empty")
    ordered = tuple(sorted(folds, key=lambda item: item.fold_index))
    if tuple(item.fold_id for item in ordered) != baseline_run.fold_ids:
        raise ValueError("baseline run fold identity mismatch")
    if any(item.horizon is not baseline_run.horizon for item in ordered):
        raise ValueError("baseline run horizon mismatch")
    return ordered


def _row_map(
    features: Sequence[HistoricalFeatureRow],
    labels: Sequence[FutureOutcomeLabel],
) -> dict[str, LabeledFeatureRow]:
    rows = join_labeled_rows(features, labels)
    return {item.feature.feature_row_id: item for item in rows}


def _fold_rows(
    fold: WalkForwardFoldPlan,
    rows: Mapping[str, LabeledFeatureRow],
) -> tuple[tuple[LabeledFeatureRow, ...], tuple[LabeledFeatureRow, ...]]:
    try:
        train = tuple(rows[item] for item in fold.train_feature_row_ids)
        test = tuple(rows[item] for item in fold.test_feature_row_ids)
    except KeyError as exc:
        raise ValueError(f"fold references unknown feature_row_id: {exc.args[0]}") from exc
    if not train or not test:
        raise ValueError("fold requires non-empty train and test rows")
    if any(item.label.resolved_at >= fold.cutoff_at for item in train):
        raise ValueError("training label is unresolved at fold cutoff")
    if any(item.feature.horizon is not fold.horizon for item in (*train, *test)):
        raise ValueError("fold row horizon mismatch")
    return train, test


def _smoothed_rate(rows: Sequence[LabeledFeatureRow], event_key: str) -> float:
    positives = sum(1 for item in rows if binary_event_actual(event_key, item))
    return (positives + 1.0) / (len(rows) + 2.0)


def _fit_id(
    fold: WalkForwardFoldPlan,
    states: Sequence[RegimeState],
    *,
    event_key: str,
    regime_policy: RegimeClassifierPolicy,
    challenger_policy: RegimeAnalogChallengerPolicy,
) -> str:
    material = {
        "fold_id": fold.fold_id,
        "event_key": event_key,
        "regime_policy_id": regime_policy.policy_id,
        "analog_config": _config_payload(challenger_policy.analog_config),
        "prior_strength": challenger_policy.prior_strength,
        "training_state_ids": [item.state_id for item in states],
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return f"regime-analog-fit:sha256:{digest}"


def _weighted_probability(
    report_matches: Sequence[HistoricalAnalogMatch],
    state_to_row: Mapping[str, LabeledFeatureRow],
    *,
    event_key: str,
    prior_rate: float,
    prior_strength: float,
) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
    weighted_positive = prior_rate * prior_strength
    total_weight = prior_strength
    state_ids: list[str] = []
    feature_ids: list[str] = []
    for match in report_matches:
        state_id = match.state_id
        similarity = match.similarity
        if not math.isfinite(similarity) or similarity <= 0:
            raise ValueError("analog similarity must be finite and positive")
        row = state_to_row.get(state_id)
        if row is None:
            raise ValueError("analog report references state outside training lineage")
        actual = binary_event_actual(event_key, row)
        weighted_positive += similarity * (1.0 if actual else 0.0)
        total_weight += similarity
        state_ids.append(state_id)
        feature_ids.append(row.feature.feature_row_id)
    if total_weight <= 0:
        raise ValueError("analog probability denominator must be positive")
    return (
        min(1.0, max(0.0, weighted_positive / total_weight)),
        tuple(state_ids),
        tuple(feature_ids),
    )


def _baseline_evidence_on_subset(
    baseline_run: BaselineOOSRun,
    feature_ids: set[str],
) -> dict[BaselineKind, CalibrationEvidenceV1]:
    eligible_kinds = {
        skill.kind
        for skill in baseline_run.skills
        if skill.state
        in {
            BaselineSkillState.REFERENCE_BASELINE,
            BaselineSkillState.ELIGIBLE_CHALLENGER,
        }
    }
    evidence: dict[BaselineKind, CalibrationEvidenceV1] = {}
    outcome_by_prediction = {item.prediction_id: item for item in baseline_run.outcomes}
    for kind in sorted(eligible_kinds, key=lambda item: item.value):
        model_id = f"baseline:{kind.value}"
        predictions = tuple(
            item
            for item in baseline_run.predictions
            if item.model_id == model_id and item.feature_row_id in feature_ids
        )
        outcomes = tuple(
            outcome_by_prediction[item.prediction_id]
            for item in predictions
            if item.prediction_id in outcome_by_prediction
        )
        if not predictions or len(predictions) != len(outcomes):
            continue
        records = join_resolved_predictions(predictions, outcomes)
        base_rate = sum(1 for item in records if item.actual) / len(records)
        evidence[kind] = build_calibration_evidence(
            records,
            reference_base_rate=base_rate,
        )
    return evidence


def run_regime_analog_oos_challenger(
    *,
    features: Sequence[HistoricalFeatureRow],
    labels: Sequence[FutureOutcomeLabel],
    folds: Sequence[WalkForwardFoldPlan],
    baseline_run: BaselineOOSRun,
    event_key: str,
    regime_policy: RegimeClassifierPolicy | None = None,
    challenger_policy: RegimeAnalogChallengerPolicy | None = None,
) -> RegimeAnalogOOSRun:
    selected_regime_policy = regime_policy or canonical_regime_policy()
    selected_policy = challenger_policy or RegimeAnalogChallengerPolicy()
    ordered_folds = _validate_baseline_run(baseline_run, folds, event_key)
    rows = _row_map(features, labels)

    predictions: list[OOSPrediction] = []
    outcomes: list[ResolvedOOSOutcome] = []
    lineages: list[AnalogPredictionLineage] = []
    suppressions: list[AnalogSuppression] = []
    fit_ids: list[str] = []

    for fold in ordered_folds:
        train_rows, test_rows = _fold_rows(fold, rows)
        training_states = tuple(
            classify_regime(item.feature, policy=selected_regime_policy) for item in train_rows
        )
        state_to_row = {
            state.state_id: row for state, row in zip(training_states, train_rows, strict=True)
        }
        if len(state_to_row) != len(training_states):
            raise ValueError("training regime state identity collision")
        fit_id = _fit_id(
            fold,
            training_states,
            event_key=event_key,
            regime_policy=selected_regime_policy,
            challenger_policy=selected_policy,
        )
        fit_ids.append(fit_id)
        prior_rate = _smoothed_rate(train_rows, event_key)

        for row in test_rows:
            query_state = classify_regime(
                row.feature,
                policy=selected_regime_policy,
            )
            analog_report = search_historical_analogs(
                query_state,
                training_states,
                config=selected_policy.analog_config,
            )
            suppression_reasons: list[str] = []
            sensitivity_report_id: str | None = None
            if analog_report.status is not AnalogSearchStatus.READY:
                suppression_reasons.extend(analog_report.reasons)
            if not suppression_reasons and selected_policy.require_stable_sensitivity:
                sensitivity = run_analog_sensitivity(
                    query_state,
                    training_states,
                    base_config=selected_policy.analog_config,
                    metrics=selected_policy.sensitivity_metrics,
                    ablation_sets=selected_policy.ablation_sets,
                    lookbacks=selected_policy.lookbacks,
                    provider_universe_filters=selected_policy.provider_universe_filters,
                    min_ready_scenarios=selected_policy.min_ready_sensitivity_scenarios,
                    min_top_k_overlap=selected_policy.min_top_k_overlap,
                    min_top_regime_agreement=selected_policy.min_top_regime_agreement,
                )
                sensitivity_report_id = sensitivity.report_id
                if not sensitivity.stable:
                    suppression_reasons.extend(sensitivity.reasons)

            if suppression_reasons:
                suppressions.append(
                    AnalogSuppression(
                        fold_id=fold.fold_id,
                        feature_row_id=row.feature.feature_row_id,
                        query_state_id=query_state.state_id,
                        analog_report_id=analog_report.report_id,
                        sensitivity_report_id=sensitivity_report_id,
                        reasons=tuple(sorted(set(suppression_reasons))),
                    )
                )
                continue

            score, matched_states, matched_features = _weighted_probability(
                analog_report.matches,
                state_to_row,
                event_key=event_key,
                prior_rate=prior_rate,
                prior_strength=selected_policy.prior_strength,
            )
            prediction = OOSPrediction.build(
                fold=cast(FoldPlanLike, fold),
                feature_row_id=row.feature.feature_row_id,
                prediction_time=row.feature.prediction_time,
                horizon=row.feature.horizon,
                event_key=event_key,
                model_id="regime-analog:weighted-knn",
                model_version=fit_id,
                model_training_cutoff=fold.cutoff_at,
                feature_schema_version=row.feature.feature_schema_version,
                provider_universe_version=row.feature.provider_universe_version,
                source_snapshot_ids=row.feature.source_snapshot_ids,
                raw_score=score,
            )
            outcome = resolve_oos_outcome(
                prediction,
                cast(FutureOutcomeLabelLike, row.label),
            )
            predictions.append(prediction)
            outcomes.append(outcome)
            lineages.append(
                AnalogPredictionLineage(
                    prediction_id=prediction.prediction_id,
                    fold_id=fold.fold_id,
                    feature_row_id=row.feature.feature_row_id,
                    query_state_id=query_state.state_id,
                    analog_report_id=analog_report.report_id,
                    sensitivity_report_id=sensitivity_report_id,
                    matched_state_ids=matched_states,
                    matched_feature_row_ids=matched_features,
                    model_fit_id=fit_id,
                )
            )

    reasons: list[str] = []
    analog_evidence: CalibrationEvidenceV1 | None = None
    comparator_kind: BaselineKind | None = None
    comparator_evidence: CalibrationEvidenceV1 | None = None
    brier_improvement: float | None = None
    log_loss_delta: float | None = None
    state = RegimeAnalogSkillState.INSUFFICIENT_EVIDENCE

    if predictions:
        records = join_resolved_predictions(tuple(predictions), tuple(outcomes))
        actual_rate = sum(1 for item in records if item.actual) / len(records)
        analog_evidence = build_calibration_evidence(
            records,
            reference_base_rate=actual_rate,
        )
        subset = {item.feature_row_id for item in predictions}
        baseline_evidence = _baseline_evidence_on_subset(
            baseline_run,
            subset,
        )
        if not baseline_evidence:
            raise ValueError("no eligible H6 baseline comparator on analog subset")
        comparator_kind, comparator_evidence = min(
            baseline_evidence.items(),
            key=lambda item: (
                item[1].brier_score,
                item[1].log_loss,
                item[0].value,
            ),
        )
        brier_improvement = comparator_evidence.brier_score - analog_evidence.brier_score
        log_loss_delta = analog_evidence.log_loss - comparator_evidence.log_loss

        if analog_evidence.sample_count < selected_policy.min_oos_predictions:
            reasons.append("INSUFFICIENT_OOS_SAMPLE")
        if analog_evidence.positive_count < selected_policy.min_class_count:
            reasons.append("INSUFFICIENT_POSITIVE_CLASS")
        if analog_evidence.negative_count < selected_policy.min_class_count:
            reasons.append("INSUFFICIENT_NEGATIVE_CLASS")
        total_test = len(predictions) + len(suppressions)
        suppressed_fraction = len(suppressions) / total_test if total_test else 1.0
        if suppressed_fraction > selected_policy.max_suppressed_fraction:
            reasons.append("EXCESSIVE_ANALOG_SUPPRESSION")
        if brier_improvement < selected_policy.min_brier_improvement:
            reasons.append("NO_BRIER_IMPROVEMENT_OVER_H6")
        if log_loss_delta > selected_policy.max_log_loss_regression:
            reasons.append("LOG_LOSS_REGRESSION_VS_H6")

        insufficiency = {
            "INSUFFICIENT_OOS_SAMPLE",
            "INSUFFICIENT_POSITIVE_CLASS",
            "INSUFFICIENT_NEGATIVE_CLASS",
            "EXCESSIVE_ANALOG_SUPPRESSION",
        }
        if any(reason in insufficiency for reason in reasons):
            state = RegimeAnalogSkillState.INSUFFICIENT_EVIDENCE
        elif reasons:
            state = RegimeAnalogSkillState.NO_DEMONSTRATED_REGIME_SKILL
        else:
            state = RegimeAnalogSkillState.ELIGIBLE_REGIME_CHALLENGER
    else:
        reasons.append("NO_READY_ANALOG_PREDICTIONS")

    material: dict[str, object] = {
        "dataset_version_id": baseline_run.dataset_version_id,
        "event_key": event_key,
        "horizon": baseline_run.horizon.value,
        "fold_ids": [item.fold_id for item in ordered_folds],
        "model_fit_ids": sorted(set(fit_ids)),
        "prediction_ids": [item.prediction_id for item in predictions],
        "outcome_ids": [item.outcome_id for item in outcomes],
        "lineage_report_ids": [item.analog_report_id for item in lineages],
        "suppressed_feature_row_ids": [item.feature_row_id for item in suppressions],
        "analog_evidence_id": (
            analog_evidence.evidence_id if analog_evidence is not None else None
        ),
        "comparator_kind": (comparator_kind.value if comparator_kind is not None else None),
        "comparator_evidence_id": (
            comparator_evidence.evidence_id if comparator_evidence is not None else None
        ),
        "state": state.value,
        "reasons": sorted(reasons),
        "brier_improvement_vs_baseline": brier_improvement,
        "log_loss_delta_vs_baseline": log_loss_delta,
        "final_holdout_untouched": True,
        "probability_calibrated": False,
        "production_ready": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return RegimeAnalogOOSRun(
        run_id=f"regime-analog-oos-run:sha256:{digest}",
        run_sha256=digest,
        dataset_version_id=baseline_run.dataset_version_id,
        event_key=event_key,
        horizon=baseline_run.horizon,
        fold_ids=tuple(item.fold_id for item in ordered_folds),
        model_fit_ids=tuple(sorted(set(fit_ids))),
        predictions=tuple(predictions),
        outcomes=tuple(outcomes),
        lineages=tuple(lineages),
        suppressions=tuple(suppressions),
        analog_evidence=analog_evidence,
        comparator_kind=comparator_kind,
        comparator_evidence=comparator_evidence,
        state=state,
        reasons=tuple(sorted(set(reasons))),
        brier_improvement_vs_baseline=brier_improvement,
        log_loss_delta_vs_baseline=log_loss_delta,
    )
