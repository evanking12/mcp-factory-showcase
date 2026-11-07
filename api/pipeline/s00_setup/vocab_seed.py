"""api.pipeline.s00_setup.vocab_seed -- Phase 0a: seed vocabulary table."""

from __future__ import annotations

import json
import logging
import re as _re

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import (
    _get_job_status, _upload_to_blob, _download_blob,
)
from api.pipeline.core.helpers import _SENTINEL_DEFAULTS
from api.pipeline.s00_setup.calibration import _parse_hint_error_codes

logger = logging.getLogger("mcp_factory.api")


def _run_phase_0_vocab_seed(ctx) -> None:
    """Load cross-session vocab from blob, then seed from user hints and calibrated sentinels.

    READS:  ctx.job_id, ctx.sentinels
    WRITES: ctx.vocab, ctx.use_cases_text
    """
    try:
        _vraw = _download_blob(ARTIFACT_CONTAINER, f"{ctx.job_id}/vocab.json")
        ctx.vocab = json.loads(_vraw)
        logger.info("[%s] phase0a: reloaded vocab from blob (%d keys)",
                    ctx.job_id, len(ctx.vocab))
    except Exception:
        pass

    if ctx.sentinels is not _SENTINEL_DEFAULTS:
        ctx.vocab.setdefault("error_codes", {})
        ctx.vocab["error_codes"].update({f"0x{k:08X}": v for k, v in ctx.sentinels.items()})

    try:
        _job_meta = _get_job_status(ctx.job_id) or {}
        _user_hints = (_job_meta.get("hints") or "").strip()
        ctx.use_cases_text = (_job_meta.get("use_cases") or "").strip()

        if _user_hints:
            _hint_ids = list(dict.fromkeys(_re.findall(r'[A-Z]{2,6}-[\w-]+', _user_hints)))
            if _hint_ids:
                ctx.vocab["id_formats"] = _hint_ids
            _clean_hints = " | ".join(
                p.strip() for p in _user_hints.split(" | ")
                if p.strip() and not p.strip().startswith("DOMAIN ANSWER")
            )
            if _clean_hints and "notes" not in ctx.vocab:
                ctx.vocab["notes"] = f"User description: {_clean_hints}"
            logger.info("[%s] phase0a: seeded vocab from user hints: %s",
                        ctx.job_id, _user_hints[:80])

            _hint_codes = _parse_hint_error_codes(_user_hints)
            if _hint_codes:
                ctx.sentinels.update(_hint_codes)
                ctx.vocab.setdefault("error_codes", {})
                ctx.vocab["error_codes"].update(
                    {f"0x{k:08X}": v for k, v in _hint_codes.items()}
                )
                logger.info("[%s] phase0a: merged %d error codes from hints: %s",
                            ctx.job_id, len(_hint_codes),
                            {f"0x{k:08X}": v for k, v in _hint_codes.items()})
                try:
                    _upload_to_blob(
                        ARTIFACT_CONTAINER,
                        f"{ctx.job_id}/sentinel_calibration.json",
                        json.dumps(
                            {f"0x{k:08X}": v for k, v in ctx.sentinels.items()}, indent=2
                        ).encode(),
                    )
                except Exception:
                    pass

        if ctx.use_cases_text and "user_context" not in ctx.vocab:
            ctx.vocab["user_context"] = ctx.use_cases_text
            logger.info("[%s] phase0a: seeded vocab[user_context] from use_cases", ctx.job_id)
    except Exception as _he:
        logger.debug("[%s] phase0a: hints seed failed: %s", ctx.job_id, _he)

    # Persist the pre-probe vocab contract surface even if later stages fail.
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/vocab.json",
            json.dumps(ctx.vocab, indent=2).encode(),
        )
    except Exception as exc:
        logger.debug("[%s] phase0a: vocab artifact upload failed: %s", ctx.job_id, exc)
