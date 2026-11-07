"""S-05B owned verification-replay boundary."""

from __future__ import annotations

from typing import Any

from api.pipeline.s05_enrichment.status import emit_s05_stage_status
from api.pipeline.s05_enrichment.verify import _run_phase_7b_verify_enrichment


def run_verification_replay(ctx: Any) -> None:
    """Replay working calls and preserve verified versus inferred boundaries."""
    emit_s05_stage_status(
        ctx,
        "s05_verification_replay",
        "S-05B: Replaying verification evidence...",
        state="start",
    )
    try:
        _run_phase_7b_verify_enrichment(ctx)
    except Exception:
        emit_s05_stage_status(
            ctx,
            "s05_verification_replay",
            "S-05B: Verification replay failed.",
            state="fail",
        )
        raise
    emit_s05_stage_status(
        ctx,
        "s05_verification_replay",
        "S-05B: Verification replay complete.",
        state="done",
    )
