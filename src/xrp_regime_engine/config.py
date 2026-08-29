from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"configuration root must be an object: {path}")
    return payload


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    mode: str = field(default_factory=lambda: _env("XRP_ENGINE_MODE", "demo"))
    db_path: Path = field(
        default_factory=lambda: Path(_env("XRP_ENGINE_DB_PATH", "state/live/engine.sqlite3"))
    )
    log_level: str = field(default_factory=lambda: _env("XRP_ENGINE_LOG_LEVEL", "INFO"))
    binance_base_url: str = field(
        default_factory=lambda: _env("BINANCE_BASE_URL", "https://data-api.binance.vision")
    )
    coinbase_base_url: str = field(
        default_factory=lambda: _env(
            "COINBASE_BASE_URL", "https://api.exchange.coinbase.com"
        )
    )
    kraken_base_url: str = field(
        default_factory=lambda: _env("KRAKEN_BASE_URL", "https://api.kraken.com")
    )
    xrpl_url: str = field(
        default_factory=lambda: _env("XRPL_JSON_RPC_URL", "https://s1.ripple.com:51234")
    )
    fred_api_key: str | None = field(default_factory=lambda: os.getenv("FRED_API_KEY") or None)
    alert_webhook_url: str | None = field(
        default_factory=lambda: os.getenv("ALERT_WEBHOOK_URL") or None
    )

    def __post_init__(self) -> None:
        if self.mode not in {"demo", "shadow", "live"}:
            raise ValueError("XRP_ENGINE_MODE must be demo, shadow or live")
        if not self.log_level:
            raise ValueError("XRP_ENGINE_LOG_LEVEL cannot be empty")

    @property
    def config_dir(self) -> Path:
        return PROJECT_ROOT / "config"

    def weights(self) -> dict[str, Any]:
        return load_json(self.config_dir / "weights.json")

    def thresholds(self) -> dict[str, Any]:
        return load_json(self.config_dir / "thresholds.json")

    def assets(self) -> dict[str, Any]:
        return load_json(self.config_dir / "assets.json")

    def providers(self) -> dict[str, Any]:
        return load_json(self.config_dir / "providers.json")

    def fred_series(self) -> dict[str, Any]:
        return load_json(self.config_dir / "fred_series.json")
