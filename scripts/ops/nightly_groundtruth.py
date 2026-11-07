from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

import psutil
import requests

from api.infra.local_lane_admission import (
    LOCAL_LANE_ADMISSION_VERSION,
)
from api.infra.service_identity import (
    PIPELINE_SCHEMA_VERSION,
    REPO_ROOT,
    STATUS_SCHEMA_VERSION,
    TRUST_CONTRACT_VERSION,
    build_api_identity,
    build_bridge_identity,
    build_lane_comparability_contract,
    build_minimal_compatibility_contract,
    build_runner_identity,
    git_identity,
)
from api.pipeline.core.job_terminalization import (
    build_job_terminalization_payload,
    is_quasi_terminal_clarify_signature as _shared_is_quasi_terminal_clarify_signature,
    status_progress_text as _shared_status_progress_text,
)
from api.pipeline.core.run_authority import build_run_authority_payload
from api.pipeline.core.scoring_scope import canonical_status_map, target_scope_names
from runtime.runtime_contract import (
    local_lane_admission_path,
    local_api_base_url,
    local_api_candidate_urls,
    local_bridge_base_url,
    runtime_contract_id,
)


TERMINAL_ANALYZE_STATUS = {"done", "error"}
TERMINAL_EXPLORE_PHASE = {"done", "awaiting_clarification", "error", "failed", "cancelled", "canceled"}
SUCCESS_LIKE_FINDING_STATUSES = {
    "success",
    "verified_success",
    "functional",
    "functional_precondition_unmet",
    "inferred_success",
}
DEFAULT_LOCAL_API_CANDIDATES = local_api_candidate_urls()
LOCAL_API_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOCAL_API_MAX_AGE_SECONDS = 5 * 60 * 60
LOCAL_BRIDGE_MAX_AGE_SECONDS = LOCAL_API_MAX_AGE_SECONDS
BRIDGE_SECRET_ENV_FILES = (
    REPO_ROOT / "scripts" / "bridge" / ".bridge.env",
    REPO_ROOT / "scripts" / ".bridge.env",
    REPO_ROOT / ".env",
)
RESTART_READINESS_PROBE_TARGET = "session_bootstrap"
RESTART_READINESS_REQUIRED_CHECKPOINT = "SP_OpenOperatorSession"
RESTART_READINESS_MAX_ROUNDS = 1
RESTART_READINESS_MAX_TOOL_CALLS = 2
RESTART_READINESS_ANALYZE_TIMEOUT_SEC = 180
RESTART_READINESS_EXPLORE_TIMEOUT_SEC = 180
RESTART_READINESS_STUCK_SECONDS = 90
QUASI_TERMINAL_CLARIFY_STAGE = "s06_gaps"
QUASI_TERMINAL_CLARIFY_MESSAGE_TOKEN = "finalizing harmonized state"
REQUEST_ERROR_GRACE_SECONDS = 30
LIVE_OBSERVABILITY_SOFT_STALL_SECONDS = 60
TERMINALIZATION_TERMINAL_KINDS = {
    "done",
    "error",
    "timeout",
    "cancelled",
    "canceled",
    "awaiting_clarification_authoritative",
    "quasi_terminal_stall",
    "runner_invalid",
    "session_capture_failed",
    "bridge_execution_failed",
    "api_contract_failed",
}
MEASUREMENT_TERMINALIZATION_REASON_CODES = {
    "discovery_empty",
    "analyzer_error",
    "analyzer_timeout",
    "output_missing",
    "lane_or_infra_unavailable",
    "unknown_measurement_failure",
}
POST_EXPLORE_ARTIFACT_FETCH_REASON_CODES = {
    "post_explore_verdict_fetch_connection_reset",
    "post_explore_verdict_fetch_failed",
    "post_explore_findings_fetch_failed",
    "unknown_post_explore_artifact_fetch_failure",
}
POST_EXPLORE_ARTIFACT_FETCH_MAX_ATTEMPTS = 3
POST_EXPLORE_ARTIFACT_FETCH_RETRY_DELAY_SECONDS = 0.5
ANALYZE_AUTHORITY_OUTPUT_PATHS = (
    "job-status-analyze.json",
    "discovery-output-authority.json",
    "bridge-analyzer-authority.json",
    "analyzer-runtime-authority.json",
    "session/discovery_meta.json",
    "session/invocables_map.json",
    "session/evidence/stage-00-setup/invocables-map.json",
    "session/evidence/stage-00b-static-evidence/static-analysis.json",
)
LANE_OR_INFRA_UNAVAILABLE_REASONS = {
    "api_readiness_unavailable",
    "bridge_readiness_unavailable",
    "api_identity_unavailable",
    "bridge_identity_unavailable",
    "api_local_lane_admission_red",
    "bridge_local_lane_admission_red",
    "api_health_unreachable",
    "bridge_health_unreachable",
    "runner_git_sha_missing",
    "api_git_sha_missing",
    "bridge_git_sha_missing",
    "runner_api_git_sha_mismatch",
    "runner_bridge_git_sha_mismatch",
    "api_bridge_git_sha_mismatch",
    "git_sha_mismatch",
}


class QuasiTerminalClarifyStall(TimeoutError):
    def __init__(
        self,
        job_id: str,
        status_payload: dict[str, Any],
        *,
        stable_for_seconds: int,
    ) -> None:
        self.job_id = str(job_id or "").strip()
        self.status_payload = dict(status_payload or {})
        self.stable_for_seconds = int(stable_for_seconds or 0)
        self.terminalization_payload: dict[str, Any] | None = None
        super().__init__(
            f"explore quasi-terminal clarify stall for {self.job_id} (>{self.stable_for_seconds}s stable signature)"
        )


def _utc_iso_from_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.utcfromtimestamp(float(value)).isoformat() + "Z"
    except Exception:
        return None


def _local_connection_details(service_url: str) -> dict[str, Any]:
    parsed = urlparse(str(service_url or "").strip())
    host = (parsed.hostname or "").strip().lower()
    port = parsed.port
    return {
        "host": host,
        "port": port,
        "is_local": host in LOCAL_API_HOSTS and port is not None,
    }


def _local_api_connection_details(api_url: str) -> dict[str, Any]:
    return _local_connection_details(api_url)


def _local_bridge_connection_details(bridge_url: str) -> dict[str, Any]:
    return _local_connection_details(bridge_url)


def _read_local_process_info(port: int) -> dict[str, Any] | None:
    try:
        connections = psutil.net_connections(kind="inet")
    except Exception:
        return None
    for conn in connections:
        laddr = getattr(conn, "laddr", None)
        if not laddr:
            continue
        if int(getattr(laddr, "port", 0) or 0) != int(port):
            continue
        if getattr(conn, "status", "") != psutil.CONN_LISTEN:
            continue
        pid = getattr(conn, "pid", None)
        if not pid:
            continue
        try:
            proc = psutil.Process(pid)
            cmdline = " ".join(proc.cmdline())
            created_at = float(proc.create_time())
            return {
                "pid": int(pid),
                "name": proc.name(),
                "command_line": cmdline,
                "created_at": created_at,
                "started_at": _utc_iso_from_timestamp(created_at),
            }
        except Exception:
            return {
                "pid": int(pid),
                "name": "",
                "command_line": "",
                "created_at": None,
                "started_at": None,
            }
    return None


def _read_local_api_process_info(port: int) -> dict[str, Any] | None:
    return _read_local_process_info(port)


def _read_local_bridge_process_info(port: int) -> dict[str, Any] | None:
    return _read_local_process_info(port)


def _current_repo_git_sha(repo_root: Path) -> str:
    git_sha, _dirty = git_identity(repo_root)
    return str(git_sha or "").strip()


def _latest_tree_mtime(root: Path) -> float | None:
    latest = None
    if not root.exists():
        return None
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            mtime = float(path.stat().st_mtime)
        except OSError:
            continue
        if latest is None or mtime > latest:
            latest = mtime
    return latest


def _normalize_command_marker_text(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("/", "\\")
    while "\\\\" in normalized:
        normalized = normalized.replace("\\\\", "\\")
    return normalized


def _status_progress_text(status_payload: Mapping[str, Any]) -> str:
    return _shared_status_progress_text(status_payload)


def _explore_signature(status_payload: Mapping[str, Any]) -> tuple[str, str, str, str, str, str, str, str]:
    return (
        str(status_payload.get("status") or "").strip().lower(),
        str(status_payload.get("explore_phase") or "").strip().lower(),
        str(status_payload.get("explore_stage") or "").strip().lower(),
        str(status_payload.get("explore_span") or "").strip().lower(),
        str(status_payload.get("explore_span_state") or "").strip().lower(),
        str(status_payload.get("explore_span_message") or "").strip(),
        str(status_payload.get("explore_message") or "").strip(),
        _status_progress_text(status_payload),
    )


def _is_quasi_terminal_clarify_signature(status_payload: Mapping[str, Any]) -> bool:
    return _shared_is_quasi_terminal_clarify_signature(status_payload)


def _soft_stall_hint(
    status_payload: Mapping[str, Any],
    *,
    phase: str,
    signature_stable_seconds: float,
    soft_stall_seconds: int = LIVE_OBSERVABILITY_SOFT_STALL_SECONDS,
) -> str:
    if signature_stable_seconds < max(1, soft_stall_seconds):
        return ""
    normalized_phase = str(phase or "").strip().lower()
    stage = str(status_payload.get("explore_stage") or "").strip().lower()
    span = str(status_payload.get("explore_span") or "").strip().lower()
    message = str(status_payload.get("explore_message") or "").strip().lower()
    if normalized_phase == "analyze":
        return "analyze_status_static"
    if stage == "s07_finalize" and span:
        return f"{span}_no_close" if span.startswith("s07_") else f"s07_{span}_no_close"
    if stage == "s07_finalize" or "finalizing harmonized state" in message:
        return "s07_finalization_no_close"
    if stage:
        return f"{stage}_status_static"
    return f"{normalized_phase or 'job'}_status_static"


def build_live_checkpoint_observation(
    status_payload: Mapping[str, Any],
    *,
    job_id: str,
    phase: str,
    elapsed_seconds: float,
    status_age_seconds: float | None,
    status_stability_seconds: float,
    signature_stable_seconds: float,
    soft_stall_seconds: int = LIVE_OBSERVABILITY_SOFT_STALL_SECONDS,
) -> dict[str, Any]:
    progress = _status_progress_text(status_payload)
    span_updated_at = status_payload.get("explore_span_updated_at")
    span_stable_seconds = None
    if span_updated_at is not None:
        try:
            span_stable_seconds = max(0.0, time.time() - float(span_updated_at))
        except Exception:
            span_stable_seconds = None
    observation = {
        "job_id": str(status_payload.get("job_id") or job_id or "").strip(),
        "phase": str(phase or "").strip(),
        "status": str(status_payload.get("status") or "").strip(),
        "explore_phase": str(status_payload.get("explore_phase") or "").strip(),
        "stage": str(status_payload.get("explore_stage") or "").strip(),
        "span": str(status_payload.get("explore_span") or "").strip(),
        "span_state": str(status_payload.get("explore_span_state") or "").strip(),
        "span_message": str(status_payload.get("explore_span_message") or "").strip(),
        "message": str(status_payload.get("explore_message") or "").strip(),
        "progress": progress,
        "elapsed_seconds": round(max(0.0, elapsed_seconds), 2),
        "status_age_seconds": (
            round(max(0.0, status_age_seconds), 2)
            if status_age_seconds is not None
            else None
        ),
        "status_stability_seconds": round(max(0.0, status_stability_seconds), 2),
        "signature_stable_seconds": round(max(0.0, signature_stable_seconds), 2),
        "span_stable_seconds": (
            round(max(0.0, span_stable_seconds), 2)
            if span_stable_seconds is not None
            else None
        ),
        "soft_stall_hint": _soft_stall_hint(
            status_payload,
            phase=phase,
            signature_stable_seconds=signature_stable_seconds,
            soft_stall_seconds=soft_stall_seconds,
        ),
        "claim_ceiling": "live_observation_only",
    }
    return observation


def live_checkpoint_observation_line(observation: Mapping[str, Any]) -> str:
    stage = str(observation.get("stage") or "").strip() or "-"
    span = str(observation.get("span") or "").strip()
    message = str(observation.get("message") or "").strip()
    if len(message) > 120:
        message = message[:117] + "..."
    hint = str(observation.get("soft_stall_hint") or "").strip()
    hint_part = f" soft_stall_hint={hint}" if hint else ""
    span_part = f"span={span} " if span else ""
    span_stable = observation.get("span_stable_seconds")
    span_stable_part = f" span_stable={span_stable}s" if span_stable is not None else ""
    return (
        "checkpoint-observer "
        f"job={observation.get('job_id') or ''} "
        f"phase={observation.get('phase') or ''} "
        f"stage={stage} "
        f"{span_part}"
        f"progress={observation.get('progress') or ''} "
        f"elapsed={observation.get('elapsed_seconds')}s "
        f"signature_stable={observation.get('signature_stable_seconds')}s"
        f"{span_stable_part}"
        f"{hint_part} "
        f"message={message}"
    )


def _runner_terminalization_payload(
    kind: str,
    status_payload: Mapping[str, Any],
    *,
    stable_for_seconds: int | None = None,
) -> dict[str, Any]:
    payload = build_job_terminalization_payload(
        str(status_payload.get("job_id") or ""),
        status_payload,
        observed_stable_for_seconds=stable_for_seconds,
        observed_timeout=str(kind or "").strip() == "timeout",
    )
    payload["source"] = "runner_fallback"
    payload["kind"] = str(kind or payload.get("terminalization_kind") or "").strip()
    payload["classified"] = True
    if payload["kind"] and not payload.get("terminalization_kind"):
        payload["terminalization_kind"] = payload["kind"]
    return payload


def _terminalization_kind(payload: Mapping[str, Any] | None) -> str:
    return str((payload or {}).get("terminalization_kind") or (payload or {}).get("kind") or "").strip().lower()


def _is_terminalization_terminal(payload: Mapping[str, Any] | None) -> bool:
    return bool((payload or {}).get("terminal")) or _terminalization_kind(payload) in TERMINALIZATION_TERMINAL_KINDS


def _recover_terminal_status_snapshot(
    status_payload: Mapping[str, Any] | None,
    terminalization: Mapping[str, Any] | None,
    *,
    phase: str,
    job_id: str,
) -> dict[str, Any] | None:
    if str(phase or "").strip().lower() != "explore":
        return None
    if not _is_terminalization_terminal(terminalization):
        return None
    kind = _terminalization_kind(terminalization)
    if not kind:
        return None

    payload = dict(status_payload or {})
    reason = dict((terminalization or {}).get("reason") or {})
    message = str(reason.get("message") or "").strip()
    payload["job_id"] = str(payload.get("job_id") or job_id)

    if kind == "done":
        payload["status"] = "done"
        payload["explore_phase"] = "done"
        payload["explore_stage"] = str(payload.get("explore_stage") or "done")
        payload["explore_message"] = message or str(payload.get("explore_message") or "Complete")
    elif kind == "awaiting_clarification_authoritative":
        payload["status"] = str(payload.get("status") or "running")
        payload["explore_phase"] = "awaiting_clarification"
        payload["explore_stage"] = str(payload.get("explore_stage") or "done")
        payload["explore_message"] = message or str(payload.get("explore_message") or "Awaiting clarification")
        macro_verdict = dict(payload.get("macro_verdict") or {})
        macro_verdict["status"] = str(macro_verdict.get("status") or "awaiting_clarification")
        payload["macro_verdict"] = macro_verdict
    else:
        payload["status"] = "failed"
        payload["explore_phase"] = str(payload.get("explore_phase") or "failed")
        payload["explore_stage"] = str(payload.get("explore_stage") or "done")
        payload["explore_message"] = message or str(payload.get("explore_message") or kind.replace("_", " "))
    payload["_transport_recovered_terminalization_kind"] = kind
    return payload


def _recover_terminal_status_from_readthrough(
    client: "ApiClient",
    job_id: str,
    *,
    phase: str,
    status_payload: Mapping[str, Any] | None,
    observed_stable_for_seconds: int | None = None,
    observed_timeout: bool = False,
) -> dict[str, Any] | None:
    latest_status: Mapping[str, Any] | None = status_payload
    try:
        refreshed = client.get(f"/api/jobs/{job_id}", timeout=30)
        if isinstance(refreshed, Mapping):
            latest_status = dict(refreshed)
            if str(phase or "").strip().lower() == "analyze":
                if str(refreshed.get("status") or "").strip().lower() in TERMINAL_ANALYZE_STATUS:
                    return dict(refreshed)
            elif _is_terminal_explore_state(dict(refreshed)):
                return dict(refreshed)
    except requests.RequestException:
        pass

    recovered = _recover_terminal_status_snapshot(
        latest_status,
        resolve_job_terminalization(
            client,
            job_id,
            status_payload=latest_status,
            observed_stable_for_seconds=observed_stable_for_seconds,
            observed_timeout=observed_timeout,
        ),
        phase=phase,
        job_id=job_id,
    )
    if recovered is not None:
        recovered["_terminal_readthrough_recovered"] = True
    return recovered


def resolve_job_terminalization(
    client: "ApiClient",
    job_id: str,
    *,
    status_payload: Mapping[str, Any] | None = None,
    observed_stable_for_seconds: int | None = None,
    observed_timeout: bool = False,
) -> dict[str, Any]:
    query: list[str] = []
    if observed_stable_for_seconds is not None:
        query.append(f"observed_stable_for_seconds={int(observed_stable_for_seconds)}")
    if observed_timeout:
        query.append("observed_timeout=true")
    path = f"/api/jobs/{job_id}/terminalization"
    if query:
        path = f"{path}?{'&'.join(query)}"
    last_transport_error: requests.RequestException | None = None
    for _attempt in range(3):
        try:
            payload = client.get(path, timeout=30)
            if isinstance(payload, dict):
                payload = dict(payload)
                payload["source"] = "api_contract"
                payload["kind"] = str(payload.get("terminalization_kind") or payload.get("kind") or "").strip()
                return payload
        except requests.HTTPError as exc:
            response = getattr(exc, "response", None)
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code not in {404, 405}:
                raise
            break
        except requests.RequestException as exc:
            last_transport_error = exc
            time.sleep(1)
    fallback = _runner_terminalization_payload(
        "timeout" if observed_timeout else "",
        status_payload or {},
        stable_for_seconds=observed_stable_for_seconds,
    )
    if not fallback.get("kind"):
        fallback["kind"] = str(fallback.get("terminalization_kind") or "").strip()
    if last_transport_error is not None:
        reason = dict(fallback.get("reason") or {})
        reason.setdefault("message", str(last_transport_error))
        reason["transport_error"] = str(last_transport_error)
        fallback["reason"] = reason
    return fallback


def _wait_for_api_health(api_url: str, api_key: str, timeout_sec: int = 90) -> tuple[bool, str]:
    deadline = time.time() + timeout_sec
    last_message = "api_health_timeout"
    while time.time() < deadline:
        ok, message = verify_api_identity(api_url, api_key)
        if ok:
            return True, message
        last_message = message
        time.sleep(1)
    return False, last_message


def relaunch_local_api_lane(
    repo_root: Path,
    api_url: str,
    api_key: str,
    *,
    campaign_log: Path | None = None,
    no_reload: bool = False,
) -> dict[str, Any]:
    start_script = repo_root / "start.ps1"
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(start_script),
        "-ApiOnly",
        "-ForceRestartApi",
    ]
    if no_reload:
        command.append("-NoReload")
    log_line(f"api-freshness relaunching managed local lane via {start_script.name}", campaign_log)
    proc = subprocess.run(
        command,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "api_relaunch_failed:"
            + ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[:1200]
        )
    ok, message = _wait_for_api_health(api_url, api_key)
    if not ok:
        raise RuntimeError(f"api_relaunch_health_failed:{message}")
    port = _local_api_connection_details(api_url).get("port")
    owner = _read_local_api_process_info(int(port)) if port else None
    return {
        "restart_performed": True,
        "post_restart_identity": message,
        "post_restart_owner": owner,
    }


def ensure_local_api_freshness(
    repo_root: Path,
    api_url: str,
    api_key: str = "",
    *,
    campaign_log: Path | None = None,
    allow_relaunch: bool = True,
    force_restart_reason: str = "",
) -> dict[str, Any]:
    details = _local_api_connection_details(api_url)
    host = str(details.get("host") or "")
    port = details.get("port")
    is_local = bool(details.get("is_local"))
    source_root = repo_root / "api"
    source_latest_mtime = _latest_tree_mtime(source_root)
    result: dict[str, Any] = {
        "api_url": str(api_url or "").strip(),
        "host": host,
        "port": port,
        "is_local": is_local,
        "source_watch_root": str(source_root),
        "source_latest_mtime": source_latest_mtime,
        "source_latest_mtime_iso": _utc_iso_from_timestamp(source_latest_mtime),
        "age_threshold_seconds": LOCAL_API_MAX_AGE_SECONDS,
        "restart_required": False,
        "restart_performed": False,
        "restart_suppressed": False,
        "allow_relaunch": allow_relaunch,
        "force_restart_reason": str(force_restart_reason or "").strip(),
        "freshness_verdict": "fresh",
    }
    if not is_local:
        result["freshness_verdict"] = "restart_skipped_nonlocal"
        return result

    owner = _read_local_api_process_info(int(port)) if port else None
    result["api_process"] = owner
    if not owner:
        return result

    created_at = owner.get("created_at")
    command_line = str(owner.get("command_line") or "")
    managed_marker = f"api.routes.main:app --host 0.0.0.0 --port {port}"
    is_managed = _normalize_command_marker_text(managed_marker) in _normalize_command_marker_text(command_line)
    result["is_managed_owner"] = is_managed

    age_seconds = None
    if created_at is not None:
        age_seconds = max(0.0, time.time() - float(created_at))
    result["api_age_seconds"] = age_seconds

    expected_git_sha = _current_repo_git_sha(repo_root)
    identity_payload = fetch_api_identity(api_url, api_key)
    identity_git_sha = str((identity_payload or {}).get("git_sha") or "").strip()
    result["expected_git_sha"] = expected_git_sha
    result["identity_git_sha"] = identity_git_sha
    result["identity_git_sha_matched"] = (
        bool(expected_git_sha and identity_git_sha and expected_git_sha == identity_git_sha)
        if identity_git_sha
        else None
    )

    restart_reason = ""
    if str(force_restart_reason or "").strip():
        restart_reason = str(force_restart_reason or "").strip()
    elif age_seconds is not None and age_seconds > LOCAL_API_MAX_AGE_SECONDS:
        restart_reason = "restart_required_age"
    elif (
        created_at is not None
        and source_latest_mtime is not None
        and source_latest_mtime > float(created_at)
    ):
        restart_reason = "restart_required_code_newer"
    elif expected_git_sha and identity_git_sha and expected_git_sha != identity_git_sha:
        restart_reason = "restart_required_git_sha_mismatch"

    if not restart_reason:
        log_line(
            "api-freshness fresh"
            + (
                f" pid={owner.get('pid')} age_seconds={round(age_seconds, 1)}"
                if age_seconds is not None
                else ""
            ),
            campaign_log,
        )
        return result

    result["restart_required"] = True
    result["freshness_verdict"] = restart_reason
    if not is_managed:
        result["freshness_verdict"] = "restart_blocked_unmanaged_owner"
        log_line(
            f"api-freshness blocked unmanaged owner pid={owner.get('pid')} reason={restart_reason}",
            campaign_log,
        )
        return result

    if not allow_relaunch:
        result["restart_suppressed"] = True
        suppressed_reason = restart_reason.replace("restart_required_", "restart_suppressed_", 1)
        result["freshness_verdict"] = suppressed_reason
        log_line(
            f"api-freshness suppressed restart pid={owner.get('pid')} reason={restart_reason}",
            campaign_log,
        )
        return result

    restart = relaunch_local_api_lane(repo_root, api_url, api_key, campaign_log=campaign_log)
    result.update(restart)
    owner = restart.get("post_restart_owner") or owner
    result["api_process"] = owner
    if owner and owner.get("created_at") is not None:
        result["api_age_seconds"] = max(0.0, time.time() - float(owner["created_at"]))
    post_identity = fetch_api_identity(api_url, api_key)
    if post_identity:
        post_identity_git_sha = str(post_identity.get("git_sha") or "").strip()
        result["identity_git_sha"] = post_identity_git_sha
        result["identity_git_sha_matched"] = (
            bool(expected_git_sha and post_identity_git_sha and expected_git_sha == post_identity_git_sha)
            if post_identity_git_sha
            else None
        )
    log_line(
        f"api-freshness restarted verdict={restart_reason} pid={owner.get('pid') if owner else 'unknown'}",
        campaign_log,
    )
    return result


