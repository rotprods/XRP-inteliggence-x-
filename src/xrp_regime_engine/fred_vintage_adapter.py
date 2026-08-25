from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping, Sequence

from xrp_regime_engine.historical_backfill import (
    BackfillPage,
    BackfillWindow,
    NormalizedPageRecord,
)
from xrp_regime_engine.historical_spot_adapters import HistoricalHTTPClient
from xrp_regime_engine.historical_store import sanitize_source_url
from xrp_regime_engine.live_provider_plane import ProviderProtocolError


_API_KEY_PATTERN = re.compile(r"^[a-z0-9]{32}$")


def _date_at_utc(raw: str) -> datetime:
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ProviderProtocolError(f"invalid FRED date: {raw}") from exc
    return datetime.combine(parsed, time.min, tzinfo=timezone.utc)


def _require_int(payload: Mapping[str, Any], key: str) -> int:
    try:
        return int(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderProtocolError(f"FRED payload has no valid {key}") from exc


@dataclass(frozen=True, slots=True)
class FREDSeriesSpec:
    series_id: str
    dataset: str
    frequency: str
    category: str
    units: str
    weight: float = 1.0
    exploratory: bool = False

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z0-9_.-]+", self.series_id):
            raise ValueError("series_id contains unsafe characters")
        if not re.fullmatch(r"[a-z0-9_.-]+", self.dataset):
            raise ValueError("dataset contains unsafe characters")
        if not self.frequency or not self.category or not self.units:
            raise ValueError("frequency, category and units are required")
        if self.weight < 0:
            raise ValueError("weight cannot be negative")


