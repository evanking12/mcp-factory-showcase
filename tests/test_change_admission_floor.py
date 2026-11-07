from __future__ import annotations

import json
from pathlib import Path

from scripts.regression import run_change_admission_floor


def test_floor_runner_writes_result_and_summary(tmp_path: Path, monkeypatch) -> None:
    paths_file = tmp_path / "changed-files.txt"
    output_root = tmp_path / "floor"
    paths_file.write_text("scripts/regression/write_ci_job_summary.py\n", encoding="utf-8")
    monkeypatch.setattr(
        run_change_admission_floor,
        "run_cli_smokes",
        lambda: [{"name": "write_ci_job_summary", "verdict": "pass", "message": ""}],
    )
    monkeypatch.setattr(
        run_change_admission_floor,
        "parse_workflows",
        lambda: [{"name": ".github/workflows/fast-checks.yml", "verdict": "pass", "message": ""}],
    )

    result, exit_code = run_change_admission_floor.run_floor(
        paths_file=paths_file,
        output_root=output_root,
        registry=run_change_admission_floor.DEFAULT_REGISTRY,
        packet=None,
        mode="local",
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert (output_root / "change-admission-result.json").exists()
    assert (output_root / "change-admission-summary.md").exists()
    assert json.loads((output_root / "change-admission-result.json").read_text(encoding="utf-8"))["mode"] == "local"


def test_cli_smoke_failures_become_meta_check_failures(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "floor"
    monkeypatch.setattr(
        run_change_admission_floor,
        "run_cli_smokes",
        lambda: [{"name": "broken_entrypoint", "verdict": "fail", "message": "boom"}],
    )
    monkeypatch.setattr(run_change_admission_floor, "parse_workflows", lambda: [])

    result, exit_code = run_change_admission_floor.run_floor(
        paths_file=None,
        output_root=output_root,
        registry=run_change_admission_floor.DEFAULT_REGISTRY,
        packet=None,
        mode="ci",
    )

    assert exit_code == 1
    assert result["verdict"] == "fail"
    assert any(failure["code"] == "meta_check_failed" for failure in result["failures"])
    assert "broken_entrypoint" in (output_root / "change-admission-summary.md").read_text(encoding="utf-8")


def test_no_changed_paths_still_validates_registry_and_entrypoints(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "floor"
    monkeypatch.setattr(
        run_change_admission_floor,
        "run_cli_smokes",
        lambda: [{"name": "help", "verdict": "pass", "message": ""}],
    )
    monkeypatch.setattr(
        run_change_admission_floor,
        "parse_workflows",
        lambda: [{"name": "workflow", "verdict": "pass", "message": ""}],
    )

    result, exit_code = run_change_admission_floor.run_floor(
        paths_file=None,
        output_root=output_root,
        registry=run_change_admission_floor.DEFAULT_REGISTRY,
        packet=None,
        mode="local",
    )

    assert exit_code == 0
    assert result["checked_paths"] == []
    assert result["affected_systems"] == []


def test_ci_mode_does_not_fail_for_unrelated_docs(tmp_path: Path, monkeypatch) -> None:
    paths_file = tmp_path / "changed-files.txt"
    output_root = tmp_path / "floor"
    paths_file.write_text("docs/readme-not-regression.md\n", encoding="utf-8")
    monkeypatch.setattr(
        run_change_admission_floor,
        "run_cli_smokes",
        lambda: [{"name": "help", "verdict": "pass", "message": ""}],
    )
    monkeypatch.setattr(
        run_change_admission_floor,
        "parse_workflows",
        lambda: [{"name": "workflow", "verdict": "pass", "message": ""}],
    )

    result, exit_code = run_change_admission_floor.run_floor(
        paths_file=paths_file,
        output_root=output_root,
        registry=run_change_admission_floor.DEFAULT_REGISTRY,
        packet=None,
        mode="ci",
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert result["affected_systems"] == []


def test_fast_checks_workflow_invokes_change_admission_floor_and_tests() -> None:
    workflow = Path(".github/workflows/fast-checks.yml").read_text(encoding="utf-8")

    assert "run_change_admission_floor.py" in workflow
    assert "run_path_aware_checks.py" in workflow
    assert "tests/test_change_admission_check.py" in workflow
    assert "tests/test_change_admission_floor.py" in workflow
    assert "tests/test_stage_sticky_docs.py" in workflow
    assert "tests/test_s00_s01_handoff_packet.py" in workflow
    assert "tests/test_routes_session_snapshot_handoff_packet.py" in workflow
    assert "tests/test_routes_session_report.py" in workflow
    assert "tests/test_contract_artifacts.py" in workflow
    assert "tests/test_path_aware_checks.py" in workflow
    assert "tests/test_stage_breakpoint_checks.py" in workflow
    assert "tests/test_s00_s01_breakpoint_suite.py" in workflow
    assert ".tmp/change-admission-floor/change-admission-result.json" in workflow
    assert ".tmp/path-aware-checks/path-aware-check-result.json" in workflow
    assert ".tmp/path-aware-checks/path-aware-check-summary.md" in workflow
    assert "fast-checks-path-aware.log" in workflow
    assert "$GITHUB_STEP_SUMMARY" in workflow
    assert "path_aware" in workflow
    assert "claim_ceiling: tier0 contract/governance/artifact compatibility only" in workflow
    assert "live_lane: not exercised by Fast Checks" in workflow


def test_stage_breakpoint_workflow_invokes_stage_breakpoint_runner() -> None:
    workflow = Path(".github/workflows/stage-breakpoint-checks.yml").read_text(encoding="utf-8")

    assert "windows-latest" in workflow
    assert "run_stage_breakpoint_checks.py" in workflow
    assert "changed-files.txt" in workflow
    assert "stage-breakpoint-result.json" in workflow
    assert "stage-breakpoint-summary.md" in workflow
    assert "stage/seam breakpoint evidence only" in workflow
    assert "$env:GITHUB_STEP_SUMMARY" in workflow
