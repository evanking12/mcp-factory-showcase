from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


DEPENDENCY_CLASS_INFERENCE_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class DependencyClassObserverResult:
    observer_name: str
    object_id: str
    status: str
    evidence_edges_explicit: bool
    bounded_group: bool
    distinct_from_init_groups: bool
    distinct_from_clusters: bool
    contradiction_state: str
    warnings: tuple[str, ...] = ()
    schema_version: str = DEPENDENCY_CLASS_INFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if str(self.observer_name or "").strip() != "dependency_class_plausibility":
            raise ValueError("observer_name must be dependency_class_plausibility")
        normalized_status = str(self.status or "").strip().lower()
        if normalized_status not in {"pass", "warn", "fail"}:
            raise ValueError("observer status must be pass, warn, or fail")
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(self, "contradiction_state", str(self.contradiction_state or "").strip() or "none")
        object.__setattr__(
            self,
            "warnings",
            tuple(str(warning or "").strip() for warning in tuple(self.warnings or ()) if str(warning or "").strip()),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_str_tuple(values: Any) -> tuple[str, ...]:
    return tuple(
        str(value or "").strip()
        for value in list(values or [])
        if str(value or "").strip()
    )


def infer_dependency_classes(
    merge_output: dict[str, Any],
    *,
    init_group_output: dict[str, Any] | None = None,
    max_member_dlls: int = 6,
) -> dict[str, Any]:
    package_id = str(merge_output.get("package_id") or "").strip()
    graph_epoch = str(merge_output.get("graph_epoch") or "").strip()
    rows = [
        dict(row)
        for row in list(merge_output.get("candidate_dependency_classes") or [])
        if isinstance(row, dict)
    ]
    init_groups = [
        dict(row)
        for row in list((init_group_output or {}).get("initialization_groups") or [])
        if isinstance(row, dict)
    ]
    init_group_sets: dict[frozenset[str], list[str]] = {}
    for group in init_groups:
        members = frozenset(_normalize_str_tuple(group.get("member_dlls")))
        if not members:
            continue
        group_id = str(group.get("group_id") or "").strip()
        if group_id:
            init_group_sets.setdefault(members, []).append(group_id)

    artifacts: list[dict[str, Any]] = []
    observers: list[dict[str, Any]] = []
    cross_dll_class_count = 0
    oversized_class_count = 0
    collapsed_init_group_count = 0
    collapsed_cluster_count = 0

    for row in rows:
        lifecycle = dict(row.get("lifecycle") or {})
        details = dict(row.get("details") or {})
        member_dlls = _normalize_str_tuple(row.get("member_dlls"))
        member_clusters = _normalize_str_tuple(details.get("member_clusters"))
        member_init_groups = _normalize_str_tuple(details.get("member_init_groups"))
        evidence_edges = _normalize_str_tuple(details.get("evidence_edges"))
        member_functions = _normalize_str_tuple(details.get("member_functions"))
        dependency_kind = str(details.get("dependency_kind") or row.get("key") or "").strip()
        contradiction_state = str(lifecycle.get("contradiction_state") or "none").strip() or "none"
        if len(member_dlls) > 1:
            cross_dll_class_count += 1
        bounded_group = 0 < len(member_dlls) <= max_member_dlls
        if not bounded_group:
            oversized_class_count += 1

        matching_init_group_ids = tuple(
            init_group_sets.get(frozenset(member_dlls), [])
        )
        distinct_from_init_groups = not matching_init_group_ids or bool(member_init_groups) or bool(evidence_edges)
        distinct_from_clusters = len(member_dlls) > 1 or len(member_clusters) > 1 or bool(evidence_edges)

        status = "pass"
        warnings: list[str] = []
        if contradiction_state in {"contradicted", "blocked"}:
            status = "fail"
            warnings.append("contradiction_state_blocks_class")
        elif not bounded_group:
            status = "fail"
            warnings.append("oversized_dependency_class")
        elif not distinct_from_init_groups:
            status = "fail"
            warnings.append("collapses_into_init_group")
            collapsed_init_group_count += 1
        elif not distinct_from_clusters:
            status = "fail"
            warnings.append("collapses_into_cluster")
            collapsed_cluster_count += 1
        elif not evidence_edges:
            status = "warn"
            warnings.append("missing_dependency_edges")

        observer = DependencyClassObserverResult(
            observer_name="dependency_class_plausibility",
            object_id=str(lifecycle.get("id") or "").strip(),
            status=status,
            evidence_edges_explicit=bool(evidence_edges),
            bounded_group=bounded_group,
            distinct_from_init_groups=distinct_from_init_groups,
            distinct_from_clusters=distinct_from_clusters,
            contradiction_state=contradiction_state,
            warnings=tuple(warnings),
        ).to_dict()
        observers.append(observer)
        artifacts.append(
            {
                "class_id": str(lifecycle.get("id") or "").strip(),
                "package_id": package_id,
                "graph_epoch": graph_epoch,
                "dependency_kind": dependency_kind,
                "member_dlls": member_dlls,
                "member_clusters": member_clusters,
                "member_init_groups": member_init_groups,
                "matching_init_group_ids": matching_init_group_ids,
                "member_functions": member_functions,
                "evidence_edges": evidence_edges,
                "confidence": row.get("confidence_score", 0.0),
                "contradiction_state": contradiction_state if bounded_group else "blocked",
                "observer_summary": observer,
                "lifecycle": lifecycle,
                "schema_version": DEPENDENCY_CLASS_INFERENCE_SCHEMA_VERSION,
            }
        )

    return {
        "schema_version": DEPENDENCY_CLASS_INFERENCE_SCHEMA_VERSION,
        "package_id": package_id,
        "graph_epoch": graph_epoch,
        "dependency_classes": artifacts,
        "dependency_class_observer_summaries": observers,
        "cross_dll_class_count": cross_dll_class_count,
        "oversized_class_count": oversized_class_count,
        "collapsed_init_group_count": collapsed_init_group_count,
        "collapsed_cluster_count": collapsed_cluster_count,
    }