class FREDVintageAdapter:
    """Discovers FRED vintage dates, then records each series state at each vintage."""

    provider = "fred"
    schema_version = "fred-observation.v1"
    vintage_endpoint = "https://api.stlouisfed.org/fred/series/vintagedates"
    observations_endpoint = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(
        self,
        client: HistoricalHTTPClient,
        *,
        api_key: str,
        spec: FREDSeriesSpec,
        vintage_start: date,
        vintage_end: date,
        vintage_limit: int = 1000,
        observation_limit: int = 100_000,
        max_vintage_dates: int = 5_000,
    ) -> None:
        if not _API_KEY_PATTERN.fullmatch(api_key):
            raise ValueError("FRED api_key must be a 32-character lowercase alphanumeric key")
        if vintage_end < vintage_start:
            raise ValueError("vintage_end cannot precede vintage_start")
        if vintage_limit <= 0 or observation_limit <= 0 or max_vintage_dates <= 0:
            raise ValueError("FRED pagination limits must be positive")
        self.client = client
        self._api_key = api_key
        self.spec = spec
        self.dataset = spec.dataset
        self.source = f"fred:{spec.series_id}"
        self.vintage_start = vintage_start
        self.vintage_end = vintage_end
        self.vintage_limit = min(vintage_limit, 1000)
        self.observation_limit = min(observation_limit, 100_000)
        self.max_vintage_dates = max_vintage_dates

    def __repr__(self) -> str:
        return (
            f"FREDVintageAdapter(series_id={self.spec.series_id!r}, "
            f"dataset={self.dataset!r}, api_key='[REDACTED]')"
        )

    def initial_cursor(self, window: BackfillWindow) -> Mapping[str, Any]:
        del window
        return {
            "phase": "discover_vintages",
            "offset": 0,
            "vintage_dates": [],
        }

    def _base_params(self) -> dict[str, str | int]:
        return {
            "series_id": self.spec.series_id,
            "api_key": self._api_key,
            "file_type": "json",
        }

    def _discover_vintages(self, cursor: Mapping[str, Any]) -> BackfillPage:
        try:
            offset = int(cursor.get("offset", 0))
            accumulated = list(cursor.get("vintage_dates", []))
        except (TypeError, ValueError) as exc:
            raise ValueError("FRED vintage cursor is malformed") from exc
        if offset < 0 or any(not isinstance(item, str) for item in accumulated):
            raise ValueError("FRED vintage cursor is malformed")

        params = {
            **self._base_params(),
            "realtime_start": self.vintage_start.isoformat(),
            "realtime_end": self.vintage_end.isoformat(),
            "sort_order": "asc",
            "limit": self.vintage_limit,
            "offset": offset,
        }
        payload = self.client.get_json_value(self.vintage_endpoint, params=params)
        if not isinstance(payload.data, Mapping):
            raise ProviderProtocolError("FRED vintage-date root must be an object")
        raw_dates = payload.data.get("vintage_dates")
        if not isinstance(raw_dates, list) or any(not isinstance(item, str) for item in raw_dates):
            raise ProviderProtocolError("FRED vintage_dates must be a list of date strings")
        count = _require_int(payload.data, "count")
        response_offset = _require_int(payload.data, "offset")
        response_limit = _require_int(payload.data, "limit")
        if response_offset != offset or response_limit <= 0 or count < 0:
            raise ProviderProtocolError("FRED vintage pagination metadata is inconsistent")

        dates = accumulated + raw_dates
        deduplicated = sorted(set(dates))
        if len(deduplicated) > self.max_vintage_dates:
            raise ProviderProtocolError("FRED vintage-date discovery exceeded its configured maximum")
        next_offset = offset + len(raw_dates)
        more = next_offset < count
        if more and not raw_dates:
            raise ProviderProtocolError("FRED vintage pagination made no progress")
        if more:
            next_cursor: Mapping[str, Any] | None = {
                "phase": "discover_vintages",
                "offset": next_offset,
                "vintage_dates": deduplicated,
            }
        else:
            if not deduplicated:
                raise ProviderProtocolError("FRED returned no vintage dates for the configured window")
            next_cursor = {
                "phase": "observations",
                "vintage_dates": deduplicated,
                "vintage_index": 0,
                "observation_offset": 0,
            }

        return BackfillPage(
            raw_payload=payload.raw_payload,
            source_url=sanitize_source_url(payload.source_url),
            received_at=payload.received_at,
            records=(),
            next_cursor=next_cursor,
            completed=False,
            attributes={
                "adapter": "fred-vintage-discovery",
                "series_id": self.spec.series_id,
                "offset": offset,
                "dates_discovered": len(deduplicated),
                "attempts": payload.attempts,
                "latency_ms": payload.latency_ms,
            },
        )

    def _fetch_observations(
        self,
        window: BackfillWindow,
        cursor: Mapping[str, Any],
    ) -> BackfillPage:
        raw_dates = cursor.get("vintage_dates")
        if not isinstance(raw_dates, list) or not raw_dates or any(
            not isinstance(item, str) for item in raw_dates
        ):
            raise ValueError("FRED observations cursor has no vintage dates")
        try:
            vintage_index = int(cursor.get("vintage_index", 0))
            offset = int(cursor.get("observation_offset", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("FRED observations cursor is malformed") from exc
        if not 0 <= vintage_index < len(raw_dates) or offset < 0:
            raise ValueError("FRED observations cursor is outside its discovered vintage range")

        vintage_date = raw_dates[vintage_index]
        available_at = _date_at_utc(vintage_date)
        params = {
            **self._base_params(),
            "realtime_start": vintage_date,
            "realtime_end": vintage_date,
            "observation_start": window.start.date().isoformat(),
            "observation_end": window.end.date().isoformat(),
            "sort_order": "asc",
            "output_type": 1,
            "limit": self.observation_limit,
            "offset": offset,
        }
        payload = self.client.get_json_value(self.observations_endpoint, params=params)
        if not isinstance(payload.data, Mapping):
            raise ProviderProtocolError("FRED observation root must be an object")
        observations = payload.data.get("observations")
        if not isinstance(observations, list):
            raise ProviderProtocolError("FRED observations must be a list")
        count = _require_int(payload.data, "count")
        response_offset = _require_int(payload.data, "offset")
        response_limit = _require_int(payload.data, "limit")
        if response_offset != offset or response_limit <= 0 or count < 0:
            raise ProviderProtocolError("FRED observation pagination metadata is inconsistent")

        records: list[NormalizedPageRecord] = []
        for item in observations:
            if not isinstance(item, Mapping):
                raise ProviderProtocolError("FRED observation must be an object")
            observed_at = _date_at_utc(str(item.get("date", "")))
            if not window.start <= observed_at < window.end:
                continue
            if available_at < observed_at:
                raise ProviderProtocolError(
                    "FRED vintage date precedes the observation date; point-in-time semantics are invalid"
                )
            raw_value = str(item.get("value", "."))
            if raw_value == ".":
                value: str | None = None
                missing = True
            else:
                try:
                    value = str(Decimal(raw_value))
                except InvalidOperation as exc:
                    raise ProviderProtocolError("FRED observation value is invalid") from exc
                missing = False
            records.append(
                NormalizedPageRecord(
                    record_id=f"{self.spec.series_id}:{observed_at.date().isoformat()}",
                    observed_at=observed_at,
                    available_at=available_at,
                    revision=vintage_index,
                    values={
                        "series_id": self.spec.series_id,
                        "value": value,
                        "missing": missing,
                        "frequency": self.spec.frequency,
                        "category": self.spec.category,
                        "units": self.spec.units,
                        "vintage_date": vintage_date,
                        "weight": self.spec.weight,
                        "exploratory": self.spec.exploratory,
                    },
                )
            )

        next_offset = offset + len(observations)
        more_in_vintage = next_offset < count
        if more_in_vintage and not observations:
            raise ProviderProtocolError("FRED observation pagination made no progress")
        if more_in_vintage:
            next_cursor: Mapping[str, Any] | None = {
                "phase": "observations",
                "vintage_dates": raw_dates,
                "vintage_index": vintage_index,
                "observation_offset": next_offset,
            }
            completed = False
        elif vintage_index + 1 < len(raw_dates):
            next_cursor = {
                "phase": "observations",
                "vintage_dates": raw_dates,
                "vintage_index": vintage_index + 1,
                "observation_offset": 0,
            }
            completed = False
        else:
            next_cursor = None
            completed = True

        return BackfillPage(
            raw_payload=payload.raw_payload,
            source_url=sanitize_source_url(payload.source_url),
            received_at=payload.received_at,
            records=tuple(records),
            next_cursor=next_cursor,
            completed=completed,
            attributes={
                "adapter": "fred-vintage-observations",
                "series_id": self.spec.series_id,
                "vintage_date": vintage_date,
                "vintage_index": vintage_index,
                "observation_offset": offset,
                "attempts": payload.attempts,
                "latency_ms": payload.latency_ms,
            },
        )

    def fetch_page(
        self,
        window: BackfillWindow,
        cursor: Mapping[str, Any],
    ) -> BackfillPage:
        phase = cursor.get("phase")
        if phase == "discover_vintages":
            return self._discover_vintages(cursor)
        if phase == "observations":
            return self._fetch_observations(window, cursor)
        raise ValueError(f"unsupported FRED cursor phase: {phase!r}")


FRED_ALLOWED_HOSTS: tuple[str, ...] = ("api.stlouisfed.org",)
