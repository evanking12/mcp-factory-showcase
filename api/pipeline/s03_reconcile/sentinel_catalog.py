"""api.pipeline.s03_reconcile.sentinel_catalog -- Phase 5: sentinel catalog persist."""

from __future__ import annotations

import json
import logging

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _upload_to_blob

logger = logging.getLogger("mcp_factory.api")


def _run_phase_5_sentinel_catalog(ctx) -> None:
    """Persist the sentinel evidence catalog and promote confident codes to vocab."""
    try:
        _promoted = 0
        ctx.vocab.setdefault("error_codes", {})
        for _hex, _row in ctx.sentinel_catalog.items():
            _conf = float(_row.get("confidence") or 0.0)
            _evi = int(_row.get("evidence_count") or 0)
            _src = str(_row.get("source") or "")
            _meaning = str(_row.get("meaning") or "unknown")
            _strong_det = _src.startswith("deterministic.") and _conf >= 0.95
            _stable = _conf >= 0.85 and _evi >= 2
            if (_strong_det or _stable) and _meaning and _meaning != "unknown":
                ctx.vocab["error_codes"].setdefault(_hex, _meaning)
                _row["provisional"] = False
                _row["promotion_reason"] = (
                    "deterministic_single" if _strong_det else "repeated_evidence"
                )
                _promoted += 1

        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/sentinel_catalog.json",
            json.dumps({
                "codes": ctx.sentinel_catalog,
                "promoted_count": _promoted,
                "total_counts": len(ctx.sentinel_catalog),
            }, indent=2).encode(),
        )
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/vocab.json",
            json.dumps(ctx.vocab).encode(),
        )
        logger.info("[%s] phase5: sentinel_catalog persisted (%d codes, %d promoted)",
                    ctx.job_id, len(ctx.sentinel_catalog), _promoted)
    except Exception as _sce:
        logger.debug("[%s] phase5: sentinel_catalog persist failed: %s", ctx.job_id, _sce)
