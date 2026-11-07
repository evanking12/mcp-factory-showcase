"""api.pipeline.s01_unlock.unlock_helpers -- Write-unlock resolution + re-probe."""

from __future__ import annotations

import json
import logging
import re as _re

from api.infra.config import ARTIFACT_CONTAINER
from api.services.executor import _execute_tool
from api.infra.storage import (
    _persist_job_status, _get_job_status,
    _load_findings, _patch_finding, _save_finding, _upload_to_blob,
)
from api.pipeline.core.helpers import (
    _is_true_output_param,
    _WRITE_FN_RE,
    _build_ranked_fallback_probe_args,
)
from api.pipeline.core.evidence_candidates import classify_value_kind
from api.pipeline.core.types import ExploreContext

logger = logging.getLogger("mcp_factory.api")

_WRITE_FN_PATTERN = _WRITE_FN_RE


def _build_write_args_from_vocab(ctx: ExploreContext) -> dict[str, list[dict]]:
    """Build write function test args from vocab id_formats and known values.

    Skips genuine output buffers (using _is_true_output_param) -- Ghidra's
    direction="out" on byte*/char* is treated as ambiguous, not factual.
    """
    write_args, _ = _build_write_arg_candidates(ctx)
    return write_args


def _build_write_arg_candidates(
    ctx: ExploreContext,
    *,
    max_attempts: int = 4,
) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """Build ranked write-function argument candidates plus selection metadata.

    This reuses the same ranked fallback machinery as the probe loop so later
    stage retries consume the strongest available evidence instead of position-
    based placeholder combos.
    """
    write_args: dict[str, list[dict]] = {}
    write_selection: dict[str, list[dict]] = {}
    evidence = getattr(ctx, "evidence_candidates", None)

    for inv in ctx.invocables:
        if not _WRITE_FN_PATTERN.search(inv["name"]):
            continue
        combos: list[dict] = []
        selection_list: list[dict] = []
        for attempt in range(max_attempts):
            args, selection = _build_ranked_fallback_probe_args(
                inv,
                ctx.vocab,
                attempt=attempt,
                evidence=evidence,
            )
            if not args or args in combos:
                continue
            combos.append(args)
            selection_list.append(selection)
        if not combos:
            combos = [{}]
            selection_list = [{}]
        write_args[inv["name"]] = combos
        write_selection[inv["name"]] = selection_list
    return write_args, write_selection


def _classify_write_dependency_cluster(fn_name: str) -> str:
    fn = str(fn_name or "")
    if _re.search(r"reserv|stock|inventory|product|sku", fn, _re.I):
        return "inventory"
    if _re.search(r"purchase|payment|refund|void|transaction|charge|settle", fn, _re.I):
        return "payment"
    if _re.search(r"redeem|loyalty|points", fn, _re.I):
        return "loyalty"
    if _re.search(r"customer|account|profile", fn, _re.I):
        return "customer"
    return "generic"


def _required_runtime_id_kind_for_function(fn_name: str) -> str:
    fn = str(fn_name or "")
    if _re.search(r"cancel", fn, _re.I) and _re.search(r"reserv|resv", fn, _re.I):
        return "reservation_id"
    if _re.search(r"void", fn, _re.I) and _re.search(r"transaction|txn", fn, _re.I):
        return "transaction_id"
    return ""