def _wait_for_bridge_contract(bridge_url: str, bridge_key: str, timeout_sec: int = 90) -> tuple[bool, str]:
    deadline = time.time() + timeout_sec
    last_message = "bridge_contract_timeout"
    while time.time() < deadline:
        ok, message = verify_bridge_identity(bridge_url, bridge_key)
        if ok:
            readiness = fetch_bridge_readiness(bridge_url, bridge_key)
            if readiness is not None:
                return True, message
            last_message = "bridge_readiness_unavailable"
        else:
            last_message = message
        time.sleep(1)
    return False, last_message


def relaunch_local_bridge_lane(
    repo_root: Path,
    bridge_url: str,
    bridge_key: str,
    *,
    campaign_log: Path | None = None,
) -> dict[str, Any]:
    start_script = repo_root / "start.ps1"
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(start_script),
        "-BridgeOnly",
        "-ForceRestartBridge",
    ]
    log_line(f"bridge-freshness relaunching managed local lane via {start_script.name}", campaign_log)
    proc = subprocess.run(
        command,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "bridge_relaunch_failed:"
            + ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[:1200]
        )
    ok, message = _wait_for_bridge_contract(bridge_url, bridge_key)
    if not ok:
        raise RuntimeError(f"bridge_relaunch_health_failed:{message}")
    port = _local_bridge_connection_details(bridge_url).get("port")
    owner = _read_local_bridge_process_info(int(port)) if port else None
    return {
        "restart_performed": True,
        "post_restart_identity": message,
        "post_restart_owner": owner,
    }


def ensure_local_bridge_freshness(
    repo_root: Path,
    bridge_url: str,
    bridge_key: str = "",
    *,
    campaign_log: Path | None = None,
    allow_relaunch: bool = True,
) -> dict[str, Any]:
    details = _local_bridge_connection_details(bridge_url)
    host = str(details.get("host") or "")
    port = details.get("port")
    is_local = bool(details.get("is_local"))
    source_roots = (
        repo_root / "scripts" / "bridge",
        repo_root / "api" / "infra",
    )
    source_latest_mtime = max(
        (mtime for mtime in (_latest_tree_mtime(root) for root in source_roots) if mtime is not None),
        default=None,
    )
    result: dict[str, Any] = {
        "bridge_url": str(bridge_url or "").strip(),
        "host": host,
        "port": port,
        "is_local": is_local,
        "source_watch_roots": [str(root) for root in source_roots],
        "source_latest_mtime": source_latest_mtime,
        "source_latest_mtime_iso": _utc_iso_from_timestamp(source_latest_mtime),
        "age_threshold_seconds": LOCAL_BRIDGE_MAX_AGE_SECONDS,
        "restart_required": False,
        "restart_performed": False,
        "restart_suppressed": False,
        "allow_relaunch": allow_relaunch,
        "freshness_verdict": "fresh",
    }
    if not is_local:
        result["freshness_verdict"] = "restart_skipped_nonlocal"
        return result

    owner = _read_local_bridge_process_info(int(port)) if port else None
    result["bridge_process"] = owner
    if not owner:
        return result

    created_at = owner.get("created_at")
    command_line = str(owner.get("command_line") or "")
    managed_marker = "scripts\\bridge\\gui_bridge.py"
    is_managed = _normalize_command_marker_text(managed_marker) in _normalize_command_marker_text(command_line)
    result["is_managed_owner"] = is_managed

    age_seconds = None
    if created_at is not None:
        age_seconds = max(0.0, time.time() - float(created_at))
    result["bridge_age_seconds"] = age_seconds

    identity_payload = fetch_bridge_identity(bridge_url, bridge_key)
    readiness_payload = fetch_bridge_readiness(bridge_url, bridge_key)
    contract_missing = identity_payload is None or readiness_payload is None
    expected_git_sha = _current_repo_git_sha(repo_root)
    identity_git_sha = str((identity_payload or {}).get("git_sha") or "").strip()
    result["expected_git_sha"] = expected_git_sha
    result["identity_git_sha"] = identity_git_sha
    result["identity_git_sha_matched"] = (
        bool(expected_git_sha and identity_git_sha and expected_git_sha == identity_git_sha)
        if identity_git_sha
        else None
    )

    restart_reason = ""
    if contract_missing:
        restart_reason = "restart_required_contract_missing"
    elif age_seconds is not None and age_seconds > LOCAL_BRIDGE_MAX_AGE_SECONDS:
        restart_reason = "restart_required_age"
    elif (
        created_at is not None
        and source_latest_mtime is not None
        and source_latest_mtime > float(created_at)
    ):
        restart_reason = "restart_required_code_newer"
    elif expected_git_sha and identity_git_sha and expected_git_sha != identity_git_sha:
        restart_reason = "restart_required_git_sha_mismatch"

    if not restart_reason:
        log_line(
            "bridge-freshness fresh"
            + (
                f" pid={owner.get('pid')} age_seconds={round(age_seconds, 1)}"
                if age_seconds is not None
                else ""
            ),
            campaign_log,
        )
        return result

    result["restart_required"] = True
    result["freshness_verdict"] = restart_reason
    if not is_managed:
        result["freshness_verdict"] = "restart_blocked_unmanaged_owner"
        log_line(
            f"bridge-freshness blocked unmanaged owner pid={owner.get('pid')} reason={restart_reason}",
            campaign_log,
        )
        return result

    if not allow_relaunch:
        result["restart_suppressed"] = True
        suppressed_reason = restart_reason.replace("restart_required_", "restart_suppressed_", 1)
        result["freshness_verdict"] = suppressed_reason
        log_line(
            f"bridge-freshness suppressed restart pid={owner.get('pid')} reason={restart_reason}",
            campaign_log,
        )
        return result

    restart = relaunch_local_bridge_lane(repo_root, bridge_url, bridge_key, campaign_log=campaign_log)
    result.update(restart)
    owner = restart.get("post_restart_owner") or owner
    result["bridge_process"] = owner
    if owner and owner.get("created_at") is not None:
        result["bridge_age_seconds"] = max(0.0, time.time() - float(owner["created_at"]))
    post_identity = fetch_bridge_identity(bridge_url, bridge_key)
    if post_identity:
        post_identity_git_sha = str(post_identity.get("git_sha") or "").strip()
        result["identity_git_sha"] = post_identity_git_sha
        result["identity_git_sha_matched"] = (
            bool(expected_git_sha and post_identity_git_sha and expected_git_sha == post_identity_git_sha)
            if post_identity_git_sha
            else None
        )
    log_line(
        f"bridge-freshness restarted verdict={restart_reason} pid={owner.get('pid') if owner else 'unknown'}",
        campaign_log,
    )
    return result


def now_local() -> datetime:
    return datetime.now().astimezone()


def utc_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(content)


def log_line(message: str, campaign_log: Path | None = None) -> None:
    line = f"[{now_local().isoformat()}] {message}"
    print(line, flush=True)
    if campaign_log:
        append_text(campaign_log, line + "\n")


def emit_harness_state(
    state_path: Path,
    lifecycle_path: Path,
    state: str,
    details: dict[str, Any] | None = None,
) -> None:
    payload = {
        "state": state,
        "updated_at": utc_iso(),
        "details": details or {},
    }
    write_json(state_path, payload)
    history = read_json(lifecycle_path, [])
    if not isinstance(history, list):
        history = []
    history.append(payload)
    write_json(lifecycle_path, history)


def update_lane_heartbeat(
    heartbeat_path: Path,
    lane_id: str,
    run_id: str,
    *,
    status: str,
    job_id: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    rows = read_json(heartbeat_path, {})
    if not isinstance(rows, dict):
        rows = {}
    rows[lane_id] = {
        "lane_id": lane_id,
        "run_id": run_id,
        "job_id": job_id,
        "status": status,
        "updated_at": utc_iso(),
        "details": details or {},
    }
    write_json(heartbeat_path, rows)


def record_live_checkpoint_observation(
    observation: Mapping[str, Any],
    *,
    heartbeat_path: Path,
    lane_id: str,
    run_id: str,
    status: str,
    job_id: str,
    campaign_log: Path | None = None,
) -> None:
    observation_dict = dict(observation or {})
    log_line(live_checkpoint_observation_line(observation_dict), campaign_log)
    update_lane_heartbeat(
        heartbeat_path,
        lane_id,
        run_id,
        status=status,
        job_id=job_id,
        details={
            "phase": observation_dict.get("explore_phase") or observation_dict.get("phase"),
            "stage": observation_dict.get("stage"),
            "message": observation_dict.get("message"),
            "progress": observation_dict.get("progress"),
            "last_observation": observation_dict,
        },
    )


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


_GENERIC_PARAM_NAME_RE = re.compile(r"^param_\d+$")


def _summarize_session_capture_semantics(session_dir: Path) -> dict[str, Any]:
    invocables_map = read_json(session_dir / "invocables_map.json", {})
    transition_audit = read_json(session_dir / "transition-contract-audit.json", {})
    backfill_report = read_json(
        session_dir / "evidence" / "stage-05a-schema-backfill" / "backfill-report.json",
        {},
    )
    rename_decisions = read_json(
        session_dir / "evidence" / "stage-02c-evidence-capture" / "param-rename-decisions.json",
        [],
    )

    generic_param_count = 0
    semantic_param_count = 0
    invocable_count = 0
    if isinstance(invocables_map, dict):
        for invocable in invocables_map.values():
            if not isinstance(invocable, dict):
                continue
            invocable_count += 1
            for param in list(invocable.get("parameters") or []):
                if not isinstance(param, dict):
                    continue
                name = str(param.get("name") or "").strip()
                if not name:
                    continue
                if _GENERIC_PARAM_NAME_RE.match(name):
                    generic_param_count += 1
                else:
                    semantic_param_count += 1

    semantic_name_status = "missing"
    if generic_param_count or semantic_param_count:
        if semantic_param_count and not generic_param_count:
            semantic_name_status = "semantic_only"
        elif semantic_param_count and generic_param_count:
            semantic_name_status = "mixed"
        else:
            semantic_name_status = "all_generic"

    transitions_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(transition_audit, dict):
        for row in list(transition_audit.get("transitions") or []):
            if isinstance(row, dict):
                transition_id = str(row.get("id") or "").strip()
                if transition_id:
                    transitions_by_id[transition_id] = row

    return {
        "schema_version": "1.0.0",
        "invocable_count": invocable_count,
        "generic_param_count": generic_param_count,
        "semantic_param_count": semantic_param_count,
        "semantic_name_status": semantic_name_status,
        "rename_decision_count": (
            len(rename_decisions)
            if isinstance(rename_decisions, list)
            else len(rename_decisions or {})
            if isinstance(rename_decisions, dict)
            else 0
        ),
        "schema_patch_applied": bool(backfill_report),
        "backfill_patches_applied": int((backfill_report or {}).get("patches_applied") or 0),
        "t08_status": str((transitions_by_id.get("T-08") or {}).get("status") or ""),
        "t10_status": str((transitions_by_id.get("T-10") or {}).get("status") or ""),
    }


def _session_capture_artifacts_present(session_dir: Path) -> bool:
    required = (
        "session-manifest.json",
        "run-validity.json",
        "verification-report.json",
        "kpi_run.json",
        "human/collect-session-result.json",
    )
    return all((session_dir / name).exists() for name in required)


def _reset_session_capture_dir(session_dir: Path) -> None:
    if not session_dir.exists():
        session_dir.mkdir(parents=True, exist_ok=True)
        return
    for child in session_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _session_capture_artifacts_fresh(session_dir: Path, *, started_at: float) -> bool:
    required = (
        "session-manifest.json",
        "run-validity.json",
        "verification-report.json",
        "kpi_run.json",
        "human/collect-session-result.json",
    )
    for name in required:
        path = session_dir / name
        if not path.exists():
            return False
        try:
            if path.stat().st_mtime < started_at:
                return False
        except OSError:
            return False
    return True


def _session_capture_has_ledger_completion(session_dir: Path) -> bool:
    payload = read_json(session_dir / "human" / "collect-session-result.json", {})
    ledger = payload.get("ledger") if isinstance(payload, dict) else {}
    if not isinstance(ledger, dict):
        return False
    if bool(ledger.get("appended")):
        return True
    reason = str(ledger.get("reason") or "").strip().lower()
    return reason == "duplicate_content_hash_noop"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _read_openapi_paths(base_url: str, headers: dict[str, str], timeout: int = 30) -> set[str]:
    base = str(base_url or "").rstrip("/")
    if not base:
        return set()
    candidate_paths = ("/openapi.json", "/docs/openapi.json")
    for suffix in candidate_paths:
        try:
            resp = requests.get(f"{base}{suffix}", headers=headers, timeout=timeout)
            if resp.status_code != 200:
                continue
            payload = resp.json()
            paths = payload.get("paths") if isinstance(payload, dict) else {}
            if isinstance(paths, dict):
                return {str(k) for k in paths.keys()}
        except Exception:
            continue
    return set()


def _fetch_json_payload(
    base_url: str,
    path: str,
    headers: dict[str, str],
    *,
    timeout: int = 20,
) -> dict[str, Any] | None:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return None
    try:
        response = requests.get(f"{base}{path}", headers=headers, timeout=timeout)
        if response.status_code != 200:
            return None
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _read_env_file_value(path: Path, name: str) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


def resolve_bridge_secret(explicit_bridge_key: str = "") -> str:
    explicit = str(explicit_bridge_key or "").strip()
    if explicit:
        return explicit
    env_value = str(os.getenv("GUI_BRIDGE_SECRET", "")).strip()
    if env_value:
        return env_value
    for env_path in BRIDGE_SECRET_ENV_FILES:
        value = _read_env_file_value(env_path, "GUI_BRIDGE_SECRET")
        if value:
            return value
    return ""


def _fetch_json_payload_with_diagnostic(
    base_url: str,
    path: str,
    headers: dict[str, str],
    *,
    timeout: int = 5,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    base = str(base_url or "").strip().rstrip("/")
    diagnostic: dict[str, Any] = {
        "url": f"{base}{path}" if base else path,
        "status_code": None,
        "error_class": "",
        "error_message": "",
    }
    if not base:
        diagnostic["error_class"] = "missing_url"
        diagnostic["error_message"] = "bridge URL is empty"
        return None, diagnostic
    try:
        response = requests.get(f"{base}{path}", headers=headers, timeout=timeout)
        diagnostic["status_code"] = int(response.status_code)
        if response.status_code != 200:
            diagnostic["error_message"] = response.text[:500]
            return None, diagnostic
        payload = response.json()
        return (payload if isinstance(payload, dict) else None), diagnostic
    except Exception as exc:
        diagnostic["error_class"] = exc.__class__.__name__
        diagnostic["error_message"] = str(exc)[:500]
        return None, diagnostic


def _is_local_url(base_url: str) -> bool:
    parsed = urlparse(str(base_url or "").strip())
    host = (parsed.hostname or "").lower()
    return host in LOCAL_API_HOSTS


def _looks_like_connection_refused(diagnostic: Mapping[str, Any]) -> bool:
    text = (
        str(diagnostic.get("error_class") or "")
        + " "
        + str(diagnostic.get("error_message") or "")
    ).lower()
    return any(
        token in text
        for token in (
            "connectionerror",
            "connection refused",
            "actively refused",
            "failed to establish",
            "max retries exceeded",
            "timed out",
            "connection aborted",
        )
    )


def build_bridge_identity_smoke_packet(
    bridge_url: str,
    bridge_key: str = "",
    *,
    required_capabilities: Sequence[str] | None = None,
) -> dict[str, Any]:
    base = str(bridge_url or "").strip().rstrip("/")
    resolved_key = resolve_bridge_secret(bridge_key)
    headers = {"X-Bridge-Key": resolved_key} if resolved_key else {}
    required = [str(item).strip() for item in list(required_capabilities or ("analyze", "execute")) if str(item).strip()]
    packet: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source": "bridge_identity_smoke",
        "bridge_url": base,
        "required_capabilities": required,
        "secret_configured": bool(resolved_key),
        "identity": {},
        "readiness": {},
        "admission": {},
        "diagnostics": {},
        "safe_to_run": False,
        "safe_to_compare": False,
        "reason_code": "unknown_bridge_identity_failure",
        "next_action": "restore or verify configured local bridge lane before product-route proof",
    }
    if not base:
        packet["reason_code"] = "bridge_wrong_port_or_url"
        packet["diagnostics"]["identity"] = {"error_class": "missing_url"}
        return packet

    identity, identity_diag = _fetch_json_payload_with_diagnostic(base, "/identity", headers, timeout=5)
    packet["diagnostics"]["identity"] = identity_diag
    identity_status = identity_diag.get("status_code")
    if identity is None:
        if identity_status == 401:
            packet["reason_code"] = "bridge_secret_mismatch" if resolved_key else "bridge_secret_missing"
        elif _is_local_url(base) and _looks_like_connection_refused(identity_diag):
            packet["reason_code"] = "bridge_process_not_running"
        else:
            packet["reason_code"] = "bridge_wrong_port_or_url"
        return packet

    packet["identity"] = identity
    if str(identity.get("component") or "").strip() == "api":
        packet["reason_code"] = "bridge_api_shaped_endpoint_detected"
        return packet
    if str(identity.get("component") or "").strip() != "bridge":
        packet["reason_code"] = "bridge_wrong_port_or_url"
        return packet
    if str(identity.get("role") or "").strip() != "execution_bridge":
        packet["reason_code"] = "bridge_wrong_port_or_url"
        return packet
    if str(identity.get("contract_version") or "").strip() != TRUST_CONTRACT_VERSION:
        packet["reason_code"] = "bridge_wrong_port_or_url"
        return packet

    capabilities = {
        str(item).strip()
        for item in list(identity.get("capabilities") or [])
        if str(item).strip()
    }
    missing = [item for item in required if item not in capabilities]
    if missing:
        packet["reason_code"] = "bridge_capabilities_incomplete"
        packet["missing_capabilities"] = missing
        return packet

    readiness, readiness_diag = _fetch_json_payload_with_diagnostic(base, "/readiness", headers, timeout=5)
    packet["diagnostics"]["readiness"] = readiness_diag
    if readiness is None:
        if readiness_diag.get("status_code") == 401:
            packet["reason_code"] = "bridge_secret_mismatch" if resolved_key else "bridge_secret_missing"
        else:
            packet["reason_code"] = "bridge_readiness_unavailable"
        return packet
    packet["readiness"] = readiness
    if not bool(readiness.get("ready")):
        packet["reason_code"] = "bridge_readiness_unavailable"
        packet["blocking_reasons"] = list(readiness.get("blocking_reasons") or [])
        return packet

    admission, admission_diag = _fetch_json_payload_with_diagnostic(
        base,
        local_lane_admission_path("bridge"),
        headers,
        timeout=5,
    )
    packet["diagnostics"]["admission"] = admission_diag
    if admission is None:
        if admission_diag.get("status_code") == 401:
            packet["reason_code"] = "bridge_secret_mismatch" if resolved_key else "bridge_secret_missing"
        else:
            packet["reason_code"] = "bridge_readiness_unavailable"
        return packet
    packet["admission"] = admission
    if str(admission.get("contract_version") or "").strip() != LOCAL_LANE_ADMISSION_VERSION:
        packet["reason_code"] = "bridge_readiness_unavailable"
        packet["blocking_reasons"] = ["bridge_local_lane_admission_version_mismatch"]
        return packet
    if str(admission.get("runtime_contract_id") or "").strip() != runtime_contract_id():
        packet["reason_code"] = "bridge_readiness_unavailable"
        packet["blocking_reasons"] = ["bridge_runtime_contract_id_mismatch"]
        return packet
    if not bool(admission.get("admitted")):
        packet["reason_code"] = "bridge_readiness_unavailable"
        packet["blocking_reasons"] = list(admission.get("blocking_reasons") or [])
        return packet

    packet["reason_code"] = "bridge_identity_green"
    packet["safe_to_run"] = True
    packet["safe_to_compare"] = True
    packet["next_action"] = "run bounded Medium01 product-route proof"
    return packet


def build_api_identity_smoke_packet(api_url: str, api_key: str = "") -> dict[str, Any]:
    base = str(api_url or "").strip().rstrip("/")
    headers = {"X-Pipeline-Key": api_key} if api_key else {}
    packet: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source": "api_identity_smoke",
        "api_url": base,
        "identity": {},
        "readiness": {},
        "admission": {},
        "diagnostics": {},
        "safe_to_run": False,
        "safe_to_compare": False,
        "reason_code": "unknown_api_identity_failure",
        "next_action": "restore or verify configured local API lane before product-route proof",
    }
    if not base:
        packet["reason_code"] = "api_wrong_port_or_url"
        packet["diagnostics"]["identity"] = {"error_class": "missing_url"}
        return packet

    identity, identity_diag = _fetch_json_payload_with_diagnostic(base, "/identity", headers, timeout=5)
    packet["diagnostics"]["identity"] = identity_diag
    if identity is None:
        if _is_local_url(base) and _looks_like_connection_refused(identity_diag):
            packet["reason_code"] = "api_process_not_running"
        else:
            paths = _read_openapi_paths(base, headers, timeout=5)
            packet["openapi_paths_sample"] = sorted(paths)[:20]
            if not paths:
                packet["reason_code"] = "api_openapi_unavailable"
            elif "/execute" in paths and not any(str(path).startswith("/api/jobs") for path in paths):
                packet["reason_code"] = "api_bridge_shaped_endpoint_detected"
            else:
                packet["reason_code"] = "api_wrong_port_or_url"
        return packet

    packet["identity"] = identity
    if str(identity.get("component") or "").strip() == "bridge":
        packet["reason_code"] = "api_bridge_shaped_endpoint_detected"
        return packet
    if str(identity.get("component") or "").strip() != "api":
        packet["reason_code"] = "api_wrong_port_or_url"
        return packet
    if str(identity.get("role") or "").strip() != "pipeline_control_plane":
        packet["reason_code"] = "api_wrong_port_or_url"
        return packet
    if str(identity.get("contract_version") or "").strip() != TRUST_CONTRACT_VERSION:
        packet["reason_code"] = "api_wrong_port_or_url"
        return packet
    if str(identity.get("status_schema_version") or "").strip() != STATUS_SCHEMA_VERSION:
        packet["reason_code"] = "api_wrong_port_or_url"
        return packet

    readiness, readiness_diag = _fetch_json_payload_with_diagnostic(base, "/readiness", headers, timeout=5)
    packet["diagnostics"]["readiness"] = readiness_diag
    if readiness is None:
        packet["reason_code"] = "api_readiness_unavailable"
        return packet
    packet["readiness"] = readiness

    admission, admission_diag = _fetch_json_payload_with_diagnostic(
        base,
        local_lane_admission_path("api"),
        headers,
        timeout=5,
    )
    packet["diagnostics"]["admission"] = admission_diag
    if admission is None:
        packet["reason_code"] = "api_readiness_unavailable"
        return packet
    packet["admission"] = admission
    if str(admission.get("contract_version") or "").strip() != LOCAL_LANE_ADMISSION_VERSION:
        packet["reason_code"] = "api_local_lane_admission_red"
        packet["blocking_reasons"] = ["api_local_lane_admission_version_mismatch"]
        return packet
    if str(admission.get("runtime_contract_id") or "").strip() != runtime_contract_id():
        packet["reason_code"] = "api_local_lane_admission_red"
        packet["blocking_reasons"] = ["api_runtime_contract_id_mismatch"]
        return packet
    if not bool(admission.get("admitted")):
        packet["reason_code"] = "api_local_lane_admission_red"
        packet["blocking_reasons"] = list(admission.get("blocking_reasons") or [])
        return packet

    packet["reason_code"] = "api_identity_green"
    packet["safe_to_run"] = True
    packet["safe_to_compare"] = True
    packet["next_action"] = "run bounded Easy01 product-route proof"
    return packet


