from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.regression import run_path_aware_checks


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _paths_file(tmp_path: Path, *paths: str) -> Path:
    path = tmp_path / "changed-files.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(paths) + "\n", encoding="utf-8")
    return path


def _minimal_registry(tmp_path: Path, *, command: str, blocking: bool = True) -> Path:
    registry = {
        "schema_version": "1.0",
        "systems": [
            {
                "system_id": "example_system",
                "path_patterns": ["example/**"],
                "description": "example system",
                "required_regression_tier": "tier0",
                "durable_contracts": ["example contract"],
                "allowed_to_churn": ["example wording"],
                "unrelated_surfaces_expected_stable": ["lane startup"],
            }
        ],
        "checks": [
            {
                "check_id": "example_check",
                "system_id": "example_system",
                "category": "meta_check",
                "command": command,
                "blocking": blocking,
                "expected_runtime_seconds": 5,
                "when_required": "example changes",
            }
        ],
    }
    registry_path = tmp_path / "registry.json"
    _write_json(registry_path, registry)
    return registry_path


def _trigger_config(tmp_path: Path, *, tier: str = "tier2") -> Path:
    config = {
        "schema_version": "1.0",
        "triggers": [
            {
                "trigger_id": "scheduled_or_manual_heavier_baselines",
                "path_patterns": ["example/**"],
                "system_ids": ["example_system"],
                "required_tier_at_or_above": tier,
                "recommended_next_system": "scheduled_or_manual_heavier_baseline_suites",
                "claim_effect": "Do not claim heavier baseline coverage from Tier 0 checks.",
            }
        ],
    }
    config_path = tmp_path / "triggers.json"
    _write_json(config_path, config)
    return config_path


