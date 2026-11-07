"""S-02C owned evidence-capture and boundary recalibration."""

from __future__ import annotations

import concurrent.futures as _cf
import json
import logging
import re as _re
from typing import Any

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import (
    _append_explore_probe_log,
    _download_blob,
    _get_job_status,
    _persist_job_status,
    _upload_to_blob,
)
from api.pipeline.s00_setup.calibration import _name_sentinel_candidates
from api.pipeline.s01_unlock.write_unlock import _probe_write_unlock
from api.pipeline.s02_probe.status import emit_s02_substage_status

logger = logging.getLogger("mcp_factory.api")

S02C_PROBE_LOG_ALIAS = "evidence/stage-02c-evidence-capture/probe-log.json"
S02C_FINDING_STATUS_ALIAS = "evidence/stage-02c-evidence-capture/finding-status.json"


def run_evidence_capture(ctx: Any) -> None:
    """Persist boundary evidence and recalibrate sentinels after probing."""
    emit_s02_substage_status(
        ctx,
        "s02_evidence_capture",
        "S-02C: Capturing probe evidence...",
        state="start",
    )
    try:
        _persist_probe_log_snapshot(ctx)
        _run_stage_boundary_recalibration(ctx)
    except Exception:
        emit_s02_substage_status(
            ctx,
            "s02_evidence_capture",
            "S-02C: Evidence capture failed.",
            state="fail",
        )
        raise
    emit_s02_substage_status(
        ctx,
        "s02_evidence_capture",
        "S-02C: Evidence capture complete.",
        state="done",
    )


def _load_legacy_probe_entries(ctx: Any) -> list[Any]:
    try:
        probe_log_bytes = _download_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/explore_probe_log.json",
        )
    except Exception:
        return []
    try:
        decoded = probe_log_bytes.decode("utf-8", errors="replace")
        probe_entries = json.loads(decoded) if decoded else []
    except Exception:
        return []
    return probe_entries if isinstance(probe_entries, list) else []


def _persist_probe_log_snapshot(ctx: Any) -> None:
    """Write the S-02C-owned probe-log alias without changing legacy storage."""
    entries = _load_legacy_probe_entries(ctx)
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/{S02C_PROBE_LOG_ALIAS}",
            json.dumps(entries, indent=2, default=str).encode("utf-8"),
        )
    except Exception as exc:
        logger.debug("[%s] S-02C probe-log snapshot failed: %s", ctx.job_id, exc)
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/{S02C_FINDING_STATUS_ALIAS}",
            json.dumps(_build_finding_status_snapshot(entries), indent=2, default=str).encode(
                "utf-8"
            ),
        )
    except Exception as exc:
        logger.debug("[%s] S-02C finding-status snapshot failed: %s", ctx.job_id, exc)


def _build_finding_status_snapshot(entries: list[Any]) -> list[dict[str, Any]]:
    """Preserve status boundaries without asking S-02C to interpret semantics."""
    snapshot: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        classification = entry.get("classification")
        classification_obj = classification if isinstance(classification, dict) else {}
        status = classification_obj.get("status") or entry.get("status") or "unresolved"
        boundary = classification_obj.get("boundary") or entry.get("boundary") or "unknown"
        snapshot.append(
            {
                "index": index,
                "function": entry.get("function") or "",
                "tool": entry.get("tool") or entry.get("function") or "",
                "status": status,
                "boundary": boundary,
                "classification": classification_obj,
                "args": entry.get("args") if isinstance(entry.get("args"), dict) else {},
                "result_excerpt": entry.get("result_excerpt") or "",
                "phase": entry.get("phase") or "",
                "trace": entry.get("trace") if isinstance(entry.get("trace"), dict) else None,
            }
        )
    return snapshot


def _run_stage_boundary_recalibration(ctx: Any) -> None:
    try:
        probe_entries = _load_legacy_probe_entries(ctx)
        if not probe_entries:
            return

        new_sentinel_candidates: dict[int, list[str]] = {}
        for entry in probe_entries:
            return_match = _re.match(
                r"Returned:\s*(\d+)",
                str(entry.get("result_excerpt") or ""),
            )
            if return_match:
                return_val = int(return_match.group(1)) & 0xFFFFFFFF
                if return_val > 0x80000000 and return_val not in ctx.sentinels:
                    new_sentinel_candidates.setdefault(return_val, []).append(
                        str(entry.get("function") or "")
                    )
        if not new_sentinel_candidates:
            return

        boundary_resolved = _name_sentinel_candidates(
            new_sentinel_candidates,
            ctx.client,
            ctx.model,
        )
        if not boundary_resolved:
            return

        ctx.sentinels.update(boundary_resolved)
        ctx.sentinel_new_codes_this_run += len(boundary_resolved)
        logger.info(
            "[%s] stage-boundary recal: %d new codes: %s",
            ctx.job_id,
            len(boundary_resolved),
            {f"0x{k:08X}": v for k, v in boundary_resolved.items()},
        )
        try:
            _append_explore_probe_log(
                ctx.job_id,
                [
                    {
                        "phase": "stage_boundary_name_sentinel_candidates",
                        "function": "(all)",
                        "args": {
                            "candidate_codes": [
                                f"0x{v:08X}"
                                for v in sorted(new_sentinel_candidates.keys(), reverse=True)
                            ],
                            "candidate_count": len(new_sentinel_candidates),
                        },
                        "result_excerpt": json.dumps(
                            {f"0x{k:08X}": v for k, v in boundary_resolved.items()}
                        )[:400],
                        "trace": None,
                    }
                ],
            )
        except Exception as exc:
            logger.debug("[%s] stage-boundary recal log flush failed: %s", ctx.job_id, exc)

        if not ctx.unlock_result.get("unlocked"):
            logger.info(
                "[%s] stage-boundary: re-probing write-unlock with %d new sentinel codes",
                ctx.job_id,
                len(boundary_resolved),
            )
            with _cf.ThreadPoolExecutor(max_workers=1) as _tp:
                _fut = _tp.submit(
                    _probe_write_unlock,
                    ctx.invocables,
                    ctx.dll_strings,
                    ctx.vocab,
                )
                try:
                    ctx.unlock_result = _fut.result(timeout=120)
                except _cf.TimeoutError:
                    logger.warning(
                        "[%s] stage-boundary: write-unlock re-probe timed out after 120s",
                        ctx.job_id,
                    )
                    _fut.cancel()
            if ctx.unlock_result.get("unlocked"):
                ctx.write_unlock_block = (
                    "\nWRITE MODE ACTIVE (resolved after sentinel recalibration): "
                    "The write-unlock sequence has been executed. Write functions "
                    "should now succeed. Probe with real ID values from "
                    "STATIC ANALYSIS HINTS.\n"
                )
                logger.info(
                    "[%s] stage-boundary: WRITE UNLOCKED after recal: %s",
                    ctx.job_id,
                    ctx.unlock_result.get("notes"),
                )
                try:
                    current_status = _get_job_status(ctx.job_id) or {}
                    _persist_job_status(
                        ctx.job_id,
                        {
                            **current_status,
                            "write_unlock_outcome": "resolved",
                            "write_unlock_sentinel": None,
                        },
                    )
                except Exception as exc:
                    logger.debug(
                        "[%s] stage-boundary unlock status update failed: %s",
                        ctx.job_id,
                        exc,
                    )
    except Exception as exc:
        logger.debug("[%s] stage-boundary recal failed: %s", ctx.job_id, exc)
