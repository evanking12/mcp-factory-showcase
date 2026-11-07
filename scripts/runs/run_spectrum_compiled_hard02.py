from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.spectrum_compiled_ingest import (  # noqa: E402
    SPECTRUM_COMPILED_HARD02_CASE_ID,
    SPECTRUM_COMPILED_HARD02_CHAIN_PLAN,
    SPECTRUM_COMPILED_SUITE_ID,
    build_spectrum_compiled_hard02_report,
    ensure_spectrum_compiled_package_built,
    load_spectrum_authored_hard02_manifest,
    load_spectrum_authored_truth_manifest,
    load_spectrum_compiled_package_manifest,
    load_spectrum_compiled_truth_manifest,
    ordered_spectrum_compiled_hard02_targets,
)
from api.pipeline.core.enterprise_survivability import write_enterprise_survivability_summary  # noqa: E402
from scripts.ops.measurement_control_plane import (  # noqa: E402
    apply_control_plane_to_run_record,
    build_bridge_candidate_registry_packet,
    build_bridge_candidates_from_config,
    bridge_stream_health_from_run_record,
    control_plane_allows_run,
    hard_family_bridge_stream_health_for_target,
    selected_bridge_url_from_registry,
    split_configured_bridge_urls,
    write_control_plane_blocked_result,
)
from scripts.ops.nightly_groundtruth import (  # noqa: E402
    ApiClient,
    build_post_restart_readiness_probe,
    build_lane_identity_packet,
    build_lane_readiness_packet,
    collect_api_identity,
    collect_bridge_identity,
    collect_runner_identity,
    ensure_local_api_freshness,
    ensure_local_bridge_freshness,
    ensure_strict_local_lane_preflight,
    fetch_api_readiness,
    fetch_bridge_readiness,
    log_line,
    relaunch_local_api_lane,
    resolve_api_url,
    run_one,
    run_post_restart_readiness_probe,
    verify_api_identity_for_resolution,
    verify_api_identity,
    verify_bridge_identity,
    write_json,
)
from runtime.runtime_contract import local_bridge_base_url  # noqa: E402

RUNNER_VERSION = "1.0.0"


def _load_repo_env_value(name: str) -> str:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return ""
    prefix = f"{name}="
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        return stripped[len(prefix):].strip()
    return ""


