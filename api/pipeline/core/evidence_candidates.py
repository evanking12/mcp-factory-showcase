"""api.pipeline.core.evidence_candidates — Tiered evidence candidate registry.

Progressive specialization engine: starts with generic placeholders (tier 0),
fills from static discovery (tier 1), runtime probe results (tier 2), prior
verified calls (tier 3), cross-DLL transfer (tier 4), and user hints (tier 5).

The pipeline wraps loosely around any DLL, then tightens as evidence
accumulates.  No domain-specific knowledge belongs in this module.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("mcp_factory.api")

TIER_GENERIC = 0
TIER_STATIC_DISCOVERY = 1
TIER_RUNTIME = 2
TIER_PRIOR_VERIFIED = 3
TIER_CROSS_DLL = 4
TIER_USER_HINT = 5

_ID_LIKE_RE = re.compile(r"[A-Z]{2,}(?:[-_][A-Z0-9]{2,})+", re.I)
_RESULT_RETURN_RE = re.compile(r"Returned:\s*(-?\d+)")
_KIND_PREFIX_MAP: dict[str, list[str]] = {
    "customer_id": ["CUST", "ACCT", "ACCOUNT", "CLIENT", "USR", "USER"],
    "order_id": ["ORD", "ORDER"],
    "transaction_id": ["TXN", "TRANS"],
    "reservation_id": ["RSV", "RESV", "RES"],
    "auth_token": ["SP-OPERATOR"],
    "preview_ticket": ["SP-PREVIEW"],
    "fee_quote_id": ["SP-FEE"],
    "stale_attestation_token": ["SP-ATT-STALE"],
    "attestation_packet": ["SP-ATT"],
    "hold_token": ["HOLD"],
    "commit_receipt": ["COMMIT"],
    "invoice_id": ["INV"],
    "quote_id": ["PRQ"],
    "report_id": ["RPT"],
    "ticket": ["CFG"],
    "sku": ["SKU", "WDG", "PRO", "ACC", "GDG", "SW-", "ITEM", "PROD"],
}

_DAG_INIT_RE = re.compile(r"(init(ializ)?|startup|start|setup|login|logon|connect)", re.I)
_PIPE_TICKET_RE = re.compile(r"^[A-Za-z0-9_-]+(?:\|[A-Za-z0-9_-]+=[^|]+){1,}$")
_OVERLAP_BASELINE_PREFIX = "overlap_baseline:"
_FAMILY_SENSITIVE_KINDS = {
    "handle",
    "nonce",
    "blob_token",
    "auth_token",
    "customer_id",
    "order_id",
    "transaction_id",
    "reservation_id",
    "preview_ticket",
    "fee_quote_id",
    "attestation_packet",
    "stale_attestation_token",
    "stale_reason",
    "hold_token",
    "commit_receipt",
    "invoice_id",
    "quote_id",
    "report_id",
    "ticket",
    "sku",
    "string_id",
}


def _is_pseudo_function_name(name: str) -> bool:
    stripped = str(name or "").strip()
    return not stripped or stripped.lower() == "entry" or stripped.startswith("FUN_")


def _function_family_prefix(name: str) -> str:
    return str(name or "").split("_", 1)[0].strip().lower()


def _source_function_name(source: str, discovered_at: str = "") -> str:
    source_text = str(source or "")
    if source_text.startswith(_OVERLAP_BASELINE_PREFIX):
        source_text = source_text.split(":", 1)[1]
    for prefix in ("runtime:", "working_call:"):
        if source_text.startswith(prefix):
            return source_text.split(":", 1)[1].strip()
    return str(discovered_at or "").strip()


def _is_overlap_baseline_source(source: str) -> bool:
    source_text = str(source or "")
    return source_text.startswith(_OVERLAP_BASELINE_PREFIX) or f":{_OVERLAP_BASELINE_PREFIX}" in source_text


def _identifier_family_from_value(value: Any, param_kind: str = "", source_function: str = "") -> str | None:
    if isinstance(value, str):
        raw = str(value or "").strip()
        if raw:
            upper = raw.upper()
            if upper.startswith("WFH-"):
                return "workflow_handle"
            if upper.startswith("SP-OPERATOR-"):
                return "auth_token"
            if upper.startswith("SP-PREVIEW-"):
                return "preview_ticket"
            if upper.startswith("SP-FEE-"):
                return "fee_quote_id"
            if upper.startswith("SP-ATT-"):
                return "attestation_packet"
            if _PIPE_TICKET_RE.match(raw):
                return "ticket"
            kind = classify_value_kind(raw)
            if kind != "string_id":
                return kind
    kind = str(param_kind or "").strip().lower()
    if isinstance(value, str) and str(value or "").strip() and kind == "commit_receipt":
        return None
    if kind in _FAMILY_SENSITIVE_KINDS and kind not in {"string_id", "handle"}:
        return kind
    if kind == "handle":
        fn_family = _function_family_prefix(source_function)
        if fn_family == "wf" and isinstance(value, str):
            return "workflow_handle"
        return "handle"
    return None


def _expected_identifier_family(
    param_name: str,
    description: str,
    json_type: str,
    fn_name: str,
    inferred_kinds: list[str],
    resolved_type: str = "",
) -> str | None:
    lowered = f"{param_name} {description}".lower()
    resolved_lower = str(resolved_type or "").lower()
    fn_family = _function_family_prefix(fn_name)
    if "trusted" in lowered and "branch" in lowered and any(
        marker in lowered for marker in ("id", "identifier", "code", "name")
    ):
        return "trusted_branch_id"
    if "rejected" in lowered and "branch" in lowered and any(
        marker in lowered for marker in ("id", "identifier", "code", "name")
    ):
        return "rejected_branch_id"
    if "nonce" in lowered:
        return "nonce"
    if "preview" in lowered and "ticket" in lowered:
        return "preview_ticket"
    if "fee" in lowered and "quote" in lowered:
        return "fee_quote_id"
    if "attestation" in lowered and "packet" in lowered:
        return "attestation_packet"
    if "sp-resv-" in lowered:
        return "reservation_id"
    if "sp-hold-" in lowered or ("hold" in lowered and "token" in lowered):
        return "hold_token"
    if "sp-commit-" in lowered or ("commit" in lowered and "receipt" in lowered):
        return "commit_receipt"
    if "token" in lowered or "auth" in lowered:
        return "auth_token"
    if "quote" in lowered and "id" in lowered:
        return "quote_id"
    if "report" in lowered and "id" in lowered:
        return "report_id"
    if "ticket" in lowered:
        return "ticket"
    if ("workflow" in lowered and "handle" in lowered) or (
        "handle" in lowered and fn_family == "wf" and str(json_type or "").lower() not in {"integer", "number"}
    ):
        return "workflow_handle"
    if (
        fn_family == "wf"
        and str(json_type or "").lower() not in {"integer", "number"}
        and any(tok in lowered for tok in ("lpszhandle", "workflow", "instance"))
        and any(tok in resolved_lower for tok in ("char", "wchar", "lpstr", "lpcstr", "lpwstr", "lpcwstr"))
    ):
        return "workflow_handle"
    for kind in inferred_kinds:
        if kind in {
            "customer_id",
            "order_id",
            "transaction_id",
            "reservation_id",
            "trusted_branch_id",
            "rejected_branch_id",
            "preview_ticket",
            "fee_quote_id",
            "attestation_packet",
            "hold_token",
            "commit_receipt",
            "invoice_id",
            "quote_id",
            "report_id",
            "ticket",
            "sku",
        }:
            return kind
        if kind == "handle":
            if fn_family == "wf" and str(json_type or "").lower() not in {"integer", "number"}:
                return "workflow_handle"
            return "handle"
    return None


def infer_identifier_family_from_value(value: Any, param_kind: str = "", source_function: str = "") -> str | None:
    """Public wrapper for family inference from a candidate value."""
    return _identifier_family_from_value(value, param_kind=param_kind, source_function=source_function)


def infer_expected_identifier_family(
    param_name: str,
    description: str,
    json_type: str,
    fn_name: str,
    inferred_kinds: list[str],
    resolved_type: str = "",
) -> str | None:
    """Public wrapper for expected family inference for a parameter slot."""
    return _expected_identifier_family(
        param_name,
        description,
        json_type,
        fn_name,
        inferred_kinds,
        resolved_type=resolved_type,
    )


def _has_handle_output_context(param_lookup: dict[str, dict] | None) -> bool:
    for meta in (param_lookup or {}).values():
        if not isinstance(meta, dict):
            continue
        context = f"{meta.get('name') or ''} {meta.get('description') or ''}"
        if _is_handle_context(context):
            return True
    return False


def classify_value_kind(value: str, id_formats: list[str] | None = None) -> str:
    """Classify an ID-like string value into a param_kind using prefix heuristics."""
    raw = str(value or "").strip()
    upper = raw.upper()
    if upper.startswith("WFH-"):
        return "handle"
    if upper.startswith("SP-OPERATOR-"):
        return "auth_token"
    if upper.startswith("SP-RESV-"):
        return "reservation_id"
    if upper.startswith("SP-HOLD-"):
        return "hold_token"
    if upper.startswith("SP-BRANCH-REPLAY-"):
        return "commit_receipt"
    if upper.startswith("SP-COMMIT-"):
        return "commit_receipt"
    if upper.startswith("SP-ATT-STALE-"):
        return "stale_attestation_token"
    if re.match(r"^FRESHNESS_GAP\|EPOCH=\d+\|PACKET=SP-ATT-[A-Z0-9-]+(?:-PACKET)?$", upper, re.I):
        return "stale_reason"
    if _PIPE_TICKET_RE.match(raw):
        return "ticket"
    for kind, prefixes in _KIND_PREFIX_MAP.items():
        if any(upper.startswith(p) for p in prefixes):
            return kind
    if id_formats:
        for fmt in id_formats:
            fmt_upper = str(fmt).upper()
            for kind, prefixes in _KIND_PREFIX_MAP.items():
                if any(p in fmt_upper for p in prefixes):
                    if _id_matches_format(value, fmt):
                        return kind
    return "string_id"


def _id_matches_format(value: str, fmt: str) -> bool:
    """Check if a value loosely matches an id_format pattern."""
    prefix = fmt.split("-")[0].upper() if "-" in fmt else fmt[:4].upper()
    return str(value).upper().startswith(prefix)


def _classify_param_kind_simple(param_name: str, json_type: str) -> str:
    """Lightweight param kind inference for Ghidra seeding (no description needed)."""
    name = param_name.lower()
    if re.search(r"nonce", name):
        return "nonce"
    if re.search(r"blob", name) and re.search(r"token", name):
        return "blob_token"
    if re.search(r"token|auth", name):
        return "auth_token"
    if re.search(r"handle|session", name):
        return "handle"
    if re.search(r"order", name):
        return "order_id"
    if re.search(r"customer|account", name):
        return "customer_id"
    if re.search(r"transaction|txn", name):
        return "transaction_id"
    if re.search(r"quote", name):
        return "quote_id"
    if re.search(r"preview", name) and re.search(r"ticket", name):
        return "preview_ticket"
    if re.search(r"fee", name) and re.search(r"quote", name):
        return "fee_quote_id"
    if re.search(r"attestation", name) and re.search(r"packet", name):
        return "attestation_packet"
    if re.search(r"stale", name) and re.search(r"attestation", name) and re.search(r"token", name):
        return "stale_attestation_token"
    if re.search(r"stale", name) and re.search(r"reason", name):
        return "stale_reason"
    if re.search(r"report", name):
        return "report_id"
    if re.search(r"ticket", name):
        return "ticket"
    if re.search(r"reserv|resv", name):
        return "reservation_id"
    if re.search(r"sku|product|item", name):
        return "sku"
    if re.search(r"amount|cents|payment", name):
        return "amount"
    if re.search(r"points", name):
        return "points"
    if re.search(r"size|count|length|len|buf", name):
        return "buffer_size"
    if re.search(r"mode|flag|enable", name):
        return "flag"
    jtype = json_type.lower()
    if jtype in {"integer", "number"}:
        return "integer"
    if jtype == "boolean":
        return "boolean"
    return "string_id" if jtype == "string" else "unknown"


def _is_handle_context(text: str) -> bool:
    return bool(re.search(r"handle|session|window", text))


def _is_nonce_context(text: str) -> bool:
    return bool(re.search(r"nonce", text))


def _is_token_context(text: str) -> bool:
    return bool(re.search(r"token|auth", text))


def _is_blob_token_context(text: str) -> bool:
    return bool(re.search(r"blob", text) and re.search(r"token", text))


def _is_version_context(text: str) -> bool:
    return bool(re.search(r"version|count|size|length|mode|flag", text))


def _should_capture_return_as_handle(function_name: str, result_value: int, result_str: str) -> bool:
    fn_text = str(function_name or "").lower()
    result_text = str(result_str or "").lower()
    if result_value <= 1:
        return False
    if _is_version_context(fn_text) or _is_version_context(result_text):
        return False
    if re.search(r"close|free|release|count|getstructversion|getmode", fn_text):
        return False
    return bool(re.search(r"open|create|alloc|session|window|handle", fn_text))


def _parse_result_outputs(result_str: str) -> tuple[int | None, dict[str, Any]]:
    result_value: int | None = None
    outputs: dict[str, Any] = {}

    if not result_str:
        return result_value, outputs

    ret_match = _RESULT_RETURN_RE.search(result_str)
    if ret_match:
        try:
            result_value = int(ret_match.group(1))
        except (TypeError, ValueError):
            result_value = None

    for raw_line in str(result_str or "").splitlines()[1:]:
        line = str(raw_line or "").strip()
        if "=" not in line:
            continue
        key, raw = line.split("=", 1)
        key = key.strip()
        raw = raw.strip()
        if not key or not raw:
            continue
        try:
            outputs[key] = int(raw)
            continue
        except (TypeError, ValueError):
            pass
        try:
            outputs[key] = raw.strip("'\"")
        except Exception:
            outputs[key] = raw

    return result_value, outputs


def _classify_enum_member(enum_name: str, member_name: str) -> str:
    """Infer a param_kind from an enum name/member for ECR seeding."""
    combined = f"{enum_name} {member_name}".lower()
    if re.search(r"status|state|mode|flag", combined):
        return "flag"
    if re.search(r"error|result|code|ret", combined):
        return "error_code"
    if re.search(r"type|kind|category", combined):
        return "type_hint"
    return "integer"


@dataclass
class CandidateEntry:
    """A single candidate value with provenance metadata."""
    value: Any
    tier: int
    source: str
    param_kind: str
    confidence: float = 1.0
    discovered_at: str = ""
    source_dll: str = ""
    source_job: str = ""
    campaign_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> CandidateEntry:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class EvidenceCandidateRegistry:
    """Mutable, tiered store of candidate argument values.

    Thread-safe: all mutations acquire ``_lock``.
    """

    def __init__(self) -> None:
        self._candidates: dict[str, list[CandidateEntry]] = {}
        self._init_satisfied: set[str] = set()
        self._lock = threading.Lock()

    def seed_tier0(self) -> None:
        """Populate generic placeholders that work for any DLL."""
        generics = [
            ("integer", 1, 1.0), ("integer", 0, 0.9), ("integer", 2, 0.8),
            ("buffer_size", 64, 1.0), ("buffer_size", 128, 0.85), ("buffer_size", 256, 0.75),
            ("amount", 1000, 1.0), ("amount", 2500, 0.9), ("amount", 100, 0.8),
            ("points", 100, 1.0), ("points", 250, 0.85), ("points", 10, 0.75),
            ("flag", 1, 1.0), ("flag", 0, 0.9),
            ("boolean", True, 1.0), ("boolean", False, 0.9),
            ("generic_string", "TEST", 0.7), ("generic_string", "A", 0.55),
        ]
        with self._lock:
            for kind, val, conf in generics:
                self._add_locked(val, TIER_GENERIC, "generic", kind, conf, "seed_tier0")

    def seed_tier1(self, vocab: dict, static_analysis: dict | None = None) -> None:
        """Populate from static discovery: id_formats, binary_strings, Ghidra constants."""
        id_formats = [str(x) for x in (vocab.get("id_formats") or []) if x]
        binary_ids = [str(x) for x in (vocab.get("binary_string_ids") or []) if x]

        with self._lock:
            for fmt in id_formats:
                fmt_str = str(fmt).strip()
                if not fmt_str:
                    continue
                is_literal = (
                    "-" in fmt_str
                    and not any(ch in fmt_str.upper() for ch in ("NNN", "YYYY", "AAAA", "*"))
                )
                if is_literal:
                    kind = classify_value_kind(fmt_str, id_formats)
                    self._add_locked(fmt_str, TIER_STATIC_DISCOVERY, "vocab.id_formats",
                                     kind, 0.9, "seed_tier1")

            for bid in binary_ids:
                if not bid or not _ID_LIKE_RE.search(bid):
                    continue
                kind = classify_value_kind(bid, id_formats)
                self._add_locked(bid, TIER_STATIC_DISCOVERY, "static_analysis.binary_strings",
                                 kind, 0.8, "seed_tier1")

            error_codes = vocab.get("error_codes")
            if isinstance(error_codes, dict):
                for code_hex, meaning in error_codes.items():
                    self._add_locked(
                        {"code": code_hex, "meaning": meaning},
                        TIER_STATIC_DISCOVERY, "vocab.error_codes",
                        "error_code", 0.7, "seed_tier1",
                    )

    def seed_tier1_ghidra(
        self,
        invocables: list[dict],
        ghidra_data_types: list[dict] | None = None,
    ) -> int:
        """Populate tier 1 from Ghidra provenance-tagged invocables and data types.

        Ingests param types, enum values, decompiler-recovered constants, and
        structures — all weighted by their provenance trust level rather than
        treated uniformly.  Returns count of candidates added.
        """
        count = 0
        if isinstance(ghidra_data_types, dict):
            ghidra_items = list(ghidra_data_types.values())
        else:
            ghidra_items = list(ghidra_data_types or [])
        with self._lock:
            for inv in invocables:
                fn_prov = inv.get("_ghidra_provenance")
                if fn_prov is None:
                    continue
                params_prov = fn_prov.get("params") or {}
                for p in (inv.get("parameters") or []):
                    pname = p.get("name", "")
                    pprov = params_prov.get(pname) or p.get("_ghidra_provenance")
                    if pprov is None:
                        continue

                    type_prov = pprov.get("param_type", {})
                    type_conf = type_prov.get("confidence", 0.5)
                    type_trust = type_prov.get("trust_level", "low")
                    ptype_val = type_prov.get("value", p.get("type", ""))

                    dir_prov = pprov.get("direction", {})
                    dir_val = dir_prov.get("value", p.get("direction", "in"))

                    if dir_val == "out":
                        continue

                    # Decompiler param-type records are useful role/context facts,
                    # but they are not candidate argument values. Keep them in the
                    # discovery/invocable artifacts, not in the value registry.
                    continue

            if ghidra_items:
                for dt in ghidra_items:
                    if not isinstance(dt, dict):
                        continue
                    dt_name = dt.get("name", "")
                    dt_kind = dt.get("kind", "")

                    if dt_kind == "enum":
                        members = dt.get("members") or []
                        if isinstance(members, dict):
                            member_items = [
                                {"name": str(name), "value": value}
                                for name, value in members.items()
                            ]
                        else:
                            member_items = [m for m in members if isinstance(m, dict)]
                        for member in member_items:
                            mname = member.get("name", "")
                            mval = member.get("value")
                            if mval is None:
                                continue
                            inferred_kind = _classify_enum_member(dt_name, mname)
                            self._add_locked(
                                mval, TIER_STATIC_DISCOVERY, "ghidra.enum",
                                inferred_kind, 0.65, f"seed_tier1_ghidra:{dt_name}",
                            )
                            count += 1

                    elif dt_kind in {"struct", "typedef"}:
                        # Struct fields and typedefs are still useful static context,
                        # but they are weak candidate-value seeds. Persist them in the
                        # discovery artifacts, not in the value-ranking registry.
                        continue

        logger.info("seed_tier1_ghidra: added %d candidates from provenance-tagged invocables", count)
        return count

    def add(
        self,
        value: Any,
        tier: int,
        source: str,
        param_kind: str,
        confidence: float = 1.0,
        discovered_at: str = "",
        *,
        source_dll: str = "",
        source_job: str = "",
        campaign_id: str = "",
    ) -> None:
        """Thread-safe addition of a candidate."""
        with self._lock:
            self._add_locked(
                value,
                tier,
                source,
                param_kind,
                confidence,
                discovered_at,
                source_dll=source_dll,
                source_job=source_job,
                campaign_id=campaign_id,
            )

    def _add_locked(
        self,
        value: Any,
        tier: int,
        source: str,
        param_kind: str,
        confidence: float,
        discovered_at: str,
        *,
        source_dll: str = "",
        source_job: str = "",
        campaign_id: str = "",
    ) -> None:
        entry = CandidateEntry(
            value=value, tier=tier, source=source,
            param_kind=param_kind, confidence=confidence,
            discovered_at=discovered_at,
            source_dll=source_dll,
            source_job=source_job,
            campaign_id=campaign_id,
        )
        bucket = self._candidates.setdefault(param_kind, [])
        for existing in bucket:
            if existing.value == value and existing.tier == tier:
                if confidence > existing.confidence:
                    existing.confidence = confidence
                    existing.source = source
                    existing.source_dll = source_dll or existing.source_dll
                    existing.source_job = source_job or existing.source_job
                    existing.campaign_id = campaign_id or existing.campaign_id
                return
        bucket.append(entry)

    def query(
        self,
        param_kind: str,
        json_type: str = "",
        max_results: int = 5,
        min_tier: int = 0,
        prefer_latest: bool = False,
    ) -> list[CandidateEntry]:
        """Return top candidates for a param_kind, ranked by tier (descending) then confidence."""
        with self._lock:
            bucket = list(self._candidates.get(param_kind, []))
        filtered = [c for c in bucket if c.tier >= min_tier]
        if prefer_latest:
            ranked = list(enumerate(filtered))
            ranked.sort(key=lambda item: (item[1].tier, item[1].confidence, item[0]), reverse=True)
            return [item[1] for item in ranked[:max_results]]
        filtered.sort(key=lambda c: (c.tier, c.confidence), reverse=True)
        return filtered[:max_results]

    def query_all_string_ids(self, max_results: int = 10) -> list[CandidateEntry]:
        """Return all ID-like string candidates across all kinds."""
        id_kinds = {"customer_id", "order_id", "transaction_id", "reservation_id",
                    "invoice_id", "quote_id", "report_id", "ticket", "sku", "string_id"}
        results = []
        with self._lock:
            for kind in id_kinds:
                results.extend(self._candidates.get(kind, []))
        results.sort(key=lambda c: (c.tier, c.confidence), reverse=True)
        return results[:max_results]

    def available_id_kinds(self) -> set[str]:
        """Return all ID-like kinds currently present in the registry."""
        id_kinds = {
            "customer_id",
            "order_id",
            "transaction_id",
            "reservation_id",
            "invoice_id",
            "quote_id",
            "report_id",
            "ticket",
            "sku",
            "string_id",
        }
        with self._lock:
            return {
                kind for kind in id_kinds
                if self._candidates.get(kind)
            }

    def materialize_live_hints(
        self,
        function_name: str,
        hints: dict[str, Any] | None,
    ) -> int:
        """Promote live same-run lineage hints into reusable runtime evidence."""
        count = 0
        source = f"runtime:{function_name}"
        for kind, value in dict(hints or {}).items():
            param_kind = "handle" if kind == "workflow_handle" else str(kind or "").strip()
            if param_kind not in (_FAMILY_SENSITIVE_KINDS | {"nonce", "handle", "blob_token", "auth_token"}):
                continue
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                if value <= 0:
                    continue
            elif isinstance(value, str):
                if not value.strip():
                    continue
            else:
                continue
            self.add(value, TIER_RUNTIME, source, param_kind, 1.0, function_name)
            count += 1
        return count

    def mark_init_satisfied(self, function_name: str) -> None:
        """Record that an init function was successfully called."""
        with self._lock:
            self._init_satisfied.add(function_name)

    def is_init_satisfied(self) -> bool:
        with self._lock:
            return len(self._init_satisfied) > 0

    def harvest_from_result(
        self,
        function_name: str,
        result_str: str,
        trace: dict | None = None,
        working_args: dict | None = None,
        id_formats: list[str] | None = None,
        param_lookup: dict[str, dict] | None = None,
    ) -> int:
        """Extract candidate values from a successful probe result.

        Parses output buffers, returned IDs/handles, and working_call args.
        Returns count of new candidates added.
        """
        count = 0
        source = f"runtime:{function_name}"
        result_value, parsed_outputs = _parse_result_outputs(result_str or "")
        has_handle_output_context = _has_handle_output_context(param_lookup)

        for match in _ID_LIKE_RE.finditer(result_str or ""):
            val = match.group(0)
            kind = classify_value_kind(val, id_formats)
            self.add(val, TIER_RUNTIME, source, kind, 0.95, function_name)
            count += 1
            if has_handle_output_context:
                self.add(val, TIER_RUNTIME, source, "handle", 0.96, function_name)
                count += 1

        if trace and isinstance(trace, dict):
            for buf_name in (trace.get("out_str_bufs") or []):
                buf_match = re.search(
                    rf"{re.escape(buf_name)}='([^']*)'",
                    result_str or "",
                )
                if buf_match:
                    buf_val = buf_match.group(1)
                    for sub_match in _ID_LIKE_RE.finditer(buf_val):
                        val = sub_match.group(0)
                        kind = classify_value_kind(val, id_formats)
                        self.add(val, TIER_RUNTIME, source, kind, 0.95, function_name)
                        count += 1
                    if "|" in buf_val:
                        for field_val in buf_val.split("|"):
                            field_val = field_val.strip()
                            if _ID_LIKE_RE.search(field_val):
                                kind = classify_value_kind(field_val, id_formats)
                                self.add(field_val, TIER_RUNTIME, source, kind, 0.9,
                                         function_name)
                                count += 1

        for out_name, out_val in parsed_outputs.items():
            meta = (param_lookup or {}).get(out_name) or {}
            pname = str(meta.get("name") or out_name or "").lower()
            pdesc = str(meta.get("description") or "").lower()
            context = f"{pname} {pdesc}"
            if isinstance(out_val, int):
                if out_val <= 0:
                    continue
                if _is_nonce_context(context):
                    self.add(out_val, TIER_RUNTIME, source, "nonce", 1.0, function_name)
                    count += 1
                    continue
                if _is_blob_token_context(context):
                    self.add(out_val, TIER_RUNTIME, source, "blob_token", 1.0, function_name)
                    count += 1
                    continue
                if _is_token_context(context):
                    self.add(out_val, TIER_RUNTIME, source, "handle", 0.98, function_name)
                    count += 1
                    continue
                if _is_handle_context(context):
                    self.add(out_val, TIER_RUNTIME, source, "handle", 1.0, function_name)
                    count += 1
                    continue
            if isinstance(out_val, str):
                if _is_handle_context(context):
                    self.add(out_val, TIER_RUNTIME, source, "handle", 1.0, function_name)
                    count += 1
                    continue
                if _is_token_context(context) and re.fullmatch(r"[A-Fa-f0-9]{6,32}", out_val or ""):
                    self.add(out_val.upper(), TIER_RUNTIME, source, "auth_token", 1.0, function_name)
                    count += 1
                    continue
                kind = classify_value_kind(out_val, id_formats)
                if kind != "string_id" or _ID_LIKE_RE.search(out_val):
                    self.add(out_val, TIER_RUNTIME, source, kind, 0.95, function_name)
                    count += 1

        if result_value is not None and _should_capture_return_as_handle(function_name, result_value, result_str or ""):
            self.add(result_value, TIER_RUNTIME, source, "handle", 0.92, function_name)
            count += 1

        if working_args and isinstance(working_args, dict):
            for arg_name, arg_val in working_args.items():
                meta = (param_lookup or {}).get(arg_name) or {}
                pname = str(meta.get("name") or arg_name or "").lower()
                pdesc = str(meta.get("description") or "").lower()
                context = f"{pname} {pdesc}"
                if isinstance(arg_val, int) and arg_val > 0 and _is_nonce_context(context):
                    self.add(arg_val, TIER_RUNTIME, f"working_call:{function_name}",
                             "nonce", 1.0, function_name)
                    count += 1
                    continue
                if isinstance(arg_val, int) and arg_val > 0 and _is_blob_token_context(context):
                    self.add(arg_val, TIER_RUNTIME, f"working_call:{function_name}",
                             "blob_token", 1.0, function_name)
                    count += 1
                    continue
                if isinstance(arg_val, int) and arg_val > 0 and _is_handle_context(context):
                    self.add(arg_val, TIER_RUNTIME, f"working_call:{function_name}",
                             "handle", 1.0, function_name)
                    count += 1
                    continue
                if isinstance(arg_val, int) and arg_val > 0 and _is_token_context(context):
                    self.add(arg_val, TIER_RUNTIME, f"working_call:{function_name}",
                             "handle", 0.98, function_name)
                    count += 1
                    continue
                if isinstance(arg_val, str) and arg_val.strip() and _is_handle_context(context):
                    self.add(arg_val, TIER_RUNTIME, f"working_call:{function_name}",
                             "handle", 1.0, function_name)
                    count += 1
                    continue
                if (
                    isinstance(arg_val, str)
                    and arg_val.strip()
                    and _is_token_context(context)
                    and re.fullmatch(r"[A-Fa-f0-9]{6,32}", arg_val or "")
                ):
                    self.add(arg_val.upper(), TIER_RUNTIME, f"working_call:{function_name}",
                             "auth_token", 1.0, function_name)
                    count += 1
                    continue
                if isinstance(arg_val, str) and arg_val.strip():
                    kind = classify_value_kind(arg_val, id_formats)
                    if kind == "string_id" and not _ID_LIKE_RE.search(arg_val):
                        continue
                    self.add(arg_val, TIER_RUNTIME, f"working_call:{function_name}",
                             kind, 1.0, function_name)
                    count += 1

        return count

    def get_best_for_param(
        self,
        param_name: str,
        json_type: str,
        description: str,
        fn_name: str = "",
        resolved_type: str = "",
        attempt: int = 0,
        string_slot_index: int = 0,
        string_slot_count: int = 0,
        has_output_buffer: bool = False,
        is_buffer_size_context: bool = False,
    ) -> list[dict]:
        """Return ranked candidates suitable for a specific parameter.

        This is the main interface for _ranked_param_candidates() integration.
        Returns dicts with {value, score, source, reason} matching the existing
        candidate format in helpers.py.
        """
        name_lower = (param_name or "").lower()
        desc_lower = (description or "").lower()
        fn_lower = (fn_name or "").lower()
        jtype = (json_type or "").lower()

        inferred_kinds = self._infer_param_kinds(
            name_lower,
            desc_lower,
            fn_lower,
            jtype,
            string_slot_index=string_slot_index,
            string_slot_count=string_slot_count,
            has_output_buffer=has_output_buffer,
            is_buffer_size_context=is_buffer_size_context,
        )

        results: list[dict] = []
        seen_values: set[str] = set()
        target_family = _function_family_prefix(fn_lower)
        expected_identifier_family = _expected_identifier_family(
            param_name,
            description,
            json_type,
            fn_name,
            inferred_kinds,
            resolved_type=resolved_type,
        )

        for kind_index, kind in enumerate(inferred_kinds):
            prefer_latest = kind in {"handle", "nonce", "blob_token"}
            query_limit = 12 if kind in _FAMILY_SENSITIVE_KINDS else 8
            for entry in self.query(kind, jtype, max_results=query_limit, prefer_latest=prefer_latest):
                if isinstance(entry.value, (dict, list, tuple, set)):
                    continue
                if jtype in {"integer", "number"} and (
                    not isinstance(entry.value, (int, float)) or isinstance(entry.value, bool)
                ):
                    continue
                val_key = repr(entry.value)
                if val_key in seen_values:
                    continue
                seen_values.add(val_key)
                tier_bonus = entry.tier * 0.1
                score = min(1.0, entry.confidence + tier_bonus)
                ranking_score = score
                source_fn = _source_function_name(entry.source, entry.discovered_at)
                source_family = _function_family_prefix(source_fn)
                is_overlap_baseline = _is_overlap_baseline_source(entry.source)
                candidate_family = _identifier_family_from_value(entry.value, entry.param_kind, source_fn)
                source_text = str(entry.source or "")
                is_static_seed = source_text.startswith(("static_analysis.", "vocab.id_formats"))
                if (
                    expected_identifier_family
                    and kind in _FAMILY_SENSITIVE_KINDS
                    and is_overlap_baseline
                    and candidate_family not in {expected_identifier_family}
                ):
                    continue
                if (
                    expected_identifier_family
                    and kind in _FAMILY_SENSITIVE_KINDS
                    and is_static_seed
                    and candidate_family not in {expected_identifier_family}
                ):
                    continue
                selection_flags: list[str] = []
                if kind in {"handle", "blob_token", "nonce", "auth_token"}:
                    if (
                        target_family
                        and source_family
                        and source_family == target_family
                        and entry.source.startswith(("runtime:", "working_call:"))
                    ):
                        ranking_score += 0.45
                        selection_flags.append("same_family_runtime")
                    elif (
                        target_family
                        and source_family
                        and source_family == target_family
                        and entry.tier >= TIER_PRIOR_VERIFIED
                    ):
                        ranking_score += 0.2
                        selection_flags.append("same_family_verified")
                elif (
                    kind in _FAMILY_SENSITIVE_KINDS
                    and target_family
                    and source_family
                    and source_family == target_family
                    and is_overlap_baseline
                ):
                    ranking_score += 0.28
                    selection_flags.append("same_family_overlap_baseline")
                if (
                    kind in _FAMILY_SENSITIVE_KINDS
                    and is_overlap_baseline
                    and target_family
                    and source_family
                    and source_family == target_family
                ):
                    ranking_score += 0.14
                    selection_flags.append("overlap_baseline")
                if (
                    kind in _FAMILY_SENSITIVE_KINDS
                    and target_family
                    and source_family
                    and source_family != target_family
                    and entry.tier >= TIER_CROSS_DLL
                ):
                    ranking_score -= 0.22
                    selection_flags.append("foreign_function_family")
                if expected_identifier_family and candidate_family:
                    if candidate_family == expected_identifier_family:
                        ranking_score += 0.4
                        selection_flags.append("same_identifier_family")
                        if entry.source.startswith(("runtime:", "working_call:")):
                            ranking_score += 0.15
                            selection_flags.append("same_identifier_runtime")
                    else:
                        ranking_score -= 0.8
                        selection_flags.append("foreign_identifier_family")
                elif expected_identifier_family and candidate_family is None and kind in _FAMILY_SENSITIVE_KINDS:
                    ranking_score -= 0.15
                    selection_flags.append("unknown_identifier_family")
                if jtype in {"integer", "number"} and isinstance(entry.value, (int, float)) and not isinstance(entry.value, bool):
                    ranking_score += 0.18
                elif jtype not in {"integer", "number", "boolean"} and isinstance(entry.value, str):
                    ranking_score += 0.18
                results.append({
                    "value": entry.value,
                    "score": score,
                    "ranking_score": ranking_score,
                    "kind_priority": len(inferred_kinds) - kind_index,
                    "source": f"evidence.tier{entry.tier}.{entry.source}",
                    "reason": f"evidence candidate ({entry.param_kind}, tier {entry.tier})",
                    "candidate_family": candidate_family,
                    "expected_family": expected_identifier_family,
                    "source_family": source_family,
                    "is_overlap_baseline": is_overlap_baseline,
                    "selection_flags": selection_flags,
                    "guard_applied": False,
                })

        if expected_identifier_family and results:
            same_family_current = [
                item for item in results
                if item.get("candidate_family") == expected_identifier_family
                and not item.get("is_overlap_baseline")
            ]
            same_family_baselines = [
                item for item in results
                if item.get("candidate_family") == expected_identifier_family
                and item.get("is_overlap_baseline")
            ]
            top_candidate = max(results, key=lambda item: (item["kind_priority"], item["ranking_score"], item["score"]))
            strongest_current = max(
                same_family_current,
                key=lambda item: (item["kind_priority"], item["ranking_score"], item["score"]),
                default=None,
            )
            strongest_baseline = max(
                same_family_baselines,
                key=lambda item: (item["kind_priority"], item["ranking_score"], item["score"]),
                default=None,
            )
            if (
                strongest_baseline is not None
                and top_candidate.get("candidate_family") not in {expected_identifier_family, None}
                and top_candidate is not strongest_baseline
                and (
                    strongest_current is None
                    or strongest_current["ranking_score"] <= strongest_baseline["ranking_score"] + 0.12
                )
            ):
                strongest_baseline["ranking_score"] = max(
                    strongest_baseline["ranking_score"],
                    top_candidate["ranking_score"] + 0.01,
                )
                strongest_baseline["guard_applied"] = True
                strongest_baseline["selection_flags"] = list(strongest_baseline.get("selection_flags") or []) + [
                    "overlap_guard_preserved"
                ]
                strongest_baseline["reason"] = (
                    f"{strongest_baseline['reason']}; preserved trusted overlap-baseline path against foreign-family candidate"
                )

        results.sort(key=lambda x: (x["kind_priority"], x["ranking_score"], x["score"]), reverse=True)
        return [{k: v for k, v in item.items() if k not in {"kind_priority", "ranking_score"}} for item in results[:5]]

    def _infer_param_kinds(
        self,
        name: str,
        desc: str,
        fn: str,
        jtype: str,
        *,
        string_slot_index: int = 0,
        string_slot_count: int = 0,
        has_output_buffer: bool = False,
        is_buffer_size_context: bool = False,
    ) -> list[str]:
        """Map parameter metadata to candidate param_kinds to query."""
        kinds: list[str] = []

        def _append(kind: str) -> None:
            if kind and kind not in kinds:
                kinds.append(kind)

        if re.search(r"order", name) or re.search(r"order", desc):
            _append("order_id")
        if re.search(r"customer|account", name) or re.search(r"customer|account", desc):
            _append("customer_id")
        if re.search(r"transaction|txn", name) or re.search(r"transaction|txn", desc):
            _append("transaction_id")
        if re.search(r"reserv|resv", name) or re.search(r"reserv|resv", desc):
            _append("reservation_id")
        if re.search(r"quote", name) or re.search(r"quote", desc):
            _append("quote_id")
            if jtype not in {"integer", "number", "boolean"}:
                _append("string_id")
        if re.search(r"report", name) or re.search(r"report", desc):
            _append("report_id")
            if jtype not in {"integer", "number", "boolean"}:
                _append("string_id")
        if re.search(r"ticket", name) or re.search(r"ticket", desc):
            _append("ticket")
            if jtype not in {"integer", "number", "boolean"}:
                _append("string_id")
        if re.search(r"nonce", name) or re.search(r"nonce", desc):
            _append("nonce")
        if re.search(r"attestation", name) and re.search(r"packet", name):
            _append("attestation_packet")
            if jtype not in {"integer", "number", "boolean"}:
                _append("string_id")
        if re.search(r"blob", name) or re.search(r"blob", desc):
            _append("blob_token")
        if re.search(r"token|auth", name) or re.search(r"token|auth", desc):
            if jtype in {"integer", "number"}:
                _append("handle")
            _append("auth_token")
        if re.search(r"handle|session", name) or re.search(r"handle|session", desc):
            _append("handle")
        if re.search(r"sku|product|item", name) or re.search(r"sku|product|item", desc):
            _append("sku")

        if re.search(r"amount|cents|refund|payment|debit|credit", name):
            _append("amount")
        if re.search(r"points", name) or re.search(r"points", desc):
            _append("points")
        if re.search(r"size|count|length|len|buf", name):
            _append("buffer_size")
        if re.search(r"mode|flag|enable", name):
            _append("flag")

        if not kinds and jtype not in {"integer", "number", "boolean"}:
            if re.search(r"workflow", fn):
                _append("handle")
                _append("string_id")
            if re.search(r"quote", fn):
                _append("quote_id")
                _append("string_id")
            if re.search(r"report", fn):
                _append("report_id")
                _append("string_id")
            if re.search(r"history|list", fn) and has_output_buffer:
                if re.search(r"transaction|order|reservation", fn):
                    _append("customer_id")
                    _append("account_id")
            if re.search(r"void", fn) and re.search(r"transaction|txn", fn):
                _append("transaction_id")
            if re.search(r"cancel", fn) and re.search(r"reserv|resv", fn):
                _append("reservation_id")
            if re.search(r"transaction|txn", fn):
                _append("transaction_id")
            if re.search(r"reserv|resv", fn):
                _append("reservation_id")
            if re.search(r"order", fn):
                _append("order_id")
            if re.search(r"customer|account|loyalty|balance|refund|payment", fn):
                _append("customer_id")
            if re.search(r"purchase|reserve", fn):
                if string_slot_count > 1 and string_slot_index > 0:
                    _append("sku")
                    _append("customer_id")
                else:
                    _append("customer_id")
                    _append("sku")
            if re.search(r"stock|inventory|product|lookup|check|search", fn):
                _append("sku")
            _append("string_id")

        if not kinds:
            if jtype in {"integer", "number"}:
                if is_buffer_size_context:
                    _append("buffer_size")
                _append("integer")
            elif jtype == "boolean":
                _append("boolean")
            else:
                _append("generic_string")

        return kinds

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "candidates": {
                    kind: [e.to_dict() for e in entries]
                    for kind, entries in self._candidates.items()
                },
                "init_satisfied": sorted(self._init_satisfied),
            }

    @classmethod
    def from_dict(cls, data: dict) -> EvidenceCandidateRegistry:
        reg = cls()
        for kind, entries in (data.get("candidates") or {}).items():
            for ed in entries:
                try:
                    reg._candidates.setdefault(kind, []).append(
                        CandidateEntry.from_dict(ed)
                    )
                except Exception:
                    pass
        for fn in (data.get("init_satisfied") or []):
            reg._init_satisfied.add(str(fn))
        return reg

    def promote_to_tier(self, from_tier: int, to_tier: int, source_suffix: str = "") -> int:
        """Promote all entries from one tier to another (e.g., tier 2 -> tier 3 for cross-run)."""
        count = 0
        with self._lock:
            for entries in self._candidates.values():
                for entry in entries:
                    if entry.tier == from_tier:
                        entry.tier = to_tier
                        if source_suffix:
                            entry.source = f"{entry.source}:{source_suffix}"
                        count += 1
        return count

    def merge_from(
        self,
        other: EvidenceCandidateRegistry,
        tier_override: int | None = None,
        *,
        min_tier: int | None = None,
        source_prefix: str = "",
        source_suffix: str = "",
        source_dll: str = "",
        source_job: str = "",
        campaign_id: str = "",
    ) -> int:
        """Merge candidates from another registry, optionally overriding their tier.

        ``min_tier`` is useful when carrying evidence across runs or DLLs: keep
        generic/static seeds in the source registry, but do not let them
        masquerade as stronger carry-forward evidence in the destination.
        """
        count = 0
        other_data = other.to_dict()
        with self._lock:
            for kind, entries in (other_data.get("candidates") or {}).items():
                for ed in entries:
                    try:
                        entry = CandidateEntry.from_dict(ed)
                        if min_tier is not None and entry.tier < min_tier:
                            continue
                        if tier_override is not None:
                            entry.tier = tier_override
                        if source_prefix:
                            entry.source = f"{source_prefix}{entry.source}"
                        if source_suffix:
                            entry.source = f"{entry.source}:{source_suffix}"
                        entry.source_dll = source_dll or entry.source_dll
                        entry.source_job = source_job or entry.source_job
                        entry.campaign_id = campaign_id or entry.campaign_id
                        self._add_locked(
                            entry.value, entry.tier, entry.source,
                            entry.param_kind, entry.confidence, entry.discovered_at,
                            source_dll=entry.source_dll,
                            source_job=entry.source_job,
                            campaign_id=entry.campaign_id,
                        )
                        count += 1
                    except Exception:
                        pass
        return count

    def stats(self) -> dict[str, Any]:
        """Summary statistics for logging/diagnostics."""
        with self._lock:
            total = sum(len(v) for v in self._candidates.values())
            by_tier: dict[int, int] = {}
            by_kind: dict[str, int] = {}
            for kind, entries in self._candidates.items():
                by_kind[kind] = len(entries)
                for e in entries:
                    by_tier[e.tier] = by_tier.get(e.tier, 0) + 1
            return {
                "total_candidates": total,
                "by_tier": by_tier,
                "by_kind": by_kind,
                "init_satisfied": sorted(self._init_satisfied),
            }


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 3: Prerequisite Chain Detector
# ═══════════════════════════════════════════════════════════════════════════════

_INIT_RE = re.compile(r"(init(ializ)?|startup|start|setup|open|login|logon|connect)", re.I)
_VERSION_RE = re.compile(r"get(version|version_?string|build|revision|release)", re.I)
_READ_RE = re.compile(r"get|lookup|status|history|diagnostic|version|list|check|search|query", re.I)
_WRITE_RE = re.compile(
    r"(pay|refund|redeem|unlock|process|write|commit|transfer|debit|credit|update|set|create|void|cancel|reserve)",
    re.I,
)

_OUTPUT_BASE_TYPES = frozenset({"undefined", "undefined2", "undefined4", "undefined8",
                                "int", "uint", "dword", "long", "ulong"})


@dataclass
class FunctionRole:
    """Classification of a function's role in the prerequisite chain."""
    name: str
    role: str  # "init", "version", "producer", "consumer", "transformer", "unknown"
    input_kinds: list[str] = field(default_factory=list)
    output_kinds: list[str] = field(default_factory=list)
    has_output_buffer: bool = False
    param_count: int = 0
    input_param_count: int = 0
    sequence_role: str = "unknown"
    prerequisites: list[str] = field(default_factory=list)
    sequence_confidence: float = 0.0
    sequence_reasons: list[str] = field(default_factory=list)


