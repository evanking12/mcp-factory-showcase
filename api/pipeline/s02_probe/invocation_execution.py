"""S-02B owned invocation-execution boundary."""

from __future__ import annotations

from typing import Any

from api.pipeline.s02_probe.probe_loop import _run_phase_3_probe_loop
from api.pipeline.s02_probe.status import emit_s02_substage_status


def run_invocation_execution(ctx: Any) -> None:
    """Construct probe arguments, execute calls, and collect raw observations."""
    emit_s02_substage_status(
        ctx,
        "s02_invocation_execution",
        "S-02B: Executing probe invocations...",
        state="start",
    )
    try:
        _run_phase_3_probe_loop(ctx)
    except Exception:
        emit_s02_substage_status(
            ctx,
            "s02_invocation_execution",
            "S-02B: Invocation execution failed.",
            state="fail",
        )
        raise
    emit_s02_substage_status(
        ctx,
        "s02_invocation_execution",
        "S-02B: Invocation execution complete.",
        state="done",
    )
