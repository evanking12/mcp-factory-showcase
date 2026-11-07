from __future__ import annotations

import json
import logging
import re as _re
import time
from typing import Any

import httpx

from api.infra.config import ARTIFACT_CONTAINER, OPENAI_API_KEY, OPENAI_EXPLORE_MODEL, OPENAI_MODEL
from api.analysis.cohesion import emit_contract_artifacts
from api.services.executor import _execute_tool, _execute_tool_traced
from api.infra.config import GUI_BRIDGE_URL
from api.pipeline.core.helpers import (
    _GAP_RESOLUTION_ENABLED,
    _WRITE_FN_RE,
    _build_tool_schemas,
    _merge_result_output_values,
    _set_explore_status,
    _snapshot_schema_stage,
    FINDING_DISCOVERED_STATUSES,
    FINDING_VERIFIED_STATUSES,
)
from api.pipeline.core.finding_status import is_functional_precondition_text
from api.pipeline.core.helpers import _MAX_EXPLORE_ROUNDS_PER_FUNCTION, _MAX_TOOL_CALLS_PER_FUNCTION, _SENTINEL_DEFAULTS
from api.pipeline.core.prompts import _build_explore_system_message, _generate_confidence_gaps
from api.infra.storage import (
    _append_executor_trace,
    _append_transcript,
    _download_blob,
    _get_job_status,
    _merge_invocables,
    _patch_finding,
    _persist_job_status,
    _register_invocables,
    _upload_to_blob,
)
from api.infra.telemetry import _openai_client

logger = logging.getLogger("mcp_factory.api")

_PLACEHOLDER_STRINGS = frozenset({
    "some_value", "output_pointer", "placeholder", "test", "example",
    "value", "unknown", "null", "none", "tbd", "todo", "fixme",
    "your_value", "insert_here", "change_me", "result_ptr",
})

_GAP_TRACE_BLOB = "gap_execution_trace.json"


def _probe_bridge_now() -> bool | None:
    if not GUI_BRIDGE_URL:
        return None
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=2.0, read=2.0, write=2.0, pool=2.0)) as client:
            response = client.get(f"{GUI_BRIDGE_URL.rstrip('/')}/health")
        return response.status_code == 200
    except Exception:
        return False


def _append_gap_trace(job_id: str, entry: dict) -> None:
    blob_name = f"{job_id}/{_GAP_TRACE_BLOB}"
    payload = {"ts": time.time(), **(entry or {})}
    try:
        try:
            existing = json.loads(_download_blob(ARTIFACT_CONTAINER, blob_name))
        except Exception:
            existing = []
        existing.append(payload)
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            blob_name,
            json.dumps(existing, indent=2).encode(),
        )
    except Exception as exc:
        logger.debug("[%s] gap_trace append failed: %s", job_id, exc)


def _execute_gap_tool_traced(
    job_id: str,
    inv: dict | None,
    args: dict,
    *,
    stage: str,
    target_function: str,
    note: str,
) -> tuple[str, dict | None]:
    if not inv:
        result = "Tool not found."
        _append_gap_trace(
            job_id,
            {
                "stage": stage,
                "target_function": target_function,
                "tool": "",
                "args": args,
                "note": note,
                "bridge_before": _probe_bridge_now(),
                "bridge_after": _probe_bridge_now(),
                "result_excerpt": result[:200],
                "trace": None,
            },
        )
        return result, None

    bridge_before = _probe_bridge_now()
    traced = _execute_tool_traced(inv, args)
    result = traced["result_str"]
    trace = traced.get("trace")
    bridge_after = _probe_bridge_now()
    _append_gap_trace(
        job_id,
        {
            "stage": stage,
            "target_function": target_function,
            "tool": inv.get("name", ""),
            "args": args,
            "note": note,
            "bridge_before": bridge_before,
            "bridge_after": bridge_after,
            "result_excerpt": str(result)[:200],
            "trace": trace,
        },
    )
    return result, trace


def _has_placeholder_args(args: dict) -> bool:
    """Reject args that contain obvious LLM placeholder strings."""
    for v in args.values():
        if isinstance(v, str) and v.strip().lower() in _PLACEHOLDER_STRINGS:
            return True
    return False


def _build_gap_observed_success_patch(
    fn_name: str,
    working_call: dict,
    *,
    source: str,
) -> dict:
    return {
        "working_call": working_call,
        "status": "partial",
        "finding": (
            f"{source}: observed {fn_name}({working_call}) return 0 during probing; "
            "replay validation still required."
        ),
        "notes": (
            "Observed probe success superseded the earlier exhaustion fallback; "
            "replay validation still required before confirmed success."
        ),
        "stop_reason": "gap_observed_success_pending_validation",
    }


