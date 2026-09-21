from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from xrp_regime_engine.oos_predictions_v1 import (
    OOSPrediction,
    OOSPredictionLedgerV1,
    resolve_oos_outcome,
)
from xrp_regime_engine.research_horizon import ResearchHorizon

T0 = datetime(2026, 1, 1, tzinfo=UTC)
FEATURE = "feature:sha256:" + "a" * 64
SNAP = "snapshot:sha256:" + "b" * 64


@dataclass
class Fold:
    fold_id: str = "fold:1"
    horizon: ResearchHorizon = ResearchHorizon.H1
    cutoff_at: datetime = T0 - timedelta(minutes=1)
    train_feature_row_ids: tuple[str, ...] = (
        "feature:sha256:" + "1" * 64,
        "feature:sha256:" + "2" * 64,
    )
    test_feature_row_ids: tuple[str, ...] = (FEATURE,)
    test_prediction_start: datetime = T0
    test_prediction_end: datetime = T0


@dataclass
class Label:
    label_id: str = "label:1"
    feature_row_id: str = FEATURE
    prediction_time: datetime = T0
    horizon: ResearchHorizon = ResearchHorizon.H1
    label_end_at: datetime = T0 + timedelta(hours=1)
    resolved_at: datetime = T0 + timedelta(hours=1)
    future_return: float = 0.05
    positive_return_touches: dict[str, bool] | None = None
    negative_return_touches: dict[str, bool] | None = None
    absolute_price_touches: dict[str, bool] | None = None

    def __post_init__(self) -> None:
        if self.positive_return_touches is None:
            self.positive_return_touches = {"0.05": True}
        if self.negative_return_touches is None:
            self.negative_return_touches = {"0.05": False}
        if self.absolute_price_touches is None:
            self.absolute_price_touches = {"2": True}


def pred(**kwargs: object) -> OOSPrediction:
    args: dict[str, object] = {
        "fold": Fold(),
        "feature_row_id": FEATURE,
        "prediction_time": T0,
        "horizon": ResearchHorizon.H1,
        "event_key": "return_gt_0",
        "model_id": "m",
        "model_version": "v1",
        "model_training_cutoff": T0 - timedelta(minutes=1),
        "feature_schema_version": "f1",
        "provider_universe_version": "p1",
        "source_snapshot_ids": (SNAP,),
        "raw_score": 0.7,
    }
    args.update(kwargs)
    return OOSPrediction.build(**args)  # type: ignore[arg-type]


def test_prediction_build_is_deterministic_and_non_authoritative() -> None:
    a = pred()
    b = pred()
    assert a == b
    assert a.probability_calibrated is False
    assert a.decision_authority is False
    assert a.execution_weight == 0
    assert a.training_sample_count == 2
    assert len(a.training_feature_digest) == 64


def test_prediction_rejects_bad_identity_and_fold_rules() -> None:
    with pytest.raises(ValueError, match="feature:sha256"):
        pred(feature_row_id="bad")
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        pred(feature_row_id="feature:sha256:" + "G" * 64)
    with pytest.raises(ValueError, match="fold horizon"):
        pred(horizon=ResearchHorizon.H4)
    with pytest.raises(ValueError, match="fold test set"):
        pred(feature_row_id="feature:sha256:" + "c" * 64)
    with pytest.raises(ValueError, match="test interval"):
        pred(prediction_time=T0 + timedelta(seconds=1))
    with pytest.raises(ValueError, match="fold cutoff"):
        pred(model_training_cutoff=T0)
    with pytest.raises(ValueError, match="source snapshot"):
        pred(source_snapshot_ids=())
    with pytest.raises(ValueError, match="snapshot:sha256"):
        pred(source_snapshot_ids=("bad",))
    with pytest.raises(ValueError, match=r"within \[0, 1\]"):
        pred(raw_score=2)
    with pytest.raises(ValueError, match="event_key"):
        pred(event_key=" ")


def test_prediction_rejects_duplicate_or_empty_train() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        pred(fold=Fold(train_feature_row_ids=()))
    with pytest.raises(ValueError, match="unique"):
        pred(fold=Fold(train_feature_row_ids=("x", "x")))


