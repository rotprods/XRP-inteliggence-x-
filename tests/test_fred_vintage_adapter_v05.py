from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json

import httpx
import pytest

from xrp_regime_engine.fred_vintage_adapter import (
    FREDSeriesSpec,
    FREDVintageAdapter,
)
from xrp_regime_engine.historical_backfill import BackfillWindow
from xrp_regime_engine.historical_spot_adapters import HistoricalHTTPClient
from xrp_regime_engine.live_provider_plane import ProviderProtocolError


UTC = timezone.utc
BASE = datetime(2025, 12, 1, tzinfo=UTC)
API_KEY = "a" * 32


def resolver(host: str, port: int) -> tuple[str, ...]:
    del host, port
    return ("8.8.8.8",)


def spec() -> FREDSeriesSpec:
    return FREDSeriesSpec(
        series_id="DGS10",
        dataset="us_treasury_10y_daily",
        frequency="daily",
        category="rates",
        units="percent",
        weight=1.0,
    )


def client(handler) -> HistoricalHTTPClient:
    return HistoricalHTTPClient(
        allowed_hosts=("api.stlouisfed.org",),
        resolver=resolver,
        transport=httpx.MockTransport(handler),
        clock=lambda: datetime(2026, 3, 1, tzinfo=UTC),
    )


def test_spec_and_adapter_redact_api_key() -> None:
    with pytest.raises(ValueError, match="series_id"):
        FREDSeriesSpec("../DGS10", "dataset", "daily", "rates", "percent")
    with pytest.raises(ValueError, match="weight"):
        FREDSeriesSpec("DGS10", "dataset", "daily", "rates", "percent", weight=-1)
    with pytest.raises(ValueError, match="api_key"):
        FREDVintageAdapter(
            client(lambda request: httpx.Response(200, json={}, request=request)),
            api_key="short",
            spec=spec(),
            vintage_start=date(2026, 1, 1),
            vintage_end=date(2026, 2, 1),
        )
    adapter = FREDVintageAdapter(
        client(lambda request: httpx.Response(200, json={}, request=request)),
        api_key=API_KEY,
        spec=spec(),
        vintage_start=date(2026, 1, 1),
        vintage_end=date(2026, 2, 1),
    )
    assert API_KEY not in repr(adapter)
    assert "[REDACTED]" in repr(adapter)


def test_vintage_discovery_paginates_and_redacts_source_url() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path.endswith("/series/vintagedates")
        assert request.url.params["api_key"] == API_KEY
        offset = int(request.url.params["offset"])
        body = {
            "count": 2,
            "offset": offset,
            "limit": 1,
            "vintage_dates": ["2026-01-15"] if offset == 0 else ["2026-02-15"],
        }
        return httpx.Response(200, json=body, request=request)

    adapter = FREDVintageAdapter(
        client(handler),
        api_key=API_KEY,
        spec=spec(),
        vintage_start=date(2026, 1, 1),
        vintage_end=date(2026, 2, 28),
        vintage_limit=1,
    )
    window = BackfillWindow(BASE, BASE + timedelta(days=100), 86400)
    cursor = adapter.initial_cursor(window)
    first = adapter.fetch_page(window, cursor)
    assert first.completed is False
    assert first.records == ()
    assert API_KEY not in first.source_url
    assert "%5BREDACTED%5D" in first.source_url
    assert first.next_cursor == {
        "phase": "discover_vintages",
        "offset": 1,
        "vintage_dates": ["2026-01-15"],
    }
    second = adapter.fetch_page(window, first.next_cursor or {})
    assert second.next_cursor == {
        "phase": "observations",
        "vintage_dates": ["2026-01-15", "2026-02-15"],
        "vintage_index": 0,
        "observation_offset": 0,
    }
    assert calls == 2


def test_observations_preserve_vintages_revisions_and_missing_values() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/series/observations")
        vintage = request.url.params["realtime_start"]
        assert request.url.params["realtime_end"] == vintage
        body = {
            "count": 2,
            "offset": 0,
            "limit": 100000,
            "observations": [
                {
                    "realtime_start": vintage,
                    "realtime_end": vintage,
                    "date": "2025-12-01",
                    "value": "4.25" if vintage == "2026-01-15" else "4.20",
                },
                {
                    "realtime_start": vintage,
                    "realtime_end": vintage,
                    "date": "2025-12-02",
                    "value": ".",
                },
            ],
        }
        return httpx.Response(200, json=body, request=request)

    adapter = FREDVintageAdapter(
        client(handler),
        api_key=API_KEY,
        spec=spec(),
        vintage_start=date(2026, 1, 1),
        vintage_end=date(2026, 2, 28),
    )
    window = BackfillWindow(BASE, BASE + timedelta(days=40), 86400)
    cursor = {
        "phase": "observations",
        "vintage_dates": ["2026-01-15", "2026-02-15"],
        "vintage_index": 0,
        "observation_offset": 0,
    }
    first = adapter.fetch_page(window, cursor)
    assert first.completed is False
    assert first.next_cursor == {
        "phase": "observations",
        "vintage_dates": ["2026-01-15", "2026-02-15"],
        "vintage_index": 1,
        "observation_offset": 0,
    }
    assert first.records[0].record_id == "DGS10:2025-12-01"
    assert first.records[0].revision == 0
    assert first.records[0].available_at == datetime(2026, 1, 15, tzinfo=UTC)
    assert first.records[0].values["value"] == "4.25"
    assert first.records[1].values["value"] is None
    assert first.records[1].values["missing"] is True
    assert API_KEY not in first.source_url

    second = adapter.fetch_page(window, first.next_cursor or {})
    assert second.completed is True
    assert second.next_cursor is None
    assert second.records[0].revision == 1
    assert second.records[0].values["value"] == "4.20"
    assert second.records[0].available_at == datetime(2026, 2, 15, tzinfo=UTC)


