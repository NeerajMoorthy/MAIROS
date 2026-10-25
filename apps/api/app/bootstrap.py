"""Python path bootstrap — import this before any MAIROS package.

The repo is a monorepo, not an installed distribution, and one directory
(``packages/shared-types``) has a name that is not a legal module identifier.
Rather than scattering ``sys.path`` hacks across every router, every entry
point imports this module first.

Entry points: ``apps/api/main.py`` and ``tests/conftest.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# apps/api/app/bootstrap.py -> parents[3] == repo root (mairos/)
ROOT = Path(__file__).resolve().parents[3]

_PATHS = [
    ROOT,                                  # `services.*`, `apps.api.app.*`
    ROOT / "apps" / "api",                 # `app.*`, `main`
    ROOT / "packages" / "shared-types",    # `schemas`
    ROOT / "services",                     # legacy `ingestion.*`, `retrieval.*`
]

for _path in _PATHS:
    resolved = str(_path)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)

__all__ = ["ROOT"]
