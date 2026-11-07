"""Runtime-visible status helpers for current S-00 internal seams."""

from __future__ import annotations

import time
from typing import Any

from api.infra.storage import _get_job_status, _persist_job_status
from api.pipeline.core.helpers import _set_explore_status

PARENT_STAGE_ID = "s00_setup"

S00_SUBSTAGES: dict[str, dict[str, str]] = {
    "s00_setup_baseline": {
        "display_label": "S-00A setup_baseline",
        "short_name": "setup_baseline",
    },
    "s00_static_evidence": {
        "display_label": "S-00B static_evidence",
        "short_name": "static_evidence",
    },
    "s00_admission_handoff": {
        "display_label": "S-00C admission_handoff",
        "short_name": "admission_handoff",
    },
}


def emit_s00_substage_status(
    ctx: Any,
    substage_id: str,
    message: str,
    *,
    state: str,
) -> None:
    """Expose an S-00 internal seam without changing the runner stage count."""
    if substage_id not in S00_SUBSTAGES:
        return
    job_id = str(getattr(ctx, "job_id", "") or "").strip()
    if not job_id:
        return

    total = int(getattr(ctx, "total", 0) or 0)
    metadata = S00_SUBSTAGES[substage_id]
    now = time.time()
    _set_explore_status(job_id, 0, total, message, stage=substage_id)
    current = _get_job_status(job_id) or {}
    substage_status = dict(current.get("s00_substage_status") or {})
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
            "s00_substage_status": substage_status,
            "updated_at": now,
        },
    )

