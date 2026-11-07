"""
openapi_analyzer.py — Invocable extractor for OpenAPI 3.x / Swagger 2.x
                       and JSON-RPC 2.0 service descriptor files.

Supported input files:
  • .yaml / .yml  — OpenAPI 3.0 or Swagger 2.0 spec
  • .json         — OpenAPI 3.0, Swagger 2.0, or JSON-RPC 2.0 service descriptor

Each HTTP operation (path + method) maps to one Invocable with
source_type='openapi_operation'; each JSON-RPC method maps to
source_type='jsonrpc_method'.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False

from schema import Invocable

logger = logging.getLogger(__name__)

# Matches any non-word character (for sanitising route paths to identifiers)
_NON_WORD = re.compile(r'\W')

# JSON type → JSON Schema type normalisation
_TYPE_MAP: Dict[str, str] = {
    "integer": "integer",
    "int":     "integer",
    "int32":   "integer",
    "int64":   "integer",
    "number":  "number",
    "float":   "number",
    "double":  "number",
    "boolean": "boolean",
    "bool":    "boolean",
    "array":   "array",
    "object":  "object",
    "string":  "string",
    "str":     "string",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_spec(path: Path) -> Optional[dict]:
    """Load JSON or YAML file; return None on failure."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.error("Cannot read %s: %s", path, exc)
        return None

    ext = path.suffix.lower()
    if ext in (".yaml", ".yml"):
        if not _YAML_OK:
            logger.error("PyYAML not installed; cannot parse %s", path)
            return None
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            logger.error("YAML parse error in %s: %s", path, exc)
            return None
    else:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error in %s: %s", path, exc)
            return None


def _openapi_version(spec: dict) -> Optional[str]:
    """Return '3', '2', or None depending on spec format."""
    if "openapi" in spec:
        return "3"
    if "swagger" in spec:
        return "2"
    return None


def _is_jsonrpc(spec: dict) -> bool:
    """Return True if this looks like a JSON-RPC service descriptor."""
    return "methods" in spec and isinstance(spec["methods"], list)


def _param_string_openapi(parameters: list) -> str:
    """Build a 'name: type' comma-joined param string from an OpenAPI parameters list."""
    parts: List[str] = []
    for p in parameters:
        if not isinstance(p, dict):
            continue
        name = p.get("name", "param")
        schema = p.get("schema") or {}
        ptype = _TYPE_MAP.get(str(schema.get("type", "")).lower(), schema.get("type", "any"))
        required = p.get("required", False)
        loc = p.get("in", "query")
        parts.append(f"{name}: {ptype} ({loc}{'*' if required else ''})")
    return ", ".join(parts)


def _response_description(responses: dict) -> Optional[str]:
    """Extract a return description from the responses block."""
    for code in ("200", "201", "default"):
        resp = responses.get(code)
        if isinstance(resp, dict):
            desc = resp.get("description") or ""
            if desc:
                return desc
    return None


def _confidence_from(has_doc: bool, has_params: bool, has_ret: bool) -> str:
    if has_doc and has_params and has_ret:
        return "guaranteed"
    if has_doc and (has_params or has_ret):
        return "high"
    if has_doc or has_params:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# OpenAPI 3.x / Swagger 2.x
# ---------------------------------------------------------------------------

