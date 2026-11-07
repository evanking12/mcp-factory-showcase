"""api.pipeline.s00_setup.static_analysis -- Phase 0b: binary static analysis."""

from __future__ import annotations

import json
import logging

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _upload_to_blob, _download_blob

logger = logging.getLogger("mcp_factory.api")


def _run_phase_0_static(ctx) -> None:
    """Run binary static analysis and inject results into vocab + LLM prompt block.

    Implements G-4 (IAT capabilities), G-7 (binary strings), G-8 (PE version info),
    and G-9 (Capstone sentinel harvesting).

    READS:  ctx.job_id, ctx.invocables, ctx.vocab
    WRITES: ctx.static_hints_block, ctx.dll_strings, ctx.static_analysis_result
            ctx.vocab (seeds binary evidence; never overwrites user-set keys)
    """
    try:
        dll_path = next(
            (inv.get("execution", {}).get("dll_path", "") for inv in ctx.invocables
             if inv.get("execution", {}).get("dll_path")),
            "",
        )

        from pathlib import Path as _Path
        _data: bytes | None = None

        if dll_path:
            try:
                _data = _Path(dll_path).read_bytes()
            except Exception:
                pass

        if _data is None:
            try:
                from api.infra.config import UPLOAD_CONTAINER
                for _ext in (".dll", ".exe", ".bin", ""):
                    try:
                        _data = _download_blob(UPLOAD_CONTAINER, f"{ctx.job_id}/input{_ext}")
                        break
                    except Exception:
                        pass
            except Exception:
                pass

        if _data is not None:
            from api.analysis.static_analysis import (
                run_static_analysis, build_vocab_seeds,
                build_static_hints_block as _build_shb,
            )
            _dll_name = _Path(dll_path).name if dll_path else "unknown.dll"
            ctx.static_analysis_result = run_static_analysis(_data, _dll_name)

            _vocab_seeds = build_vocab_seeds(ctx.static_analysis_result, ctx.vocab)
            for _k, _v in _vocab_seeds.items():
                ctx.vocab.setdefault(_k, _v)
                if _k not in ctx.vocab or ctx.vocab[_k] == _v:
                    ctx.vocab[_k] = _v
            if _vocab_seeds:
                logger.info("[%s] phase0b: vocab seeds applied: %s",
                            ctx.job_id, list(_vocab_seeds.keys()))

            _bs = ctx.static_analysis_result.get("binary_strings", {})
            ctx.dll_strings = {
                "ids":    _bs.get("ids_found", []),
                "emails": _bs.get("emails_found", []),
                "all":    _bs.get("ids_found", []) + _bs.get("emails_found", []),
            }
            ctx.static_hints_block = _build_shb(ctx.static_analysis_result)
            ctx.static_analysis_result["injected_into_prompt"] = bool(ctx.static_hints_block)
            ctx.static_analysis_result["static_hints_block_length"] = len(ctx.static_hints_block)

            try:
                _upload_to_blob(
                    ARTIFACT_CONTAINER,
                    f"{ctx.job_id}/static_analysis.json",
                    json.dumps(ctx.static_analysis_result, indent=2).encode(),
                )
                logger.info("[%s] phase0b: static_analysis.json uploaded", ctx.job_id)
            except Exception as _sa_err:
                logger.debug("[%s] phase0b: static_analysis.json upload failed: %s",
                             ctx.job_id, _sa_err)

            logger.info(
                "[%s] phase0b: G-4/G-7/G-8/G-9 complete -- %d IDs, %d sentinels, IAT:%s",
                ctx.job_id,
                len(_bs.get("ids_found", [])),
                len(ctx.static_analysis_result.get("sentinel_constants", {}).get("harvested", {})),
                list(ctx.static_analysis_result.get("iat_capabilities", {}).get("categories", {}).keys()),
            )
    except Exception as _e:
        logger.debug("[%s] phase0b: static enrichment failed: %s", ctx.job_id, _e)

    # BUG-002 fix: reclassify Ghidra direction:out on byte*/char* parameters.
    _reclassified = reclassify_ghidra_directions(ctx.invocables, ctx.static_analysis_result)
    if _reclassified:
        logger.info("[%s] phase0b: reclassified %d ambiguous direction:out params",
                    ctx.job_id, _reclassified)

    # Wire Ghidra enhanced data: call graph, data types, confidence
    _build_call_graph(ctx)
    _extract_ghidra_data_types(ctx)


def _build_call_graph(ctx) -> None:
    """Build ctx.call_graph from invocables' call_graph_callees fields."""
    _exported_names = {inv["name"] for inv in ctx.invocables}
    for inv in ctx.invocables:
        callees = inv.get("call_graph_callees") or []
        if callees:
            relevant = [c for c in callees if c in _exported_names]
            if relevant:
                ctx.call_graph[inv["name"]] = relevant
    if ctx.call_graph:
        logger.info("[%s] phase0b: call graph has %d edges across %d functions",
                    ctx.job_id, sum(len(v) for v in ctx.call_graph.values()),
                    len(ctx.call_graph))
        try:
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{ctx.job_id}/call_graph.json",
                json.dumps(ctx.call_graph, indent=2).encode(),
            )
        except Exception as exc:
            logger.debug("[%s] phase0b: call_graph.json upload failed: %s", ctx.job_id, exc)


