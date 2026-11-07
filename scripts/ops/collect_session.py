from __future__ import annotations

import sys
from pathlib import Path


# Keep legacy import path working for tests and old scripts.
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

import harness_lib.collector as _collector
from harness_lib.collector import *  # noqa: F401,F403
from harness_lib.collector import main

# Re-export private helpers used by existing tests/tools.
_validate_contract = _collector._validate_contract
_build_run_validity = _collector._build_run_validity
_compute_status_counts = _collector._compute_status_counts
ContractResult = _collector.ContractResult


if __name__ == "__main__":
    raise SystemExit(main())
