from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from xrp_regime_engine.derivatives import DerivativesRiskState
from xrp_regime_engine.microstructure import MicrostructureState


class MarketStateLabel(StrEnum):
    SPOT_LED_BREAKOUT = "SPOT_LED_BREAKOUT"
    LEVERAGED_BREAKOUT = "LEVERAGED_BREAKOUT"
    ABSORPTION = "ABSORPTION"
    DISTRIBUTION = "DISTRIBUTION"
    LONG_CROWDING = "LONG_CROWDING"
    BALANCED = "BALANCED"
    NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class MarketState:
    symbol: str
    observed_at: datetime
    label: MarketStateLabel
    confidence: float
    reasons: tuple[str, ...]
    execution_weight: float = 0.0


def classify_market_state(
    micro: MicrostructureState | None,
    derivatives: DerivativesRiskState | None,
) -> MarketState:
    """Classify observable state without producing a trade instruction.

    V1 intentionally fails closed. It does not infer a breakout from a single
    REST depth snapshot and never grants execution authority.
    """
    if micro is None:
        now = derivatives.observed_at if derivatives else datetime.min
        symbol = derivatives.symbol if derivatives else "UNKNOWN"
        return MarketState(
            symbol=symbol,
            observed_at=now,
            label=MarketStateLabel.NO_DATA,
            confidence=0.0,
            reasons=("MICROSTRUCTURE_NO_DATA",),
        )

    reasons: list[str] = []
    label = MarketStateLabel.BALANCED
    confidence = 0.45

    if micro.imbalance_25bps >= 0.35 and micro.microprice > micro.mid_price:
        label = MarketStateLabel.ABSORPTION
        confidence = 0.62
        reasons.extend(("BID_IMBALANCE_25BPS", "MICROPRICE_ABOVE_MID"))
    elif micro.imbalance_25bps <= -0.35 and micro.microprice < micro.mid_price:
        label = MarketStateLabel.DISTRIBUTION
        confidence = 0.62
        reasons.extend(("ASK_IMBALANCE_25BPS", "MICROPRICE_BELOW_MID"))

    if derivatives is not None:
        flags = set(derivatives.quality_flags)
        if "ELEVATED_POSITIVE_FUNDING" in flags:
            reasons.append("ELEVATED_POSITIVE_FUNDING")
            if label == MarketStateLabel.ABSORPTION:
                label = MarketStateLabel.LONG_CROWDING
                confidence = 0.58
        if "WIDE_MARK_INDEX_BASIS" in flags:
            reasons.append("WIDE_MARK_INDEX_BASIS")
            confidence = min(confidence, 0.50)

    if not reasons:
        reasons.append("NO_STRONG_MICROSTRUCTURE_EDGE")

    return MarketState(
        symbol=micro.symbol,
        observed_at=micro.observed_at,
        label=label,
        confidence=confidence,
        reasons=tuple(reasons),
        execution_weight=0.0,
    )
