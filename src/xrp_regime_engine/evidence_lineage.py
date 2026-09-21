from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from xrp_regime_engine.semantic_brain.models import (
    ClaimRecord,
    EntityRecord,
    EntityType,
    EpistemicStatus,
    GraphDocument,
    SourceRecord,
    SourceTier,
    TemporalEnvelope,
)
from xrp_regime_engine.shadow_evidence import ShadowEvidenceVector

LINEAGE_SCHEMA_VERSION = 2


class EvidenceSourceRole(StrEnum):
    INDEPENDENT_PRICE = "independent_price"
    DEPTH = "depth"
    AGG_TRADE = "agg_trade"
    OPEN_INTEREST = "open_interest"
    FUNDING = "funding"
    BASIS = "basis"


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class EvidenceSourceDigest:
    source_id: str
    provider: str
    role: EvidenceSourceRole
    content_sha256: str
    observed_at: datetime
    available_at: datetime
    fetched_at: datetime

    def __post_init__(self) -> None:
        if not self.source_id or not self.provider:
            raise ValueError("source_id and provider are required")
        if not isinstance(self.role, EvidenceSourceRole):
            raise ValueError("role must be an EvidenceSourceRole")
        if len(self.content_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.content_sha256
        ):
            raise ValueError("content_sha256 must be a lowercase SHA-256 hex digest")
        for field, value in (
            ("observed_at", self.observed_at),
            ("available_at", self.available_at),
            ("fetched_at", self.fetched_at),
        ):
            _require_aware(value, field)
        if not self.observed_at <= self.available_at <= self.fetched_at:
            raise ValueError("source timestamps must satisfy observed <= available <= fetched")

    def canonical_payload(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "provider": self.provider,
            "role": self.role.value,
            "content_sha256": self.content_sha256,
            "observed_at": self.observed_at.isoformat(),
            "available_at": self.available_at.isoformat(),
            "fetched_at": self.fetched_at.isoformat(),
        }


@dataclass(frozen=True)
class ShadowEvidenceLineage:
    evidence_id: str
    vector_sha256: str
    lineage_sha256: str
    vector: ShadowEvidenceVector
    sources: tuple[EvidenceSourceDigest, ...]

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(source.source_id for source in self.sources)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "schema_version": LINEAGE_SCHEMA_VERSION,
            "evidence_id": self.evidence_id,
            "vector_sha256": self.vector_sha256,
            "lineage_sha256": self.lineage_sha256,
            "vector": _vector_payload(self.vector),
            "sources": [source.canonical_payload() for source in self.sources],
        }

    def to_json(self) -> str:
        return _canonical_json(self.canonical_payload())


def _vector_payload(vector: ShadowEvidenceVector) -> dict[str, object]:
    payload = asdict(vector)
    payload["prediction_time"] = vector.prediction_time.isoformat()
    payload["independent_providers"] = sorted(set(vector.independent_providers))
    payload["quality_flags"] = sorted(set(vector.quality_flags))
    return payload


def _required_roles(vector: ShadowEvidenceVector) -> set[EvidenceSourceRole]:
    roles = {
        EvidenceSourceRole.INDEPENDENT_PRICE,
        EvidenceSourceRole.DEPTH,
        EvidenceSourceRole.AGG_TRADE,
    }
    if vector.open_interest_delta_pct is not None:
        roles.add(EvidenceSourceRole.OPEN_INTEREST)
    if vector.funding_delta_bps is not None:
        roles.add(EvidenceSourceRole.FUNDING)
    if vector.basis_delta_bps is not None:
        roles.add(EvidenceSourceRole.BASIS)
    return roles


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if not normalized:
        raise ValueError("provider names must be non-empty")
    return normalized


def _validate_source_coverage(
    vector: ShadowEvidenceVector,
    sources: tuple[EvidenceSourceDigest, ...],
) -> None:
    roles = {source.role for source in sources}
    missing_roles = _required_roles(vector) - roles
    if missing_roles:
        missing = ", ".join(sorted(role.value for role in missing_roles))
        raise ValueError(f"required evidence source roles are missing: {missing}")

    vector_providers = {
        _normalize_provider(provider) for provider in vector.independent_providers
    }
    if (
        len(vector_providers) != vector.independent_provider_count
        or vector.independent_provider_count < 2
        or vector.independent_external_provider_count < 1
    ):
        raise ValueError("independent consensus provider counts are inconsistent")

    source_providers = {
        _normalize_provider(source.provider)
        for source in sources
        if source.role == EvidenceSourceRole.INDEPENDENT_PRICE
    }
    if source_providers != vector_providers:
        raise ValueError(
            "independent price source providers must exactly match vector consensus providers"
        )


