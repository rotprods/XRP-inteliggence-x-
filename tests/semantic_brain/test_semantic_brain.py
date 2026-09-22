from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.semantic_brain.graphify import ClaimLedger, EntityResolver
from xrp_regime_engine.semantic_brain.integration import build_regime_context
from xrp_regime_engine.semantic_brain.models import (
    ClaimRecord,
    EntityRecord,
    EntityType,
    EpistemicStatus,
    SourceTier,
    TemporalEnvelope,
)
from xrp_regime_engine.semantic_brain.riddles import FrozenPrediction, PredictionResolution

NOW = datetime(2026, 9, 15, tzinfo=UTC)


def test_future_available_data_is_rejected() -> None:
    with pytest.raises(ValueError, match="available_at"):
        TemporalEnvelope(available_at=NOW + timedelta(hours=1), retrieved_at=NOW)


def test_social_only_evidence_cannot_become_fact() -> None:
    ledger = ClaimLedger()
    claim = ledger.append(ClaimRecord.from_statement("589 predicts XRP price"))
    with pytest.raises(ValueError, match="primary evidence"):
        ledger.promote(claim.claim_id, EpistemicStatus.FACT, {SourceTier.T4_SOCIAL_CLAIM})


def test_fact_contradiction_degrades_both_claims() -> None:
    ledger = ClaimLedger()
    a = ledger.append(ClaimRecord.from_statement("Rail selected XRP", status=EpistemicStatus.FACT))
    b = ledger.append(
        ClaimRecord.from_statement("Rail did not select XRP", status=EpistemicStatus.FACT)
    )
    ledger.link_contradiction(a.claim_id, b.claim_id)
    assert a.status == EpistemicStatus.DISPUTED
    assert b.status == EpistemicStatus.DISPUTED


def test_entity_alias_collision_fails_closed() -> None:
    resolver = EntityResolver()
    resolver.register(
        EntityRecord(
            entity_id="org:ripple",
            entity_type=EntityType.ORGANIZATION,
            canonical_name="Ripple",
        )
    )
    with pytest.raises(ValueError, match="ambiguous"):
        resolver.register(
            EntityRecord(
                entity_id="asset:ripple",
                entity_type=EntityType.ASSET,
                canonical_name="Other",
                aliases={"Ripple"},
            )
        )


def test_regime_context_excludes_future_information_and_zero_weights_narrative() -> None:
    records = [
        {
            "claim_id": "c1",
            "statement": "known",
            "status": "FACT",
            "evidence_confidence": 0.9,
            "available_at": NOW - timedelta(minutes=1),
            "source_ids": ["s1"],
        },
        {
            "claim_id": "c2",
            "statement": "future",
            "status": "FACT",
            "evidence_confidence": 0.9,
            "available_at": NOW + timedelta(minutes=1),
            "source_ids": ["s2"],
        },
        {
            "claim_id": "c3",
            "statement": "riddle",
            "status": "CLAIM_ONLY",
            "evidence_confidence": 0.1,
            "available_at": NOW - timedelta(minutes=1),
            "source_ids": ["social"],
        },
    ]
    context = build_regime_context(records, NOW)
    assert {item.claim_id for item in context.evidence} == {"c1", "c3"}
    assert context.narrative_execution_weight == 0.0
    assert "NON_DIRECTIONAL_RESEARCH_ONLY" in context.evidence[1].quality_flags


def test_regime_context_filters_serialized_future_availability() -> None:
    records = [
        {
            "claim_id": "known",
            "statement": "known before decision",
            "status": "FACT",
            "available_at": "2026-09-14T23:59:00Z",
        },
        {
            "claim_id": "future",
            "statement": "not yet knowable",
            "status": "FACT",
            "available_at": "2026-09-15T00:01:00+00:00",
        },
    ]

    context = build_regime_context(records, NOW)

    assert [item.claim_id for item in context.evidence] == ["known"]


@pytest.mark.parametrize(
    "available_at",
    [None, "not-a-datetime", datetime(2026, 9, 14, 23, 59)],
)
def test_regime_context_rejects_unknown_or_ambiguous_availability(
    available_at: object,
) -> None:
    record = {
        "claim_id": "ambiguous",
        "statement": "availability is not trustworthy",
        "status": "FACT",
        "available_at": available_at,
    }

    with pytest.raises(ValueError, match="available_at"):
        build_regime_context([record], NOW)


def test_prediction_cannot_be_scored_before_horizon() -> None:
    prediction = FrozenPrediction(
        prediction_id="p1",
        source_id="social:example",
        original_text="red october",
        published_at=NOW,
        frozen_at=NOW + timedelta(minutes=1),
        target="XRP > 3",
        horizon_end=NOW + timedelta(days=30),
        success_rule="close > 3",
        failure_rule="otherwise",
    )
    with pytest.raises(ValueError, match="horizon"):
        prediction.resolve(
            PredictionResolution.HIT,
            NOW + timedelta(days=1),
            ["market:snapshot"],
        )
