from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from xrp_regime_engine.historical_store import (
    BackfillCheckpointStore,
    ContentAddressedRawStore,
    DatasetManifest,
    DatasetPartition,
    HistoricalRecord,
    JSONLPartitionStore,
    ManifestStore,
    PointInTimeCatalog,
    utc,
)


@dataclass(frozen=True, slots=True)
class BackfillWindow:
    start: datetime
    end: datetime
    interval_seconds: int

    def __post_init__(self) -> None:
        start = utc(self.start)
        end = utc(self.end)
        if end <= start:
            raise ValueError("backfill end must be later than start")
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "interval_seconds": self.interval_seconds,
        }


@dataclass(frozen=True, slots=True)
class NormalizedPageRecord:
    record_id: str
    observed_at: datetime
    available_at: datetime
    values: Mapping[str, Any]
    revision: int = 0

    def __post_init__(self) -> None:
        observed = utc(self.observed_at)
        available = utc(self.available_at)
        if not self.record_id:
            raise ValueError("record_id is required")
        if available < observed:
            raise ValueError("available_at cannot precede observed_at")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "values", dict(self.values))


@dataclass(frozen=True, slots=True)
class BackfillPage:
    raw_payload: bytes
    source_url: str
    received_at: datetime
    records: tuple[NormalizedPageRecord, ...]
    next_cursor: Mapping[str, Any] | None
    completed: bool
    attributes: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.raw_payload:
            raise ValueError("backfill page raw_payload cannot be empty")
        object.__setattr__(self, "received_at", utc(self.received_at))
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "attributes", dict(self.attributes))
        if self.completed and self.next_cursor is not None:
            raise ValueError("a completed page cannot expose a next cursor")
        if not self.completed and self.next_cursor is None:
            raise ValueError("an incomplete page must expose a next cursor")


class HistoricalAdapter(Protocol):
    provider: str
    source: str
    dataset: str
    schema_version: str

    def initial_cursor(self, window: BackfillWindow) -> Mapping[str, Any]: ...

    def fetch_page(self, window: BackfillWindow, cursor: Mapping[str, Any]) -> BackfillPage: ...


@dataclass(frozen=True, slots=True)
class BackfillResult:
    job_key: str
    dataset: str
    pages_fetched: int
    raw_payloads_written: int
    records_seen: int
    catalog_records_inserted: int
    partitions: tuple[DatasetPartition, ...]
    manifest_path: str | None
    completed: bool
    resumed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_key": self.job_key,
            "dataset": self.dataset,
            "pages_fetched": self.pages_fetched,
            "raw_payloads_written": self.raw_payloads_written,
            "records_seen": self.records_seen,
            "catalog_records_inserted": self.catalog_records_inserted,
            "partitions": [partition.to_dict() for partition in self.partitions],
            "manifest_path": self.manifest_path,
            "completed": self.completed,
            "resumed": self.resumed,
        }


class BackfillRunner:
    def __init__(
        self,
        *,
        raw_store: ContentAddressedRawStore,
        partition_store: JSONLPartitionStore,
        catalog: PointInTimeCatalog,
        manifest_store: ManifestStore,
        checkpoints: BackfillCheckpointStore,
        max_pages: int = 10_000,
    ) -> None:
        if max_pages <= 0:
            raise ValueError("max_pages must be positive")
        self.raw_store = raw_store
        self.partition_store = partition_store
        self.catalog = catalog
        self.manifest_store = manifest_store
        self.checkpoints = checkpoints
        self.max_pages = max_pages

    @staticmethod
    def job_key(adapter: HistoricalAdapter, window: BackfillWindow) -> str:
        return (
            f"{adapter.provider}:{adapter.dataset}:"
            f"{window.start.isoformat()}:{window.end.isoformat()}:{window.interval_seconds}"
        )

    def run(self, adapter: HistoricalAdapter, window: BackfillWindow) -> BackfillResult:
        key = self.job_key(adapter, window)
        checkpoint = self.checkpoints.load(key)
        resumed = checkpoint is not None
        if checkpoint and checkpoint[1]:
            return BackfillResult(
                job_key=key,
                dataset=adapter.dataset,
                pages_fetched=0,
                raw_payloads_written=0,
                records_seen=0,
                catalog_records_inserted=0,
                partitions=(),
                manifest_path=None,
                completed=True,
                resumed=True,
            )

        cursor: Mapping[str, Any] = checkpoint[0] if checkpoint else adapter.initial_cursor(window)
        seen_cursors: set[str] = set()
        partitions: list[DatasetPartition] = []
        pages_fetched = 0
        raw_payloads_written = 0
        records_seen = 0
        catalog_inserted = 0
        completed = False

        while not completed:
            if pages_fetched >= self.max_pages:
                raise RuntimeError("backfill exceeded max_pages before completion")
            cursor_key = json.dumps(cursor, sort_keys=True, separators=(",", ":"), default=str)
            if cursor_key in seen_cursors:
                raise RuntimeError("backfill adapter produced a cursor cycle")
            seen_cursors.add(cursor_key)

            page = adapter.fetch_page(window, cursor)
            pages_fetched += 1
            envelope = self.raw_store.put(
                provider=adapter.provider,
                payload=page.raw_payload,
                received_at=page.received_at,
                observed_at=min((record.observed_at for record in page.records), default=None),
                source_url=page.source_url,
                media_type="application/json",
                attributes={
                    "dataset": adapter.dataset,
                    "schema_version": adapter.schema_version,
                    "cursor": dict(cursor),
                    **dict(page.attributes),
                },
            )
            raw_payloads_written += 1

            normalized = tuple(
                HistoricalRecord(
                    dataset=adapter.dataset,
                    record_id=record.record_id,
                    observed_at=record.observed_at,
                    available_at=record.available_at,
                    source=adapter.source,
                    revision=record.revision,
                    values=record.values,
                    raw_payload_sha256=envelope.payload_sha256,
                )
                for record in page.records
            )
            records_seen += len(normalized)

            grouped: dict[str, list[HistoricalRecord]] = {}
            for record in normalized:
                grouped.setdefault(record.observed_at.strftime("date=%Y-%m-%d"), []).append(record)
            for partition_key, records in sorted(grouped.items()):
                partition = self.partition_store.write_partition(
                    dataset=adapter.dataset,
                    partition_key=partition_key,
                    records=records,
                )
                partitions.append(partition)
                catalog_inserted += self.catalog.add_many(records, partition_path=partition.path)

            completed = page.completed
            next_cursor = None if completed else dict(page.next_cursor or {})
            self.checkpoints.save(
                key,
                cursor=next_cursor or {"completed_at": datetime.now(timezone.utc).isoformat()},
                completed=completed,
            )
            if not completed:
                cursor = next_cursor or {}

        manifest_path: str | None = None
        if partitions:
            manifest = DatasetManifest.build(
                dataset=adapter.dataset,
                schema_version=adapter.schema_version,
                created_at=datetime.now(timezone.utc),
                partitions=partitions,
            )
            manifest_path = str(self.manifest_store.put(manifest))

        return BackfillResult(
            job_key=key,
            dataset=adapter.dataset,
            pages_fetched=pages_fetched,
            raw_payloads_written=raw_payloads_written,
            records_seen=records_seen,
            catalog_records_inserted=catalog_inserted,
            partitions=tuple(partitions),
            manifest_path=manifest_path,
            completed=completed,
            resumed=resumed,
        )