@dataclass
class PrerequisiteEdge:
    """A directed edge in the prerequisite DAG."""
    producer: str
    consumer: str
    shared_kind: str
    confidence: float = 0.5


_EXPLICIT_PRECONDITION_RE = re.compile(r"Required preconditions:\s*([^\n]+)", re.I)
_STATE_CONSUMER_RE = re.compile(r"(get|read|render|export|state|nonce|status|echo|diagnostic)", re.I)
_LIFECYCLE_RE = re.compile(r"(bind|begin|open|approve|prepare|confirm|commit|close|cancel|submit|reserve|create)", re.I)
_APPROVAL_HINT_RE = re.compile(r"(approved|approval required|confirm(ed)?|nonce mismatch|badnonce|license nonce)", re.I)
_CUSTOMER_GATE_HINT_RE = re.compile(r"(customer binding required|bindcustomer|g_(?:b)?customer_bound|bound customer)", re.I)
_OPEN_GATE_HINT_RE = re.compile(r"(workflow open|required open|g_(?:b)?workflow_open|g_(?:b)?session_open)", re.I)
_RESERVATION_GATE_HINT_RE = re.compile(r"(reservation created|required reservation|g_(?:b)?reservation_created)", re.I)
_LICENSE_GATE_HINT_RE = re.compile(r"(licensed mode required|not licensed|setupenvironment|config artifact missing|not initialized|g_bapproved|approval required)", re.I)


