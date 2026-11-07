from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DESIGN_SUITE_REUSABLE_CAMPAIGN_SEAM_ARTIFACT = "design-suite-reusable-campaign-seam.json"


def build_design_suite_campaign_snapshot(
    *,
    campaign_id: str,
    suite_id: str,
    pressure_mode: str,
    active_modules: list[str],
    deferred_modules: list[str],
    campaign_kind: str = "design_suite_architecture_proof",
) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "campaign_kind": campaign_kind,
        "suite_id": suite_id,
        "pressure_mode": pressure_mode,
        "active_modules": active_modules,
        "deferred_modules": deferred_modules,
        "status": "completed",
        "compare_ready": False,
        "promotion_ready": False,
    }


def build_design_suite_campaign_truth(
    campaign_id: str,
    campaign_plan: Mapping[str, Any],
    campaign_truth: Mapping[str, Any],
    *,
    campaign_surface: str = "design_suite_bounded_campaign",
) -> dict[str, Any]:
    plan = dict(campaign_plan or {})
    truth = dict(campaign_truth or {})
    return {
        "campaign_id": campaign_id,
        "suite_id": str(plan.get("suite_id") or "").strip(),
        "pressure_mode": str(plan.get("pressure_mode") or "").strip(),
        "campaign_surface": campaign_surface,
        "active_modules": list(plan.get("active_modules") or []),
        "deferred_modules": list(plan.get("deferred_modules") or []),
        "blocker_family_ids": list(truth.get("blocker_family_ids") or plan.get("blocker_family_ids") or []),
        "provisional_subject_ids": list(truth.get("provisional_subject_ids") or []),
        "confirmation_sites": list(truth.get("confirmation_sites") or []),
        "lineage_branches": list(truth.get("lineage_branches") or []),
        "accepted_branches": list(truth.get("accepted_branches") or []),
        "rejected_branches": list(truth.get("rejected_branches") or []),
        "family_blocker_ids": list(plan.get("blocker_family_ids") or []),
        "compare_ready": False,
        "promotion_ready": False,
    }


def build_design_suite_campaign_cohesion(
    campaign_id: str,
    campaign_plan: Mapping[str, Any],
    scaling_cohesion: Mapping[str, Any],
    *,
    campaign_surface: str = "design_suite_bounded_campaign",
) -> dict[str, Any]:
    plan = dict(campaign_plan or {})
    cohesion = dict(scaling_cohesion or {})
    return {
        "campaign_id": campaign_id,
        "suite_id": str(plan.get("suite_id") or "").strip(),
        "pressure_mode": str(plan.get("pressure_mode") or "").strip(),
        "campaign_surface": campaign_surface,
        "active_modules": list(plan.get("active_modules") or []),
        "family_blocker_ids": list(plan.get("blocker_family_ids") or []),
        "provisional_subject_ids": list(cohesion.get("provisional_subject_ids") or []),
        "confirmation_sites": list(cohesion.get("confirmation_sites") or []),
        "lineage_branches": list(cohesion.get("lineage_branches") or []),
        "accepted_branches": list(cohesion.get("accepted_branches") or []),
        "rejected_branches": list(cohesion.get("rejected_branches") or []),
        "forked_state_semantics_preserved": bool(cohesion.get("accepted_branches")) and bool(cohesion.get("rejected_branches")),
        "readable": bool(cohesion.get("readable")),
        "complete": bool(cohesion.get("complete")),
        "compare_ready": False,
        "promotion_ready": False,
    }


def build_design_suite_campaign_attribution_review(
    campaign_id: str,
    campaign_truth: Mapping[str, Any],
    campaign_cohesion: Mapping[str, Any],
    *,
    expected_suite_id: str | None = None,
    expected_active_module_count: int | None = None,
) -> dict[str, Any]:
    truth = dict(campaign_truth or {})
    cohesion = dict(campaign_cohesion or {})
    suite_id = str(truth.get("suite_id") or "").strip()
    active_modules = list(truth.get("active_modules") or [])
    return {
        "campaign_id": campaign_id,
        "suite_used": suite_id == str(expected_suite_id or suite_id).strip(),
        "pressure_mode": str(truth.get("pressure_mode") or "").strip(),
        "forked_state_mode_used": str(truth.get("pressure_mode") or "").strip() == "forked_state",
        "active_modules_bounded": (
            len(active_modules) == expected_active_module_count
            if expected_active_module_count is not None
            else bool(active_modules)
        ),
        "provisional_subjects_preserved": bool(truth.get("provisional_subject_ids")),
        "confirmation_sites_preserved": bool(truth.get("confirmation_sites")),
        "accepted_branch_preserved": bool(truth.get("accepted_branches")) and bool(cohesion.get("accepted_branches")),
        "rejected_branch_preserved": bool(truth.get("rejected_branches")) and bool(cohesion.get("rejected_branches")),
        "branch_overclaim_detected": (
            str(truth.get("pressure_mode") or "").strip() == "forked_state"
            and not (
                bool(truth.get("accepted_branches"))
                and bool(truth.get("rejected_branches"))
                and bool(cohesion.get("accepted_branches"))
                and bool(cohesion.get("rejected_branches"))
            )
        ),
        "compare_overclaim_detected": bool(truth.get("compare_ready")) or bool(cohesion.get("compare_ready")),
        "promotion_overclaim_detected": bool(truth.get("promotion_ready")) or bool(cohesion.get("promotion_ready")),
    }


