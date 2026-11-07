"""api.pipeline.s01_unlock.write_unlock – Write-unlock probe (Phase 1).

Attempts to flip the DLL from read-only to write-ready by discovering
the correct initialization sequence and unlock codes.

Strategy:
  0a. LLM code reasoning: ask a strong model to analyze decompiled C and
      produce structured unlock strategies (generic — works on any DLL)
  0b. Regex code reasoning: pattern-match XOR checksums, flag checks
  1.  No-param init -> test write fn with real args
  2.  Mode-based init (0..512) -> test write fn with real args
  3.  Credential sweep from binary strings -> test write fn with real args
"""

from __future__ import annotations

import json
import itertools as _it
import logging
import re as _re
import time

from api.services.executor import _execute_tool

logger = logging.getLogger("mcp_factory.api")


_LLM_CODE_REASONING_PROMPT = """\
You are a reverse-engineering expert analyzing decompiled C code from a Windows DLL.
Your task: identify the EXACT conditions that make each function return 0 (success).

For each function below, analyze the code and produce a structured strategy.

FOCUS ON:
1. **Initialization requirements**: Does the function check a global flag? What function sets it?
2. **Checksums/XOR validations**: If the code XORs bytes of a parameter and compares to a target,
   compute the exact target value and generate 3+ concrete input strings whose bytes XOR to that value.
   IMPORTANT: For XOR targets, generate strings where ALL bytes are printable ASCII (0x20-0x7E)
   and at least 4 bytes long. Example: for target 0xA5, bytes [0x41, 0x42, 0x43, 0xE5] won't work
   because 0xE5 is non-printable. Instead use longer strings of printable chars that XOR correctly.
3. **Flag/bit checks**: Does the function check a bit flag on a record? What function sets/clears it?
4. **Entity existence**: Does the function look up an ID in a table? What format are the IDs?
5. **Ordering constraints**: Must functions be called in a specific order?
6. **Parameter constraints**: Expected types, ranges, string formats for each parameter.

Respond with ONLY valid JSON (no markdown fences):
{
  "strategies": [
    {
      "target_function": "<function name>",
      "prerequisites": ["<function to call first>", ...],
      "prerequisite_args": [{"param_1": "<value>"}, ...],
      "target_args": {"param_name": "<value>", ...},
      "reasoning": "<one sentence explaining WHY these args should work>",
      "confidence": "high|medium|low",
      "mechanism": "<checksum|flag_clear|init_required|entity_lookup|other>"
    }
  ]
}

Generate MULTIPLE strategies per function if there are multiple possible approaches.
"""


def _llm_analyze_decompiled_code(invocables: list[dict]) -> list[dict]:
    """Ask an LLM to analyze decompiled C code and produce unlock strategies.

    Returns a list of strategy dicts. Falls back to empty list on any error.
    This is completely generic — works on any DLL with decompiled code.
    """
    code_blocks = []
    for inv in invocables:
        doc = inv.get("doc_comment") or inv.get("doc") or ""
        if not doc:
            continue
        name = inv["name"]
        is_relevant = bool(_re.search(
            r"init|unlock|auth|login|enable|activate|write|pay|redeem|process|commit|transfer",
            name, _re.I
        ))
        if is_relevant:
            code_blocks.append(f"=== {name} ===\nParameters: {inv.get('parameters', [])}\n{doc[:3000]}")

    if not code_blocks:
        logger.info("[phase1] No decompiled code available for LLM code reasoning")
        return []

    try:
        from api.infra.telemetry import _openai_client
        from api.infra.config import OPENAI_MODEL

        client = _openai_client()
        model = OPENAI_MODEL or "gpt-4o"

        user_content = (
            "Here is decompiled C code from a Windows DLL. "
            "Analyze each function and produce unlock strategies.\n\n"
            + "\n\n".join(code_blocks)
        )

        logger.info("[phase1] LLM code reasoning: analyzing %d functions with %s",
                     len(code_blocks), model)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _LLM_CODE_REASONING_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=4000,
            timeout=60,
        )

        raw = response.choices[0].message.content or ""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = _re.sub(r"^```\w*\n?", "", raw)
            raw = _re.sub(r"\n?```$", "", raw)

        parsed = json.loads(raw)
        strategies = parsed.get("strategies", [])
        logger.info("[phase1] LLM code reasoning produced %d strategies", len(strategies))
        return strategies

    except Exception as exc:
        logger.warning("[phase1] LLM code reasoning failed: %s", exc)
        return []


