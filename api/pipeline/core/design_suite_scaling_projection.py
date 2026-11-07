from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from api.pipeline.core.decomposition_runtime_bridge import build_decomposition_campaign_plan
from api.pipeline.core.design_suite_artifacts import (
    NORTHSTAR_FAMILY_BLOCKER_ARTIFACT,
    NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT,
    NORTHSTAR_SHARED_STATE_ARTIFACT,
    NorthstarProducerConsumerReport,
    NorthstarSharedStateReport,
)
from api.pipeline.core.design_suite_expected_observed import (
    load_design_suite_manifest,
    write_design_suite_artifact,
)
from api.pipeline.core.package_frontier_planner import build_package_frontier_plan


DESIGN_SUITE_SCALING_PROJECTION_ARTIFACT = "design-suite-scaling-projection.json"
DESIGN_SUITE_SLICE_PLAN_ARTIFACT = "design-suite-slice-plan.json"
DESIGN_SUITE_SCALING_COHESION_ARTIFACT = "design-suite-scaling-cohesion.json"


def _module_verified_count(per_module: list[dict[str, Any]], module_name: str) -> int:
    for row in per_module:
        if str((row or {}).get("module") or "").strip() != module_name:
            continue
        return 1 if str((row or {}).get("status") or "").strip().lower() == "success" else 0
    return 0


def _build_package_summary(
    campaign_plan: Mapping[str, Any],
    campaign_truth: Mapping[str, Any],
) -> dict[str, Any]:
    plan = dict(campaign_plan or {})
    truth = dict(campaign_truth or {})
    suite_id = str(plan.get("suite_id") or "").strip() or "design_suite"
    active_modules = [str(name or "").strip() for name in list(plan.get("active_modules") or []) if str(name or "").strip()]
    deferred_modules = [str(name or "").strip() for name in list(plan.get("deferred_modules") or []) if str(name or "").strip()]
    runtime_targets = active_modules + [name for name in deferred_modules if name not in active_modules]
    per_module = [dict(row) for row in list(truth.get("per_module") or []) if isinstance(row, dict)]
    provisional_subjects = [str(name or "").strip() for name in list(plan.get("provisional_subject_ids") or []) if str(name or "").strip()]

    frontier_targets = provisional_subjects or [
        f"{module_name}.execute"
        for module_name in active_modules
        if module_name != "session"
    ]
    overlap_regression_summary = []
    for subject_id in frontier_targets:
        module_name, _, function_name = subject_id.partition(".")
        if not module_name or not function_name:
            continue
        overlap_regression_summary.append(
            {
                "dll": module_name,
                "function": function_name,
                "likely_regression_cause": "design_suite_local_campaign_shape",
                "follow_up_class": "immediate_follow_up",
            }
        )

    return {
        "wave_id": f"{plan.get('suite_id', '')}:{plan.get('pressure_mode', '')}:local_campaign_shape",
        "campaign_id": f"{plan.get('suite_id', '')}:{plan.get('pressure_mode', '')}:local_campaign_shape",
        "package_id": str(plan.get("suite_id") or "").strip(),
        "package_label": str(plan.get("suite_name") or plan.get("suite_id") or "").strip(),
        "runtime_targets": runtime_targets,
        "cohesion_summary": {
            "per_dll": [
                {
                    "filename": module_name,
                    "job_id": f"{suite_id}-local::{module_name}",
                    "component": module_name,
                    "verified_count": _module_verified_count(per_module, module_name),
                    "total_functions": 1,
                }
                for module_name in runtime_targets
            ]
        },
        "attribution_summary": {
            "baseline_contract": {
                "source_wave_id": "design_suite_local_campaign_shape",
                "overlap_dll_set": active_modules,
                "dll_entries": [
                    {
                        "filename": module_name,
                        "dll_id": module_name,
                        "component": module_name,
                        "baseline_job_id": f"{suite_id}-baseline::{module_name}",
                    }
                    for module_name in active_modules
                ],
            },
            "per_dll": [
                {
                    "filename": module_name,
                    "component": module_name,
                }
                for module_name in runtime_targets
            ],
        },
        "overlap_regression_summary": overlap_regression_summary,
    }


def _build_campaign_input(campaign_plan: Mapping[str, Any]) -> dict[str, Any]:
    plan = dict(campaign_plan or {})
    suite_id = str(plan.get("suite_id") or "").strip() or "design_suite"
    runtime_targets = [
        str(name or "").strip()
        for name in list(plan.get("active_modules") or []) + list(plan.get("deferred_modules") or [])
        if str(name or "").strip()
    ]
    return {
        "package_id": str(plan.get("suite_id") or "").strip(),
        "package_label": str(plan.get("suite_name") or plan.get("suite_id") or "").strip(),
        "graph_epoch": f"{plan.get('suite_id', '')}:{plan.get('pressure_mode', '')}:local_campaign_shape",
        "dll_entries": [
            {
                "dll_id": module_name,
                "filename": module_name,
                "job_id": f"{suite_id}-local::{module_name}",
            }
            for module_name in runtime_targets
        ],
    }


