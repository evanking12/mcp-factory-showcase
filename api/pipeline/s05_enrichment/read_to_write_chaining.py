"""S-05C owned read-to-write chaining boundary."""

from __future__ import annotations

from typing import Any

from api.pipeline.s05_enrichment.mc5_chain_reads import _mc5_post_verification
from api.pipeline.s05_enrichment.status import emit_s05_stage_status


def run_read_to_write_chaining(ctx: Any) -> None:
    """Use verified read evidence for bounded MC-5 write retry decisions."""
    emit_s05_stage_status(
        ctx,
        "s05_read_to_write_chaining",
        "S-05C: Chaining verified reads into write retries...",
        state="start",
    )
    try:
        _mc5_post_verification(ctx)
    except Exception:
        emit_s05_stage_status(
            ctx,
            "s05_read_to_write_chaining",
            "S-05C: Read-to-write chaining failed.",
            state="fail",
        )
        raise
    emit_s05_stage_status(
        ctx,
        "s05_read_to_write_chaining",
        "S-05C: Read-to-write chaining complete.",
        state="done",
    )
