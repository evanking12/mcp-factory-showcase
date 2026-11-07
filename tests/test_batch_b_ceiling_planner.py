from __future__ import annotations

import json

from api.pipeline.core.package_frontier_planner import build_package_frontier_plan
from api.pipeline.core.batch_b_ceiling_planner import build_batch_b_ceiling_plan


def _load_wave_summary() -> dict:
    with open(
        ".\\sessions\\campaigns\\blocker_harvest\\20260406-104644\\wave-2-batch-b\\wave-summary.json",
        encoding="utf-8",
    ) as handle:
        return json.load(handle)


def test_batch_b_ceiling_plan_targets_only_overlap_frontier() -> None:
    wave_summary = _load_wave_summary()

    plan = build_package_frontier_plan(wave_summary)

    assert plan["planner_status"] == "ready"
    assert plan["baseline_contract_present"] is True
    assert plan["baseline_contract"]["source_wave_id"] == "wave-2-batch-a"
    assert plan["floor_scope"] == "package"
    assert plan["package_floor"]["floor_scope"] == "package"
    assert plan["package_floor"]["comparison_gate"] == "baseline_contract_required_for_overlap_claims"
    assert plan["active_frontier_dlls"] == [
        "contoso_config.dll",
        "contoso_reporting.dll",
        "contoso_pricing.dll",
    ]
    assert "contoso_workflow.dll" in plan["imported_lower_floor_dlls"]
    imported = next(row for row in plan["imported_lower_floor_rows"] if row["dll"] == "contoso_workflow.dll")
    assert imported["verified_count"] == 12
    assert imported["total_functions"] == 12
    assert plan["frontier_entry_count"] == 3


def test_batch_b_ceiling_plan_maps_reporting_residual_into_reporting_cluster() -> None:
    wave_summary = _load_wave_summary()

    plan = build_package_frontier_plan(
        wave_summary,
        local_proofs_by_filename={
            "contoso_reporting.dll": {
                "proof_job_id": "6fad7c7d",
                "iteration_index": 2,
                "carryover_status": "fail",
                "status": "stop",
                "next_ceiling_functions": ["RP_PrepareReservationReport"],
                "observer_verdicts": {
                    "first_broken_handoff_group": "reporting_report_bootstrap",
                },
            }
        },
    )

    reporting = next(
        entry for entry in plan["frontier_entries"]
        if entry["dll"] == "contoso_reporting.dll"
    )
    assert reporting["cluster_checkpoint_id"] == "reporting_preview_render_export"
    assert list(reporting["ceiling_functions"]) == ["RP_SelectFormat"]
    assert list(reporting["prerequisite_state_group_ids"]) == ["reporting_report_bootstrap"]
    assert reporting["local_proof"]["proof_job_id"] == "6fad7c7d"
    assert reporting["local_proof"]["first_broken_handoff_group"] == "reporting_report_bootstrap"


def test_batch_b_ceiling_plan_wrapper_stays_backward_compatible() -> None:
    wave_summary = _load_wave_summary()

    plan = build_batch_b_ceiling_plan(wave_summary)

    assert plan["planner_type"] == "batch_b_ceiling_compat"
    assert plan["active_frontier_dlls"] == [
        "contoso_config.dll",
        "contoso_reporting.dll",
        "contoso_pricing.dll",
    ]
