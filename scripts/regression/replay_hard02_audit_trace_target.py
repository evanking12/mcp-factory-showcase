from __future__ import annotations

import argparse
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

from api.pipeline.core.enterprise_survivability import write_enterprise_survivability_summary  # noqa: E402
from api.pipeline.core.spectrum_compiled_ingest import (  # noqa: E402
    SPECTRUM_COMPILED_HARD02_CASE_ID,
    SPECTRUM_COMPILED_HARD02_CHAIN_PLAN,
    SPECTRUM_COMPILED_SUITE_ID,
    ensure_spectrum_compiled_package_built,
    ordered_spectrum_compiled_hard02_targets,
)
from runtime.runtime_contract import local_bridge_base_url  # noqa: E402
from scripts.ops.measurement_control_plane import (  # noqa: E402
    apply_control_plane_to_run_record,
    build_bridge_candidate_registry_packet,
    build_bridge_candidates_from_config,
    bridge_stream_health_from_run_record,
    control_plane_allows_run,
    selected_bridge_url_from_registry,
    split_configured_bridge_urls,
    write_control_plane_blocked_result,
)
from scripts.ops.nightly_groundtruth import (  # noqa: E402
    ApiClient,
    build_lane_identity_packet,
    build_lane_readiness_packet,
    build_post_restart_readiness_probe,
    collect_api_identity,
    collect_bridge_identity,
    collect_runner_identity,
    ensure_local_api_freshness,
    ensure_local_bridge_freshness,
    ensure_strict_local_lane_preflight,
    fetch_api_readiness,
    fetch_bridge_readiness,
    log_line,
    resolve_api_url,
    run_one,
    verify_api_identity_for_resolution,
    verify_bridge_identity,
    write_json,
)
from scripts.regression.summarize_product_proof_artifacts import (  # noqa: E402
    summarize_product_proof_artifacts,
)
from scripts.runs.run_spectrum_compiled_hard02 import (  # noqa: E402
    RUNNER_VERSION as HARD02_RUNNER_VERSION,
    _bridge_stream_health_by_url,
    _fingerprint_bytes,
    _is_trusted_predecessor_record,
    _load_repo_env_value,
    _run_one_supports_lane_readiness,
)


