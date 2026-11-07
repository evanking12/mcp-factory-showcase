"""S-02A owned probe-ordering boundary."""

from __future__ import annotations

from typing import Any

from api.pipeline.s02_probe.curriculum import _run_phase_2_curriculum_order
from api.pipeline.s02_probe.status import emit_s02_substage_status


def run_probe_ordering(ctx: Any) -> None:
    """Order probe work and persist prerequisite-state planning evidence."""
    emit_s02_substage_status(
        ctx,
        "s02_probe_ordering",
        "S-02A: Ordering probe work...",
        state="start",
    )
    try:
        _run_phase_2_curriculum_order(ctx)
    except Exception:
        emit_s02_substage_status(
            ctx,
            "s02_probe_ordering",
            "S-02A: Probe ordering failed.",
            state="fail",
        )
        raise
    emit_s02_substage_status(
        ctx,
        "s02_probe_ordering",
        "S-02A: Probe ordering complete.",
        state="done",
    )
