from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import median

from xrp_regime_engine.models import Candle, DataFlag


@dataclass(frozen=True)
class ConsensusResult:
    value: float | None
    provider_count: int
    input_provider_count: int
    rejected_provider_count: int
    relative_spread: float
    agreement_score: float
    freshness_score: float
    valid: bool
    providers: tuple[str, ...]
    flags: tuple[DataFlag, ...]


def _deduplicate_by_provider(candles: list[Candle]) -> list[Candle]:
    latest: dict[str, Candle] = {}
    for candle in candles:
        provider = candle.provenance.provider
        previous = latest.get(provider)
        if previous is None or candle.close_time > previous.close_time:
            latest[provider] = candle
    return list(latest.values())


def consensus_close(
    candles: list[Candle],
    now: datetime | None = None,
    *,
    max_age_seconds: int = 7200,
    min_provider_count: int = 2,
    max_relative_spread: float = 0.02,
    outlier_deviation: float = 0.03,
    alignment_tolerance_seconds: int = 300,
) -> ConsensusResult:
    """Build a fail-closed median consensus from independent providers.

    A value is returned only when minimum independent coverage, freshness,
    timestamp alignment and price agreement all pass. With fewer than three
    providers no source can be identified as an outlier, so a wide two-source
    spread is treated as a conflict rather than averaged.
    """

    if not candles:
        raise ValueError("no candles supplied")
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")
    if min_provider_count < 2:
        raise ValueError("min_provider_count must be at least 2")
    if max_relative_spread <= 0 or outlier_deviation <= 0:
        raise ValueError("spread thresholds must be positive")
    if alignment_tolerance_seconds < 0:
        raise ValueError("alignment_tolerance_seconds must be non-negative")

    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(UTC)
    unique = _deduplicate_by_provider(candles)
    input_provider_count = len(unique)
    providers = tuple(sorted(item.provenance.provider for item in unique))
    flags: list[DataFlag] = []

    assets = {item.asset for item in unique}
    intervals = {item.interval for item in unique}
    if len(assets) != 1 or len(intervals) != 1:
        raise ValueError("all candles must share the same asset and interval")

    close_times = [item.close_time for item in unique]
    if any(close_time > now for close_time in close_times):
        flags.append(DataFlag.INVALID)
    if (max(close_times) - min(close_times)).total_seconds() > alignment_tolerance_seconds:
        flags.append(DataFlag.CONFLICT)

    filtered = unique
    if len(unique) >= 3:
        center = median(item.close for item in unique)
        filtered = [
            item for item in unique if abs(item.close - center) / center <= outlier_deviation
        ]
        if len(filtered) < len(unique):
            flags.append(DataFlag.OUTLIER)

    provider_count = len(filtered)
    rejected_provider_count = input_provider_count - provider_count
    if provider_count < min_provider_count:
        flags.append(DataFlag.MISSING)

    values = [item.close for item in filtered]
    candidate = median(values) if values else None
    relative_spread = (
        (max(values) - min(values)) / candidate
        if candidate is not None and candidate > 0 and len(values) >= 2
        else 0.0
    )
    agreement_score = max(0.0, 1.0 - min(relative_spread / max_relative_spread, 1.0))
    if relative_spread > max_relative_spread:
        flags.append(DataFlag.CONFLICT)

    ages = [max(0.0, (now - item.close_time).total_seconds()) for item in filtered]
    median_age = median(ages) if ages else float("inf")
    freshness_score = max(0.0, 1.0 - min(median_age / max_age_seconds, 1.0))
    if median_age > max_age_seconds:
        flags.append(DataFlag.STALE)

    flags = list(dict.fromkeys(flags))
    valid = (
        provider_count >= min_provider_count
        and DataFlag.CONFLICT not in flags
        and DataFlag.STALE not in flags
        and DataFlag.INVALID not in flags
        and candidate is not None
    )

    return ConsensusResult(
        value=float(candidate) if valid and candidate is not None else None,
        provider_count=provider_count,
        input_provider_count=input_provider_count,
        rejected_provider_count=rejected_provider_count,
        relative_spread=float(relative_spread),
        agreement_score=float(agreement_score),
        freshness_score=float(freshness_score),
        valid=valid,
        providers=providers,
        flags=tuple(flags),
    )
