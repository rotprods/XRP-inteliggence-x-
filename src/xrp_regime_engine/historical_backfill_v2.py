from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from xrp_regime_engine.historical_contract import FetchReceipt, HistoricalObservation
from xrp_regime_engine.historical_store_v2 import DurableManifest, HistoricalEvidenceStoreV2


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical_cursor(cursor: Mapping[str, object]) -> str:
    return json.dumps(
        dict(cursor),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


@dataclass(frozen=True, slots=True)
class BackfillWindowV2:
    start: datetime
    end: datetime
    interval_seconds: int

    def __post_init__(self) -> None:
        start = _utc(self.start, "start")
        end = _utc(self.end, "end")
        if end <= start:
            raise ValueError("backfill end must be later than start")
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    def identity(self) -> dict[str, object]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "interval_seconds": self.interval_seconds,
        }


@dataclass(frozen=True, slots=True)
class BackfillPageV2:
    raw_payload: bytes
    receipt: FetchReceipt
    observations: tuple[HistoricalObservation, ...]
    partition_key: str | None
    next_cursor: Mapping[str, object] | None
    completed: bool

    def __post_init__(self) -> None:
        if not self.raw_payload:
            raise ValueError("backfill page raw_payload cannot be empty")
        if sha256(self.raw_payload).hexdigest() != self.receipt.payload_sha256:
            raise ValueError("backfill page receipt digest does not match raw payload")
        object.__setattr__(self, "observations", tuple(self.observations))
        if self.observations and not self.partition_key:
            raise ValueError("observations require a partition_key")
        if not self.observations and self.partition_key is not None:
            raise ValueError("empty page cannot declare a partition_key")
        if self.completed and self.next_cursor is not None:
            raise ValueError("completed page cannot expose next_cursor")
        if not self.completed and self.next_cursor is None:
            raise ValueError("incomplete page requires next_cursor")


class HistoricalAdapterV2(Protocol):
    provider: str
    dataset: str
    schema_version: str

    def initial_cursor(self, window: BackfillWindowV2) -> Mapping[str, object]: ...

    def fetch_page(
        self,
        window: BackfillWindowV2,
        cursor: Mapping[str, object],
    ) -> BackfillPageV2: ...


@dataclass(frozen=True, slots=True)
class BackfillRunResultV2:
    job_key: str
    dataset: str
    pages_fetched: int
    observations_seen: int
    completed: bool
    resumed: bool
    manifest: DurableManifest | None


