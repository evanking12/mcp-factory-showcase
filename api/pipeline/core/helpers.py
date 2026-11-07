from __future__ import annotations

import ast
import logging
import re as _re
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry

from api.infra.config import ARTIFACT_CONTAINER
from api.analysis.sentinel_codes import SENTINEL_DEFAULTS, classify_common_result_code
from api.infra.storage import _download_blob, _get_job_status, _persist_job_status, _upload_to_blob
from api.pipeline.core.evidence_candidates import (
    classify_value_kind,
    infer_expected_identifier_family,
    infer_identifier_family_from_value,
)
from api.pipeline.core.explore_config import (
    CAP_PROFILE as _CAP_PROFILE,
    GAP_RESOLUTION_ENABLED as _CONFIG_GAP_RESOLUTION_ENABLED,
    MAX_EXPLORE_ROUNDS_PER_FUNCTION as _MAX_EXPLORE_ROUNDS_PER_FUNCTION,
    MAX_FUNCTIONS_PER_SESSION as _MAX_FUNCTIONS_PER_SESSION,
    MAX_TOOL_CALLS_PER_FUNCTION as _MAX_TOOL_CALLS_PER_FUNCTION,
)
from api.pipeline.core.finding_status import (
    DISCOVERED_STATUSES as _DISCOVERED_STATUSES,
    FUNCTIONAL_CLASSIFICATION_PATTERN as _FUNCTIONAL_SENTINEL_PATTERNS,
    STATUS_ORDER as _STATUS_ORDER,
    VERIFIED_STATUSES as _VERIFIED_STATUSES,
    classify_finding_status as _classify_finding_status_shared,
)

logger = logging.getLogger("mcp_factory.api")

_SENTINEL_DEFAULTS = SENTINEL_DEFAULTS

# ── Finding status taxonomy (NxM locked 2026-03-25) ──────────────────────────
# Canonical hierarchy used by SFP, Variant Merger, macro coordinator, and all
# stages that classify or rank findings. Higher rank = better outcome.
FINDING_STATUS_RANK: dict[str, int] = dict(_STATUS_ORDER)

# Statuses that count toward "discovered" and "verified" coverage metrics.
FINDING_DISCOVERED_STATUSES = frozenset(_DISCOVERED_STATUSES)
FINDING_VERIFIED_STATUSES = frozenset(_VERIFIED_STATUSES)
TERMINAL_JOB_STATUSES = frozenset({"done", "error"})
STALE_CANCEL_REQUEST_GRACE_SECONDS = 30.0
STALE_NONTERMINAL_JOB_GRACE_SECONDS = 7200.0
TERMINAL_EXPLORE_PHASES = frozenset(
    {
        "",
        "done",
        "awaiting_clarification",
        "error",
        "canceled",
        "cancelled",
        "cancel_requested",
    }
)


def _classify_finding_status(
    return_value: int,
    sentinels: dict,
    sentinel_meaning: str = "",
) -> str:
    """Classify a probe return value into the finding status taxonomy.

    Returns one of: verified_success, functional_precondition_unmet, failure.
    (inferred_success and unknown are assigned by verification/fallback paths,
    not by raw return classification.)
    """
    return _classify_finding_status_shared(
        return_value=return_value,
        sentinels=sentinels,
        sentinel_meaning=sentinel_meaning,
    )


def _normalize_lifecycle_value(value: Any) -> str:
    return str(value or "").strip().lower()


def is_terminal_job_status(status: Any) -> bool:
    return _normalize_lifecycle_value(status) in TERMINAL_JOB_STATUSES


def is_terminal_explore_phase(phase: Any) -> bool:
    return _normalize_lifecycle_value(phase) in TERMINAL_EXPLORE_PHASES


def has_job_lifecycle_inconsistency(status_payload: dict[str, Any] | None) -> bool:
    if not isinstance(status_payload, dict):
        return False
    status = _normalize_lifecycle_value(status_payload.get("status"))
    phase = _normalize_lifecycle_value(status_payload.get("explore_phase"))
    return status == "done" and phase == "exploring"


def is_terminal_job_record(status_payload: dict[str, Any] | None) -> bool:
    if not isinstance(status_payload, dict):
        return False
    return is_terminal_job_status(status_payload.get("status")) and is_terminal_explore_phase(
        status_payload.get("explore_phase")
    )


def is_stale_cancel_requested_job_record(
    status_payload: dict[str, Any] | None,
    *,
    now: float | None = None,
    stale_after_seconds: float = STALE_CANCEL_REQUEST_GRACE_SECONDS,
) -> bool:
    if not isinstance(status_payload, dict):
        return False
    if _normalize_lifecycle_value(status_payload.get("explore_phase")) != "cancel_requested":
        return False
    reference_ts = status_payload.get("updated_at") or status_payload.get("created_at") or 0.0
    try:
        reference = float(reference_ts)
    except Exception:
        return False
    if reference <= 0:
        return False
    current = float(now if now is not None else time.time())
    return (current - reference) >= float(stale_after_seconds)


def is_stale_nonterminal_job_record(
    status_payload: dict[str, Any] | None,
    *,
    now: float | None = None,
    stale_after_seconds: float = STALE_NONTERMINAL_JOB_GRACE_SECONDS,
) -> bool:
    if not isinstance(status_payload, dict):
        return False
    if is_terminal_job_record(status_payload):
        return False
    reference_ts = status_payload.get("updated_at") or status_payload.get("created_at") or 0.0
    try:
        reference = float(reference_ts)
    except Exception:
        return False
    if reference <= 0:
        return False
    current = float(now if now is not None else time.time())
    return (current - reference) >= float(stale_after_seconds)


def _deduplicate_findings_latest(findings: list[dict]) -> list[dict]:
    """Return the latest finding per function from an append-only findings list.

    Findings are appended over time; this picks the last entry per function name,
    which reflects the most up-to-date status after all stages have run.
    """
    latest: dict[str, dict] = {}
    for f in findings:
        fn = f.get("function", "")
        if fn:
            latest[fn] = f
    return list(latest.values())


# ── Shared regex patterns ─────────────────────────────────────────────────────
_WRITE_FN_RE = _re.compile(
    r"(pay|refund|redeem|unlock|process|write|commit|transfer|debit|credit|update|set|create|reserv|reserve|void|cancel|discount|price)",
    _re.I,
)
_INIT_RE = _re.compile(r"(init(ializ)?|startup|start|setup|open|login|logon|connect)", _re.I)
_VERSION_FN_RE = _re.compile(r"get(version|version_?string|build|revision|release)", _re.I)
_GENERIC_PARAM_RE = _re.compile(r"^param_\d+$", _re.I)

_WRITE_RETRY_BUDGET_BY_CLASS: dict[str, int] = {
    "write_denied": 3,
    "not_initialized": 3,
    "account_locked": 2,
    "invalid_input": 3,
    "unknown": 2,
}

# Backward-compatible alias: modules/tests still import this from helpers.
_GAP_RESOLUTION_ENABLED = _CONFIG_GAP_RESOLUTION_ENABLED


def _parse_id_format_pattern(pattern: str) -> str:
    out = []
    for ch in str(pattern):
        if ch == "N":
            out.append(r"\d")
        elif ch == "A":
            out.append(r"[A-Z]")
        elif ch == "X":
            out.append(r"[A-Z0-9]")
        elif ch == "*":
            out.append(r"[A-Z0-9_-]+")
        elif ch in "-_":
            out.append(_re.escape(ch))
        else:
            out.append(_re.escape(ch))
    return "^" + "".join(out) + "$"


def _sample_id_from_vocab(id_formats: list[str], kind: str, attempt: int = 0) -> str:
    """Sample an ID value from vocab id_formats. Falls back to generic patterns."""
    kind = (kind or "").lower()
    _literal_ids = [
        str(fmt)
        for fmt in id_formats
        if isinstance(fmt, str)
        and "-" in str(fmt)
        and not any(ch in str(fmt).upper() for ch in ("NNN", "YYYY", "AAAA", "*"))
    ]
    def _looks_like_sku(value: str) -> bool:
        upper = str(value or "").upper()
        return any(tok in upper for tok in ("WDG-", "GDG-", "PRO-", "ITEM-", "SW-", "ACC-"))

    _kind_tokens = {
        "order": ["ORD", "ORDER"],
        "customer": ["CUST", "ACCT", "ACCOUNT", "CLIENT", "USR"],
        "account": ["CUST", "ACCT", "ACCOUNT", "CLIENT", "USR"],
        "transaction": ["TXN", "TRANS"],
        "reservation": ["RSV", "RESV", "RES"],
    }
    tokens = _kind_tokens.get(kind, [])
    if tokens:
        matches = [
            v for v in _literal_ids
            if any(tok in v.upper() for tok in tokens)
            and not ((kind in {"customer", "account"}) and _looks_like_sku(v))
        ]
        if matches:
            return matches[attempt % len(matches)]
    if kind in {"customer", "account"}:
        customer_like = [
            v for v in _literal_ids
            if not _looks_like_sku(v)
            and any(tok in v.upper() for tok in ("CUST-", "ACCOUNT-", "CLIENT-", "USER-", "ACCT-"))
        ]
        if customer_like:
            return customer_like[attempt % len(customer_like)]
    if _literal_ids:
        return _literal_ids[attempt % len(_literal_ids)]
    _suffix = str(attempt + 1).zfill(3)
    _generic_prefix = {"order": "ORD", "customer": "ID", "account": "ID",
                       "transaction": "TXN", "reservation": "RSV"}
    return f"{_generic_prefix.get(kind, 'ID')}-{_suffix}"