def test_resolve_outcome_supported_events() -> None:
    p = pred()
    label = Label()
    assert resolve_oos_outcome(p, label).actual is True
    assert resolve_oos_outcome(pred(event_key="touch_return_up:0.05"), label).actual is True
    assert resolve_oos_outcome(pred(event_key="touch_return_down:0.05"), label).actual is False
    assert resolve_oos_outcome(pred(event_key="touch_price:2"), label).actual is True


def test_resolve_outcome_rejects_mismatch_and_unknown_event() -> None:
    p = pred()
    label = Label()
    with pytest.raises(ValueError, match="feature_row_id"):
        resolve_oos_outcome(p, replace(label, feature_row_id="x"))
    with pytest.raises(ValueError, match="prediction_time"):
        resolve_oos_outcome(
            p,
            replace(label, prediction_time=T0 + timedelta(seconds=1)),
        )
    with pytest.raises(ValueError, match="horizon"):
        resolve_oos_outcome(p, replace(label, horizon=ResearchHorizon.H4))
    with pytest.raises(ValueError, match="label_end_at"):
        resolve_oos_outcome(p, replace(label, resolved_at=T0))
    with pytest.raises(ValueError, match="does not contain"):
        resolve_oos_outcome(pred(event_key="touch_price:99"), label)
    with pytest.raises(ValueError, match="unsupported"):
        resolve_oos_outcome(pred(event_key="wat"), label)


def test_ledger_is_append_only(tmp_path: Path) -> None:
    store = OOSPredictionLedgerV1(tmp_path / "oos.db")
    p = pred()
    outcome = resolve_oos_outcome(p, Label())
    store.save_prediction(p)
    store.save_prediction(p)
    assert store.prediction_count() == 1
    store.save_outcome(outcome)
    store.save_outcome(outcome)
    assert store.outcome_count() == 1
    pairs = store.resolved_pairs()
    assert pairs[0][0]["prediction_id"] == p.prediction_id
    assert pairs[0][1]["outcome_id"] == outcome.outcome_id


def test_ledger_rejects_outcome_without_prediction_and_mutation(tmp_path: Path) -> None:
    store = OOSPredictionLedgerV1(tmp_path / "oos.db")
    p = pred()
    outcome = resolve_oos_outcome(p, Label())
    with pytest.raises(ValueError, match="not present"):
        store.save_outcome(outcome)
    store.save_prediction(p)
    store.save_outcome(outcome)
    with pytest.raises(ValueError, match="immutable"):
        store.save_outcome(replace(outcome, actual=False))


def test_ledger_rejects_authority_and_bad_timeout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="busy_timeout"):
        OOSPredictionLedgerV1(tmp_path / "x.db", busy_timeout_ms=0)
    store = OOSPredictionLedgerV1(tmp_path / "y.db")
    p = pred()
    with pytest.raises(ValueError, match="calibrated/decision"):
        store.save_prediction(replace(p, probability_calibrated=True))
    with pytest.raises(ValueError, match="execution_weight"):
        store.save_prediction(replace(p, execution_weight=1.0))


def test_prediction_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        pred(prediction_time=datetime(2026, 1, 1))


def test_prediction_collision_and_corrupt_pair_payload(tmp_path: Path) -> None:
    store = OOSPredictionLedgerV1(tmp_path / "oos.db")
    p = pred()
    store.save_prediction(p)
    with store._connection() as connection:
        connection.execute(
            "UPDATE oos_predictions SET payload_json='{}' WHERE prediction_id=?",
            (p.prediction_id,),
        )
    with pytest.raises(ValueError, match="prediction_id collision"):
        store.save_prediction(p)

    with store._connection() as connection:
        connection.execute(
            "DELETE FROM oos_predictions WHERE prediction_id=?",
            (p.prediction_id,),
        )
    store.save_prediction(p)
    outcome = resolve_oos_outcome(p, Label())
    store.save_outcome(outcome)
    with store._connection() as connection:
        connection.execute(
            "UPDATE oos_outcomes SET payload_json='[]' WHERE prediction_id=?",
            (p.prediction_id,),
        )
    with pytest.raises(RuntimeError, match="payload must be an object"):
        store.resolved_pairs()
