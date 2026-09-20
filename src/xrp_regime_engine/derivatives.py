from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True)
class FundingState:
    symbol: str
    observed_at: datetime
    mark_price: float
    index_price: float
    funding_rate: float
    next_funding_at: datetime

    def __post_init__(self) -> None:
        for value in (self.mark_price, self.index_price, self.funding_rate):
            if not isfinite(value):
                raise ValueError("derivatives values must be finite")
        if self.mark_price <= 0 or self.index_price <= 0:
            raise ValueError("mark and index prices must be positive")

    @property
    def basis_bps(self) -> float:
        return (self.mark_price - self.index_price) / self.index_price * 10_000


@dataclass(frozen=True)
class OpenInterestState:
    symbol: str
    observed_at: datetime
    open_interest: float

    def __post_init__(self) -> None:
        if not isfinite(self.open_interest) or self.open_interest < 0:
            raise ValueError("open interest must be finite and non-negative")


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
