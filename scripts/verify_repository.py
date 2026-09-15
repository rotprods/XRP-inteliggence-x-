from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

from build_manifest import render_manifest


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SOURCE_TOKENS = {
    "execute_trade",
    "place_order",
    "seed_phrase",
    "submit_transaction",
    "wallet_sign",
    "withdraw_funds",
}
GENERATED_PARTS = {
    ".coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".mutmut-cache",
    "__pycache__",
    "quality",
    "mutants",
    "build",
    "dist",
    "dist-a",
    "dist-b",
}
RUNTIME_SUFFIXES = {".pyc", ".pyo", ".sqlite3", ".db"}
ACTION_REF_PATTERN = re.compile(
    r"(?m)^\s*uses:\s*(?P<action>[^@\s]+)@(?P<ref>[^\s#]+)(?:\s+#.*)?$"
)


def _git_visible_paths(root: Path) -> list[Path] | None:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    values = [item for item in completed.stdout.split(b"\0") if item]
    return [root / item.decode("utf-8") for item in values]


def _fallback_paths(root: Path) -> Iterable[Path]:
    yield from root.rglob("*")


def _repository_paths(root: Path) -> Iterable[Path]:
    visible = _git_visible_paths(root)
    if visible is not None:
        yield from visible
    else:
        yield from _fallback_paths(root)


def verify(root: Path = ROOT) -> dict[str, object]:
    errors: list[str] = []
    required = [
        "pyproject.toml",
        "README.md",
        "src/xrp_regime_engine",
        "tests",
        "docs/verification/VERIFICATION_OS.md",
        "release/MANIFEST.sha256",
    ]
    for relative in required:
        if not (root / relative).exists():
            errors.append(f"missing required path: {relative}")

    for path in _repository_paths(root):
        if not path.exists():
            continue
        relative = path.relative_to(root)
        if any(part in GENERATED_PARTS for part in relative.parts):
            # Generated/ignored runtime state may exist locally, but it may not be Git-visible.
            visible = _git_visible_paths(root)
            if visible is not None and path in visible:
                errors.append(f"generated artifact tracked or unignored in source tree: {relative}")
            continue
        if path.is_file() and path.suffix in RUNTIME_SUFFIXES:
            errors.append(f"runtime artifact tracked or unignored in source tree: {relative}")

    source_root = root / "src"
    if source_root.exists():
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for token in FORBIDDEN_SOURCE_TOKENS:
                if token in text:
                    errors.append(
                        f"forbidden execution primitive {token!r} in {path.relative_to(root)}"
                    )

    workflow_dir = root / ".github/workflows"
    workflows = sorted(workflow_dir.glob("*.yml")) if workflow_dir.exists() else []
    if len(workflows) != 1:
        errors.append(f"expected exactly one workflow, found {len(workflows)}")
    elif workflows:
        workflow = workflows[0]
        if workflow.name != "ci.yml":
            errors.append("the single workflow must be .github/workflows/ci.yml")
        text = workflow.read_text(encoding="utf-8")
        if "workflow_dispatch:" not in text or "pull_request:" not in text:
            errors.append("CI must support bounded PR FAST checks and explicit manual profiles")
        if re.search(r"(?m)^\s*(push|schedule):", text):
            errors.append("CI must not run on push or schedule")
        if not re.search(r"(?m)^\s*contents:\s*read\s*$", text):
            errors.append("CI must declare contents: read")
        if re.search(r"(?m)^\s*(contents|pull-requests|actions):\s*write\s*$", text):
            errors.append("CI must not have repository write permissions")
        if "persist-credentials: false" not in text:
            errors.append("checkout must disable persisted credentials")
        if "runs-on: ubuntu-latest" not in text:
            errors.append("CI must use the standard ubuntu-latest runner")
        if re.search(r"(?m)^\s*matrix:\s*$", text):
            errors.append("CI matrix fan-out is forbidden by the cost guardrail")
        if "actions/upload-artifact" in text:
            errors.append("CI artifact uploads are disabled during cost-controlled alpha")
        if "--allow-network" in text:
            errors.append("CI must never enable live network tests")
        if re.search(r"(?m)^\s*(git\s+push|gh\s+pr\s+merge|gh\s+release\s+create)", text):
            errors.append("CI must verify only and never mutate repository state")
        action_refs = list(ACTION_REF_PATTERN.finditer(text))
        if not action_refs:
            errors.append("CI must declare pinned external actions")
        for match in action_refs:
            if not re.fullmatch(r"[0-9a-f]{40}", match.group("ref")):
                errors.append(
                    f"workflow action {match.group('action')} must be pinned to a full commit SHA"
                )

    for directory in (root / "config", root / "schemas"):
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"invalid JSON {path.relative_to(root)}: {exc}")

    assets_path = root / "config/assets.json"
    if assets_path.exists():
        assets = json.loads(assets_path.read_text(encoding="utf-8"))["assets"]
        for name in ("XRP_USD", "BTC_USD", "ETH_USD"):
            symbol = assets.get(name, {}).get("symbols", {}).get("binance")
            if symbol:
                errors.append(f"{name} must not map a Binance USDT market into USD semantics")

    manifest_path = root / "release/MANIFEST.sha256"
    manifest_ok = manifest_path.exists() and manifest_path.read_text(
        encoding="utf-8"
    ) == render_manifest(root)
    if not manifest_ok:
        errors.append("release manifest is missing or stale")

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "workflow_count": len(workflows),
        "manifest_ok": manifest_ok,
        "read_only_boundary": True,
        "verification_scope": "git_visible" if _git_visible_paths(root) is not None else "filesystem",
        "cost_guardrail": {
            "workflow_count": len(workflows),
            "standard_runner_only": True,
            "matrix_fanout": False,
            "scheduled_runs": False,
            "paid_live_provider_calls": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
