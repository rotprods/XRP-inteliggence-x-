import math

import pandas as pd
import pytest

from xrp_regime_engine.demo import DEMO_SUPPLEMENTAL_FEATURES, generate_demo_frame
from xrp_regime_engine.features import _rsi, compute_features


def test_features_are_finite_when_inputs_exist() -> None:
    features = compute_features(
        generate_demo_frame(), supplemental=DEMO_SUPPLEMENTAL_FEATURES
    )
    assert all(value is None or math.isfinite(value) for value in features.values())
    assert features["xrp_rsi_14"] is not None
    assert 0 <= features["xrp_rsi_14"] <= 100
    assert "xrp_btc_return_30d" in features


def test_missing_used_column_fails_with_explicit_value_error() -> None:
    frame = generate_demo_frame().drop(columns=["XRP_BTC"])
    with pytest.raises(ValueError, match="XRP_BTC"):
        compute_features(frame)


def test_flat_rsi_is_neutral() -> None:
    assert _rsi(pd.Series([1.0] * 30), 14) == 50.0


def test_supplemental_features_are_never_invented() -> None:
    features = compute_features(generate_demo_frame())
    assert features["funding_z"] is None
    assert features["provider_agreement"] is None
    assert features["xrpl_activity_z"] is None


def test_short_history_preserves_unavailable_values() -> None:
    features = compute_features(generate_demo_frame(40))
    assert features["xrp_ma100_distance"] is None
    assert features["xrp_drawdown_365d"] is None


def test_frame_requires_utc_datetime_index() -> None:
    frame = generate_demo_frame().copy()
    frame.index = frame.index.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_features(frame)
