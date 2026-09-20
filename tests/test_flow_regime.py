from datetime import UTC, datetime

from xrp_regime_engine.derivatives import DerivativesRiskState
from xrp_regime_engine.flow_regime import FlowRegimeLabel, classify_flow_regime
from xrp_regime_engine.microstructure import MicrostructureState
from xrp_regime_engine.order_flow import OrderFlowState

NOW = datetime(2026, 9, 20, 20, 0, tzinfo=UTC)


def micro(imbalance: float) -> MicrostructureState:
    return MicrostructureState(
        symbol="XRPUSDT",
        observed_at=NOW,
        mid_price=1.4,
        spread_bps=1,
        microprice=1.4002,
        imbalance_10bps=imbalance,
        imbalance_25bps=imbalance,
        imbalance_50bps=imbalance,
        imbalance_100bps=imbalance,
        bid_notional_100bps=1_000_000,
        ask_notional_100bps=700_000,
    )


def flow(imbalance: float) -> OrderFlowState:
    return OrderFlowState(
        symbol="XRPUSDT",
        observed_at=NOW,
        aggressive_buy_notional=600_000,
        aggressive_sell_notional=400_000,
        cvd_quote=200_000 if imbalance > 0 else -200_000,
        taker_imbalance=imbalance,
        trade_count=100,
    )


def test_missing_trade_flow_fails_closed() -> None:
    state = classify_flow_regime(micro(0.4), None, None)
    assert state.label == FlowRegimeLabel.NO_DATA
    assert state.execution_weight == 0.0


def test_depth_and_positive_cvd_classify_spot_led_demand() -> None:
    state = classify_flow_regime(micro(0.4), flow(0.3), None)
    assert state.label == FlowRegimeLabel.SPOT_LED_DEMAND
    assert state.execution_weight == 0.0


def test_bid_support_against_aggressive_sells_is_absorption() -> None:
    state = classify_flow_regime(micro(0.4), flow(-0.3), None)
    assert state.label == FlowRegimeLabel.BID_ABSORPTION


def test_positive_funding_prevents_spot_led_claim() -> None:
    derivatives = DerivativesRiskState(
        symbol="XRPUSDT",
        observed_at=NOW,
        funding_rate=0.001,
        basis_bps=5,
        open_interest=1_000_000,
        quality_flags=("ELEVATED_POSITIVE_FUNDING",),
    )
    state = classify_flow_regime(micro(0.4), flow(0.3), derivatives)
    assert state.label == FlowRegimeLabel.LEVERAGED_DEMAND
    assert state.execution_weight == 0.0


def test_ask_depth_and_negative_cvd_classify_sell_pressure() -> None:
    state = classify_flow_regime(micro(-0.4), flow(-0.3), None)
    assert state.label == FlowRegimeLabel.SELL_PRESSURE
