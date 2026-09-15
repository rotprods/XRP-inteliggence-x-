from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.models import Candle, Provenance


def test_provenance_requires_timezone() -> None:
    with pytest.raises(ValueError):
        Provenance(provider="x", observed_at=datetime.now(), available_at=datetime.now())


def test_provenance_normalizes_utc() -> None:
    now = datetime.now(UTC)
    item = Provenance(provider="x", observed_at=now, available_at=now)
    assert item.observed_at.tzinfo is not None


def test_provenance_rejects_invalid_hash() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="SHA-256"):
        Provenance(
            provider="x",
            observed_at=now,
            available_at=now,
            payload_hash="not-a-hash",
        )


def test_candle_rejects_invalid_geometry_and_negative_values() -> None:
    now = datetime.now(UTC)
    provenance = Provenance(provider="x", observed_at=now, available_at=now)
    with pytest.raises(ValueError):
        Candle(
            asset="XRP_USD",
            interval="1h",
            open_time=now,
            close_time=now - timedelta(hours=1),
            open=-1.0,
            high=1.0,
            low=2.0,
            close=3.0,
            volume=-1.0,
            provenance=provenance,
        )
