from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.analysis.stage_split_migration_compare import compare_phase1_migration, write_comparison_result
from scripts.ops.nightly_groundtruth import ensure_strict_local_lane_preflight
from runtime.runtime_contract import local_api_base_url, local_bridge_base_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Phase 1 stage-split migration baseline vs candidate.")
    parser.add_argument("--baseline-session-root", required=True, type=Path)
    parser.add_argument("--candidate-session-root", required=True, type=Path)
    parser.add_argument("--difference-claims-artifact", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--api-url",
        default=os.getenv("MCP_FACTORY_API_URL") or local_api_base_url(),
    )
    parser.add_argument("--api-key", default=os.getenv("MCP_FACTORY_API_KEY", ""))
    parser.add_argument("--bridge-url", default=os.getenv("GUI_BRIDGE_URL", local_bridge_base_url()))
    parser.add_argument("--bridge-key", default=os.getenv("GUI_BRIDGE_SECRET", ""))
    args = parser.parse_args()

    strict_local_preflight = ensure_strict_local_lane_preflight(
        api_url=str(args.api_url or "").strip(),
        api_key=str(args.api_key or "").strip(),
        bridge_url=str(args.bridge_url or "").strip(),
        bridge_key=str(args.bridge_key or "").strip(),
    )
    payload = compare_phase1_migration(
        baseline_session_root=args.baseline_session_root,
        candidate_session_root=args.candidate_session_root,
        difference_claims_artifact=args.difference_claims_artifact,
    )
    payload["strict_local_preflight"] = strict_local_preflight
    write_comparison_result(args.output, payload)
    print(json.dumps({"overall_verdict": payload["overall_verdict"], "output": str(args.output)}, indent=2))
    return 1 if payload["overall_verdict"] in {"blocked_regression", "unclassified_difference"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
