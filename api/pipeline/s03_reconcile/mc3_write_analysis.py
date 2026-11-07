"""api.pipeline.s03_reconcile.mc3_write_analysis -- MC-3: post-reconcile coordinator."""

from __future__ import annotations

import ast
import json
import logging
import re as _re
from collections import defaultdict

from api.analysis.sentinel_codes import classify_common_result_code
from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _download_blob, _patch_finding
from api.pipeline.core.helpers import _persist_mc_decision
from api.pipeline.s01_unlock.unlock_helpers import (
    _WRITE_FN_PATTERN,
    _build_write_arg_candidates,
    _build_write_retry_plan,
    _mark_unlock_resolved,
    _targeted_unlock_attempt,
)
from api.pipeline.s01_unlock.write_unlock import _probe_write_unlock

logger = logging.getLogger("mcp_factory.api")


def _selection_source_summary(selection_by_fn: dict[str, list[dict]]) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for fn, selections in selection_by_fn.items():
        primary = selections[0] if selections else {}
        sources = [
            str(meta.get("source") or "")
            for meta in primary.values()
            if isinstance(meta, dict)
        ]
        summary[fn] = {
            "param_count": len(primary),
            "evidence_params": sum(1 for src in sources if src.startswith("evidence.")),
            "generic_params": sum(
                1
                for src in sources
                if src.startswith(("default.", "heuristic.", "function_context."))
            ),
            "vocab_params": sum(
                1 for src in sources if src.startswith(("vocab.", "static_analysis."))
            ),
            "top_sources": sorted({src for src in sources if src})[:4],
        }
    return summary


def _cluster_hints_from_retry_plan(retry_plan: list[dict]) -> list[dict]:
    hints: list[dict] = []
    for row in retry_plan[:8]:
        hints.append(
            {
                "function": row.get("function"),
                "cluster": row.get("cluster"),
                "priority": row.get("priority"),
                "sentinel_codes": row.get("sentinel_codes") or [],
                "runtime_ids_available": bool(row.get("runtime_ids_available")),
                "fallback": row.get("fallback") or "",
                "hint": (
                    f"{row.get('function')} grouped into {row.get('cluster')} "
                    f"with {row.get('evidence_param_count', 0)} evidence-backed params"
                ),
            }
        )
    return hints