def _build_write_retry_plan(
    write_selection: dict[str, list[dict]],
    *,
    sentinel_codes_by_fn: dict[str, list[str]] | None = None,
    extracted_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    id_formats: list[str] | None = None,
    available_id_kinds_override: set[str] | None = None,
) -> list[dict]:
    sentinel_codes_by_fn = sentinel_codes_by_fn or {}
    extracted_ids = list(extracted_ids or [])
    evidence_ids = list(evidence_ids or [])
    id_formats = list(id_formats or [])
    available_id_kinds = {
        classify_value_kind(val, id_formats)
        for val in (extracted_ids + evidence_ids)
        if str(val).strip()
    }
    if available_id_kinds_override:
        available_id_kinds.update(
            str(kind).strip()
            for kind in available_id_kinds_override
            if str(kind).strip()
        )
    retry_plan: list[dict] = []

    for fn, selections in write_selection.items():
        primary = selections[0] if selections else {}
        strongest_sources = sorted(
            {
                str(meta.get("source") or "")
                for meta in primary.values()
                if isinstance(meta, dict) and str(meta.get("source") or "").strip()
            }
        )
        evidence_param_count = sum(
            1
            for meta in primary.values()
            if isinstance(meta, dict) and str(meta.get("source") or "").startswith("evidence.")
        )
        vocab_param_count = sum(
            1
            for meta in primary.values()
            if isinstance(meta, dict) and str(meta.get("source") or "").startswith("vocab.")
        )
        candidate_count = len(selections)
        cluster = _classify_write_dependency_cluster(fn)
        required_id_kind = _required_runtime_id_kind_for_function(fn)
        has_runtime_ids = bool(extracted_ids or evidence_ids)
        has_required_runtime_id = (
            not required_id_kind or required_id_kind in available_id_kinds
        )
        rationale_parts = [
            f"{evidence_param_count} evidence-backed params" if evidence_param_count else "no direct evidence-backed params",
            f"{candidate_count} ranked candidate set(s)",
            f"cluster={cluster}",
        ]
        if sentinel_codes_by_fn.get(fn):
            rationale_parts.append(f"sentinels={','.join(sentinel_codes_by_fn[fn])}")
        if has_runtime_ids:
            rationale_parts.append("runtime IDs available")
        if required_id_kind:
            if has_required_runtime_id:
                rationale_parts.append(f"{required_id_kind} evidence available")
            else:
                rationale_parts.append(f"missing {required_id_kind} evidence")
        fallback = "retry_ranked_candidates"
        if required_id_kind and not has_required_runtime_id:
            fallback = "defer_to_gap_resolution"
        elif evidence_param_count == 0 and not has_runtime_ids:
            fallback = "defer_to_gap_resolution"
        retry_plan.append(
            {
                "function": fn,
                "cluster": cluster,
                "priority": (evidence_param_count * 10) + (vocab_param_count * 4) + min(candidate_count, 3),
                "candidate_count": candidate_count,
                "evidence_param_count": evidence_param_count,
                "vocab_param_count": vocab_param_count,
                "strongest_sources": strongest_sources[:4],
                "sentinel_codes": sentinel_codes_by_fn.get(fn, []),
                "runtime_ids_available": has_runtime_ids,
                "required_runtime_id_kind": required_id_kind,
                "matching_runtime_id_available": has_required_runtime_id,
                "available_runtime_id_kinds": sorted(available_id_kinds),
                "fallback": fallback,
                "rationale": "; ".join(rationale_parts),
            }
        )

    retry_plan.sort(
        key=lambda row: (
            -int(row.get("priority") or 0),
            -int(row.get("candidate_count") or 0),
            str(row.get("function") or ""),
        )
    )
    return retry_plan


def _mark_unlock_resolved(ctx: ExploreContext, trigger: str, notes: str) -> None:
    """Update context and job status when write-unlock is cracked."""
    ctx.unlock_result["unlocked"] = True
    ctx.unlock_result["resolved_at"] = trigger
    ctx.unlock_result["notes"] = notes
    ctx.write_unlock_block = (
        f"\nWRITE MODE ACTIVE (resolved at {trigger}): "
        "The write-unlock sequence has been executed. Write functions "
        "should now succeed. Probe with real ID values from "
        "STATIC ANALYSIS HINTS.\n"
    )
    logger.info("[%s] %s: WRITE UNLOCKED: %s", ctx.job_id, trigger, notes)

    winning_sequence = ctx.unlock_result.get("sequence", [])
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/winning_init_sequence.json",
            json.dumps({
                "resolved_at": trigger,
                "sequence": winning_sequence,
                "write_fn_tested": ctx.unlock_result.get("write_fn_tested"),
                "write_fn_args": ctx.unlock_result.get("write_fn_args"),
                "notes": notes,
            }, indent=2).encode(),
        )
        logger.info("[%s] %s: winning init sequence persisted", ctx.job_id, trigger)
    except Exception:
        pass

    try:
        _cur = _get_job_status(ctx.job_id) or {}
        _persist_job_status(ctx.job_id, {
            **_cur,
            "write_unlock_outcome": "resolved",
            "write_unlock_sentinel": None,
            "write_unlock_resolved_at": trigger,
        })
    except Exception:
        pass

    _persist_unlock_success_finding(
        ctx,
        str(ctx.unlock_result.get("write_fn_tested") or ""),
        ctx.unlock_result.get("write_fn_args"),
        trigger,
        notes,
    )
    _reprobe_write_functions_after_unlock(ctx, trigger)


