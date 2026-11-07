from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CLAIM_CEILING = "analyzer_runtime_target_local_classification_only"


def _read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _phase_names(runtime: dict[str, Any]) -> list[str]:
    rows = runtime.get("phase_history")
    if not isinstance(rows, list):
        return []
    return [str(row.get("phase") or "") for row in rows if isinstance(row, dict)]


def _runtime_from_run_dir(run_dir: Path) -> dict[str, Any]:
    runtime = _dict(_read_json_if_exists(run_dir / "analyzer-runtime-authority.json"))
    if runtime:
        return runtime
    job_status = _dict(_read_json_if_exists(run_dir / "job-status-analyze.json"))
    return _dict(job_status.get("analyzer_runtime_authority"))


def _job_status_from_run_result(run_result: dict[str, Any]) -> dict[str, Any]:
    snapshot = _dict(run_result.get("job_status_snapshot"))
    if snapshot:
        return snapshot
    payload = _dict(run_result.get("status_payload"))
    return payload


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _runtime_packet(runtime: dict[str, Any]) -> dict[str, Any]:
    phases = _phase_names(runtime)
    embedded = _dict(runtime.get("embedded_authority"))
    embedded_phases = _phase_names(embedded)
    return {
        "state": str(runtime.get("status") or ""),
        "reason_code": str(runtime.get("reason_code") or ""),
        "runtime_phase": str(runtime.get("runtime_phase") or runtime.get("phase") or ""),
        "embedded_runtime_phase": str(embedded.get("runtime_phase") or embedded.get("phase") or ""),
        "phase_history_tail": phases[-5:],
        "embedded_phase_history_tail": embedded_phases[-5:],
        "status_progress": _int(runtime.get("status_progress")),
        "status_message": str(runtime.get("status_message") or ""),
        "bridge_attempted": bool(runtime.get("bridge_attempted")),
        "ghidra_entered": bool(runtime.get("ghidra_entered")),
        "ghidra_exited": bool(runtime.get("ghidra_exited")),
        "output_file_count": _int(runtime.get("output_file_count")),
        "parent_wait_returned": "discovery_child_wait_returned" in phases,
        "returncode_observed": "discovery_child_returncode_observed" in phases,
        "output_scan_completed": "discovery_output_scan_completed" in phases,
    }


def _terminal_packet(run_result: dict[str, Any], measurement: dict[str, Any]) -> dict[str, Any]:
    authority = _dict(run_result.get("run_authority"))
    validity = _dict(run_result.get("run_validity"))
    return {
        "state": str(run_result.get("status") or ""),
        "phase": str(run_result.get("phase") or ""),
        "valid_run": bool(run_result.get("valid_run")),
        "run_validity_reason": str(validity.get("reason") or ""),
        "authority_level": str(authority.get("authority_level") or ""),
        "authoritative_proving": bool(authority.get("authoritative_proving")),
        "safe_to_steer_next_prompt": bool(authority.get("safe_to_steer_next_prompt")),
        "terminalization_kind": str(authority.get("terminalization_kind") or ""),
        "blocking_reasons": list(authority.get("blocking_reasons") or []),
        "measurement_status": str(measurement.get("status") or ""),
        "measurement_next_action": str(measurement.get("next_action") or ""),
    }


def _public_status_packet(job_status: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": str(job_status.get("status") or ""),
        "progress": _int(job_status.get("progress") or runtime.get("status_progress")),
        "message": str(job_status.get("message") or runtime.get("status_message") or ""),
    }


def _input_completeness(
    *,
    run_result: dict[str, Any],
    measurement: dict[str, Any],
    runtime: dict[str, Any],
    public_status: dict[str, Any],
) -> dict[str, Any]:
    terminal_authority = _dict(run_result.get("run_authority"))
    required = {
        "run_result": bool(run_result),
        "analyzer_runtime_authority": bool(runtime),
        "public_status": bool(public_status),
        "terminal_authority": bool(terminal_authority),
    }
    supporting = {
        "measurement_terminalization": bool(measurement),
    }
    missing_required = sorted(name for name, present in required.items() if not present)
    return {
        "required": required,
        "supporting": supporting,
        "missing_required": missing_required,
        "required_complete": not missing_required,
        "classification_support_level": (
            "supported_by_required_artifacts" if not missing_required else "insufficient_required_artifacts"
        ),
    }


def _target_signal(target: str, suffix: str) -> str:
    normalized = str(target or "").strip().replace("-", "_")
    if not normalized:
        normalized = "unknown_target"
    return f"{normalized}_{suffix}"


