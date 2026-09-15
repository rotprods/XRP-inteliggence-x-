from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class PredictionResolution(StrEnum):
    OPEN = "OPEN"
    HIT = "HIT"
    MISS = "MISS"
    AMBIGUOUS = "AMBIGUOUS"
    NON_FALSIFIABLE = "NON_FALSIFIABLE"


class FrozenPrediction(BaseModel):
    prediction_id: str
    source_id: str
    original_text: str
    published_at: datetime
    frozen_at: datetime
    target: str
    horizon_end: datetime
    success_rule: str
    failure_rule: str
    interpretation_version: str = "v1"
    resolution: PredictionResolution = PredictionResolution.OPEN
    resolved_at: datetime | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    quality_flags: set[str] = Field(default_factory=set)

    @model_validator(mode="after")
    def enforce_ex_ante_freeze(self) -> "FrozenPrediction":
        if self.frozen_at < self.published_at:
            raise ValueError("frozen_at cannot precede publication")
        if self.frozen_at >= self.horizon_end:
            raise ValueError("interpretation must be frozen before outcome horizon")
        return self

    def resolve(self, outcome: PredictionResolution, at: datetime, evidence_ids: list[str]) -> "FrozenPrediction":
        if outcome == PredictionResolution.OPEN:
            raise ValueError("resolution must close the prediction")
        if at < self.horizon_end and outcome in {PredictionResolution.HIT, PredictionResolution.MISS}:
            raise ValueError("cannot score HIT/MISS before horizon expiry")
        self.resolution = outcome
        self.resolved_at = at
        self.evidence_ids = list(evidence_ids)
        return self
