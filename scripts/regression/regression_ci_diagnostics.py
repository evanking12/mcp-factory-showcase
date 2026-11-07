from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.analysis.regression_gate_v1 import load_gate_config  # noqa: E402
from api.pipeline.core.spectrum_compiled_ingest import (  # noqa: E402
    SPECTRUM_COMPILED_EASY01_CHAIN_PLAN,
    SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN,
)
from scripts.ops.nightly_groundtruth import write_json  # noqa: E402


REQUIRED_BASELINE_FILES = (
    "compiled-ingest-summary.json",
    "compiled-ingest-compare-report.json",
    "compiled-ingest.log",
)


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _last_observation_from_heartbeat(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    rows: list[Any]
    if isinstance(payload, dict):
        rows = list(payload.values())
    elif isinstance(payload, list):
        rows = payload
    else:
        return {}
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        details = row.get("details") if isinstance(row.get("details"), dict) else {}
        observation = details.get("last_observation") if isinstance(details, dict) else {}
        if isinstance(observation, dict) and observation:
            return observation
    return {}


def _chain_plan(case_id: str) -> tuple[dict[str, Any], ...]:
    if case_id == "easy-01":
        return SPECTRUM_COMPILED_EASY01_CHAIN_PLAN
    if case_id == "medium-01":
        return SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN
    raise ValueError(f"unsupported_case_id:{case_id}")


def _chain_step(case_id: str, target_name: str) -> dict[str, Any]:
    for step in _chain_plan(case_id):
        if str(step.get("target_name") or "") == target_name:
            return dict(step)
    raise ValueError(f"unsupported_checkpoint_target:{case_id}:{target_name}")


def _runner_label() -> str:
    return str(os.getenv("RUNNER_LABEL") or os.getenv("RUNNER_NAME") or "").strip()


def checkpoint_start(
    *,
    case_id: str,
    target_name: str,
    checkpoint_root: Path,
    checkpoint_output_root: Path,
    commit: str,
) -> dict[str, Any]:
    step = _chain_step(case_id, target_name)
    packet = {
        "schema_version": "1.0",
        "case_id": case_id,
        "target_name": target_name,
        "required_semantic_checkpoint": str(step.get("required_semantic_checkpoint") or ""),
        "predecessor_targets": list(step.get("predecessor_targets") or []),
        "runner": _runner_label(),
        "api_port": str(os.getenv("API_PORT") or os.getenv("MCP_FACTORY_API_PORT") or ""),
        "bridge_port": str(os.getenv("BRIDGE_PORT") or os.getenv("MCP_FACTORY_BRIDGE_PORT") or ""),
        "commit": commit,
        "checkpoint_root": str(checkpoint_root),
        "checkpoint_output_root": str(checkpoint_output_root),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    checkpoint_output_root.mkdir(parents=True, exist_ok=True)
    write_json(checkpoint_root / "checkpoint-job-started.json", packet)
    return packet


def checkpoint_finalize(
    *,
    case_id: str,
    target_name: str,
    checkpoint_root: Path,
    checkpoint_output_root: Path,
    commit: str,
) -> dict[str, Any]:
    step = _chain_step(case_id, target_name)
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    checkpoint_output_root.mkdir(parents=True, exist_ok=True)
    packet_path = checkpoint_output_root / "checkpoint-result.json"
    run_record_path = checkpoint_output_root / "run-record.json"
    heartbeat_path = checkpoint_output_root / "heartbeats.json"
    startup_packet_path = checkpoint_root / "lane_startup" / "lane-startup.json"
    run_dirs = [item for item in (checkpoint_output_root / "runs").glob("*") if item.is_dir()]

    if not packet_path.exists():
        run_record = _read_json_if_exists(run_record_path)
        last_observation = (
            run_record.get("last_observation")
            if isinstance(run_record.get("last_observation"), dict)
            else _last_observation_from_heartbeat(heartbeat_path)
        )
        fallback = {
            "schema_version": "1.0.0",
            "case_id": case_id,
            "target_name": target_name,
            "required_semantic_checkpoint": str(step.get("required_semantic_checkpoint") or ""),
            "predecessor_targets": list(step.get("predecessor_targets") or []),
            "verdict": "fail",
            "job_id": "",
            "status": "failed",
            "phase": "",
            "failure_kind": "missing_checkpoint_packet_after_failure",
            "message": "Checkpoint process ended without producing checkpoint-result.json.",
            "last_observation": dict(last_observation or {}),
            "api_identity": "",
            "bridge_identity": "",
            "run_dir_relative": "",
            "run_record": {},
            "commit": commit,
        }
        write_json(packet_path, fallback)

    status = {
        "schema_version": "1.0",
        "case_id": case_id,
        "target_name": target_name,
        "checkpoint_root": str(checkpoint_root),
        "checkpoint_output_root": str(checkpoint_output_root),
        "checkpoint_packet_present": packet_path.exists(),
        "run_record_present": run_record_path.exists(),
        "heartbeat_present": heartbeat_path.exists(),
        "startup_packet_present": startup_packet_path.exists(),
        "run_directory_present": bool(run_dirs),
        "run_directories": [str(item) for item in run_dirs],
        "last_observation": (
            _read_json_if_exists(run_record_path).get("last_observation")
            if isinstance(_read_json_if_exists(run_record_path).get("last_observation"), dict)
            else _last_observation_from_heartbeat(heartbeat_path)
        ),
        "commit": commit,
        "finalized_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_json(checkpoint_root / "checkpoint-artifact-status.json", status)
    write_json(checkpoint_output_root / "checkpoint-artifact-status.json", status)
    return status


def baseline_precheck(*, config_path: Path, case_id: str, output_root: Path) -> dict[str, Any]:
    config = load_gate_config(config_path, repo_root=REPO_ROOT)
    suite_cfg = next(
        dict(item)
        for item in list(config.get("suites") or [])
        if str(item.get("case_id") or "").strip() == case_id
    )
    baseline_root = Path(str(suite_cfg["baseline_output_root"]))
    missing_files = [name for name in REQUIRED_BASELINE_FILES if not (baseline_root / name).exists()]
    root_exists = baseline_root.exists()
    reasons: list[str] = []
    if not root_exists:
        reasons.append("baseline_unavailable_in_summary_job")
    elif missing_files:
        reasons.append("baseline_required_files_missing")
    packet = {
        "schema_version": "1.0",
        "case_id": case_id,
        "baseline_output_root": str(baseline_root),
        "root_exists": root_exists,
        "required_files": list(REQUIRED_BASELINE_FILES),
        "missing_files": missing_files,
        "reasons": reasons,
        "verdict": "pass" if not reasons else "fail",
    }
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "baseline-access.json", packet)
    return packet


def artifact_manifest(
    *,
    case_id: str,
    checkpoint_artifacts_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    expected_targets = [str(step.get("target_name") or "") for step in _chain_plan(case_id)]
    downloaded_dirs = sorted(str(item) for item in checkpoint_artifacts_root.glob("*") if item.is_dir())
    packet_paths = sorted(checkpoint_artifacts_root.rglob("checkpoint-result.json"))
    found_packets: list[dict[str, Any]] = []
    found_targets: set[str] = set()
    for packet_path in packet_paths:
        packet = _read_json_if_exists(packet_path)
        target_name = str(packet.get("target_name") or "").strip()
        if not target_name:
            continue
        found_targets.add(target_name)
        found_packets.append(
            {
                "target_name": target_name,
                "verdict": str(packet.get("verdict") or ""),
                "failure_kind": str(packet.get("failure_kind") or ""),
                "path": str(packet_path),
            }
        )
    missing_targets = [target for target in expected_targets if target not in found_targets]
    packet = {
        "schema_version": "1.0",
        "case_id": case_id,
        "checkpoint_artifacts_root": str(checkpoint_artifacts_root),
        "expected_targets": expected_targets,
        "downloaded_artifact_count": len(downloaded_dirs),
        "downloaded_artifact_dirs": downloaded_dirs,
        "found_checkpoint_packets": found_packets,
        "found_checkpoint_count": len(found_packets),
        "missing_targets": missing_targets,
        "verdict": "pass" if not missing_targets else "fail",
    }
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "checkpoint-artifact-manifest.json", packet)
    return packet


def _first_checkpoint_failure(checkpoints: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    for row in list(checkpoints.get("checkpoints") or []):
        if str(row.get("verdict") or "") == "fail":
            return dict(row)
    for row in list(manifest.get("found_checkpoint_packets") or []):
        if str(row.get("verdict") or "") == "fail":
            return dict(row)
    missing_targets = list(manifest.get("missing_targets") or [])
    if missing_targets:
        return {
            "target_name": str(missing_targets[0]),
            "failure_kind": "missing_checkpoint_artifact",
            "message": "Expected checkpoint artifact was not downloaded.",
        }
    return {}


def triage(
    *,
    case_id: str,
    output_root: Path,
    result_path: Path,
    checkpoints_path: Path | None,
    baseline_access_path: Path,
    artifact_manifest_path: Path,
    commit: str,
) -> dict[str, Any]:
    result = _read_json_if_exists(result_path)
    checkpoints = _read_json_if_exists(checkpoints_path) if checkpoints_path else {}
    baseline_access = _read_json_if_exists(baseline_access_path)
    manifest = _read_json_if_exists(artifact_manifest_path)
    first_failure = _first_checkpoint_failure(checkpoints, manifest)
    reasons = list(result.get("reasons") or [])
    tier = "tier2" if case_id == "easy-01" else "tier3"
    failure_kind = str(first_failure.get("failure_kind") or "").strip()
    if not failure_kind and str(baseline_access.get("verdict") or "") == "fail":
        failure_kind = "baseline_unavailable_in_summary_job"
    if not failure_kind and reasons:
        failure_kind = str(reasons[0])
    first_failed_checkpoint = str(
        checkpoints.get("first_failed_checkpoint")
        or first_failure.get("target_name")
        or ""
    ).strip()
    artifact_status = {
        "downloaded_artifact_count": manifest.get("downloaded_artifact_count"),
        "found_checkpoint_count": manifest.get("found_checkpoint_count"),
        "missing_targets": list(manifest.get("missing_targets") or []),
    }
    next_action = "investigate_checkpoint_failure"
    if failure_kind == "baseline_unavailable_in_summary_job":
        next_action = "restore_or_publish_pinned_baseline_for_summary_job"
    elif failure_kind == "missing_checkpoint_artifact":
        next_action = "inspect_checkpoint_job_artifact_upload"
    elif failure_kind == "missing_checkpoint_packet_after_failure":
        next_action = "inspect_checkpoint_wrapper_and_process_exit"
    elif failure_kind == "explore_timeout":
        next_action = "investigate_session_bootstrap_explore_timeout"

    failure_domain = str(first_failure.get("failure_domain") or "").strip()
    if not failure_domain and failure_kind:
        failure_domain = "pipeline"

    packet = {
        "schema_version": "1.0",
        "case_id": case_id,
        "first_failed_tier": tier,
        "first_failed_checkpoint": first_failed_checkpoint,
        "failure_kind": failure_kind,
        "failure_domain": failure_domain,
        "runner": _runner_label(),
        "api_port": str(os.getenv("API_PORT") or os.getenv("MCP_FACTORY_API_PORT") or ""),
        "bridge_port": str(os.getenv("BRIDGE_PORT") or os.getenv("MCP_FACTORY_BRIDGE_PORT") or ""),
        "commit": commit,
        "baseline_access": baseline_access,
        "artifact_status": artifact_status,
        "result_reasons": reasons,
        "next_action": next_action,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "regression-triage.json", packet)
    markdown = "\n".join(
        [
            f"## Regression Triage: {case_id}",
            "",
            f"- First failed tier: `{packet['first_failed_tier']}`",
            f"- First failed checkpoint: `{packet['first_failed_checkpoint'] or 'none'}`",
            f"- Failure class: `{packet['failure_kind'] or 'none'}`",
            f"- Runner: `{packet['runner']}`",
            f"- Ports: `api={packet['api_port']}, bridge={packet['bridge_port']}`",
            f"- Baseline access: `{baseline_access.get('verdict') or 'missing'}`",
            f"- Downloaded checkpoint artifacts: `{artifact_status['downloaded_artifact_count']}`",
            f"- Missing targets: `{', '.join(str(item) for item in artifact_status['missing_targets']) or 'none'}`",
            f"- Next action: `{packet['next_action']}`",
            "",
        ]
    )
    (output_root / "regression-triage.md").write_text(markdown, encoding="utf-8")
    return packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write regression CI diagnostic packets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("checkpoint-start")
    start.add_argument("--case-id", required=True)
    start.add_argument("--target-name", required=True)
    start.add_argument("--checkpoint-root", required=True, type=Path)
    start.add_argument("--checkpoint-output-root", required=True, type=Path)
    start.add_argument("--commit", default="")

    finalize = subparsers.add_parser("checkpoint-finalize")
    finalize.add_argument("--case-id", required=True)
    finalize.add_argument("--target-name", required=True)
    finalize.add_argument("--checkpoint-root", required=True, type=Path)
    finalize.add_argument("--checkpoint-output-root", required=True, type=Path)
    finalize.add_argument("--commit", default="")

    baseline = subparsers.add_parser("baseline-precheck")
    baseline.add_argument("--config", required=True, type=Path)
    baseline.add_argument("--case-id", required=True)
    baseline.add_argument("--output-root", required=True, type=Path)

    manifest = subparsers.add_parser("artifact-manifest")
    manifest.add_argument("--case-id", required=True)
    manifest.add_argument("--checkpoint-artifacts-root", required=True, type=Path)
    manifest.add_argument("--output-root", required=True, type=Path)

    triage_parser = subparsers.add_parser("triage")
    triage_parser.add_argument("--case-id", required=True)
    triage_parser.add_argument("--output-root", required=True, type=Path)
    triage_parser.add_argument("--result", required=True, type=Path)
    triage_parser.add_argument("--checkpoints", default=None, type=Path)
    triage_parser.add_argument("--baseline-access", required=True, type=Path)
    triage_parser.add_argument("--artifact-manifest", required=True, type=Path)
    triage_parser.add_argument("--commit", default="")

    args = parser.parse_args(argv)
    if args.command == "checkpoint-start":
        payload = checkpoint_start(
            case_id=args.case_id,
            target_name=args.target_name,
            checkpoint_root=args.checkpoint_root,
            checkpoint_output_root=args.checkpoint_output_root,
            commit=args.commit,
        )
    elif args.command == "checkpoint-finalize":
        payload = checkpoint_finalize(
            case_id=args.case_id,
            target_name=args.target_name,
            checkpoint_root=args.checkpoint_root,
            checkpoint_output_root=args.checkpoint_output_root,
            commit=args.commit,
        )
    elif args.command == "baseline-precheck":
        payload = baseline_precheck(config_path=args.config, case_id=args.case_id, output_root=args.output_root)
    elif args.command == "artifact-manifest":
        payload = artifact_manifest(
            case_id=args.case_id,
            checkpoint_artifacts_root=args.checkpoint_artifacts_root,
            output_root=args.output_root,
        )
    elif args.command == "triage":
        payload = triage(
            case_id=args.case_id,
            output_root=args.output_root,
            result_path=args.result,
            checkpoints_path=args.checkpoints,
            baseline_access_path=args.baseline_access,
            artifact_manifest_path=args.artifact_manifest,
            commit=args.commit,
        )
    else:  # pragma: no cover - argparse prevents this.
        raise ValueError(args.command)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
