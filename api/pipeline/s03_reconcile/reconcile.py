"""api.pipeline.s03_reconcile.reconcile -- Phase 4: post-probe reconciliation."""

from __future__ import annotations

import json
import logging
from collections import defaultdict

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _load_findings, _patch_finding, _download_blob
from api.pipeline.core.helpers import _set_explore_status

logger = logging.getLogger("mcp_factory.api")

S02C_PROBE_LOG_ALIAS = "evidence/stage-02c-evidence-capture/probe-log.json"


def _load_reconciliation_probe_log(job_id: str) -> list[dict]:
    """Load S-02C-owned probe evidence, falling back to legacy probe logs."""
    for blob_name in (
        f"{job_id}/{S02C_PROBE_LOG_ALIAS}",
        f"{job_id}/explore_probe_log.json",
    ):
        try:
            raw = _download_blob(ARTIFACT_CONTAINER, blob_name)
            decoded = json.loads(raw)
        except Exception:
            continue
        if not isinstance(decoded, list):
            continue
        return [row for row in decoded if isinstance(row, dict)]
    return []


def _run_phase_4_reconcile(ctx) -> None:
    """Scan probe log for error findings that had a successful direct probe.

    Functions that returned 0 during the probe loop but whose LLM-recorded
    finding ended up as "error" are upgraded to "success" here.
    """
    try:
        _set_explore_status(ctx.job_id, ctx.explored_count(), ctx.total,
                            "Reconciling probe evidence...")
        _recon_findings = _load_findings(ctx.job_id)
        _recon_probe_log = _load_reconciliation_probe_log(ctx.job_id)

        if not _recon_probe_log:
            return

        _success_probes: dict[str, list[dict]] = defaultdict(list)
        for _pe in _recon_probe_log:
            _clf = _pe.get("classification") or {}
            _fn = _pe.get("function") or ""
            _tool = _pe.get("tool") or ""
            _phase = str(_pe.get("phase") or "")
            if not (_fn and _tool and _fn == _tool):
                continue
            if _phase not in {"explore", "cross_validate", "deterministic_fallback"}:
                continue
            if _clf.get("has_return") and int(_clf.get("signed", -1)) == 0:
                _success_probes[_fn].append(_pe)

        _recon_patched = 0
        for _f in _recon_findings:
            _fn = _f.get("function", "")
            if _f.get("status") == "error" and _fn in _success_probes:
                _best_pe = max(_success_probes[_fn], key=lambda _p: len(_p.get("args") or {}))
                _wc = _best_pe.get("args") or {}
                _patch_finding(ctx.job_id, _fn, {
                    "status": "success", "working_call": _wc,
                    "finding": f"Reconciled: {_fn}({_wc}) returned 0 (probe {_best_pe.get('probe_id', '?')})",
                    "stop_reason": "reconciled_from_probe_log",
                    "notes": (
                        f"AC-1 reconciliation: probe "
                        f"{_best_pe.get('probe_id', '?')} returned 0 "
                        "but finding was error. Overridden to success."
                    ),
                })
                _recon_patched += 1

        if _recon_patched:
            logger.info("[%s] phase4: AC-1 reconciliation patched %d functions error->success",
                        ctx.job_id, _recon_patched)
    except Exception as _recon_e:
        logger.debug("[%s] phase4: AC-1 reconciliation failed: %s", ctx.job_id, _recon_e)
