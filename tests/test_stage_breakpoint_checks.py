from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.regression import run_stage_breakpoint_checks


def _paths_file(tmp_path: Path, *paths: str) -> Path:
    path = tmp_path / "changed-files.txt"
    path.write_text("\n".join(paths) + "\n", encoding="utf-8")
    return path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _minimal_registry(tmp_path: Path, *, command: str) -> Path:
    registry = {
        "schema_version": "1.0",
        "systems": [
            {
                "system_id": "example_stage_breakpoint",
                "path_patterns": ["example/stage/**"],
                "description": "example stage breakpoint",
                "required_regression_tier": "tier0",
                "durable_contracts": ["stage breakpoint stays bounded"],
                "allowed_to_churn": ["fixture wording"],
                "unrelated_surfaces_expected_stable": ["live lane"],
            }
        ],
        "checks": [
            {
                "check_id": "example_stage_breakpoint_tests",
                "system_id": "example_stage_breakpoint",
                "category": "stage_breakpoint",
                "command": command,
                "blocking": True,
                "expected_runtime_seconds": 5,
                "when_required": "example stage changes",
                "breakpoint_scope": "S-00X example",
                "ownership_type": "stage-owned",
                "breakpoint_family": "example pressure",
                "current_tier": "Tier 1",
                "target_tier": "Tier 2",
                "claim_ceiling": "example stage breakpoint only",
            },
            {
                "check_id": "example_stage_meta",
                "system_id": "example_stage_breakpoint",
                "category": "meta_check",
                "command": f'"{sys.executable}" -c "print(1)"',
                "blocking": True,
                "expected_runtime_seconds": 5,
                "when_required": "example meta changes",
            },
        ],
    }
    registry_path = tmp_path / "registry.json"
    _write_json(registry_path, registry)
    return registry_path


def test_pipeline_full_baseline_path_selects_pipeline_baseline_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(
            tmp_path,
            "dynamic_campaigns/pipeline_full_tier2_baseline_v1/ROW-LOCK.md",
        ),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "pipeline_full_tier2_baseline_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "pipeline_full_tier2_baseline_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-00 -> S-07 full pipeline baseline"
    assert selected[0]["ownership_type"] == "mixed stage/seam/coordinator/bottom-up"
    assert selected[0]["breakpoint_family"] == "full pipeline Tier 2 baseline classification"
    assert selected[0]["current_tier"] == (
        "mixed Tier 2 with failed_tier2, blocked_at_tier2, deferred, and unimplemented rows"
    )
    assert selected[0]["target_tier"] == "Tier 2"
    assert selected[0]["claim_ceiling"] == (
        "Full-pipeline row classification only; failed, blocked, deferred, and unimplemented rows are not promoted"
    )


def test_s00_s01_changed_path_selects_default_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "api/pipeline/s00_setup/admission_handoff.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(system["system_id"] == "s00_s01_breakpoint_suite" for system in result["affected_systems"])
    selected = [check for check in result["selected_checks"] if "s00_s01_breakpoint_suite_tests" in check["check_ids"]]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-00C -> S-01"
    assert selected[0]["ownership_type"] == "seam-owned"
    assert selected[0]["breakpoint_family"] == "admission pressure"
    assert selected[0]["current_tier"] == "Tier 1"
    assert selected[0]["target_tier"] == "Tier 3"
    assert selected[0]["claim_ceiling"] == "handoff survives one easy compiled pressure case"
    assert not any("s00_s01_breakpoint_suite_meta_floor" in check["check_ids"] for check in result["selected_checks"])
    assert result["claim_ceiling"] == run_stage_breakpoint_checks.CLAIM_CEILING


def test_s02b_changed_path_selects_invocation_execution_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "api/pipeline/s02_probe/invocation_execution.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s02b_invocation_execution_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s02b_invocation_execution_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-02B invocation_execution"
    assert selected[0]["ownership_type"] == "stage-owned"
    assert selected[0]["breakpoint_family"] == "raw observation integrity"
    assert selected[0]["current_tier"] == "Tier 2"
    assert selected[0]["target_tier"] == "Tier 3"
    assert selected[0]["claim_ceiling"] == "S-02B preserves raw observations under medium compiled invocation pressure"
    assert not any(
        "s02b_invocation_execution_breakpoint_suite_meta_floor" in check["check_ids"]
        for check in result["selected_checks"]
    )


