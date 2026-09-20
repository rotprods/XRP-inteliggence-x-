from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.temporal_flow import TemporalFlowSample, build_temporal_window

T0 = datetime(2026, 9, 20, 20, 0, tzinfo=UTC)


def sample(
    seconds: int,
    *,
    mid: float,
    depth: float,
    buys: float,
    sells: float,
    oi: float | None = None,
    funding: float | None = None,
    basis: float | None = None,
    availability_delay: int = 0,
) -> TemporalFlowSample:
    observed = T0 + timedelta(seconds=seconds)
    available = observed + timedelta(seconds=availability_delay)
    return TemporalFlowSample(
        symbol="XRPUSDT",
        observed_at=observed,
        available_at=available,
        fetched_at=available,
        mid_price=mid,
        depth_imbalance_25bps=depth,
        aggressive_buy_notional=buys,
        aggressive_sell_notional=sells,
        open_interest=oi,
        funding_rate=funding,
        basis_bps=basis,
    )


def test_future_available_sample_is_excluded_from_point_in_time_window() -> None:
    prediction_time = T0 + timedelta(minutes=1)
    samples = (
        sample(10, mid=1.40, depth=0.2, buys=100, sells=50),
        sample(
            50,
            mid=1.50,
            depth=0.8,
            buys=10_000,
            sells=0,
            availability_delay=30,
        ),
    )
    window = build_temporal_window(
        samples,
        prediction_time=prediction_time,
        window_seconds=60,
    )
    assert window is not None
    assert window.sample_count == 1
    assert window.mid_return_bps == pytest.approx(0)
    assert window.aggressive_buy_notional == pytest.approx(100)
    assert "SPARSE_WINDOW" in window.quality_flags


def test_window_aggregates_cvd_and_derivatives_deltas() -> None:
    prediction_time = T0 + timedelta(minutes=5)
    samples = (
        sample(
            20,
            mid=1.40,
            depth=0.20,
            buys=100,
            sells=50,
            oi=1_000,
            funding=0.0001,
            basis=2.0,
        ),
        sample(
            280,
            mid=1.414,
            depth=0.40,
            buys=250,
            sells=100,
            oi=1_100,
            funding=0.0002,
            basis=5.0,
        ),
    )
    window = build_temporal_window(
        samples,
        prediction_time=prediction_time,
        window_seconds=300,
    )
    assert window is not None
    assert window.sample_count == 2
    assert window.mid_return_bps == pytest.approx(100)
    assert window.mean_depth_imbalance_25bps == pytest.approx(0.30)
    assert window.cvd_quote == pytest.approx(200)
    assert window.taker_imbalance == pytest.approx(200 / 500)
    assert window.open_interest_delta_pct == pytest.approx(0.10)
    assert window.funding_delta_bps == pytest.approx(1.0)
    assert window.basis_delta_bps == pytest.approx(3.0)
    assert window.execution_weight == 0.0


def test_missing_derivatives_remain_null_and_are_flagged() -> None:
    prediction_time = T0 + timedelta(minutes=1)
    window = build_temporal_window(
        (
            sample(5, mid=1.40, depth=0.0, buys=50, sells=50),
            sample(55, mid=1.40, depth=0.0, buys=50, sells=50),
        ),
        prediction_time=prediction_time,
        window_seconds=60,
    )
    assert window is not None
    assert window.open_interest_delta_pct is None
    assert window.funding_delta_bps is None
    assert window.basis_delta_bps is None
    assert "OPEN_INTEREST_NO_DATA" in window.quality_flags
    assert "FUNDING_NO_DATA" in window.quality_flags
    assert "BASIS_NO_DATA" in window.quality_flags


def test_naive_timestamp_is_rejected() -> None:
    naive = datetime(2026, 9, 20, 20, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        TemporalFlowSample(
            symbol="XRPUSDT",
            observed_at=naive,
            available_at=naive,
            fetched_at=naive,
            mid_price=1.4,
            depth_imbalance_25bps=0.0,
            aggressive_buy_notional=0,
            aggressive_sell_notional=0,
        )


def test_window_cannot_mix_symbols() -> None:
    second = sample(20, mid=1.4, depth=0.0, buys=0, sells=0)
    other = TemporalFlowSample(
        symbol="BTCUSDT",
        observed_at=second.observed_at,
        available_at=second.available_at,
        fetched_at=second.fetched_at,
        mid_price=70_000,
        depth_imbalance_25bps=0.0,
        aggressive_buy_notional=0,
        aggressive_sell_notional=0,
    )
    with pytest.raises(ValueError, match="mix symbols"):
        build_temporal_window(
            (second, other),
            prediction_time=T0 + timedelta(minutes=1),
            window_seconds=60,
        )


def test_unsupported_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        build_temporal_window(
            (sample(1, mid=1.4, depth=0, buys=0, sells=0),),
            prediction_time=T0 + timedelta(minutes=1),
            window_seconds=120,
        )
