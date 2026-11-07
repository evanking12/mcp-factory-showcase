"""S-00 owned static evidence boundary."""

from __future__ import annotations

from typing import Any

from api.pipeline.s00_setup.status import emit_s00_substage_status
from api.pipeline.s00_setup.static_analysis import _run_phase_0_static
from api.pipeline.s00_setup.static_enrichment import write_static_enrichment


def run_static_evidence(ctx: Any) -> None:
    """Run static extraction and emit the normalized static-enrichment artifact."""
    emit_s00_substage_status(
        ctx,
        "s00_static_evidence",
        "S-00B: Extracting static evidence...",
        state="start",
    )
    try:
        _run_phase_0_static(ctx)
        write_static_enrichment(ctx)
    except Exception:
        emit_s00_substage_status(
            ctx,
            "s00_static_evidence",
            "S-00B: Static evidence failed.",
            state="fail",
        )
        raise
    emit_s00_substage_status(
        ctx,
        "s00_static_evidence",
        "S-00B: Static evidence complete.",
        state="done",
    )
