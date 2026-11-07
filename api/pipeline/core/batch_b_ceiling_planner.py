from __future__ import annotations

from api.pipeline.core.package_frontier_planner import (
    PACKAGE_FRONTIER_PLAN_SCHEMA_VERSION as BATCH_B_CEILING_PLAN_SCHEMA_VERSION,
    PackageFrontierEntry as BatchBCeilingEntry,
    build_package_frontier_plan,
)


def build_batch_b_ceiling_plan(
    wave_summary: dict,
    *,
    local_proofs_by_filename: dict[str, dict] | None = None,
    max_iteration_cycles: int = 3,
) -> dict:
    """Compatibility wrapper around the canonical package frontier planner."""
    plan = build_package_frontier_plan(
        wave_summary,
        local_proofs_by_filename=local_proofs_by_filename,
        max_iteration_cycles=max_iteration_cycles,
    )
    # Keep the historical planner_type visible for old tests/artifacts that still
    # describe this surface as a Batch B ceiling plan.
    return {
        **plan,
        "planner_type": "batch_b_ceiling_compat",
    }
