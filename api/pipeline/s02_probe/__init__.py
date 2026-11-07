"""S-02: Probe ordering, invocation execution, and evidence capture."""

from __future__ import annotations

from api.pipeline.s02_probe.probe_loop import (  # noqa: F401
    _explore_one,
    _run_phase_3_probe_loop,
)
from api.pipeline.s02_probe.curriculum import (  # noqa: F401
    _run_phase_2_curriculum_order,
)
from api.pipeline.s02_probe.evidence_capture import run_evidence_capture
from api.pipeline.s02_probe.invocation_execution import run_invocation_execution
from api.pipeline.s02_probe.probe_ordering import run_probe_ordering
# Runtime-owned metadata modules for stage contracts/capture surfaces.
from api.pipeline.s02_probe import checkpoint_hooks as _checkpoint_hooks  # noqa: F401
from api.pipeline.s02_probe import context as _stage_context  # noqa: F401
from api.pipeline.s02_probe import session_artifacts as _session_artifacts  # noqa: F401


def run_s02(ctx) -> None:
    """Legacy S-02 compatibility entry point."""
    run_probe_ordering(ctx)
    run_invocation_execution(ctx)
    run_evidence_capture(ctx)
