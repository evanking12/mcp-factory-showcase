"""Runtime-visible status helpers for split S-05 enrichment stages."""

from __future__ import annotations

import time
from typing import Any

from api.infra.storage import _get_job_status, _persist_job_status
from api.pipeline.core.helpers import _set_explore_status

PARENT_STAGE_ID = "s05_enrichment"

S05_STAGES: dict[str, dict[str, str]] = {
    "s05_schema_backfill": {
        "display_label": "S-05A schema_backfill",
        "short_name": "schema_backfill",
    },
    "s05_verification_replay": {
        "display_label": "S-05B verification_replay",
        "short_name": "verification_replay",
    },
    "s05_read_to_write_chaining": {
        "display_label": "S-05C read_to_write_chaining",
        "short_name": "read_to_write_chaining",
    },
}


def emit_s05_stage_status(
    ctx: Any,
    stage_id: str,
    message: str,
    *,
    state: str,
) -> None:
    """Expose one S-05 responsibility without removing parent compatibility."""
    if stage_id not in S05_STAGES:
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

    metadata = S05_STAGES[stage_id]
    now = time.time()
    _set_explore_status(job_id, explored, total, message, stage=stage_id)
    current = _get_job_status(job_id) or {}
    stage_status = dict(current.get("s05_stage_status") or {})
    stage_status[stage_id] = {
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
            "explore_substage": stage_id,
            "explore_substage_state": str(state or "").strip(),
            "explore_substage_label": metadata["display_label"],
            "s05_stage_status": stage_status,
            "updated_at": now,
        },
    )