def _derive_subject_hints(observed_bundle: Mapping[str, Any]) -> dict[str, list[str]]:
    hints: dict[str, list[str]] = {}
    for row in list(observed_bundle.get(NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT) or []):
        if not isinstance(row, Mapping):
            continue
        family = str(row.get("family") or "").strip()
        producer_module = str(row.get("producer_module") or "").strip()
        consumer_module = str(row.get("consumer_module") or "").strip()
        if family:
            hints[family] = sorted({producer_module, consumer_module} - {""})
    for row in list(observed_bundle.get(NORTHSTAR_SHARED_STATE_ARTIFACT) or []):
        if not isinstance(row, Mapping):
            continue
        carrier_id = str(row.get("carrier_id") or "").strip()
        modules = {
            str(item or "").strip().split(".", 1)[0]
            for item in list(row.get("downstream_consumers") or [])
            if str(item or "").strip()
        }
        modules.update(
            str(item or "").strip().split(".", 1)[0]
            for item in list(row.get("exporting_seams") or [])
            if str(item or "").strip()
        )
        if carrier_id:
            hints[carrier_id] = sorted(modules - {""})
    return hints


def _build_interwoven_context(observed_bundle: Mapping[str, Any]) -> dict[str, Any]:
    producer_reports = []
    for row in list(observed_bundle.get(NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT) or []):
        if not isinstance(row, Mapping):
            continue
        payload = dict(row)
        payload.pop("artifact_type", None)
        payload.pop("contract_version", None)
        producer_reports.append(NorthstarProducerConsumerReport(**payload).to_interwoven_report().to_dict())

    shared_state_reports = []
    for row in list(observed_bundle.get(NORTHSTAR_SHARED_STATE_ARTIFACT) or []):
        if not isinstance(row, Mapping):
            continue
        payload = dict(row)
        payload.pop("artifact_type", None)
        payload.pop("contract_version", None)
        shared_state_reports.append(NorthstarSharedStateReport(**payload).to_interwoven_report().to_dict())

    return {
        "producer_consumer_reports": producer_reports,
        "shared_state_reports": shared_state_reports,
        "subject_dll_hints": _derive_subject_hints(observed_bundle),
    }


