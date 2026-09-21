from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .models import EpistemicStatus


@dataclass(frozen=True)
class SemanticEvidence:
    claim_id: str
    statement: str
    status: EpistemicStatus
    evidence_confidence: float
    source_ids: tuple[str, ...]
    quality_flags: tuple[str, ...]


@dataclass(frozen=True)
class RegimeSemanticContext:
    decision_at: datetime
    evidence: tuple[SemanticEvidence, ...]
    narrative_execution_weight: float = 0.0


def build_regime_context(
    records: list[dict[str, Any]], decision_at: datetime
) -> RegimeSemanticContext:
    if decision_at.tzinfo is None:
        decision_at = decision_at.replace(tzinfo=UTC)
    evidence: list[SemanticEvidence] = []
    for raw in records:
        available_at = raw.get("available_at")
        if isinstance(available_at, datetime) and available_at > decision_at:
            continue
        status = EpistemicStatus(raw.get("status", EpistemicStatus.NO_DATA))
        flags = set(raw.get("quality_flags", []))
        if status in {
            EpistemicStatus.CLAIM_ONLY,
            EpistemicStatus.DISPUTED,
            EpistemicStatus.REFUTED,
            EpistemicStatus.NO_DATA,
        }:
            flags.add("NON_DIRECTIONAL_RESEARCH_ONLY")
        evidence.append(
            SemanticEvidence(
                claim_id=str(raw["claim_id"]),
                statement=str(raw["statement"]),
                status=status,
                evidence_confidence=float(raw.get("evidence_confidence", 0.0)),
                source_ids=tuple(sorted(str(item) for item in raw.get("source_ids", []))),
                quality_flags=tuple(sorted(flags)),
            )
        )
    return RegimeSemanticContext(decision_at=decision_at, evidence=tuple(evidence))
