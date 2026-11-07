"""
pdb_analyzer.py — Invocable extractor for Windows PDB (Program Database) files.

Uses the Windows DbgHelp API (dbghelp.dll) via ctypes to enumerate symbols
from a PDB file.  The companion DLL/EXE is loaded as a module so DbgHelp can
resolve the PDB; the image is never actually mapped into user memory.

Each SymTagFunction / SymTagPublicSymbol entry becomes an Invocable with
source_type='pdb_symbol'.  Where type information is available (SymTagData,
parameter children) parameters/return types are extracted at 'high' confidence.

Windows-only.  Returns an empty list on non-Windows platforms.
"""

import ctypes
import ctypes.wintypes as wintypes
import logging
import re
import sys
from ctypes import c_uint64, c_char, c_void_p, c_ulong, POINTER
from pathlib import Path
from typing import List, Optional

from schema import Invocable

logger = logging.getLogger(__name__)

# ── SymTag constants (from cvconst.h) ─────────────────────────────────────────
_TAG_FUNCTION      = 5
_TAG_PUBLIC_SYMBOL = 10
_TAG_DATA          = 7   # parameter / variable

# ── SymType constants ──────────────────────────────────────────────────────────
_TYPE_NONE    = 0
_TYPE_COFF    = 1
_TYPE_CV      = 2
_TYPE_PDB     = 3
_TYPE_EXPORT  = 4
_TYPE_DEFERRED = 5
_TYPE_SYM     = 6
_TYPE_DIA     = 7
_TYPE_VIRTUAL = 8

# ── DbgHelp option flags ────────────────────────────────────────────────────────
SYMOPT_DEFERRED_LOADS   = 0x00000004
SYMOPT_NO_CPP           = 0x00000008
SYMOPT_LOAD_LINES       = 0x00000010
SYMOPT_CASE_INSENSITIVE = 0x00000001
SYMOPT_UNDNAME          = 0x00000002

# ── SYMBOL_INFO structure (winnt.h / dbghelp.h) ────────────────────────────────
_MAX_NAME = 2000

class SYMBOL_INFO(ctypes.Structure):
    _fields_ = [
        ("SizeOfStruct",  c_ulong),
        ("TypeIndex",     c_ulong),
        ("Reserved",      c_uint64 * 2),
        ("Index",         c_ulong),
        ("Size",          c_ulong),
        ("ModBase",       c_uint64),
        ("Flags",         c_ulong),
        ("Value",         c_uint64),
        ("Address",       c_uint64),
        ("Register",      c_ulong),
        ("Scope",         c_ulong),
        ("Tag",           c_ulong),
        ("NameLen",       c_ulong),
        ("MaxNameLen",    c_ulong),
        ("Name",          c_char * _MAX_NAME),
    ]


# Callback signature: BOOL CALLBACK EnumSymProc(PSYMBOL_INFO, ULONG, PVOID)
_ENUM_CALLBACK = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    POINTER(SYMBOL_INFO),
    c_ulong,
    c_void_p,
) if sys.platform == "win32" else None


# ---------------------------------------------------------------------------
# Name mangling / demangling helpers
# ---------------------------------------------------------------------------

def _looks_compiler_internal(name: str) -> bool:
    """Return True for names that are compiler artefacts, not user API."""
    return (
        name.startswith("__")
        or name.startswith("??_")
        or name.startswith("$")
        or re.match(r'^_+[A-Z]', name) is not None
        or name in ("DbgBreakPoint", "DbgUiRemoteBreakin", "LdrpDebugBreakPoint")
    )


def _demangle_name(name: bytes) -> str:
    """Use UnDecorateSymbolName to convert a mangled C++ name."""
    if sys.platform != "win32":
        return name.decode("mbcs", errors="replace")
    try:
        dbghelp = ctypes.WinDLL("dbghelp.dll")
        buf = ctypes.create_string_buffer(2048)
        flags = 0x0000  # UNDNAME_COMPLETE
        result = dbghelp.UnDecorateSymbolName(name, buf, 2048, flags)
        if result:
            return buf.value.decode("mbcs", errors="replace")
    except Exception:
        pass
    return name.decode("mbcs", errors="replace")


def _parse_undecorated(undecorated: str):
    """Extract (return_type, func_name, params_str) from an undecorated C++ name.

    Examples::

        "void __cdecl ZSTD_compress(void *, size_t, void const *, size_t, int)"
        "int sqlite3_open(char const *, sqlite3 **)"
    """
    # Strip calling convention
    clean = re.sub(r'\b(__cdecl|__stdcall|__fastcall|__thiscall|__vectorcall)\b', '', undecorated).strip()

    # Match: rettype name(params)
    m = re.match(r'^(?P<ret>.+?)\s+(?P<name>\w[\w:~<>]*)\s*\((?P<params>.*)\)\s*$', clean, re.DOTALL)
    if not m:
        return None, undecorated, None

    ret = m.group("ret").strip()
    name = m.group("name").strip()
    params_raw = m.group("params").strip()

    # Convert C types to JSON types
    def _c_to_json(t: str) -> str:
        t = t.strip().lower()
        if any(x in t for x in ["char*", "char *", "wchar", "lpstr", "lpwstr", "bstr", "string"]):
            return "string"
        if any(x in t for x in ["int", "long", "short", "dword", "size_t", "word", "byte", "uint", "ulong"]):
            return "integer"
        if any(x in t for x in ["float", "double"]):
            return "number"
        if "bool" in t:
            return "boolean"
        if "void" in t and "*" not in t:
            return "null"
        return t or "any"

    # Parse params
    if not params_raw or params_raw.lower() == "void":
        params_str = ""
    else:
        param_parts: List[str] = []
        for i, p in enumerate(params_raw.split(",")):
            p = p.strip()
            if not p:
                continue
            # Last token is param name if no pointer, else extract
            tokens = p.rsplit(None, 1)
            if len(tokens) == 2 and re.match(r'^\w+$', tokens[1].strip("*&")):
                pname = tokens[1].strip("*&") or f"arg{i}"
                ptype = _c_to_json(tokens[0])
            else:
                pname = f"arg{i}"
                ptype = _c_to_json(p)
            param_parts.append(f"{pname}: {ptype}")
        params_str = ", ".join(param_parts)

    ret_json = _c_to_json(ret) if ret.lower() != "void" else None
    return ret_json, name, params_str


