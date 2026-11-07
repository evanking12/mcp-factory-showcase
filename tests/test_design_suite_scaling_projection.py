from __future__ import annotations

import json
from pathlib import Path

from scripts.runs.run_design_suite_scaling_projection import main as scaling_main
from scripts.runs.run_design_suite_scaling_projection import run_design_suite_campaign_local
from api.pipeline.core.design_suite_scaling_projection import run_design_suite_scaling_projection


def test_design_suite_scaling_projection_emits_expected_artifacts(tmp_path: Path) -> None:
    run_design_suite_campaign_local(
        suite="northstar_transaction_suite",
        mode="late_confirmation",
        output_root=tmp_path,
    )
    result = run_design_suite_scaling_projection(tmp_path)
    output_dir = Path(result["output_dir"])

    assert (output_dir / "design-suite-scaling-projection.json").exists()
    assert (output_dir / "design-suite-slice-plan.json").exists()
    assert (output_dir / "design-suite-scaling-cohesion.json").exists()


def test_design_suite_scaling_projection_preserves_family_blockers_and_provisional_semantics(tmp_path: Path) -> None:
    run_design_suite_campaign_local(
        suite="northstar_transaction_suite",
        mode="late_confirmation",
        output_root=tmp_path,
    )
    run_design_suite_scaling_projection(tmp_path)

    projection = json.loads((tmp_path / "design-suite-scaling-projection.json").read_text(encoding="utf-8"))
    slice_plan = json.loads((tmp_path / "design-suite-slice-plan.json").read_text(encoding="utf-8"))

    assert projection["family_blockers_preserved"] is True
    assert "late_confirmation_blocker" in projection["family_blocker_ids"]
    assert set(slice_plan["provisional_subject_ids"]) == {
        "inventory.reserve_item",
        "billing.authorize_charge",
    }
    assert slice_plan["confirmation_sites"] == ["audit.commit_receipt"]
    assert slice_plan["slice_execution_attribution"] is True


def test_design_suite_scaling_projection_preserves_forked_state_branch_visibility(tmp_path: Path) -> None:
    run_design_suite_campaign_local(
        suite="northstar_transaction_suite",
        mode="forked_state",
        output_root=tmp_path,
    )
    run_design_suite_scaling_projection(tmp_path)

    slice_plan = json.loads((tmp_path / "design-suite-slice-plan.json").read_text(encoding="utf-8"))
    cohesion = json.loads((tmp_path / "design-suite-scaling-cohesion.json").read_text(encoding="utf-8"))

    assert "authorization_receipt_primary" in slice_plan["accepted_branches"]
    assert "authorization_receipt_shadow" in slice_plan["rejected_branches"]
    assert "authorization_receipt_primary" in cohesion["accepted_branches"]