def fetch_bridge_identity(bridge_url: str, bridge_key: str = "") -> dict[str, Any] | None:
    headers = {"X-Bridge-Key": bridge_key} if bridge_key else {}
    return _fetch_json_payload(bridge_url, "/identity", headers, timeout=20)


def fetch_bridge_readiness(bridge_url: str, bridge_key: str = "") -> dict[str, Any] | None:
    headers = {"X-Bridge-Key": bridge_key} if bridge_key else {}
    return _fetch_json_payload(bridge_url, "/readiness", headers, timeout=20)


def fetch_api_identity(api_url: str, api_key: str = "") -> dict[str, Any] | None:
    headers = {"X-Pipeline-Key": api_key} if api_key else {}
    return _fetch_json_payload(api_url, "/identity", headers, timeout=20)


def fetch_api_readiness(api_url: str, api_key: str = "") -> dict[str, Any] | None:
    headers = {"X-Pipeline-Key": api_key} if api_key else {}
    return _fetch_json_payload(api_url, "/readiness", headers, timeout=20)


def fetch_bridge_admission(bridge_url: str, bridge_key: str = "") -> dict[str, Any] | None:
    headers = {"X-Bridge-Key": bridge_key} if bridge_key else {}
    return _fetch_json_payload(bridge_url, local_lane_admission_path("bridge"), headers, timeout=20)


def fetch_api_admission(api_url: str, api_key: str = "") -> dict[str, Any] | None:
    headers = {"X-Pipeline-Key": api_key} if api_key else {}
    return _fetch_json_payload(api_url, local_lane_admission_path("api"), headers, timeout=20)


def ensure_strict_local_lane_preflight(
    *,
    api_url: str,
    api_key: str,
    bridge_url: str,
    bridge_key: str,
) -> dict[str, Any]:
    api_admission = fetch_api_admission(api_url, api_key) or {}
    bridge_admission = fetch_bridge_admission(bridge_url, bridge_key) or {}
    blocking_reasons: list[str] = []
    expected_runtime_contract_id = runtime_contract_id()
    for component, payload in (("api", api_admission), ("bridge", bridge_admission)):
        if not payload:
            blocking_reasons.append(f"{component}_local_lane_admission_unavailable")
            continue
        if str(payload.get("contract_version") or "").strip() != LOCAL_LANE_ADMISSION_VERSION:
            blocking_reasons.append(f"{component}_local_lane_admission_version_mismatch")
        if str(payload.get("runtime_contract_id") or "").strip() != expected_runtime_contract_id:
            blocking_reasons.append(f"{component}_runtime_contract_id_mismatch")
        if not bool(payload.get("admitted")):
            blocking_reasons.append(f"{component}_local_lane_admission_red")
            blocking_reasons.extend(
                f"{component}:{item}"
                for item in list(payload.get("blocking_reasons") or [])
                if str(item).strip()
            )
    if blocking_reasons:
        raise RuntimeError("strict_local_lane_preflight_failed:" + ";".join(blocking_reasons))
    return {
        "api": api_admission,
        "bridge": bridge_admission,
        "runtime_contract_id": expected_runtime_contract_id,
        "admitted": True,
    }


def collect_runner_identity(
    *,
    runner_name: str,
    runner_version: str,
    runner_file: Path,
    api_url: str,
    bridge_url: str,
    started_at: float,
) -> dict[str, Any]:
    return build_runner_identity(
        runner_name=runner_name,
        runner_version=runner_version,
        started_at=started_at,
        source_paths=(runner_file, REPO_ROOT / "scripts" / "ops" / "nightly_groundtruth.py"),
        config_payload={
            "api_url": str(api_url or "").strip(),
            "bridge_url": str(bridge_url or "").strip(),
        },
    )


def _synthetic_api_identity(api_url: str, verification_reason: str) -> dict[str, Any]:
    identity = build_api_identity(
        service_version="unknown",
        process_started_at=time.time(),
        source_paths=(REPO_ROOT / "api" / "routes" / "main.py",),
        config_payload={
            "api_url": str(api_url or "").strip(),
            "verification_reason": verification_reason,
            "identity_source": "runner_fallback",
        },
        status_schema_version=STATUS_SCHEMA_VERSION,
        pipeline_schema_version=PIPELINE_SCHEMA_VERSION,
    )
    identity["identity_source"] = "runner_fallback"
    return identity


def _synthetic_bridge_identity(bridge_url: str, verification_reason: str) -> dict[str, Any]:
    identity = build_bridge_identity(
        service_version="unknown",
        process_started_at=time.time(),
        source_paths=(REPO_ROOT / "scripts" / "bridge" / "gui_bridge.py",),
        config_payload={
            "bridge_url": str(bridge_url or "").strip(),
            "verification_reason": verification_reason,
            "identity_source": "runner_fallback",
        },
        capabilities=("execute", "flush_dll_cache"),
    )
    identity["identity_source"] = "runner_fallback"
    return identity


def collect_api_identity(api_url: str, api_key: str, verification_reason: str = "") -> dict[str, Any]:
    identity = fetch_api_identity(api_url, api_key)
    return identity if identity else _synthetic_api_identity(api_url, verification_reason)


def collect_bridge_identity(bridge_url: str, bridge_key: str, verification_reason: str = "") -> dict[str, Any]:
    identity = fetch_bridge_identity(bridge_url, bridge_key)
    return identity if identity else _synthetic_bridge_identity(bridge_url, verification_reason)


def build_lane_identity_packet(
    *,
    runner_identity: Mapping[str, Any],
    api_identity: Mapping[str, Any],
    bridge_identity: Mapping[str, Any],
) -> dict[str, Any]:
    compatibility = build_minimal_compatibility_contract(api_identity, bridge_identity)
    comparability = build_lane_comparability_contract(
        runner_identity=runner_identity,
        api_identity=api_identity,
        bridge_identity=bridge_identity,
    )
    return {
        "contract_version": TRUST_CONTRACT_VERSION,
        "runner_identity": dict(runner_identity),
        "api_identity": dict(api_identity),
        "bridge_identity": dict(bridge_identity),
        "minimal_compatibility_contract": compatibility,
        "lane_comparability_contract": comparability,
        "comparable": bool(comparability.get("comparable")),
        "comparability_blocking_reasons": list(comparability.get("blocking_reasons") or []),
    }


def build_lane_readiness_packet(
    *,
    runner_identity: Mapping[str, Any] | None = None,
    api_identity: Mapping[str, Any],
    bridge_identity: Mapping[str, Any],
    api_readiness: Mapping[str, Any] | None,
    bridge_readiness: Mapping[str, Any] | None,
    freshness: Mapping[str, Any],
    bridge_freshness: Mapping[str, Any] | None = None,
    post_restart_readiness_probe: Mapping[str, Any] | None = None,
    canary_verdict: str = "not_run",
) -> dict[str, Any]:
    api_ready_payload = dict(api_readiness or {})
    bridge_ready_payload = dict(bridge_readiness or {})
    compatibility = build_minimal_compatibility_contract(api_identity, bridge_identity)
    comparability = (
        build_lane_comparability_contract(
            runner_identity=runner_identity,
            api_identity=api_identity,
            bridge_identity=bridge_identity,
        )
        if runner_identity is not None
        else None
    )
    api_identity_ok = (
        str(api_identity.get("component") or "").strip() == "api"
        and str(api_identity.get("role") or "").strip() == "pipeline_control_plane"
    )
    bridge_identity_ok = (
        str(bridge_identity.get("component") or "").strip() == "bridge"
        and str(bridge_identity.get("role") or "").strip() == "execution_bridge"
    )
    freshness_verdict = str(freshness.get("freshness_verdict") or "fresh").strip()
    bridge_freshness_payload = dict(bridge_freshness or {})
    bridge_freshness_verdict = str(bridge_freshness_payload.get("freshness_verdict") or "fresh").strip()
    blocking_reasons: list[str] = []
    if not api_identity_ok:
        blocking_reasons.append("api_identity_invalid")
    if not bridge_identity_ok:
        blocking_reasons.append("bridge_identity_invalid")
    if not bool(compatibility.get("compatible")):
        blocking_reasons.extend([str(item) for item in list(compatibility.get("blocking_reasons") or [])])
    if comparability is not None and not bool(comparability.get("comparable")):
        for item in list(comparability.get("blocking_reasons") or []):
            reason = str(item or "").strip()
            if reason and reason not in blocking_reasons:
                blocking_reasons.append(reason)
    if not api_ready_payload:
        blocking_reasons.append("api_readiness_unavailable")
    if not bridge_ready_payload:
        blocking_reasons.append("bridge_readiness_unavailable")
    if api_ready_payload and not bool(api_ready_payload.get("ready")):
        blocking_reasons.append(str(api_ready_payload.get("blocking_reason") or "api_not_ready"))
    if bridge_ready_payload and not bool(bridge_ready_payload.get("ready")):
        blocking_reasons.append(str(bridge_ready_payload.get("blocking_reason") or "bridge_not_ready"))
    if freshness_verdict == "restart_blocked_unmanaged_owner":
        blocking_reasons.append("api_restart_blocked_unmanaged_owner")
    if bridge_freshness_verdict == "restart_blocked_unmanaged_owner":
        blocking_reasons.append("bridge_restart_blocked_unmanaged_owner")

    readiness_probe = (
        dict(post_restart_readiness_probe)
        if post_restart_readiness_probe is not None
        else {"performed": False, "ready": None, "verdict": "not_required"}
    )
    return {
        "contract_version": TRUST_CONTRACT_VERSION,
        "ready": not blocking_reasons,
        "checked_at": utc_iso(),
        "api_identity_ok": api_identity_ok,
        "bridge_identity_ok": bridge_identity_ok,
        "api_bridge_compatible": bool(compatibility.get("compatible")),
        "api_freshness_verdict": freshness_verdict,
        "api_restart_required": bool(freshness.get("restart_required")),
        "api_restart_performed": bool(freshness.get("restart_performed")),
        "bridge_freshness_verdict": bridge_freshness_verdict,
        "bridge_restart_required": bool(bridge_freshness_payload.get("restart_required")),
        "bridge_restart_performed": bool(bridge_freshness_payload.get("restart_performed")),
        "post_restart_readiness_probe": readiness_probe,
        "canary_verdict": str(canary_verdict or "not_run"),
        "blocking_reason": "" if not blocking_reasons else blocking_reasons[0],
        "blocking_reasons": blocking_reasons,
        "api_readiness": api_ready_payload,
        "bridge_readiness": bridge_ready_payload,
        "bridge_freshness": bridge_freshness_payload,
        "minimal_compatibility_contract": compatibility,
        "lane_comparability_contract": dict(comparability or {}),
        "lane_comparable": bool((comparability or {}).get("comparable")) if comparability is not None else None,
    }

def verify_bridge_identity(bridge_url: str, bridge_key: str = "") -> tuple[bool, str]:
    """Validate that bridge_url points to the GUI bridge and not the API server."""
    base = str(bridge_url or "").strip().rstrip("/")
    if not base:
        return False, "bridge_url_missing"
    smoke = build_bridge_identity_smoke_packet(base, bridge_key, required_capabilities=("execute",))
    reason = str(smoke.get("reason_code") or "").strip()
    if reason != "bridge_identity_green":
        return False, reason or "unknown_bridge_identity_failure"
    identity = dict(smoke.get("identity") or {})
    if str(identity.get("component") or "").strip() == "api":
        return False, "bridge_api_shaped_endpoint_detected"
    if str(identity.get("component") or "").strip() != "bridge":
        return False, "bridge_component_mismatch"
    if str(identity.get("role") or "").strip() != "execution_bridge":
        return False, "bridge_role_mismatch"
    if str(identity.get("contract_version") or "").strip() != TRUST_CONTRACT_VERSION:
        return False, "bridge_contract_version_mismatch"
    readiness = dict(smoke.get("readiness") or {})
    admission = dict(smoke.get("admission") or {})
    if str(admission.get("contract_version") or "").strip() != LOCAL_LANE_ADMISSION_VERSION:
        return False, "bridge_local_lane_admission_version_mismatch"
    if str(admission.get("runtime_contract_id") or "").strip() != runtime_contract_id():
        return False, "bridge_runtime_contract_id_mismatch"
    if not bool(admission.get("admitted")):
        reasons = ",".join(str(item) for item in list(admission.get("blocking_reasons") or []) if str(item).strip())
        return False, f"bridge_local_lane_admission_red:{reasons or 'unknown'}"
    return True, f"bridge_ok:admission={admission.get('contract_version')}"


def verify_api_identity(api_url: str, api_key: str = "") -> tuple[bool, str]:
    """Validate that api_url points to the pipeline API and not the bridge server."""
    base = str(api_url or "").strip().rstrip("/")
    if not base:
        return False, "api_url_missing"
    headers = {"X-Pipeline-Key": api_key} if api_key else {}
    identity = fetch_api_identity(base, api_key)
    if identity is not None:
        if str(identity.get("component") or "").strip() != "api":
            return False, "api_component_mismatch"
        if str(identity.get("role") or "").strip() != "pipeline_control_plane":
            return False, "api_role_mismatch"
        if str(identity.get("contract_version") or "").strip() != TRUST_CONTRACT_VERSION:
            return False, "api_contract_version_mismatch"
        if str(identity.get("status_schema_version") or "").strip() != STATUS_SCHEMA_VERSION:
            return False, "api_status_schema_version_mismatch"
        readiness = fetch_api_readiness(base, api_key)
        if readiness is None:
            return False, "api_readiness_unavailable"
        admission = fetch_api_admission(base, api_key)
        if admission is None:
            return False, "api_local_lane_admission_unavailable"
        if str(admission.get("contract_version") or "").strip() != LOCAL_LANE_ADMISSION_VERSION:
            return False, "api_local_lane_admission_version_mismatch"
        if str(admission.get("runtime_contract_id") or "").strip() != runtime_contract_id():
            return False, "api_runtime_contract_id_mismatch"
        if not bool(admission.get("admitted")):
            reasons = ",".join(str(item) for item in list(admission.get("blocking_reasons") or []) if str(item).strip())
            return False, f"api_local_lane_admission_red:{reasons or 'unknown'}"
        return True, f"api_ok:admission={admission.get('contract_version')}"

    paths = _read_openapi_paths(base, headers, timeout=20)
    if not paths:
        return False, "api_openapi_unavailable"
    has_jobs = any(p.startswith("/api/jobs") for p in paths)
    has_execute = "/execute" in paths
    if not has_jobs:
        return False, "api_missing_jobs_routes"
    if has_execute and len(paths) < 15:
        return False, "api_bridge_shaped_endpoint_detected"
    return True, f"api_ok:routes={len(paths)}"


def verify_api_identity_for_resolution(api_url: str, api_key: str = "") -> tuple[bool, str]:
    """Resolve API URL before bridge-dependent local admission is repaired."""
    base = str(api_url or "").strip().rstrip("/")
    if not base:
        return False, "api_url_missing"
    headers = {"X-Pipeline-Key": api_key} if api_key else {}
    identity = fetch_api_identity(base, api_key)
    if identity is not None:
        if str(identity.get("component") or "").strip() != "api":
            return False, "api_component_mismatch"
        if str(identity.get("role") or "").strip() != "pipeline_control_plane":
            return False, "api_role_mismatch"
        if str(identity.get("contract_version") or "").strip() != TRUST_CONTRACT_VERSION:
            return False, "api_contract_version_mismatch"
        if str(identity.get("status_schema_version") or "").strip() != STATUS_SCHEMA_VERSION:
            return False, "api_status_schema_version_mismatch"
        readiness = fetch_api_readiness(base, api_key)
        if readiness is None:
            return False, "api_readiness_unavailable"
        return True, "api_ok:identity_shape"

    paths = _read_openapi_paths(base, headers, timeout=20)
    if not paths:
        return False, "api_openapi_unavailable"
    has_jobs = any(p.startswith("/api/jobs") for p in paths)
    has_execute = "/execute" in paths
    if not has_jobs:
        return False, "api_missing_jobs_routes"
    if has_execute and len(paths) < 15:
        return False, "api_bridge_shaped_endpoint_detected"
    return True, f"api_ok:routes={len(paths)}"


def resolve_api_url(
    api_url: str = "",
    api_key: str = "",
    *,
    env: Mapping[str, str] | None = None,
    candidate_urls: Sequence[str] = DEFAULT_LOCAL_API_CANDIDATES,
    verify_identity: Callable[[str, str], tuple[bool, str]] | None = None,
) -> tuple[str, str, str]:
    verifier = verify_identity or verify_api_identity
    explicit_url = str(api_url or "").strip().rstrip("/")
    env_map = dict(os.environ) if env is None else dict(env)
    env_url = str(env_map.get("MCP_FACTORY_API_URL") or "").strip().rstrip("/")

    if explicit_url:
        ok, message = verifier(explicit_url, api_key)
        if not ok:
            raise RuntimeError(f"api_identity_failed:explicit:{explicit_url}:{message}")
        return explicit_url, message, "explicit"

    if env_url:
        ok, message = verifier(env_url, api_key)
        if not ok:
            raise RuntimeError(f"api_identity_failed:env:{env_url}:{message}")
        return env_url, message, "env"

    failures: list[str] = []
    for candidate_url in candidate_urls:
        candidate = str(candidate_url or "").strip().rstrip("/")
        if not candidate:
            continue
        ok, message = verifier(candidate, api_key)
        if ok:
            return candidate, message, "auto-detected"
        failures.append(f"{candidate}:{message}")

    failure_summary = "; ".join(failures) if failures else "no_candidate_urls"
    raise RuntimeError(f"api_identity_failed:auto-detect:{failure_summary}")


