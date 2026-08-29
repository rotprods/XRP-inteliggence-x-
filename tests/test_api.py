from pathlib import Path

from fastapi.testclient import TestClient

from xrp_regime_engine.demo import DEMO_SUPPLEMENTAL_FEATURES, generate_demo_frame
from xrp_regime_engine.features import compute_features
from xrp_regime_engine.models import Horizon
from xrp_regime_engine.regime import score_regime
from xrp_regime_engine.storage import SQLiteStore


def _client_for_database(db: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("XRP_ENGINE_DB_PATH", str(db))
    import importlib
    import xrp_regime_engine.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.app)


def test_health_and_regime_endpoints(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "api.sqlite3"
    store = SQLiteStore(db)
    store.save_snapshot(
        score_regime(
            compute_features(generate_demo_frame(), supplemental=DEMO_SUPPLEMENTAL_FEATURES),
            Horizon.D1,
        )
    )
    client = _client_for_database(db, monkeypatch)
    assert client.get("/health").status_code == 200
    response = client.get("/v1/regime/xrp/1d")
    assert response.status_code == 200
    assert "data_confidence" in response.json()
    assert client.get("/v1/regime/xrp/invalid").status_code == 400
    assert client.get("/v1/explain/xrp/invalid").status_code == 400
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["read_only"] is True


def test_no_data_state_returns_404(tmp_path: Path, monkeypatch) -> None:
    client = _client_for_database(tmp_path / "empty.sqlite3", monkeypatch)
    assert client.get("/v1/regime/xrp/1d").status_code == 404
    assert client.get("/ready").status_code == 503
