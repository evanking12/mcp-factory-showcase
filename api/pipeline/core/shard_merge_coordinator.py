from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from api.pipeline.core.decomposition_contract import DecompositionLifecycle, build_decomposition_object_id


SHARD_MERGE_SCHEMA_VERSION = "1.0.0"


def _stable_hash(parts: list[str]) -> str:
    digest = hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


def _normalize_dll_name(row: dict[str, Any]) -> str:
    return str(row.get("filename") or row.get("dll_id") or "").strip()


def _collect_detail_values(rows: list[dict[str, Any]], field: str) -> list[str]:
    return sorted(
        {
            str(member or "").strip()
            for row in rows
            for member in list(row.get(field) or [])
            if str(member or "").strip()
        }
    )


@dataclass(frozen=True)
class MergeCandidate:
    lifecycle: DecompositionLifecycle
    candidate_type: str
    key: str
    label: str
    member_dlls: tuple[str, ...]
    member_shard_ids: tuple[str, ...]
    source_inventory_ids: tuple[str, ...]
    confidence_status: str = "bounded_placeholder"
    confidence_score: float = 0.0
    contradiction_notes: tuple[str, ...] = ()
    details: dict[str, Any] | None = None
    schema_version: str = SHARD_MERGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.candidate_type not in {
            "cluster_candidate",
            "init_group_candidate",
            "dependency_class",
            "frontier_candidate",
        }:
            raise ValueError(f"unsupported merge candidate type: {self.candidate_type}")
        if self.confidence_score < 0:
            raise ValueError("confidence_score must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["lifecycle"] = self.lifecycle.to_dict()
        return payload


def _coalesce_candidate_hints(shard_inventory: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for inventory_row in list(shard_inventory.get("shard_inventory_artifacts") or []):
        if not isinstance(inventory_row, dict):
            continue
        shard_id = str(inventory_row.get("shard_id") or "").strip()
        for hint in list(inventory_row.get("candidate_hints") or []):
            if not isinstance(hint, dict):
                continue
            hint_type = str(hint.get("hint_type") or "").strip().lower()
            key = str(hint.get("key") or "").strip()
            if hint_type not in {"init_group", "dependency_class", "frontier"} or not key:
                continue
            row = dict(hint)
            row["shard_id"] = shard_id
            grouped.setdefault((hint_type, key), []).append(row)
    return grouped


def _build_cluster_candidates(
    package_id: str,
    graph_epoch: str,
    inventory_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for inventory_row in inventory_rows:
        shard_id = str(inventory_row.get("shard_id") or "").strip()
        dll_entries = list(inventory_row.get("dll_entries") or [])
        for dll_row in dll_entries:
            dll_name = _normalize_dll_name(dll_row)
            if not dll_name:
                continue
            stable_hash = _stable_hash([dll_name])
            lifecycle = DecompositionLifecycle(
                id=build_decomposition_object_id(
                    "cluster_candidate",
                    package_id,
                    stable_hash=stable_hash,
                ),
                object_type="cluster_candidate",
                package_id=package_id,
                graph_epoch=graph_epoch,
                source_ids=(shard_id, dll_name),
                contradiction_state="none",
            )
            candidates.append(
                MergeCandidate(
                    lifecycle=lifecycle,
                    candidate_type="cluster_candidate",
                    key=dll_name,
                    label=dll_name.rsplit(".", 1)[0],
                    member_dlls=(dll_name,),
                    member_shard_ids=(shard_id,),
                    source_inventory_ids=(shard_id,),
                ).to_dict()
            )
    return candidates


def _build_hint_candidates(
    package_id: str,
    graph_epoch: str,
    grouped_hints: dict[tuple[str, str], list[dict[str, Any]]],
    *,
    target_type: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    object_type = "init_group_candidate" if target_type == "init_group" else "dependency_class"
    for (hint_type, key), rows in grouped_hints.items():
        if hint_type != target_type:
            continue
        labels = {
            str(row.get("label") or key).strip()
            for row in rows
            if str(row.get("label") or key).strip()
        }
        member_dlls = _collect_detail_values(rows, "member_dlls")
        member_functions = _collect_detail_values(rows, "member_functions")
        exported_state_artifacts = _collect_detail_values(rows, "exported_state_artifacts")
        likely_downstream_consumers = _collect_detail_values(rows, "likely_downstream_consumers")
        member_clusters = _collect_detail_values(rows, "member_clusters")
        member_init_groups = _collect_detail_values(rows, "member_init_groups")
        evidence_edges = _collect_detail_values(rows, "evidence_edges")
        shard_ids = sorted(
            {
                str(row.get("shard_id") or "").strip()
                for row in rows
                if str(row.get("shard_id") or "").strip()
            }
        )
        contradiction_state = "none"
        notes: list[str] = []
        if len(labels) > 1:
            contradiction_state = "tentative"
            notes.append("label_divergence")
            contradictions.append(
                {
                    "candidate_type": object_type,
                    "key": key,
                    "reason": "label_divergence",
                    "labels": sorted(labels),
                    "shard_ids": shard_ids,
                }
            )
        if any(str(row.get("contradiction_state") or "").strip() == "contradicted" for row in rows):
            contradiction_state = "contradicted"
            notes.append("input_contradicted")
        stable_hash = _stable_hash([target_type, key])
        first = next(
            (
                row
                for row in rows
                if str(row.get("supersedes_id") or "").strip()
            ),
            rows[0],
        )
        lifecycle = DecompositionLifecycle(
            id=build_decomposition_object_id(object_type, package_id, stable_hash=stable_hash),
            object_type=object_type,
            package_id=package_id,
            graph_epoch=graph_epoch,
            source_ids=tuple(shard_ids),
            supersedes_id=str(first.get("supersedes_id") or "").strip(),
            supersedes_reason=str(first.get("supersedes_reason") or "").strip(),
            contradiction_state=contradiction_state,
        )
        candidates.append(
            MergeCandidate(
                lifecycle=lifecycle,
                candidate_type=object_type,
                key=key,
                label=sorted(labels)[0] if labels else key,
                member_dlls=tuple(member_dlls),
                member_shard_ids=tuple(shard_ids),
                source_inventory_ids=tuple(shard_ids),
                confidence_status="bounded_placeholder",
                confidence_score=0.0 if contradiction_state != "none" else 0.2,
                contradiction_notes=tuple(notes),
                details={
                    "member_functions": member_functions,
                    "exported_state_artifacts": exported_state_artifacts,
                    "likely_downstream_consumers": likely_downstream_consumers,
                    "member_clusters": member_clusters,
                    "member_init_groups": member_init_groups,
                    "evidence_edges": evidence_edges,
                    "dependency_kind": str(first.get("dependency_kind") or key).strip() or key,
                },
            ).to_dict()
        )
    return candidates, contradictions


def _build_frontier_candidates(
    package_id: str,
    graph_epoch: str,
    inventory_rows: list[dict[str, Any]],
    grouped_hints: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    frontier_hints = [item for (hint_type, _), values in grouped_hints.items() if hint_type == "frontier" for item in values]
    if frontier_hints:
        keyed: dict[str, list[dict[str, Any]]] = {}
        for row in frontier_hints:
            keyed.setdefault(str(row.get("key") or "").strip(), []).append(row)
        for ordinal, (key, values) in enumerate(sorted(keyed.items())):
            member_dlls = sorted(
                {
                    str(member or "").strip()
                    for value in values
                    for member in list(value.get("member_dlls") or [])
                    if str(member or "").strip()
                }
            )
            lifecycle = DecompositionLifecycle(
                id=build_decomposition_object_id(
                    "frontier_slice",
                    package_id,
                    graph_epoch=graph_epoch,
                    ordinal=ordinal,
                ),
                object_type="frontier_slice",
                package_id=package_id,
                graph_epoch=graph_epoch,
                source_ids=tuple(
                    str(value.get("shard_id") or "").strip()
                    for value in values
                    if str(value.get("shard_id") or "").strip()
                ),
                contradiction_state="none",
            )
            rows.append(
                MergeCandidate(
                    lifecycle=lifecycle,
                    candidate_type="frontier_candidate",
                    key=key,
                    label=str(values[0].get("label") or key).strip(),
                    member_dlls=tuple(member_dlls),
                    member_shard_ids=tuple(
                        str(value.get("shard_id") or "").strip()
                        for value in values
                        if str(value.get("shard_id") or "").strip()
                    ),
                    source_inventory_ids=tuple(
                        str(value.get("shard_id") or "").strip()
                        for value in values
                        if str(value.get("shard_id") or "").strip()
                    ),
                    confidence_status="bounded_placeholder",
                    confidence_score=0.1,
                ).to_dict()
            )
        return rows

    for ordinal, inventory_row in enumerate(inventory_rows):
        shard_id = str(inventory_row.get("shard_id") or "").strip()
        member_dlls = tuple(
            _normalize_dll_name(row)
            for row in list(inventory_row.get("dll_entries") or [])
            if _normalize_dll_name(row)
        )
        lifecycle = DecompositionLifecycle(
            id=build_decomposition_object_id(
                "frontier_slice",
                package_id,
                graph_epoch=graph_epoch,
                ordinal=ordinal,
            ),
            object_type="frontier_slice",
            package_id=package_id,
            graph_epoch=graph_epoch,
            source_ids=(shard_id,),
            contradiction_state="none",
        )
        rows.append(
            MergeCandidate(
                lifecycle=lifecycle,
                candidate_type="frontier_candidate",
                key=shard_id,
                label=shard_id,
                member_dlls=member_dlls,
                member_shard_ids=(shard_id,),
                source_inventory_ids=(shard_id,),
                confidence_status="bounded_placeholder",
                confidence_score=0.0,
            ).to_dict()
        )
    return rows


def _build_merge_observer(
    *,
    object_id: str,
    contradiction_state: str,
    contradiction_notes: list[str],
) -> dict[str, Any]:
    return {
        "observer_name": "merge_coherence",
        "object_id": object_id,
        "status": "warn" if contradiction_state != "none" else "pass",
        "provenance_complete": True,
        "stable_identity_present": True,
        "contradictions_visible": contradiction_state != "none" or bool(contradiction_notes),
        "ambiguity_score": 0.5 if contradiction_state != "none" else 0.0,
        "warnings": tuple(contradiction_notes),
    }


def build_shard_merge_candidates(shard_inventory: dict[str, Any]) -> dict[str, Any]:
    package_id = str(shard_inventory.get("package_id") or "").strip()
    graph_epoch = str(shard_inventory.get("graph_epoch") or "").strip()
    inventory_rows = [
        dict(row)
        for row in list(shard_inventory.get("shard_inventory_artifacts") or [])
        if isinstance(row, dict)
    ]
    grouped_hints = _coalesce_candidate_hints(shard_inventory)

    cluster_candidates = _build_cluster_candidates(package_id, graph_epoch, inventory_rows)
    init_groups, init_contradictions = _build_hint_candidates(
        package_id,
        graph_epoch,
        grouped_hints,
        target_type="init_group",
    )
    dependency_classes, dependency_contradictions = _build_hint_candidates(
        package_id,
        graph_epoch,
        grouped_hints,
        target_type="dependency_class",
    )
    frontier_candidates = _build_frontier_candidates(package_id, graph_epoch, inventory_rows, grouped_hints)

    observers = []
    for row in cluster_candidates + init_groups + dependency_classes:
        lifecycle = dict(row.get("lifecycle") or {})
        observers.append(
            _build_merge_observer(
                object_id=str(lifecycle.get("id") or "").strip(),
                contradiction_state=str(lifecycle.get("contradiction_state") or "none"),
                contradiction_notes=list(row.get("contradiction_notes") or []),
            )
        )

    return {
        "schema_version": SHARD_MERGE_SCHEMA_VERSION,
        "package_id": package_id,
        "graph_epoch": graph_epoch,
        "candidate_clusters": cluster_candidates,
        "candidate_initialization_groups": init_groups,
        "candidate_dependency_classes": dependency_classes,
        "initial_frontier_candidates": frontier_candidates,
        "merge_contradiction_registry": init_contradictions + dependency_contradictions,
        "merge_observer_summaries": observers,
    }
