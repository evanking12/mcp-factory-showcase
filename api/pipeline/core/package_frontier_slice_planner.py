from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from api.pipeline.core.decomposition_contract import (
    DecompositionLifecycle,
    build_frontier_slice_boundedness_observer,
)
from api.pipeline.core.interwoven_runtime_projection import project_interwoven_for_dlls


PACKAGE_FRONTIER_SLICE_SCHEMA_VERSION = "1.0.0"


def _normalize_str_tuple(values: Any) -> tuple[str, ...]:
    return tuple(
        str(value or "").strip()
        for value in list(values or [])
        if str(value or "").strip()
    )


def _all_package_dlls(package_input: dict[str, Any]) -> tuple[str, ...]:
    dll_entries = list(package_input.get("dll_entries") or [])
    runtime_targets = list(package_input.get("runtime_targets") or [])
    dll_names = {
        str(row.get("filename") or row.get("dll_id") or "").strip()
        for row in dll_entries
        if isinstance(row, dict)
    }
    dll_names.update(str(name or "").strip() for name in runtime_targets if str(name or "").strip())
    return tuple(sorted(name for name in dll_names if name))


def _group_status_index(rows: list[dict[str, Any]], key_field: str) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        object_id = str(row.get(key_field) or row.get("object_id") or "").strip()
        if not object_id:
            continue
        observer = dict(row.get("observer_summary") or {})
        status = str(observer.get("status") or row.get("status") or "").strip().lower()
        resolved[object_id] = status or "warn"
    return resolved


def _index_init_groups(init_group_output: dict[str, Any]) -> list[dict[str, Any]]:
    indexed: list[dict[str, Any]] = []
    for row in list(init_group_output.get("initialization_groups") or []):
        if not isinstance(row, dict):
            continue
        indexed.append(
            {
                "group_id": str(row.get("group_id") or "").strip(),
                "member_dlls": _normalize_str_tuple(row.get("member_dlls")),
                "status": str(dict(row.get("observer_summary") or {}).get("status") or "warn").strip().lower(),
            }
        )
    return indexed


def _index_dependency_classes(dependency_class_output: dict[str, Any]) -> list[dict[str, Any]]:
    indexed: list[dict[str, Any]] = []
    for row in list(dependency_class_output.get("dependency_classes") or []):
        if not isinstance(row, dict):
            continue
        indexed.append(
            {
                "class_id": str(row.get("class_id") or "").strip(),
                "member_dlls": _normalize_str_tuple(row.get("member_dlls")),
                "status": str(dict(row.get("observer_summary") or {}).get("status") or "warn").strip().lower(),
            }
        )
    return indexed


@dataclass(frozen=True)
class FrontierSliceArtifact:
    lifecycle: DecompositionLifecycle
    label: str
    imported_lower_floor_dlls: tuple[str, ...]
    active_dlls: tuple[str, ...]
    active_frontier_ids: tuple[str, ...]
    required_cluster_ids: tuple[str, ...]
    required_initialization_group_ids: tuple[str, ...]
    related_dependency_class_ids: tuple[str, ...]
    deferred_initialization_group_ids: tuple[str, ...]
    deferred_dependency_class_ids: tuple[str, ...]
    interwoven_subject_ids: tuple[str, ...]
    interwoven_contradiction_summary: dict[str, Any]
    interwoven_attribution_present: bool
    economics: dict[str, Any]
    observer_summary: dict[str, Any]
    schema_version: str = PACKAGE_FRONTIER_SLICE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["lifecycle"] = self.lifecycle.to_dict()
        return payload


