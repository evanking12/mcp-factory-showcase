from __future__ import annotations

import runpy
import sys
from pathlib import Path

print("[deprecated-wrapper] Use python scripts/harness.py instead of this entrypoint.", file=sys.stderr)
_TARGET = Path(__file__).resolve().parent / "runs/run_ab_parallel.py"

if __name__ == "__main__":
    runpy.run_path(str(_TARGET), run_name="__main__")