def test_regression_policy_path_selects_policy_governance_check(tmp_path: Path) -> None:
    result, exit_code = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(tmp_path, "docs/architecture/testing_strategy/REGRESSION-POLICY.md"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(system["system_id"] == "regression_policy_governance" for system in result["affected_systems"])
    assert any(
        "regression_policy_governance_tests" in check["check_ids"]
        for check in result["selected_checks"]
    )


def test_stage_trace_path_selects_stage_live_truth_check(tmp_path: Path) -> None:
    result, exit_code = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(tmp_path, "api/pipeline/s00_setup/TRACE.md"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert any(system["system_id"] == "stage_live_truth_governance" for system in result["affected_systems"])
    assert any("stage_live_truth_governance_tests" in check["check_ids"] for check in result["selected_checks"])


def test_s00_red_owned_path_selects_s00_s01_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(tmp_path, "api/pipeline/s00_setup/admission_handoff.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert any(system["system_id"] == "s00_s01_breakpoint_suite" for system in result["affected_systems"])
    assert any("s00_s01_breakpoint_suite_tests" in check["check_ids"] for check in result["selected_checks"])


def test_s00_s01_yellow_dependency_selects_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(tmp_path, "api/pipeline/core/s00_s01_handoff.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert any(system["system_id"] == "s00_s01_breakpoint_suite" for system in result["affected_systems"])
    assert any("s00_s01_breakpoint_suite_tests" in check["check_ids"] for check in result["selected_checks"])


def test_s00_s01_compiled_fixture_path_selects_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(
            tmp_path,
            "tests/fixtures/s00_s01_admission_pressure/s00_s01_admission_pressure.c",
        ),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert any(system["system_id"] == "s00_s01_breakpoint_suite" for system in result["affected_systems"])
    assert any("s00_s01_breakpoint_suite_tests" in check["check_ids"] for check in result["selected_checks"])


def test_paths_file_strips_utf8_bom_from_first_changed_path(tmp_path: Path) -> None:
    result, exit_code = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(tmp_path, "\ufeffapi/pipeline/s07_finalize/harmonize.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["checked_paths"][0] == "api/pipeline/s07_finalize/harmonize.py"
    assert any(system["system_id"] == "checkpoint_live_observability" for system in result["affected_systems"])


def test_nonblocking_checks_are_reported_as_skipped(tmp_path: Path) -> None:
    registry = _minimal_registry(tmp_path, command="manual review only", blocking=False)
    result, exit_code = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(tmp_path, "example/file.txt"),
        output_root=tmp_path / "out",
        registry_path=registry,
        execute=True,
    )

    assert exit_code == 0
    assert result["selected_checks"] == []
    assert result["skipped_checks"][0]["check_id"] == "example_check"
    assert result["skipped_checks"][0]["reason"] == "nonblocking_check"


def test_command_execution_pass_and_fail_are_captured(tmp_path: Path) -> None:
    pass_script = tmp_path / "pass_check.py"
    fail_script = tmp_path / "fail_check.py"
    pass_script.write_text("print('ok')\n", encoding="utf-8")
    fail_script.write_text("import sys\nprint('bad')\nsys.exit(7)\n", encoding="utf-8")

    pass_registry = _minimal_registry(tmp_path / "pass", command=f'"{sys.executable}" "{pass_script}"')
    pass_result, pass_exit = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(tmp_path / "pass", "example/file.txt"),
        output_root=tmp_path / "pass-out",
        registry_path=pass_registry,
        execute=True,
    )

    fail_registry = _minimal_registry(tmp_path / "fail", command=f'"{sys.executable}" "{fail_script}"')
    fail_result, fail_exit = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(tmp_path / "fail", "example/file.txt"),
        output_root=tmp_path / "fail-out",
        registry_path=fail_registry,
        execute=True,
    )

    assert pass_exit == 0
    assert pass_result["executions"][0]["verdict"] == "pass"
    assert "ok" in pass_result["executions"][0]["stdout_tail"]
    assert fail_exit == 1
    assert fail_result["executions"][0]["verdict"] == "fail"
    assert fail_result["executions"][0]["exit_code"] == 7
    assert fail_result["verdict"] == "fail"


def test_promotion_triggers_report_lane_migration_and_higher_tier_cases(tmp_path: Path) -> None:
    lane_result, _ = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(tmp_path / "lane", ".github/workflows/required-regression-gates.yml"),
        output_root=tmp_path / "lane-out",
        execute=False,
    )
    migration_result, _ = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(tmp_path / "migration", "api/pipeline/s00_setup/init.py"),
        output_root=tmp_path / "migration-out",
        execute=False,
    )

    higher_registry = {
        "schema_version": "1.0",
        "systems": [
            {
                "system_id": "example_system",
                "path_patterns": ["example/**"],
                "description": "example system",
                "required_regression_tier": "tier2",
                "durable_contracts": ["example contract"],
                "allowed_to_churn": ["example wording"],
                "unrelated_surfaces_expected_stable": ["lane startup"],
            }
        ],
        "checks": [
            {
                "check_id": "example_check",
                "system_id": "example_system",
                "category": "meta_check",
                "command": f'"{sys.executable}" -c "print(1)"',
                "blocking": True,
                "expected_runtime_seconds": 5,
                "when_required": "example changes",
            }
        ],
    }
    registry_path = tmp_path / "higher" / "registry.json"
    _write_json(registry_path, higher_registry)
    higher_result, _ = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(tmp_path / "higher", "example/file.txt"),
        output_root=tmp_path / "higher-out",
        registry_path=registry_path,
        trigger_config_path=_trigger_config(tmp_path / "higher"),
        execute=False,
    )

    lane_triggers = {trigger["trigger_id"]: trigger for trigger in lane_result["promotion_triggers"]}
    migration_triggers = {trigger["trigger_id"]: trigger for trigger in migration_result["promotion_triggers"]}
    higher_triggers = {trigger["trigger_id"]: trigger for trigger in higher_result["promotion_triggers"]}

    assert lane_triggers["lane_runtime_reliability_classification"]["state"] == "watch"
    assert migration_triggers["baseline_breakage_map_generation"]["state"] == "watch"
    assert higher_triggers["scheduled_or_manual_heavier_baselines"]["state"] == "watch"


def test_output_json_and_markdown_are_written(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    result, exit_code = run_path_aware_checks.run_path_aware_checks(
        paths_file=_paths_file(tmp_path, "scripts/regression/run_path_aware_checks.py"),
        output_root=output_root,
        execute=False,
    )

    result_path = output_root / run_path_aware_checks.RESULT_NAME
    summary_path = output_root / run_path_aware_checks.SUMMARY_NAME

    assert exit_code == 0
    assert result["claim_ceiling"] == "tier0 contract/governance/artifact compatibility only"
    assert result_path.exists()
    assert summary_path.exists()
    assert json.loads(result_path.read_text(encoding="utf-8"))["verdict"] == "pass"
    summary = summary_path.read_text(encoding="utf-8")
    assert "Path-Aware Checks" in summary
    assert "path_aware_check_runner_tests" in summary
    assert "Promotion Triggers" in summary
