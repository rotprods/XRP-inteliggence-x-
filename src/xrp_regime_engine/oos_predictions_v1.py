from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast

from xrp_regime_engine.research_horizon import ResearchHorizon

OOS_LEDGER_ROLE = "OOS_PREDICTION_LEDGER"
OOS_LEDGER_SCHEMA_VERSION = 1


class RawScoreSemantics(StrEnum):
    RAW_MODEL_SCORE = "RAW_MODEL_SCORE"


class FoldPlanLike(Protocol):
    fold_id: str
    horizon: ResearchHorizon
    cutoff_at: datetime
    train_feature_row_ids: tuple[str, ...]
    test_feature_row_ids: tuple[str, ...]
    test_prediction_start: datetime
    test_prediction_end: datetime


class FutureOutcomeLabelLike(Protocol):
    label_id: str
    feature_row_id: str
    prediction_time: datetime
    horizon: ResearchHorizon
    label_end_at: datetime
    resolved_at: datetime
    future_return: float
    positive_return_touches: Mapping[str, bool]
    negative_return_touches: Mapping[str, bool]
    absolute_price_touches: Mapping[str, bool]


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _nonempty(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _sha_prefixed(value: str, prefix: str, field: str) -> str:
    if not value.startswith(prefix):
        raise ValueError(f"{field} must use {prefix}<digest>")
    digest = value.removeprefix(prefix)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"{field} digest must be lowercase SHA-256")
    return value


def _score(value: float) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or not 0 <= numeric <= 1:
        raise ValueError("raw_score must be finite and within [0, 1]")
    return numeric


def _training_digest(feature_ids: Sequence[str]) -> str:
    ordered = tuple(feature_ids)
    if not ordered:
        raise ValueError("training feature set cannot be empty")
    if len(ordered) != len(set(ordered)):
        raise ValueError("training feature ids must be unique")
    return sha256(_canonical(list(ordered)).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class OOSPrediction:
    prediction_id: str
    prediction_sha256: str
    fold_id: str
    feature_row_id: str
    prediction_time: datetime
    horizon: ResearchHorizon
    event_key: str
    model_id: str
    model_version: str
    model_training_cutoff: datetime
    training_feature_digest: str
    training_sample_count: int
    feature_schema_version: str
    provider_universe_version: str
    source_snapshot_ids: tuple[str, ...]
    raw_score: float
    raw_score_semantics: RawScoreSemantics = RawScoreSemantics.RAW_MODEL_SCORE
    probability_calibrated: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0

    @classmethod
    def build(
        cls,
        *,
        fold: FoldPlanLike,
        feature_row_id: str,
        prediction_time: datetime,
        horizon: ResearchHorizon,
        event_key: str,
        model_id: str,
        model_version: str,
        model_training_cutoff: datetime,
        feature_schema_version: str,
        provider_universe_version: str,
        source_snapshot_ids: Sequence[str],
        raw_score: float,
    ) -> OOSPrediction:
        feature_id = _sha_prefixed(feature_row_id, "feature:sha256:", "feature_row_id")
        prediction = _utc(prediction_time, "prediction_time")
        training_cutoff = _utc(model_training_cutoff, "model_training_cutoff")
        fold_cutoff = _utc(fold.cutoff_at, "fold.cutoff_at")
        test_start = _utc(fold.test_prediction_start, "fold.test_prediction_start")
        test_end = _utc(fold.test_prediction_end, "fold.test_prediction_end")
        if horizon is not fold.horizon:
            raise ValueError("prediction horizon must match fold horizon")
        if feature_id not in fold.test_feature_row_ids:
            raise ValueError("feature_row_id is not part of the fold test set")
        if not test_start <= prediction <= test_end:
            raise ValueError("prediction_time must lie inside the fold test interval")
        if training_cutoff > fold_cutoff:
            raise ValueError("model_training_cutoff cannot exceed fold cutoff")
        training_digest = _training_digest(fold.train_feature_row_ids)
        snapshots = tuple(
            sorted(
                {
                    _sha_prefixed(item, "snapshot:sha256:", "source_snapshot_id")
                    for item in source_snapshot_ids
                }
            )
        )
        if not snapshots:
            raise ValueError("at least one source snapshot is required")
        normalized_event = _nonempty(event_key, "event_key")
        normalized_model_id = _nonempty(model_id, "model_id")
        normalized_model_version = _nonempty(model_version, "model_version")
        schema_version = _nonempty(feature_schema_version, "feature_schema_version")
        universe_version = _nonempty(provider_universe_version, "provider_universe_version")
        score = _score(raw_score)
        material: dict[str, object] = {
            "fold_id": _nonempty(fold.fold_id, "fold_id"),
            "feature_row_id": feature_id,
            "prediction_time": prediction.isoformat(),
            "horizon": horizon.value,
            "event_key": normalized_event,
            "model_id": normalized_model_id,
            "model_version": normalized_model_version,
            "model_training_cutoff": training_cutoff.isoformat(),
            "training_feature_digest": training_digest,
            "training_sample_count": len(fold.train_feature_row_ids),
            "feature_schema_version": schema_version,
            "provider_universe_version": universe_version,
            "source_snapshot_ids": list(snapshots),
            "raw_score": score,
            "raw_score_semantics": RawScoreSemantics.RAW_MODEL_SCORE.value,
            "probability_calibrated": False,
            "decision_authority": False,
            "execution_weight": 0.0,
        }
        digest = sha256(_canonical(material).encode()).hexdigest()
        return cls(
            prediction_id=f"oos-prediction:sha256:{digest}",
            prediction_sha256=digest,
            fold_id=cast(str, material["fold_id"]),
            feature_row_id=feature_id,
            prediction_time=prediction,
            horizon=horizon,
            event_key=normalized_event,
            model_id=normalized_model_id,
            model_version=normalized_model_version,
            model_training_cutoff=training_cutoff,
            training_feature_digest=training_digest,
            training_sample_count=len(fold.train_feature_row_ids),
            feature_schema_version=schema_version,
            provider_universe_version=universe_version,
            source_snapshot_ids=snapshots,
            raw_score=score,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "prediction_id": self.prediction_id,
            "prediction_sha256": self.prediction_sha256,
            "fold_id": self.fold_id,
            "feature_row_id": self.feature_row_id,
            "prediction_time": self.prediction_time.isoformat(),
            "horizon": self.horizon.value,
            "event_key": self.event_key,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "model_training_cutoff": self.model_training_cutoff.isoformat(),
            "training_feature_digest": self.training_feature_digest,
            "training_sample_count": self.training_sample_count,
            "feature_schema_version": self.feature_schema_version,
            "provider_universe_version": self.provider_universe_version,
            "source_snapshot_ids": list(self.source_snapshot_ids),
            "raw_score": self.raw_score,
            "raw_score_semantics": self.raw_score_semantics.value,
            "probability_calibrated": self.probability_calibrated,
            "decision_authority": self.decision_authority,
            "execution_weight": self.execution_weight,
        }


@dataclass(frozen=True, slots=True)
class ResolvedOOSOutcome:
    outcome_id: str
    outcome_sha256: str
    prediction_id: str
    label_id: str
    feature_row_id: str
    event_key: str
    horizon: ResearchHorizon
    prediction_time: datetime
    label_end_at: datetime
    resolved_at: datetime
    actual: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "outcome_id": self.outcome_id,
            "outcome_sha256": self.outcome_sha256,
            "prediction_id": self.prediction_id,
            "label_id": self.label_id,
            "feature_row_id": self.feature_row_id,
            "event_key": self.event_key,
            "horizon": self.horizon.value,
            "prediction_time": self.prediction_time.isoformat(),
            "label_end_at": self.label_end_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat(),
            "actual": self.actual,
        }


