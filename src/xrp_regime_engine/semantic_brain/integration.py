from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from .models import EpistemicStatus


class SemanticEvidence(BaseModel):
    claim_id: str
    statement: str
    status: EpistemicStatus
    evidence_confidence: float = Field(ge=0.0, le=1.0)
    available_at: datetime | None
    source_ids: list[str]
    quality_flags: list[str] = Field(default_factory=list)


class RegimeSemanticContext(BaseModel):
    decision_at: datetime
    evidence: list[SemanticEvidence]
    narrative_execution_weight: float = 0.0
    semantic_directional_weight: float = 0.0


def build_regime_context(records: list[dict[str, Any]], decision_at: datetime) -> RegimeSemanticContext:
    if decision_at.tzinfo is None:
        decision_at = decision_at.replace(tzinfo=timezone.utc)
    evidence: list[SemanticEvidence] = []
    for raw in records:
        item = SemanticEvidence.model_validate(raw)
        if item.available_at is None or item.available_at > decision_at:
            continue
        if item.status in {EpistemicStatus.CLAIM_ONLY, EpistemicStatus.DISPUTED, EpistemicStatus.REFUTED, EpistemicStatus.NO_DATA}:
            item.quality_flags.append("NON_DIRECTIONAL_RESEARCH_ONLY")
        evidence.append(item)
    return RegimeSemanticContext(decision_at=decision_at, evidence=evidence)
