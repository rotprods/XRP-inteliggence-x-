from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from xrp_regime_engine.derivatives import DerivativesRiskState
from xrp_regime_engine.microstructure import MicrostructureState
from xrp_regime_engine.order_flow import OrderFlowState


class FlowRegimeLabel(StrEnum):
    SPOT_LED_DEMAND = "SPOT_LED_DEMAND"
    LEVERAGED_DEMAND = "LEVERAGED_DEMAND"
    BID_ABSORPTION = "BID_ABSORPTION"
    SELL_PRESSURE = "SELL_PRESSURE"
    LONG_CROWDING = "LONG_CROWDING"
    MIXED = "MIXED"
    NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class FlowRegime:
    symbol: str
    observed_at: datetime
    label: FlowRegimeLabel
    confidence: float
    reasons: tuple[str, ...]
    execution_weight: float = 0.0


def classify_flow_regime(
    micro: MicrostructureState | None,
    flow: OrderFlowState | None,
    derivatives: DerivativesRiskState | None,
) -> FlowRegime:
    if micro is None or flow is None:
        observed = (
            micro.observed_at if micro is not None
            else flow.observed_at if flow is not None
            else derivatives.observed_at if derivatives is not None
            else datetime.min
        )
        symbol = (
            micro.symbol if micro is not None
            else flow.symbol if flow is not None
            else derivatives.symbol if derivatives is not None
            else "UNKNOWN"
        )
        return FlowRegime(
            symbol=symbol,
            observed_at=observed,
            label=FlowRegimeLabel.NO_DATA,
            confidence=0.0,
            reasons=("DEPTH_OR_TRADE_FLOW_NO_DATA",),
        )

    reasons: list[str] = []
    label = FlowRegimeLabel.MIXED
    confidence = 0.45

    bid_support = micro.imbalance_25bps >= 0.25
    ask_pressure = micro.imbalance_25bps <= -0.25
    aggressive_buying = flow.taker_imbalance >= 0.20
    aggressive_selling = flow.taker_imbalance <= -0.20

    if bid_support and aggressive_buying:
        label = FlowRegimeLabel.SPOT_LED_DEMAND
        confidence = 0.72
        reasons.extend(("BID_DEPTH_SUPPORT", "POSITIVE_CVD"))
    elif bid_support and aggressive_selling:
        label = FlowRegimeLabel.BID_ABSORPTION
        confidence = 0.68
        reasons.extend(("BID_DEPTH_SUPPORT", "SELLS_ABSORBED"))
    elif ask_pressure and aggressive_selling:
        label = FlowRegimeLabel.SELL_PRESSURE
        confidence = 0.72
        reasons.extend(("ASK_DEPTH_PRESSURE", "NEGATIVE_CVD"))

    if derivatives is not None:
        flags = set(derivatives.quality_flags)
        positive_funding = "ELEVATED_POSITIVE_FUNDING" in flags
        wide_basis = "WIDE_MARK_INDEX_BASIS" in flags
        if positive_funding:
            reasons.append("ELEVATED_POSITIVE_FUNDING")
            if label == FlowRegimeLabel.SPOT_LED_DEMAND:
                label = FlowRegimeLabel.LEVERAGED_DEMAND
                confidence = 0.60
            elif label == FlowRegimeLabel.BID_ABSORPTION:
                label = FlowRegimeLabel.LONG_CROWDING
                confidence = 0.55
        if wide_basis:
            reasons.append("WIDE_MARK_INDEX_BASIS")
            confidence = min(confidence, 0.50)

    if not reasons:
        reasons.append("NO_CONFLUENT_FLOW_EDGE")

    return FlowRegime(
        symbol=micro.symbol,
        observed_at=max(micro.observed_at, flow.observed_at),
        label=label,
        confidence=confidence,
        reasons=tuple(reasons),
        execution_weight=0.0,
    )
