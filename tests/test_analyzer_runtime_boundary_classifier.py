from __future__ import annotations

import json
from pathlib import Path

from scripts.regression.classify_analyzer_runtime_boundary import classify_analyzer_runtime_boundary


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _base_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "04-fee_quote"
    _write_json(
        run_dir / "run_result.json",
        {
            "target": "fee_quote",
            "job_id": "fee-job",
            "status": "failed",
            "phase": "analyze",
            "valid_run": False,
            "run_validity": {"reason": "measurement_terminalized_analyzer_timeout"},
            "job_status_snapshot": {
                "job_id": "fee-job",
                "status": "done",
                "progress": 100,
                "message": "Analysis complete - 2 invocables found",
            },
            "run_authority": {
                "authority_level": "non_authoritative",
                "authoritative_proving": False,
                "safe_to_steer_next_prompt": False,
                "terminalization_kind": "timeout",
                "blocking_reasons": [
                    "terminalization_kind_timeout",
                    "verdict_status_missing",
                    "session_capture_incomplete",
                ],
            },
        },
    )
    _write_json(
        run_dir / "measurement-terminalization.json",
        {
            "status": "non_comparable_failure",
            "next_action": "isolate analyzer stall or timeout behavior",
        },
    )
    return run_dir


def test_classifier_names_false_done_without_authority_completion(tmp_path: Path) -> None:
    run_dir = _base_run_dir(tmp_path)
    _write_json(
        run_dir / "analyzer-runtime-authority.json",
        {
            "status": "non_comparable_analyzer_runtime_stall",
            "reason_code": "unknown_analyzer_runtime_stall",
            "runtime_phase": "bridge_pending",
            "status_progress": 100,
            "status_message": "Analysis complete - 2 invocables found",
            "bridge_attempted": True,
            "ghidra_entered": False,
            "output_file_count": 1,
            "phase_history": [
                {"phase": "discovery_child_wait_returned"},
                {"phase": "discovery_child_returncode_observed"},
                {"phase": "discovery_output_scan_completed"},
            ],
        },
    )

    result = classify_analyzer_runtime_boundary(run_dir=run_dir, output_root=tmp_path / "out")

    assert result["classification"] == "false_done_status_without_authority_completion"
    assert result["sharp_signal"] == "fee_quote_false_done_status_without_authority_completion"
    assert result["safe_to_compare"] is False
    assert result["product_green_claimed"] is False
    assert result["runtime_boundary"]["output_file_count"] == 1
    assert result["public_status_boundary"]["state"] == "done"
    assert result["terminal_authority_boundary"]["terminalization_kind"] == "timeout"
    assert result["input_completeness"]["required_complete"] is True
    assert (
        result["input_completeness"]["classification_support_level"]
        == "supported_by_required_artifacts"
    )
    assert (
        result["classification_precedence"]
        == "operator_decision_bearing_contradiction_over_runtime_root_cause"
    )
    assert (tmp_path / "out" / "analyzer-runtime-boundary-classification.json").exists()


def test_classifier_names_false_done_for_reservation_stage(tmp_path: Path) -> None:
    run_dir = _base_run_dir(tmp_path)
    run_result = json.loads((run_dir / "run_result.json").read_text(encoding="utf-8"))
    run_result["target"] = "reservation_stage"
    run_result["job_id"] = "reservation-job"
    run_result["job_status_snapshot"]["job_id"] = "reservation-job"
    _write_json(run_dir / "run_result.json", run_result)
    _write_json(
        run_dir / "analyzer-runtime-authority.json",
        {
            "status": "non_comparable_analyzer_runtime_stall",
            "runtime_phase": "bridge_pending",
            "status_progress": 60,
            "status_message": "Analysis complete - 2 invocables found",
            "bridge_attempted": True,
            "ghidra_entered": False,
            "output_file_count": 1,
            "phase_history": [
                {"phase": "discovery_child_wait_returned"},
                {"phase": "discovery_child_returncode_observed"},
                {"phase": "discovery_output_scan_completed"},
            ],
        },
    )

    result = classify_analyzer_runtime_boundary(run_dir=run_dir, output_root=tmp_path / "out")

    assert result["target"] == "reservation_stage"
    assert result["classification"] == "false_done_status_without_authority_completion"
    assert (
        result["sharp_signal"]
        == "reservation_stage_false_done_status_without_authority_completion"
    )


def test_classifier_names_bridge_pending_when_public_done_is_absent(tmp_path: Path) -> None:
    run_dir = _base_run_dir(tmp_path)
    run_result = json.loads((run_dir / "run_result.json").read_text(encoding="utf-8"))
    run_result["job_status_snapshot"] = {"status": "running", "progress": 60, "message": "calling bridge"}
    _write_json(run_dir / "run_result.json", run_result)
    _write_json(
        run_dir / "analyzer-runtime-authority.json",
        {
            "runtime_phase": "bridge_pending",
            "bridge_attempted": True,
            "ghidra_entered": False,
            "output_file_count": 1,
        },
    )

    result = classify_analyzer_runtime_boundary(run_dir=run_dir, output_root=tmp_path / "out")

    assert result["classification"] == "bridge_pending_without_ghidra_entry_after_output"
    assert result["sharp_signal"] == "fee_quote_bridge_pending_without_ghidra_entry_after_output"


