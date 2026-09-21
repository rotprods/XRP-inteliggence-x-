from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.depth_dynamics import DepthDynamics
from xrp_regime_engine.derivatives import FundingState, OpenInterestState
from xrp_regime_engine.order_flow import OrderFlowState
from xrp_regime_engine.temporal_alignment import build_aligned_temporal_window
from xrp_regime_engine.temporal_flow import build_temporal_window
from xrp_regime_engine.trade_attribution import _derived_window_seconds

T0 = datetime(2026, 9, 21, 7, 0, tzinfo=UTC)
OBSERVED = T0 + timedelta(seconds=8)
AVAILABLE = OBSERVED + timedelta(milliseconds=100)
FETCHED = OBSERVED + timedelta(milliseconds=200)
PREDICTION = T0 + timedelta(seconds=10)


def _depth(*, first_observed_at: datetime | None = None) -> DepthDynamics:
    first_observed = first_observed_at or OBSERVED - timedelta(seconds=1)
    return DepthDynamics(
        symbol="XRPUSDT",
        observed_at=OBSERVED,
        first_update_id=1,
        final_update_id=2,
        elapsed_seconds=1.0,
        bid_added_notional=0.0,
        bid_removed_notional=10.0,
        ask_added_notional=0.0,
        ask_removed_notional=10.0,
        bid_net_notional=-10.0,
        ask_net_notional=-10.0,
        gross_churn_notional=20.0,
        churn_quote_per_second=20.0,
        trade_attribution_confirmed=False,
        quality_flags=("TRADE_ATTRIBUTION_REQUIRED",),
        first_observed_at=first_observed,
        last_observed_at=OBSERVED,
        first_available_at=OBSERVED - timedelta(milliseconds=900),
        last_available_at=AVAILABLE,
        first_fetched_at=OBSERVED - timedelta(milliseconds=800),
        last_fetched_at=FETCHED,
        provenance_complete=True,
        execution_weight=0.0,
    )


def _flow() -> OrderFlowState:
    return OrderFlowState(
        symbol="XRPUSDT",
        observed_at=OBSERVED,
        aggressive_buy_notional=10.0,
        aggressive_sell_notional=10.0,
        cvd_quote=0.0,
        taker_imbalance=0.0,
        trade_count=2,
        first_observed_at=OBSERVED - timedelta(seconds=1),
        last_observed_at=OBSERVED,
        first_available_at=OBSERVED - timedelta(milliseconds=900),
        last_available_at=AVAILABLE,
        first_fetched_at=OBSERVED - timedelta(milliseconds=800),
        last_fetched_at=FETCHED,
        provenance_complete=True,
    )


def _funding() -> FundingState:
    return FundingState(
        symbol="XRPUSDT",
        observed_at=OBSERVED,
        mark_price=1.4,
        index_price=1.4,
        funding_rate=0.0,
        next_funding_at=T0 + timedelta(hours=8),
        available_at=AVAILABLE,
        fetched_at=FETCHED,
        payload_sha256="a" * 64,
    )


def _open_interest() -> OpenInterestState:
    return OpenInterestState(
        symbol="XRPUSDT",
        observed_at=OBSERVED,
        open_interest=100.0,
        available_at=AVAILABLE,
        fetched_at=FETCHED,
        payload_sha256="b" * 64,
    )


def test_aligned_temporal_window_fails_closed_when_sample_window_has_no_data() -> None:
    result = build_aligned_temporal_window(
        samples=(),
        depth=_depth(),
        order_flow=_flow(),
        funding=_funding(),
        open_interest=_open_interest(),
        prediction_time=PREDICTION,
        window_seconds=60,
    )
    assert result.evidence_eligible is False
    assert result.window is None
    assert "TEMPORAL_WINDOW_NO_DATA" in result.quality_flags
    assert result.execution_weight == 0.0


def test_temporal_window_empty_input_returns_no_data() -> None:
    assert build_temporal_window((), prediction_time=PREDICTION, window_seconds=60) is None


def test_reversed_observation_window_fails_closed_before_provenance_reconciliation() -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        _derived_window_seconds(
            OBSERVED + timedelta(seconds=1),
            OBSERVED,
            field="probe",
        )
