"""S-04: API Reference Synthesis + MC-4 Init Sequence Clues."""

from api.pipeline.s04_synthesis.synthesize import _run_phase_6_synthesize  # noqa: F401
from api.pipeline.s04_synthesis.mc4_init_clues import _mc4_post_synthesis  # noqa: F401
# Runtime-owned metadata modules for stage contracts/capture surfaces.
from api.pipeline.s04_synthesis import checkpoint_hooks as _checkpoint_hooks  # noqa: F401
from api.pipeline.s04_synthesis import context as _stage_context  # noqa: F401
from api.pipeline.s04_synthesis import session_artifacts as _session_artifacts  # noqa: F401


def run_s04(ctx) -> str | None:
    """S-04 entry point: synthesis + MC-4. Returns the synthesis report string."""
    report = _run_phase_6_synthesize(ctx)
    _mc4_post_synthesis(ctx)
    return report
