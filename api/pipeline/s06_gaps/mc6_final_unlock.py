"""api.pipeline.s06_gaps.mc6_final_unlock -- MC-6: final comprehensive unlock."""

from __future__ import annotations

import json
import logging
import re as _re

from api.services.executor import _execute_tool
from api.infra.storage import _load_findings
from api.pipeline.core.helpers import _persist_mc_decision
from api.pipeline.s01_unlock.write_unlock import (
    _llm_analyze_decompiled_code,
    _execute_llm_strategies,
    _analyze_decompiled_unlock_patterns,
    _build_unlock_probe_arg_sets,
)
from api.pipeline.s01_unlock.unlock_helpers import (
    _mark_unlock_resolved,
    _targeted_unlock_attempt,
    _WRITE_FN_PATTERN,
)

logger = logging.getLogger("mcp_factory.api")


def _mc6_post_gap_resolution(ctx) -> None:
    """Final comprehensive unlock attempt with ALL accumulated knowledge."""
    if ctx.unlock_result.get("unlocked"):
        return

    decision = {"trigger": "mc6-post-gap-resolution", "analysis": {}, "action": None, "result": None}

    try:
        findings = _load_findings(ctx.job_id)

        gap_resolved_writes = [
            f for f in findings
            if _WRITE_FN_PATTERN.search(f.get("function", ""))
            and f.get("status") == "success"
            and "gap" in str(f.get("stop_reason", "")).lower()
        ]

        if gap_resolved_writes:
            decision["analysis"]["gap_resolved_writes"] = [
                f.get("function") for f in gap_resolved_writes
            ]
            decision["action"] = "gap_resolution_cracked_write"
            decision["result"] = (
                f"Gap resolution already cracked {len(gap_resolved_writes)} write functions -- "
                "checking if full unlock is now possible"
            )

        all_ids: set = set()
        all_amounts: set = set()
        for f in findings:
            if f.get("status") != "success":
                continue
            wc = f.get("working_call")
            if not isinstance(wc, dict):
                continue
            for v in wc.values():
                sv = str(v).strip()
                if _re.match(r"^[A-Z]+-", sv):
                    all_ids.add(sv)
                elif isinstance(v, (int, float)) and 1 <= v <= 100000:
                    all_amounts.add(int(v))

        if ctx.vocab:
            for fmt in (ctx.vocab.get("id_formats") or []):
                if fmt:
                    all_ids.add(str(fmt))

        all_ids_list = list(all_ids)[:8]
        all_amounts_list = sorted(all_amounts)[:4] if all_amounts else [1, 10, 50, 100]

        decision["analysis"]["total_known_ids"] = len(all_ids_list)
        decision["analysis"]["total_known_amounts"] = len(all_amounts_list)
        decision["analysis"]["total_sentinel_codes"] = len(ctx.sentinels)
        decision["action"] = "final_comprehensive_attempt"

        # Phase A: LLM code-reasoning unlock
        inv_map = {inv["name"]: inv for inv in ctx.invocables}
        _mc6_init_names = [n for n in inv_map if _re.search(r"init(ializ)?", n, _re.I)]
        _mc6_write_fns = [n for n in inv_map if _WRITE_FN_PATTERN.search(n)]
        _mc6_tried: list[str] = []

        llm_strategies = _llm_analyze_decompiled_code(ctx.invocables)
        decision["analysis"]["llm_strategies_count"] = len(llm_strategies)

        if llm_strategies:
            llm_hit = _execute_llm_strategies(
                llm_strategies, inv_map, _mc6_init_names, _mc6_write_fns, _mc6_tried,
            )
            if llm_hit:
                decision["analysis"]["unlock_cracked"] = True
                decision["analysis"]["unlock_args"] = llm_hit.get("write_fn_args")
                ctx.unlock_result["sequence"] = list(llm_hit.get("sequence") or [])
                ctx.unlock_result["write_fn_tested"] = llm_hit.get("write_fn_tested")
                ctx.unlock_result["write_fn_args"] = llm_hit.get("write_fn_args")
                logger.info("[%s] MC-6: LLM strategy CRACKED: %s", ctx.job_id, llm_hit.get("notes"))
                _mark_unlock_resolved(ctx, "mc6-llm-code-reasoning", llm_hit.get("notes", ""))
                with ctx._lock:
                    ctx.live_findings.append({
                        "function": llm_hit.get("write_fn_tested", "unknown"),
                        "status": "success",
                        "finding": f"MC-6 LLM code reasoning: {llm_hit.get('notes')}",
                        "working_call": llm_hit.get("write_fn_args"),
                    })
                decision["result"] = f"UNLOCKED via LLM code reasoning: {llm_hit.get('notes')}"
                _persist_mc_decision(ctx, "mc6-post-gap-resolution", decision)
                return

        code_analysis = _analyze_decompiled_unlock_patterns(ctx.invocables)
        decision["analysis"]["code_reasoning"] = code_analysis

        sku_samples = [
            value
            for value in all_ids_list
            if str(value).upper().startswith(("WDG", "PRO", "ACC", "GDG", "SW-"))
        ]
        if not sku_samples:
            sku_samples = ["WDG-XL-BLU", "ACC-USB-C", "PRO-SVC-ANNUAL"]
        id_samples = [
            value
            for value in all_ids_list
            if value not in sku_samples
        ] or ["CUST-001", "ORD-001", "ACCT-001"]
        amount_samples = [5000, 2500, 1000, 500]

        for uf in code_analysis.get("unlock_functions", []):
            uf_inv = inv_map.get(uf["name"])
            if not uf_inv:
                continue
            params = uf.get("params") or []
            if not params:
                continue

            decision["analysis"]["unlock_fn_found"] = uf["name"]
            decision["analysis"]["xor_checksum_target"] = uf.get("xor_target_hex")
            decision["analysis"]["xor_codes_generated"] = len(uf.get("xor_codes", []))

            for code in uf.get("xor_codes", [])[:5]:
                for args in _build_unlock_probe_arg_sets(
                    uf_inv,
                    xor_code=code,
                    id_samples=id_samples[:4],
                    sku_samples=sku_samples[:4],
                    amount_samples=amount_samples,
                ):
                    try:
                        for init_inv in ctx.init_invocables or []:
                            _execute_tool(init_inv, {})
                        result = _execute_tool(uf_inv, args)
                        ret_m = _re.match(r"Returned:\s*(\d+)", result or "")
                        if ret_m and int(ret_m.group(1)) == 0:
                            decision["analysis"]["unlock_cracked"] = True
                            decision["analysis"]["unlock_args"] = args
                            logger.info("[%s] MC-6: %s CRACKED with XOR code: %s",
                                        ctx.job_id, uf["name"], args)
                            _init_seq = [
                                {"fn": ii["name"], "args": {}}
                                for ii in (ctx.init_invocables or [])
                            ]
                            _init_seq.append({"fn": uf["name"], "args": args})
                            ctx.unlock_result["sequence"] = _init_seq
                            ctx.unlock_result["write_fn_tested"] = uf["name"]
                            ctx.unlock_result["write_fn_args"] = args
                            _mark_unlock_resolved(
                                ctx, "mc6-code-reasoning",
                                f"{uf['name']}({args}) -> 0 (XOR checksum solved)",
                            )
                            with ctx._lock:
                                ctx.live_findings.append({
                                    "function": uf["name"],
                                    "status": "success",
                                    "finding": f"MC-6 XOR: {uf['name']}({args}) -> 0",
                                    "working_call": args,
                                })
                            decision["result"] = (
                                f"UNLOCKED via code reasoning: {uf['name']}({args}) "
                                f"with XOR target {uf['xor_target_hex']}"
                            )
                            _persist_mc_decision(ctx, "mc6-post-gap-resolution", decision)
                            return
                    except Exception:
                        continue

        for dep in code_analysis.get("dependency_chains", []):
            src = inv_map.get(dep["source"])
            if not src:
                continue
            try:
                for init_inv in ctx.init_invocables or []:
                    _execute_tool(init_inv, {})
                _execute_tool(src, {})
                dep_write_args: dict[str, list[dict]] = {}
                for inv in ctx.invocables:
                    if inv["name"] == dep["target"] and _WRITE_FN_PATTERN.search(inv["name"]):
                        p = inv.get("parameters") or []
                        if p:
                            for id_val in all_ids_list[:3]:
                                a = {}
                                for j, pp in enumerate(p):
                                    pn = pp.get("name", f"param_{j+1}")
                                    a[pn] = id_val if j == 0 else 1
                                dep_write_args.setdefault(inv["name"], []).append(a)
                init_seqs = [{"fn": init_inv["name"], "args": {}} for init_inv in (ctx.init_invocables or [])]
                init_seqs.append({"fn": dep["source"], "args": {}})
                if dep_write_args and _targeted_unlock_attempt(ctx, init_seqs, dep_write_args, "mc6-dependency-chain"):
                    with ctx._lock:
                        ctx.live_findings.append({
                            "function": dep["target"],
                            "status": "success",
                            "finding": f"MC-6 dependency chain: {dep['source']} -> {dep['target']}",
                            "working_call": ctx.unlock_result.get("write_fn_args"),
                        })
                    decision["result"] = f"UNLOCKED via dependency chain: {dep['source']} -> {dep['target']}"
                    _persist_mc_decision(ctx, "mc6-post-gap-resolution", decision)
                    return
            except Exception:
                continue

        # Phase B: Brute-force fallback
        write_args: dict[str, list[dict]] = {}
        for inv in ctx.invocables:
            if not _WRITE_FN_PATTERN.search(inv["name"]):
                continue
            params = inv.get("parameters") or []
            if not params:
                continue
            combos = []
            for id_val in all_ids_list[:4]:
                for amt in all_amounts_list[:3]:
                    a = {}
                    for i, p in enumerate(params):
                        pn = p.get("name", f"param_{i+1}")
                        if i == 0:
                            a[pn] = id_val
                        elif i == 1:
                            a[pn] = amt
                        else:
                            a[pn] = id_val if i % 2 == 0 else amt
                    combos.append(a)
            write_args[inv["name"]] = combos

        init_names = [inv["name"] for inv in ctx.invocables
                      if _re.search(r"init(ializ)?", inv["name"], _re.I)]
        init_seqs = []
        for init_fn in init_names:
            for mode in list(range(17)) + [32, 64, 128, 256, 512]:
                init_seqs.append({"fn": init_fn, "args": {"param_1": mode}})
            init_seqs.append({"fn": init_fn, "args": {}})

        if _targeted_unlock_attempt(ctx, init_seqs, write_args, "mc6-post-gap-resolution"):
            with ctx._lock:
                ctx.live_findings.append({
                    "function": ctx.unlock_result.get("write_fn_tested", "unknown"),
                    "status": "success",
                    "finding": f"MC-6 brute-force fallback: {ctx.unlock_result.get('notes', '')}",
                    "working_call": ctx.unlock_result.get("write_fn_args"),
                })
            decision["result"] = "UNLOCKED on brute-force fallback"
        else:
            decision["result"] = (
                f"FINAL: still blocked after {len(init_seqs)} init sequences x "
                f"{sum(len(v) for v in write_args.values())} write arg combos"
            )

    except Exception as exc:
        decision["result"] = f"error: {exc}"
        logger.debug("[%s] mc6-post-gap-resolution failed: %s", ctx.job_id, exc)

    _persist_mc_decision(ctx, "mc6-post-gap-resolution", decision)
