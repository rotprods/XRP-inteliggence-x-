from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.baseline_model_registry_v1 import (
    build_baseline_model_registry,
)
from xrp_regime_engine.baseline_models_v1 import BaselineKind
from xrp_regime_engine.baseline_oos_factory_v1 import BaselineSkillPolicy
from xrp_regime_engine.baseline_research_matrix_v1 import (
    HorizonResearchBundle,
    build_baseline_research_matrix,
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
    WalkForwardConfig,
    build_walk_forward_folds,
    join_labeled_rows,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
DATASET = "dataset-version:sha256:" + "e" * 64


def matrix():
    actuals = tuple(index % 2 == 0 for index in range(10))
    features = []
    labels = []
    for index, actual in enumerate(actuals):
        prediction = T0 + timedelta(days=index)
        snapshot = sha256(f"registry:{index}".encode()).hexdigest()
        item = HistoricalFeatureRow.build(
            feature_time=prediction,
            prediction_time=prediction,
            horizon=ResearchHorizon.H1,
            feature_schema_version="features-v1",
            provider_universe_version="providers-v1",
            eligibility_class=EligibilityClass.STRICT_REPLAY,
            source_snapshot_ids=(f"snapshot:sha256:{snapshot}",),
            feature_families={
                "market": {
                    "signal": 2.0 if actual else -2.0,
                }
            },
        )
        end = horizon_end_at(prediction, ResearchHorizon.H1)
        labels.append(
            build_future_outcome_label(
                feature_row_id=item.feature_row_id,
                prediction_time=prediction,
                horizon=ResearchHorizon.H1,
                start_price=1.0,
                price_path=(PricePoint(end, 2.1 if actual else 0.9),),
                resolved_at=end,
                barrier_set=canonical_xrp_barrier_set(),
            )
        )
        features.append(item)
    rows = join_labeled_rows(tuple(features), tuple(labels))
    folds = build_walk_forward_folds(
        rows,
        config=WalkForwardConfig(min_train_size=4),
    )
    bundle = HorizonResearchBundle(
        dataset_version_id=DATASET,
        features=tuple(features),
        labels=tuple(labels),
        folds=folds,
    )
    return build_baseline_research_matrix(
        {ResearchHorizon.H1: bundle},
        required_horizons=(ResearchHorizon.H1,),
        event_keys=("return_gt_0",),
        feature_keys=("market.signal",),
        momentum_feature_key="market.signal",
        model_kinds=(
            BaselineKind.B0_BASE_RATE,
            BaselineKind.B2_MOMENTUM,
            BaselineKind.B3_MEAN_REVERSION,
        ),
        skill_policy=BaselineSkillPolicy(
            min_oos_predictions=4,
            min_class_count=1,
        ),
    )


def test_registry_is_deterministic_and_queryable() -> None:
    source = matrix()
    first = build_baseline_model_registry(source)
    second = build_baseline_model_registry(source)
    assert first == second
    assert first.reference_entry_count == 1
    assert len(first.entries) == 3
    assert first.final_holdout_untouched
    assert not first.production_ready
    assert not first.decision_authority
    assert first.execution_weight == 0
    h1 = first.entries_for(ResearchHorizon.H1, "return_gt_0")
    assert len(h1) == 3
    assert {item.kind for item in h1} == {
        BaselineKind.B0_BASE_RATE,
        BaselineKind.B2_MOMENTUM,
        BaselineKind.B3_MEAN_REVERSION,
    }


def test_registry_rejects_authority_and_duplicate_runs() -> None:
    source = matrix()
    with pytest.raises(ValueError, match="non-authoritative"):
        build_baseline_model_registry(replace(source, probability_calibrated=True))

    duplicate = replace(
        source,
        runs=(source.runs[0], source.runs[0]),
    )
    with pytest.raises(ValueError, match="duplicate run_id"):
        build_baseline_model_registry(duplicate)


def test_registry_rejects_authoritative_run_and_unknown_cell_run() -> None:
    source = matrix()
    bad_run = replace(source.runs[0], production_ready=True)
    with pytest.raises(ValueError, match="non-authoritative"):
        build_baseline_model_registry(replace(source, runs=(bad_run,)))

    bad_cell = replace(
        source.cells[0],
        run_id="baseline-oos-run:sha256:" + "f" * 64,
    )
    with pytest.raises(ValueError, match="unknown baseline run"):
        build_baseline_model_registry(replace(source, cells=(bad_cell,)))


def test_registry_rejects_challenger_without_eligible_skill() -> None:
    source = matrix()
    cell = source.cells[0]
    rejected_kind = BaselineKind.B3_MEAN_REVERSION
    bad_cell = replace(
        cell,
        development_challenger=rejected_kind,
    )
    with pytest.raises(ValueError, match="not eligible"):
        build_baseline_model_registry(replace(source, cells=(bad_cell,)))