def _sample_sku_from_vocab(vocab: dict, attempt: int = 0) -> str:
    """Extract SKU-like values from vocab. Returns "ITEM-001" as generic fallback."""
    _values = []
    for raw in list(vocab.get("binary_string_ids") or []) + list(vocab.get("id_formats") or []):
        val = str(raw or "").strip()
        if not val or "-" not in val:
            continue
        upper = val.upper()
        if any(tok in upper for tok in ("CUST", "ORD", "TXN", "RSV", "RES")):
            continue
        if any(tok in upper for tok in ("SKU", "WDG", "ACC", "PRO", "GDG", "SW-", "ITEM", "PROD")):
            _values.append(val)
    if _values:
        _deduped = list(dict.fromkeys(_values))
        return _deduped[attempt % len(_deduped)]
    return "ITEM-001"


def _default_scalar_value(param_name: str, json_type: str, description: str, vocab: dict, attempt: int = 0) -> Any:
    name = (param_name or "").lower()
    desc = (description or "").lower()
    jtype = (json_type or "").lower()
    id_formats = [str(x) for x in (vocab.get("id_formats") or []) if x]
    if jtype == "string":
        _default_match = _re.search(r'empty string defaults to "([^"]+)"', description or "", _re.I)
        if _default_match:
            value = str(_default_match.group(1) or "").strip()
            if value:
                return value
        _prefix_match = _re.search(r'must start with "([^"]+)"', description or "", _re.I)
        if _prefix_match:
            prefix = str(_prefix_match.group(1) or "").strip()
            if prefix:
                return f"{prefix}{attempt}"

    if _re.search(r"order", name) or _re.search(r"order", desc):
        return _sample_id_from_vocab(id_formats, "order", attempt)
    if _re.search(r"customer|account", name) or _re.search(r"customer|account", desc):
        return _sample_id_from_vocab(id_formats, "customer", attempt)
    if _re.search(r"sku|product|item", name) or _re.search(r"sku|product|item", desc):
        return _sample_sku_from_vocab(vocab, attempt)
    if _re.search(r"qty|quantity", name) or _re.search(r"qty|quantity", desc):
        return 2 if attempt == 0 else 1
    if _re.search(r"hold", name) and _re.search(r"minute|duration", desc):
        return 30 if attempt == 0 else 15
    if _re.search(r"hold", desc) and _re.search(r"minute|duration", desc):
        return 30 if attempt == 0 else 15
    if _re.search(r"amount|cents|refund|payment|debit|credit", name) or _re.search(r"amount|cents", desc):
        return 100 if attempt > 0 else 1000
    if _re.search(r"points", name) or _re.search(r"points", desc):
        return 100
    if _re.search(r"size|count|length|len", name):
        return 64
    if _re.search(r"mode|flag|enable", name):
        return 1

    if jtype in {"integer", "number"}:
        return 1
    if jtype == "boolean":
        return True
    return "TEST"


def _canonical_args_from_doc(function_doc: str) -> dict[str, Any]:
    """Extract Canonical args JSON from a doc/decompiler comment block."""
    doc = str(function_doc or "")
    marker = "Canonical args:"
    idx = doc.find(marker)
    if idx < 0:
        return {}
    payload = doc[idx + len(marker):].strip()
    if not payload:
        return {}
    first_line = payload.splitlines()[0].strip()
    if " | " in first_line:
        first_line = first_line.split(" | ", 1)[0].strip()
    try:
        parsed = ast.literal_eval(first_line)
    except Exception:
        try:
            parsed = ast.literal_eval(first_line.replace("null", "None"))
        except Exception:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _required_string_prefix_hint(
    description: str,
    function_doc: str,
    param_name: str,
) -> str | None:
    match = _re.search(r'must start with "([^"]+)"', str(description or ""), _re.I)
    if match:
        prefix = str(match.group(1) or "").strip()
        if prefix:
            return prefix
    prefix = _tool_schema_doc_prefix_hint(function_doc, param_name)
    if prefix:
        return prefix
    canonical_args = _canonical_args_from_doc(function_doc)
    canonical_value = canonical_args.get(str(param_name or ""))
    if not isinstance(canonical_value, str):
        return None
    text = canonical_value.strip()
    if not text:
        return None
    for pattern in (
        r"^(sp-operator-)",
        r"^([A-Za-z]+-preview-)",
        r"^([A-Za-z]+-fee-)",
        r"^([A-Za-z]+-hold-)",
        r"^([A-Za-z]+-branch-replay-)",
        r"^([A-Za-z]+-commit-)",
        r"^(?:RESV-|([A-Za-z]+-resv-))",
        r"^(PRQ-)",
        r"^(RPT-)",
        r"^(CFG-)",
        r"^(WFH-)",
    ):
        match = _re.match(pattern, text, _re.I)
        if not match:
            continue
        prefix = match.group(1) if match.lastindex else match.group(0)
        prefix = str(prefix or "").strip()
        if prefix:
            return prefix
    return None


def _struct_base_type_name(raw_type: str) -> str:
    raw = str(raw_type or "").replace("const ", "").strip()
    raw = raw.rstrip("*").strip()
    if not raw:
        return ""
    if any(tok in raw.lower() for tok in ("void", "char", "wchar", "lpcstr", "lpstr", "lpcwstr", "lpwstr")):
        return ""
    return raw


def _simple_json_type_from_ctype(raw_type: str) -> str:
    raw = str(raw_type or "").lower().replace("const ", "").strip()
    if "bool" in raw:
        return "boolean"
    if any(tok in raw for tok in ("word", "dword", "uint", "int", "long", "short", "undefined", "size_t")):
        return "integer"
    if any(tok in raw for tok in ("float", "double")):
        return "number"
    return "string"


def _lookup_struct_definition(inv: dict, param: dict) -> dict | None:
    base_name = _struct_base_type_name(str(param.get("resolved_type") or param.get("type") or ""))
    if not base_name:
        return None
    extras = inv.get("_ghidra_extras") or {}
    for item in extras.get("data_types") or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "struct" and str(item.get("name") or "") == base_name:
            fields = item.get("fields") or []
            if isinstance(fields, list) and fields:
                return item
    return None


def _field_role_hint(field_name: str, field_seed: Any) -> str:
    seed_text = str(field_seed or "").lower()
    name_text = str(field_name or "").lower()
    combined = f"{name_text} {seed_text}"
    if "nonce" in combined:
        return "nonce returned by prior runtime call"
    if "token" in combined or "blob" in combined:
        return "opaque token returned by prior runtime call"
    if "handle" in combined or "session" in combined:
        return "opaque handle returned by prior runtime call"
    return "structured field input"


