from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType

import numpy as np
import pandas as pd


DEMO_END = datetime(2026, 8, 24, tzinfo=UTC)
DEMO_SUPPLEMENTAL_FEATURES = MappingProxyType(
    {
        "funding_z": 0.35,
        "oi_price_divergence": 0.20,
        "liquidation_impulse": 0.45,
        "provider_agreement": 0.96,
        "freshness_score": 0.98,
        "source_coverage": 0.88,
        "xrpl_activity_z": 0.25,
    }
)

ASSETS = [
    "XRP_USD",
    "BTC_USD",
    "ETH_USD",
    "BTC_DOMINANCE",
    "NDX",
    "SPX",
    "VIX",
    "DXY",
    "US10Y",
    "GOLD",
    "WTI",
    "GASOLINE",
    "NATGAS",
    "COCOA",
    "COIN",
    "MSTR",
]


def generate_demo_frame(
    periods: int = 900,
    seed: int = 42,
    *,
    end: datetime = DEMO_END,
) -> pd.DataFrame:
    """Generate deterministic daily data with a late risk-on reversal regime."""

    if periods < 2:
        raise ValueError("periods must be at least 2")
    if end.tzinfo is None:
        raise ValueError("demo end timestamp must be timezone-aware")

    rng = np.random.default_rng(seed)
    normalized_end = end.astimezone(UTC).normalize() if hasattr(end, "normalize") else end
    end_date = normalized_end.date()
    index = pd.date_range(end=end_date, periods=periods, freq="D", tz="UTC")
    market = rng.normal(0.0004, 0.015, periods)
    risk = rng.normal(0.0002, 0.011, periods)
    macro = rng.normal(0.0, 0.005, periods)
    late = np.zeros(periods)
    late_window = min(45, periods)
    late[-late_window:] = np.linspace(-0.01, 0.025, late_window)
    xrp_idio = rng.normal(0.0001, 0.028, periods) + late
    btc_ret = market + 0.35 * risk
    eth_ret = 1.15 * market + 0.50 * risk + rng.normal(0, 0.008, periods)
    xrp_ret = 1.45 * market + 0.65 * risk + xrp_idio

    frame = pd.DataFrame(index=index)
    frame["BTC_USD"] = 18_000 * np.exp(np.cumsum(btc_ret))
    frame["ETH_USD"] = 1_300 * np.exp(np.cumsum(eth_ret))
    frame["XRP_USD"] = 0.35 * np.exp(np.cumsum(xrp_ret))
    frame["BTC_DOMINANCE"] = (
        52
        + np.cumsum(rng.normal(0, 0.08, periods))
        - np.linspace(0, 2.5, periods)
    )
    frame["NDX"] = 11_000 * np.exp(
        np.cumsum(0.7 * market + 0.5 * risk + rng.normal(0, 0.006, periods))
    )
    frame["SPX"] = 3_900 * np.exp(
        np.cumsum(0.55 * market + 0.3 * risk + rng.normal(0, 0.004, periods))
    )
    frame["VIX"] = np.maximum(
        10,
        24 * np.exp(np.cumsum(-0.05 * risk + rng.normal(0, 0.015, periods))),
    )
    frame["DXY"] = 105 * np.exp(
        np.cumsum(-0.08 * risk + 0.08 * macro + rng.normal(0, 0.0025, periods))
    )
    frame["US10Y"] = np.clip(
        4.2 + np.cumsum(0.008 * macro + rng.normal(0, 0.012, periods)),
        0.5,
        8.0,
    )
    frame["GOLD"] = 1_800 * np.exp(
        np.cumsum(-0.04 * macro + rng.normal(0, 0.006, periods))
    )
    frame["WTI"] = 78 * np.exp(np.cumsum(rng.normal(0, 0.012, periods)))
    frame["GASOLINE"] = 2.9 * np.exp(np.cumsum(rng.normal(0, 0.011, periods)))
    frame["NATGAS"] = 3.5 * np.exp(np.cumsum(rng.normal(0, 0.025, periods)))
    frame["COCOA"] = 2_500 * np.exp(np.cumsum(rng.normal(0, 0.02, periods)))
    frame["COIN"] = 60 * np.exp(
        np.cumsum(1.4 * market + 1.0 * risk + rng.normal(0, 0.018, periods))
    )
    frame["MSTR"] = 25 * np.exp(
        np.cumsum(1.8 * market + 1.3 * risk + rng.normal(0, 0.022, periods))
    )
    frame["XRP_BTC"] = frame["XRP_USD"] / frame["BTC_USD"]
    frame["ETH_BTC"] = frame["ETH_USD"] / frame["BTC_USD"]
    return frame.replace([np.inf, -np.inf], np.nan).ffill().bfill()
