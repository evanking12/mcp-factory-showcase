"""S-00 owned admission handoff boundary for S-01."""

from __future__ import annotations

from typing import Any

from api.pipeline.core.s00_s01_handoff import build_s00_s01_handoff_packet
from api.pipeline.s00_setup.status import emit_s00_substage_status


def run_admission_handoff(ctx: Any) -> dict[str, Any] | None:
    """Build the S-01 handoff packet without changing the shared packet contract."""
    emit_s00_substage_status(
        ctx,
        "s00_admission_handoff",
        "S-00C: Building S-01 admission handoff...",
        state="start",
    )
    try:
        packet = build_s00_s01_handoff_packet(ctx)
    except Exception:
        emit_s00_substage_status(
            ctx,
            "s00_admission_handoff",
            "S-00C: Admission handoff failed.",
            state="fail",
        )
        raise
    emit_s00_substage_status(
        ctx,
        "s00_admission_handoff",
        "S-00C: Admission handoff complete.",
        state="done",
    )
    return packet
