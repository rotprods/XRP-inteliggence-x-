from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from xrp_regime_engine.demo import DEMO_SUPPLEMENTAL_FEATURES, generate_demo_frame
from xrp_regime_engine.features import compute_features
from xrp_regime_engine.models import (
    AssetObservation,
    Candle,
    ComponentScores,
    DerivativesSnapshot,
    Horizon,
    Provenance,
    ProviderHealth,
    RegimeLabel,
    RegimeSnapshot,
)
from xrp_regime_engine.regime import score_regime

pytestmark = [pytest.mark.unit, pytest.mark.temporal]


def now() -> datetime:
    return datetime(2026, 8, 28, 9, 0, tzinfo=UTC)


def provenance(**updates: object) -> Provenance:
    base = now()
    values: dict[str, object] = {
        "provider": "fixture",
        "observed_at": base,
        "available_at": base,
        "fetched_at": base,
    }
    values.update(updates)
    return Provenance(**values)


def candle(**updates: object) -> Candle:
    close = now()
    values: dict[str, object] = {
        "asset": "XRP_USD",
        "interval": "1h",
        "open_time": close - timedelta(hours=1),
        "close_time": close,
        "open": 1.0,
        "high": 1.1,
        "low": 0.9,
        "close": 1.05,
        "volume": 10.0,
        "provenance": provenance(),
    }
    values.update(updates)
    return Candle(**values)


def snapshot() -> RegimeSnapshot:
    return score_regime(
        compute_features(generate_demo_frame(), supplemental=DEMO_SUPPLEMENTAL_FEATURES),
        Horizon.D1,
    )


def test_payload_hash_accepts_uppercase_and_normalizes_lowercase() -> None:
    item = provenance(payload_hash="A" * 64)
    assert item.payload_hash == "a" * 64


@pytest.mark.parametrize(
    ("available_delta", "fetched_delta", "message"),
    [
        (-1, 0, "available_at cannot precede"),
        (0, -1, "fetched_at cannot precede"),
    ],
)
def test_provenance_temporal_order_fails_closed(
    available_delta: int, fetched_delta: int, message: str
) -> None:
    base = now()
    with pytest.raises(ValidationError, match=message):
        provenance(
            observed_at=base,
            available_at=base + timedelta(seconds=available_delta),
            fetched_at=base + timedelta(seconds=fetched_delta),
        )


def test_aware_timestamp_normalizes_to_utc() -> None:
    local = datetime(2026, 8, 28, 11, tzinfo=timezone(timedelta(hours=2)))
    item = Provenance(provider="p", observed_at=local, available_at=local, fetched_at=local)
    assert item.observed_at.tzinfo is UTC
    assert item.observed_at.hour == 9


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
@pytest.mark.parametrize("bad", [0.0, -1.0, math.inf, -math.inf, math.nan])
def test_candle_rejects_non_positive_or_non_finite_prices(field: str, bad: float) -> None:
    with pytest.raises(ValidationError):
        candle(**{field: bad})


@pytest.mark.parametrize("bad", [-1.0, math.inf, math.nan])
def test_candle_rejects_invalid_volume(bad: float) -> None:
    with pytest.raises(ValidationError):
        candle(volume=bad)


def test_candle_rejects_non_increasing_times() -> None:
    close = now()
    with pytest.raises(ValidationError, match="close_time must be later"):
        candle(open_time=close, close_time=close)


def test_candle_rejects_low_above_body() -> None:
    with pytest.raises(ValidationError, match="low must be less"):
        candle(low=1.06)


def test_candle_rejects_high_below_body() -> None:
    with pytest.raises(ValidationError, match="high must be greater"):
        candle(high=1.01)


def test_candle_rejects_provenance_observed_before_close() -> None:
    close = now()
    p = provenance(
        observed_at=close - timedelta(seconds=1),
        available_at=close,
        fetched_at=close,
    )
    with pytest.raises(ValidationError, match="candle provenance"):
        candle(provenance=p)