def _execute_llm_strategies(
    strategies: list[dict],
    inv_map: dict[str, dict],
    init_names: list[str],
    write_fn_names: list[str],
    tried: list[str],
) -> dict | None:
    """Execute strategies produced by LLM code reasoning.

    Returns an unlock result dict if any strategy succeeds, None otherwise.
    """
    _WRITE_SENTINELS = {0xFFFFFFFB, 0xFFFFFFFE, 0xFFFFFFFF}

    for strat in strategies:
        target_fn = strat.get("target_function", "")
        target_inv = inv_map.get(target_fn)
        if not target_inv:
            continue

        prereqs = strat.get("prerequisites", [])
        prereq_args = strat.get("prerequisite_args", [])
        target_args = strat.get("target_args", {})
        mechanism = strat.get("mechanism", "unknown")

        init_seq = []

        for i, prereq_name in enumerate(prereqs):
            prereq_inv = inv_map.get(prereq_name)
            if not prereq_inv:
                continue
            p_args = prereq_args[i] if i < len(prereq_args) else {}
            result = _execute_tool(prereq_inv, p_args)
            tried.append(f"[llm-strategy:{mechanism}] {prereq_name}({p_args}) -> {result}")
            init_seq.append({"fn": prereq_name, "args": p_args})

        result = _execute_tool(target_inv, target_args)
        tried.append(f"[llm-strategy:{mechanism}] {target_fn}({target_args}) -> {result}")
        ret_match = _re.match(r"Returned:\s*(\d+)", result or "")
        ret_val = int(ret_match.group(1)) & 0xFFFFFFFF if ret_match else 0xFFFFFFFF

        if ret_val == 0:
            init_seq.append({"fn": target_fn, "args": target_args})
            for wfn in write_fn_names:
                if wfn == target_fn:
                    continue
                wfn_inv = inv_map.get(wfn)
                if not wfn_inv:
                    continue
                w_result = _execute_tool(wfn_inv, target_args)
                tried.append(f"[llm-strategy:post-unlock] {wfn}({target_args}) -> {w_result}")
                w_match = _re.match(r"Returned:\s*(\d+)", w_result or "")
                w_val = int(w_match.group(1)) & 0xFFFFFFFF if w_match else 0xFFFFFFFF
                if w_val not in _WRITE_SENTINELS and w_val == 0:
                    return {
                        "unlocked": True,
                        "sequence": init_seq,
                        "write_fn_tested": wfn,
                        "write_fn_args": target_args,
                        "notes": (
                            f"unlocked via LLM CODE REASONING ({mechanism}) — "
                            f"{target_fn}({target_args}) → 0, then {wfn}({target_args}) → 0"
                        ),
                        "llm_strategy": strat,
                    }

            is_write = bool(_re.search(
                r"pay|redeem|unlock|process|write|commit|transfer|debit|credit",
                target_fn, _re.I
            ))
            if is_write:
                return {
                    "unlocked": True,
                    "sequence": init_seq,
                    "write_fn_tested": target_fn,
                    "write_fn_args": target_args,
                    "notes": (
                        f"unlocked via LLM CODE REASONING ({mechanism}) — "
                        f"{target_fn}({target_args}) → 0"
                    ),
                    "llm_strategy": strat,
                }

    return None


