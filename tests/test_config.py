from pathlib import Path

import pytest

from xrp_regime_engine.config import Settings, load_json


def test_settings_read_environment_at_instantiation(monkeypatch) -> None:
    monkeypatch.setenv("XRP_ENGINE_MODE", "shadow")
    monkeypatch.setenv("XRP_ENGINE_DB_PATH", "/tmp/xrp-shadow.sqlite3")
    settings = Settings()
    assert settings.mode == "shadow"
    assert settings.db_path == Path("/tmp/xrp-shadow.sqlite3")


def test_invalid_mode_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("XRP_ENGINE_MODE", "trade")
    with pytest.raises(ValueError, match="demo, shadow or live"):
        Settings()


def test_config_root_must_be_object(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        load_json(path)
