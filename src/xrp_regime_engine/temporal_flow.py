from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite

SUPPORTED_WINDOWS_SECONDS = frozenset({60, 300, 900, 3600})
FRESHNESS_LIMIT_SECONDS = {
    60: 15,
    300: 60,
    900: 180,
    3600: 600,
}


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _require_finite(value: float, field: str) -> None:
    if not isfinite(value):
        raise ValueError(f"{field} must be finite")


@dataclass(frozen=True)
class TemporalFlowSample:
    symbol: str
    observed_at: datetime
    available_at: datetime
    fetched_at: datetime
    mid_price: float
    depth_imbalance_25bps: float
    aggressive_buy_notional: float
    aggressive_sell_notional: float
    open_interest: float | None = None
    funding_rate: float | None = None
    basis_bps: float | None = None

    def __post_init__(self) -> None:
        for field, value in (
            ("observed_at", self.observed_at),
            ("available_at", self.available_at),
            ("fetched_at", self.fetched_at),
        ):
            _require_aware(value, field)
        if not self.observed_at <= self.available_at <= self.fetched_at:
            raise ValueError("microstructure timestamps must satisfy observed <= available <= fetched")
        if not self.symbol:
            raise ValueError("symbol is required")
        for field, value in (
            ("mid_price", self.mid_price),
            ("depth_imbalance_25bps", self.depth_imbalance_25bps),
            ("aggressive_buy_notional", self.aggressive_buy_notional),
            ("aggressive_sell_notional", self.aggressive_sell_notional),
        ):
            _require_finite(value, field)
        if self.mid_price <= 0:
            raise ValueError("mid_price must be positive")
        if not -1 <= self.depth_imbalance_25bps <= 1:
            raise ValueError("depth imbalance must be within [-1, 1]")
        if self.aggressive_buy_notional < 0 or self.aggressive_sell_notional < 0:
            raise ValueError("aggressive notionals must be non-negative")
        for field, value in (
            ("open_interest", self.open_interest),
            ("funding_rate", self.funding_rate),
            ("basis_bps", self.basis_bps),
        ):
            if value is not None:
                _require_finite(value, field)
        if self.open_interest is not None and self.open_interest < 0:
            raise ValueError("open_interest must be non-negative")


@dataclass(frozen=True)
class TemporalFlowWindow:
    symbol: str
    prediction_time: datetime
    window_seconds: int
    sample_count: int
    first_observed_at: datetime
    last_observed_at: datetime
    mid_return_bps: float
    mean_depth_imbalance_25bps: float
    aggressive_buy_notional: float
    aggressive_sell_notional: float
    cvd_quote: float
    taker_imbalance: float
    open_interest_delta_pct: float | None
    funding_delta_bps: float | None
    basis_delta_bps: float | None
    last_sample_age_seconds: float
    freshness_limit_seconds: int
    regime_eligible: bool
    quality_flags: tuple[str, ...]
    execution_weight: float = 0.0


def _first_last(values: list[float | None]) -> tuple[float, float] | None:
    present = [value for value in values if value is not None]
    if len(present) < 2:
        return None
    return present[0], present[-1]


def build_temporal_window(
    samples: tuple[TemporalFlowSample, ...],
    *,
    prediction_time: datetime,
    window_seconds: int,
) -> TemporalFlowWindow | None:
    _require_aware(prediction_time, "prediction_time")
    if window_seconds not in SUPPORTED_WINDOWS_SECONDS:
        raise ValueError("unsupported temporal window")
    if not samples:
        return None

    symbols = {sample.symbol for sample in samples}
    if len(symbols) != 1:
        raise ValueError("temporal window cannot mix symbols")

    start = prediction_time - timedelta(seconds=window_seconds)
    eligible = sorted(
        (
            sample
            for sample in samples
            if start < sample.observed_at <= prediction_time
            and sample.available_at <= prediction_time
            and sample.fetched_at <= prediction_time
        ),
        key=lambda sample: (sample.observed_at, sample.available_at, sample.fetched_at),
    )
    if not eligible:
        return None

    buys = sum(sample.aggressive_buy_notional for sample in eligible)
    sells = sum(sample.aggressive_sell_notional for sample in eligible)
    total = buys + sells
    cvd = buys - sells
    first = eligible[0]
    last = eligible[-1]

    oi_pair = _first_last([sample.open_interest for sample in eligible])
    funding_pair = _first_last([sample.funding_rate for sample in eligible])
    basis_pair = _first_last([sample.basis_bps for sample in eligible])

    oi_delta_pct = None
    if oi_pair is not None and oi_pair[0] > 0:
        oi_delta_pct = (oi_pair[1] - oi_pair[0]) / oi_pair[0]

    flags: list[str] = []
    coverage_seconds = (last.observed_at - first.observed_at).total_seconds()
    if len(eligible) < 2 or coverage_seconds < window_seconds * 0.5:
        flags.append("SPARSE_WINDOW")
    if oi_pair is None:
        flags.append("OPEN_INTEREST_NO_DATA")
    if funding_pair is None:
        flags.append("FUNDING_NO_DATA")
    if basis_pair is None:
        flags.append("BASIS_NO_DATA")

    freshness_limit = FRESHNESS_LIMIT_SECONDS[window_seconds]
    last_sample_age = (prediction_time - last.observed_at).total_seconds()
    if last_sample_age > freshness_limit:
        flags.append("STALE_WINDOW")

    ingestion_lag = (last.fetched_at - last.observed_at).total_seconds()
    if ingestion_lag > freshness_limit:
        flags.append("INGESTION_LAG")

    regime_eligible = not any(flag in {"STALE_WINDOW", "INGESTION_LAG"} for flag in flags)

    return TemporalFlowWindow(
        symbol=first.symbol,
        prediction_time=prediction_time,
        window_seconds=window_seconds,
        sample_count=len(eligible),
        first_observed_at=first.observed_at,
        last_observed_at=last.observed_at,
        mid_return_bps=(last.mid_price / first.mid_price - 1) * 10_000,
        mean_depth_imbalance_25bps=sum(
            sample.depth_imbalance_25bps for sample in eligible
        )
        / len(eligible),
        aggressive_buy_notional=buys,
        aggressive_sell_notional=sells,
        cvd_quote=cvd,
        taker_imbalance=0.0 if total == 0 else cvd / total,
        open_interest_delta_pct=oi_delta_pct,
        funding_delta_bps=(
            None if funding_pair is None else (funding_pair[1] - funding_pair[0]) * 10_000
        ),
        basis_delta_bps=None if basis_pair is None else basis_pair[1] - basis_pair[0],
        last_sample_age_seconds=last_sample_age,
        freshness_limit_seconds=freshness_limit,
        regime_eligible=regime_eligible,
        quality_flags=tuple(flags),
        execution_weight=0.0,
    )
