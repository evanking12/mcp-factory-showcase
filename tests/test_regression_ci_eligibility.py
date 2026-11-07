from __future__ import annotations

from scripts.regression.ci_gate_eligibility import evaluate_gate_eligibility


def test_api_path_requires_heavy_gate() -> None:
    result = evaluate_gate_eligibility(["api/pipeline/runner.py"])
    assert result["should_run_gate"] is True
    assert result["proof_risk_level"] == "red"
    assert result["requires_full_product_gate"] is True
    assert "api/pipeline/runner.py" in result["matched_paths"]


def test_non_governance_testing_strategy_doc_requires_heavy_gate() -> None:
    result = evaluate_gate_eligibility(["docs/architecture/testing_strategy/REGRESSION-POLICY.md"])
    assert result["should_run_gate"] is True


def test_issue_template_does_not_require_heavy_gate() -> None:
    result = evaluate_gate_eligibility([".github/ISSUE_TEMPLATE/bug_report.md"])
    assert result["should_run_gate"] is False
    assert result["proof_risk_level"] == "green"
    assert result["requires_full_product_gate"] is False


def test_unrelated_ui_doc_does_not_require_heavy_gate() -> None:
    result = evaluate_gate_eligibility(["dashboard/README.md"])
    assert result["should_run_gate"] is False
    assert result["proof_risk_level"] == "green"


def test_agents_file_requires_heavy_gate() -> None:
    result = evaluate_gate_eligibility(["AGENTS.md"])
    assert result["should_run_gate"] is True


def test_required_regression_workflow_file_requires_heavy_gate() -> None:
    result = evaluate_gate_eligibility([".github/workflows/required-regression-gates.yml"])
    assert result["should_run_gate"] is True
    assert ".github/workflows/required-regression-gates.yml" in result["matched_paths"]


def test_medium01_checkpoint_workflow_file_requires_heavy_gate() -> None:
    result = evaluate_gate_eligibility([".github/workflows/medium01-checkpoints.yml"])
    assert result["should_run_gate"] is True
    assert ".github/workflows/medium01-checkpoints.yml" in result["matched_paths"]


def test_stage_breakpoint_workflow_file_requires_heavy_gate() -> None:
    result = evaluate_gate_eligibility([".github/workflows/stage-breakpoint-checks.yml"])
    assert result["should_run_gate"] is True
    assert ".github/workflows/stage-breakpoint-checks.yml" in result["matched_paths"]


def test_change_admission_governance_file_is_fast_floor_only() -> None:
    result = evaluate_gate_eligibility(["configs/regression/check_registry.json"])
    assert result["should_run_gate"] is False
    assert result["proof_risk_level"] == "grey"
    assert result["requires_full_product_gate"] is False
    assert "configs/regression/check_registry.json" in result["fast_floor_only_paths"]


def test_change_admission_system_map_is_fast_floor_only() -> None:
    result = evaluate_gate_eligibility(["docs/architecture/testing_strategy/SYSTEM-MAP.md"])
    assert result["should_run_gate"] is False
    assert "docs/architecture/testing_strategy/SYSTEM-MAP.md" in result["fast_floor_only_paths"]


def test_mixed_fast_floor_and_runtime_change_still_requires_heavy_gate() -> None:
    result = evaluate_gate_eligibility(
        [
            "configs/regression/check_registry.json",
            "api/pipeline/runner.py",
        ]
    )
    assert result["should_run_gate"] is True
    assert result["proof_risk_level"] == "red"
    assert result["requires_full_product_gate"] is True
    assert "configs/regression/check_registry.json" in result["fast_floor_only_paths"]
    assert "api/pipeline/runner.py" in result["matched_paths"]


def test_storage_closeout_surface_is_red_risk() -> None:
    result = evaluate_gate_eligibility(["api/infra/storage.py"])

    assert result["proof_risk_level"] == "red"
    assert result["requires_full_product_gate"] is True
    assert "full_product_gate_surface" in result["reason_codes"]
    assert "checkpoint/replay" in result["recommended_local_proof"]


def test_generate_schema_surface_is_red_risk() -> None:
    result = evaluate_gate_eligibility(["api/services/generate.py"])

    assert result["proof_risk_level"] == "red"
    assert result["requires_full_product_gate"] is True


def test_hard01_product_runner_is_yellow_risk() -> None:
    result = evaluate_gate_eligibility(["scripts/runs/run_spectrum_compiled_hard01_product.py"])

    assert result["should_run_gate"] is True
    assert result["proof_risk_level"] == "yellow"
    assert result["requires_full_product_gate"] is False
    assert "Medium02 or the touched suite" in result["recommended_local_proof"]


def test_hard03_runner_is_yellow_not_full_product_gate() -> None:
    result = evaluate_gate_eligibility(["scripts/runs/run_spectrum_compiled_hard03.py"])

    assert result["should_run_gate"] is True
    assert result["proof_risk_level"] == "yellow"
    assert result["requires_full_product_gate"] is False
    assert "scripts/runs/run_spectrum_compiled_hard03.py" in result["matched_paths"]


def test_proof_routing_markdown_is_grey_risk() -> None:
    result = evaluate_gate_eligibility(
        ["docs/architecture/testing_strategy/PROOF-ROUTING-AND-HARD01-FOCUS.md"]
    )

    assert result["should_run_gate"] is True
    assert result["proof_risk_level"] == "grey"
    assert result["requires_full_product_gate"] is False


def test_mixed_paths_choose_highest_risk() -> None:
    result = evaluate_gate_eligibility(
        [
            "dashboard/README.md",
            "scripts/runs/run_spectrum_compiled_hard01_product.py",
            "api/services/generate.py",
        ]
    )

    assert result["proof_risk_level"] == "red"
    assert result["requires_full_product_gate"] is True
    assert [row["risk_level"] for row in result["path_risks"]] == ["green", "yellow", "red"]
