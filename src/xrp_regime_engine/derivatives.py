from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _validate_optional_provenance(
    observed_at: datetime,
    available_at: datetime | None,
    fetched_at: datetime | None,
) -> None:
    _require_aware(observed_at, "observed_at")
    if available_at is not None:
        _require_aware(available_at, "available_at")
        if available_at < observed_at:
            raise ValueError("available_at cannot precede observed_at")
    if fetched_at is not None:
        _require_aware(fetched_at, "fetched_at")
        if fetched_at < observed_at:
            raise ValueError("fetched_at cannot precede observed_at")
    if available_at is not None and fetched_at is not None and available_at > fetched_at:
        raise ValueError("available_at cannot follow fetched_at")


def _validate_payload_digest(value: str | None) -> None:
    if value is None:
        return
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("payload_sha256 must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True)
class FundingState:
    symbol: str
    observed_at: datetime
    mark_price: float
    index_price: float
    funding_rate: float
    next_funding_at: datetime
    available_at: datetime | None = None
    fetched_at: datetime | None = None
    payload_sha256: str | None = None

    def __post_init__(self) -> None:
        for value in (self.mark_price, self.index_price, self.funding_rate):
            if not isfinite(value):
                raise ValueError("derivatives values must be finite")
        if self.mark_price <= 0 or self.index_price <= 0:
            raise ValueError("mark and index prices must be positive")
        _require_aware(self.next_funding_at, "next_funding_at")
        _validate_optional_provenance(self.observed_at, self.available_at, self.fetched_at)
        _validate_payload_digest(self.payload_sha256)

    @property
    def basis_bps(self) -> float:
        return (self.mark_price - self.index_price) / self.index_price * 10_000

    @property
    def provenance_complete(self) -> bool:
        return self.available_at is not None and self.fetched_at is not None


@dataclass(frozen=True)
class OpenInterestState:
    symbol: str
    observed_at: datetime
    open_interest: float
    available_at: datetime | None = None
    fetched_at: datetime | None = None
    payload_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.open_interest) or self.open_interest < 0:
            raise ValueError("open interest must be finite and non-negative")
        _validate_optional_provenance(self.observed_at, self.available_at, self.fetched_at)
        _validate_payload_digest(self.payload_sha256)

    @property
    def provenance_complete(self) -> bool:
        return self.available_at is not None and self.fetched_at is not None


@dataclass(frozen=True)
class DerivativesRiskState:
    symbol: str
    observed_at: datetime
    funding_rate: float
    basis_bps: float
    open_interest: float | None
    quality_flags: tuple[str, ...]


def assess_derivatives_risk(
    funding: FundingState,
    open_interest: OpenInterestState | None = None,
) -> DerivativesRiskState:
    flags: list[str] = []
    if funding.funding_rate > 0.0005:
        flags.append("ELEVATED_POSITIVE_FUNDING")
    elif funding.funding_rate < -0.0005:
        flags.append("ELEVATED_NEGATIVE_FUNDING")
    if abs(funding.basis_bps) > 25:
        flags.append("WIDE_MARK_INDEX_BASIS")
    if open_interest is None:
        flags.append("OPEN_INTEREST_NO_DATA")
    return DerivativesRiskState(
        symbol=funding.symbol,
        observed_at=funding.observed_at,
        funding_rate=funding.funding_rate,
        basis_bps=funding.basis_bps,
        open_interest=None if open_interest is None else open_interest.open_interest,
        quality_flags=tuple(flags),
    )
