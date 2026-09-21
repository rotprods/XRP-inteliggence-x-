from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.historical_contract import (
    AmbiguousRevisionError,
    AvailabilityPrecision,
    EligibilityClass,
    FetchReceipt,
    HistoricalObservation,
    SourceSnapshot,
    select_as_of,
)

T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
PAYLOAD_SHA = sha256(b"payload").hexdigest()
REQUEST_SHA = sha256(b"request").hexdigest()


def fetch_id(provider: str = "coinbase") -> str:
    return FetchReceipt.create(
        source_id=f"source:{provider}",
        provider=provider,
        canonical_uri="https://example.com/market",
        endpoint="/market",
        request_fingerprint=REQUEST_SHA,
        fetched_at=T0,
        payload_sha256=PAYLOAD_SHA,
        ingestion_version="2",
        parser_version="2",
    ).fetch_id


def obs(
    observation_id: str,
    *,
    provider: str = "coinbase",
    available_at: datetime | None = T0 - timedelta(minutes=1),
    available_date: date | None = None,
    precision: AvailabilityPrecision = AvailabilityPrecision.EXACT,
    fetched_at: datetime = T0,
    revision: int = 0,
    value: float = 1.0,
    reconstruction_basis_id: str | None = None,
) -> HistoricalObservation:
    return HistoricalObservation(
        observation_id=observation_id,
        dataset="xrp_spot_1h",
        record_id="2026-01-02T11:00:00Z",
        provider=provider,
        source_id=f"source:{provider}",
        symbol="XRP_USD" if provider == "coinbase" else "XRP_USDT",
        instrument="spot",
        observed_at=T0 - timedelta(hours=1),
        fetched_at=fetched_at,
        fetch_id=fetch_id(provider),
        payload_sha256=PAYLOAD_SHA,
        values={"close": value},
        availability_precision=precision,
        availability_policy="provider_exact",
        available_at=available_at,
        available_date=available_date,
        revision_sequence=revision,
        reconstruction_basis_id=reconstruction_basis_id,
    )


def test_fetch_receipt_rejects_credentials() -> None:
    with pytest.raises(ValueError, match="credentials"):
        FetchReceipt.create(
            source_id="s",
            provider="p",
            canonical_uri="https://u:p@example.com/x",
            endpoint="/x",
            request_fingerprint=REQUEST_SHA,
            fetched_at=T0,
            payload_sha256=PAYLOAD_SHA,
            ingestion_version="2",
            parser_version="2",
        )


def test_future_fetch_is_not_strict_replay() -> None:
    item = obs("a", fetched_at=T0 + timedelta(minutes=1))
    assert item.eligibility_at(T0) is EligibilityClass.INELIGIBLE


def test_reconstructed_pit_requires_explicit_basis() -> None:
    item = obs(
        "a",
        fetched_at=T0 + timedelta(days=20),
        reconstruction_basis_id="alfred:vintage:2026-01-02",
    )
    assert item.eligibility_at(T0) is EligibilityClass.RECONSTRUCTED_PIT


def test_date_only_fails_closed_until_next_utc_day() -> None:
    item = obs(
        "a",
        precision=AvailabilityPrecision.DATE_ONLY,
        available_at=None,
        available_date=date(2026, 1, 2),
        fetched_at=T0 - timedelta(days=1),
    )
    assert (
        item.eligibility_at(datetime(2026, 1, 2, 23, 59, tzinfo=UTC))
        is EligibilityClass.INELIGIBLE
    )
    assert (
        item.eligibility_at(datetime(2026, 1, 3, 0, 0, tzinfo=UTC))
        is EligibilityClass.STRICT_REPLAY
    )


def test_unknown_availability_is_ineligible() -> None:
    item = obs(
        "a",
        precision=AvailabilityPrecision.UNKNOWN,
        available_at=None,
    )
    assert item.eligibility_at(T0 + timedelta(days=30)) is EligibilityClass.INELIGIBLE


def test_as_of_preserves_provider_independence() -> None:
    rows = select_as_of((obs("a"), obs("b", provider="binance")), prediction_time=T0)
    assert {row.provider for row in rows} == {"coinbase", "binance"}


def test_as_of_preserves_distinct_logical_series() -> None:
    hourly = obs("hourly")
    five_minute = replace(obs("five-minute"), dataset="xrp_spot_5m")
    rows = select_as_of((hourly, five_minute), prediction_time=T0)
    assert {row.dataset for row in rows} == {"xrp_spot_1h", "xrp_spot_5m"}


def test_as_of_rejects_future_revision() -> None:
    old = obs(
        "old",
        available_at=T0 - timedelta(minutes=5),
        fetched_at=T0 - timedelta(minutes=4),
        revision=0,
        value=1.0,
    )
    future = obs(
        "future",
        available_at=T0 + timedelta(minutes=5),
        fetched_at=T0 + timedelta(minutes=6),
        revision=1,
        value=2.0,
    )
    assert select_as_of((old, future), prediction_time=T0) == (old,)


def test_equally_ranked_conflicts_fail_closed() -> None:
    with pytest.raises(AmbiguousRevisionError, match="equally ranked"):
        select_as_of((obs("a", value=1.0), obs("b", value=2.0)), prediction_time=T0)


def test_snapshot_is_order_independent() -> None:
    a = obs("a")
    b = obs("b", provider="binance")
    left = SourceSnapshot.build((a, b), prediction_time=T0)
    right = SourceSnapshot.build((b, a), prediction_time=T0)
    assert left.snapshot_sha256 == right.snapshot_sha256
    assert left.provider_universe == ("binance", "coinbase")


def test_snapshot_rejects_duplicate_observation_ids() -> None:
    first = obs("duplicate")
    second = replace(obs("duplicate", provider="binance"), observation_id="duplicate")
    with pytest.raises(ValueError, match="observation_id values must be unique"):
        SourceSnapshot.build((first, second), prediction_time=T0)


def test_snapshot_reconstructed_requires_opt_in() -> None:
    item = obs(
        "r",
        fetched_at=T0 + timedelta(days=20),
        reconstruction_basis_id="archive:v1",
    )
    with pytest.raises(ValueError, match="opt-in"):
        SourceSnapshot.build((item,), prediction_time=T0)
    snapshot = SourceSnapshot.build(
        (item,),
        prediction_time=T0,
        allow_reconstructed=True,
    )
    assert snapshot.eligibility_class is EligibilityClass.RECONSTRUCTED_PIT
