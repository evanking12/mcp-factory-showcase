from __future__ import annotations

import json
from pathlib import Path

from scripts.regression.change_admission_check import (
    DEFAULT_REGISTRY,
    evaluate_change_admission,
    main,
    render_markdown,
    validate_registry,
    write_outputs,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _registry() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "systems": [
            {
                "system_id": "checkpoint_summary",
                "path_patterns": ["scripts/regression/write_ci_job_summary.py"],
                "description": "summary surface",
                "required_regression_tier": "tier0",
                "durable_contracts": ["summary entrypoint works"],
                "allowed_to_churn": ["markdown wording"],
                "unrelated_surfaces_expected_stable": ["lane startup"],
            }
        ],
        "checks": [
            {
                "check_id": "summary_writer_help",
                "system_id": "checkpoint_summary",
                "category": "meta_check",
                "command": "python scripts/regression/write_ci_job_summary.py --help",
                "blocking": True,
                "expected_runtime_seconds": 5,
                "when_required": "summary changes",
            }
        ],
    }


def test_valid_registry_and_paths_classify_affected_system(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    _write_json(registry_path, _registry())

    result = evaluate_change_admission(
        registry_path=registry_path,
        changed_paths=["scripts/regression/write_ci_job_summary.py"],
    )

    assert result["verdict"] == "pass"
    assert result["affected_systems"][0]["system_id"] == "checkpoint_summary"
    assert result["required_meta_checks"][0]["check_id"] == "summary_writer_help"
    assert result["durable_contracts_expected_stable"] == ["summary entrypoint works"]


def test_unmapped_regression_bearing_path_fails(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    _write_json(registry_path, _registry())

    result = evaluate_change_admission(
        registry_path=registry_path,
        changed_paths=["api/pipeline/runner.py"],
    )

    assert result["verdict"] == "fail"
    assert any(failure["code"] == "unmapped_changed_path" for failure in result["failures"])


def test_system_without_durable_contracts_or_meta_check_fails_registry_validation() -> None:
    registry = _registry()
    registry["systems"][0]["durable_contracts"] = []
    registry["checks"][0]["category"] = "durable_contract"

    failures, _warnings = validate_registry(registry)

    codes = {failure["code"] for failure in failures}
    assert "incomplete_system" in codes
    assert "missing_system_meta_check" in codes


def test_optional_packet_missing_required_fields_fails(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    packet_path = tmp_path / "packet.json"
    _write_json(registry_path, _registry())
    _write_json(packet_path, {"system_changed": ["checkpoint_summary"]})

    result = evaluate_change_admission(
        registry_path=registry_path,
        changed_paths=["scripts/regression/write_ci_job_summary.py"],
        packet_path=packet_path,
    )

    assert result["verdict"] == "fail"
    missing_fields = [failure["field"] for failure in result["failures"] if failure["code"] == "missing_packet_field"]
    assert "durable_contracts" in missing_fields
    assert "next_blocker" in missing_fields


def test_valid_packet_and_outputs_are_stable(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    packet_path = tmp_path / "packet.json"
    output_json = tmp_path / "out" / "result.json"
    output_md = tmp_path / "out" / "summary.md"
    _write_json(registry_path, _registry())
    _write_json(
        packet_path,
        {
            "system_changed": ["checkpoint_summary"],
            "durable_contracts": ["summary entrypoint works"],
            "allowed_churn": ["markdown wording"],
            "meta_checks": [{"command": "python scripts/regression/write_ci_job_summary.py --help", "result": "pass"}],
            "regression_posture": "tier0",
            "change_admission_result": "pass",
            "unexpected_blast_radius": ["none"],
            "classification_updates_required": "no",
            "next_blocker": "none",
        },
    )

    result = evaluate_change_admission(
        registry_path=registry_path,
        changed_paths=["scripts/regression/write_ci_job_summary.py"],
        packet_path=packet_path,
    )
    write_outputs(result, output_json=output_json, output_md=output_md)

    assert result["verdict"] == "pass"
    assert json.loads(output_json.read_text(encoding="utf-8"))["verdict"] == "pass"
    markdown = output_md.read_text(encoding="utf-8")
    assert "Change Admission" in markdown
    assert "checkpoint_summary" in markdown
    assert render_markdown(result) == markdown


def test_strict_mode_requires_mapped_system_for_changed_paths(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    _write_json(registry_path, _registry())

    result = evaluate_change_admission(
        registry_path=registry_path,
        changed_paths=["docs/unmapped.md"],
        strict=True,
    )

    assert result["verdict"] == "fail"
    assert any(failure["code"] == "no_affected_system" for failure in result["failures"])


def test_cli_writes_github_output(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    paths_file = tmp_path / "paths.txt"
    github_output = tmp_path / "github-output.txt"
    _write_json(registry_path, _registry())
    paths_file.write_text("scripts/regression/write_ci_job_summary.py\n", encoding="utf-8")

    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "--paths-file",
            str(paths_file),
            "--github-output",
            str(github_output),
        ]
    )

    assert exit_code == 0
    output = github_output.read_text(encoding="utf-8")
    assert "change_admission_verdict=pass" in output
    assert "affected_system_count=1" in output


def test_default_registry_maps_stage_route_worker_and_agent_surfaces() -> None:
    result = evaluate_change_admission(
        registry_path=DEFAULT_REGISTRY,
        changed_paths=[
            "AGENTS.md",
            "api/pipeline/README.md",
            "api/infra/worker.py",
            "api/pipeline/core/s00_s01_handoff.py",
            "api/pipeline/core/types.py",
            "api/pipeline/s00_setup/TRACE.md",
            "api/pipeline/s01_unlock/FAMILY-BLOCKERS.md",
            "api/pipeline/s00_setup/session_artifacts.py",
            "api/pipeline/s01_unlock/__init__.py",
            "api/routes/routes_session.py",
            "docs/architecture/stage_split/s00_stage_split.md",
            "docs/architecture/testing_strategy/STAGE-PROVING-MAP.md",
            "docs/architecture/testing_strategy/STAGE-QUALIFICATION-MAP.md",
            "docs/architecture/testing_strategy/REGRESSION-POLICY.md",
            "docs/architecture/testing_strategy/S00-S01-HANDOFF-REGRESSION-CHECKLIST.md",
            "tests/test_s00_s01_breakpoint_suite.py",
            "tests/fixtures/s00_s01_admission_pressure/s00_s01_admission_pressure.c",
            "scripts/regression/run_path_aware_checks.py",
            "scripts/regression/run_stage_breakpoint_checks.py",
            ".github/workflows/stage-breakpoint-checks.yml",
            "tests/test_stage_breakpoint_checks.py",
            "configs/regression/observability_promotion_triggers.json",
            "docs/architecture/testing_strategy/OBSERVABILITY-PROMOTION-TRIGGERS.md",
        ],
    )

    assert result["verdict"] == "pass"
    system_ids = {system["system_id"] for system in result["affected_systems"]}
    assert "agent_governance" in system_ids
    assert "worker_persistence" in system_ids
    assert "regression_policy_governance" in system_ids
    assert "path_aware_check_runner" in system_ids
    assert "stage_breakpoint_check_runner" in system_ids
    assert "checkpoint_live_observability" in system_ids
    assert "stage_handoff_packets" in system_ids
    assert "s00_s01_breakpoint_suite" in system_ids
    assert "stage_live_truth_governance" in system_ids
    assert "session_routes" in system_ids
    assert any(
        check["check_id"] == "stage_live_truth_governance_tests"
        for check in result["required_meta_checks"]
    )
    assert any(
        check["check_id"] == "s00_s01_breakpoint_suite_meta_floor"
        for check in result["required_meta_checks"]
    )
    assert not any(failure["code"] == "unmapped_changed_path" for failure in result["failures"])


def test_default_registry_maps_hard03_runner() -> None:
    result = evaluate_change_admission(
        registry_path=DEFAULT_REGISTRY,
        changed_paths=["scripts/runs/run_spectrum_compiled_hard03.py"],
    )

    assert result["verdict"] == "pass"
    assert not any(failure["code"] == "unmapped_changed_path" for failure in result["failures"])
    system_ids = {system["system_id"] for system in result["affected_systems"]}
    assert "enterprise_survivability_suite" in system_ids
    assert "hard_family_measurement_fabric" in system_ids
