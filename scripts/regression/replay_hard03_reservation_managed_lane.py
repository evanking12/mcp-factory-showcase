from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ops.nightly_groundtruth import (
    ApiClient,
    relaunch_local_api_lane,
    resolve_api_url,
    run_one,
    verify_api_identity_for_resolution,
)
from scripts.regression.replay_hard03_reservation_stage_target import (
    _authority_from_file_or_status,
    _classify,
    _read_json_if_exists,
    _target_dir,
)
from scripts.regression.summarize_product_proof_artifacts import summarize_product_proof_artifacts
from runtime.runtime_contract import local_api_base_url


TARGET = "reservation_stage"
CLAIM_CEILING = "managed_lane_target_local_only"


def _load_repo_env_value(name: str) -> str:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return ""
    prefix = f"{name}="
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return ""


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _source_manifest(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(str(path.relative_to(root)) for path in root.rglob("*"))


def _phase_names(runtime: dict[str, Any]) -> list[str]:
    rows = runtime.get("phase_history")
    if not isinstance(rows, list):
        return []
    return [str(row.get("phase") or "") for row in rows if isinstance(row, dict)]


def _source_target_record(source_proof_root: Path, target: str = TARGET) -> tuple[Path | None, dict[str, Any]]:
    target_dir = _target_dir(source_proof_root, target)
    if not target_dir:
        return None, {}
    record = _read_json_if_exists(target_dir / "run_result.json")
    return target_dir, record if isinstance(record, dict) else {}


def _extract_run_inputs(source_proof_root: Path, target: str = TARGET) -> dict[str, Any]:
    target_dir, record = _source_target_record(source_proof_root, target)
    if not target_dir or not record:
        return {
            "ok": False,
            "reason": f"{target} run_result missing",
            "target_dir": str(target_dir or ""),
        }
    dll_path = Path(str(record.get("target_dll") or ""))
    settings = record.get("explore_settings")
    if not isinstance(settings, dict):
        settings = {}
    if not dll_path.exists():
        return {
            "ok": False,
            "reason": f"{target} DLL unavailable",
            "target_dir": str(target_dir),
            "target_dll": str(dll_path),
        }
    return {
        "ok": True,
        "target_dir": str(target_dir),
        "target_run_dir_name": target_dir.name,
        "target_name": str(record.get("target") or target),
        "target_dll": str(dll_path),
        "variant": str(record.get("variant") or "compiled_hard03"),
        "settings": settings,
    }


def _runtime_from_run_dir(run_dir: Path) -> dict[str, Any]:
    runtime = _authority_from_file_or_status(
        run_dir,
        "analyzer-runtime-authority.json",
        "analyzer_runtime_authority",
    )
    if not runtime:
        status = _read_json_if_exists(run_dir / "job-status-analyze.json")
        if isinstance(status, dict) and isinstance(status.get("analyzer_runtime_authority"), dict):
            runtime = status["analyzer_runtime_authority"]
    return runtime if isinstance(runtime, dict) else {}


def _measurement_from_run_dir(run_dir: Path) -> dict[str, Any]:
    measurement = _read_json_if_exists(run_dir / "measurement-terminalization.json")
    return measurement if isinstance(measurement, dict) else {}


def _classify_managed_run(run_dir: Path, record: dict[str, Any]) -> str:
    runtime = _runtime_from_run_dir(run_dir)
    measurement = _measurement_from_run_dir(run_dir)
    phases = _phase_names(runtime)
    if "worker_before_discovery" not in phases and "run_discovery_entered" not in phases:
        if str(record.get("phase") or "") == "preflight":
            return "managed_lane_preflight_unavailable"
        return "managed_lane_pre_discovery_blocked"
    if all(
        phase in phases
        for phase in (
            "discovery_child_wait_returned",
            "discovery_child_returncode_observed",
            "discovery_output_scan_completed",
        )
    ):
        return "managed_lane_parent_wait_authority_recovered"
    if runtime or measurement:
        return _classify(runtime, measurement)
    return "managed_lane_replay_unclassified"


def _parent_wait_fields(run_dir: Path) -> dict[str, Any]:
    runtime = _runtime_from_run_dir(run_dir)
    phases = _phase_names(runtime)
    child_runtime = runtime.get("child_runtime_diagnostic") or {}
    return {
        "parent_wait_started": "discovery_child_wait_start" in phases,
        "parent_wait_returned": "discovery_child_wait_returned" in phases,
        "returncode_observed": "discovery_child_returncode_observed" in phases,
        "output_scan_completed": "discovery_output_scan_completed" in phases,
        "child_runtime_phase": str(runtime.get("child_runtime_phase") or child_runtime.get("phase") or ""),
        "child_returncode": runtime.get("child_returncode")
        if runtime.get("child_returncode") is not None
        else (child_runtime.get("last_observation") or {}).get("returncode"),
        "output_file_count": int(runtime.get("output_file_count") or 0),
        "bridge_attempted": bool(runtime.get("bridge_attempted")),
        "ghidra_entered": bool(runtime.get("ghidra_entered")),
    }


def _compare_surfaces(
    *,
    source_proof_root: Path,
    target: str,
    managed_classification: str,
    managed_wait: dict[str, Any],
) -> dict[str, Any]:
    target_dir, _record = _source_target_record(source_proof_root, target)
    source_runtime = _runtime_from_run_dir(target_dir) if target_dir else {}
    source_measurement = _measurement_from_run_dir(target_dir) if target_dir else {}
    source_classification = _classify(source_runtime, source_measurement) if target_dir else ""
    direct_live_path: Path | None = None
    if target == "reservation_stage":
        direct_live_path = (
            REPO_ROOT
            / ".tmp"
            / "hard03-reservation-stage-child-wrapper-wait-return-repair-v1"
            / "live-discovery-05"
            / "live-discovery-result.json"
        )
    direct_live = _read_json_if_exists(direct_live_path) if direct_live_path else {}
    if not isinstance(direct_live, dict):
        direct_live = {}
    direct_recovered = bool(
        direct_live.get("parent_wait_returned")
        and direct_live.get("returncode_observed")
        and direct_live.get("output_scan_completed")
    )
    managed_recovered = bool(
        managed_wait.get("parent_wait_returned")
        and managed_wait.get("returncode_observed")
        and managed_wait.get("output_scan_completed")
    )
    mismatch_reproduced = bool(direct_recovered and not managed_recovered)
    return {
        "source_full_suite_classification": source_classification,
        "direct_live_replay_result_path": str(direct_live_path) if direct_live_path and direct_live else "",
        "direct_live_classification": str(direct_live.get("classification") or ""),
        "direct_live_parent_wait_recovered": direct_recovered,
        "managed_lane_classification": managed_classification,
        "managed_lane_parent_wait_recovered": managed_recovered,
        "managed_lane_wait_recovery_mismatch_reproduced": mismatch_reproduced,
    }


def _resolve_api_url_with_target_local_recovery(
    *,
    api_url: str,
    api_key: str,
    output_root: Path,
    campaign_log: Path,
) -> tuple[str, str, str, dict[str, Any]]:
    packet: dict[str, Any] = {
        "schema_version": "1.0.0",
        "claim": "hard03_target_local_pre_target_api_identity_authority",
        "target_execution_invoked": False,
        "safe_to_compare": False,
        "product_green_claimed": False,
        "recovery_attempted": False,
        "attempts": [],
    }

    def _record_attempt(label: str, verdict: str, **fields: Any) -> None:
        packet["attempts"].append({"label": label, "verdict": verdict, **fields})

    try:
        resolved_api_url, api_msg, api_resolution_source = resolve_api_url(
            api_url,
            api_key,
            verify_identity=verify_api_identity_for_resolution,
        )
        _record_attempt(
            "initial_resolve",
            "pass",
            resolved_api_url=resolved_api_url,
            message=api_msg,
            source=api_resolution_source,
        )
        packet.update(
            {
                "verdict": "pass",
                "resolved_api_url": resolved_api_url,
                "message": api_msg,
                "source": api_resolution_source,
            }
        )
        _write_json(output_root / "pre-target-api-identity-authority.json", packet)
        return resolved_api_url, api_msg, api_resolution_source, packet
    except RuntimeError as exc:
        failure_message = str(exc)
        _record_attempt("initial_resolve", "fail", exception_message=failure_message)

    recoverable = (
        not str(api_url or "").strip()
        and "api_identity_failed:auto-detect:" in failure_message
        and "api_openapi_unavailable" in failure_message
    )
    if not recoverable:
        packet.update(
            {
                "verdict": "fail",
                "blocking_signal": "target_local_replay_api_identity_resolution_failed",
                "failure": failure_message,
                "recovery_reason": "not_recoverable_by_managed_local_api_relaunch",
            }
        )
        _write_json(output_root / "pre-target-api-identity-authority.json", packet)
        raise RuntimeError(failure_message)

    packet["recovery_attempted"] = True
    packet["recovery_reason"] = "auto_detect_local_api_openapi_unavailable"
    try:
        relaunch = relaunch_local_api_lane(
            REPO_ROOT,
            local_api_base_url(),
            api_key,
            campaign_log=campaign_log,
            no_reload=True,
        )
    except Exception as exc:
        packet.update(
            {
                "verdict": "fail_managed_relaunch",
                "blocking_signal": "target_local_replay_api_identity_recovery_failed",
                "failure": str(exc),
            }
        )
        _write_json(output_root / "pre-target-api-identity-authority.json", packet)
        raise
    packet["managed_relaunch"] = relaunch
    try:
        resolved_api_url, api_msg, api_resolution_source = resolve_api_url(
            api_url,
            api_key,
            verify_identity=verify_api_identity_for_resolution,
        )
        _record_attempt(
            "post_relaunch_resolve",
            "pass",
            resolved_api_url=resolved_api_url,
            message=api_msg,
            source=api_resolution_source,
        )
        packet.update(
            {
                "verdict": "pass_after_managed_relaunch",
                "resolved_api_url": resolved_api_url,
                "message": api_msg,
                "source": api_resolution_source,
            }
        )
        _write_json(output_root / "pre-target-api-identity-authority.json", packet)
        return resolved_api_url, api_msg, api_resolution_source, packet
    except RuntimeError as exc:
        retry_failure = str(exc)
        _record_attempt("post_relaunch_resolve", "fail", exception_message=retry_failure)
        packet.update(
            {
                "verdict": "fail_after_managed_relaunch",
                "blocking_signal": "target_local_replay_api_identity_recovery_failed",
                "failure": retry_failure,
            }
        )
        _write_json(output_root / "pre-target-api-identity-authority.json", packet)
        raise RuntimeError(retry_failure)


def replay_hard03_reservation_managed_lane(
    *,
    source_proof_root: Path,
    output_root: Path,
    mode: str = "strict",
    api_url: str = "",
    api_key: str = "",
    poll_sec: int = 2,
    analyze_timeout_sec: int = 240,
    explore_timeout_sec: int = 360,
    stuck_seconds: int = 120,
) -> dict[str, Any]:
    return replay_hard03_managed_lane_target(
        source_proof_root=source_proof_root,
        output_root=output_root,
        target=TARGET,
        mode=mode,
        api_url=api_url,
        api_key=api_key,
        poll_sec=poll_sec,
        analyze_timeout_sec=analyze_timeout_sec,
        explore_timeout_sec=explore_timeout_sec,
        stuck_seconds=stuck_seconds,
    )


def replay_hard03_managed_lane_target(
    *,
    source_proof_root: Path,
    output_root: Path,
    target: str,
    mode: str = "strict",
    api_url: str = "",
    api_key: str = "",
    poll_sec: int = 2,
    analyze_timeout_sec: int = 240,
    explore_timeout_sec: int = 360,
    stuck_seconds: int = 120,
) -> dict[str, Any]:
    source_proof_root = source_proof_root.resolve()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    before = _source_manifest(source_proof_root)

    if not source_proof_root.exists():
        result = {
            "schema_version": "1.0.0",
            "mode": mode,
            "claim_ceiling": CLAIM_CEILING,
            "product_green_claimed": False,
            "source_proof_root": str(source_proof_root),
            "target": target,
            "status": "failed_closed",
            "classification": "trusted_predecessor_boundary_unavailable",
            "reason": "source proof root missing",
            "source_root_mutated": False,
        }
        _write_json(output_root / "managed-lane-replay-result.json", result)
        return result

    inputs = _extract_run_inputs(source_proof_root, target)
    if not bool(inputs.get("ok")):
        result = {
            "schema_version": "1.0.0",
            "mode": mode,
            "claim_ceiling": CLAIM_CEILING,
            "product_green_claimed": False,
            "source_proof_root": str(source_proof_root),
            "target": target,
            "status": "failed_closed",
            "classification": "trusted_predecessor_boundary_unavailable",
            "reason": str(inputs.get("reason") or "trusted predecessor unavailable"),
            "target_dir": str(inputs.get("target_dir") or ""),
            "source_root_mutated": before != _source_manifest(source_proof_root),
        }
        _write_json(output_root / "managed-lane-replay-result.json", result)
        return result

    run_dir_name = str(inputs.get("target_run_dir_name") or target)
    run_dir = output_root / "runs" / run_dir_name
    heartbeat_path = output_root / "heartbeats.json"
    campaign_log = output_root / "managed-lane-replay.log"
    resolved_api_key = str(api_key or os.getenv("MCP_FACTORY_API_KEY", "") or _load_repo_env_value("PIPELINE_API_KEY")).strip()
    resolved_api_url, api_msg, api_resolution_source, api_authority = _resolve_api_url_with_target_local_recovery(
        api_url=api_url,
        api_key=resolved_api_key,
        output_root=output_root,
        campaign_log=campaign_log,
    )
    client = ApiClient(resolved_api_url, resolved_api_key)
    settings = dict(inputs.get("settings") or {})
    settings["lane_id"] = f"hard03-managed-lane-replay-{target}"
    settings["chain_step_target"] = target
    settings.setdefault("analysis_profile", "strict_dll")
    settings.setdefault("ghidra_required", True)
    settings["skip_cache"] = True
    record = run_one(
        client,
        REPO_ROOT,
        run_dir,
        resolved_api_url,
        resolved_api_key,
        str(inputs.get("target_name") or target),
        Path(str(inputs.get("target_dll"))),
        str(inputs.get("variant") or "compiled_hard03"),
        settings,
        poll_sec,
        analyze_timeout_sec,
        explore_timeout_sec,
        stuck_seconds,
        "compact",
        heartbeat_path,
        campaign_log,
    )
    classification = _classify_managed_run(run_dir, record)
    wait_fields = _parent_wait_fields(run_dir)
    summary_path = output_root / "proof-artifact-summary.json"
    summarize_product_proof_artifacts(
        proof_root=output_root,
        target=target,
        output=summary_path,
    )
    comparison = _compare_surfaces(
        source_proof_root=source_proof_root,
        target=target,
        managed_classification=classification,
        managed_wait=wait_fields,
    )
    result = {
        "schema_version": "1.0.0",
        "mode": mode,
        "claim_ceiling": CLAIM_CEILING,
        "product_green_claimed": False,
        "source_proof_root": str(source_proof_root),
        "target": target,
        "target_dir": str(inputs.get("target_dir") or ""),
        "status": "classified",
        "classification": classification,
        "decision_bearing_blocker": classification,
        "job_id": str(record.get("job_id") or ""),
        "run_dir": str(run_dir),
        "selected_dll": str(inputs.get("target_dll") or ""),
        "api_url": resolved_api_url,
        "api_resolution_source": api_resolution_source,
        "api_identity_message": api_msg,
        "pre_target_api_identity": api_authority,
        **wait_fields,
        **comparison,
        "source_root_mutated": before != _source_manifest(source_proof_root),
        "proof_artifact_summary": str(summary_path),
        "next_action": (
            "repair managed-lane subprocess recovery or authority persistence before full Hard03 rerun"
            if comparison.get("managed_lane_wait_recovery_mismatch_reproduced")
            else "run one full Hard03 confirmation if managed-lane proof is authoritative enough"
            if wait_fields.get("parent_wait_returned") and wait_fields.get("returncode_observed")
            else f"repair or sharpen {classification} before full Hard03 confirmation"
        ),
    }
    _write_json(output_root / "managed-lane-replay-result.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay one Hard03 target through the managed API/worker lane only."
    )
    parser.add_argument("--source-proof-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--target", default=TARGET)
    parser.add_argument("--mode", default="strict", choices=["strict"])
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--poll-sec", default=2, type=int)
    parser.add_argument("--analyze-timeout-sec", default=240, type=int)
    parser.add_argument("--explore-timeout-sec", default=360, type=int)
    parser.add_argument("--stuck-seconds", default=120, type=int)
    args = parser.parse_args(argv)
    result = replay_hard03_managed_lane_target(
        source_proof_root=args.source_proof_root,
        output_root=args.output_root,
        target=args.target,
        mode=args.mode,
        api_url=args.api_url,
        api_key=args.api_key,
        poll_sec=args.poll_sec,
        analyze_timeout_sec=args.analyze_timeout_sec,
        explore_timeout_sec=args.explore_timeout_sec,
        stuck_seconds=args.stuck_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("classification") != "trusted_predecessor_boundary_unavailable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
