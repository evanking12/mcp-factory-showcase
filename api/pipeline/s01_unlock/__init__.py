"""S-01: Write-Unlock Probe."""

from __future__ import annotations

import concurrent.futures as _cf
import json
import logging
import re as _re

from api.infra.config import ARTIFACT_CONTAINER
from api.services.executor import _execute_tool
from api.infra.storage import (
    _persist_job_status, _get_job_status,
    _upload_to_blob, _patch_finding,
)
from api.pipeline.core.helpers import _set_explore_status
from api.pipeline.core.s00_s01_handoff import admit_s00_s01_handoff

from api.pipeline.s01_unlock.write_unlock import (  # noqa: F401
    _probe_write_unlock,
    _generate_xor_codes,
)
from api.pipeline.s01_unlock.unlock_helpers import (  # noqa: F401
    _mark_unlock_resolved,
    _reprobe_write_functions_after_unlock,
    _build_write_args_from_vocab,
    _targeted_unlock_attempt,
    _WRITE_FN_PATTERN,
)
# Runtime-owned metadata modules for stage contracts/capture surfaces.
from api.pipeline.s01_unlock import checkpoint_hooks as _checkpoint_hooks  # noqa: F401
from api.pipeline.s01_unlock import context as _stage_context  # noqa: F401
from api.pipeline.s01_unlock import session_artifacts as _session_artifacts  # noqa: F401

logger = logging.getLogger("mcp_factory.api")

_S01_TIMEOUT_SEC = 300


def _prioritize_invocables_for_s01_targets(invocables, s01_targets):
    """Move admitted S-01 targets to the front without dropping legacy candidates."""
    target_names = []
    for key in ("init_candidates", "write_candidates"):
        for name in (s01_targets or {}).get(key) or []:
            clean = str(name or "").strip()
            if clean and clean not in target_names:
                target_names.append(clean)
    if not target_names:
        return list(invocables or [])

    by_name = {}
    for inv in invocables or []:
        name = str((inv or {}).get("name") or "").strip()
        if name and name not in by_name:
            by_name[name] = inv

    prioritized = [by_name[name] for name in target_names if name in by_name]
    if not prioritized:
        return list(invocables or [])
    prioritized_names = {str((inv or {}).get("name") or "").strip() for inv in prioritized}
    fallback = [
        inv for inv in invocables or []
        if str((inv or {}).get("name") or "").strip() not in prioritized_names
    ]
    return prioritized + fallback


