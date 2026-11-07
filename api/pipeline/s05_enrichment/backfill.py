"""api.pipeline.s05_enrichment.backfill -- Phase 7: schema backfill from synthesis."""

from __future__ import annotations

import json
import logging
from typing import Any

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _upload_to_blob
from api.pipeline.core.helpers import _set_explore_status, _snapshot_schema_stage
from api.pipeline.core.vocab import _backfill_schema_from_synthesis

logger = logging.getLogger("mcp_factory.api")


def _build_schema_backfill_provenance(
    report: str,
    invocables: list[dict[str, Any]],
    backfill_stats: dict[str, Any],
) -> dict[str, Any]:
    """Record S-05A provenance without presenting schema enrichment as proof."""
    patched_functions = [
        str(name)
        for name in (backfill_stats.get("patched_functions") or [])
        if str(name or "").strip()
    ]
    patched = set(patched_functions)
    report_text = str(report or "")
    rows: list[dict[str, Any]] = []
    for inv in invocables or []:
        fn_name = str((inv or {}).get("name") or "").strip()
        if not fn_name:
            continue
        rows.append(
            {
                "function": fn_name,
                "patch_applied": fn_name in patched,
                "source": "s04_synthesis_report" if fn_name in report_text else "schema_only",
                "proof_boundary": "schema_enrichment_not_verification",
                "verification": "not_verified_by_s05a",
            }
        )
    return {
        "stage_id": "s05_schema_backfill",
        "source_stage": "s04_synthesis",
        "proof_boundary": "schema_enrichment_not_verification",
        "patches_requested": int(backfill_stats.get("patches_requested") or 0),
        "patches_applied": int(backfill_stats.get("patches_applied") or 0),
        "patched_functions": patched_functions,
        "function_count": len(rows),
        "rows": rows,
    }


def _run_phase_7_backfill(ctx, report: str) -> None:
    """Backfill schema descriptions from the synthesis document."""
    _backfill_stats: dict[str, Any] = {
        "patches_requested": 0,
        "patches_applied": 0,
        "patched_functions": [],
    }
    try:
        logger.info("[%s] phase7: layer3 schema backfill...", ctx.job_id)
        _set_explore_status(ctx.job_id, ctx.explored_count(), ctx.total,
                            "Enriching schema from synthesis...")
        _backfill_stats = _backfill_schema_from_synthesis(
            ctx.client, ctx.model, report, ctx.invocables, ctx.job_id
        )
    except Exception as _bf_e:
        logger.debug("[%s] phase7: backfill failed: %s", ctx.job_id, _bf_e)
        _backfill_stats["error"] = str(_bf_e)

    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/backfill_result.json",
            json.dumps(
                {
                    "backfill_ran": True,
                    "patches_requested": int(_backfill_stats.get("patches_requested") or 0),
                    "patches_applied": int(_backfill_stats.get("patches_applied") or 0),
                    "patched_functions": _backfill_stats.get("patched_functions") or [],
                    "error": _backfill_stats.get("error"),
                    "provenance": _build_schema_backfill_provenance(
                        report,
                        list(getattr(ctx, "invocables", []) or []),
                        _backfill_stats,
                    ),
                },
                indent=2,
            ).encode("utf-8"),
        )
    except Exception as _bf_emit_e:
        logger.debug("[%s] phase7: backfill_result emit failed: %s", ctx.job_id, _bf_emit_e)

    _snapshot_schema_stage(ctx.job_id, "mcp_schema_post_discovery.json")
    _snapshot_schema_stage(ctx.job_id, "mcp_schema_pre_gap_resolution.json")
