from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.market_state_v2 import (
    AuthorityClass,
    EvidenceRef,
    FeatureValue,
    GateResult,
    GateStatus,
    MarketStateSnapshot,
)


def evidence(**overrides: object) -> EvidenceRef:
    observed = datetime(2026, 9, 22, 20, 0, tzinfo=UTC)
    values = dict(
        evidence_id="binance:xrp:1",
        provider="binance",
        endpoint="/api/v3/klines",
        instrument="XRPUSDT:SPOT",
        observed_at=observed,
        available_at=observed + timedelta(seconds=1),
        fetched_at=observed + timedelta(seconds=2),
        raw_sha256="a" * 64,
    )
    values.update(overrides)
    return EvidenceRef(**values)  # type: ignore[arg-type]


def test_snapshot_is_deterministic_and_non_executing() -> None:
    item = evidence()
    kwargs = dict(
        as_of=datetime(2026, 9, 22, 20, 1, tzinfo=UTC),
        instruments=("XRPUSDT:SPOT",),
        evidence=(item,),
        features=(FeatureValue("rsi14", 71.2, "1h", (item.evidence_id,)),),
        gates=(GateResult("TEMPORAL", GateStatus.PASS),),
    )
    left = MarketStateSnapshot(**kwargs)
    right = MarketStateSnapshot(**kwargs)
    assert left.snapshot_id == right.snapshot_id
    assert left.overall_status is GateStatus.PASS
    assert left.execution_weight == 0.0
    assert left.decision_authority is False


def test_future_fetched_evidence_fails_closed() -> None:
    item = evidence()
    with pytest.raises(ValueError, match="future-fetched"):
        MarketStateSnapshot(
            as_of=item.fetched_at - timedelta(milliseconds=1),
            instruments=("XRPUSDT:SPOT",),
            evidence=(item,),
            features=(),
        )


def test_unknown_feature_evidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown evidence"):
        MarketStateSnapshot(
            as_of=datetime(2026, 9, 22, 20, 1, tzinfo=UTC),
            instruments=("XRPUSDT:SPOT",),
            evidence=(evidence(),),
            features=(FeatureValue("rsi14", 50.0, "1h", ("missing",)),),
        )


def test_forbidden_execution_authority_cannot_enter_snapshot() -> None:
    with pytest.raises(ValueError, match="execution-authority"):
        evidence(authority=AuthorityClass.FORBIDDEN_EXECUTION)


def test_no_data_dominates_over_warning() -> None:
    snapshot = MarketStateSnapshot(
        as_of=datetime(2026, 9, 22, 20, 1, tzinfo=UTC),
        instruments=("XRPUSDT:SPOT",),
        evidence=(evidence(),),
        features=(),
        gates=(
            GateResult("PROVIDER", GateStatus.PASS_WITH_WARNINGS),
            GateResult("DERIVATIVES", GateStatus.NO_DATA),
        ),
    )
    assert snapshot.overall_status is GateStatus.NO_DATA
