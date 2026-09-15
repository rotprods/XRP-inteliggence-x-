from typer.testing import CliRunner

from xrp_regime_engine.cli import app


runner = CliRunner()


def test_doctor_is_read_only() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert '"read_only": true' in result.stdout
    assert '"live_snapshot_implemented": false' in result.stdout


def test_live_snapshot_fails_closed() -> None:
    result = runner.invoke(app, ["snapshot"])
    assert result.exit_code == 2
    assert "blocked" in result.output.lower()