def _persist_unlock_success_finding(
    ctx: ExploreContext,
    fn_name: str,
    working_call: dict | None,
    trigger: str,
    notes: str,
) -> None:
    if not fn_name or not isinstance(working_call, dict):
        return
    patch = {
        "status": "success",
        "working_call": working_call,
        "finding": f"Confirmed by {trigger}: {fn_name}({working_call}) = 0",
        "notes": notes,
        "verification": "verified",
    }
    findings = _load_findings(ctx.job_id)
    if any(f.get("function") == fn_name for f in findings):
        _patch_finding(ctx.job_id, fn_name, patch)
    else:
        _save_finding(ctx.job_id, {"function": fn_name, **patch})
    with ctx._lock:
        ctx.live_findings.append({
            "function": fn_name,
            "status": "success",
            "finding": patch["finding"],
            "working_call": working_call,
        })


def _targeted_unlock_attempt(
    ctx: ExploreContext,
    init_sequences: list[dict],
    write_test_args: dict[str, list[dict]],
    label: str,
) -> bool:
    """Try specific init->write sequences. Returns True if any write returns 0."""
    inv_map = {inv["name"]: inv for inv in ctx.invocables}
    write_fns: list[str] = []
    for fn_name in write_test_args:
        if fn_name in inv_map and _WRITE_FN_PATTERN.search(fn_name):
            write_fns.append(fn_name)
    for fn_name in inv_map:
        if _WRITE_FN_PATTERN.search(fn_name) and fn_name not in write_fns:
            write_fns.append(fn_name)

    for seq in init_sequences:
        init_fn = seq.get("fn", "")
        init_args = seq.get("args", {})
        init_inv = inv_map.get(init_fn)
        if not init_inv:
            continue
        try:
            _execute_tool(init_inv, init_args)
        except Exception:
            continue

        for wfn in write_fns:
            w_inv = inv_map.get(wfn)
            if not w_inv:
                continue
            for args in write_test_args.get(wfn, [{}])[:3]:
                try:
                    result = _execute_tool(w_inv, args)
                    ret_m = _re.match(r"Returned:\s*(\d+)", result or "")
                    if ret_m:
                        ret_val = int(ret_m.group(1)) & 0xFFFFFFFF
                        if ret_val == 0:
                            ctx.unlock_result = {
                                "unlocked": True,
                                "sequence": [{"fn": init_fn, "args": init_args}],
                                "write_fn_tested": wfn,
                                "write_fn_args": args,
                                "notes": f"{label}: {init_fn}({init_args}) -> {wfn}({args}) = 0",
                            }
                            _mark_unlock_resolved(ctx, label, ctx.unlock_result["notes"])
                            return True
                except Exception:
                    continue
    return False


