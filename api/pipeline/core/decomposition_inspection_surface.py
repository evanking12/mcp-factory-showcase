from __future__ import annotations

from collections import Counter
from typing import Any

from api.pipeline.core.decomposition_contract import DEFAULT_DECOMPOSITION_RETENTION_POLICY


DECOMPOSITION_INSPECTION_SCHEMA_VERSION = "1.0.0"


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status:
            counts[status] += 1
    return dict(counts)


def _ratio(imported_count: int, active_count: int) -> float:
    if active_count <= 0:
        return 0.0
    return round(float(imported_count) / float(active_count), 2)


def build_decomposition_inspection_surface(
    *,
    shard_plan: dict[str, Any],
    shard_inventory: dict[str, Any],
    merge_output: dict[str, Any],
    init_group_output: dict[str, Any],
    dependency_class_output: dict[str, Any],
    frontier_slice_plan: dict[str, Any],
    execution_map: dict[str, Any],
) -> dict[str, Any]:
    package_id = str(
        frontier_slice_plan.get("package_id")
        or dependency_class_output.get("package_id")
        or init_group_output.get("package_id")
        or merge_output.get("package_id")
        or shard_plan.get("package_id")
        or ""
    ).strip()
    graph_epoch = str(
        frontier_slice_plan.get("graph_epoch")
        or dependency_class_output.get("graph_epoch")
        or init_group_output.get("graph_epoch")
        or merge_output.get("graph_epoch")
        or shard_plan.get("graph_epoch")
        or ""
    ).strip()

    shard_rows = list(shard_plan.get("shards") or [])
    shard_observers = list(shard_inventory.get("shard_observer_summaries") or [])
    merge_observers = list(merge_output.get("merge_observer_summaries") or [])
    init_observers = list(init_group_output.get("init_group_observer_summaries") or [])
    dependency_observers = list(dependency_class_output.get("dependency_class_observer_summaries") or [])
    slice_observers = list(frontier_slice_plan.get("frontier_slice_observer_summaries") or [])
    execution_observers = list(execution_map.get("coordinator_observer_summaries") or [])
    frontier_slices = list(frontier_slice_plan.get("frontier_slices") or [])
    execution_units = list(execution_map.get("execution_units") or [])

    contradiction_hotspots: list[dict[str, Any]] = []
    for row in list(merge_output.get("merge_contradiction_registry") or []):
        if not isinstance(row, dict):
            continue
        contradiction_hotspots.append(
            {
                "source": "merge_contradiction_registry",
                "object_id": str(row.get("key") or "").strip(),
                "status": "warn",
                "reason": str(row.get("reason") or "").strip(),
            }
        )
    for source_name, rows, id_field in (
        ("init_group_observer_summaries", init_observers, "object_id"),
        ("dependency_class_observer_summaries", dependency_observers, "object_id"),
        ("frontier_slice_observer_summaries", slice_observers, "object_id"),
        ("coordinator_observer_summaries", execution_observers, "execution_unit_id"),
    ):
        for row in rows:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "").strip().lower()
            if status == "pass":
                continue
            contradiction_hotspots.append(
                {
                    "source": source_name,
                    "object_id": str(row.get(id_field) or "").strip(),
                    "status": status,
                    "reason": ", ".join(str(item) for item in list(row.get("warnings") or []) if str(item).strip()),
                }
            )

    execution_units_by_slice: dict[str, list[str]] = {}
    for unit in execution_units:
        if not isinstance(unit, dict):
            continue
        slice_id = str(unit.get("source_frontier_slice_id") or "").strip()
        unit_id = str(unit.get("execution_unit_id") or "").strip()
        if slice_id and unit_id:
            execution_units_by_slice.setdefault(slice_id, []).append(unit_id)

    slice_inspection_rows: list[dict[str, Any]] = []
    active_slice_ids: list[str] = []
    imported_truth_ids = tuple(frontier_slice_plan.get("imported_lower_floor_dlls") or ())
    for row in frontier_slices:
        if not isinstance(row, dict):
            continue
        lifecycle = dict(row.get("lifecycle") or {})
        slice_id = str(lifecycle.get("id") or "").strip()
        if slice_id:
            active_slice_ids.append(slice_id)
        slice_inspection_rows.append(
            {
                "slice_id": slice_id,
                "label": str(row.get("label") or slice_id).strip(),
                "active_dlls": tuple(row.get("active_dlls") or ()),
                "imported_lower_floor_dlls": tuple(row.get("imported_lower_floor_dlls") or ()),
                "required_initialization_group_ids": tuple(row.get("required_initialization_group_ids") or ()),
                "related_dependency_class_ids": tuple(row.get("related_dependency_class_ids") or ()),
                "execution_unit_ids": tuple(execution_units_by_slice.get(slice_id, [])),
                "observer_status": str(dict(row.get("observer_summary") or {}).get("status") or "").strip(),
                "canonical_source": "frontier_slices",
            }
        )

    total_shard_width = sum(
        int(dict(row.get("economics") or {}).get("actual_shard_width") or 0)
        for row in shard_rows
        if isinstance(row, dict)
    )
    shard_budget_breach_count = sum(
        1
        for row in shard_rows
        if isinstance(row, dict) and bool(dict(row.get("economics") or {}).get("budget_breached"))
    )
    active_dll_count = len(
        {
            dll_name
            for row in frontier_slices
            if isinstance(row, dict)
            for dll_name in list(row.get("active_dlls") or [])
            if str(dll_name).strip()
        }
    )
    dashboard = {
        "package_id": package_id,
        "graph_epoch": graph_epoch,
        "shard_count": len(shard_rows),
        "merge_result_counts": {
            "cluster_candidates": len(list(merge_output.get("candidate_clusters") or [])),
            "initialization_groups": len(list(init_group_output.get("initialization_groups") or [])),
            "dependency_classes": len(list(dependency_class_output.get("dependency_classes") or [])),
            "frontier_slices": len(frontier_slices),
            "execution_units": len(execution_units),
        },
        "active_slice_ids": tuple(active_slice_ids),
        "imported_truth_ids": imported_truth_ids,
        "imported_to_active_ratio": _ratio(len(imported_truth_ids), active_dll_count),
        "economics_summary": {
            "average_shard_width": round(total_shard_width / len(shard_rows), 2) if shard_rows else 0.0,
            "shard_budget_breach_count": shard_budget_breach_count,
            "active_dll_count": active_dll_count,
        },
        "observer_verdict_summary": {
            "shard_validity": _status_counts(shard_observers),
            "merge_coherence": _status_counts(merge_observers),
            "initialization_group_plausibility": _status_counts(init_observers),
            "dependency_class_plausibility": _status_counts(dependency_observers),
            "frontier_slice_boundedness": _status_counts(slice_observers),
            "slice_execution_coordination": _status_counts(execution_observers),
        },
        "contradiction_hotspot_count": len(contradiction_hotspots),
        "canonical_sources": {
            "shard_plan": "shards",
            "shard_inventory": "shard_inventory_artifacts",
            "merge_output": "candidate_clusters,candidate_initialization_groups,candidate_dependency_classes,initial_frontier_candidates",
            "init_group_output": "initialization_groups",
            "dependency_class_output": "dependency_classes",
            "frontier_slice_plan": "frontier_slices",
            "execution_map": "execution_units",
        },
        "retention_class": DEFAULT_DECOMPOSITION_RETENTION_POLICY.classify_artifact("decomposition_dashboard"),
        "schema_version": DECOMPOSITION_INSPECTION_SCHEMA_VERSION,
    }

    merge_ambiguity_report = {
        "package_id": package_id,
        "graph_epoch": graph_epoch,
        "ambiguity_hotspots": tuple(contradiction_hotspots),
        "canonical_sources": (
            "merge_contradiction_registry",
            "init_group_observer_summaries",
            "dependency_class_observer_summaries",
            "frontier_slice_observer_summaries",
            "coordinator_observer_summaries",
        ),
        "retention_class": DEFAULT_DECOMPOSITION_RETENTION_POLICY.classify_artifact("merge_ambiguity_report"),
        "schema_version": DECOMPOSITION_INSPECTION_SCHEMA_VERSION,
    }
    slice_inspection_report = {
        "package_id": package_id,
        "graph_epoch": graph_epoch,
        "active_slice_rows": tuple(slice_inspection_rows),
        "canonical_source": "frontier_slices+execution_units",
        "retention_class": DEFAULT_DECOMPOSITION_RETENTION_POLICY.classify_artifact("slice_inspection_report"),
        "schema_version": DECOMPOSITION_INSPECTION_SCHEMA_VERSION,
    }
    return {
        "schema_version": DECOMPOSITION_INSPECTION_SCHEMA_VERSION,
        "package_id": package_id,
        "graph_epoch": graph_epoch,
        "decomposition_dashboard": dashboard,
        "merge_ambiguity_report": merge_ambiguity_report,
        "slice_inspection_report": slice_inspection_report,
        "retention_boundaries": {
            "decomposition_dashboard": DEFAULT_DECOMPOSITION_RETENTION_POLICY.classify_artifact("decomposition_dashboard"),
            "merge_ambiguity_report": DEFAULT_DECOMPOSITION_RETENTION_POLICY.classify_artifact("merge_ambiguity_report"),
            "slice_inspection_report": DEFAULT_DECOMPOSITION_RETENTION_POLICY.classify_artifact("slice_inspection_report"),
            "candidate_clusters": DEFAULT_DECOMPOSITION_RETENTION_POLICY.classify_artifact("candidate_clusters"),
            "frontier_slices": DEFAULT_DECOMPOSITION_RETENTION_POLICY.classify_artifact("frontier_slices"),
        },
    }
