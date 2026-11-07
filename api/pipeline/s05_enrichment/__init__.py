"""S-05: Schema Backfill + Verification + MC-5 Read-to-Write Chaining."""

from api.pipeline.s05_enrichment.backfill import _run_phase_7_backfill  # noqa: F401
from api.pipeline.s05_enrichment.verify import _run_phase_7b_verify_enrichment  # noqa: F401
from api.pipeline.s05_enrichment.mc5_chain_reads import _mc5_post_verification  # noqa: F401
from api.pipeline.s05_enrichment.schema_backfill import run_schema_backfill
from api.pipeline.s05_enrichment.verification_replay import run_verification_replay
from api.pipeline.s05_enrichment.read_to_write_chaining import run_read_to_write_chaining
# Runtime-owned metadata modules for stage contracts/capture surfaces.
from api.pipeline.s05_enrichment import checkpoint_hooks as _checkpoint_hooks  # noqa: F401
from api.pipeline.s05_enrichment import context as _stage_context  # noqa: F401
from api.pipeline.s05_enrichment import session_artifacts as _session_artifacts  # noqa: F401


def run_s05(ctx, report: str) -> None:
    """S-05 entry point: backfill, verify, MC-5."""
    run_schema_backfill(ctx, report)
    run_verification_replay(ctx)
    run_read_to_write_chaining(ctx)
