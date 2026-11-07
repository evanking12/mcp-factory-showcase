"""Runtime-visible status helpers for split S-02 probe substages."""

from __future__ import annotations

import time
from typing import Any

from api.infra.storage import _get_job_status, _persist_job_status
from api.pipeline.core.helpers import _set_explore_status

PARENT_STAGE_ID = "s02_probe"

S02_SUBSTAGES: dict[str, dict[str, str]] = {
    "s02_probe_ordering": {
        "display_label": "S-02A probe_ordering",
        "short_name": "probe_ordering",
    },
    "s02_invocation_execution": {
        "display_label": "S-02B invocation_execution",
        "short_name": "invocation_execution",
    },
    "s02_evidence_capture": {
        "display_label": "S-02C evidence_capture",
        "short_name": "evidence_capture",
    },
}


def emit_s02_substage_status(
    ctx: Any,
    substage_id: str,
    message: str,
    *,
    state: str,
) -> None:
    """Expose one S-02 responsibility without removing parent compatibility."""
    if substage_id not in S02_SUBSTAGES:
        return
    job_id = str(getattr(ctx, "job_id", "") or "").strip()
    if not job_id:
        return

    total = int(getattr(ctx, "total", 0) or 0)
    explored = 0
    getter = getattr(ctx, "explored_count", None)
    if callable(getter):
        try:
            explored = int(getter())
        except Exception:
            explored = 0

    metadata = S02_SUBSTAGES[substage_id]
    now = time.time()
    _set_explore_status(job_id, explored, total, message, stage=substage_id)
    current = _get_job_status(job_id) or {}
    substage_status = dict(current.get("s02_substage_status") or {})
    substage_status[substage_id] = {
        "state": str(state or "").strip(),
        "message": str(message or "").strip(),
        "updated_at": now,
        "parent_stage": PARENT_STAGE_ID,
        "display_label": metadata["display_label"],
        "short_name": metadata["short_name"],
    }
    _persist_job_status(
        job_id,
        {
            **current,
            "explore_parent_stage": PARENT_STAGE_ID,
            "explore_substage": substage_id,
            "explore_substage_state": str(state or "").strip(),
            "explore_substage_label": metadata["display_label"],
            "s02_substage_status": substage_status,
            "updated_at": now,
        },
    )
