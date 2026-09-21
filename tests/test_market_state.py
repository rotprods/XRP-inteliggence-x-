from datetime import UTC, datetime

from xrp_regime_engine.derivatives import DerivativesRiskState
from xrp_regime_engine.market_state import MarketStateLabel, classify_market_state
from xrp_regime_engine.microstructure import MicrostructureState

NOW = datetime(2026, 9, 20, 19, 0, tzinfo=UTC)


def _micro(imbalance: float, microprice: float = 1.401, mid: float = 1.400) -> MicrostructureState:
    return MicrostructureState(
        symbol="XRPUSDT",
        observed_at=NOW,
        mid_price=mid,
        spread_bps=1.0,
        microprice=microprice,
        imbalance_10bps=imbalance,
        imbalance_25bps=imbalance,
        imbalance_50bps=imbalance,
        imbalance_100bps=imbalance,
        bid_notional_100bps=1_000_000,
        ask_notional_100bps=700_000,
    )


def test_missing_microstructure_fails_closed() -> None:
    state = classify_market_state(None, None)
    assert state.label == MarketStateLabel.NO_DATA
    assert state.execution_weight == 0.0


def test_bid_absorption_is_observation_not_trade_instruction() -> None:
    state = classify_market_state(_micro(0.45), None)
    assert state.label == MarketStateLabel.ABSORPTION
    assert state.execution_weight == 0.0
    assert "BID_IMBALANCE_25BPS" in state.reasons


def test_positive_funding_downgrades_absorption_to_crowding() -> None:
    derivatives = DerivativesRiskState(
        symbol="XRPUSDT",
        observed_at=NOW,
        funding_rate=0.001,
        basis_bps=5.0,
        open_interest=100_000_000,
        quality_flags=("ELEVATED_POSITIVE_FUNDING",),
    )
    state = classify_market_state(_micro(0.45), derivatives)
    assert state.label == MarketStateLabel.LONG_CROWDING
    assert state.execution_weight == 0.0


def test_ask_pressure_classifies_distribution() -> None:
    state = classify_market_state(_micro(-0.50, microprice=1.399), None)
    assert state.label == MarketStateLabel.DISTRIBUTION
    assert state.execution_weight == 0.0
