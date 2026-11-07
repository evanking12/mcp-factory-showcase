from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DESIGN_SUITE_POST_CAMPAIGN_REVIEW_ARTIFACT = "design-suite-post-campaign-review.json"


def build_design_suite_post_campaign_review(
    branch_decision: Mapping[str, Any],
    campaign_truth: Mapping[str, Any],
    campaign_cohesion: Mapping[str, Any],
    attribution_review: Mapping[str, Any],
) -> dict[str, Any]:
    decision = dict(branch_decision or {})
    truth = dict(campaign_truth or {})
    cohesion = dict(campaign_cohesion or {})
    attribution = dict(attribution_review or {})

    stronger_blocker_remains = not (
        bool(attribution.get("suite_used"))
        and bool(attribution.get("active_modules_bounded"))
        and not bool(attribution.get("compare_overclaim_detected"))
        and not bool(attribution.get("promotion_overclaim_detected"))
    )
    if stronger_blocker_remains:
        recommended_next_branch = "next implementation blocker"
        weakness_register_triage_eligible = False
    else:
        recommended_next_branch = "weakness-register triage and reduction"
        weakness_register_triage_eligible = True

    return {
        "artifact_type": DESIGN_SUITE_POST_CAMPAIGN_REVIEW_ARTIFACT,
        "schema_version": "1.0.0",
        "suite_id": str(truth.get("suite_id") or "").strip(),
        "pressure_mode": str(truth.get("pressure_mode") or "").strip(),
        "prior_branch_decision": str(decision.get("recommended_next_branch") or "").strip(),
        "campaign_truth_present": bool(truth),
        "campaign_cohesion_present": bool(cohesion),
        "campaign_attribution_present": bool(attribution),
        "stronger_blocker_remains": stronger_blocker_remains,
        "weakness_register_triage_eligible": weakness_register_triage_eligible,
        "recommended_next_branch": recommended_next_branch,
    }


def write_design_suite_post_campaign_review(output_dir: str | Path, payload: Mapping[str, Any]) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / DESIGN_SUITE_POST_CAMPAIGN_REVIEW_ARTIFACT
    destination.write_text(json.dumps(dict(payload), indent=2), encoding="utf-8")
    return destination
