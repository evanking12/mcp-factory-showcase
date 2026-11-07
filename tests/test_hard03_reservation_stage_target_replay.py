from __future__ import annotations

import json
from pathlib import Path

from scripts.regression.replay_hard03_reservation_stage_target import (
    replay_hard03_reservation_stage_target,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_missing_source_root_fails_closed(tmp_path: Path) -> None:
    output_root = tmp_path / "out"

    result = replay_hard03_reservation_stage_target(
        source_proof_root=tmp_path / "missing",
        output_root=output_root,
    )

    assert result["classification"] == "trusted_predecessor_boundary_unavailable"
    assert result["claim_ceiling"] == "target_local_replay_only"
    assert result["product_green_claimed"] is False
    assert (output_root / "target-local-replay-result.json").exists()


def test_classifies_child_wrapper_wait_return_from_source_artifacts(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_dir = source_root / "runs" / "02-reservation_stage"
    output_root = tmp_path / "out"

    _write_json(
        target_dir / "analyzer-runtime-authority.json",
        {
            "reason_code": "child_wrapper_wait_return_missing",
            "phase_history": [
                {"phase": "discovery_child_started"},
                {"phase": "discovery_child_wait_start"},
            ],
            "child_runtime_phase": "bootstrap_main_returned",
            "child_runtime_diagnostic": {
                "phase": "bootstrap_main_returned",
                "last_observation": {"returncode": 0},
            },
            "bridge_attempted": False,
        },
    )
    _write_json(target_dir / "measurement-terminalization.json", {"reason_code": "analyzer_timeout"})
    _write_json(source_root / "enterprise-survivability-summary.json", {"targets": []})
    before = sorted(str(path.relative_to(source_root)) for path in source_root.rglob("*"))

    result = replay_hard03_reservation_stage_target(
        source_proof_root=source_root,
        output_root=output_root,
    )

    after = sorted(str(path.relative_to(source_root)) for path in source_root.rglob("*"))
    assert after == before
    assert result["classification"] == "child_wrapper_wait_return_missing"
    assert result["parent_wait_started"] is True
    assert result["parent_wait_returned"] is False
    assert result["child_runtime_phase"] == "bootstrap_main_returned"
    assert result["child_returncode"] == 0
    assert result["current_code_recovery_path_present"] is True
    assert result["claim_ceiling"] == "target_local_replay_only"
    assert result["product_green_claimed"] is False


def test_classifies_returncode_and_output_scan_boundaries(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_dir = source_root / "runs" / "02-reservation_stage"

    _write_json(
        target_dir / "analyzer-runtime-authority.json",
        {
            "phase_history": [
                {"phase": "discovery_child_started"},
                {"phase": "discovery_child_wait_start"},
                {"phase": "discovery_child_wait_returned"},
            ],
        },
    )
    _write_json(target_dir / "measurement-terminalization.json", {"reason_code": "analyzer_timeout"})
    result = replay_hard03_reservation_stage_target(
        source_proof_root=source_root,
        output_root=tmp_path / "out-returncode",
    )
    assert result["classification"] == "child_returncode_observation_missing"

    _write_json(
        target_dir / "analyzer-runtime-authority.json",
        {
            "phase_history": [
                {"phase": "discovery_child_started"},
                {"phase": "discovery_child_wait_start"},
                {"phase": "discovery_child_wait_returned"},
                {"phase": "discovery_child_returncode_observed"},
            ],
            "child_returncode": 0,
        },
    )
    result = replay_hard03_reservation_stage_target(
        source_proof_root=source_root,
        output_root=tmp_path / "out-scan",
    )
    assert result["classification"] == "child_output_scan_missing"


def test_classifies_completed_no_output_boundary(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_dir = source_root / "runs" / "02-reservation_stage"
    _write_json(
        target_dir / "analyzer-runtime-authority.json",
        {
            "phase_history": [
                {"phase": "discovery_child_started"},
                {"phase": "discovery_child_wait_start"},
                {"phase": "discovery_child_wait_returned"},
                {"phase": "discovery_child_returncode_observed"},
                {"phase": "discovery_output_scan_started"},
                {"phase": "discovery_output_scan_completed"},
            ],
            "output_file_count": 0,
        },
    )
    _write_json(target_dir / "measurement-terminalization.json", {"reason_code": "analyzer_timeout"})

    result = replay_hard03_reservation_stage_target(
        source_proof_root=source_root,
        output_root=tmp_path / "out",
    )

    assert result["classification"] == "child_completed_no_output"
    assert result["product_green_claimed"] is False


def test_discovery_empty_preserves_producer_subreason_from_current_run_authority(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_dir = source_root / "runs" / "02-reservation_stage"
    output_root = tmp_path / "out"

    _write_json(
        target_dir / "measurement-terminalization.json",
        {
            "reason_code": "discovery_empty",
            "safe_to_compare": False,
        },
    )
    _write_json(
        target_dir / "run-authority.json",
        {
            "authoritative_proving": False,
            "safe_to_steer_next_prompt": False,
            "blocking_reasons": ["discovery_empty"],
        },
    )
    _write_json(
        target_dir / "run_result.json",
        {
            "status_payload": {
                "analyzer_runtime_authority": {
                    "phase_history": [
                        {"phase": "discovery_child_wait_start"},
                        {"phase": "discovery_child_wait_returned"},
                        {"phase": "discovery_child_returncode_observed"},
                        {"phase": "discovery_output_scan_completed"},
                    ],
                    "output_file_count": 0,
                    "bridge_attempted": False,
                },
                "discovery_output_authority": {
                    "reason_code": "child_python_startup_interrupt",
                    "owner": "discovery_child_python_startup",
                    "safe_to_compare": False,
                    "ghidra_entered": False,
                    "discovery_file_count": 0,
                    "invocable_count": 0,
                    "subprocess_returncode": 3221225786,
                    "subprocess_keyboard_interrupt": True,
                    "subprocess_interrupt_diagnostics": {
                        "subreason_code": "child_python_startup_interrupt",
                        "source_reason_code": "child_bootstrap_entry_missing",
                        "classification_precision": "precise",
                    },
                    "next_action": "stabilize child interpreter startup",
                },
                "analyzer_authority": {
                    "reason_code": "discovery_empty",
                    "producer_reason_code": "child_python_startup_interrupt",
                    "producer_owner": "discovery_child_python_startup",
                },
            }
        },
    )

    result = replay_hard03_reservation_stage_target(
        source_proof_root=source_root,
        output_root=output_root,
    )

    assert result["classification"] == "discovery_empty"
    assert result["decision_bearing_blocker"] == "discovery_empty"
    assert result["producer_authority_present"] is True
    assert result["producer_reason_code"] == "child_python_startup_interrupt"
    assert result["producer_subreason_signal"] == "child_python_startup_interrupt"
    assert result["producer_source_reason_code"] == "child_bootstrap_entry_missing"
    assert result["producer_classification_precision"] == "precise"
    assert result["producer_subreason_status"] == "branch_steering"
    assert result["producer_subreason_decision_bearing"] is True
    assert result["producer_subreason_branch_steering_authority"] is True
    assert result["producer_subreason_authority_scope"] == "blocker_repair_routing_only_not_product_proof"
    assert result["safe_to_steer_next_prompt"] is False
    assert result["product_green_claimed"] is False
    assert "child_python_startup_interrupt" in result["next_action"]


def test_incomplete_startup_interrupt_context_remains_diagnostic_only(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_dir = source_root / "runs" / "02-reservation_stage"

    _write_json(target_dir / "measurement-terminalization.json", {"reason_code": "discovery_empty"})
    _write_json(
        target_dir / "run_result.json",
        {
            "status_payload": {
                "discovery_output_authority": {
                    "reason_code": "child_python_startup_interrupt",
                    "owner": "discovery_child_python_startup",
                    "safe_to_compare": False,
                    "ghidra_entered": False,
                    "discovery_file_count": 0,
                    "invocable_count": 0,
                    "subprocess_returncode": 3221225786,
                    "subprocess_keyboard_interrupt": True,
                    "subprocess_interrupt_diagnostics": {
                        "subreason_code": "child_python_startup_interrupt",
                        "source_reason_code": "child_bootstrap_entry_missing",
                        "classification_precision": "medium",
                    },
                }
            }
        },
    )

    result = replay_hard03_reservation_stage_target(
        source_proof_root=source_root,
        output_root=tmp_path / "out",
    )

    assert result["classification"] == "discovery_empty"
    assert result["producer_subreason_status"] == "diagnostic_only"
    assert result["producer_subreason_decision_bearing"] is False
    assert result["producer_subreason_branch_steering_authority"] is False


def test_discovery_empty_without_producer_authority_stays_parent_classification(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_dir = source_root / "runs" / "02-reservation_stage"

    _write_json(target_dir / "measurement-terminalization.json", {"reason_code": "discovery_empty"})
    _write_json(
        target_dir / "analyzer-authority.json",
        {
            "reason_code": "discovery_empty",
            "safe_to_compare": False,
        },
    )

    result = replay_hard03_reservation_stage_target(
        source_proof_root=source_root,
        output_root=tmp_path / "out",
    )

    assert result["classification"] == "discovery_empty"
    assert result["producer_authority_present"] is False
    assert result["producer_subreason_status"] == "missing"
    assert result["producer_subreason_decision_bearing"] is False
