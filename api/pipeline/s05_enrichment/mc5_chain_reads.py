"""api.pipeline.s05_enrichment.mc5_chain_reads -- MC-5: post-verification coordinator."""

from __future__ import annotations

import json
import logging
import re as _re

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _download_blob, _load_findings
from api.pipeline.core.helpers import _persist_mc_decision
from api.pipeline.core.evidence_candidates import (
    TIER_RUNTIME,
    classify_value_kind,
)
from api.pipeline.s01_unlock.unlock_helpers import (
    _targeted_unlock_attempt,
    _WRITE_FN_PATTERN,
    _build_write_arg_candidates,
    _build_write_retry_plan,
)

logger = logging.getLogger("mcp_factory.api")


def _is_verified_read_finding(finding: dict) -> bool:
    """MC-5 may only chain from verified read evidence, not inherited success."""
    status = str(finding.get("status") or "").strip().lower()
    verification = str(finding.get("verification") or "").strip().lower()
    if status == "verified_success":
        return verification in {"", "verified"}
    return status == "success" and verification == "verified"


def _load_s03_retry_surface(ctx) -> dict:
    if hasattr(ctx, "latest_mc_decision"):
        try:
            latest = ctx.latest_mc_decision("mc3-post-reconcile")
            if isinstance(latest, dict):
                analysis = latest.get("analysis") if isinstance(latest.get("analysis"), dict) else {}
                if analysis.get("retry_plan"):
                    return {"source": "live_mc3", **analysis}
        except Exception:
            pass

    state = getattr(ctx, "_state", None)
    if isinstance(state, dict):
        mc_state = state.get("mc_decisions") or {}
        if isinstance(mc_state, dict):
            latest = mc_state.get("mc3-post-reconcile")
            if isinstance(latest, dict):
                analysis = latest.get("analysis") if isinstance(latest.get("analysis"), dict) else {}
                if analysis.get("retry_plan"):
                    return {"source": "live_mc3", **analysis}

    checkpoint = getattr(ctx, "_checkpoint", None)
    try:
        stage_data = ((checkpoint.stages or {}).get("s03_reconcile") or {}).data  # type: ignore[attr-defined]
    except Exception:
        stage_data = {}
    if isinstance(stage_data, dict):
        mc_decision = stage_data.get("mc_decision")
        if isinstance(mc_decision, dict):
            analysis = mc_decision.get("analysis") if isinstance(mc_decision.get("analysis"), dict) else {}
            if analysis.get("retry_plan"):
                return {"source": "checkpoint_stage", **analysis}

    try:
        raw = _download_blob(ARTIFACT_CONTAINER, f"{ctx.job_id}/mc-decisions/mc3-post-reconcile.json")
        history = json.loads(raw)
        if isinstance(history, list) and history:
            latest = history[-1]
            if isinstance(latest, dict):
                analysis = latest.get("analysis") if isinstance(latest.get("analysis"), dict) else {}
                if analysis.get("retry_plan"):
                    return {"source": "blob_history", **analysis}
    except Exception:
        pass
    return {}