def build_design_suite_reusable_campaign_seam(
    campaign_plan: Mapping[str, Any],
    campaign_truth: Mapping[str, Any],
    campaign_cohesion: Mapping[str, Any],
    attribution_review: Mapping[str, Any],
) -> dict[str, Any]:
    plan = dict(campaign_plan or {})
    truth = dict(campaign_truth or {})
    cohesion = dict(campaign_cohesion or {})
    attribution = dict(attribution_review or {})
    pressure_mode = str(plan.get("pressure_mode") or "").strip()
    remaining_glue: list[str] = [
        "suite-specific entrypoint wrapper",
        "suite-specific campaign artifact naming",
    ]
    if pressure_mode == "forked_state":
        remaining_glue.append("suite-specific branch review wording")
    glue_resolution_plan = {
        "suite-specific entrypoint wrapper": "keep for now",
        "suite-specific campaign artifact naming": "narrow",
        "suite-specific branch review wording": (
            "supersede in next prompt" if pressure_mode == "forked_state" else "keep for now"
        ),
    }
    inherited_surfaces = [
        "campaign truth projection",
        "campaign cohesion projection",
        "campaign attribution preservation",
    ]
    not_yet_inherited = [
        "generic design-suite campaign runner",
        "compare or promotion readiness",
        "collector or ledger integration",
    ]
    return {
        "artifact_type": DESIGN_SUITE_REUSABLE_CAMPAIGN_SEAM_ARTIFACT,
        "schema_version": "1.0.0",
        "suite_id": str(plan.get("suite_id") or "").strip(),
        "pressure_mode": pressure_mode,
        "reusable_truth_projection_present": bool(truth.get("suite_id")) and bool(truth.get("campaign_surface")),
        "reusable_cohesion_projection_present": bool(cohesion.get("suite_id")) and bool(cohesion.get("campaign_surface")),
        "reusable_attribution_projection_present": bool(attribution.get("suite_used")),
        "remaining_northstar_specific_glue": remaining_glue,
        "glue_resolution_plan": glue_resolution_plan,
        "successor_suite_inherits": inherited_surfaces,
        "successor_suite_does_not_yet_inherit": not_yet_inherited,
    }


def build_northstar_campaign_snapshot(
    *,
    campaign_id: str,
    suite_id: str,
    pressure_mode: str,
    active_modules: list[str],
    deferred_modules: list[str],
) -> dict[str, Any]:
    return build_design_suite_campaign_snapshot(
        campaign_id=campaign_id,
        suite_id=suite_id,
        pressure_mode=pressure_mode,
        active_modules=active_modules,
        deferred_modules=deferred_modules,
        campaign_kind="design_suite_architecture_proof",
    )


def build_northstar_campaign_truth(
    campaign_id: str,
    campaign_plan: Mapping[str, Any],
    campaign_truth: Mapping[str, Any],
) -> dict[str, Any]:
    return build_design_suite_campaign_truth(
        campaign_id,
        campaign_plan,
        campaign_truth,
        campaign_surface="northstar_bounded_campaign",
    )


def build_northstar_campaign_cohesion(
    campaign_id: str,
    campaign_plan: Mapping[str, Any],
    scaling_cohesion: Mapping[str, Any],
) -> dict[str, Any]:
    return build_design_suite_campaign_cohesion(
        campaign_id,
        campaign_plan,
        scaling_cohesion,
        campaign_surface="northstar_bounded_campaign",
    )


def build_northstar_campaign_attribution_review(
    campaign_id: str,
    campaign_truth: Mapping[str, Any],
    campaign_cohesion: Mapping[str, Any],
) -> dict[str, Any]:
    return build_design_suite_campaign_attribution_review(
        campaign_id,
        campaign_truth,
        campaign_cohesion,
        expected_suite_id="northstar_transaction_suite",
        expected_active_module_count=4,
    )


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2), encoding="utf-8")
