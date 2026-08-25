from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from xrp_regime_engine.historical_backfill import BackfillRunner, BackfillWindow
from xrp_regime_engine.historical_spot_adapters import (
    BinanceKlineAdapter,
    CoinbaseCandleAdapter,
    HistoricalHTTPClient,
    historical_allowed_hosts,
)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill read-only XRP spot candles")
    parser.add_argument("--provider", choices=("coinbase", "binance"), required=True)
    parser.add_argument("--start", type=parse_timestamp, required=True)
    parser.add_argument("--end", type=parse_timestamp, required=True)
    parser.add_argument("--interval-seconds", type=int, default=3600)
    parser.add_argument("--root", type=Path, default=Path("state/historical"))
    parser.add_argument("--max-pages", type=int, default=10_000)
    parser.add_argument("--allow-large-window", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("reports/backfill-xrp-spot-v05.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    window = BackfillWindow(args.start, args.end, args.interval_seconds)
    if not args.allow_large_window and (window.end - window.start).days > 31:
        raise SystemExit("window exceeds 31 days; pass --allow-large-window after reviewing cost and rate limits")

    client = HistoricalHTTPClient(allowed_hosts=historical_allowed_hosts())
    if args.provider == "coinbase":
        adapter = CoinbaseCandleAdapter(client, interval_seconds=args.interval_seconds)
    else:
        adapter = BinanceKlineAdapter(client, interval_seconds=args.interval_seconds)

    root = args.root
    runner = BackfillRunner(
        raw_store=ContentAddressedRawStore(root),
        partition_store=JSONLPartitionStore(root),
        catalog=PointInTimeCatalog(root / "catalog.sqlite"),
        manifest_store=ManifestStore(root),
        checkpoints=BackfillCheckpointStore(root / "checkpoints.sqlite"),
        max_pages=args.max_pages,
    )
    result = runner.run(adapter, window)
    document = {
        "version": "0.5.0",
        "mode": "read-only-historical-backfill",
        "provider": args.provider,
        "window": window.to_dict(),
        "root": str(root),
        "result": result.to_dict(),
        "production_release": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
