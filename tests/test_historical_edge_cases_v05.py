from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Mapping

import httpx
import pytest

from xrp_regime_engine.historical_backfill import (
    BackfillPage,
    BackfillRunner,
    BackfillWindow,
    NormalizedPageRecord,
)
from xrp_regime_engine.historical_spot_adapters import (
    BinanceKlineAdapter,
    CoinbaseCandleAdapter,
    HistoricalHTTPClient,
)
from xrp_regime_engine.historical_store import (
    BackfillCheckpointStore,
    ContentAddressedRawStore,
    DatasetManifest,
    DatasetPartition,
    HistoricalRecord,
    JSONLPartitionStore,
    ManifestStore,
    PointInTimeCatalog,
    sanitize_source_url,
)
from xrp_regime_engine.live_provider_plane import ProviderProtocolError, ProviderUnavailable


UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def resolver(host: str, port: int) -> tuple[str, ...]:
    del host, port
    return ("8.8.8.8",)


def historical_record(dataset: str = "dataset") -> HistoricalRecord:
    return HistoricalRecord(
        dataset=dataset,
        record_id="record",
        observed_at=BASE,
        available_at=BASE + timedelta(hours=1),
        source="source",
        revision=0,
        values={"close": 1},
        raw_payload_sha256="a" * 64,
    )


def test_window_record_and_page_contracts_fail_closed() -> None:
    with pytest.raises(ValueError, match="later"):
        BackfillWindow(BASE, BASE, 3600)
    with pytest.raises(ValueError, match="positive"):
        BackfillWindow(BASE, BASE + timedelta(hours=1), 0)
    with pytest.raises(ValueError, match="record_id"):
        NormalizedPageRecord("", BASE, BASE, {})
    with pytest.raises(ValueError, match="available_at"):
        NormalizedPageRecord("x", BASE, BASE - timedelta(seconds=1), {})
    with pytest.raises(ValueError, match="raw_payload"):
        BackfillPage(b"", "https://api.example.test", BASE, (), None, True, {})
    with pytest.raises(ValueError, match="completed page"):
        BackfillPage(b"{}", "https://api.example.test", BASE, (), {"page": 2}, True, {})
    with pytest.raises(ValueError, match="incomplete page"):
        BackfillPage(b"{}", "https://api.example.test", BASE, (), None, False, {})


def test_partition_and_manifest_reject_unsafe_or_mixed_inputs(tmp_path: Path) -> None:
    store = JSONLPartitionStore(tmp_path)
    with pytest.raises(ValueError, match="unsafe"):
        store.write_partition(dataset="dataset", partition_key="../escape", records=(historical_record(),))
    with pytest.raises(ValueError, match="another dataset"):
        store.write_partition(
            dataset="dataset",
            partition_key="date=2026-01-01",
            records=(historical_record("other"),),
        )
    with pytest.raises(ValueError, match="at least one"):
        store.write_partition(dataset="dataset", partition_key="date=2026-01-01", records=())
    with pytest.raises(ValueError, match="at least one partition"):
        DatasetManifest.build(
            dataset="dataset",
            schema_version="v1",
            created_at=BASE,
            partitions=(),
        )


def test_manifest_rejects_partition_from_another_dataset() -> None:
    partition = DatasetPartition(
        dataset="other",
        partition_key="date=2026-01-01",
        path="p",
        row_count=1,
        byte_count=1,
        file_sha256="a" * 64,
        minimum_observed_at=BASE,
        maximum_observed_at=BASE,
        minimum_available_at=BASE,
        maximum_available_at=BASE,
    )
    with pytest.raises(ValueError, match="another dataset"):
        DatasetManifest.build(
            dataset="dataset",
            schema_version="v1",
            created_at=BASE,
            partitions=(partition,),
        )


def test_source_url_contract_rejects_invalid_and_redacts_case_insensitively() -> None:
    with pytest.raises(ValueError, match="HTTP"):
        sanitize_source_url("file:///tmp/payload")
    with pytest.raises(ValueError, match="absolute"):
        sanitize_source_url("https:///missing-host")
    sanitized = sanitize_source_url("https://api.example.test/path?TOKEN=secret&pair=XRP")
    assert "secret" not in sanitized
    assert "pair=XRP" in sanitized


def test_catalog_count_all_and_checkpoint_key_contract(tmp_path: Path) -> None:
    catalog = PointInTimeCatalog(tmp_path / "catalog.sqlite")
    assert catalog.count() == 0
    assert catalog.add(historical_record(), partition_path="p") is True
    assert catalog.count() == 1
    checkpoints = BackfillCheckpointStore(tmp_path / "checkpoints.sqlite")
    with pytest.raises(ValueError, match="job_key"):
        checkpoints.save("", cursor={}, completed=False)


