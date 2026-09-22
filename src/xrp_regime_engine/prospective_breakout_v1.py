from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Literal


class LiveBreakoutState(StrEnum):
    BREAKOUT_UNCONFIRMED = "BREAKOUT_UNCONFIRMED"
    SPOT_CONFIRMED_BREAKOUT = "SPOT_CONFIRMED_BREAKOUT"
    LEVERAGED_BREAKOUT = "LEVERAGED_BREAKOUT"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
    NO_DATA = "NO_DATA"


EvidenceTruth = bool | None


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _nonempty(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _positive(value: float, field: str) -> float:
    candidate = float(value)
    if candidate <= 0:
        raise ValueError(f"{field} must be positive")
    return candidate


def _sha256(value: str, field: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return normalized


@dataclass(frozen=True, slots=True)
class BreakoutEvidenceFrame:
    observed_at: datetime
    pair: str
    reference_price: float
    breakout_level: float
    target_barrier: float
    independent_price_consensus_valid: EvidenceTruth
    breakout_level_accepted: EvidenceTruth
    spot_flow_confirmed: EvidenceTruth
    relative_strength_confirmed: EvidenceTruth
    leverage_expansion: EvidenceTruth
    funding_dangerous: EvidenceTruth
    failed_breakout: EvidenceTruth
    screenshot_sha256: tuple[str, ...] = ()
    source_note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "pair", _nonempty(self.pair, "pair"))
        object.__setattr__(
            self,
            "reference_price",
            _positive(self.reference_price, "reference_price"),
        )
        object.__setattr__(
            self,
            "breakout_level",
            _positive(self.breakout_level, "breakout_level"),
        )
        object.__setattr__(
            self,
            "target_barrier",
            _positive(self.target_barrier, "target_barrier"),
        )
        if self.target_barrier <= self.breakout_level:
            raise ValueError("target_barrier must be above breakout_level")
        normalized_hashes = tuple(
            sorted({_sha256(item, "screenshot_sha256") for item in self.screenshot_sha256})
        )
        object.__setattr__(self, "screenshot_sha256", normalized_hashes)

    @property
    def missing_signals(self) -> tuple[str, ...]:
        fields = (
            "independent_price_consensus_valid",
            "breakout_level_accepted",
            "spot_flow_confirmed",
            "relative_strength_confirmed",
            "leverage_expansion",
            "funding_dangerous",
            "failed_breakout",
        )
        return tuple(
            field
            for field in fields
            if getattr(self, field) is None
        )


@dataclass(frozen=True, slots=True)
class ProspectiveBreakoutAssessment:
    assessment_id: str
    assessment_sha256: str
    experiment_id: str
    observed_at: datetime
    pair: str
    reference_price: float
    breakout_level: float
    target_barrier: float
    state: LiveBreakoutState
    support: tuple[str, ...]
    contradictions: tuple[str, ...]
    missing_signals: tuple[str, ...]
    research_signal_ready: bool
    shadow_long_candidate: bool
    probability_calibrated: Literal[False] = False
    production_ready: Literal[False] = False
    decision_authority: Literal[False] = False
    execution_weight: float = 0.0


def evaluate_breakout_frame(
    frame: BreakoutEvidenceFrame,
    *,
    experiment_id: str,
) -> ProspectiveBreakoutAssessment:
    experiment = _nonempty(experiment_id, "experiment_id")
    support: list[str] = []
    contradictions: list[str] = []
    missing = frame.missing_signals

    if frame.failed_breakout is True:
        state = LiveBreakoutState.FAILED_BREAKOUT
        contradictions.append("FAILED_BREAKOUT_CONFIRMED")
    elif frame.independent_price_consensus_valid is False:
        state = LiveBreakoutState.NO_DATA
        contradictions.append("INDEPENDENT_PRICE_CONSENSUS_INVALID")
    elif frame.independent_price_consensus_valid is None:
        state = LiveBreakoutState.NO_DATA
        contradictions.append("INDEPENDENT_PRICE_CONSENSUS_MISSING")
    elif frame.breakout_level_accepted is False:
        state = LiveBreakoutState.BREAKOUT_UNCONFIRMED
        contradictions.append("BREAKOUT_LEVEL_NOT_ACCEPTED")
    elif frame.breakout_level_accepted is None:
        state = LiveBreakoutState.BREAKOUT_UNCONFIRMED
        contradictions.append("BREAKOUT_ACCEPTANCE_UNKNOWN")
    elif frame.spot_flow_confirmed is not True:
        state = LiveBreakoutState.BREAKOUT_UNCONFIRMED
        contradictions.append("SPOT_FLOW_NOT_CONFIRMED")
    elif frame.relative_strength_confirmed is not True:
        state = LiveBreakoutState.BREAKOUT_UNCONFIRMED
        contradictions.append("RELATIVE_STRENGTH_NOT_CONFIRMED")
    else:
        support.extend(
            (
                "BREAKOUT_LEVEL_ACCEPTED",
                "SPOT_FLOW_CONFIRMED",
                "RELATIVE_STRENGTH_CONFIRMED",
            )
        )
        if frame.leverage_expansion is True:
            state = LiveBreakoutState.LEVERAGED_BREAKOUT
            support.append("LEVERAGE_EXPANSION_PRESENT")
            if frame.funding_dangerous is True:
                contradictions.append("FUNDING_DANGEROUS")
        elif frame.leverage_expansion is False:
            state = LiveBreakoutState.SPOT_CONFIRMED_BREAKOUT
            support.append("NO_LEVERAGE_EXPANSION")
        else:
            state = LiveBreakoutState.BREAKOUT_UNCONFIRMED
            contradictions.append("LEVERAGE_STATE_UNKNOWN")

    research_ready = state in {
        LiveBreakoutState.SPOT_CONFIRMED_BREAKOUT,
        LiveBreakoutState.LEVERAGED_BREAKOUT,
        LiveBreakoutState.FAILED_BREAKOUT,
    }
    shadow_long_candidate = (
        state is LiveBreakoutState.SPOT_CONFIRMED_BREAKOUT
        and frame.funding_dangerous is not True
    )

    payload = {
        "experiment_id": experiment,
        "observed_at": frame.observed_at.isoformat(),
        "pair": frame.pair,
        "reference_price": frame.reference_price,
        "breakout_level": frame.breakout_level,
        "target_barrier": frame.target_barrier,
        "state": state.value,
        "support": sorted(support),
        "contradictions": sorted(contradictions),
        "missing_signals": list(missing),
        "research_signal_ready": research_ready,
        "shadow_long_candidate": shadow_long_candidate,
        "screenshot_sha256": list(frame.screenshot_sha256),
        "source_note": frame.source_note,
        "probability_calibrated": False,
        "production_ready": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(payload).encode()).hexdigest()
    return ProspectiveBreakoutAssessment(
        assessment_id=f"prospective-breakout:sha256:{digest}",
        assessment_sha256=digest,
        experiment_id=experiment,
        observed_at=frame.observed_at,
        pair=frame.pair,
        reference_price=frame.reference_price,
        breakout_level=frame.breakout_level,
        target_barrier=frame.target_barrier,
        state=state,
        support=tuple(sorted(support)),
        contradictions=tuple(sorted(contradictions)),
        missing_signals=missing,
        research_signal_ready=research_ready,
        shadow_long_candidate=shadow_long_candidate,
    )
