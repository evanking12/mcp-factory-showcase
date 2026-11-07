from __future__ import annotations

from typing import Any

from api.pipeline.core.decomposition_inspection_surface import build_decomposition_inspection_surface
from api.pipeline.core.dependency_class_inference import infer_dependency_classes
from api.pipeline.core.init_group_inference import infer_initialization_groups
from api.pipeline.core.interwoven_runtime_projection import build_interwoven_runtime_projection
from api.pipeline.core.package_frontier_slice_planner import build_package_frontier_slices
from api.pipeline.core.package_intake_shard_runner import build_package_intake_shards
from api.pipeline.core.shard_inventory_emitter import emit_shard_inventory_artifacts
from api.pipeline.core.shard_merge_coordinator import build_shard_merge_candidates
from api.pipeline.core.slice_execution_coordinator import build_slice_execution_map


DECOMPOSITION_CAMPAIGN_PLAN_SCHEMA_VERSION = "1.0.0"


def _normalize_package_input(
    package_input: dict[str, Any],
    package_frontier_plan: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(package_input or {})
    payload["package_id"] = str(
        payload.get("package_id")
        or package_frontier_plan.get("package_id")
        or ""
    ).strip()
    payload["package_label"] = str(
        payload.get("package_label")
        or package_frontier_plan.get("package_label")
        or payload.get("package_id")
        or ""
    ).strip()
    payload["graph_epoch"] = str(
        payload.get("graph_epoch")
        or package_frontier_plan.get("campaign_id")
        or package_frontier_plan.get("graph_epoch")
        or "decomposition-runtime"
    ).strip()
    payload["baseline_contract"] = dict(
        payload.get("baseline_contract")
        or package_frontier_plan.get("baseline_contract")
        or {}
    )

    dll_entries = list(payload.get("dll_entries") or [])
    if dll_entries:
        payload["dll_entries"] = dll_entries
        return payload

    runtime_targets = [
        str(name or "").strip()
        for name in list(
            payload.get("runtime_targets")
            or package_frontier_plan.get("runtime_targets")
            or []
        )
        if str(name or "").strip()
    ]
    payload["dll_entries"] = [
        {
            "dll_id": dll_name,
            "filename": dll_name,
        }
        for dll_name in runtime_targets
    ]
    return payload


def _find_shard_targets(shard_inventory: dict[str, Any], member_dlls: list[str]) -> list[int]:
    normalized = {str(name or "").strip() for name in member_dlls if str(name or "").strip()}
    targets: list[int] = []
    for index, row in enumerate(list(shard_inventory.get("shard_inventory_artifacts") or [])):
        if not isinstance(row, dict):
            continue
        shard_dlls = {
            str((entry or {}).get("filename") or (entry or {}).get("dll_id") or "").strip()
            for entry in list(row.get("dll_entries") or [])
            if isinstance(entry, dict)
        }
        if normalized & shard_dlls:
            targets.append(index)
    return targets


def _append_hint(
    hints_by_shard: dict[int, list[dict[str, Any]]],
    shard_indexes: list[int],
    hint: dict[str, Any],
) -> None:
    for index in shard_indexes:
        hints_by_shard.setdefault(index, []).append(dict(hint))


def _candidate_hints_from_package_frontier_plan(
    shard_inventory: dict[str, Any],
    package_frontier_plan: dict[str, Any],
) -> dict[int, list[dict[str, Any]]]:
    hints_by_shard: dict[int, list[dict[str, Any]]] = {}
    frontier_entries = [
        dict(row)
        for row in list(package_frontier_plan.get("frontier_entries") or [])
        if isinstance(row, dict)
    ]
    if not frontier_entries:
        frontier_entries = [
            {
                "dll": dll_name,
                "ceiling_functions": (),
                "prerequisite_state_group_ids": (),
                "imported_dependency_classes": (),
            }
            for dll_name in list(package_frontier_plan.get("active_frontier_dlls") or [])
            if str(dll_name or "").strip()
        ]

    for entry in frontier_entries:
        dll_name = str(entry.get("dll") or "").strip()
        if not dll_name:
            continue
        _append_hint(
            hints_by_shard,
            _find_shard_targets(shard_inventory, [dll_name]),
            {
                "hint_type": "frontier",
                "key": f"frontier::{dll_name}",
                "label": str(entry.get("component") or dll_name).strip(),
                "member_dlls": [dll_name],
            },
        )

    group_members: dict[str, dict[str, Any]] = {}
    for entry in frontier_entries:
        dll_name = str(entry.get("dll") or "").strip()
        for group_id in list(entry.get("prerequisite_state_group_ids") or []):
            normalized_group_id = str(group_id or "").strip()
            if not normalized_group_id or not dll_name:
                continue
            group_row = group_members.setdefault(
                normalized_group_id,
                {
                    "member_dlls": [],
                    "member_functions": [],
                    "likely_downstream_consumers": [],
                },
            )
            if dll_name not in group_row["member_dlls"]:
                group_row["member_dlls"].append(dll_name)
            for fn_name in list(entry.get("ceiling_functions") or []):
                normalized_fn = str(fn_name or "").strip()
                if normalized_fn and normalized_fn not in group_row["member_functions"]:
                    group_row["member_functions"].append(normalized_fn)
                if normalized_fn and normalized_fn not in group_row["likely_downstream_consumers"]:
                    group_row["likely_downstream_consumers"].append(normalized_fn)

    for group_id, group_row in group_members.items():
        _append_hint(
            hints_by_shard,
            _find_shard_targets(shard_inventory, group_row["member_dlls"]),
            {
                "hint_type": "init_group",
                "key": group_id,
                "label": group_id,
                "member_dlls": list(group_row["member_dlls"]),
                "member_functions": list(group_row["member_functions"]),
                "exported_state_artifacts": [group_id],
                "likely_downstream_consumers": list(group_row["likely_downstream_consumers"]),
            },
        )

    dependency_members: dict[str, dict[str, Any]] = {}
    for entry in frontier_entries:
        dll_name = str(entry.get("dll") or "").strip()
        for class_id in list(entry.get("imported_dependency_classes") or []):
            normalized_class_id = str(class_id or "").strip()
            if not normalized_class_id or not dll_name:
                continue
            class_row = dependency_members.setdefault(
                normalized_class_id,
                {
                    "member_dlls": [],
                    "member_clusters": [],
                    "member_init_groups": [],
                    "evidence_edges": [],
                },
            )
            if dll_name not in class_row["member_dlls"]:
                class_row["member_dlls"].append(dll_name)
            cluster_id = str(entry.get("cluster_checkpoint_id") or "").strip()
            if cluster_id and cluster_id not in class_row["member_clusters"]:
                class_row["member_clusters"].append(cluster_id)
            for group_id in list(entry.get("prerequisite_state_group_ids") or []):
                normalized_group_id = str(group_id or "").strip()
                if normalized_group_id and normalized_group_id not in class_row["member_init_groups"]:
                    class_row["member_init_groups"].append(normalized_group_id)
            for fn_name in list(entry.get("ceiling_functions") or []):
                normalized_fn = str(fn_name or "").strip()
                if normalized_fn:
                    edge = f"{dll_name}:{normalized_fn}"
                    if edge not in class_row["evidence_edges"]:
                        class_row["evidence_edges"].append(edge)

    for class_id, class_row in dependency_members.items():
        _append_hint(
            hints_by_shard,
            _find_shard_targets(shard_inventory, class_row["member_dlls"]),
            {
                "hint_type": "dependency_class",
                "key": class_id,
                "label": class_id,
                "member_dlls": list(class_row["member_dlls"]),
                "member_clusters": list(class_row["member_clusters"]),
                "member_init_groups": list(class_row["member_init_groups"]),
                "evidence_edges": list(class_row["evidence_edges"]) or [class_id],
                "dependency_kind": class_id,
            },
        )
    return hints_by_shard


def _apply_candidate_hints(
    shard_inventory: dict[str, Any],
    candidate_hints_by_shard: dict[int, list[dict[str, Any]]],
) -> None:
    for index, row in enumerate(list(shard_inventory.get("shard_inventory_artifacts") or [])):
        if not isinstance(row, dict):
            continue
        hints = list(candidate_hints_by_shard.get(index) or [])
        if hints:
            row["candidate_hints"] = [dict(item) for item in hints if isinstance(item, dict)]


def build_decomposition_campaign_plan(
    package_input: dict[str, Any],
    package_frontier_plan: dict[str, Any],
    *,
    target_shard_width: int = 2,
    max_slice_dlls: int = 3,
    interwoven_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_input = _normalize_package_input(package_input, package_frontier_plan)
    shard_plan = build_package_intake_shards(
        normalized_input,
        target_shard_width=target_shard_width,
        graph_epoch=str(normalized_input.get("graph_epoch") or "").strip(),
    )
    shard_inventory = emit_shard_inventory_artifacts(shard_plan)
    candidate_hints = _candidate_hints_from_package_frontier_plan(shard_inventory, package_frontier_plan)
    _apply_candidate_hints(shard_inventory, candidate_hints)
    merge_output = build_shard_merge_candidates(shard_inventory)
    init_group_output = infer_initialization_groups(merge_output)
    dependency_class_output = infer_dependency_classes(
        merge_output,
        init_group_output=init_group_output,
    )
    interwoven_projection = build_interwoven_runtime_projection(interwoven_context)
    frontier_slice_plan = build_package_frontier_slices(
        normalized_input,
        merge_output,
        init_group_output,
        dependency_class_output,
        max_slice_dlls=max_slice_dlls,
        interwoven_projection=interwoven_projection,
    )
    execution_map = build_slice_execution_map(frontier_slice_plan)
    inspection_surface = build_decomposition_inspection_surface(
        shard_plan=shard_plan,
        shard_inventory=shard_inventory,
        merge_output=merge_output,
        init_group_output=init_group_output,
        dependency_class_output=dependency_class_output,
        frontier_slice_plan=frontier_slice_plan,
        execution_map=execution_map,
    )

    per_dll_runtime_settings: dict[str, dict[str, Any]] = {}
    for unit in list(execution_map.get("execution_units") or []):
        if not isinstance(unit, dict):
            continue
        dll_name = str(unit.get("target_dll") or "").strip()
        if not dll_name:
            continue
        per_dll_runtime_settings[dll_name] = {
            **dict(unit.get("runtime_overrides") or {}),
            "source_frontier_slice_id": str(unit.get("source_frontier_slice_id") or "").strip(),
            "decomposition_execution_unit_id": str(unit.get("execution_unit_id") or "").strip(),
            "required_dependency_class_ids": list(unit.get("related_dependency_class_ids") or []),
            "protected_imported_truth_ids": list(unit.get("protected_imported_truth_ids") or []),
            "interwoven_subject_ids": list(unit.get("interwoven_subject_ids") or []),
            "interwoven_contradiction_summary": dict(unit.get("interwoven_contradiction_summary") or {}),
            "interwoven_attribution_present": bool(unit.get("interwoven_attribution_present")),
        }

    dashboard = dict(inspection_surface.get("decomposition_dashboard") or {})
    active_frontier_slice_ids = list(dashboard.get("active_slice_ids") or [])
    execution_target_names = {
        str(unit.get("target_dll") or "").strip()
        for unit in list(execution_map.get("execution_units") or [])
        if str(unit.get("target_dll") or "").strip()
    }
    preferred_frontier_dlls = [
        str(name or "").strip()
        for name in list(package_frontier_plan.get("active_frontier_dlls") or [])
        if str(name or "").strip()
    ]
    active_dll_targets = [
        dll_name
        for dll_name in preferred_frontier_dlls
        if dll_name in execution_target_names
    ]
    if not active_dll_targets:
        active_dll_targets = sorted(execution_target_names)

    return {
        "schema_version": DECOMPOSITION_CAMPAIGN_PLAN_SCHEMA_VERSION,
        "planner_type": "decomposition_campaign_bridge",
        "package_id": str(normalized_input.get("package_id") or "").strip(),
        "package_label": str(normalized_input.get("package_label") or "").strip(),
        "graph_epoch": str(normalized_input.get("graph_epoch") or "").strip(),
        "package_floor": dict(package_frontier_plan.get("package_floor") or {}),
        "baseline_contract": dict(package_frontier_plan.get("baseline_contract") or {}),
        "package_frontier_plan": dict(package_frontier_plan),
        "active_frontier_dlls": list(package_frontier_plan.get("active_frontier_dlls") or []),
        "imported_lower_floor_dlls": list(package_frontier_plan.get("imported_lower_floor_dlls") or []),
        "imported_lower_floor_rows": list(package_frontier_plan.get("imported_lower_floor_rows") or []),
        "active_frontier_slice_ids": active_frontier_slice_ids,
        "imported_to_active_ratio": dashboard.get("imported_to_active_ratio", 0.0),
        "deferred_initialization_group_ids": list(frontier_slice_plan.get("deferred_initialization_group_ids") or []),
        "deferred_dependency_class_ids": list(frontier_slice_plan.get("deferred_dependency_class_ids") or []),
        "interwoven_artifact_presence": bool(interwoven_projection.get("interwoven_artifact_presence")),
        "interwoven_subject_ids": list(interwoven_projection.get("interwoven_subject_ids") or []),
        "interwoven_contradiction_summary": dict(interwoven_projection.get("interwoven_contradiction_summary") or {}),
        "interwoven_attribution_present": bool(interwoven_projection.get("interwoven_attribution_present")),
        "active_dll_targets": active_dll_targets,
        "per_dll_runtime_settings": per_dll_runtime_settings,
        "slice_execution_attribution_present": bool(execution_map.get("execution_units")),
        "shard_plan": shard_plan,
        "shard_inventory": shard_inventory,
        "merge_output": merge_output,
        "init_group_output": init_group_output,
        "dependency_class_output": dependency_class_output,
        "interwoven_projection": interwoven_projection,
        "frontier_slice_plan": frontier_slice_plan,
        "execution_map": execution_map,
        "inspection_surface": inspection_surface,
    }
