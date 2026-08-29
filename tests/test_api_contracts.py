from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xrp_regime_engine import api
from xrp_regime_engine.demo import DEMO_SUPPLEMENTAL_FEATURES, generate_demo_frame
from xrp_regime_engine.features import compute_features
from xrp_regime_engine.models import Horizon, ProviderHealth
from xrp_regime_engine.regime import score_regime
from xrp_regime_engine.storage import SQLiteStore

pytestmark = [pytest.mark.api, pytest.mark.contract]


def client_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, SQLiteStore]:
    path = tmp_path / "engine.sqlite3"
    monkeypatch.setattr(api, "DB_PATH", path)
    return TestClient(api.app), SQLiteStore(path)


def test_invalid_horizon_is_rejected_without_stack_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = client_for(tmp_path, monkeypatch)
    response = client.get("/v1/regime/xrp/2h")
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert "traceback" not in response.text.lower()


def test_readiness_reports_blocked_and_available_horizons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, store = client_for(tmp_path, monkeypatch)
    features = compute_features(generate_demo_frame(), supplemental=DEMO_SUPPLEMENTAL_FEATURES)
    blocked = score_regime(features, Horizon.D1, minimum_data_confidence=1.0)
    store.save_snapshot(blocked)
    response = client.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["blocked_horizons"] == ["1d"]
    assert payload["read_only"] is True


def test_provider_health_endpoint_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, store = client_for(tmp_path, monkeypatch)
    store.save_health(
        ProviderHealth(
            provider="coinbase",
            checked_at=datetime.now(UTC),
            status="ok",
            freshness_score=1,
            agreement_score=1,
        )
    )
    response = client.get("/v1/providers/health")
    assert response.status_code == 200
    assert response.json()[0]["provider"] == "coinbase"


def test_explain_contract_and_no_data_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, store = client_for(tmp_path, monkeypatch)
    missing = client.get("/v1/explain/xrp/1d")
    assert missing.status_code == 404

    snapshot = score_regime(
        compute_features(generate_demo_frame(), supplemental=DEMO_SUPPLEMENTAL_FEATURES),
        Horizon.D1,
    )
    store.save_snapshot(snapshot)
    response = client.get("/v1/explain/xrp/1d")
    assert response.status_code == 200
    payload = response.json()
    required = {
        "regime",
        "bull_score",
        "confidence",
        "data_confidence",
        "model_confidence",
        "directional_conviction",
        "output_blocked",
        "block_reasons",
        "drivers",
        "invalidations",
        "components",
        "component_coverage",
        "analogues",
        "data_flags",
    }
    assert set(payload) == required
    assert "private_key" not in response.text.lower()