# ---------------------------------------------------------------------------
# DbgHelp loader
# ---------------------------------------------------------------------------

def _load_dbghelp():
    """Return (dbghelp, kernel32) WinDLL handles, or (None, None) on failure."""
    if sys.platform != "win32":
        return None, None
    try:
        dbghelp = ctypes.WinDLL("dbghelp.dll")
        kernel32 = ctypes.WinDLL("kernel32.dll")
        return dbghelp, kernel32
    except OSError as exc:
        logger.debug("Cannot load dbghelp.dll: %s", exc)
        return None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_pdb(path: Path) -> List[Invocable]:
    """Extract symbols from a Windows PDB file using DbgHelp.

    The function looks for a companion DLL/EXE in the same directory whose
    stem matches the PDB.  DbgHelp loads the image and automatically resolves
    the PDB via the symbol search path set to the PDB's directory.

    Args:
        path: Path to the .pdb file.

    Returns:
        List[Invocable] — one entry per discovered function symbol.
    """
    if sys.platform != "win32":
        logger.info("PDB analysis skipped: not running on Windows")
        return []

    dbghelp, kernel32 = _load_dbghelp()
    if dbghelp is None:
        return []

    # Locate companion binary (same directory, same stem)
    companion: Optional[Path] = None
    for ext in (".dll", ".exe", ".sys"):
        candidate = path.with_suffix(ext)
        if candidate.exists():
            companion = candidate
            break

    if companion is None:
        logger.warning("No companion DLL/EXE found for %s — cannot load module for PDB", path.name)
        return []

    hProcess = kernel32.GetCurrentProcess()
    search_path = str(path.parent).encode("mbcs")

    # Options: deferred loads, undecorate names
    dbghelp.SymSetOptions(SYMOPT_DEFERRED_LOADS | SYMOPT_UNDNAME | SYMOPT_LOAD_LINES)

    if not dbghelp.SymInitialize(hProcess, search_path, False):
        logger.warning("SymInitialize failed for %s (error %d)", path.name,
                       kernel32.GetLastError())
        return []

    BASE = c_uint64(0x10_000_000)
    dbghelp.SymLoadModuleEx.restype = c_uint64
    mod_base = dbghelp.SymLoadModuleEx(
        hProcess,
        None,
        str(companion).encode("mbcs"),
        None,
        BASE,
        ctypes.c_ulong(0),
        None,
        ctypes.c_ulong(0),
    )

    if not mod_base:
        err = kernel32.GetLastError()
        logger.warning("SymLoadModuleEx failed for %s (error %d)", companion.name, err)
        dbghelp.SymCleanup(hProcess)
        return []

    raw_symbols: List[dict] = []

    @_ENUM_CALLBACK
    def _sym_callback(sym_info_ptr, _size, _user_ctx):
        try:
            info = sym_info_ptr.contents
            name_bytes = info.Name[: info.NameLen]
            raw_symbols.append({
                "name":  name_bytes,
                "tag":   info.Tag,
                "flags": info.Flags,
                "size":  info.Size,
                "addr":  info.Address,
            })
        except Exception:
            pass
        return True  # continue enumeration

    dbghelp.SymEnumSymbols(hProcess, mod_base, b"*", _sym_callback, None)
    dbghelp.SymCleanup(hProcess)

    # Build Invocables
    invocables: List[Invocable] = []
    seen: set = set()

    for sym in raw_symbols:
        tag = sym["tag"]
        if tag not in (_TAG_FUNCTION, _TAG_PUBLIC_SYMBOL):
            continue

        raw_name = sym["name"]
        mangled = raw_name.decode("mbcs", errors="replace")

        if _looks_compiler_internal(mangled):
            continue

        # Attempt demangling
        undecorated = _demangle_name(raw_name)
        ret_type, clean_name, params_str = _parse_undecorated(undecorated)

        if not clean_name or clean_name in seen:
            continue
        seen.add(clean_name)

        if _looks_compiler_internal(clean_name):
            continue

        sig = f"{clean_name}({params_str or ''})"
        if ret_type:
            sig += f": {ret_type}"

        has_params = bool(params_str)
        has_ret    = bool(ret_type)
        is_public  = (tag == _TAG_PUBLIC_SYMBOL)

        if has_params and has_ret and is_public:
            confidence = "guaranteed"
        elif is_public and (has_params or has_ret):
            confidence = "high"
        elif is_public:
            confidence = "medium"
        else:
            confidence = "low"

        invocables.append(Invocable(
            name=clean_name,
            source_type="pdb_symbol",
            signature=sig,
            parameters=params_str or None,
            return_type=ret_type,
            doc_comment=f"Symbol from {path.name} (tag={tag})",
            confidence=confidence,
            dll_path=str(companion),
        ))

    logger.info("PDB: extracted %d symbols from %s", len(invocables), path.name)
    return invocables
