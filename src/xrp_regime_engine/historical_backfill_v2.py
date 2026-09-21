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
class BackfillPage:
    observations: tuple[HistoricalObservation, ...]
    next_cursor: Mapping[str, object] | None


class HistoricalBackfillProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def source_id(self) -> str: ...

    def fetch_page(self, cursor: Mapping[str, object] | None) -> BackfillPage: ...


@dataclass(frozen=True, slots=True)
class BackfillRunReceipt:
    run_id: str
    run_sha256: str
    provider: str
    source_id: str
    started_at: datetime
    completed_at: datetime
    page_count: int
    observation_count: int
    final_cursor: Mapping[str, object] | None
    manifest: DurableManifest

    def to_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "run_sha256": self.run_sha256,
            "provider": self.provider,
            "source_id": self.source_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "page_count": self.page_count,
            "observation_count": self.observation_count,
            "final_cursor": dict(self.final_cursor) if self.final_cursor is not None else None,
            "manifest": self.manifest.to_payload(),
        }


def _build_run_receipt(
    *,
    provider: HistoricalBackfillProvider,
    started_at: datetime,
    completed_at: datetime,
    page_count: int,
    observation_count: int,
    final_cursor: Mapping[str, object] | None,
    manifest: DurableManifest,
) -> BackfillRunReceipt:
    material: dict[str, object] = {
        "provider": provider.provider_id,
        "source_id": provider.source_id,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "page_count": page_count,
        "observation_count": observation_count,
        "final_cursor": dict(final_cursor) if final_cursor is not None else None,
        "manifest_id": manifest.manifest_id,
        "manifest_sha256": manifest.manifest_sha256,
    }
    digest = sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return BackfillRunReceipt(
        run_id=f"backfill:sha256:{digest}",
        run_sha256=digest,
        provider=provider.provider_id,
        source_id=provider.source_id,
        started_at=started_at,
        completed_at=completed_at,
        page_count=page_count,
        observation_count=observation_count,
        final_cursor=final_cursor,
        manifest=manifest,
    )


def run_historical_backfill(
    *,
    provider: HistoricalBackfillProvider,
    store: HistoricalEvidenceStoreV2,
    started_at: datetime,
    completed_at: datetime,
    start_cursor: Mapping[str, object] | None = None,
    max_pages: int = 10_000,
) -> BackfillRunReceipt:
    started = _utc(started_at, "started_at")
    completed = _utc(completed_at, "completed_at")
    if completed < started:
        raise ValueError("completed_at cannot precede started_at")
    if max_pages < 1:
        raise ValueError("max_pages must be positive")

    cursor = dict(start_cursor) if start_cursor is not None else None
    page_count = 0
    observation_count = 0
    seen_cursors: set[str] = set()

    while page_count < max_pages:
        cursor_key = _canonical_cursor(cursor or {})
        if cursor_key in seen_cursors:
            raise RuntimeError("backfill cursor cycle detected")
        seen_cursors.add(cursor_key)

        page = provider.fetch_page(cursor)
        page_count += 1
        if not page.observations and page.next_cursor is not None:
            raise RuntimeError("backfill provider returned empty non-terminal page")

        for observation in page.observations:
            if observation.provider != provider.provider_id:
                raise ValueError("backfill observation provider mismatch")
            if observation.source_id != provider.source_id:
                raise ValueError("backfill observation source_id mismatch")
            store.save_observation(observation)
            observation_count += 1

        if page.next_cursor is None:
            cursor = None
            break
        cursor = dict(page.next_cursor)
    else:
        raise RuntimeError("backfill exceeded max_pages")

    manifest = store.build_manifest()
    return _build_run_receipt(
        provider=provider,
        started_at=started,
        completed_at=completed,
        page_count=page_count,
        observation_count=observation_count,
        final_cursor=cursor,
        manifest=manifest,
    )
