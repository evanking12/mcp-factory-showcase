"""S-06: Gap Resolution + MC-6 Final Comprehensive Unlock."""

from __future__ import annotations

import json
import logging

from api.infra.storage import (
    _load_findings, _persist_job_status, _get_job_status,
)
from api.pipeline.core.helpers import (
    _set_explore_status, _snapshot_schema_stage, _save_stage_context,
    _cancel_requested,
)
from api.pipeline.core.prompts import (
    _build_explore_system_message, _generate_confidence_gaps,
)
from api.analysis.cohesion import emit_contract_artifacts

from api.pipeline.s06_gaps.gap_resolution import (  # noqa: F401
    _attempt_gap_resolution,
    _run_gap_answer_mini_sessions,
)
from api.pipeline.s06_gaps.mc6_final_unlock import _mc6_post_gap_resolution  # noqa: F401
# Runtime-owned metadata modules for stage contracts/capture surfaces.
from api.pipeline.s06_gaps import checkpoint_hooks as _checkpoint_hooks  # noqa: F401
from api.pipeline.s06_gaps import context as _stage_context  # noqa: F401
from api.pipeline.s06_gaps import session_artifacts as _session_artifacts  # noqa: F401

logger = logging.getLogger("mcp_factory.api")


def run_s06(ctx) -> None:
    """S-06 entry point: gap resolution + MC-6 + clarification questions."""
    if not ctx.runtime.gap_resolution_enabled:
        logger.info("[%s] phase8: gap resolution disabled for this run", ctx.job_id)
        _persist_job_status(
            ctx.job_id,
            {**(_get_job_status(ctx.job_id) or {}), "explore_questions": []},
            sync=True,
        )
        return

    # Save gap-resolution model context
    try:
        _gap_findings = _load_findings(ctx.job_id)
        _failed = [f for f in _gap_findings if f.get("status") != "success"]
        _succeeded = [f for f in _gap_findings if f.get("status") == "success"]
        _gap_sys = _build_explore_system_message(
            ctx.invocables, _gap_findings,
            sentinels=ctx.sentinels, vocab=ctx.vocab, use_cases=ctx.use_cases_text,
        )
        _gap_ctx_lines = [
            "=== GAP RESOLUTION PHASE MODEL CONTEXT ===",
            f"Functions total: {len(ctx.invocables)} | succeeded: {len(_succeeded)} | failed: {len(_failed)}",
            "",
            "--- Failed functions to retry ---",
        ]
        for _f in _failed:
            _gap_ctx_lines.append(
                f"  {_f.get('function','?')}: {_f.get('status','?')} | "
                f"finding={str(_f.get('finding',''))[:80]}"
            )
        _gap_ctx_lines.append("")
        _gap_ctx_lines.append("--- Known-good calls ---")
        for _f in _succeeded[:6]:
            _gap_ctx_lines.append(
                f"  {_f.get('function','?')}: working_call={_f.get('working_call')}"
            )
        _gap_ctx_lines.append("")
        _gap_ctx_lines.append("--- System prompt ---")
        _gap_ctx_lines.append(_gap_sys.get("content", ""))
        _save_stage_context(ctx.job_id, "model_context_phase_08_gap_resolution.txt",
                            "\n".join(_gap_ctx_lines))
    except Exception as _mce:
        logger.debug("[%s] phase8: model context save failed: %s", ctx.job_id, _mce)

    # Gap resolution
    try:
        logger.info("[%s] phase8: gap resolution pass...", ctx.job_id)
        _set_explore_status(ctx.job_id, ctx.explored_count(), ctx.total,
                            "Retrying failed functions...")
        _attempt_gap_resolution(
            ctx.job_id, ctx.invocables, ctx.client, ctx.model,
            ctx.sentinels, ctx.vocab, ctx.use_cases_text,
            ctx.inv_map, ctx.tool_schemas,
            ctx=ctx,
        )
    except Exception as _gr_e:
        logger.debug("[%s] phase8: gap resolution failed: %s", ctx.job_id, _gr_e)

    _snapshot_schema_stage(ctx.job_id, "mcp_schema_post_gap_resolution.json")
    _snapshot_schema_stage(ctx.job_id, "mcp_schema_pre_clarification.json")

    # MC-6
    _mc6_post_gap_resolution(ctx)

    # Clarification questions
    if ctx.runtime.clarification_enabled:
        try:
            logger.info("[%s] phase8: generating confidence gaps...", ctx.job_id)
            _set_explore_status(ctx.job_id, ctx.explored_count(), ctx.total,
                                "Generating clarification questions...")
            _syn_findings = _load_findings(ctx.job_id)
            _gaps = _generate_confidence_gaps(
                ctx.client, ctx.model, _syn_findings, ctx.invocables
            )
            if _gaps:
                logger.info("[%s] phase8: %d confidence gaps generated", ctx.job_id, len(_gaps))
            _gap_current = _get_job_status(ctx.job_id) or {}
            _persist_job_status(
                ctx.job_id, {**_gap_current, "explore_questions": _gaps}, sync=True
            )
        except Exception as _gap_e:
            logger.debug("[%s] phase8: confidence gaps failed: %s", ctx.job_id, _gap_e)
    else:
        _gap_current = _get_job_status(ctx.job_id) or {}
        _persist_job_status(
            ctx.job_id, {**_gap_current, "explore_questions": []}, sync=True
        )

    _snapshot_schema_stage(ctx.job_id, "mcp_schema_post_clarification.json")
