"""S-05A owned schema-backfill boundary."""

from __future__ import annotations

from typing import Any

from api.pipeline.s05_enrichment.backfill import _run_phase_7_backfill
from api.pipeline.s05_enrichment.status import emit_s05_stage_status


def run_schema_backfill(ctx: Any, report: str) -> None:
    """Backfill schema descriptions from synthesis without claiming proof."""
    emit_s05_stage_status(
        ctx,
        "s05_schema_backfill",
        "S-05A: Backfilling schema from synthesis...",
        state="start",
    )
    try:
        _run_phase_7_backfill(ctx, report)
    except Exception:
        emit_s05_stage_status(
            ctx,
            "s05_schema_backfill",
            "S-05A: Schema backfill failed.",
            state="fail",
        )
        raise
    emit_s05_stage_status(
        ctx,
        "s05_schema_backfill",
        "S-05A: Schema backfill complete.",
        state="done",
    )
