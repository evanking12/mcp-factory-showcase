"""api.pipeline.s07_finalize.behavioral_spec -- Phase 9: behavioral specification."""

from __future__ import annotations

import logging

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _load_findings, _get_job_status, _upload_to_blob
from api.pipeline.core.helpers import _set_explore_status, _cancel_requested
from api.pipeline.core.prompts import _generate_behavioral_spec

logger = logging.getLogger("mcp_factory.api")


def _run_phase_9_behavioral_spec(ctx, report: str) -> None:
    """Generate a typed Python behavioral specification from findings + synthesis."""
    if _cancel_requested(ctx.job_id):
        return

    try:
        logger.info("[%s] phase9: generating behavioral spec...", ctx.job_id)
        _set_explore_status(ctx.job_id, ctx.explored_count(), ctx.total,
                            "Generating behavioral specification...")
        _component = (_get_job_status(ctx.job_id) or {}).get("component_name", "DLLComponent")
        _spec_py = _generate_behavioral_spec(
            ctx.client, ctx.model, _load_findings(ctx.job_id),
            ctx.invocables, _component, report,
        )
        if _spec_py:
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{ctx.job_id}/behavioral_spec.py",
                _spec_py.encode("utf-8"),
            )
            logger.info("[%s] phase9: behavioral_spec.py saved to blob", ctx.job_id)
    except Exception as _spec_e:
        logger.debug("[%s] phase9: behavioral spec failed: %s", ctx.job_id, _spec_e)