def _is_output_param(p: dict) -> bool:
    """Check if a parameter is a genuine output buffer (not a string input)."""
    direction = str(p.get("direction") or "in").lower()
    if direction != "out":
        return False
    ptype = str(p.get("type") or "").lower()
    if "*" not in ptype:
        return True
    base = ptype.replace("const ", "").strip().rstrip(" *")
    if base in ("byte", "char", "string", "str"):
        return False
    return True


def _param_provenance_confidence(p: dict) -> tuple[float, float]:
    """Extract (direction_confidence, type_confidence) from a parameter's provenance.

    Returns (0.5, 0.5) if no provenance is attached.
    """
    prov = p.get("_ghidra_provenance")
    if prov is None:
        return 0.5, 0.5
    dir_prov = prov.get("direction", {})
    type_prov = prov.get("param_type", {})
    dir_conf = dir_prov.get("confidence", 0.5) if isinstance(dir_prov, dict) else 0.5
    type_conf = type_prov.get("confidence", 0.5) if isinstance(type_prov, dict) else 0.5
    return dir_conf, type_conf


def _classify_param_kind(p: dict, id_formats: list[str] | None = None) -> str:
    """Infer the semantic kind of a parameter from its name, description, and type."""
    name = str(p.get("name") or "").lower()
    desc = str(p.get("description") or "").lower()
    jtype = str(p.get("json_type") or "string").lower()

    if re.search(r"order", name) or re.search(r"order", desc):
        return "order_id"
    if re.search(r"customer|account", name) or re.search(r"customer|account", desc):
        return "customer_id"
    if re.search(r"transaction|txn", name) or re.search(r"transaction|txn", desc):
        return "transaction_id"
    if re.search(r"quote", name) or re.search(r"quote", desc):
        return "quote_id"
    if re.search(r"report", name) or re.search(r"report", desc):
        return "report_id"
    if re.search(r"ticket", name) or re.search(r"ticket", desc):
        return "ticket"
    if re.search(r"nonce", name) or re.search(r"nonce", desc):
        return "nonce"
    if re.search(r"blob", name) or re.search(r"blob", desc):
        return "blob_token"
    if re.search(r"token|auth", name) or re.search(r"token|auth", desc):
        return "auth_token"
    if re.search(r"handle|session", name) or re.search(r"handle|session", desc):
        return "handle"
    if re.search(r"qty|quantity", name) or re.search(r"qty|quantity", desc):
        return "integer"
    if re.search(r"hold", name) and re.search(r"minute|duration", desc):
        return "integer"
    if re.search(r"sku|product|item", name) or re.search(r"sku|product|item", desc):
        return "sku"
    if (
        re.search(r"reserv|resv", name)
        and re.search(r"id|identifier|code|number", name)
    ) or (
        re.search(r"reserv|resv", desc)
        and re.search(r"id|identifier|code|number", desc)
    ):
        return "reservation_id"
    if re.search(r"amount|cents|payment|debit|credit", name):
        return "amount"
    if re.search(r"points", name) or re.search(r"points", desc):
        return "points"
    if re.search(r"size|count|length|len|buf", name):
        return "buffer_size"
    if jtype in {"integer", "number"}:
        return "integer"
    if jtype == "boolean":
        return "boolean"
    return "string_id" if jtype == "string" else "unknown"