def _build_structured_arg_scaffold(
    inv: dict,
    param: dict,
    vocab: dict,
    *,
    attempt: int = 0,
    evidence: "EvidenceCandidateRegistry | None" = None,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Build a simple flat struct/object scaffold for one input parameter."""
    if str(param.get("direction") or "in").lower() == "out":
        return None
    struct_def = _lookup_struct_definition(inv, param)
    if not struct_def:
        return None

    function_doc = str(inv.get("doc_comment") or inv.get("doc") or "")
    canonical_args = _canonical_args_from_doc(function_doc)
    pname = str(param.get("name") or "")
    canonical_seed = canonical_args.get(pname)
    if canonical_seed is not None and not isinstance(canonical_seed, dict):
        return None
    canonical_seed = canonical_seed if isinstance(canonical_seed, dict) else {}
    fields = list(struct_def.get("fields") or [])
    if not fields:
        return None

    scaffold: dict[str, Any] = {}
    field_selection: dict[str, Any] = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        field_name = str(field.get("name") or "")
        if not field_name:
            continue
        field_type = str(field.get("type") or "")
        field_json_type = _simple_json_type_from_ctype(field_type)
        field_seed = canonical_seed.get(field_name)
        field_desc = f"{_field_role_hint(field_name, field_seed)}; struct field {field_name}"
        if isinstance(field_seed, (int, bool)) or (
            isinstance(field_seed, str) and field_seed and "-from-" not in field_seed
        ):
            scaffold[field_name] = field_seed
            field_selection[field_name] = {
                "source": "doc.canonical_args",
                "reason": "literal struct field value from canonical args",
                "score": 0.95,
                "rank": 1,
                "candidate_count": 1,
            }
            continue

        candidates = _ranked_param_candidates(
            field_name,
            field_json_type,
            field_desc,
            vocab,
            fn_name=str(inv.get("name") or ""),
            resolved_type=field_type,
            evidence=evidence,
            function_doc=function_doc,
        )
        if not candidates:
            scaffold[field_name] = _default_scalar_value(
                field_name, field_json_type, field_desc, vocab, attempt=attempt,
            )
            field_selection[field_name] = {
                "source": "default.scalar",
                "reason": "no ranked field candidates available",
                "score": 0.0,
                "rank": 1,
                "candidate_count": 1,
            }
            continue
        chosen_idx = min(max(int(attempt), 0), len(candidates) - 1)
        chosen = candidates[chosen_idx]
        scaffold[field_name] = chosen["value"]
        field_selection[field_name] = {
            "source": chosen["source"],
            "reason": chosen["reason"],
            "score": chosen["score"],
            "rank": chosen_idx + 1,
            "candidate_count": len(candidates),
        }
        for extra_key in ("candidate_family", "expected_family", "source_family", "selection_flags", "guard_applied"):
            if extra_key in chosen:
                field_selection[field_name][extra_key] = chosen.get(extra_key)

    if not scaffold:
        return None
    return scaffold, {
        "source": "structured.scaffolder",
        "reason": f"flat struct scaffold for {_struct_base_type_name(struct_def.get('name') or pname)}",
        "score": 0.88,
        "fields": field_selection,
    }


def _generate_xor_token_candidates(target: int, max_results: int = 6) -> list[str]:
    """Generate deterministic UTF-8 strings whose bytes XOR to *target*."""
    if target >= 256 or target == 0:
        return []

    if target < 128:
        codes: list[str] = []
        for prefix in (b"AAA", b"abc", b"123", b"XYZ", b"key", b"COD"):
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
        return codes

    found: list[str] = []
    for prefix_byte in (0x41, 0x42, 0x43, 0x61, 0x62, 0x63, 0x31, 0x32):
        if len(found) >= max_results:
            break
        for cp in range(0x0800, 0x10000):
            try:
                codepoint = chr(cp)
                utf8 = codepoint.encode("utf-8")
            except (ValueError, UnicodeEncodeError):
                continue
            if len(utf8) != 3:
                continue
            xor_val = prefix_byte
            for b in utf8:
                xor_val ^= b
            if xor_val != target:
                continue
            candidate = chr(prefix_byte) + codepoint
            full_utf8 = candidate.encode("utf-8")
            if 0 in full_utf8 or candidate in found:
                continue
            found.append(candidate)
            if len(found) >= max_results:
                break
    return found


def _doc_xor_target_for_param(function_doc: str, param_name: str) -> int | None:
    doc = str(function_doc or "")
    pname = str(param_name or "")
    if not doc or not pname:
        return None
    if not _re.search(fr"\b{_re.escape(pname)}\b", doc, _re.I):
        return None
    param_used_as_string = _re.search(
        fr"lstrlenA\(\(LPCSTR\){_re.escape(pname)}\)"
        fr"|=\s*\*\s*{_re.escape(pname)}\b"
        fr"|\b{_re.escape(pname)}\b\s*=\s*\b{_re.escape(pname)}\b\s*\+\s*1",
        doc,
        _re.I,
    )
    if not param_used_as_string:
        return None
    xor_hint = _re.search(r"\bxor\b|\^", doc, _re.I) or _re.search(r"==\s*0x([0-9a-fA-F]{1,4})", doc, _re.I)
    if not xor_hint:
        return None
    candidates: list[int] = []
    for match in _re.finditer(r"==\s*0x([0-9a-fA-F]{1,8})|==\s*(\d{1,3})", doc, _re.I):
        raw = match.group(1) or match.group(2)
        if raw is None:
            continue
        target = int(raw, 16) if match.group(1) else int(raw)
        if 0 < target < 256:
            candidates.append(target)
    if not candidates:
        return None
    return candidates[0]


def _ranked_param_candidates(
    param_name: str,
    json_type: str,
    description: str,
    vocab: dict,
    *,
    fn_name: str = "",
    resolved_type: str = "",
    has_output_buffer: bool = False,
    string_slot_index: int = 0,
    string_slot_count: int = 0,
    integer_slot_index: int = 0,
    integer_slot_count: int = 0,
    is_buffer_size_context: bool = False,
    evidence: "EvidenceCandidateRegistry | None" = None,
    function_doc: str = "",
) -> list[dict]:
    """Return ranked candidate values for one parameter.

    When an EvidenceCandidateRegistry is provided, its candidates are merged in
    and scored higher than heuristic-only candidates.  The registry replaces
    hardcoded domain knowledge with discovered evidence.
    """
    name = (param_name or "").lower()
    desc = (description or "").lower()
    jtype = (json_type or "").lower()
    fn = (fn_name or "").lower()
    function_doc = str(function_doc or "")
    id_formats = [str(x) for x in (vocab.get("id_formats") or []) if x]
    is_generic_param = bool(_GENERIC_PARAM_RE.match(name))
    is_generic_desc = desc in {"", "input string parameter", "integer input parameter"}
    read_like_fn = bool(_re.search(r"get|lookup|status|history|diagnostic|version|list", fn))
    doc_xor_target = _doc_xor_target_for_param(function_doc, param_name)
    required_prefix = (
        _required_string_prefix_hint(description, function_doc, param_name)
        if jtype not in {"integer", "number", "boolean"}
        else None
    )
    inferred_kinds: list[str] = []
    if evidence is not None and hasattr(evidence, "_infer_param_kinds"):
        try:
            inferred_kinds = list(
                evidence._infer_param_kinds(  # type: ignore[attr-defined]
                    name,
                    desc,
                    fn,
                    jtype,
                    string_slot_index=string_slot_index,
                    string_slot_count=string_slot_count,
                    has_output_buffer=has_output_buffer,
                    is_buffer_size_context=is_buffer_size_context,
                )
            )
        except Exception:
            inferred_kinds = []
    if not inferred_kinds and jtype not in {"integer", "number", "boolean"}:
        if _re.search(r"workflow", fn):
            inferred_kinds.extend(["handle", "string_id"])
        if _re.search(r"quote", fn):
            inferred_kinds.extend(["quote_id", "string_id"])
        if _re.search(r"report", fn):
            inferred_kinds.extend(["report_id", "string_id"])
    expected_identifier_family = infer_expected_identifier_family(
        param_name,
        description,
        json_type,
        fn_name,
        inferred_kinds,
        resolved_type=resolved_type,
    )

    ranked: list[dict] = []

    def _numeric_value(value: Any) -> Any:
        if jtype == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return value

    def _add(value: Any, score: float, source: str, reason: str, **extra: Any) -> None:
        ranked.append({
            "value": _numeric_value(value),
            "score": float(score),
            "source": source,
            "reason": reason,
            **extra,
        })

    if evidence is not None:
        ev_candidates = evidence.get_best_for_param(
            param_name=param_name, json_type=json_type,
            description=description, fn_name=fn_name,
            resolved_type=resolved_type,
            string_slot_index=string_slot_index,
            string_slot_count=string_slot_count,
            has_output_buffer=has_output_buffer,
            is_buffer_size_context=is_buffer_size_context,
        )
        for ec in ev_candidates:
            if (
                jtype in {"integer", "number"}
                and (is_generic_param or is_generic_desc or is_buffer_size_context)
                and str(ec.get("source") or "").startswith("evidence.tier1.ghidra.enum")
            ):
                adjusted = dict(ec)
                adjusted["score"] = round(min(float(adjusted.get("score") or 0.0), 0.17), 3)
                adjusted["reason"] = (
                    f"{adjusted.get('reason', '')}; softened because enum constants are weaker than slot-specific numeric context"
                ).strip("; ")
                ec = adjusted
            extra = {
                key: value
                for key, value in ec.items()
                if key not in {"value", "score", "source", "reason"}
            }
            _add(ec["value"], ec["score"], ec["source"], ec["reason"], **extra)
        if required_prefix and hasattr(evidence, "query_all_string_ids"):
            try:
                prefix_string_entries = list(evidence.query_all_string_ids(max_results=24))  # type: ignore[attr-defined]
            except Exception:
                prefix_string_entries = []
            for entry in prefix_string_entries:
                value = getattr(entry, "value", None)
                if not isinstance(value, str) or not value.startswith(required_prefix):
                    continue
                _add(
                    value,
                    min(1.0, float(getattr(entry, "confidence", 0.0) or 0.0) + float(getattr(entry, "tier", 0) or 0) * 0.1),
                    f"evidence.tier{getattr(entry, 'tier', 0)}.{getattr(entry, 'source', 'prefix_scan')}",
                    f"prefix-matching evidence candidate for required prefix {required_prefix}",
                    candidate_family=infer_identifier_family_from_value(
                        value,
                        getattr(entry, "param_kind", ""),
                        getattr(entry, "discovered_at", ""),
                    ),
                    selection_flags=["prefix_scan_match"],
                )

    if jtype not in {"integer", "number", "boolean"} and doc_xor_target is not None:
        xor_codes = _generate_xor_token_candidates(doc_xor_target)
        for idx, code in enumerate(xor_codes[:3]):
            _add(
                code,
                0.86 - idx * 0.05,
                "function_context.auth_token",
                f"decompiled code XOR-checks {param_name} against 0x{doc_xor_target:02X}",
            )
    if required_prefix:
        _add(
            f"{required_prefix}0",
            0.74,
            "function_context.prefix",
            f"{param_name} must start with required prefix {required_prefix}",
        )
        _add(
            f"{required_prefix}1",
            0.69,
            "function_context.prefix",
            f"{param_name} retry preserving required prefix {required_prefix}",
        )

    if _re.search(r"order", name) or _re.search(r"order", desc):
        _add(_sample_id_from_vocab(id_formats, "order", attempt=0), 0.7, "vocab.id_formats", "order-like parameter")
        _add(_sample_id_from_vocab(id_formats, "order", attempt=1), 0.65, "vocab.id_formats", "order-like retry variant")
    elif _re.search(r"customer|account", name) or _re.search(r"customer|account", desc):
        _add(_sample_id_from_vocab(id_formats, "customer", attempt=0), 0.7, "vocab.id_formats", "customer/account-like parameter")
        _add(_sample_id_from_vocab(id_formats, "customer", attempt=1), 0.65, "vocab.id_formats", "customer/account retry variant")
    elif _re.search(r"amount|cents|refund|payment|debit|credit", name) or _re.search(r"amount|cents", desc):
        _add(2500, 0.7, "heuristic.amount", "common cents baseline")
        _add(1000, 0.6, "heuristic.amount", "smaller cents baseline")
        _add(100, 0.5, "heuristic.amount", "low cents probe")
    elif _re.search(r"points", name) or _re.search(r"points", desc):
        _add(100, 0.7, "heuristic.points", "common points baseline")
        _add(250, 0.6, "heuristic.points", "higher points probe")
    elif _re.search(r"size|count|length|len", name):
        _add(64, 0.7, "heuristic.buffer", "safe buffer/count baseline")
        _add(128, 0.6, "heuristic.buffer", "medium buffer/count retry")
        _add(256, 0.5, "heuristic.buffer", "larger buffer/count retry")
    elif is_buffer_size_context:
        _add(64, 0.7, "heuristic.buffer", "buffer_size heuristic: integer slot adjacent to output buffer")
        _add(128, 0.6, "heuristic.buffer", "adjacent output-buffer size retry")
        _add(256, 0.5, "heuristic.buffer", "larger adjacent output-buffer size retry")
    elif _re.search(r"mode|flag|enable", name):
        _add(1, 0.7, "heuristic.flag", "enabled mode baseline")
        _add(0, 0.6, "heuristic.flag", "disabled mode retry")
    elif jtype in {"integer", "number"} and (
        _re.search(r"channel", name) or _re.search(r"channel", desc)
    ):
        _add(2, 0.82, "function_context.channels", "common stereo channel count")
        _add(1, 0.74, "function_context.channels", "mono channel retry")
    elif jtype in {"integer", "number"} and (
        _re.search(r"sample.?rate", name) or _re.search(r"sample.?rate", desc) or _re.search(r"sample.?rate", fn)
    ):
        _add(44100, 0.84, "function_context.sample_rate", "common audio sample rate")
        _add(48000, 0.78, "function_context.sample_rate", "alternate audio sample rate")
        _add(22050, 0.68, "function_context.sample_rate", "lower audio sample rate retry")
    elif jtype in {"integer", "number"} and (
        _re.search(r"tempo.?change|rate.?change|pitchsemi|semi.?tone", name)
        or _re.search(r"tempo.?change|rate.?change|pitchsemi|semi.?tone", desc)
        or _re.search(r"tempo.?change|rate.?change|pitchsemi|semi.?tone", fn)
    ):
        _add(0.0 if jtype == "number" else 0, 0.84, "function_context.delta", "neutral delta baseline")
        _add(5.0 if jtype == "number" else 5, 0.78, "function_context.delta", "small positive bounded delta")
        _add(-5.0 if jtype == "number" else -5, 0.72, "function_context.delta", "small negative bounded delta")
        _add(12.0 if jtype == "number" else 12, 0.66, "function_context.delta", "larger positive bounded delta")
        _add(-12.0 if jtype == "number" else -12, 0.6, "function_context.delta", "larger negative bounded delta")
    elif jtype in {"integer", "number"} and (
        _re.search(r"tempo|rate|pitch", name) or _re.search(r"tempo|rate|pitch", desc) or _re.search(r"tempo|rate|pitch", fn)
    ):
        _add(1.0 if jtype == "number" else 1, 0.84, "function_context.scalar", "unity baseline for rate-like scalar")
        _add(1.1 if jtype == "number" else 2, 0.78, "function_context.scalar", "slightly increased scalar retry")
        _add(0.9 if jtype == "number" else 0, 0.72, "function_context.scalar", "slightly reduced scalar retry")
        _add(0.5 if jtype == "number" else 3, 0.64, "function_context.scalar", "bounded lower scalar retry")
    elif jtype in {"integer", "number"} and (is_generic_param or is_generic_desc):
        if _re.search(r"sound|bpm|tempo|pitch|rate|sample|channel", fn):
            if integer_slot_index == 0:
                _add(2, 0.8, "function_context.audio", "first generic integer on audio-style function")
                _add(1, 0.72, "function_context.audio", "audio channel-count retry")
            elif integer_slot_index == 1:
                _add(44100, 0.8, "function_context.audio", "second generic integer on audio-style function")
                _add(48000, 0.72, "function_context.audio", "alternate audio sample rate retry")
                _add(22050, 0.64, "function_context.audio", "lower audio sample rate retry")
        elif _re.search(r"purchase", fn):
            if integer_slot_index == 0:
                _add(1, 0.78, "function_context.quantity", "first generic integer on purchase-style function")
                _add(2, 0.7, "function_context.quantity", "purchase quantity retry")
                _add(3, 0.62, "function_context.quantity", "higher purchase quantity retry")
            elif integer_slot_index == 1:
                _add(0, 0.78, "function_context.discount", "second generic integer on purchase-style function")
                _add(100, 0.68, "function_context.discount", "purchase discount retry in basis points")
                _add(500, 0.58, "function_context.discount", "higher purchase discount retry in basis points")
        elif _re.search(r"discount|price", fn):
            if integer_slot_index == 0:
                _add(5000, 0.79, "function_context.amount", "first generic integer on discount-style function")
                _add(2500, 0.71, "function_context.amount", "discount amount retry in cents")
                _add(1000, 0.63, "function_context.amount", "smaller discount amount retry in cents")
        elif _re.search(r"reserve|stock", fn):
            if integer_slot_index == 0:
                _add(1, 0.78, "function_context.quantity", "first generic integer on reserve-style function")
                _add(2, 0.7, "function_context.quantity", "reserve quantity retry")
                _add(3, 0.62, "function_context.quantity", "higher reserve quantity retry")
            elif integer_slot_index == 1:
                _add(30, 0.78, "function_context.duration", "second generic integer on reserve-style function")
                _add(60, 0.68, "function_context.duration", "reserve hold-minutes retry")
                _add(15, 0.58, "function_context.duration", "shorter reserve hold-minutes retry")

    if is_generic_param or is_generic_desc:
        if jtype not in {"integer", "number", "boolean"}:
            if _re.search(r"order|transaction|reservation", fn):
                if _re.search(r"history|list", fn) and has_output_buffer and string_slot_count == 1:
                    _add(_sample_id_from_vocab(id_formats, "customer", attempt=0), 0.72, "function_context.id", "history/list reader keyed by customer-like id")
                    _add(_sample_id_from_vocab(id_formats, "customer", attempt=1), 0.67, "function_context.id", "history/list retry customer variant")
                elif _re.search(r"void", fn) and _re.search(r"transaction", fn):
                    _add(_sample_id_from_vocab(id_formats, "transaction", attempt=0), 0.72, "function_context.id", "void-transaction style function")
                    _add(_sample_id_from_vocab(id_formats, "transaction", attempt=1), 0.67, "function_context.id", "void-transaction retry variant")
                elif _re.search(r"cancel", fn) and _re.search(r"reserv", fn):
                    _add(_sample_id_from_vocab(id_formats, "reservation", attempt=0), 0.72, "function_context.id", "cancel-reservation style function")
                    _add(_sample_id_from_vocab(id_formats, "reservation", attempt=1), 0.67, "function_context.id", "cancel-reservation retry variant")
                elif _re.search(r"transaction", fn):
                    _add(_sample_id_from_vocab(id_formats, "transaction", attempt=0), 0.7, "function_context.id", "transaction-like function with generic string param")
                    _add(_sample_id_from_vocab(id_formats, "transaction", attempt=1), 0.65, "function_context.id", "transaction-like retry variant")
                elif _re.search(r"reserv", fn):
                    _add(_sample_id_from_vocab(id_formats, "reservation", attempt=0), 0.7, "function_context.id", "reservation-like function with generic string param")
                    _add(_sample_id_from_vocab(id_formats, "reservation", attempt=1), 0.65, "function_context.id", "reservation-like retry variant")
                else:
                    _add(_sample_id_from_vocab(id_formats, "order", attempt=0), 0.7, "function_context.id", "order-like function with generic string param")
                    _add(_sample_id_from_vocab(id_formats, "order", attempt=1), 0.65, "function_context.id", "order-like retry variant")
            elif _re.search(r"customer|account|loyalty|balance|refund|payment", fn):
                _add(_sample_id_from_vocab(id_formats, "customer", attempt=0), 0.7, "function_context.id", "customer/account-like function with generic string param")
                _add(_sample_id_from_vocab(id_formats, "customer", attempt=1), 0.65, "function_context.id", "customer/account retry variant")
            elif _re.search(r"purchase|reserve", fn):
                if string_slot_count > 1 and string_slot_index > 0:
                    _add(_sample_sku_from_vocab(vocab, attempt=0), 0.7, "function_context.sku", "later string slot on purchase/reserve-style function")
                    _add(_sample_sku_from_vocab(vocab, attempt=1), 0.65, "function_context.sku", "purchase/reserve retry SKU variant")
                else:
                    _add(_sample_id_from_vocab(id_formats, "customer", attempt=0), 0.7, "function_context.id", "first string slot on purchase/reserve-style function")
                    _add(_sample_id_from_vocab(id_formats, "customer", attempt=1), 0.65, "function_context.id", "purchase/reserve retry customer variant")
            elif _re.search(r"discount|price", fn):
                if doc_xor_target is not None:
                    pass
                elif string_slot_index == 0:
                    _add(_sample_sku_from_vocab(vocab, attempt=0), 0.74, "function_context.sku", "first string slot on discount-style function")
                    _add(_sample_sku_from_vocab(vocab, attempt=1), 0.69, "function_context.sku", "discount retry SKU variant")
                else:
                    _add(_sample_id_from_vocab(id_formats, "customer", attempt=0), 0.62, "function_context.id", "later generic string slot on discount-style function")
                    _add(_sample_id_from_vocab(id_formats, "customer", attempt=1), 0.57, "function_context.id", "discount retry customer variant")
            elif _re.search(r"stock|inventory|product|lookup|check|search", fn):
                _add(_sample_sku_from_vocab(vocab, attempt=0), 0.7, "function_context.sku", "product/stock-like function with generic string param")
                _add(_sample_sku_from_vocab(vocab, attempt=1), 0.65, "function_context.sku", "product/stock retry SKU variant")
        elif has_output_buffer and read_like_fn:
            _add(64, 0.7, "function_context.buffer", "read-style function with output buffer")
            _add(128, 0.6, "function_context.buffer", "read-style buffer retry")
            _add(256, 0.5, "function_context.buffer", "larger read-style buffer retry")

    _binary_string_ids = [str(x) for x in (vocab.get("binary_string_ids") or []) if x]
    if _binary_string_ids and jtype not in {"integer", "number", "boolean"} and not ranked:
        for _bsi, _bsid in enumerate(_binary_string_ids[:3]):
            candidate_family = infer_identifier_family_from_value(_bsid, source_function=fn_name)
            if (
                expected_identifier_family
                and candidate_family not in {expected_identifier_family}
            ):
                continue
            _add(_bsid, 0.52 - _bsi * 0.05, "static_analysis.binary_strings", f"static ID from binary: {_bsid}")

    if jtype in {"integer", "number"}:
        _add(1, 0.4, "default.numeric", "generic positive numeric")
        _add(0, 0.35, "default.numeric", "generic zero numeric")
        _add(2, 0.3, "default.numeric", "generic alternate numeric")
    elif jtype == "boolean":
        _add(True, 0.4, "default.boolean", "generic true baseline")
        _add(False, 0.35, "default.boolean", "generic false retry")
    else:
        _add("TEST", 0.3, "default.string", "generic string baseline")
        _add("A", 0.25, "default.string", "short string retry")
        _add("0", 0.2, "default.string", "numeric-string retry")

    deduped: list[dict] = []
    seen: set[str] = set()
    evidence_ranked = [c for c in ranked if str(c.get("source") or "").startswith("evidence.")]
    heuristic_ranked = [c for c in ranked if c not in evidence_ranked]
    strong_evidence = [
        c for c in evidence_ranked
        if "generic" not in str(c.get("source") or "")
        and not str(c.get("source") or "").startswith("evidence.tier1.ghidra.enum")
    ]
    generic_evidence = [c for c in evidence_ranked if c not in strong_evidence]
    if strong_evidence:
        adjusted_heuristics: list[dict] = []
        for candidate in heuristic_ranked:
            adjusted = dict(candidate)
            source = str(adjusted.get("source") or "")
            if source.startswith(("default.", "heuristic.", "function_context.")):
                adjusted["score"] = round(min(float(adjusted.get("score") or 0.0), 0.18), 3)
                adjusted["reason"] = (
                    f"{adjusted.get('reason', '')}; demoted because stronger runtime evidence exists"
                ).strip("; ")
            elif source.startswith(("vocab.", "static_analysis.")):
                adjusted["score"] = round(min(float(adjusted.get("score") or 0.0), 0.32), 3)
                adjusted["reason"] = (
                    f"{adjusted.get('reason', '')}; softened because stronger runtime evidence exists"
                ).strip("; ")
            adjusted_heuristics.append(adjusted)
        heuristic_ranked = adjusted_heuristics
    adjusted_generic_evidence: list[dict] = []
    for candidate in generic_evidence:
        adjusted = dict(candidate)
        adjusted["score"] = round(min(float(adjusted.get("score") or 0.0), 0.16), 3)
        adjusted["reason"] = (
            f"{adjusted.get('reason', '')}; softened because tier0 generic seeds are weaker than function context"
        ).strip("; ")
        adjusted_generic_evidence.append(adjusted)
    ordered_candidates = strong_evidence + sorted(
        adjusted_generic_evidence + heuristic_ranked,
        key=lambda x: x["score"],
        reverse=True,
    )
    for c in ordered_candidates:
        key = repr(c["value"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    if required_prefix:
        prefix_matched: list[dict] = []
        prefix_other: list[dict] = []
        has_prefix_match = False
        for candidate in deduped:
            value = candidate.get("value")
            if not isinstance(value, str):
                prefix_other.append(candidate)
                continue
            if value.startswith(required_prefix):
                adjusted = dict(candidate)
                source = str(adjusted.get("source") or "")
                floor = 0.99 if source.startswith("evidence.") else 0.78
                adjusted["score"] = round(max(float(adjusted.get("score") or 0.0), floor), 3)
                adjusted["reason"] = (
                    f"{adjusted.get('reason', '')}; promoted because value satisfies required prefix {required_prefix}"
                ).strip("; ")
                prefix_matched.append(adjusted)
                has_prefix_match = True
                continue
            adjusted = dict(candidate)
            source = str(adjusted.get("source") or "")
            if source.startswith("evidence."):
                adjusted["score"] = round(min(float(adjusted.get("score") or 0.0), 0.34), 3)
            else:
                adjusted["score"] = round(min(float(adjusted.get("score") or 0.0), 0.16), 3)
            adjusted["reason"] = (
                f"{adjusted.get('reason', '')}; softened because value does not satisfy required prefix {required_prefix}"
            ).strip("; ")
            prefix_other.append(adjusted)
        if has_prefix_match:
            deduped = sorted(prefix_matched, key=lambda x: x["score"], reverse=True) + sorted(
                prefix_other,
                key=lambda x: x["score"],
                reverse=True,
            )
    if _re.search(r"customer|account|custid|acct", name) or _re.search(r"customer|account", desc):
        customer_prefixes = [
            str(fmt).split("-", 1)[0].upper()
            for fmt in id_formats
            if "-" in str(fmt)
            and any(tok in str(fmt).upper() for tok in ("CUST", "ACCOUNT", "CLIENT", "USER"))
        ]
        preferred: list[dict] = []
        deferred: list[dict] = []
        has_customer_like = False
        for candidate in deduped:
            value = candidate.get("value")
            if not isinstance(value, str):
                preferred.append(candidate)
                continue
            upper = value.upper()
            looks_customer = (
                any(upper.startswith(f"{prefix}-") for prefix in customer_prefixes)
                or any(tok in upper for tok in ("CUST-", "ACCOUNT-", "CLIENT-", "USER-"))
            )
            looks_sku = any(tok in upper for tok in ("WDG-", "GDG-", "PRO-", "ITEM-", "SW-", "ACC-"))
            if looks_customer:
                has_customer_like = True
            if looks_sku and not looks_customer:
                adjusted = dict(candidate)
                adjusted["score"] = round(min(float(adjusted.get("score") or 0.0), 0.12), 3)
                adjusted["reason"] = (
                    f"{adjusted.get('reason', '')}; demoted because customer/account context disfavors SKU-like values"
                ).strip("; ")
                deferred.append(adjusted)
                continue
            preferred.append(candidate)
        deduped = preferred if has_customer_like else (preferred + deferred)
    return deduped


def _is_true_output_param(p: dict) -> bool:
    """True only for parameters that are genuinely output-only buffers.

    Ghidra marks ALL pointer params as direction="out", but byte*/char*
    are almost always INPUT strings (customer IDs, unlock codes, etc.).
    Only explicit output aliases (LPSTR/LPWSTR/etc.) and
    undefined*/int*/uint*/dword* pointers are true output buffers.

    For non-Ghidra schemas (no pointer type), direction="out" is trusted.
    """
    direction = str(p.get("direction") or "in").lower()
    if direction != "out":
        return False
    ptype = str(p.get("type") or "").lower()
    resolved = str(p.get("resolved_type") or "").upper().strip()
    # No pointer indicator — trust the explicit direction="out" label.
    if "*" not in ptype:
        return True
    # Trust explicit Win32 text-output aliases when they are still marked out.
    if resolved in {"LPSTR", "LPWSTR", "LPBYTE", "LPVOID"}:
        return True
    # Has pointer type — override Ghidra's mislabeling of string inputs.
    base = ptype.replace("const ", "").strip().rstrip(" *")
    if base in ("byte", "char", "string", "str"):
        return False
    return True


def _tool_schema_doc_prefix_hint(function_doc: str, param_name: str) -> str | None:
    pname = str(param_name or "").strip()
    if not pname:
        return None
    match = _re.search(
        rf"strncmp\(\s*{_re.escape(pname)}\s*,\s*\"([^\"]+)\"",
        str(function_doc or ""),
        _re.I,
    )
    if not match:
        return None
    prefix = str(match.group(1) or "").strip()
    return prefix or None


def _tool_schema_doc_default_hint(function_doc: str, param_name: str) -> str | None:
    pname = str(param_name or "").strip()
    if not pname:
        return None
    match = _re.search(
        rf"{_re.escape(pname)}\s*=\s*\"([^\"]+)\"",
        str(function_doc or ""),
        _re.I,
    )
    if not match:
        return None
    value = str(match.group(1) or "").strip()
    return value or None


def _tool_schema_param_shape(inv: dict, p: dict) -> tuple[str, str]:
    pname = str(p.get("name") or "arg")
    json_type = str(p.get("json_type") or "string")
    desc = str(p.get("description") or p.get("type") or "string")
    raw_type = str(p.get("resolved_type") or p.get("type") or "").lower()
    direction = str(p.get("direction") or "in").lower()
    function_doc = str(inv.get("doc_comment") or inv.get("doc") or "")

    if (
        direction != "out"
        and not _is_true_output_param(p)
        and any(tok in raw_type for tok in ("char", "wchar", "lpstr", "lpcstr", "lpwstr", "lpcwstr"))
        and json_type.lower() in {"integer", "number"}
    ):
        json_type = "string"
        lowered_desc = desc.lower()
        if lowered_desc in {"parameter recovered by ghidra decompiler", "input string parameter", "parameter of type char *"}:
            desc = "Input text parameter"
        prefix = _tool_schema_doc_prefix_hint(function_doc, pname)
        if prefix and f'must start with "{prefix}"' not in desc:
            desc = f'{desc} (must start with "{prefix}")'.strip()
        default = _tool_schema_doc_default_hint(function_doc, pname)
        if default and f'empty string defaults to "{default}"' not in desc:
            desc = f'{desc} (empty string defaults to "{default}")'.strip()
    return json_type, desc


def _normalize_tool_schema_invocables(invocables: list[dict]) -> None:
    for inv in invocables:
        if not isinstance(inv, dict):
            continue
        params = inv.get("parameters") or []
        for raw_param in params:
            if not isinstance(raw_param, dict):
                continue
            json_type, desc = _tool_schema_param_shape(inv, raw_param)
            raw_param["json_type"] = json_type
            raw_param["description"] = desc


def _fallback_json_type(param: dict) -> str:
    declared = str(param.get("json_type") or "string").lower()
    if declared in {"integer", "number", "boolean"}:
        return declared
    raw = str(param.get("resolved_type") or param.get("type") or "").lower().replace("const ", "").strip()
    raw = raw.rstrip("*").strip()
    if not raw:
        return declared
    if any(tok in raw for tok in ("float", "double")):
        return "number"
    if any(tok in raw for tok in ("bool",)):
        return "boolean"
    if any(tok in raw for tok in ("word", "dword", "uint", "int", "long", "short", "undefined", "size_t")):
        return "integer"
    return declared


def _ranked_pointer_payload_candidates(inv: dict, param: dict, index: int) -> list[dict]:
    fn_lower = str(inv.get("name") or "").lower()
    pname = str(param.get("name") or f"param_{index + 1}").lower()
    pdesc = str(param.get("description") or param.get("type") or "").lower()
    raw_type = str(param.get("resolved_type") or param.get("type") or "").lower().replace("const ", "").strip()
    if "*" not in raw_type:
        return []
    if any(tok in raw_type for tok in ("char", "wchar", "lpstr", "lpcstr", "lpwstr", "lpcwstr")):
        return []
    if "handle" in pdesc or "handle" in pname:
        return []
    looks_payload = bool(_re.search(r"(sample|pcm|audio|buffer|data)", f"{pname} {pdesc}"))
    if not looks_payload and not ("putsamples" in fn_lower and index > 0):
        return []

    payloads: list[dict] = []

    def _add_payload(value: list[Any], frame_count: int, score: float, reason: str) -> None:
        payloads.append({
            "value": value,
            "frame_count": frame_count,
            "score": score,
            "source": "function_context.payload",
            "reason": reason,
        })

    if any(tok in raw_type for tok in ("float *", "double *")):
        _add_payload([0.0, 0.25, -0.25, 0.5, -0.5, 0.75, -0.75, 1.0], 4, 0.86, "stereo-like floating-point sample payload")
        _add_payload([0.0, 0.2, -0.2, 0.4], 2, 0.78, "short floating-point sample payload")
    elif any(tok in raw_type for tok in ("short *", "int16", "word *", "undefined2 *")):
        _add_payload([0, 512, -512, 1024, -1024, 1536, -1536, 2048], 4, 0.84, "stereo-like 16-bit sample payload")
        _add_payload([0, 512, -512, 1024], 2, 0.76, "short 16-bit sample payload")
    elif any(tok in raw_type for tok in ("int *", "uint *", "long *", "undefined4 *")) and index > 0:
        _add_payload([0, 1, -1, 2, -2, 3, -3, 4], 4, 0.72, "bounded integer payload for opaque numeric buffer")
    return payloads


def _ranked_payload_count_candidates(
    inv: dict,
    param: dict,
    payload_candidate: dict[str, Any],
) -> list[dict]:
    fn_lower = str(inv.get("name") or "").lower()
    pname = str(param.get("name") or "").lower()
    pdesc = str(param.get("description") or param.get("type") or "").lower()
    if not _re.search(r"(count|samples|frames|len|length|size)", f"{pname} {pdesc} {fn_lower}"):
        return []
    frame_count = int(payload_candidate.get("frame_count") or 0)
    payload_len = len(payload_candidate.get("value") or [])
    if frame_count <= 0 and payload_len <= 0:
        return []
    counts = [c for c in (frame_count, payload_len, max(1, frame_count // 2)) if isinstance(c, int) and c > 0]
    candidates: list[dict] = []
    for idx, count in enumerate(dict.fromkeys(counts)):
        candidates.append({
            "value": count,
            "score": round(0.88 - idx * 0.08, 3),
            "source": "payload.derived_count",
            "reason": "derived count from synthesized pointer payload",
        })
    return candidates


def _build_ranked_fallback_probe_args(
    inv: dict, vocab: dict, attempt: int = 0,
    evidence: "EvidenceCandidateRegistry | None" = None,
) -> tuple[dict, dict]:
    """Build deterministic fallback args plus per-parameter selection metadata."""
    args: dict = {}
    selection: dict = {}
    params = list(inv.get("parameters") or [])
    has_output_buffer = any(
        _is_true_output_param(p if isinstance(p, dict) else {"name": str(p), "json_type": "string"})
        for p in params
    )
    input_string_params = []
    input_numeric_params = []
    for p in params:
        if isinstance(p, str):
            p = {"name": p, "json_type": "string"}
        if _is_true_output_param(p):
            continue
        if _fallback_json_type(p) in {"integer", "number", "boolean"}:
            input_numeric_params.append(str(p.get("name") or ""))
            continue
        input_string_params.append(str(p.get("name") or ""))
    string_slot_lookup = {name: idx for idx, name in enumerate(input_string_params)}
    integer_slot_lookup = {name: idx for idx, name in enumerate(input_numeric_params)}
    normalized_params = []
    for p in (inv.get("parameters") or []):
        if isinstance(p, str):
            p = {"name": p, "json_type": "string"}
        normalized_params.append(p)
    for idx, p in enumerate(normalized_params):
        pname = str(p.get("name") or "")
        if _is_true_output_param(p):
            continue
        jtype = _fallback_json_type(p)
        pdesc = str(p.get("description") or p.get("type") or "")
        prev_payload = args.get(str(normalized_params[idx - 1].get("name") or "")) if idx > 0 and isinstance(normalized_params[idx - 1], dict) else None
        prev_selection = selection.get(str(normalized_params[idx - 1].get("name") or "")) if idx > 0 and isinstance(normalized_params[idx - 1], dict) else None
        if jtype in {"integer", "number"} and isinstance(prev_payload, list) and isinstance(prev_selection, dict):
            count_candidates = _ranked_payload_count_candidates(
                inv,
                p,
                {
                    "value": prev_payload,
                    "frame_count": prev_selection.get("frame_count"),
                },
            )
            if count_candidates:
                chosen_idx = min(max(int(attempt), 0), len(count_candidates) - 1)
                chosen = count_candidates[chosen_idx]
                args[pname] = chosen["value"]
                selection[pname] = {
                    "source": chosen["source"],
                    "reason": chosen["reason"],
                    "score": chosen["score"],
                    "rank": chosen_idx + 1,
                    "candidate_count": len(count_candidates),
                }
                continue
        payload_candidates = _ranked_pointer_payload_candidates(inv, p, idx)
        if payload_candidates:
            chosen_idx = min(max(int(attempt), 0), len(payload_candidates) - 1)
            chosen = payload_candidates[chosen_idx]
            args[pname] = chosen["value"]
            selection[pname] = {
                "source": chosen["source"],
                "reason": chosen["reason"],
                "score": chosen["score"],
                "rank": chosen_idx + 1,
                "candidate_count": len(payload_candidates),
                "frame_count": chosen["frame_count"],
            }
            continue
        structured = _build_structured_arg_scaffold(
            inv,
            p,
            vocab,
            attempt=attempt,
            evidence=evidence,
        )
        if structured is not None:
            structured_args, structured_selection = structured
            args[pname] = structured_args
            selection[pname] = structured_selection
            continue
        is_buffer_size_context = False
        if jtype.lower() in {"integer", "number"}:
            prev_is_output = idx > 0 and _is_true_output_param(normalized_params[idx - 1])
            if prev_is_output:
                is_buffer_size_context = True
        candidates = _ranked_param_candidates(
            pname,
            jtype,
            pdesc,
            vocab,
            fn_name=str(inv.get("name") or ""),
            resolved_type=str(p.get("resolved_type") or p.get("type") or ""),
            has_output_buffer=has_output_buffer,
            string_slot_index=string_slot_lookup.get(pname, 0),
            string_slot_count=len(input_string_params),
            integer_slot_index=integer_slot_lookup.get(pname, 0),
            integer_slot_count=len(input_numeric_params),
            is_buffer_size_context=is_buffer_size_context,
            evidence=evidence,
            function_doc=str(inv.get("doc_comment") or inv.get("doc") or ""),
        )
        if not candidates:
            val = _default_scalar_value(pname, jtype, pdesc, vocab, attempt=attempt)
            args[pname] = val
            selection[pname] = {
                "source": "default.scalar",
                "reason": "no ranked candidates available",
                "score": 0.0,
                "rank": 1,
                "candidate_count": 1,
            }
            continue
        idx = min(max(int(attempt), 0), len(candidates) - 1)
        chosen = candidates[idx]
        args[pname] = chosen["value"]
        selection[pname] = {
            "source": chosen["source"],
            "reason": chosen["reason"],
            "score": chosen["score"],
            "rank": idx + 1,
            "candidate_count": len(candidates),
        }
        for extra_key in ("candidate_family", "expected_family", "source_family", "selection_flags", "guard_applied"):
            if extra_key in chosen:
                selection[pname][extra_key] = chosen.get(extra_key)
    return args, selection


def _build_fallback_probe_args(
    inv: dict, vocab: dict, attempt: int = 0,
    evidence: "EvidenceCandidateRegistry | None" = None,
) -> dict:
    """Build deterministic fallback args for one probe attempt.

    This is intentionally generic: it uses parameter names/types plus vocabulary
    seeds rather than component-specific constants.
    """
    args, _ = _build_ranked_fallback_probe_args(inv, vocab, attempt=attempt, evidence=evidence)
    return args


def _classify_result_text(result_text: str, sentinels: dict | None = None) -> dict:
    m = _re.search(r"Returned:\s*(-?\d+)", result_text or "")
    if not m:
        return {
            "has_return": False,
            "format_guess": "no_return_detected",
            "confidence": 0.0,
            "source": "none",
        }
    signed = int(m.group(1))
    unsigned = signed & 0xFFFFFFFF
    meaning = ""
    if isinstance(sentinels, dict):
        meaning = str(sentinels.get(unsigned) or "")
    if not meaning:
        meaning = classify_common_result_code(unsigned) or ""

    if signed == 0:
        fmt = "bool_style_success"
        conf = 1.0
        src = "deterministic.zero"
    elif meaning:
        if meaning.startswith("HRESULT") or meaning.startswith("HRESULT_FROM_WIN32"):
            fmt = "hresult_like"
            conf = 0.98
            src = "deterministic.common_hresult"
        elif meaning.startswith("NTSTATUS"):
            fmt = "ntstatus_like"
            conf = 0.98
            src = "deterministic.common_ntstatus"
        elif meaning.startswith("Win32"):
            fmt = "win32_error"
            conf = 0.95
            src = "deterministic.common_win32"
        elif "-like" in meaning:
            fmt = "high_bit_failure_family"
            conf = 0.75
            src = "heuristic.high_bit_family"
        else:
            fmt = "custom_signed_negative"
            conf = 0.9
            src = "deterministic.default_sentinel"
    elif signed < 0:
        fmt = "custom_signed_negative"
        conf = 0.7
        src = "heuristic.signed_negative"
    elif unsigned >= 0x80000000:
        fmt = "high_bit_unknown"
        conf = 0.45
        src = "heuristic.high_bit"
    elif signed > 0:
        fmt = "custom_positive_status_or_data"
        conf = 0.65
        src = "heuristic.custom_positive"
    else:
        fmt = "domain_or_non_sentinel"
        conf = 0.3
        src = "heuristic.low_value"

    return {
        "has_return": True,
        "signed": signed,
        "unsigned": unsigned,
        "hex": f"0x{unsigned:08X}",
        "format_guess": fmt,
        "confidence": conf,
        "source": src,
        "meaning": meaning,
    }


def _sentinel_class_from_classification(classification: dict) -> str:
    meaning = (classification.get("meaning") or "").lower()
    if "write" in meaning and "denied" in meaning:
        return "write_denied"
    if "not initialized" in meaning:
        return "not_initialized"
    if "locked" in meaning:
        return "account_locked"
    if "invalid" in meaning or "not found" in meaning or "null" in meaning:
        return "invalid_input"
    return "unknown"


def _write_policy_precheck(
    fn_name: str,
    args: dict,
    vocab: dict,
    unlock_result: dict | None,
 ) -> tuple[bool, str | None, str | None]:
    if not _WRITE_FN_RE.search(fn_name):
        return True, None, None

    # Q16§5: allow write probes even when unlock failed — the LLM probe loop
    # or deterministic fallback may discover the correct init sequence.
    # Safety is enforced by the per-sentinel-class retry budget in _explore_one.
    # (Previously this was a hard block that permanently gated all write fns.)

    # Only block if NO args at all — any non-empty arg set is allowed.
    # Safety is enforced by the per-sentinel-class retry budget in _explore_one,
    # not by blocking probes before they can even try.
    if not args:
        if _re.search(r"(create|new|open|init|initialize|startup|connect)", fn_name, _re.I):
            return True, None, None
        return False, "schema_missing", "write function probe requires at least one argument"

    amount_keys = {k for k in args if _re.search(r"amount|points|cents|value", k, _re.I)}
    for k in amount_keys:
        if k not in args:
            continue
        try:
            v = int(args[k])
        except (ValueError, TypeError):
            continue
        if v <= 0 or v > 1_000_000_000:
            return False, "policy_exhausted", f"{k}={v} outside bounded write-policy range"

    return True, None, None


def _build_tool_schemas(invocables: list[dict]) -> list[dict]:
    """Build OpenAI tool call schemas from a list of invocable dicts."""
    from api.services.chat import _RECORD_FINDING_TOOL, _ENRICH_INVOCABLE_TOOL  # type: ignore

    tool_schemas: list[dict] = []
    for inv in invocables:
        props: dict = {}
        required: list = []
        for p in (inv.get("parameters") or []):
            if isinstance(p, str):
                p = {"name": p, "type": "string"}
            pname = p.get("name", "arg")
            json_type, _desc = _tool_schema_param_shape(inv, p)
            _ptype = str(p.get("type") or "").lower()
            _dir = str(p.get("direction") or "in").lower()
            if _dir == "out" and "*" in _ptype and _ptype.replace("const ", "").strip().rstrip(" *") in ("byte", "char", "string", "str"):
                _desc += " [LIKELY INPUT STRING — pass customer ID, name, or code value]"
            props[pname] = {
                "type": json_type,
                "description": _desc,
            }
            if not _is_true_output_param(p):
                required.append(pname)
        safe_name = _re.sub(r"[^a-zA-Z0-9_.\-]", "_", inv["name"])[:64]
        desc = inv.get("doc") or inv.get("description") or inv.get("signature") or inv["name"]
        tool_schemas.append({
            "type": "function",
            "function": {
                "name": safe_name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        })
    tool_schemas.append(_RECORD_FINDING_TOOL)
    tool_schemas.append(_ENRICH_INVOCABLE_TOOL)
    return tool_schemas


def _strip_output_buffer_params(tc_args: dict, p_lookup: dict) -> dict:
    """Return *tc_args* with genuine output-buffer parameters removed.

    FIX-1 invariant: only strip params whose Ghidra type is a pointer to a
    numeric/undefined base type (e.g. ``int*``, ``undefined4*``).  Do NOT
    strip params whose base type is ``byte`` or a text-like type — Ghidra
    tags ``byte*`` as ``direction=out`` because it is a pointer, but such
    params are commonly string *inputs* (customer_id, order_id, etc.).

    READS:  tc_args   — {param_name: value} dict from tool call
            p_lookup  — {param_name: invocable_param_dict}
    WRITES: returns a new dict (never mutates tc_args or p_lookup)
    INVARIANT: every non-output-buffer key from tc_args is present in result
    """
    result: dict = {}
    for k, v in tc_args.items():
        p = p_lookup.get(k, {}) if isinstance(p_lookup.get(k, {}), dict) else {}
        ptype = str(p.get("type") or "").lower().replace("const ", "").strip().rstrip(" *")
        implicit_numeric_output = (
            not str(p.get("direction") or "").strip()
            and "*" in str(p.get("type") or "")
            and ptype in {
                "undefined", "undefined2", "undefined4", "undefined8",
                "uint", "uint32_t", "int", "int32_t", "dword",
                "ulong", "uint4", "uint8", "long", "ulong32",
            }
        )
        if not (_is_true_output_param(p) or implicit_numeric_output):
            result[k] = v
    return result


def _extract_result_output_values(result_text: str) -> dict:
    """Parse executor output lines like ``param_5='RESV-...'`` into values."""
    result: dict = {}
    for raw_line in str(result_text or "").splitlines()[1:]:
        line = str(raw_line or "").strip()
        if "=" not in line:
            continue
        key, value_text = line.split("=", 1)
        key = key.strip()
        value_text = value_text.strip()
        if not key or not value_text:
            continue
        try:
            value = ast.literal_eval(value_text)
        except Exception:
            _int_match = _re.match(r"^(-?\d+)\b", value_text)
            if _int_match:
                try:
                    value = int(_int_match.group(1))
                except Exception:
                    value = value_text.strip("'\"")
            else:
                value = value_text.strip("'\"")
        if value not in (None, ""):
            result[key] = value
    return result


def _looks_output_like_param(param: dict, key: str = "") -> bool:
    pname = str((param or {}).get("name") or key or "").strip().lower()
    desc = str((param or {}).get("description") or "").strip().lower()
    if pname.startswith("out_"):
        return True
    if pname.startswith(("pdw", "pout", "pszout", "lpszout")):
        return True
    return "output" in desc or "populated" in desc


def _normalize_output_value_for_param(param: dict, value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    if set(value) != {"field_0"}:
        return value
    field_0 = value.get("field_0")
    json_type = str((param or {}).get("json_type") or "").strip().lower()
    resolved = str((param or {}).get("resolved_type") or (param or {}).get("type") or "").lower()
    if json_type in {"integer", "number"} and isinstance(field_0, (int, float)) and not isinstance(field_0, bool):
        return field_0
    if any(token in resolved for token in ("int*", "uint*", "dword*", "long*", "short*", "size_t*", "ssize_t*")):
        return field_0
    return value


def _merge_result_output_values(tc_args: dict, result_text: str, p_lookup: dict) -> dict:
    """Merge successful output-buffer values back into the preserved working call."""
    merged = dict(tc_args or {})
    for key, value in _extract_result_output_values(result_text).items():
        param = p_lookup.get(key, {})
        value = _normalize_output_value_for_param(param, value)
        if (
            _is_true_output_param(param)
            or str(param.get("direction") or "").lower() == "out"
            or _looks_output_like_param(param, key)
            or key not in merged
        ):
            merged[key] = value
    return merged


def _snapshot_schema_stage(job_id: str, stage_blob_name: str) -> None:
    """Copy current mcp_schema.json to a stage-specific blob for diffing."""
    try:
        _raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/mcp_schema.json")
        _upload_to_blob(ARTIFACT_CONTAINER, f"{job_id}/{stage_blob_name}", _raw)
    except Exception as _se:
        logger.debug("[%s] schema snapshot failed (%s): %s", job_id, stage_blob_name, _se)


def _save_stage_context(job_id: str, blob_name: str, content: str) -> None:
    """Persist a plain-text model-context snapshot for one pipeline phase.

    Captures the system prompt (or a human-readable summary of it) at the
    start of a phase so that save-session can expose what the LLM saw at
    each stage.  Failures are silently swallowed — this is diagnostic only.
    """
    try:
        _upload_to_blob(ARTIFACT_CONTAINER, f"{job_id}/{blob_name}",
                        content.encode("utf-8"))
    except Exception as _ce:
        logger.debug("[%s] stage context save failed (%s): %s", job_id, blob_name, _ce)


def _set_explore_status(
    job_id: str,
    explored: int,
    total: int,
    message: str,
    *,
    stage: str = "",
) -> None:
    current = _get_job_status(job_id) or {}
    terminal_or_explicit_phase = {
        "done",
        "awaiting_clarification",
        "error",
        "cancel_requested",
        "queued",
    }
    update: dict = {
        **current,
        "explore_phase": stage if stage in terminal_or_explicit_phase else "exploring",
        "explore_progress": f"{explored}/{total}",
        "explore_message": message,
        "updated_at": time.time(),
    }
    if stage:
        update["explore_stage"] = stage
    _persist_job_status(job_id, update)


def _ctx_explored_count(ctx: Any) -> int:
    """Return explored count for both typed contexts and lightweight test doubles."""
    getter = getattr(ctx, "explored_count", None)
    if callable(getter):
        try:
            return int(getter())
        except Exception:
            pass

    state = getattr(ctx, "_state", None)
    if isinstance(state, dict):
        try:
            return int(state.get("explored") or 0)
        except Exception:
            return 0
    return 0


def _cancel_requested(job_id: str) -> bool:
    """Return True if the explore worker has been asked to stop early."""
    return bool((_get_job_status(job_id) or {}).get("explore_cancel_requested"))


def _infer_param_desc(pname: str, ptype: str, fn_findings: list) -> str:
    """Produce a human-readable parameter description from type info and findings.
    Called when the stored description is just Ghidra boilerplate."""
    t = (ptype or "").lower().replace("const ", "").strip()
    base = t.rstrip(" *").strip()
    is_ptr = "*" in t

    all_text = " ".join(
        (f.get("finding", "") + " " + f.get("notes", ""))
        for f in fn_findings
    )

    if is_ptr and base in {"uint", "ulong", "ushort", "int", "uint32_t", "dword"}:
        m = _re.search(rf"{_re.escape(pname)}\s*[=:]\s*(\S+)", all_text)
        val = f" (observed: {m.group(1)})" if m else ""
        return f"Output — receives integer result{val}"

    if is_ptr and base in {"undefined", "undefined2", "undefined4", "undefined8", "void"}:
        if "pipe-delimited" in all_text or "|" in all_text:
            return "Output buffer — receives pipe-delimited key=value result string"
        if "balance" in all_text and pname in ("param_2", "param_4"):
            return "Output buffer — receives balance or result data"
        return "Output buffer — receives result data (omit from call; auto-allocated)"

    if t == "byte *":
        id_patterns = list(dict.fromkeys(_re.findall(r'[A-Z]{2,6}-[\w-]+', all_text)))
        if id_patterns:
            return "Input string — e.g. " + " or ".join(f"'{p}'" for p in id_patterns[:3])
        return "Input string parameter"

    if base == "hinstance__":
        return "DLL instance handle (Windows DllMain param)"
    if t == "void *":
        return "Reserved pointer (Windows DllMain param)"

    if base in {"uint", "ulong", "ushort", "int", "uint32_t", "dword", "ulong32"}:
        m = _re.search(rf"{_re.escape(pname)}\s*[=:]\s*(\S+)", all_text)
        val = f" (e.g. {m.group(1)})" if m else ""
        return f"Integer input parameter{val}"

    return f"Parameter of type {ptype}"


# ── Shared MC decision persistence ───────────────────────────────────────────

def _persist_mc_decision(ctx, mc_id: str, decision: dict) -> None:
    """Write a micro coordinator decision artifact for observability."""
    import json
    decision = dict(decision or {})
    decision.setdefault("recorded_at", time.time())
    try:
        if hasattr(ctx, "persist_mc_decision"):
            ctx.persist_mc_decision(mc_id, decision)
        else:
            state = getattr(ctx, "_state", None)
            if isinstance(state, dict):
                mc_state = state.setdefault("mc_decisions", {})
                if isinstance(mc_state, dict):
                    mc_state[mc_id] = decision
    except Exception:
        pass
    try:
        blob_key = f"{ctx.job_id}/mc-decisions/{mc_id}.json"
        existing: list = []
        try:
            existing = json.loads(_download_blob(ARTIFACT_CONTAINER, blob_key))
        except Exception:
            pass
        existing.append(decision)
        _upload_to_blob(ARTIFACT_CONTAINER, blob_key,
                        json.dumps(existing, indent=2).encode())
    except Exception as exc:
        logger.debug("[%s] %s: decision artifact write failed: %s",
                     ctx.job_id, mc_id, exc)
