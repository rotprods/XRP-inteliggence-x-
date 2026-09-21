from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256

from xrp_regime_engine.regime_state_v1 import CanonicalRegime, RegimeState


class DistanceMetric(StrEnum):
    EUCLIDEAN = "EUCLIDEAN"
    MANHATTAN = "MANHATTAN"
    COSINE = "COSINE"


class AnalogSearchStatus(StrEnum):
    READY = "READY"
    NO_DATA = "NO_DATA"


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


@dataclass(frozen=True, slots=True)
class AnalogSearchConfig:
    k: int = 5
    min_history: int = 20
    metric: DistanceMetric = DistanceMetric.EUCLIDEAN
    same_regime_only: bool = False
    signal_keys: tuple[str, ...] = ()
    excluded_signals: tuple[str, ...] = ()
    max_lookback: timedelta | None = None
    provider_universe_versions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError("k must be positive")
        if self.min_history < self.k:
            raise ValueError("min_history must be >= k")
        if len(self.signal_keys) != len(set(self.signal_keys)):
            raise ValueError("signal_keys must be unique")
        if len(self.excluded_signals) != len(set(self.excluded_signals)):
            raise ValueError("excluded_signals must be unique")
        if set(self.signal_keys) & set(self.excluded_signals):
            raise ValueError("signal_keys and excluded_signals cannot overlap")
        if self.max_lookback is not None and self.max_lookback <= timedelta(0):
            raise ValueError("max_lookback must be positive")
        if len(self.provider_universe_versions) != len(set(self.provider_universe_versions)):
            raise ValueError("provider_universe_versions must be unique")


@dataclass(frozen=True, slots=True)
class HistoricalAnalogMatch:
    state_id: str
    prediction_time: datetime
    regime: CanonicalRegime
    distance: float
    similarity: float
    provider_universe_version: str


@dataclass(frozen=True, slots=True)
class HistoricalAnalogReport:
    report_id: str
    report_sha256: str
    query_state_id: str
    metric: DistanceMetric
    selected_signals: tuple[str, ...]
    normalizer_digest: str | None
    eligible_candidate_count: int
    status: AnalogSearchStatus
    reasons: tuple[str, ...]
    matches: tuple[HistoricalAnalogMatch, ...]
    decision_authority: bool = False
    execution_weight: float = 0.0


def _selected_signals(
    query: RegimeState,
    config: AnalogSearchConfig,
) -> tuple[str, ...]:
    available = set(query.signal_map())
    if config.signal_keys:
        selected = tuple(
            key for key in config.signal_keys if key not in set(config.excluded_signals)
        )
        missing = set(selected) - available
        if missing:
            raise ValueError(
                "query is missing requested analog signals: " + ",".join(sorted(missing))
            )
        return selected
    return tuple(sorted(available - set(config.excluded_signals)))


def _eligible_candidates(
    query: RegimeState,
    history: Sequence[RegimeState],
    config: AnalogSearchConfig,
    selected: Sequence[str],
) -> tuple[RegimeState, ...]:
    provider_filter = set(config.provider_universe_versions)
    earliest = (
        query.prediction_time - config.max_lookback if config.max_lookback is not None else None
    )
    candidates: list[RegimeState] = []
    seen: set[str] = set()
    for item in history:
        if item.state_id in seen:
            raise ValueError("historical regime state_id values must be unique")
        seen.add(item.state_id)
        if item.state_id == query.state_id:
            continue
        if item.horizon is not query.horizon:
            continue
        if item.prediction_time >= query.prediction_time:
            continue
        if earliest is not None and item.prediction_time < earliest:
            continue
        if config.same_regime_only and item.regime is not query.regime:
            continue
        if provider_filter and item.provider_universe_version not in provider_filter:
            continue
        item_signals = item.signal_map()
        if any(key not in item_signals for key in selected):
            continue
        candidates.append(item)
    return tuple(
        sorted(
            candidates,
            key=lambda item: (item.prediction_time, item.state_id),
        )
    )


def _normalizer(
    candidates: Sequence[RegimeState],
    selected: Sequence[str],
) -> tuple[dict[str, tuple[float, float]], str]:
    if not candidates or not selected:
        raise ValueError("normalizer requires candidates and signals")
    stats: dict[str, tuple[float, float]] = {}
    for key in selected:
        values = [item.signal_map()[key] for item in candidates]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        scale = math.sqrt(variance)
        stats[key] = (mean, scale if scale > 1e-12 else 1.0)
    material = {key: {"mean": mean, "scale": scale} for key, (mean, scale) in sorted(stats.items())}
    digest = sha256(_canonical(material).encode()).hexdigest()
    return stats, f"analog-normalizer:sha256:{digest}"


def _vector(
    state: RegimeState,
    selected: Sequence[str],
    stats: dict[str, tuple[float, float]],
) -> tuple[float, ...]:
    signals = state.signal_map()
    return tuple((signals[key] - stats[key][0]) / stats[key][1] for key in selected)