def test_s02b_argument_builder_path_selects_argument_construction_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "api/pipeline/core/helpers.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s02b_argument_construction_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s02b_argument_construction_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-02B invocation_execution"
    assert selected[0]["ownership_type"] == "stage-owned"
    assert selected[0]["breakpoint_family"] == "argument construction"
    assert selected[0]["current_tier"] == "Tier 2"
    assert selected[0]["target_tier"] == "Tier 3"
    assert (
        selected[0]["claim_ceiling"]
        == "S-02B constructs usable typed arguments for medium-pressure simple exports"
    )
    assert not any(
        "s02b_argument_construction_breakpoint_suite_meta_floor" in check["check_ids"]
        for check in result["selected_checks"]
    )


def test_s02b_functional_precondition_fixture_selects_precondition_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(
            tmp_path,
            "tests/fixtures/s02b_functional_precondition_tier2/s02b_functional_precondition_tier2.c",
        ),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s02b_functional_precondition_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s02b_functional_precondition_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-02B invocation_execution"
    assert selected[0]["ownership_type"] == "stage-owned"
    assert selected[0]["breakpoint_family"] == "functional precondition handling"
    assert selected[0]["current_tier"] == "Tier 2"
    assert selected[0]["target_tier"] == "Tier 3"
    assert (
        selected[0]["claim_ceiling"]
        == "S-02B records blocked calls without pretending final semantics are known"
    )
    assert not any(
        "s02b_functional_precondition_breakpoint_suite_meta_floor" in check["check_ids"]
        for check in result["selected_checks"]
    )


def test_s02a_changed_path_selects_probe_ordering_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "api/pipeline/s02_probe/probe_ordering.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s02a_probe_ordering_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s02a_probe_ordering_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-02A probe_ordering"
    assert selected[0]["ownership_type"] == "stage-owned"
    assert selected[0]["breakpoint_family"] == "ordering quality"
    assert selected[0]["current_tier"] == "Tier 2"
    assert selected[0]["target_tier"] == "Tier 3"
    assert (
        selected[0]["claim_ceiling"]
        == "S-02A can produce a useful ordered probe plan under medium naming pressure"
    )
    assert not any(
        "s02a_probe_ordering_breakpoint_suite_meta_floor" in check["check_ids"]
        for check in result["selected_checks"]
    )


def test_s02a_s02b_seam_path_selects_ordering_execution_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "tests/test_s02a_s02b_seam_breakpoint_suite.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s02a_s02b_ordering_execution_seam_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s02a_s02b_ordering_execution_seam_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-02A -> S-02B"
    assert selected[0]["ownership_type"] == "seam-owned"
    assert selected[0]["breakpoint_family"] == "ordering-to-execution preservation"
    assert selected[0]["current_tier"] == "Tier 2"
    assert selected[0]["target_tier"] == "Tier 3"
    assert (
        selected[0]["claim_ceiling"]
        == "S-02B receives the S-02A ordered plan and preserves execution order under medium compiled seam pressure"
    )
    assert not any(
        "s02a_s02b_ordering_execution_seam_breakpoint_suite_meta_floor" in check["check_ids"]
        for check in result["selected_checks"]
    )


def test_s02b_s02c_seam_path_selects_raw_observation_durability_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "tests/test_s02b_s02c_seam_breakpoint_suite.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s02b_s02c_raw_observation_durability_seam_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s02b_s02c_raw_observation_durability_seam_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-02B -> S-02C"
    assert selected[0]["ownership_type"] == "seam-owned"
    assert selected[0]["breakpoint_family"] == "raw-observation durability"
    assert selected[0]["current_tier"] == "Tier 2"
    assert selected[0]["target_tier"] == "Tier 3"
    assert (
        selected[0]["claim_ceiling"]
        == "S-02B raw observations survive the live S-02C durability handoff under medium compiled pressure"
    )
    assert not any(
        "s02b_s02c_raw_observation_durability_seam_breakpoint_suite_meta_floor" in check["check_ids"]
        for check in result["selected_checks"]
    )


