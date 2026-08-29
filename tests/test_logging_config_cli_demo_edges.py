from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from xrp_regime_engine import cli
from xrp_regime_engine.config import Settings, load_json
from xrp_regime_engine.demo import generate_demo_frame
from xrp_regime_engine.logging import JsonFormatter, configure_logging

pytestmark = pytest.mark.unit


def test_json_formatter_includes_redacted_exception() -> None:
    formatter = JsonFormatter()
    try:
        raise RuntimeError("token=SUPERSECRET")
    except RuntimeError:
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom", (), __import__("sys").exc_info())
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "ERROR"
    assert "SUPERSECRET" not in payload["exception"]


def test_configure_logging_replaces_root_handlers() -> None:
    root = logging.getLogger()
    root.handlers[:] = [logging.NullHandler(), logging.NullHandler()]
    configure_logging("warning")
    assert len(root.handlers) == 1
    assert root.level == logging.WARNING
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_load_json_rejects_non_object_and_loads_object(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text('{"x": 1}', encoding="utf-8")
    assert load_json(good) == {"x": 1}
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="configuration root must be an object"):
        load_json(bad)


def test_settings_rejects_empty_log_level() -> None:
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        Settings(log_level="")


def test_settings_config_accessors_return_objects() -> None:
    settings = Settings()
    assert settings.weights()["version"] >= 1
    assert settings.thresholds()["version"] >= 1
    assert settings.assets()["version"] >= 1
    assert settings.providers()["version"] >= 1
    assert settings.fred_series()["version"] >= 1


def test_demo_rejects_too_short_and_naive_end() -> None:
    with pytest.raises(ValueError, match="periods"):
        generate_demo_frame(1)
    with pytest.raises(ValueError, match="timezone-aware"):
        generate_demo_frame(10, end=datetime(2026, 1, 1))


def test_cli_demo_and_api_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli.app, ["demo", "--output", str(tmp_path / "demo")])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["snapshots"] == 4

    called: dict[str, object] = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, host, port, reload: called.update(app=app, host=host, port=port, reload=reload))
    result = runner.invoke(cli.app, ["api", "--host", "127.0.0.1", "--port", "9090"])
    assert result.exit_code == 0
    assert called == {"app": "xrp_regime_engine.api:app", "host": "127.0.0.1", "port": 9090, "reload": False}
