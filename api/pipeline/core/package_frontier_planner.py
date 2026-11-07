from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from api.pipeline.core.cluster_checkpoint import CLUSTER_CHECKPOINTS_BY_ID, infer_cluster_checkpoint_id
from api.pipeline.core.prerequisite_state_groups import PREREQUISITE_STATE_GROUPS_BY_ID


PACKAGE_FRONTIER_PLAN_SCHEMA_VERSION = "1.1.0"


@dataclass(frozen=True)
class PackageFrontierEntry:
    dll: str
    component: str
    source_job_id: str
    overlap_baseline_job_id: str
    cluster_checkpoint_id: str
    prerequisite_state_group_ids: tuple[str, ...]
    ceiling_functions: tuple[str, ...]
    ceiling_origin_functions: tuple[str, ...]
    focus_functions: tuple[str, ...]
    iteration_mode: str
    floor_scope: str
    max_iteration_cycles: int
    planner_reason: str
    imported_dependency_classes: tuple[str, ...]
    local_proof: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _baseline_job_by_filename(wave_summary: dict[str, Any]) -> dict[str, str]:
    baseline_contract = extract_package_baseline_contract(wave_summary)
    rows = (
        baseline_contract.get("entries")
        or baseline_contract.get("dll_entries")
        or baseline_contract.get("baseline_dll_entries")
        or []
    )
    resolved: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        filename = str(row.get("filename") or "").strip()
        job_id = str(row.get("baseline_job_id") or "").strip()
        if filename and job_id:
            resolved[filename] = job_id
    return resolved


def extract_package_baseline_contract(package_summary: dict[str, Any]) -> dict[str, Any]:
    attribution_summary = package_summary.get("attribution_summary") or {}
    baseline_contract = (
        attribution_summary.get("baseline_contract")
        or package_summary.get("baseline_contract")
        or {}
    )
    return dict(baseline_contract) if isinstance(baseline_contract, dict) else {}


