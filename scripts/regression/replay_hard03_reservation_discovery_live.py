from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.regression.replay_hard03_reservation_stage_target import _read_json_if_exists


TARGET = "reservation_stage"
CLAIM_CEILING = "target_local_live_discovery_only"


def _target_dir(proof_root: Path) -> Path | None:
    runs_root = proof_root / "runs"
    if not runs_root.exists():
        return None
    for candidate in sorted(runs_root.iterdir()):
        if candidate.is_dir() and candidate.name.endswith(f"-{TARGET}"):
            return candidate
    return None


def _source_manifest(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(str(path.relative_to(root)) for path in root.rglob("*"))


def _status_payload(target_dir: Path) -> dict[str, Any]:
    run_result = _read_json_if_exists(target_dir / "run_result.json")
    if isinstance(run_result, dict):
        payload = run_result.get("status_payload")
        if isinstance(payload, dict):
            return payload
        snapshot = run_result.get("job_status_snapshot")
        if isinstance(snapshot, dict):
            return snapshot
    status = _read_json_if_exists(target_dir / "job-status-analyze.json")
    return status if isinstance(status, dict) else {}


def _candidate_dll_paths(target_dir: Path) -> list[Path]:
    payload = _status_payload(target_dir)
    run_result = _read_json_if_exists(target_dir / "run_result.json")
    candidates: list[str] = []
    if isinstance(run_result, dict):
        target_dll = run_result.get("target_dll")
        if isinstance(target_dll, str):
            candidates.append(target_dll)
    runtime = payload.get("analyzer_runtime_authority")
    if isinstance(runtime, dict):
        dll_path = runtime.get("dll_path")
        if isinstance(dll_path, str):
            candidates.append(dll_path)
    for row in payload.get("upload_investigation") or []:
        if isinstance(row, dict):
            temp_upload = row.get("temp_upload_path")
            if isinstance(temp_upload, str):
                candidates.append(temp_upload)
    seen: set[str] = set()
    paths: list[Path] = []
    for raw in candidates:
        path = Path(raw)
        key = str(path)
        if key not in seen:
            seen.add(key)
            paths.append(path)
    return paths


def _phase_names(runtime: dict[str, Any]) -> list[str]:
    rows = runtime.get("phase_history")
    if not isinstance(rows, list):
        return []
    return [str(row.get("phase") or "") for row in rows if isinstance(row, dict)]


def _classify_runtime(runtime: dict[str, Any], *, exception_class: str = "") -> str:
    phases = _phase_names(runtime)
    output_count = int(runtime.get("output_file_count") or 0)
    if "discovery_child_wait_start" in phases and "discovery_child_wait_returned" not in phases:
        return "child_wrapper_wait_return_missing"
    if "discovery_child_wait_returned" in phases and "discovery_child_returncode_observed" not in phases:
        return "child_returncode_observation_missing"
    if "discovery_child_returncode_observed" in phases and "discovery_output_scan_completed" not in phases:
        return "child_output_scan_missing"
    if "discovery_output_scan_completed" in phases and output_count == 0:
        return "child_completed_no_output"
    if all(
        phase in phases
        for phase in (
            "discovery_child_wait_returned",
            "discovery_child_returncode_observed",
            "discovery_output_scan_completed",
        )
    ):
        if exception_class:
            return "parent_wait_authority_recovered_live_downstream_blocked"
        return "parent_wait_authority_recovered_live"
    return "hard03_live_discovery_unclassified"


def _local_runtime_authority(job_id: str) -> dict[str, Any]:
    import api.services.discovery as discovery

    status = discovery._get_job_status(job_id)
    if not isinstance(status, dict):
        return {}
    runtime = status.get("analyzer_runtime_authority")
    return runtime if isinstance(runtime, dict) else {}


def replay_hard03_reservation_discovery_live(
    *,
    source_proof_root: Path,
    output_root: Path,
    mode: str = "strict",
    timeout_sec: float = 20.0,
    poll_sec: float = 1.0,
) -> dict[str, Any]:
    source_proof_root = source_proof_root.resolve()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    before = _source_manifest(source_proof_root)

    target_dir = _target_dir(source_proof_root)
    if not target_dir:
        result = {
            "schema_version": "1.0.0",
            "mode": mode,
            "claim_ceiling": CLAIM_CEILING,
            "product_green_claimed": False,
            "source_proof_root": str(source_proof_root),
            "target": TARGET,
            "status": "failed_closed",
            "classification": "trusted_predecessor_boundary_unavailable",
            "reason": "reservation_stage target directory missing",
            "source_root_mutated": before != _source_manifest(source_proof_root),
        }
        (output_root / "live-discovery-result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result

    dll_paths = _candidate_dll_paths(target_dir)
    selected_dll = next((path for path in dll_paths if path.exists()), None)
    if selected_dll is None:
        result = {
            "schema_version": "1.0.0",
            "mode": mode,
            "claim_ceiling": CLAIM_CEILING,
            "product_green_claimed": False,
            "source_proof_root": str(source_proof_root),
            "target": TARGET,
            "target_dir": str(target_dir),
            "status": "failed_closed",
            "classification": "trusted_predecessor_boundary_unavailable",
            "reason": "reservation_stage DLL unavailable",
            "candidate_dll_paths": [str(path) for path in dll_paths],
            "source_root_mutated": before != _source_manifest(source_proof_root),
        }
        (output_root / "live-discovery-result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result

    import api.services.discovery as discovery

    previous_timeout = discovery._DISCOVERY_CHILD_WAIT_TIMEOUT_SEC
    previous_poll = discovery._DISCOVERY_CHILD_WAIT_POLL_SEC
    discovery._DISCOVERY_CHILD_WAIT_TIMEOUT_SEC = float(timeout_sec)
    discovery._DISCOVERY_CHILD_WAIT_POLL_SEC = float(poll_sec)
    job_id = f"hard03live{int(time.time() * 1000) % 100000000}"
    started_at = time.time()
    status = "ok"
    exception_class = ""
    exception_message = ""
    traceback_tail = ""
    invocable_count = 0
    artifact_blob = ""
    try:
        payload = discovery._run_discovery(
            selected_dll,
            job_id,
            hints="Hard03 reservation live diagnostic",
            skip_cache=True,
            analysis_profile="strict_dll",
            ghidra_required=True,
        )
        invocable_count = len(payload.get("invocables") or [])
        artifact_blob = str(payload.get("artifact_blob") or "")
    except Exception as exc:  # diagnostic-only proof must preserve downstream blocker shape
        status = "classified"
        exception_class = type(exc).__name__
        exception_message = str(exc)
        traceback_tail = traceback.format_exc()[-2000:]
    finally:
        discovery._DISCOVERY_CHILD_WAIT_TIMEOUT_SEC = previous_timeout
        discovery._DISCOVERY_CHILD_WAIT_POLL_SEC = previous_poll

    runtime = _local_runtime_authority(job_id)
    classification = _classify_runtime(runtime, exception_class=exception_class)
    phases = _phase_names(runtime)
    result = {
        "schema_version": "1.0.0",
        "mode": mode,
        "claim_ceiling": CLAIM_CEILING,
        "product_green_claimed": False,
        "source_proof_root": str(source_proof_root),
        "target": TARGET,
        "target_dir": str(target_dir),
        "status": status,
        "classification": classification,
        "job_id": job_id,
        "selected_dll": str(selected_dll),
        "candidate_dll_paths": [str(path) for path in dll_paths],
        "elapsed_sec": round(time.time() - started_at, 3),
        "parent_wait_started": "discovery_child_wait_start" in phases,
        "parent_wait_returned": "discovery_child_wait_returned" in phases,
        "returncode_observed": "discovery_child_returncode_observed" in phases,
        "output_scan_completed": "discovery_output_scan_completed" in phases,
        "child_returncode": runtime.get("child_returncode"),
        "output_file_count": int(runtime.get("output_file_count") or 0),
        "bridge_attempted": bool(runtime.get("bridge_attempted")),
        "ghidra_entered": bool(runtime.get("ghidra_entered")),
        "exception_class": exception_class,
        "exception_message": exception_message,
        "traceback_tail": traceback_tail,
        "invocable_count": invocable_count,
        "artifact_blob": artifact_blob,
        "source_root_mutated": before != _source_manifest(source_proof_root),
        "next_action": (
            "full Hard03 confirmation is justified to test current-code parent wait recovery"
            if classification.startswith("parent_wait_authority_recovered_live")
            else f"repair or sharpen {classification} before full Hard03 confirmation"
        ),
    }
    (output_root / "live-discovery-result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a target-local live discovery diagnostic for Hard03 reservation_stage."
    )
    parser.add_argument("--source-proof-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--mode", default="strict", choices=["strict"])
    parser.add_argument("--timeout-sec", default=20.0, type=float)
    parser.add_argument("--poll-sec", default=1.0, type=float)
    args = parser.parse_args(argv)
    result = replay_hard03_reservation_discovery_live(
        source_proof_root=args.source_proof_root,
        output_root=args.output_root,
        mode=args.mode,
        timeout_sec=args.timeout_sec,
        poll_sec=args.poll_sec,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("classification") != "trusted_predecessor_boundary_unavailable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
