from __future__ import annotations

from typing import Any, Mapping


DESIGN_SUITE_LOCAL_CAMPAIGN_SCHEMA_VERSION = "1.0.0"

DESIGN_SUITE_CAMPAIGN_PLAN_ARTIFACT = "design-suite-campaign-plan.json"
DESIGN_SUITE_CAMPAIGN_TRUTH_ARTIFACT = "design-suite-campaign-truth.json"
DESIGN_SUITE_CAMPAIGN_COHESION_ARTIFACT = "design-suite-campaign-cohesion-report.json"
DESIGN_SUITE_CAMPAIGN_EXECUTION_TRACE_ARTIFACT = "design-suite-campaign-execution-trace.json"
DESIGN_SUITE_CAMPAIGN_READINESS_INPUT_ARTIFACT = "design-suite-campaign-readiness-input.json"


def build_design_suite_campaign_local_plan(
    runtime_projection: Mapping[str, Any],
    package_truth: Mapping[str, Any],
) -> dict[str, Any]:
    projection = dict(runtime_projection or {})
    truth = dict(package_truth or {})
    return {
        "schema_version": DESIGN_SUITE_LOCAL_CAMPAIGN_SCHEMA_VERSION,
        "artifact_type": DESIGN_SUITE_CAMPAIGN_PLAN_ARTIFACT,
        "suite_id": str(projection.get("suite_id") or "").strip(),
        "suite_name": str(projection.get("suite_name") or "").strip(),
        "pressure_mode": str(projection.get("pressure_mode") or "").strip(),
        "campaign_surface": "design_suite_local_campaign_shape",
        "compare_ready": False,
        "promotion_ready": False,
        "active_modules": list(projection.get("active_modules") or []),
        "deferred_modules": list(projection.get("deferred_modules") or []),
        "execution_order": list(projection.get("execution_order") or []),
        "blocker_family_ids": list(projection.get("blocker_family_ids") or []),
        "provisional_subject_ids": list(projection.get("provisional_subject_ids") or []),
        "confirmation_sites": list(projection.get("confirmation_sites") or []),
        "lineage_branches": list(projection.get("lineage_branches") or []),
        "accepted_branches": list(projection.get("accepted_branches") or []),
        "rejected_branches": list(projection.get("rejected_branches") or []),
        "design_suite_subject_ids": list(projection.get("design_suite_subject_ids") or []),
        "design_suite_projection_present": bool(truth.get("design_suite_projection_present")),
        "package_runtime_evidence_class": str(truth.get("package_runtime_evidence_class") or "").strip(),
    }


def build_design_suite_campaign_local_truth(
    campaign_plan: Mapping[str, Any],
    package_truth: Mapping[str, Any],
) -> dict[str, Any]:
    plan = dict(campaign_plan or {})
    truth = dict(package_truth or {})
    return {
        "schema_version": DESIGN_SUITE_LOCAL_CAMPAIGN_SCHEMA_VERSION,
        "artifact_type": DESIGN_SUITE_CAMPAIGN_TRUTH_ARTIFACT,
        "suite_id": str(plan.get("suite_id") or "").strip(),
        "pressure_mode": str(plan.get("pressure_mode") or "").strip(),
        "campaign_surface": "design_suite_local_campaign_shape",
        "active_modules": list(plan.get("active_modules") or []),
        "deferred_modules": list(plan.get("deferred_modules") or []),
        "per_module": list(truth.get("per_module") or []),
        "blocker_family_ids": list(plan.get("blocker_family_ids") or []),
        "provisional_subject_ids": list(plan.get("provisional_subject_ids") or []),
        "confirmation_sites": list(plan.get("confirmation_sites") or []),
        "lineage_branches": list(plan.get("lineage_branches") or []),
        "accepted_branches": list(plan.get("accepted_branches") or []),
        "rejected_branches": list(plan.get("rejected_branches") or []),
        "compare_ready": False,
        "promotion_ready": False,
    }


def build_design_suite_campaign_local_cohesion(
    campaign_plan: Mapping[str, Any],
    cohesion_report: Mapping[str, Any],
) -> dict[str, Any]:
    plan = dict(campaign_plan or {})
    cohesion = dict(cohesion_report or {})
    return {
        "schema_version": DESIGN_SUITE_LOCAL_CAMPAIGN_SCHEMA_VERSION,
        "artifact_type": DESIGN_SUITE_CAMPAIGN_COHESION_ARTIFACT,
        "suite_id": str(plan.get("suite_id") or "").strip(),
        "pressure_mode": str(plan.get("pressure_mode") or "").strip(),
        "campaign_surface": "design_suite_local_campaign_shape",
        "active_modules": list(plan.get("active_modules") or []),
        "blocker_family_ids": list(plan.get("blocker_family_ids") or []),
        "design_suite_subject_ids": list(cohesion.get("design_suite_subject_ids") or []),
        "provisional_subject_ids": list(plan.get("provisional_subject_ids") or []),
        "confirmation_sites": list(plan.get("confirmation_sites") or []),
        "lineage_branches": list(plan.get("lineage_branches") or []),
        "accepted_branches": list(plan.get("accepted_branches") or []),
        "rejected_branches": list(plan.get("rejected_branches") or []),
        "runtime_attribution_present": bool(cohesion.get("runtime_attribution_present")),
        "complete": bool(cohesion.get("complete")),
        "readable": True,
        "compare_ready": False,
        "promotion_ready": False,
    }


def build_design_suite_campaign_readiness_input(
    campaign_plan: Mapping[str, Any],
    campaign_truth: Mapping[str, Any],
    campaign_cohesion: Mapping[str, Any],
    execution_trace: Mapping[str, Any],
) -> dict[str, Any]:
    plan = dict(campaign_plan or {})
    truth = dict(campaign_truth or {})
    cohesion = dict(campaign_cohesion or {})
    trace = dict(execution_trace or {})
    return {
        "schema_version": DESIGN_SUITE_LOCAL_CAMPAIGN_SCHEMA_VERSION,
        "artifact_type": DESIGN_SUITE_CAMPAIGN_READINESS_INPUT_ARTIFACT,
        "suite_id": str(plan.get("suite_id") or "").strip(),
        "pressure_mode": str(plan.get("pressure_mode") or "").strip(),
        "campaign_surface": "design_suite_local_campaign_shape",
        "active_modules": list(plan.get("active_modules") or []),
        "deferred_modules": list(plan.get("deferred_modules") or []),
        "blocker_family_ids": list(plan.get("blocker_family_ids") or []),
        "provisional_subject_ids": list(truth.get("provisional_subject_ids") or []),
        "confirmation_sites": list(truth.get("confirmation_sites") or []),
        "lineage_branches": list(truth.get("lineage_branches") or []),
        "accepted_branches": list(truth.get("accepted_branches") or []),
        "rejected_branches": list(truth.get("rejected_branches") or []),
        "runtime_attribution_present": bool(cohesion.get("runtime_attribution_present")),
        "execution_step_ids": [
            str((row or {}).get("step_id") or "").strip()
            for row in list(trace.get("steps") or [])
            if str((row or {}).get("step_id") or "").strip()
        ],
        "compare_ready": False,
        "promotion_ready": False,
    }