def build_design_suite_scaling_projection(
    campaign_plan: Mapping[str, Any],
    campaign_truth: Mapping[str, Any],
    campaign_cohesion: Mapping[str, Any],
    observed_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    package_summary = _build_package_summary(campaign_plan, campaign_truth)
    package_frontier_plan = build_package_frontier_plan(package_summary)
    decomposition_plan = build_decomposition_campaign_plan(
        _build_campaign_input(campaign_plan),
        package_frontier_plan,
        max_slice_dlls=4,
        interwoven_context=_build_interwoven_context(observed_bundle),
    )
    family_blocker_ids = sorted(
        {
            str((row or {}).get("blocker_family") or "").strip()
            for row in list(observed_bundle.get(NORTHSTAR_FAMILY_BLOCKER_ARTIFACT) or [])
            if str((row or {}).get("blocker_family") or "").strip()
        }
    )
    contradiction_summary = Counter(
        str((row or {}).get("contradiction_state") or "none").strip() or "none"
        for row in list(observed_bundle.get(NORTHSTAR_FAMILY_BLOCKER_ARTIFACT) or [])
        if isinstance(row, Mapping)
    )
    return {
        "artifact_type": DESIGN_SUITE_SCALING_PROJECTION_ARTIFACT,
        "schema_version": "1.0.0",
        "suite_id": str(campaign_plan.get("suite_id") or "").strip(),
        "pressure_mode": str(campaign_plan.get("pressure_mode") or "").strip(),
        "active_modules": list(campaign_plan.get("active_modules") or []),
        "design_suite_campaign_surface": str(campaign_plan.get("campaign_surface") or "").strip(),
        "family_blocker_ids": family_blocker_ids,
        "family_blocker_contradiction_summary": dict(contradiction_summary),
        "family_blockers_preserved": True,
        "provisional_subject_ids": list(campaign_plan.get("provisional_subject_ids") or []),
        "confirmation_sites": list(campaign_plan.get("confirmation_sites") or []),
        "lineage_branches": list(campaign_plan.get("lineage_branches") or []),
        "accepted_branches": list(campaign_plan.get("accepted_branches") or []),
        "rejected_branches": list(campaign_plan.get("rejected_branches") or []),
        "decomposition_campaign_plan": decomposition_plan,
        "campaign_cohesion_runtime_attribution_present": bool(campaign_cohesion.get("runtime_attribution_present")),
    }


def build_design_suite_slice_plan(scaling_projection: Mapping[str, Any]) -> dict[str, Any]:
    projection = dict(scaling_projection or {})
    decomposition_plan = dict(projection.get("decomposition_campaign_plan") or {})
    frontier_slice_plan = dict(decomposition_plan.get("frontier_slice_plan") or {})
    execution_map = dict(decomposition_plan.get("execution_map") or {})
    return {
        "artifact_type": DESIGN_SUITE_SLICE_PLAN_ARTIFACT,
        "schema_version": "1.0.0",
        "suite_id": str(projection.get("suite_id") or "").strip(),
        "pressure_mode": str(projection.get("pressure_mode") or "").strip(),
        "active_modules": list(projection.get("active_modules") or []),
        "family_blocker_ids": list(projection.get("family_blocker_ids") or []),
        "design_suite_subject_ids": list(decomposition_plan.get("interwoven_subject_ids") or []),
        "provisional_subject_ids": list(projection.get("provisional_subject_ids") or []),
        "confirmation_sites": list(projection.get("confirmation_sites") or []),
        "lineage_branches": list(projection.get("lineage_branches") or []),
        "accepted_branches": list(projection.get("accepted_branches") or []),
        "rejected_branches": list(projection.get("rejected_branches") or []),
        "frontier_slices": list(frontier_slice_plan.get("frontier_slices") or []),
        "execution_units": list(execution_map.get("execution_units") or []),
        "slice_execution_attribution": bool(decomposition_plan.get("slice_execution_attribution_present")),
    }


def build_design_suite_scaling_cohesion(
    scaling_projection: Mapping[str, Any],
    slice_plan: Mapping[str, Any],
) -> dict[str, Any]:
    projection = dict(scaling_projection or {})
    decomposition_plan = dict(projection.get("decomposition_campaign_plan") or {})
    slices = list(slice_plan.get("frontier_slices") or [])
    return {
        "artifact_type": DESIGN_SUITE_SCALING_COHESION_ARTIFACT,
        "schema_version": "1.0.0",
        "suite_id": str(projection.get("suite_id") or "").strip(),
        "pressure_mode": str(projection.get("pressure_mode") or "").strip(),
        "active_modules": list(projection.get("active_modules") or []),
        "family_blocker_ids": list(projection.get("family_blocker_ids") or []),
        "family_blockers_preserved": bool(projection.get("family_blockers_preserved")),
        "provisional_subject_ids": list(projection.get("provisional_subject_ids") or []),
        "confirmation_sites": list(projection.get("confirmation_sites") or []),
        "lineage_branches": list(projection.get("lineage_branches") or []),
        "accepted_branches": list(projection.get("accepted_branches") or []),
        "rejected_branches": list(projection.get("rejected_branches") or []),
        "slice_count": len(slices),
        "slice_execution_attribution_present": bool(slice_plan.get("slice_execution_attribution")),
        "readable": len(slices) <= 4,
        "complete": bool(slices),
    }


def run_design_suite_scaling_projection(
    campaign_local_dir: str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(campaign_local_dir)
    if manifest_path is not None:
        load_design_suite_manifest(manifest_path)
    campaign_plan = __import__("json").loads((root / "design-suite-campaign-plan.json").read_text(encoding="utf-8"))
    campaign_truth = __import__("json").loads((root / "design-suite-campaign-truth.json").read_text(encoding="utf-8"))
    campaign_cohesion = __import__("json").loads((root / "design-suite-campaign-cohesion-report.json").read_text(encoding="utf-8"))
    observed_bundle = {
        NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT: __import__("json").loads((root / NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT).read_text(encoding="utf-8")),
        NORTHSTAR_SHARED_STATE_ARTIFACT: __import__("json").loads((root / NORTHSTAR_SHARED_STATE_ARTIFACT).read_text(encoding="utf-8")),
        NORTHSTAR_FAMILY_BLOCKER_ARTIFACT: __import__("json").loads((root / NORTHSTAR_FAMILY_BLOCKER_ARTIFACT).read_text(encoding="utf-8")),
    }
    scaling_projection = build_design_suite_scaling_projection(campaign_plan, campaign_truth, campaign_cohesion, observed_bundle)
    slice_plan = build_design_suite_slice_plan(scaling_projection)
    scaling_cohesion = build_design_suite_scaling_cohesion(scaling_projection, slice_plan)
    write_design_suite_artifact(root, DESIGN_SUITE_SCALING_PROJECTION_ARTIFACT, scaling_projection)
    write_design_suite_artifact(root, DESIGN_SUITE_SLICE_PLAN_ARTIFACT, slice_plan)
    write_design_suite_artifact(root, DESIGN_SUITE_SCALING_COHESION_ARTIFACT, scaling_cohesion)
    return {
        "output_dir": str(root),
        "scaling_projection": scaling_projection,
        "slice_plan": slice_plan,
        "scaling_cohesion": scaling_cohesion,
    }