def _analyze_decompiled_unlock_patterns(invocables: list[dict]) -> dict:
    """Analyze decompiled code for unlock patterns (XOR checksums, flag checks, etc.).

    Returns a structured analysis that both Phase 1 and MC-6 can use to generate
    targeted inputs instead of brute-forcing.
    """
    analysis: dict = {
        "unlock_functions": [],
        "dependency_chains": [],
        "flag_checks": [],
    }

    for inv in invocables:
        doc = inv.get("doc_comment") or inv.get("doc") or ""
        if not doc:
            continue
        name = inv["name"]

        is_unlock = bool(_re.search(r"unlock|auth|login|enable|activate", name, _re.I))
        if not is_unlock and _re.search(
            r"auth\s*token|auth\s*code|credential|same as .*unlock|xor validation",
            doc,
            _re.I,
        ):
            is_unlock = True
        xor_match = _re.search(
            r"[=!]=\s*0x([0-9a-fA-F]{1,8})\b"
            r"|[=!]=\s*(\d{2,10})\b(?!.*line)"
            r"|\bxor.*?0x([0-9a-fA-F]{1,4})",
            doc, _re.I
        )

        if is_unlock and xor_match:
            hex_val = xor_match.group(1) or xor_match.group(3)
            dec_val = xor_match.group(2)
            if hex_val:
                xor_target = int(hex_val, 16)
            elif dec_val:
                xor_target = int(dec_val)
            else:
                continue
            if xor_target >= 256 or xor_target == 0:
                continue
            xor_codes = _generate_xor_codes(xor_target)
            analysis["unlock_functions"].append({
                "name": name,
                "xor_target": xor_target,
                "xor_target_hex": f"0x{xor_target:02X}",
                "xor_codes": xor_codes,
                "params": inv.get("parameters") or [],
            })

        flag_match = _re.search(r"\(.*?&\s*(0x[0-9a-fA-F]+|[0-9]+)\)\s*[!=]=\s*0", doc)
        if flag_match and not is_unlock:
            flag_val = flag_match.group(1)
            for other_inv in invocables:
                other_doc = other_inv.get("doc_comment") or other_inv.get("doc") or ""
                other_name = other_inv["name"]
                if other_name == name or not other_doc:
                    continue
                if flag_val in other_doc and _re.search(
                    r"unlock|init|enable|activate|set|clear", other_name, _re.I
                ):
                    analysis["dependency_chains"].append({
                        "source": other_name,
                        "target": name,
                        "mechanism": f"sets flag {flag_val}",
                    })
                    analysis["flag_checks"].append({
                        "function": name,
                        "flag_hex": flag_val,
                        "setter_function": other_name,
                    })

        for cmp_match in _re.finditer(r"return\s+0x([0-9a-fA-F]{8})", doc):
            val = int(cmp_match.group(1), 16)
            if val >= 0x80000000:
                pass  # handled by sentinel calibration

    return analysis


def _semantic_hint_from_text(text: str) -> str:
    lower = str(text or "").lower()
    if _re.search(r"auth|token|credential|checksum|xor", lower):
        return "auth_token"
    if _re.search(r"sku|product|item", lower):
        return "sku"
    if _re.search(r"amount|price|cost|cents|discount|bps|basis", lower):
        return "amount"
    if _re.search(r"customer|account|client|user", lower):
        return "customer_id"
    if _re.search(r"transaction|txn", lower):
        return "transaction_id"
    if _re.search(r"reserv|resv", lower):
        return "reservation_id"
    if _re.search(r"order", lower):
        return "order_id"
    return ""


def _ordered_doc_param_hints(doc: str) -> list[str]:
    hints: list[str] = []
    for line in str(doc or "").splitlines():
        match = _re.match(r"\s*\*\s*([A-Za-z_][A-Za-z0-9_]*)\s*:(.*)$", line)
        if not match:
            continue
        hint = _semantic_hint_from_text(f"{match.group(1)} {match.group(2)}")
        if hint:
            hints.append(hint)
    return hints


