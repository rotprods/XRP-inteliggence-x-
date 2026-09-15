from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from xrp_regime_engine.demo import DEMO_SUPPLEMENTAL_FEATURES, generate_demo_frame
from xrp_regime_engine.features import compute_features
from xrp_regime_engine.models import Horizon
from xrp_regime_engine.regime import score_regime
from xrp_regime_engine.storage import SQLiteStore

pytestmark = [pytest.mark.storage, pytest.mark.integration]


def snapshot():
    return score_regime(
        compute_features(generate_demo_frame(), supplemental=DEMO_SUPPLEMENTAL_FEATURES),
        Horizon.D1,
    )


def test_invalid_busy_timeout_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="busy_timeout"):
        SQLiteStore(tmp_path / "x.db", busy_timeout_ms=0)


def test_latest_queries_return_empty_when_no_data(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "x.db")
    assert store.latest_snapshot() is None
    assert store.latest_health() == []
    assert store.audit_event_count() == 0


def test_transaction_rolls_back_on_exception(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "x.db")
    with pytest.raises(RuntimeError):
        with store.connection() as conn:
            conn.execute("INSERT INTO audit_events(event_type, payload_json) VALUES ('test', '{}')")
            raise RuntimeError("boom")
    assert store.audit_event_count() == 0


def test_corrupt_database_fails_loudly(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.db"
    path.write_bytes(b"not-a-sqlite-database")
    with pytest.raises(sqlite3.DatabaseError):
        SQLiteStore(path)


def test_schema_version_missing_is_detected(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "x.db")
    with store.connection() as conn:
        conn.execute("DELETE FROM schema_metadata WHERE key='schema_version'")
    with pytest.raises(RuntimeError, match="schema version is missing"):
        store.schema_version()


def test_snapshot_upsert_preserves_single_row_and_audit_history(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "x.db")
    item = snapshot()
    store.save_snapshot(item)
    updated = item.model_copy(update={"bull_score": item.bull_score + 0.01, "bear_score": item.bear_score - 0.01})
    store.save_snapshot(updated)
    with store.connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM regime_snapshots").fetchone()[0]
    assert count == 1
    assert store.audit_event_count() == 2


def test_quick_check_backup_and_restore_round_trip(tmp_path: Path) -> None:
    source = SQLiteStore(tmp_path / "source.db")
    source.save_snapshot(snapshot())
    assert source.quick_check()

    backup = source.backup_to(tmp_path / "backups" / "engine.db")
    assert backup.is_file()
    restored = SQLiteStore.restore_from(backup, tmp_path / "restored.db")
    assert restored.quick_check()
    assert restored.latest_snapshot() is not None
    assert restored.audit_event_count() == source.audit_event_count()


def test_restore_rejects_missing_or_corrupt_backup(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        SQLiteStore.restore_from(tmp_path / "missing.db", tmp_path / "target.db")

    corrupt = tmp_path / "corrupt-backup.db"
    corrupt.write_bytes(b"broken")
    with pytest.raises(sqlite3.DatabaseError):
        SQLiteStore.restore_from(corrupt, tmp_path / "target.db")


def test_restore_rejects_backup_when_quick_check_is_not_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.db"
    source.write_bytes(b"placeholder")

    class FakeConnection:
        def execute(self, sql: str):
            assert sql == "PRAGMA quick_check"
            return self

        def fetchone(self):
            return ("corrupt",)

        def close(self) -> None:
            pass

    monkeypatch.setattr("xrp_regime_engine.storage.sqlite3.connect", lambda path: FakeConnection())
    with pytest.raises(sqlite3.DatabaseError, match="backup failed integrity check"):
        SQLiteStore.restore_from(source, tmp_path / "target.db")


def test_restore_rejects_target_when_post_restore_check_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = SQLiteStore(tmp_path / "source.db")
    source.save_snapshot(snapshot())
    backup = source.backup_to(tmp_path / "backup.db")

    original = SQLiteStore.quick_check
    calls = 0

    def fail_once_after_restore(self: SQLiteStore) -> bool:
        nonlocal calls
        calls += 1
        return False if calls == 1 else original(self)

    monkeypatch.setattr(SQLiteStore, "quick_check", fail_once_after_restore)
    with pytest.raises(sqlite3.DatabaseError, match="restored database failed integrity check"):
        SQLiteStore.restore_from(backup, tmp_path / "restored.db")