def _mc5_post_verification(ctx) -> None:
    """Use verified read function outputs as concrete write function arguments."""
    if ctx.unlock_result.get("unlocked"):
        return

    decision = {"trigger": "mc5-post-verification", "analysis": {}, "action": None, "result": None}

    try:
        findings = _load_findings(ctx.job_id)
        verified_reads: list[dict] = []
        extracted_ids: list[str] = []
        extracted_amounts: list[int] = []
        evidence = getattr(ctx, "evidence_candidates", None)
        id_formats = [str(x) for x in (ctx.vocab.get("id_formats") or []) if x]

        for f in findings:
            fn = f.get("function", "")
            if _WRITE_FN_PATTERN.search(fn):
                continue
            if not _is_verified_read_finding(f):
                continue

            verified_reads.append(f)
            wc = f.get("working_call")
            if isinstance(wc, dict):
                for k, v in wc.items():
                    sv = str(v).strip()
                    if _re.match(r"^[A-Z]+-\d+", sv):
                        extracted_ids.append(sv)
                        if evidence is not None:
                            evidence.add(
                                sv,
                                TIER_RUNTIME,
                                f"mc5-working-call:{fn}",
                                classify_value_kind(sv, id_formats),
                                0.98,
                                fn,
                            )
                    elif _re.match(r"^ORD-", sv):
                        extracted_ids.append(sv)
                        if evidence is not None:
                            evidence.add(
                                sv,
                                TIER_RUNTIME,
                                f"mc5-working-call:{fn}",
                                classify_value_kind(sv, id_formats),
                                0.98,
                                fn,
                            )
                    elif _re.match(r"^ACCT-", sv):
                        extracted_ids.append(sv)
                        if evidence is not None:
                            evidence.add(
                                sv,
                                TIER_RUNTIME,
                                f"mc5-working-call:{fn}",
                                classify_value_kind(sv, id_formats),
                                0.98,
                                fn,
                            )
                    elif isinstance(v, (int, float)) and 1 <= v <= 100000:
                        iv = int(v)
                        _is_buffer_size = (
                            _re.search(r"(size|len|buf|count|capacity)", k, _re.I)
                            or (iv & (iv - 1) == 0 and iv >= 16 and iv <= 4096)
                        )
                        if not _is_buffer_size:
                            extracted_amounts.append(iv)

        extracted_ids = list(dict.fromkeys(extracted_ids))[:6]
        extracted_amounts = list(dict.fromkeys(extracted_amounts))[:4]
        if not extracted_amounts:
            extracted_amounts = [100, 500, 1000]
        evidence_ids = []
        available_id_kinds: set[str] = set()
        if evidence is not None:
            evidence_ids = [
                str(entry.value)
                for entry in evidence.query_all_string_ids(max_results=12)
                if str(entry.value).strip()
            ]
            available_id_kinds = set(evidence.available_id_kinds())
        evidence_ids = list(dict.fromkeys(evidence_ids))
        s03_surface = _load_s03_retry_surface(ctx)

        decision["analysis"]["verified_read_count"] = len(verified_reads)
        decision["analysis"]["extracted_ids"] = extracted_ids
        decision["analysis"]["evidence_ids"] = evidence_ids
        decision["analysis"]["extracted_amounts"] = extracted_amounts
        if s03_surface:
            decision["analysis"]["micro_coordinator_source"] = s03_surface.get("source")
            decision["analysis"]["s03_cluster_hints"] = list(s03_surface.get("cluster_hints") or [])[:6]

        write_args, write_selection = _build_write_arg_candidates(ctx)
        retry_plan = _build_write_retry_plan(
            write_selection,
            extracted_ids=extracted_ids,
            evidence_ids=evidence_ids,
            id_formats=id_formats,
            available_id_kinds_override=available_id_kinds,
        )
        if s03_surface:
            prior_order = {
                str(row.get("function") or ""): idx
                for idx, row in enumerate(list(s03_surface.get("retry_plan") or []))
                if str(row.get("function") or "").strip()
            }
            retry_plan.sort(
                key=lambda row: (
                    prior_order.get(str(row.get("function") or ""), 10_000),
                    -int(row.get("priority") or 0),
                    str(row.get("function") or ""),
                )
            )
        ordered_retry_functions = [row["function"] for row in retry_plan]
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
        decision["analysis"]["retry_plan"] = retry_plan[:6]
        decision["analysis"]["prerequisite_clusters"] = {
            row["cluster"]: sum(1 for item in retry_plan if item.get("cluster") == row["cluster"])
            for row in retry_plan
        }
        decision["analysis"]["retry_rationale"] = {
            "checkpoint_recommended_boundary": "s02_probe",
            "verified_read_count": len(verified_reads),
            "runtime_string_ids": extracted_ids[:6],
            "cross_stage_hint_source": s03_surface.get("source") if s03_surface else "",
            "top_retry_functions": ordered_retry_functions[:4],
        }

        if not extracted_ids and not evidence_ids:
            decision["action"] = "no_ids_extracted"
            decision["result"] = "no verified IDs to chain into write functions"
            _persist_mc_decision(ctx, "mc5-post-verification", decision)
            return

        decision["action"] = "chain_read_outputs_to_write_inputs"

        init_names = [inv["name"] for inv in ctx.invocables
                      if _re.search(r"init(ializ)?", inv["name"], _re.I)]
        init_seqs = []
        for init_fn in init_names:
            for mode in range(9):
                init_seqs.append({"fn": init_fn, "args": {"param_1": mode}})

        if _targeted_unlock_attempt(ctx, init_seqs, write_args, "mc5-post-verification"):
            with ctx._lock:
                ctx.live_findings.append({
                    "function": ctx.unlock_result.get("write_fn_tested", "unknown"),
                    "status": "success",
                    "finding": f"MC-5 chain: read outputs → write inputs (IDs: {extracted_ids})",
                    "working_call": ctx.unlock_result.get("write_fn_args"),
                })
            decision["result"] = (
                f"UNLOCKED by chaining verified read outputs "
                f"(IDs: {extracted_ids}) into write functions"
            )
        else:
            decision["result"] = (
                f"tried {len(extracted_ids)} verified IDs x {len(extracted_amounts)} "
                f"amounts x {len(init_seqs)} init sequences -- still blocked"
            )

    except Exception as exc:
        decision["result"] = f"error: {exc}"
        logger.debug("[%s] mc5-post-verification failed: %s", ctx.job_id, exc)

    _persist_mc_decision(ctx, "mc5-post-verification", decision)