class BackfillRunnerV2:
    def __init__(
        self,
        store: HistoricalEvidenceStoreV2,
        *,
        max_pages: int = 10_000,
        max_empty_pages: int = 10,
    ) -> None:
        if max_pages <= 0:
            raise ValueError("max_pages must be positive")
        if max_empty_pages < 0:
            raise ValueError("max_empty_pages cannot be negative")
        self.store = store
        self.max_pages = max_pages
        self.max_empty_pages = max_empty_pages

    @staticmethod
    def job_key(adapter: HistoricalAdapterV2, window: BackfillWindowV2) -> str:
        material = {
            "provider": adapter.provider,
            "dataset": adapter.dataset,
            "schema_version": adapter.schema_version,
            "window": window.identity(),
        }
        digest = sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return f"backfill:sha256:{digest}"

    @staticmethod
    def _validate_page(
        adapter: HistoricalAdapterV2,
        page: BackfillPageV2,
    ) -> None:
        if page.receipt.provider != adapter.provider:
            raise ValueError("adapter page receipt provider does not match adapter provider")
        for observation in page.observations:
            if observation.dataset != adapter.dataset:
                raise ValueError("adapter page contains observation from another dataset")
            if observation.fetch_id != page.receipt.fetch_id:
                raise ValueError("observation fetch_id does not match page receipt")
            if observation.payload_sha256 != page.receipt.payload_sha256:
                raise ValueError("observation payload digest does not match page receipt")
            if observation.provider != page.receipt.provider:
                raise ValueError("observation provider does not match page receipt")
            if observation.source_id != page.receipt.source_id:
                raise ValueError("observation source_id does not match page receipt")
            if observation.fetched_at != page.receipt.fetched_at:
                raise ValueError("observation fetched_at does not match page receipt")

    def _finalize_from_checkpoint(
        self,
        *,
        adapter: HistoricalAdapterV2,
        checkpoint_updated_at: datetime,
    ) -> DurableManifest:
        return self.store.finalize_manifest(
            dataset=adapter.dataset,
            schema_version=adapter.schema_version,
            created_at=checkpoint_updated_at,
        )

    def run(
        self,
        adapter: HistoricalAdapterV2,
        window: BackfillWindowV2,
    ) -> BackfillRunResultV2:
        key = self.job_key(adapter, window)
        checkpoint = self.store.load_checkpoint(key)
        resumed = checkpoint is not None
        if checkpoint is not None and checkpoint.completed:
            manifest = self._finalize_from_checkpoint(
                adapter=adapter,
                checkpoint_updated_at=checkpoint.updated_at,
            )
            return BackfillRunResultV2(
                job_key=key,
                dataset=adapter.dataset,
                pages_fetched=0,
                observations_seen=0,
                completed=True,
                resumed=True,
                manifest=manifest,
            )

        cursor: Mapping[str, object] = (
            checkpoint.cursor if checkpoint is not None else adapter.initial_cursor(window)
        )
        if not cursor:
            raise ValueError("backfill cursor cannot be empty")

        seen_cursors: set[str] = set()
        pages_fetched = 0
        observations_seen = 0
        empty_pages = 0
        completed = False
        final_receipt_time: datetime | None = None

        while not completed:
            if pages_fetched >= self.max_pages:
                raise RuntimeError("backfill exceeded max_pages before completion")

            cursor_key = _canonical_cursor(cursor)
            seen_cursors.add(cursor_key)

            page = adapter.fetch_page(window, cursor)
            self._validate_page(adapter, page)
            pages_fetched += 1
            observations_seen += len(page.observations)
            final_receipt_time = page.receipt.fetched_at
            self.store.record_fetch(page.raw_payload, page.receipt)

            if page.observations:
                empty_pages = 0
            else:
                empty_pages += 1
                if empty_pages > self.max_empty_pages:
                    raise RuntimeError("backfill exceeded maximum consecutive empty pages")

            if not page.completed:
                if page.next_cursor is None:
                    raise RuntimeError("validated incomplete page lost next_cursor")
                next_cursor_key = _canonical_cursor(page.next_cursor)
                if next_cursor_key == cursor_key or next_cursor_key in seen_cursors:
                    raise RuntimeError("backfill adapter made no forward cursor progress")
                next_cursor: Mapping[str, object] = dict(page.next_cursor)
            else:
                next_cursor = {"completed": True}

            if page.observations:
                if page.partition_key is None:
                    raise RuntimeError("validated observation page lost partition_key")
                self.store.persist_partition_then_checkpoint(
                    dataset=adapter.dataset,
                    partition_key=page.partition_key,
                    observations=page.observations,
                    job_key=key,
                    cursor=next_cursor,
                    completed=page.completed,
                    updated_at=page.receipt.fetched_at,
                )
            else:
                self.store.save_checkpoint(
                    job_key=key,
                    cursor=next_cursor,
                    completed=page.completed,
                    updated_at=page.receipt.fetched_at,
                )

            completed = page.completed
            if not completed:
                cursor = next_cursor

        if final_receipt_time is None:
            raise RuntimeError("completed backfill has no receipt timestamp")
        manifest = self.store.finalize_manifest(
            dataset=adapter.dataset,
            schema_version=adapter.schema_version,
            created_at=final_receipt_time,
        )
        return BackfillRunResultV2(
            job_key=key,
            dataset=adapter.dataset,
            pages_fetched=pages_fetched,
            observations_seen=observations_seen,
            completed=True,
            resumed=resumed,
            manifest=manifest,
        )
