from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.design_suite_campaign_readiness import (  # noqa: E402
    build_design_suite_campaign_readiness,
    write_design_suite_campaign_readiness,
)
from scripts.runs.run_design_suite_campaign_local import run_design_suite_campaign_local  # noqa: E402
from scripts.runs.run_design_suite_scaling_projection import run_design_suite_scaling_projection  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Northstar campaign readiness artifact.")
    parser.add_argument("--suite", default="northstar_transaction_suite")
    parser.add_argument("--mode", default="late_confirmation")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_root = (
        Path(args.output_root)
        if str(args.output_root or "").strip()
        else REPO_ROOT / "sessions" / "design_suite" / "campaign_readiness" / str(args.suite or "").strip() / f"{timestamp}-{str(args.mode or '').strip()}"
    )
    output_root.mkdir(parents=True, exist_ok=True)

    local_result = run_design_suite_campaign_local(
        suite=str(args.suite or "").strip(),
        mode=str(args.mode or "").strip(),
        output_root=output_root,
    )
    scaling_result = run_design_suite_scaling_projection(output_root)
    forked_guard_root = output_root / "forked_state_guard"
    forked_result = run_design_suite_campaign_local(
        suite=str(args.suite or "").strip(),
        mode="forked_state",
        output_root=forked_guard_root,
    )

    readiness = build_design_suite_campaign_readiness(
        local_result["campaign_plan"],
        local_result["campaign_truth"],
        local_result["campaign_cohesion"],
        scaling_result["scaling_projection"],
        scaling_result["scaling_cohesion"],
        forked_state_guard=forked_result["campaign_plan"],
    )
    path = write_design_suite_campaign_readiness(output_root, readiness)
    print(json.dumps({"output_dir": str(output_root), "readiness_path": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