def test_s02c_s03_seam_path_selects_probe_evidence_consumability_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "tests/test_s02c_s03_seam_breakpoint_suite.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s02c_s03_probe_evidence_consumability_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s02c_s03_probe_evidence_consumability_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-02C -> S-03"
    assert selected[0]["ownership_type"] == "seam-owned"
    assert selected[0]["breakpoint_family"] == "probe evidence consumability"
    assert selected[0]["current_tier"] == "Tier 2"
    assert selected[0]["target_tier"] == "Tier 3"
    assert (
        selected[0]["claim_ceiling"]
        == "S-03 consumes S-02C durable probe evidence boundaries under medium focused seam pressure"
    )
    assert not any(
        "s02c_s03_probe_evidence_consumability_breakpoint_suite_meta_floor" in check["check_ids"]
        for check in result["selected_checks"]
    )


def test_s02_bottom_up_path_selects_raw_evidence_window_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "tests/test_s02b_s02c_s03_bottom_up_breakpoint_suite.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s02b_s02c_s03_bottom_up_evidence_window_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s02b_s02c_s03_bottom_up_evidence_window_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-02B -> S-02C -> S-03"
    assert selected[0]["ownership_type"] == "bottom-up window"
    assert selected[0]["breakpoint_family"] == "raw runtime evidence becomes reconciliation input"
    assert selected[0]["current_tier"] == "Tier 2"
    assert selected[0]["target_tier"] == "Tier 3"
    assert (
        selected[0]["claim_ceiling"]
        == "S-02B raw observations pass through S-02C durable capture into S-03 reconciliation under medium focused bottom-up pressure"
    )
    assert not any(
        "s02b_s02c_s03_bottom_up_evidence_window_breakpoint_suite_meta_floor" in check["check_ids"]
        for check in result["selected_checks"]
    )


def test_s02_remaining_tier2_path_selects_remaining_grounding_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "tests/test_s02_remaining_tier2_grounding_suite.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s02_remaining_tier2_grounding_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s02_remaining_tier2_grounding_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-02 remaining Tier 2 targets"
    assert selected[0]["ownership_type"] == "mixed stage/seam/bottom-up"
    assert selected[0]["breakpoint_family"] == "remaining S-02 Tier 2 grounding"
    assert selected[0]["current_tier"] == "partial Tier 2 with blocked_at_tier2 rows"
    assert selected[0]["target_tier"] == "Tier 2"
    assert (
        selected[0]["claim_ceiling"]
        == "Family-specific remaining S-02 Tier 2 evidence only; blocked_at_tier2 rows are not promoted"
    )
    assert not any(
        "s02_remaining_tier2_grounding_breakpoint_suite_meta_floor" in check["check_ids"]
        for check in result["selected_checks"]
    )


def test_s02c_changed_path_selects_evidence_capture_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "api/pipeline/s02_probe/evidence_capture.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s02c_evidence_capture_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s02c_evidence_capture_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-02C evidence_capture"
    assert selected[0]["ownership_type"] == "stage-owned"
    assert selected[0]["breakpoint_family"] == "probe-log durability"
    assert selected[0]["current_tier"] == "Tier 2"
    assert selected[0]["target_tier"] == "Tier 3"
    assert (
        selected[0]["claim_ceiling"]
        == "S-02C persists multiple raw observation packets under medium durability pressure without loss or semantic rewriting"
    )
    assert not any(
        "s02c_evidence_capture_breakpoint_suite_meta_floor" in check["check_ids"]
        for check in result["selected_checks"]
    )
    metadata = selected[0]["breakpoint_metadata"]
    status_rows = [
        row
        for row in metadata
        if row["breakpoint_family"] == "finding status persistence"
    ]
    assert status_rows
    assert status_rows[0]["breakpoint_scope"] == "S-02C evidence_capture"
    assert status_rows[0]["ownership_type"] == "stage-owned"
    assert status_rows[0]["current_tier"] == "Tier 2"
    assert status_rows[0]["target_tier"] == "Tier 3"
    assert (
        status_rows[0]["claim_ceiling"]
        == "S-02C preserves observed, blocked, ambiguous, and unresolved finding-status distinctions under medium pressure"
    )


def test_s02c_finding_status_path_selects_status_persistence_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(
            tmp_path,
            "dynamic_campaigns/s02_tier2_grounding_priority_v1/prompts/05-s02c-finding-status-persistence-tier2.md",
        ),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s02c_finding_status_persistence_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s02c_finding_status_persistence_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    metadata = selected[0]["breakpoint_metadata"]
    assert any(
        row["breakpoint_family"] == "finding status persistence"
        and row["current_tier"] == "Tier 2"
        and row["target_tier"] == "Tier 3"
        for row in metadata
    )
    assert not any(
        "s02c_finding_status_persistence_breakpoint_suite_meta_floor" in check["check_ids"]
        for check in result["selected_checks"]
    )


