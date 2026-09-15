from __future__ import annotations

import argparse
import hashlib
from collections.abc import Iterator
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".mutmut-cache",
    "__pycache__",
    "state",
    "quality",
    "mutants",
    "build",
    "dist",
    "dist-a",
    "dist-b",
}
EXCLUDED_FILES = {
    Path("release/MANIFEST.sha256"),
    Path("release/R0_CLEAN_MANIFEST_VERIFICATION.json"),
    Path("coverage.json"),
    Path("coverage.xml"),
    Path(".coverage"),
}


def iter_source_files(root: Path = ROOT) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in relative.parts):
            continue
        if relative in EXCLUDED_FILES:
            continue
        if path.name == ".coverage" or path.suffix in {".pyc", ".pyo"}:
            continue
        yield path


def render_manifest(root: Path = ROOT) -> str:
    lines: list[str] = []
    for path in iter_source_files(root):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    target = ROOT / "release" / "MANIFEST.sha256"
    expected = render_manifest()
    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != expected:
            raise SystemExit("release/MANIFEST.sha256 is stale; run scripts/build_manifest.py")
        print(f"verified {target} with {len(expected.splitlines())} entries")
        return

    target.parent.mkdir(exist_ok=True)
    target.write_text(expected, encoding="utf-8")
    print(f"wrote {target} with {len(expected.splitlines())} entries")


if __name__ == "__main__":
    main()