def _extract_explicit_preconditions(inv: dict, known_names: set[str] | None = None) -> list[str]:
    def _valid_name(name: str) -> bool:
        stripped = str(name or "").strip()
        if _is_pseudo_function_name(stripped):
            return False
        return bool(re.match(r"^[A-Za-z_]\w*$", stripped))

    fn_name = str(inv.get("name") or "")
    doc = str(inv.get("doc_comment") or inv.get("doc") or "")
    match = _EXPLICIT_PRECONDITION_RE.search(doc)
    if not match:
        return []
    raw = match.group(1).split("Canonical args:", 1)[0]
    parts = [part.strip() for part in re.split(r"[|,]", raw) if part.strip()]
    names = [part for part in parts if _valid_name(part)]
    if known_names:
        names = [name for name in names if name in known_names]
    names = [name for name in names if name != fn_name]
    return names[:4]


def _find_matching_functions(invocables: list[dict], pattern: re.Pattern[str], exclude_name: str) -> list[str]:
    matches: list[str] = []
    for inv in invocables:
        fn_name = str(inv.get("name") or "")
        if _is_pseudo_function_name(fn_name) or fn_name == exclude_name:
            continue
        if pattern.search(fn_name):
            matches.append(fn_name)
    return matches


def _infer_heuristic_preconditions(inv: dict, invocables: list[dict], known_names: set[str]) -> tuple[list[str], list[str]]:
    fn_name = str(inv.get("name") or "")
    if _DAG_INIT_RE.search(fn_name):
        return [], []
    doc = str(inv.get("doc_comment") or inv.get("doc") or "")
    doc_lower = doc.lower()
    params = [p for p in (inv.get("parameters") or []) if isinstance(p, dict)]
    param_text = " ".join(
        f"{p.get('name') or ''} {p.get('description') or ''} {p.get('resolved_type') or p.get('type') or ''}"
        for p in params
    ).lower()
    inferred: list[str] = []
    reasons: list[str] = []

    def _add(pattern: re.Pattern[str], reason: str) -> None:
        for candidate in _find_matching_functions(invocables, pattern, fn_name):
            if candidate in known_names and candidate not in inferred:
                inferred.append(candidate)
        if reason not in reasons and inferred:
            reasons.append(reason)

    if "not initialized" in doc_lower or "g_initial" in doc_lower:
        _add(_INIT_RE, "doc hints that initialization state is required")
    if _CUSTOMER_GATE_HINT_RE.search(doc):
        _add(re.compile(r"bind.*customer|customer.*bind", re.I), "doc hints that customer binding gate is required")
    if _RESERVATION_GATE_HINT_RE.search(doc):
        _add(re.compile(r"create.*reserv|reserv.*create|reserve", re.I), "doc hints that reservation state must exist first")
    if _OPEN_GATE_HINT_RE.search(doc):
        _add(re.compile(r"open", re.I), "doc hints that an open/session gate is required")
    if _APPROVAL_HINT_RE.search(doc):
        _add(re.compile(r"approve|confirm|get.*nonce|nonce", re.I), "doc hints that approval or nonce-producing state is required")
    if _LICENSE_GATE_HINT_RE.search(doc):
        _add(re.compile(r"setup|initialize|approve|bind", re.I), "doc hints that licensed/setup state is required")
    if (
        re.search(r"open|fulfill", fn_name, re.I)
        and re.search(r"reserv|resv", param_text, re.I)
    ):
        _add(
            re.compile(r"create.*reserv|reserv.*create|reserve", re.I),
            "reservation-bearing open suggests a reservation-producing prerequisite",
        )

    if not inferred and _STATE_CONSUMER_RE.search(fn_name):
        if re.search(r"nonce", fn_name, re.I):
            _add(re.compile(r"open|begin|prepare|bind", re.I), "name suggests nonce read after an open/bind gate")
        elif re.search(r"state|status|echo|diagnostic|render|export", fn_name, re.I):
            _add(re.compile(r"open|prepare|begin|approve|confirm", re.I), "name suggests state read after lifecycle transition")
    elif not inferred and re.search(r"run|commit|submit|close|cancel", fn_name, re.I):
        _add(re.compile(r"approve|confirm|open|begin|prepare|bind", re.I), "name suggests a late lifecycle transition")

    return inferred[:4], reasons[:3]