def test_classifier_names_missing_terminal_semantic_writeback(tmp_path: Path) -> None:
    run_dir = _base_run_dir(tmp_path)
    run_result = json.loads((run_dir / "run_result.json").read_text(encoding="utf-8"))
    run_result["job_status_snapshot"] = {"status": "running", "progress": 80, "message": "post analyzer"}
    run_result["run_authority"]["terminalization_kind"] = "error"
    _write_json(run_dir / "run_result.json", run_result)
    _write_json(
        run_dir / "analyzer-runtime-authority.json",
        {
            "runtime_phase": "post_output",
            "bridge_attempted": False,
            "ghidra_entered": False,
            "output_file_count": 0,
        },
    )

    result = classify_analyzer_runtime_boundary(run_dir=run_dir, output_root=tmp_path / "out")

    assert result["classification"] == "missing_terminal_semantic_writeback"
    assert result["sharp_signal"] == "fee_quote_missing_terminal_semantic_writeback"


def test_classifier_names_analyze_api_read_timeout_before_runtime_entry(tmp_path: Path) -> None:
    run_dir = _base_run_dir(tmp_path)
    run_result = json.loads((run_dir / "run_result.json").read_text(encoding="utf-8"))
    run_result["target"] = "reservation_stage"
    run_result["job_id"] = ""
    run_result["job_status_snapshot"] = {
        "status": "error",
        "error": "HTTPConnectionPool(host='127.0.0.1', port=8201): Read timed out. (read timeout=180)",
    }
    run_result["run_authority"]["terminalization_kind"] = "error"
    run_result["run_validity"] = {"reason": "measurement_terminalized_analyzer_error"}
    _write_json(run_dir / "run_result.json", run_result)
    _write_json(
        run_dir / "analyzer-runtime-authority.json",
        {
            "status": "non_comparable_analyze_launch_error",
            "reason_code": "analyze_api_read_timeout",
            "owner": "api_analyze_launch",
            "runtime_phase": "",
            "status_progress": 0,
            "status_message": "HTTPConnectionPool: Read timed out",
            "bridge_attempted": False,
            "ghidra_entered": False,
            "output_file_count": 0,
        },
    )

    result = classify_analyzer_runtime_boundary(run_dir=run_dir, output_root=tmp_path / "out")

    assert result["status"] == "classified"
    assert result["classification"] == "analyze_api_read_timeout_before_runtime_entry"
    assert (
        result["sharp_signal"]
        == "reservation_stage_analyze_api_read_timeout_before_runtime_entry"
    )
    assert result["runtime_boundary"]["reason_code"] == "analyze_api_read_timeout"


def test_classifier_fails_closed_when_required_packets_are_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "04-fee_quote"
    _write_json(run_dir / "measurement-terminalization.json", {"status": "non_comparable_failure"})

    result = classify_analyzer_runtime_boundary(run_dir=run_dir, output_root=tmp_path / "out")

    assert result["status"] == "failed_closed"
    assert result["classification"] == "analyzer_runtime_boundary_inputs_missing"
    assert result["decision_bearing_blocker"] == "non_comparable_analyzer_runtime_stall"
    assert result["input_completeness"]["required_complete"] is False
    assert result["input_completeness"]["classification_support_level"] == "insufficient_required_artifacts"
    assert result["input_completeness"]["missing_required"] == [
        "analyzer_runtime_authority",
        "public_status",
        "run_result",
        "terminal_authority",
    ]


def test_classifier_does_not_route_stale_runtime_when_terminal_authority_is_clean(
    tmp_path: Path,
) -> None:
    run_dir = _base_run_dir(tmp_path)
    run_result = json.loads((run_dir / "run_result.json").read_text(encoding="utf-8"))
    run_result["status"] = "ok"
    run_result["valid_run"] = True
    run_result["run_validity"] = {"valid": True, "reason": ""}
    run_result["job_status_snapshot"] = {"status": "done", "progress": 60, "message": "bridge pending"}
    run_result["run_authority"] = {
        "authority_level": "decision_bearing",
        "authoritative_proving": True,
        "safe_to_steer_next_prompt": True,
        "terminalization_kind": "done",
        "blocking_reasons": [],
    }
    _write_json(run_dir / "run_result.json", run_result)
    _write_json(
        run_dir / "analyzer-runtime-authority.json",
        {
            "runtime_phase": "bridge_pending",
            "bridge_attempted": True,
            "ghidra_entered": False,
            "output_file_count": 1,
        },
    )

    result = classify_analyzer_runtime_boundary(run_dir=run_dir, output_root=tmp_path / "out")

    assert result["classification"] == "authority_completion_reconciled"
    assert result["sharp_signal"] == ""
    assert result["decision_bearing_blocker"] == ""
    assert result["terminal_authority_boundary"]["authority_level"] == "decision_bearing"
