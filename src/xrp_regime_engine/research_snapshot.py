from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from xrp_regime_engine.historical_store import (
    HistoricalRecord,
    PointInTimeCatalog,
    atomic_write,
    canonical_json_bytes,
    sha256_hex,
    utc,
)


class SnapshotUnavailable(RuntimeError):
    """A required point-in-time dataset could not satisfy its contract."""


@dataclass(frozen=True, slots=True)
class DatasetRequirement:
    dataset: str
    lookback: timedelta
    minimum_records: int
    maximum_latest_age: timedelta
    required: bool = True

    def __post_init__(self) -> None:
        if not self.dataset:
            raise ValueError("dataset is required")
        if self.lookback <= timedelta(0):
            raise ValueError("lookback must be positive")
        if self.minimum_records < 0:
            raise ValueError("minimum_records cannot be negative")
        if self.maximum_latest_age < timedelta(0):
            raise ValueError("maximum_latest_age cannot be negative")


@dataclass(frozen=True, slots=True)
class SnapshotDataset:
    dataset: str
    required: bool
    record_count: int
    minimum_observed_at: datetime | None
    maximum_observed_at: datetime | None
    maximum_available_at: datetime | None
    record_hashes: tuple[str, ...]
    records: tuple[HistoricalRecord, ...]

    def to_dict(self, *, include_records: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "dataset": self.dataset,
            "required": self.required,
            "record_count": self.record_count,
            "minimum_observed_at": self.minimum_observed_at.isoformat()
            if self.minimum_observed_at
            else None,
            "maximum_observed_at": self.maximum_observed_at.isoformat()
            if self.maximum_observed_at
            else None,
            "maximum_available_at": self.maximum_available_at.isoformat()
            if self.maximum_available_at
            else None,
            "record_hashes": list(self.record_hashes),
        }
        if include_records:
            payload["records"] = [record.to_dict() for record in self.records]
        return payload


@dataclass(frozen=True, slots=True)
class ResearchSnapshot:
    decision_time: datetime
    created_at: datetime
    datasets: tuple[SnapshotDataset, ...]
    record_count: int
    snapshot_sha256: str

    def to_dict(self, *, include_records: bool = True) -> dict[str, Any]:
        return {
            "decision_time": self.decision_time.isoformat(),
            "created_at": self.created_at.isoformat(),
            "datasets": [dataset.to_dict(include_records=include_records) for dataset in self.datasets],
            "record_count": self.record_count,
            "snapshot_sha256": self.snapshot_sha256,
        }


class ResearchSnapshotBuilder:
    def __init__(self, catalog: PointInTimeCatalog) -> None:
        self.catalog = catalog

    def build(
        self,
        *,
        decision_time: datetime,
        requirements: Iterable[DatasetRequirement],
        created_at: datetime | None = None,
    ) -> ResearchSnapshot:
        decision = utc(decision_time)
        created = utc(created_at or datetime.now(timezone.utc))
        if created < decision:
            raise ValueError("snapshot created_at cannot precede decision_time")
        requirements_tuple = tuple(requirements)
        if not requirements_tuple:
            raise ValueError("at least one dataset requirement is required")
        names = [requirement.dataset for requirement in requirements_tuple]
        if len(names) != len(set(names)):
            raise ValueError("dataset requirements must be unique")

        datasets: list[SnapshotDataset] = []
        blockers: list[str] = []
        for requirement in sorted(requirements_tuple, key=lambda item: item.dataset):
            lookback_start = decision - requirement.lookback
            rows = tuple(
                record
                for record in self.catalog.as_of(
                    dataset=requirement.dataset,
                    decision_time=decision,
                )
                if lookback_start <= record.observed_at <= decision
            )
            for record in rows:
                if record.available_at > decision:
                    raise RuntimeError(
                        f"catalog returned future data for {requirement.dataset}: {record.record_id}"
                    )
            ordered = tuple(
                sorted(
                    rows,
                    key=lambda record: (
                        record.observed_at,
                        record.record_id,
                        record.revision,
                        record.source,
                    ),
                )
            )
            latest = max((record.observed_at for record in ordered), default=None)
            if requirement.required:
                if len(ordered) < requirement.minimum_records:
                    blockers.append(
                        f"{requirement.dataset}: {len(ordered)} record(s), minimum {requirement.minimum_records}"
                    )
                elif latest is None or decision - latest > requirement.maximum_latest_age:
                    blockers.append(
                        f"{requirement.dataset}: latest observation exceeds freshness contract"
                    )
            datasets.append(
                SnapshotDataset(
                    dataset=requirement.dataset,
                    required=requirement.required,
                    record_count=len(ordered),
                    minimum_observed_at=min(
                        (record.observed_at for record in ordered),
                        default=None,
                    ),
                    maximum_observed_at=latest,
                    maximum_available_at=max(
                        (record.available_at for record in ordered),
                        default=None,
                    ),
                    record_hashes=tuple(record.canonical_sha256 for record in ordered),
                    records=ordered,
                )
            )

        if blockers:
            raise SnapshotUnavailable("; ".join(blockers))

        unsigned = {
            "decision_time": decision.isoformat(),
            "datasets": [dataset.to_dict(include_records=False) for dataset in datasets],
            "record_count": sum(dataset.record_count for dataset in datasets),
        }
        snapshot_hash = sha256_hex(canonical_json_bytes(unsigned))
        return ResearchSnapshot(
            decision_time=decision,
            created_at=created,
            datasets=tuple(datasets),
            record_count=unsigned["record_count"],
            snapshot_sha256=snapshot_hash,
        )


class ResearchSnapshotStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def put(self, snapshot: ResearchSnapshot) -> Path:
        relative = (
            Path("research_snapshots")
            / snapshot.decision_time.strftime("%Y/%m/%d")
            / f"{snapshot.snapshot_sha256}.json"
        )
        path = self.root / relative
        payload = canonical_json_bytes(snapshot.to_dict(include_records=True)) + b"\n"
        if path.exists():
            if path.read_bytes() != payload:
                raise RuntimeError("research snapshot collision or corruption")
        else:
            atomic_write(path, payload)
        return relative

    def read(self, relative_path: str | Path) -> Mapping[str, Any]:
        path = (self.root / relative_path).resolve()
        root = self.root.resolve()
        if root not in path.parents:
            raise ValueError("research snapshot path escapes its root")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise RuntimeError("research snapshot root must be an object")
        datasets = payload.get("datasets")
        if not isinstance(datasets, list):
            raise RuntimeError("research snapshot has no dataset list")
        unsigned = {
            "decision_time": payload.get("decision_time"),
            "datasets": [
                {key: value for key, value in dataset.items() if key != "records"}
                for dataset in datasets
            ],
            "record_count": payload.get("record_count"),
        }
        if sha256_hex(canonical_json_bytes(unsigned)) != payload.get("snapshot_sha256"):
            raise RuntimeError("research snapshot integrity check failed")
        return payload
