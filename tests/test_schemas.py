import json
from pathlib import Path

from xrp_regime_engine.models import AssetObservation, Candle, ProviderHealth, Provenance, RegimeSnapshot


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "market_observation.schema.json": AssetObservation,
    "candle.schema.json": Candle,
    "provenance.schema.json": Provenance,
    "provider_health.schema.json": ProviderHealth,
    "regime_snapshot.schema.json": RegimeSnapshot,
}


def test_exported_schemas_match_models() -> None:
    for filename, model in EXPECTED.items():
        exported = json.loads((ROOT / "schemas" / filename).read_text(encoding="utf-8"))
        current = model.model_json_schema()
        assert exported["properties"] == current["properties"]
        assert exported.get("required", []) == current.get("required", [])
        assert exported.get("additionalProperties") is False
