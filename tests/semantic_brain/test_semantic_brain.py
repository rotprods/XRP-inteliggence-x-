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
    records =