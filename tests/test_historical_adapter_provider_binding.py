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


class ClaimedKrakenAdapter:
    provider = "kraken"
    dataset = "xrp_spot_1h"
    schema_version = "historical-observation-v2"

    def initial_cursor(self, window: BackfillWindowV2) -> dict[str, object]:
        del window
        return {"page": 1}

    def fetch_page(
        self,
        window: BackfillWindowV2,
        cursor: dict[str, object],
    ) -> BackfillPageV2:
        del window, cursor
        raw = b'{"provider":"coinbase","close":2.0}'
        payload_sha = sha256(raw).hexdigest()
        receipt = FetchReceipt.create(
            source_id="source:coinbase",
            provider="coinbase",
            canonical_uri="https://example.com/coinbase/history",
            endpoint="/history",
            request_fingerprint=sha256(b"request").hexdigest(),
            fetched_at=T0,
            payload_sha256=payload_sha,
            ingestion_version="2",
            parser_version="2",
        )
        observation = HistoricalObservation(
            observation_id="obs:coinbase:1",
            dataset=self.dataset,
            record_id="record:1",
            provider="coinbase",
            source_id=receipt.source_id,
            symbol="XRP_USD",
            instrument="spot",
            observed_at=T0 - timedelta(hours=1),
            fetched_at=T0,
            fetch_id=receipt.fetch_id,
            payload_sha256=payload_sha,
            values={"close": 2.0},
            availability_precision=AvailabilityPrecision.EXACT,
            availability_policy="provider_exact",
            available_at=T0 - timedelta(minutes=1),
        )
        return BackfillPageV2(
            raw_payload=raw,
            receipt=receipt,
            observations=(observation,),
            partition_key="date=2026-01-02",
            next_cursor=None,
            completed=True,
        )


def test_adapter_provider_mismatch_fails_before_persistence(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    adapter = ClaimedKrakenAdapter()
    window = BackfillWindowV2(
        start=T0 - timedelta(days=1),
        end=T0,
        interval_seconds=3600,
    )

    with pytest.raises(ValueError, match="receipt provider"):
        BackfillRunnerV2(store).run(adapter, window)

    assert store.raw_blob_count() == 0
    assert store.fetch_receipt_count() == 0
    assert store.observation_count() == 0
    assert store.load_checkpoint(BackfillRunnerV2.job_key(adapter, window)) is None
