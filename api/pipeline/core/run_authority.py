from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from api.infra.service_identity import TRUST_CONTRACT_VERSION

FAILURE_DOMAINS = {
    "runner",
    "api",
    "bridge",
    "pipeline",
    "session_capture",
    "product_semantics",
    "unknown",
}


def _utc_iso_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _coerce_str(value: Any) -> str:
    return str(value or "").strip()


def _normalize_failure_domain(value: str) -> str:
    normalized = _coerce_str(value).lower()
    return normalized if normalized in FAILURE_DOMAINS else "unknown"


def classify_failure_domain(
    *,
    lane_readiness: Mapping[str, Any] | None,
    terminalization: Mapping[str, Any] | None,
    valid_run: bool,
    session_capture_complete: bool,
    verdict_status: str,
    job_status: str,
    save_session_exit: int | None = None,
    save_session_timed_out: bool = False,
) -> str:
    readiness = dict(lane_readiness or {})
    if readiness and not bool(readiness.get("ready")):
        blocking_reasons = [
            _coerce_str(item).lower()
            for item in list(readiness.get("blocking_reasons") or [])
            if _coerce_str(item)
        ]
        if any(reason.startswith("api_") for reason in blocking_reasons):
            return "api"
        if any(reason.startswith("bridge_") for reason in blocking_reasons):
            return "bridge"
        return "unknown"

    terminal = dict(terminalization or {})
    terminal_kind = _coerce_str(
        terminal.get("terminalization_kind") or terminal.get("kind")
    ).lower()
    if terminal_kind == "runner_invalid":
        return "runner"
    if terminal_kind == "api_contract_failed":
        return "api"
    if terminal_kind == "bridge_execution_failed":
        return "bridge"
    if terminal_kind == "session_capture_failed":
        return "session_capture"
    if terminal_kind in {
        "quasi_terminal_stall",
        "quasi_terminal_clarify_stall",
        "timeout",
        "awaiting_clarification_authoritative",
        "error",
        "cancelled",
    }:
        return "pipeline"

    if save_session_timed_out or (save_session_exit is not None and int(save_session_exit) != 0):
        return "session_capture"
    if not session_capture_complete or not bool(valid_run):
        return "session_capture"

    normalized_verdict = _coerce_str(verdict_status).lower()
    normalized_job_status = _coerce_str(job_status).lower()
    if terminal_kind == "done":
        if normalized_job_status != "done" or normalized_verdict not in {"", "done"}:
            return "pipeline"
        return ""

    return "unknown"


def build_run_authority_payload(
    *,
    run_id: str,
    job_id: str,
    lane_readiness: Mapping[str, Any] | None,
    terminalization: Mapping[str, Any] | None,
    valid_run: bool,
    session_capture_complete: bool,
    verdict_status: str,
    job_status: str,
    save_session_exit: int | None = None,
    save_session_timed_out: bool = False,
) -> dict[str, Any]:
    readiness = dict(lane_readiness or {})
    terminal = dict(terminalization or {})
    blocking_reasons: list[str] = []
    reasons: list[str] = []

    lane_ready = bool(readiness.get("ready")) if readiness else None
    if lane_ready is True:
        reasons.append("lane_ready")
    elif lane_ready is False:
        blocking_reasons.extend(
            [
                _coerce_str(item)
                for item in list(readiness.get("blocking_reasons") or [])
                if _coerce_str(item)
            ]
        )

    terminal_kind = _coerce_str(
        terminal.get("terminalization_kind") or terminal.get("kind")
    ).lower()
    if terminal_kind:
        if terminal_kind == "done":
            reasons.append("terminalization_kind_done")
        elif terminal_kind == "awaiting_clarification_authoritative":
            reasons.append("terminalization_kind_awaiting_clarification_authoritative")
        else:
            blocking_reasons.append(f"terminalization_kind_{terminal_kind}")
    else:
        blocking_reasons.append("terminalization_kind_missing")

    normalized_verdict = _coerce_str(verdict_status).lower()
    if normalized_verdict == "done":
        reasons.append("verdict_status_done")
    elif normalized_verdict == "awaiting_clarification":
        reasons.append("verdict_status_awaiting_clarification")
    elif normalized_verdict:
        blocking_reasons.append(f"verdict_status_{normalized_verdict}")
    else:
        blocking_reasons.append("verdict_status_missing")

    normalized_job_status = _coerce_str(job_status).lower()
    if normalized_job_status == "done":
        reasons.append("job_status_done")
    elif normalized_job_status:
        blocking_reasons.append(f"job_status_{normalized_job_status}")
    else:
        blocking_reasons.append("job_status_missing")

    if bool(valid_run):
        reasons.append("run_validity_true")
    else:
        blocking_reasons.append("run_validity_false")

    if bool(session_capture_complete):
        reasons.append("session_capture_complete")
    else:
        blocking_reasons.append("session_capture_incomplete")

    if save_session_timed_out:
        blocking_reasons.append("save_session_timed_out")
    elif save_session_exit is not None and int(save_session_exit) != 0:
        blocking_reasons.append(f"save_session_exit_{int(save_session_exit)}")

    decision_bearing = (
        (lane_ready is not False)
        and terminal_kind == "done"
        and bool(valid_run)
        and bool(session_capture_complete)
        and normalized_verdict == "done"
        and normalized_job_status == "done"
    )
    review_only = (
        not decision_bearing
        and (lane_ready is not False)
        and terminal_kind == "awaiting_clarification_authoritative"
        and bool(valid_run)
        and bool(session_capture_complete)
    )
    authority_level = (
        "decision_bearing"
        if decision_bearing
        else ("review_only" if review_only else "non_authoritative")
    )
    failure_domain = (
        ""
        if decision_bearing
        else classify_failure_domain(
            lane_readiness=lane_readiness,
            terminalization=terminalization,
            valid_run=valid_run,
            session_capture_complete=session_capture_complete,
            verdict_status=normalized_verdict,
            job_status=normalized_job_status,
            save_session_exit=save_session_exit,
            save_session_timed_out=save_session_timed_out,
        )
    )

    return {
        "contract_version": TRUST_CONTRACT_VERSION,
        "run_id": _coerce_str(run_id),
        "job_id": _coerce_str(job_id),
        "authoritative_proving": bool(decision_bearing),
        "authority_level": authority_level,
        "checked_at": _utc_iso_now(),
        "reasons": reasons,
        "blocking_reasons": blocking_reasons,
        "failure_domain": failure_domain,
        "safe_to_steer_next_prompt": bool(decision_bearing),
        "terminalization_kind": terminal_kind,
        "lane_ready": lane_ready,
    }
