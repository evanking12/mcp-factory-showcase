"""
ghidra_analyzer.py - Recover function signatures from stripped binaries via Ghidra headless.

This analyzer is the "last resort" fallback for .dll and .exe files where
every other analyzer (TLB, CLI, RPC, .NET exports) yields zero invocables.
It invokes Ghidra's analyzeHeadless CLI, lets Ghidra auto-analyze the binary,
then runs ExtractFunctions.py (Jython) to dump all recovered functions to JSON.

Requirements (on the Windows VM):
  - GHIDRA_HOME env var pointing to the Ghidra installation directory
    (set by _vm_install_ghidra.ps1, e.g.  C:\\ghidra)
  - Java 17+ on PATH (installed by the same script)

Timeout:
  Default 180 s — enough for most DLLs under 10 MB.  Large binaries (> 50 MB)
  may need more time; callers can pass timeout_s explicitly.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path to our Jython extraction script, co-located in ghidra_scripts/
_SCRIPT_DIR  = Path(__file__).parent / "ghidra_scripts"
_SCRIPT_NAME = "ExtractFunctions.py"

# Calling-convention strings Ghidra emits → ctypes convention names
_CC_MAP: dict[str, str] = {
    "__cdecl":    "cdecl",
    "__stdcall":  "stdcall",
    "__fastcall": "fastcall",
    "__thiscall": "cdecl",     # closest Python ctypes approximation
    "unknown":    "cdecl",     # safe default for x86
    "default":    "cdecl",
}

# Ghidra / C type strings → JSON Schema type strings.
# "undefined*" and pointer types are treated as strings so the LLM can pass
# numeric ids, hex addresses, or string values without the schema rejecting them.
_GHIDRA_TYPE_TO_JSON: dict[str, str] = {
    "int":        "integer",
    "uint":       "integer",
    "long":       "integer",
    "ulong":      "integer",
    "longlong":   "integer",
    "ulonglong":  "integer",
    "short":      "integer",
    "ushort":     "integer",
    "char":       "integer",
    "uchar":      "integer",
    "bool":       "boolean",
    "float":      "number",
    "double":     "number",
    "void":       "string",
}

_MAX_RETAINED_GHIDRA_DATA_TYPES = 160


def _ghidra_type_to_json_schema(ghidra_type: str) -> str:
    """Convert a Ghidra/C type string to a JSON Schema primitive type.

    Falls back to "string" for pointers, undefined*, and anything unknown so
    the LLM can always pass a serialised value the executor can handle.
    """
    t = ghidra_type.lower().strip()
    # Strip pointer stars and const so we check the base type
    base = t.replace("*", "").replace("const", "").strip()
    return _GHIDRA_TYPE_TO_JSON.get(base, "string")


def _extract_type_tokens(raw_type: str) -> set[str]:
    text = str(raw_type or "")
    if not text:
        return set()
    cleaned = (
        text.replace("const", " ")
        .replace("*", " ")
        .replace("[", " ")
        .replace("]", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace(",", " ")
    )
    tokens = {
        token.strip()
        for token in re.split(r"\s+", cleaned)
        if token.strip()
    }
    return {
        token
        for token in tokens
        if token
        and not token.lower().startswith("undefined")
        and token not in {"void"}
    }


def _prioritize_ghidra_data_types(
    functions: list[dict[str, Any]],
    data_types: list[dict[str, Any]],
    *,
    max_items: int = _MAX_RETAINED_GHIDRA_DATA_TYPES,
) -> list[dict[str, Any]]:
    """Keep function-referenced data types first in the retained handoff set."""
    if not data_types:
        return []

    referenced: set[str] = set()
    for fn in functions or []:
        for key in ("return_type",):
            referenced.update(_extract_type_tokens(str(fn.get(key) or "")))
        for param in fn.get("parameters") or []:
            if not isinstance(param, dict):
                continue
            referenced.update(_extract_type_tokens(str(param.get("type") or "")))
            referenced.update(_extract_type_tokens(str(param.get("resolved_type") or "")))

    prioritized: list[dict[str, Any]] = []
    spill: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in data_types:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if name in referenced:
            prioritized.append(item)
        else:
            spill.append(item)
    combined = prioritized + spill
    if max_items and max_items > 0:
        return combined[:max_items]
    return combined


# ── Provenance helpers ────────────────────────────────────────────────────
# Build provenance dicts matching api.pipeline.core.ghidra_provenance schema
# without importing across the src → api boundary.

_TRUST_TABLE: dict[str, tuple[str, float]] = {
    "decompiler":      ("medium", 0.75),
    "getParameters":   ("medium", 0.65),
    "signature_parse": ("low",    0.45),
    "pe_export":       ("high",   0.95),
    "dtm_lookup":      ("medium", 0.70),
    "heuristic":       ("low",    0.40),
}
_WARNING_PENALTY = 0.15


def _prov_trust(source_method: str, has_warnings: bool = False) -> tuple[str, float]:
    trust, conf = _TRUST_TABLE.get(source_method, ("low", 0.40))
    if has_warnings:
        conf = max(0.1, conf - _WARNING_PENALTY)
        if trust == "high":
            trust = "medium"
    return trust, round(conf, 2)


def _prov_field(value: Any, source_method: str, trust: str, confidence: float,
                warnings: list[str] | None = None) -> dict:
    return {
        "value": value,
        "source_method": source_method,
        "trust_level": trust,
        "confidence": confidence,
        "decompiler_warnings": warnings or [],
        "reclassified": False,
        "reclassified_reason": "",
    }


def _prov_direction_trust(direction: str, ghidra_type: str, resolved: str = "") -> tuple[str, float]:
    raw = f"{ghidra_type} {resolved}".lower()
    if "lpcstr" in raw or "pcstr" in raw or "lpcwstr" in raw or "pcwstr" in raw:
        return "high", 0.90
    if "lpstr" in raw or "lpwstr" in raw:
        return "high", 0.85
    if "*" not in raw:
        return "medium", 0.75
    if "const " in raw:
        return "medium", 0.70
    return "low", 0.35


def _prov_type_trust(ghidra_type: str, resolved: str = "",
                     source_method: str = "decompiler", has_warnings: bool = False) -> tuple[str, float]:
    raw = f"{ghidra_type} {resolved}".lower()
    _known = {"lpcstr", "lpstr", "lpcwstr", "lpwstr", "dword", "word",
              "byte", "bool", "handle", "hresult", "hwnd", "lpvoid"}
    if any(td in raw for td in _known):
        trust, conf = "high", 0.85
    elif "undefined" in raw:
        trust, conf = "low", 0.35
    else:
        trust, conf = _prov_trust(source_method, has_warnings)
    if has_warnings:
        conf = max(0.1, conf - _WARNING_PENALTY)
    return trust, round(conf, 2)


def _prov_name_trust(name: str, source_method: str = "decompiler") -> tuple[str, float]:
    if re.match(r"^param_\d+$", name, re.I):
        return "low", 0.30
    return _prov_trust(source_method, has_warnings=False)


def _ghidra_param_direction(ghidra_type: str, resolved_type: str = "") -> str:
    """Infer parameter direction from Ghidra types without dropping string inputs.

    Ghidra often emits non-const pointer aliases like LPCSTR/LPSTR as plain
    pointer types. Treating every non-const pointer as output causes the probe
    planner to omit real string inputs such as customer IDs and SKUs.
    """
    raw = f"{ghidra_type} {resolved_type}".lower()
    if "*" not in raw and "lpstr" not in raw and "lpcstr" not in raw and "lpwstr" not in raw and "lpcwstr" not in raw:
        return "in"

    if (
        "undefined" in raw
        or "int *" in raw
        or "uint *" in raw
        or "dword *" in raw
        or "word *" in raw
        or "short *" in raw
        or "ushort *" in raw
        or "long *" in raw
        or "ulong *" in raw
        or "float *" in raw
        or "double *" in raw
        or "bool *" in raw
    ):
        return "out"

    if "lpcstr" in raw or "pcstr" in raw or "lpcwstr" in raw or "pcwstr" in raw:
        return "in"

    if "lpstr" in raw or "lpwstr" in raw:
        return "out"

    if "const " in raw or "byte *" in raw or "char *" in raw or "wchar_t *" in raw:
        return "in"

    return "out"


def _params_from_signature(sig: str) -> list[dict]:
    """Parse parameter types/names from a C-style Ghidra prototype string.

    Handles signatures like:
        int __stdcall CS_Foo(undefined8 param1, float * param2, int param3)

    Returns a list of {"name", "type", "ordinal"} dicts, or [] if unparseable.
    This is used as a last-resort fallback when neither DecompInterface nor
    getParameters() returned any parameters.
    """
    m = re.search(r'\(([^)]*)\)', sig)
    if not m:
        return []
    params_str = m.group(1).strip()
    if not params_str or params_str.lower() == "void":
        return []
    result = []
    for i, part in enumerate(params_str.split(",")):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if len(tokens) >= 2:
            # Last token is the parameter name; preceding tokens are the type
            raw_name = tokens[-1]
            ptype    = " ".join(tokens[:-1])
            # If the name starts with '*', it's a pointer — move stars to type
            stars    = len(raw_name) - len(raw_name.lstrip("*"))
            name     = raw_name.lstrip("*") or f"param_{i}"
            if stars:
                ptype += " " + ("*" * stars)
        else:
            name  = f"param_{i}"
            ptype = tokens[0] if tokens else "undefined"
        result.append({"name": name, "type": ptype, "ordinal": i})
    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_with_ghidra(
    binary_path: Path,
    timeout_s: int = 180,
    exported_only: bool = False,
) -> list[dict[str, Any]]:
    """Run Ghidra headless on *binary_path* and return a list of invocable dicts.

    Args:
        binary_path:   Absolute path to the .dll or .exe to analyze.
        timeout_s:     Maximum seconds to wait for analyzeHeadless.
        exported_only: If True, only return functions that appear in the PE
                       export table.  If False (default), return all recovered
                       functions — useful for showing internal helpers Ghidra
                       found that are NOT in the export table.

    Returns:
        List of invocable dicts in the standard gui_bridge format.
        Empty list if Ghidra is not installed or analysis fails.
    """
    headless = _find_headless()
    if headless is None:
        logger.warning(
            "Ghidra not found — set GHIDRA_HOME or install via scripts/_vm_install_ghidra.ps1"
        )
        return []

    binary_path = Path(binary_path).resolve()
    if not binary_path.exists():
        logger.error("ghidra_analyzer: binary not found: %s", binary_path)
        return []

    # Resolve proj_dir to its canonical long-path form.  On some Windows builds
    # tempfile.mkdtemp() returns an 8.3 short path (e.g. C:\Example\SHORTP~1\...) while
    # Ghidra's JVM expands it to the full long path before writing files — so the
    # output JSON lands at a path that Python's os.path.exists() never finds.
    proj_dir  = Path(tempfile.mkdtemp(prefix="ghidra_proj_")).resolve()
    proj_name = "analysis"

    # Write output JSON to a sibling temp file OUTSIDE the Ghidra project dir.
    # This avoids any risk of -deleteProject wiping the file before we read it,
    # and eliminates path-canonicalization races on 8.3 short-name accounts.
    # IMPORTANT: .resolve() converts 8.3 short names (e.g. AZUREU~1) to their
    # full long-path equivalents.  Without it, Python creates the file at the
    # short path, passes that string to Ghidra's JVM, the JVM canonicalises
    # the path internally and writes the JSON to the long-path location, then
    # Python reads back the original short-path file which is still empty —
    # producing the misleading "Expecting value: line 1 column 1 (char 0)" error.
    _out_fd, _out_json_str = tempfile.mkstemp(suffix=".json", prefix="ghidra_out_")
    os.close(_out_fd)
    out_json = Path(_out_json_str).resolve()

    try:
        _run_headless(headless, binary_path, proj_dir, proj_name, out_json, timeout_s)
        invocables, extras = _parse_output(out_json, binary_path, exported_only)
        for inv in invocables:
            inv["_ghidra_extras"] = extras
        return invocables
    finally:
        try:
            shutil.rmtree(proj_dir, ignore_errors=True)
        except Exception:
            pass
        try:
            out_json.unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_headless() -> Path | None:
    """Locate analyzeHeadless.bat from GHIDRA_HOME or common install paths."""
    candidates: list[Path] = []

    ghidra_home = os.environ.get("GHIDRA_HOME", "")
    if ghidra_home:
        candidates.append(Path(ghidra_home) / "support" / "analyzeHeadless.bat")

    # Common default install locations
    for base in [Path("C:/ghidra"), Path("C:/Program Files/Ghidra")]:
        candidates.append(base / "support" / "analyzeHeadless.bat")

    # Also search C:\ for any ghidra_*_PUBLIC directory
    try:
        for d in Path("C:/").iterdir():
            if d.is_dir() and d.name.lower().startswith("ghidra_"):
                candidates.append(d / "support" / "analyzeHeadless.bat")
    except Exception:
        pass

    for c in candidates:
        if c.exists():
            logger.info("ghidra_analyzer: found analyzeHeadless at %s", c)
            return c

    return None


def _run_headless(
    headless: Path,
    binary: Path,
    proj_dir: Path,
    proj_name: str,
    out_json: Path,
    timeout_s: int,
) -> None:
    """Invoke analyzeHeadless and block until it finishes or times out."""
    script_path = str(_SCRIPT_DIR)
    cmd = [
        str(headless),
        str(proj_dir),
        proj_name,
        "-import",   str(binary),
        "-postScript", _SCRIPT_NAME, str(out_json),
        "-scriptPath", script_path,
        "-deleteProject",
        "-log",      str(proj_dir / "ghidra.log"),
    ]

    logger.info("ghidra_analyzer: running analyzeHeadless on %s (timeout=%ds)",
                binary.name, timeout_s)
    logger.debug("ghidra_analyzer: cmd = %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(proj_dir),
        )
        # Always log at least the tail of stdout — ExtractFunctions.py's
        # print() calls land here and are the only way to see Jython errors
        # when analyzeHeadless exits 0 but the postScript crashed silently.
        _stdout_tail = (result.stdout or "").strip()[-3000:]
        _stderr_tail = (result.stderr or "").strip()[-1000:]
        if result.returncode != 0:
            logger.warning(
                "ghidra_analyzer: analyzeHeadless exited %d\nstdout: %s\nstderr: %s",
                result.returncode, _stdout_tail, _stderr_tail,
            )
        else:
            logger.info("ghidra_analyzer: analyzeHeadless completed for %s", binary.name)
            if _stdout_tail:
                logger.info("ghidra_analyzer: headless stdout:\n%s", _stdout_tail)
            if _stderr_tail:
                logger.warning("ghidra_analyzer: headless stderr:\n%s", _stderr_tail)
    except subprocess.TimeoutExpired:
        logger.error(
            "ghidra_analyzer: analyzeHeadless timed out after %ds for %s",
            timeout_s, binary.name,
        )


def _parse_output(
    out_json: Path,
    binary_path: Path,
    exported_only: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse the JSON written by ExtractFunctions.py into invocable dicts.

    Returns (invocables, extras) where extras contains call_graph and data_types.
    """
    _empty_extras: dict[str, Any] = {"call_graph": {}, "data_types": []}
    if not out_json.exists():
        logger.error("ghidra_analyzer: output JSON not found: %s", out_json)
        return [], _empty_extras

    try:
        content = out_json.read_text(encoding="utf-8").strip()
        if not content:
            logger.error(
                "ghidra_analyzer: output JSON is empty — ExtractFunctions.py postScript "
                "may not have executed. Path used: %s",
                out_json,
            )
            return [], _empty_extras
        data = json.loads(content)
    except Exception as exc:
        logger.error("ghidra_analyzer: failed to parse output JSON: %s", exc)
        return [], _empty_extras

    if "error" in data:
        logger.error("ghidra_analyzer: ExtractFunctions.py reported error: %s", data["error"])

    functions = data.get("functions", [])
    prioritized_data_types = _prioritize_ghidra_data_types(
        functions,
        data.get("data_types", []),
    )
    extras: dict[str, Any] = {
        "call_graph": data.get("call_graph", {}),
        "data_types": prioritized_data_types,
    }
    invocables: list[dict[str, Any]] = []

    for fn in functions:
        name = fn.get("name", "")
        if not name or name.startswith("FUN_"):
            if not fn.get("is_exported"):
                continue

        if exported_only and not fn.get("is_exported"):
            continue

        cc_ghidra = fn.get("calling_convention", "unknown")
        cc = _CC_MAP.get(cc_ghidra, "cdecl")

        parameters: list[dict] = []
        raw_params = fn.get("parameters", [])
        _param_source = "decompiler"

        if not raw_params:
            sig = fn.get("signature", "")
            if sig:
                parsed = _params_from_signature(sig)
                if parsed:
                    logger.debug(
                        "ghidra_analyzer: parsed %d params from signature for %s: %s",
                        len(parsed), name, sig,
                    )
                    raw_params = parsed
                    _param_source = "signature_parse"

        _has_warnings = bool(fn.get("decompiler_warnings"))
        _param_provenance_map: dict[str, dict] = {}

        for p in raw_params:
            ptype    = p.get("type", "int")
            _resolved = p.get("resolved_type", "")
            _pname   = p.get("name", f"param_{p.get('ordinal', 0)}")
            _direction = _ghidra_param_direction(ptype, _resolved)
            _jtype   = _ghidra_type_to_json_schema(ptype)
            _desc = f"Parameter recovered by Ghidra decompiler (type: {ptype})"
            if _resolved:
                _desc += f" [resolved: {_resolved}]"

            _warn_list = [fn.get("decompiler_warnings", "")] if _has_warnings else []
            _nt, _nc = _prov_name_trust(_pname, _param_source)
            _tt, _tc = _prov_type_trust(ptype, _resolved, _param_source, _has_warnings)
            _dt, _dc = _prov_direction_trust(_direction, ptype, _resolved)
            _jt, _jc = _prov_trust(_param_source, _has_warnings)

            _pprov = {
                "name": _prov_field(_pname, _param_source, _nt, _nc),
                "param_type": _prov_field(ptype, _param_source, _tt, _tc, _warn_list),
                "direction": _prov_field(_direction, "heuristic", _dt, _dc),
                "json_type": _prov_field(_jtype, _param_source, _jt, _jc),
            }
            _param_provenance_map[_pname] = _pprov

            parameters.append({
                "name":          _pname,
                "type":          ptype,
                "json_type":     _jtype,
                "description":   _desc,
                "direction":     _direction,
                "resolved_type": _resolved,
                "_ghidra_provenance": _pprov,
            })

        ret_type = fn.get("return_type", "int")

        _decomp_conf = fn.get("decompiler_confidence", 0.5)
        if fn.get("is_exported"):
            confidence = _decomp_conf
        else:
            confidence = min(_decomp_conf, 0.5)

        source_tag = "ghidra_export" if fn.get("is_exported") else "ghidra_internal"

        _decompiled_c = fn.get("decompiled_c", "")
        _base_doc = (
            f"Recovered by Ghidra static analysis. "
            f"Address: {fn.get('address', '?')}. "
            f"Calling convention: {cc_ghidra}."
        )
        _doc = (_base_doc + "\n\nDecompiled C:\n" + _decompiled_c) if _decompiled_c else _base_doc

        _callees = extras["call_graph"].get(name, [])

        _is_exported = bool(fn.get("is_exported"))
        _ex_trust, _ex_conf = ("high", 1.0) if _is_exported else ("medium", 0.6)
        _cc_trust, _cc_conf = ("high", 0.90) if cc_ghidra not in ("unknown", "default") else ("low", 0.40)
        _pc_trust, _pc_conf = _prov_trust(_param_source, _has_warnings)
        _rt_trust, _rt_conf = _prov_type_trust(ret_type, source_method=_param_source,
                                               has_warnings=_has_warnings)
        _cg_edges_prov = [
            _prov_field(c, "call_graph_xref", "medium", 0.70) for c in _callees
        ]

        _fn_prov = {
            "exists": _prov_field(name, "pe_export" if _is_exported else "decompiler",
                                  _ex_trust, _ex_conf),
            "calling_convention": _prov_field(cc_ghidra, "decompiler", _cc_trust, _cc_conf),
            "param_count": _prov_field(len(raw_params), _param_source, _pc_trust, _pc_conf),
            "return_type": _prov_field(ret_type, _param_source, _rt_trust, _rt_conf),
            "params": _param_provenance_map,
            "call_graph_edges": _cg_edges_prov,
            "decompiler_confidence": _decomp_conf,
            "decompiler_warnings": [fn.get("decompiler_warnings", "")] if _has_warnings else [],
        }

        invocables.append({
            "name":                   name,
            "source_type":            source_tag,
            "signature":              fn.get("signature", name),
            "confidence":             confidence,
            "decompiler_confidence":  _decomp_conf,
            "decompiler_warnings":    fn.get("decompiler_warnings", ""),
            "call_graph_callees":     _callees,
            "dll_path":               str(binary_path),
            "doc_comment":            _doc,
            "doc":                    _doc,
            "parameters":             parameters,
            "return_type":            ret_type,
            "_ghidra_provenance":     _fn_prov,
            "execution": {
                "method":             "dll_import",
                "dll_path":           str(binary_path),
                "function_name":      name,
                "calling_convention": cc,
                "arg_types":          [p.get("type", "int") for p in fn.get("parameters", [])],
                "return_type":        ret_type,
            },
        })

    exported = sum(1 for i in invocables if "export" in i["source_type"])
    internal = len(invocables) - exported
    logger.info(
        "ghidra_analyzer: %d invocables from %s (%d exported, %d internal, "
        "%d call_graph edges, %d data_types)",
        len(invocables), binary_path.name, exported, internal,
        len(extras["call_graph"]), len(extras["data_types"]),
    )
    return invocables, extras
