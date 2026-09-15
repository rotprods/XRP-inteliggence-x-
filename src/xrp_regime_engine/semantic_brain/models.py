from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, Field, model_validator


class EpistemicStatus(StrEnum):
    FACT = "FACT"
    STRONG_EVIDENCE = "STRONG_EVIDENCE"
    PLAUSIBLE = "PLAUSIBLE"
    HYPOTHESIS = "HYPOTHESIS"
    CLAIM_ONLY = "CLAIM_ONLY"
    DISPUTED = "DISPUTED"
    REFUTED = "REFUTED"
    NO_DATA = "NO_DATA"


class SourceTier(StrEnum):
    T0_PRIMARY_MACHINE = "T0_PRIMARY_MACHINE"
    T1_PRIMARY_DOCUMENT = "T1_PRIMARY_DOCUMENT"
    T2_HIGH_QUALITY_SECONDARY = "T2_HIGH_QUALITY_SECONDARY"
    T3_SECONDARY = "T3_SECONDARY"
    T4_SOCIAL_CLAIM = "T4_SOCIAL_CLAIM"


class EntityType(StrEnum):
    PERSON = "Person"
    ORGANIZATION = "Organization"
    GOVERNMENT = "Government"
    REGULATOR = "Regulator"
    CENTRAL_BANK = "CentralBank"
    COMMERCIAL_BANK = "CommercialBank"
    NETWORK = "Network"
    PROTOCOL = "Protocol"
    ASSET = "Asset"
    STABLECOIN = "Stablecoin"
    CBDC = "CBDC"
    LEGISLATION = "Legislation"
    COURT_CASE = "CourtCase"
    EVENT = "Event"
    MARKET_INSTRUMENT = "MarketInstrument"
    COMMODITY = "Commodity"
    GEOGRAPHY = "Geography"
    CHOKEPOINT = "Chokepoint"
    TECHNOLOGY = "Technology"
    CLAIM = "Claim"
    PREDICTION = "Prediction"
    SOURCE = "Source"
    DOCUMENT = "Document"
    API_ENDPOINT = "APIEndpoint"
    DATASET = "Dataset"


class RelationType(StrEnum):
    FOUNDED = "FOUNDED"
    EMPLOYED_BY = "EMPLOYED_BY"
    INVESTED_IN = "INVESTED_IN"
    PARTNERED_WITH = "PARTNERED_WITH"
    REGULATES = "REGULATES"
    SUED = "SUED"
    SETTLED = "SETTLED"
    PILOTED_WITH = "PILOTED_WITH"
    USES_TECHNOLOGY = "USES_TECHNOLOGY"
    ISSUES = "ISSUES"
    SETTLES_WITH = "SETTLES_WITH"
    PROVIDES_LIQUIDITY = "PROVIDES_LIQUIDITY"
    COMPETES_WITH = "COMPETES_WITH"
    DEPENDS_ON = "DEPENDS_ON"
    SANCTIONED_BY = "SANCTIONED_BY"
    FUNDS = "FUNDS"
    LOBBIED = "LOBBIED"
    VOTED_ON = "VOTED_ON"
    CORRELATES_WITH = "CORRELATES_WITH"
    CLAIMS = "CLAIMS"
    CONTRADICTS = "CONTRADICTS"
    SUPPORTS = "SUPPORTS"
    PREDICTED = "PREDICTED"
    OCCURRED_AT = "OCCURRED_AT"
    AFFECTS_MARKET = "AFFECTS_MARKET"
    SOURCE_OF = "SOURCE_OF"


def utc_now() -> datetime:
    return datetime.now(UTC)


class TemporalEnvelope(BaseModel):
    event_at: datetime | None = None
    observed_at: datetime | None = None
    published_at: datetime | None = None
    available_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def availability_is_not_after_retrieval(self) -> TemporalEnvelope:
        if self.available_at and self.available_at > self.retrieved_at:
            raise ValueError("available_at cannot be later than retrieved_at")
        return self


class SourceRecord(BaseModel):
    source_id: str
    canonical_url: str
    provider: str
    tier: SourceTier
    source_type: str
    content_sha256: str | None = None
    temporal: TemporalEnvelope = Field(default_factory=TemporalEnvelope)
    quality_flags: set[str] = Field(default_factory=set)


class EntityRecord(BaseModel):
    entity_id: str
    entity_type: EntityType
    canonical_name: str
    aliases: set[str] = Field(default_factory=set)
    attributes: dict[str, Any] = Field(default_factory=dict)


class ClaimRecord(BaseModel):
    claim_id: str
    statement: str
    status: EpistemicStatus = EpistemicStatus.CLAIM_ONLY
    evidence_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_ids: set[str] = Field(default_factory=set)
    entity_ids: set[str] = Field(default_factory=set)
    contradicts: set[str] = Field(default_factory=set)
    supports: set[str] = Field(default_factory=set)
    temporal: TemporalEnvelope = Field(default_factory=TemporalEnvelope)
    quality_flags: set[str] = Field(default_factory=set)

    @classmethod
    def from_statement(cls, statement: str, **kwargs: Any) -> ClaimRecord:
        normalized = " ".join(statement.casefold().split())
        digest = sha256(normalized.encode()).hexdigest()
        return cls(claim_id=f"claim:sha256:{digest}", statement=statement, **kwargs)


class EdgeRecord(BaseModel):
    edge_id: str
    subject_id: str
    relation: RelationType
    object_id: str
    source_ids: set[str]
    evidence_status: EpistemicStatus
    confidence: float = Field(ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    observed_at: datetime | None = None
    available_at: datetime | None = None
    mechanism: str | None = None
    causal_grade: str | None = None


class GraphDocument(BaseModel):
    document_id: str
    source: SourceRecord
    title: str | None = None
    text: str
    entities: list[EntityRecord] = Field(default_factory=list)
    claims: list[ClaimRecord] = Field(default_factory=list)
    edges: list[EdgeRecord] = Field(default_factory=list)