def _build_unlock_probe_arg_sets(
    inv: dict,
    *,
    xor_code: str,
    id_samples: list[str],
    sku_samples: list[str],
    amount_samples: list[int],
    max_results: int = 8,
) -> list[dict]:
    params = list(inv.get("parameters") or [])
    if not params:
        return []

    doc_hints = _ordered_doc_param_hints(inv.get("doc_comment") or inv.get("doc") or "")
    per_param_values: list[list[object]] = []
    for idx, param in enumerate(params):
        name = str(param.get("name") or f"param_{idx+1}")
        desc = str(param.get("description") or "")
        jtype = str(param.get("json_type") or "").lower()
        hint = _semantic_hint_from_text(f"{name} {desc}")
        if not hint and idx < len(doc_hints):
            hint = doc_hints[idx]

        if hint == "auth_token":
            candidates: list[object] = [xor_code]
        elif hint == "sku":
            candidates = list(sku_samples or id_samples or ["WDG-XL-BLU"])
        elif hint == "amount":
            candidates = list(amount_samples or [5000, 2500, 1000, 500])
        elif hint in {"customer_id", "transaction_id", "reservation_id", "order_id"}:
            candidates = list(id_samples or ["CUST-001"])
        elif jtype in {"integer", "number"}:
            candidates = list(amount_samples or [5000, 2500, 1000, 500])
        else:
            candidates = list(id_samples or sku_samples or [xor_code])

        deduped: list[object] = []
        for value in candidates:
            if value not in deduped:
                deduped.append(value)
        per_param_values.append(deduped[:3] or [xor_code])

    arg_sets: list[dict] = []
    for combo in _it.product(*per_param_values):
        args = {
            str(params[i].get("name") or f"param_{i+1}"): combo[i]
            for i in range(len(params))
        }
        if args not in arg_sets:
            arg_sets.append(args)
        if len(arg_sets) >= max_results:
            break
    return arg_sets


def _generate_xor_codes(target: int, max_results: int = 10) -> list[str]:
    """Generate Python strings whose UTF-8 encoded bytes XOR to *target*.

    The DLL receives a C string via ctypes. The executor path is:
      Python str -> str.encode("utf-8") -> ctypes c_char_p -> DLL byte*
    The DLL then XORs each byte of that C string (via lstrlenA).

    For targets < 128: ASCII-only codes work (same in UTF-8 and latin-1).
    For targets >= 128 (e.g. 0xA5): we use 3-byte UTF-8 characters whose
    encoded bytes contribute high-bit XOR values that ASCII cannot reach.
    """
    if target >= 256 or target == 0:
        return []

    codes: list[str] = []

    if target < 128:
        prefixes = [b"AAA", b"abc", b"123", b"XYZ", b"key",
                    b"COD", b"PAS", b"UNL", b"adm", b"XXX"]
        for prefix in prefixes:
            xor_acc = 0
            for b in prefix:
                xor_acc ^= b
            needed = xor_acc ^ target
            if needed == 0 or needed > 127:
                continue
            candidate = prefix + bytes([needed])
            if 0 not in candidate:
                codes.append(candidate.decode("ascii"))
            if len(codes) >= max_results:
                break
        return list(dict.fromkeys(codes))

    _found: set[str] = set()

    for prefix_byte in [0x41, 0x42, 0x43, 0x61, 0x62, 0x63, 0x31, 0x32, 0x33, 0x58]:
        if len(_found) >= max_results:
            break
        for cp in range(0x0800, 0x10000):
            if len(_found) >= max_results:
                break
            try:
                s = chr(cp)
                utf8 = s.encode("utf-8")
            except (ValueError, UnicodeEncodeError):
                continue
            if len(utf8) != 3:
                continue
            xor_val = prefix_byte
            for b in utf8:
                xor_val ^= b
            if xor_val == target:
                code = chr(prefix_byte) + s
                if code not in _found:
                    full_utf8 = code.encode("utf-8")
                    if 0 not in full_utf8:
                        _found.add(code)
            if len(_found) >= max_results:
                break

    codes = list(_found)

    if len(codes) < max_results:
        for p1 in [0x41, 0x61, 0x31]:
            if len(codes) >= max_results:
                break
            for p2 in [0x42, 0x62, 0x32]:
                if len(codes) >= max_results:
                    break
                prefix_xor = p1 ^ p2
                for cp in range(0x0800, 0x10000):
                    if len(codes) >= max_results:
                        break
                    try:
                        s = chr(cp)
                        utf8 = s.encode("utf-8")
                    except (ValueError, UnicodeEncodeError):
                        continue
                    if len(utf8) != 3:
                        continue
                    xor_val = prefix_xor
                    for b in utf8:
                        xor_val ^= b
                    if xor_val == target:
                        code = chr(p1) + chr(p2) + s
                        full_utf8 = code.encode("utf-8")
                        if 0 not in full_utf8 and code not in codes:
                            codes.append(code)

    return codes[:max_results]


