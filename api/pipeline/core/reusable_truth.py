from __future__ import annotations

import re
from typing import Any

from api.pipeline.core.finding_status import normalize_status

_PLACEHOLDER_REPLAY_VALUE_RE = re.compile(r"^[a-z_]+-from-[a-z_]+$", re.I)
_STRING_POINTER_RE = re.compile(r"(char|wchar|string)", re.I)
_CUSTOMER_TOKENS = ("CUST-", "ACCOUNT-", "CLIENT-", "USER-", "ACCT-")
_SKU_TOKENS = ("WDG-", "GDG-", "PRO-", "ITEM-", "SW-", "ACC-")
_FAMILY_PATTERNS: dict[str, re.Pattern[str]] = {
    "customer_id": re.compile(r"^(?:CUST|ACCOUNT|CLIENT|USER|ACCT)-[A-Z0-9-]+$", re.I),
    "sku": re.compile(r"^(?:WDG|GDG|PRO|ITEM|SW|ACC)-[A-Z0-9-]+$", re.I),
    "reservation_id": re.compile(r"^(?:(?:SP-)?RESV|RSV)-[A-Z0-9-]+$", re.I),
    "operator_id": re.compile(r"^(?:(?:EASY|MEDIUM|HARD)\d+-OPERATOR|ACTIVATION-OPERATOR|ORD-\d+)$", re.I),
    "operator_token": re.compile(r"^SP-OPERATOR-[A-Z0-9-]+$", re.I),
    "hold_token": re.compile(r"^SP-HOLD-[A-Z0-9-]+$", re.I),
    "preview_ticket": re.compile(r"^SP-PREVIEW-[A-Z0-9-]+$", re.I),
    "fee_quote_id": re.compile(r"^SP-FEE-[A-Z0-9-]+$", re.I),
    "attestation_packet": re.compile(r"^SP-ATT-[A-Z0-9-]+(?:-PACKET)?$", re.I),
    "stale_attestation_token": re.compile(r"^SP-ATT-STALE-[A-Z0-9-]+$", re.I),
    "stale_reason": re.compile(r"^freshness_gap\|epoch=\d+\|packet=sp-att-[A-Z0-9-]+(?:-packet)?$", re.I),
    "audit_token": re.compile(r"^SP-AUDIT-[A-Z0-9-]+$", re.I),
    "quote_id": re.compile(r"^(?:PRQ|QTE)-[A-Z0-9-]+$", re.I),
    "report_id": re.compile(r"^RPT-[A-Z0-9-]+$", re.I),
    "ticket": re.compile(r"^(?:CFG|SP-VERIFY)-[A-Z0-9-]+$", re.I),
    "workflow_handle": re.compile(r"^WFH-[A-Z0-9-]+$", re.I),
}
_FAMILY_KINDS = frozenset(_FAMILY_PATTERNS)
_SEMANTIC_OUTPUT_KINDS = _FAMILY_KINDS.union({"nonce", "handle", "blob_token"})


def _is_output_param(param: dict[str, Any]) -> bool:
    direction = str(param.get("direction") or "").strip().lower()
    if direction in {"out", "inout", "output"}:
        return True
    name = str(param.get("name") or "")
    return bool(name) and name.lower().startswith(("pout", "out"))


def _is_placeholder_replay_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = str(value or "").strip()
    if not text:
        return False
    if _PLACEHOLDER_REPLAY_VALUE_RE.match(text):
        return True
    return text.upper() in {
        "HANDLE-FROM-OPEN",
        "QUOTE-FROM-BEGIN",
        "REPORT-FROM-PREPARE",
        "RESERVATION-FROM-CREATE",
        "TICKET-FROM-OPEN",
    }


