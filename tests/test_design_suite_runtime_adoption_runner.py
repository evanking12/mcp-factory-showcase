from __future__ import annotations

import json
from pathlib import Path

from scripts.runs.run_design_suite_runtime_adoption import run_design_suite_runtime_adoption


def test_runtime_adoption_runner_emits_local_runtime_package_artifacts(tmp_path: Path) -> None:
    result = run_design_suite_runtime_adoption(
        suite="northstar_transaction_suite",
        mode="forked_state",
        output_root=tmp_path,
    )

    output_dir = Path(result["output_dir"])
    assert (output_dir / "design-suite-runtime-plan.json").exists()
    assert (output_dir / "design-suite-package-truth.json").exists()
    assert (output_dir / "design-suite-cohesion-report.json").exists()
    assert (output_dir / "design-suite-execution-trace.json").exists()
    assert not (output_dir / "campaign-truth.json").exists()
    assert not (output_dir / "decomposition-campaign-plan.json").exists()


def test_runtime_adoption_runner_executes_serialized_branch_selection(tmp_path: Path) -> None:
    result = run_design_suite_runtime_adoption(
        suite="northstar_transaction_suite",
        mode="forked_state",
        output_root=tmp_path,
    )
    trace_path = Path(result["output_dir"]) / "design-suite-execution-trace.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))

    step_ids = [row["step_id"] for row in trace["steps"]]
    assert step_ids[:3] == [
        "session.bootstrap_session",
        "inventory.reserve_item",
        "billing.authorize_charge",
    ]
    assert "audit.commit_receipt:authorization_receipt_primary" in step_ids
    assert "audit.commit_receipt:authorization_receipt_shadow" in step_ids


def test_runtime_adoption_runner_marks_late_confirmation_subjects_provisional(tmp_path: Path) -> None:
    result = run_design_suite_runtime_adoption(
        suite="northstar_transaction_suite",
        mode="late_confirmation",
        output_root=tmp_path,
    )

    truth_path = Path(result["output_dir"]) / "design-suite-package-truth.json"
    truth = json.loads(truth_path.read_text(encoding="utf-8"))

    assert set(truth["provisional_subject_ids"]) == {
        "inventory.reserve_item",
        "billing.authorize_charge",
    }
    assert truth["confirmation_sites"] == ["audit.commit_receipt"]
