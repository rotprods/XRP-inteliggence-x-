from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from xrp_regime_engine.historical_backfill_v2 import (
    BackfillPageV2,
    BackfillRunnerV2,
    BackfillWindowV2,
)
from xrp_regime_engine.historical_contract import (
    AvailabilityPrecision,
    FetchReceipt,
    HistoricalObservation,
)
from xrp_regime_engine.historical_store_v2 import HistoricalEvidenceStoreV2

T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
REQUEST_SHA = sha256(b"request").hexdigest()


def page_material(
    label: str,
    *,
    provider: str = "coinbase",
    fetched_at: datetime = T0,
    dataset: str = "xrp_spot_1h",
) -> tuple[bytes, FetchReceipt, HistoricalObservation]:
    raw = f'{{"page":"{label}"}}'.encode()
    payload_sha = sha256(raw).hexdigest()
    receipt = FetchReceipt.create(
        source_id=f"source:{provider}",
        provider=provider,
        canonical_uri=f"https://example.com/{provider}/{label}",
        endpoint="/history",
        request_fingerprint=REQUEST_SHA,
        fetched_at=fetched_at,
        payload_sha256=payload_sha,
        ingestion_version="2",
        parser_version="2",
    )
    observation = HistoricalObservation(
        observation_id=f"obs:{label}",
        dataset=dataset,
        record_id=f"record:{label}",
        provider=provider,
        source_id=receipt.source_id,
        symbol="XRP_USD",
        instrument="spot",
        observed_at=T0 - timedelta(hours=1),
        fetched_at=fetched_at,
        fetch_id=receipt.fetch_id,
        payload_sha256=payload_sha,
        values={"close": 2.0},
        availability_precision=AvailabilityPrecision.EXACT,
        availability_policy="provider_exact",
        available_at=T0 - timedelta(minutes=1),
    )
    return raw, receipt, observation


class TwoPageAdapter:
    provider = "coinbase"
    dataset = "xrp_spot_1h"
    schema_version = "historical-observation-v2"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def initial_cursor(self, window: BackfillWindowV2) -> dict[str, object]:
        del window
        return {"page": 1}

    def fetch_page(
        self,
        window: BackfillWindowV2,
        cursor: dict[str, object],
    ) -> BackfillPageV2:
        del window
        self.calls.append(dict(cursor))
        page = int(cursor["page"])
        raw, receipt, obs = page_material(
            str(page),
            fetched_at=T0 + timedelta(minutes=page),
        )
        if page == 1:
            return BackfillPageV2(
                raw_payload=raw,
                receipt=receipt,
                observations=(obs,),
                partition_key="date=2026-01-01",
                next_cursor={"page": 2},
                completed=False,
            )
        if page == 2:
            return BackfillPageV2(
                raw_payload=raw,
                receipt=receipt,
                observations=(obs,),
                partition_key="date=2026-01-02",
                next_cursor=None,
                completed=True,
            )
        raise AssertionError("unexpected cursor")


class NoFetchAdapter(TwoPageAdapter):
    def fetch_page(
        self,
        window: BackfillWindowV2,
        cursor: dict[str, object],
    ) -> BackfillPageV2:
        del window, cursor
        raise AssertionError("completed checkpoint must not refetch")


def window() -> BackfillWindowV2:
    return BackfillWindowV2(
        start=T0 - timedelta(days=2),
        end=T0,
        interval_seconds=3600,
    )


def test_window_contract_and_identity() -> None:
    item = window()
    assert item.identity()["interval_seconds"] == 3600

    with pytest.raises(ValueError, match="timezone-aware"):
        BackfillWindowV2(
            start=datetime(2026, 1, 1),
            end=T0,
            interval_seconds=3600,
        )
    with pytest.raises(ValueError, match="later than start"):
        BackfillWindowV2(start=T0, end=T0, interval_seconds=3600)
    with pytest.raises(ValueError, match="positive"):
        BackfillWindowV2(
            start=T0 - timedelta(days=1),
            end=T0,
            interval_seconds=0,
        )


