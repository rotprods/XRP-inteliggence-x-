from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256

from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow


class HistoricalRegime(StrEnum):
    CAPITULATION = "CAPITULATION"
    ACCUMULATION = "ACCUMULATION"
    RECOVERY = "RECOVERY"
    RISK_ON = "RISK_ON"
    SPOT_LED_EXPANSION = "SPOT_LED_EXPANSION"
    LEVERAGED_EXPANSION = "LEVERAGED_EXPANSION"
    LONG_CROWDING = "LONG_CROWDING"
    DISTRIBUTION = "DISTRIBUTION"
    DELEVERAGING = "DELEVERAGING"
    BREAKOUT = "BREAKOUT"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
    NO_DATA = "NO_DATA"


class AnalogDistanceMetric(StrEnum):
    EUCLIDEAN = "EUCLIDEAN"
    MANHATTAN = "MANHATTAN"
    COSINE = "COSINE"


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _finite(value: float, field: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field} must be finite")
    return numeric


def _nonempty(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _read_feature(
    feature: HistoricalFeatureRow,
    key: str,
) -> float | None:
    try:
        family, name = key.split(".", 1)
    except ValueError as exc:
        raise ValueError("feature keys must use family.name") from exc
    family_values = feature.feature_families.get(family)
    if family_values is None:
        return None
    value = family_values.get(name)
    if value is None:
        return None
    return _finite(value, key)


@dataclass(frozen=True, slots=True)
class RegimeFeatureMap:
    short_return: str
    medium_return: str
    relative_strength: str
    spot_flow: str
    open_interest_change: str
    funding: str
    liquidation_stress: str
    depth_imbalance: str

    def __post_init__(self) -> None:
        for field_name in (
            "short_return",
            "medium_return",
            "relative_strength",
            "spot_flow",
            "open_interest_change",
            "funding",
            "liquidation_stress",
            "depth_imbalance",
        ):
            value = getattr(self, field_name)
            _nonempty(value, field_name)
            if "." not in value:
                raise ValueError(f"{field_name} must use family.name")


@dataclass(frozen=True, slots=True)
class RegimeThresholds:
    breakout_return: float = 0.05
    recovery_return: float = 0.02
    capitulation_return: float = -0.08
    flat_abs_return: float = 0.01
    relative_strength: float = 0.01
    positive_flow: float = 0.10
    negative_flow: float = -0.10
    oi_expansion: float = 0.05
    oi_deleveraging: float = -0.05
    elevated_funding: float = 0.0003
    crowded_funding: float = 0.001
    liquidation_stress: float = 1.0
    supportive_depth: float = 0.20
    distribution_depth: float = -0.20

    def __post_init__(self) -> None:
        for field_name in (
            "breakout_return",
            "recovery_return",
            "capitulation_return",
            "flat_abs_return",
            "relative_strength",
            "positive_flow",
            "negative_flow",
            "oi_expansion",
            "oi_deleveraging",
            "elevated_funding",
            "crowded_funding",
            "liquidation_stress",
            "supportive_depth",
            "distribution_depth",
        ):
            _finite(float(getattr(self, field_name)), field_name)
        if self.breakout_return <= self.recovery_return or self.recovery_return <= 0:
            raise ValueError("breakout/recovery thresholds are inconsistent")
        if self.capitulation_return >= 0:
            raise ValueError("capitulation_return must be negative")
        if self.flat_abs_return <= 0:
            raise ValueError("flat_abs_return must be positive")
        if self.relative_strength <= 0:
            raise ValueError("relative_strength must be positive")
        if self.positive_flow <= 0 or self.negative_flow >= 0:
            raise ValueError("flow thresholds must straddle zero")
        if self.oi_expansion <= 0 or self.oi_deleveraging >= 0:
            raise ValueError("OI thresholds must straddle zero")
        if not 0 <= self.elevated_funding < self.crowded_funding:
            raise ValueError("funding thresholds are inconsistent")
        if self.liquidation_stress < 0:
            raise ValueError("liquidation_stress cannot be negative")
        if self.supportive_depth <= 0 or self.distribution_depth >= 0:
            raise ValueError("depth thresholds must straddle zero")


@dataclass(frozen=True, slots=True)
class RegimeAssessment:
    assessment_id: str
    feature_row_id: str
    regime: HistoricalRegime
    reasons: tuple[str, ...]
    missing_features: tuple[str, ...]
    rule_version: str
    truth_claim: bool = False
    probability_calibrated: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0


def classify_regime_candidate(
    feature: HistoricalFeatureRow,
    *,
    feature_map: RegimeFeatureMap,
    thresholds: RegimeThresholds | None = None,
    rule_version: str = "regime-candidate-v1",
) -> RegimeAssessment:
    selected = thresholds or RegimeThresholds()
    version = _nonempty(rule_version, "rule_version")
    keys = {
        "short_return": feature_map.short_return,
        "medium_return": feature_map.medium_return,
        "relative_strength": feature_map.relative_strength,
        "spot_flow": feature_map.spot_flow,
        "open_interest_change": feature_map.open_interest_change,
        "funding": feature_map.funding,
        "liquidation_stress": feature_map.liquidation_stress,
        "depth_imbalance": feature_map.depth_imbalance,
    }
    values = {name: _read_feature(feature, key) for name, key in keys.items()}
    missing = tuple(sorted(keys[name] for name, value in values.items() if value is None))

    regime = HistoricalRegime.NO_DATA
    reasons: tuple[str, ...]
    if missing:
        reasons = ("MISSING_REQUIRED_REGIME_FEATURES",)
    else:
        def required_value(name: str) -> float:
            value = values[name]
            if value is None:
                raise RuntimeError("missingness gate failed to narrow required regime feature")
            return value

        short = required_value("short_return")
        medium = required_value("medium_return")
        relative = required_value("relative_strength")
        flow = required_value("spot_flow")
        oi_change = required_value("open_interest_change")
        funding = required_value("funding")
        liquidations = required_value("liquidation_stress")
        depth = required_value("depth_imbalance")

        if medium <= selected.capitulation_return and liquidations >= selected.liquidation_stress:
            regime = HistoricalRegime.CAPITULATION
            reasons = ("SEVERE_DRAWDOWN", "LIQUIDATION_STRESS")
        elif oi_change <= selected.oi_deleveraging and liquidations >= selected.liquidation_stress:
            regime = HistoricalRegime.DELEVERAGING
            reasons = ("OI_CONTRACTION", "LIQUIDATION_STRESS")
        elif funding >= selected.crowded_funding and oi_change >= selected.oi_expansion:
            regime = HistoricalRegime.LONG_CROWDING
            reasons = ("CROWDED_FUNDING", "OI_EXPANSION")
        elif (
            medium >= selected.breakout_return
            and short <= -selected.recovery_return
            and relative <= 0
        ):
            regime = HistoricalRegime.FAILED_BREAKOUT
            reasons = ("PRIOR_EXPANSION", "SHORT_TERM_REVERSAL", "RELATIVE_STRENGTH_LOST")
        elif (
            short >= selected.breakout_return
            and relative >= selected.relative_strength
            and flow >= selected.positive_flow
        ):
            regime = HistoricalRegime.BREAKOUT
            reasons = ("BREAKOUT_RETURN", "RELATIVE_STRENGTH", "POSITIVE_SPOT_FLOW")
        elif (
            short >= selected.recovery_return
            and oi_change >= selected.oi_expansion
            and funding >= selected.elevated_funding
        ):
            regime = HistoricalRegime.LEVERAGED_EXPANSION
            reasons = ("POSITIVE_RETURN", "OI_EXPANSION", "ELEVATED_FUNDING")
        elif (
            short >= selected.recovery_return
            and flow >= selected.positive_flow
            and oi_change < selected.oi_expansion
            and funding < selected.elevated_funding
        ):
            regime = HistoricalRegime.SPOT_LED_EXPANSION
            reasons = ("POSITIVE_RETURN", "POSITIVE_SPOT_FLOW", "LEVERAGE_NOT_EXPANDING")
        elif (
            short >= selected.recovery_return
            and medium <= 0
            and relative >= selected.relative_strength
        ):
            regime = HistoricalRegime.RECOVERY
            reasons = ("SHORT_TERM_RECOVERY", "RELATIVE_STRENGTH")
        elif (
            short <= 0
            and flow <= selected.negative_flow
            and depth <= selected.distribution_depth
        ):
            regime = HistoricalRegime.DISTRIBUTION
            reasons = ("NON_POSITIVE_RETURN", "NEGATIVE_SPOT_FLOW", "ASK_SIDE_PRESSURE")
        elif (
            abs(short) <= selected.flat_abs_return
            and flow >= 0
            and depth >= selected.supportive_depth
            and funding < selected.elevated_funding
        ):
            regime = HistoricalRegime.ACCUMULATION
            reasons = ("FLAT_PRICE", "NON_NEGATIVE_FLOW", "SUPPORTIVE_DEPTH")
        elif short > 0 and medium > 0 and relative > 0:
            regime = HistoricalRegime.RISK_ON
            reasons = ("POSITIVE_TREND", "POSITIVE_RELATIVE_STRENGTH")
        else:
            reasons = ("NO_REGIME_RULE_MATCHED",)

    material = {
        "feature_row_id": feature.feature_row_id,
        "regime": regime.value,
        "reasons": list(reasons),
        "missing_features": list(missing),
        "rule_version": version,
        "truth_claim": False,
        "probability_calibrated": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return RegimeAssessment(
        assessment_id=f"regime-assessment:sha256:{digest}",
        feature_row_id=feature.feature_row_id,
        regime=regime,
        reasons=reasons,
        missing_features=missing,
        rule_version=version,
    )


@dataclass(frozen=True, slots=True)
class AnalogSearchPolicy:
    feature_keys: tuple[str, ...]
    top_k: int = 5
    min_history: int = 20
    metric: AnalogDistanceMetric = AnalogDistanceMetric.EUCLIDEAN

    def __post_init__(self) -> None:
        if not self.feature_keys:
            raise ValueError("feature_keys cannot be empty")
        if len(self.feature_keys) != len(set(self.feature_keys)):
            raise ValueError("feature_keys must be unique")
        for key in self.feature_keys:
            _nonempty(key, "feature_key")
            if "." not in key:
                raise ValueError("feature keys must use family.name")
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
        if self.min_history < self.top_k:
            raise ValueError("min_history must be >= top_k")


@dataclass(frozen=True, slots=True)
class AnalogMatch:
    rank: int
    feature_row_id: str
    prediction_time: str
    distance: float
    regime: HistoricalRegime | None


@dataclass(frozen=True, slots=True)
class HistoricalAnalogSearchResult:
    search_id: str
    query_feature_row_id: str
    query_prediction_time: str
    horizon: str
    metric: AnalogDistanceMetric
    feature_keys: tuple[str, ...]
    candidate_count: int
    skipped_missing_count: int
    universe_sha256: str
    scaler_sha256: str
    matches: tuple[AnalogMatch, ...]
    regime_counts: tuple[tuple[HistoricalRegime, int], ...]
    truth_claim: bool = False
    probability_calibrated: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0


def _complete_vector(
    feature: HistoricalFeatureRow,
    keys: Sequence[str],
) -> tuple[float, ...] | None:
    values: list[float] = []
    for key in keys:
        value = _read_feature(feature, key)
        if value is None:
            return None
        values.append(value)
    return tuple(values)


def _mean_scale_matrix(
    matrix: Sequence[tuple[float, ...]],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if not matrix:
        raise ValueError("analog matrix cannot be empty")
    width = len(matrix[0])
    if width < 1 or any(len(row) != width for row in matrix):
        raise ValueError("analog matrix must be rectangular")
    means: list[float] = []
    scales: list[float] = []
    for column in range(width):
        values = [row[column] for row in matrix]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        scale = math.sqrt(variance)
        means.append(mean)
        scales.append(scale if scale > 1e-12 else 1.0)
    return tuple(means), tuple(scales)


def _standardize(
    vector: Sequence[float],
    means: Sequence[float],
    scales: Sequence[float],
) -> tuple[float, ...]:
    if not (len(vector) == len(means) == len(scales)):
        raise ValueError("analog scaling dimensions do not match")
    return tuple(
        (value - mean) / scale
        for value, mean, scale in zip(vector, means, scales, strict=True)
    )


def _distance(
    left: Sequence[float],
    right: Sequence[float],
    metric: AnalogDistanceMetric,
) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("analog distance vectors must be non-empty and aligned")
    if metric is AnalogDistanceMetric.EUCLIDEAN:
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))
    if metric is AnalogDistanceMetric.MANHATTAN:
        return sum(abs(a - b) for a, b in zip(left, right, strict=True))
    if metric is AnalogDistanceMetric.COSINE:
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm <= 1e-12 or right_norm <= 1e-12:
            return 1.0
        cosine = max(min(dot / (left_norm * right_norm), 1.0), -1.0)
        return 1.0 - cosine
    raise ValueError(f"unsupported analog distance metric: {metric}")


def search_historical_analogs(
    query: HistoricalFeatureRow,
    history: Sequence[HistoricalFeatureRow],
    *,
    policy: AnalogSearchPolicy,
    regime_feature_map: RegimeFeatureMap | None = None,
    regime_thresholds: RegimeThresholds | None = None,
) -> HistoricalAnalogSearchResult:
    query_vector = _complete_vector(query, policy.feature_keys)
    if query_vector is None:
        raise ValueError("query is missing required analog features")
    seen_ids: set[str] = set()
    candidates: list[tuple[HistoricalFeatureRow, tuple[float, ...]]] = []
    skipped_missing = 0
    for item in history:
        if item.feature_row_id in seen_ids:
            raise ValueError("historical analog universe contains duplicate feature_row_id")
        seen_ids.add(item.feature_row_id)
        if item.horizon is not query.horizon:
            continue
        if item.prediction_time >= query.prediction_time:
            continue
        vector = _complete_vector(item, policy.feature_keys)
        if vector is None:
            skipped_missing += 1
            continue
        candidates.append((item, vector))
    if len(candidates) < policy.min_history:
        raise ValueError("insufficient strictly-prior complete historical analog universe")

    matrix = tuple(vector for _, vector in candidates)
    means, scales = _mean_scale_matrix(matrix)
    query_scaled = _standardize(query_vector, means, scales)
    scored: list[tuple[float, HistoricalFeatureRow]] = []
    for item, vector in candidates:
        candidate_scaled = _standardize(vector, means, scales)
        distance = _distance(query_scaled, candidate_scaled, policy.metric)
        scored.append((_finite(distance, "analog distance"), item))
    scored.sort(key=lambda pair: (pair[0], pair[1].prediction_time, pair[1].feature_row_id))
    selected = scored[: policy.top_k]

    matches: list[AnalogMatch] = []
    regime_counter: Counter[HistoricalRegime] = Counter()
    for rank, (distance, item) in enumerate(selected, start=1):
        regime: HistoricalRegime | None = None
        if regime_feature_map is not None:
            assessment = classify_regime_candidate(
                item,
                feature_map=regime_feature_map,
                thresholds=regime_thresholds,
            )
            regime = assessment.regime
            regime_counter[regime] += 1
        matches.append(
            AnalogMatch(
                rank=rank,
                feature_row_id=item.feature_row_id,
                prediction_time=item.prediction_time.isoformat(),
                distance=distance,
                regime=regime,
            )
        )

    universe_material = [
        {
            "feature_row_id": item.feature_row_id,
            "prediction_time": item.prediction_time.isoformat(),
            "vector": list(vector),
        }
        for item, vector in candidates
    ]
    universe_digest = sha256(_canonical(universe_material).encode()).hexdigest()
    scaler_material = {"means": list(means), "scales": list(scales)}
    scaler_digest = sha256(_canonical(scaler_material).encode()).hexdigest()
    material = {
        "query_feature_row_id": query.feature_row_id,
        "query_prediction_time": query.prediction_time.isoformat(),
        "horizon": query.horizon.value,
        "metric": policy.metric.value,
        "feature_keys": list(policy.feature_keys),
        "candidate_count": len(candidates),
        "skipped_missing_count": skipped_missing,
        "universe_sha256": universe_digest,
        "scaler_sha256": scaler_digest,
        "matches": [
            {
                "rank": item.rank,
                "feature_row_id": item.feature_row_id,
                "prediction_time": item.prediction_time,
                "distance": item.distance,
                "regime": item.regime.value if item.regime is not None else None,
            }
            for item in matches
        ],
        "truth_claim": False,
        "probability_calibrated": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return HistoricalAnalogSearchResult(
        search_id=f"historical-analog-search:sha256:{digest}",
        query_feature_row_id=query.feature_row_id,
        query_prediction_time=query.prediction_time.isoformat(),
        horizon=query.horizon.value,
        metric=policy.metric,
        feature_keys=policy.feature_keys,
        candidate_count=len(candidates),
        skipped_missing_count=skipped_missing,
        universe_sha256=universe_digest,
        scaler_sha256=scaler_digest,
        matches=tuple(matches),
        regime_counts=tuple(sorted(regime_counter.items(), key=lambda item: item[0].value)),
    )


@dataclass(frozen=True, slots=True)
class AnalogStabilityPolicy:
    metrics: tuple[AnalogDistanceMetric, ...] = (
        AnalogDistanceMetric.EUCLIDEAN,
        AnalogDistanceMetric.MANHATTAN,
        AnalogDistanceMetric.COSINE,
    )
    leave_one_feature_out: bool = True
    min_overlap: float = 0.40

    def __post_init__(self) -> None:
        if not self.metrics:
            raise ValueError("stability metrics cannot be empty")
        if len(self.metrics) != len(set(self.metrics)):
            raise ValueError("stability metrics must be unique")
        if not 0 <= self.min_overlap <= 1:
            raise ValueError("min_overlap must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class AnalogStabilityVariant:
    variant_id: str
    metric: AnalogDistanceMetric
    feature_keys: tuple[str, ...]
    search_id: str
    top_k_overlap: float


@dataclass(frozen=True, slots=True)
class AnalogStabilityReport:
    report_id: str
    base_search_id: str
    variants: tuple[AnalogStabilityVariant, ...]
    minimum_overlap: float
    stable: bool
    reasons: tuple[str, ...]
    truth_claim: bool = False
    probability_calibrated: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0


def assess_analog_stability(
    query: HistoricalFeatureRow,
    history: Sequence[HistoricalFeatureRow],
    *,
    base_policy: AnalogSearchPolicy,
    stability_policy: AnalogStabilityPolicy | None = None,
) -> AnalogStabilityReport:
    selected = stability_policy or AnalogStabilityPolicy()
    base = search_historical_analogs(query, history, policy=base_policy)
    base_ids = {item.feature_row_id for item in base.matches}
    variants: list[AnalogStabilityVariant] = []

    variant_policies: list[AnalogSearchPolicy] = []
    for metric in selected.metrics:
        if metric is base_policy.metric:
            continue
        variant_policies.append(replace(base_policy, metric=metric))
    if selected.leave_one_feature_out and len(base_policy.feature_keys) > 1:
        for excluded in base_policy.feature_keys:
            feature_keys = tuple(key for key in base_policy.feature_keys if key != excluded)
            variant_policies.append(replace(base_policy, feature_keys=feature_keys))

    seen_variants: set[tuple[AnalogDistanceMetric, tuple[str, ...]]] = set()
    for policy in variant_policies:
        variant_key = (policy.metric, policy.feature_keys)
        if variant_key in seen_variants:
            continue
        seen_variants.add(variant_key)
        result = search_historical_analogs(query, history, policy=policy)
        variant_ids = {item.feature_row_id for item in result.matches}
        overlap = len(base_ids & variant_ids) / len(base_ids)
        material = {
            "metric": policy.metric.value,
            "feature_keys": list(policy.feature_keys),
            "search_id": result.search_id,
            "top_k_overlap": overlap,
        }
        digest = sha256(_canonical(material).encode()).hexdigest()
        variants.append(
            AnalogStabilityVariant(
                variant_id=f"analog-stability-variant:sha256:{digest}",
                metric=policy.metric,
                feature_keys=policy.feature_keys,
                search_id=result.search_id,
                top_k_overlap=overlap,
            )
        )

    minimum_overlap = min((item.top_k_overlap for item in variants), default=1.0)
    reasons: list[str] = []
    if not variants:
        reasons.append("NO_STABILITY_VARIANTS")
    if minimum_overlap < selected.min_overlap:
        reasons.append("ANALOG_SET_UNSTABLE")
    material = {
        "base_search_id": base.search_id,
        "variant_ids": [item.variant_id for item in variants],
        "minimum_overlap": minimum_overlap,
        "stable": not reasons,
        "reasons": reasons,
        "truth_claim": False,
        "probability_calibrated": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return AnalogStabilityReport(
        report_id=f"analog-stability-report:sha256:{digest}",
        base_search_id=base.search_id,
        variants=tuple(variants),
        minimum_overlap=minimum_overlap,
        stable=not reasons,
        reasons=tuple(reasons),
    )