def _expected_param_kind(param: dict[str, Any]) -> str | None:
    name = str(param.get("name") or "")
    description = str(param.get("description") or param.get("type") or "")
    lowered = f"{name} {description}".lower()
    lowered_name = name.lower()
    compact_name = re.sub(r"[^a-z0-9]+", "", lowered_name)

    if "qty" in lowered or "quantity" in lowered:
        return "quantity"
    if "hold" in lowered and ("minute" in lowered or "duration" in lowered):
        return "hold_minutes"
    if "operator_token" in lowered_name:
        return "operator_token"
    if (
        "operator_id" in lowered_name
        or "operatoridentifier" in compact_name
        or "operatorid" in compact_name
        or (
            "operator" in lowered
            and "identifier" in lowered
            and "token" not in lowered_name
        )
    ):
        return "operator_id"
    if "hold_token" in lowered_name:
        return "hold_token"
    if "reservation_handle" in lowered_name or "reservation_id" in lowered_name:
        return "reservation_id"
    if "preview_ticket" in lowered_name:
        return "preview_ticket"
    if "fee_quote" in lowered_name:
        return "fee_quote_id"
    if (
        _is_output_param(param)
        and "audit_token" in lowered_name
        and ("object-bound" in lowered or "rejected branch" in lowered)
    ):
        return "blob_token"
    if "audit_token" in lowered_name:
        return "audit_token"
    if "stale" in lowered_name and "attestation" in lowered_name and "token" in lowered_name:
        return "stale_attestation_token"
    if "stale" in lowered_name and "reason" in lowered_name:
        return "stale_reason"
    if "attestation" in lowered_name and "packet" in lowered_name:
        return "attestation_packet"
    if re.search(r"(?:^|_)(?:len|length|size|capacity|count)(?:$|_)", lowered_name) and not any(
        token in lowered_name for token in ("token", "ticket", "quote", "report", "reservation")
    ):
        return "buffer_size"
    if (
        any(token in lowered for token in ("buf", "buffer"))
        and any(token in lowered for token in ("size", "len", "length", "capacity", "count", "bytes"))
    ):
        return "buffer_size"
    if any(token in lowered for token in ("customer", "custid", "cust_id", "account id", "account_id", "acct")):
        return "customer_id"
    if "sku" in lowered or "product" in lowered or "item code" in lowered:
        return "sku"
    if "operator" in lowered and "token" in lowered:
        return "operator_token"
    if "hold" in lowered and "token" in lowered:
        return "hold_token"
    if "reservation" in lowered or "resv" in lowered:
        return "reservation_id"
    if "preview" in lowered and "ticket" in lowered:
        return "preview_ticket"
    if "fee" in lowered and "quote" in lowered:
        return "fee_quote_id"
    if "audit" in lowered and "token" in lowered:
        return "audit_token"
    if "stale" in lowered and "attestation" in lowered and "token" in lowered:
        return "stale_attestation_token"
    if "stale" in lowered and "reason" in lowered:
        return "stale_reason"
    if "attestation" in lowered and "packet" in lowered:
        return "attestation_packet"
    if "workflow" in lowered and "handle" in lowered:
        return "workflow_handle"
    if "quote" in lowered and "id" in lowered:
        return "quote_id"
    if "report" in lowered and "id" in lowered:
        return "report_id"
    if "ticket" in lowered:
        return "ticket"
    if "nonce" in lowered:
        return "nonce"
    if "handle" in lowered or "session" in lowered:
        return "handle"
    if "token" in lowered:
        return "blob_token"
    return None


def _looks_customer_like(value: Any) -> bool:
    upper = str(value or "").upper()
    return any(token in upper for token in _CUSTOMER_TOKENS)


def _looks_sku_like(value: Any) -> bool:
    upper = str(value or "").upper()
    return any(token in upper for token in _SKU_TOKENS)


def _value_matches_kind(kind: str | None, value: Any) -> bool:
    if kind is None:
        return value not in (None, "")
    if kind in _FAMILY_KINDS:
        if not isinstance(value, str) or _is_placeholder_replay_value(value):
            return False
        return bool(_FAMILY_PATTERNS[kind].match(str(value or "").strip()))
    if kind == "customer_id":
        return isinstance(value, str) and _looks_customer_like(value) and not _looks_sku_like(value)
    if kind == "sku":
        return isinstance(value, str) and _looks_sku_like(value) and not _looks_customer_like(value)
    if kind == "quantity":
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
    if kind == "hold_minutes":
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
    if kind == "buffer_size":
        return isinstance(value, int) and not isinstance(value, bool) and value >= 24
    if kind in {"nonce", "handle", "blob_token"}:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
    return value not in (None, "")