def _build_write_test_args(
    inv_map: dict[str, dict],
    write_fn_names: list[str],
    dll_strings: dict,
    vocab: dict | None,
) -> dict[str, list[dict]]:
    """Build plausible argument sets for write-function unlock testing."""
    id_samples = []
    if vocab and vocab.get("id_formats"):
        for fmt in vocab["id_formats"]:
            s = str(fmt).strip()
            if s:
                id_samples.append(s)
    for s in dll_strings.get("ids", []):
        if s and s not in id_samples:
            id_samples.append(s)
    if not id_samples:
        id_samples = ["CUST-001", "ORD-001", "ACCT-001"]

    result: dict[str, list[dict]] = {}
    for fn_name in write_fn_names:
        inv = inv_map.get(fn_name)
        if not inv:
            continue
        params = inv.get("parameters") or []
        if not params:
            result[fn_name] = [{}]
            continue
        candidates: list[dict] = []
        for id_val in id_samples[:3]:
            args: dict = {}
            for p in params:
                if isinstance(p, str):
                    p = {"name": p, "type": "string"}
                pname = p.get("name", "arg")
                ptype = (p.get("type") or "").lower()
                is_ptr = "*" in ptype
                from api.pipeline.core.helpers import _is_true_output_param
                if _is_true_output_param(p):
                    pass  # genuine output buffer → bridge allocates
                elif _re.search(r"id|account|customer|order", pname, _re.I):
                    args[pname] = id_val
                elif _re.search(r"amount|cents|points|value|price", pname, _re.I):
                    args[pname] = 100
                elif is_ptr and ("byte" in ptype or "char" in ptype):
                    args[pname] = id_val
                elif "int" in ptype or "dword" in ptype or "long" in ptype:
                    args[pname] = 1
                elif "char" in ptype or "str" in ptype:
                    args[pname] = id_val
                else:
                    args[pname] = 1
            candidates.append(args)
        result[fn_name] = candidates or [{}]
    return result


_MAX_UNLOCK_BRIDGE_CALLS = 200


