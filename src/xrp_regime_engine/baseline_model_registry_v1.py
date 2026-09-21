from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from xrp_regime_engine.baseline_models_v1 import BaselineKind
from xrp_regime_engine.baseline_oos_factory_v1 import (
    BaselineOOSRun,
    BaselineSkillState,
)
from xrp_regime_engine.baseline_research_matrix_v1 import BaselineResearchMatrix
from xrp_regime_engine.research_horizon import ResearchHorizon


@dataclass(frozen=True, slots=True)
class BaselineRegistryEntry:
    horizon: ResearchHorizon
    event_key: str
    kind: BaselineKind
    dataset_version_id: str
    run_id: str
    evidence_id: str
    sample_count: int
    brier_score: float
    log_loss: float
    state: BaselineSkillState


@dataclass(frozen=True, slots=True)
class BaselineModelRegistry:
    registry_id: str
    registry_sha256: str
    matrix_id: str
    entries: tuple[BaselineRegistryEntry, ...]
    development_challenger_keys: tuple[str, ...]
    reference_entry_count: int
    eligible_challenger_count: int
    rejected_entry_count: int
    final_holdout_untouched: bool = True
    production_ready: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0

    def entries_for(
        self,
        horizon: ResearchHorizon,
        event_key: str,
    ) -> tuple[BaselineRegistryEntry, ...]:
        return tuple(
            item
            for item in self.entries
            if item.horizon is horizon and item.event_key == event_key
        )


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _entry_key(
    horizon: ResearchHorizon,
    event_key: str,
    kind: BaselineKind,
) -> str:
    return f"{horizon.value}|{event_key}|{kind.value}"


def _validate_run(run: BaselineOOSRun) -> None:
    if not run.final_holdout_untouched:
        raise ValueError("baseline run must preserve final holdout")
    if run.probability_calibrated or run.production_ready or run.decision_authority:
        raise ValueError("baseline run must remain non-authoritative")
    if run.execution_weight != 0.0:
        raise ValueError("baseline run execution_weight must remain zero")
    if not run.dataset_version_id.startswith("dataset-version:sha256:"):
        raise ValueError("baseline run lacks DatasetVersion identity")


def build_baseline_model_registry(
    matrix: BaselineResearchMatrix,
) -> BaselineModelRegistry:
    if not matrix.final_holdout_untouched:
        raise ValueError("baseline matrix must preserve final holdout")
    if matrix.probability_calibrated or matrix.production_ready or matrix.decision_authority:
        raise ValueError("baseline matrix must remain non-authoritative")
    if matrix.execution_weight != 0.0:
        raise ValueError("baseline matrix execution_weight must remain zero")

    run_by_id = {item.run_id: item for item in matrix.runs}
    if len(run_by_id) != len(matrix.runs):
        raise ValueError("baseline matrix contains duplicate run_id")

    entries: list[BaselineRegistryEntry] = []
    challenger_keys: list[str] = []
    seen: set[str] = set()
    for run in matrix.runs:
        _validate_run(run)
        for skill in run.skills:
            key = _entry_key(run.horizon, run.event_key, skill.kind)
            if key in seen:
                raise ValueError("duplicate registry entry")
            seen.add(key)
            entries.append(
                BaselineRegistryEntry(
                    horizon=run.horizon,
                    event_key=run.event_key,
                    kind=skill.kind,
                    dataset_version_id=run.dataset_version_id,
                    run_id=run.run_id,
                    evidence_id=skill.evidence_id,
                    sample_count=skill.sample_count,
                    brier_score=skill.brier_score,
                    log_loss=skill.log_loss,
                    state=skill.state,
                )
            )
            if skill.state is BaselineSkillState.ELIGIBLE_CHALLENGER:
                challenger_keys.append(key)

    for cell in matrix.cells:
        if cell.run_id is not None and cell.run_id not in run_by_id:
            raise ValueError("matrix cell references unknown baseline run")
        if cell.development_challenger is not None:
            expected = _entry_key(
                cell.horizon,
                cell.event_key,
                cell.development_challenger,
            )
            if expected not in challenger_keys:
                raise ValueError("matrix challenger is not eligible in registry evidence")

    ordered_entries = tuple(
        sorted(
            entries,
            key=lambda item: (
                item.horizon.value,
                item.event_key,
                item.kind.value,
            ),
        )
    )
    ordered_challengers = tuple(sorted(challenger_keys))
    reference_count = sum(
        1
        for item in ordered_entries
        if item.state is BaselineSkillState.REFERENCE_BASELINE
    )
    eligible_count = sum(
        1
        for item in ordered_entries
        if item.state is BaselineSkillState.ELIGIBLE_CHALLENGER
    )
    rejected_count = sum(
        1
        for item in ordered_entries
        if item.state is BaselineSkillState.REJECTED
    )
    material = {
        "matrix_id": matrix.matrix_id,
        "entries": [
            {
                "horizon": item.horizon.value,
                "event_key": item.event_key,
                "kind": item.kind.value,
                "dataset_version_id": item.dataset_version_id,
                "run_id": item.run_id,
                "evidence_id": item.evidence_id,
                "sample_count": item.sample_count,
                "brier_score": item.brier_score,
                "log_loss": item.log_loss,
                "state": item.state.value,
            }
            for item in ordered_entries
        ],
        "development_challenger_keys": list(ordered_challengers),
        "final_holdout_untouched": True,
        "production_ready": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return BaselineModelRegistry(
        registry_id=f"baseline-model-registry:sha256:{digest}",
        registry_sha256=digest,
        matrix_id=matrix.matrix_id,
        entries=ordered_entries,
        development_challenger_keys=ordered_challengers,
        reference_entry_count=reference_count,
        eligible_challenger_count=eligible_count,
        rejected_entry_count=rejected_count,
    )
