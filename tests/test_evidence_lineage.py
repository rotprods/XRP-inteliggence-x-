from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from xrp_regime_engine.evidence_lineage import (
    EvidenceSourceDigest,
    EvidenceSourceRole,
    build_shadow_evidence_lineage,
    shadow_evidence_graph_document,
)
from xrp_regime_engine.semantic_brain.graphify import GraphifyCompiler
from xrp_regime_engine.semantic_brain.models import EpistemicStatus, SourceTier
from xrp_regime_engine.shadow_evidence import ShadowEvidenceVector
from xrp_regime_engine.storage import SQLiteStore

PREDICTION_TIME = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)


def vector(**overrides: object) -> ShadowEvidenceVector:
    values: dict[str, object] = {
        "symbol": "XRPUSDT",
        "prediction_time": PREDICTION_TIME,
        "window_seconds": 900,
        "independent_price": 1.42,
        "independent_provider_count": 3,
        "independent_external_provider_count": 2,
        "independent_providers": ("coinbase", "kraken", "binance"),
        "consensus_agreement_score": 0.98,
        "consensus_freshness_score": 0.97,
        "mid_return_bps": 12.0,
        "mean_depth_imbalance_25bps": 0.22,
        "cvd_quote": 250_000.0,
        "taker_imbalance": 0.18,
        "open_interest_delta_pct": 0.7,
        "funding_delta_bps": 0.15,
        "basis_delta_bps": 1.2,
        "depth_trade_coverage_ratio": 0.74,
        "removal_candidate_residual_notional": 12_500.0,
        "quality_flags": ("INDEPENDENT_PRICE_CONSENSUS", "UNCALIBRATED_SHADOW_ONLY"),
    }
    values.update(overrides)
    return ShadowEvidenceVector(**values)  # type: ignore[arg-type]


def source(
    source_id: str,
    provider: str,
    digest_character: str,
    *,
    role: EvidenceSourceRole = EvidenceSourceRole.INDEPENDENT_PRICE,
    fetched_at: datetime = PREDICTION_TIME,
) -> EvidenceSourceDigest:
    return EvidenceSourceDigest(
        source_id=source_id,
        provider=provider,
        role=role,
        content_sha256=digest_character * 64,
        observed_at=PREDICTION_TIME - timedelta(seconds=2),
        available_at=PREDICTION_TIME - timedelta(seconds=1),
        fetched_at=fetched_at,
    )


def complete_sources() -> tuple[EvidenceSourceDigest, ...]:
    return (
        source("source:coinbase:xrp", "coinbase", "a"),
        source("source:kraken:xrp", "kraken", "b"),
        source("source:binance:price", "binance", "c"),
        source(
            "source:binance:depth",
            "binance",
            "d",
            role=EvidenceSourceRole.DEPTH,
        ),
        source(
            "source:binance:aggtrade",
            "binance",
            "e",
            role=EvidenceSourceRole.AGG_TRADE,
        ),
        source(
            "source:binance:oi",
            "binance",
            "f",
            role=EvidenceSourceRole.OPEN_INTEREST,
        ),
        source(
            "source:binance:funding",
            "binance",
            "0",
            role=EvidenceSourceRole.FUNDING,
        ),
        source(
            "source:binance:basis",
            "binance",
            "1",
            role=EvidenceSourceRole.BASIS,
        ),
    )


def test_lineage_is_deterministic_and_source_order_independent() -> None:
    sources = complete_sources()
    first = build_shadow_evidence_lineage(vector(), sources)
    second = build_shadow_evidence_lineage(
        replace(
            vector(),
            independent_providers=("binance", "kraken", "coinbase"),
            quality_flags=("UNCALIBRATED_SHADOW_ONLY", "INDEPENDENT_PRICE_CONSENSUS"),
        ),
        tuple(reversed(sources)),
    )
    assert first.evidence_id == second.evidence_id
    assert first.vector_sha256 == second.vector_sha256
    assert first.lineage_sha256 == second.lineage_sha256
    assert first.source_ids == tuple(sorted(item.source_id for item in sources))
    payload = json.loads(first.to_json())
    assert payload["schema_version"] == 2
    assert payload["vector"]["execution_weight"] == 0.0
    assert payload["vector"]["decision_authority"] is False
    assert payload["vector"]["calibrated"] is False
    assert payload["vector"]["probability"] is None
    assert {item["role"] for item in payload["sources"]} == {
        role.value for role in EvidenceSourceRole
    }


def test_lineage_rejects_directional_or_incomplete_inputs() -> None:
    sources = complete_sources()
    with pytest.raises(ValueError, match="non-directional"):
        build_shadow_evidence_lineage(replace(vector(), execution_weight=1.0), sources)
    with pytest.raises(ValueError, match="at least one"):
        build_shadow_evidence_lineage(vector(), ())

    duplicate = replace(sources[1], source_id=sources[0].source_id)
    with pytest.raises(ValueError, match="unique"):
        build_shadow_evidence_lineage(vector(), (sources[0], duplicate, *sources[2:]))

    future = replace(
        sources[0],
        fetched_at=PREDICTION_TIME + timedelta(microseconds=1),
    )
    with pytest.raises(ValueError, match="prediction_time"):
        build_shadow_evidence_lineage(vector(), (future, *sources[1:]))

    with pytest.raises(ValueError, match="timezone-aware"):
        build_shadow_evidence_lineage(
            vector(prediction_time=PREDICTION_TIME.replace(tzinfo=None)),
            sources,
        )


