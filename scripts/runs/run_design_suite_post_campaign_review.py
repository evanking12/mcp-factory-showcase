from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.design_suite_post_campaign_review import (  # noqa: E402
    build_design_suite_post_campaign_review,
    write_design_suite_post_campaign_review,
)


def run_design_suite_post_campaign_review(
    *,
    branch_decision_path: str | Path,
    campaign_dir: str | Path,
    output_root: str | Path | None = None,
) -> dict[str, object]:
    branch_decision = json.loads(Path(branch_decision_path).read_text(encoding="utf-8"))
    campaign_root = Path(campaign_dir)
    campaign_truth = json.loads((campaign_root / "campaign" / "campaign-truth.json").read_text(encoding="utf-8"))
    campaign_cohesion = json.loads((campaign_root / "audits" / "campaign-cohesion-report.json").read_text(encoding="utf-8"))
    attribution_review = json.loads((campaign_root / "audits" / "design-suite-campaign-attribution-review.json").read_text(encoding="utf-8"))
    payload = build_design_suite_post_campaign_review(
        branch_decision,
        campaign_truth,
        campaign_cohesion,
        attribution_review,
    )
    resolved_output_root = Path(output_root) if output_root is not None else campaign_root / "audits"
    artifact_path = write_design_suite_post_campaign_review(resolved_output_root, payload)
    return {
        "output_dir": str(resolved_output_root),
        "artifact_path": str(artifact_path),
        "review": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit a post-campaign design-suite branch review.")
    parser.add_argument("--branch-decision-path", required=True)
    parser.add_argument("--campaign-dir", required=True)
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    result = run_design_suite_post_campaign_review(
        branch_decision_path=Path(args.branch_decision_path),
        campaign_dir=Path(args.campaign_dir),
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
    )
    print(json.dumps({"output_dir": result["output_dir"], "recommended_next_branch": result["review"]["recommended_next_branch"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
