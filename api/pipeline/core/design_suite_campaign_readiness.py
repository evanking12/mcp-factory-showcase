from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from api.pipeline.core.design_suite_expected_observed import write_design_suite_artifact


DESIGN_SUITE_CAMPAIGN_READINESS_ARTIFACT = "northstar-campaign-readiness.json"


def build_design_suite_campaign_readiness(
    campaign_local_plan: Mapping[str, Any],
    campaign_local_truth: Mapping[str, Any],
    campaign_local_cohesion: Mapping[str, Any],
    scaling_projection: Mapping[str, Any],
    scaling_cohesion: Mapping[str, Any],
    *,
    target_mode: str | None = None,
    forked_state_guard: Mapping[str, Any] | None = None,
    require_forked_state_local_guard: bool = True,
    artifact_type: str = DESIGN_SUITE_CAMPAIGN_READINESS_ARTIFACT,
) -> dict[str, Any]:
    plan = dict(campaign_local_plan or {})
    truth = dict(campaign_local_truth or {})
    cohesion = dict(campaign_local_cohesion or {})
    projection = dict(scaling_projection or {})
    projection_plan = dict(projection.get("decomposition_campaign_plan") or {})
    execution_map = dict(projection_plan.get("execution_map") or {})
    scaling = dict(scaling_cohesion or {})
    forked_guard = dict(forked_state_guard or {})
    normalized_target_mode = str(target_mode or plan.get("pressure_mode") or "").strip() or "late_confirmation"

    local_campaign_shape_green = (
        str(plan.get("campaign_surface") or "").strip() == "design_suite_local_campaign_shape"
        and bool(plan.get("active_modules"))
        and bool(truth.get("active_modules"))
    )
    scaling_projection_green = bool(projection.get("family_blockers_preserved")) and bool(projection_plan.get("active_frontier_slice_ids"))
    runtime_projection_green = bool(projection_plan.get("interwoven_artifact_presence")) and bool(execution_map.get("execution_units"))
    is_forked_state_target = normalized_target_mode == "forked_state"
    package_truth_green = (
        bool(truth.get("accepted_branches")) and bool(truth.get("rejected_branches"))
        if is_forked_state_target
        else bool(truth.get("provisional_subject_ids")) and bool(truth.get("confirmation_sites"))
    )
    cohesion_green = bool(cohesion.get("runtime_attribution_present")) and bool(scaling.get("complete"))
    forked_state_local_guard_green = (
        bool(forked_guard.get("accepted_branches")) and bool(forked_guard.get("rejected_branches"))
        if require_forked_state_local_guard
        else True
    )
    accepted_branch_present = bool(truth.get("accepted_branches"))
    rejected_branch_present = bool(truth.get("rejected_branches"))
    campaign_truth_branch_projection_green = accepted_branch_present and rejected_branch_present
    campaign_cohesion_branch_projection_green = (
        bool(scaling.get("accepted_branches"))
        and bool(scaling.get("rejected_branches"))
        and bool(scaling.get("lineage_branches"))
    )
    forked_state_campaign_semantics_green = (
        campaign_truth_branch_projection_green and campaign_cohesion_branch_projection_green
        if is_forked_state_target
        else True
    )
    campaign_runner_changes_required = True

    blocking_reasons: list[str] = []
    if not local_campaign_shape_green:
        blocking_reasons.append("local_campaign_shape_incomplete")
    if not scaling_projection_green:
        blocking_reasons.append("scaling_projection_incomplete")
    if not runtime_projection_green:
        blocking_reasons.append("runtime_projection_incomplete")
    if not package_truth_green:
        blocking_reasons.append("package_truth_missing_provisional_or_confirmation_semantics")
    if not cohesion_green:
        blocking_reasons.append("cohesion_missing_runtime_or_scaling_attribution")
    if require_forked_state_local_guard and not forked_state_local_guard_green:
        blocking_reasons.append("forked_state_local_guard_incomplete")
    if is_forked_state_target and not forked_state_campaign_semantics_green:
        blocking_reasons.append("forked_state_campaign_semantics_incomplete")

    ready = not blocking_reasons
    return {
        "artifact_type": artifact_type,
        "schema_version": "1.0.0",
        "suite_id": str(plan.get("suite_id") or "").strip(),
        "target_mode": normalized_target_mode,
        "local_campaign_shape_green": local_campaign_shape_green,
        "scaling_projection_green": scaling_projection_green,
        "runtime_projection_green": runtime_projection_green,
        "package_truth_green": package_truth_green,
        "cohesion_green": cohesion_green,
        "forked_state_local_guard_green": forked_state_local_guard_green,
        "forked_state_campaign_semantics_green": forked_state_campaign_semantics_green,
        "accepted_branch_present": accepted_branch_present,
        "rejected_branch_present": rejected_branch_present,
        "campaign_truth_branch_projection_green": campaign_truth_branch_projection_green,
        "campaign_cohesion_branch_projection_green": campaign_cohesion_branch_projection_green,
        "campaign_runner_changes_required": campaign_runner_changes_required,
        "compare_ready": False,
        "promotion_ready": False,
        "ready_for_first_bounded_campaign": ready,
        "blocking_reasons": blocking_reasons,
    }


def write_design_suite_campaign_readiness(
    output_dir: str | Path,
    readiness: Mapping[str, Any],
) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    write_design_suite_artifact(root, DESIGN_SUITE_CAMPAIGN_READINESS_ARTIFACT, dict(readiness))
    return root / DESIGN_SUITE_CAMPAIGN_READINESS_ARTIFACT
