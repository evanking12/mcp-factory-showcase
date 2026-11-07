"""
idl_analyzer.py — Invocable extractor for CORBA IDL (Interface Definition Language) files.

Extracts method declarations from CORBA IDL interfaces.  The grammar is
a subset of C++ interfaces extended with CORBA-specific keywords
(in/out/inout parameter directions, sequence<T>, oneway, etc.).

Each method in an interface block becomes an Invocable with
source_type='corba_method'.

No third-party dependencies — pure regex / state-machine parsing.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional

from schema import Invocable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Strip // line comments and /* ... */ block comments
_LINE_COMMENT_RE  = re.compile(r'//[^\n]*')
_BLOCK_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)

# module Foo { ... }
_MODULE_RE = re.compile(r'\bmodule\s+(?P<name>\w+)\s*\{', re.MULTILINE)

# interface Foo [: Base, ...] { ... }
_INTERFACE_RE = re.compile(
    r'\binterface\s+(?P<name>\w+)'
    r'(?:\s*:\s*(?P<bases>[^{]+))?'
    r'\s*\{',
    re.MULTILINE,
)

# Method declaration inside an interface:
#   [oneway] RetType methodName ( [params] ) [raises (...)];
# RetType can be: void, long, string, sequence<T>, wstring, boolean, octet, etc.
_METHOD_RE = re.compile(
    r'(?P<oneway>\boneway\s+)?'
    r'(?P<rettype>(?:sequence\s*<[^>]+>|\w+(?:::\w+)*))\s+'
    r'(?P<name>\w+)\s*'
    r'\((?P<params>[^)]*)\)',
    re.MULTILINE,
)

# Parameter: [direction] type name
_PARAM_RE = re.compile(
    r'(?:(?P<dir>in|out|inout)\s+)?'
    r'(?P<type>(?:sequence\s*<[^>]+>|\w+(?:::\w+)*))\s+'
    r'(?P<name>\w+)',
    re.IGNORECASE,
)

# IDL doc comment: the /// or /** style block immediately before the method
_DOCCMT_RE = re.compile(
    r'(?:(?://[ \t]*(.+)\n)+)',
    re.MULTILINE,
)

# IDL keywords to skip if they match as "methods"
_KEYWORDS = frozenset({
    "void", "module", "interface", "struct", "enum", "exception",
    "typedef", "sequence", "attribute", "readonly", "raises", "oneway",
    "in", "out", "inout", "boolean", "long", "short", "unsigned",
    "float", "double", "octet", "char", "wchar", "string", "wstring",
    "any", "Object", "ValueBase",
})

# IDL type → JSON Schema type
_IDL_TYPE_MAP = {
    "long": "integer", "short": "integer", "unsigned": "integer",
    "longlong": "integer", "unsignedlong": "integer",
    "octet": "integer",
    "float": "number", "double": "number",
    "boolean": "boolean",
    "string": "string", "wstring": "string", "char": "string", "wchar": "string",
    "void": "null", "any": "any",
}


def _idl_type_to_json(idl_type: str) -> str:
    base = re.sub(r'\s+', '', idl_type.lower())
    # sequence<T> → array
    if base.startswith("sequence"):
        return "array"
    return _IDL_TYPE_MAP.get(base, idl_type)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _strip_comments(source: str) -> str:
    """Remove comments but insert newline placeholders to preserve line offsets."""
    source = _BLOCK_COMMENT_RE.sub(lambda m: '\n' * m.group(0).count('\n'), source)
    source = _LINE_COMMENT_RE.sub('', source)
    return source


def _extract_block(source: str, open_pos: int) -> Optional[str]:
    """Return the content between matching braces starting at open_pos (which
    must point to the '{') or None if unmatched."""
    depth = 0
    i = open_pos
    start = None
    while i < len(source):
        ch = source[i]
        if ch == '{':
            depth += 1
            if start is None:
                start = i + 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return source[start:i]
        i += 1
    return None


def _parse_params(raw: str) -> str:
    """Convert a raw parameter list string to 'name: type' notation."""
    if not raw.strip():
        return ""
    parts: List[str] = []
    for param_str in raw.split(','):
        m = _PARAM_RE.search(param_str.strip())
        if m:
            direction = m.group('dir') or 'in'
            ptype = m.group('type')
            pname = m.group('name')
            json_type = _idl_type_to_json(ptype)
            parts.append(f"{pname}: {json_type} [{direction}]")
    return ", ".join(parts)


def _find_doc_before(original_source: str, clean_source: str, method_pos: int) -> Optional[str]:
    """Find a // doc comment immediately preceding the method declaration.

    Uses the *original* (un-stripped) source positionally aligned with the
    *clean* (comment-stripped) source.  Because _strip_comments preserves
    newline counts, the character offset in clean maps onto the same line
    number in original.
    """
    # Count the line number of method_pos in clean source
    line_no = clean_source[:method_pos].count('\n')
    orig_lines = original_source.splitlines()

    doc_lines: List[str] = []
    for i in range(line_no - 1, max(-1, line_no - 10), -1):
        if i >= len(orig_lines):
            continue
        stripped = orig_lines[i].strip()
        if stripped.startswith('//'):
            doc_lines.insert(0, stripped.lstrip('/').strip())
        elif stripped == '' and not doc_lines:
            continue
        else:
            break
    return ' '.join(doc_lines) if doc_lines else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_idl(path: Path) -> List[Invocable]:
    """Extract CORBA interface methods from an IDL file.

    Args:
        path: Path to the .idl file.

    Returns:
        List[Invocable] — one entry per discovered method.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.error("Cannot read %s: %s", path, exc)
        return []

    clean = _strip_comments(source)
    invocables: List[Invocable] = []

    # Scan for interface blocks
    for iface_m in _INTERFACE_RE.finditer(clean):
        iface_name = iface_m.group("name")
        if iface_name in _KEYWORDS:
            continue

        # Determine module context by scanning before this match
        prefix_text = clean[: iface_m.start()]
        modules_found = [m.group("name") for m in _MODULE_RE.finditer(prefix_text)]
        current_module = modules_found[-1] if modules_found else None

        full_iface = (f"{current_module}::{iface_name}" if current_module else iface_name)

        block_start = iface_m.end() - 1  # points to '{'
        body = _extract_block(clean, block_start)
        if body is None:
            logger.warning("Unmatched brace for interface %s in %s", iface_name, path.name)
            continue

        # Offset of body within full clean source
        body_offset = iface_m.end()

        for method_m in _METHOD_RE.finditer(body):
            name = method_m.group("name")
            if name in _KEYWORDS:
                continue

            rettype_raw = method_m.group("rettype").strip()
            raw_params = method_m.group("params") or ""
            is_oneway = bool(method_m.group("oneway"))

            # Doc comment — search in original source at the same line offset
            abs_pos = body_offset + method_m.start()
            doc = _find_doc_before(source, clean, abs_pos)

            ret_type = _idl_type_to_json(rettype_raw)
            params_str = _parse_params(raw_params)
            sig = f"{name}({params_str}): {ret_type}"
            if is_oneway:
                sig = f"[oneway] {sig}"

            has_doc = bool(doc)
            has_params = bool(params_str)
            has_ret = bool(ret_type)
            if has_doc and has_params and has_ret:
                confidence = "guaranteed"
            elif has_doc and (has_params or has_ret):
                confidence = "high"
            elif has_doc or has_params:
                confidence = "medium"
            else:
                confidence = "low"

            invocables.append(Invocable(
                name=name,
                source_type="corba_method",
                signature=sig,
                parameters=params_str or None,
                return_type=ret_type,
                doc_comment=doc,
                confidence=confidence,
                type_name=full_iface,
                dll_path=str(path),
            ))

    logger.info("IDL: extracted %d methods from %s", len(invocables), path.name)
    return invocables