def test_s05b_verification_replay_path_selects_direct_replay_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "api/pipeline/s05_enrichment/verification_replay.py"),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s05b_verification_replay_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s05b_verification_replay_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-05B verification_replay"
    assert selected[0]["ownership_type"] == "stage-owned"
    assert selected[0]["breakpoint_family"] == "direct replay truth"
    assert selected[0]["current_tier"] == "Tier 2"
    assert selected[0]["target_tier"] == "Tier 3"
    assert (
        selected[0]["claim_ceiling"]
        == "S-05B distinguishes replayed truth from inherited working-call confidence under deterministic compiled replay pressure"
    )
    assert not any(
        "s05b_verification_replay_breakpoint_suite_meta_floor" in check["check_ids"]
        for check in result["selected_checks"]
    )


def test_s05_anchor_paths_select_stage_breakpoint_suites(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(
            tmp_path,
            "tests/test_s05b_weak_positive_breakpoint_suite.py",
            "tests/test_s05a_schema_provenance_breakpoint_suite.py",
            "tests/test_s05c_verified_read_extraction_breakpoint_suite.py",
        ),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    selected = {
        check["breakpoint_family"]: check
        for check in result["selected_checks"]
        if check.get("breakpoint_scope", "").startswith("S-05")
    }
    assert selected["weak-positive non-promotion"]["current_tier"] == "Tier 2"
    assert selected["weak-positive non-promotion"]["ownership_type"] == "stage-owned"
    assert selected["schema provenance"]["breakpoint_scope"] == "S-05A schema_backfill"
    assert selected["schema provenance"]["target_tier"] == "Tier 3"
    assert selected["verified-read extraction"]["breakpoint_scope"] == "S-05C read_to_write_chaining"
    assert selected["verified-read extraction"]["claim_ceiling"] == (
        "S-05C extracts write-retry values only from verified read evidence under medium MC-5 pressure"
    )


def test_s05b_s05c_seam_path_selects_verified_to_chaining_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(
            tmp_path,
            "tests/test_s05b_s05c_verified_to_chaining_seam_breakpoint_suite.py",
        ),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s05b_s05c_verified_to_chaining_seam_breakpoint_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s05b_s05c_verified_to_chaining_seam_breakpoint_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-05B -> S-05C"
    assert selected[0]["ownership_type"] == "seam-owned"
    assert selected[0]["breakpoint_family"] == "verified-to-chaining boundary"
    assert selected[0]["current_tier"] == "Tier 2"
    assert selected[0]["target_tier"] == "Tier 3"
    assert (
        selected[0]["claim_ceiling"]
        == "S-05C chains only from S-05B-verified read evidence under medium seam pressure"
    )


def test_s05_full_family_path_selects_baseline_breakpoint_suite(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(
            tmp_path,
            "tests/test_s05_full_family_tier2_baseline_suite.py",
        ),
        output_root=tmp_path / "out",
        execute=False,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert any(
        system["system_id"] == "s05_full_family_tier2_baseline_suite"
        for system in result["affected_systems"]
    )
    selected = [
        check
        for check in result["selected_checks"]
        if "s05_full_family_tier2_baseline_suite_tests" in check["check_ids"]
    ]
    assert selected
    assert selected[0]["breakpoint_scope"] == "S-05 full family baseline"
    assert selected[0]["ownership_type"] == "mixed stage/seam/bottom-up"
    assert selected[0]["breakpoint_family"] == "full S-05 Tier 2 baseline"
    assert selected[0]["current_tier"] == "mixed Tier 2 with blocked_at_tier2 and deferred rows"
    assert selected[0]["target_tier"] == "Tier 2"
    assert (
        selected[0]["claim_ceiling"]
        == "Family-specific S-05 Tier 2 evidence only; blocked and deferred rows are not promoted"
    )
    metadata_by_family = {
        row["breakpoint_family"]: row
        for check in result["selected_checks"]
        for row in check["breakpoint_metadata"]
    }
    assert metadata_by_family["state-effect verification"]["current_tier"] == "blocked_at_tier2"
    assert metadata_by_family["retry containment"]["current_tier"] == "blocked_at_tier2"
    assert metadata_by_family["weak-ID/value overtrust"]["current_tier"] == "deferred_as_tier3_shaped"
    assert metadata_by_family["S-05A -> S-05B -> S-05C; S-04 -> S-05A -> S-05B; S-05B -> S-05C -> S-06"][
        "ownership_type"
    ] == "bottom-up window"


def test_unrelated_changed_path_noops_cleanly(tmp_path: Path) -> None:
    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "docs/not-a-breakpoint.md"),
        output_root=tmp_path / "out",
        execute=True,
    )

    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert result["selected_checks"] == []
    assert result["executions"] == []
    assert "none selected" in (tmp_path / "out" / run_stage_breakpoint_checks.SUMMARY_NAME).read_text(
        encoding="utf-8"
    )


