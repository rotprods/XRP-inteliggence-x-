from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _sha256_or_none(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return normalized


def _finite_optional(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return float(value)


def _non_negative_optional(value: float | None, field_name: str) -> float | None:
    candidate = _finite_optional(value, field_name)
    if candidate is not None and candidate < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return candidate


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Horizon(StrEnum):
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class RegimeLabel(StrEnum):
    STRONG_BULL = "STRONG_BULL"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    STRONG_BEAR = "STRONG_BEAR"
    DEGRADED = "DEGRADED"


class DataFlag(StrEnum):
    STALE = "STALE"
    OUTLIER = "OUTLIER"
    CONFLICT = "CONFLICT"
    MISSING = "MISSING"
    SYNTHETIC = "SYNTHETIC"
    REVISED = "REVISED"
    INVALID = "INVALID"


class Provenance(StrictModel):
    provider: str = Field(min_length=1)
    source_uri: str | None = None
    observed_at: datetime
    available_at: datetime
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload_hash: str | None = None
    flags: list[DataFlag] = Field(default_factory=list)

    @field_validator("observed_at", "available_at", "fetched_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @field_validator("payload_hash")
    @classmethod
    def validate_payload_hash(cls, value: str | None) -> str | None:
        return _sha256_or_none(value, "payload_hash")

    @model_validator(mode="after")
    def validate_temporal_order(self) -> Provenance:
        if self.available_at < self.observed_at:
            raise ValueError("available_at cannot precede observed_at")
        if self.fetched_at < self.available_at:
            raise ValueError("fetched_at cannot precede available_at")
        return self


class Candle(StrictModel):
    asset: str = Field(min_length=1)
    interval: str = Field(min_length=1)
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    provenance: Provenance

    @field_validator("open_time", "close_time")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @field_validator("open", "high", "low", "close")
    @classmethod
    def validate_price(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("OHLC prices must be finite and strictly positive")
        return float(value)

    @field_validator("volume")
    @classmethod
    def validate_volume(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("volume must be finite and non-negative")
        return float(value)

    @model_validator(mode="after")
    def validate_candle_geometry(self) -> Candle:
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be later than open_time")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be greater than or equal to open, close and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be less than or equal to open, close and high")
        if self.provenance.observed_at < self.close_time:
            raise ValueError("candle provenance cannot be observed before candle close")
        # Provenance already guarantees available_at >= observed_at, so checking
        # available_at against close_time again would be an unreachable branch.
        return self


class AssetObservation(StrictModel):
    asset: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    observed_at: datetime
    available_at: datetime
    provenance: Provenance
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at", "available_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("observation values must be finite")
        return float(value)

    @model_validator(mode="after")
    def validate_temporal_order(self) -> AssetObservation:
        # Provenance already enforces available_at >= observed_at and must match the
        # observation below, so a second ordering branch here would be unreachable.
        if self.provenance.observed_at != self.observed_at:
            raise ValueError("observation and provenance observed_at must match")
        if self.provenance.available_at != self.available_at:
            raise ValueError("observation and provenance available_at must match")
        return self


class DerivativesSnapshot(StrictModel):
    asset: str = Field(min_length=1)
    observed_at: datetime
    open_interest_usd: float | None = None
    funding_rate: float | None = None
    futures_basis_pct: float | None = None
    liquidations_long_usd: float | None = None
    liquidations_short_usd: float | None = None
    long_short_ratio: float | None = None
    taker_buy_sell_ratio: float | None = None
    provenance: list[Provenance] = Field(default_factory=list)

    @field_validator("observed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @field_validator("funding_rate", "futures_basis_pct")
    @classmethod
    def validate_signed_metrics(
        cls,
        value: float | None,
        info: Any,
    ) -> float | None:
        return _finite_optional(value, info.field_name)

    @field_validator(
        "open_interest_usd",
        "liquidations_long_usd",
        "liquidations_short_usd",
        "long_short_ratio",
        "taker_buy_sell_ratio",
    )
    @classmethod
    def validate_non_negative_metrics(
        cls,
        value: float | None,
        info: Any,
    ) -> float | None:
        return _non_negative_optional(value, info.field_name)


class ProviderHealth(StrictModel):
    provider: str = Field(min_length=1)
    checked_at: datetime
    status: str = Field(min_length=1)
    latency_ms: float | None = Field(default=None, ge=0)
    last_observation_at: datetime | None = None
    freshness_score: float = Field(ge=0, le=1)
    agreement_score: float = Field(ge=0, le=1)
    error: str | None = None

    @field_validator("checked_at", "last_observation_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None


class ComponentScores(StrictModel):
    macro: float = Field(ge=0, le=100)
    crypto: float = Field(ge=0, le=100)
    xrp_relative: float = Field(ge=0, le=100)
    derivatives: float = Field(ge=0, le=100)
    xrpl: float = Field(ge=0, le=100)
    data_quality: float = Field(ge=0, le=100)


class RegimeSnapshot(StrictModel):
    asset: str = "XRP"
    horizon: Horizon
    generated_at: datetime
    regime: RegimeLabel
    policy_version: str = Field(min_length=1)
    policy_digest: str
    bull_score: float = Field(ge=0, le=100)
    bear_score: float = Field(ge=0, le=100)
    squeeze_risk: float = Field(ge=0, le=100)
    distribution_risk: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    data_confidence: float = Field(ge=0, le=1)
    model_confidence: float = Field(ge=0, le=1)
    directional_conviction: float = Field(ge=0, le=1)
    output_blocked: bool = False
    block_reasons: list[str] = Field(default_factory=list)
    components: ComponentScores
    component_coverage: dict[str, float] = Field(default_factory=dict)
    key_drivers: list[str]
    invalidations: list[str]
    data_flags: list[DataFlag] = Field(default_factory=list)
    historical_analogues: list[dict[str, float | str]] = Field(default_factory=list)
    feature_hash: str
    feature_values: dict[str, float | None] = Field(default_factory=dict)

    @field_validator("generated_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @field_validator("policy_digest", "feature_hash")
    @classmethod
    def validate_digest(cls, value: str, info: Any) -> str:
        # The field type is non-optional; Pydantic rejects None before this validator.
        validated = _sha256_or_none(value, info.field_name)
        assert validated is not None
        return validated

    @field_validator("component_coverage")
    @classmethod
    def validate_component_coverage(cls, value: dict[str, float]) -> dict[str, float]:
        for name, coverage in value.items():
            if not math.isfinite(coverage) or not 0 <= coverage <= 1:
                raise ValueError(f"component coverage {name!r} must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def validate_snapshot_semantics(self) -> RegimeSnapshot:
        if not math.isclose(self.bull_score + self.bear_score, 100.0, abs_tol=0.02):
            raise ValueError("bull_score and bear_score must sum to 100")
        if self.output_blocked and not self.block_reasons:
            raise ValueError("blocked output requires at least one block reason")
        if self.output_blocked != (self.regime is RegimeLabel.DEGRADED):
            raise ValueError("DEGRADED regime and output_blocked must have identical state")
        return self


class AlertEvent(StrictModel):
    alert_id: str = Field(min_length=1)
    created_at: datetime
    severity: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    asset: str = Field(min_length=1)
    horizon: Horizon
    summary: str = Field(min_length=1)
    dedupe_key: str = Field(min_length=1)
    payload: dict[str, Any]

    @field_validator("created_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _as_utc(value)
