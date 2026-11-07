from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.atlas_successor_suite import ATLAS_CAMPAIGN_READINESS_ARTIFACT  # noqa: E402
from api.pipeline.core.design_suite_branch_decision import (  # noqa: E402
    build_successor_suite_branch_decision,
    write_successor_suite_branch_decision,
)


def _latest_campaign_local_dir(suite_id: str) -> Path:
    root = REPO_ROOT / "sessions" / "design_suite" / "campaign_local" / suite_id
    if not root.exists():
        raise FileNotFoundError(f"campaign_local root missing for {suite_id}")
    candidates = sorted((path for path in root.iterdir() if path.is_dir()), key=lambda item: item.name, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"no campaign_local runs found for {suite_id}")
    return candidates[0]


def run_successor_suite_branch_decision(
    *,
    suite_id: str = "atlas_reconciliation_suite",
    suite_name: str = "Atlas Reconciliation Suite",
    readiness_path: str | Path | None = None,
    output_root: str | Path | None = None,
) -> dict[str, object]:
    readiness_file = Path(readiness_path) if readiness_path is not None else _latest_campaign_local_dir(suite_id) / ATLAS_CAMPAIGN_READINESS_ARTIFACT
    readiness = json.loads(readiness_file.read_text(encoding="utf-8"))

    payload = build_successor_suite_branch_decision(
        readiness,
        suite_id=suite_id,
        suite_name=suite_name,
        real_campaign_runtime_reusable=False,
        remaining_real_campaign_glue=[
            "Northstar-specific real campaign runner",
            "Northstar-specific campaign snapshot/truth/cohesion wrapper names",
            "Northstar-specific attribution review wording",
        ],
    )
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT / "sessions" / "design_suite" / "branch_decision" / suite_id / timestamp
    )
    artifact_path = write_successor_suite_branch_decision(output_dir, payload)
    return {
        "output_dir": str(output_dir),
        "artifact_path": str(artifact_path),
        "decision": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Choose the next bounded post-readiness branch for the successor suite.")
    parser.add_argument("--suite-id", default="atlas_reconciliation_suite")
    parser.add_argument("--suite-name", default="Atlas Reconciliation Suite")
    parser.add_argument("--readiness-path", default="")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    result = run_successor_suite_branch_decision(
        suite_id=str(args.suite_id or "").strip(),
        suite_name=str(args.suite_name or "").strip(),
        readiness_path=Path(args.readiness_path) if str(args.readiness_path or "").strip() else None,
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
    )
    print(json.dumps({"output_dir": result["output_dir"], "recommended_next_branch": result["decision"]["recommended_next_branch"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
