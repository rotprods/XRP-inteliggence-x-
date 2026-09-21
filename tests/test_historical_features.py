from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.evidence_lineage import (
    EvidenceSourceDigest,
    EvidenceSourceRole,
    build_shadow_evidence_lineage,
)
from xrp_regime_engine.historical_features import (
    FuturePathLabel,
    build_historical_feature_row,
)
from xrp_regime_engine.shadow_evidence import ShadowEvidenceVector

T = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def vector() -> ShadowEvidenceVector:
    return ShadowEvidenceVector(
        symbol="XRPUSDT", prediction_time=T, window_seconds=900,
        independent_price=1.5, independent_provider_count=2,
        independent_external_provider_count=1,
        independent_providers=("binance", "kraken"),
        consensus_agreement_score=0.99, consensus_freshness_score=0.99,
        mid_return_bps=5, mean_depth_imbalance_25bps=0.1,
        cvd_quote=1000, taker_imbalance=0.1,
        open_interest_delta_pct=None, funding_delta_bps=None, basis_delta_bps=None,
        depth_trade_coverage_ratio=None, removal_candidate_residual_notional=None,
        quality_flags=("UNCALIBRATED_SHADOW_ONLY",),
    )


def source(source_id: str, provider: str, role: EvidenceSourceRole, char: str) -> EvidenceSourceDigest:
    return EvidenceSourceDigest(
        source_id=source_id, provider=provider, role=role, content_sha256=char * 64,
        observed_at=T - timedelta(seconds=2), available_at=T - timedelta(seconds=1),
        fetched_at=T,
    )


def lineage():
    sources = (
        source("p:binance", "binance", EvidenceSourceRole.INDEPENDENT_PRICE, "a"),
        source("p:kraken", "kraken", EvidenceSourceRole.INDEPENDENT_PRICE, "b"),
        source("d:binance", "binance", EvidenceSourceRole.DEPTH, "c"),
        source("t:binance", "binance", EvidenceSourceRole.AGG_TRADE, "d"),
    )
    return build_shadow_evidence_lineage(vector(), sources)


def test_feature_row_is_deterministic_shadow_only() -> None:
    first = build_historical_feature_row(lineage())
    second = build_historical_feature_row(lineage())
    assert first.row_id == second.row_id
    assert first.evidence_id == lineage().evidence_id
    assert first.calibrated is False
    assert first.execution_weight == 0.0


def test_future_label_is_separate_from_feature_identity() -> None:
    base = build_historical_feature_row(lineage())
    label = FuturePathLabel(
        horizon="1h", horizon_seconds=3600, end_time=T + timedelta(hours=1),
        end_price=1.53, return_pct=2.0, mfe_pct=3.0, mae_pct=-1.0,
    )
    labeled = build_historical_feature_row(lineage(), labels=(label,))
    assert labeled.row_id == base.row_id
    assert labeled.feature_payload == base.feature_payload
    assert labeled.labels == (label,)


def test_labels_must_be_future_unique_and_canonical() -> None:
    past = FuturePathLabel(
        horizon="1h", horizon_seconds=3600, end_time=T - timedelta(seconds=1),
        end_price=1.5, return_pct=0, mfe_pct=0, mae_pct=0,
    )
    with pytest.raises(ValueError, match="strictly after"):
        build_historical_feature_row(lineage(), labels=(past,))

    good = replace(past, end_time=T + timedelta(hours=1))
    with pytest.raises(ValueError, match="duplicate"):
        build_historical_feature_row(lineage(), labels=(good, good))

    with pytest.raises(ValueError, match="canonical horizon"):
        FuturePathLabel(
            horizon="1h", horizon_seconds=1, end_time=T + timedelta(hours=1),
            end_price=1.5, return_pct=0, mfe_pct=0, mae_pct=0,
        )


def test_path_label_rejects_invalid_mfe_mae() -> None:
    with pytest.raises(ValueError, match="MFE"):
        FuturePathLabel(
            horizon="1h", horizon_seconds=3600, end_time=T + timedelta(hours=1),
            end_price=1.5, return_pct=0, mfe_pct=-1, mae_pct=0,
        )
    with pytest.raises(ValueError, match="MAE"):
        FuturePathLabel(
            horizon="1h", horizon_seconds=3600, end_time=T + timedelta(hours=1),
            end_price=1.5, return_pct=0, mfe_pct=1, mae_pct=1,
        )