def _classify(
    *,
    target: str,
    runtime_packet: dict[str, Any],
    terminal_packet: dict[str, Any],
    public_status_packet: dict[str, Any],
) -> tuple[str, str, str]:
    terminal_authority_reconciled = (
        str(terminal_packet.get("authority_level") or "") == "decision_bearing"
        and bool(terminal_packet.get("authoritative_proving"))
        and bool(terminal_packet.get("valid_run"))
        and str(terminal_packet.get("terminalization_kind") or "") == "done"
        and not terminal_packet.get("blocking_reasons")
    )
    if terminal_authority_reconciled:
        return (
            "authority_completion_reconciled",
            "",
            "authority completion is reconciled for this target-local run; use broader proof only if separately authorized",
        )
    output_present = _int(runtime_packet.get("output_file_count")) > 0
    public_done = (
        str(public_status_packet.get("state") or "") == "done"
        or _int(public_status_packet.get("progress")) >= 100
    )
    terminal_timeout = str(terminal_packet.get("terminalization_kind") or "") == "timeout"
    non_authoritative = str(terminal_packet.get("authority_level") or "") == "non_authoritative"
    bridge_attempted = bool(runtime_packet.get("bridge_attempted"))
    ghidra_entered = bool(runtime_packet.get("ghidra_entered"))
    runtime_phase = str(runtime_packet.get("runtime_phase") or "")
    embedded_phase = str(runtime_packet.get("embedded_runtime_phase") or "")
    runtime_reason = str(runtime_packet.get("reason_code") or "")

    if runtime_reason == "analyze_api_read_timeout" and non_authoritative:
        return (
            "analyze_api_read_timeout_before_runtime_entry",
            _target_signal(target, "analyze_api_read_timeout_before_runtime_entry"),
            "repair or bound the API analyze launch/read timeout before another full Hard03 attempt",
        )
    if public_done and output_present and terminal_timeout and non_authoritative:
        return (
            "false_done_status_without_authority_completion",
            _target_signal(target, "false_done_status_without_authority_completion"),
            "add or repair the smallest authority packet that reconciles done status, verdict persistence, and session capture before rerun",
        )
    if bridge_attempted and not ghidra_entered and (runtime_phase == "bridge_pending" or embedded_phase == "bridge_pending"):
        return (
            "bridge_pending_without_ghidra_entry_after_output",
            _target_signal(target, "bridge_pending_without_ghidra_entry_after_output"),
            "isolate bridge pending to Ghidra entry or bridge result persistence before rerun",
        )
    if output_present and terminal_timeout:
        return (
            "analyzer_post_output_timeout",
            _target_signal(target, "analyzer_post_output_timeout"),
            "isolate post-output analyzer timeout and terminal authority persistence before rerun",
        )
    if non_authoritative and "verdict_status_missing" in terminal_packet.get("blocking_reasons", []):
        return (
            "missing_terminal_semantic_writeback",
            _target_signal(target, "missing_terminal_semantic_writeback"),
            "repair verdict or semantic writeback authority before rerun",
        )
    return (
        "analyzer_runtime_boundary_unclassified",
        "non_comparable_analyzer_runtime_stall",
        "collect a richer analyzer-runtime boundary packet before rerun",
    )


def classify_analyzer_runtime_boundary(*, run_dir: Path, output_root: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    output_root = output_root.resolve()
    run_result = _dict(_read_json_if_exists(run_dir / "run_result.json"))
    measurement = _dict(_read_json_if_exists(run_dir / "measurement-terminalization.json"))
    runtime = _runtime_from_run_dir(run_dir)
    public_status = _job_status_from_run_result(run_result)
    if not public_status:
        public_status = _dict(_read_json_if_exists(run_dir / "job-status-analyze.json"))

    input_completeness = _input_completeness(
        run_result=run_result,
        measurement=measurement,
        runtime=runtime,
        public_status=public_status,
    )
    target = str(run_result.get("target") or runtime.get("target") or "")
    runtime_boundary = _runtime_packet(runtime)
    terminal_boundary = _terminal_packet(run_result, measurement)
    public_status_boundary = _public_status_packet(public_status, runtime)
    if input_completeness["required_complete"]:
        classification, sharp_signal, next_action = _classify(
            target=target,
            runtime_packet=runtime_boundary,
            terminal_packet=terminal_boundary,
            public_status_packet=public_status_boundary,
        )
        status = "classified"
    else:
        classification = "analyzer_runtime_boundary_inputs_missing"
        sharp_signal = "non_comparable_analyzer_runtime_stall"
        next_action = "collect required analyzer-runtime, public-status, run-result, and terminal-authority packets before classification"
        status = "failed_closed"
    result = {
        "schema_version": "1.0.0",
        "claim_ceiling": CLAIM_CEILING,
        "product_green_claimed": False,
        "safe_to_compare": False,
        "run_dir": str(run_dir),
        "target": target,
        "job_id": str(run_result.get("job_id") or public_status.get("job_id") or runtime.get("job_id") or ""),
        "status": status,
        "parent_signal": "non_comparable_analyzer_runtime_stall",
        "classification": classification,
        "sharp_signal": sharp_signal,
        "decision_bearing_blocker": sharp_signal,
        "input_completeness": input_completeness,
        "classification_precedence": "operator_decision_bearing_contradiction_over_runtime_root_cause",
        "runtime_boundary": runtime_boundary,
        "public_status_boundary": public_status_boundary,
        "terminal_authority_boundary": terminal_boundary,
        "next_action": next_action,
    }
    _write_json(output_root / "analyzer-runtime-boundary-classification.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify analyzer-runtime boundary artifacts.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    result = classify_analyzer_runtime_boundary(run_dir=args.run_dir, output_root=args.output_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "classified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
