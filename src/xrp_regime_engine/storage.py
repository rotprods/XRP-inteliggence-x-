from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from xrp_regime_engine.models import ProviderHealth, RegimeSnapshot


SCHEMA_VERSION = 1
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS schema_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT INTO schema_metadata(key, value) VALUES ('schema_version', '{SCHEMA_VERSION}')
ON CONFLICT(key) DO UPDATE SET value=excluded.value;

CREATE TABLE IF NOT EXISTS regime_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  asset TEXT NOT NULL,
  horizon TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  regime TEXT NOT NULL,
  bull_score REAL NOT NULL,
  confidence REAL NOT NULL,
  payload_json TEXT NOT NULL,
  UNIQUE(asset, horizon, generated_at)
);
CREATE INDEX IF NOT EXISTS idx_regime_latest
  ON regime_snapshots(asset, horizon, generated_at DESC);

CREATE TABLE IF NOT EXISTS provider_health (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  checked_at TEXT NOT NULL,
  status TEXT NOT NULL,
  freshness_score REAL NOT NULL,
  agreement_score REAL NOT NULL,
  payload_json TEXT NOT NULL,
  UNIQUE(provider, checked_at)
);
CREATE INDEX IF NOT EXISTS idx_health_latest
  ON provider_health(provider, checked_at DESC);

CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
"""


class SQLiteStore:
    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 5_000) -> None:
        self.path = Path(path)
        self.busy_timeout_ms = busy_timeout_ms
        if busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be positive")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1000,
            isolation_level="DEFERRED",
        )
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        finally:
            # Configuration itself may fail (for example, a corrupt database).
            # Closing from the outer finally prevents descriptor/resource leaks even
            # when the context manager never reaches its yield point.
            conn.close()

    def save_snapshot(self, snapshot: RegimeSnapshot) -> None:
        payload = snapshot.model_dump_json()
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO regime_snapshots
                (asset, horizon, generated_at, regime, bull_score, confidence, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset, horizon, generated_at) DO UPDATE SET
                  regime=excluded.regime,
                  bull_score=excluded.bull_score,
                  confidence=excluded.confidence,
                  payload_json=excluded.payload_json""",
                (
                    snapshot.asset,
                    snapshot.horizon.value,
                    snapshot.generated_at.isoformat(),
                    snapshot.regime.value,
                    snapshot.bull_score,
                    snapshot.confidence,
                    payload,
                ),
            )
            conn.execute(
                "INSERT INTO audit_events(event_type, payload_json) VALUES (?, ?)",
                (
                    "regime_snapshot_saved",
                    json.dumps(
                        {
                            "asset": snapshot.asset,
                            "horizon": snapshot.horizon.value,
                            "generated_at": snapshot.generated_at.isoformat(),
                        },
                        sort_keys=True,
                    ),
                ),
            )

    def save_health(self, health: ProviderHealth) -> None:
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO provider_health
                (provider, checked_at, status, freshness_score, agreement_score, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, checked_at) DO UPDATE SET
                  status=excluded.status,
                  freshness_score=excluded.freshness_score,
                  agreement_score=excluded.agreement_score,
                  payload_json=excluded.payload_json""",
                (
                    health.provider,
                    health.checked_at.isoformat(),
                    health.status,
                    health.freshness_score,
                    health.agreement_score,
                    health.model_dump_json(),
                ),
            )
            conn.execute(
                "INSERT INTO audit_events(event_type, payload_json) VALUES (?, ?)",
                (
                    "provider_health_saved",
                    json.dumps(
                        {
                            "provider": health.provider,
                            "checked_at": health.checked_at.isoformat(),
                            "status": health.status,
                        },
                        sort_keys=True,
                    ),
                ),
            )

    def latest_snapshot(
        self, asset: str = "XRP", horizon: str = "1d"
    ) -> RegimeSnapshot | None:
        with self.connection() as conn:
            row = conn.execute(
                """SELECT payload_json FROM regime_snapshots
                WHERE asset=? AND horizon=? ORDER BY generated_at DESC LIMIT 1""",
                (asset, horizon),
            ).fetchone()
        return RegimeSnapshot.model_validate_json(row["payload_json"]) if row else None

    def latest_health(self) -> list[ProviderHealth]:
        query = """
        WITH ranked AS (
          SELECT payload_json, provider, checked_at,
                 ROW_NUMBER() OVER (
                   PARTITION BY provider ORDER BY checked_at DESC, id DESC
                 ) AS row_number
          FROM provider_health
        )
        SELECT payload_json FROM ranked WHERE row_number=1 ORDER BY provider
        """
        with self.connection() as conn:
            rows = conn.execute(query).fetchall()
        return [ProviderHealth.model_validate_json(row["payload_json"]) for row in rows]

    def schema_version(self) -> int:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT value FROM schema_metadata WHERE key='schema_version'"
            ).fetchone()
        if row is None:
            raise RuntimeError("database schema version is missing")
        return int(row["value"])

    def audit_event_count(self) -> int:
        with self.connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM audit_events").fetchone()
        return int(row["count"])

    def quick_check(self) -> bool:
        with self.connection() as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
        return bool(row and row[0] == "ok")

    def backup_to(self, target: str | Path) -> Path:
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as source:
            destination = sqlite3.connect(target_path)
            try:
                source.backup(destination)
                destination.commit()
            finally:
                destination.close()
        return target_path

    @classmethod
    def restore_from(cls, source: str | Path, target: str | Path) -> SQLiteStore:
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        source_conn = sqlite3.connect(source_path)
        try:
            check = source_conn.execute("PRAGMA quick_check").fetchone()
            if not check or check[0] != "ok":
                raise sqlite3.DatabaseError("backup failed integrity check")
            target_path = Path(target)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_conn = sqlite3.connect(target_path)
            try:
                source_conn.backup(target_conn)
                target_conn.commit()
            finally:
                target_conn.close()
        finally:
            source_conn.close()
        restored = cls(target_path)
        if not restored.quick_check():
            raise sqlite3.DatabaseError("restored database failed integrity check")
        return restored