def build_shadow_evidence_lineage(
    vector: ShadowEvidenceVector,
    sources: tuple[EvidenceSourceDigest, ...],
) -> ShadowEvidenceLineage:
    _require_aware(vector.prediction_time, "prediction_time")
    if (
        vector.calibrated
        or vector.probability is not None
        or vector.decision_authority
        or vector.execution_weight != 0.0
    ):
        raise ValueError("shadow evidence lineage accepts non-directional evidence only")
    if not sources:
        raise ValueError("at least one source digest is required")

    ordered_sources = tuple(sorted(sources, key=lambda source: source.source_id))
    source_ids = [source.source_id for source in ordered_sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("source_id values must be unique")
    if any(source.fetched_at > vector.prediction_time for source in ordered_sources):
        raise ValueError("source fetched_at cannot be later than prediction_time")
    _validate_source_coverage(vector, ordered_sources)

    vector_json = _canonical_json(_vector_payload(vector))
    vector_sha256 = sha256(vector_json.encode()).hexdigest()
    lineage_material = {
        "schema_version": LINEAGE_SCHEMA_VERSION,
        "vector_sha256": vector_sha256,
        "sources": [source.canonical_payload() for source in ordered_sources],
    }
    lineage_sha256 = sha256(_canonical_json(lineage_material).encode()).hexdigest()
    evidence_id = f"shadow-evidence:sha256:{lineage_sha256}"
    return ShadowEvidenceLineage(
        evidence_id=evidence_id,
        vector_sha256=vector_sha256,
        lineage_sha256=lineage_sha256,
        vector=vector,
        sources=ordered_sources,
    )


def shadow_evidence_graph_document(lineage: ShadowEvidenceLineage) -> GraphDocument:
    prediction_time = lineage.vector.prediction_time
    artifact_source_id = f"source:{lineage.evidence_id}"
    statement = (
        f"{lineage.evidence_id} records an uncalibrated observational shadow-evidence "
        f"artifact for {lineage.vector.symbol} at {prediction_time.isoformat()}."
    )
    temporal = TemporalEnvelope(
        event_at=prediction_time,
        observed_at=prediction_time,
        published_at=prediction_time,
        available_at=prediction_time,
        retrieved_at=prediction_time,
    )
    source = SourceRecord(
        source_id=artifact_source_id,
        canonical_url=f"urn:{lineage.evidence_id}",
        provider="xrp-regime-engine",
        tier=SourceTier.T0_PRIMARY_MACHINE,
        source_type="shadow_evidence_vector",
        content_sha256=lineage.lineage_sha256,
        temporal=temporal,
        quality_flags={
            "UNCALIBRATED_SHADOW_ONLY",
            "NON_DIRECTIONAL_RESEARCH_ONLY",
            "PROVENANCE_SCOPE_COMPLETE",
        },
    )
    entity = EntityRecord(
        entity_id=f"dataset:{lineage.evidence_id}",
        entity_type=EntityType.DATASET,
        canonical_name=lineage.evidence_id,
        attributes={
            "symbol": lineage.vector.symbol,
            "prediction_time": prediction_time.isoformat(),
            "lineage_sha256": lineage.lineage_sha256,
            "source_digests": {
                source.source_id: source.content_sha256 for source in lineage.sources
            },
            "source_roles": {
                source.source_id: source.role.value for source in lineage.sources
            },
            "execution_weight": 0.0,
        },
    )
    claim = ClaimRecord.from_statement(
        statement,
        status=EpistemicStatus.FACT,
        evidence_confidence=1.0,
        source_ids={artifact_source_id, *lineage.source_ids},
        entity_ids={entity.entity_id},
        temporal=temporal,
        quality_flags={
            "UNCALIBRATED_SHADOW_ONLY",
            "NON_DIRECTIONAL_RESEARCH_ONLY",
            "EXECUTION_WEIGHT_ZERO",
            "PROVENANCE_SCOPE_COMPLETE",
        },
    )
    return GraphDocument(
        document_id=f"document:{lineage.evidence_id}",
        source=source,
        text=statement,
        entities=[entity],
        claims=[claim],
    )
