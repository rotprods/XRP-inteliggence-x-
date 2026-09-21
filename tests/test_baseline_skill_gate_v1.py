from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.baseline_models_v1 import (
    BaselineKind,
    BaselineTrainingPolicy,
    binary_event_actual,
    fit_baseline_model,
    flatten_numeric_features,
)
from xrp_regime_engine.baseline_oos_factory_v1 import (
    BaselineSkillPolicy,
    BaselineSkillState,
    run_baseline_oos_factory,
)
from xrp_regime_engine.future_labels_v1 import (
    PricePoint,
    build_future_outcome_label,
    canonical_xrp_barrier_set,
)
from xrp_regime_engine.historical_contract import EligibilityClass
from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow
from xrp_regime_engine.research_horizon import ResearchHorizon, horizon_end_at
from xrp_regime_engine.walk_forward_v1 import (
    LabeledFeatureRow,
    WalkForwardConfig,
    build_walk_forward_folds,
    join_labeled_rows,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
DATASET = "dataset-version:sha256:" + "d" * 64


def feature(index: int, actual: bool) -> HistoricalFeatureRow:
    prediction = T0 + timedelta(days=index)
    snapshot = sha256(f"snapshot-{index}".encode()).hexdigest()
    signal = 2.0 if actual else -2.0
    return HistoricalFeatureRow.build(
        feature_time=prediction,
        prediction_time=prediction,
        horizon=ResearchHorizon.H1,
        feature_schema_version="features-v1",
        provider_universe_version="providers-v1",
        eligibility_class=EligibilityClass.STRICT_REPLAY,
        source_snapshot_ids=(f"snapshot:sha256:{snapshot}",),
        feature_families={
            "market": {
                "signal": signal,
                "noise": float((index % 3) - 1),
            }
        },
    )


def label(item: HistoricalFeatureRow, actual: bool):
    end = horizon_end_at(item.prediction_time, item.horizon)
    end_price = 2.1 if actual else 0.9
    return build_future_outcome_label(
        feature_row_id=item.feature_row_id,
        prediction_time=item.prediction_time,
        horizon=item.horizon,
        start_price=1.0,
        price_path=(PricePoint(at=end, price=end_price),),
        resolved_at=end,
        barrier_set=canonical_xrp_barrier_set(),
    )


def dataset(size: int = 14):
    actuals = tuple(index % 2 == 0 for index in range(size))
    features = tuple(feature(index, actual) for index, actual in enumerate(actuals))
    labels = tuple(label(item, actual) for item, actual in zip(features, actuals, strict=True))
    rows = join_labeled_rows(features, labels)
    folds = build_walk_forward_folds(
        rows,
        config=WalkForwardConfig(min_train_size=4),
    )
    return features, labels, rows, folds


def test_flatten_and_event_resolution() -> None:
    features, labels, rows, _ = dataset(6)
    flat = flatten_numeric_features(features[0])
    assert flat["market.signal"] == 2.0
    assert binary_event_actual("return_gt_0", rows[0]) is True
    assert binary_event_actual("touch_price:2", rows[0]) is True
    assert binary_event_actual("touch_price:50", rows[0]) is False
    with pytest.raises(ValueError, match="unsupported"):
        binary_event_actual("unknown", rows[0])
    with pytest.raises(ValueError, match="does not contain"):
        binary_event_actual("touch_price:999", rows[0])
    assert labels[0].future_return > 0


def test_b0_b1_and_signal_baselines_are_deterministic() -> None:
    _, _, rows, _ = dataset(8)
    b0 = fit_baseline_model(
        BaselineKind.B0_BASE_RATE,
        rows[:6],
        event_key="return_gt_0",
        feature_keys=("market.signal",),
        momentum_feature_key="market.signal",
    )
    assert b0 == fit_baseline_model(
        BaselineKind.B0_BASE_RATE,
        rows[:6],
        event_key="return_gt_0",
        feature_keys=("market.signal",),
        momentum_feature_key="market.signal",
    )
    assert 0 < b0.predict(rows[6].feature) < 1

    persistence = fit_baseline_model(
        BaselineKind.B1_PERSISTENCE,
        rows[:6],
        event_key="return_gt_0",
        feature_keys=(),
        momentum_feature_key="market.signal",
    )
    assert 0 < persistence.predict(rows[6].feature) < 1

    momentum = fit_baseline_model(
        BaselineKind.B2_MOMENTUM,
        rows[:6],
        event_key="return_gt_0",
        feature_keys=(),
        momentum_feature_key="market.signal",
    )
    reversion = fit_baseline_model(
        BaselineKind.B3_MEAN_REVERSION,
        rows[:6],
        event_key="return_gt_0",
        feature_keys=(),
        momentum_feature_key="market.signal",
    )
    assert momentum.predict(rows[6].feature) > reversion.predict(rows[6].feature)


def test_logistic_fits_only_declared_train_features() -> None:
    _, _, rows, _ = dataset(10)
    model = fit_baseline_model(
        BaselineKind.B4_LOGISTIC_L2,
        rows[:8],
        event_key="return_gt_0",
        feature_keys=("market.signal", "market.noise"),
        momentum_feature_key="market.signal",
        policy=BaselineTrainingPolicy(
            logistic_l2=0.1,
            logistic_learning_rate=0.2,
            logistic_iterations=300,
        ),
    )
    positive_score = model.predict(rows[8].feature)
    negative_score = model.predict(rows[9].feature)
    assert 0 <= negative_score <= 1
    assert 0 <= positive_score <= 1
    assert positive_score > negative_score
    assert model.training_feature_row_ids == tuple(
        row.feature.feature_row_id for row in rows[:8]
    )


def test_training_guards_fail_closed() -> None:
    _, _, rows, _ = dataset(6)
    with pytest.raises(ValueError, match="cannot be empty"):
        fit_baseline_model(
            BaselineKind.B0_BASE_RATE,
            (),
            event_key="return_gt_0",
            feature_keys=(),
            momentum_feature_key="market.signal",
        )
    with pytest.raises(ValueError, match="at least one feature"):
        fit_baseline_model(
            BaselineKind.B4_LOGISTIC_L2,
            rows[:4],
            event_key="return_gt_0",
            feature_keys=(),
            momentum_feature_key="market.signal",
        )
    with pytest.raises(ValueError, match="required baseline feature"):
        fit_baseline_model(
            BaselineKind.B2_MOMENTUM,
            rows[:4],
            event_key="return_gt_0",
            feature_keys=(),
            momentum_feature_key="market.missing",
        )
    with pytest.raises(ValueError, match="family.name"):
        fit_baseline_model(
            BaselineKind.B2_MOMENTUM,
            rows[:4],
            event_key="return_gt_0",
            feature_keys=(),
            momentum_feature_key="bad",
        )
    with pytest.raises(ValueError, match="smoothing"):
        BaselineTrainingPolicy(smoothing=0)
    with pytest.raises(ValueError, match="logistic_l2"):
        BaselineTrainingPolicy(logistic_l2=-1)
    with pytest.raises(ValueError, match="learning_rate"):
        BaselineTrainingPolicy(logistic_learning_rate=2)
    with pytest.raises(ValueError, match="iterations"):
        BaselineTrainingPolicy(logistic_iterations=0)


def test_factory_executes_all_baselines_and_freezes_oos_records() -> None:
    features, labels, _, folds = dataset()
    result = run_baseline_oos_factory(
        dataset_version_id=DATASET,
        features=features,
        labels=labels,
        folds=folds,
        event_key="return_gt_0",
        feature_keys=("market.signal", "market.noise"),
        momentum_feature_key="market.signal",
        training_policy=BaselineTrainingPolicy(
            logistic_l2=0.1,
            logistic_learning_rate=0.2,
            logistic_iterations=300,
        ),
        skill_policy=BaselineSkillPolicy(
            min_oos_predictions=6,
            min_class_count=2,
            min_brier_improvement=0.0,
            max_log_loss_regression=0.0,
        ),
    )
    assert result.dataset_version_id == DATASET
    assert len(result.model_kinds) == 5
    assert len(result.predictions) == len(folds) * 5
    assert len(result.outcomes) == len(result.predictions)
    assert len({item.prediction_id for item in result.predictions}) == len(result.predictions)
    assert result.model_fit_ids
    assert all(
        item.model_version.startswith("baseline-fit:sha256:")
        for item in result.predictions
    )
    assert result.final_holdout_untouched is True
    assert result.probability_calibrated is False
    assert result.production_ready is False
    assert result.decision_authority is False
    assert result.execution_weight == 0

    skill = {item.kind: item for item in result.skills}
    assert skill[BaselineKind.B0_BASE_RATE].state is BaselineSkillState.REFERENCE_BASELINE
    assert skill[BaselineKind.B2_MOMENTUM].state is BaselineSkillState.ELIGIBLE_CHALLENGER
    assert skill[BaselineKind.B3_MEAN_REVERSION].state is BaselineSkillState.REJECTED
    assert skill[BaselineKind.B2_MOMENTUM].brier_score < skill[BaselineKind.B0_BASE_RATE].brier_score
    assert result.development_challenger in {
        BaselineKind.B1_PERSISTENCE,
        BaselineKind.B2_MOMENTUM,
        BaselineKind.B4_LOGISTIC_L2,
    }


def test_factory_supports_barrier_events() -> None:
    features, labels, _, folds = dataset()
    result = run_baseline_oos_factory(
        dataset_version_id=DATASET,
        features=features,
        labels=labels,
        folds=folds,
        event_key="touch_price:2",
        feature_keys=("market.signal",),
        momentum_feature_key="market.signal",
        model_kinds=(BaselineKind.B0_BASE_RATE, BaselineKind.B2_MOMENTUM),
        skill_policy=BaselineSkillPolicy(
            min_oos_predictions=4,
            min_class_count=1,
        ),
    )
    assert result.event_key == "touch_price:2"
    assert all(item.event_key == "touch_price:2" for item in result.predictions)


def test_factory_fail_closed_on_scope_and_fold_corruption() -> None:
    features, labels, _, folds = dataset(8)
    with pytest.raises(ValueError, match="event_key"):
        run_baseline_oos_factory(
            dataset_version_id=DATASET,
            features=features,
            labels=labels,
            folds=folds,
            event_key=" ",
            feature_keys=("market.signal",),
            momentum_feature_key="market.signal",
        )
    with pytest.raises(ValueError, match="B0_BASE_RATE"):
        run_baseline_oos_factory(
            dataset_version_id=DATASET,
            features=features,
            labels=labels,
            folds=folds,
            event_key="return_gt_0",
            feature_keys=("market.signal",),
            momentum_feature_key="market.signal",
            model_kinds=(BaselineKind.B2_MOMENTUM,),
        )
    with pytest.raises(ValueError, match="folds cannot be empty"):
        run_baseline_oos_factory(
            dataset_version_id=DATASET,
            features=features,
            labels=labels,
            folds=(),
            event_key="return_gt_0",
            feature_keys=("market.signal",),
            momentum_feature_key="market.signal",
        )
    broken = folds[0]
    unknown = replace(
        broken,
        train_feature_row_ids=("feature:sha256:" + "f" * 64,),
    )
    with pytest.raises(ValueError, match="unknown feature_row_id"):
        run_baseline_oos_factory(
            dataset_version_id=DATASET,
            features=features,
            labels=labels,
            folds=(unknown,),
            event_key="return_gt_0",
            feature_keys=("market.signal",),
            momentum_feature_key="market.signal",
        )


def test_skill_policy_validation() -> None:
    with pytest.raises(ValueError, match="positive"):
        BaselineSkillPolicy(min_oos_predictions=0)
    with pytest.raises(ValueError, match="negative"):
        BaselineSkillPolicy(min_brier_improvement=-1)



def test_factory_requires_content_addressed_dataset_version() -> None:
    features, labels, _, folds = dataset(8)
    with pytest.raises(ValueError, match="dataset_version_id"):
        run_baseline_oos_factory(
            dataset_version_id="bad",
            features=features,
            labels=labels,
            folds=folds,
            event_key="return_gt_0",
            feature_keys=("market.signal",),
            momentum_feature_key="market.signal",
        )
