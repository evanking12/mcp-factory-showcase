from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.spectrum_compiled_ingest import (  # noqa: E402
    SPECTRUM_COMPILED_HARD01_CASE_ID,
    SPECTRUM_COMPILED_HARD01_CHAIN_PLAN,
    SPECTRUM_COMPILED_SUITE_ID,
    build_spectrum_compiled_hard01_report,
    ensure_spectrum_compiled_package_built,
    load_spectrum_authored_hard01_manifest,
    load_spectrum_authored_truth_manifest,
    load_spectrum_compiled_package_manifest,
    load_spectrum_compiled_truth_manifest,
    ordered_spectrum_compiled_hard01_targets,
)
from api.pipeline.core.enterprise_survivability import write_enterprise_survivability_summary  # noqa: E402
from scripts.ops.measurement_control_plane import (  # noqa: E402
    apply_control_plane_to_run_record,
    build_bridge_candidate_registry_packet,
    build_bridge_candidates_from_config,
    build_hard01_baseline_readiness_packet,
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
from scripts.runs.product_route_contract import (  # noqa: E402
    product_contract_fields_for_record as _product_contract_fields_for_record,
    product_contract_summary as _product_contract_summary,
    product_route_authority_for_record as _product_route_authority_for_record,
)
from scripts.runs.product_route_trace import append_trace_event, trace_span  # noqa: E402
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


def _failure_kind_for_record(record: dict[str, Any]) -> str:
    enterprise_authority = dict(record.get("enterprise_survivability_authority") or {})
    enterprise_blocker = str(
        enterprise_authority.get("blocking_signal")
        or enterprise_authority.get("reason_code")
        or ""
    ).strip()
    if enterprise_blocker:
        return enterprise_blocker
    terminalization = dict(record.get("measurement_terminalization") or record.get("job_terminalization") or {})
    kind = str(terminalization.get("terminalization_kind") or terminalization.get("kind") or "").strip()
    phase = str(record.get("phase") or "").strip().lower()
    if kind == "timeout":
        if phase.startswith("analy"):
            return "analyze_timeout"
        if phase.startswith("explor"):
            return "explore_timeout"
        return "timeout"
    if kind and kind != "done":
        return f"runner_{kind}"
    if str(record.get("failure_domain") or "").strip():
        return str(record.get("failure_domain") or "").strip()
    if str(record.get("error") or "").strip():
        return "runner_error"
    if str(record.get("status") or "").strip().lower() != "ok":
        return f"status_{str(record.get('status') or '').strip().lower()}"
    return ""


def _attach_enterprise_branch_authority(
    *,
    run_records: list[dict[str, Any]],
    report: dict[str, Any],
) -> None:
    authority = dict(report.get("branch_invalidation_authority") or {})
    if not authority:
        return
    for record in run_records:
        target_name = str((record.get("chain_context") or {}).get("target_name") or record.get("target") or "").strip()
        if target_name != "audit_trace":
            continue
        record["enterprise_survivability_authority"] = authority
        record["branch_invalidation_authority"] = authority
        run_dir = Path(str(record.get("run_dir") or ""))
        if run_dir:
            write_json(run_dir / "branch-invalidation-authority.json", authority)
        break


def _dependency_blocked_record(
    *,
    run_dir: Path,
    target_name: str,
    dll_path: Path,
    predecessor_targets: list[str],
    missing_predecessors: list[str],
    chain_step: dict[str, Any],
    prior_job_id: str,
    cross_dll_prior_job_ids: list[str],
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    run_authority = {
        "schema_version": "1.0.0",
        "target": target_name,
        "status": "non_decision_bearing",
        "reason_code": "dependency_blocked",
        "failure_domain": "dependency_policy",
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "authoritative_proving": False,
        "decision_bearing": False,
        "blocking_reasons": [f"missing_predecessor:{name}" for name in missing_predecessors],
    }
    terminalization = {
        "schema_version": "1.0.0",
        "target": target_name,
        "terminalization_kind": "dependency_blocked",
        "kind": "dependency_blocked",
        "reason": {
            "code": "dependency_blocked",
            "message": "required predecessor was non-comparable or did not produce a trusted job id",
        },
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "authoritative_proving": False,
        "missing_predecessors": missing_predecessors,
    }
    record = {
        "job_id": "",
        "status": "dependency_blocked",
        "phase": "not_scheduled",
        "target": target_name,
        "dll_name": dll_path.name,
        "dll_path": str(dll_path),
        "run_dir": str(run_dir),
        "binary_hash": _fingerprint_bytes(dll_path),
        "entry_surface": "upload",
        "valid_run": False,
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "authoritative_proving": False,
        "failure_domain": "dependency_policy",
        "run_authority": run_authority,
        "measurement_terminalization": terminalization,
        "chain_context": {
            "target_name": target_name,
            "predecessor_targets": predecessor_targets,
            "prior_job_id": prior_job_id,
            "cross_dll_prior_job_ids": cross_dll_prior_job_ids,
            "required_semantic_checkpoint": str(chain_step["required_semantic_checkpoint"]),
        },
    }
    write_json(run_dir / "run-authority.json", run_authority)
    write_json(run_dir / "measurement-terminalization.json", terminalization)
    write_json(run_dir / "run_result.json", record)
    return record


def run_spectrum_compiled_hard01(
    *,
    api_url: str = "",
    api_key: str = "",
    bridge_url: str = "",
    bridge_urls: str = "",
    bridge_quarantine_registry: str = "",
    bridge_key: str = "",
    output_root: str | Path | None = None,
    stop_after_first_failure: bool = False,
    product_route_required: bool = False,
    case_id: str = SPECTRUM_COMPILED_HARD01_CASE_ID,
    variant_id: str = "compiled_hard01",
    poll_sec: int = 10,
    analyze_timeout_sec: int = 1800,
    explore_timeout_sec: int = 5400,
    stuck_seconds: int = 900,
) -> dict[str, Any]:
    manifest = ensure_spectrum_compiled_package_built()
    compiled_truth = load_spectrum_compiled_truth_manifest()
    authored_truth = load_spectrum_authored_truth_manifest()
    authored_hard = load_spectrum_authored_hard01_manifest()

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
        / case_id
        / timestamp
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    campaign_log = output_dir / "compiled-ingest.log"
    heartbeat_path = output_dir / "heartbeats.json"
    trace_id = str(os.getenv("MCP_FACTORY_PRODUCT_TRACE_ID", "")).strip()
    trace_path = str(os.getenv("MCP_FACTORY_PRODUCT_TRACE_PATH", "")).strip()
    if product_route_required and not trace_path:
        trace_path = str(output_dir / "product-route-trace.jsonl")
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
        runner_name="run_spectrum_compiled_hard01",
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

    selected_targets = ordered_spectrum_compiled_hard01_targets(manifest)
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
        target=SPECTRUM_COMPILED_HARD01_CASE_ID,
        analysis_profile="strict_dll",
        bridge_identities=bridge_identities_by_url,
        bridge_readiness=bridge_readiness_by_url,
        bridge_lane_readiness=bridge_lane_readiness_by_url,
        bridge_stream_health={
            url: hard_family_bridge_stream_health_for_target(SPECTRUM_COMPILED_HARD01_CASE_ID, "strict_dll")
            for url in configured_bridge_urls
        },
        quarantine_registry=resolved_bridge_quarantine_registry,
    )
    suite_control_plane = build_bridge_candidate_registry_packet(
        target=SPECTRUM_COMPILED_HARD01_CASE_ID,
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
        str(step["target_name"]): dict(step) for step in SPECTRUM_COMPILED_HARD01_CHAIN_PLAN
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
        missing_predecessors = [
            name for name in predecessor_targets if not str(successful_job_by_target.get(name) or "").strip()
        ]
        if product_route_required and predecessor_targets and missing_predecessors:
            record = _dependency_blocked_record(
                run_dir=run_dir,
                target_name=target_name,
                dll_path=dll_path,
                predecessor_targets=predecessor_targets,
                missing_predecessors=missing_predecessors,
                chain_step=chain_step,
                prior_job_id=prior_job_id,
                cross_dll_prior_job_ids=cross_dll_prior_job_ids,
            )
            product_route_authority = _product_route_authority_for_record(record)
            record["product_route_authority"] = product_route_authority
            write_json(run_dir / "product-route-authority.json", product_route_authority)
            record.update(_product_contract_fields_for_record(record))
            run_records.append(record)
            append_trace_event(
                trace_path=trace_path,
                trace_id=trace_id,
                span_name="hard01.target",
                event_name="dependency_blocked",
                attributes={"target": target_name, "missing_predecessors": ",".join(missing_predecessors)},
            )
            if stop_after_first_failure:
                break
            continue
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
            "variant_id": variant_id,
            "lane_id": f"spectrum-hard01-{index}",
            "binary_fixture_suite": SPECTRUM_COMPILED_SUITE_ID,
            "entry_surface": "upload",
            "prior_job_id": prior_job_id,
            "chain_step_target": target_name,
            "required_semantic_checkpoint": str(chain_step["required_semantic_checkpoint"]),
            "selected_invocable_names": [str(chain_step["required_semantic_checkpoint"])],
        }
        if product_route_required:
            explore_settings.update(
                {
                    "route_authority_required": True,
                    "green_contract_level_requested": "product_green",
                    "product_route_required": True,
                }
            )
        if trace_id:
            explore_settings["product_trace_id"] = trace_id
            explore_settings["product_trace_path"] = trace_path
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
            bridge_stream_health={
                url: hard_family_bridge_stream_health_for_target(target_name, target_profile)
                for url in configured_bridge_urls
            },
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
        append_trace_event(
            trace_path=trace_path,
            trace_id=trace_id,
            span_name="hard01.control_plane",
            event_name="decision",
            attributes={
                "target": target_name,
                "phase": "pre_run",
                "light": str(target_control_plane.get("light") or ""),
                "reason_code": str(target_control_plane.get("reason_code") or ""),
                "source": "measurement_control_plane",
                "current_run_evidence": False,
            },
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
                with trace_span(
                    trace_path=trace_path,
                    trace_id=trace_id,
                    span_name="hard01.target",
                    attributes={
                        "target": target_name,
                        "variant_id": variant_id,
                        "attempt_index": attempt_index + 1,
                    },
                ):
                    record = run_one(
                        client,
                        REPO_ROOT,
                        run_dir,
                        resolved_api_url,
                        resolved_api_key,
                        target_name,
                        dll_path,
                        variant_id,
                        explore_settings,
                        **run_one_kwargs,
                    )
                if product_route_required:
                    current_run_bridge_health = bridge_stream_health_from_run_record(record)
                    final_candidates = build_bridge_candidates_from_config(
                        bridge_urls=configured_bridge_urls,
                        default_bridge_url="",
                        target=target_name,
                        analysis_profile=target_profile,
                        bridge_identities=bridge_identities_by_url,
                        bridge_readiness=bridge_readiness_by_url,
                        bridge_lane_readiness=bridge_lane_readiness_by_url,
                        bridge_stream_health={url: current_run_bridge_health for url in configured_bridge_urls},
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
                        bridge_candidates=final_candidates,
                        evidence_paths=[
                            str((run_dir / "measurement-control-plane.json").relative_to(output_dir)).replace("\\", "/"),
                            str((run_dir / "run-authority.json").relative_to(output_dir)).replace("\\", "/"),
                            "lane-readiness.json",
                            "lane-identity.json",
                        ],
                    )
                    write_json(run_dir / "measurement-control-plane.json", target_control_plane)
                    append_trace_event(
                        trace_path=trace_path,
                        trace_id=trace_id,
                        span_name="hard01.control_plane",
                        event_name="decision",
                        attributes={
                            "target": target_name,
                            "phase": "post_run",
                            "light": str(target_control_plane.get("light") or ""),
                            "reason_code": str(target_control_plane.get("reason_code") or ""),
                            "source": str(current_run_bridge_health.get("source") or ""),
                            "current_run_evidence": bool(current_run_bridge_health.get("current_run_authority")),
                        },
                    )
                record = apply_control_plane_to_run_record(
                    run_dir=run_dir,
                    record=record,
                    control_plane=target_control_plane,
                )
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
        if product_route_required:
            product_route_authority = _product_route_authority_for_record(record)
            record["product_route_authority"] = product_route_authority
            write_json(run_dir / "product-route-authority.json", product_route_authority)
            record.update(_product_contract_fields_for_record(record))
        run_records.append(record)
        job_id = str(record.get("job_id") or "").strip()
        record_trusted = _is_trusted_predecessor_record(record)
        if product_route_required:
            record_trusted = record_trusted and bool(record.get("product_green_eligible"))
        if record_trusted:
            successful_job_by_target[target_name] = job_id
        if product_route_required and stop_after_first_failure and not bool(record.get("product_green_eligible")):
            break
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

    report = build_spectrum_compiled_hard01_report(
        output_dir=output_dir,
        package_manifest=load_spectrum_compiled_package_manifest(),
        compiled_truth_manifest=compiled_truth,
        authored_truth_manifest=authored_truth,
        authored_hard_manifest=authored_hard,
        run_records=run_records,
    )
    if case_id != SPECTRUM_COMPILED_HARD01_CASE_ID:
        report["case_id"] = case_id
    _attach_enterprise_branch_authority(run_records=run_records, report=report)
    if product_route_required:
        for record in run_records:
            record.update(_product_contract_fields_for_record(record))
    green_contract = (
        _product_contract_summary(
            run_records,
            report,
            expected_target_count=len(SPECTRUM_COMPILED_HARD01_CHAIN_PLAN),
            failure_kind_for_record=_failure_kind_for_record,
        )
        if product_route_required
        else {
            "green_contract_level": "compatibility_green",
            "product_green_eligible": False,
            "route_authority_required": False,
            "ghidra_required": False,
            "route_authority_present": False,
            "safe_to_compare": bool(report.get("binary_ingest_proof_succeeded")),
            "semantic_proof_satisfied": bool(report.get("semantic_checkpoint_alignment_succeeded")),
            "authoritative_proving": bool(
                report.get("binary_ingest_proof_succeeded")
                and report.get("semantic_checkpoint_alignment_succeeded")
            ),
            "blocking_signal": "",
            "per_target_green_contract": [],
        }
    )
    report.update({key: value for key, value in green_contract.items() if key != "per_target_green_contract"})
    survivability_summary = write_enterprise_survivability_summary(
        output_dir=output_dir,
        suite_id=SPECTRUM_COMPILED_SUITE_ID,
        case_id=case_id,
        run_records=run_records,
        chain_plan=SPECTRUM_COMPILED_HARD01_CHAIN_PLAN,
    )
    report["measurement_control_plane"] = suite_control_plane
    report["enterprise_survivability_summary"] = survivability_summary
    hard01_baseline_readiness = build_hard01_baseline_readiness_packet(
        case_id=case_id,
        lane_readiness=lane_readiness,
        suite_control_plane=suite_control_plane,
        run_records=run_records,
        control_plane_contracts={
            "tier2_traffic_light_enforcement": True,
            "tier3_selected_bridge_routing": True,
            "tier4_quarantine_recovery_selection": True,
        },
    )
    write_json(output_dir / "hard01-baseline-readiness.json", hard01_baseline_readiness)
    report["hard01_baseline_readiness"] = hard01_baseline_readiness

    run_bundle = {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": case_id,
        "entry_surface": "upload",
        "product_route_required": bool(product_route_required),
        "trace_id": trace_id,
        "trace_path": trace_path,
        "telemetry_diagnostic_only": True,
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
        "hard01_baseline_readiness": hard01_baseline_readiness,
        "comparison_report": report,
        **green_contract,
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
    parser = argparse.ArgumentParser(description="Run compiled Spectrum hard-01 through the upload lane.")
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--bridge-url", default="")
    parser.add_argument("--bridge-urls", default="")
    parser.add_argument("--bridge-quarantine-registry", default="")
    parser.add_argument("--bridge-key", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--stop-after-first-failure", action="store_true")
    parser.add_argument("--poll-sec", type=int, default=10)
    parser.add_argument("--analyze-timeout-sec", type=int, default=1800)
    parser.add_argument("--explore-timeout-sec", type=int, default=5400)
    parser.add_argument("--stuck-seconds", type=int, default=900)
    args = parser.parse_args()

    result = run_spectrum_compiled_hard01(
        api_url=str(args.api_url or "").strip(),
        api_key=str(args.api_key or "").strip(),
        bridge_url=str(args.bridge_url or "").strip(),
        bridge_urls=str(args.bridge_urls or "").strip(),
        bridge_quarantine_registry=str(args.bridge_quarantine_registry or "").strip(),
        bridge_key=str(args.bridge_key or "").strip(),
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
        stop_after_first_failure=bool(args.stop_after_first_failure),
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
