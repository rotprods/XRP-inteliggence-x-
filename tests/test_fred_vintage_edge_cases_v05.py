from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from xrp_regime_engine.fred_vintage_adapter import FREDSeriesSpec, FREDVintageAdapter
from xrp_regime_engine.historical_backfill import BackfillWindow
from xrp_regime_engine.historical_spot_adapters import HistoricalHTTPClient
from xrp_regime_engine.live_provider_plane import ProviderProtocolError


UTC = timezone.utc
BASE = datetime(2025, 1, 1, tzinfo=UTC)
KEY = "b" * 32


def resolver(host: str, port: int) -> tuple[str, ...]:
    del host, port
    return ("8.8.8.8",)


def spec() -> FREDSeriesSpec:
    return FREDSeriesSpec("M2SL", "us_m2_monthly", "monthly", "liquidity", "billions_usd")


def make_client(handler) -> HistoricalHTTPClient:
    return HistoricalHTTPClient(
        allowed_hosts=("api.stlouisfed.org",),
        resolver=resolver,
        transport=httpx.MockTransport(handler),
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )


def make_adapter(handler, **kwargs) -> FREDVintageAdapter:
    return FREDVintageAdapter(
        make_client(handler),
        api_key=KEY,
        spec=spec(),
        vintage_start=date(2025, 1, 1),
        vintage_end=date(2025, 12, 31),
        **kwargs,
    )


def window() -> BackfillWindow:
    return BackfillWindow(BASE, BASE + timedelta(days=365), 86400)


def test_constructor_rejects_invalid_vintage_range_and_limits() -> None:
    client = make_client(lambda request: httpx.Response(200, json={}, request=request))
    with pytest.raises(ValueError, match="vintage_end"):
        FREDVintageAdapter(
            client,
            api_key=KEY,
            spec=spec(),
            vintage_start=date(2025, 2, 1),
            vintage_end=date(2025, 1, 1),
        )
    with pytest.raises(ValueError, match="limits"):
        FREDVintageAdapter(
            client,
            api_key=KEY,
            spec=spec(),
            vintage_start=date(2025, 1, 1),
            vintage_end=date(2025, 2, 1),
            vintage_limit=0,
        )


def test_discovery_rejects_malformed_cursor_root_and_pagination_metadata() -> None:
    adapter = make_adapter(lambda request: httpx.Response(200, json=[], request=request))
    with pytest.raises(ValueError, match="cursor"):
        adapter.fetch_page(window(), {"phase": "discover_vintages", "offset": -1})
    with pytest.raises(ProviderProtocolError, match="root"):
        adapter.fetch_page(window(), adapter.initial_cursor(window()))

    malformed = make_adapter(
        lambda request: httpx.Response(
            200,
            json={"count": "bad", "offset": 0, "limit": 1000, "vintage_dates": []},
            request=request,
        )
    )
    with pytest.raises(ProviderProtocolError, match="count"):
        malformed.fetch_page(window(), malformed.initial_cursor(window()))

    inconsistent = make_adapter(
        lambda request: httpx.Response(
            200,
            json={"count": 1, "offset": 1, "limit": 1000, "vintage_dates": ["2025-01-15"]},
            request=request,
        )
    )
    with pytest.raises(ProviderProtocolError, match="inconsistent"):
        inconsistent.fetch_page(window(), inconsistent.initial_cursor(window()))


def test_discovery_rejects_invalid_dates_empty_completion_and_maximum() -> None:
    invalid_list = make_adapter(
        lambda request: httpx.Response(
            200,
            json={"count": 1, "offset": 0, "limit": 1000, "vintage_dates": [123]},
            request=request,
        )
    )
    with pytest.raises(ProviderProtocolError, match="list"):
        invalid_list.fetch_page(window(), invalid_list.initial_cursor(window()))

    empty = make_adapter(
        lambda request: httpx.Response(
            200,
            json={"count": 0, "offset": 0, "limit": 1000, "vintage_dates": []},
            request=request,
        )
    )
    with pytest.raises(ProviderProtocolError, match="no vintage"):
        empty.fetch_page(window(), empty.initial_cursor(window()))

    too_many = make_adapter(
        lambda request: httpx.Response(
            200,
            json={
                "count": 2,
                "offset": 0,
                "limit": 1000,
                "vintage_dates": ["2025-01-15", "2025-02-15"],
            },
            request=request,
        ),
        max_vintage_dates=1,
    )
    with pytest.raises(ProviderProtocolError, match="maximum"):
        too_many.fetch_page(window(), too_many.initial_cursor(window()))


def test_observation_cursor_root_metadata_and_item_contracts() -> None:
    adapter = make_adapter(lambda request: httpx.Response(200, json=[], request=request))
    with pytest.raises(ValueError, match="outside"):
        adapter.fetch_page(
            window(),
            {
                "phase": "observations",
                "vintage_dates": ["2025-03-15"],
                "vintage_index": 2,
                "observation_offset": 0,
            },
        )
    with pytest.raises(ProviderProtocolError, match="root"):
        adapter.fetch_page(
            window(),
            {
                "phase": "observations",
                "vintage_dates": ["2025-03-15"],
                "vintage_index": 0,
                "observation_offset": 0,
            },
        )

    invalid_items = make_adapter(
        lambda request: httpx.Response(
            200,
            json={"count": 1, "offset": 0, "limit": 100000, "observations": [1]},
            request=request,
        )
    )
    with pytest.raises(ProviderProtocolError, match="must be an object"):
        invalid_items.fetch_page(
            window(),
            {
                "phase": "observations",
                "vintage_dates": ["2025-03-15"],
                "vintage_index": 0,
                "observation_offset": 0,
            },
        )


def test_observation_pagination_no_progress_and_invalid_date_are_blocked() -> None:
    no_progress = make_adapter(
        lambda request: httpx.Response(
            200,
            json={"count": 2, "offset": 0, "limit": 100000, "observations": []},
            request=request,
        )
    )
    cursor = {
        "phase": "observations",
        "vintage_dates": ["2025-03-15"],
        "vintage_index": 0,
        "observation_offset": 0,
    }
    with pytest.raises(ProviderProtocolError, match="no progress"):
        no_progress.fetch_page(window(), cursor)

    invalid_date = make_adapter(
        lambda request: httpx.Response(
            200,
            json={
                "count": 1,
                "offset": 0,
                "limit": 100000,
                "observations": [{"date": "not-a-date", "value": "1"}],
            },
            request=request,
        )
    )
    with pytest.raises(ProviderProtocolError, match="invalid FRED date"):
        invalid_date.fetch_page(window(), cursor)


def test_out_of_window_observation_is_skipped_without_forward_fill() -> None:
    adapter = make_adapter(
        lambda request: httpx.Response(
            200,
            json={
                "count": 1,
                "offset": 0,
                "limit": 100000,
                "observations": [{"date": "2024-01-01", "value": "100"}],
            },
            request=request,
        )
    )
    page = adapter.fetch_page(
        window(),
        {
            "phase": "observations",
            "vintage_dates": ["2025-03-15"],
            "vintage_index": 0,
            "observation_offset": 0,
        },
    )
    assert page.completed is True
    assert page.records == ()


def test_exploratory_series_preserves_zero_weight() -> None:
    cocoa = FREDSeriesSpec(
        "PCOCOUSDM",
        "global_cocoa_price_monthly",
        "monthly",
        "exploratory_commodity",
        "usd_per_metric_ton",
        weight=0.0,
        exploratory=True,
    )
    assert cocoa.weight == 0.0
    assert cocoa.exploratory is True
