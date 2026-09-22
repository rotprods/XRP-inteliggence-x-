from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from xrp_regime_engine.historical_backfill_v2 import (
    BackfillPageV2,
    BackfillRunnerV2,
    BackfillWindowV2,
)
from xrp_regime_engine.historical_contract import (
    AvailabilityPrecision,
    FetchReceipt,
    HistoricalObservation,
)
from xrp_regime_engine.historical_store_v2 import HistoricalEvidenceStoreV2

T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
WINDOW_START = T0 - timedelta(days=1)
WINDOW_END = T0
FETCHED_AT = T0 + timedelta(hours=1)
REQUEST_SHA = sha256(b"h7-window-generation-gauntlet").hexdigest()


def window() -> BackfillWindowV2:
    return BackfillWindowV2(
        start=WINDOW_START,
        end=WINDOW_END,
        interval_seconds=3600,
    )


class SinglePageAdapter:
    provider = "kraken"
    dataset = "xrp_spot_1h"
    schema_version = "historical-observation-v2"

    def __init__(
        self,
        *,
        observed_times: tuple[datetime, ...] = (WINDOW_START,),
        ingestion_version: str = "2",
        parser_version: str = "2",
        receipt_ingestion_version: str | None = None,
        receipt_parser_version: str | None = None,
    ) -> None:
        self.observed_times = observed_times
        self.ingestion_version = ingestion_version
        self.parser_version = parser_version
        self.receipt_ingestion_version = receipt_ingestion_version or ingestion_version
        self.receipt_parser_version = receipt_parser_version or parser_version

    def initial_cursor(self, window: BackfillWindowV2) -> dict[str, object]:
        del window
        return {"page": 1}

    def fetch_page(
        self,
        window: BackfillWindowV2,
        cursor: dict[str, object],
    ) -> BackfillPageV2:
        del window, cursor
        raw = b'{"provider":"kraken","dataset":"xrp_spot_1h"}'
        payload_sha = sha256(raw).hexdigest()
        receipt = FetchReceipt.create(
            source_id="source:kraken",
            provider=self.provider,
            canonical_uri="https://example.com/kraken/history",
            endpoint="/history",
            request_fingerprint=REQUEST_SHA,
            fetched_at=FETCHED_AT,
            payload_sha256=payload_sha,
            ingestion_version=self.receipt_ingestion_version,
            parser_version=self.receipt_parser_version,
        )
        observations = tuple(
            HistoricalObservation(
                observation_id=f"obs:kraken:{index}",
                dataset=self.dataset,
                record_id=f"record:{index}",
                provider=self.provider,
                source_id=receipt.source_id,
                symbol="XRP_USD",
                instrument="spot",
                observed_at=observed_at,
                fetched_at=receipt.fetched_at,
                fetch_id=receipt.fetch_id,
                payload_sha256=payload_sha,
                values={"close": 2.0 + index / 100},
                availability_precision=AvailabilityPrecision.EXACT,
                availability_policy="provider_exact",
                available_at=observed_at,
            )
            for index, observed_at in enumerate(self.observed_times)
        )
        return BackfillPageV2(
            raw_payload=raw,
            receipt=receipt,
            observations=observations,
            partition_key="date=2026-01-01",
            next_cursor=None,
            completed=True,
        )


def assert_no_persistence(
    store: HistoricalEvidenceStoreV2,
    adapter: SinglePageAdapter,
    backfill_window: BackfillWindowV2,
) -> None:
    assert store.raw_blob_count() == 0
    assert store.fetch_receipt_count() == 0
    assert store.observation_count() == 0
    assert store.load_checkpoint(BackfillRunnerV2.job_key(adapter, backfill_window)) is None


@pytest.mark.parametrize(
    ("observed_at", "accepted"),
    [
        (WINDOW_START - timedelta(microseconds=1), False),
        (WINDOW_START, True),
        (WINDOW_END - timedelta(microseconds=1), True),
        (WINDOW_END, False),
        (WINDOW_END + timedelta(microseconds=1), False),
    ],
)
def test_backfill_window_is_half_open_and_fail_closed(
    tmp_path: Path,
    observed_at: datetime,
    accepted: bool,
) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    adapter = SinglePageAdapter(observed_times=(observed_at,))
    backfill_window = window()
    runner = BackfillRunnerV2(store)

    if accepted:
        result = runner.run(adapter, backfill_window)
        assert result.completed is True
        assert result.manifest is not None
        assert result.manifest.total_rows == 1
        assert store.fetch_receipt_count() == 1
        assert store.observation_count() == 1
    else:
        with pytest.raises(ValueError, match="outside backfill window"):
            runner.run(adapter, backfill_window)
        assert_no_persistence(store, adapter, backfill_window)


def test_mixed_page_with_one_out_of_window_observation_is_atomic_failure(
    tmp_path: Path,
) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    adapter = SinglePageAdapter(
        observed_times=(
            WINDOW_START,
            WINDOW_END,
        )
    )
    backfill_window = window()

    with pytest.raises(ValueError, match="outside backfill window"):
        BackfillRunnerV2(store).run(adapter, backfill_window)

    assert_no_persistence(store, adapter, backfill_window)


def test_job_key_binds_parser_and_ingestion_generation() -> None:
    backfill_window = window()
    baseline = SinglePageAdapter()
    parser_changed = SinglePageAdapter(parser_version="3")
    ingestion_changed = SinglePageAdapter(ingestion_version="3")

    baseline_key = BackfillRunnerV2.job_key(baseline, backfill_window)
    assert BackfillRunnerV2.job_key(SinglePageAdapter(), backfill_window) == baseline_key
    assert BackfillRunnerV2.job_key(parser_changed, backfill_window) != baseline_key
    assert BackfillRunnerV2.job_key(ingestion_changed, backfill_window) != baseline_key


@pytest.mark.parametrize(
    ("receipt_ingestion_version", "receipt_parser_version", "expected_message"),
    [
        ("3", "2", "ingestion_version"),
        ("2", "3", "parser_version"),
    ],
)
def test_receipt_generation_mismatch_fails_before_persistence(
    tmp_path: Path,
    receipt_ingestion_version: str,
    receipt_parser_version: str,
    expected_message: str,
) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    adapter = SinglePageAdapter(
        receipt_ingestion_version=receipt_ingestion_version,
        receipt_parser_version=receipt_parser_version,
    )
    backfill_window = window()

    with pytest.raises(ValueError, match=expected_message):
        BackfillRunnerV2(store).run(adapter, backfill_window)

    assert_no_persistence(store, adapter, backfill_window)


@pytest.mark.parametrize(
    ("ingestion_version", "parser_version"),
    [
        ("", "2"),
        ("   ", "2"),
        ("2", ""),
        ("2", "   "),
    ],
)
def test_empty_adapter_generation_is_rejected_before_job_identity(
    ingestion_version: str,
    parser_version: str,
) -> None:
    adapter = SinglePageAdapter(
        ingestion_version=ingestion_version,
        parser_version=parser_version,
    )

    with pytest.raises(ValueError, match="cannot be empty"):
        BackfillRunnerV2.job_key(adapter, window())