def test_asset_observation_rejects_non_finite_value() -> None:
    base = now()
    with pytest.raises(ValidationError, match="must be finite"):
        AssetObservation(
            asset="US10Y",
            metric="level",
            value=math.inf,
            unit="pct",
            observed_at=base,
            available_at=base,
            provenance=provenance(),
        )


def test_asset_observation_rejects_temporal_mismatch() -> None:
    base = now()
    with pytest.raises(ValidationError, match="observed_at must match"):
        AssetObservation(
            asset="US10Y",
            metric="level",
            value=4.0,
            unit="pct",
            observed_at=base,
            available_at=base,
            provenance=provenance(observed_at=base + timedelta(seconds=1), available_at=base + timedelta(seconds=1), fetched_at=base + timedelta(seconds=1)),
        )


def test_asset_observation_rejects_availability_mismatch() -> None:
    base = now()
    with pytest.raises(ValidationError, match="available_at must match"):
        AssetObservation(
            asset="US10Y",
            metric="level",
            value=4.0,
            unit="pct",
            observed_at=base,
            available_at=base + timedelta(seconds=1),
            provenance=provenance(),
        )


@pytest.mark.parametrize("field", ["funding_rate", "futures_basis_pct"])
def test_derivatives_signed_metrics_reject_non_finite(field: str) -> None:
    with pytest.raises(ValidationError, match="must be finite"):
        DerivativesSnapshot(asset="XRP", observed_at=now(), **{field: math.nan})


@pytest.mark.parametrize(
    "field",
    [
        "open_interest_usd",
        "liquidations_long_usd",
        "liquidations_short_usd",
        "long_short_ratio",
        "taker_buy_sell_ratio",
    ],
)
def test_derivatives_non_negative_metrics_reject_negative(field: str) -> None:
    with pytest.raises(ValidationError, match="must be non-negative"):
        DerivativesSnapshot(asset="XRP", observed_at=now(), **{field: -0.1})


def test_provider_health_normalizes_optional_last_observation() -> None:
    health = ProviderHealth(
        provider="p",
        checked_at=now(),
        last_observation_at=now(),
        status="ok",
        freshness_score=1,
        agreement_score=1,
    )
    assert health.last_observation_at is not None
    empty = health.model_copy(update={"last_observation_at": None})
    assert empty.last_observation_at is None


def test_regime_snapshot_rejects_bad_digest() -> None:
    payload = snapshot().model_dump()
    payload["feature_hash"] = "bad"
    with pytest.raises(ValidationError, match="SHA-256"):
        RegimeSnapshot.model_validate(payload)


def test_regime_snapshot_rejects_bad_component_coverage() -> None:
    payload = snapshot().model_dump()
    payload["component_coverage"] = {"macro": 1.1}
    with pytest.raises(ValidationError, match="between 0 and 1"):
        RegimeSnapshot.model_validate(payload)


def test_regime_snapshot_rejects_score_sum_mismatch() -> None:
    payload = snapshot().model_dump()
    payload["bear_score"] = 0
    with pytest.raises(ValidationError, match="sum to 100"):
        RegimeSnapshot.model_validate(payload)


def test_regime_snapshot_rejects_blocked_without_reason() -> None:
    payload = snapshot().model_dump()
    payload.update(output_blocked=True, regime=RegimeLabel.DEGRADED, block_reasons=[])
    with pytest.raises(ValidationError, match="requires at least one"):
        RegimeSnapshot.model_validate(payload)


def test_regime_snapshot_rejects_degraded_block_state_mismatch() -> None:
    payload = snapshot().model_dump()
    payload.update(output_blocked=False, regime=RegimeLabel.DEGRADED)
    with pytest.raises(ValidationError, match="identical state"):
        RegimeSnapshot.model_validate(payload)


def test_component_scores_are_strict() -> None:
    with pytest.raises(ValidationError):
        ComponentScores(
            macro=50,
            crypto=50,
            xrp_relative=50,
            derivatives=50,
            xrpl=50,
            data_quality=101,
        )


def test_private_optional_validators_cover_none_paths() -> None:
    from xrp_regime_engine import models

    assert models._sha256_or_none(None, "x") is None
    assert models._finite_optional(None, "x") is None
    assert models._non_negative_optional(None, "x") is None