def _parse_gap_return_value(result_text: str) -> int | None:
    match = _re.search(r"Returned:\s*(-?\d+)", str(result_text or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _build_gap_direct_target_truth(
    function_name: str,
    working_call: dict[str, Any] | None,
    *,
    source: str,
    phase: str,
    result_text: str = "",
    verification: str = "",
) -> dict[str, Any]:
    truth: dict[str, Any] = {
        "function": str(function_name or "").strip(),
        "source": str(source or "").strip(),
        "phase": str(phase or "").strip(),
    }
    if isinstance(working_call, dict):
        truth["working_call"] = dict(working_call)
    return_value = _parse_gap_return_value(result_text or "")
    if return_value is not None:
        truth["return_value"] = int(return_value & 0xFFFFFFFF)
    if verification:
        truth["verification"] = str(verification or "").strip()
    elif return_value == 0:
        truth["verification"] = "verified"
    return truth


def _build_gap_verified_success_patch(
    fn_name: str,
    working_call: dict,
    *,
    source: str,
    truth_source: str,
    result_text: str,
) -> dict:
    return_value = _parse_gap_return_value(result_text or "")
    rendered_return = (return_value & 0xFFFFFFFF) if return_value is not None else "unknown"
    return {
        "working_call": dict(working_call or {}),
        "status": "verified_success",
        "finding": f"{source}: replay verified {fn_name}({working_call}) with return {rendered_return}.",
        "notes": "Observed probe success survived immediate same-branch replay verification.",
        "verification": "verified",
        "stop_reason": "gap_observed_success_verified",
        "direct_target_truth": _build_gap_direct_target_truth(
            fn_name,
            working_call,
            source=truth_source,
            phase="verify",
            result_text=result_text,
            verification="verified",
        ),
    }


def _build_gap_verification_downgrade_patch(
    fn_name: str,
    working_call: dict | None,
    return_value: int,
    *,
    sentinel_meaning: str,
    source: str,
) -> dict:
    reason = (
        f"{source}: replay rejected {fn_name}({working_call}) with return {return_value}"
        + (f" ({sentinel_meaning})" if sentinel_meaning else "")
    )
    status = "functional_precondition_unmet" if is_functional_precondition_text(sentinel_meaning) else "failure"
    return {
        "working_call": None,
        "status": status,
        "finding": reason,
        "verification": "state_drift",
        "direct_target_truth_rejected_reason": reason,
        "stop_reason": "gap_verify_state_drift",
    }


def _resolve_gap_observed_success(
    job_id: str,
    fn_name: str,
    inv: dict | None,
    working_call: dict,
    *,
    source: str,
    truth_source: str,
    stage: str,
    sentinels: dict,
) -> dict:
    verify_result, _ = _execute_gap_tool_traced(
        job_id,
        inv,
        working_call,
        stage=stage,
        target_function=fn_name,
        note="gap_verify_observed_success",
    )
    verify_return = _parse_gap_return_value(verify_result or "")
    if verify_return is not None:
        verify_unsigned = verify_return & 0xFFFFFFFF
        if verify_unsigned not in sentinels and verify_unsigned <= 0xFFFFFFF0:
            return _build_gap_verified_success_patch(
                fn_name,
                working_call,
                source=source,
                truth_source=truth_source,
                result_text=str(verify_result or ""),
            )
        sentinel_meaning = str(sentinels.get(verify_unsigned) or "")
        return _build_gap_verification_downgrade_patch(
            fn_name,
            working_call,
            verify_unsigned,
            sentinel_meaning=sentinel_meaning,
            source=f"{source} verify",
        )
    return {
        "working_call": None,
        "status": "failure",
        "finding": (
            f"{source} verify: replay for {fn_name}({working_call}) did not produce a parseable return value."
        ),
        "verification": "state_drift",
        "direct_target_truth_rejected_reason": (
            f"{source} verify: replay for {fn_name}({working_call}) did not produce a parseable return value."
        ),
        "stop_reason": "gap_verify_state_drift",
    }


def _attempt_gap_resolution(
    job_id: str,
    invocables: list[dict],
    client,
    model: str,
    sentinels: dict,
    vocab: dict,
    use_cases_text: str,
    inv_map: dict,
    tool_schemas: list[dict],
    ctx=None,
) -> None:
    """Targeted second-pass re-probe of functions that failed every probe in the main loop."""
    from api.infra.storage import _load_findings

    # Inherit runtime settings from the explore job so gap resolution respects
    # the same floor / max-rounds / max-tool-calls the user configured in the UI.
    _job_runtime = (_get_job_status(job_id) or {}).get("explore_runtime") or {}
    _max_rounds = int(_job_runtime.get("max_rounds") or _MAX_EXPLORE_ROUNDS_PER_FUNCTION)
    _max_tool_calls = int(_job_runtime.get("max_tool_calls") or _MAX_TOOL_CALLS_PER_FUNCTION)

    all_findings = _load_findings(job_id)

    failed_invs = [
        inv for inv in invocables
        if not any(
            f.get("function") == inv["name"]
            and (str(f.get("status") or "").strip().lower() in FINDING_DISCOVERED_STATUSES
                 or str(f.get("status_canonical") or "").strip().lower() in FINDING_DISCOVERED_STATUSES)
            for f in all_findings
        )
    ]
    if not failed_invs:
        logger.info("[%s] gap_resolution: no failed functions — skipping", job_id)
        return

    fn_list = [inv["name"] for inv in failed_invs]
    logger.info("[%s] gap_resolution: targeted retry of %d function(s): %s", job_id, len(failed_invs), fn_list)

    successful_findings = [
        f
        for f in all_findings
        if str(f.get("status") or "").strip().lower() in FINDING_VERIFIED_STATUSES
        and f.get("working_call")
    ]
    kb_lines = [f"  - {sf['function']}({sf['working_call']})" for sf in successful_findings[:6]]
    kb_block = (
        "\nKNOWN-GOOD CALLS (reuse these IDs/values as inputs):\n" + "\n".join(kb_lines) + "\n"
    ) if kb_lines else ""

    _is_write_fn = lambda fn: bool(_WRITE_FN_RE.search(fn))

    _init_invs = (ctx.init_invocables if ctx and ctx.init_invocables else [
        inv for inv in invocables
        if _re.search(r"(init(ializ)?|startup|start|setup|open|login|logon|connect)",
                      inv["name"], _re.I)
    ])

    for i, inv in enumerate(failed_invs):
        fn_name = inv["name"]
        _set_explore_status(job_id, i, len(failed_invs), f"Gap resolution: retrying {fn_name}…")

        # ── State baseline restoration ──────────────────────────────────
        # Reinitialize DLL state before each write function retry to restore
        # depleted balances/points from earlier probes (BUG-021).
        # Also replay known-good write calls to build prerequisite state
        # (e.g., ProcessPayment earns loyalty points that RedeemLoyaltyPoints
        # needs — a generic cross-function dependency pattern).
        if _is_write_fn(fn_name):
            for init_inv in _init_invs:
                try:
                    _execute_gap_tool_traced(
                        job_id,
                        init_inv,
                        {},
                        stage="s06_gaps",
                        target_function=fn_name,
                        note="state_restore_init",
                    )
                except Exception:
                    pass
            if ctx is not None and ctx.unlock_result.get("unlocked"):
                for step in (ctx.unlock_result.get("sequence") or []):
                    step_inv = inv_map.get(step.get("fn", ""))
                    if step_inv:
                        try:
                            _execute_gap_tool_traced(
                                job_id,
                                step_inv,
                                step.get("args", {}),
                                stage="s06_gaps",
                                target_function=fn_name,
                                note="state_restore_unlock_sequence",
                            )
                        except Exception:
                            pass
            # Replay known-good write calls to build prerequisite state.
            # Use ALL known customer IDs so points/balances accrue for every
            # entity the target function might be called with.
            _known_ids = set()
            if ctx is not None and ctx.vocab and ctx.vocab.get("id_formats"):
                _known_ids = {str(v) for v in ctx.vocab["id_formats"] if v}
            for sf in successful_findings:
                sf_wc = sf.get("working_call")
                if isinstance(sf_wc, dict):
                    for v in sf_wc.values():
                        if isinstance(v, str) and _re.match(r"^[A-Z]+-", v):
                            _known_ids.add(v)
            _known_ids_list = sorted(_known_ids)[:4] or ["CUST-001"]

            _prereq_call_budget = 12
            _prereq_calls_made = 0
            for sf in successful_findings:
                if _prereq_calls_made >= _prereq_call_budget:
                    break
                sf_fn = sf.get("function", "")
                if sf_fn == fn_name or not _is_write_fn(sf_fn):
                    continue
                sf_inv = inv_map.get(sf_fn)
                if not sf_inv:
                    continue
                sf_wc = sf.get("working_call")
                if not isinstance(sf_wc, dict):
                    continue
                _str_param_keys = [
                    k for k, v in sf_wc.items() if isinstance(v, str)
                ]
                for _kid in _known_ids_list:
                    if _prereq_calls_made >= _prereq_call_budget:
                        break
                    prereq_args = dict(sf_wc)
                    for k, v in prereq_args.items():
                        if isinstance(v, int) and v <= 1:
                            prereq_args[k] = 100
                    if _str_param_keys:
                        prereq_args[_str_param_keys[0]] = _kid
                    try:
                        _execute_gap_tool_traced(
                            job_id,
                            sf_inv,
                            prereq_args,
                            stage="s06_gaps",
                            target_function=fn_name,
                            note="state_restore_prereq_write",
                        )
                    except Exception:
                        pass
                    _prereq_calls_made += 1
            logger.info("[%s] gap_resolution: state baseline + prereq writes restored for %s",
                        job_id, fn_name)

        prev_finding = next((f for f in reversed(all_findings) if f.get("function") == fn_name), None)
        prev_ctx = (
            f"Previous attempt: {prev_finding.get('finding', 'no finding')}.\n"
            if prev_finding else ""
        )

        _write_unlock_ctx = ""
        if ctx is not None and ctx.write_unlock_block and _is_write_fn(fn_name):
            _write_unlock_ctx = (
                f"\n{ctx.write_unlock_block}\n"
                "CRITICAL: You MUST execute the EXACT prerequisite sequence above "
                "BEFORE calling this function. The unlock code is cryptographic.\n"
            )

        _init_names = [ii["name"] for ii in _init_invs]
        _init_hint = (
            f"Init functions available: {', '.join(_init_names)}. "
            "Call them FIRST to restore DLL state before each write attempt.\n"
        ) if _init_names else ""

        _prereq_write_hint = ""
        if _is_write_fn(fn_name) and successful_findings:
            _prereq_writes = [
                sf for sf in successful_findings
                if _is_write_fn(sf.get("function", "")) and sf.get("function") != fn_name
            ]
            if _prereq_writes:
                _pw_lines = [
                    f"  - {pw['function']}({pw['working_call']})"
                    for pw in _prereq_writes[:4]
                ]
                _prereq_write_hint = (
                    "PREREQUISITE STATE: This function may depend on side-effects of "
                    "other write functions. Before calling this function, you should "
                    "call these known-good write functions (with moderate amounts like "
                    "100) to build up prerequisite state:\n"
                    + "\n".join(_pw_lines)
                    + "\nFor example, a payment function may earn loyalty points that "
                    "a redemption function needs.\n"
                )

        _write_amount_hint = ""
        if _is_write_fn(fn_name):
            _write_amount_hint = (
                "IMPORTANT: For numeric parameters (amounts, quantities), start with "
                "the SMALLEST valid value (1, then 10, then 50). DLL state may have "
                "been depleted by prior calls — small values avoid exceeding limits. "
                "Do NOT try large values like 1000 or 10000 first.\n"
            )

        sys_msg = _build_explore_system_message(
            invocables, _load_findings(job_id),
            sentinels=sentinels, vocab=vocab, use_cases=use_cases_text,
        )
        conversation = [
            sys_msg,
            {
                "role": "user",
                "content": (
                    f"SECOND-PASS RETRY for '{fn_name}'.\n"
                    f"{prev_ctx}"
                    f"{_write_unlock_ctx}"
                    f"{_init_hint}"
                    f"{_prereq_write_hint}"
                    f"{_write_amount_hint}"
                    f"{kb_block}\n"
                    "This function failed every probe in the first pass. "
                    "Try these strategies in order:\n"
                    "1. Call the init function(s) FIRST to restore DLL state, then call "
                    "any unlock function with the EXACT args from the KNOWN-GOOD CALLS "
                    "or EXACT SEQUENCE above.\n"
                    "2. After the prerequisite sequence, call this function with "
                    "real customer/order IDs from the KNOWN-GOOD CALLS above.\n"
                    "3. For numeric params: try 1, 10, 50, 100 (small values first).\n"
                    "4. For string params: try known-good ID formats first.\n"
                    "5. If you get an error suggesting insufficient balance/points, "
                    "re-call the init function to reset state, then retry with amount=1.\n"
                    "Goal: find ANY call that returns 0. Once found, call record_finding with "
                    "status='verified_success' and working_call set to the exact args that worked.\n"
                    "If still failing after all strategies, call record_finding with "
                    "status='failure' and note the exact error code(s) observed. "
                    "If the sentinel clearly indicates unmet business state (insufficient balance/points), "
                    "use status='functional_precondition_unmet'."
                ),
            },
        ]

        _observed_successes: list[dict] = []
        _p_lookup = {p.get("name", ""): p for p in (inv.get("parameters") or [])}
        _fn_tool_call_count = 0

        for _round in range(_max_rounds):
            if _fn_tool_call_count >= _max_tool_calls:
                logger.info("[%s] gap_resolution: %s hit tool-call cap (%d)",
                            job_id, fn_name, _max_tool_calls)
                break
            try:
                from typing import cast, Any as _Any
                response = client.chat.completions.create(
                    model=model,
                    messages=conversation,
                    tools=cast(_Any, tool_schemas),
                    tool_choice="auto",
                    temperature=0,
                    timeout=90.0,
                )
            except Exception as exc:
                logger.warning("[%s] gap_resolution: OpenAI call failed for %s round %d: %s",
                               job_id, fn_name, _round, exc)
                break

            msg = response.choices[0].message
            if not msg.tool_calls:
                break

            conversation.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,  # type: ignore[union-attr]
                            "arguments": tc.function.arguments,  # type: ignore[union-attr]
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                if _fn_tool_call_count >= _max_tool_calls:
                    break
                _fn = tc.function  # type: ignore[union-attr]
                tc_name = _fn.name
                try:
                    tc_args = json.loads(_fn.arguments)
                except json.JSONDecodeError:
                    tc_args = {}

                tc_inv = inv_map.get(tc_name)
                if tc_inv:
                    tool_result, _ = _execute_gap_tool_traced(
                        job_id,
                        tc_inv,
                        tc_args,
                        stage="s06_gaps",
                        target_function=fn_name,
                        note="gap_round_tool_call",
                    )
                else:
                    tool_result = f"Tool '{tc_name}' not found."
                _fn_tool_call_count += 1

                if tc_name == fn_name:
                    _ret_m = _re.match(r"Returned:\s*(\d+)", tool_result or "")
                    if _ret_m and int(_ret_m.group(1)) == 0:
                        _out_bases = frozenset({
                            "undefined", "undefined2", "undefined4", "undefined8",
                            "uint", "uint32_t", "int", "int32_t", "dword",
                            "ulong", "uint4", "uint8", "long", "ulong32",
                        })
                        _clean: dict = {}
                        for _k, _v in tc_args.items():
                            _p = _p_lookup.get(_k, {})
                            _pt = _p.get("type", "").lower().replace("const ", "").strip().rstrip(" *")
                            _is_out = "*" in _p.get("type", "") and _pt in _out_bases
                            _pt_is_string = _pt in ("byte", "char", "string", "str")
                            if not _is_out and (not _p.get("direction") == "out" or _pt_is_string):
                                _clean[_k] = _v
                        _clean = _merge_result_output_values(_clean, tool_result, _p_lookup)
                        if not _has_placeholder_args(_clean):
                            _observed_successes.append(_clean)
                        else:
                            logger.info("[%s] gap_resolution: %s returned 0 but args contain placeholders — rejected: %s",
                                        job_id, fn_name, _clean)

                logger.info("[%s] gap_resolution: tool=%s result=%s", job_id, tc_name, str(tool_result)[:120])
                conversation.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})

        if _observed_successes:
            success_patch = _resolve_gap_observed_success(
                job_id,
                fn_name,
                inv_map.get(fn_name),
                _observed_successes[0],
                source="Gap resolution",
                truth_source="s06_gap_resolution",
                stage="s06_gaps",
                sentinels=sentinels,
            )
            _patch_finding(job_id, fn_name, success_patch)
            if ctx is not None:
                with ctx._lock:
                    ctx.live_findings.append({"function": fn_name, **success_patch})
            logger.info("[%s] gap_resolution: resolved %s → %s", job_id, fn_name, success_patch.get("status"))
        else:
            _cur = _load_findings(job_id)
            _ff = next((f for f in reversed(_cur) if f.get("function") == fn_name), None)
            if _ff and _ff.get("working_call") is not None:
                _vi = inv_map.get(fn_name)
                if _vi:
                    try:
                        _vr, _ = _execute_gap_tool_traced(
                            job_id,
                            _vi,
                            _ff["working_call"],
                            stage="s06_gaps",
                            target_function=fn_name,
                            note="gap_verify_existing_working_call",
                        )
                        _vm = _re.match(r"Returned:\s*(\d+)", _vr or "")
                        if _vm:
                            _vret = int(_vm.group(1))
                            if _vret not in sentinels and _vret <= 0xFFFFFFF0:
                                _patch_finding(job_id, fn_name, {
                                    "status": "verified_success",
                                    "finding": f"Gap resolution verify: {fn_name}({_ff['working_call']}) returned {_vret}",
                                })
                                if ctx is not None:
                                    with ctx._lock:
                                        ctx.live_findings.append({
                                            "function": fn_name,
                                            "status": "verified_success",
                                            "finding": f"Gap resolution verify: {fn_name}({_ff['working_call']}) returned {_vret}",
                                            "working_call": _ff["working_call"],
                                        })
                                logger.info("[%s] gap_resolution: resolved %s via verification", job_id, fn_name)
                            else:
                                _meaning = str(sentinels.get(_vret & 0xFFFFFFFF) or "")
                                _patch_finding(
                                    job_id,
                                    fn_name,
                                    _build_gap_verification_downgrade_patch(
                                        fn_name,
                                        _ff["working_call"],
                                        _vret,
                                        sentinel_meaning=_meaning,
                                        source="Gap resolution verify",
                                    ),
                                )
                    except Exception as _ve:
                        logger.debug("[%s] gap_resolution: verify failed for %s: %s", job_id, fn_name, _ve)


