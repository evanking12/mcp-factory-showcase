from __future__ import annotations

import json
from pathlib import Path

from api.pipeline.core.design_suite_campaign_readiness import build_design_suite_campaign_readiness
from scripts.runs.run_design_suite_campaign_local import run_design_suite_campaign_local
from api.pipeline.core.design_suite_scaling_projection import run_design_suite_scaling_projection


def test_campaign_readiness_turns_green_when_local_and_scaling_inputs_are_present(tmp_path: Path) -> None:
    local_result = run_design_suite_campaign_local(
        suite="northstar_transaction_suite",
        mode="late_confirmation",
        output_root=tmp_path,
    )
    scaling_result = run_design_suite_scaling_projection(tmp_path)
    forked_result = run_design_suite_campaign_local(
        suite="northstar_transaction_suite",
        mode="forked_state",
        output_root=tmp_path / "forked_state_guard",
    )

    readiness = build_design_suite_campaign_readiness(
        local_result["campaign_plan"],
        local_result["campaign_truth"],
        local_result["campaign_cohesion"],
        scaling_result["scaling_projection"],
        scaling_result["scaling_cohesion"],
        target_mode="late_confirmation",
        forked_state_guard=forked_result["campaign_plan"],
    )

    assert readiness["target_mode"] == "late_confirmation"
    assert readiness["local_campaign_shape_green"] is True
    assert readiness["scaling_projection_green"] is True
    assert readiness["runtime_projection_green"] is True
    assert readiness["package_truth_green"] is True
    assert readiness["cohesion_green"] is True
    assert readiness["forked_state_local_guard_green"] is True
    assert readiness["compare_ready"] is False
    assert readiness["promotion_ready"] is False
    assert readiness["ready_for_first_bounded_campaign"] is True


def test_campaign_readiness_turns_green_for_forked_state_when_branch_semantics_survive(tmp_path: Path) -> None:
    local_result = run_design_suite_campaign_local(
        suite="northstar_transaction_suite",
        mode="forked_state",
        output_root=tmp_path,
    )
    scaling_result = run_design_suite_scaling_projection(tmp_path)

    readiness = build_design_suite_campaign_readiness(
        local_result["campaign_plan"],
        local_result["campaign_truth"],
        local_result["campaign_cohesion"],
        scaling_result["scaling_projection"],
        scaling_result["scaling_cohesion"],
        target_mode="forked_state",
        forked_state_guard=local_result["campaign_truth"],
    )

    assert readiness["target_mode"] == "forked_state"
    assert readiness["package_truth_green"] is True
    assert readiness["forked_state_local_guard_green"] is True
    assert readiness["forked_state_campaign_semantics_green"] is True
    assert readiness["accepted_branch_present"] is True
    assert readiness["rejected_branch_present"] is True
    assert readiness["campaign_truth_branch_projection_green"] is True
    assert readiness["campaign_cohesion_branch_projection_green"] is True
    assert readiness["ready_for_first_bounded_campaign"] is True


def test_campaign_readiness_blocks_missing_confirmation_or_forked_guard(tmp_path: Path) -> None:
    local_result = run_design_suite_campaign_local(
        suite="northstar_transaction_suite",
        mode="late_confirmation",
        output_root=tmp_path,
    )
    scaling_result = run_design_suite_scaling_projection(tmp_path)

    broken_truth = dict(local_result["campaign_truth"])
    broken_truth["confirmation_sites"] = []
    readiness = build_design_suite_campaign_readiness(
        local_result["campaign_plan"],
        broken_truth,
        local_result["campaign_cohesion"],
        scaling_result["scaling_projection"],
        scaling_result["scaling_cohesion"],
        target_mode="late_confirmation",
        forked_state_guard={},
    )

    assert readiness["ready_for_first_bounded_campaign"] is False
    assert "package_truth_missing_provisional_or_confirmation_semantics" in readiness["blocking_reasons"]
    assert "forked_state_local_guard_incomplete" in readiness["blocking_reasons"]


def test_campaign_readiness_blocks_forked_state_when_branch_projection_is_missing(tmp_path: Path) -> None:
    local_result = run_design_suite_campaign_local(
        suite="northstar_transaction_suite",
        mode="forked_state",
        output_root=tmp_path,
    )
    scaling_result = run_design_suite_scaling_projection(tmp_path)

    broken_truth = dict(local_result["campaign_truth"])
    broken_truth["accepted_branches"] = []
    readiness = build_design_suite_campaign_readiness(
        local_result["campaign_plan"],
        broken_truth,
        local_result["campaign_cohesion"],
        scaling_result["scaling_projection"],
        scaling_result["scaling_cohesion"],
        target_mode="forked_state",
        forked_state_guard=local_result["campaign_truth"],
    )

    assert readiness["ready_for_first_bounded_campaign"] is False
    assert "forked_state_campaign_semantics_incomplete" in readiness["blocking_reasons"]
