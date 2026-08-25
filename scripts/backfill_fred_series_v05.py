from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

from xrp_regime_engine.fred_vintage_adapter import (
    FRED_ALLOWED_HOSTS,
    FREDSeriesSpec,
    FREDVintageAdapter,
)
from xrp_regime_engine.historical_backfill import BackfillRunner, BackfillWindow
from xrp_regime_engine.historical_spot_adapters import HistoricalHTTPClient
from xrp_regime_engine.historical_store import (
    BackfillCheckpointStore,
    ContentAddressedRawStore,
    JSONLPartitionStore,
    ManifestStore,
    PointInTimeCatalog,
)


def parse_timestamp(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("dates must use YYYY-MM-DD") from exc


def load_spec(path: Path, series_id: str) -> FREDSeriesSpec:
    document = json.loads(path.read_text(encoding="utf-8"))
    series = document.get("series")
    if not isinstance(series, list):
        raise SystemExit("FRED registry has no series list")
    for item in series:
        if isinstance(item, dict) and item.get("series_id") == series_id:
            return FREDSeriesSpec(
                series_id=str(item["series_id"]),
                dataset=str(item["dataset"]),
                frequency=str(item["frequency"]),
                category=str(item["category"]),
                units=str(item["units"]),
                weight=float(item.get("weight", 1.0)),
                exploratory=bool(item.get("exploratory", False)),
            )
    raise SystemExit(f"series_id is not registered: {series_id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill FRED/ALFRED point-in-time vintages")
    parser.add_argument("--series-id", required=True)
    parser.add_argument("--observation-start", type=parse_timestamp, required=True)
    parser.add_argument("--observation-end", type=parse_timestamp, required=True)
    parser.add_argument("--vintage-start", type=parse_date, required=True)
    parser.add_argument("--vintage-end", type=parse_date, required=True)
    parser.add_argument("--root", type=Path, default=Path("state/historical/fred"))
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("config/fred_series_v05.json"),
    )
    parser.add_argument("--max-pages", type=int, default=20_000)
    parser.add_argument("--allow-large-vintage-window", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("reports/backfill-fred-v05.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key:
        raise SystemExit("FRED_API_KEY is required and must be supplied through the environment")
    vintage_days = (args.vintage_end - args.vintage_start).days
    if not args.allow_large_vintage_window and vintage_days > 366:
        raise SystemExit(
            "vintage window exceeds 366 days; pass --allow-large-vintage-window after reviewing API cost"
        )

    spec = load_spec(args.registry, args.series_id)
    window = BackfillWindow(
        args.observation_start,
        args.observation_end,
        interval_seconds=86400,
    )
    client = HistoricalHTTPClient(allowed_hosts=FRED_ALLOWED_HOSTS)
    adapter = FREDVintageAdapter(
        client,
        api_key=api_key,
        spec=spec,
        vintage_start=args.vintage_start,
        vintage_end=args.vintage_end,
    )
    root = args.root / spec.dataset
    runner = BackfillRunner(
        raw_store=ContentAddressedRawStore(root),
        partition_store=JSONLPartitionStore(root),
        catalog=PointInTimeCatalog(root / "catalog.sqlite"),
        manifest_store=ManifestStore(root),
        checkpoints=BackfillCheckpointStore(root / "checkpoints.sqlite"),
        max_pages=args.max_pages,
    )
    result = runner.run(adapter, window)
    document: dict[str, Any] = {
        "version": "0.5.0",
        "mode": "read-only-fred-point-in-time-backfill",
        "series": {
            "series_id": spec.series_id,
            "dataset": spec.dataset,
            "frequency": spec.frequency,
            "category": spec.category,
            "units": spec.units,
            "weight": spec.weight,
            "exploratory": spec.exploratory,
        },
        "observation_window": window.to_dict(),
        "vintage_window": {
            "start": args.vintage_start.isoformat(),
            "end": args.vintage_end.isoformat(),
        },
        "result": result.to_dict(),
        "production_release": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