def test_page_contract_rejects_invalid_shapes() -> None:
    raw, receipt, obs = page_material("1")
    with pytest.raises(ValueError, match="cannot be empty"):
        BackfillPageV2(
            raw_payload=b"",
            receipt=receipt,
            observations=(),
            partition_key=None,
            next_cursor=None,
            completed=True,
        )

    wrong_receipt = replace(receipt, payload_sha256=sha256(b"wrong").hexdigest())
    with pytest.raises(ValueError, match="digest"):
        BackfillPageV2(
            raw_payload=raw,
            receipt=wrong_receipt,
            observations=(),
            partition_key=None,
            next_cursor=None,
            completed=True,
        )

    with pytest.raises(ValueError, match="partition_key"):
        BackfillPageV2(
            raw_payload=raw,
            receipt=receipt,
            observations=(obs,),
            partition_key=None,
            next_cursor=None,
            completed=True,
        )
    with pytest.raises(ValueError, match="empty page"):
        BackfillPageV2(
            raw_payload=raw,
            receipt=receipt,
            observations=(),
            partition_key="date=2026-01-01",
            next_cursor=None,
            completed=True,
        )
    with pytest.raises(ValueError, match="completed page"):
        BackfillPageV2(
            raw_payload=raw,
            receipt=receipt,
            observations=(),
            partition_key=None,
            next_cursor={"page": 2},
            completed=True,
        )
    with pytest.raises(ValueError, match="incomplete page"):
        BackfillPageV2(
            raw_payload=raw,
            receipt=receipt,
            observations=(),
            partition_key=None,
            next_cursor=None,
            completed=False,
        )


