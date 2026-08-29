from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from statistics import pstdev
from typing import Iterable

from xrp_regime_engine.models import (
    ComponentScores,
    DataFlag,
    Horizon,
    RegimeLabel,
    RegimeSnapshot,
)


FeatureMap = dict[str, float | None]

REGIME_POLICY_VERSION = "0.2.0-alpha.2"

HORIZON_WEIGHTS: dict[Horizon, dict[str, float]] = {
    Horizon.H1: {
        "macro": 0.10,
        "crypto": 0.30,
        "xrp_relative": 0.30,
        "derivatives": 0.25,
        "xrpl": 0.05,
    },
    Horizon.H4: {
        "macro": 0.15,
        "crypto": 0.30,
        "xrp_relative": 0.30,
        "derivatives": 0.20,
        "xrpl": 0.05,
    },
    Horizon.D1: {
        "macro": 0.25,
        "crypto": 0.30,
        "xrp_relative": 0.30,
        "derivatives": 0.10,
        "xrpl": 0.05,
    },
    Horizon.W1: {
        "macro": 0.35,
        "crypto": 0.30,
        "xrp_relative": 0.25,
        "derivatives": 0.05,
        "xrpl": 0.05,
    },
}


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_feature_values(features: FeatureMap) -> FeatureMap:
    return {key: _feature(features, key) for key in sorted(features)}


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _scale(value: float, center: float = 0.0, width: float = 0.10) -> float:
    if width <= 0:
        raise ValueError("width must be positive")
    return _clip(50 + 50 * (value - center) / width)


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 50.0


def _feature(features: FeatureMap, key: str) -> float | None:
    value = features.get(key)
    if value is None:
        return None
    candidate = float(value)
    return candidate if math.isfinite(candidate) else None


def _scaled(
    features: FeatureMap,
    key: str,
    *,
    center: float = 0.0,
    width: float = 0.10,
    multiplier: float = 1.0,
) -> float | None:
    value = _feature(features, key)
    if value is None:
        return None
    return _scale(multiplier * value, center=center, width=width)


def _component(values: Iterable[float | None]) -> tuple[float, float]:
    materialized = list(values)
    present = [float(value) for value in materialized if value is not None]
    coverage = len(present) / len(materialized) if materialized else 0.0
    return (_mean(present), coverage)


def _quality(features: FeatureMap) -> tuple[float, float, float]:
    keys = ("provider_agreement", "freshness_score", "source_coverage")
    values = [_feature(features, key) for key in keys]
    present = [_clip01(value) for value in values if value is not None]
    coverage = len(present) / len(keys)
    quality = _mean([value * 100 for value in present]) if present else 0.0
    confidence = (_mean(present) if present else 0.0) * coverage
    return quality, coverage, confidence


PROTOTYPES: dict[str, dict[str, float]] = {
    "2017_XRP_EXPANSION": {
        "xrp_return_30d": 0.70,
        "xrp_btc_return_30d": 0.40,
        "xrp_rsi_14": 78.0,
        "dxy_return_20d": -0.02,
    },
    "2022_LIQUIDITY_STRESS": {
        "xrp_return_30d": -0.35,
        "btc_return_30d": -0.30,
        "vix_z_20d": 1.8,
        "dxy_return_20d": 0.05,
    },
    "2023_LEGAL_REPRICING": {
        "xrp_return_30d": 0.45,
        "xrp_btc_return_30d": 0.30,
        "xrp_rsi_14": 72.0,
        "btc_return_30d": 0.08,
    },
    "BOTTOMING_REVERSAL": {
        "xrp_return_30d": 0.18,
        "xrp_btc_return_30d": 0.08,
        "xrp_drawdown_365d": -0.55,
        "ndx_return_20d": 0.04,
    },
}


def historical_analogues(features: FeatureMap, top_n: int = 3) -> list[dict[str, float | str]]:
    scored: list[tuple[str, float]] = []
    for name, prototype in PROTOTYPES.items():
        distances: list[float] = []
        for key, target in prototype.items():
            value = _feature(features, key)
            if value is None:
                continue
            scale = max(abs(target), 0.05)
            distances.append(abs(value - target) / scale)
        if not distances:
            continue
        similarity = 1.0 / (1.0 + _mean(distances))
        scored.append((name, similarity))
    return [
        {
            "window": name,
            "similarity": round(score, 4),
            "caveat": "prototype similarity, not forecast identity",
        }
        for name, score in sorted(scored, key=lambda item: item[1], reverse=True)[:top_n]
    ]