def _reprobe_write_functions_after_unlock(ctx: ExploreContext, trigger: str) -> None:
    """Re-probe every write function that previously failed, now that unlock is active."""
    findings = _load_findings(ctx.job_id)
    failed_writes = [
        f for f in findings
        if _WRITE_FN_PATTERN.search(f.get("function", ""))
        and f.get("status") == "error"
    ]
    if not failed_writes:
        return

    logger.info("[%s] %s: re-probing %d failed write functions after unlock",
                ctx.job_id, trigger, len(failed_writes))

    inv_map = {inv["name"]: inv for inv in ctx.invocables}
    for step in ctx.unlock_result.get("sequence", []):
        init_inv = inv_map.get(step.get("fn", ""))
        if init_inv:
            try:
                _execute_tool(init_inv, step.get("args", {}))
            except Exception:
                pass

    _known_ids: set = set()
    _known_amounts: set = set()
    for f in findings:
        wc = f.get("working_call")
        if not wc or not isinstance(wc, dict):
            continue
        for _k, _v in wc.items():
            if isinstance(_v, str) and _v:
                _known_ids.add(_v)
            elif isinstance(_v, (int, float)) and _v > 0:
                _known_amounts.add(int(_v))
    if ctx.vocab and ctx.vocab.get("id_formats"):
        for _idf in ctx.vocab["id_formats"]:
            if _idf:
                _known_ids.add(str(_idf))

    write_args = _build_write_args_from_vocab(ctx)
    reprobe_count = 0

    _id_list = sorted(_known_ids)[:6] or ["CUST-001"]
    _amt_list = sorted(_known_amounts)[:4] or [100, 500]
    for fn_name in list(write_args.keys()):
        _extra = []
        _inv = inv_map.get(fn_name)
        if _inv:
            _params = _inv.get("parameters") or []
            for _id_val in _id_list[:3]:
                for _amt in _amt_list[:2]:
                    _a = {}
                    for _i, _p in enumerate(_params):
                        if _is_true_output_param(_p):
                            continue
                        _pn = _p.get("name", f"param_{_i+1}")
                        if _i == 0:
                            _a[_pn] = _id_val
                        elif _i == 1:
                            _a[_pn] = _amt
                        else:
                            _a[_pn] = _id_val if _i % 2 == 0 else _amt
                    if _a:
                        _extra.append(_a)
            write_args[fn_name] = _extra + write_args.get(fn_name, [])

    _winning_fn = ctx.unlock_result.get("write_fn_tested", "")
    _winning_args = ctx.unlock_result.get("write_fn_args")
    if _winning_args and isinstance(_winning_args, dict):
        for fn in write_args:
            write_args[fn] = [_winning_args] + write_args[fn]

    for finding in failed_writes:
        fn_name = finding["function"]
        inv = inv_map.get(fn_name)
        if not inv:
            continue

        arg_candidates = write_args.get(fn_name, [])
        if not arg_candidates:
            params = inv.get("parameters") or []
            if params:
                _fallback = {}
                for _i, _p in enumerate(params):
                    if _is_true_output_param(_p):
                        continue
                    _pn = _p.get("name", f"param_{_i+1}")
                    _fallback[_pn] = _id_list[0] if _i == 0 else (_amt_list[0] if _i == 1 else 1)
                arg_candidates = [_fallback] if _fallback else [{}]
            else:
                arg_candidates = [{}]
        if _winning_args and _winning_args not in arg_candidates:
            arg_candidates = [_winning_args] + arg_candidates

        for args in arg_candidates[:6]:
            try:
                for step in ctx.unlock_result.get("sequence", []):
                    init_inv = inv_map.get(step.get("fn", ""))
                    if init_inv:
                        _execute_tool(init_inv, step.get("args", {}))

                    result = _execute_tool(inv, args)
                    ret_m = _re.match(r"Returned:\s*(\d+)", result or "")
                    if ret_m:
                        ret_val = int(ret_m.group(1)) & 0xFFFFFFFF
                        if ret_val == 0:
                            _persist_unlock_success_finding(
                                ctx,
                                fn_name,
                                args,
                                trigger,
                                f"Cracked at {trigger}: init sequence + {fn_name}({args}) = 0",
                            )
                            reprobe_count += 1
                            logger.info("[%s] %s: %s CRACKED with args %s",
                                        ctx.job_id, trigger, fn_name, args)
                            break
            except Exception:
                continue

    if _winning_fn and _winning_args and reprobe_count == 0:
        for finding in failed_writes:
            if finding["function"] == _winning_fn:
                _persist_unlock_success_finding(
                    ctx,
                    _winning_fn,
                    _winning_args,
                    trigger,
                    f"Confirmed by {trigger}: {_winning_fn}({_winning_args}) = 0",
                )
                reprobe_count += 1
                logger.info("[%s] %s: force-patched %s from MC unlock proof",
                            ctx.job_id, trigger, _winning_fn)
                break

    logger.info("[%s] %s: re-probe complete -- %d/%d write functions now succeed",
                ctx.job_id, trigger, reprobe_count, len(failed_writes))