def _extract_ghidra_data_types(ctx) -> None:
    """Extract Ghidra data types from the first invocable's _ghidra_extras."""
    for inv in ctx.invocables:
        extras = inv.get("_ghidra_extras")
        if extras and extras.get("data_types"):
            ctx.ghidra_data_types = extras["data_types"]
            logger.info("[%s] phase0b: loaded %d Ghidra data types (structs/enums/typedefs)",
                        ctx.job_id, len(ctx.ghidra_data_types))
            try:
                _upload_to_blob(
                    ARTIFACT_CONTAINER,
                    f"{ctx.job_id}/ghidra_data_types.json",
                    json.dumps(ctx.ghidra_data_types, indent=2).encode(),
                )
            except Exception as exc:
                logger.debug("[%s] phase0b: ghidra_data_types.json upload failed: %s",
                             ctx.job_id, exc)
            break


def reclassify_ghidra_directions(invocables: list[dict], static_result: dict) -> int:
    """Reclassify Ghidra's unreliable direction='out' on byte*/char* params.

    Ghidra labels ALL pointer params as direction='out' by default. For byte*/char*
    params this is almost always wrong — they're input strings (customer IDs, names).
    Only undefined*/int*/uint* pointers are genuine output buffers.

    Uses heuristics:
    1. Function name context: getters have input params, setters may have output
    2. Parameter name hints: 'id', 'name', 'code', 'key' are inputs
    3. Type-based: byte*/char*/string* → likely input; undefined*/int*/uint* → likely output
    4. Cross-reference with binary string constants for format hints

    Returns count of reclassified parameters.
    """
    _INPUT_BASE_TYPES = {"byte", "char", "string", "str", "uchar"}
    _INPUT_ALIAS_TYPES = {"lpcstr", "pcstr", "lpcwstr", "pcwstr"}
    _OUTPUT_ALIAS_TYPES = {"lpstr", "lpwstr"}
    _INPUT_PARAM_HINTS = {"id", "name", "code", "key", "account", "customer",
                          "user", "email", "token", "label", "desc", "text",
                          "message", "path", "file", "address"}
    _GETTER_PATTERNS = {"get", "query", "lookup", "find", "search", "check",
                        "validate", "verify", "read", "fetch", "list", "count"}
    count = 0
    for inv in invocables:
        fn_name_lower = inv.get("name", "").lower()
        is_getter = any(p in fn_name_lower for p in _GETTER_PATTERNS)
        for param in (inv.get("parameters") or []):
            direction = str(param.get("direction") or "in").lower()
            if direction != "out":
                continue
            ptype = str(param.get("type") or "").lower()
            resolved_type = str(param.get("resolved_type") or "").lower()
            raw_type = f"{ptype} {resolved_type}".strip()
            if (
                "*" not in raw_type
                and not any(alias in raw_type for alias in _INPUT_ALIAS_TYPES | _OUTPUT_ALIAS_TYPES)
            ):
                continue
            if any(alias in raw_type for alias in _OUTPUT_ALIAS_TYPES):
                continue
            if any(alias in raw_type for alias in _INPUT_ALIAS_TYPES):
                param["direction"] = "in"
                param["direction_reclassified"] = True
                _reason = (
                    "string typedef pointer reclassified from out->in "
                    f"(resolved={resolved_type or ptype}, getter={is_getter})"
                )
                param["direction_reclassified_reason"] = _reason
                _patch_direction_provenance(param, "in", _reason, confidence=0.85)
                count += 1
                continue
            base = (
                ptype.replace("const ", "")
                .replace("typedef ", "")
                .strip()
                .rstrip(" *")
                .split()[-1]
            )
            if base not in _INPUT_BASE_TYPES:
                continue
            pname = str(param.get("name") or "").lower()
            has_input_hint = any(h in pname for h in _INPUT_PARAM_HINTS)
            if has_input_hint or is_getter or base in ("byte", "char", "str", "string"):
                param["direction"] = "in"
                param["direction_reclassified"] = True
                _reason = (
                    f"byte*/char* pointer reclassified from out→in "
                    f"(base={base}, name_hint={has_input_hint}, getter={is_getter})"
                )
                param["direction_reclassified_reason"] = _reason
                _conf = 0.80 if has_input_hint else (0.75 if is_getter else 0.65)
                _patch_direction_provenance(param, "in", _reason, confidence=_conf)
                count += 1
    return count


def _patch_direction_provenance(
    param: dict, new_direction: str, reason: str, confidence: float,
) -> None:
    """Update the _ghidra_provenance.direction field after reclassification."""
    prov = param.get("_ghidra_provenance")
    if prov is None:
        return
    dir_prov = prov.get("direction")
    if dir_prov is None:
        return
    dir_prov["value"] = new_direction
    dir_prov["source_method"] = "reclassified"
    dir_prov["trust_level"] = "medium"
    dir_prov["confidence"] = confidence
    dir_prov["reclassified"] = True
    dir_prov["reclassified_reason"] = reason