def test_runner_constructor_and_job_key(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    with pytest.raises(ValueError, match="max_pages"):
        BackfillRunnerV2(store, max_pages=0)
    with pytest.raises(ValueError, match="max_empty_pages"):
        BackfillRunnerV2(store, max_empty_pages=-1)

    adapter = TwoPageAdapter()
    first = BackfillRunnerV2.job_key(adapter, window())
    second = BackfillRunnerV2.job_key(adapter, window())
    assert first == second
    assert first.startswith("backfill:sha256:")


def test_two_page_run_commits_manifest_after_checkpointed_partitions(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    adapter = TwoPageAdapter()
    result = BackfillRunnerV2(store).run(adapter, window())

    assert result.completed is True
    assert result.resumed is False
    assert result.pages_fetched == 2
    assert result.observations_seen == 2
    assert result.manifest is not None
    assert result.manifest.total_rows == 2
    assert len(store.list_partitions(adapter.dataset)) == 2
    checkpoint = store.load_checkpoint(result.job_key)
    assert checkpoint is not None and checkpoint.completed is True
    assert adapter.calls == [{"page": 1}, {"page": 2}]


def test_resume_continues_from_durable_cursor_and_keeps_prior_partition(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    adapter = TwoPageAdapter()
    with pytest.raises(RuntimeError, match="max_pages"):
        BackfillRunnerV2(store, max_pages=1).run(adapter, window())

    key = BackfillRunnerV2.job_key(adapter, window())
    checkpoint = store.load_checkpoint(key)
    assert checkpoint is not None
    assert checkpoint.cursor == {"page": 2}
    assert len(store.list_partitions(adapter.dataset)) == 1

    resumed_adapter = TwoPageAdapter()
    result = BackfillRunnerV2(store).run(resumed_adapter, window())
    assert result.resumed is True
    assert result.pages_fetched == 1
    assert result.manifest is not None
    assert result.manifest.total_rows == 2
    assert resumed_adapter.calls == [{"page": 2}]


def test_completed_checkpoint_does_not_refetch(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    first = BackfillRunnerV2(store).run(TwoPageAdapter(), window())
    assert first.manifest is not None

    result = BackfillRunnerV2(store).run(NoFetchAdapter(), window())
    assert result.completed is True
    assert result.resumed is True
    assert result.pages_fetched == 0
    assert result.observations_seen == 0
    assert result.manifest is not None
    assert result.manifest.total_rows == 2


def test_empty_initial_cursor_is_rejected(tmp_path: Path) -> None:
    class EmptyCursorAdapter(TwoPageAdapter):
        def initial_cursor(self, window: BackfillWindowV2) -> dict[str, object]:
            del window
            return {}

    with pytest.raises(ValueError, match="cursor cannot be empty"):
        BackfillRunnerV2(HistoricalEvidenceStoreV2(tmp_path)).run(
            EmptyCursorAdapter(),
            window(),
        )


def test_no_forward_cursor_progress_is_rejected_before_checkpoint(tmp_path: Path) -> None:
    class StuckAdapter(TwoPageAdapter):
        def fetch_page(
            self,
            window: BackfillWindowV2,
            cursor: dict[str, object],
        ) -> BackfillPageV2:
            del window
            raw, receipt, _ = page_material("stuck")
            return BackfillPageV2(
                raw_payload=raw,
                receipt=receipt,
                observations=(),
                partition_key=None,
                next_cursor=dict(cursor),
                completed=False,
            )

    store = HistoricalEvidenceStoreV2(tmp_path)
    adapter = StuckAdapter()
    with pytest.raises(RuntimeError, match="no forward cursor progress"):
        BackfillRunnerV2(store).run(adapter, window())
    assert store.load_checkpoint(BackfillRunnerV2.job_key(adapter, window())) is None
    assert store.fetch_receipt_count() == 1


def test_cursor_cycle_is_rejected(tmp_path: Path) -> None:
    class CycleAdapter(TwoPageAdapter):
        def fetch_page(
            self,
            window: BackfillWindowV2,
            cursor: dict[str, object],
        ) -> BackfillPageV2:
            del window
            page = int(cursor["page"])
            raw, receipt, _ = page_material(
                f"cycle-{page}",
                fetched_at=T0 + timedelta(minutes=page),
            )
            return BackfillPageV2(
                raw_payload=raw,
                receipt=receipt,
                observations=(),
                partition_key=None,
                next_cursor={"page": 2 if page == 1 else 1},
                completed=False,
            )

    with pytest.raises(RuntimeError, match="no forward cursor progress"):
        BackfillRunnerV2(HistoricalEvidenceStoreV2(tmp_path)).run(
            CycleAdapter(),
            window(),
        )


def test_consecutive_empty_page_budget_is_enforced(tmp_path: Path) -> None:
    class EmptyAdapter(TwoPageAdapter):
        def fetch_page(
            self,
            window: BackfillWindowV2,
            cursor: dict[str, object],
        ) -> BackfillPageV2:
            del window
            page = int(cursor["page"])
            raw, receipt, _ = page_material(
                f"empty-{page}",
                fetched_at=T0 + timedelta(minutes=page),
            )
            return BackfillPageV2(
                raw_payload=raw,
                receipt=receipt,
                observations=(),
                partition_key=None,
                next_cursor={"page": page + 1},
                completed=False,
            )

    store = HistoricalEvidenceStoreV2(tmp_path)
    with pytest.raises(RuntimeError, match="consecutive empty pages"):
        BackfillRunnerV2(store, max_empty_pages=0).run(EmptyAdapter(), window())
    assert store.fetch_receipt_count() == 1


@pytest.mark.parametrize(
    ("field", "expected_message"),
    [
        ("dataset", "another dataset"),
        ("fetch_id", "fetch_id"),
        ("payload_sha256", "payload digest"),
        ("provider", "provider"),
        ("source_id", "source_id"),
        ("fetched_at", "fetched_at"),
    ],
)
def test_page_observation_provenance_must_match_receipt(
    tmp_path: Path,
    field: str,
    expected_message: str,
) -> None:
    class BadAdapter(TwoPageAdapter):
        def fetch_page(
            self,
            window: BackfillWindowV2,
            cursor: dict[str, object],
        ) -> BackfillPageV2:
            del window, cursor
            raw, receipt, obs = page_material("bad")
            if field == "dataset":
                obs = replace(obs, dataset="other")
            elif field == "fetch_id":
                obs = replace(obs, fetch_id="fetch:sha256:" + "a" * 64)
            elif field == "payload_sha256":
                obs = replace(obs, payload_sha256="b" * 64)
            elif field == "provider":
                obs = replace(obs, provider="kraken")
            elif field == "source_id":
                obs = replace(obs, source_id="source:other")
            elif field == "fetched_at":
                obs = replace(obs, fetched_at=obs.fetched_at + timedelta(seconds=1))
            else:
                raise AssertionError(field)
            return BackfillPageV2(
                raw_payload=raw,
                receipt=receipt,
                observations=(obs,),
                partition_key="date=2026-01-02",
                next_cursor=None,
                completed=True,
            )

    with pytest.raises(ValueError, match=expected_message):
        BackfillRunnerV2(HistoricalEvidenceStoreV2(tmp_path)).run(
            BadAdapter(),
            window(),
        )


def test_completed_empty_dataset_fails_when_manifest_has_no_partition(tmp_path: Path) -> None:
    class EmptyCompleteAdapter(TwoPageAdapter):
        def fetch_page(
            self,
            window: BackfillWindowV2,
            cursor: dict[str, object],
        ) -> BackfillPageV2:
            del window, cursor
            raw, receipt, _ = page_material("empty-complete")
            return BackfillPageV2(
                raw_payload=raw,
                receipt=receipt,
                observations=(),
                partition_key=None,
                next_cursor=None,
                completed=True,
            )

    store = HistoricalEvidenceStoreV2(tmp_path)
    adapter = EmptyCompleteAdapter()
    with pytest.raises(ValueError, match="durable partition"):
        BackfillRunnerV2(store).run(adapter, window())
    checkpoint = store.load_checkpoint(BackfillRunnerV2.job_key(adapter, window()))
    assert checkpoint is not None and checkpoint.completed is True


def test_defensive_incomplete_page_lost_cursor_fails_closed(tmp_path: Path) -> None:
    class CorruptCursorAdapter(TwoPageAdapter):
        def fetch_page(
            self,
            window: BackfillWindowV2,
            cursor: dict[str, object],
        ) -> BackfillPageV2:
            del window, cursor
            raw, receipt, _ = page_material("corrupt-cursor")
            page = BackfillPageV2(
                raw_payload=raw,
                receipt=receipt,
                observations=(),
                partition_key=None,
                next_cursor={"page": 2},
                completed=False,
            )
            object.__setattr__(page, "next_cursor", None)
            return page

    with pytest.raises(RuntimeError, match="lost next_cursor"):
        BackfillRunnerV2(HistoricalEvidenceStoreV2(tmp_path)).run(
            CorruptCursorAdapter(),
            window(),
        )


def test_defensive_observation_page_lost_partition_fails_closed(tmp_path: Path) -> None:
    class CorruptPartitionAdapter(TwoPageAdapter):
        def fetch_page(
            self,
            window: BackfillWindowV2,
            cursor: dict[str, object],
        ) -> BackfillPageV2:
            del window, cursor
            raw, receipt, obs = page_material("corrupt-partition")
            page = BackfillPageV2(
                raw_payload=raw,
                receipt=receipt,
                observations=(obs,),
                partition_key="date=2026-01-02",
                next_cursor=None,
                completed=True,
            )
            object.__setattr__(page, "partition_key", None)
            return page

    with pytest.raises(RuntimeError, match="lost partition_key"):
        BackfillRunnerV2(HistoricalEvidenceStoreV2(tmp_path)).run(
            CorruptPartitionAdapter(),
            window(),
        )


def test_defensive_completed_run_without_receipt_timestamp_fails_closed() -> None:
    class CorruptReceiptTimeAdapter(TwoPageAdapter):
        def fetch_page(
            self,
            window: BackfillWindowV2,
            cursor: dict[str, object],
        ) -> BackfillPageV2:
            del window, cursor
            raw, receipt, _ = page_material("corrupt-receipt-time")
            page = BackfillPageV2(
                raw_payload=raw,
                receipt=receipt,
                observations=(),
                partition_key=None,
                next_cursor=None,
                completed=True,
            )
            object.__setattr__(receipt, "fetched_at", None)
            return page

    class MinimalStore:
        def load_checkpoint(self, key: str) -> None:
            del key
            return None

        def record_fetch(self, raw_payload: bytes, receipt: FetchReceipt) -> None:
            del raw_payload, receipt

        def save_checkpoint(self, **kwargs: object) -> None:
            del kwargs

        def finalize_manifest(self, **kwargs: object) -> None:
            del kwargs
            raise AssertionError("finalize_manifest must not be reached")

    with pytest.raises(RuntimeError, match="no receipt timestamp"):
        BackfillRunnerV2(MinimalStore()).run(CorruptReceiptTimeAdapter(), window())
