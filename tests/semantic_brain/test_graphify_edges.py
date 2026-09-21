from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from xrp_regime_engine.models import RegimeSnapshot
from xrp_regime_engine.semantic_brain.graphify import (
    ClaimLedger,
    ContradictionGraph,
    EntityResolver,
    GraphifyCompiler,
)
from xrp_regime_engine.semantic_brain.integration import build_regime_context
from xrp_regime_engine.semantic_brain.models import (
    ClaimRecord,
    EdgeRecord,
    EntityRecord,
    EntityType,
    EpistemicStatus,
    GraphDocument,
    RelationType,
    SourceRecord,
    SourceTier,
)
from xrp_regime_engine.semantic_brain.riddles import FrozenPrediction, PredictionResolution

NOW = datetime(2026, 9, 21, tzinfo=UTC)


def _source(source_id: str = "source:primary") -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        canonical_url=f"https://example.test/{source_id}",
        provider="fixture",
        tier=SourceTier.T1_PRIMARY_DOCUMENT,
        source_type="document",
    )


def _edge(object_id: str = "asset:xrp") -> EdgeRecord:
    return EdgeRecord(
        edge_id="edge:1",
        subject_id="org:ripple",
        relation=RelationType.SUPPORTS,
        object_id=object_id,
        source_ids={"source:primary"},
        evidence_status=EpistemicStatus.FACT,
        confidence=1.0,
    )


def _prediction(**overrides: object) -> FrozenPrediction:
    values: dict[str, object] = {
        "prediction_id": "prediction:1",
        "source_id": "source:social",
        "original_text": "example prediction",
        "published_at": NOW,
        "frozen_at": NOW + timedelta(minutes=1),
        "target": "XRP closes above threshold",
        "horizon_end": NOW + timedelta(days=1),
        "success_rule": "close > threshold",
        "failure_rule": "otherwise",
    }
    values.update(overrides)
    return FrozenPrediction(**values)


def test_entity_resolver_resolves_normalized_alias_and_unknown() -> None:
    resolver = EntityResolver()
    entity = EntityRecord(
        entity_id="org:ripple",
        entity_type=EntityType.ORGANIZATION,
        canonical_name="Ripple",
        aliases={"Ripple Labs"},
    )
    resolver.register(entity)

    assert resolver.resolve("  RIPPLE LABS ") == entity
    assert resolver.resolve("unknown") is None


def test_claim_ledger_rejects_id_collision_and_self_contradiction() -> None:
    ledger = ClaimLedger()
    ledger.append(ClaimRecord(claim_id="claim:1", statement="first"))

    with pytest.raises(ValueError, match="claim id collision"):
        ledger.append(ClaimRecord(claim_id="claim:1", statement="different"))
    with pytest.raises(ValueError, match="contradict itself"):
        ledger.link_contradiction("claim:1", "claim:1")


def test_claim_promotion_requires_resolved_primary_evidence() -> None:
    ledger = ClaimLedger()
    left = ledger.append(ClaimRecord(claim_id="claim:left", statement="left"))
    ledger.append(ClaimRecord(claim_id="claim:right", statement="right"))
    ledger.link_contradiction("claim:left", "claim:right")

    with pytest.raises(ValueError, match="unresolved contradiction"):
        ledger.promote(
            left.claim_id,
            EpistemicStatus.FACT,
            {SourceTier.T1_PRIMARY_DOCUMENT},
        )

    clean = ledger.append(ClaimRecord(claim_id="claim:clean", statement="clean"))
    promoted = ledger.promote(
        clean.claim_id,
        EpistemicStatus.FACT,
        {SourceTier.T0_PRIMARY_MACHINE},
    )
    assert promoted.status == EpistemicStatus.FACT


def test_contradiction_graph_is_symmetric_and_unknown_safe() -> None:
    graph = ContradictionGraph()
    graph.add("claim:a", "claim:b")

    assert graph.neighbors("claim:a") == {"claim:b"}
    assert graph.neighbors("claim:b") == {"claim:a"}
    assert graph.neighbors("claim:unknown") == set()


def test_graphify_compiler_materializes_entities_claims_edges_and_contradictions() -> None:
    entity = EntityRecord(
        entity_id="org:ripple",
        entity_type=EntityType.ORGANIZATION,
        canonical_name="Ripple",
    )
    left = ClaimRecord(
        claim_id="claim:left",
        statement="left",
        contradicts={"claim:right", "claim:external"},
    )
    right = ClaimRecord(claim_id="claim:right", statement="right")
    document = GraphDocument(
        document_id="doc:1",
        source=_source(),
        text="fixture",
        entities=[entity],
        claims=[left, right],
        edges=[_edge()],
    )

    compiled = GraphifyCompiler().compile([document])

    assert compiled.entities == {entity.entity_id: entity}
    assert set(compiled.claims) == {left.claim_id, right.claim_id}
    assert set(compiled.edges) == {"edge:1"}
    assert compiled.contradictions.neighbors(left.claim_id) == {right.claim_id}


def test_graphify_compiler_rejects_conflicting_edge_id() -> None:
    first = GraphDocument(
        document_id="doc:1",
        source=_source("source:one"),
        text="one",
        edges=[_edge("asset:xrp")],
    )
    second = GraphDocument(
        document_id="doc:2",
        source=_source("source:two"),
        text="two",
        edges=[_edge("asset:rlusd")],
    )

    with pytest.raises(ValueError, match="edge id collision"):
        GraphifyCompiler().compile([first, second])


def test_naive_semantic_decision_time_is_normalized_to_utc() -> None:
    context = build_regime_context([], datetime(2026, 9, 21, 8, 0))

    assert context.decision_at.tzinfo == UTC
    assert context.narrative_execution_weight == 0.0


def test_frozen_prediction_rejects_invalid_freeze_boundaries() -> None:
    with pytest.raises(ValueError, match="precede publication"):
        _prediction(frozen_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="before outcome horizon"):
        _prediction(frozen_at=NOW + timedelta(days=1))


def test_frozen_prediction_rejects_open_resolution_and_can_close_ambiguous() -> None:
    prediction = _prediction()
    with pytest.raises(ValueError, match="must close"):
        prediction.resolve(PredictionResolution.OPEN, NOW, [])

    resolved = prediction.resolve(
        PredictionResolution.AMBIGUOUS,
        NOW + timedelta(minutes=2),
        ["evidence:1"],
    )
    assert resolved is prediction
    assert resolved.resolution == PredictionResolution.AMBIGUOUS
    assert resolved.resolved_at == NOW + timedelta(minutes=2)
    assert resolved.evidence_ids == ["evidence:1"]


def test_regime_snapshot_digest_validator_retains_required_guard() -> None:
    with pytest.raises(ValueError, match="policy_digest is required"):
        RegimeSnapshot.validate_digest(None, SimpleNamespace(field_name="policy_digest"))