def test_observation_pagination_stays_on_vintage_until_complete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        observed = "2025-12-01" if offset == 0 else "2025-12-02"
        return httpx.Response(
            200,
            json={
                "count": 2,
                "offset": offset,
                "limit": 1,
                "observations": [{"date": observed, "value": "4.0"}],
            },
            request=request,
        )

    adapter = FREDVintageAdapter(
        client(handler),
        api_key=API_KEY,
        spec=spec(),
        vintage_start=date(2026, 1, 1),
        vintage_end=date(2026, 1, 31),
        observation_limit=1,
    )
    window = BackfillWindow(BASE, BASE + timedelta(days=40), 86400)
    cursor = {
        "phase": "observations",
        "vintage_dates": ["2026-01-15"],
        "vintage_index": 0,
        "observation_offset": 0,
    }
    first = adapter.fetch_page(window, cursor)
    assert first.completed is False
    assert first.next_cursor == {
        "phase": "observations",
        "vintage_dates": ["2026-01-15"],
        "vintage_index": 0,
        "observation_offset": 1,
    }
    second = adapter.fetch_page(window, first.next_cursor or {})
    assert second.completed is True


def test_fred_cursor_and_payload_failures_are_blocked() -> None:
    adapter = FREDVintageAdapter(
        client(lambda request: httpx.Response(200, json={}, request=request)),
        api_key=API_KEY,
        spec=spec(),
        vintage_start=date(2026, 1, 1),
        vintage_end=date(2026, 2, 1),
    )
    window = BackfillWindow(BASE, BASE + timedelta(days=40), 86400)
    with pytest.raises(ValueError, match="unsupported"):
        adapter.fetch_page(window, {"phase": "unknown"})
    with pytest.raises(ValueError, match="no vintage dates"):
        adapter.fetch_page(
            window,
            {"phase": "observations", "vintage_dates": [], "vintage_index": 0},
        )


def test_fred_rejects_pagination_without_progress_and_future_semantics() -> None:
    def no_progress(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"count": 2, "offset": 0, "limit": 1000, "vintage_dates": []},
            request=request,
        )

    adapter = FREDVintageAdapter(
        client(no_progress),
        api_key=API_KEY,
        spec=spec(),
        vintage_start=date(2026, 1, 1),
        vintage_end=date(2026, 2, 1),
    )
    window = BackfillWindow(BASE, BASE + timedelta(days=40), 86400)
    with pytest.raises(ProviderProtocolError, match="no progress"):
        adapter.fetch_page(window, adapter.initial_cursor(window))

    def future_observation(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "count": 1,
                "offset": 0,
                "limit": 100000,
                "observations": [{"date": "2026-02-01", "value": "1"}],
            },
            request=request,
        )

    future_adapter = FREDVintageAdapter(
        client(future_observation),
        api_key=API_KEY,
        spec=spec(),
        vintage_start=date(2026, 1, 1),
        vintage_end=date(2026, 1, 31),
    )
    future_window = BackfillWindow(BASE, datetime(2026, 3, 1, tzinfo=UTC), 86400)
    with pytest.raises(ProviderProtocolError, match="precedes"):
        future_adapter.fetch_page(
            future_window,
            {
                "phase": "observations",
                "vintage_dates": ["2026-01-15"],
                "vintage_index": 0,
                "observation_offset": 0,
            },
        )


def test_fred_rejects_invalid_numeric_values() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "count": 1,
                "offset": 0,
                "limit": 100000,
                "observations": [{"date": "2025-12-01", "value": "not-a-number"}],
            },
            request=request,
        )

    adapter = FREDVintageAdapter(
        client(handler),
        api_key=API_KEY,
        spec=spec(),
        vintage_start=date(2026, 1, 1),
        vintage_end=date(2026, 1, 31),
    )
    with pytest.raises(ProviderProtocolError, match="value is invalid"):
        adapter.fetch_page(
            BackfillWindow(BASE, BASE + timedelta(days=40), 86400),
            {
                "phase": "observations",
                "vintage_dates": ["2026-01-15"],
                "vintage_index": 0,
                "observation_offset": 0,
            },
        )
