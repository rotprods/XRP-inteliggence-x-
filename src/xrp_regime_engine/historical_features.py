from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from math import isfinite

from xrp_regime_engine.evidence_lineage import ShadowEvidenceLineage

HORIZONS_SECONDS = {
    "1h": 3600,
    "4h": 4 * 3600,
    "1d": 24 * 3600,
    "1w": 7 * 24 * 3600,
    "1m": 30 * 24 * 3600,
    "3m": 90 * 24 * 3600,
    "1y": 365 * 24 * 3600,
}


@dataclass(frozen=True)
class FuturePathLabel:
    horizon: str
    horizon_seconds: int
    end_time: datetime
    end_price: float
    return_pct: float
    mfe_pct: float
    mae_pct: float

    def __post_init__(self) -> None:
        if self.horizon not in HORIZONS_SECONDS:
            raise ValueError("unsupported forecast horizon")
        if self.horizon_seconds != HORIZONS_SECONDS[self.horizon]:
            raise ValueError("horizon seconds do not match canonical horizon")
        if self.end_time.tzinfo is None or self.end_time.utcoffset() is None:
            raise ValueError("end_time must be timezone-aware")
        for value in (self.end_price, self.return_pct, self.mfe_pct, self.mae_pct):
            if not isfinite(value):
                raise ValueError("future path values must be finite")
        if self.end_price <= 0:
            raise ValueError("end_price must be positive")
        if self.mfe_pct < 0:
            raise ValueError("MFE must be non-negative")
        if self.mae_pct > 0:
            raise ValueError("MAE must be non-positive")


@dataclass(frozen=True)
class HistoricalFeatureRow:
    row_id: str
    feature_time: datetime
    prediction_time: datetime
    evidence_id: str
    evidence_lineage_sha256: str
    source_ids: tuple[str, ...]
    symbol: str
    feature_schema_version: int
    feature_payload: dict[str, float | int | str | None]
    labels: tuple[FuturePathLabel, ...]

    @property
    def calibrated(self) -> bool:
        return False

    @property
    def execution_weight(self) -> float:
        return 0.0


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def build_historical_feature_row(
    lineage: ShadowEvidenceLineage,
    *,
    labels: tuple[FuturePathLabel, ...] = (),
) -> HistoricalFeatureRow:
    vector = lineage.vector
    prediction_time = vector.prediction_time
    if any(source.fetched_at > prediction_time for source in lineage.sources):
        raise ValueError("future-fetched evidence cannot enter historical feature store")
    if any(label.end_time <= prediction_time for label in labels):
        raise ValueError("future labels must resolve strictly after prediction_time")
    horizons = [label.horizon for label in labels]
    if len(horizons) != len(set(horizons)):
        raise ValueError("duplicate future label horizon")

    features: dict[str, float | int | str | None] = {
        "window_seconds": vector.window_seconds,
        "independent_price": vector.independent_price,
        "independent_provider_count": vector.independent_provider_count,
        "independent_external_provider_count": vector.independent_external_provider_count,
        "consensus_agreement_score": vector.consensus_agreement_score,
        "consensus_freshness_score": vector.consensus_freshness_score,
        "mid_return_bps": vector.mid_return_bps,
        "mean_depth_imbalance_25bps": vector.mean_depth_imbalance_25bps,
        "cvd_quote": vector.cvd_quote,
        "taker_imbalance": vector.taker_imbalance,
        "open_interest_delta_pct": vector.open_interest_delta_pct,
        "funding_delta_bps": vector.funding_delta_bps,
        "basis_delta_bps": vector.basis_delta_bps,
        "depth_trade_coverage_ratio": vector.depth_trade_coverage_ratio,
        "removal_candidate_residual_notional": vector.removal_candidate_residual_notional,
    }
    material = {
        "schema_version": 1,
        "evidence_id": lineage.evidence_id,
        "prediction_time": prediction_time.isoformat(),
        "features": features,
    }
    row_id = f"historical-feature:sha256:{sha256(_canonical_json(material).encode()).hexdigest()}"
    return HistoricalFeatureRow(
        row_id=row_id,
        feature_time=prediction_time,
        prediction_time=prediction_time,
        evidence_id=lineage.evidence_id,
        evidence_lineage_sha256=lineage.lineage_sha256,
        source_ids=lineage.source_ids,
        symbol=vector.symbol,
        feature_schema_version=1,
        feature_payload=features,
        labels=tuple(sorted(labels, key=lambda item: item.horizon_seconds)),
    )
