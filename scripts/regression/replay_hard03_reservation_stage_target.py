from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.regression.summarize_product_proof_artifacts import summarize_product_proof_artifacts


TARGET = "reservation_stage"
CLAIM_CEILING = "target_local_replay_only"


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return _read_json(path)


def _target_dir(proof_root: Path, target: str = TARGET) -> Path | None:
    runs_root = proof_root / "runs"
    if not runs_root.exists():
        return None
    for candidate in sorted(runs_root.iterdir()):
        if candidate.is_dir() and candidate.name.endswith(f"-{target}"):
            return candidate
    return None


def _status_payload(target_dir: Path) -> dict[str, Any]:
    run_result = _read_json_if_exists(target_dir / "run_result.json")
    if not isinstance(run_result, dict):
        return {}
    payload = run_result.get("status_payload")
    if isinstance(payload, dict):
        return payload
    snapshot = run_result.get("job_status_snapshot")
    if isinstance(snapshot, dict):
        return snapshot
    return {}


def _embedded_authority(target_dir: Path, field: str) -> dict[str, Any]:
    payload = _status_payload(target_dir)
    value = payload.get(field)
    if isinstance(value, dict):
        return value
    return {}


def _authority_from_file_or_status(target_dir: Path, filename: str, status_field: str) -> dict[str, Any]:
    from_file = _read_json_if_exists(target_dir / filename)
    if isinstance(from_file, dict):
        return from_file
    return _embedded_authority(target_dir, status_field)


def _subprocess_interrupt_diagnostics(discovery_output: dict[str, Any]) -> dict[str, Any]:
    value = discovery_output.get("subprocess_interrupt_diagnostics")
    if isinstance(value, dict):
        return value
    return {}


def _int_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _producer_subreason_branch_steering_authority(
    *,
    classification: str,
    discovery_output: dict[str, Any],
    subprocess_diagnostics: dict[str, Any],
) -> bool:
    """Return whether a producer subreason can steer blocker repair only."""
    producer_reason = str(discovery_output.get("reason_code") or "")
    subreason = str(subprocess_diagnostics.get("subreason_code") or "")
    source_reason = str(subprocess_diagnostics.get("source_reason_code") or "")
    return bool(
        classification == "discovery_empty"
        and producer_reason == "child_python_startup_interrupt"
        and subreason == "child_python_startup_interrupt"
        and source_reason == "child_bootstrap_entry_missing"
        and str(subprocess_diagnostics.get("classification_precision") or "") == "precise"
        and _int_value(discovery_output.get("subprocess_returncode")) == 0xC000013A
        and bool(discovery_output.get("subprocess_keyboard_interrupt"))
        and int(discovery_output.get("discovery_file_count") or 0) == 0
        and int(discovery_output.get("invocable_count") or 0) == 0
        and not bool(discovery_output.get("ghidra_entered"))
    )