class EndlessAdapter:
    provider = "provider"
    source = "source"
    dataset = "dataset"
    schema_version = "v1"

    def initial_cursor(self, window: BackfillWindow) -> Mapping[str, Any]:
        del window
        return {"page": 0}

    def fetch_page(self, window: BackfillWindow, cursor: Mapping[str, Any]) -> BackfillPage:
        page = int(cursor["page"])
        return BackfillPage(
            raw_payload=json.dumps({"page": page}).encode(),
            source_url=f"https://api.example.test/history?page={page}",
            received_at=window.end + timedelta(hours=1),
            records=(
                NormalizedPageRecord(
                    f"r-{page}",
                    window.start,
                    window.start + timedelta(hours=1),
                    {"close": page},
                ),
            ),
            next_cursor={"page": page + 1},
            completed=False,
            attributes={},
        )


def test_runner_enforces_max_pages(tmp_path: Path) -> None:
    runner = BackfillRunner(
        raw_store=ContentAddressedRawStore(tmp_path),
        partition_store=JSONLPartitionStore(tmp_path),
        catalog=PointInTimeCatalog(tmp_path / "catalog.sqlite"),
        manifest_store=ManifestStore(tmp_path),
        checkpoints=BackfillCheckpointStore(tmp_path / "checkpoints.sqlite"),
        max_pages=1,
    )
    with pytest.raises(RuntimeError, match="max_pages"):
        runner.run(EndlessAdapter(), BackfillWindow(BASE, BASE + timedelta(hours=2), 3600))


def test_historical_http_client_rejects_scalar_oversize_and_retry_exhaustion() -> None:
    scalar = HistoricalHTTPClient(
        allowed_hosts=("api.example.test",),
        max_attempts=1,
        resolver=resolver,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json="scalar", request=request)
        ),
    )
    with pytest.raises(ProviderUnavailable):
        scalar.get_json_value("https://api.example.test/history")

    oversized = HistoricalHTTPClient(
        allowed_hosts=("api.example.test",),
        max_attempts=1,
        max_payload_bytes=5,
        resolver=resolver,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"large": "payload"}, request=request)
        ),
    )
    with pytest.raises(ProviderUnavailable):
        oversized.get_json_value("https://api.example.test/history")

    sleeps: list[float] = []
    unavailable = HistoricalHTTPClient(
        allowed_hosts=("api.example.test",),
        max_attempts=2,
        resolver=resolver,
        sleep=sleeps.append,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503, json={"error": "down"}, request=request)
        ),
    )
    with pytest.raises(ProviderUnavailable, match="2 attempt"):
        unavailable.get_json_value("https://api.example.test/history")
    assert sleeps == [1.0]


def test_historical_adapters_reject_bad_numeric_values_and_outside_cursor() -> None:
    for adapter_type, host, body in (
        (
            CoinbaseCandleAdapter,
            "api.exchange.coinbase.com",
            [[int(BASE.timestamp()), "low", "1", "1", "1", "1"]],
        ),
        (
            BinanceKlineAdapter,
            "api.binance.com",
            [[int(BASE.timestamp() * 1000), "open", "1", "1", "1", "1", int(BASE.timestamp() * 1000 + 3599999)]],
        ),
    ):
        client = HistoricalHTTPClient(
            allowed_hosts=(host,),
            resolver=resolver,
            clock=lambda: BASE + timedelta(days=1),
            transport=httpx.MockTransport(
                lambda request, body=body: httpx.Response(200, json=body, request=request)
            ),
        )
        adapter = adapter_type(client, interval_seconds=3600)
        window = BackfillWindow(BASE, BASE + timedelta(hours=2), 3600)
        with pytest.raises(ProviderProtocolError, match="invalid values"):
            adapter.fetch_page(window, adapter.initial_cursor(window))

    coinbase_client = HistoricalHTTPClient(
        allowed_hosts=("api.exchange.coinbase.com",),
        resolver=resolver,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[], request=request)),
    )
    coinbase = CoinbaseCandleAdapter(coinbase_client, interval_seconds=3600)
    window = BackfillWindow(BASE, BASE + timedelta(hours=2), 3600)
    with pytest.raises(ValueError, match="outside"):
        coinbase.fetch_page(window, {"start": (BASE - timedelta(hours=1)).isoformat()})

    binance_client = HistoricalHTTPClient(
        allowed_hosts=("api.binance.com",),
        resolver=resolver,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[], request=request)),
    )
    binance = BinanceKlineAdapter(binance_client, interval_seconds=3600)
    with pytest.raises(ValueError, match="outside"):
        binance.fetch_page(window, {"start_ms": int((BASE - timedelta(hours=1)).timestamp() * 1000)})
