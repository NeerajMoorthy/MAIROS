#!/usr/bin/env python3
"""Write the sample project used by docs/SAMPLE_PROJECT_WALKTHROUGH.md.

    python scripts/generate_sample_project.py          # -> output/sample-project/

The content lives in ``services/samples/railguard.py``, which Settings ->
*Load example data* also uses, so the files written here and the example
workspace the app loads never drift apart.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "sample-project"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.samples.railguard import *  # noqa: E402,F401,F403
from services.samples.railguard import build  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    for path, detail in build(parser.parse_args().out):
        print(f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}  ({detail})")


if __name__ == "__main__":
    main()
