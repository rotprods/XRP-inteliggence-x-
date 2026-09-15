from __future__ import annotations

import json
from pathlib import Path

import typer
import uvicorn

from xrp_regime_engine.config import Settings
from xrp_regime_engine.logging import configure_logging
from xrp_regime_engine.pipeline import run_demo


app = typer.Typer(no_args_is_help=True)


@app.command()
def demo(output: Path = typer.Option(Path("state/demo"), help="Output directory")) -> None:
    """Run a deterministic, network-free vertical slice."""
    configure_logging()
    result = run_demo(output)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def snapshot() -> None:
    """Refuse live execution until the approved provider orchestrator exists."""
    typer.echo(
        "Live snapshot is blocked: the read-only provider orchestrator has not passed its release gate.",
        err=True,
    )
    raise typer.Exit(code=2)


@app.command()
def doctor() -> None:
    """Inspect local configuration without contacting external providers."""
    settings = Settings()
    result = {
        "mode": settings.mode,
        "db_path": str(settings.db_path),
        "config_dir": str(settings.config_dir),
        "config_files_present": all(
            (settings.config_dir / name).is_file()
            for name in (
                "assets.json",
                "fred_series.json",
                "providers.json",
                "thresholds.json",
                "weights.json",
            )
        ),
        "fred_key_configured": settings.fred_api_key is not None,
        "live_snapshot_implemented": False,
        "read_only": True,
    }
    typer.echo(json.dumps(result, indent=2))


@app.command()
def api(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Start the read-only API."""
    uvicorn.run("xrp_regime_engine.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":  # pragma: no cover - console-script entrypoint is integration-level
    app()
