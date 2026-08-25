from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

from xrp_regime_engine.live_provider_plane import (
    DEFAULT_ADAPTERS,
    DEFAULT_ALLOWED_HOSTS,
    LiveProviderPlane,
    ReadOnlyJSONClient,
)
from xrp_regime_engine.provider_consensus import (
    ConsensusUnavailable,
    ProviderObservation,
    build_consensus,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe public read-only XRP spot providers")
    parser.add_argument("--output", type=Path, default=Path("reports/provider-probe-v04.json"))
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--require-consensus", action="store_true")
    return parser.parse_args()


def _consensus_payload(quotes: list[Any], *, now: datetime) -> dict[str, Any]:
    groups: dict[str, list[ProviderObservation]] = {}
    for quote in quotes:
        groups.setdefault(quote.symbol, []).append(
            ProviderObservation(
                provider=quote.provider,
                symbol=quote.symbol,
                price=quote.price,
                observed_at=quote.observed_at,
                received_at=quote.received_at,
                payload_sha256=quote.payload_sha256,
            )
        )

    payload: dict[str, Any] = {}
    for symbol, observations in sorted(groups.items()):
        try:
            result = build_consensus(observations, now=now)
            payload[symbol] = {
                "status": "PASS",
                "price": str(result.price),
                "providers": list(result.providers),
                "observation_count": result.observation_count,
                "spread_ratio": str(result.spread_ratio),
                "confidence": result.confidence,
                "rejected": list(result.rejected),
            }
        except ConsensusUnavailable as exc:
            payload[symbol] = {
                "status": "BLOCKED",
                "reason": str(exc),
                "observation_count": len(observations),
            }
    return payload


def main() -> int:
    args = parse_args()
    checked_at = datetime.now(timezone.utc)
    client = ReadOnlyJSONClient(
        allowed_hosts=DEFAULT_ALLOWED_HOSTS,
        timeout_seconds=args.timeout,
        max_attempts=args.attempts,
    )
    plane = LiveProviderPlane(client, DEFAULT_ADAPTERS)
    probes = plane.probe()
    quotes = list(plane.healthy_quotes(probes))
    consensus = _consensus_payload(quotes, now=checked_at)

    document = {
        "version": "0.4.0",
        "mode": "read-only-public-probe",
        "checked_at": checked_at.isoformat(),
        "providers": [probe.to_dict() for probe in probes],
        "healthy_provider_count": len(quotes),
        "consensus": consensus,
        "production_release": "BLOCKED",
        "boundary": "No authentication, trading, custody, signing, transfers, withdrawals or orders",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(document, indent=2, sort_keys=True))

    passing_consensus = any(item.get("status") == "PASS" for item in consensus.values())
    if args.require_consensus and not passing_consensus:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