def build_package_frontier_slices(
    package_input: dict[str, Any],
    merge_output: dict[str, Any],
    init_group_output: dict[str, Any],
    dependency_class_output: dict[str, Any],
    *,
    max_slice_dlls: int = 3,
    interwoven_projection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package_id = str(package_input.get("package_id") or merge_output.get("package_id") or "").strip()
    package_label = str(package_input.get("package_label") or "").strip()
    graph_epoch = str(
        package_input.get("graph_epoch")
        or merge_output.get("graph_epoch")
        or init_group_output.get("graph_epoch")
        or dependency_class_output.get("graph_epoch")
        or ""
    ).strip()
    all_dlls = _all_package_dlls(package_input)
    cluster_index = {
        str(dict(row.get("lifecycle") or {}).get("id") or "").strip(): row
        for row in list(merge_output.get("candidate_clusters") or [])
        if isinstance(row, dict)
    }
    clusters_by_dll = {
        str(row.get("key") or "").strip(): cluster_id
        for cluster_id, row in cluster_index.items()
        if str(row.get("key") or "").strip()
    }
    init_groups = _index_init_groups(init_group_output)
    dependency_classes = _index_dependency_classes(dependency_class_output)
    frontier_candidates = [
        dict(row)
        for row in list(merge_output.get("initial_frontier_candidates") or [])
        if isinstance(row, dict)
    ]

    artifacts: list[dict[str, Any]] = []
    observers: list[dict[str, Any]] = []
    active_dll_union: set[str] = set()
    deferred_init_group_ids: set[str] = set()
    deferred_dependency_class_ids: set[str] = set()

    for candidate in frontier_candidates:
        lifecycle = DecompositionLifecycle.from_dict(dict(candidate.get("lifecycle") or {}))
        seed_active_dlls = list(_normalize_str_tuple(candidate.get("member_dlls")))
        active_dlls = list(seed_active_dlls)
        required_init_groups: list[str] = []
        related_dependency_classes: list[str] = []
        local_deferred_init_groups: list[str] = []
        local_deferred_dependency_classes: list[str] = []
        warnings: list[str] = []
        contradiction_state = lifecycle.contradiction_state

        overlapping_init_groups = [
            row
            for row in init_groups
            if set(row["member_dlls"]).intersection(active_dlls) and row["status"] != "fail"
        ]
        for group in overlapping_init_groups:
            expanded = sorted(set(active_dlls).union(group["member_dlls"]))
            if len(expanded) <= max_slice_dlls:
                active_dlls = expanded
                required_init_groups.append(group["group_id"])
                if group["status"] == "warn":
                    contradiction_state = "tentative"
                    warnings.append("tentative_init_group_support")
            else:
                local_deferred_init_groups.append(group["group_id"])
                deferred_init_group_ids.add(group["group_id"])

        overlapping_dependency_classes = [
            row
            for row in dependency_classes
            if set(row["member_dlls"]).intersection(active_dlls) and row["status"] != "fail"
        ]
        for dep_class in overlapping_dependency_classes:
            expanded = sorted(set(active_dlls).union(dep_class["member_dlls"]))
            if len(expanded) <= max_slice_dlls:
                active_dlls = expanded
                related_dependency_classes.append(dep_class["class_id"])
                if dep_class["status"] == "warn":
                    contradiction_state = "tentative"
                    warnings.append("tentative_dependency_class_support")
            else:
                local_deferred_dependency_classes.append(dep_class["class_id"])
                deferred_dependency_class_ids.add(dep_class["class_id"])

        required_cluster_ids = tuple(
            cluster_id
            for dll_name in sorted(set(active_dlls))
            if (cluster_id := clusters_by_dll.get(dll_name))
        )
        imported_lower_floor_dlls = tuple(
            dll_name
            for dll_name in all_dlls
            if dll_name not in set(active_dlls)
        )
        interwoven_summary = project_interwoven_for_dlls(
            interwoven_projection,
            dll_names=active_dlls,
        )
        status = "pass"
        if not active_dlls:
            status = "fail"
            warnings.append("empty_slice")
        elif len(active_dlls) > max_slice_dlls:
            status = "fail"
            warnings.append("oversized_slice")
        elif local_deferred_init_groups or local_deferred_dependency_classes:
            status = "warn"
            warnings.append("bounded_expansion_deferred")
        elif not required_cluster_ids:
            status = "warn"
            warnings.append("missing_cluster_bindings")

        observer = build_frontier_slice_boundedness_observer(
            object_id=lifecycle.id,
            status=status,
            imported_truth_explicit=True,
            active_work_explicit=bool(active_dlls),
            slice_width=len(active_dlls),
            dll_count=len(active_dlls),
            cluster_count=len(required_cluster_ids),
            init_group_count=len(required_init_groups),
            reopened_imported_truth=bool(set(active_dlls).intersection(imported_lower_floor_dlls)),
            warnings=tuple(warnings),
        )
        observers.append(observer)
        active_dll_union.update(active_dlls)
        artifacts.append(
            FrontierSliceArtifact(
                lifecycle=DecompositionLifecycle(
                    id=lifecycle.id,
                    object_type="frontier_slice",
                    package_id=package_id,
                    graph_epoch=graph_epoch or lifecycle.graph_epoch,
                    source_ids=tuple(
                        source_id
                        for source_id in tuple(lifecycle.source_ids)
                        + tuple(required_init_groups)
                        + tuple(related_dependency_classes)
                        if source_id
                    ),
                    contradiction_state=contradiction_state,
                ),
                label=str(candidate.get("label") or candidate.get("key") or lifecycle.id).strip(),
                imported_lower_floor_dlls=imported_lower_floor_dlls,
                active_dlls=tuple(active_dlls),
                active_frontier_ids=(lifecycle.id,),
                required_cluster_ids=required_cluster_ids,
                required_initialization_group_ids=tuple(required_init_groups),
                related_dependency_class_ids=tuple(related_dependency_classes),
                deferred_initialization_group_ids=tuple(local_deferred_init_groups),
                deferred_dependency_class_ids=tuple(local_deferred_dependency_classes),
                interwoven_subject_ids=tuple(interwoven_summary.get("interwoven_subject_ids") or ()),
                interwoven_contradiction_summary=dict(interwoven_summary.get("interwoven_contradiction_summary") or {}),
                interwoven_attribution_present=bool(interwoven_summary.get("interwoven_attribution_present")),
                economics={
                    "target_max_dlls": int(max_slice_dlls),
                    "planned_dll_count": len(active_dlls),
                    "bounded": len(active_dlls) <= max_slice_dlls,
                },
                observer_summary=observer,
            ).to_dict()
        )

    imported_lower_floor_dlls = tuple(
        dll_name for dll_name in all_dlls if dll_name not in active_dll_union
    )
    imported_lower_floor_rows = [
        {
            "dll": dll_name,
            "component": dll_name.rsplit(".", 1)[0],
        }
        for dll_name in imported_lower_floor_dlls
    ]
    return {
        "schema_version": PACKAGE_FRONTIER_SLICE_SCHEMA_VERSION,
        "planner_type": "package_frontier_slice",
        "package_id": package_id,
        "package_label": package_label,
        "graph_epoch": graph_epoch,
        "imported_lower_floor_dlls": imported_lower_floor_dlls,
        "imported_lower_floor_rows": imported_lower_floor_rows,
        "frontier_slice_count": len(artifacts),
        "frontier_slices": artifacts,
        "frontier_slice_observer_summaries": observers,
        "deferred_initialization_group_ids": tuple(sorted(deferred_init_group_ids)),
        "deferred_dependency_class_ids": tuple(sorted(deferred_dependency_class_ids)),
    }