def _phase_names(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    return [str(row.get("phase") or "") for row in rows if isinstance(row, dict)]


def _current_code_recovery_present() -> bool:
    source = Path("api/services/discovery.py")
    if not source.exists():
        return False
    text = source.read_text(encoding="utf-8")
    required_fragments = (
        "def _communicate_discovery_child",
        "child_runtime_completed_no_output",
        "discovery_child_wait_returned",
        "discovery_child_returncode_observed",
        "discovery_output_scan_completed",
    )
    return all(fragment in text for fragment in required_fragments)


def _classify(runtime: dict[str, Any], measurement: dict[str, Any]) -> str:
    phases = _phase_names(runtime.get("phase_history"))
    child_runtime = runtime.get("child_runtime_diagnostic") or {}
    child_phase = str(runtime.get("child_runtime_phase") or child_runtime.get("phase") or "")
    child_returncode = (child_runtime.get("last_observation") or {}).get("returncode")
    output_count = int(runtime.get("output_file_count") or 0)
    parent_signal = str(measurement.get("reason_code") or "")
    runtime_signal = str(runtime.get("reason_code") or "")

    if parent_signal == "discovery_empty":
        return "discovery_empty"
    if "discovery_child_wait_start" in phases and "discovery_child_wait_returned" not in phases:
        if child_phase == "bootstrap_main_returned" and child_returncode == 0:
            return "child_wrapper_wait_return_missing"
        return "child_wrapper_wait_return_missing"
    if "discovery_child_wait_returned" in phases and "discovery_child_returncode_observed" not in phases:
        return "child_returncode_observation_missing"
    if "discovery_child_returncode_observed" in phases and "discovery_output_scan_completed" not in phases:
        return "child_output_scan_missing"
    if "discovery_output_scan_completed" in phases and output_count == 0:
        return "child_completed_no_output"
    return runtime_signal or parent_signal or "hard03_reservation_stage_blocker_unclassified"


def replay_hard03_reservation_stage_target(
    *,
    source_proof_root: Path,
    output_root: Path,
    mode: str = "strict",
) -> dict[str, Any]:
    source_proof_root = source_proof_root.resolve()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    summary_path = output_root / "proof-artifact-summary.json"
    summary = summarize_product_proof_artifacts(
        proof_root=source_proof_root,
        target=TARGET,
        output=summary_path,
    )

    if not source_proof_root.exists():
        result = {
            "schema_version": "1.0.0",
            "mode": mode,
            "claim_ceiling": CLAIM_CEILING,
            "product_green_claimed": False,
            "source_proof_root": str(source_proof_root),
            "target": TARGET,
            "status": "failed_closed",
            "classification": "trusted_predecessor_boundary_unavailable",
            "reason": "source proof root missing",
            "source_root_mutated": False,
            "next_action": "provide an existing Hard03 proof root",
        }
        (output_root / "target-local-replay-result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return result

    target_dir = _target_dir(source_proof_root)
    runtime = _authority_from_file_or_status(
        target_dir,
        "analyzer-runtime-authority.json",
        "analyzer_runtime_authority",
    ) if target_dir else {}
    measurement = _read_json_if_exists(target_dir / "measurement-terminalization.json") if target_dir else None
    discovery_output = _authority_from_file_or_status(
        target_dir,
        "discovery-output-authority.json",
        "discovery_output_authority",
    ) if target_dir else {}
    analyzer_authority = _authority_from_file_or_status(
        target_dir,
        "analyzer-authority.json",
        "analyzer_authority",
    ) if target_dir else {}
    run_authority = _read_json_if_exists(target_dir / "run-authority.json") if target_dir else {}
    if not isinstance(run_authority, dict):
        run_authority = {}
    if not target_dir or not isinstance(measurement, dict) or not (
        isinstance(runtime, dict) and runtime
        or isinstance(discovery_output, dict) and discovery_output
        or isinstance(analyzer_authority, dict) and analyzer_authority
    ):
        result = {
            "schema_version": "1.0.0",
            "mode": mode,
            "claim_ceiling": CLAIM_CEILING,
            "product_green_claimed": False,
            "source_proof_root": str(source_proof_root),
            "target": TARGET,
            "target_dir": str(target_dir or ""),
            "status": "failed_closed",
            "classification": "trusted_predecessor_boundary_unavailable",
            "reason": "reservation_stage authority or terminalization artifacts missing",
            "source_root_mutated": False,
            "next_action": "rerun or rebuild a trusted Hard03 source proof before target-local classification",
        }
        (output_root / "target-local-replay-result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return result

    classification = _classify(runtime, measurement)
    phases = _phase_names(runtime.get("phase_history"))
    current_code_recovery_present = _current_code_recovery_present()
    child_runtime = runtime.get("child_runtime_diagnostic") or {}
    subprocess_diagnostics = _subprocess_interrupt_diagnostics(discovery_output)
    producer_reason = str(
        discovery_output.get("reason_code")
        or analyzer_authority.get("producer_reason_code")
        or ""
    )
    producer_owner = str(
        discovery_output.get("owner")
        or analyzer_authority.get("producer_owner")
        or ""
    )
    producer_subreason = str(subprocess_diagnostics.get("subreason_code") or producer_reason)
    producer_source_reason = str(subprocess_diagnostics.get("source_reason_code") or "")
    producer_authority_present = bool(discovery_output)
    producer_subreason_branch_steering_authority = _producer_subreason_branch_steering_authority(
        classification=classification,
        discovery_output=discovery_output,
        subprocess_diagnostics=subprocess_diagnostics,
    )
    producer_subreason_decision_bearing = producer_subreason_branch_steering_authority
    producer_subreason_status = (
        "branch_steering"
        if producer_subreason_branch_steering_authority
        else "diagnostic_only"
        if producer_reason
        else "missing"
    )
    decision_bearing_blocker = classification
    result = {
        "schema_version": "1.0.0",
        "mode": mode,
        "claim_ceiling": CLAIM_CEILING,
        "product_green_claimed": False,
        "source_proof_root": str(source_proof_root),
        "target": TARGET,
        "target_dir": str(target_dir),
        "status": "classified",
        "classification": classification,
        "decision_bearing_blocker": decision_bearing_blocker,
        "parent_signal": str(measurement.get("reason_code") or ""),
        "runtime_signal": str(runtime.get("reason_code") or ""),
        "producer_authority_present": producer_authority_present,
        "producer_reason_code": producer_reason,
        "producer_owner": producer_owner,
        "producer_subreason_signal": producer_subreason,
        "producer_source_reason_code": producer_source_reason,
        "producer_classification_precision": str(subprocess_diagnostics.get("classification_precision") or ""),
        "producer_subreason_status": producer_subreason_status,
        "producer_subreason_decision_bearing": producer_subreason_decision_bearing,
        "producer_subreason_branch_steering_authority": producer_subreason_branch_steering_authority,
        "producer_subreason_authority_scope": (
            "blocker_repair_routing_only_not_product_proof"
            if producer_subreason_branch_steering_authority
            else "diagnostic_only"
            if producer_reason
            else "missing"
        ),
        "producer_next_action": str(
            discovery_output.get("next_action")
            or subprocess_diagnostics.get("next_action")
            or ""
        ),
        "parent_wait_started": "discovery_child_wait_start" in phases,
        "parent_wait_returned": "discovery_child_wait_returned" in phases,
        "returncode_observed": "discovery_child_returncode_observed" in phases,
        "output_scan_completed": "discovery_output_scan_completed" in phases,
        "child_runtime_phase": str(runtime.get("child_runtime_phase") or child_runtime.get("phase") or ""),
        "child_returncode": (child_runtime.get("last_observation") or {}).get("returncode"),
        "bridge_attempted": bool(runtime.get("bridge_attempted")),
        "ghidra_entered": bool(discovery_output.get("ghidra_entered") or runtime.get("ghidra_entered")),
        "discovery_file_count": int(discovery_output.get("discovery_file_count") or runtime.get("output_file_count") or 0),
        "invocable_count": int(discovery_output.get("invocable_count") or 0),
        "safe_to_steer_next_prompt": run_authority.get("safe_to_steer_next_prompt"),
        "current_code_recovery_path_present": current_code_recovery_present,
        "source_root_mutated": False,
        "proof_artifact_summary": str(summary_path),
        "next_action": (
            "repair child_python_startup_interrupt under discovery subprocess control; producer subreason is branch-steering but not product proof"
            if classification == "discovery_empty" and producer_subreason_branch_steering_authority
            else "preserve discovery_empty as the authoritative blocker; build producer-subreason decision authority before steering on child_python_startup_interrupt"
            if classification == "discovery_empty" and producer_reason and not producer_subreason_branch_steering_authority
            else
            "run one full Hard03 confirmation to test whether current recovery path moves the stale artifact blocker"
            if classification == "child_wrapper_wait_return_missing" and current_code_recovery_present
            else f"repair or sharpen {classification} before full Hard03 confirmation"
        ),
    }
    (output_root / "target-local-replay-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify Hard03 reservation_stage from a trusted proof root without claiming product green."
    )
    parser.add_argument("--source-proof-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--mode", default="strict", choices=["strict"])
    args = parser.parse_args(argv)
    result = replay_hard03_reservation_stage_target(
        source_proof_root=args.source_proof_root,
        output_root=args.output_root,
        mode=args.mode,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("classification") != "trusted_predecessor_boundary_unavailable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