def _lifecycle_rank(fn_name: str) -> int | None:
    lowered = str(fn_name or "").lower()
    if not lowered:
        return None
    if re.search(r"(?:^|_)(init|initialize|startup|start|setup|connect|login|logon)", lowered):
        return 0
    if re.search(r"(?:^|_)(bind|load|select|attach)", lowered):
        return 1
    if re.search(r"(?:^|_)(open|begin|prepare|create|reserve)", lowered):
        return 2
    if re.search(r"get.*nonce|nonce", lowered):
        return 3
    if re.search(r"(?:^|_)(approve|confirm)", lowered):
        return 4
    if re.search(r"(?:^|_)(run|submit|commit|seal|close|cancel)|state|status|diagnostic|echo|render|export", lowered):
        return 5
    return None


def _is_backward_lifecycle_edge(producer: str, consumer: str) -> bool:
    producer_name = str(producer or "").strip()
    consumer_name = str(consumer or "").strip()
    if not producer_name or not consumer_name:
        return False
    producer_family = producer_name.split("_", 1)[0].lower()
    consumer_family = consumer_name.split("_", 1)[0].lower()
    if not producer_family or producer_family != consumer_family:
        return False
    producer_rank = _lifecycle_rank(producer_name)
    consumer_rank = _lifecycle_rank(consumer_name)
    if producer_rank is None or consumer_rank is None:
        return False
    return producer_rank > consumer_rank


