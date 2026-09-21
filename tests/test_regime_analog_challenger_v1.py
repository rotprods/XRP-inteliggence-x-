from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.baseline_models_v1 import BaselineKind, BaselineTrainingPolicy
from xrp_regime_engine.baseline_oos_factory_v1 import (
    BaselineSkillPolicy,
    run_baseline_oos_factory,
)
from xrp_regime_engine.future_labels_v1 import (
    PricePoint,
    build_future_outcome_label,
    canonical_xrp_barrier_set,
)
from xrp_regime_engine.historical_analog_v1 import (
    AnalogSearchConfig,
    DistanceMetric,
    HistoricalAnalogMatch,
)
from xrp_regime_engine.historical_contract import EligibilityClass
from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow
from xrp_regime_engine.regime_analog_challenger_v1 import (
    RegimeAnalogChallengerPolicy,
    RegimeAnalogSkillState,
    _baseline_evidence_on_subset,
    _fold_rows,
    _weighted_probability,
    run_regime_analog_oos_challenger,
)
from xrp_regime_engine.regime_state_v1 import canonical_regime_policy, classify_regime
from xrp_regime_engine.research_horizon import ResearchHorizon, horizon_end_at
from xrp_regime_engine.walk_forward_v1 import (
    LabeledFeatureRow,
    WalkForwardConfig,
    build_walk_forward_folds,
    join_labeled_rows,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
DATASET = "dataset-version:sha256:" + "a" * 64


def actual_for(index: int) -> bool:
    return ((index * 37 + 11) % 101) < 50


def feature(
    index: int,
    actual: bool,
    *,
    omit_relative: bool = False,
) -> HistoricalFeatureRow:
    policy = canonical_regime_policy()
    desired = {spec.signal: 0.0 for spec in policy.specs}
    if actual:
        desired.update(
            {
                "trend": 0.50,
                "relative_strength": 0.20,
                "spot_flow": 0.70,
                "leverage": 0.10,
                "crowding": 0.05,
                "deleveraging": 0.0,
                "breakout": 0.0,
                "distribution": 0.0,
                "volatility": 0.10,
                "drawdown_stress": 0.05,
                "liquidity": 0.20,
            }
        )
    else:
        desired.update(
            {
                "trend": -0.80,
                "relative_strength": -0.20,
                "spot_flow": -0.20,
                "leverage": 0.20,
                "crowding": 0.05,
                "deleveraging": 0.0,
                "breakout": 0.0,
                "distribution": 0.0,
                "volatility": 0.80,
                "drawdown_stress": 0.80,
                "liquidity": -0.20,
            }
        )

    families: dict[str, dict[str, float]] = {"aux": {"noise": 0.0}}
    for spec in policy.specs:
        if omit_relative and spec.signal == "relative_strength":
            continue
        family, name = spec.feature_key.split(".", 1)
        raw = spec.center + desired[spec.signal] * spec.scale / spec.direction
        families.setdefault(family, {})[name] = raw

    prediction = T0 + timedelta(days=index)
    snapshot = sha256(f"challenger:{index}:{omit_relative}".encode()).hexdigest()
    return HistoricalFeatureRow.build(
        feature_time=prediction,
        prediction_time=prediction,
        horizon=ResearchHorizon.H1,
        feature_schema_version="features-v1",
        provider_universe_version="providers-v1",
        eligibility_class=EligibilityClass.STRICT_REPLAY,
        source_snapshot_ids=(f"snapshot:sha256:{snapshot}",),
        feature_families=families,
    )


def label(item: HistoricalFeatureRow, actual: bool):
    end = horizon_end_at(item.prediction_time, item.horizon)
    return build_future_outcome_label(
        feature_row_id=item.feature_row_id,
        prediction_time=item.prediction_time,
        horizon=item.horizon,
        start_price=1.0,
        price_path=(
            PricePoint(
                at=end,
                price=1.10 if actual else 0.90,
            ),
        ),
        resolved_at=end,
        barrier_set=canonical_xrp_barrier_set(),
    )


def corpus(
    size: int = 56,
    *,
    last_missing_relative: bool = False,
):
    features = []
    labels = []
    for index in range(size):
        actual = actual_for(index)
        item = feature(
            index,
            actual,
            omit_relative=last_missing_relative and index == size - 1,
        )
        features.append(item)
        labels.append(label(item, actual))
    rows = join_labeled_rows(tuple(features), tuple(labels))
    folds = build_walk_forward_folds(
        rows,
        config=WalkForwardConfig(
            min_train_size=24,
            test_size=1,
        ),
    )
    baseline = run_baseline_oos_factory(
        dataset_version_id=DATASET,
        features=tuple(features),
        labels=tuple(labels),
        folds=folds,
        event_key="return_gt_0",
        feature_keys=("aux.noise",),
        momentum_feature_key="aux.noise",
        training_policy=BaselineTrainingPolicy(
            logistic_l2=1.0,
            logistic_learning_rate=0.1,
            logistic_iterations=100,
        ),
        skill_policy=BaselineSkillPolicy(
            min_oos_predictions=10,
            min_class_count=3,
            min_brier_improvement=0.0,
            max_log_loss_regression=0.0,
        ),
    )
    return tuple(features), tuple(labels), folds, baseline


def challenger_policy(**overrides: object) -> RegimeAnalogChallengerPolicy:
    values: dict[str, object] = {
        "analog_config": AnalogSearchConfig(
            k=5,
            min_history=5,
            same_regime_only=True,
        ),
        "prior_strength": 1.0,
        "require_stable_sensitivity": True,
        "sensitivity_metrics": tuple(DistanceMetric),
        "ablation_sets": ((), ("relative_strength",)),
        "lookbacks": (None,),
        "provider_universe_filters": ((),),
        "min_ready_sensitivity_scenarios": 3,
        "min_top_k_overlap": 0.0,
        "min_top_regime_agreement": 1.0,
        "min_oos_predictions": 10,
        "min_class_count": 3,
        "max_suppressed_fraction": 0.50,
        "min_brier_improvement": 0.0,
        "max_log_loss_regression": 0.0,
    }
    values.update(overrides)
    return RegimeAnalogChallengerPolicy(**values)  # type: ignore[arg-type]


def test_regime_analog_challenger_beats_h6_on_same_oos_subset() -> None:
    features, labels, folds, baseline = corpus()
    result = run_regime_analog_oos_challenger(
        features=features,
        labels=labels,
        folds=folds,
        baseline_run=baseline,
        event_key="return_gt_0",
        challenger_policy=challenger_policy(),
    )

    assert result.state is RegimeAnalogSkillState.ELIGIBLE_REGIME_CHALLENGER
    assert result.analog_evidence is not None
    assert result.comparator_evidence is not None
    assert result.comparator_kind is not None
    assert result.analog_evidence.sample_count == result.comparator_evidence.sample_count
    assert result.brier_improvement_vs_baseline is not None
    assert result.brier_improvement_vs_baseline > 0
    assert result.log_loss_delta_vs_baseline is not None
    assert result.log_loss_delta_vs_baseline < 0
    assert result.final_holdout_untouched
    assert not result.probability_calibrated
    assert not result.production_ready
    assert not result.decision_authority
    assert result.execution_weight == 0

    fold_by_id = {item.fold_id: item for item in folds}
    for lineage in result.lineages:
        assert set(lineage.matched_feature_row_ids) <= set(
            fold_by_id[lineage.fold_id].train_feature_row_ids
        )
        assert lineage.model_fit_id.startswith("regime-analog-fit:sha256:")
    assert all(
        item.model_version.startswith("regime-analog-fit:sha256:") for item in result.predictions
    )


def test_future_rows_outside_folds_do_not_change_challenger_result() -> None:
    features, labels, folds, baseline = corpus()
    policy = challenger_policy()
    first = run_regime_analog_oos_challenger(
        features=features,
        labels=labels,
        folds=folds,
        baseline_run=baseline,
        event_key="return_gt_0",
        challenger_policy=policy,
    )

    future_index = 100
    future_actual = actual_for(future_index)
    future_feature = feature(future_index, future_actual)
    future_label = label(future_feature, future_actual)
    second = run_regime_analog_oos_challenger(
        features=(*features, future_feature),
        labels=(*labels, future_label),
        folds=folds,
        baseline_run=baseline,
        event_key="return_gt_0",
        challenger_policy=policy,
    )
    assert first == second


def test_missing_required_signal_suppresses_without_peeking_at_outcome() -> None:
    features, labels, folds, baseline = corpus(
        last_missing_relative=True,
    )
    result = run_regime_analog_oos_challenger(
        features=features,
        labels=labels,
        folds=folds,
        baseline_run=baseline,
        event_key="return_gt_0",
        challenger_policy=challenger_policy(
            max_suppressed_fraction=0.90,
        ),
    )
    missing_feature_id = features[-1].feature_row_id
    suppression = next(
        item for item in result.suppressions if item.feature_row_id == missing_feature_id
    )
    assert suppression.reasons
    assert any(
        reason.startswith("QUERY_REGIME_NO_DATA") or reason.startswith("MISSING_REQUIRED_SIGNALS")
        for reason in suppression.reasons
    )
    assert all(item.feature_row_id != missing_feature_id for item in result.predictions)


def test_performance_gate_can_return_no_demonstrated_regime_skill() -> None:
    features, labels, folds, baseline = corpus()
    result = run_regime_analog_oos_challenger(
        features=features,
        labels=labels,
        folds=folds,
        baseline_run=baseline,
        event_key="return_gt_0",
        challenger_policy=challenger_policy(
            min_brier_improvement=0.90,
        ),
    )
    assert result.state is RegimeAnalogSkillState.NO_DEMONSTRATED_REGIME_SKILL
    assert "NO_BRIER_IMPROVEMENT_OVER_H6" in result.reasons


def test_insufficient_history_yields_insufficient_evidence() -> None:
    features, labels, folds, baseline = corpus()
    result = run_regime_analog_oos_challenger(
        features=features,
        labels=labels,
        folds=folds,
        baseline_run=baseline,
        event_key="return_gt_0",
        challenger_policy=challenger_policy(
            analog_config=AnalogSearchConfig(
                k=20,
                min_history=100,
                same_regime_only=True,
            ),
        ),
    )
    assert result.state is RegimeAnalogSkillState.INSUFFICIENT_EVIDENCE
    assert result.predictions == ()
    assert result.analog_evidence is None
    assert "NO_READY_ANALOG_PREDICTIONS" in result.reasons
    assert result.suppressions


def test_sample_gate_can_return_insufficient_evidence_after_predictions() -> None:
    features, labels, folds, baseline = corpus()
    result = run_regime_analog_oos_challenger(
        features=features,
        labels=labels,
        folds=folds,
        baseline_run=baseline,
        event_key="return_gt_0",
        challenger_policy=challenger_policy(
            min_oos_predictions=10_000,
        ),
    )
    assert result.predictions
    assert result.state is RegimeAnalogSkillState.INSUFFICIENT_EVIDENCE
    assert "INSUFFICIENT_OOS_SAMPLE" in result.reasons


def test_baseline_identity_and_temporal_guards_fail_closed() -> None:
    features, labels, folds, baseline = corpus()
    with pytest.raises(ValueError, match="event_key mismatch"):
        run_regime_analog_oos_challenger(
            features=features,
            labels=labels,
            folds=folds,
            baseline_run=baseline,
            event_key="touch_price:2",
            challenger_policy=challenger_policy(),
        )

    with pytest.raises(ValueError, match="fold identity mismatch"):
        run_regime_analog_oos_challenger(
            features=features,
            labels=labels,
            folds=folds[:-1],
            baseline_run=baseline,
            event_key="return_gt_0",
            challenger_policy=challenger_policy(),
        )

    first_train_id = folds[0].train_feature_row_ids[0]
    index = next(i for i, item in enumerate(labels) if item.feature_row_id == first_train_id)
    corrupted = list(labels)
    corrupted[index] = replace(
        corrupted[index],
        resolved_at=folds[0].cutoff_at + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="unresolved at fold cutoff"):
        run_regime_analog_oos_challenger(
            features=features,
            labels=tuple(corrupted),
            folds=folds,
            baseline_run=baseline,
            event_key="return_gt_0",
            challenger_policy=challenger_policy(),
        )


def test_challenger_policy_validation() -> None:
    with pytest.raises(ValueError, match="prior_strength"):
        challenger_policy(prior_strength=-1)
    with pytest.raises(ValueError, match="min_ready"):
        challenger_policy(min_ready_sensitivity_scenarios=0)
    with pytest.raises(ValueError, match="max_suppressed_fraction"):
        challenger_policy(max_suppressed_fraction=2)
    with pytest.raises(ValueError, match="sample thresholds"):
        challenger_policy(min_oos_predictions=0)
    with pytest.raises(ValueError, match="tolerances"):
        challenger_policy(min_brier_improvement=-1)
    with pytest.raises(ValueError, match="sensitivity_metrics"):
        challenger_policy(sensitivity_metrics=())
    with pytest.raises(ValueError, match="scenario axes"):
        challenger_policy(ablation_sets=())


def test_baseline_run_defensive_guards() -> None:
    features, labels, folds, baseline = corpus()

    with pytest.raises(ValueError, match="preserve final holdout"):
        run_regime_analog_oos_challenger(
            features=features,
            labels=labels,
            folds=folds,
            baseline_run=replace(baseline, final_holdout_untouched=False),
            event_key="return_gt_0",
            challenger_policy=challenger_policy(),
        )
    with pytest.raises(ValueError, match="non-authoritative"):
        run_regime_analog_oos_challenger(
            features=features,
            labels=labels,
            folds=folds,
            baseline_run=replace(baseline, production_ready=True),
            event_key="return_gt_0",
            challenger_policy=challenger_policy(),
        )
    with pytest.raises(ValueError, match="DatasetVersion"):
        run_regime_analog_oos_challenger(
            features=features,
            labels=labels,
            folds=folds,
            baseline_run=replace(baseline, dataset_version_id="bad"),
            event_key="return_gt_0",
            challenger_policy=challenger_policy(),
        )
    with pytest.raises(ValueError, match="folds cannot be empty"):
        run_regime_analog_oos_challenger(
            features=features,
            labels=labels,
            folds=(),
            baseline_run=replace(baseline, fold_ids=()),
            event_key="return_gt_0",
            challenger_policy=challenger_policy(),
        )
    with pytest.raises(ValueError, match="horizon mismatch"):
        run_regime_analog_oos_challenger(
            features=features,
            labels=labels,
            folds=folds,
            baseline_run=replace(baseline, horizon=ResearchHorizon.H4),
            event_key="return_gt_0",
            challenger_policy=challenger_policy(),
        )


def test_fold_row_defensive_guards() -> None:
    features, labels, rows, folds = (
        *corpus()[:2],
        join_labeled_rows(*corpus()[:2]),
        corpus()[2],
    )
    del features, labels
    row_map = {item.feature.feature_row_id: item for item in rows}
    fold = folds[0]

    unknown = replace(
        fold,
        train_feature_row_ids=("feature:sha256:" + "f" * 64,),
    )
    with pytest.raises(ValueError, match="unknown feature_row_id"):
        _fold_rows(unknown, row_map)

    empty = replace(fold, train_feature_row_ids=())
    with pytest.raises(ValueError, match="non-empty"):
        _fold_rows(empty, row_map)

    target_id = fold.test_feature_row_ids[0]
    original = row_map[target_id]
    h4_feature = replace(original.feature, horizon=ResearchHorizon.H4)
    h4_label = replace(original.label, horizon=ResearchHorizon.H4)
    contaminated = dict(row_map)
    contaminated[target_id] = LabeledFeatureRow(
        feature=h4_feature,
        label=h4_label,
    )
    with pytest.raises(ValueError, match="horizon mismatch"):
        _fold_rows(fold, contaminated)


def test_weighted_probability_defensive_guards() -> None:
    features, labels, rows, _ = (
        *corpus(30)[:2],
        join_labeled_rows(*corpus(30)[:2]),
        corpus(30)[2],
    )
    del features, labels
    row = rows[0]
    state = classify_regime(row.feature)
    state_map = {state.state_id: row}

    zero_similarity = HistoricalAnalogMatch(
        state_id=state.state_id,
        prediction_time=state.prediction_time,
        regime=state.regime,
        distance=1.0,
        similarity=0.0,
        provider_universe_version=state.provider_universe_version,
    )
    with pytest.raises(ValueError, match="similarity"):
        _weighted_probability(
            (zero_similarity,),
            state_map,
            event_key="return_gt_0",
            prior_rate=0.5,
            prior_strength=1.0,
        )

    unknown = replace(
        zero_similarity,
        state_id="regime-state:sha256:" + "f" * 64,
        similarity=0.5,
    )
    with pytest.raises(ValueError, match="outside training lineage"):
        _weighted_probability(
            (unknown,),
            state_map,
            event_key="return_gt_0",
            prior_rate=0.5,
            prior_strength=1.0,
        )

    with pytest.raises(ValueError, match="denominator"):
        _weighted_probability(
            (),
            {},
            event_key="return_gt_0",
            prior_rate=0.5,
            prior_strength=0.0,
        )


def test_baseline_subset_skips_missing_model_predictions() -> None:
    _, _, _, baseline = corpus()
    b0_predictions = tuple(
        item for item in baseline.predictions if item.model_id == "baseline:B0_BASE_RATE"
    )
    b0_ids = {item.prediction_id for item in b0_predictions}
    b0_outcomes = tuple(item for item in baseline.outcomes if item.prediction_id in b0_ids)
    truncated = replace(
        baseline,
        predictions=b0_predictions,
        outcomes=b0_outcomes,
    )
    feature_ids = {item.feature_row_id for item in b0_predictions}
    evidence = _baseline_evidence_on_subset(truncated, feature_ids)
    assert BaselineKind.B0_BASE_RATE in evidence
    assert len(evidence) == 1


def test_training_state_identity_collision_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xrp_regime_engine.regime_analog_challenger_v1 as module

    features, labels, folds, baseline = corpus()
    fixed = classify_regime(features[0])
    monkeypatch.setattr(
        module,
        "classify_regime",
        lambda feature, policy: fixed,
    )
    with pytest.raises(ValueError, match="identity collision"):
        run_regime_analog_oos_challenger(
            features=features,
            labels=labels,
            folds=folds,
            baseline_run=baseline,
            event_key="return_gt_0",
            challenger_policy=challenger_policy(
                require_stable_sensitivity=False,
            ),
        )


def test_unstable_sensitivity_suppresses_predictions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xrp_regime_engine.regime_analog_challenger_v1 as module

    features, labels, folds, baseline = corpus()

    class Unstable:
        report_id = "analog-sensitivity:sha256:" + "c" * 64
        stable = False
        reasons = ("ANALOG_TOP_K_UNSTABLE",)

    monkeypatch.setattr(
        module,
        "run_analog_sensitivity",
        lambda *args, **kwargs: Unstable(),
    )
    result = run_regime_analog_oos_challenger(
        features=features,
        labels=labels,
        folds=folds,
        baseline_run=baseline,
        event_key="return_gt_0",
        challenger_policy=challenger_policy(),
    )
    assert result.state is RegimeAnalogSkillState.INSUFFICIENT_EVIDENCE
    assert result.predictions == ()
    assert any("ANALOG_TOP_K_UNSTABLE" in item.reasons for item in result.suppressions)


def test_missing_h6_comparator_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xrp_regime_engine.regime_analog_challenger_v1 as module

    features, labels, folds, baseline = corpus()
    monkeypatch.setattr(
        module,
        "_baseline_evidence_on_subset",
        lambda baseline_run, feature_ids: {},
    )
    with pytest.raises(ValueError, match="no eligible H6 baseline comparator"):
        run_regime_analog_oos_challenger(
            features=features,
            labels=labels,
            folds=folds,
            baseline_run=baseline,
            event_key="return_gt_0",
            challenger_policy=challenger_policy(),
        )


def test_class_and_suppression_gates_are_explicit() -> None:
    features, labels, folds, baseline = corpus(
        last_missing_relative=True,
    )
    result = run_regime_analog_oos_challenger(
        features=features,
        labels=labels,
        folds=folds,
        baseline_run=baseline,
        event_key="return_gt_0",
        challenger_policy=challenger_policy(
            min_class_count=10_000,
            max_suppressed_fraction=0.0,
        ),
    )
    assert result.state is RegimeAnalogSkillState.INSUFFICIENT_EVIDENCE
    assert "INSUFFICIENT_POSITIVE_CLASS" in result.reasons
    assert "INSUFFICIENT_NEGATIVE_CLASS" in result.reasons
    assert "EXCESSIVE_ANALOG_SUPPRESSION" in result.reasons


def test_log_loss_regression_gate_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xrp_regime_engine.regime_analog_challenger_v1 as module

    features, labels, folds, baseline = corpus()
    first = run_regime_analog_oos_challenger(
        features=features,
        labels=labels,
        folds=folds,
        baseline_run=baseline,
        event_key="return_gt_0",
        challenger_policy=challenger_policy(),
    )
    assert first.comparator_evidence is not None
    fabricated = replace(
        first.comparator_evidence,
        brier_score=1.0,
        log_loss=0.0,
    )
    monkeypatch.setattr(
        module,
        "_baseline_evidence_on_subset",
        lambda baseline_run, feature_ids: {BaselineKind.B0_BASE_RATE: fabricated},
    )
    second = run_regime_analog_oos_challenger(
        features=features,
        labels=labels,
        folds=folds,
        baseline_run=baseline,
        event_key="return_gt_0",
        challenger_policy=challenger_policy(),
    )
    assert second.state is RegimeAnalogSkillState.NO_DEMONSTRATED_REGIME_SKILL
    assert "LOG_LOSS_REGRESSION_VS_H6" in second.reasons
