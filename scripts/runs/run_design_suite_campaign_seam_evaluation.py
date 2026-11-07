from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.design_suite_campaign_evaluation import (  # noqa: E402
    build_design_suite_campaign_seam_evaluation,
    write_design_suite_campaign_seam_evaluation,
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the reusable Northstar campaign seam.")
    parser.add_argument("--late-campaign-dir", required=True)
    parser.add_argument("--forked-campaign-dir", required=True)
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    late_root = Path(args.late_campaign_dir)
    forked_root = Path(args.forked_campaign_dir)
    output_root = Path(args.output_root) if str(args.output_root or "").strip() else late_root.parent / "campaign-seam-evaluation"
    output_root.mkdir(parents=True, exist_ok=True)

    evaluation = build_design_suite_campaign_seam_evaluation(
        _load_json(late_root / "campaign" / "campaign-truth.json"),
        _load_json(late_root / "audits" / "campaign-cohesion-report.json"),
        _load_json(late_root / "audits" / "northstar-campaign-attribution-review.json"),
        _load_json(late_root / "design-suite-reusable-campaign-seam.json"),
        _load_json(forked_root / "campaign" / "campaign-truth.json"),
        _load_json(forked_root / "audits" / "campaign-cohesion-report.json"),
        _load_json(forked_root / "audits" / "northstar-campaign-attribution-review.json"),
        _load_json(forked_root / "design-suite-reusable-campaign-seam.json"),
    )
    write_design_suite_campaign_seam_evaluation(output_root, evaluation)
    print(json.dumps({"output_dir": str(output_root), "evaluation": evaluation}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
