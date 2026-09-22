import pytest

from xrp_regime_engine.technicals_v1 import ema, macd, rsi_wilder


def test_rsi_flat_market_is_neutral() -> None:
    result = rsi_wilder([10.0] * 20)
    assert result.value == 50.0


def test_rsi_monotonic_rise_is_100() -> None:
    result = rsi_wilder([float(i) for i in range(1, 30)])
    assert result.value == 100.0


def test_rsi_scale_invariance() -> None:
    prices = [100.0, 101.0, 99.0, 103.0, 104.0, 102.0, 105.0, 108.0, 106.0, 109.0,
              111.0, 110.0, 112.0, 115.0, 114.0, 117.0, 119.0, 118.0, 121.0, 123.0]
    left = rsi_wilder(prices)
    right = rsi_wilder([value * 10 for value in prices])
    assert left.value == pytest.approx(right.value)


def test_ema_sma_seed_known_vector() -> None:
    result = ema([1.0, 2.0, 3.0, 4.0, 5.0], 3)
    assert result.value == pytest.approx(4.0)


def test_macd_requires_warmup() -> None:
    result = macd([float(i) for i in range(1, 30)])
    assert result.macd is None
    assert "INSUFFICIENT_WARMUP" in result.quality_flags


@pytest.mark.parametrize("values", [[1.0, float("nan")], [1.0, float("inf")], [1.0, 0.0]])
def test_indicator_rejects_invalid_prices(values: list[float]) -> None:
    with pytest.raises(ValueError):
        rsi_wilder(values)
