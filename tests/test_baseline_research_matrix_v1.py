from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.baseline_models_v1 import BaselineKind
from xrp_regime_engine.baseline_oos_factory_v1 import BaselineSkillPolicy
from xrp_regime_engine.baseline_research_matrix_v1 import (
    CANONICAL_RESEARCH_HORIZONS,
    HorizonResearchBundle,
    MatrixCellState,
    build_baseline_research_matrix,
    canonical_binary_event_keys,
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
DATASET = "dataset-version:sha256:" + "a" * 64


def bundle(horizon: ResearchHorizon = ResearchHorizon.H1) -> HorizonResearchBundle:
    actuals = tuple(index % 2 == 0 for index in range(10))
    features = []
    labels = []
    for index, actual in enumerate(actuals):
        prediction = T0 + timedelta(days=index)
        snapshot = sha256(f"{horizon.value}:{index}".encode()).hexdigest()
        item = HistoricalFeatureRow.build(
            feature_time=prediction,
            prediction_time=prediction,
            horizon=horizon,
            feature_schema_version="features-v1",
            provider_universe_version="providers-v1",
            eligibility_class=EligibilityClass.STRICT_REPLAY,
            source_snapshot_ids=(f"snapshot:sha256:{snapshot}",),
            feature_families={
                "market": {
                    "signal": 2.0 if actual else -2.0,
                    "noise": float(index % 2),
                }
            },
        )
        end = horizon_end_at(prediction, horizon)
        outcome = build_future_outcome_label(
            feature_row_id=item.feature_row_id,
            prediction_time=prediction,
            horizon=horizon,
            start_price=1.0,
            price_path=(
                PricePoint(
                    at=end,
                    price=2.1 if actual else 0.9,
                ),
            ),
            resolved_at=end,
            barrier_set=canonical_xrp_barrier_set(),
        )
        features.append(item)
        labels.append(outcome)
    rows = join_labeled_rows(tuple(features), tuple(labels))
    folds = build_walk_forward_folds(
        rows,
        config=WalkForwardConfig(min_train_size=4),
    )
    return HorizonResearchBundle(
        dataset_version_id=DATASET,
        features=tuple(features),
        labels=tuple(labels),
        folds=folds,
    )


def test_canonical_event_surface_is_18_by_7() -> None:
    events = canonical_binary_event_keys()
    assert len(events) == 18
    assert len(set(events)) == 18
    assert events[0] == "return_gt_0"
    assert "touch_return_up:0.01" in events
    assert "touch_return_down:0.1" in events
    assert "touch_price:50" in events
    assert len(CANONICAL_RESEARCH_HORIZONS) == 7


def test_empty_bundle_map_yields_126_explicit_missing_cells() -> None:
    matrix = build_baseline_research_matrix(
        {},
        feature_keys=("market.signal",),
        momentum_feature_key="market.signal",
    )
    assert len(matrix.cells) == 7 * 18
    assert matrix.missing_cell_count == 126
    assert matrix.challenger_cell_count == 0
    assert matrix.reference_only_cell_count == 0
    assert matrix.complete is False
    assert not matrix.probability_calibrated
    assert not matrix.production_ready
    assert matrix.execution_weight == 0
    assert all(item.state is MatrixCellState.MISSING_HORIZON_DATA for item in matrix.cells)


def test_single_horizon_executes_real_oos_cell() -> None:
    matrix = build_baseline_research_matrix(
        {ResearchHorizon.H1: bundle()},
        required_horizons=(ResearchHorizon.H1,),
        event_keys=("return_gt_0",),
        feature_keys=("market.signal", "market.noise"),
        momentum_feature_key="market.signal",
        model_kinds=(BaselineKind.B0_BASE_RATE, BaselineKind.B2_MOMENTUM),
        skill_policy=BaselineSkillPolicy(
            min_oos_predictions=4,
            min_class_count=1,
        ),
    )
    assert matrix.complete is True
    assert len(matrix.cells) == 1
    assert len(matrix.runs) == 1
    cell = matrix.cells[0]
    assert cell.run_id == matrix.runs[0].run_id
    assert cell.dataset_version_id == DATASET
    assert cell.state in {
        MatrixCellState.CHALLENGER_FOUND,
        MatrixCellState.REFERENCE_ONLY,
    }
    assert matrix.runs[0].final_holdout_untouched is True


def test_matrix_rejects_horizon_contamination_and_scope_errors() -> None:
    h1 = bundle(ResearchHorizon.H1)
    with pytest.raises(ValueError, match="outside required_horizons"):
        build_baseline_research_matrix(
            {ResearchHorizon.H4: h1},
            required_horizons=(ResearchHorizon.H1,),
            event_keys=("return_gt_0",),
            feature_keys=("market.signal",),
            momentum_feature_key="market.signal",
        )
    with pytest.raises(ValueError, match="feature horizon"):
        build_baseline_research_matrix(
            {ResearchHorizon.H4: h1},
            required_horizons=(ResearchHorizon.H4,),
            event_keys=("return_gt_0",),
            feature_keys=("market.signal",),
            momentum_feature_key="market.signal",
        )
    with pytest.raises(ValueError, match="required_horizons"):
        build_baseline_research_matrix(
            {},
            required_horizons=(),
            feature_keys=("market.signal",),
            momentum_feature_key="market.signal",
        )
    with pytest.raises(ValueError, match="event_keys"):
        build_baseline_research_matrix(
            {},
            required_horizons=(ResearchHorizon.H1,),
            event_keys=(" ",),
            feature_keys=("market.signal",),
            momentum_feature_key="market.signal",
        )


def test_present_bundle_must_be_complete() -> None:
    item = bundle()
    empty = HorizonResearchBundle(
        dataset_version_id=item.dataset_version_id,
        features=(),
        labels=item.labels,
        folds=item.folds,
    )
    with pytest.raises(ValueError, match="features, labels and folds"):
        build_baseline_research_matrix(
            {ResearchHorizon.H1: empty},
            required_horizons=(ResearchHorizon.H1,),
            event_keys=("return_gt_0",),
            feature_keys=("market.signal",),
            momentum_feature_key="market.signal",
        )



def test_matrix_rejects_label_and_fold_horizon_contamination() -> None:
    item = bundle(ResearchHorizon.H1)

    wrong_labels = tuple(
        replace(label, horizon=ResearchHorizon.H4)
        for label in item.labels
    )
    with pytest.raises(ValueError, match="label horizon"):
        build_baseline_research_matrix(
            {
                ResearchHorizon.H1: replace(
                    item,
                    labels=wrong_labels,
                )
            },
            required_horizons=(ResearchHorizon.H1,),
            event_keys=("return_gt_0",),
            feature_keys=("market.signal",),
            momentum_feature_key="market.signal",
        )

    wrong_folds = tuple(
        replace(fold, horizon=ResearchHorizon.H4)
        for fold in item.folds
    )
    with pytest.raises(ValueError, match="fold horizon"):
        build_baseline_research_matrix(
            {
                ResearchHorizon.H1: replace(
                    item,
                    folds=wrong_folds,
                )
            },
            required_horizons=(ResearchHorizon.H1,),
            event_keys=("return_gt_0",),
            feature_keys=("market.signal",),
            momentum_feature_key="market.signal",
        )
