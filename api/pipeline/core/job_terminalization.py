from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from api.pipeline.core.runtime_api import (
    has_job_lifecycle_inconsistency,
    is_stale_nonterminal_job_record,
    is_terminal_job_record,
)

QUASI_TERMINAL_CLARIFY_STAGE = "s06_gaps"
QUASI_TERMINAL_CLARIFY_MESSAGE_TOKEN = "finalizing harmonized state"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _utc_iso_from_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.utcfromtimestamp(float(value)).isoformat() + "Z"
    except Exception:
        return None


def status_progress_text(status_payload: Mapping[str, Any]) -> str:
    raw = status_payload.get("explore_progress", status_payload.get("progress"))
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw).strip()


def is_quasi_terminal_clarify_signature(status_payload: Mapping[str, Any]) -> bool:
    explore_phase = str(status_payload.get("explore_phase") or "").strip().lower()
    explore_stage = str(status_payload.get("explore_stage") or "").strip().lower()
    explore_message = str(status_payload.get("explore_message") or "").strip().lower()
    progress_text = status_progress_text(status_payload).lower()
    return (
        explore_phase == "awaiting_clarification"
        and explore_stage == QUASI_TERMINAL_CLARIFY_STAGE
        and QUASI_TERMINAL_CLARIFY_MESSAGE_TOKEN in explore_message
        and progress_text in {"1/1", "1"}
    )


def build_job_terminalization_payload(
    job_id: str,
    status_payload: Mapping[str, Any] | None,
    *,
    now: float | None = None,
    stale_after_seconds: int = 900,
    observed_stable_for_seconds: int | None = None,
    observed_timeout: bool = False,
    verdict_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(status_payload or {})
    verdict = dict(verdict_payload or {})
    status = str(payload.get("status") or "").strip().lower()
    explore_phase = str(payload.get("explore_phase") or "").strip().lower()
    explore_stage = str(payload.get("explore_stage") or "").strip().lower()
    explore_message = str(payload.get("explore_message") or "").strip()
    progress_text = status_progress_text(payload)
    updated_at = _safe_float(payload.get("updated_at"), 0.0)
    terminal = False
    terminalization_kind = ""
    reason_code = "not_terminal"
    reason_message = "Job has not reached a terminalized state yet."

    if bool(observed_timeout):
        terminal = True
        terminalization_kind = "timeout"
        reason_code = "runner_observed_nonterminal_timeout"
        reason_message = "Runner observed a non-terminal timeout while polling job status."
    elif observed_stable_for_seconds is not None and is_quasi_terminal_clarify_signature(payload):
        terminal = True
        terminalization_kind = "quasi_terminal_stall"
        reason_code = "awaiting_clarification_stable_without_authoritative_close"
        reason_message = "Clarification-shaped state remained stable without authoritative finalization."
    elif has_job_lifecycle_inconsistency(payload):
        terminal = True
        terminalization_kind = "api_contract_failed"
        reason_code = "job_lifecycle_inconsistency"
        reason_message = "Job status record contains an inconsistent terminal lifecycle shape."
    elif status == "error":
        terminal = True
        terminalization_kind = "error"
        reason_code = "job_status_error"
        reason_message = str(payload.get("error") or "").strip() or "Job ended with status=error."
    elif payload.get("explore_cancel_requested") and status in {"done", "error", "cancelled", "canceled"}:
        terminal = True
        terminalization_kind = "cancelled"
        reason_code = "cancel_requested_terminal"
        reason_message = "Job was terminalized after cancellation was requested."
    elif explore_phase == "awaiting_clarification":
        macro_status = str((verdict or payload.get("macro_verdict") or {}).get("status") or "").strip().lower()
        if status in {"done", "awaiting_clarification"} or macro_status in {"done", "awaiting_clarification"}:
            terminal = True
            terminalization_kind = "awaiting_clarification_authoritative"
            reason_code = "awaiting_clarification_closed_by_pipeline"
            reason_message = "Pipeline closed in awaiting_clarification with an explicit terminal verdict."
    elif is_terminal_job_record(payload):
        terminal = True
        terminalization_kind = "done"
        reason_code = "job_completed_done"
        reason_message = "Job reached a completed terminal state."
    elif is_stale_nonterminal_job_record(payload, now=now, stale_after_seconds=stale_after_seconds):
        terminal = True
        terminalization_kind = "timeout"
        reason_code = "stale_nonterminal_job_record"
        reason_message = "Job remained non-terminal beyond the allowed stale window."

    return {
        "job_id": str(job_id or "").strip(),
        "terminal": bool(terminal),
        "terminalization_kind": terminalization_kind,
        "ended_at": _utc_iso_from_timestamp(updated_at) if terminal and updated_at > 0 else None,
        "final_stage": {
            "name": "explore" if explore_phase else "analyze",
            "substage": explore_stage,
        },
        "reason": {
            "code": reason_code,
            "message": reason_message,
        },
        "evidence": {
            "status": status,
            "explore_phase": explore_phase,
            "explore_stage": explore_stage,
            "explore_message": explore_message,
            "progress": progress_text,
            "updated_at": updated_at if updated_at > 0 else None,
            "observed_stable_for_seconds": observed_stable_for_seconds,
            "observed_timeout": bool(observed_timeout),
        },
    }