def _run_gap_answer_mini_sessions(job_id: str, invocables: list[dict], max_mini_session_rounds: int = 50) -> None:
    """Targeted mini-sessions driven by user gap answers."""
    from api.infra.storage import _load_findings

    if not _GAP_RESOLUTION_ENABLED:
        logger.info("[%s] gap_mini_sessions: skipped (EXPLORE_ENABLE_GAP_RESOLUTION=0)", job_id)
        return

    if not OPENAI_API_KEY:
        return

    try:
        vocab: dict = {}
        try:
            raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/vocab.json")
            vocab = json.loads(raw)
        except Exception:
            pass

        gap_answers: dict = vocab.get("gap_answers") or {}
        targeted = {fn: ans for fn, ans in gap_answers.items() if fn != "general" and (ans or "").strip()}
        if not targeted:
            logger.info("[%s] gap_mini_sessions: no function-specific answers — skipping", job_id)
            return

        _snapshot_schema_stage(job_id, "mcp_schema_pre_mini_session.json")

        client = _openai_client()
        model = OPENAI_EXPLORE_MODEL or OPENAI_MODEL

        _job_meta = _get_job_status(job_id) or {}
        _use_cases_text = _job_meta.get("use_cases", "")
        sentinels = _SENTINEL_DEFAULTS

        # Inherit runtime settings so mini-sessions respect the same caps the user set.
        _job_runtime = _job_meta.get("explore_runtime") or {}
        _max_rounds = int(_job_runtime.get("max_rounds") or _MAX_EXPLORE_ROUNDS_PER_FUNCTION)
        _max_tool_calls = int(_job_runtime.get("max_tool_calls") or _MAX_TOOL_CALLS_PER_FUNCTION)

        inv_map: dict[str, dict] = {inv["name"]: inv for inv in invocables}

        # COH-2: Merge invocables so enrich_invocable / _patch_invocable can
        # resolve function names during gap mini-sessions.  Use merge (not
        # replace) so functions outside this subset remain in the registry and
        # run_generate continues to produce a complete schema.
        _merge_invocables(job_id, invocables)

        inv_map["enrich_invocable"] = {
            "name": "enrich_invocable", "source_type": "enrich", "_job_id": job_id,
            "execution": {"method": "enrich"}, "parameters": [],
        }
        inv_map["record_finding"] = {
            "name": "record_finding", "source_type": "findings", "_job_id": job_id,
            "execution": {"method": "findings"}, "parameters": [],
        }
        tool_schemas = _build_tool_schemas(invocables)

        explore_questions = _job_meta.get("explore_questions") or []

        logger.info("[%s] gap_mini_sessions: %d answered function(s) to retry: %s",
                    job_id, len(targeted), list(targeted))

        for i, (fn_name, answer_text) in enumerate(targeted.items()):
            inv = inv_map.get(fn_name)
            if not inv:
                logger.debug("[%s] gap_mini_sessions: no invocable for %s — skipping", job_id, fn_name)
                continue

            _set_explore_status(job_id, i, len(targeted), f"Gap mini-session: {fn_name}…")
            logger.info("[%s] gap_mini_sessions: starting mini-session for %s", job_id, fn_name)

            all_findings = _load_findings(job_id)
            prev_finding = next((f for f in reversed(all_findings) if f.get("function") == fn_name), None)
            prev_ctx = (
                f"Previous attempt: {prev_finding.get('finding', 'no finding')}.\n"
                if prev_finding else ""
            )

            fn_gap = next((g for g in explore_questions if g.get("function") == fn_name), {})
            technical_q = fn_gap.get("technical_question", "")
            technical_ctx = f"Technical context: {technical_q}\n" if technical_q else ""

            sys_msg = _build_explore_system_message(
                invocables, all_findings,
                sentinels=sentinels, vocab=vocab, use_cases=_use_cases_text,
            )
            conversation = [
                sys_msg,
                {
                    "role": "user",
                    "content": (
                        f"DOMAIN EXPERT ANSWER for '{fn_name}'.\n"
                        f"{technical_ctx}"
                        f"{prev_ctx}"
                        f"A domain expert answered: {answer_text!r}\n\n"
                        f"Use this information to re-probe '{fn_name}' now. "
                        "Apply the expert's answer to determine the correct prerequisite calls, "
                        "argument formats, or conditions needed for a successful call. "
                        "Goal: find a call that returns 0 (success). "
                        "When done, call enrich_invocable and record_finding with what you found. "
                        "If every probe still fails after applying the answer, call "
                        "record_finding(status='failure') with exact codes seen. "
                        "If business-state sentinels indicate unmet preconditions, use "
                        "record_finding(status='functional_precondition_unmet')."
                    ),
                },
            ]

            # Reasoning artifact: record expert answer interpretation inputs before the mini-session.
            # Writes to evidence/stage-05-gap-resolution/expert-answer-interpretation.json.
            try:
                _expert_entry = {
                    "function": fn_name,
                    "answer_text": answer_text,
                    "technical_question": technical_q,
                    "prev_finding": prev_finding.get("finding") if prev_finding else None,
                    "prev_status": prev_finding.get("status") if prev_finding else None,
                }
                _expert_blob = (
                    f"{job_id}/evidence/stage-05-gap-resolution/expert-answer-interpretation.json"
                )
                for _rmw_attempt in range(3):
                    try:
                        try:
                            _existing_exp = json.loads(
                                _download_blob(ARTIFACT_CONTAINER, _expert_blob)
                            )
                        except Exception:
                            _existing_exp = []
                        _existing_exp.append(_expert_entry)
                        _upload_to_blob(
                            ARTIFACT_CONTAINER, _expert_blob,
                            json.dumps(_existing_exp, indent=2).encode(),
                        )
                        break
                    except Exception:
                        if _rmw_attempt < 2:
                            time.sleep(0.1 * (2 ** _rmw_attempt))
            except Exception as _eae:
                logger.debug(
                    "[%s] gap_mini_sessions: expert-answer-interpretation write failed for %s: %s",
                    job_id, fn_name, _eae,
                )

            _p_lookup = {p.get("name", ""): p for p in (inv.get("parameters") or [])}
            _observed_successes: list[dict] = []
            _mini_tool_log: list[dict] = []
            _mini_traces: list[dict] = []
            _fn_tool_call_count = 0
            _fn_start = time.time()

            for _round in range(min(_max_rounds, max_mini_session_rounds)):
                if time.time() - _fn_start > 300:
                    logger.warning("[%s] gap_mini_sessions: %s exceeded 300s timeout — aborting",
                                   job_id, fn_name)
                    break
                if _fn_tool_call_count >= _max_tool_calls:
                    logger.info("[%s] gap_mini_sessions: %s hit tool-call cap (%d)",
                                job_id, fn_name, _max_tool_calls)
                    break
                try:
                    from typing import cast, Any as _Any
                    response = client.chat.completions.create(
                        model=model,
                        messages=conversation,
                        tools=cast(_Any, tool_schemas),
                        tool_choice="auto",
                        temperature=0,
                        timeout=90.0,
                    )
                except Exception as exc:
                    logger.warning("[%s] gap_mini_sessions: OpenAI call failed for %s round %d: %s",
                                   job_id, fn_name, _round, exc)
                    break

                msg = response.choices[0].message
                if not msg.tool_calls:
                    break

                conversation.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,  # type: ignore[union-attr]
                                "arguments": tc.function.arguments,  # type: ignore[union-attr]
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })

                _round_reasoning = (msg.content or "").strip()
                _first_in_round = True
                for tc in msg.tool_calls:
                    if _fn_tool_call_count >= _max_tool_calls:
                        break
                    _fn = tc.function  # type: ignore[union-attr]
                    tc_name = _fn.name
                    try:
                        tc_args = json.loads(_fn.arguments)
                    except json.JSONDecodeError:
                        tc_args = {}

                    tc_inv = inv_map.get(tc_name)
                    if tc_inv:
                        _traced = _execute_tool_traced(tc_inv, tc_args)
                        tool_result = _traced["result_str"]
                        _tc_trace = _traced.get("trace")
                    else:
                        tool_result = f"Tool '{tc_name}' not found."
                        _tc_trace = None
                    _fn_tool_call_count += 1

                    _mini_tool_log.append({
                        "call": tc_name,
                        "args": tc_args,
                        "result": tool_result,
                        "trace": _tc_trace,
                        "reasoning": _round_reasoning if _first_in_round else None,
                    })
                    if _tc_trace:
                        _mini_traces.append(_tc_trace)
                    _first_in_round = False

                    if tc_name == fn_name:
                        _ret_m = _re.match(r"Returned:\s*(\d+)", tool_result or "")
                        if _ret_m and int(_ret_m.group(1)) == 0:
                            _out_bases = frozenset({
                                "undefined", "undefined2", "undefined4", "undefined8",
                                "uint", "uint32_t", "int", "int32_t", "dword",
                                "ulong", "uint4", "uint8", "long", "ulong32",
                            })
                            _clean: dict = {}
                            for _k, _v in tc_args.items():
                                _p = _p_lookup.get(_k, {})
                                _pt = _p.get("type", "").lower().replace("const ", "").strip().rstrip(" *")
                                _is_out = "*" in _p.get("type", "") and _pt in _out_bases
                                _pt_is_string = _pt in ("byte", "char", "string", "str")
                                if not _is_out and (not _p.get("direction") == "out" or _pt_is_string):
                                    _clean[_k] = _v
                            _clean = _merge_result_output_values(_clean, tool_result, _p_lookup)
                            if not _has_placeholder_args(_clean):
                                _observed_successes.append(_clean)
                            else:
                                logger.info("[%s] gap_mini_sessions: %s returned 0 but args contain placeholders — rejected",
                                            job_id, fn_name)

                    logger.info("[%s] gap_mini_sessions: tool=%s result=%s",
                                job_id, tc_name, str(tool_result)[:120])
                    conversation.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})

            # Reasoning artifact: extract per-round reasoning from mini-session tool log.
            # Writes to evidence/stage-05-gap-resolution/mini-session-round-reasoning.json.
            try:
                _mini_reasoning_entries = [
                    {
                        "function": fn_name,
                        "call": e["call"],
                        "args": e.get("args", {}),
                        "reasoning": e.get("reasoning") or "",
                        "result_excerpt": str(e.get("result", ""))[:200],
                    }
                    for e in _mini_tool_log
                    if e.get("reasoning")
                ]
                if _mini_reasoning_entries:
                    _mini_reasoning_blob = (
                        f"{job_id}/evidence/stage-05-gap-resolution/"
                        "mini-session-round-reasoning.json"
                    )
                    for _rmw_attempt in range(3):
                        try:
                            try:
                                _existing_mr = json.loads(
                                    _download_blob(ARTIFACT_CONTAINER, _mini_reasoning_blob)
                                )
                            except Exception:
                                _existing_mr = []
                            _existing_mr.extend(_mini_reasoning_entries)
                            _upload_to_blob(
                                ARTIFACT_CONTAINER, _mini_reasoning_blob,
                                json.dumps(_existing_mr, indent=2).encode(),
                            )
                            break
                        except Exception:
                            if _rmw_attempt < 2:
                                time.sleep(0.1 * (2 ** _rmw_attempt))
            except Exception as _mrre:
                logger.debug(
                    "[%s] gap_mini_sessions: mini-session-round-reasoning write failed for %s: %s",
                    job_id, fn_name, _mrre,
                )

            try:
                _mini_user_msg = (
                    f"[GAP MINI-SESSION: {fn_name}]\n"
                    f"Domain expert answer: {answer_text!r}\n"
                    f"{technical_ctx}"
                    f"{prev_ctx}"
                )
                _mini_final = "(mini-session complete)"
                for _turn in reversed(conversation):
                    if _turn.get("role") == "assistant" and _turn.get("content"):
                        _mini_final = _turn["content"]
                        break
                _append_transcript(job_id, _mini_user_msg, _mini_final, _mini_tool_log,
                                   transcript_blob="mini_session_transcript.txt")
                if _mini_traces:
                    _append_executor_trace(job_id, _mini_traces)
            except Exception as _tr_e:
                logger.debug("[%s] gap_mini_sessions: transcript write failed for %s: %s",
                              job_id, fn_name, _tr_e)

            if _observed_successes:
                success_patch = _resolve_gap_observed_success(
                    job_id,
                    fn_name,
                    inv_map.get(fn_name),
                    _observed_successes[0],
                    source="Gap mini-session",
                    truth_source="s06_gap_mini_session",
                    stage="s06_gaps",
                    sentinels=sentinels,
                )
                _patch_finding(job_id, fn_name, success_patch)
                logger.info("[%s] gap_mini_sessions: resolved %s → %s",
                            job_id, fn_name, success_patch.get("status"))
            else:
                _cur = _load_findings(job_id)
                _ff = next((f for f in reversed(_cur) if f.get("function") == fn_name), None)
                if _ff and _ff.get("working_call") is not None:
                    _vi = inv_map.get(fn_name)
                    if _vi:
                        try:
                            _vr = _execute_tool(_vi, _ff["working_call"])
                            _vm = _re.match(r"Returned:\s*(\d+)", _vr or "")
                            if _vm:
                                _vret = int(_vm.group(1))
                                if _vret not in sentinels and _vret <= 0xFFFFFFF0:
                                    _patch_finding(job_id, fn_name, {
                                        "status": "verified_success",
                                        "finding": f"Gap mini-session verify: {fn_name}({_ff['working_call']}) returned {_vret}",
                                    })
                                else:
                                    _meaning = str(sentinels.get(_vret & 0xFFFFFFFF) or "")
                                    _patch_finding(
                                        job_id,
                                        fn_name,
                                        _build_gap_verification_downgrade_patch(
                                            fn_name,
                                            _ff["working_call"],
                                            _vret,
                                            sentinel_meaning=_meaning,
                                            source="Gap mini-session verify",
                                        ),
                                    )
                        except Exception as _ve:
                            logger.debug("[%s] gap_mini_sessions: verify failed for %s: %s",
                                         job_id, fn_name, _ve)

        try:
            logger.info("[%s] gap_mini_sessions: re-generating confidence gaps after mini-sessions…", job_id)
            _set_explore_status(job_id, len(targeted), len(targeted), "Re-assessing gaps…")
            updated_findings = _load_findings(job_id)
            new_gaps = _generate_confidence_gaps(client, model, updated_findings, invocables)
            resolved = {
                f.get("function")
                for f in updated_findings
                if f.get("status") in FINDING_DISCOVERED_STATUSES
                or f.get("status_canonical") in FINDING_DISCOVERED_STATUSES
            }
            new_gaps = [g for g in new_gaps if g.get("function") not in resolved]
            _gap_current = _get_job_status(job_id) or {}
            _persist_job_status(job_id, {**_gap_current, "explore_questions": new_gaps}, sync=True)
            logger.info("[%s] gap_mini_sessions: %d gap(s) remain after re-assessment", job_id, len(new_gaps))
        except Exception as _re_e:
            logger.debug("[%s] gap_mini_sessions: re-gap generation failed: %s", job_id, _re_e)

        try:
            _targeted_fns = set(targeted)
            _grl_findings = _load_findings(job_id)
            _grl = [
                {
                    "function": f.get("function"),
                    "status": f.get("status"),
                    "working_call": f.get("working_call"),
                    "confidence": f.get("confidence"),
                    "successes": f.get("successes", 0),
                    "attempts": f.get("attempts", 0),
                }
                for f in _grl_findings
                if f.get("function") in _targeted_fns
            ]
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{job_id}/gap_resolution_log.json",
                json.dumps(_grl, indent=2).encode(),
            )
            logger.info("[%s] gap_mini_sessions: gap_resolution_log written (%d entries)", job_id, len(_grl))
        except Exception as _grl_e:
            logger.debug("[%s] gap_mini_sessions: gap_resolution_log upload failed: %s", job_id, _grl_e)

        _snapshot_schema_stage(job_id, "mcp_schema_post_mini_session.json")

        _cur_status = _get_job_status(job_id) or {}
        # AC-4: Use clarification closure gate — only mark "done" if no
        # unanswered questions remain after mini-session resolution.
        _open_q = _cur_status.get("explore_questions") or []
        _has_unanswered = any(
            isinstance(q, dict)
            and not (bool(q.get("answered")) or bool(str(q.get("answer") or "").strip()))
            for q in _open_q
        )
        _final_phase = "awaiting_clarification" if _has_unanswered else "done"
        _persist_job_status(
            job_id,
            {**_cur_status, "explore_phase": _final_phase, "updated_at": time.time()},
            sync=True,
        )

        # Emit machine-first contract artifacts for answer-gaps-triggered runs
        # so strict snapshot validation has parity with explore-worker finalize.
        try:
            emit_contract_artifacts(job_id)
        except Exception as _coh_e:
            logger.debug("[%s] gap_mini_sessions: cohesion artifact emission failed: %s", job_id, _coh_e)

        logger.info("[%s] gap_mini_sessions: complete (phase=%s)", job_id, _final_phase)

    except Exception as exc:
        logger.error("[%s] gap_mini_sessions: fatal error: %s", job_id, exc)