def _event_actual(event_key: str, label: FutureOutcomeLabelLike) -> bool:
    if event_key == "return_gt_0":
        return label.future_return > 0
    prefixes = (
        ("touch_return_up:", label.positive_return_touches),
        ("touch_return_down:", label.negative_return_touches),
        ("touch_price:", label.absolute_price_touches),
    )
    for prefix, mapping in prefixes:
        if event_key.startswith(prefix):
            key = event_key.removeprefix(prefix)
            if key not in mapping:
                raise ValueError(f"label does not contain event barrier {event_key!r}")
            return bool(mapping[key])
    raise ValueError(f"unsupported event_key: {event_key!r}")


def resolve_oos_outcome(
    prediction: OOSPrediction,
    label: FutureOutcomeLabelLike,
) -> ResolvedOOSOutcome:
    if prediction.feature_row_id != label.feature_row_id:
        raise ValueError("prediction and label feature_row_id must match")
    if prediction.prediction_time != _utc(label.prediction_time, "label.prediction_time"):
        raise ValueError("prediction and label prediction_time must match")
    if prediction.horizon is not label.horizon:
        raise ValueError("prediction and label horizon must match")
    label_end = _utc(label.label_end_at, "label.label_end_at")
    resolved = _utc(label.resolved_at, "label.resolved_at")
    if resolved < label_end:
        raise ValueError("outcome cannot resolve before label_end_at")
    actual = _event_actual(prediction.event_key, label)
    material: dict[str, object] = {
        "prediction_id": prediction.prediction_id,
        "label_id": _nonempty(label.label_id, "label_id"),
        "feature_row_id": prediction.feature_row_id,
        "event_key": prediction.event_key,
        "horizon": prediction.horizon.value,
        "prediction_time": prediction.prediction_time.isoformat(),
        "label_end_at": label_end.isoformat(),
        "resolved_at": resolved.isoformat(),
        "actual": actual,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return ResolvedOOSOutcome(
        outcome_id=f"oos-outcome:sha256:{digest}",
        outcome_sha256=digest,
        prediction_id=prediction.prediction_id,
        label_id=cast(str, material["label_id"]),
        feature_row_id=prediction.feature_row_id,
        event_key=prediction.event_key,
        horizon=prediction.horizon,
        prediction_time=prediction.prediction_time,
        label_end_at=label_end,
        resolved_at=resolved,
        actual=actual,
    )


class OOSPredictionLedgerV1:
    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 5_000) -> None:
        if busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.busy_timeout_ms = busy_timeout_ms
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1000,
            isolation_level="DEFERRED",
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            connection.execute("PRAGMA foreign_keys=ON")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS oos_metadata(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO oos_metadata(key, value) VALUES('ledger_role', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (OOS_LEDGER_ROLE,),
            )
            connection.execute(
                """
                INSERT INTO oos_metadata(key, value) VALUES('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(OOS_LEDGER_SCHEMA_VERSION),),
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS oos_predictions(
                    prediction_id TEXT PRIMARY KEY,
                    prediction_sha256 TEXT NOT NULL UNIQUE,
                    prediction_time TEXT NOT NULL,
                    horizon TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    fold_id TEXT NOT NULL,
                    feature_row_id TEXT NOT NULL,
                    raw_score REAL NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS oos_outcomes(
                    outcome_id TEXT PRIMARY KEY,
                    outcome_sha256 TEXT NOT NULL UNIQUE,
                    prediction_id TEXT NOT NULL UNIQUE,
                    resolved_at TEXT NOT NULL,
                    actual INTEGER NOT NULL CHECK(actual IN (0, 1)),
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(prediction_id) REFERENCES oos_predictions(prediction_id)
                )
                """
            )

    def save_prediction(self, prediction: OOSPrediction) -> None:
        if prediction.probability_calibrated or prediction.decision_authority:
            raise ValueError("OOS raw prediction cannot claim calibrated/decision authority")
        if prediction.execution_weight != 0.0:
            raise ValueError("OOS raw prediction execution_weight must remain zero")
        payload = _canonical(prediction.to_payload())
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM oos_predictions WHERE prediction_id=?",
                (prediction.prediction_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_json"]) != payload:
                    raise ValueError("prediction_id collision with different payload")
                return
            connection.execute(
                """
                INSERT INTO oos_predictions(
                    prediction_id, prediction_sha256, prediction_time,
                    horizon, event_key, fold_id, feature_row_id, raw_score, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prediction.prediction_id,
                    prediction.prediction_sha256,
                    prediction.prediction_time.isoformat(),
                    prediction.horizon.value,
                    prediction.event_key,
                    prediction.fold_id,
                    prediction.feature_row_id,
                    prediction.raw_score,
                    payload,
                ),
            )

    def save_outcome(self, outcome: ResolvedOOSOutcome) -> None:
        payload = _canonical(outcome.to_payload())
        with self._connection() as connection:
            prediction = connection.execute(
                "SELECT prediction_id FROM oos_predictions WHERE prediction_id=?",
                (outcome.prediction_id,),
            ).fetchone()
            if prediction is None:
                raise ValueError("outcome prediction_id is not present in the OOS ledger")
            existing = connection.execute(
                "SELECT payload_json FROM oos_outcomes WHERE prediction_id=?",
                (outcome.prediction_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_json"]) != payload:
                    raise ValueError("prediction outcome is immutable once resolved")
                return
            connection.execute(
                """
                INSERT INTO oos_outcomes(
                    outcome_id, outcome_sha256, prediction_id,
                    resolved_at, actual, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome.outcome_id,
                    outcome.outcome_sha256,
                    outcome.prediction_id,
                    outcome.resolved_at.isoformat(),
                    int(outcome.actual),
                    payload,
                ),
            )

    def prediction_count(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM oos_predictions").fetchone()
        return int(cast(sqlite3.Row, row)["count"])

    def outcome_count(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM oos_outcomes").fetchone()
        return int(cast(sqlite3.Row, row)["count"])

    def resolved_pairs(self) -> tuple[tuple[dict[str, object], dict[str, object]], ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT p.payload_json AS prediction_json, o.payload_json AS outcome_json
                FROM oos_predictions p
                JOIN oos_outcomes o ON o.prediction_id = p.prediction_id
                ORDER BY p.prediction_time, p.prediction_id
                """
            ).fetchall()
        pairs: list[tuple[dict[str, object], dict[str, object]]] = []
        for row in rows:
            prediction_payload = json.loads(str(row["prediction_json"]))
            outcome_payload = json.loads(str(row["outcome_json"]))
            if not isinstance(prediction_payload, dict) or not isinstance(outcome_payload, dict):
                raise RuntimeError("stored OOS ledger payload must be an object")
            pairs.append((prediction_payload, outcome_payload))
        return tuple(pairs)
