"""S-03: Post-Probe Reconciliation + MC-3 Write Analysis + Sentinel Catalog."""

from api.pipeline.s03_reconcile.reconcile import _run_phase_4_reconcile  # noqa: F401
from api.pipeline.s03_reconcile.mc3_write_analysis import _mc3_post_reconcile  # noqa: F401
from api.pipeline.s03_reconcile.sentinel_catalog import _run_phase_5_sentinel_catalog  # noqa: F401
# Runtime-owned metadata modules for stage contracts/capture surfaces.
from api.pipeline.s03_reconcile import checkpoint_hooks as _checkpoint_hooks  # noqa: F401
from api.pipeline.s03_reconcile import context as _stage_context  # noqa: F401
from api.pipeline.s03_reconcile import session_artifacts as _session_artifacts  # noqa: F401


def run_s03(ctx) -> None:
    """S-03 entry point: reconcile, MC-3 write analysis, sentinel catalog."""
    _run_phase_4_reconcile(ctx)
    _mc3_post_reconcile(ctx)
    _run_phase_5_sentinel_catalog(ctx)