def test_lineage_requires_complete_role_and_provider_coverage() -> None:
    sources = complete_sources()

    without_depth = tuple(
        item for item in sources if item.role != EvidenceSourceRole.DEPTH
    )
    with pytest.raises(ValueError, match="required evidence source roles.*depth"):
        build_shadow_evidence_lineage(vector(), without_depth)

    without_funding = tuple(
        item for item in sources if item.role != EvidenceSourceRole.FUNDING
    )
    with pytest.raises(ValueError, match="required evidence source roles.*funding"):
        build_shadow_evidence_lineage(vector(), without_funding)

    vector_without_funding = vector(funding_delta_bps=None)
    lineage = build_shadow_evidence_lineage(vector_without_funding, without_funding)
    assert EvidenceSourceRole.FUNDING not in {item.role for item in lineage.sources}

    without_kraken = tuple(
        item for item in sources if item.source_id != "source:kraken:xrp"
    )
    with pytest.raises(ValueError, match="exactly match"):
        build_shadow_evidence_lineage(vector(), without_kraken)

    with pytest.raises(ValueError, match="provider counts"):
        build_shadow_evidence_lineage(
            replace(vector(), independent_provider_count=2),
            sources,
        )

    blank_provider = replace(sources[0], provider=" ")
    with pytest.raises(ValueError, match="provider names must be non-empty"):
        build_shadow_evidence_lineage(vector(), (blank_provider, *sources[1:]))


def test_source_digest_validation_is_fail_closed() -> None:
    with pytest.raises(ValueError, match="required"):
        source("", "coinbase", "a")
    with pytest.raises(ValueError, match="EvidenceSourceRole"):
        EvidenceSourceDigest(
            source_id="source:x",
            provider="coinbase",
            role="independent_price",  # type: ignore[arg-type]
            content_sha256="a" * 64,
            observed_at=PREDICTION_TIME,
            available_at=PREDICTION_TIME,
            fetched_at=PREDICTION_TIME,
        )
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        EvidenceSourceDigest(
            source_id="source:x",
            provider="coinbase",
            role=EvidenceSourceRole.INDEPENDENT_PRICE,
            content_sha256="A" * 64,
            observed_at=PREDICTION_TIME,
            available_at=PREDICTION_TIME,
            fetched_at=PREDICTION_TIME,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        EvidenceSourceDigest(
            source_id="source:x",
            provider="coinbase",
            role=EvidenceSourceRole.INDEPENDENT_PRICE,
            content_sha256="a" * 64,
            observed_at=PREDICTION_TIME.replace(tzinfo=None),
            available_at=PREDICTION_TIME,
            fetched_at=PREDICTION_TIME,
        )
    with pytest.raises(ValueError, match="observed <= available <= fetched"):
        EvidenceSourceDigest(
            source_id="source:x",
            provider="coinbase",
            role=EvidenceSourceRole.INDEPENDENT_PRICE,
            content_sha256="a" * 64,
            observed_at=PREDICTION_TIME,
            available_at=PREDICTION_TIME - timedelta(seconds=1),
            fetched_at=PREDICTION_TIME,
        )


def test_graph_document_is_machine_fact_without_directional_authority() -> None:
    lineage = build_shadow_evidence_lineage(vector(), complete_sources())
    document = shadow_evidence_graph_document(lineage)
    assert document.source.tier == SourceTier.T0_PRIMARY_MACHINE
    assert document.source.content_sha256 == lineage.lineage_sha256
    assert document.source.quality_flags == {
        "UNCALIBRATED_SHADOW_ONLY",
        "NON_DIRECTIONAL_RESEARCH_ONLY",
        "PROVENANCE_SCOPE_COMPLETE",
    }
    assert document.entities[0].attributes["execution_weight"] == 0.0
    assert document.entities[0].attributes["source_digests"] == {
        item.source_id: item.content_sha256 for item in lineage.sources
    }
    assert document.entities[0].attributes["source_roles"] == {
        item.source_id: item.role.value for item in lineage.sources
    }
    assert document.claims[0].status == EpistemicStatus.FACT
    assert "NON_DIRECTIONAL_RESEARCH_ONLY" in document.claims[0].quality_flags
    assert "PROVENANCE_SCOPE_COMPLETE" in document.claims[0].quality_flags
    graph = GraphifyCompiler().compile([document])
    assert document.claims[0].claim_id in graph.claims
    assert document.entities[0].entity_id in graph.entities


def test_sqlite_persists_lineage_immutably(tmp_path: Path) -> None:
    lineage = build_shadow_evidence_lineage(vector(), complete_sources())
    store = SQLiteStore(tmp_path / "lineage.sqlite3")
    assert store.load_shadow_evidence_lineage_payload(lineage.evidence_id) is None

    store.save_shadow_evidence_lineage(lineage)
    stored = store.load_shadow_evidence_lineage_payload(lineage.evidence_id)
    assert stored is not None
    assert stored["evidence_id"] == lineage.evidence_id
    assert stored["lineage_sha256"] == lineage.lineage_sha256
    assert store.audit_event_count() == 1

    store.save_shadow_evidence_lineage(lineage)
    assert store.audit_event_count() == 1

    with store.connection() as conn:
        conn.execute(
            "UPDATE shadow_evidence_lineage SET payload_json='{}' WHERE evidence_id=?",
            (lineage.evidence_id,),
        )
    with pytest.raises(ValueError, match="collision"):
        store.save_shadow_evidence_lineage(lineage)
