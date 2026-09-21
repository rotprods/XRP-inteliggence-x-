from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow
from xrp_regime_engine.research_horizon import ResearchHorizon


class CanonicalRegime(StrEnum):
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


def _nonempty(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _clip_unit(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _feature_value(
    feature: HistoricalFeatureRow,
    feature_key: str,
) -> float | None:
    try:
        family, name = feature_key.split(".", 1)
    except ValueError as exc:
        raise ValueError("signal feature keys must use family.name") from exc
    family_values = feature.feature_families.get(family)
    if family_values is None:
        return None
    value = family_values.get(name)
    if value is None:
        return None
    return _finite(float(value), feature_key)


@dataclass(frozen=True, slots=True)
class RegimeSignalSpec:
    signal: str
    feature_key: str
    center: float = 0.0
    scale: float = 1.0
    direction: float = 1.0

    def __post_init__(self) -> None:
        _nonempty(self.signal, "signal")
        _nonempty(self.feature_key, "feature_key")
        _finite(self.center, "center")
        if _finite(self.scale, "scale") <= 0:
            raise ValueError("scale must be positive")
        if self.direction not in {-1.0, 1.0}:
            raise ValueError("direction must be -1 or 1")

    def transform(self, feature: HistoricalFeatureRow) -> float | None:
        value = _feature_value(feature, self.feature_key)
        if value is None:
            return None
        return _clip_unit(self.direction * (value - self.center) / self.scale)


@dataclass(frozen=True, slots=True)
class RegimeClassifierPolicy:
    specs: tuple[RegimeSignalSpec, ...]
    required_signals: tuple[str, ...]
    min_signal_coverage: float = 0.70
    breakout_threshold: float = 0.65
    failed_breakout_threshold: float = -0.55
    deleveraging_threshold: float = 0.60
    distribution_threshold: float = 0.60
    crowding_threshold: float = 0.60
    expansion_trend_threshold: float = 0.35
    spot_flow_threshold: float = 0.40
    leverage_threshold: float = 0.45
    capitulation_trend_threshold: float = -0.65
    capitulation_volatility_threshold: float = 0.55
    capitulation_drawdown_threshold: float = 0.55
    recovery_trend_threshold: float = 0.15
    risk_on_liquidity_threshold: float = 0.35
    accumulation_abs_trend_max: float = 0.25

    def __post_init__(self) -> None:
        if not self.specs:
            raise ValueError("regime policy requires signal specs")
        names = tuple(item.signal for item in self.specs)
        if len(names) != len(set(names)):
            raise ValueError("regime signal names must be unique")
        unknown_required = set(self.required_signals) - set(names)
        if unknown_required:
            raise ValueError("required_signals must reference declared signal specs")
        if not 0 < _finite(self.min_signal_coverage, "min_signal_coverage") <= 1:
            raise ValueError("min_signal_coverage must be within (0, 1]")
        for field in (
            "breakout_threshold",
            "deleveraging_threshold",
            "distribution_threshold",
            "crowding_threshold",
            "expansion_trend_threshold",
            "spot_flow_threshold",
            "leverage_threshold",
            "capitulation_volatility_threshold",
            "capitulation_drawdown_threshold",
            "recovery_trend_threshold",
            "risk_on_liquidity_threshold",
            "accumulation_abs_trend_max",
        ):
            value = _finite(float(getattr(self, field)), field)
            if not 0 <= value <= 1:
                raise ValueError(f"{field} must be within [0, 1]")
        failed = _finite(
            self.failed_breakout_threshold,
            "failed_breakout_threshold",
        )
        capitulation = _finite(
            self.capitulation_trend_threshold,
            "capitulation_trend_threshold",
        )
        if not -1 <= failed < 0 or not -1 <= capitulation < 0:
            raise ValueError("negative regime thresholds must be within [-1, 0)")

    @property
    def policy_id(self) -> str:
        payload = {
            "specs": [
                {
                    "signal": item.signal,
                    "feature_key": item.feature_key,
                    "center": item.center,
                    "scale": item.scale,
                    "direction": item.direction,
                }
                for item in self.specs
            ],
            "required_signals": list(self.required_signals),
            "min_signal_coverage": self.min_signal_coverage,
            "thresholds": {
                "breakout": self.breakout_threshold,
                "failed_breakout": self.failed_breakout_threshold,
                "deleveraging": self.deleveraging_threshold,
                "distribution": self.distribution_threshold,
                "crowding": self.crowding_threshold,
                "expansion_trend": self.expansion_trend_threshold,
                "spot_flow": self.spot_flow_threshold,
                "leverage": self.leverage_threshold,
                "capitulation_trend": self.capitulation_trend_threshold,
                "capitulation_volatility": self.capitulation_volatility_threshold,
                "capitulation_drawdown": self.capitulation_drawdown_threshold,
                "recovery_trend": self.recovery_trend_threshold,
                "risk_on_liquidity": self.risk_on_liquidity_threshold,
                "accumulation_abs_trend_max": self.accumulation_abs_trend_max,
            },
        }
        return f"regime-policy:sha256:{sha256(_canonical(payload).encode()).hexdigest()}"


def canonical_regime_policy() -> RegimeClassifierPolicy:
    return RegimeClassifierPolicy(
        specs=(
            RegimeSignalSpec("trend", "market.trailing_return_30d", scale=0.30),
            RegimeSignalSpec(
                "relative_strength",
                "cross_asset.xrp_btc_return_30d",
                scale=0.25,
            ),
            RegimeSignalSpec(
                "spot_flow",
                "microstructure.spot_flow_imbalance",
                scale=1.0,
            ),
            RegimeSignalSpec(
                "leverage",
                "derivatives.leverage_expansion",
                scale=1.0,
            ),
            RegimeSignalSpec(
                "crowding",
                "derivatives.long_crowding",
                scale=1.0,
            ),
            RegimeSignalSpec(
                "deleveraging",
                "derivatives.deleveraging",
                scale=1.0,
            ),
            RegimeSignalSpec(
                "breakout",
                "market.breakout_score",
                scale=1.0,
            ),
            RegimeSignalSpec(
                "distribution",
                "market.distribution_score",
                scale=1.0,
            ),
            RegimeSignalSpec(
                "volatility",
                "market.realized_volatility_z",
                scale=2.0,
            ),
            RegimeSignalSpec(
                "drawdown_stress",
                "market.drawdown_stress",
                scale=1.0,
            ),
            RegimeSignalSpec(
                "liquidity",
                "macro.liquidity_risk_on",
                scale=1.0,
            ),
        ),
        required_signals=("trend", "relative_strength"),
    )


@dataclass(frozen=True, slots=True)
class RegimeState:
    state_id: str
    state_sha256: str
    feature_row_id: str
    prediction_time: datetime
    horizon: ResearchHorizon
    policy_id: str
    regime: CanonicalRegime
    confidence: float
    signal_coverage: float
    signals: tuple[tuple[str, float], ...]
    reasons: tuple[str, ...]
    provider_universe_version: str
    source_snapshot_ids: tuple[str, ...]
    decision_authority: bool = False
    execution_weight: float = 0.0

    def signal_map(self) -> dict[str, float]:
        return dict(self.signals)


def _signal(
    signals: Mapping[str, float],
    name: str,
    default: float = 0.0,
) -> float:
    return float(signals.get(name, default))


def _has(signals: Mapping[str, float], *names: str) -> bool:
    return all(name in signals for name in names)


def classify_regime(
    feature: HistoricalFeatureRow,
    *,
    policy: RegimeClassifierPolicy | None = None,
) -> RegimeState:
    selected = policy or canonical_regime_policy()
    extracted: dict[str, float] = {}
    for spec in selected.specs:
        value = spec.transform(feature)
        if value is not None:
            extracted[spec.signal] = value
    coverage = len(extracted) / len(selected.specs)
    missing_required = tuple(sorted(set(selected.required_signals) - set(extracted)))
    reasons: list[str] = []

    if missing_required:
        regime = CanonicalRegime.NO_DATA
        reasons.append("MISSING_REQUIRED_SIGNALS:" + ",".join(missing_required))
    elif coverage < selected.min_signal_coverage:
        regime = CanonicalRegime.NO_DATA
        reasons.append("INSUFFICIENT_SIGNAL_COVERAGE")
    else:
        trend = _signal(extracted, "trend")
        relative = _signal(extracted, "relative_strength")
        spot_flow = _signal(extracted, "spot_flow")
        leverage = _signal(extracted, "leverage")
        crowding = _signal(extracted, "crowding")
        deleveraging = _signal(extracted, "deleveraging")
        breakout = _signal(extracted, "breakout")
        distribution = _signal(extracted, "distribution")
        volatility = _signal(extracted, "volatility")
        drawdown = _signal(extracted, "drawdown_stress")
        liquidity = _signal(extracted, "liquidity")

        if _has(extracted, "breakout") and breakout <= selected.failed_breakout_threshold:
            regime = CanonicalRegime.FAILED_BREAKOUT
        elif _has(extracted, "deleveraging") and deleveraging >= selected.deleveraging_threshold:
            regime = CanonicalRegime.DELEVERAGING
        elif (
            _has(extracted, "trend", "volatility", "drawdown_stress")
            and trend <= selected.capitulation_trend_threshold
            and volatility >= selected.capitulation_volatility_threshold
            and drawdown >= selected.capitulation_drawdown_threshold
        ):
            regime = CanonicalRegime.CAPITULATION
        elif (
            _has(extracted, "crowding", "leverage")
            and crowding >= selected.crowding_threshold
            and leverage >= selected.leverage_threshold
        ):
            regime = CanonicalRegime.LONG_CROWDING
        elif (
            _has(extracted, "distribution")
            and distribution >= selected.distribution_threshold
        ):
            regime = CanonicalRegime.DISTRIBUTION
        elif (
            _has(extracted, "breakout", "trend")
            and breakout >= selected.breakout_threshold
            and trend >= selected.expansion_trend_threshold
        ):
            regime = CanonicalRegime.BREAKOUT
        elif (
            _has(extracted, "trend", "spot_flow", "leverage")
            and trend >= selected.expansion_trend_threshold
            and spot_flow >= selected.spot_flow_threshold
            and leverage < selected.leverage_threshold
        ):
            regime = CanonicalRegime.SPOT_LED_EXPANSION
        elif (
            _has(extracted, "trend", "leverage", "crowding")
            and trend >= selected.expansion_trend_threshold
            and leverage >= selected.leverage_threshold
            and crowding < selected.crowding_threshold
        ):
            regime = CanonicalRegime.LEVERAGED_EXPANSION
        elif (
            _has(extracted, "trend", "drawdown_stress")
            and trend >= selected.recovery_trend_threshold
            and drawdown >= 0.30
        ):
            regime = CanonicalRegime.RECOVERY
        elif (
            _has(extracted, "liquidity", "trend", "relative_strength")
            and liquidity >= selected.risk_on_liquidity_threshold
            and trend >= selected.recovery_trend_threshold
            and relative >= 0.0
        ):
            regime = CanonicalRegime.RISK_ON
        elif (
            _has(extracted, "trend", "spot_flow", "leverage", "distribution")
            and abs(trend) <= selected.accumulation_abs_trend_max
            and spot_flow >= 0.10
            and leverage < selected.leverage_threshold
            and distribution < selected.distribution_threshold
        ):
            regime = CanonicalRegime.ACCUMULATION
        else:
            regime = CanonicalRegime.NO_DATA
            reasons.append("NO_RULE_WITH_SUFFICIENT_SEPARATION")

    max_strength = max((abs(value) for value in extracted.values()), default=0.0)
    confidence = (
        0.0
        if regime is CanonicalRegime.NO_DATA
        else min(
            1.0,
            coverage * (0.5 + 0.5 * max_strength),
        )
    )
    payload = {
        "feature_row_id": feature.feature_row_id,
        "prediction_time": feature.prediction_time.isoformat(),
        "horizon": feature.horizon.value,
        "policy_id": selected.policy_id,
        "regime": regime.value,
        "confidence": confidence,
        "signal_coverage": coverage,
        "signals": sorted(extracted.items()),
        "reasons": sorted(reasons),
        "provider_universe_version": feature.provider_universe_version,
        "source_snapshot_ids": list(feature.source_snapshot_ids),
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(payload).encode()).hexdigest()
    return RegimeState(
        state_id=f"regime-state:sha256:{digest}",
        state_sha256=digest,
        feature_row_id=feature.feature_row_id,
        prediction_time=feature.prediction_time,
        horizon=feature.horizon,
        policy_id=selected.policy_id,
        regime=regime,
        confidence=confidence,
        signal_coverage=coverage,
        signals=tuple(sorted(extracted.items())),
        reasons=tuple(sorted(reasons)),
        provider_universe_version=feature.provider_universe_version,
        source_snapshot_ids=feature.source_snapshot_ids,
    )
