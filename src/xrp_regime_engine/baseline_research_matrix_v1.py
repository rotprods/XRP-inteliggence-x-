from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from xrp_regime_engine.baseline_models_v1 import BaselineKind, BaselineTrainingPolicy
from xrp_regime_engine.baseline_oos_factory_v1 import (
    BaselineOOSRun,
    BaselineSkillPolicy,
    run_baseline_oos_factory,
)
from xrp_regime_engine.future_labels_v1 import FutureOutcomeLabel
from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow
from xrp_regime_engine.research_horizon import ResearchHorizon
from xrp_regime_engine.walk_forward_v1 import WalkForwardFoldPlan

CANONICAL_RESEARCH_HORIZONS = (
    ResearchHorizon.H1,
    ResearchHorizon.H4,
    ResearchHorizon.D1,
    ResearchHorizon.W1,
    ResearchHorizon.M1,
    ResearchHorizon.M3,
    ResearchHorizon.Y1,
)
CANONICAL_RETURN_THRESHOLDS = (0.01, 0.02, 0.05, 0.10)
CANONICAL_XRP_BARRIERS = (2.0, 3.0, 3.65, 5.0, 7.34, 10.0, 17.0, 26.6, 50.0)


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _number_key(value: float) -> str:
    return format(value, ".12g")


def canonical_binary_event_keys() -> tuple[str, ...]:
    events = ["return_gt_0"]
    for threshold in CANONICAL_RETURN_THRESHOLDS:
        key = _number_key(threshold)
        events.extend((f"touch_return_up:{key}", f"touch_return_down:{key}"))
    events.extend(f"touch_price:{_number_key(barrier)}" for barrier in CANONICAL_XRP_BARRIERS)
    return tuple(events)


@dataclass(frozen=True, slots=True)
class HorizonResearchBundle:
    dataset_version_id: str
    features: tuple[HistoricalFeatureRow, ...]
    labels: tuple[FutureOutcomeLabel, ...]
    folds: tuple[WalkForwardFoldPlan, ...]


class MatrixCellState(StrEnum):
    CHALLENGER_FOUND = "CHALLENGER_FOUND"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    MISSING_HORIZON_DATA = "MISSING_HORIZON_DATA"


@dataclass(frozen=True, slots=True)
class BaselineResearchCell:
    horizon: ResearchHorizon
    event_key: str
    state: MatrixCellState
    run_id: str | None
    development_challenger: BaselineKind | None
    dataset_version_id: str | None
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BaselineResearchMatrix:
    matrix_id: str
    matrix_sha256: str
    required_horizons: tuple[ResearchHorizon, ...]
    event_keys: tuple[str, ...]
    cells: tuple[BaselineResearchCell, ...]
    runs: tuple[BaselineOOSRun, ...]
    complete: bool
    challenger_cell_count: int
    reference_only_cell_count: int
    missing_cell_count: int
    final_holdout_untouched: bool = True
    probability_calibrated: bool = False
    production_ready: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0


def build_baseline_research_matrix(
    bundles: Mapping[ResearchHorizon, HorizonResearchBundle],
    *,
    feature_keys: Sequence[str],
    momentum_feature_key: str,
    required_horizons: Sequence[ResearchHorizon] = CANONICAL_RESEARCH_HORIZONS,
    event_keys: Sequence[str] | None = None,
    model_kinds: Sequence[BaselineKind] = tuple(BaselineKind),
    training_policy: BaselineTrainingPolicy | None = None,
    skill_policy: BaselineSkillPolicy | None = None,
) -> BaselineResearchMatrix:
    horizons = tuple(dict.fromkeys(required_horizons))
    if not horizons:
        raise ValueError("required_horizons cannot be empty")
    events = tuple(dict.fromkeys(event_keys or canonical_binary_event_keys()))
    if not events or any(not item.strip() for item in events):
        raise ValueError("event_keys must be non-empty strings")
    unsupported = set(bundles) - set(horizons)
    if unsupported:
        raise ValueError("bundle map contains horizon outside required_horizons")

    cells: list[BaselineResearchCell] = []
    runs: list[BaselineOOSRun] = []
    for horizon in horizons:
        bundle = bundles.get(horizon)
        if bundle is None:
            for event_key in events:
                cells.append(
                    BaselineResearchCell(
                        horizon=horizon,
                        event_key=event_key,
                        state=MatrixCellState.MISSING_HORIZON_DATA,
                        run_id=None,
                        development_challenger=None,
                        dataset_version_id=None,
                        reasons=("MISSING_HORIZON_DATA",),
                    )
                )
            continue
        if not bundle.features or not bundle.labels or not bundle.folds:
            raise ValueError("present horizon bundle must contain features, labels and folds")
        if any(item.horizon is not horizon for item in bundle.features):
            raise ValueError("feature horizon does not match bundle horizon")
        if any(item.horizon is not horizon for item in bundle.labels):
            raise ValueError("label horizon does not match bundle horizon")
        if any(item.horizon is not horizon for item in bundle.folds):
            raise ValueError("fold horizon does not match bundle horizon")
        for event_key in events:
            run = run_baseline_oos_factory(
                dataset_version_id=bundle.dataset_version_id,
                features=bundle.features,
                labels=bundle.labels,
                folds=bundle.folds,
                event_key=event_key,
                feature_keys=feature_keys,
                momentum_feature_key=momentum_feature_key,
                model_kinds=model_kinds,
                training_policy=training_policy,
                skill_policy=skill_policy,
            )
            runs.append(run)
            state = (
                MatrixCellState.CHALLENGER_FOUND
                if run.development_challenger is not None
                else MatrixCellState.REFERENCE_ONLY
            )
            cells.append(
                BaselineResearchCell(
                    horizon=horizon,
                    event_key=event_key,
                    state=state,
                    run_id=run.run_id,
                    development_challenger=run.development_challenger,
                    dataset_version_id=bundle.dataset_version_id,
                    reasons=()
                    if state is MatrixCellState.CHALLENGER_FOUND
                    else ("NO_SKILLED_CHALLENGER",),
                )
            )

    challenger_count = sum(1 for item in cells if item.state is MatrixCellState.CHALLENGER_FOUND)
    reference_count = sum(1 for item in cells if item.state is MatrixCellState.REFERENCE_ONLY)
    missing_count = sum(1 for item in cells if item.state is MatrixCellState.MISSING_HORIZON_DATA)
    complete = missing_count == 0
    material = {
        "required_horizons": [item.value for item in horizons],
        "event_keys": list(events),
        "cells": [
            {
                "horizon": item.horizon.value,
                "event_key": item.event_key,
                "state": item.state.value,
                "run_id": item.run_id,
                "development_challenger": (
                    item.development_challenger.value
                    if item.development_challenger is not None
                    else None
                ),
                "dataset_version_id": item.dataset_version_id,
                "reasons": list(item.reasons),
            }
            for item in cells
        ],
        "run_ids": [item.run_id for item in runs],
        "complete": complete,
        "final_holdout_untouched": True,
        "probability_calibrated": False,
        "production_ready": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return BaselineResearchMatrix(
        matrix_id=f"baseline-research-matrix:sha256:{digest}",
        matrix_sha256=digest,
        required_horizons=horizons,
        event_keys=events,
        cells=tuple(cells),
        runs=tuple(runs),
        complete=complete,
        challenger_cell_count=challenger_count,
        reference_only_cell_count=reference_count,
        missing_cell_count=missing_count,
    )