def _parse_openapi(spec: dict, path: Path) -> List[Invocable]:
    """Extract operations from an OpenAPI / Swagger spec."""
    invocables: List[Invocable] = []
    paths_block = spec.get("paths") or {}

    # Collect global parameters / servers for context
    servers = spec.get("servers") or spec.get("host") or ""
    base_path = spec.get("basePath", "")

    for route, path_item in paths_block.items():
        if not isinstance(path_item, dict):
            continue
        # Parameters defined at the path level (shared across methods)
        path_level_params = path_item.get("parameters") or []

        for method in ("get", "post", "put", "patch", "delete", "options", "head"):
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue

            op_id = op.get("operationId") or (
                f"{method}_{re.sub(_NON_WORD, '_', route).strip('_')}"
            )
            summary = op.get("summary") or op.get("description") or ""
            description = op.get("description") or summary

            # Merge path-level + operation-level parameters
            op_params = path_level_params + (op.get("parameters") or [])
            # Resolve $ref parameters (shallow)
            resolved_params = []
            components = spec.get("components", {}).get("parameters", {})
            for p in op_params:
                if "$ref" in p:
                    ref_name = p["$ref"].split("/")[-1]
                    resolved_params.append(components.get(ref_name, p))
                else:
                    resolved_params.append(p)

            params_str = _param_string_openapi(resolved_params)

            # Request body (POST/PUT/PATCH)
            req_body = op.get("requestBody") or {}
            if req_body:
                content = req_body.get("content") or {}
                for mt, schema_wrap in content.items():
                    schema = (schema_wrap or {}).get("schema") or {}
                    props = schema.get("properties") or {}
                    body_parts = [
                        f"{k}: {_TYPE_MAP.get(str(v.get('type','')).lower(), v.get('type','any'))}"
                        for k, v in props.items()
                    ]
                    if body_parts:
                        suffix = f"body({', '.join(body_parts)})"
                        params_str = f"{params_str}, {suffix}" if params_str else suffix
                    break  # first media type only

            # Return type from responses
            responses = op.get("responses") or {}
            ret_desc = _response_description(responses)

            tags = op.get("tags") or []
            tag_str = f"[{', '.join(tags)}] " if tags else ""

            sig = f"{method.upper()} {route}({params_str})"

            confidence = _confidence_from(
                has_doc=bool(summary),
                has_params=bool(params_str),
                has_ret=bool(ret_desc),
            )

            invocables.append(Invocable(
                name=op_id,
                source_type="openapi_operation",
                signature=sig,
                parameters=params_str or None,
                return_type=ret_desc,
                doc_comment=f"{tag_str}{description}" if description else None,
                confidence=confidence,
                dll_path=str(path),
            ))

    logger.info("OpenAPI: extracted %d operations from %s", len(invocables), path.name)
    return invocables


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 service descriptor
# ---------------------------------------------------------------------------

def _parse_jsonrpc(spec: dict, path: Path) -> List[Invocable]:
    """Extract methods from a JSON-RPC 2.0 service descriptor."""
    invocables: List[Invocable] = []
    service_name = spec.get("service") or spec.get("name") or path.stem

    for method in spec.get("methods") or []:
        if not isinstance(method, dict):
            continue
        name = method.get("name") or method.get("method") or "unknown"
        description = method.get("description") or method.get("summary") or ""
        params_raw = method.get("params") or method.get("parameters") or []
        ret_raw = method.get("returns") or method.get("result") or {}

        # Params: list of strings or {name, type, description} dicts
        param_parts: List[str] = []
        for p in params_raw:
            if isinstance(p, str):
                param_parts.append(f"{p}: any")
            elif isinstance(p, dict):
                pname = p.get("name", "param")
                ptype = _TYPE_MAP.get(str(p.get("type", "")).lower(), p.get("type", "any"))
                param_parts.append(f"{pname}: {ptype}")
        params_str = ", ".join(param_parts)

        # Return type
        if isinstance(ret_raw, str):
            ret_type = _TYPE_MAP.get(ret_raw.lower(), ret_raw)
        elif isinstance(ret_raw, dict):
            ret_type = str(ret_raw.get("type") or ret_raw.get("description") or "")
        else:
            ret_type = None

        sig = f"{service_name}.{name}({params_str})"
        if ret_type:
            sig += f" -> {ret_type}"

        confidence = _confidence_from(
            has_doc=bool(description),
            has_params=bool(params_str),
            has_ret=bool(ret_type),
        )

        invocables.append(Invocable(
            name=name,
            source_type="jsonrpc_method",
            signature=sig,
            parameters=params_str or None,
            return_type=ret_type,
            doc_comment=description or None,
            confidence=confidence,
            dll_path=str(path),
        ))

    logger.info("JSON-RPC: extracted %d methods from %s", len(invocables), path.name)
    return invocables


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_openapi(path: Path) -> List[Invocable]:
    """Extract invocables from an OpenAPI/Swagger or JSON-RPC descriptor file.

    Args:
        path: Path to the spec file (.yaml, .yml, or .json).

    Returns:
        List[Invocable] — one entry per discovered operation / method.
    """
    spec = _load_spec(path)
    if spec is None or not isinstance(spec, dict):
        return []

    if _is_jsonrpc(spec) and "openapi" not in spec and "swagger" not in spec:
        return _parse_jsonrpc(spec, path)

    version = _openapi_version(spec)
    if version:
        return _parse_openapi(spec, path)

    logger.warning("%s: unrecognised spec format (no openapi/swagger/methods key)", path.name)
    return []
