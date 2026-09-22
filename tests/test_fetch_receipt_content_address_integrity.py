from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256

import pytest

from xrp_regime_engine.historical_contract import FetchReceipt
from xrp_regime_engine.historical_store_v2 import HistoricalEvidenceStoreV2

T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
PAYLOAD = b"payload"
PAYLOAD_SHA = sha256(PAYLOAD).hexdigest()
OTHER_PAYLOAD_SHA = sha256(b"other-payload").hexdigest()
REQUEST_SHA = sha256(b"request").hexdigest()
OTHER_REQUEST_SHA = sha256(b"other-request").hexdigest()


def receipt() -> FetchReceipt:
    return FetchReceipt.create(
        source_id="source:kraken_spot",
        provider="kraken_spot",
        canonical_uri="https://api.kraken.com/0/public/OHLC?interval=60&pair=XRPUSD",
        endpoint="/0/public/OHLC",
        request_fingerprint=REQUEST_SHA,
        fetched_at=T0,
        payload_sha256=PAYLOAD_SHA,
        ingestion_version="2",
        parser_version="2",
    )


def test_created_receipt_is_bound_to_canonical_payload() -> None:
    item = receipt()
    assert item.fetch_id == f"fetch:sha256:{item.canonical_sha256}"
    item.validate_identity()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_id", "source:kraken_spot:other"),
        ("provider", "other_provider"),
        ("canonical_uri", "https://api.kraken.com/0/public/OHLC?interval=5&pair=XRPUSD"),
        ("endpoint", "/0/public/Trades"),
        ("request_fingerprint", OTHER_REQUEST_SHA),
        ("fetched_at", T0 + timedelta(seconds=1)),
        ("payload_sha256", OTHER_PAYLOAD_SHA),
        ("ingestion_version", "3"),
        ("parser_version", "3"),
    ),
)
def test_replace_rejects_stale_fetch_id_when_identity_material_changes(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match="canonical receipt payload"):
        replace(receipt(), **{field: value})


def test_direct_constructor_rejects_valid_but_stale_fetch_id() -> None:
    original = receipt()
    with pytest.raises(ValueError, match="canonical receipt payload"):
        FetchReceipt(
            fetch_id=original.fetch_id,
            source_id=original.source_id,
            provider="forged-provider",
            canonical_uri=original.canonical_uri,
            endpoint=original.endpoint,
            request_fingerprint=original.request_fingerprint,
            fetched_at=original.fetched_at,
            payload_sha256=original.payload_sha256,
            ingestion_version=original.ingestion_version,
            parser_version=original.parser_version,
        )


def test_stale_direct_constructor_fails_before_first_store_insert(tmp_path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    original = receipt()
    with pytest.raises(ValueError, match="canonical receipt payload"):
        forged = FetchReceipt(
            fetch_id=original.fetch_id,
            source_id=original.source_id,
            provider="forged-provider",
            canonical_uri=original.canonical_uri,
            endpoint=original.endpoint,
            request_fingerprint=original.request_fingerprint,
            fetched_at=original.fetched_at,
            payload_sha256=original.payload_sha256,
            ingestion_version=original.ingestion_version,
            parser_version=original.parser_version,
        )
        store.record_fetch(PAYLOAD, forged)
    assert not (tmp_path / "raw").exists()


def test_identity_uses_normalized_utc_fetch_time() -> None:
    offset_time = T0.astimezone(timezone(timedelta(hours=2)))
    left = FetchReceipt.create(
        source_id=" source:kraken_spot ",
        provider=" kraken_spot ",
        canonical_uri="https://api.kraken.com/0/public/OHLC?interval=60&pair=XRPUSD",
        endpoint=" /0/public/OHLC ",
        request_fingerprint=REQUEST_SHA,
        fetched_at=offset_time,
        payload_sha256=PAYLOAD_SHA,
        ingestion_version=" 2 ",
        parser_version=" 2 ",
    )
    right = receipt()
    assert left.fetch_id == right.fetch_id
    assert left.fetched_at == T0
    assert left.source_id == "source:kraken_spot"
    assert left.provider == "kraken_spot"
    assert left.endpoint == "/0/public/OHLC"
    assert left.ingestion_version == "2"
    assert left.parser_version == "2"


def test_post_construction_tampering_is_detectable() -> None:
    item = receipt()
    object.__setattr__(item, "provider", "forged-provider")
    with pytest.raises(ValueError, match="canonical receipt payload"):
        item.validate_identity()