class ApiClient:
    def __init__(self, api_url: str, api_key: str):
        self.base = api_url.rstrip("/")
        self.session = requests.Session()
        self.headers = {"X-Pipeline-Key": api_key} if api_key else {}

    def get(self, path: str, timeout: int = 60) -> dict[str, Any]:
        r = self.session.get(f"{self.base}{path}", headers=self.headers, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def post_json(self, path: str, payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
        r = self.session.post(f"{self.base}{path}", headers=self.headers, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def analyze(
        self,
        dll_path: Path,
        hints: str,
        use_cases: str,
        tags: dict[str, Any],
        *,
        bridge_url_override: str = "",
    ) -> str:
        with dll_path.open("rb") as fh:
            files = {"file": (dll_path.name, fh, "application/octet-stream")}
            data = {"hints": hints, "use_cases": use_cases}
            for k, v in tags.items():
                if v is not None and str(v) != "":
                    data[k] = str(v)
            if str(bridge_url_override or "").strip():
                data["selected_bridge_url"] = str(bridge_url_override or "").strip()
            r = self.session.post(f"{self.base}/api/analyze", headers=self.headers, files=files, data=data, timeout=180)
        r.raise_for_status()
        return str(r.json()["job_id"])


_PROGRESS10_CONTROL_PHASES = {
    "progress_10_status_persist_start",
    "progress_10_status_persist_returned",
    "progress_10_authority_emit_start",
    "progress_10_authority_emit_returned",
    "progress_10_authority_return_marker_emit_start",
    "progress_10_authority_return_marker_emit_returned",
    "progress_30_persist_start_boundary",
    "progress_30_status_persist_start",
    "progress_30_status_persist_returned",
    "worker_pre_progress_30_exception",
    "worker_before_discovery",
}


def _progress10_control_breadcrumbs(payload: Any) -> list[dict[str, Any]]:
    events = payload
    if isinstance(payload, Mapping):
        events = payload.get("events") or payload.get("upload_investigation") or []
    if not isinstance(events, list):
        return []
    breadcrumbs: list[dict[str, Any]] = []
    for entry in events:
        if not isinstance(entry, Mapping):
            continue
        phase = str(entry.get("phase") or "").strip()
        if phase in _PROGRESS10_CONTROL_PHASES:
            breadcrumbs.append(dict(entry))
    return breadcrumbs


def _fetch_upload_investigation_artifact(client: ApiClient, job_id: str, run_dir: Path) -> dict[str, Any]:
    try:
        payload = client.get(f"/api/download/{job_id}/upload_investigation.json", timeout=30)
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
            "events": [],
        }
    events = payload if isinstance(payload, list) else payload.get("events") if isinstance(payload, Mapping) else []
    packet = {
        "available": True,
        "artifact": "upload_investigation.json",
        "events": events if isinstance(events, list) else [],
        "progress_10_control_breadcrumbs": _progress10_control_breadcrumbs(payload),
    }
    write_json(run_dir / "upload-investigation.json", packet)
    return packet


def wait_job(
    client: ApiClient,
    job_id: str,
    phase: str,
    timeout_sec: int,
    poll_sec: int,
    *,
    stuck_seconds: int = 900,
    heartbeat_cb: Any | None = None,
    observation_cb: Any | None = None,
    soft_stall_seconds: int = LIVE_OBSERVABILITY_SOFT_STALL_SECONDS,
) -> dict[str, Any]:
    start = time.time()
    last_updated = 0.0
    last_movement = start
    last_status_snapshot: dict[str, Any] | None = None
    last_explore_signature: tuple[str, str, str, str, str] | None = None
    last_explore_signature_change = start
    request_error_since: float | None = None
    while True:
        try:
            st = client.get(f"/api/jobs/{job_id}", timeout=60)
            if isinstance(st, dict):
                last_status_snapshot = dict(st)
            request_error_since = None
        except requests.RequestException as exc:
            if isinstance(exc, requests.HTTPError):
                raise
            now = time.time()
            if request_error_since is None:
                request_error_since = now
            recovered = _recover_terminal_status_snapshot(
                last_status_snapshot,
                resolve_job_terminalization(
                    client,
                    job_id,
                    status_payload=last_status_snapshot,
                ),
                phase=phase,
                job_id=job_id,
            )
            if recovered is not None:
                return recovered
            if now - request_error_since > REQUEST_ERROR_GRACE_SECONDS:
                raise TimeoutError(
                    f"{phase} request error for {job_id} (>{REQUEST_ERROR_GRACE_SECONDS}s): {exc}"
                ) from exc
            time.sleep(max(1, poll_sec))
            continue
        if heartbeat_cb:
            try:
                heartbeat_cb(st)
            except Exception:
                pass
        updated_at = _safe_float(st.get("updated_at"), 0.0)
        if updated_at > last_updated:
            last_updated = updated_at
            last_movement = time.time()
        if phase == "analyze":
            now = time.time()
            if observation_cb:
                try:
                    observation_cb(
                        build_live_checkpoint_observation(
                            st,
                            job_id=job_id,
                            phase=phase,
                            elapsed_seconds=now - start,
                            status_age_seconds=(now - updated_at) if updated_at else None,
                            status_stability_seconds=now - last_movement,
                            signature_stable_seconds=now - last_movement,
                            soft_stall_seconds=soft_stall_seconds,
                        )
                    )
                except Exception:
                    pass
            if str(st.get("status") or "").lower() in TERMINAL_ANALYZE_STATUS:
                return st
        else:
            signature = _explore_signature(st)
            if signature != last_explore_signature:
                last_explore_signature = signature
                last_explore_signature_change = time.time()
            now = time.time()
            if observation_cb:
                try:
                    observation_cb(
                        build_live_checkpoint_observation(
                            st,
                            job_id=job_id,
                            phase=phase,
                            elapsed_seconds=now - start,
                            status_age_seconds=(now - updated_at) if updated_at else None,
                            status_stability_seconds=now - last_movement,
                            signature_stable_seconds=now - last_explore_signature_change,
                            soft_stall_seconds=soft_stall_seconds,
                        )
                    )
                except Exception:
                    pass
            if _is_terminal_explore_state(st):
                return st
            if (
                _is_quasi_terminal_clarify_signature(st)
                and time.time() - last_explore_signature_change > max(60, stuck_seconds)
            ):
                raise QuasiTerminalClarifyStall(
                    job_id,
                    st,
                    stable_for_seconds=max(60, stuck_seconds),
                )
        stable_for_seconds = int(max(60, stuck_seconds))
        if time.time() - last_movement > stable_for_seconds:
            recovered = _recover_terminal_status_from_readthrough(
                client,
                job_id,
                phase=phase,
                status_payload=last_status_snapshot,
                observed_stable_for_seconds=stable_for_seconds,
            )
            if recovered is not None:
                return recovered
            raise TimeoutError(f"{phase} stuck for {job_id} (>{stuck_seconds}s without status movement)")
        if time.time() - start > timeout_sec:
            recovered = _recover_terminal_status_from_readthrough(
                client,
                job_id,
                phase=phase,
                status_payload=last_status_snapshot,
                observed_timeout=True,
            )
            if recovered is not None:
                return recovered
            raise TimeoutError(f"{phase} timeout for {job_id}")
        time.sleep(poll_sec)


def _is_terminal_explore_state(status_payload: dict[str, Any]) -> bool:
    explore_phase = str(status_payload.get("explore_phase") or "").strip().lower()
    if explore_phase not in TERMINAL_EXPLORE_PHASE:
        return False
    job_status = str(status_payload.get("status") or "").strip().lower()
    if explore_phase in {"done", "error", "failed", "cancelled", "canceled"}:
        return job_status in TERMINAL_ANALYZE_STATUS or job_status in {"failed", "cancelled", "canceled"}
    if job_status in TERMINAL_ANALYZE_STATUS or job_status == "awaiting_clarification":
        return True
    macro_verdict = status_payload.get("macro_verdict") or {}
    macro_status = str((macro_verdict or {}).get("status") or "").strip().lower()
    return macro_status in {"done", "awaiting_clarification"}


def _select_invocables(
    analyzed_payload: Mapping[str, Any],
    selected_invocable_names: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    invocables = list(((analyzed_payload.get("result") or {}).get("invocables") or []))
    if not invocables:
        raise RuntimeError("no_invocables_after_analyze")
    selected_names = {
        str(name).strip()
        for name in list(selected_invocable_names or [])
        if str(name).strip()
    }
    if not selected_names:
        return invocables
    filtered = [
        item
        for item in invocables
        if str((item or {}).get("name") or "").strip() in selected_names
    ]
    if not filtered:
        raise RuntimeError("no_selected_invocables_after_analyze")
    return filtered


def build_post_restart_readiness_probe(
    *,
    performed: bool = False,
    target_name: str = RESTART_READINESS_PROBE_TARGET,
    required_semantic_checkpoint: str = RESTART_READINESS_REQUIRED_CHECKPOINT,
) -> dict[str, Any]:
    return {
        "performed": bool(performed),
        "target_name": str(target_name or "").strip(),
        "required_semantic_checkpoint": str(required_semantic_checkpoint or "").strip(),
        "ready": None,
        "verdict": "not_required" if not performed else "pending",
        "authoritative_or_not": False,
        "job_id": "",
        "job_terminalization": None,
        "runner_terminalization": None,
    }


def run_post_restart_readiness_probe(
    client: ApiClient,
    repo_root: Path,
    output_dir: Path,
    api_url: str,
    api_key: str,
    dll_path: Path,
    *,
    heartbeat_path: Path,
    campaign_log: Path | None = None,
) -> dict[str, Any]:
    probe_dir = output_dir / "post-restart-readiness"
    probe_dir.mkdir(parents=True, exist_ok=True)
    readiness = build_post_restart_readiness_probe(performed=True)
    readiness["probe_dir"] = str(probe_dir)
    readiness["dll_path"] = str(dll_path)
    lane_id = "post-restart-readiness"
    try:
        update_lane_heartbeat(
            heartbeat_path,
            lane_id,
            "readiness-probe",
            status="launch",
            details={"target": RESTART_READINESS_PROBE_TARGET, "variant": "post_restart_readiness"},
        )
        log_line(
            f"post-restart-readiness-start target={RESTART_READINESS_PROBE_TARGET} dll={dll_path.name}",
            campaign_log,
        )
        job_id = client.analyze(
            dll_path,
            hints="Post-restart readiness probe for session_bootstrap",
            use_cases="Readiness gate before proving run",
            tags={
                "run_set_id": output_dir.name,
                "playbook_step": "post-restart-readiness",
                "analysis_profile": "strict_dll",
                "lane_id": lane_id,
            },
        )
        readiness["job_id"] = job_id
        update_lane_heartbeat(heartbeat_path, lane_id, "readiness-probe", status="analyze", job_id=job_id)
        analyzed = wait_job(
            client,
            job_id,
            phase="analyze",
            timeout_sec=RESTART_READINESS_ANALYZE_TIMEOUT_SEC,
            poll_sec=5,
            stuck_seconds=RESTART_READINESS_STUCK_SECONDS,
            heartbeat_cb=lambda st: update_lane_heartbeat(
                heartbeat_path,
                lane_id,
                "readiness-probe",
                status="analyze",
                job_id=job_id,
                details={"status": st.get("status"), "progress": st.get("progress")},
            ),
        )
        write_json(probe_dir / "job-status-analyze.json", analyzed)
        if str(analyzed.get("status") or "").lower() == "error":
            raise RuntimeError(f"readiness_analyze_error:{analyzed.get('error')}")
        invocables = _select_invocables(analyzed, [RESTART_READINESS_REQUIRED_CHECKPOINT])
        client.post_json(
            "/api/generate",
            {
                "job_id": job_id,
                "component_name": RESTART_READINESS_PROBE_TARGET,
                "selected": invocables,
            },
            timeout=120,
        )
        client.post_json(
            f"/api/jobs/{job_id}/explore",
            {
                "explore_settings": {
                    "mode": "normal",
                    "cap_profile": "deploy",
                    "max_rounds": RESTART_READINESS_MAX_ROUNDS,
                    "max_tool_calls": RESTART_READINESS_MAX_TOOL_CALLS,
                    "gap_resolution_enabled": False,
                    "skip_documented": True,
                    "deterministic_fallback_enabled": True,
                    "context_density": "minimal",
                    "analysis_profile": "strict_dll",
                    "parallel_runs": 1,
                    "variant_id": "post_restart_readiness",
                    "lane_id": lane_id,
                    "entry_surface": "upload",
                    "chain_step_target": RESTART_READINESS_PROBE_TARGET,
                    "required_semantic_checkpoint": RESTART_READINESS_REQUIRED_CHECKPOINT,
                    "selected_invocable_names": [RESTART_READINESS_REQUIRED_CHECKPOINT],
                }
            },
            timeout=120,
        )
        update_lane_heartbeat(heartbeat_path, lane_id, "readiness-probe", status="explore", job_id=job_id)
        finished = wait_job(
            client,
            job_id,
            phase="explore",
            timeout_sec=RESTART_READINESS_EXPLORE_TIMEOUT_SEC,
            poll_sec=5,
            stuck_seconds=RESTART_READINESS_STUCK_SECONDS,
            heartbeat_cb=lambda st: update_lane_heartbeat(
                heartbeat_path,
                lane_id,
                "readiness-probe",
                status="explore",
                job_id=job_id,
                details={
                    "phase": st.get("explore_phase"),
                    "stage": st.get("explore_stage", ""),
                    "message": st.get("explore_message"),
                    "progress": st.get("explore_progress", st.get("progress")),
                },
            ),
        )
        write_json(probe_dir / "job-status-final.json", finished)
        readiness["job_terminalization"] = resolve_job_terminalization(
            client,
            job_id,
            status_payload=finished,
        )
        write_json(probe_dir / "job-terminalization.json", readiness["job_terminalization"])
        terminal_kind = str((readiness["job_terminalization"] or {}).get("kind") or "").strip().lower()
        readiness["ready"] = terminal_kind in {"done", "awaiting_clarification_authoritative"}
        readiness["verdict"] = "ready" if readiness["ready"] else "nonterminal_or_untrusted_terminal"
        readiness["authoritative_or_not"] = bool(readiness["ready"])
        readiness["job_status_snapshot"] = {
            "status": finished.get("status"),
            "explore_phase": finished.get("explore_phase"),
            "explore_stage": finished.get("explore_stage"),
            "explore_message": finished.get("explore_message"),
            "progress": _status_progress_text(finished),
        }
    except QuasiTerminalClarifyStall as exc:
        write_json(probe_dir / "job-status-final.json", exc.status_payload)
        readiness["ready"] = False
        readiness["verdict"] = "quasi_terminal_clarify_stall"
        readiness["authoritative_or_not"] = False
        readiness["job_id"] = readiness.get("job_id") or exc.job_id
        readiness["job_terminalization"] = resolve_job_terminalization(
            client,
            readiness["job_id"],
            status_payload=exc.status_payload,
            observed_stable_for_seconds=exc.stable_for_seconds,
        )
        write_json(probe_dir / "job-terminalization.json", readiness["job_terminalization"])
        readiness["runner_terminalization"] = (
            dict(readiness["job_terminalization"])
            if str((readiness["job_terminalization"] or {}).get("source") or "").strip() == "runner_fallback"
            else None
        )
        readiness["job_status_snapshot"] = {
            "status": exc.status_payload.get("status"),
            "explore_phase": exc.status_payload.get("explore_phase"),
            "explore_stage": exc.status_payload.get("explore_stage"),
            "explore_message": exc.status_payload.get("explore_message"),
            "progress": _status_progress_text(exc.status_payload),
        }
    except Exception as exc:
        recovered_snapshot = None
        recovered_terminalization = None
        if readiness.get("job_id"):
            recovered_terminalization = resolve_job_terminalization(
                client,
                str(readiness["job_id"]),
                status_payload=readiness.get("job_status_snapshot"),
            )
            recovered_snapshot = _recover_terminal_status_snapshot(
                readiness.get("job_status_snapshot"),
                recovered_terminalization,
                phase="explore",
                job_id=str(readiness["job_id"]),
            )
        if recovered_snapshot is not None and recovered_terminalization is not None:
            readiness["job_terminalization"] = recovered_terminalization
            readiness["runner_terminalization"] = (
                dict(recovered_terminalization)
                if str((recovered_terminalization or {}).get("source") or "").strip() == "runner_fallback"
                else None
            )
            readiness["job_status_snapshot"] = {
                "status": recovered_snapshot.get("status"),
                "explore_phase": recovered_snapshot.get("explore_phase"),
                "explore_stage": recovered_snapshot.get("explore_stage"),
                "explore_message": recovered_snapshot.get("explore_message"),
                "progress": _status_progress_text(recovered_snapshot),
            }
            terminal_kind = _terminalization_kind(recovered_terminalization)
            readiness["ready"] = terminal_kind in {"done", "awaiting_clarification_authoritative"}
            readiness["verdict"] = "ready" if readiness["ready"] else "nonterminal_or_untrusted_terminal"
            readiness["authoritative_or_not"] = bool(readiness["ready"])
            if readiness["ready"]:
                write_json(probe_dir / "job-terminalization.json", recovered_terminalization)
                write_json(probe_dir / "job-status-final.json", recovered_snapshot)
                write_json(output_dir / "post-restart-readiness.json", readiness)
                log_line(
                    f"post-restart-readiness verdict={readiness.get('verdict')} ready={readiness.get('ready')}",
                    campaign_log,
                )
                return readiness
        readiness["ready"] = False
        readiness["verdict"] = "probe_failed"
        readiness["authoritative_or_not"] = False
        readiness["error"] = str(exc)
    write_json(output_dir / "post-restart-readiness.json", readiness)
    log_line(
        f"post-restart-readiness verdict={readiness.get('verdict')} ready={readiness.get('ready')}",
        campaign_log,
    )
    return readiness


def latest_status_map(findings: list[dict[str, Any]]) -> dict[str, str]:
    return canonical_status_map(findings)


def ensure_interwoven(repo_root: Path, timeout_min: int) -> tuple[bool, str]:
    script = repo_root / "tests" / "fixtures" / "contoso_interwoven" / "build-interwoven.ps1"
    if not script.exists():
        return False, f"missing build script: {script}"
    timeout_sec = timeout_min * 60
    for attempt in (1, 2):
        try:
            p = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            if p.returncode == 0:
                return True, "ok"
            if attempt == 2:
                return False, ((p.stdout or "") + "\n" + (p.stderr or "")).strip()[:1200]
        except subprocess.TimeoutExpired:
            if attempt == 2:
                return False, f"build timed out after {timeout_sec}s"
        time.sleep(1)
    return False, "unknown build failure"


def _apply_terminalized_failure_record(
    rec: dict[str, Any],
    *,
    run_dir: Path,
    start: float,
    finished: Mapping[str, Any],
    terminalization: Mapping[str, Any],
    lane_readiness: Mapping[str, Any] | None = None,
    last_observation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    terminal_kind = str((terminalization or {}).get("kind") or (terminalization or {}).get("terminalization_kind") or "").strip()
    run_authority = build_run_authority_payload(
        run_id=str(rec.get("run_id") or run_dir.name),
        job_id=str(rec.get("job_id") or finished.get("job_id") or ""),
        lane_readiness=lane_readiness,
        terminalization=terminalization,
        valid_run=False,
        session_capture_complete=False,
        verdict_status="",
        job_status=str(finished.get("status") or ""),
    )
    rec.update(
        {
            "status": "failed",
            "phase": finished.get("explore_phase") or finished.get("status"),
            "ended_at": utc_iso(),
            "duration_sec": round(time.time() - start, 2),
            "save_session_exit": None,
            "save_session_timed_out": False,
            "run_validity": {"valid": False, "reason": f"terminalized_{terminal_kind or 'failed'}"},
            "valid_run": False,
            "kpi_run": {},
            "latest_status_map": {},
            "metrics": {
                "success_rate": 0.0,
                "verified_count": 0,
                "discovered_count": 0,
                "total_count": 0,
                "verification_verified": 0,
                "verification_inferred": 0,
                "verification_error": 0,
                "runtime_total_sec": None,
                "runtime_stage_p95_sec": None,
                "cost_run_usd": None,
                "cost_per_verified_function_usd": None,
            },
            "verdict": finished.get("macro_verdict") or {},
            "job_status_snapshot": {
                "status": finished.get("status"),
                "explore_phase": finished.get("explore_phase"),
                "explore_stage": finished.get("explore_stage"),
                "explore_message": finished.get("explore_message"),
                "progress": _status_progress_text(finished),
            },
            "job_terminalization": dict(terminalization or {}),
            "runner_terminalization": (
                dict(terminalization or {})
                if str((terminalization or {}).get("source") or "").strip() == "runner_fallback"
                else None
            ),
            "run_authority": run_authority,
            "failure_domain": str(run_authority.get("failure_domain") or ""),
            "authoritative_proving": bool(run_authority.get("authoritative_proving")),
            "last_observation": dict(last_observation or {}),
        }
    )
    write_json(run_dir / "job-terminalization.json", terminalization)
    write_json(run_dir / "run-authority.json", run_authority)
    write_json(run_dir / "run_result.json", rec)
    return rec


def _classify_measurement_reason(
    *,
    phase: str,
    status_payload: Mapping[str, Any] | None = None,
    exc: BaseException | None = None,
    lane_readiness: Mapping[str, Any] | None = None,
) -> str:
    readiness = dict(lane_readiness or {})
    if readiness and _lane_or_infra_unavailable(readiness):
        return "lane_or_infra_unavailable"

    message = " ".join(
        [
            str(exc or ""),
            str((status_payload or {}).get("error") or ""),
            str((status_payload or {}).get("message") or ""),
        ]
    ).lower()
    if phase == "analyze" and isinstance(exc, TimeoutError):
        return "analyzer_timeout"
    if "discovery produced no output" in message or "no output files" in message:
        return "discovery_empty"
    if "output missing" in message or "missing output" in message:
        return "output_missing"
    if phase == "analyze" and (exc is not None or str((status_payload or {}).get("status") or "").lower() == "error"):
        return "analyzer_error"
    return "unknown_measurement_failure"


def _is_analyze_api_read_timeout(
    *,
    status_payload: Mapping[str, Any] | None = None,
    exc: BaseException | None = None,
) -> bool:
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return True
    message = " ".join(
        [
            type(exc).__name__ if exc else "",
            str(exc or ""),
            str((status_payload or {}).get("error") or ""),
            str((status_payload or {}).get("message") or ""),
        ]
    ).lower()
    return "read timed out" in message or "readtimeout" in message


def _lane_or_infra_unavailable(readiness: Mapping[str, Any] | None) -> bool:
    payload = dict(readiness or {})
    if not payload:
        return False
    blocking_reasons = [
        str(item or "").strip().lower()
        for item in list(payload.get("blocking_reasons") or [])
        if str(item or "").strip()
    ]
    if any(reason in LANE_OR_INFRA_UNAVAILABLE_REASONS for reason in blocking_reasons):
        return True
    if any(reason.startswith("api_readiness_") or reason.startswith("bridge_readiness_") for reason in blocking_reasons):
        return True
    return False


def _measurement_owner_for_reason(reason_code: str) -> str:
    if reason_code == "lane_or_infra_unavailable":
        return "lane_or_infra"
    if reason_code in {"discovery_empty", "analyzer_error", "analyzer_timeout", "output_missing"}:
        return "hard_family_analyze_discovery"
    return "hard_family_measurement"


def _measurement_next_action_for_reason(reason_code: str) -> str:
    if reason_code == "lane_or_infra_unavailable":
        return "repair lane readiness before interpreting hard-family target behavior"
    if reason_code == "analyzer_timeout":
        return "isolate analyzer stall or timeout behavior and preserve last status snapshot"
    if reason_code == "discovery_empty":
        return "isolate why analyze completed without durable discovery output"
    if reason_code == "output_missing":
        return "repair analyze output persistence before semantic comparison"
    if reason_code == "analyzer_error":
        return "classify analyzer failure and preserve durable diagnostic output"
    return "inspect hard-family measurement packet before semantic comparison"


def _inspect_pe_exports_for_discovery_authority(dll_path: Path) -> dict[str, Any]:
    exports: list[str] = []
    if not dll_path.exists():
        return {"available": False, "exports": exports, "error": "binary_missing"}
    try:
        import pefile  # type: ignore
    except Exception as exc:
        return {"available": False, "exports": exports, "error": f"pefile_unavailable: {exc}"}
    try:
        pe_obj = pefile.PE(str(dll_path), fast_load=True)
        try:
            pe_obj.parse_data_directories(
                directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]]
            )
        except Exception:
            pass
        for symbol in getattr(getattr(pe_obj, "DIRECTORY_ENTRY_EXPORT", None), "symbols", []) or []:
            raw_name = getattr(symbol, "name", None)
            if raw_name:
                exports.append(raw_name.decode("utf-8", errors="replace"))
            else:
                exports.append(f"#{getattr(symbol, 'ordinal', '')}")
    except Exception as exc:
        return {"available": False, "exports": exports, "error": str(exc)}
    return {"available": True, "exports": sorted({name for name in exports if name}), "error": ""}


def _runner_discovery_output_authority(
    *,
    rec: Mapping[str, Any],
    reason_code: str,
    status_payload: Mapping[str, Any],
    exc: BaseException | None = None,
) -> dict[str, Any]:
    dll_path = Path(str(rec.get("target_dll") or ""))
    settings = dict(rec.get("explore_settings") or {})
    measurement_control_plane = dict(rec.get("measurement_control_plane") or {})
    selected_bridge = measurement_control_plane.get("selected_bridge")
    selected_bridge_url = ""
    if isinstance(selected_bridge, Mapping):
        selected_bridge_url = str(selected_bridge.get("url") or "").strip()
    selected_bridge_url = selected_bridge_url or str(settings.get("selected_bridge_url") or "").strip()
    ghidra_required = bool(status_payload.get("ghidra_required") or settings.get("ghidra_required"))
    analyzer_progress = status_payload.get("progress")
    message = str(status_payload.get("message") or status_payload.get("error") or exc or "")
    bridge_attempted = bool(
        selected_bridge_url
        and (
            analyzer_progress == 60
            or "bridge" in message.lower()
            or "ghidra" in message.lower()
        )
    )
    export_inspection = _inspect_pe_exports_for_discovery_authority(dll_path)
    exports = list(export_inspection.get("exports") or [])
    owner = "analyzer_runtime" if reason_code == "analyzer_timeout" else _measurement_owner_for_reason(reason_code)
    next_action = (
        "isolate Ghidra/static analyzer stall before discovery-output comparison"
        if reason_code == "analyzer_timeout"
        else _measurement_next_action_for_reason(reason_code)
    )
    return {
        "schema_version": "1.0.0",
        "source": "runner_fallback",
        "target": str(rec.get("target") or ""),
        "dll_name": dll_path.name,
        "dll_path": str(dll_path),
        "phase": "analyze_discovery_output",
        "status": "non_comparable_discovery_failure",
        "reason_code": reason_code,
        "owner": owner,
        "safe_to_compare": False,
        "route_policy": "ghidra_first_required" if ghidra_required else "compiled_first_default",
        "ghidra_required": ghidra_required,
        "ghidra_entered": False,
        "bridge_configured": bool(selected_bridge_url),
        "bridge_attempted": bridge_attempted,
        "selected_bridge_url": selected_bridge_url,
        "legacy_pe_parser_entered": False,
        "exports_detected": exports,
        "export_count": len(exports),
        "export_inspection": export_inspection,
        "discovery_files_expected": ["*_mcp.json", "*.json"],
        "discovery_files_found": [],
        "discovery_file_count": 0,
        "invocable_count": 0,
        "analyzer_status": str(status_payload.get("status") or ""),
        "analyzer_progress": status_payload.get("progress"),
        "analyzer_error": str(status_payload.get("error") or status_payload.get("message") or exc or ""),
        "evidence_paths": ["discovery-output-authority.json"],
        "next_action": next_action,
        "created_at": utc_iso(),
    }


def _runner_bridge_analyzer_authority(
    *,
    rec: Mapping[str, Any],
    status_payload: Mapping[str, Any],
    last_observation: Mapping[str, Any] | None = None,
    exc: BaseException | None = None,
) -> dict[str, Any]:
    status = dict(status_payload or {})
    observation = dict(last_observation or {})
    embedded = status.get("bridge_analyzer_authority")
    if isinstance(embedded, Mapping):
        return dict(embedded)

    message = str(
        observation.get("message")
        or status.get("message")
        or status.get("error")
        or exc
        or ""
    )
    progress = observation.get("progress", status.get("progress"))
    bridge_message = "calling windows gui bridge" in message.lower()
    if bridge_message or progress == 60:
        reason_code = "bridge_stream_no_heartbeat"
        owner = "api_to_bridge_stream"
        next_action = "inspect whether bridge /analyze accepted the request and started streaming"
    else:
        reason_code = "unknown_bridge_analyzer_stall"
        owner = "bridge_analyzer"
        next_action = "capture richer bridge/analyzer diagnostics for this stall"
    settings = rec.get("settings") if isinstance(rec.get("settings"), Mapping) else {}

    return {
        "schema_version": "1.0.0",
        "source": "runner_fallback",
        "target": str(rec.get("target") or ""),
        "dll_name": Path(str(rec.get("target_dll") or "")).name,
        "dll_path": str(rec.get("target_dll") or ""),
        "phase": "bridge_analyzer",
        "status": "non_comparable_bridge_stall",
        "reason_code": reason_code,
        "owner": owner,
        "safe_to_compare": False,
        "bridge_url": "",
        "analysis_profile": str(settings.get("analysis_profile") or ""),
        "request_attempt_count": 0,
        "request_attempts": [],
        "heartbeat_count": 0,
        "stream_result_present": False,
        "exception_class": type(exc).__name__ if exc else "",
        "exception_message": str(exc or message),
        "timeout_type": type(exc).__name__ if exc and "Timeout" in type(exc).__name__ else "",
        "bridge_worker_phase": "",
        "elapsed_sec": None,
        "invocable_count": 0,
        "evidence_paths": ["bridge-analyzer-authority.json"],
        "next_action": next_action,
        "created_at": utc_iso(),
    }


def _runner_analyzer_runtime_authority(
    *,
    rec: Mapping[str, Any],
    status_payload: Mapping[str, Any],
    last_observation: Mapping[str, Any] | None = None,
    exc: BaseException | None = None,
) -> dict[str, Any]:
    status = dict(status_payload or {})
    observation = dict(last_observation or {})
    embedded = status.get("analyzer_runtime_authority")
    embedded_payload = dict(embedded) if isinstance(embedded, Mapping) else {}
    message = str(
        observation.get("message")
        or status.get("message")
        or status.get("error")
        or exc
        or ""
    )
    progress = observation.get("progress", status.get("progress"))
    try:
        progress_num = int(progress)
    except Exception:
        progress_num = None
    phase = str(embedded_payload.get("phase") or "").strip()
    post_progress_10_seen = bool(embedded_payload.get("post_progress_10_seen"))
    progress_30_persist_started = bool(embedded_payload.get("progress_30_persist_started"))
    progress_30_persisted = bool(embedded_payload.get("progress_30_persisted"))
    worker_pre_discovery_exception = bool(embedded_payload.get("worker_pre_discovery_exception"))
    worker_before_seen = bool(embedded_payload.get("worker_before_discovery_seen"))
    run_discovery_entered = bool(embedded_payload.get("run_discovery_entered"))
    child_launch_attempted = bool(embedded_payload.get("child_launch_attempted"))
    child_started = bool(embedded_payload.get("child_started"))
    child_completed = bool(embedded_payload.get("child_completed"))
    bridge_attempted = bool(embedded_payload.get("bridge_attempted"))
    output_file_count = int(embedded_payload.get("output_file_count") or 0)
    embedded_observation = (
        embedded_payload.get("last_observation") if isinstance(embedded_payload.get("last_observation"), Mapping) else {}
    )
    progress10_breadcrumbs: list[dict[str, Any]] = []
    for candidate in (
        observation.get("worker_progress_10_breadcrumbs"),
        status.get("worker_progress_10_breadcrumbs"),
        observation.get("progress_10_control_breadcrumbs"),
        status.get("progress_10_control_breadcrumbs"),
        observation.get("upload_investigation"),
        status.get("upload_investigation"),
    ):
        progress10_breadcrumbs.extend(_progress10_control_breadcrumbs(candidate))
    seen_progress10_phases = {str(item.get("phase") or "") for item in progress10_breadcrumbs}
    progress10_last_phase = ""
    if progress10_breadcrumbs:
        progress10_last_phase = str(progress10_breadcrumbs[-1].get("phase") or "")

    def _has_progress10_phase(name: str) -> bool:
        return name in seen_progress10_phases

    def _progress10_control_reason() -> str:
        if _has_progress10_phase("worker_pre_progress_30_exception"):
            return "worker_pre_progress_30_exception"
        if (
            _has_progress10_phase("worker_before_discovery")
            or _has_progress10_phase("progress_30_status_persist_returned")
            or _has_progress10_phase("progress_30_status_persist_start")
        ) and progress_num is not None and progress_num <= 10:
            return "status_persistence_stale"
        if _has_progress10_phase("progress_10_status_persist_start") and not _has_progress10_phase(
            "progress_10_status_persist_returned"
        ):
            return "progress_10_status_persist_stall"
        if _has_progress10_phase("progress_10_status_persist_returned") and not _has_progress10_phase(
            "progress_10_authority_emit_returned"
        ):
            return "progress_10_authority_emit_stall"
        if _has_progress10_phase("progress_10_authority_emit_returned") and not _has_progress10_phase(
            "progress_10_authority_return_marker_emit_returned"
        ):
            return "progress_10_authority_return_marker_missing"
        if _has_progress10_phase("progress_10_authority_return_marker_emit_returned") and not _has_progress10_phase(
            "progress_30_persist_start_boundary"
        ):
            return "progress_30_persist_start_missing"
        if progress10_breadcrumbs:
            return "unknown_post_progress_10_control_stall"
        return ""

    try:
        active_analysis_lock_wait_ms = float(embedded_observation.get("active_analysis_lock_wait_ms") or 0)
    except Exception:
        active_analysis_lock_wait_ms = 0.0
    embedded_phase_history = embedded_payload.get("phase_history")
    embedded_phase_names: set[str] = set()
    if isinstance(embedded_phase_history, list):
        for entry in embedded_phase_history:
            if isinstance(entry, Mapping):
                phase_name = str(entry.get("phase") or "").strip()
                if phase_name:
                    embedded_phase_names.add(phase_name)

    def _read_child_runtime_from_out_dir() -> dict[str, Any]:
        out_dir = str(embedded_observation.get("out_dir") or embedded_payload.get("out_dir") or "").strip()
        if not out_dir:
            return {}
        path = Path(out_dir) / "discovery-child-runtime.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception as read_exc:
            return {
                "schema_version": "1.0.0",
                "reason_code": "child_runtime_diagnostic_unreadable",
                "path": str(path),
                "error": str(read_exc),
            }

    if embedded_payload and progress_num is not None:
        stale_status_phases = {
            "worker_before_discovery",
            "run_discovery_entered",
            "discovery_child_launch_attempted",
            "discovery_child_started",
            "discovery_child_completed",
            "bridge_pending",
        }
        if progress_num <= 10 and phase in stale_status_phases:
            reason_code = "status_persistence_stale"
        elif progress_num <= 30 and bridge_attempted:
            reason_code = "status_persistence_stale"
        elif progress_num <= 30 and "discovery_output_scan_completed" in embedded_phase_names:
            reason_code = "status_packet_missing_parent_closeout"
        else:
            reason_code = ""
    else:
        reason_code = ""

    if not reason_code and _is_analyze_api_read_timeout(status_payload=status, exc=exc):
        reason_code = "analyze_api_read_timeout"

    child_runtime_diagnostic = {}
    if isinstance(observation.get("child_runtime_diagnostic"), Mapping):
        child_runtime_diagnostic = dict(observation.get("child_runtime_diagnostic") or {})
    elif isinstance(embedded_observation.get("child_runtime_diagnostic"), Mapping):
        child_runtime_diagnostic = dict(embedded_observation.get("child_runtime_diagnostic") or {})
    else:
        child_runtime_diagnostic = _read_child_runtime_from_out_dir()
    child_runtime_phase = str(child_runtime_diagnostic.get("phase") or "")
    child_runtime_history = child_runtime_diagnostic.get("phase_history")
    if not child_runtime_phase and isinstance(child_runtime_history, list) and child_runtime_history:
        last_runtime_entry = child_runtime_history[-1]
        if isinstance(last_runtime_entry, Mapping):
            child_runtime_phase = str(last_runtime_entry.get("phase") or "")

    def _has_embedded_phase(name: str) -> bool:
        return phase == name or name in embedded_phase_names

    def _child_runtime_no_output_reason() -> str:
        if not child_runtime_diagnostic:
            return "child_runtime_diagnostic_missing"
        if (
            child_runtime_phase == "bootstrap_main_returned"
            and _has_embedded_phase("discovery_child_wait_start")
            and not _has_embedded_phase("discovery_child_wait_returned")
        ):
            return "child_wrapper_wait_return_missing"
        if (
            _has_embedded_phase("discovery_child_wait_returned")
            and not _has_embedded_phase("discovery_child_returncode_observed")
        ):
            return "child_returncode_observation_missing"
        if (
            _has_embedded_phase("discovery_child_returncode_observed")
            and not _has_embedded_phase("discovery_output_scan_started")
        ):
            return "child_output_scan_missing"
        if _has_embedded_phase("discovery_output_scan_completed") and not output_file_count:
            return "child_completed_no_output"
        if child_runtime_phase == "bootstrap_import_start":
            return "child_bootstrap_import_hung"
        if child_runtime_phase == "bootstrap_import_success":
            return "child_main_entry_missing"
        if child_runtime_phase in {"bootstrap_main_calling", "main_args_parsed"}:
            return "child_main_running_no_output"
        if child_runtime_phase in {
            "main_classify_start",
            "main_classify_done",
            "main_pe_exports_start",
            "main_pe_exports_done",
            "main_import_analysis_start",
            "main_import_analysis_done",
        }:
            return "child_analysis_phase_hung"
        if child_runtime_phase == "main_output_write_start":
            return "child_output_write_hung"
        if child_runtime_phase == "bootstrap_main_returned":
            return "child_wrapper_process_wait_stall"
        return "unknown_child_runtime_no_output"

    if not reason_code:
        if not embedded_payload:
            progress10_reason = _progress10_control_reason()
            if progress10_reason:
                reason_code = progress10_reason
            elif progress_num == 10 or "discovery started" in message.lower():
                reason_code = "post_progress_10_control_stall"
            else:
                reason_code = "unknown_analyzer_runtime_stall"
        elif worker_pre_discovery_exception:
            reason_code = "worker_pre_discovery_exception"
        elif progress_30_persist_started and not progress_30_persisted:
            reason_code = "progress_30_persist_stall"
        elif active_analysis_lock_wait_ms >= 1000 and not worker_before_seen:
            reason_code = "active_analysis_lock_contention"
        elif not post_progress_10_seen and phase == "worker_progress_10_persisted":
            reason_code = "progress_10_authority_return_marker_missing"
        elif not worker_before_seen:
            if phase == "worker_progress_10_authority_returned":
                reason_code = "progress_30_persist_start_missing"
            elif progress_30_persisted:
                reason_code = "run_discovery_entry_missing"
            else:
                reason_code = "worker_startup_stall"
        elif not run_discovery_entered:
            reason_code = "run_discovery_entry_missing"
        elif not child_launch_attempted:
            reason_code = "discovery_child_launch_missing"
        elif not child_started:
            if phase == "discovery_child_popen_exception":
                reason_code = "discovery_child_popen_exception"
            elif phase == "discovery_child_popen_calling":
                reason_code = "discovery_child_popen_stall"
            else:
                reason_code = "discovery_child_launch_missing"
        elif child_started and not child_completed:
            reason_code = _child_runtime_no_output_reason()
        elif bridge_attempted and not output_file_count:
            reason_code = "ghidra_entry_missing"
        else:
            reason_code = "unknown_analyzer_runtime_stall"

    next_actions = {
        "worker_startup_stall": "inspect worker startup and progress-10 persistence before discovery entry",
        "post_progress_10_control_stall": "inspect control flow after progress-10 analyzer-runtime authority returns",
        "progress_10_status_persist_stall": "inspect synchronous progress-10 status persistence before analyzer-runtime authority emit",
        "progress_10_authority_emit_stall": "inspect analyzer-runtime authority emission immediately after progress-10 status persistence",
        "progress_10_authority_return_marker_missing": "inspect progress-10 authority return-marker writeback",
        "progress_30_persist_start_missing": "inspect control flow between progress-10 authority return and progress-30 persistence start",
        "unknown_post_progress_10_control_stall": "inspect out-of-band progress-10 breadcrumbs for an unmapped control-flow split",
        "progress_30_persist_stall": "inspect synchronous progress-30 status persistence before discovery entry",
        "worker_pre_discovery_exception": "inspect exception before worker-before-discovery and _run_discovery entry",
        "active_analysis_lock_contention": "inspect active-analysis lock contention and concurrent worker state",
        "run_discovery_entry_missing": "inspect worker-to-discovery handoff before child launch",
        "discovery_child_launch_missing": "inspect discovery child process launch path",
        "discovery_child_popen_stall": "inspect subprocess.Popen construction before child PID capture",
        "discovery_child_popen_exception": "inspect subprocess.Popen exception before child PID capture",
        "discovery_child_running_no_output": "inspect child process runtime, output, and timeout behavior",
        "child_bootstrap_import_hung": "inspect discovery child bootstrap import before main module loads",
        "child_main_entry_missing": "inspect bootstrap-to-main handoff in the discovery child",
        "child_main_running_no_output": "inspect discovery main entry and early argument/runtime setup",
        "child_analysis_phase_hung": "inspect discovery child analysis phase boundedness",
        "child_output_write_hung": "inspect discovery child output persistence/write path",
        "child_wrapper_wait_return_missing": "inspect parent-side process wait after child launch and before timeout closeout",
        "child_returncode_observation_missing": "inspect parent-side returncode observation after child wait returned",
        "child_output_scan_missing": "inspect parent-side discovery output enumeration after child completion",
        "child_completed_no_output": "inspect why the completed child produced no durable discovery outputs",
        "child_wrapper_process_wait_stall": "inspect Python launcher/wrapper process wait after discovery child returned",
        "child_runtime_diagnostic_missing": "inspect why launched discovery child wrote no runtime diagnostic packet",
        "unknown_child_runtime_no_output": "capture sharper child runtime phase diagnostics before rerun",
        "ghidra_entry_missing": "inspect bridge/Ghidra entry after discovery subprocess output",
        "status_packet_missing_parent_closeout": "inspect parent status/closeout writeback after child completion breadcrumbs exist",
        "status_persistence_stale": "inspect status persistence ordering versus runtime breadcrumbs",
        "timeout_policy_too_short": "inspect timeout budget against analyzer phase evidence",
        "analyze_api_read_timeout": "inspect API analyze launch/read timeout before analyzer runtime entry",
        "unknown_analyzer_runtime_stall": "capture richer analyzer-runtime breadcrumbs before rerun",
    }
    settings = rec.get("settings") if isinstance(rec.get("settings"), Mapping) else {}
    owner = "api_analyze_launch" if reason_code == "analyze_api_read_timeout" else "analyzer_runtime"
    status_name = (
        "non_comparable_analyze_launch_error"
        if reason_code == "analyze_api_read_timeout"
        else "non_comparable_analyzer_runtime_stall"
    )
    payload = {
        "schema_version": "1.0.0",
        "source": "status_payload" if embedded_payload else "runner_fallback",
        "target": str(rec.get("target") or ""),
        "dll_name": Path(str(rec.get("target_dll") or "")).name,
        "dll_path": str(rec.get("target_dll") or ""),
        "phase": "analyzer_runtime",
        "status": status_name,
        "reason_code": reason_code,
        "owner": owner,
        "safe_to_compare": False,
        "analysis_profile": str(settings.get("analysis_profile") or ""),
        "status_progress": progress,
        "status_message": message,
        "runtime_phase": phase,
        "progress_10_control_breadcrumbs": progress10_breadcrumbs,
        "progress_10_control_last_phase": progress10_last_phase,
        "post_progress_10_seen": post_progress_10_seen,
        "progress_30_persist_started": progress_30_persist_started,
        "progress_30_persisted": progress_30_persisted,
        "worker_pre_discovery_exception": worker_pre_discovery_exception,
        "active_analysis_lock_wait_ms": active_analysis_lock_wait_ms,
        "phase_history": list(embedded_payload.get("phase_history") or []),
        "parent_wrapper_phases_seen": sorted(
            phase_name
            for phase_name in embedded_phase_names
            if phase_name.startswith("discovery_child_wait_")
            or phase_name.startswith("discovery_child_returncode_")
            or phase_name.startswith("discovery_output_scan_")
        ),
        "worker_before_discovery_seen": worker_before_seen,
        "run_discovery_entered": run_discovery_entered,
        "child_launch_attempted": child_launch_attempted,
        "child_started": child_started,
        "child_pid": embedded_payload.get("child_pid"),
        "child_completed": child_completed,
        "child_returncode": embedded_payload.get("child_returncode"),
        "child_runtime_diagnostic_present": bool(child_runtime_diagnostic),
        "child_runtime_phase": child_runtime_phase,
        "child_runtime_diagnostic": child_runtime_diagnostic,
        "bridge_attempted": bridge_attempted,
        "ghidra_entered": bool(embedded_payload.get("ghidra_entered")),
        "ghidra_exited": bool(embedded_payload.get("ghidra_exited")),
        "output_file_count": output_file_count,
        "output_files_found": list(embedded_payload.get("output_files_found") or []),
        "embedded_authority_present": bool(embedded_payload),
        "last_observation": observation,
        "exception_class": type(exc).__name__ if exc else "",
        "exception_message": str(exc or ""),
        "evidence_paths": ["analyzer-runtime-authority.json"],
        "next_action": next_actions.get(reason_code, next_actions["unknown_analyzer_runtime_stall"]),
        "created_at": utc_iso(),
    }
    if embedded_payload:
        payload["embedded_authority"] = embedded_payload
    return payload


def _analyze_authority_diagnostic(
    *,
    rec: Mapping[str, Any],
    run_dir: Path,
    phase: str,
    reason_code: str,
    status_payload: Mapping[str, Any] | None = None,
    last_observation: Mapping[str, Any] | None = None,
    exc: BaseException | None = None,
) -> dict[str, Any]:
    status = dict(status_payload or {})
    observation = dict(last_observation or {})
    result = status.get("result") if isinstance(status.get("result"), Mapping) else {}
    invocables = list((result or {}).get("invocables") or [])
    normalized_reason = reason_code if reason_code in MEASUREMENT_TERMINALIZATION_REASON_CODES else "unknown_measurement_failure"
    discovery_output_authority = (
        dict(status.get("discovery_output_authority"))
        if isinstance(status.get("discovery_output_authority"), Mapping)
        else {}
    )
    if (
        not discovery_output_authority
        and phase == "analyze"
        and normalized_reason in {"discovery_empty", "analyzer_error", "analyzer_timeout", "output_missing"}
    ):
        discovery_output_authority = _runner_discovery_output_authority(
            rec=rec,
            reason_code=normalized_reason,
            status_payload=status,
            exc=exc,
        )
    bridge_analyzer_authority = {}
    if phase == "analyze" and normalized_reason == "analyzer_timeout":
        bridge_analyzer_authority = _runner_bridge_analyzer_authority(
            rec=rec,
            status_payload=status,
            last_observation=observation,
            exc=exc,
        )
    analyzer_runtime_authority = {}
    if phase == "analyze" and (
        normalized_reason == "analyzer_timeout"
        or _is_analyze_api_read_timeout(status_payload=status, exc=exc)
    ):
        analyzer_runtime_authority = _runner_analyzer_runtime_authority(
            rec=rec,
            status_payload=status,
            last_observation=observation,
            exc=exc,
        )
    checked = []
    found = []
    discovery_found = []
    for relative in ANALYZE_AUTHORITY_OUTPUT_PATHS:
        path = run_dir / relative
        status_embedded_authority = (
            (relative == "discovery-output-authority.json" and bool(discovery_output_authority))
            or (relative == "bridge-analyzer-authority.json" and bool(bridge_analyzer_authority))
            or (relative == "analyzer-runtime-authority.json" and bool(analyzer_runtime_authority))
        )
        entry = {
            "path": relative,
            "exists": path.exists() or status_embedded_authority,
            "size_bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
            "source": "status_payload" if status_embedded_authority and not path.exists() else "run_dir",
        }
        checked.append(entry)
        if entry["exists"]:
            found.append(relative)
            if relative not in {
                "job-status-analyze.json",
                "discovery-output-authority.json",
                "bridge-analyzer-authority.json",
                "analyzer-runtime-authority.json",
            }:
                discovery_found.append(relative)

    return {
        "schema_version": "1.0.0",
        "target": str(rec.get("target") or ""),
        "case_id": str(rec.get("variant_id") or rec.get("variant") or ""),
        "run_id": str(rec.get("run_id") or run_dir.name),
        "job_id": str(rec.get("job_id") or status.get("job_id") or ""),
        "phase": str(phase or ""),
        "reason_code": normalized_reason,
        "owner": _measurement_owner_for_reason(normalized_reason),
        "safe_to_compare": False,
        "analyzer_status": str(status.get("status") or ""),
        "analyzer_progress": status.get("progress"),
        "analyzer_error": str(status.get("error") or status.get("message") or exc or ""),
        "last_observation": observation,
        "timeout_or_stall": {
            "timed_out": normalized_reason == "analyzer_timeout",
            "last_observed_status": str(observation.get("status") or status.get("status") or ""),
            "last_observed_progress": observation.get("progress", status.get("progress")),
            "last_observed_stage": str(
                observation.get("explore_stage")
                or observation.get("stage")
                or status.get("explore_stage")
                or status.get("stage")
                or ""
            ),
        },
        "output_paths_checked": checked,
        "output_files_found": found,
        "discovery_output_present": bool(invocables or discovery_found),
        "invocable_count": len(invocables),
        "discovery_output_authority": discovery_output_authority,
        "bridge_analyzer_authority": bridge_analyzer_authority,
        "analyzer_runtime_authority": analyzer_runtime_authority,
        "analyzer_runtime_reason_code": str(analyzer_runtime_authority.get("reason_code") or ""),
        "analyzer_runtime_owner": str(analyzer_runtime_authority.get("owner") or ""),
        "bridge_reason_code": str(bridge_analyzer_authority.get("reason_code") or ""),
        "bridge_owner": str(bridge_analyzer_authority.get("owner") or ""),
        "producer_reason_code": str(discovery_output_authority.get("reason_code") or ""),
        "producer_owner": str(discovery_output_authority.get("owner") or ""),
        "classification_precision": "precise" if normalized_reason != "unknown_measurement_failure" else "unknown",
        "next_action": _measurement_next_action_for_reason(normalized_reason),
        "created_at": utc_iso(),
    }


def _measurement_terminalization_packet(
    *,
    rec: Mapping[str, Any],
    run_dir: Path,
    phase: str,
    reason_code: str,
    status_payload: Mapping[str, Any] | None = None,
    last_observation: Mapping[str, Any] | None = None,
    exc: BaseException | None = None,
) -> dict[str, Any]:
    normalized_reason = reason_code if reason_code in MEASUREMENT_TERMINALIZATION_REASON_CODES else "unknown_measurement_failure"
    evidence_paths = []
    for name in ("job-status-analyze.json", "job-status-final.json", "heartbeats.json"):
        path = run_dir / name
        if path.exists():
            evidence_paths.append(path.name)
    discovery_output_authority = (
        dict((status_payload or {}).get("discovery_output_authority"))
        if isinstance((status_payload or {}).get("discovery_output_authority"), Mapping)
        else {}
    )
    if discovery_output_authority:
        evidence_paths.append("discovery-output-authority.json")
    evidence_paths.append("analyzer-authority.json")
    evidence_paths.append("measurement-terminalization.json")
    analyzer_authority = _analyze_authority_diagnostic(
        rec=rec,
        run_dir=run_dir,
        phase=phase,
        reason_code=normalized_reason,
        status_payload=status_payload,
        last_observation=last_observation,
        exc=exc,
    )
    if analyzer_authority.get("discovery_output_authority") and "discovery-output-authority.json" not in evidence_paths:
        evidence_paths.append("discovery-output-authority.json")
    if analyzer_authority.get("bridge_analyzer_authority"):
        evidence_paths.append("bridge-analyzer-authority.json")
    if analyzer_authority.get("analyzer_runtime_authority"):
        evidence_paths.append("analyzer-runtime-authority.json")
    packet = {
        "schema_version": "1.0.0",
        "target": str(rec.get("target") or ""),
        "case_id": str(rec.get("variant_id") or rec.get("variant") or ""),
        "run_id": str(rec.get("run_id") or run_dir.name),
        "job_id": str(rec.get("job_id") or (status_payload or {}).get("job_id") or ""),
        "phase": str(phase or ""),
        "status": "non_comparable_failure",
        "reason_code": normalized_reason,
        "owner": _measurement_owner_for_reason(normalized_reason),
        "safe_to_compare": False,
        "evidence_paths": evidence_paths,
        "last_observation": dict(last_observation or {}),
        "status_payload": dict(status_payload or {}),
        "exception": str(exc or ""),
        "analyzer_authority": analyzer_authority,
        "next_action": _measurement_next_action_for_reason(normalized_reason),
        "created_at": utc_iso(),
    }
    return packet


def _apply_measurement_terminalized_record(
    rec: dict[str, Any],
    *,
    run_dir: Path,
    start: float,
    phase: str,
    reason_code: str,
    status_payload: Mapping[str, Any] | None = None,
    lane_readiness: Mapping[str, Any] | None = None,
    last_observation: Mapping[str, Any] | None = None,
    exc: BaseException | None = None,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    packet = _measurement_terminalization_packet(
        rec=rec,
        run_dir=run_dir,
        phase=phase,
        reason_code=reason_code,
        status_payload=status_payload,
        last_observation=last_observation,
        exc=exc,
    )
    terminal_kind = "timeout" if packet["reason_code"] == "analyzer_timeout" else "error"
    terminalization = {
        "contract_version": "trust_contract_v1",
        "source": "runner_measurement_terminalization",
        "kind": terminal_kind,
        "terminalization_kind": terminal_kind,
        "reason": {
            "code": packet["reason_code"],
            "message": packet["next_action"],
        },
        "evidence": {
            "phase": phase,
            "safe_to_compare": False,
            "measurement_terminalization": "measurement-terminalization.json",
        },
    }
    run_authority = build_run_authority_payload(
        run_id=str(rec.get("run_id") or run_dir.name),
        job_id=str(rec.get("job_id") or packet.get("job_id") or ""),
        lane_readiness=lane_readiness,
        terminalization=terminalization,
        valid_run=False,
        session_capture_complete=False,
        verdict_status="",
        job_status=str((status_payload or {}).get("status") or packet["status"]),
    )
    authority_completion = _authority_completion_reconciliation_packet(
        rec=rec,
        run_dir=run_dir,
        status_payload=status_payload,
        measurement_packet=packet,
        terminalization=terminalization,
        run_authority=run_authority,
        valid_run=False,
        session_capture_complete=False,
        verdict_status="",
    )
    packet["authority_completion_reconciliation"] = authority_completion
    packet.setdefault("evidence_paths", [])
    if "authority-completion-reconciliation.json" not in packet["evidence_paths"]:
        packet["evidence_paths"].append("authority-completion-reconciliation.json")
    rec.update(
        {
            "status": "failed",
            "phase": phase,
            "ended_at": utc_iso(),
            "duration_sec": round(time.time() - start, 2),
            "save_session_exit": None,
            "save_session_timed_out": False,
            "run_validity": {
                "valid": False,
                "reason": f"measurement_terminalized_{packet['reason_code']}",
            },
            "valid_run": False,
            "kpi_run": {},
            "latest_status_map": {},
            "metrics": {
                "success_rate": 0.0,
                "verified_count": 0,
                "discovered_count": 0,
                "total_count": 0,
                "verification_verified": 0,
                "verification_inferred": 0,
                "verification_error": 0,
                "runtime_total_sec": None,
                "runtime_stage_p95_sec": None,
                "cost_run_usd": None,
                "cost_per_verified_function_usd": None,
            },
            "verdict": {},
            "job_status_snapshot": dict(status_payload or {}),
            "job_terminalization": terminalization,
            "runner_terminalization": terminalization,
            "measurement_terminalization": packet,
            "analyzer_authority": packet["analyzer_authority"],
            "authority_completion_reconciliation": authority_completion,
            "run_authority": run_authority,
            "failure_domain": str(run_authority.get("failure_domain") or ""),
            "authoritative_proving": False,
            "last_observation": dict(last_observation or {}),
        }
    )
    write_json(run_dir / "analyzer-authority.json", packet["analyzer_authority"])
    if packet["analyzer_authority"].get("discovery_output_authority"):
        write_json(
            run_dir / "discovery-output-authority.json",
            packet["analyzer_authority"]["discovery_output_authority"],
        )
    if packet["analyzer_authority"].get("bridge_analyzer_authority"):
        write_json(
            run_dir / "bridge-analyzer-authority.json",
            packet["analyzer_authority"]["bridge_analyzer_authority"],
        )
    if packet["analyzer_authority"].get("analyzer_runtime_authority"):
        write_json(
            run_dir / "analyzer-runtime-authority.json",
            packet["analyzer_authority"]["analyzer_runtime_authority"],
        )
    write_json(run_dir / "measurement-terminalization.json", packet)
    write_json(run_dir / "authority-completion-reconciliation.json", authority_completion)
    write_json(run_dir / "job-terminalization.json", terminalization)
    write_json(run_dir / "run-authority.json", run_authority)
    write_json(run_dir / "run_result.json", rec)
    return rec


def _authority_completion_reconciliation_packet(
    *,
    rec: Mapping[str, Any],
    run_dir: Path,
    status_payload: Mapping[str, Any] | None,
    measurement_packet: Mapping[str, Any],
    terminalization: Mapping[str, Any],
    run_authority: Mapping[str, Any],
    valid_run: bool,
    session_capture_complete: bool,
    verdict_status: str,
) -> dict[str, Any]:
    public_status = str((status_payload or {}).get("status") or "").strip().lower()
    try:
        public_progress = int((status_payload or {}).get("progress") or 0)
    except (TypeError, ValueError):
        public_progress = 0
    authority_level = str((run_authority or {}).get("authority_level") or "").strip()
    terminal_kind = str((run_authority or {}).get("terminalization_kind") or "").strip()
    blocking_reasons = [
        str(item)
        for item in list((run_authority or {}).get("blocking_reasons") or [])
        if str(item)
    ]
    public_done = public_status == "done" or public_progress >= 100
    non_authoritative = authority_level == "non_authoritative"
    completion_reconciled = (
        public_done
        and authority_level == "decision_bearing"
        and bool((run_authority or {}).get("authoritative_proving"))
        and bool(valid_run)
        and bool(session_capture_complete)
        and terminal_kind == "done"
        and bool(verdict_status)
    )
    contradiction = bool(public_done and non_authoritative)
    if completion_reconciled:
        classification = "authority_completion_reconciled"
        status = "reconciled"
        next_action = "use a bounded reopen gate before spending broader proof"
        decision_bearing_blocker = ""
    elif contradiction:
        classification = "false_done_status_without_authority_completion"
        status = "contradiction"
        next_action = "reconcile public done status with terminal verdict, run validity, and session capture authority"
        decision_bearing_blocker = (
            f"{rec.get('target') or measurement_packet.get('target') or 'target'}_{classification}"
        )
    else:
        classification = "authority_completion_fail_closed"
        status = "fail_closed"
        next_action = "preserve non-authoritative terminal authority before rerun"
        decision_bearing_blocker = classification
    return {
        "schema_version": "1.0.0",
        "source": (
            "runner_terminal_authority_completion"
            if completion_reconciled
            else "runner_measurement_terminalization"
        ),
        "run_id": str(rec.get("run_id") or run_dir.name),
        "job_id": str(rec.get("job_id") or (status_payload or {}).get("job_id") or measurement_packet.get("job_id") or ""),
        "target": str(rec.get("target") or measurement_packet.get("target") or ""),
        "claim_ceiling": "terminal_authority_reconciliation_only",
        "product_green_claimed": False,
        "safe_to_compare": False,
        "public_status": {
            "status": public_status,
            "progress": public_progress,
            "message": str((status_payload or {}).get("message") or ""),
        },
        "terminalization": {
            "kind": terminal_kind,
            "source": str((terminalization or {}).get("source") or ""),
            "reason_code": str(((terminalization or {}).get("reason") or {}).get("code") or ""),
        },
        "run_authority": {
            "authority_level": authority_level,
            "authoritative_proving": bool((run_authority or {}).get("authoritative_proving")),
            "safe_to_steer_next_prompt": bool((run_authority or {}).get("safe_to_steer_next_prompt")),
            "blocking_reasons": blocking_reasons,
        },
        "completion_requirements": {
            "valid_run": bool(valid_run),
            "session_capture_complete": bool(session_capture_complete),
            "verdict_status": str(verdict_status or ""),
        },
        "status": status,
        "classification": classification,
        "decision_bearing_blocker": decision_bearing_blocker,
        "next_action": next_action,
        "created_at": utc_iso(),
    }


def _analyze_timeout_recovery_authority_packet(
    *,
    job_id: str,
    target_name: str,
    status_payload: Mapping[str, Any],
    selected_invocables: list[Mapping[str, Any]],
    last_observation: Mapping[str, Any] | None,
    exc: BaseException,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "claim": "analyze_timeout_recovered_from_terminal_done_status",
        "claim_ceiling": "analyze_phase_recovery_only",
        "target": str(target_name),
        "job_id": str(job_id),
        "product_green_claimed": False,
        "safe_to_compare": False,
        "status": "recovered",
        "public_status": {
            "status": str((status_payload or {}).get("status") or ""),
            "progress": (status_payload or {}).get("progress"),
            "message": str((status_payload or {}).get("message") or ""),
        },
        "selected_invocable_count": len(selected_invocables),
        "selected_invocable_names": [
            str(item.get("name") or "")
            for item in selected_invocables
            if isinstance(item, Mapping)
        ],
        "exception": str(exc),
        "last_observation": dict(last_observation or {}),
        "next_action": "continue into generate/explore because analyze produced terminal invocable output despite the wait timeout",
        "created_at": utc_iso(),
    }


def _is_connection_reset_error(exc: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = (str(current) + " " + repr(current)).lower()
        if (
            "winerror 10054" in message
            or "connectionreseterror" in message
            or "forcibly closed" in message
            or "connection reset" in message
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def _post_explore_artifact_fetch_reason(*, artifact: str, exc: BaseException) -> str:
    normalized = str(artifact or "").strip().lower()
    if normalized == "verdict" and _is_connection_reset_error(exc):
        return "post_explore_verdict_fetch_connection_reset"
    if normalized == "verdict":
        return "post_explore_verdict_fetch_failed"
    if normalized == "findings":
        return "post_explore_findings_fetch_failed"
    return "unknown_post_explore_artifact_fetch_failure"


def _post_explore_artifact_next_action(reason_code: str) -> str:
    if reason_code == "post_explore_verdict_fetch_connection_reset":
        return "repair API lane health or verdict artifact retrieval before rerunning hard-family semantic interpretation"
    if reason_code == "post_explore_verdict_fetch_failed":
        return "repair verdict artifact retrieval before treating terminal explore output as comparable"
    if reason_code == "post_explore_findings_fetch_failed":
        return "repair findings artifact retrieval before scoring or checkpoint alignment"
    return "repair post-explore artifact retrieval before semantic interpretation"


def _fetch_post_explore_artifact_with_retry(
    client: ApiClient,
    endpoint: str,
    *,
    artifact: str,
    run_dir: Path,
    timeout: int = 60,
    max_attempts: int = POST_EXPLORE_ARTIFACT_FETCH_MAX_ATTEMPTS,
    retry_delay_seconds: float = POST_EXPLORE_ARTIFACT_FETCH_RETRY_DELAY_SECONDS,
    campaign_log: Path | None = None,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    last_exc: BaseException | None = None
    max_attempts = max(1, int(max_attempts or 1))
    for attempt in range(1, max_attempts + 1):
        try:
            payload = client.get(endpoint, timeout=timeout)
            if attempts:
                attempts.append(
                    {
                        "attempt": attempt,
                        "artifact": artifact,
                        "endpoint": endpoint,
                        "verdict": "pass",
                    }
                )
                write_json(run_dir / "post-explore-artifact-fetch-retries.json", attempts)
            return dict(payload or {})
        except Exception as exc:
            last_exc = exc
            retryable = _is_connection_reset_error(exc) and attempt < max_attempts
            attempts.append(
                {
                    "attempt": attempt,
                    "artifact": artifact,
                    "endpoint": endpoint,
                    "verdict": "retry" if retryable else "fail",
                    "reason_code": _post_explore_artifact_fetch_reason(artifact=artifact, exc=exc),
                    "exception_class": exc.__class__.__name__,
                    "exception": str(exc),
                }
            )
            write_json(run_dir / "post-explore-artifact-fetch-retries.json", attempts)
            if not retryable:
                raise
            log_line(
                (
                    f"post-explore-fetch-retry artifact={artifact} attempt={attempt}/{max_attempts} "
                    f"reason={attempts[-1]['reason_code']}"
                ),
                campaign_log,
            )
            time.sleep(max(0.0, float(retry_delay_seconds or 0.0)))
    if last_exc is not None:
        raise last_exc
    return {}


def _post_explore_artifact_fetch_packet(
    rec: Mapping[str, Any],
    *,
    run_dir: Path,
    job_id: str,
    finished: Mapping[str, Any],
    terminalization: Mapping[str, Any],
    artifact: str,
    endpoint: str,
    exc: BaseException,
) -> dict[str, Any]:
    reason_code = _post_explore_artifact_fetch_reason(artifact=artifact, exc=exc)
    fallback_macro_verdict = dict((finished or {}).get("macro_verdict") or {})
    return {
        "schema_version": "1.0.0",
        "target": str(rec.get("target") or ""),
        "case_id": str(rec.get("variant_id") or rec.get("variant") or ""),
        "run_id": str(rec.get("run_id") or run_dir.name),
        "job_id": str(job_id or (finished or {}).get("job_id") or ""),
        "phase": "post_explore_artifact_fetch",
        "artifact": str(artifact or ""),
        "endpoint": str(endpoint or ""),
        "status": "non_comparable_failure",
        "reason_code": reason_code,
        "owner": "runner_post_explore_artifact_retrieval",
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "authoritative_proving": False,
        "fallback_macro_verdict_present": bool(fallback_macro_verdict),
        "fallback_macro_verdict": fallback_macro_verdict,
        "terminalization": dict(terminalization or {}),
        "job_status_snapshot": {
            "status": (finished or {}).get("status"),
            "explore_phase": (finished or {}).get("explore_phase"),
            "explore_stage": (finished or {}).get("explore_stage"),
            "explore_message": (finished or {}).get("explore_message"),
            "progress": _status_progress_text(finished),
        },
        "exception_class": exc.__class__.__name__,
        "exception": str(exc),
        "evidence_paths": [
            "job-status-final.json",
            "job-terminalization.json",
            "post-explore-artifact-fetch-authority.json",
            "measurement-terminalization.json",
            "run-authority.json",
            "run_result.json",
        ],
        "next_action": _post_explore_artifact_next_action(reason_code),
        "created_at": utc_iso(),
    }


def _apply_post_explore_artifact_fetch_failure_record(
    rec: dict[str, Any],
    *,
    run_dir: Path,
    start: float,
    job_id: str,
    finished: Mapping[str, Any],
    terminalization: Mapping[str, Any],
    artifact: str,
    endpoint: str,
    exc: BaseException,
    lane_readiness: Mapping[str, Any] | None = None,
    last_observation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    packet = _post_explore_artifact_fetch_packet(
        rec,
        run_dir=run_dir,
        job_id=job_id,
        finished=finished,
        terminalization=terminalization,
        artifact=artifact,
        endpoint=endpoint,
        exc=exc,
    )
    terminal = {
        "contract_version": "trust_contract_v1",
        "source": "runner_post_explore_artifact_fetch",
        "kind": "api_contract_failed",
        "terminalization_kind": "api_contract_failed",
        "reason": {
            "code": packet["reason_code"],
            "message": packet["next_action"],
        },
        "evidence": {
            "phase": "post_explore_artifact_fetch",
            "artifact": artifact,
            "endpoint": endpoint,
            "safe_to_compare": False,
            "post_explore_artifact_fetch_authority": "post-explore-artifact-fetch-authority.json",
            "measurement_terminalization": "measurement-terminalization.json",
        },
    }
    run_authority = build_run_authority_payload(
        run_id=str(rec.get("run_id") or run_dir.name),
        job_id=str(job_id or packet.get("job_id") or ""),
        lane_readiness=lane_readiness,
        terminalization=terminal,
        valid_run=False,
        session_capture_complete=False,
        verdict_status="",
        job_status=str((finished or {}).get("status") or ""),
    )
    rec.update(
        {
            "status": "failed",
            "phase": "post_explore_artifact_fetch",
            "ended_at": utc_iso(),
            "duration_sec": round(time.time() - start, 2),
            "save_session_exit": None,
            "save_session_timed_out": False,
            "run_validity": {
                "valid": False,
                "reason": f"post_explore_artifact_fetch_{packet['reason_code']}",
            },
            "valid_run": False,
            "kpi_run": {},
            "latest_status_map": {},
            "metrics": {
                "success_rate": 0.0,
                "verified_count": 0,
                "discovered_count": 0,
                "total_count": 0,
                "verification_verified": 0,
                "verification_inferred": 0,
                "verification_error": 0,
                "runtime_total_sec": None,
                "runtime_stage_p95_sec": None,
                "cost_run_usd": None,
                "cost_per_verified_function_usd": None,
            },
            "verdict": {},
            "job_status_snapshot": packet["job_status_snapshot"],
            "job_terminalization": terminal,
            "runner_terminalization": terminal,
            "measurement_terminalization": packet,
            "post_explore_artifact_fetch_authority": packet,
            "run_authority": run_authority,
            "failure_domain": str(run_authority.get("failure_domain") or ""),
            "authoritative_proving": False,
            "last_observation": dict(last_observation or {}),
        }
    )
    write_json(run_dir / "post-explore-artifact-fetch-authority.json", packet)
    write_json(run_dir / "measurement-terminalization.json", packet)
    write_json(run_dir / "job-terminalization.json", terminal)
    write_json(run_dir / "run-authority.json", run_authority)
    write_json(run_dir / "run_result.json", rec)
    return rec


def flake_rate(control_runs: list[dict[str, Any]]) -> float | None:
    if len(control_runs) < 2:
        return None
    baseline = control_runs[0].get("latest_status_map") or {}
    if not baseline:
        return None
    changed = 0
    total = 0
    for r in control_runs[1:]:
        curr = r.get("latest_status_map") or {}
        for fn in (set(baseline) | set(curr)):
            total += 1
            if baseline.get(fn, "unknown") != curr.get(fn, "unknown"):
                changed += 1
    return round((changed / total) if total else 0.0, 4)


def run_one(
    client: ApiClient,
    repo_root: Path,
    run_dir: Path,
    api_url: str,
    api_key: str,
    target_name: str,
    dll_path: Path,
    variant_name: str,
    settings: dict[str, Any],
    poll_sec: int,
    analyze_timeout_sec: int,
    explore_timeout_sec: int,
    stuck_seconds: int,
    snapshot_profile: str,
    heartbeat_path: Path,
    campaign_log: Path | None = None,
    lane_readiness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    lane_id = str(settings.get("lane_id") or "lane-main")
    variant_id = str(settings.get("variant_id") or variant_name)
    rec: dict[str, Any] = {
        "run_id": run_dir.name,
        "target": target_name,
        "target_dll": str(dll_path),
        "variant": variant_name,
        "variant_id": variant_id,
        "lane_id": lane_id,
        "explore_settings": settings,
        "started_at": utc_iso(),
        "status": "running",
    }
    start = time.time()
    last_observation: dict[str, Any] = {}

    def _capture_observation(observation: Mapping[str, Any], *, status: str) -> None:
        nonlocal last_observation
        last_observation = dict(observation or {})
        rec["last_observation"] = last_observation
        record_live_checkpoint_observation(
            last_observation,
            heartbeat_path=heartbeat_path,
            lane_id=lane_id,
            run_id=run_dir.name,
            status=status,
            job_id=job_id,
            campaign_log=campaign_log,
        )

    update_lane_heartbeat(
        heartbeat_path,
        lane_id,
        run_dir.name,
        status="launch",
        details={"target": target_name, "variant": variant_name},
    )
    log_line(f"run-start {run_dir.name} target={target_name} variant={variant_name}", campaign_log)
    if _lane_or_infra_unavailable(lane_readiness):
        finished = {
            "status": "error",
            "error": "lane readiness unavailable before analyze",
            "blocking_reasons": list(lane_readiness.get("blocking_reasons") or []),
        }
        write_json(run_dir / "job-status-analyze.json", finished)
        reason_code = _classify_measurement_reason(
            phase="preflight",
            status_payload=finished,
            lane_readiness=lane_readiness,
        )
        _apply_measurement_terminalized_record(
            rec,
            run_dir=run_dir,
            start=start,
            phase="preflight",
            reason_code=reason_code,
            status_payload=finished,
            lane_readiness=lane_readiness,
            last_observation=last_observation,
        )
        log_line(f"run-measurement-terminalized {run_dir.name} reason={reason_code} phase=preflight", campaign_log)
        update_lane_heartbeat(
            heartbeat_path,
            lane_id,
            run_dir.name,
            status="failed",
            details={
                "phase": "preflight",
                "measurement_terminalization": reason_code,
            },
        )
        return rec
    try:
        selected_bridge_url = str(
            settings.get("selected_bridge_url")
            or settings.get("control_plane_selected_bridge_url")
            or ""
        ).strip()
        analyze_kwargs: dict[str, Any] = {}
        try:
            if "bridge_url_override" in inspect.signature(client.analyze).parameters:
                analyze_kwargs["bridge_url_override"] = selected_bridge_url
        except (TypeError, ValueError):
            analyze_kwargs = {}
        job_id = client.analyze(
            dll_path,
            hints=f"Nightly ground-truth for {target_name}",
            use_cases="Regression + flake + stress",
            tags={
                "run_set_id": run_dir.parent.parent.name,
                "playbook_step": run_dir.name,
                "analysis_profile": settings.get("analysis_profile", "strict_dll"),
                "lane_id": lane_id,
                "ghidra_required": bool(settings.get("ghidra_required")),
                "skip_cache": bool(settings.get("skip_cache")),
            },
            **analyze_kwargs,
        )
    except Exception as exc:
        finished = {
            "status": "error",
            "error": str(exc),
        }
        write_json(run_dir / "job-status-analyze.json", finished)
        reason_code = _classify_measurement_reason(
            phase="analyze",
            status_payload=finished,
            exc=exc,
            lane_readiness=lane_readiness,
        )
        _apply_measurement_terminalized_record(
            rec,
            run_dir=run_dir,
            start=start,
            phase="analyze",
            reason_code=reason_code,
            status_payload=finished,
            lane_readiness=lane_readiness,
            last_observation=last_observation,
            exc=exc,
        )
        log_line(f"run-measurement-terminalized {run_dir.name} reason={reason_code} phase=analyze-launch", campaign_log)
        update_lane_heartbeat(
            heartbeat_path,
            lane_id,
            run_dir.name,
            status="failed",
            details={
                "phase": "analyze",
                "measurement_terminalization": reason_code,
            },
        )
        return rec
    rec["job_id"] = job_id
    update_lane_heartbeat(heartbeat_path, lane_id, run_dir.name, status="analyze", job_id=job_id)
    log_line(f"analyze-start job={job_id}", campaign_log)
    try:
        analyzed = wait_job(
            client,
            job_id,
            phase="analyze",
            timeout_sec=analyze_timeout_sec,
            poll_sec=poll_sec,
            stuck_seconds=stuck_seconds,
            heartbeat_cb=lambda st: update_lane_heartbeat(
                heartbeat_path,
                lane_id,
                run_dir.name,
                status="analyze",
                job_id=job_id,
                details={"status": st.get("status"), "progress": st.get("progress")},
            ),
            observation_cb=lambda observation: _capture_observation(observation, status="analyze"),
        )
    except TimeoutError as exc:
        try:
            analyzed = client.get(f"/api/jobs/{job_id}", timeout=60)
        except Exception:
            analyzed = {
                "job_id": job_id,
                "status": "timeout",
                "error": str(exc),
                "last_observation": last_observation,
            }
        upload_investigation = _fetch_upload_investigation_artifact(client, job_id, run_dir)
        if upload_investigation.get("available"):
            analyzed["upload_investigation"] = upload_investigation.get("events") or []
            progress10_breadcrumbs = list(upload_investigation.get("progress_10_control_breadcrumbs") or [])
            if progress10_breadcrumbs:
                analyzed["worker_progress_10_breadcrumbs"] = progress10_breadcrumbs
                last_observation = {
                    **dict(last_observation or {}),
                    "worker_progress_10_breadcrumbs": progress10_breadcrumbs,
                    "progress_10_control_last_phase": str(progress10_breadcrumbs[-1].get("phase") or ""),
                }
                rec["last_observation"] = last_observation
        write_json(run_dir / "job-status-analyze.json", analyzed)
        try:
            recovered_invocables = _select_invocables(
                analyzed,
                settings.get("selected_invocable_names") or [],
            )
        except Exception:
            recovered_invocables = []
        if str(analyzed.get("status") or "").strip().lower() == "done" and recovered_invocables:
            recovery_packet = _analyze_timeout_recovery_authority_packet(
                job_id=job_id,
                target_name=target_name,
                status_payload=analyzed,
                selected_invocables=recovered_invocables,
                last_observation=last_observation,
                exc=exc,
            )
            rec["analyze_timeout_recovery_authority"] = recovery_packet
            write_json(run_dir / "analyze-timeout-recovery-authority.json", recovery_packet)
            log_line(
                (
                    f"analyze-timeout-recovered {run_dir.name} "
                    f"job={job_id} invocables={len(recovered_invocables)}"
                ),
                campaign_log,
            )
        else:
            reason_code = _classify_measurement_reason(
                phase="analyze",
                status_payload=analyzed,
                exc=exc,
                lane_readiness=lane_readiness,
            )
            _apply_measurement_terminalized_record(
                rec,
                run_dir=run_dir,
                start=start,
                phase="analyze",
                reason_code=reason_code,
                status_payload=analyzed,
                lane_readiness=lane_readiness,
                last_observation=last_observation,
                exc=exc,
            )
            log_line(f"run-measurement-terminalized {run_dir.name} reason={reason_code} phase=analyze", campaign_log)
            update_lane_heartbeat(
                heartbeat_path,
                lane_id,
                run_dir.name,
                status="failed",
                job_id=job_id,
                details={
                    "phase": "analyze",
                    "measurement_terminalization": reason_code,
                    "last_observation": last_observation,
                },
            )
            return rec
    write_json(run_dir / "job-status-analyze.json", analyzed)
    if str(analyzed.get("status") or "").lower() == "error":
        reason_code = _classify_measurement_reason(
            phase="analyze",
            status_payload=analyzed,
            lane_readiness=lane_readiness,
        )
        _apply_measurement_terminalized_record(
            rec,
            run_dir=run_dir,
            start=start,
            phase="analyze",
            reason_code=reason_code,
            status_payload=analyzed,
            lane_readiness=lane_readiness,
            last_observation=last_observation,
        )
        log_line(f"run-measurement-terminalized {run_dir.name} reason={reason_code} phase=analyze", campaign_log)
        update_lane_heartbeat(
            heartbeat_path,
            lane_id,
            run_dir.name,
            status="failed",
            job_id=job_id,
            details={
                "phase": "analyze",
                "measurement_terminalization": reason_code,
                "last_observation": last_observation,
            },
        )
        return rec
    invocables = _select_invocables(analyzed, settings.get("selected_invocable_names") or [])

    client.post_json("/api/generate", {"job_id": job_id, "component_name": target_name, "selected": invocables}, timeout=240)
    client.post_json(f"/api/jobs/{job_id}/explore", {"explore_settings": settings}, timeout=120)
    update_lane_heartbeat(heartbeat_path, lane_id, run_dir.name, status="explore", job_id=job_id)
    log_line(f"explore-start job={job_id}", campaign_log)
    try:
        finished = wait_job(
            client,
            job_id,
            phase="explore",
            timeout_sec=explore_timeout_sec,
            poll_sec=poll_sec,
            stuck_seconds=stuck_seconds,
            heartbeat_cb=lambda st: update_lane_heartbeat(
                heartbeat_path,
                lane_id,
                run_dir.name,
                status="explore",
                job_id=job_id,
                details={
                    "phase": st.get("explore_phase"),
                    "stage": st.get("explore_stage", ""),
                    "message": st.get("explore_message"),
                    "progress": st.get("explore_progress", st.get("progress")),
                },
            ),
            observation_cb=lambda observation: _capture_observation(observation, status="explore"),
        )
    except QuasiTerminalClarifyStall as exc:
        finished = dict(exc.status_payload or {})
        write_json(run_dir / "job-status-final.json", finished)
        terminalization = resolve_job_terminalization(
            client,
            job_id,
            status_payload=finished,
            observed_stable_for_seconds=exc.stable_for_seconds,
        )
        _apply_terminalized_failure_record(
            rec,
            run_dir=run_dir,
            start=start,
            finished=finished,
            terminalization=terminalization,
            lane_readiness=lane_readiness,
            last_observation=last_observation,
        )
        log_line(
            (
                f"run-terminalized {run_dir.name} kind={terminalization['kind']} "
                f"phase={rec.get('phase')} message={terminalization.get('reason', {}).get('message')}"
            ),
            campaign_log,
        )
        update_lane_heartbeat(
            heartbeat_path,
            lane_id,
            run_dir.name,
            status="failed",
            job_id=job_id,
            details={
                "phase": rec.get("phase"),
                "runner_terminalization": terminalization["kind"],
                "last_observation": last_observation,
            },
        )
        return rec
    except TimeoutError:
        finished = client.get(f"/api/jobs/{job_id}", timeout=60)
        write_json(run_dir / "job-status-final.json", finished)
        terminalization = resolve_job_terminalization(
            client,
            job_id,
            status_payload=finished,
            observed_timeout=True,
        )
        _apply_terminalized_failure_record(
            rec,
            run_dir=run_dir,
            start=start,
            finished=finished,
            terminalization=terminalization,
            lane_readiness=lane_readiness,
            last_observation=last_observation,
        )
        log_line(
            (
                f"run-terminalized {run_dir.name} kind={terminalization['kind']} "
                f"phase={rec.get('phase')} message={terminalization.get('reason', {}).get('message')}"
            ),
            campaign_log,
        )
        update_lane_heartbeat(
            heartbeat_path,
            lane_id,
            run_dir.name,
            status="failed",
            job_id=job_id,
            details={
                "phase": rec.get("phase"),
                "runner_terminalization": terminalization["kind"],
                "last_observation": last_observation,
            },
        )
        return rec
    write_json(run_dir / "job-status-final.json", finished)
    terminalization = resolve_job_terminalization(
        client,
        job_id,
        status_payload=finished,
    )
    write_json(run_dir / "job-terminalization.json", terminalization)

    verdict_endpoint = f"/api/jobs/{job_id}/verdict"
    try:
        verdict = (
            _fetch_post_explore_artifact_with_retry(
                client,
                verdict_endpoint,
                artifact="verdict",
                run_dir=run_dir,
                timeout=60,
                campaign_log=campaign_log,
            ).get("verdict")
            or {}
        )
    except Exception as exc:
        _apply_post_explore_artifact_fetch_failure_record(
            rec,
            run_dir=run_dir,
            start=start,
            job_id=job_id,
            finished=finished,
            terminalization=terminalization,
            artifact="verdict",
            endpoint=verdict_endpoint,
            exc=exc,
            lane_readiness=lane_readiness,
            last_observation=last_observation,
        )
        log_line(
            f"run-post-explore-fetch-terminalized {run_dir.name} artifact=verdict reason={rec['measurement_terminalization']['reason_code']}",
            campaign_log,
        )
        update_lane_heartbeat(
            heartbeat_path,
            lane_id,
            run_dir.name,
            status="failed",
            job_id=job_id,
            details={
                "phase": "post_explore_artifact_fetch",
                "measurement_terminalization": rec["measurement_terminalization"]["reason_code"],
                "last_observation": last_observation,
            },
        )
        return rec
    if not verdict:
        verdict = finished.get("macro_verdict") or {}
    write_json(run_dir / "verdict.json", verdict)
    findings_endpoint = f"/api/findings/{job_id}"
    try:
        findings = (
            _fetch_post_explore_artifact_with_retry(
                client,
                findings_endpoint,
                artifact="findings",
                run_dir=run_dir,
                timeout=60,
                campaign_log=campaign_log,
            ).get("findings")
            or []
        )
    except Exception as exc:
        _apply_post_explore_artifact_fetch_failure_record(
            rec,
            run_dir=run_dir,
            start=start,
            job_id=job_id,
            finished=finished,
            terminalization=terminalization,
            artifact="findings",
            endpoint=findings_endpoint,
            exc=exc,
            lane_readiness=lane_readiness,
            last_observation=last_observation,
        )
        log_line(
            f"run-post-explore-fetch-terminalized {run_dir.name} artifact=findings reason={rec['measurement_terminalization']['reason_code']}",
            campaign_log,
        )
        update_lane_heartbeat(
            heartbeat_path,
            lane_id,
            run_dir.name,
            status="failed",
            job_id=job_id,
            details={
                "phase": "post_explore_artifact_fetch",
                "measurement_terminalization": rec["measurement_terminalization"]["reason_code"],
                "last_observation": last_observation,
            },
        )
        return rec
    write_json(run_dir / "findings.json", findings)
    scoring_scope = target_scope_names(settings)
    st_map = canonical_status_map(findings, scoring_scope)

    session_dir = run_dir / "session"
    _reset_session_capture_dir(session_dir)
    save_started_at = time.time()
    save_cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repo_root / "scripts" / "ops" / "save-session.ps1"),
        "-JobId",
        job_id,
        "-ApiUrl",
        api_url,
        "-OutDir",
        str(session_dir),
        "-SnapshotProfile",
        snapshot_profile,
    ]
    if api_key:
        save_cmd.extend(["-ApiKey", api_key])
    save_stdout = ""
    save_stderr = ""
    save_returncode = 0
    save_timed_out = False
    try:
        save = subprocess.run(save_cmd, cwd=str(repo_root), capture_output=True, text=True, timeout=240)
        save_stdout = save.stdout or ""
        save_stderr = save.stderr or ""
        save_returncode = int(save.returncode or 0)
    except subprocess.TimeoutExpired as exc:
        save_timed_out = True
        save_stdout = str(exc.stdout or "")
        save_stderr = str(exc.stderr or "")
        if not _session_capture_artifacts_present(session_dir) or not _session_capture_artifacts_fresh(
            session_dir,
            started_at=save_started_at,
        ) or not _session_capture_has_ledger_completion(session_dir):
            raise
        save_stderr = (
            save_stderr
            + "\nsave-session timeout tolerated because required session artifacts and ledger completion were already written"
        ).strip()
        save_returncode = 0
    (run_dir / "save-session.log").write_text((save_stdout + "\n" + save_stderr), encoding="utf-8")

    verification = read_json(session_dir / "verification-report.json", {})
    run_validity = read_json(session_dir / "run-validity.json", {})
    kpi_run = read_json(session_dir / "kpi_run.json", {})
    session_capture_complete = bool(read_json(session_dir / "session-meta.json", {})) and bool(
        read_json(session_dir / "stage-index.json", {})
    )
    session_capture_diagnostics = _summarize_session_capture_semantics(session_dir)
    session_capture_diagnostics.update(
        {
            "save_session_exit": save_returncode,
            "save_session_timed_out": save_timed_out,
            "session_capture_complete": session_capture_complete,
            "run_validity_valid": bool((run_validity or {}).get("valid")),
        }
    )
    write_json(run_dir / "session-capture-diagnostics.json", session_capture_diagnostics)
    run_valid = bool((run_validity or {}).get("valid"))
    v_verified = int((verification or {}).get("verified_count") or finished.get("verification_verified") or 0)
    v_inferred = int((verification or {}).get("inferred_count") or finished.get("verification_inferred") or 0)
    v_error = int(finished.get("verification_error") or 0)

    discovered_count = sum(1 for st in st_map.values() if str(st).strip().lower() in SUCCESS_LIKE_FINDING_STATUSES)
    verified_count = int(verdict.get("verified_count") or v_verified or 0)
    total_count = int(verdict.get("total_count") or len(st_map) or 0)
    success_rate = (verified_count / total_count) if total_count else 0.0
    explore_started_at = _safe_float(finished.get("explore_started_at"), start)
    updated_at = _safe_float(finished.get("updated_at"), time.time())
    run_authority = build_run_authority_payload(
        run_id=str(rec.get("run_id") or run_dir.name),
        job_id=job_id,
        lane_readiness=lane_readiness,
        terminalization=terminalization,
        valid_run=run_valid,
        session_capture_complete=session_capture_complete,
        verdict_status=str((verdict or {}).get("status") or ""),
        job_status=str(finished.get("status") or ""),
        save_session_exit=save_returncode,
        save_session_timed_out=save_timed_out,
    )
    authority_completion = _authority_completion_reconciliation_packet(
        rec=rec,
        run_dir=run_dir,
        status_payload=finished,
        measurement_packet={},
        terminalization=terminalization,
        run_authority=run_authority,
        valid_run=run_valid,
        session_capture_complete=session_capture_complete,
        verdict_status=str((verdict or {}).get("status") or ""),
    )

    rec.update(
        {
            "status": "ok" if str(run_authority.get("authority_level") or "") in {"decision_bearing", "review_only"} else "failed",
            "phase": finished.get("explore_phase"),
            "ended_at": utc_iso(),
            "duration_sec": round(time.time() - start, 2),
            "save_session_exit": save_returncode,
            "save_session_timed_out": save_timed_out,
            "run_validity": run_validity,
            "valid_run": run_valid,
            "kpi_run": kpi_run,
            "latest_status_map": st_map,
            "metrics": {
                "success_rate": round(success_rate, 4),
                "verified_count": verified_count,
                "discovered_count": discovered_count,
                "total_count": total_count,
                "verification_verified": v_verified,
                "verification_inferred": v_inferred,
                "verification_error": v_error,
                "runtime_total_sec": round(max(0.0, updated_at - explore_started_at), 2),
                "runtime_stage_p95_sec": None,
                "cost_run_usd": None,
                "cost_per_verified_function_usd": None,
            },
            "verdict": verdict,
            "job_status_snapshot": {
                "status": finished.get("status"),
                "explore_phase": finished.get("explore_phase"),
                "explore_message": finished.get("explore_message"),
            },
            "job_terminalization": terminalization,
            "runner_terminalization": (
                dict(terminalization or {})
                if str((terminalization or {}).get("source") or "").strip() == "runner_fallback"
                else None
            ),
            "run_authority": run_authority,
            "authority_completion_reconciliation": authority_completion,
            "failure_domain": str(run_authority.get("failure_domain") or ""),
            "authoritative_proving": bool(run_authority.get("authoritative_proving")),
            "session_capture_diagnostics": session_capture_diagnostics,
            "last_observation": last_observation,
        }
    )
    write_json(run_dir / "authority-completion-reconciliation.json", authority_completion)
    write_json(run_dir / "run-authority.json", run_authority)
    write_json(run_dir / "run_result.json", rec)
    log_line(
        (
            f"run-end {run_dir.name} status={rec['status']} phase={rec.get('phase')} "
            f"success_rate={rec['metrics']['success_rate']:.2%} verified={verified_count}/{total_count}"
        ),
        campaign_log,
    )
    update_lane_heartbeat(
        heartbeat_path,
        lane_id,
        run_dir.name,
        status="done" if rec.get("status") == "ok" else "failed",
        job_id=job_id,
        details={"phase": rec.get("phase"), "valid_run": run_valid, "last_observation": last_observation},
    )
    return rec


def append_bug(
    bug_md: Path,
    bugs_json: Path,
    bugs: list[dict[str, Any]],
    severity: str,
    signature: str,
    stage: str,
    details: str,
    job_id: str = "",
    repro: str = "",
    likely: str = "",
    guardrail: str = "",
) -> None:
    item = {
        "timestamp": utc_iso(),
        "severity": severity,
        "signature": signature,
        "stage": stage,
        "details": details,
        "job_id": job_id,
        "repro": repro,
        "likely_cause": likely,
        "next_guardrail": guardrail,
    }
    bugs.append(item)
    write_json(bugs_json, bugs)
    append_text(
        bug_md,
        (
            f"\n## [{severity}] {signature} ({item['timestamp']})\n"
            f"- Stage: `{stage}`\n- Job: `{job_id or 'n/a'}`\n- Details: {details}\n"
            f"- Likely cause: {likely or 'TBD'}\n- Next guardrail/test: {guardrail or 'TBD'}\n"
            f"- Repro: `{repro or 'n/a'}`\n"
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run nightly ground-truth campaign.")
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--max-runs", type=int, default=20)
    parser.add_argument("--poll-interval-sec", type=int, default=10)
    parser.add_argument("--analyze-timeout-sec", type=int, default=1800)
    parser.add_argument("--explore-timeout-sec", type=int, default=5400)
    parser.add_argument("--build-timeout-minutes", type=int, default=30)
    parser.add_argument(
        "--api-url",
        default=os.getenv("MCP_FACTORY_API_URL") or local_api_base_url(),
    )
    parser.add_argument("--api-key", default=os.getenv("MCP_FACTORY_API_KEY", ""))
    parser.add_argument("--bridge-url", default=os.getenv("GUI_BRIDGE_URL", local_bridge_base_url()))
    parser.add_argument("--bridge-key", default=os.getenv("GUI_BRIDGE_SECRET", ""))
    parser.add_argument(
        "--analysis-profile",
        choices=("strict_dll", "greybox_dll", "full_surface"),
        default="strict_dll",
    )
    parser.add_argument(
        "--snapshot-profile",
        choices=("full", "compact"),
        default="full",
    )
    parser.add_argument("--stuck-seconds", type=int, default=900)
    parser.add_argument(
        "--targets",
        default="contoso_cs,contoso_cs_interwoven",
        help="Comma-separated targets: contoso_cs,contoso_cs_interwoven",
    )
    parser.add_argument(
        "--campaign-suffix",
        default="",
        help="Optional suffix appended to campaign id (for parallel campaigns).",
    )
    parser.add_argument(
        "--report-suffix",
        default="",
        help="Optional suffix appended to morning report filenames.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    started = now_local()
    deadline = started + timedelta(hours=float(args.hours))
    date_slug = started.strftime("%Y-%m-%d")
    campaign_id = started.strftime("%Y%m%d-%H%M%S")
    if args.campaign_suffix:
        campaign_id = f"{campaign_id}-{args.campaign_suffix.strip()}"
    report_suffix = f"-{args.report_suffix.strip()}" if args.report_suffix else ""

    nightly_root = repo_root / "sessions" / "nightly" / date_slug / campaign_id
    runs_root = nightly_root / "runs"
    report_md = repo_root / "sessions" / "reports" / f"morning-{date_slug}{report_suffix}.md"
    report_json = repo_root / "sessions" / "reports" / f"morning-{date_slug}{report_suffix}.json"
    bug_md = repo_root / "docs" / "bugs" / "nightly" / f"{date_slug}.md"
    bugs_json = nightly_root / "bugs.json"
    summary_path = nightly_root / "kpi_nightly_summary.json"
    runs_jsonl = nightly_root / "runs.jsonl"
    campaign_log = nightly_root / "campaign.log"
    harness_manifest_path = nightly_root / "harness_manifest.json"
    harness_state_path = nightly_root / "harness_state.json"
    harness_lifecycle_path = nightly_root / "harness_lifecycle.json"
    lane_heartbeat_path = nightly_root / "lane_heartbeats.json"

    if args.dry_run:
        print(f"campaign_id={campaign_id}")
        print(f"api_url={args.api_url}")
        print(f"bridge_url={args.bridge_url}")
        print(f"output={nightly_root}")
        print(f"analysis_profile={args.analysis_profile}")
        print(f"snapshot_profile={args.snapshot_profile}")
        return 0

    nightly_root.mkdir(parents=True, exist_ok=True)
    runs_root.mkdir(parents=True, exist_ok=True)
    log_line(f"campaign-start id={campaign_id} api_url={args.api_url}", campaign_log)
    manifest = {
        "version": "1.0",
        "campaign_id": campaign_id,
        "started_at": started.isoformat(),
        "api_url": args.api_url,
        "bridge_url": args.bridge_url,
        "analysis_profile": args.analysis_profile,
        "snapshot_profile": args.snapshot_profile,
        "hours": args.hours,
        "max_runs": args.max_runs,
        "baseline_policy": "valid_only",
        "lifecycle_ref": harness_lifecycle_path.name,
        "state_ref": harness_state_path.name,
        "lane_heartbeat_ref": lane_heartbeat_path.name,
    }
    write_json(harness_manifest_path, manifest)
    emit_harness_state(
        harness_state_path,
        harness_lifecycle_path,
        "preflight",
        {"campaign_id": campaign_id, "api_url": args.api_url},
    )
    if not bug_md.exists():
        append_text(bug_md, f"\n# Nightly Bugs - {date_slug}\n")
    append_text(bug_md, f"\n\n## Campaign `{campaign_id}` started `{started.isoformat()}`\n")

    bugs: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    last_job_by_target: dict[str, str] = {}

    contoso = repo_root / "tests" / "fixtures" / "contoso_legacy" / "contoso_cs.dll"
    interwoven = repo_root / "tests" / "fixtures" / "contoso_interwoven" / "contoso_cs_interwoven.dll"
    requested_targets = {t.strip().lower() for t in str(args.targets).split(",") if t.strip()}
    valid_target_names = {"contoso_cs", "contoso_cs_interwoven"}
    unknown_targets = sorted(requested_targets - valid_target_names)
    if unknown_targets:
        append_bug(
            bug_md, bugs_json, bugs, "P1", "unknown_targets", "preflight",
            f"Unknown target names: {', '.join(unknown_targets)}",
            likely="invalid CLI arg --targets",
            guardrail="validate target names before run",
        )
        write_json(summary_path, {"campaign_id": campaign_id, "error": "unknown targets", "bugs": bugs})
        emit_harness_state(
            harness_state_path,
            harness_lifecycle_path,
            "teardown",
            {"error": "unknown_targets"},
        )
        return 2

    if "contoso_cs" in requested_targets and not contoso.exists():
        append_bug(
            bug_md, bugs_json, bugs, "P0", "missing_contoso_fixture", "preflight",
            f"Missing DLL: {contoso}", likely="fixture missing", guardrail="preflight fixture existence check"
        )
        write_json(summary_path, {"campaign_id": campaign_id, "error": "missing contoso fixture", "bugs": bugs})
        emit_harness_state(
            harness_state_path,
            harness_lifecycle_path,
            "teardown",
            {"error": "missing_contoso_fixture"},
        )
        return 2

    targets: list[tuple[str, Path]] = []
    if "contoso_cs" in requested_targets:
        targets.append(("contoso_cs", contoso))

    if "contoso_cs_interwoven" in requested_targets:
        log_line("phase1-build interwoven fixture", campaign_log)
        ok_interwoven, build_msg = ensure_interwoven(repo_root, args.build_timeout_minutes)
        if not ok_interwoven:
            log_line("interwoven-build failed; requested target unavailable", campaign_log)
            append_bug(
                bug_md, bugs_json, bugs, "P1", "interwoven_build_failed", "phase1-build",
                build_msg,
                repro=f"powershell -ExecutionPolicy Bypass -File {repo_root / 'tests/fixtures/contoso_interwoven/build-interwoven.ps1'}",
                likely="toolchain env unavailable", guardrail="timebox build and continue with contoso"
            )
        elif interwoven.exists():
            log_line("interwoven fixture ready; including in nightly targets", campaign_log)
            targets.append(("contoso_cs_interwoven", interwoven))
        else:
            append_bug(
                bug_md, bugs_json, bugs, "P1", "interwoven_missing_after_build", "phase1-build",
                f"Expected DLL missing after build: {interwoven}",
                likely="build script did not emit expected output",
                guardrail="validate build output path",
            )

    if not targets:
        append_bug(
            bug_md, bugs_json, bugs, "P0", "no_runnable_targets", "preflight",
            "No runnable targets after preflight/build checks.",
            likely="invalid targets or fixture build failure",
            guardrail="require at least one runnable target",
        )
        write_json(summary_path, {"campaign_id": campaign_id, "error": "no runnable targets", "bugs": bugs})
        emit_harness_state(
            harness_state_path,
            harness_lifecycle_path,
            "teardown",
            {"error": "no_runnable_targets"},
        )
        return 2

    emit_harness_state(
        harness_state_path,
        harness_lifecycle_path,
        "health",
        {"target_count": len(targets), "api_url": args.api_url, "bridge_url": args.bridge_url},
    )
    api_ok, api_msg = verify_api_identity(args.api_url, args.api_key)
    if not api_ok:
        append_bug(
            bug_md,
            bugs_json,
            bugs,
            "P0",
            "api_identity_failed",
            "preflight",
            api_msg,
            likely="API endpoint unavailable or miswired",
            guardrail="verify API URL/port and endpoint identity before campaign",
        )
        write_json(summary_path, {"campaign_id": campaign_id, "error": "api_identity_failed", "bugs": bugs})
        emit_harness_state(
            harness_state_path,
            harness_lifecycle_path,
            "teardown",
            {"error": "api_identity_failed", "detail": api_msg},
        )
        return 2

    bridge_ok, bridge_msg = verify_bridge_identity(args.bridge_url, args.bridge_key)
    if not bridge_ok:
        append_bug(
            bug_md,
            bugs_json,
            bugs,
            "P0",
            "bridge_identity_failed",
            "preflight",
            bridge_msg,
            likely="bridge endpoint unavailable, miswired, or API-shaped",
            guardrail="verify bridge URL/port and /execute route before campaign",
        )
        write_json(summary_path, {"campaign_id": campaign_id, "error": "bridge_identity_failed", "bugs": bugs})
        emit_harness_state(
            harness_state_path,
            harness_lifecycle_path,
            "teardown",
            {"error": "bridge_identity_failed", "detail": bridge_msg},
        )
        return 2

    log_line(f"preflight-ok api={api_msg} bridge={bridge_msg}", campaign_log)
    freshness = ensure_local_api_freshness(
        repo_root,
        args.api_url,
        args.api_key,
        campaign_log=campaign_log,
    )
    manifest["api_freshness"] = freshness
    write_json(harness_manifest_path, manifest)
    emit_harness_state(
        harness_state_path,
        harness_lifecycle_path,
        "freshness",
        {"freshness_verdict": freshness.get("freshness_verdict")},
    )
    if freshness.get("freshness_verdict") == "restart_blocked_unmanaged_owner":
        append_bug(
            bug_md,
            bugs_json,
            bugs,
            "P0",
            "api_freshness_blocked_unmanaged_owner",
            "preflight",
            "Local API lane is stale but owned by an unmanaged process; refusing to kill it automatically.",
            likely="another service is bound to the proving port",
            guardrail="run against a managed MCP Factory lane or free the local API port first",
        )
        write_json(
            summary_path,
            {
                "campaign_id": campaign_id,
                "error": "api_freshness_blocked_unmanaged_owner",
                "freshness": freshness,
                "bugs": bugs,
            },
        )
        emit_harness_state(
            harness_state_path,
            harness_lifecycle_path,
            "teardown",
            {"error": "api_freshness_blocked_unmanaged_owner"},
        )
        return 2
    client = ApiClient(args.api_url, args.api_key)

    model_env = os.getenv("OPENAI_EXPLORE_MODEL", "").strip()
    control = {
        "mode": "normal", "cap_profile": "deploy", "max_rounds": 5, "max_tool_calls": 8,
        "gap_resolution_enabled": True, "skip_documented": True, "deterministic_fallback_enabled": True,
        "clarification_questions_enabled": True, "context_density": "full",
        "analysis_profile": args.analysis_profile,
        "parallel_runs": 1,
    }
    if model_env:
        control["model"] = model_env

    variants = [
        ("control", control),
        ("v_context_minimal", {**control, "context_density": "minimal"}),
        ("v_budget_low", {**control, "mode": "dev", "max_rounds": 2, "max_tool_calls": 5, "gap_resolution_enabled": False}),
        ("v_curriculum_reverse", {**control, "instruction_fragment": "Probe uncertain or dependency-heavy functions first, then reverse ordering."}),
        ("stress", {**control, "mode": "extended", "max_rounds": 12, "max_tool_calls": 24, "skip_documented": False, "deterministic_fallback_enabled": False}),
    ]

    # Planned sequence: interleaved across targets so both contoso and interwoven get early coverage.
    plan: list[tuple[str, Path, str, dict[str, Any], bool]] = []
    phase_plan = [
        ("control", control, True),
        ("control", control, False),
        ("v_context_minimal", variants[1][1], False),
        ("v_budget_low", variants[2][1], False),
        ("v_curriculum_reverse", variants[3][1], False),
        ("control", control, True),
        ("stress", variants[4][1], False),
    ]
    for variant_name, variant_settings, cold in phase_plan:
        for target_name, target_path in targets:
            plan.append((target_name, target_path, variant_name, variant_settings, cold))

    emit_harness_state(
        harness_state_path,
        harness_lifecycle_path,
        "launch",
        {"planned_runs": len(plan), "max_runs": args.max_runs},
    )

    run_idx = 0
    while now_local() < deadline and run_idx < args.max_runs:
        if run_idx < len(plan):
            target_name, target_path, variant_name, settings_base, cold = plan[run_idx]
        else:
            target_name, target_path = targets[run_idx % len(targets)]
            variant_name, settings_base, cold = "control", control, ((run_idx + 1) % 4 == 0)
        run_idx += 1

        settings = dict(settings_base)
        settings["variant_id"] = variant_name
        settings["lane_id"] = f"lane-{(run_idx % max(1, len(targets))) + 1}"
        if not cold and last_job_by_target.get(target_name):
            settings["prior_job_id"] = last_job_by_target[target_name]
            settings["skip_to_stage"] = ""
        else:
            settings["prior_job_id"] = ""
            settings["skip_to_stage"] = ""

        # Mandatory bridge DLL cache flush for cold runs
        if cold:
            try:
                _flush_headers = {"X-Bridge-Key": args.bridge_key} if args.bridge_key else {}
                requests.post(
                    f"{args.bridge_url.rstrip('/')}/flush-dll-cache",
                    headers=_flush_headers,
                    timeout=10,
                )
                log_line(f"cold-flush bridge DLL cache flushed for {target_name}", campaign_log)
            except Exception as _flush_exc:
                log_line(f"cold-flush failed (non-fatal): {_flush_exc}", campaign_log)

        # Cross-DLL seeding: for warm runs, set cross_dll_prior_job_ids to
        # the last successful job of each *other* target
        _cross_dll_ids = [
            jid for tgt, jid in last_job_by_target.items()
            if tgt != target_name and jid
        ]
        if not cold and _cross_dll_ids:
            settings["cross_dll_prior_job_ids"] = _cross_dll_ids

        run_dir = runs_root / f"run-{run_idx:03d}-{target_name}-{variant_name}{'-cold' if cold else '-warm'}"
        rec: dict[str, Any] | None = None
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                rec = run_one(
                    client, repo_root, run_dir, args.api_url, args.api_key, target_name, target_path, variant_name, settings,
                    args.poll_interval_sec, args.analyze_timeout_sec, args.explore_timeout_sec,
                    args.stuck_seconds, args.snapshot_profile, lane_heartbeat_path, campaign_log
                )
                break
            except Exception as exc:
                last_exc = exc
                log_line(f"run-error {run_dir.name} attempt={attempt} err={exc}", campaign_log)
                if attempt == 1:
                    time.sleep(3)
        if rec is None:
            rec = {
                "run_id": run_dir.name,
                "target": target_name,
                "variant": variant_name,
                "variant_id": settings.get("variant_id"),
                "lane_id": settings.get("lane_id"),
                "status": "failed",
                "error": str(last_exc),
                "started_at": utc_iso(),
                "ended_at": utc_iso(),
            }
            write_json(run_dir / "run_result.json", rec)
            update_lane_heartbeat(
                lane_heartbeat_path,
                str(settings.get("lane_id") or "lane-main"),
                run_dir.name,
                status="failed",
                details={"error": str(last_exc)},
            )
            append_bug(
                bug_md, bugs_json, bugs, "P0", "run_exception", "runner", str(last_exc),
                likely="runner/API exception", guardrail="retry once then continue"
            )

        runs.append(rec)
        append_text(runs_jsonl, json.dumps(rec) + "\n")
        if rec.get("job_id"):
            last_job_by_target[target_name] = str(rec["job_id"])
        if rec.get("status") != "ok":
            append_bug(
                bug_md, bugs_json, bugs, "P0", "pipeline_run_failed", "explore",
                f"{rec['run_id']} phase={rec.get('phase')} err={rec.get('error')}",
                job_id=str(rec.get("job_id") or ""),
                likely="pipeline stage failure", guardrail="capture repro config and add stage guardrail"
            )
        if int(rec.get("save_session_exit") or 0) != 0:
            append_bug(
                bug_md, bugs_json, bugs, "P1", "save_session_nonzero_exit", "session-capture",
                f"{rec['run_id']} save-session exit={rec.get('save_session_exit')}",
                job_id=str(rec.get("job_id") or ""),
                likely="contract artifacts incomplete", guardrail="tighten compatibility capture checks"
            )
        if rec.get("status") == "ok" and not bool(rec.get("valid_run", False)):
            append_bug(
                bug_md, bugs_json, bugs, "P1", "invalid_run_excluded", "validity-gate",
                f"{rec['run_id']} failed run-validity gates: {(rec.get('run_validity') or {}).get('reasons')}",
                job_id=str(rec.get("job_id") or ""),
                likely="profile mismatch, artifact gaps, or contract failures",
                guardrail="exclude invalid runs from KPI baseline by default",
            )

    if run_idx >= args.max_runs:
        append_bug(
            bug_md, bugs_json, bugs, "P2", "campaign_cap_reached", "orchestrator",
            f"Reached max run cap {args.max_runs}", likely="intentional budget cap", guardrail="adjust cap after baseline"
        )

    emit_harness_state(
        harness_state_path,
        harness_lifecycle_path,
        "collect",
        {"runs_recorded": len(runs)},
    )

    # ── Parity check: warn if cold run diverges >10% from last warm run ──
    parity_warnings: list[dict[str, Any]] = []
    _warm_rates: dict[str, float] = {}
    for rec in runs:
        if rec.get("status") != "ok":
            continue
        target_name = str(rec.get("target") or "")
        vr = float((rec.get("metrics") or {}).get("success_rate") or 0.0)
        settings = rec.get("explore_settings") or {}
        is_cold = not bool(settings.get("prior_job_id"))
        if is_cold and target_name in _warm_rates:
            delta = abs(vr - _warm_rates[target_name])
            if delta > 0.10:
                parity_warnings.append({
                    "target": target_name,
                    "cold_run": rec.get("run_id"),
                    "cold_verified_rate": round(vr, 4),
                    "warm_verified_rate": round(_warm_rates[target_name], 4),
                    "delta": round(delta, 4),
                    "severity": "high" if delta > 0.20 else "medium",
                })
                log_line(
                    f"parity-warning target={target_name} cold={vr:.2%} warm={_warm_rates[target_name]:.2%} delta={delta:.2%}",
                    campaign_log,
                )
        elif not is_cold:
            _warm_rates[target_name] = vr

    ok_runs = [r for r in runs if r.get("status") == "ok"]
    valid_ok_runs = [r for r in ok_runs if bool(r.get("valid_run"))]
    invalid_ok_runs = [r for r in ok_runs if not bool(r.get("valid_run"))]
    controls = [r for r in valid_ok_runs if r.get("variant") == "control"]
    if not controls:
        controls = [r for r in ok_runs if r.get("variant") == "control"]

    baseline_runs = valid_ok_runs
    sr = [float((r.get("metrics") or {}).get("success_rate") or 0.0) for r in baseline_runs]
    rt = [float((r.get("metrics") or {}).get("runtime_total_sec") or 0.0) for r in baseline_runs]
    rt_p95 = None
    if rt:
        x = sorted(rt)
        rt_p95 = x[int(round(0.95 * (len(x) - 1)))]
    vv = sum(int((r.get("metrics") or {}).get("verification_verified") or 0) for r in baseline_runs)
    vi = sum(int((r.get("metrics") or {}).get("verification_inferred") or 0) for r in baseline_runs)
    vratio = (vv / (vv + vi)) if (vv + vi) else 0.0

    summary = {
        "campaign_id": campaign_id,
        "started_at": started.isoformat(),
        "ended_at": now_local().isoformat(),
        "runs_total": len(runs),
        "runs_ok": len(ok_runs),
        "runs_failed": len(runs) - len(ok_runs),
        "runs_valid": len(valid_ok_runs),
        "runs_invalid": len(invalid_ok_runs),
        "baseline_mode": "valid_only",
        "success_rate_avg": round(sum(sr) / len(sr), 4) if sr else 0.0,
        "flake_rate": flake_rate(controls),
        "runtime_p95_sec": round(rt_p95, 2) if rt_p95 is not None else None,
        "verified_vs_inferred_ratio": round(vratio, 4),
        "cost_run_usd": None,
        "runtime_stage_p95_sec": None,
        "duplicate_job_rate": round((len([r for r in runs if r.get("job_id")]) - len(set(str(r.get("job_id")) for r in runs if r.get("job_id")))) / max(1, len([r for r in runs if r.get('job_id')])), 4),
        "parity_warnings": parity_warnings,
        "runs": runs,
        "bugs": bugs,
    }
    write_json(summary_path, summary)
    write_json(report_json, summary)
    log_line(
        (
            f"campaign-end id={campaign_id} runs_total={summary['runs_total']} "
            f"runs_ok={summary['runs_ok']} runs_failed={summary['runs_failed']}"
        ),
        campaign_log,
    )

    report_lines = [
        f"# Morning Ground-Truth Report - {date_slug}",
        "",
        f"- Campaign: `{campaign_id}`",
        f"- Runs: {summary['runs_total']} total, {summary['runs_ok']} ok, {summary['runs_failed']} failed",
        f"- Valid runs: {summary['runs_valid']}, invalid runs: {summary['runs_invalid']} (excluded from baseline)",
        f"- Avg success rate: {summary['success_rate_avg']:.2%}",
        f"- Flake rate: {((summary['flake_rate'] or 0.0) if summary['flake_rate'] is not None else 0.0):.2%}" if summary["flake_rate"] is not None else "- Flake rate: N/A",
        f"- p95 runtime: {summary['runtime_p95_sec']} sec" if summary["runtime_p95_sec"] is not None else "- p95 runtime: N/A",
        f"- Verified vs inferred ratio: {summary['verified_vs_inferred_ratio']:.2%}",
        "- Cost/run: N/A (artifact gap)",
        "- Stage runtime p95: N/A (artifact gap)",
        "",
        "## Top failed runs",
    ]
    failed = [r for r in runs if r.get("status") != "ok"]
    if failed:
        for r in failed[:10]:
            report_lines.append(f"- `{r.get('run_id')}` target={r.get('target')} variant={r.get('variant')} error={r.get('error') or r.get('phase')}")
    else:
        report_lines.append("- None")
    report_lines.extend(["", "## Actions (P0/P1/P2)"])
    if bugs:
        for b in bugs[:5]:
            report_lines.append(f"- **{b['severity']}** `{b['signature']}`: {b.get('next_guardrail') or b.get('details')}")
    else:
        report_lines.append("- No new bugs detected.")
    report_md.parent.mkdir(parents=True, exist_ok=True)
    report_md.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    # Append-only baseline note to architecture doc.
    arch = repo_root / "docs" / "architecture" / "NXM-EXPANSION-ARCHITECTURE.md"
    marker = f"Nightly Ground Truth Baseline ({date_slug} / {campaign_id})"
    if arch.exists() and marker not in arch.read_text(encoding="utf-8"):
        append_text(
            arch,
            (
                f"\n\n### {marker}\n"
                f"- Runs total: {summary['runs_total']} (ok={summary['runs_ok']}, failed={summary['runs_failed']})\n"
                f"- Avg success rate: {summary['success_rate_avg']:.2%}\n"
                f"- Flake rate: {((summary['flake_rate'] or 0.0) if summary['flake_rate'] is not None else 0.0):.2%}\n"
                f"- p95 runtime: {summary['runtime_p95_sec'] if summary['runtime_p95_sec'] is not None else 'N/A'} sec\n"
                f"- Verified vs inferred ratio: {summary['verified_vs_inferred_ratio']:.2%}\n"
                f"- Cost/run: N/A (artifact gap)\n"
                f"- Stage runtime p95: N/A (artifact gap)\n"
                f"- Artifacts: `sessions/nightly/{date_slug}/{campaign_id}/` and `sessions/reports/morning-{date_slug}{report_suffix}.md`\n"
            ),
        )
    append_text(
        bug_md,
        (
            f"\n- Campaign completed `{now_local().isoformat()}` "
            f"(runs={summary['runs_total']}, ok={summary['runs_ok']}, failed={summary['runs_failed']}).\n"
        ),
    )
    emit_harness_state(
        harness_state_path,
        harness_lifecycle_path,
        "teardown",
        {
            "runs_total": summary["runs_total"],
            "runs_ok": summary["runs_ok"],
            "runs_failed": summary["runs_failed"],
            "runs_valid": summary["runs_valid"],
            "runs_invalid": summary["runs_invalid"],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