def _probe_write_unlock(invocables: list[dict], dll_strings: dict,
                        vocab: dict | None = None) -> dict:
    """Phase 1: try to flip the DLL from read-only to write-ready.

    Hard-capped at ``_MAX_UNLOCK_BRIDGE_CALLS`` bridge round-trips to
    prevent runaway sweeps from starving the pipeline.
    """
    _WRITE_SENTINELS = {0xFFFFFFFB, 0xFFFFFFFE, 0xFFFFFFFF}
    inv_map = {inv["name"]: inv for inv in invocables}
    init_names = [n for n in inv_map if _re.search(r"init(ializ)?", n, _re.I)]
    write_fn_names = [
        n for n in inv_map
        if _re.search(r"(pay|redeem|unlock|process|write|commit|transfer|debit|credit)", n, _re.I)
    ]
    tried: list[str] = []
    code_analysis: dict = {}
    _call_count = 0

    test_arg_sets = _build_write_test_args(inv_map, write_fn_names, dll_strings, vocab)

    def _budget_ok() -> bool:
        return _call_count < _MAX_UNLOCK_BRIDGE_CALLS

    def _exec(inv: dict, args: dict) -> str:
        nonlocal _call_count
        _call_count += 1
        return _execute_tool(inv, args)

    def _heartbeat(phase: str) -> None:
        try:
            from api.pipeline.core.helpers import _set_explore_status
            from api.infra.storage import _get_job_status
            job_id = (inv_map.get(init_names[0]) or {}).get("_job_id", "") if init_names else ""
            if not job_id:
                for inv in invocables:
                    job_id = inv.get("_job_id", "")
                    if job_id:
                        break
            if job_id:
                total = len(invocables)
                _set_explore_status(job_id, 0, total,
                                    f"S-01: write-unlock {phase} ({_call_count} calls)...")
        except Exception:
            pass

    def _test_write_after_init(init_seq: list[dict]) -> dict | None:
        for wfn in write_fn_names:
            if not _budget_ok():
                return None
            arg_candidates = test_arg_sets.get(wfn, [{}])
            for test_args in arg_candidates[:3]:
                if not _budget_ok():
                    return None
                result = _exec(inv_map[wfn], test_args)
                tried.append(f"{wfn}({test_args}) -> {result}")
                ret_match = _re.match(r"Returned:\s*(\d+)", result or "")
                ret_val = int(ret_match.group(1)) & 0xFFFFFFFF if ret_match else 0xFFFFFFFF
                if ret_val not in _WRITE_SENTINELS and ret_val == 0:
                    return {
                        "unlocked": True, "sequence": init_seq,
                        "write_fn_tested": wfn, "write_fn_args": test_args,
                        "notes": f"unlocked — {wfn}({test_args}) returned 0",
                        "code_reasoning_analysis": code_analysis,
                    }
        return None

    # Strategy 0a: LLM code reasoning
    _heartbeat("llm-reasoning")
    llm_strategies = _llm_analyze_decompiled_code(invocables)
    if llm_strategies and _budget_ok():
        llm_hit = _execute_llm_strategies(
            llm_strategies, inv_map, init_names, write_fn_names, tried,
        )
        if llm_hit:
            llm_hit["code_reasoning_analysis"] = code_analysis
            llm_hit["llm_strategies_total"] = len(llm_strategies)
            return llm_hit
        logger.info("[phase1] LLM strategies (%d) did not crack unlock, "
                    "falling back to regex + brute-force", len(llm_strategies))

    # Strategy 0b: Regex code-reasoning from decompiled source
    _heartbeat("regex-patterns")
    code_analysis = _analyze_decompiled_unlock_patterns(invocables)

    if code_analysis.get("unlock_functions") and _budget_ok():
        for uf in code_analysis["unlock_functions"]:
            if not _budget_ok():
                break
            uf_inv = inv_map.get(uf["name"])
            if not uf_inv:
                continue
            params = uf.get("params") or []
            if not params:
                continue

            id_samples = []
            sku_samples = []
            if vocab and vocab.get("id_formats"):
                for fmt in vocab["id_formats"]:
                    if not fmt:
                        continue
                    sval = str(fmt)
                    if sval.upper().startswith(("WDG", "PRO", "ACC", "GDG", "SW-")):
                        if sval not in sku_samples:
                            sku_samples.append(sval)
                    elif sval not in id_samples:
                        id_samples.append(sval)
            for s in dll_strings.get("ids", []):
                if not s:
                    continue
                sval = str(s)
                if sval.upper().startswith(("WDG", "PRO", "ACC", "GDG", "SW-")):
                    if sval not in sku_samples:
                        sku_samples.append(sval)
                elif sval not in id_samples:
                    id_samples.append(sval)
            if not id_samples:
                id_samples = ["CUST-001", "ORD-001", "ACCT-001"]
            if not sku_samples:
                sku_samples = ["WDG-XL-BLU", "ACC-USB-C", "PRO-SVC-ANNUAL"]
            amount_samples = [5000, 2500, 1000, 500]

            for init_n in init_names:
                if not _budget_ok():
                    break
                _exec(inv_map[init_n], {})

            for xor_code in uf.get("xor_codes", []):
                if not _budget_ok():
                    break
                for args in _build_unlock_probe_arg_sets(
                    uf_inv,
                    xor_code=xor_code,
                    id_samples=id_samples[:4],
                    sku_samples=sku_samples[:4],
                    amount_samples=amount_samples,
                ):
                    if not _budget_ok():
                        break
                    result = _exec(uf_inv, args)
                    tried.append(f"[code-reasoning] {uf['name']}({args}) -> {result}")
                    ret_match = _re.match(r"Returned:\s*(\d+)", result or "")
                    ret_val = int(ret_match.group(1)) & 0xFFFFFFFF if ret_match else 0xFFFFFFFF
                    if ret_val == 0:
                        hit = _test_write_after_init([
                            {"fn": init_n, "args": {}} for init_n in init_names
                        ] + [{"fn": uf["name"], "args": args}])
                        if hit:
                            hit["notes"] = (
                                f"unlocked via CODE REASONING — {uf['name']}({args}) "
                                f"returned 0 (XOR target: {uf['xor_target_hex']})"
                            )
                            return hit

    for dep in code_analysis.get("dependency_chains", []):
        if not _budget_ok():
            break
        src = inv_map.get(dep["source"])
        if not src:
            continue
        for init_n in init_names:
            if not _budget_ok():
                break
            _exec(inv_map[init_n], {})
        src_params = src.get("parameters") or []
        if src_params:
            for id_val in (test_arg_sets.get(dep["source"]) or [{}])[:3]:
                if not _budget_ok():
                    break
                result = _exec(src, id_val)
                tried.append(f"[dependency] {dep['source']}({id_val}) -> {result}")
        else:
            result = _exec(src, {})
            tried.append(f"[dependency] {dep['source']}() -> {result}")
        hit = _test_write_after_init([
            {"fn": init_n, "args": {}} for init_n in init_names
        ] + [{"fn": dep["source"], "args": {}}])
        if hit:
            hit["notes"] = f"unlocked via DEPENDENCY CHAIN — {dep['source']} → {dep['target']}"
            return hit

    # Brute-force fallback: no-param init
    _heartbeat("no-param-init")
    no_param_inits = [n for n in init_names if not inv_map[n].get("parameters")]
    if no_param_inits and _budget_ok():
        for n in no_param_inits:
            if not _budget_ok():
                break
            result = _exec(inv_map[n], {})
            tried.append(f"{n}() -> {result}")
        if write_fn_names and _budget_ok():
            hit = _test_write_after_init([{"fn": n, "args": {}} for n in no_param_inits])
            if hit:
                return hit

    # Mode-based init (reduced sweep: skip 256, 512 — rarely productive)
    _heartbeat("mode-sweep")
    for mode in (0, 1, 2, 4, 8, 16):
        if not _budget_ok():
            break
        for n in init_names:
            if not _budget_ok():
                break
            if inv_map[n].get("parameters"):
                result = _exec(inv_map[n], {"param_1": mode})
                tried.append(f"{n}(mode={mode}) -> {result}")
                if write_fn_names and _budget_ok():
                    hit = _test_write_after_init([{"fn": n, "args": {"param_1": mode}}])
                    if hit:
                        return hit

    # Credential sweep (capped to 12 tokens to respect budget)
    _heartbeat("credential-sweep")
    all_strings = dll_strings.get("ids", []) + dll_strings.get("misc", [])
    cred_tokens = list(dict.fromkeys(
        s for s in all_strings if 3 < len(s) < 40
    ))[:12]
    for n in init_names:
        if not _budget_ok():
            break
        if not inv_map[n].get("parameters"):
            continue
        for tok in cred_tokens:
            if not _budget_ok():
                break
            result = _exec(inv_map[n], {"param_1": tok})
            tried.append(f"{n}(cred={tok!r}) -> {result}")
            if write_fn_names and _budget_ok():
                hit = _test_write_after_init([{"fn": n, "args": {"param_1": tok}}])
                if hit:
                    return hit

    canary = write_fn_names[0] if write_fn_names else None
    budget_note = "" if _budget_ok() else f" (budget exhausted at {_call_count} calls)"
    return {"unlocked": False, "sequence": [], "write_fn_tested": canary,
            "notes": f"write-unlock failed after {len(tried)} attempts{budget_note}",
            "code_reasoning_analysis": code_analysis}
