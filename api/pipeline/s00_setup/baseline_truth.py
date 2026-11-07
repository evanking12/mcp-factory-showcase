"""S-00 owned calibration and baseline-truth seam."""

from __future__ import annotations

import json
import logging
from typing import Any

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _get_job_status, _upload_to_blob
from api.pipeline.core.helpers import _set_explore_status
from api.pipeline.s00_setup.calibration import _calibrate_sentinels

logger = logging.getLogger("mcp_factory.api")


def run_baseline_truth(ctx: Any) -> None:
    """Run the current sentinel calibration behavior through an owned seam."""
    try:
        logger.info("[%s] phase0.5: calibrating sentinels...", ctx.job_id)
        _set_explore_status(ctx.job_id, 0, ctx.total, "Calibrating error codes...")

        hints = ""
        try:
            hints = str((_get_job_status(ctx.job_id) or {}).get("hints") or "")
        except Exception:
            pass

        prev_sentinel_count = len(ctx.sentinels)
        ctx.sentinels = _calibrate_sentinels(
            ctx.invocables,
            ctx.client,
            ctx.model,
            job_id=ctx.job_id,
            hints=hints,
        )
        ctx.sentinel_new_codes_this_run += max(0, len(ctx.sentinels) - prev_sentinel_count)
        logger.info(
            "[%s] phase0.5: sentinels: %s",
            ctx.job_id,
            {f"0x{k:08X}": v for k, v in ctx.sentinels.items()},
        )
        try:
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{ctx.job_id}/sentinel_calibration.json",
                json.dumps(
                    {f"0x{k:08X}": v for k, v in ctx.sentinels.items()},
                    indent=2,
                ).encode(),
            )
        except Exception as exc:
            logger.debug(
                "[%s] phase0.5: sentinel artifact upload failed: %s",
                ctx.job_id,
                exc,
            )
    except Exception as exc:
        logger.debug("[%s] phase0.5: failed, using defaults: %s", ctx.job_id, exc)
