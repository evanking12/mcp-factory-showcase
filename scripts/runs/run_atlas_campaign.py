from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.runs.run_design_suite_real_campaign import run_design_suite_real_campaign  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the first bounded Atlas campaign.")
    parser.add_argument("--suite", default="atlas_reconciliation_suite")
    parser.add_argument("--mode", default="mutual_pressure")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    result = run_design_suite_real_campaign(
        suite=str(args.suite or "").strip(),
        mode=str(args.mode or "").strip(),
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
    )
    print(json.dumps({"campaign_id": result["campaign_id"], "output_dir": result["output_dir"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
