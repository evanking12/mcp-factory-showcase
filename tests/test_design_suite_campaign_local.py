from __future__ import annotations

import json
from pathlib import Path

from scripts.runs.run_design_suite_campaign_local import run_design_suite_campaign_local


def test_campaign_local_runner_emits_session_owned_rehearsal_artifacts(tmp_path: Path) -> None:
    result = run_design_suite_campaign_local(
        suite="northstar_transaction_suite",
        mode="late_confirmation",
        output_root=tmp_path,
    )
    output_dir = Path(result["output_dir"])

    assert (output_dir / "design-suite-campaign-plan.json").exists()
    assert (output_dir / "design-suite-campaign-truth.json").exists()
    assert (output_dir / "design-suite-campaign-cohesion-report.json").exists()
    assert (output_dir / "design-suite-campaign-execution-trace.json").exists()
    assert (output_dir / "design-suite-campaign-readiness-input.json").exists()
    assert not (output_dir / "campaign-truth.json").exists()
    assert not (output_dir / "campaign-cohesion-report.json").exists()


def test_campaign_local_runner_preserves_late_confirmation_truth(tmp_path: Path) -> None:
    result = run_design_suite_campaign_local(
        suite="northstar_transaction_suite",
        mode="late_confirmation",
        output_root=tmp_path,
    )
    truth = json.loads((Path(result["output_dir"]) / "design-suite-campaign-truth.json").read_text(encoding="utf-8"))

    assert truth["campaign_surface"] == "design_suite_local_campaign_shape"
    assert truth["compare_ready"] is False
    assert truth["promotion_ready"] is False
    assert set(truth["provisional_subject_ids"]) == {
        "inventory.reserve_item",
        "billing.authorize_charge",
    }
    assert truth["confirmation_sites"] == ["audit.commit_receipt"]


def test_campaign_local_runner_preserves_forked_state_visibility(tmp_path: Path) -> None:
    result = run_design_suite_campaign_local(
        suite="northstar_transaction_suite",
        mode="forked_state",
        output_root=tmp_path,
    )
    plan = json.loads((Path(result["output_dir"]) / "design-suite-campaign-plan.json").read_text(encoding="utf-8"))
    readiness = json.loads((Path(result["output_dir"]) / "design-suite-campaign-readiness-input.json").read_text(encoding="utf-8"))

    assert plan["campaign_surface"] == "design_suite_local_campaign_shape"
    assert "authorization_receipt_primary" in plan["accepted_branches"]
    assert "authorization_receipt_shadow" in plan["rejected_branches"]
    assert "authorization_receipt_primary" in readiness["accepted_branches"]
    assert "authorization_receipt_shadow" in readiness["rejected_branches"]
