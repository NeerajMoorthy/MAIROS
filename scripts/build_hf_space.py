#!/usr/bin/env python3
"""Assemble the Hugging Face Space bundle for the MAIROS API.

A Space is built from the root of its own repository, so the backend's code is
copied into one folder with the Space's Dockerfile and README at its root:

    python scripts/build_hf_space.py            # -> build/hf-space/

Only what the API needs at runtime is copied: apps/api (without its virtual
environment, data or tests), services and packages. Secrets are never copied;
the Groq key is set as a Space secret.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPACE_FILES = ROOT / "deploy" / "hf-space"

IGNORE = shutil.ignore_patterns(
    ".venv", "venv", "data", "__pycache__", "*.pyc", ".pytest_cache", ".env", ".env.*",
    "tests", "*.db", "*.sqlite3", "*.log",
)


def build(out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in ("Dockerfile", "README.md"):
        shutil.copy2(SPACE_FILES / name, out / name)
    for part in ("apps/api", "services", "packages"):
        shutil.copytree(ROOT / part, out / part, ignore=IGNORE)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "hf-space")
    out = build(parser.parse_args().out)
    files = [p for p in out.rglob("*") if p.is_file()]
    size = sum(p.stat().st_size for p in files)
    print(f"{out} ({len(files)} files, {size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