def test_stage_breakpoint_execution_pass_and_fail_are_captured(tmp_path: Path) -> None:
    pass_script = tmp_path / "pass_check.py"
    fail_script = tmp_path / "fail_check.py"
    pass_script.write_text("print('stage ok')\n", encoding="utf-8")
    fail_script.write_text("import sys\nprint('stage bad')\nsys.exit(9)\n", encoding="utf-8")

    pass_registry = _minimal_registry(tmp_path / "pass", command=f'"{sys.executable}" "{pass_script}"')
    pass_result, pass_exit = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path / "pass", "example/stage/file.py"),
        output_root=tmp_path / "pass-out",
        registry_path=pass_registry,
        execute=True,
    )
    fail_registry = _minimal_registry(tmp_path / "fail", command=f'"{sys.executable}" "{fail_script}"')
    fail_result, fail_exit = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path / "fail", "example/stage/file.py"),
        output_root=tmp_path / "fail-out",
        registry_path=fail_registry,
        execute=True,
    )

    assert pass_exit == 0
    assert pass_result["executions"][0]["verdict"] == "pass"
    assert "stage ok" in pass_result["executions"][0]["stdout_tail"]
    assert pass_result["selected_checks"][0]["breakpoint_scope"] == "S-00X example"
    assert pass_result["selected_checks"][0]["breakpoint_metadata"][0]["breakpoint_scope"] == "S-00X example"
    assert "scope=`S-00X example`" in (
        tmp_path / "pass-out" / run_stage_breakpoint_checks.SUMMARY_NAME
    ).read_text(encoding="utf-8")
    assert fail_exit == 1
    assert fail_result["executions"][0]["verdict"] == "fail"
    assert fail_result["executions"][0]["exit_code"] == 9
    assert fail_result["verdict"] == "fail"


def test_grouped_commands_preserve_each_breakpoint_metadata(tmp_path: Path) -> None:
    command = f'"{sys.executable}" -c "print(1)"'
    registry_path = _minimal_registry(tmp_path, command=command)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["checks"].append(
        {
            "check_id": "example_stage_breakpoint_second_tests",
            "system_id": "example_stage_breakpoint",
            "category": "stage_breakpoint",
            "command": command,
            "blocking": True,
            "expected_runtime_seconds": 5,
            "when_required": "example stage changes",
            "breakpoint_scope": "S-00Y example",
            "ownership_type": "stage-owned",
            "breakpoint_family": "second pressure",
            "current_tier": "Tier 1",
            "target_tier": "Tier 2",
            "claim_ceiling": "second stage breakpoint only",
        }
    )
    _write_json(registry_path, registry)

    result, exit_code = run_stage_breakpoint_checks.run_stage_breakpoint_checks(
        paths_file=_paths_file(tmp_path, "example/stage/file.py"),
        output_root=tmp_path / "out",
        registry_path=registry_path,
        execute=False,
    )

    assert exit_code == 0
    assert len(result["selected_checks"]) == 1
    metadata = result["selected_checks"][0]["breakpoint_metadata"]
    assert [row["breakpoint_scope"] for row in metadata] == ["S-00X example", "S-00Y example"]
    summary = (tmp_path / "out" / run_stage_breakpoint_checks.SUMMARY_NAME).read_text(encoding="utf-8")
    assert "scope=`S-00X example`" in summary
    assert "scope=`S-00Y example`" in summary
