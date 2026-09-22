from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from math import isfinite
from typing import Any


class AuthorityClass(StrEnum):
    SOURCE_OF_TRUTH = "SOURCE_OF_TRUTH"
    DERIVED = "DERIVED"
    COORDINATION = "COORDINATION"
    OBSERVER = "OBSERVER"
    FORBIDDEN_EXECUTION = "FORBIDDEN_EXECUTION"


class GateStatus(StrEnum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    DEGRADED = "DEGRADED"
    NO_DATA = "NO_DATA"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    provider: str
    endpoint: str
    instrument: str
    observed_at: datetime
    available_at: datetime
    fetched_at: datetime
    raw_sha256: str
    authority: AuthorityClass = AuthorityClass.SOURCE_OF_TRUTH
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("observed_at", self.observed_at),
            ("available_at", self.available_at),
            ("fetched_at", self.fetched_at),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if not self.observed_at <= self.available_at <= self.fetched_at:
            raise ValueError("evidence timestamps must satisfy observed <= available <= fetched")
        if len(self.raw_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.raw_sha256):
            raise ValueError("raw_sha256 must be lowercase SHA-256")
        if self.authority is AuthorityClass.FORBIDDEN_EXECUTION:
            raise ValueError("execution-authority evidence cannot enter MarketStateSnapshot")


@dataclass(frozen=True)
class FeatureValue:
    name: str
    value: float | str | bool | None
    timeframe: str | None = None
    evidence_ids: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.value, float) and not isfinite(self.value):
            raise ValueError("feature values must be finite")


@dataclass(frozen=True)
class Contradiction:
    code: str
    statement: str
    evidence_for: tuple[str, ...]
    evidence_against: tuple[str, ...]
    severity: str = "WARNING"


@dataclass(frozen=True)
class GateResult:
    gate: str
    status: GateStatus
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketStateSnapshot:
    as_of: datetime
    instruments: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]
    features: tuple[FeatureValue, ...]
    contradictions: tuple[Contradiction, ...] = ()
    gates: tuple[GateResult, ...] = ()
    missing_data: tuple[str, ...] = ()
    decision_authority: bool = False
    execution_weight: float = 0.0
    schema_version: str = "market-state-v2"
    snapshot_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if self.decision_authority:
            raise ValueError("MarketStateSnapshot cannot grant decision authority")
        if self.execution_weight != 0.0:
            raise ValueError("MarketStateSnapshot execution_weight must remain zero")
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate evidence_id")
        known = set(ids)
        for feature in self.features:
            unknown = set(feature.evidence_ids) - known
            if unknown:
                raise ValueError(f"feature references unknown evidence: {sorted(unknown)}")
        for item in self.evidence:
            if item.fetched_at > self.as_of:
                raise ValueError("future-fetched evidence cannot enter snapshot")
        object.__setattr__(self, "snapshot_id", self._digest())

    def _canonical_payload(self) -> dict[str, Any]:
        def encode(value: Any) -> Any:
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, StrEnum):
                return value.value
            if isinstance(value, tuple):
                return [encode(v) for v in value]
            if isinstance(value, list):
                return [encode(v) for v in value]
            if isinstance(value, dict):
                return {k: encode(v) for k, v in sorted(value.items())}
            return value

        payload = asdict(self)
        payload.pop("snapshot_id", None)
        return encode(payload)

    def _digest(self) -> str:
        raw = json.dumps(
            self._canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def overall_status(self) -> GateStatus:
        statuses = {gate.status for gate in self.gates}
        if GateStatus.QUARANTINED in statuses:
            return GateStatus.QUARANTINED
        if GateStatus.NO_DATA in statuses:
            return GateStatus.NO_DATA
        if GateStatus.DEGRADED in statuses:
            return GateStatus.DEGRADED
        if GateStatus.PASS_WITH_WARNINGS in statuses or self.contradictions:
            return GateStatus.PASS_WITH_WARNINGS
        return GateStatus.PASS