def _derivatives_health(features: FeatureMap) -> tuple[float, float]:
    funding = _feature(features, "funding_z")
    oi_divergence = _feature(features, "oi_price_divergence")
    liquidation_impulse = _feature(features, "liquidation_impulse")
    values: list[float | None] = [
        None if funding is None else _clip(100 * (1 - min(abs(funding) / 2.5, 1.0))),
        None
        if oi_divergence is None
        else _clip(100 * (1 - min(abs(oi_divergence) / 2.0, 1.0))),
        None if liquidation_impulse is None else _scale(liquidation_impulse, width=1.0),
    ]
    return _component(values)


def score_regime(
    features: FeatureMap,
    horizon: Horizon = Horizon.D1,
    *,
    input_flags: Iterable[DataFlag] | None = None,
    minimum_data_confidence: float = 0.50,
) -> RegimeSnapshot:
    macro, macro_coverage = _component(
        [
            _scaled(features, "ndx_return_20d", width=0.10),
            _scaled(features, "dxy_return_20d", width=0.05, multiplier=-1),
            _scaled(features, "us10y_change_20d", width=0.50, multiplier=-1),
            _scaled(features, "vix_z_20d", width=2.0, multiplier=-1),
        ]
    )
    crypto, crypto_coverage = _component(
        [
            _scaled(features, "btc_return_7d", width=0.15),
            _scaled(features, "btc_return_30d", width=0.30),
            _scaled(features, "eth_btc_return_7d", width=0.10),
            _scaled(features, "btc_dominance_change_20d", width=0.08, multiplier=-1),
        ]
    )
    xrp_relative, xrp_coverage = _component(
        [
            _scaled(features, "xrp_return_7d", width=0.20),
            _scaled(features, "xrp_return_30d", width=0.45),
            _scaled(features, "xrp_btc_return_7d", width=0.15),
            _scaled(features, "xrp_btc_return_30d", width=0.30),
            _scaled(features, "xrp_ma100_distance", width=0.40),
        ]
    )
    derivatives, derivatives_coverage = _derivatives_health(features)
    xrpl_value = _scaled(features, "xrpl_activity_z", width=2.0)
    xrpl, xrpl_coverage = _component([xrpl_value])
    data_quality, quality_coverage, quality_confidence = _quality(features)

    components = ComponentScores(
        macro=round(macro, 4),
        crypto=round(crypto, 4),
        xrp_relative=round(xrp_relative, 4),
        derivatives=round(derivatives, 4),
        xrpl=round(xrpl, 4),
        data_quality=round(data_quality, 4),
    )
    component_coverage = {
        "macro": macro_coverage,
        "crypto": crypto_coverage,
        "xrp_relative": xrp_coverage,
        "derivatives": derivatives_coverage,
        "xrpl": xrpl_coverage,
        "data_quality": quality_coverage,
    }

    base_weights = HORIZON_WEIGHTS[horizon]
    directional_scores = {
        "macro": macro,
        "crypto": crypto,
        "xrp_relative": xrp_relative,
        "derivatives": derivatives,
        "xrpl": xrpl,
    }
    effective_weights = {
        key: weight * component_coverage[key] for key, weight in base_weights.items()
    }
    total_effective_weight = sum(effective_weights.values())
    bull_score = (
        sum(effective_weights[key] * directional_scores[key] for key in directional_scores)
        / total_effective_weight
        if total_effective_weight > 0
        else 50.0
    )
    bull_score = _clip(bull_score)

    directional_coverage = sum(
        base_weights[key] * component_coverage[key] for key in base_weights
    )
    data_confidence = _clip01(min(quality_confidence, directional_coverage))

    active_component_scores = [
        directional_scores[key] for key in directional_scores if component_coverage[key] > 0
    ]
    alignment = (
        _clip01(1 - pstdev(active_component_scores) / 50)
        if len(active_component_scores) >= 2
        else 0.0
    )
    directional_conviction = _clip01(abs(bull_score - 50) / 50)
    model_confidence = _clip01(
        0.65 * directional_coverage + 0.20 * alignment + 0.15 * directional_conviction
    )
    confidence = math.sqrt(data_confidence * model_confidence)

    rsi = _feature(features, "xrp_rsi_14")
    ma20 = _feature(features, "xrp_ma20_distance")
    funding = _feature(features, "funding_z")
    oi_divergence = _feature(features, "oi_price_divergence")
    liquidation = _feature(features, "liquidation_impulse")
    volatility = _feature(features, "xrp_vol_30d")

    overextension, _ = _component(
        [
            None if rsi is None else _scale(rsi - 65, width=25),
            None if ma20 is None else _scale(ma20, width=0.30),
            None if funding is None else _scale(funding, width=2.0),
        ]
    )
    distribution_risk = _clip(
        0.55 * overextension
        + 0.45 * (50.0 if oi_divergence is None else _scale(oi_divergence, width=1.5))
    )
    squeeze_risk, _ = _component(
        [
            None if liquidation is None else _scale(liquidation, width=1.0),
            None if funding is None else _scale(abs(funding), width=2.0),
            None if volatility is None else _scale(volatility, width=1.5),
        ]
    )

    flags = list(dict.fromkeys(input_flags or []))
    block_reasons: list[str] = []
    if quality_coverage < 1.0:
        flags.append(DataFlag.MISSING)
        block_reasons.append("provider quality, freshness or source coverage is missing")
    if directional_coverage < 0.60:
        flags.append(DataFlag.MISSING)
        block_reasons.append("directional feature coverage is below 60%")
    if data_confidence < minimum_data_confidence:
        block_reasons.append(
            f"data confidence {data_confidence:.2f} is below {minimum_data_confidence:.2f}"
        )
    flags = list(dict.fromkeys(flags))
    output_blocked = bool(block_reasons)

    if output_blocked:
        regime = RegimeLabel.DEGRADED
    elif bull_score >= 72:
        regime = RegimeLabel.STRONG_BULL
    elif bull_score >= 58:
        regime = RegimeLabel.BULLISH
    elif bull_score >= 43:
        regime = RegimeLabel.NEUTRAL
    elif bull_score >= 28:
        regime = RegimeLabel.BEARISH
    else:
        regime = RegimeLabel.STRONG_BEAR

    driver_candidates = {
        "XRP/BTC relative strength": (xrp_relative, xrp_coverage),
        "Bitcoin and crypto breadth": (crypto, crypto_coverage),
        "macro/liquidity backdrop": (macro, macro_coverage),
        "derivatives structure": (derivatives, derivatives_coverage),
        "XRPL activity": (xrpl, xrpl_coverage),
    }
    ranked_drivers = sorted(
        (
            (name, score)
            for name, (score, coverage) in driver_candidates.items()
            if coverage > 0
        ),
        key=lambda item: abs(item[1] - 50),
        reverse=True,
    )
    key_drivers = [name for name, _ in ranked_drivers[:4]]

    invalidations = [
        "XRP/BTC relative strength reverses below its medium-term trend",
        "Bitcoin loses reclaimed daily structure with expanding spot volume",
        "provider agreement or freshness falls below the operational threshold",
    ]
    if distribution_risk > 70:
        invalidations.insert(0, "overextension converts into lower highs with rising open interest")

    feature_values = _canonical_feature_values(features)
    policy_payload = {
        "version": REGIME_POLICY_VERSION,
        "horizon": horizon.value,
        "weights": base_weights,
        "minimum_data_confidence": minimum_data_confidence,
        "minimum_directional_coverage": 0.60,
        "regime_thresholds": {
            "strong_bull": 72,
            "bullish": 58,
            "neutral": 43,
            "bearish": 28,
        },
    }

    return RegimeSnapshot(
        horizon=horizon,
        generated_at=datetime.now(UTC),
        regime=regime,
        policy_version=REGIME_POLICY_VERSION,
        policy_digest=_canonical_digest(policy_payload),
        bull_score=round(bull_score, 2),
        bear_score=round(100 - bull_score, 2),
        squeeze_risk=round(squeeze_risk, 2),
        distribution_risk=round(distribution_risk, 2),
        confidence=round(confidence, 4),
        data_confidence=round(data_confidence, 4),
        model_confidence=round(model_confidence, 4),
        directional_conviction=round(directional_conviction, 4),
        output_blocked=output_blocked,
        block_reasons=block_reasons,
        components=components,
        component_coverage={key: round(value, 4) for key, value in component_coverage.items()},
        key_drivers=key_drivers,
        invalidations=invalidations,
        data_flags=flags,
        historical_analogues=historical_analogues(features),
        feature_hash=_canonical_digest(feature_values),
        feature_values=feature_values,
    )
