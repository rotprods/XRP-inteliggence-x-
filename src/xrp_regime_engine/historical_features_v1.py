from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

from xrp_regime_engine.historical_contract import EligibilityClass
from xrp_regime_engine.research_horizon import ResearchHorizon

FEATURE_STORE_ROLE = "FEATURES"
FEATURE_STORE_SCHEMA_VERSION = 1
_FORBIDDEN_PREFIXES = ("future_", "label_", "target_", "touch_", "outcome_", "mfe", "mae")


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


def _validate_snapshot_id(value: str) -> str:
    if not value.startswith("snapshot:sha256:"):
        raise ValueError("source snapshot ids must use snapshot:sha256:<digest>")
    digest = value.removeprefix("snapshot:sha256:")
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("source snapshot id digest must be lowercase SHA-256")
    return value


def _validate_feature_name(name: str) -> str:
    normalized = _nonempty(name, "feature name")
    lowered = normalized.lower()
    if lowered.startswith(_FORBIDDEN_PREFIXES):
        raise ValueError(f"future/outcome field is forbidden in feature row: {name}")
    return normalized


def _normalize_families(
    families: Mapping[str, Mapping[str, float | int | None]],
) -> dict[str, dict[str, float | None]]:
    normalized: dict[str, dict[str, float | None]] = {}
    if not families:
        raise ValueError("feature_families cannot be empty")
    for family_name, values in sorted(families.items()):
        family = _nonempty(family_name, "feature family")
        if not values:
            raise ValueError(f"feature family {family!r} cannot be empty")
        family_values: dict[str, float | None] = {}
        for feature_name, value in sorted(values.items()):
            name = _validate_feature_name(feature_name)
            if value is None:
                family_values[name] = None
                continue
            if isinstance(value, bool):
                raise ValueError(f"feature {name!r} must be numeric or null, not bool")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError(f"feature {name!r} must be finite or null")
            family_values[name] = numeric
        normalized[family] = family_values
    return normalized