def assess_reusable_truth(
    finding: dict[str, Any],
    *,
    invocable: dict[str, Any] | None = None,
) -> dict[str, Any]:
    canonical_status = normalize_status(
        (finding or {}).get("status_canonical") or (finding or {}).get("status")
    )
    working_call = (finding or {}).get("working_call")
    verification = str((finding or {}).get("verification") or "").strip().lower()
    cross_validation = str((finding or {}).get("cross_validation") or "").strip()
    verified_evidence = verification == "verified" or bool(cross_validation)

    result: dict[str, Any] = {
        "seed_eligible": False,
        "demote_success": False,
        "score": 0.0,
        "checked_params": 0,
        "match_count": 0,
        "mismatch_count": 0,
        "reasons": [],
    }

    if canonical_status != "verified_success":
        result["reasons"] = ["status_not_verified_success"]
        return result
    if not isinstance(working_call, dict) or not working_call:
        result["reasons"] = ["missing_working_call"]
        return result

    placeholder_keys = sorted(
        key for key, value in working_call.items()
        if _is_placeholder_replay_value(value)
    )
    if placeholder_keys:
        result["reasons"] = [f"placeholder_replay_values:{','.join(placeholder_keys[:4])}"]
        result["demote_success"] = not verified_evidence
        return result

    score = 0.0
    reasons: list[str] = []
    checked = 0
    matches = 0
    mismatches = 0

    if verified_evidence:
        score += 2.0

    params = [p for p in (invocable or {}).get("parameters") or [] if isinstance(p, dict)]
    for param in params:
        if _is_output_param(param):
            continue
        pname = str(param.get("name") or "").strip()
        if not pname or pname not in working_call:
            continue

        value = working_call.get(pname)
        expected_kind = _expected_param_kind(param)
        resolved_type = str(param.get("resolved_type") or param.get("type") or "")
        json_type = str(param.get("json_type") or "").strip().lower()

        checked += 1
        if _value_matches_kind(expected_kind, value):
            matches += 1
            score += 1.5 if expected_kind else 0.5
        else:
            mismatches += 1
            if expected_kind:
                reasons.append(f"{pname}_expected_{expected_kind}")
            else:
                reasons.append(f"{pname}_type_mismatch")
            score -= 2.5

        if json_type in {"integer", "number"}:
            if isinstance(value, int) and not isinstance(value, bool):
                score += 0.25
            else:
                score -= 1.0
        elif json_type == "string":
            if isinstance(value, str):
                score += 0.25
            else:
                score -= 1.0
        elif not json_type and _STRING_POINTER_RE.search(resolved_type):
            if isinstance(value, str):
                score += 0.25
            else:
                score -= 1.0

    if checked == 0:
        for key, value in working_call.items():
            expected_kind = _expected_param_kind({"name": key, "description": key})
            if expected_kind is None:
                continue
            checked += 1
            if _value_matches_kind(expected_kind, value):
                matches += 1
                score += 1.0
            else:
                mismatches += 1
                reasons.append(f"{key}_expected_{expected_kind}")
                score -= 2.0

    if checked == 0 and not verified_evidence:
        score -= 0.5
        reasons.append("no_semantic_alignment_checks")

    if matches and mismatches == 0:
        score += 0.5

    semantic_output_failures: list[str] = []
    for param in params:
        if not _is_output_param(param):
            continue
        pname = str(param.get("name") or "").strip()
        if not pname or pname not in working_call:
            continue
        expected_kind = _expected_param_kind(param)
        if expected_kind not in _SEMANTIC_OUTPUT_KINDS:
            continue
        value = working_call.get(pname)
        if _value_matches_kind(expected_kind, value):
            matches += 1
            checked += 1
            score += 1.0
            continue
        checked += 1
        mismatches += 1
        semantic_output_failures.append(f"{pname}_expected_{expected_kind}")
        score -= 3.0

    if semantic_output_failures:
        reasons.extend(semantic_output_failures)

    semantic_mismatch = mismatches > 0
    seed_eligible = not semantic_output_failures and not semantic_mismatch and (verified_evidence or score >= 1.0)

    if not seed_eligible and not reasons:
        reasons.append("low_expected_observed_alignment")

    result.update(
        {
            "seed_eligible": seed_eligible,
            "demote_success": not seed_eligible and not verified_evidence,
            "score": round(score, 2),
            "checked_params": checked,
            "match_count": matches,
            "mismatch_count": mismatches,
            "reasons": reasons[:6],
        }
    )
    return result