def run_s01(ctx) -> None:
    """S-01 entry point: write-unlock probe."""
    try:
        logger.info("[%s] phase1: write-unlock probe...", ctx.job_id)
        _set_explore_status(ctx.job_id, 0, ctx.total, "S-01: Testing write-mode unlock...")
        admitted = admit_s00_s01_handoff(ctx)
        admitted_vocab = admitted.get("vocab") or ctx.vocab
        admitted_dll_strings = admitted.get("dll_strings") or ctx.dll_strings
        admitted_sentinels = admitted.get("sentinels") or ctx.sentinels
        admitted_s01_targets = admitted.get("s01_targets") or {}
        ctx.s00_s01_handoff_packet = admitted.get("packet") or {}
        ctx.vocab = admitted_vocab
        ctx.dll_strings = admitted_dll_strings
        ctx.sentinels = admitted_sentinels

        _prior = getattr(ctx, '_prior_session', {}) or {}
        _winning = _prior.get("winning_init_sequence")
        if _winning and _winning.get("sequence"):
            logger.info("[%s] phase1: replaying winning init sequence from prior session",
                        ctx.job_id)
            inv_map = {inv["name"]: inv for inv in ctx.invocables}
            for step in _winning["sequence"]:
                init_inv = inv_map.get(step.get("fn", ""))
                if init_inv:
                    try:
                        _execute_tool(init_inv, step.get("args", {}))
                    except Exception:
                        pass

            _prior_wfn = _winning.get("write_fn_tested", "")
            _prior_args = _winning.get("write_fn_args", {})
            _wfn_inv = inv_map.get(_prior_wfn)
            if _wfn_inv and _prior_args:
                try:
                    result = _execute_tool(_wfn_inv, _prior_args)
                    ret_m = _re.match(r"Returned:\s*(\d+)", result or "")
                    if ret_m and int(ret_m.group(1)) == 0:
                        ctx.unlock_result = {
                            "unlocked": True,
                            "sequence": _winning["sequence"],
                            "write_fn_tested": _prior_wfn,
                            "write_fn_args": _prior_args,
                            "notes": "Replayed winning sequence from prior session",
                        }
                        logger.info("[%s] phase1: UNLOCKED via prior winning sequence!",
                                    ctx.job_id)
                except Exception:
                    pass

        if not ctx.unlock_result.get("unlocked"):
            _set_explore_status(ctx.job_id, 0, ctx.total,
                                "S-01: Running write-unlock probe (timeout %ds)..." % _S01_TIMEOUT_SEC)
            probe_invocables = _prioritize_invocables_for_s01_targets(
                ctx.invocables, admitted_s01_targets,
            )
            with _cf.ThreadPoolExecutor(max_workers=1) as _tp:
                _fut = _tp.submit(_probe_write_unlock,
                                  probe_invocables, admitted_dll_strings, admitted_vocab)
                try:
                    ctx.unlock_result = _fut.result(timeout=_S01_TIMEOUT_SEC)
                except _cf.TimeoutError:
                    logger.warning("[%s] phase1: write-unlock probe timed out after %ds",
                                   ctx.job_id, _S01_TIMEOUT_SEC)
                    _fut.cancel()
                    ctx.unlock_result = {
                        "unlocked": False, "sequence": [],
                        "write_fn_tested": None,
                        "notes": f"write-unlock timed out after {_S01_TIMEOUT_SEC}s",
                    }
        if ctx.unlock_result.get("unlocked"):
            _seq = ctx.unlock_result.get("sequence", [])
            _seq_desc = " -> ".join(
                f"{s.get('fn', '?')}({s.get('args', {})})" for s in _seq
            )
            ctx.write_unlock_block = (
                "\nWRITE MODE ACTIVE: The write-unlock sequence has already been executed.\n"
                f"EXACT SEQUENCE: {_seq_desc}\n"
                "Write functions (any function whose name implies state changes -- Process, Update, "
                "Set, Create, Delete, Transfer, Submit, Send, Redeem, Unlock) should now succeed. "
                "Probe them with real ID values from STATIC ANALYSIS HINTS.\n"
                "IMPORTANT: The unlock sequence above MUST be called before any write function. "
                "The unlock code is cryptographic — use these EXACT argument values.\n"
            )
            logger.info("[%s] phase1: UNLOCKED: %s", ctx.job_id, ctx.unlock_result["notes"])

            # Record success findings for every function in the unlock sequence
            # so S-02 skips them and subsequent stages see them as resolved.
            for step in _seq:
                fn_name = step.get("fn", "")
                fn_args = step.get("args", {})
                if not fn_name:
                    continue
                _patch_finding(ctx.job_id, fn_name, {
                    "status": "success",
                    "working_call": fn_args,
                    "finding": f"Resolved in S-01 write-unlock probe: {fn_name}({fn_args}) returned 0",
                })
                ctx.already_explored.add(fn_name)
                ctx.live_findings.append({
                    "function": fn_name,
                    "status": "success",
                    "working_call": fn_args,
                    "finding": f"S-01 unlock: {fn_name}({fn_args}) returned 0",
                })
                logger.info("[%s] phase1: recorded finding for %s (solved in unlock probe)",
                            ctx.job_id, fn_name)
        else:
            _init_names = [inv["name"] for inv in ctx.init_invocables] if ctx.init_invocables else ["the init function"]
            ctx.write_unlock_block = (
                "\nWRITE MODE NOT YET UNLOCKED. This function modifies state (payments, refunds, etc). "
                f"You MUST call {_init_names[0]} first (try mode=0, mode=1, mode=2) before probing this function. "
                "Also look for unlock functions and call them after init. "
                "Use real ID values from STATIC ANALYSIS HINTS and reasonable "
                "numeric amounts (e.g. 100, 500). If you get sentinel 0xFFFFFFFB, try a different "
                "init mode or parameter combination. Do NOT give up after one attempt.\n"
            )
            logger.info("[%s] phase1: not unlocked: %s", ctx.job_id,
                        ctx.unlock_result.get("notes", ""))

        write_fns = [
            inv for inv in ctx.invocables
            if _re.search(r"(pay|redeem|unlock|process|write|commit|transfer|debit|credit)",
                          inv["name"], _re.I)
        ]
        if not write_fns:
            unlock_outcome = "not_attempted"
            blocking_sentinel: str | None = None
        elif ctx.unlock_result.get("unlocked"):
            unlock_outcome = "resolved"
            blocking_sentinel = None
        else:
            unlock_outcome = "blocked"
            blocking_sentinel = None
            for candidate_code in (0xFFFFFFFB, 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFC):
                if candidate_code in ctx.sentinels:
                    blocking_sentinel = f"0x{candidate_code:08X}"
                    break
        try:
            current_status = _get_job_status(ctx.job_id) or {}
            _persist_job_status(ctx.job_id, {
                **current_status,
                "write_unlock_outcome": unlock_outcome,
                "write_unlock_sentinel": blocking_sentinel,
            })
        except Exception as exc:
            logger.debug("[%s] phase1: write-unlock status emit failed: %s", ctx.job_id, exc)
        try:
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{ctx.job_id}/write_unlock_probe.json",
                json.dumps({
                    "outcome": unlock_outcome,
                    "unlocked": ctx.unlock_result.get("unlocked"),
                    "blocking_sentinel": blocking_sentinel,
                    "sequence": ctx.unlock_result.get("sequence"),
                    "write_fn_tested": ctx.unlock_result.get("write_fn_tested"),
                    "notes": ctx.unlock_result.get("notes"),
                    "code_reasoning_analysis": ctx.unlock_result.get("code_reasoning_analysis"),
                }, indent=2).encode(),
            )
        except Exception as exc:
            logger.debug("[%s] phase1: write_unlock_probe artifact upload failed: %s",
                         ctx.job_id, exc)
    except Exception as _we:
        logger.debug("[%s] phase1: write-unlock probe failed: %s", ctx.job_id, _we)
