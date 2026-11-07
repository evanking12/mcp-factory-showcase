"""
wsdl_analyzer.py — Invocable extractor for SOAP/WSDL service description files.

Parses WSDL 1.1 (and limited WSDL 2.0) XML documents and maps each
<operation> in a <portType> (WSDL 1.1) or <interface> (WSDL 2.0) to an
Invocable with source_type='soap_operation'.

Parameters are resolved by following <message> → <part> references (WSDL 1.1)
or inline <input> schema references (WSDL 2.0).

Dependencies: lxml (already in requirements)
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from lxml import etree as ET
    _LXML_OK = True
except ImportError:
    import xml.etree.ElementTree as ET  # type: ignore
    _LXML_OK = False

from schema import Invocable

logger = logging.getLogger(__name__)

# ── XML namespaces ────────────────────────────────────────────────────────────
_WSDL_NS_11  = "http://schemas.xmlsoap.org/wsdl/"
_WSDL_NS_20  = "http://www.w3.org/ns/wsdl"
_SOAP_NS     = "http://schemas.xmlsoap.org/wsdl/soap/"
_SOAP12_NS   = "http://schemas.xmlsoap.org/wsdl/soap12/"
_XSD_NS      = "http://www.w3.org/2001/XMLSchema"
_SOAP_ENC_NS = "http://schemas.xmlsoap.org/soap/encoding/"

_NS11 = {"wsdl": _WSDL_NS_11, "soap": _SOAP_NS, "xsd": _XSD_NS}
_NS20 = {"wsdl": _WSDL_NS_20, "xsd": _XSD_NS}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _local(tag) -> str:
    """Strip namespace URI from a Clark-notation tag.
    Returns empty string for non-string tags (e.g. lxml Comment/PI nodes).
    """
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_text(element, *path_parts) -> str:
    """Walk a chain of child tag local-names, return .text or ''."""
    cur = element
    for part in path_parts:
        nxt = next(
            (c for c in cur if _local(c.tag) == part),
            None,
        )
        if nxt is None:
            return ""
        cur = nxt
    return (cur.text or "").strip()


def _attr(element, name: str, default: str = "") -> str:
    for k, v in element.attrib.items():
        if _local(k) == name:
            return v
    return default


def _strip_ns(ref: str) -> str:
    """Remove a 'prefix:' or '{uri}' namespace qualifier from a QName."""
    if "}" in ref:
        return ref.rsplit("}", 1)[-1]
    if ":" in ref:
        return ref.split(":", 1)[1]
    return ref


def _xsd_type_to_json(xsd_type: str) -> str:
    mapping = {
        "string": "string", "token": "string", "normalizedString": "string",
        "int": "integer", "integer": "integer", "long": "integer",
        "short": "integer", "byte": "integer", "unsignedInt": "integer",
        "unsignedLong": "integer", "unsignedShort": "integer",
        "float": "number", "double": "number", "decimal": "number",
        "boolean": "boolean",
        "date": "string", "dateTime": "string", "time": "string",
        "base64Binary": "string", "hexBinary": "string",
        "anyURI": "string", "anyType": "any",
    }
    base = _strip_ns(xsd_type)
    return mapping.get(base, base or "any")


# ---------------------------------------------------------------------------
# WSDL 1.1 parsing
# ---------------------------------------------------------------------------

def _parse_wsdl11(root) -> List[Invocable]:
    """Parse a WSDL 1.1 document; return list of Invocable."""
    invocables: List[Invocable] = []

    # Build message → parts map
    # messages: {localName: [(partName, partType), ...]}
    messages: Dict[str, List[Tuple[str, str]]] = {}
    for msg in root.iter():
        if _local(msg.tag) != "message":
            continue
        msg_name = _attr(msg, "name")
        parts: List[Tuple[str, str]] = []
        for part in msg:
            if _local(part.tag) != "part":
                continue
            pname = _attr(part, "name")
            ptype = _xsd_type_to_json(
                _attr(part, "type") or _attr(part, "element") or "any"
            )
            if pname:
                parts.append((pname, ptype))
        if msg_name:
            messages[msg_name] = parts

    # Build documentation map from <portType> docs
    doc_map: Dict[str, str] = {}
    for op in root.iter():
        if _local(op.tag) != "operation":
            continue
        op_name = _attr(op, "name")
        doc = ""
        for child in op:
            if _local(child.tag) == "documentation":
                doc = (child.text or "").strip()
            if _local(child.tag) == "fault":
                pass  # ignore faults for now
        if op_name and doc:
            doc_map[op_name] = doc

    # Walk portTypes
    for port_type in root.iter():
        if _local(port_type.tag) != "portType":
            continue
        pt_name = _attr(port_type, "name")

        for op in port_type:
            if _local(op.tag) != "operation":
                continue
            op_name = _attr(op, "name")
            if not op_name:
                continue

            doc = (doc_map.get(op_name) or "").strip()
            input_msg = output_msg = None

            for child in op:
                tag = _local(child.tag)
                if tag == "input":
                    input_msg = _strip_ns(_attr(child, "message"))
                elif tag == "output":
                    output_msg = _strip_ns(_attr(child, "message"))
                elif tag == "documentation":
                    doc = doc or (child.text or "").strip()

            # Resolve parameters
            params_list = messages.get(input_msg or "", [])
            params_str = ", ".join(f"{n}: {t}" for n, t in params_list)

            # Resolve return type
            out_parts = messages.get(output_msg or "", [])
            if out_parts:
                ret_type = out_parts[0][1] if len(out_parts) == 1 else (
                    f"object({', '.join(t for _, t in out_parts)})"
                )
            else:
                ret_type = None

            sig = f"{op_name}({params_str})"
            if ret_type:
                sig += f": {ret_type}"

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
                name=op_name,
                source_type="soap_operation",
                signature=sig,
                parameters=params_str or None,
                return_type=ret_type,
                doc_comment=doc or None,
                confidence=confidence,
                type_name=pt_name or None,
            ))

    return invocables


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_wsdl(path: Path) -> List[Invocable]:
    """Extract SOAP operations from a WSDL service description file.

    Args:
        path: Path to the .wsdl file.

    Returns:
        List[Invocable] — one entry per discovered operation.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.error("Cannot read %s: %s", path, exc)
        return []

    try:
        if _LXML_OK:
            root = ET.fromstring(text.encode("utf-8"))
        else:
            root = ET.fromstring(text)
    except Exception as exc:
        logger.error("XML parse error in %s: %s", path, exc)
        return []

    root_local = _local(root.tag)
    if root_local == "definitions":
        invocables = _parse_wsdl11(root)
    elif root_local == "description":
        # WSDL 2.0 — minimal support: fall back to WSDL 1.1 parser for overlapping tags
        invocables = _parse_wsdl11(root)
    else:
        logger.warning("%s: root element <%s> is not a WSDL definitions element", path.name, root_local)
        return []

    logger.info("WSDL: extracted %d operations from %s", len(invocables), path.name)
    return invocables
