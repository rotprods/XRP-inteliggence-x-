from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from xrp_regime_engine.storage import SQLiteStore
from xrp_regime_engine.version import __version__


DB_PATH = Path(os.getenv("XRP_ENGINE_DB_PATH", "state/demo/engine.sqlite3"))
SUPPORTED_HORIZONS = frozenset({"1h", "4h", "1d", "1w"})
app = FastAPI(title="XRP Cross-Asset Regime Engine", version=__version__)


def _validated_horizon(value: str) -> str:
    if value not in SUPPORTED_HORIZONS:
        raise HTTPException(status_code=400, detail="unsupported horizon")
    return value


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "version": __version__,
        "mode": os.getenv("XRP_ENGINE_MODE", "demo"),
        "read_only": True,
    }


@app.get("/ready")
def readiness() -> dict[str, object]:
    store = SQLiteStore(DB_PATH)
    snapshots = [
        store.latest_snapshot("XRP", horizon) for horizon in sorted(SUPPORTED_HORIZONS)
    ]
    available = [snapshot.horizon.value for snapshot in snapshots if snapshot is not None]
    if not available:
        raise HTTPException(status_code=503, detail="no regime snapshots available")
    blocked = [
        snapshot.horizon.value
        for snapshot in snapshots
        if snapshot is not None and snapshot.output_blocked
    ]
    return {
        "ready": not blocked,
        "available_horizons": available,
        "blocked_horizons": blocked,
        "read_only": True,
    }


@app.get("/v1/regime/xrp/{horizon}")
def latest_xrp_regime(horizon: str = "1d") -> dict[str, object]:
    horizon = _validated_horizon(horizon)
    snapshot = SQLiteStore(DB_PATH).latest_snapshot("XRP", horizon)
    if not snapshot:
        raise HTTPException(status_code=404, detail="no snapshot available")
    return snapshot.model_dump(mode="json")


@app.get("/v1/providers/health")
def provider_health() -> list[dict[str, object]]:
    return [
        item.model_dump(mode="json") for item in SQLiteStore(DB_PATH).latest_health()
    ]


@app.get("/v1/explain/xrp/{horizon}")
def explain_xrp(horizon: str = "1d") -> dict[str, object]:
    horizon = _validated_horizon(horizon)
    snapshot = SQLiteStore(DB_PATH).latest_snapshot("XRP", horizon)
    if not snapshot:
        raise HTTPException(status_code=404, detail="no snapshot available")
    return {
        "regime": snapshot.regime,
        "bull_score": snapshot.bull_score,
        "confidence": snapshot.confidence,
        "data_confidence": snapshot.data_confidence,
        "model_confidence": snapshot.model_confidence,
        "directional_conviction": snapshot.directional_conviction,
        "output_blocked": snapshot.output_blocked,
        "block_reasons": snapshot.block_reasons,
        "drivers": snapshot.key_drivers,
        "invalidations": snapshot.invalidations,
        "components": snapshot.components.model_dump(),
        "component_coverage": snapshot.component_coverage,
        "analogues": snapshot.historical_analogues,
        "data_flags": snapshot.data_flags,
    }
