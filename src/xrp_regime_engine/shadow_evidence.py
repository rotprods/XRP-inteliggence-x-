from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from xrp_regime_engine.consensus import ConsensusResult
from xrp_regime_engine.temporal_alignment import AlignedTemporalWindow
from xrp_regime_engine.trade_attribution import DepthTradeCompatibility


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _normalize_asset(value: str) -> str:
    normalized = value.replace("_", "").replace("-", "").upper()
    if not normalized:
        raise ValueError("asset is required")
    return normalized


@dataclass(frozen=True)
class IndependentPriceAnchor:
    asset: str
    observed_at: datetime
    available_at: datetime
    fetched_at: datetime
    consensus: ConsensusResult
    source_family: str = "binance"

    def __post_init__(self) -> None:
        for field, value in (
            ("observed_at", self.observed_at),
            ("available_at", self.available_at),
            ("fetched_at", self.fetched_at),
        ):
            _require_aware(value, field)
        if not self.observed_at <= self.available_at <= self.fetched_at:
            raise ValueError("anchor timestamps must satisfy observed <= available <= fetched")
        _normalize_asset(self.asset)
        if not self.source_family:
            raise ValueError("source_family is required")


@dataclass(frozen=True)
class ShadowEvidenceVector:
    symbol: str
    prediction_time: datetime
    window_seconds: int
    independent_price: float
    independent_provider_count: int
    independent_external_provider_count: int
    independent_providers: tuple[str, ...]
    consensus_agreement_score: float
    consensus_freshness_score: float
    mid_return_bps: float
    mean_depth_imbalance_25bps: float
    cvd_quote: float
    taker_imbalance: float
    open_interest_delta_pct: float | None
    funding_delta_bps: float | None
    basis_delta_bps: float | None
    depth_trade_coverage_ratio: float | None
    removal_candidate_residual_notional: float | None
    quality_flags: tuple[str, ...]
    calibrated: bool = False
    probability: None = None
    decision_authority: bool = False
    execution_weight: float = 0.0


def build_shadow_evidence_vector(
    aligned: AlignedTemporalWindow,
    *,
    independent_anchor: IndependentPriceAnchor,
    compatibility: DepthTradeCompatibility | None = None,
) -> ShadowEvidenceVector | None:
    """Assemble point-in-time evidence without producing a prediction or trade signal."""
    if not aligned.evidence_eligible or aligned.window is None:
        return None

    window = aligned.window
    if _normalize_asset(independent_anchor.asset) != _normalize_asset(window.symbol):
        raise ValueError("independent consensus asset must match temporal window symbol")
    if independent_anchor.fetched_at > window.prediction_time:
        return None

    consensus = independent_anchor.consensus
    external_providers = tuple(
        provider
        for provider in consensus.providers
        if not provider.lower().startswith(independent_anchor.source_family.lower())
    )
    if (
        not consensus.valid
        or consensus.value is None
        or consensus.provider_count < 2
        or not external_providers
    ):
        return None

    coverage_ratio: float | None = None
    removal_residual: float | None = None
    flags = list(aligned.quality_flags)
    flags.extend(("UNCALIBRATED_SHADOW_ONLY", "INDEPENDENT_PRICE_CONSENSUS"))

    if compatibility is not None:
        if compatibility.symbol != window.symbol:
            raise ValueError("depth/trade compatibility symbol must match temporal window")
        if compatibility.prediction_time != window.prediction_time:
            raise ValueError("depth/trade compatibility prediction_time must match temporal window")
        if not compatibility.point_in_time_eligible or not compatibility.evidence_eligible:
            return None
        coverage_ratio = compatibility.removal_coverage_ratio
        removal_residual = compatibility.removal_candidate_residual_notional
        flags.extend(compatibility.quality_flags)

    flags.extend(f"CONSENSUS_{flag.value}" for flag in consensus.flags)
    return ShadowEvidenceVector(
        symbol=window.symbol,
        prediction_time=window.prediction_time,
        window_seconds=window.window_seconds,
        independent_price=consensus.value,
        independent_provider_count=consensus.provider_count,
        independent_external_provider_count=len(external_providers),
        independent_providers=consensus.providers,
        consensus_agreement_score=consensus.agreement_score,
        consensus_freshness_score=consensus.freshness_score,
        mid_return_bps=window.mid_return_bps,
        mean_depth_imbalance_25bps=window.mean_depth_imbalance_25bps,
        cvd_quote=window.cvd_quote,
        taker_imbalance=window.taker_imbalance,
        open_interest_delta_pct=window.open_interest_delta_pct,
        funding_delta_bps=window.funding_delta_bps,
        basis_delta_bps=window.basis_delta_bps,
        depth_trade_coverage_ratio=coverage_ratio,
        removal_candidate_residual_notional=removal_residual,
        quality_flags=tuple(dict.fromkeys(flags)),
        calibrated=False,
        probability=None,
        decision_authority=False,
        execution_weight=0.0,
    )
