from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import cast

import pytest

import xrp_regime_engine.historical_contract as contract
from xrp_regime_engine.historical_contract import (
    AvailabilityPrecision,
    FetchReceipt,
    HistoricalObservation,
)

T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
PAYLOAD_SHA = sha256(b"payload").hexdigest()
REQUEST_SHA = sha256(b"request").hexdigest()


def exact_observation() -> HistoricalObservation:
    receipt = FetchReceipt.create(
        source_id="source:test",
        provider="test",
        canonical_uri="https://example.com/market",
        endpoint="/market",
        request_fingerprint=REQUEST_SHA,
        fetched_at=T0,
        payload_sha256=PAYLOAD_SHA,
        ingestion_version="2",
        parser_version="2",
    )
    return HistoricalObservation(
        observation_id="exact",
        dataset="test",
        record_id="record",
        provider="test",
        source_id="source:test",
        symbol="XRP_USD",
        instrument="spot",
        observed_at=T0 - timedelta(hours=1),
        fetched_at=T0,
        fetch_id=receipt.fetch_id,
        payload_sha256=PAYLOAD_SHA,
        values={"value": 1.0},
        availability_precision=AvailabilityPrecision.EXACT,
        availability_policy="exact",
        available_at=T0 - timedelta(minutes=1),
    )


def test_unsupported_availability_precision_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported availability precision"):
        replace(
            exact_observation(),
            availability_precision=cast(AvailabilityPrecision, "BROKEN"),
        )


def test_date_only_boundary_defensive_none_path() -> None:
    item = replace(
        exact_observation(),
        availability_precision=AvailabilityPrecision.DATE_ONLY,
        available_at=None,
        available_date=date(2026, 1, 2),
    )
    object.__setattr__(item, "available_date", None)
    assert item.availability_boundary() is None


def test_revision_rank_refuses_unknown_availability() -> None:
    item = replace(
        exact_observation(),
        availability_precision=AvailabilityPrecision.UNKNOWN,
        available_at=None,
        available_date=None,
    )
    with pytest.raises(ValueError, match="cannot rank observation without availability"):
        contract._revision_rank(item)