def _extract_mc3_result_output_values(result_text: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for raw_line in str(result_text or "").splitlines()[1:]:
        line = str(raw_line or "").strip()
        if "=" not in line:
            continue
        key, value_text = line.split("=", 1)
        key = key.strip()
        value_text = value_text.strip()
        if not key or not value_text:
            continue
        try:
            value = ast.literal_eval(value_text)
        except Exception:
            match = _re.match(r"^(-?\d+)\b", value_text)
            if match:
                try:
                    value = int(match.group(1))
                except Exception:
                    value = value_text.strip("'\"")
            else:
                value = value_text.strip("'\"")
        if value not in (None, ""):
            result[key] = value
    return result


def _mc3_param_lookup(ctx, fn_name: str) -> dict[str, dict]:
    for inv in list(getattr(ctx, "invocables", []) or []):
        if str((inv or {}).get("name") or "") != str(fn_name or ""):
            continue
        return {
            str(param.get("name") or ""): dict(param)
            for param in list((inv or {}).get("parameters") or [])
            if isinstance(param, dict) and str(param.get("name") or "")
        }
    return {}


def _mc3_is_output_like_param(param: dict, key: str) -> bool:
    pname = str((param or {}).get("name") or key or "").strip().lower()
    desc = str((param or {}).get("description") or "").strip().lower()
    direction = str((param or {}).get("direction") or "").strip().lower()
    if direction == "out":
        return True
    if pname.startswith("out_") or pname.startswith(("pdw", "pout", "pszout", "lpszout")):
        return True
    return "output" in desc or "populated" in desc


def _mc3_merge_success_args(ctx, entry: dict) -> dict[str, object]:
    merged = dict(entry.get("args") or {})
    if bool(entry.get("result_truncated")):
        return merged
    param_lookup = _mc3_param_lookup(ctx, str(entry.get("function") or ""))
    for key, value in _extract_mc3_result_output_values(str(entry.get("result_excerpt") or "")).items():
        param = param_lookup.get(key, {})
        if _mc3_is_output_like_param(param, key) or key not in merged:
            merged[key] = value
    return merged


def _mc3_post_reconcile(ctx) -> None:
    """Analyze probe results to classify the write-unlock failure mode."""
    if ctx.unlock_result.get("unlocked"):
        return

    decision = {"trigger": "mc3-post-reconcile", "analysis": {}, "action": None, "result": None}

    try:
        probe_log: list[dict] = []
        try:
            raw = _download_blob(ARTIFACT_CONTAINER, f"{ctx.job_id}/explore_probe_log.json")
            probe_log = json.loads(raw)
        except Exception:
            decision["analysis"]["probe_log"] = "unavailable"
            _persist_mc_decision(ctx, "mc3-post-reconcile", decision)
            return

        write_sentinels: dict[str, list[int]] = defaultdict(list)
        write_accidental_success: list[dict] = []

        for entry in probe_log:
            fn = entry.get("function", "")
            tool = entry.get("tool", "")
            if not _WRITE_FN_PATTERN.search(fn):
                continue
            clf = entry.get("classification") or {}
            if not clf.get("has_return"):
                continue
            ret_val = int(clf.get("signed", -1))
            if ret_val == 0 and fn == tool:
                write_accidental_success.append(entry)
            elif ret_val != 0:
                write_sentinels[fn].append(ret_val & 0xFFFFFFFF)

        all_codes = []
        for codes in write_sentinels.values():
            all_codes.extend(codes)
        unique_codes = set(all_codes)

        if write_accidental_success:
            decision["analysis"]["mode"] = "accidental_success"
            accidental_by_fn: dict[str, dict] = {}
            for idx, entry in enumerate(write_accidental_success):
                fn = str(entry.get("function") or "")
                merged_args = _mc3_merge_success_args(ctx, entry)
                candidate = {
                    "args": merged_args,
                    "score": (len(merged_args), -idx),
                }
                current = accidental_by_fn.get(fn)
                if current is None or candidate["score"] > current["score"]:
                    accidental_by_fn[fn] = candidate
            decision["analysis"]["functions"] = sorted(accidental_by_fn)
            decision["action"] = "extract_working_sequence"

            for fn, candidate in accidental_by_fn.items():
                args = dict(candidate["args"] or {})
                _patch_finding(
                    ctx.job_id,
                    fn,
                    {
                        "status": "success",
                        "working_call": args,
                        "finding": f"MC-3: preserved successful write probe for {fn} with {args}.",
                        "notes": "MC-3: write fn returned 0 in probe log; merged output values preserved.",
                    },
                )
                with ctx._lock:
                    ctx.live_findings.append(
                        {
                            "function": fn,
                            "status": "success",
                            "finding": f"MC-3: preserved successful write probe for {fn}.",
                            "working_call": args,
                        }
                    )
            decision["result"] = f"patched {len(accidental_by_fn)} write findings to success"

        elif len(unique_codes) == 1:
            the_code = list(unique_codes)[0]
            meaning = ctx.sentinels.get(the_code) or classify_common_result_code(the_code) or "unknown"
            if (
                meaning == "account locked or suspended"
                and write_sentinels
                and all(_re.search(r"purchase|reserve|stock|inventory|product", fn, _re.I) for fn in write_sentinels)
            ):
                meaning = "resource unavailable or inventory/reservation precondition"
            decision["analysis"]["mode"] = "uniform_sentinel"
            decision["analysis"]["code"] = f"0x{the_code:08X}"
            decision["analysis"]["meaning"] = meaning
            decision["analysis"]["interpretation"] = (
                "All write functions return the same sentinel. "
                "This strongly suggests an initialization/auth prerequisite, "
                "not a per-function argument problem."
            )
            decision["action"] = "targeted_init_sweep"

            ctx.write_unlock_block = (
                f"\nWRITE MODE BLOCKED -- UNIFORM SENTINEL 0x{the_code:08X} ({meaning}). "
                "All write functions return the SAME error code. This means the DLL needs "
                "a specific initialization sequence BEFORE any write operation. "
                "You MUST call CS_Initialize with different mode values (0, 1, 2, 4, 8) "
                "and IMMEDIATELY test this write function after EACH init call. "
                "The mode that changes the error code (or returns 0) is the correct one.\n"
            )

            init_names = [
                inv["name"] for inv in ctx.invocables if _re.search(r"init(ializ)?", inv["name"], _re.I)
            ]
            init_seqs = []
            for init_fn in init_names:
                for mode in (0, 1, 2, 3, 4, 5, 6, 7, 8, 16, 32, 64):
                    init_seqs.append({"fn": init_fn, "args": {"param_1": mode}})

            write_args, write_selection = _build_write_arg_candidates(ctx)
            sentinel_codes_by_fn = {
                fn: [f"0x{c:08X}" for c in sorted(set(codes))]
                for fn, codes in write_sentinels.items()
            }
            retry_plan = _build_write_retry_plan(
                write_selection,
                sentinel_codes_by_fn=sentinel_codes_by_fn,
                id_formats=[str(x) for x in (ctx.vocab.get("id_formats") or []) if x],
            )
            ordered_retry_functions = [
                row["function"]
                for row in retry_plan
                if row.get("fallback") == "retry_ranked_candidates"
            ]
            write_args = {fn: write_args[fn] for fn in ordered_retry_functions if fn in write_args}
            write_selection = {fn: write_selection[fn] for fn in ordered_retry_functions if fn in write_selection}
            decision["analysis"]["retryable_functions"] = sorted(write_args)
            decision["analysis"]["candidate_examples"] = {
                fn: args[:2] for fn, args in write_args.items() if args
            }
            decision["analysis"]["candidate_selection"] = {
                fn: selection[:1] for fn, selection in write_selection.items() if selection
            }
            decision["analysis"]["candidate_source_summary"] = _selection_source_summary(write_selection)
            decision["analysis"]["retry_plan"] = retry_plan[:6]
            decision["analysis"]["prerequisite_clusters"] = {
                row["cluster"]: sum(1 for item in retry_plan if item.get("cluster") == row["cluster"])
                for row in retry_plan
            }
            decision["analysis"]["cluster_hints"] = _cluster_hints_from_retry_plan(retry_plan)
            decision["analysis"]["checkpoint_recommended_boundary"] = "s02_probe"

            if _targeted_unlock_attempt(ctx, init_seqs, write_args, "mc3-post-reconcile"):
                decision["result"] = "UNLOCKED via targeted init sweep"
            else:
                decision["result"] = "still blocked after targeted sweep"

        elif len(unique_codes) > 1:
            decision["analysis"]["mode"] = "mixed_sentinels"
            decision["analysis"]["codes"] = [f"0x{c:08X}" for c in unique_codes]
            per_fn_codes = {
                fn: [f"0x{c:08X}" for c in codes]
                for fn, codes in write_sentinels.items()
            }
            decision["analysis"]["per_function_codes"] = per_fn_codes
            decision["analysis"]["interpretation"] = (
                "Write functions return DIFFERENT sentinel codes. "
                "This suggests mixed failure causes -- some may need init, "
                "others may need specific arguments."
            )

            init_blocked = []
            arg_blocked = []
            for fn, codes in write_sentinels.items():
                code_set = set(codes)
                if len(code_set) == 1:
                    code = list(code_set)[0]
                    meaning = ctx.sentinels.get(code, "")
                    if "init" in meaning.lower() or "lock" in meaning.lower():
                        init_blocked.append(fn)
                    else:
                        arg_blocked.append(fn)
                else:
                    arg_blocked.append(fn)

            if init_blocked:
                decision["analysis"]["init_blocked_fns"] = init_blocked
                decision["action"] = "targeted_init_sweep_partial"

                ctx.write_unlock_block = (
                    f"\nWRITE MODE MIXED SENTINELS. "
                    f"Init-blocked: {init_blocked}. "
                    f"Arg-blocked: {arg_blocked}. "
                    "Try different init modes for init-blocked, "
                    "different argument formats for arg-blocked.\n"
                )

                init_names = [
                    inv["name"] for inv in ctx.invocables if _re.search(r"init(ializ)?", inv["name"], _re.I)
                ]
                init_seqs = []
                for init_fn in init_names:
                    for mode in (0, 1, 2, 3, 4, 5, 6, 7, 8, 16, 32, 64):
                        init_seqs.append({"fn": init_fn, "args": {"param_1": mode}})

                write_args, write_selection = _build_write_arg_candidates(ctx)
                write_args = {
                    fn: args for fn, args in write_args.items() if fn in init_blocked
                }
                write_selection = {
                    fn: selection for fn, selection in write_selection.items() if fn in init_blocked
                }
                sentinel_codes_by_fn = {
                    fn: [f"0x{c:08X}" for c in sorted(set(write_sentinels.get(fn, [])))]
                    for fn in init_blocked
                }
                retry_plan = _build_write_retry_plan(
                    write_selection,
                    sentinel_codes_by_fn=sentinel_codes_by_fn,
                    id_formats=[str(x) for x in (ctx.vocab.get("id_formats") or []) if x],
                )
                ordered_retry_functions = [
                    row["function"]
                    for row in retry_plan
                    if row.get("fallback") == "retry_ranked_candidates"
                ]
                write_args = {fn: write_args[fn] for fn in ordered_retry_functions if fn in write_args}
                write_selection = {fn: write_selection[fn] for fn in ordered_retry_functions if fn in write_selection}
                decision["analysis"]["retryable_functions"] = sorted(write_args)
                decision["analysis"]["candidate_examples"] = {
                    fn: args[:2] for fn, args in write_args.items() if args
                }
                decision["analysis"]["candidate_selection"] = {
                    fn: selection[:1] for fn, selection in write_selection.items() if selection
                }
                decision["analysis"]["candidate_source_summary"] = _selection_source_summary(write_selection)
                decision["analysis"]["retry_plan"] = retry_plan[:6]
                decision["analysis"]["prerequisite_clusters"] = {
                    row["cluster"]: sum(1 for item in retry_plan if item.get("cluster") == row["cluster"])
                    for row in retry_plan
                }
                decision["analysis"]["cluster_hints"] = _cluster_hints_from_retry_plan(retry_plan)
                decision["analysis"]["checkpoint_recommended_boundary"] = "s02_probe"

                if init_seqs and write_args:
                    if _targeted_unlock_attempt(ctx, init_seqs, write_args, "mc3-mixed-sentinel-init"):
                        decision["result"] = "UNLOCKED init-blocked functions via targeted sweep"
                    else:
                        decision["result"] = (
                            f"partial sweep tried {len(init_blocked)} init-blocked fns -- still blocked"
                        )
                else:
                    decision["result"] = "deferred -- mixed sentinels classified but no init sweep targets"
            else:
                decision["action"] = "no_retry_mixed"
                decision["result"] = "deferred -- all mixed sentinel fns appear arg-blocked"
        else:
            decision["analysis"]["mode"] = "no_write_probes"
            decision["action"] = "fallback_reprobe"
            ctx.unlock_result = _probe_write_unlock(ctx.invocables, ctx.dll_strings, ctx.vocab)
            if ctx.unlock_result.get("unlocked"):
                _mark_unlock_resolved(ctx, "mc3-post-reconcile", ctx.unlock_result.get("notes", ""))
                decision["result"] = "UNLOCKED via fallback re-probe"
            else:
                decision["result"] = "still blocked"

    except Exception as exc:
        decision["result"] = f"error: {exc}"
        logger.debug("[%s] mc3-post-reconcile failed: %s", ctx.job_id, exc)

    _persist_mc_decision(ctx, "mc3-post-reconcile", decision)