@dataclass(frozen=True, slots=True)
class HistoricalFeatureRow:
    feature_row_id: str
    feature_sha256: str
    feature_time: datetime
    prediction_time: datetime
    horizon: ResearchHorizon
    feature_schema_version: str
    provider_universe_version: str
    eligibility_class: EligibilityClass
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    feature_families: Mapping[str, Mapping[str, float | None]]
    quality_flags: tuple[str, ...]

    @classmethod
    def build(
        cls,
        *,
        feature_time: datetime,
        prediction_time: datetime,
        horizon: ResearchHorizon,
        feature_schema_version: str,
        provider_universe_version: str,
        eligibility_class: EligibilityClass,
        source_snapshot_ids: Sequence[str],
        evidence_ids: Sequence[str] = (),
        feature_families: Mapping[str, Mapping[str, float | int | None]],
        quality_flags: Sequence[str] = (),
    ) -> HistoricalFeatureRow:
        feature = _utc(feature_time, "feature_time")
        prediction = _utc(prediction_time, "prediction_time")
        if feature > prediction:
            raise ValueError("feature_time cannot be later than prediction_time")
        schema_version = _nonempty(feature_schema_version, "feature_schema_version")
        universe_version = _nonempty(provider_universe_version, "provider_universe_version")
        if eligibility_class is EligibilityClass.INELIGIBLE:
            raise ValueError("ineligible evidence cannot produce a feature row")
        snapshots = tuple(sorted({_validate_snapshot_id(item) for item in source_snapshot_ids}))
        if not snapshots:
            raise ValueError("feature row requires at least one source snapshot")
        evidence = tuple(sorted({_nonempty(item, "evidence_id") for item in evidence_ids}))
        families = _normalize_families(feature_families)
        flags = tuple(sorted({_nonempty(item, "quality_flag") for item in quality_flags}))
        payload: dict[str, object] = {
            "feature_time": feature.isoformat(),
            "prediction_time": prediction.isoformat(),
            "horizon": horizon.value,
            "feature_schema_version": schema_version,
            "provider_universe_version": universe_version,
            "eligibility_class": eligibility_class.value,
            "source_snapshot_ids": list(snapshots),
            "evidence_ids": list(evidence),
            "feature_families": families,
            "quality_flags": list(flags),
        }
        digest = sha256(_canonical(payload).encode()).hexdigest()
        return cls(
            feature_row_id=f"feature:sha256:{digest}",
            feature_sha256=digest,
            feature_time=feature,
            prediction_time=prediction,
            horizon=horizon,
            feature_schema_version=schema_version,
            provider_universe_version=universe_version,
            eligibility_class=eligibility_class,
            source_snapshot_ids=snapshots,
            evidence_ids=evidence,
            feature_families=families,
            quality_flags=flags,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "feature_row_id": self.feature_row_id,
            "feature_sha256": self.feature_sha256,
            "feature_time": self.feature_time.isoformat(),
            "prediction_time": self.prediction_time.isoformat(),
            "horizon": self.horizon.value,
            "feature_schema_version": self.feature_schema_version,
            "provider_universe_version": self.provider_universe_version,
            "eligibility_class": self.eligibility_class.value,
            "source_snapshot_ids": list(self.source_snapshot_ids),
            "evidence_ids": list(self.evidence_ids),
            "feature_families": {
                family: dict(values) for family, values in self.feature_families.items()
            },
            "quality_flags": list(self.quality_flags),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> HistoricalFeatureRow:
        raw_families = payload.get("feature_families")
        if not isinstance(raw_families, Mapping):
            raise RuntimeError("stored feature_families must be an object")
        families: dict[str, dict[str, float | None]] = {}
        for family, raw_values in raw_families.items():
            if not isinstance(raw_values, Mapping):
                raise RuntimeError("stored feature family must be an object")
            values: dict[str, float | None] = {}
            for key, value in raw_values.items():
                values[str(key)] = None if value is None else float(value)
            families[str(family)] = values
        row = cls.build(
            feature_time=datetime.fromisoformat(str(payload["feature_time"])),
            prediction_time=datetime.fromisoformat(str(payload["prediction_time"])),
            horizon=ResearchHorizon(str(payload["horizon"])),
            feature_schema_version=str(payload["feature_schema_version"]),
            provider_universe_version=str(payload["provider_universe_version"]),
            eligibility_class=EligibilityClass(str(payload["eligibility_class"])),
            source_snapshot_ids=cast(Sequence[str], payload["source_snapshot_ids"]),
            evidence_ids=cast(Sequence[str], payload["evidence_ids"]),
            feature_families=families,
            quality_flags=cast(Sequence[str], payload["quality_flags"]),
        )
        if (
            row.feature_row_id != payload.get("feature_row_id")
            or row.feature_sha256 != payload.get("feature_sha256")
        ):
            raise RuntimeError("stored feature row digest does not match payload")
        return row


class FeatureStoreV1:
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
                CREATE TABLE IF NOT EXISTS research_store_metadata(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            role = connection.execute(
                "SELECT value FROM research_store_metadata WHERE key='store_role'"
            ).fetchone()
            if role is not None and str(role["value"]) != FEATURE_STORE_ROLE:
                raise ValueError("database already belongs to a non-feature research store")
            connection.execute(
                """
                INSERT INTO research_store_metadata(key, value) VALUES('store_role', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (FEATURE_STORE_ROLE,),
            )
            connection.execute(
                """
                INSERT INTO research_store_metadata(key, value) VALUES('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(FEATURE_STORE_SCHEMA_VERSION),),
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS historical_feature_rows(
                    feature_row_id TEXT PRIMARY KEY,
                    feature_sha256 TEXT NOT NULL UNIQUE,
                    prediction_time TEXT NOT NULL,
                    horizon TEXT NOT NULL,
                    eligibility_class TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_feature_prediction
                ON historical_feature_rows(prediction_time, horizon)
                """
            )

    def save(self, row: HistoricalFeatureRow) -> None:
        payload = _canonical(row.to_payload())
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM historical_feature_rows WHERE feature_row_id=?",
                (row.feature_row_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_json"]) != payload:
                    raise ValueError("feature_row_id collision with different payload")
                return
            connection.execute(
                """
                INSERT INTO historical_feature_rows(
                    feature_row_id, feature_sha256, prediction_time,
                    horizon, eligibility_class, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row.feature_row_id,
                    row.feature_sha256,
                    row.prediction_time.isoformat(),
                    row.horizon.value,
                    row.eligibility_class.value,
                    payload,
                ),
            )

    def load(self, feature_row_id: str) -> HistoricalFeatureRow | None:
        with self._connection() as connection:
            record = connection.execute(
                "SELECT payload_json FROM historical_feature_rows WHERE feature_row_id=?",
                (feature_row_id,),
            ).fetchone()
        if record is None:
            return None
        payload = json.loads(str(record["payload_json"]))
        if not isinstance(payload, dict):
            raise RuntimeError("stored feature row root must be an object")
        return HistoricalFeatureRow.from_payload(payload)

    def count(self) -> int:
        with self._connection() as connection:
            record = connection.execute(
                "SELECT COUNT(*) AS count FROM historical_feature_rows"
            ).fetchone()
        return int(record["count"])

    def table_names(self) -> tuple[str, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        return tuple(str(row["name"]) for row in rows)