AUDIT_TARGET = "audit_trace"
SETTLEMENT_TARGET = "settlement_reconcile"
SETTLEMENT_FUNCTION = "SP_InvalidateStaleAttestedRelease"
AUDIT_FUNCTION = "SP_RecordStaleAttestationInvalidation"
CLAIM_CEILING = "target_local_replay_only"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_json_or_none(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return _read_json(path)
    except Exception:
        return None


def _repo_resolve(path_value: Any) -> Path:
    path = Path(str(path_value or ""))
    return path if path.is_absolute() else (REPO_ROOT / path)


def _target_dir(proof_root: Path, target_name: str) -> Path | None:
    runs_root = proof_root / "runs"
    if not runs_root.exists():
        return None
    for candidate in sorted(runs_root.iterdir()):
        if candidate.is_dir() and candidate.name.endswith(f"-{target_name}"):
            return candidate
    return None


def _chain_step(target_name: str) -> dict[str, Any]:
    for step in SPECTRUM_COMPILED_HARD02_CHAIN_PLAN:
        if str(step.get("target_name") or "") == target_name:
            return dict(step)
    raise KeyError(target_name)


def _records_by_target(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(record.get("target") or ""): dict(record)
        for record in list(summary.get("run_records") or [])
        if str(record.get("target") or "")
    }


def _latest_function_finding(findings: Any, function_name: str) -> dict[str, Any]:
    rows = findings if isinstance(findings, list) else []
    matches = [row for row in rows if isinstance(row, dict) and row.get("function") == function_name]
    return dict(matches[-1]) if matches else {}


def _settlement_stale_outputs(settlement_dir: Path) -> dict[str, Any]:
    findings = _read_json_or_none(settlement_dir / "findings.json") or []
    row = _latest_function_finding(findings, SETTLEMENT_FUNCTION)
    working_call = dict(row.get("working_call") or {})
    return {
        "function": SETTLEMENT_FUNCTION,
        "status_canonical": str(row.get("status_canonical") or row.get("status") or ""),
        "stale_attestation_token": str(working_call.get("out_stale_attestation_token") or ""),
        "stale_reason": str(working_call.get("out_stale_reason") or ""),
        "attestation_epoch": working_call.get("attestation_epoch"),
        "attestation_packet": str(working_call.get("attestation_packet") or ""),
    }


def extract_trusted_predecessor_boundary(source_proof_root: Path) -> dict[str, Any]:
    source_proof_root = source_proof_root.resolve()
    if not source_proof_root.exists() or not source_proof_root.is_dir():
        return {
            "valid": False,
            "blocking_signal": "trusted_predecessor_boundary_unavailable",
            "reason": "source_proof_root_missing",
            "source_proof_root": str(source_proof_root),
        }
    summary = _read_json_or_none(source_proof_root / "compiled-ingest-summary.json")
    if not isinstance(summary, dict):
        return {
            "valid": False,
            "blocking_signal": "trusted_predecessor_boundary_unavailable",
            "reason": "compiled_ingest_summary_missing",
            "source_proof_root": str(source_proof_root),
        }

    records = _records_by_target(summary)
    predecessor_targets = list(_chain_step(AUDIT_TARGET).get("predecessor_targets") or [])
    missing: list[str] = []
    untrusted: list[str] = []
    job_ids: dict[str, str] = {}
    run_dirs: dict[str, str] = {}
    for target_name in predecessor_targets:
        record = records.get(str(target_name))
        if not record:
            missing.append(str(target_name))
            continue
        run_dir = _repo_resolve(record.get("run_dir"))
        record["run_dir"] = str(run_dir)
        if not run_dir.exists() or not (run_dir / "run_result.json").exists() or not (run_dir / "findings.json").exists():
            missing.append(str(target_name))
            continue
        if not _is_trusted_predecessor_record(record) or not bool(record.get("authoritative_proving")):
            untrusted.append(str(target_name))
            continue
        job_ids[str(target_name)] = str(record.get("job_id") or "")
        run_dirs[str(target_name)] = str(run_dir)

    settlement_dir = Path(run_dirs.get(SETTLEMENT_TARGET, ""))
    stale_outputs = _settlement_stale_outputs(settlement_dir) if settlement_dir.exists() else {}
    if (
        not stale_outputs
        or stale_outputs.get("status_canonical") != "verified_success"
        or not stale_outputs.get("stale_attestation_token")
        or not stale_outputs.get("stale_reason")
    ):
        untrusted.append(SETTLEMENT_TARGET + ":stale_outputs_missing")

    valid = not missing and not untrusted
    return {
        "valid": valid,
        "blocking_signal": "" if valid else "trusted_predecessor_boundary_unavailable",
        "reason": "" if valid else "missing_or_untrusted_predecessor",
        "source_proof_root": str(source_proof_root),
        "last_trusted_boundary": "08-settlement_reconcile",
        "audit_target": AUDIT_TARGET,
        "predecessor_targets": predecessor_targets,
        "job_ids_by_target": job_ids,
        "run_dirs_by_target": run_dirs,
        "prior_job_id": str(job_ids.get(SETTLEMENT_TARGET) or ""),
        "cross_dll_prior_job_ids": [job_ids[name] for name in predecessor_targets if job_ids.get(name)],
        "missing_predecessors": missing,
        "untrusted_predecessors": untrusted,
        "settlement_stale_outputs": stale_outputs,
    }


def classify_audit_trace_result(
    *,
    audit_run_dir: Path,
    boundary: dict[str, Any],
    record: dict[str, Any],
    artifact_recovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    findings = _read_json_or_none(audit_run_dir / "findings.json") or []
    row = _latest_function_finding(findings, AUDIT_FUNCTION)
    working_call = dict(row.get("working_call") or {})
    status = str(row.get("status_canonical") or row.get("status") or "")
    stale_outputs = dict(boundary.get("settlement_stale_outputs") or {})
    expected_token = str(stale_outputs.get("stale_attestation_token") or "")
    expected_reason = str(stale_outputs.get("stale_reason") or "")
    observed_token = str(
        working_call.get("stale_attestation_token")
        or working_call.get("out_stale_attestation_token")
        or ""
    )
    observed_reason = str(working_call.get("stale_reason") or working_call.get("out_stale_reason") or "")

    recovery = artifact_recovery or {}
    if bool(record.get("authoritative_proving")) and status == "verified_success":
        return {
            "blocking_signal": "checkpoint_target_replay_green",
            "classification": "local_bug",
            "authority_present": True,
            "reason": "audit_trace_target_replay_decision_bearing",
            "audit_status_canonical": status,
        }
    if (
        status == "verified_success"
        and bool(recovery.get("s07_finalize_completed"))
        and bool(recovery.get("findings_recovered"))
    ):
        return {
            "blocking_signal": "checkpoint_target_replay_green",
            "classification": "local_bug",
            "authority_present": True,
            "reason": "audit_trace_target_replay_decision_bearing_after_s07_artifact_recovery",
            "audit_status_canonical": status,
            "terminalization_recovered": True,
            "recovery_source": str(recovery.get("source") or ""),
        }
    if status == "verified_success":
        return {
            "blocking_signal": "target_local_s07_finalize_terminalization_missing",
            "classification": "missing_system",
            "authority_present": False,
            "reason": "verified_audit_call_not_decision_bearing_and_s07_recovery_unavailable",
            "audit_status_canonical": status,
        }
    if expected_token and expected_reason and (not observed_token or observed_token != expected_token or observed_reason != expected_reason):
        return {
            "blocking_signal": "stale_attestation_forwarding_missing",
            "classification": "family_blocker",
            "authority_present": False,
            "reason": "audit_trace_did_not_consume_verified_settlement_stale_outputs",
            "audit_status_canonical": status,
            "expected_stale_attestation_token": expected_token,
            "observed_stale_attestation_token": observed_token,
            "expected_stale_reason": expected_reason,
            "observed_stale_reason": observed_reason,
        }
    if status == "functional_precondition_unmet":
        return {
            "blocking_signal": "stale_attestation_object_state_precondition_unmet",
            "classification": "family_blocker",
            "authority_present": False,
            "reason": "fixture_rejected_present_stale_attestation_inputs",
            "audit_status_canonical": status,
        }
    return {
        "blocking_signal": "stale_attestation_object_bound_authority_missing",
        "classification": "family_blocker",
        "authority_present": False,
        "reason": "audit_trace_non_authoritative_without_sharper_forwarding_signal",
        "audit_status_canonical": status,
    }


def _write_replay_result(output_dir: Path, payload: dict[str, Any]) -> None:
    write_json(output_dir / "target-local-replay-result.json", payload)


def _job_artifact_dir(job_id: str) -> Path:
    return REPO_ROOT / "local-data" / "artifacts" / str(job_id or "")


def _copy_if_present(source: Path, dest: Path) -> bool:
    if not source.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return True


def recover_target_local_artifacts_from_job_store(*, run_dir: Path, job_id: str) -> dict[str, Any]:
    """Recover finalized target-local evidence when API status lags behind S-07 artifacts."""
    job_dir = _job_artifact_dir(job_id)
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
    row = _latest_function_finding(findings, AUDIT_FUNCTION)
    status = str(row.get("status_canonical") or row.get("status") or "")
    recovery = {
        "recovered": bool(copied),
        "source": "local_job_artifact_store",
        "job_id": str(job_id or ""),
        "job_artifact_dir": str(job_dir),
        "copied_artifacts": copied,
        "s07_finalize_completed": bool(checkpoint.get("completed")),
        "findings_recovered": bool(row),
        "audit_status_canonical": status,
    }
    write_json(run_dir / "target-local-artifact-recovery.json", recovery)
    return recovery


def replay_hard02_audit_trace_target(
    *,
    source_proof_root: Path,
    output_root: Path,
    mode: str = "strict",
    api_url: str = "",
    api_key: str = "",
    bridge_url: str = "",
    bridge_urls: str = "",
    bridge_quarantine_registry: str = "",
    bridge_key: str = "",
    poll_sec: int = 10,
    analyze_timeout_sec: int = 1800,
    explore_timeout_sec: int = 5400,
    stuck_seconds: int = 900,
) -> dict[str, Any]:
    output_dir = Path(output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    campaign_log = output_dir / "target-local-replay.log"
    boundary = extract_trusted_predecessor_boundary(Path(source_proof_root))
    if not boundary.get("valid"):
        result = {
            "schema_version": "1.0.0",
            "mode": mode,
            "claim_ceiling": CLAIM_CEILING,
            "product_green_claimed": False,
            "safe_to_compare": False,
            "source_mutated": False,
            "checkpoint_first_result": "unavailable",
            "blocking_signal": "trusted_predecessor_boundary_unavailable",
            "classification": "missing_system",
            "boundary": boundary,
        }
        _write_replay_result(output_dir, result)
        return result

    manifest = ensure_spectrum_compiled_package_built()
    audit_target = next(
        item for item in ordered_spectrum_compiled_hard02_targets(manifest) if str(item.get("target_name") or "") == AUDIT_TARGET
    )
    dll_path = (REPO_ROOT / str(audit_target.get("source_path") or "")).resolve()

    resolved_api_key = str(api_key or os.getenv("MCP_FACTORY_API_KEY", "") or _load_repo_env_value("PIPELINE_API_KEY")).strip()
    resolved_bridge_url = str(
        bridge_url
        or os.getenv("GUI_BRIDGE_URL", "")
        or _load_repo_env_value("GUI_BRIDGE_URL")
        or local_bridge_base_url()
    ).strip()
    configured_bridge_urls = split_configured_bridge_urls(
        bridge_urls or os.getenv("GUI_BRIDGE_CANDIDATE_URLS", "") or _load_repo_env_value("GUI_BRIDGE_CANDIDATE_URLS"),
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

    heartbeat_path = output_dir / "heartbeats.json"
    bridge_freshness = ensure_local_bridge_freshness(REPO_ROOT, resolved_bridge_url, resolved_bridge_key, campaign_log=campaign_log)
    if bridge_freshness.get("freshness_verdict") == "restart_blocked_unmanaged_owner":
        raise RuntimeError("bridge_freshness_blocked_unmanaged_owner")
    freshness = ensure_local_api_freshness(
        REPO_ROOT,
        resolved_api_url,
        resolved_api_key,
        campaign_log=campaign_log,
        force_restart_reason=("restart_required_bridge_restarted" if bool(bridge_freshness.get("restart_performed")) else ""),
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
        runner_name="replay_hard02_audit_trace_target",
        runner_version=HARD02_RUNNER_VERSION,
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

    post_restart_readiness = build_post_restart_readiness_probe(performed=False)
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

    chain_step = _chain_step(AUDIT_TARGET)
    run_dir = output_dir / "runs" / "09-audit_trace"
    run_dir.mkdir(parents=True, exist_ok=True)
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
        "variant_id": "compiled_hard02_target_local_replay",
        "lane_id": "spectrum-hard02-audit-trace-replay",
        "binary_fixture_suite": SPECTRUM_COMPILED_SUITE_ID,
        "entry_surface": "upload",
        "prior_job_id": str(boundary.get("prior_job_id") or ""),
        "cross_dll_prior_job_ids": list(boundary.get("cross_dll_prior_job_ids") or []),
        "chain_step_target": AUDIT_TARGET,
        "required_semantic_checkpoint": str(chain_step["required_semantic_checkpoint"]),
        "selected_invocable_names": [str(chain_step["required_semantic_checkpoint"])],
        "target_local_replay": True,
        "last_trusted_boundary": str(boundary.get("last_trusted_boundary") or ""),
    }
    target_profile = str(explore_settings.get("analysis_profile") or "strict_dll")
    target_candidates = build_bridge_candidates_from_config(
        bridge_urls=configured_bridge_urls,
        default_bridge_url="",
        target=AUDIT_TARGET,
        analysis_profile=target_profile,
        bridge_identities=bridge_identities_by_url,
        bridge_readiness=bridge_readiness_by_url,
        bridge_lane_readiness=bridge_lane_readiness_by_url,
        bridge_stream_health=_bridge_stream_health_by_url(
            bridge_urls=configured_bridge_urls,
            target_name=AUDIT_TARGET,
            analysis_profile=target_profile,
        ),
        quarantine_registry=resolved_bridge_quarantine_registry,
    )
    target_control_plane = build_bridge_candidate_registry_packet(
        target=AUDIT_TARGET,
        analysis_profile=target_profile,
        required_capabilities=["analyze"],
        runner_identity=runner_identity,
        api_identity=api_identity_payload,
        api_readiness=api_readiness_payload,
        lane_readiness=lane_readiness,
        bridge_candidates=target_candidates,
        evidence_paths=[
            "runs/09-audit_trace/measurement-control-plane.json",
            "lane-readiness.json",
            "lane-identity.json",
        ],
    )
    selected_bridge_url = selected_bridge_url_from_registry(target_control_plane)
    if selected_bridge_url:
        explore_settings["selected_bridge_url"] = selected_bridge_url
        explore_settings["selected_bridge_candidate_id"] = str(target_control_plane.get("selected_candidate_id") or "")
    write_json(run_dir / "measurement-control-plane.json", target_control_plane)
    if not control_plane_allows_run(target_control_plane):
        record = write_control_plane_blocked_result(
            run_dir=run_dir,
            control_plane=target_control_plane,
            dll_name=dll_path.name,
            dll_path=str(dll_path),
            binary_hash=_fingerprint_bytes(dll_path),
            entry_surface="upload",
        )
    else:
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
        log_line(f"target-local-replay-start target={AUDIT_TARGET} dll={dll_path.name}", campaign_log)
        record = run_one(
            client,
            REPO_ROOT,
            run_dir,
            resolved_api_url,
            resolved_api_key,
            AUDIT_TARGET,
            dll_path,
            "compiled_hard02_target_local_replay",
            explore_settings,
            **run_one_kwargs,
        )
        current_run_bridge_health = bridge_stream_health_from_run_record(record)
        pre_run_control_plane = target_control_plane
        final_candidates = build_bridge_candidates_from_config(
            bridge_urls=configured_bridge_urls,
            default_bridge_url="",
            target=AUDIT_TARGET,
            analysis_profile=target_profile,
            bridge_identities=bridge_identities_by_url,
            bridge_readiness=bridge_readiness_by_url,
            bridge_lane_readiness=bridge_lane_readiness_by_url,
            bridge_stream_health=_bridge_stream_health_by_url(
                bridge_urls=configured_bridge_urls,
                target_name=AUDIT_TARGET,
                analysis_profile=target_profile,
                selected_bridge_url=selected_bridge_url,
                current_run_health=current_run_bridge_health,
            ),
            quarantine_registry=resolved_bridge_quarantine_registry,
        )
        target_control_plane = build_bridge_candidate_registry_packet(
            target=AUDIT_TARGET,
            analysis_profile=target_profile,
            required_capabilities=["analyze"],
            runner_identity=runner_identity,
            api_identity=api_identity_payload,
            api_readiness=api_readiness_payload,
            lane_readiness=lane_readiness,
            bridge_candidates=final_candidates,
            evidence_paths=[
                "runs/09-audit_trace/measurement-control-plane.json",
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

    artifact_recovery = recover_target_local_artifacts_from_job_store(
        run_dir=run_dir,
        job_id=str(record.get("job_id") or ""),
    )

    record.setdefault("explore_settings", explore_settings)
    record["measurement_control_plane"] = target_control_plane
    record["dll_name"] = dll_path.name
    record["dll_path"] = str(dll_path)
    record["run_dir"] = str(run_dir)
    record["binary_hash"] = _fingerprint_bytes(dll_path)
    record["entry_surface"] = "upload"
    record["target_local_replay"] = True
    record["chain_context"] = {
        "target_name": AUDIT_TARGET,
        "predecessor_targets": list(chain_step.get("predecessor_targets") or []),
        "prior_job_id": str(boundary.get("prior_job_id") or ""),
        "cross_dll_prior_job_ids": list(boundary.get("cross_dll_prior_job_ids") or []),
        "required_semantic_checkpoint": str(chain_step["required_semantic_checkpoint"]),
    }
    source_records = list((_read_json(Path(source_proof_root) / "compiled-ingest-summary.json").get("run_records") or []))
    records_by_target = _records_by_target({"run_records": source_records})
    combined_records = [
        records_by_target[name]
        for name in list(chain_step.get("predecessor_targets") or [])
        if name in records_by_target
    ] + [record]
    survivability_summary = write_enterprise_survivability_summary(
        output_dir=output_dir,
        suite_id=SPECTRUM_COMPILED_SUITE_ID,
        case_id=SPECTRUM_COMPILED_HARD02_CASE_ID,
        run_records=combined_records,
        chain_plan=SPECTRUM_COMPILED_HARD02_CHAIN_PLAN,
    )
    write_json(output_dir / "enterprise-survivability-summary.json", survivability_summary)
    classification = classify_audit_trace_result(
        audit_run_dir=run_dir,
        boundary=boundary,
        record=record,
        artifact_recovery=artifact_recovery,
    )
    write_json(
        output_dir / "compiled-ingest-summary.json",
        {
            "schema_version": "1.0.0",
            "suite_id": SPECTRUM_COMPILED_SUITE_ID,
            "case_id": SPECTRUM_COMPILED_HARD02_CASE_ID,
            "claim_ceiling": CLAIM_CEILING,
            "product_green_claimed": False,
            "target_local_replay": True,
            "blocking_signal": classification.get("blocking_signal"),
            "source_proof_root": str(Path(source_proof_root).resolve()),
            "run_records": combined_records,
        },
    )
    artifact_summary = summarize_product_proof_artifacts(
        proof_root=output_dir,
        target=AUDIT_TARGET,
        output=output_dir / "proof-artifact-summary.json",
    )
    result = {
        "schema_version": "1.0.0",
        "mode": mode,
        "claim_ceiling": CLAIM_CEILING,
        "product_green_claimed": False,
        "safe_to_compare": bool(record.get("safe_to_compare", False)),
        "source_mutated": False,
        "checkpoint_first_result": "used",
        "last_trusted_boundary": str(boundary.get("last_trusted_boundary") or ""),
        "changed_seam": "hard02.audit_trace.stale_attestation_authority",
        "boundary": boundary,
        "run_record": {
            "target": AUDIT_TARGET,
            "job_id": str(record.get("job_id") or ""),
            "status": str(record.get("status") or ""),
            "phase": str(record.get("phase") or ""),
            "authoritative_proving": bool(record.get("authoritative_proving")),
            "run_dir": str(run_dir),
        },
        "artifact_recovery": artifact_recovery,
        "classification": classification.get("classification"),
        "blocking_signal": classification.get("blocking_signal"),
        "classification_details": classification,
        "artifact_summary": artifact_summary,
    }
    _write_replay_result(output_dir, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay only Hard02 audit_trace from trusted predecessor artifacts.")
    parser.add_argument("--source-proof-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--mode", choices=["strict"], default="strict")
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--bridge-url", default="")
    parser.add_argument("--bridge-urls", default="")
    parser.add_argument("--bridge-quarantine-registry", default="")
    parser.add_argument("--bridge-key", default="")
    parser.add_argument("--poll-sec", type=int, default=10)
    parser.add_argument("--analyze-timeout-sec", type=int, default=1800)
    parser.add_argument("--explore-timeout-sec", type=int, default=5400)
    parser.add_argument("--stuck-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    result = replay_hard02_audit_trace_target(
        source_proof_root=args.source_proof_root,
        output_root=args.output_root,
        mode=args.mode,
        api_url=args.api_url,
        api_key=args.api_key,
        bridge_url=args.bridge_url,
        bridge_urls=args.bridge_urls,
        bridge_quarantine_registry=args.bridge_quarantine_registry,
        bridge_key=args.bridge_key,
        poll_sec=args.poll_sec,
        analyze_timeout_sec=args.analyze_timeout_sec,
        explore_timeout_sec=args.explore_timeout_sec,
        stuck_seconds=args.stuck_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("blocking_signal") != "trusted_predecessor_boundary_unavailable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
