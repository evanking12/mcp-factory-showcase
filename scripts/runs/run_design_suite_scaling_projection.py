from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.design_suite_scaling_projection import run_design_suite_scaling_projection  # noqa: E402
from scripts.runs.run_design_suite_campaign_local import run_design_suite_campaign_local  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Project Northstar local campaign shape through engine-scaling surfaces.")
    parser.add_argument("--suite", default="northstar_transaction_suite")
    parser.add_argument("--mode", default="late_confirmation")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_root = (
        Path(args.output_root)
        if str(args.output_root or "").strip()
        else REPO_ROOT / "sessions" / "design_suite" / "scaling_projection" / str(args.suite or "").strip() / f"{timestamp}-{str(args.mode or '').strip()}"
    )
    output_root.mkdir(parents=True, exist_ok=True)

    run_design_suite_campaign_local(
        suite=str(args.suite or "").strip(),
        mode=str(args.mode or "").strip(),
        output_root=output_root,
    )
    result = run_design_suite_scaling_projection(output_root)
    print(json.dumps({"output_dir": result["output_dir"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
