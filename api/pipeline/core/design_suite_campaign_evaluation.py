from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DESIGN_SUITE_CAMPAIGN_SEAM_EVALUATION_ARTIFACT = "design-suite-campaign-seam-evaluation.json"


def build_design_suite_campaign_seam_evaluation(
    late_campaign_truth: Mapping[str, Any],
    late_campaign_cohesion: Mapping[str, Any],
    late_campaign_attribution: Mapping[str, Any],
    late_reusable_campaign_seam: Mapping[str, Any],
    forked_campaign_truth: Mapping[str, Any],
    forked_campaign_cohesion: Mapping[str, Any],
    forked_campaign_attribution: Mapping[str, Any],
    forked_reusable_campaign_seam: Mapping[str, Any],
) -> dict[str, Any]:
    late_truth = dict(late_campaign_truth or {})
    late_cohesion = dict(late_campaign_cohesion or {})
    late_attr = dict(late_campaign_attribution or {})
    late_seam = dict(late_reusable_campaign_seam or {})
    forked_truth = dict(forked_campaign_truth or {})
    forked_cohesion = dict(forked_campaign_cohesion or {})
    forked_attr = dict(forked_campaign_attribution or {})
    forked_seam = dict(forked_reusable_campaign_seam or {})

    late_confirmation_green = (
        str(late_truth.get("pressure_mode") or "").strip() == "late_confirmation"
        and bool(late_attr.get("suite_used"))
        and bool(late_attr.get("active_modules_bounded"))
        and bool(late_truth.get("provisional_subject_ids"))
        and bool(late_truth.get("confirmation_sites"))
        and not bool(late_attr.get("compare_overclaim_detected"))
        and not bool(late_attr.get("promotion_overclaim_detected"))
    )
    forked_state_green = (
        str(forked_truth.get("pressure_mode") or "").strip() == "forked_state"
        and bool(forked_attr.get("suite_used"))
        and bool(forked_attr.get("active_modules_bounded"))
        and bool(forked_truth.get("accepted_branches"))
        and bool(forked_truth.get("rejected_branches"))
        and bool(forked_cohesion.get("forked_state_semantics_preserved"))
        and bool(forked_attr.get("accepted_branch_preserved"))
        and bool(forked_attr.get("rejected_branch_preserved"))
        and not bool(forked_attr.get("branch_overclaim_detected"))
        and not bool(forked_attr.get("compare_overclaim_detected"))
        and not bool(forked_attr.get("promotion_overclaim_detected"))
    )

    reusable_campaign_seam_present = all(
        (
            late_seam.get("reusable_truth_projection_present"),
            late_seam.get("reusable_cohesion_projection_present"),
            late_seam.get("reusable_attribution_projection_present"),
            forked_seam.get("reusable_truth_projection_present"),
            forked_seam.get("reusable_cohesion_projection_present"),
            forked_seam.get("reusable_attribution_projection_present"),
        )
    )

    remaining_northstar_specific_glue = sorted(
        {
            str(item or "").strip()
            for seam in (late_seam, forked_seam)
            for item in list(seam.get("remaining_northstar_specific_glue") or [])
            if str(item or "").strip()
        }
    )

    inherited_sets = []
    for seam in (late_seam, forked_seam):
        inherited = {
            str(item or "").strip()
            for item in list(seam.get("successor_suite_inherits") or [])
            if str(item or "").strip()
        }
        if inherited:
            inherited_sets.append(inherited)
    recommended_inherited_surfaces = sorted(set.intersection(*inherited_sets)) if inherited_sets else []

    blocking_reasons: list[str] = []
    if not late_confirmation_green:
        blocking_reasons.append("late_confirmation_campaign_regressed")
    if not forked_state_green:
        blocking_reasons.append("forked_state_campaign_regressed")
    if not reusable_campaign_seam_present:
        blocking_reasons.append("reusable_campaign_seam_incomplete")

    successor_suite_inheritance_ready = (
        late_confirmation_green
        and forked_state_green
        and reusable_campaign_seam_present
        and len(remaining_northstar_specific_glue) <= 3
        and bool(recommended_inherited_surfaces)
    )

    if successor_suite_inheritance_ready:
        recommended_next_branch = "successor-suite contract and inheritance gate"
    elif late_confirmation_green and forked_state_green:
        recommended_next_branch = "generic campaign seam tightening"
    else:
        recommended_next_branch = "narrower repair prompt"

    return {
        "artifact_type": DESIGN_SUITE_CAMPAIGN_SEAM_EVALUATION_ARTIFACT,
        "schema_version": "1.0.0",
        "suite_id": "northstar_transaction_suite",
        "late_confirmation_green": late_confirmation_green,
        "forked_state_green": forked_state_green,
        "reusable_campaign_seam_present": reusable_campaign_seam_present,
        "remaining_northstar_specific_glue": remaining_northstar_specific_glue,
        "successor_suite_inheritance_ready": successor_suite_inheritance_ready,
        "recommended_inherited_surfaces": recommended_inherited_surfaces,
        "compare_ready": False,
        "promotion_ready": False,
        "recommended_next_branch": recommended_next_branch,
        "blocking_reasons": blocking_reasons,
    }


def write_design_suite_campaign_seam_evaluation(
    output_dir: str | Path,
    evaluation: Mapping[str, Any],
) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / DESIGN_SUITE_CAMPAIGN_SEAM_EVALUATION_ARTIFACT
    path.write_text(json.dumps(dict(evaluation), indent=2), encoding="utf-8")
    return path
