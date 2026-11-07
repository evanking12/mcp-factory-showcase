from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.pipeline.core.decomposition_inspection_surface import build_decomposition_inspection_surface
from api.pipeline.core.dependency_class_inference import infer_dependency_classes
from api.pipeline.core.init_group_inference import infer_initialization_groups
from api.pipeline.core.package_frontier_slice_planner import build_package_frontier_slices
from api.pipeline.core.package_intake_shard_runner import build_package_intake_shards
from api.pipeline.core.shard_inventory_emitter import emit_shard_inventory_artifacts
from api.pipeline.core.shard_merge_coordinator import build_shard_merge_candidates
from api.pipeline.core.slice_execution_coordinator import build_slice_execution_map


REDUCED_PACKAGE_DECOMPOSITION_PROOF_SCHEMA_VERSION = "1.0.0"


def _apply_candidate_hints(
    shard_inventory: dict[str, Any],
    candidate_hints_by_shard: dict[int | str, list[dict[str, Any]]] | None,
) -> None:
    if not candidate_hints_by_shard:
        return
    artifacts = list(shard_inventory.get("shard_inventory_artifacts") or [])
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict):
            continue
        shard_id = str(row.get("shard_id") or "").strip()
        hints = candidate_hints_by_shard.get(index)
        if hints is None and shard_id:
            hints = candidate_hints_by_shard.get(shard_id)
        if hints is None:
            continue
        row["candidate_hints"] = [dict(item) for item in list(hints or []) if isinstance(item, dict)]


def _write_json(output_dir: Path, name: str, payload: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_reduced_package_decomposition_proof(
    package_input: dict[str, Any],
    *,
    candidate_hints_by_shard: dict[int | str, list[dict[str, Any]]] | None = None,
    target_shard_width: int = 2,
    max_slice_dlls: int = 3,
    output_dir: str | None = None,
) -> dict[str, Any]:
    shard_plan = build_package_intake_shards(package_input, target_shard_width=target_shard_width)
    shard_inventory = emit_shard_inventory_artifacts(shard_plan)
    _apply_candidate_hints(shard_inventory, candidate_hints_by_shard)
    merge_output = build_shard_merge_candidates(shard_inventory)
    init_group_output = infer_initialization_groups(merge_output)
    dependency_class_output = infer_dependency_classes(
        merge_output,
        init_group_output=init_group_output,
    )
    frontier_slice_plan = build_package_frontier_slices(
        package_input,
        merge_output,
        init_group_output,
        dependency_class_output,
        max_slice_dlls=max_slice_dlls,
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

    shard_budget_breaches = sum(
        1
        for row in list(shard_plan.get("shards") or [])
        if isinstance(row, dict)
        and bool(
            dict(
                row.get("shard_economics")
                or row.get("economics")
                or {}
            ).get("budget_breached")
        )
    )
    init_collapses = int(dependency_class_output.get("collapsed_init_group_count") or 0)
    cluster_collapses = int(dependency_class_output.get("collapsed_cluster_count") or 0)
    slice_failures = [
        row
        for row in list(frontier_slice_plan.get("frontier_slice_observer_summaries") or [])
        if isinstance(row, dict) and str(row.get("status") or "").strip().lower() == "fail"
    ]
    execution_failures = [
        row
        for row in list(execution_map.get("coordinator_observer_summaries") or [])
        if isinstance(row, dict) and str(row.get("status") or "").strip().lower() == "fail"
    ]
    proof_summary = {
        "schema_version": REDUCED_PACKAGE_DECOMPOSITION_PROOF_SCHEMA_VERSION,
        "package_id": str(package_input.get("package_id") or "").strip(),
        "graph_epoch": str(package_input.get("graph_epoch") or "").strip(),
        "proof_scope": "reduced_package_decomposition",
        "rails_enforced": bool(shard_plan.get("schema_version") and frontier_slice_plan.get("schema_version")),
        "cheap_shard_economics_enforced": shard_budget_breaches == 0,
        "merge_contradictions_visible": "merge_contradiction_registry" in merge_output,
        "group_distinction_enforced": init_collapses == 0 and cluster_collapses == 0,
        "slice_boundedness_enforced": not slice_failures,
        "execution_lane_safety_enforced": not execution_failures and not execution_map.get("live_parallelism_enabled"),
        "observability_links_canonical_truth": bool(
            dict(inspection_surface.get("decomposition_dashboard") or {}).get("canonical_sources")
        ),
        "imported_to_active_ratio": dict(inspection_surface.get("decomposition_dashboard") or {}).get(
            "imported_to_active_ratio",
            0.0,
        ),
        "contradiction_hotspot_count": int(
            dict(inspection_surface.get("decomposition_dashboard") or {}).get("contradiction_hotspot_count") or 0
        ),
    }
    proof_summary["status"] = (
        "pass"
        if all(
            (
                proof_summary["rails_enforced"],
                proof_summary["cheap_shard_economics_enforced"],
                proof_summary["merge_contradictions_visible"],
                proof_summary["group_distinction_enforced"],
                proof_summary["slice_boundedness_enforced"],
                proof_summary["execution_lane_safety_enforced"],
                proof_summary["observability_links_canonical_truth"],
            )
        )
        else "fail"
    )

    result = {
        "schema_version": REDUCED_PACKAGE_DECOMPOSITION_PROOF_SCHEMA_VERSION,
        "package_id": proof_summary["package_id"],
        "graph_epoch": proof_summary["graph_epoch"],
        "shard_plan": shard_plan,
        "shard_inventory": shard_inventory,
        "merge_output": merge_output,
        "init_group_output": init_group_output,
        "dependency_class_output": dependency_class_output,
        "frontier_slice_plan": frontier_slice_plan,
        "execution_map": execution_map,
        "inspection_surface": inspection_surface,
        "proof_summary": proof_summary,
    }

    if output_dir:
        output_path = Path(output_dir)
        _write_json(output_path, "shard-plan.json", shard_plan)
        _write_json(output_path, "shard-inventory.json", shard_inventory)
        _write_json(output_path, "merge-output.json", merge_output)
        _write_json(output_path, "initialization-groups.json", init_group_output)
        _write_json(output_path, "dependency-classes.json", dependency_class_output)
        _write_json(output_path, "frontier-slices.json", frontier_slice_plan)
        _write_json(output_path, "slice-execution-map.json", execution_map)
        _write_json(output_path, "decomposition-inspection.json", inspection_surface)
        _write_json(output_path, "reduced-proof-summary.json", proof_summary)

    return result