def resolve_campaign_package_baseline_contract(
    campaign: dict[str, Any] | None,
    *,
    package_frontier_plan: dict[str, Any] | None = None,
    campaign_truth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    for candidate in (
        (campaign or {}).get("baseline_contract"),
        (campaign_truth or {}).get("baseline_contract"),
        (package_frontier_plan or {}).get("baseline_contract"),
    ):
        if isinstance(candidate, dict) and candidate:
            return dict(candidate)
    return {}


def _campaign_component_by_filename(wave_summary: dict[str, Any]) -> dict[str, str]:
    attribution = wave_summary.get("attribution_summary") or {}
    resolved: dict[str, str] = {}
    for row in list(attribution.get("per_dll") or []):
        if not isinstance(row, dict):
            continue
        filename = str(row.get("filename") or "").strip()
        component = str(row.get("component") or "").strip()
        if filename and component:
            resolved[filename] = component
    return resolved


def _current_job_by_filename(wave_summary: dict[str, Any]) -> dict[str, str]:
    cohesion = wave_summary.get("cohesion_summary") or {}
    resolved: dict[str, str] = {}
    for row in list(cohesion.get("per_dll") or []):
        if not isinstance(row, dict):
            continue
        filename = str(row.get("filename") or "").strip()
        job_id = str(row.get("job_id") or "").strip()
        if filename and job_id:
            resolved[filename] = job_id
    return resolved


def _cohesion_row_by_filename(wave_summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cohesion = wave_summary.get("cohesion_summary") or {}
    resolved: dict[str, dict[str, Any]] = {}
    for row in list(cohesion.get("per_dll") or []):
        if not isinstance(row, dict):
            continue
        filename = str(row.get("filename") or "").strip()
        if filename:
            resolved[filename] = dict(row)
    return resolved


def _normalize_local_proof(proof: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(proof, dict):
        return {}
    preserved = [
        str(fn_name or "").strip()
        for fn_name in list(proof.get("preserved_lower_floor_functions") or [])
        if str(fn_name or "").strip()
    ]
    next_ceiling = [
        str(fn_name or "").strip()
        for fn_name in list(proof.get("next_ceiling_functions") or [])
        if str(fn_name or "").strip()
    ]
    observer_verdicts = dict(proof.get("observer_verdicts") or {})
    return {
        "proof_job_id": str(proof.get("proof_job_id") or "").strip(),
        "iteration_index": int(proof.get("iteration_index") or 0),
        "carryover_status": str(proof.get("carryover_status") or "").strip(),
        "status": str(proof.get("status") or "").strip(),
        "preserved_lower_floor_functions": preserved,
        "next_ceiling_functions": next_ceiling,
        "first_broken_handoff_group": str(
            observer_verdicts.get("first_broken_handoff_group")
            or proof.get("first_broken_handoff_group")
            or ""
        ).strip(),
    }


def build_package_frontier_plan(
    package_summary: dict[str, Any],
    *,
    local_proofs_by_filename: dict[str, dict[str, Any]] | None = None,
    max_iteration_cycles: int = 3,
) -> dict[str, Any]:
    regressions = list(package_summary.get("overlap_regression_summary") or [])
    current_jobs = _current_job_by_filename(package_summary)
    baseline_jobs = _baseline_job_by_filename(package_summary)
    components = _campaign_component_by_filename(package_summary)
    cohesion_rows = _cohesion_row_by_filename(package_summary)
    local_proofs = dict(local_proofs_by_filename or {})
    baseline_contract = extract_package_baseline_contract(package_summary)

    active_frontier_dlls = []
    entries: list[PackageFrontierEntry] = []
    for row in regressions:
        if not isinstance(row, dict):
            continue
        dll = str(row.get("dll") or "").strip()
        function_name = str(row.get("function") or "").strip()
        if not dll or not function_name:
            continue
        if dll not in active_frontier_dlls:
            active_frontier_dlls.append(dll)
        cluster_checkpoint_id = infer_cluster_checkpoint_id([function_name])
        cluster = CLUSTER_CHECKPOINTS_BY_ID.get(cluster_checkpoint_id)
        prerequisite_state_group_ids = tuple(
            getattr(cluster, "adjacent_prerequisite_state_groups", ()) or ()
        ) if cluster is not None else ()
        local_proof = _normalize_local_proof(local_proofs.get(dll))
        planner_reason = (
            str(row.get("likely_regression_cause") or "").strip()
            or str(row.get("follow_up_class") or "").strip()
            or "overlap_regression"
        )
        if local_proof.get("first_broken_handoff_group"):
            planner_reason = (
                f"{planner_reason}:first_broken_handoff="
                f"{local_proof['first_broken_handoff_group']}"
            )
        entries.append(
            PackageFrontierEntry(
                dll=dll,
                component=components.get(dll) or dll.rsplit(".", 1)[0],
                source_job_id=current_jobs.get(dll, ""),
                overlap_baseline_job_id=baseline_jobs.get(dll, ""),
                cluster_checkpoint_id=cluster_checkpoint_id,
                prerequisite_state_group_ids=prerequisite_state_group_ids,
                ceiling_functions=(function_name,),
                ceiling_origin_functions=(function_name,),
                focus_functions=(function_name,),
                iteration_mode="floor_to_ceiling",
                floor_scope="cluster",
                max_iteration_cycles=max(1, int(max_iteration_cycles or 1)),
                planner_reason=planner_reason,
                imported_dependency_classes=("business_object_continuity",),
                local_proof=local_proof,
            )
        )

    runtime_targets = [
        str(name or "").strip()
        for name in list(package_summary.get("runtime_targets") or [])
        if str(name or "").strip()
    ]
    imported_lower_floor_dlls = [
        dll for dll in runtime_targets
        if dll and dll not in active_frontier_dlls
    ]
    imported_lower_floor_rows = [
        {
            "dll": dll,
            "component": components.get(dll) or dll.rsplit(".", 1)[0],
            "source_job_id": current_jobs.get(dll, ""),
            "verified_count": int((cohesion_rows.get(dll) or {}).get("verified_count") or 0),
            "total_functions": int((cohesion_rows.get(dll) or {}).get("total_functions") or 0),
        }
        for dll in imported_lower_floor_dlls
    ]
    imported_prerequisite_groups = sorted(
        {
            group_id
            for entry in entries
            for group_id in entry.prerequisite_state_group_ids
            if group_id in PREREQUISITE_STATE_GROUPS_BY_ID
        }
    )
    return {
        "schema_version": PACKAGE_FRONTIER_PLAN_SCHEMA_VERSION,
        "planner_type": "package_frontier",
        "wave_id": str(package_summary.get("wave_id") or "").strip(),
        "campaign_id": str(package_summary.get("campaign_id") or "").strip(),
        "package_id": str(package_summary.get("package_id") or "").strip(),
        "package_label": str(package_summary.get("package_label") or "").strip(),
        "planner_status": "ready" if entries else "empty",
        "iteration_mode": "floor_to_ceiling",
        "floor_scope": "package",
        "package_floor": {
            "floor_scope": "package",
            "import_mode": "preserve_lower_floor_truth",
            "frontier_mode": "overlap_regression_frontier",
            "confirmation_gate": "package_confirmation_required",
            "comparison_gate": "baseline_contract_required_for_overlap_claims",
            "observer_contracts": (
                "package frontier planner",
                "campaign cohesion",
                "carryover observer",
                "business_object_continuity",
            ),
            "stop_conditions": (
                "ceiling_stagnated",
                "contradiction_growth",
                "reopened_preserved_truth",
                "package_confirmation_required",
            ),
        },
        "baseline_contract_present": bool(baseline_contract),
        "baseline_contract": baseline_contract,
        "imported_lower_floor_dlls": imported_lower_floor_dlls,
        "imported_lower_floor_rows": imported_lower_floor_rows,
        "active_frontier_dlls": active_frontier_dlls,
        "frontier_entry_count": len(entries),
        "imported_prerequisite_state_groups": imported_prerequisite_groups,
        "frontier_entries": [entry.to_dict() for entry in entries],
    }
