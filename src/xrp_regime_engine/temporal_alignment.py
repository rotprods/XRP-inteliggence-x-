from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from xrp_regime_engine.depth_dynamics import DepthDynamics
from xrp_regime_engine.derivatives import FundingState, OpenInterestState
from xrp_regime_engine.order_flow import OrderFlowState
from xrp_regime_engine.stream_alignment import (
    CrossStreamAlignment,
    CrossStreamFreshnessPolicy,
    assess_cross_stream_alignment,
)
from xrp_regime_engine.temporal_flow import (
    TemporalFlowSample,
    TemporalFlowWindow,
    build_temporal_window,
)


@dataclass(frozen=True)
class AlignedTemporalWindow:
    alignment: CrossStreamAlignment
    window: TemporalFlowWindow | None
    evidence_eligible: bool
    quality_flags: tuple[str, ...]
    execution_weight: float = 0.0


def build_aligned_temporal_window(
    *,
    samples: tuple[TemporalFlowSample, ...],
    depth: DepthDynamics | None,
    order_flow: OrderFlowState | None,
    funding: FundingState | None,
    open_interest: OpenInterestState | None,
    prediction_time: datetime,
    window_seconds: int,
    policy: CrossStreamFreshnessPolicy | None = None,
) -> AlignedTemporalWindow:
    """Build a temporal window only after cross-stream eligibility passes.

    This is an evidence-eligibility gate, not a regime classifier or trading signal.
    A blocked alignment never exposes a temporal window to downstream consumers.
    """
    alignment = assess_cross_stream_alignment(
        depth=depth,
        order_flow=order_flow,
        funding=funding,
        open_interest=open_interest,
        prediction_time=prediction_time,
        policy=policy,
    )
    if not alignment.evidence_eligible:
        return AlignedTemporalWindow(
            alignment=alignment,
            window=None,
            evidence_eligible=False,
            quality_flags=alignment.quality_flags,
            execution_weight=0.0,
        )

    window = build_temporal_window(
        samples,
        prediction_time=prediction_time,
        window_seconds=window_seconds,
    )
    if window is None:
        flags = tuple(dict.fromkeys((*alignment.quality_flags, "TEMPORAL_WINDOW_NO_DATA")))
        return AlignedTemporalWindow(
            alignment=alignment,
            window=None,
            evidence_eligible=False,
            quality_flags=flags,
            execution_weight=0.0,
        )

    if alignment.symbol != "UNKNOWN" and window.symbol != alignment.symbol:
        raise ValueError("temporal window symbol must match aligned streams")

    flags = tuple(dict.fromkeys((*alignment.quality_flags, *window.quality_flags)))
    temporal_blocked = not window.regime_eligible or "SPARSE_WINDOW" in window.quality_flags
    if temporal_blocked:
        blocked_flags = tuple(dict.fromkeys((*flags, "TEMPORAL_WINDOW_INELIGIBLE")))
        return AlignedTemporalWindow(
            alignment=alignment,
            window=None,
            evidence_eligible=False,
            quality_flags=blocked_flags,
            execution_weight=0.0,
        )

    return AlignedTemporalWindow(
        alignment=alignment,
        window=window,
        evidence_eligible=True,
        quality_flags=flags,
        execution_weight=0.0,
    )
