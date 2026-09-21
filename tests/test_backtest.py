from xrp_regime_engine.backtest import expanding_walk_forward
from xrp_regime_engine.demo import DEMO_SUPPLEMENTAL_FEATURES, generate_demo_frame


def test_walk_forward_runs_without_claiming_calibration() -> None:
    result = expanding_walk_forward(
        generate_demo_frame(700),
        min_train=365,
        step=14,
        forward=7,
        supplemental=DEMO_SUPPLEMENTAL_FEATURES,
    )
    assert result.observations > 10
    assert 0 <= result.directional_accuracy <= 1
    assert 0 <= result.raw_score_brier <= 1
    assert result.probability_calibrated is False
    assert 0 <= result.average_data_confidence <= 1
    assert 0 <= result.average_model_confidence <= 1
