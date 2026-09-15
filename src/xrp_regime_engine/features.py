from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd


FeatureValue = float | None

REQUIRED_COLUMNS = frozenset(
    {
        "XRP_USD",
        "BTC_USD",
        "XRP_BTC",
        "ETH_BTC",
        "BTC_DOMINANCE",
        "NDX",
        "SPX",
        "VIX",
        "DXY",
        "US10Y",
        "GOLD",
        "WTI",
        "GASOLINE",
        "COIN",
        "MSTR",
    }
)

SUPPLEMENTAL_KEYS = frozenset(
    {
        "funding_z",
        "oi_price_divergence",
        "liquidation_impulse",
        "provider_agreement",
        "freshness_score",
        "source_coverage",
        "xrpl_activity_z",
    }
)

DAILY_CADENCE_MIN_SECONDS = 18 * 60 * 60
DAILY_CADENCE_MAX_SECONDS = 30 * 60 * 60


def _finite(value: float | int | np.floating[object] | None) -> FeatureValue:
    if value is None:
        return None
    candidate = float(value)
    return candidate if math.isfinite(candidate) else None


def _clean(series: pd.Series) -> pd.Series:
    return (
        pd.to_numeric(series, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )


def _return(series: pd.Series, periods: int) -> FeatureValue:
    clean = _clean(series)
    if periods < 1 or len(clean) <= periods:
        return None
    base = float(clean.iloc[-periods - 1])
    latest = float(clean.iloc[-1])
    if base == 0:
        return None
    return _finite(latest / base - 1)


def _absolute_change(series: pd.Series, periods: int) -> FeatureValue:
    clean = _clean(series)
    if periods < 1 or len(clean) <= periods:
        return None
    return _finite(float(clean.iloc[-1] - clean.iloc[-periods - 1]))


def _zscore(series: pd.Series, window: int) -> FeatureValue:
    sample = _clean(series).tail(window)
    if len(sample) < window:
        return None
    std = float(sample.std(ddof=0))
    if not math.isfinite(std):
        return None
    if std == 0:
        return 0.0
    return _finite((float(sample.iloc[-1]) - float(sample.mean())) / std)


def _rsi(series: pd.Series, window: int = 14) -> FeatureValue:
    clean = _clean(series)
    if len(clean) < window + 1:
        return None
    # len(clean) >= window + 1 guarantees exactly ``window`` finite deltas here.
    delta = clean.diff().dropna().tail(window)
    gains = float(delta.clip(lower=0).mean())
    losses = float((-delta.clip(upper=0)).mean())
    if gains == 0 and losses == 0:
        return 50.0
    if losses == 0:
        return 100.0
    if gains == 0:
        return 0.0
    rs = gains / losses
    return _finite(100 - 100 / (1 + rs))


def _paired_returns(
    first: pd.Series,
    second: pd.Series,
    window: int,
) -> pd.DataFrame:
    joined = pd.concat(
        [
            pd.to_numeric(first, errors="coerce").pct_change(),
            pd.to_numeric(second, errors="coerce").pct_change(),
        ],
        axis=1,
    )
    return (
        joined.replace([np.inf, -np.inf], np.nan)
        .dropna()
        .tail(window)
    )


def _beta(asset: pd.Series, benchmark: pd.Series, window: int = 90) -> FeatureValue:
    joined = _paired_returns(asset, benchmark, window)
    if len(joined) < window:
        return None
    variance = float(joined.iloc[:, 1].var())
    if not math.isfinite(variance) or variance == 0:
        return None
    return _finite(float(joined.cov().iloc[0, 1]) / variance)


def _corr(a: pd.Series, b: pd.Series, window: int = 90) -> FeatureValue:
    joined = _paired_returns(a, b, window)
    if len(joined) < window:
        return None
    return _finite(float(joined.corr().iloc[0, 1]))


def _distance_to_mean(series: pd.Series, window: int) -> FeatureValue:
    sample = _clean(series).tail(window)
    if len(sample) < window:
        return None
    mean = float(sample.mean())
    if mean == 0:
        return None
    return _finite(float(sample.iloc[-1]) / mean - 1)


def _drawdown(series: pd.Series, window: int) -> FeatureValue:
    sample = _clean(series).tail(window)
    if len(sample) < window:
        return None
    peak = float(sample.max())
    if peak <= 0:
        return None
    return _finite(float(sample.iloc[-1]) / peak - 1)


def _median_interval_seconds(index: pd.Index) -> FeatureValue:
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 3:
        return None
    deltas = index.to_series().diff().dropna().dt.total_seconds()
    deltas = deltas[deltas > 0]
    if deltas.empty:
        return None
    median_seconds = float(deltas.median())
    return _finite(median_seconds)


def _periods_per_year(index: pd.Index) -> FeatureValue:
    median_seconds = _median_interval_seconds(index)
    if median_seconds is None or median_seconds <= 0:
        return None
    return _finite((365.25 * 24 * 60 * 60) / median_seconds)


def _annualized_volatility(
    series: pd.Series,
    index: pd.Index,
    window: int = 30,
) -> FeatureValue:
    returns = (
        pd.to_numeric(series, errors="coerce")
        .pct_change()
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
        .tail(window)
    )
    periods_per_year = _periods_per_year(index)
    if len(returns) < window or periods_per_year is None:
        return None
    std = float(returns.std(ddof=0))
    return _finite(std * math.sqrt(periods_per_year))


def _validate_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        raise ValueError("feature frame cannot be empty")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("feature frame index must be a DatetimeIndex")
    if frame.index.tz is None:
        raise ValueError("feature frame index must be timezone-aware")
    if not frame.index.is_monotonic_increasing:
        raise ValueError("feature frame index must be monotonic increasing")
    if frame.index.has_duplicates:
        raise ValueError("feature frame index cannot contain duplicates")

    normalized = frame.copy()
    normalized.index = normalized.index.tz_convert("UTC")
    cadence = _median_interval_seconds(normalized.index)
    if cadence is None:
        raise ValueError("feature frame needs at least three timestamped observations")
    if not DAILY_CADENCE_MIN_SECONDS <= cadence <= DAILY_CADENCE_MAX_SECONDS:
        raise ValueError(
            "the current feature engine accepts daily cadence only; "
            f"observed median interval was {cadence:.0f} seconds"
        )

    missing = REQUIRED_COLUMNS.difference(normalized.columns)
    if missing:
        raise ValueError(f"missing required assets: {sorted(missing)}")
    return normalized


def compute_features(
    frame: pd.DataFrame,
    *,
    supplemental: Mapping[str, float | None] | None = None,
) -> dict[str, FeatureValue]:
    """Compute daily point-in-time features without inventing missing inputs.

    Derivatives, provider-quality and XRPL features must be supplied explicitly via
    ``supplemental``. A live caller that does not have those observations receives
    ``None`` values, allowing the regime engine to degrade or block its output.

    The current implementation is intentionally daily. Intraday horizons remain
    blocked until a separate cadence-correct feature set is introduced.
    """

    frame = _validate_frame(frame)
    xrp = frame["XRP_USD"]
    btc = frame["BTC_USD"]
    ndx = frame["NDX"]

    features: dict[str, FeatureValue] = {
        "feature_cadence_seconds": _median_interval_seconds(frame.index),
        "xrp_return_1d": _return(xrp, 1),
        "xrp_return_7d": _return(xrp, 7),
        "xrp_return_30d": _return(xrp, 30),
        "btc_return_7d": _return(btc, 7),
        "btc_return_30d": _return(btc, 30),
        "xrp_btc_return_7d": _return(frame["XRP_BTC"], 7),
        "xrp_btc_return_30d": _return(frame["XRP_BTC"], 30),
        "eth_btc_return_7d": _return(frame["ETH_BTC"], 7),
        "btc_dominance_change_20d": _return(frame["BTC_DOMINANCE"], 20),
        "ndx_return_20d": _return(ndx, 20),
        "spx_return_20d": _return(frame["SPX"], 20),
        "coin_return_20d": _return(frame["COIN"], 20),
        "mstr_return_20d": _return(frame["MSTR"], 20),
        "dxy_return_20d": _return(frame["DXY"], 20),
        "us10y_change_20d": _absolute_change(frame["US10Y"], 20),
        "vix_z_20d": _zscore(frame["VIX"], 20),
        "gold_return_20d": _return(frame["GOLD"], 20),
        "wti_return_20d": _return(frame["WTI"], 20),
        "gasoline_return_20d": _return(frame["GASOLINE"], 20),
        "xrp_rsi_14": _rsi(xrp, 14),
        "xrp_vol_30d": _annualized_volatility(xrp, frame.index, 30),
        "xrp_ma20_distance": _distance_to_mean(xrp, 20),
        "xrp_ma100_distance": _distance_to_mean(xrp, 100),
        "xrp_drawdown_365d": _drawdown(xrp, 365),
        "xrp_beta_btc_90d": _beta(xrp, btc, 90),
        "xrp_beta_ndx_90d": _beta(xrp, ndx, 90),
        "btc_ndx_corr_90d": _corr(btc, ndx, 90),
        "xrp_btc_corr_90d": _corr(xrp, btc, 90),
    }

    unknown = set(supplemental or {}).difference(SUPPLEMENTAL_KEYS)
    if unknown:
        raise ValueError(f"unknown supplemental features: {sorted(unknown)}")
    for key in sorted(SUPPLEMENTAL_KEYS):
        features[key] = _finite((supplemental or {}).get(key))

    return features
