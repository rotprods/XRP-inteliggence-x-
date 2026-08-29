#!/usr/bin/env bash
set -euo pipefail
python -m xrp_regime_engine.cli demo --output state/demo
pytest -q
python scripts/build_manifest.py