def _infer_sequence_role(
    inv: dict,
    coarse_role: str,
    explicit_preconditions: list[str],
    heuristic_preconditions: list[str],
) -> tuple[str, float, list[str]]:
    fn_name = str(inv.get("name") or "")
    doc = str(inv.get("doc_comment") or inv.get("doc") or "")
    reasons: list[str] = []
    confidence = 0.0

    if _DAG_INIT_RE.search(fn_name):
        return "gate", 0.95, ["initializer establishes baseline state"]

    if explicit_preconditions:
        confidence = 0.9
        reasons.append("explicit required preconditions found in doc comment")
        if _STATE_CONSUMER_RE.search(fn_name):
            return "state_consumer", confidence, reasons
        if _LIFECYCLE_RE.search(fn_name):
            return "lifecycle_transition", confidence, reasons
        return "gate", confidence, reasons

    if heuristic_preconditions:
        confidence = 0.72
        reasons.append("decompiled text suggests lifecycle gating")
        if _STATE_CONSUMER_RE.search(fn_name):
            return "state_consumer", confidence, reasons
        if _LIFECYCLE_RE.search(fn_name):
            return "lifecycle_transition", confidence, reasons
        if coarse_role in {"producer", "transformer"}:
            return "gate", confidence, reasons

    if _STATE_CONSUMER_RE.search(fn_name) and (
        "handle" in " ".join(str(p.get("name") or "").lower() for p in (inv.get("parameters") or []))
        or "ticket" in " ".join(str(p.get("name") or "").lower() for p in (inv.get("parameters") or []))
    ):
        return "state_consumer", 0.62, ["name and params suggest state read after prior lifecycle state"]

    if _LIFECYCLE_RE.search(fn_name) and coarse_role in {"consumer", "transformer", "producer"}:
        return "lifecycle_transition", 0.58, ["name suggests lifecycle transition, but evidence is weak"]

    return "unknown", 0.0, []


