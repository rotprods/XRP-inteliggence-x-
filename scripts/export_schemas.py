from __future__ import annotations

import json
from pathlib import Path

from xrp_regime_engine.models import (
    AssetObservation,
    Candle,
    ProviderHealth,
    Provenance,
    RegimeSnapshot,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {
    "market_observation.schema.json": AssetObservation,
    "candle.schema.json": Candle,
    "provenance.schema.json": Provenance,
    "provider_health.schema.json": ProviderHealth,
    "regime_snapshot.schema.json": RegimeSnapshot,
}


def main() -> None:
    target = ROOT / "schemas"
    target.mkdir(exist_ok=True)
    for filename, model in SCHEMAS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://rotprods.local/schemas/{filename}"
        (target / filename).write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {target / filename}")


if __name__ == "__main__":
    main()
