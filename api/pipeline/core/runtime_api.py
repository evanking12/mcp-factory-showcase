"""Public runtime helper interface for pipeline orchestration."""

from __future__ import annotations

from typing import Any

from api.pipeline.core.helpers import (
    _build_tool_schemas,
    _cancel_requested,
    _normalize_tool_schema_invocables,
    _save_stage_context,
    _set_explore_status,
    _snapshot_schema_stage,
    has_job_lifecycle_inconsistency as _has_job_lifecycle_inconsistency,
    is_stale_cancel_requested_job_record as _is_stale_cancel_requested_job_record,
    is_stale_nonterminal_job_record as _is_stale_nonterminal_job_record,
    is_terminal_explore_phase as _is_terminal_explore_phase,
    is_terminal_job_record as _is_terminal_job_record,
    is_terminal_job_status as _is_terminal_job_status,
)


def build_tool_schemas(invocables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _build_tool_schemas(invocables)


def normalize_tool_schema_invocables(invocables: list[dict[str, Any]]) -> None:
    _normalize_tool_schema_invocables(invocables)


def cancel_requested(job_id: str) -> bool:
    return _cancel_requested(job_id)


def set_explore_status(job_id: str, explored: int, total: int, message: str, stage: str | None = None) -> None:
    _set_explore_status(job_id, explored, total, message, stage=stage)


def snapshot_schema_stage(job_id: str, filename: str) -> None:
    _snapshot_schema_stage(job_id, filename)


def save_stage_context(job_id: str, blob_name: str, content: str) -> None:
    _save_stage_context(job_id, blob_name, content)


def is_terminal_job_status(status: Any) -> bool:
    return _is_terminal_job_status(status)


def is_terminal_explore_phase(phase: Any) -> bool:
    return _is_terminal_explore_phase(phase)


def is_terminal_job_record(status_payload: dict[str, Any] | None) -> bool:
    return _is_terminal_job_record(status_payload)


def has_job_lifecycle_inconsistency(status_payload: dict[str, Any] | None) -> bool:
    return _has_job_lifecycle_inconsistency(status_payload)


def is_stale_cancel_requested_job_record(
    status_payload: dict[str, Any] | None,
    *,
    now: float | None = None,
    stale_after_seconds: float | None = None,
) -> bool:
    kwargs: dict[str, Any] = {"now": now}
    if stale_after_seconds is not None:
        kwargs["stale_after_seconds"] = stale_after_seconds
    return _is_stale_cancel_requested_job_record(status_payload, **kwargs)


def is_stale_nonterminal_job_record(
    status_payload: dict[str, Any] | None,
    *,
    now: float | None = None,
    stale_after_seconds: float | None = None,
) -> bool:
    kwargs: dict[str, Any] = {"now": now}
    if stale_after_seconds is not None:
        kwargs["stale_after_seconds"] = stale_after_seconds
    return _is_stale_nonterminal_job_record(status_payload, **kwargs)