def build_prerequisite_dag(
    invocables: list[dict],
    id_formats: list[str] | None = None,
) -> tuple[list[FunctionRole], list[PrerequisiteEdge]]:
    """Analyze invocables to build a same-DLL producer/consumer dependency DAG.

    Provenance-aware: when parameters carry ``_ghidra_provenance``, direction
    and type confidence are used to scale edge confidence.  High-trust
    direction + high-trust type → strong edge (≈0.9).  Low-trust heuristic
    pointer inference → weak edge (≈0.4).

    Returns:
        (roles, edges) where roles classify each function and edges represent
        data-flow dependencies between them.
    """
    roles: list[FunctionRole] = []
    role_map: dict[str, FunctionRole] = {}
    fn_prov_conf: dict[str, tuple[float, float]] = {}
    known_names = {
        str(inv.get("name") or "")
        for inv in invocables
        if not _is_pseudo_function_name(str(inv.get("name") or ""))
    }
    inv_map = {
        str(inv.get("name") or ""): inv
        for inv in invocables
        if not _is_pseudo_function_name(str(inv.get("name") or ""))
    }
    explicit_preconditions: dict[str, list[str]] = {}
    heuristic_preconditions: dict[str, list[str]] = {}
    heuristic_reasons: dict[str, list[str]] = {}

    for inv in invocables:
        fn_name = str(inv.get("name") or "")
        if _is_pseudo_function_name(fn_name):
            continue
        params = list(inv.get("parameters") or [])

        input_kinds: list[str] = []
        output_kinds: list[str] = []
        has_output_buf = False
        input_count = 0
        dir_confs: list[float] = []
        type_confs: list[float] = []

        for p in params:
            if isinstance(p, str):
                p = {"name": p, "json_type": "string"}
            d_conf, t_conf = _param_provenance_confidence(p)
            dir_confs.append(d_conf)
            type_confs.append(t_conf)

            if _is_output_param(p):
                has_output_buf = True
                output_kinds.append("output_buffer")
                out_kind = _classify_param_kind(p, id_formats)
                if out_kind not in {"unknown", "integer", "boolean", "buffer_size"}:
                    output_kinds.append(out_kind)
            else:
                input_count += 1
                kind = _classify_param_kind(p, id_formats)
                input_kinds.append(kind)

        avg_dir = sum(dir_confs) / len(dir_confs) if dir_confs else 0.5
        avg_type = sum(type_confs) / len(type_confs) if type_confs else 0.5
        fn_prov_conf[fn_name] = (avg_dir, avg_type)

        if _DAG_INIT_RE.search(fn_name):
            role = "init"
        elif _VERSION_RE.search(fn_name):
            role = "version"
        elif input_count == 0:
            role = "producer"
        elif has_output_buf and _READ_RE.search(fn_name):
            role = "producer"
        elif has_output_buf and _WRITE_RE.search(fn_name):
            role = "transformer"
        elif _WRITE_RE.search(fn_name):
            role = "consumer"
        elif has_output_buf:
            role = "transformer"
        else:
            role = "unknown"

        fr = FunctionRole(
            name=fn_name,
            role=role,
            input_kinds=input_kinds,
            output_kinds=output_kinds,
            has_output_buffer=has_output_buf,
            param_count=len(params),
            input_param_count=input_count,
        )
        roles.append(fr)
        role_map[fn_name] = fr
        explicit_preconditions[fn_name] = _extract_explicit_preconditions(inv, known_names)
        inferred_prereqs, inferred_reasons = _infer_heuristic_preconditions(inv, invocables, known_names)
        heuristic_preconditions[fn_name] = inferred_prereqs
        heuristic_reasons[fn_name] = inferred_reasons

    edges: list[PrerequisiteEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()

    def _append_edge(edge: PrerequisiteEdge) -> None:
        key = (edge.producer, edge.consumer, edge.shared_kind)
        if key in seen_edges or edge.producer == edge.consumer:
            return
        edges.append(edge)
        seen_edges.add(key)

    producers = [r for r in roles if r.role in ("init", "producer", "transformer", "version")]
    consumers = [r for r in roles if r.role in ("consumer", "transformer", "unknown")]

    init_fns = [r for r in roles if r.role == "init"]
    for consumer in consumers:
        if consumer.role == "init":
            continue
        for init_fn in init_fns:
            _append_edge(PrerequisiteEdge(
                producer=init_fn.name,
                consumer=consumer.name,
                shared_kind="init_dependency",
                confidence=0.9,
            ))

    for producer in producers:
        if producer.role == "init":
            continue
        for consumer in consumers:
            if producer.name == consumer.name:
                continue
            shared = set(producer.output_kinds) & set(consumer.input_kinds)
            if not shared:
                prod_out_kinds = set()
                if producer.has_output_buffer:
                    for ik in consumer.input_kinds:
                        if ik in ("customer_id", "order_id", "transaction_id",
                                  "reservation_id", "sku", "string_id"):
                            prod_out_kinds.add(ik)
                shared = prod_out_kinds

            for kind in shared:
                base_conf = 0.6 if kind == "output_buffer" else 0.7
                prod_dir, prod_type = fn_prov_conf.get(producer.name, (0.5, 0.5))
                cons_dir, cons_type = fn_prov_conf.get(consumer.name, (0.5, 0.5))
                prov_factor = (prod_dir + prod_type + cons_dir + cons_type) / 4.0
                scaled_conf = round(base_conf * (0.4 + 0.6 * prov_factor), 2)
                _append_edge(PrerequisiteEdge(
                    producer=producer.name,
                    consumer=consumer.name,
                    shared_kind=kind,
                    confidence=scaled_conf,
                ))

    for fn_name, prereqs in explicit_preconditions.items():
        for prereq_name in prereqs:
            _append_edge(PrerequisiteEdge(
                producer=prereq_name,
                consumer=fn_name,
                shared_kind="explicit_precondition",
                confidence=0.95,
            ))

    for fn_name, prereqs in heuristic_preconditions.items():
        for prereq_name in prereqs:
            _append_edge(PrerequisiteEdge(
                producer=prereq_name,
                consumer=fn_name,
                shared_kind="heuristic_gate",
                confidence=0.72,
            ))

    upstream_by_consumer: dict[str, list[PrerequisiteEdge]] = {}
    for edge in edges:
        upstream_by_consumer.setdefault(edge.consumer, []).append(edge)

    for fn_name, fr in role_map.items():
        explicit = explicit_preconditions.get(fn_name) or []
        heuristic = heuristic_preconditions.get(fn_name) or []
        upstream = sorted(
            upstream_by_consumer.get(fn_name, []),
            key=lambda edge: (
                1 if edge.shared_kind in {"explicit_precondition", "init_dependency"} else 0,
                edge.confidence,
                edge.producer,
            ),
            reverse=True,
        )
        ranked_prereqs: list[str] = []
        for prereq_name in explicit + heuristic:
            if prereq_name == fn_name:
                continue
            if _is_backward_lifecycle_edge(prereq_name, fn_name):
                continue
            if prereq_name in known_names and prereq_name not in ranked_prereqs:
                ranked_prereqs.append(prereq_name)
        for edge in upstream:
            if edge.confidence < 0.55:
                continue
            if edge.producer == fn_name:
                continue
            if _is_backward_lifecycle_edge(edge.producer, fn_name):
                continue
            if edge.producer not in ranked_prereqs:
                ranked_prereqs.append(edge.producer)

        seq_role, seq_conf, seq_reasons = _infer_sequence_role(
            inv_map.get(fn_name, {}),
            fr.role,
            explicit,
            heuristic,
        )
        if heuristic_reasons.get(fn_name):
            for reason in heuristic_reasons[fn_name]:
                if reason not in seq_reasons:
                    seq_reasons.append(reason)
        fr.prerequisites = ranked_prereqs[:4]
        fr.sequence_role = seq_role
        fr.sequence_confidence = seq_conf
        fr.sequence_reasons = seq_reasons[:4]

    return roles, edges


def dag_to_execution_layers(
    roles: list[FunctionRole],
    edges: list[PrerequisiteEdge],
) -> list[list[str]]:
    """Convert the DAG into ordered execution layers.

    Layer 0: init + version functions (no dependencies)
    Layer 1: producers (functions that produce values with few/no ID inputs)
    Layer 2: consumers (functions that consume discovered values)
    Layer 3: dependents (functions that consume outputs of other functions)
    """
    layer_map: dict[str, int] = {}
    role_map = {r.name: r for r in roles}

    deps: dict[str, set[str]] = {r.name: set() for r in roles}
    for edge in edges:
        if edge.consumer in deps:
            deps[edge.consumer].add(edge.producer)

    for r in roles:
        if r.role in ("init", "version"):
            layer_map[r.name] = 0

    for r in roles:
        if r.name in layer_map:
            continue
        if r.role == "producer":
            has_non_init_dep = any(
                role_map.get(d, FunctionRole(name="", role="unknown")).role not in ("init", "version")
                for d in deps[r.name]
            )
            layer_map[r.name] = 2 if has_non_init_dep else 1
        elif r.role == "consumer":
            has_non_init_dep = any(
                role_map.get(d, FunctionRole(name="", role="unknown")).role not in ("init", "version")
                for d in deps[r.name]
            )
            layer_map[r.name] = 3 if has_non_init_dep else 2
        elif r.role == "transformer":
            has_producer_dep = any(
                role_map.get(d, FunctionRole(name="", role="unknown")).role in ("producer", "transformer")
                for d in deps[r.name]
            )
            layer_map[r.name] = 3 if has_producer_dep else 2
        else:
            layer_map[r.name] = 2

    max_layer = max(layer_map.values()) if layer_map else 0
    layers: list[list[str]] = [[] for _ in range(max_layer + 1)]
    for fn_name, layer_idx in sorted(layer_map.items(), key=lambda x: (x[1], x[0])):
        layers[layer_idx].append(fn_name)

    return [layer for layer in layers if layer]