def _distance(
    left: Sequence[float],
    right: Sequence[float],
    metric: DistanceMetric,
) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("distance vectors must be non-empty and equal length")
    if metric is DistanceMetric.EUCLIDEAN:
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))
    if metric is DistanceMetric.MANHATTAN:
        return sum(abs(a - b) for a, b in zip(left, right, strict=True))
    if metric is DistanceMetric.COSINE:
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm <= 1e-12 and right_norm <= 1e-12:
            return 0.0
        if left_norm <= 1e-12 or right_norm <= 1e-12:
            return 1.0
        similarity = max(-1.0, min(1.0, dot / (left_norm * right_norm)))
        return 1.0 - similarity
    raise ValueError(f"unsupported distance metric: {metric}")


def search_historical_analogs(
    query: RegimeState,
    history: Sequence[RegimeState],
    *,
    config: AnalogSearchConfig | None = None,
) -> HistoricalAnalogReport:
    selected_config = config or AnalogSearchConfig()
    selected = _selected_signals(query, selected_config)
    reasons: list[str] = []
    if query.regime is CanonicalRegime.NO_DATA:
        reasons.append("QUERY_REGIME_NO_DATA")
    if not selected:
        reasons.append("NO_ANALOG_SIGNALS")

    candidates = _eligible_candidates(query, history, selected_config, selected) if selected else ()
    if len(candidates) < selected_config.min_history:
        reasons.append("INSUFFICIENT_STRICTLY_PRIOR_HISTORY")

    matches: tuple[HistoricalAnalogMatch, ...] = ()
    normalizer_digest: str | None = None
    if not reasons:
        stats, normalizer_digest = _normalizer(candidates, selected)
        query_vector = _vector(query, selected, stats)
        scored: list[HistoricalAnalogMatch] = []
        for item in candidates:
            candidate_vector = _vector(item, selected, stats)
            distance = _finite(
                _distance(
                    query_vector,
                    candidate_vector,
                    selected_config.metric,
                ),
                "distance",
            )
            similarity = 1.0 / (1.0 + max(distance, 0.0))
            scored.append(
                HistoricalAnalogMatch(
                    state_id=item.state_id,
                    prediction_time=item.prediction_time,
                    regime=item.regime,
                    distance=distance,
                    similarity=similarity,
                    provider_universe_version=item.provider_universe_version,
                )
            )
        matches = tuple(
            sorted(
                scored,
                key=lambda item: (
                    item.distance,
                    item.prediction_time,
                    item.state_id,
                ),
            )[: selected_config.k]
        )

    status = AnalogSearchStatus.READY if not reasons else AnalogSearchStatus.NO_DATA
    material = {
        "query_state_id": query.state_id,
        "metric": selected_config.metric.value,
        "selected_signals": list(selected),
        "normalizer_digest": normalizer_digest,
        "eligible_candidate_count": len(candidates),
        "status": status.value,
        "reasons": sorted(reasons),
        "matches": [
            {
                "state_id": item.state_id,
                "prediction_time": item.prediction_time.isoformat(),
                "regime": item.regime.value,
                "distance": item.distance,
                "similarity": item.similarity,
                "provider_universe_version": item.provider_universe_version,
            }
            for item in matches
        ],
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return HistoricalAnalogReport(
        report_id=f"historical-analog-report:sha256:{digest}",
        report_sha256=digest,
        query_state_id=query.state_id,
        metric=selected_config.metric,
        selected_signals=selected,
        normalizer_digest=normalizer_digest,
        eligible_candidate_count=len(candidates),
        status=status,
        reasons=tuple(sorted(reasons)),
        matches=matches,
    )


@dataclass(frozen=True, slots=True)
class AnalogSensitivityScenario:
    scenario_id: str
    metric: DistanceMetric
    excluded_signals: tuple[str, ...]
    max_lookback_seconds: float | None
    provider_universe_versions: tuple[str, ...]
    report_id: str
    status: AnalogSearchStatus
    top_k_overlap_with_base: float | None
    top_regime_matches_base: bool | None


@dataclass(frozen=True, slots=True)
class AnalogSensitivityReport:
    report_id: str
    report_sha256: str
    query_state_id: str
    base_report_id: str
    scenarios: tuple[AnalogSensitivityScenario, ...]
    ready_scenario_count: int
    minimum_top_k_overlap: float | None
    top_regime_agreement_rate: float | None
    stable: bool
    reasons: tuple[str, ...]
    decision_authority: bool = False
    execution_weight: float = 0.0


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    if not union:
        return 1.0
    return len(left_set & right_set) / len(union)


def run_analog_sensitivity(
    query: RegimeState,
    history: Sequence[RegimeState],
    *,
    base_config: AnalogSearchConfig,
    metrics: Sequence[DistanceMetric] = tuple(DistanceMetric),
    ablation_sets: Sequence[tuple[str, ...]] = ((),),
    lookbacks: Sequence[timedelta | None] = (None,),
    provider_universe_filters: Sequence[tuple[str, ...]] = ((),),
    min_ready_scenarios: int = 3,
    min_top_k_overlap: float = 0.40,
    min_top_regime_agreement: float = 0.60,
) -> AnalogSensitivityReport:
    if min_ready_scenarios < 1:
        raise ValueError("min_ready_scenarios must be positive")
    if not 0 <= min_top_k_overlap <= 1:
        raise ValueError("min_top_k_overlap must be within [0, 1]")
    if not 0 <= min_top_regime_agreement <= 1:
        raise ValueError("min_top_regime_agreement must be within [0, 1]")

    base = search_historical_analogs(query, history, config=base_config)
    if base.status is not AnalogSearchStatus.READY:
        reasons = ("BASE_ANALOG_SEARCH_NOT_READY",)
        material = {
            "query_state_id": query.state_id,
            "base_report_id": base.report_id,
            "reasons": list(reasons),
        }
        digest = sha256(_canonical(material).encode()).hexdigest()
        return AnalogSensitivityReport(
            report_id=f"analog-sensitivity:sha256:{digest}",
            report_sha256=digest,
            query_state_id=query.state_id,
            base_report_id=base.report_id,
            scenarios=(),
            ready_scenario_count=0,
            minimum_top_k_overlap=None,
            top_regime_agreement_rate=None,
            stable=False,
            reasons=reasons,
        )

    base_ids = tuple(item.state_id for item in base.matches)
    base_top_regime = base.matches[0].regime if base.matches else None
    scenarios: list[AnalogSensitivityScenario] = []
    for metric in metrics:
        for ablation in ablation_sets:
            for lookback in lookbacks:
                for provider_filter in provider_universe_filters:
                    config = replace(
                        base_config,
                        metric=metric,
                        excluded_signals=tuple(ablation),
                        max_lookback=lookback,
                        provider_universe_versions=tuple(provider_filter),
                    )
                    report = search_historical_analogs(
                        query,
                        history,
                        config=config,
                    )
                    overlap: float | None = None
                    regime_match: bool | None = None
                    if report.status is AnalogSearchStatus.READY:
                        overlap = _jaccard(
                            base_ids,
                            tuple(item.state_id for item in report.matches),
                        )
                        top_regime = report.matches[0].regime if report.matches else None
                        regime_match = top_regime is base_top_regime
                    scenario_material = {
                        "metric": metric.value,
                        "excluded_signals": list(ablation),
                        "max_lookback_seconds": (
                            lookback.total_seconds() if lookback is not None else None
                        ),
                        "provider_universe_versions": list(provider_filter),
                        "report_id": report.report_id,
                    }
                    scenario_digest = sha256(_canonical(scenario_material).encode()).hexdigest()
                    scenarios.append(
                        AnalogSensitivityScenario(
                            scenario_id=f"analog-scenario:sha256:{scenario_digest}",
                            metric=metric,
                            excluded_signals=tuple(ablation),
                            max_lookback_seconds=(
                                lookback.total_seconds() if lookback is not None else None
                            ),
                            provider_universe_versions=tuple(provider_filter),
                            report_id=report.report_id,
                            status=report.status,
                            top_k_overlap_with_base=overlap,
                            top_regime_matches_base=regime_match,
                        )
                    )

    ready = tuple(item for item in scenarios if item.status is AnalogSearchStatus.READY)
    overlaps = [
        item.top_k_overlap_with_base for item in ready if item.top_k_overlap_with_base is not None
    ]
    regime_flags = [
        item.top_regime_matches_base for item in ready if item.top_regime_matches_base is not None
    ]
    minimum_overlap = min(overlaps) if overlaps else None
    regime_rate = (
        sum(1 for value in regime_flags if value) / len(regime_flags) if regime_flags else None
    )
    reasons: list[str] = []
    if len(ready) < min_ready_scenarios:
        reasons.append("INSUFFICIENT_READY_SENSITIVITY_SCENARIOS")
    if minimum_overlap is None or minimum_overlap < min_top_k_overlap:
        reasons.append("ANALOG_TOP_K_UNSTABLE")
    if regime_rate is None or regime_rate < min_top_regime_agreement:
        reasons.append("ANALOG_REGIME_UNSTABLE")
    stable = not reasons
    material = {
        "query_state_id": query.state_id,
        "base_report_id": base.report_id,
        "scenario_ids": [item.scenario_id for item in scenarios],
        "ready_scenario_count": len(ready),
        "minimum_top_k_overlap": minimum_overlap,
        "top_regime_agreement_rate": regime_rate,
        "stable": stable,
        "reasons": sorted(reasons),
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return AnalogSensitivityReport(
        report_id=f"analog-sensitivity:sha256:{digest}",
        report_sha256=digest,
        query_state_id=query.state_id,
        base_report_id=base.report_id,
        scenarios=tuple(scenarios),
        ready_scenario_count=len(ready),
        minimum_top_k_overlap=minimum_overlap,
        top_regime_agreement_rate=regime_rate,
        stable=stable,
        reasons=tuple(sorted(reasons)),
    )