def _fingerprint_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json_or_none(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _latest_function_finding(findings: Any, function_name: str) -> dict[str, Any]:
    rows = findings if isinstance(findings, list) else []
    matches = [row for row in rows if isinstance(row, dict) and row.get("function") == function_name]
    return dict(matches[-1]) if matches else {}


def _copy_if_present(source: Path, dest: Path) -> bool:
    if not source.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return True


def _recover_finalized_target_from_job_store(
    *,
    run_dir: Path,
    job_id: str,
    required_semantic_checkpoint: str,
) -> dict[str, Any]:
    job_dir = REPO_ROOT / "local-data" / "artifacts" / str(job_id or "")
    if not job_id or not job_dir.exists():
        return {
            "recovered": False,
            "source": "local_job_artifact_store",
            "job_id": str(job_id or ""),
            "reason": "job_artifact_dir_missing",
        }

    copied: list[str] = []
    for name in (
        "findings.json",
        "verification-report.json",
        "run-validity.json",
        "status.json",
        "macro_verdict.json",
        "harmonization_report.json",
    ):
        if _copy_if_present(job_dir / name, run_dir / name):
            copied.append(name)
    if _copy_if_present(
        job_dir / "evidence" / "stage-02c-evidence-capture" / "probe-log.json",
        run_dir / "recovered-artifacts" / "evidence" / "stage-02c-evidence-capture" / "probe-log.json",
    ):
        copied.append("recovered-artifacts/evidence/stage-02c-evidence-capture/probe-log.json")
    if _copy_if_present(
        job_dir / "checkpoints" / "s07_finalize.json",
        run_dir / "recovered-artifacts" / "checkpoints" / "s07_finalize.json",
    ):
        copied.append("recovered-artifacts/checkpoints/s07_finalize.json")

    checkpoint = _read_json_or_none(job_dir / "checkpoints" / "s07_finalize.json") or {}
    findings = _read_json_or_none(job_dir / "findings.json") or []
    row = _latest_function_finding(findings, required_semantic_checkpoint)
    status = str(row.get("status_canonical") or row.get("status") or "")
    recovery = {
        "recovered": bool(copied),
        "source": "local_job_artifact_store",
        "job_id": str(job_id or ""),
        "job_artifact_dir": str(job_dir),
        "copied_artifacts": copied,
        "s07_finalize_completed": bool(checkpoint.get("completed")),
        "required_semantic_checkpoint": str(required_semantic_checkpoint or ""),
        "required_checkpoint_recovered": bool(row),
        "required_checkpoint_status_canonical": status,
        "decision_bearing_recovery": bool(checkpoint.get("completed")) and status == "verified_success",
    }
    write_json(run_dir / "finalized-artifact-recovery.json", recovery)
    return recovery


def _promote_recovered_finalized_record(
    *,
    run_dir: Path,
    record: dict[str, Any],
    control_plane: dict[str, Any],
    recovery: dict[str, Any],
) -> dict[str, Any]:
    if not bool(recovery.get("decision_bearing_recovery")):
        return record

    recovered_control_plane = dict(control_plane)
    recovered_control_plane["light"] = "green"
    recovered_control_plane["status"] = "admitted"
    recovered_control_plane["reason_code"] = "current_run_s07_finalize_recovered"
    recovered_control_plane["blocking_reasons"] = []
    recovered_control_plane["safe_to_compare"] = True
    recovered_control_plane["semantic_proof_satisfied"] = True
    recovered_control_plane["artifact_recovery"] = recovery
    write_json(run_dir / "measurement-control-plane.json", recovered_control_plane)

    run_authority = {
        "contract_version": "trust_contract_v1",
        "authority_level": "decision_bearing",
        "authoritative_proving": True,
        "safe_to_steer_next_prompt": True,
        "failure_domain": "",
        "blocking_reasons": [],
        "recovered_from": "local_job_artifact_store",
        "recovery_reason": "s07_finalize_completed_with_verified_required_checkpoint",
        "job_id": str(record.get("job_id") or recovery.get("job_id") or ""),
    }
    record.update(
        {
            "status": "ok",
            "phase": "done",
            "valid_run": True,
            "safe_to_compare": True,
            "failure_domain": "",
            "authoritative_proving": True,
            "run_authority": run_authority,
            "measurement_control_plane": recovered_control_plane,
            "artifact_recovery": recovery,
            "terminalization_recovered": True,
            "job_status_snapshot": {"status": "done", "source": "s07_artifact_recovery"},
            "verdict": {"status": "done", "source": "s07_artifact_recovery"},
        }
    )
    record.pop("measurement_terminalization", None)
    write_json(run_dir / "run-authority.json", run_authority)
    write_json(run_dir / "run_result.json", record)
    return record


def _is_trusted_predecessor_record(record: dict[str, Any]) -> bool:
    job_id = str(record.get("job_id") or "").strip()
    if not job_id:
        return False
    if str(record.get("status") or "").strip().lower() != "ok":
        return False

    control_plane = dict(record.get("measurement_control_plane") or {})
    if control_plane and not bool(control_plane.get("safe_to_compare")):
        return False

    valid_run = record.get("valid_run")
    if valid_run is not None and not bool(valid_run):
        return False

    phase = str(record.get("phase") or "").strip().lower()
    if phase and phase != "done":
        return False

    verdict = record.get("verdict")
    verdict_status = str(((verdict or {}).get("status") if isinstance(verdict, dict) else "") or "").strip().lower()
    if verdict_status and verdict_status != "done":
        return False

    job_status_snapshot = record.get("job_status_snapshot")
    job_status = str(
        ((job_status_snapshot or {}).get("status") if isinstance(job_status_snapshot, dict) else "") or ""
    ).strip().lower()
    if job_status and job_status != "done":
        return False

    return True


def _should_retry_first_leg_after_restart(
    record: dict[str, Any],
    *,
    restarted_for_freshness: bool,
    attempt_count: int,
    target_name: str,
) -> tuple[bool, str]:
    if not restarted_for_freshness or attempt_count != 0:
        return False, ""
    if str(target_name or "").strip() != "session_bootstrap":
        return False, ""
    terminalization = record.get("job_terminalization") or record.get("runner_terminalization") or {}
    if str((terminalization or {}).get("kind") or "").strip() not in {"quasi_terminal_stall", "quasi_terminal_clarify_stall"}:
        return False, ""
    return True, "quasi_terminal_clarify_stall_after_restart"


def _run_one_supports_lane_readiness() -> bool:
    try:
        return "lane_readiness" in inspect.signature(run_one).parameters
    except Exception:
        return False


def _bridge_stream_health_by_url(
    *,
    bridge_urls: list[str],
    target_name: str,
    analysis_profile: str,
    selected_bridge_url: str = "",
    current_run_health: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    health_by_url = {
        url: hard_family_bridge_stream_health_for_target(target_name, analysis_profile)
        for url in bridge_urls
    }
    current_health = dict(current_run_health or {})
    if current_health:
        target_url = selected_bridge_url or (bridge_urls[0] if len(bridge_urls) == 1 else "")
        if target_url:
            health_by_url[target_url] = current_health
    return health_by_url


def run_spectrum_compiled_hard02(
    *,
    api_url: str = "",
    api_key: str = "",
    bridge_url: str = "",
    bridge_urls: str = "",
    bridge_quarantine_registry: str = "",
    bridge_key: str = "",
    output_root: str | Path | None = None,
    poll_sec: int = 10,
    analyze_timeout_sec: int = 1800,
    explore_timeout_sec: int = 5400,
    stuck_seconds: int = 900,
) -> dict[str, Any]:
    manifest = ensure_spectrum_compiled_package_built()
    compiled_truth = load_spectrum_compiled_truth_manifest()
    authored_truth = load_spectrum_authored_truth_manifest()
    authored_hard = load_spectrum_authored_hard02_manifest()

    resolved_api_key = str(
        api_key
        or os.getenv("MCP_FACTORY_API_KEY", "")
        or _load_repo_env_value("PIPELINE_API_KEY")
    ).strip()
    resolved_bridge_url = str(
        bridge_url
        or os.getenv("GUI_BRIDGE_URL", "")
        or _load_repo_env_value("GUI_BRIDGE_URL")
        or local_bridge_base_url()
    ).strip()
    configured_bridge_urls = split_configured_bridge_urls(
        bridge_urls
        or os.getenv("GUI_BRIDGE_CANDIDATE_URLS", "")
        or _load_repo_env_value("GUI_BRIDGE_CANDIDATE_URLS"),
        default_bridge_url=resolved_bridge_url,
    )
    resolved_bridge_quarantine_registry = str(
        bridge_quarantine_registry
        or os.getenv("GUI_BRIDGE_QUARANTINE_REGISTRY", "")
        or _load_repo_env_value("GUI_BRIDGE_QUARANTINE_REGISTRY")
    ).strip()
    resolved_bridge_key = str(
        bridge_key
        or os.getenv("GUI_BRIDGE_SECRET", "")
        or os.getenv("BRIDGE_SECRET", "")
        or _load_repo_env_value("GUI_BRIDGE_SECRET")
        or _load_repo_env_value("BRIDGE_SECRET")
    ).strip()

    resolved_api_url, api_msg, api_resolution_source = resolve_api_url(
        api_url,
        resolved_api_key,
        verify_identity=verify_api_identity_for_resolution,
    )

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT
        / "sessions"
        / "design_suite"
        / "compiled_ingest"
        / SPECTRUM_COMPILED_SUITE_ID
        / SPECTRUM_COMPILED_HARD02_CASE_ID
        / timestamp
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    campaign_log = output_dir / "compiled-ingest.log"
    heartbeat_path = output_dir / "heartbeats.json"
    bridge_freshness = ensure_local_bridge_freshness(
        REPO_ROOT,
        resolved_bridge_url,
        resolved_bridge_key,
        campaign_log=campaign_log,
    )
    if bridge_freshness.get("freshness_verdict") == "restart_blocked_unmanaged_owner":
        raise RuntimeError("bridge_freshness_blocked_unmanaged_owner")
    freshness = ensure_local_api_freshness(
        REPO_ROOT,
        resolved_api_url,
        resolved_api_key,
        campaign_log=campaign_log,
        force_restart_reason=(
            "restart_required_bridge_restarted"
            if bool(bridge_freshness.get("restart_performed"))
            else ""
        ),
    )
    if freshness.get("freshness_verdict") == "restart_blocked_unmanaged_owner":
        raise RuntimeError("api_freshness_blocked_unmanaged_owner")
    bridge_ok, bridge_msg = verify_bridge_identity(resolved_bridge_url, resolved_bridge_key)
    if not bridge_ok:
        raise RuntimeError(f"bridge_identity_failed:{bridge_msg}")
    strict_local_preflight = ensure_strict_local_lane_preflight(
        api_url=resolved_api_url,
        api_key=resolved_api_key,
        bridge_url=resolved_bridge_url,
        bridge_key=resolved_bridge_key,
    )
    client = ApiClient(resolved_api_url, resolved_api_key)
    runner_identity = collect_runner_identity(
        runner_name="run_spectrum_compiled_hard02",
        runner_version=RUNNER_VERSION,
        runner_file=Path(__file__),
        api_url=resolved_api_url,
        bridge_url=resolved_bridge_url,
        started_at=time.time(),
    )
    api_identity_payload = collect_api_identity(resolved_api_url, resolved_api_key, api_msg)
    bridge_identity_payload = collect_bridge_identity(resolved_bridge_url, resolved_bridge_key, bridge_msg)
    lane_identity = build_lane_identity_packet(
        runner_identity=runner_identity,
        api_identity=api_identity_payload,
        bridge_identity=bridge_identity_payload,
    )
    lane_identity["strict_local_preflight"] = strict_local_preflight
    write_json(output_dir / "lane-identity.json", lane_identity)

    selected_targets = ordered_spectrum_compiled_hard02_targets(manifest)
    post_restart_readiness = build_post_restart_readiness_probe(performed=False)
    if bool(freshness.get("restart_performed")):
        first_target = selected_targets[0] if selected_targets else {}
        first_dll_path = (REPO_ROOT / str(first_target.get("source_path") or "")).resolve()
        post_restart_readiness = run_post_restart_readiness_probe(
            client,
            REPO_ROOT,
            output_dir,
            resolved_api_url,
            resolved_api_key,
            first_dll_path,
            heartbeat_path=heartbeat_path,
            campaign_log=campaign_log,
        )
        if not bool(post_restart_readiness.get("ready")):
            raise RuntimeError(
                "post_restart_readiness_failed:"
                + str(post_restart_readiness.get("verdict") or "unknown")
            )
    api_readiness_payload = fetch_api_readiness(resolved_api_url, resolved_api_key)
    bridge_readiness_payload = fetch_bridge_readiness(resolved_bridge_url, resolved_bridge_key)
    lane_readiness = build_lane_readiness_packet(
        runner_identity=runner_identity,
        api_identity=api_identity_payload,
        bridge_identity=bridge_identity_payload,
        api_readiness=api_readiness_payload,
        bridge_readiness=bridge_readiness_payload,
        freshness=freshness,
        bridge_freshness=bridge_freshness,
        post_restart_readiness_probe=post_restart_readiness,
        canary_verdict="not_run",
    )
    write_json(output_dir / "lane-readiness.json", lane_readiness)

    bridge_identities_by_url: dict[str, dict[str, Any]] = {}
    bridge_readiness_by_url: dict[str, dict[str, Any]] = {}
    bridge_lane_readiness_by_url: dict[str, dict[str, Any]] = {}
    for candidate_url in configured_bridge_urls:
        candidate_ok, candidate_msg = verify_bridge_identity(candidate_url, resolved_bridge_key)
        candidate_identity = collect_bridge_identity(candidate_url, resolved_bridge_key, candidate_msg)
        candidate_readiness = fetch_bridge_readiness(candidate_url, resolved_bridge_key)
        if not candidate_ok:
            candidate_readiness = {
                "ready": False,
                "capabilities": [],
                "blocking_reasons": [f"bridge_identity_failed:{candidate_msg}"],
            }
        bridge_identities_by_url[candidate_url] = candidate_identity
        bridge_readiness_by_url[candidate_url] = dict(candidate_readiness or {})
        bridge_lane_readiness_by_url[candidate_url] = build_lane_readiness_packet(
            runner_identity=runner_identity,
            api_identity=api_identity_payload,
            bridge_identity=candidate_identity,
            api_readiness=api_readiness_payload,
            bridge_readiness=candidate_readiness,
            freshness=freshness,
            bridge_freshness=(
                bridge_freshness
                if candidate_url == resolved_bridge_url
                else {"freshness_verdict": "not_checked_configured_candidate_v1"}
            ),
            post_restart_readiness_probe=post_restart_readiness,
            canary_verdict="not_run",
        )

    suite_candidates = build_bridge_candidates_from_config(
        bridge_urls=configured_bridge_urls,
        default_bridge_url="",
        target=SPECTRUM_COMPILED_HARD02_CASE_ID,
        analysis_profile="strict_dll",
        bridge_identities=bridge_identities_by_url,
        bridge_readiness=bridge_readiness_by_url,
        bridge_lane_readiness=bridge_lane_readiness_by_url,
        bridge_stream_health=_bridge_stream_health_by_url(
            bridge_urls=configured_bridge_urls,
            target_name=SPECTRUM_COMPILED_HARD02_CASE_ID,
            analysis_profile="strict_dll",
        ),
        quarantine_registry=resolved_bridge_quarantine_registry,
    )
    suite_control_plane = build_bridge_candidate_registry_packet(
        target=SPECTRUM_COMPILED_HARD02_CASE_ID,
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        runner_identity=runner_identity,
        api_identity=api_identity_payload,
        api_readiness=api_readiness_payload,
        lane_readiness=lane_readiness,
        bridge_candidates=suite_candidates,
        evidence_paths=[
            "measurement-control-plane.json",
            "lane-readiness.json",
            "lane-identity.json",
        ],
    )
    write_json(output_dir / "measurement-control-plane.json", suite_control_plane)
    run_records: list[dict[str, Any]] = []
    post_restart_first_leg_recovery = {
        "armed": bool(freshness.get("restart_performed")),
        "first_leg_after_restart": bool(freshness.get("restart_performed")),
        "auto_recovery_triggered": False,
        "auto_recovery_reason": "",
        "auto_recovery_attempts": 0,
        "final_recovery_verdict": "not_armed" if not freshness.get("restart_performed") else "pending",
    }
    successful_job_by_target: dict[str, str] = {}
    chain_step_by_target = {
        str(step["target_name"]): dict(step) for step in SPECTRUM_COMPILED_HARD02_CHAIN_PLAN
    }
    for index, target in enumerate(selected_targets, start=1):
        dll_path = (REPO_ROOT / str(target.get("source_path") or "")).resolve()
        target_name = str(target.get("target_name") or Path(dll_path).stem).strip()
        chain_step = chain_step_by_target[target_name]
        predecessor_targets = list(chain_step.get("predecessor_targets") or [])
        prior_job_id = ""
        if predecessor_targets:
            prior_job_id = str(successful_job_by_target.get(predecessor_targets[-1]) or "").strip()
        cross_dll_prior_job_ids = [
            str(successful_job_by_target.get(name) or "").strip()
            for name in predecessor_targets
            if str(successful_job_by_target.get(name) or "").strip()
        ]
        run_dir = output_dir / "runs" / f"{index:02d}-{target_name}"
        log_line(f"spectrum-compiled-start target={target_name} dll={dll_path.name}", campaign_log)
        explore_settings = {
            "mode": "normal",
            "cap_profile": "deploy",
            "max_rounds": 4,
            "max_tool_calls": 10,
            "gap_resolution_enabled": True,
            "skip_documented": True,
            "deterministic_fallback_enabled": True,
            "context_density": "full",
            "analysis_profile": "strict_dll",
            "ghidra_required": True,
            "parallel_runs": 1,
            "variant_id": "compiled_hard02",
            "lane_id": f"spectrum-hard02-{index}",
            "binary_fixture_suite": SPECTRUM_COMPILED_SUITE_ID,
            "entry_surface": "upload",
            "prior_job_id": prior_job_id,
            "chain_step_target": target_name,
            "required_semantic_checkpoint": str(chain_step["required_semantic_checkpoint"]),
            "selected_invocable_names": [str(chain_step["required_semantic_checkpoint"])],
        }
        if cross_dll_prior_job_ids:
            explore_settings["cross_dll_prior_job_ids"] = cross_dll_prior_job_ids
        target_profile = str(explore_settings.get("analysis_profile") or "strict_dll")
        target_candidates = build_bridge_candidates_from_config(
            bridge_urls=configured_bridge_urls,
            default_bridge_url="",
            target=target_name,
            analysis_profile=target_profile,
            bridge_identities=bridge_identities_by_url,
            bridge_readiness=bridge_readiness_by_url,
            bridge_lane_readiness=bridge_lane_readiness_by_url,
            bridge_stream_health=_bridge_stream_health_by_url(
                bridge_urls=configured_bridge_urls,
                target_name=target_name,
                analysis_profile=target_profile,
            ),
            quarantine_registry=resolved_bridge_quarantine_registry,
        )
        target_control_plane = build_bridge_candidate_registry_packet(
            target=target_name,
            analysis_profile=target_profile,
            required_capabilities=["analyze"],
            runner_identity=runner_identity,
            api_identity=api_identity_payload,
            api_readiness=api_readiness_payload,
            lane_readiness=lane_readiness,
            bridge_candidates=target_candidates,
            evidence_paths=[
                str((run_dir / "measurement-control-plane.json").relative_to(output_dir)).replace("\\", "/"),
                "lane-readiness.json",
                "lane-identity.json",
            ],
        )
        selected_bridge_url = selected_bridge_url_from_registry(target_control_plane)
        if selected_bridge_url:
            explore_settings["selected_bridge_url"] = selected_bridge_url
            explore_settings["selected_bridge_candidate_id"] = str(target_control_plane.get("selected_candidate_id") or "")
        write_json(run_dir / "measurement-control-plane.json", target_control_plane)
        attempt_summaries: list[dict[str, Any]] = []
        record = {}
        if not control_plane_allows_run(target_control_plane):
            record = write_control_plane_blocked_result(
                run_dir=run_dir,
                control_plane=target_control_plane,
                dll_name=dll_path.name,
                dll_path=str(dll_path),
                binary_hash=_fingerprint_bytes(dll_path),
                entry_surface="upload",
            )
            attempt_summaries.append(
                {
                    "attempt_index": 0,
                    "job_id": str(record.get("job_id") or "").strip(),
                    "status": str(record.get("status") or "").strip().lower(),
                    "phase": str(record.get("phase") or "").strip().lower(),
                    "failure_domain": str(record.get("failure_domain") or ""),
                    "run_authority": record.get("run_authority"),
                    "authoritative_proving": False,
                    "control_plane_light": str(target_control_plane.get("light") or ""),
                    "control_plane_reason_code": str(target_control_plane.get("reason_code") or ""),
                }
            )
            log_line(
                (
                    "control-plane-block "
                    f"target={target_name} light={target_control_plane.get('light')} "
                    f"reason={target_control_plane.get('reason_code')}"
                ),
                campaign_log,
            )
        else:
            for attempt_index in range(2):
                run_one_kwargs: dict[str, Any] = {
                    "poll_sec": poll_sec,
                    "analyze_timeout_sec": analyze_timeout_sec,
                    "explore_timeout_sec": explore_timeout_sec,
                    "stuck_seconds": stuck_seconds,
                    "snapshot_profile": "full",
                    "heartbeat_path": heartbeat_path,
                    "campaign_log": campaign_log,
                }
                if _run_one_supports_lane_readiness():
                    run_one_kwargs["lane_readiness"] = lane_readiness
                record = run_one(
                    client,
                    REPO_ROOT,
                    run_dir,
                    resolved_api_url,
                    resolved_api_key,
                    target_name,
                    dll_path,
                    "compiled_hard02",
                    explore_settings,
                    **run_one_kwargs,
                )
                current_run_bridge_health = bridge_stream_health_from_run_record(record)
                pre_run_control_plane = target_control_plane
                final_target_candidates = build_bridge_candidates_from_config(
                    bridge_urls=configured_bridge_urls,
                    default_bridge_url="",
                    target=target_name,
                    analysis_profile=target_profile,
                    bridge_identities=bridge_identities_by_url,
                    bridge_readiness=bridge_readiness_by_url,
                    bridge_lane_readiness=bridge_lane_readiness_by_url,
                    bridge_stream_health=_bridge_stream_health_by_url(
                        bridge_urls=configured_bridge_urls,
                        target_name=target_name,
                        analysis_profile=target_profile,
                        selected_bridge_url=selected_bridge_url,
                        current_run_health=current_run_bridge_health,
                    ),
                    quarantine_registry=resolved_bridge_quarantine_registry,
                )
                target_control_plane = build_bridge_candidate_registry_packet(
                    target=target_name,
                    analysis_profile=target_profile,
                    required_capabilities=["analyze"],
                    runner_identity=runner_identity,
                    api_identity=api_identity_payload,
                    api_readiness=api_readiness_payload,
                    lane_readiness=lane_readiness,
                    bridge_candidates=final_target_candidates,
                    evidence_paths=[
                        str((run_dir / "measurement-control-plane.json").relative_to(output_dir)).replace("\\", "/"),
                        "lane-readiness.json",
                        "lane-identity.json",
                    ],
                )
                target_control_plane["pre_run_control_plane"] = pre_run_control_plane
                target_control_plane["current_run_bridge_stream_health"] = current_run_bridge_health
                write_json(run_dir / "measurement-control-plane.json", target_control_plane)
                record["pre_run_measurement_control_plane"] = pre_run_control_plane
                record["current_run_bridge_stream_health"] = current_run_bridge_health
                record = apply_control_plane_to_run_record(
                    run_dir=run_dir,
                    record=record,
                    control_plane=target_control_plane,
                )
                artifact_recovery = _recover_finalized_target_from_job_store(
                    run_dir=run_dir,
                    job_id=str(record.get("job_id") or ""),
                    required_semantic_checkpoint=str(chain_step["required_semantic_checkpoint"]),
                )
                record = _promote_recovered_finalized_record(
                    run_dir=run_dir,
                    record=record,
                    control_plane=target_control_plane,
                    recovery=artifact_recovery,
                )
                target_control_plane = dict(record.get("measurement_control_plane") or target_control_plane)
                attempt_summaries.append(
                    {
                        "attempt_index": attempt_index + 1,
                        "job_id": str(record.get("job_id") or "").strip(),
                        "status": str(record.get("status") or "").strip().lower(),
                        "phase": str(record.get("phase") or "").strip().lower(),
                        "job_terminalization": record.get("job_terminalization"),
                        "failure_domain": str(record.get("failure_domain") or ""),
                        "run_authority": record.get("run_authority"),
                        "authoritative_proving": bool(record.get("authoritative_proving")),
                        "control_plane_light": str(target_control_plane.get("light") or ""),
                        "control_plane_reason_code": str(target_control_plane.get("reason_code") or ""),
                    }
                )
                should_retry, reason = _should_retry_first_leg_after_restart(
                    record,
                    restarted_for_freshness=bool(freshness.get("restart_performed")),
                    attempt_count=attempt_index,
                    target_name=target_name,
                )
                if not should_retry:
                    break
                post_restart_first_leg_recovery.update(
                    {
                        "auto_recovery_triggered": True,
                        "auto_recovery_reason": reason,
                        "auto_recovery_attempts": attempt_index + 1,
                        "final_recovery_verdict": "retrying",
                    }
                )
                log_line(
                    f"first-leg-auto-recovery relaunching lane for {target_name} reason={reason}",
                    campaign_log,
                )
                relaunch_local_api_lane(
                    REPO_ROOT,
                    resolved_api_url,
                    resolved_api_key,
                    campaign_log=campaign_log,
                )
                client = ApiClient(resolved_api_url, resolved_api_key)
        if target_name == "session_bootstrap":
            if not post_restart_first_leg_recovery["armed"]:
                post_restart_first_leg_recovery["final_recovery_verdict"] = "not_armed"
            elif post_restart_first_leg_recovery["auto_recovery_triggered"]:
                post_restart_first_leg_recovery["final_recovery_verdict"] = (
                    "recovered"
                    if bool(record.get("authoritative_proving"))
                    else "recovery_failed_non_authoritative"
                )
            else:
                post_restart_first_leg_recovery["final_recovery_verdict"] = "not_needed"
        record["first_leg_after_restart"] = bool(freshness.get("restart_performed")) and target_name == "session_bootstrap"
        record["auto_recovery_triggered"] = bool(
            post_restart_first_leg_recovery["auto_recovery_triggered"] and target_name == "session_bootstrap"
        )
        record["auto_recovery_reason"] = (
            str(post_restart_first_leg_recovery["auto_recovery_reason"] or "")
            if target_name == "session_bootstrap"
            else ""
        )
        record["auto_recovery_attempts"] = (
            int(post_restart_first_leg_recovery["auto_recovery_attempts"] or 0)
            if target_name == "session_bootstrap"
            else 0
        )
        record["post_restart_attempts"] = attempt_summaries
        record.setdefault("explore_settings", explore_settings)
        record["measurement_control_plane"] = target_control_plane
        record["dll_name"] = dll_path.name
        record["dll_path"] = str(dll_path)
        record["run_dir"] = str(run_dir)
        record["binary_hash"] = _fingerprint_bytes(dll_path)
        record["entry_surface"] = "upload"
        record["chain_context"] = {
            "target_name": target_name,
            "predecessor_targets": predecessor_targets,
            "prior_job_id": prior_job_id,
            "cross_dll_prior_job_ids": cross_dll_prior_job_ids,
            "required_semantic_checkpoint": str(chain_step["required_semantic_checkpoint"]),
        }
        run_records.append(record)
        job_id = str(record.get("job_id") or "").strip()
        if _is_trusted_predecessor_record(record):
            successful_job_by_target[target_name] = job_id
        if record.get("measurement_terminalization"):
            record["dependent_chain_policy"] = "stop_dependent_chain_on_non_comparable_target"
            log_line(
                (
                    "hard-chain-stop "
                    f"target={target_name} reason="
                    f"{(record.get('measurement_terminalization') or {}).get('reason_code')}"
                ),
                campaign_log,
            )
            break

    report = build_spectrum_compiled_hard02_report(
        output_dir=output_dir,
        package_manifest=load_spectrum_compiled_package_manifest(),
        compiled_truth_manifest=compiled_truth,
        authored_truth_manifest=authored_truth,
        authored_hard_manifest=authored_hard,
        run_records=run_records,
    )
    survivability_summary = write_enterprise_survivability_summary(
        output_dir=output_dir,
        suite_id=SPECTRUM_COMPILED_SUITE_ID,
        case_id=SPECTRUM_COMPILED_HARD02_CASE_ID,
        run_records=run_records,
        chain_plan=SPECTRUM_COMPILED_HARD02_CHAIN_PLAN,
    )
    report["measurement_control_plane"] = suite_control_plane
    report["enterprise_survivability_summary"] = survivability_summary

    run_bundle = {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_HARD02_CASE_ID,
        "entry_surface": "upload",
        "api_url": resolved_api_url,
        "api_identity": api_msg,
        "api_resolution_source": api_resolution_source,
        "lane_identity": lane_identity,
        "lane_readiness": lane_readiness,
        "measurement_control_plane": suite_control_plane,
        "api_freshness": freshness,
        "bridge_freshness": bridge_freshness,
        "post_restart_readiness": post_restart_readiness,
        "post_restart_first_leg_recovery": post_restart_first_leg_recovery,
        "bridge_identity": bridge_msg,
        "compiled_targets": [
            {
                "staged_name": str(item.get("staged_name") or ""),
                "source_path": str(item.get("source_path") or ""),
                "target_name": str(item.get("target_name") or ""),
                "required_semantic_checkpoint": str(item.get("required_semantic_checkpoint") or ""),
            }
            for item in selected_targets
        ],
        "run_records": run_records,
        "enterprise_survivability_summary": survivability_summary,
        "comparison_report": report,
    }
    summary_path = output_dir / "compiled-ingest-summary.json"
    report_path = output_dir / "compiled-ingest-compare-report.json"
    write_json(summary_path, run_bundle)
    write_json(report_path, report)
    return {
        "output_dir": str(output_dir),
        "summary": run_bundle,
        "report": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run compiled Spectrum hard-02 through the upload lane.")
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--bridge-url", default="")
    parser.add_argument("--bridge-urls", default="")
    parser.add_argument("--bridge-quarantine-registry", default="")
    parser.add_argument("--bridge-key", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--poll-sec", type=int, default=10)
    parser.add_argument("--analyze-timeout-sec", type=int, default=1800)
    parser.add_argument("--explore-timeout-sec", type=int, default=5400)
    parser.add_argument("--stuck-seconds", type=int, default=900)
    args = parser.parse_args()

    result = run_spectrum_compiled_hard02(
        api_url=str(args.api_url or "").strip(),
        api_key=str(args.api_key or "").strip(),
        bridge_url=str(args.bridge_url or "").strip(),
        bridge_urls=str(args.bridge_urls or "").strip(),
        bridge_quarantine_registry=str(args.bridge_quarantine_registry or "").strip(),
        bridge_key=str(args.bridge_key or "").strip(),
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
        poll_sec=int(args.poll_sec),
        analyze_timeout_sec=int(args.analyze_timeout_sec),
        explore_timeout_sec=int(args.explore_timeout_sec),
        stuck_seconds=int(args.stuck_seconds),
    )
    print(
        json.dumps(
            {
                "output_dir": result["output_dir"],
                "compiled_binary_ingest_success": result["report"]["binary_ingest_proof_succeeded"],
                "semantic_checkpoint_alignment_succeeded": result["report"]["semantic_checkpoint_alignment_succeeded"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
