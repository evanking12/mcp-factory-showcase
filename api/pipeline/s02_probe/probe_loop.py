"""api.pipeline.s02_probe.probe_loop – Per-function LLM probe loop.

Contains _classify_arg_source, _explore_one, and _run_phase_3_probe_loop.
"""
from __future__ import annotations

import json
import logging
import re as _re
import threading as _threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor as _TPE
from typing import Any

from api.infra.config import ARTIFACT_CONTAINER
from api.services.executor import _execute_tool, _execute_tool_traced
from api.infra.storage import (
    _persist_job_status, _get_job_status, _patch_invocable,
    _save_finding, _patch_finding, _upload_to_blob, _download_blob,
    _append_transcript, _append_executor_trace, _append_explore_probe_log,
    _register_invocables, _merge_invocables, _get_current_invocables,
)
from api.infra.telemetry import _openai_client
from api.pipeline.core.helpers import (
    _SENTINEL_DEFAULTS, _CAP_PROFILE,
    _MAX_EXPLORE_ROUNDS_PER_FUNCTION, _MAX_TOOL_CALLS_PER_FUNCTION, _MAX_FUNCTIONS_PER_SESSION,
    _GAP_RESOLUTION_ENABLED,
    _INIT_RE,
    _VERSION_FN_RE,
    _WRITE_FN_RE,
    _WRITE_RETRY_BUDGET_BY_CLASS,
    _build_ranked_fallback_probe_args,
    _build_tool_schemas,
    _cancel_requested,
    _canonical_args_from_doc,
    _classify_result_text,
    _default_scalar_value,
    _infer_param_desc,
    FINDING_VERIFIED_STATUSES,
    _save_stage_context,
    _sentinel_class_from_classification,
    _set_explore_status,
    _snapshot_schema_stage,
    _ranked_param_candidates,
    _strip_output_buffer_params,
    _tool_schema_doc_prefix_hint,
    _merge_result_output_values,
    _is_true_output_param,
    _write_policy_precheck,
)
from api.pipeline.core.finding_status import is_functional_precondition_text
from api.pipeline.core.system_contract import (
    observe_lineage_handoff,
    observe_live_artifact_emission,
)
from api.pipeline.s00_setup.calibration import (
    _calibrate_sentinels,
    _name_sentinel_candidates,
)
from api.pipeline.s01_unlock.write_unlock import _probe_write_unlock
from api.pipeline.core.vocab import (
    _update_vocabulary, _generate_hypothesis, _backfill_schema_from_synthesis,
    _vocab_block, _uncertainty_score,
)
from api.pipeline.core.prompts import (
    _build_explore_system_message, _generate_behavioral_spec,
    _synthesize, _generate_confidence_gaps,
)
from api.pipeline.core.reusable_truth import assess_reusable_truth
from api.pipeline.s06_gaps.gap_resolution import _attempt_gap_resolution, _run_gap_answer_mini_sessions
from api.pipeline.core.types import ExploreContext, ExploreRuntime

logger = logging.getLogger("mcp_factory.api")


def _must_probe_function(fn_name: str, ctx: ExploreContext) -> bool:
    runtime = getattr(ctx, "runtime", None)
    selected = {
        str(name or "").strip()
        for name in list(getattr(runtime, "selected_invocable_names", []) or [])
        if str(name or "").strip()
    }
    required = str(getattr(runtime, "required_semantic_checkpoint", "") or "").strip()
    if required:
        selected.add(required)
    return fn_name in selected


def _should_skip_documented_function(fn_name: str, ctx: ExploreContext) -> bool:
    """Return True when a previously explored function should still be skipped.

    Focused reruns must override the documented-skip gate so a targeted replay
    can force re-probing of already-seeded functions.
    """
    if not ctx.runtime.skip_documented:
        return False
    if _must_probe_function(fn_name, ctx):
        return False
    if fn_name not in ctx.already_explored:
        return False
    return fn_name not in set(ctx.runtime.focus_functions or [])

def _classify_arg_source(
    arg_name: str, arg_value, inv: dict, ctx_vocab: dict
) -> str:
    """Return a source tag for a single probe argument value.

    Tags: static_id | known_good_replay | default_numeric | fallback_string
    """
    id_fmts = ctx_vocab.get("id_formats") or []
    if isinstance(arg_value, str):
        for fmt in id_fmts:
            if "-" in fmt:
                prefix = fmt[: fmt.index("-") + 1]
                if arg_value.startswith(prefix):
                    return "static_id"
    known_good = ctx_vocab.get("known_good_args") or {}
    if arg_name in known_good and known_good[arg_name] == arg_value:
        return "known_good_replay"
    if isinstance(arg_value, (int, float)):
        return "default_numeric"
    return "fallback_string"


def _required_prefix_hints_for_inv(inv: dict) -> dict[str, str]:
    function_doc = str(inv.get("doc_comment") or inv.get("doc") or "")
    hints: dict[str, str] = {}
    for idx, param in enumerate(inv.get("parameters") or []):
        if not isinstance(param, dict):
            continue
        if _is_effective_output_param(inv, param, idx):
            continue
        pname = str(param.get("name") or "").strip()
        if not pname:
            continue
        prefix = _tool_schema_doc_prefix_hint(function_doc, pname)
        if prefix:
            hints[pname] = prefix
    return hints


def _extract_required_preconditions(inv: dict) -> list[str]:
    def _valid_name(name: str) -> bool:
        stripped = str(name or "").strip()
        if not stripped or not _re.match(r"^[A-Za-z_]\w*$", stripped):
            return False
        if stripped.lower() == "entry" or stripped.startswith("FUN_"):
            return False
        return True

    explicit = inv.get("_required_preconditions")
    if isinstance(explicit, list):
        return [
            str(part).strip()
            for part in explicit
            if _valid_name(str(part).strip())
        ]
    doc = str(inv.get("doc_comment") or inv.get("doc") or "")
    match = _re.search(r"Required preconditions:\s*([^\n]+)", doc)
    if not match:
        return []
    raw = match.group(1).split("Canonical args:", 1)[0]
    parts = [part.strip() for part in _re.split(r"[|,]", raw) if part.strip()]
    return [part for part in parts if _valid_name(part)]


def _requires_fresh_runtime_lineage(inv: dict) -> bool:
    fn = str(inv.get("name") or "").lower()
    if "freeblobtoken" in fn:
        return True
    _has_prereqs = bool(_extract_required_preconditions(inv))
    _sequence_role = str(inv.get("_sequence_role") or "").lower()
    _required_prefix_hints = _required_prefix_hints_for_inv(inv)
    _family_lineage_consumer = False
    for param in inv.get("parameters") or []:
        if not isinstance(param, dict):
            continue
        _kind = _semantic_arg_kind(
            str(param.get("name") or ""),
            None,
            str(param.get("json_type") or ""),
            str(param.get("description") or param.get("type") or ""),
        )
        if _kind in (_FAMILY_SENSITIVE_LINEAGE_KINDS | {"commit_receipt"}):
            _family_lineage_consumer = True
            break
    if _required_prefix_hints and (
        _has_prereqs
        or _sequence_role in {"state_consumer", "lifecycle_transition", "gate"}
        or len(set(_required_prefix_hints.values())) > 1
        or _re.search(r"emit|stage|confirm|commit|approve|sync|reconcile|seal|render|export|issue", fn)
    ):
        return True
    if _has_prereqs and _family_lineage_consumer:
        return True
    for idx, param in enumerate(inv.get("parameters") or []):
        if not isinstance(param, dict):
            continue
        raw_type = str(param.get("resolved_type") or param.get("type") or "").lower()
        text = f"{param.get('name') or ''} {param.get('description') or ''} {raw_type}"
        lowered = text.lower()
        if "blob" in lowered and "token" in lowered:
            return True
        if (
            _has_prereqs or _sequence_role in {"state_consumer", "lifecycle_transition", "gate"}
        ) and any(
            marker in lowered
            for marker in ("nonce", "ticket", "quote", "report", "handle", "session", "workflow")
        ):
            return True
        if (
            idx == 0
            and "*" in raw_type
            and not any(tok in raw_type for tok in ("char", "wchar", "byte", "uchar"))
            and any(
                marker in lowered
                for marker in (
                    "opaque runtime handle",
                    "runtime handle",
                    "session handle",
                    "workflow handle",
                    "instance handle",
                    "handle input",
                )
            )
            and not _re.search(r"(create|new|open|init|alloc)", fn)
        ):
            return True
    if _has_prereqs and _re.search(r"confirm|commit|approve|run|seal|render|export|state|nonce", fn):
        return True
    return False


def _prioritized_probe_id_hints(inv: dict, vocab: dict[str, Any] | None) -> list[str]:
    all_ids = [str(value) for value in list((vocab or {}).get("id_formats") or []) if value]
    if not all_ids:
        return []
    prioritized: list[str] = []
    seen: set[str] = set()
    for prefix in _required_prefix_hints_for_inv(inv).values():
        for value in all_ids:
            if value.startswith(prefix) and value not in seen:
                prioritized.append(value)
                seen.add(value)
                if len(prioritized) >= 4:
                    return prioritized
    for value in all_ids:
        if value in seen:
            continue
        prioritized.append(value)
        seen.add(value)
        if len(prioritized) >= 4:
            break
    return prioritized


def _function_family_prefix(fn_name: str) -> str:
    return str(fn_name or "").split("_", 1)[0].strip().lower()


_FRESH_LINEAGE_REBUILT_HINT_KEYS = {
    "reservation_id",
    "preview_ticket",
    "fee_quote_id",
    "quote_id",
    "report_id",
    "ticket",
    "workflow_handle",
    "nonce",
    "handle",
    "blob_token",
    "auth_token",
    "attestation_packet",
    "invoice_stage_id",
    "entitlement_stage_id",
    "confirmation_id",
}


_PLACEHOLDER_REPLAY_VALUE_RE = _re.compile(r"^[a-z_]+-from-[a-z_]+$", _re.I)


def _is_seeded_external_success(finding: dict[str, Any]) -> bool:
    source = str((finding or {}).get("source") or "").strip().lower()
    if source in {"prior_session", "cross_dll_prior", "checkpoint_resume"}:
        return True
    notes = str((finding or {}).get("notes") or "").strip().lower()
    if "seeded from prior session" in notes or "cross-dll seeded" in notes:
        return True
    return False


def _is_placeholder_replay_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = str(value or "").strip()
    if not text:
        return False
    if _PLACEHOLDER_REPLAY_VALUE_RE.match(text):
        return True
    upper = text.upper()
    if upper in {
        "HANDLE-FROM-OPEN",
        "QUOTE-FROM-BEGIN",
        "REPORT-FROM-PREPARE",
        "RESERVATION-FROM-CREATE",
        "TICKET-FROM-OPEN",
    }:
        return True
    return False


def _sanitize_lineage_hints_for_prereq_replay(
    hints: dict[str, Any] | None,
    *,
    fresh_lineage: bool,
) -> dict[str, Any]:
    sanitized = dict(hints or {})
    if not fresh_lineage:
        return sanitized
    return {
        key: value
        for key, value in sanitized.items()
        if key not in _FRESH_LINEAGE_REBUILT_HINT_KEYS
        and not (
            key in _FAMILY_SENSITIVE_LINEAGE_KINDS
            and _is_placeholder_replay_value(value)
        )
    }


def _collect_placeholder_replay_params(inv: dict, args: dict[str, Any]) -> dict[str, dict[str, Any]]:
    placeholders: dict[str, dict[str, Any]] = {}
    for idx, param in enumerate(inv.get("parameters") or []):
        if not isinstance(param, dict):
            continue
        if _is_effective_output_param(inv, param, idx):
            continue
        pname = str(param.get("name") or "")
        if not pname or pname not in (args or {}):
            continue
        value = args.get(pname)
        if not _is_placeholder_replay_value(value):
            continue
        expected_family = _semantic_arg_kind(
            pname,
            None,
            str(param.get("json_type") or ""),
            str(param.get("description") or param.get("type") or ""),
        )
        if expected_family == "handle" and (
            pname.lower().startswith("lpsz")
            or "char" in str(param.get("resolved_type") or param.get("type") or "").lower()
            or "workflow handle" in str(param.get("description") or "").lower()
        ):
            expected_family = "workflow_handle"
        if expected_family not in (_FAMILY_SENSITIVE_LINEAGE_KINDS | {"handle"}):
            continue
        placeholders[pname] = {
            "value": value,
            "expected_family": expected_family,
        }
    return placeholders


def _looks_runtime_handle_consumer(inv: dict) -> bool:
    fn_lower = str(inv.get("name") or "").lower()
    if _re.search(r"(create|new|open|init|alloc)", fn_lower):
        return False
    params = [p for p in (inv.get("parameters") or []) if isinstance(p, dict)]
    if not params:
        return False
    first = params[0]
    raw_type = str(first.get("resolved_type") or first.get("type") or "").lower()
    if "*" not in raw_type or any(tok in raw_type for tok in ("char", "wchar", "byte", "uchar")):
        return False
    lowered = (
        f"{first.get('name') or ''} "
        f"{first.get('description') or ''} "
        f"{first.get('type') or ''} "
        f"{first.get('resolved_type') or ''}"
    ).lower()
    return any(
        marker in lowered
        for marker in (
            "opaque runtime handle",
            "runtime handle",
            "session handle",
            "workflow handle",
            "handle input",
        )
    )


def _infer_runtime_prerequisites(inv: dict, inv_map: dict[str, dict]) -> list[str]:
    prereqs = list(_extract_required_preconditions(inv))
    seen = {name.lower() for name in prereqs}
    fn_name = str(inv.get("name") or "")
    family = _function_family_prefix(fn_name)
    if not family or not _looks_runtime_handle_consumer(inv):
        return prereqs

    siblings = [
        sibling
        for sibling in inv_map
        if sibling != fn_name and _function_family_prefix(sibling) == family
    ]

    def _append_match(pattern: str) -> None:
        ranked = sorted(
            (
                name
                for name in siblings
                if _re.search(pattern, name, _re.I)
            ),
            key=lambda name: (
                0 if _re.search(r"createinstance", name, _re.I) else 1,
                len((inv_map.get(name) or {}).get("parameters") or []),
                len(name),
                name.lower(),
            ),
        )
        for candidate in ranked:
            lowered = candidate.lower()
            if lowered not in seen:
                prereqs.append(candidate)
                seen.add(lowered)
                return

    _append_match(r"(createinstance|create|new|open|init|alloc)")
    if _re.search(r"(putsamples|receivesamples|num(?:unprocessed)?samples|flush|isempty)", fn_name, _re.I):
        _append_match(r"setchannels")
        _append_match(r"setsamplerate")
    return prereqs


def _lineage_hint_key(name: str, value: Any | None = None, json_type: str = "", description: str = "") -> str | None:
    name_lower = str(name or "").lower()
    lowered = f"{name} {description}".lower()
    lowered_tokens = set(_re.split(r"[^a-z0-9]+", lowered))
    value_text = str(value or "")
    if "commit" in lowered_tokens and any(tok in lowered_tokens for tok in ("receipt", "token", "code")):
        if any(tok in lowered_tokens for tok in ("primary", "trusted")):
            return "primary_commit_receipt"
        if any(tok in lowered_tokens for tok in ("replay", "replayed", "rejected", "untrusted")):
            return "replay_commit_receipt"
    if "rejected" in lowered_tokens and "branch" in lowered_tokens and any(
        marker in lowered for marker in ("id", "identifier", "code", "name")
    ):
        return "rejected_branch_id"
    if "trusted" in lowered_tokens and "branch" in lowered_tokens and any(
        marker in lowered for marker in ("id", "identifier", "code", "name")
    ):
        return "trusted_branch_id"
    if _re.match(r"^RESV-", value_text, _re.I):
        return "reservation_id"
    if _re.match(r"^[A-Za-z]+-resv-", value_text, _re.I):
        return "reservation_id"
    if "nonce" in lowered:
        return "nonce"
    if "attestation" in lowered and "epoch" in lowered:
        return "attestation_epoch"
    if isinstance(value, int) and not isinstance(value, bool) and ("handle" in lowered or "session" in lowered):
        return "handle"
    if _re.match(r"^(?:sp-operator-[A-Za-z0-9-]+|[A-Fa-f0-9]{6,32})$", value_text, _re.I):
        return "auth_token"
    if _re.match(r"^sp-att-stale-[A-Za-z0-9-]+$", value_text, _re.I):
        return "stale_attestation_token"
    if _re.match(r"^sp-att-[A-Za-z0-9-]+(?:-packet)?$", value_text, _re.I):
        return "attestation_packet"
    if _re.match(r"^freshness_gap\|epoch=\d+\|packet=sp-att-[A-Za-z0-9-]+(?:-packet)?$", value_text, _re.I):
        return "stale_reason"
    if _re.match(r"^sp-invoice-stage-[A-Za-z0-9-]+$", value_text, _re.I):
        return "invoice_stage_id"
    if _re.match(r"^sp-entitlement-stage-[A-Za-z0-9-]+$", value_text, _re.I):
        return "entitlement_stage_id"
    if _re.match(r"^sp-confirm-[A-Za-z0-9-]+$", value_text, _re.I):
        return "confirmation_id"
    if _re.match(r"^[A-Za-z]+-preview-", value_text, _re.I):
        return "preview_ticket"
    if _re.match(r"^[A-Za-z]+-fee-", value_text, _re.I):
        return "fee_quote_id"
    if _re.match(r"^[A-Za-z]+-hold-", value_text, _re.I):
        return "hold_token"
    if _re.match(r"^[A-Za-z]+-(?:commit|branch-replay)-", value_text, _re.I):
        return "commit_receipt"
    if _re.match(r"^PRQ-", value_text, _re.I):
        return "quote_id"
    if _re.match(r"^RPT-", value_text, _re.I):
        return "report_id"
    if _re.match(r"^CFG-", value_text, _re.I):
        return "ticket"
    if _re.match(r"^WFH-", value_text, _re.I):
        return "workflow_handle"
    if _re.match(r"^[A-Za-z0-9_-]+(?:\|[A-Za-z0-9_-]+=[^|]+){1,}$", value_text):
        return "ticket"
    if "blob" in lowered and "token" in lowered:
        return "blob_token"
    if not value_text and ("operator" in lowered and "token" in lowered):
        return "auth_token"
    if "attestation" in lowered and "packet" in lowered:
        return "attestation_packet"
    if "stale" in lowered and "attestation" in lowered and "token" in lowered:
        return "stale_attestation_token"
    if "stale" in lowered and "reason" in lowered:
        return "stale_reason"
    if "invoice" in lowered and "stage" in lowered and "id" in lowered:
        return "invoice_stage_id"
    if "entitlement" in lowered and "stage" in lowered and "id" in lowered:
        return "entitlement_stage_id"
    if "confirmation" in lowered and "id" in lowered:
        return "confirmation_id"
    if "preview" in lowered and "ticket" in lowered:
        return "preview_ticket"
    if "fee" in lowered and "quote" in lowered and "id" in lowered:
        return "fee_quote_id"
    if "report" in name_lower and any(
        marker in lowered for marker in ("id", "identifier", "code", "number")
    ):
        return "report_id"
    if ("reserv" in lowered or "resv" in lowered) and any(
        marker in lowered for marker in ("id", "identifier", "code", "number")
    ):
        return "reservation_id"
    if "sp-resv-" in lowered:
        return "reservation_id"
    if "sp-hold-" in lowered or ("hold" in lowered and "token" in lowered):
        return "hold_token"
    if (
        "sp-commit-" in lowered
        or "sp-branch-replay-" in lowered
        or ("commit" in lowered and any(tok in lowered for tok in ("receipt", "token", "code")))
    ):
        return "commit_receipt"
    if "quote" in lowered and "id" in lowered:
        return "quote_id"
    if "report" in lowered and "id" in lowered:
        return "report_id"
    if "ticket" in lowered:
        return "ticket"
    if not value_text and ("reserv" in lowered or "resv" in lowered) and "handle" in lowered:
        return "reservation_id"
    if "handle" in lowered or "session" in lowered or lowered.strip() == "lpszhandle":
        if isinstance(value, int) and not isinstance(value, bool):
            return "handle"
        if str(json_type or "").lower() in {"integer", "number"}:
            return "handle"
        return "workflow_handle"
    if "cust" in lowered or "customer" in lowered or "account" in lowered:
        return "customer_id"
    if "sku" in lowered or "product" in lowered or "item" in lowered:
        return "sku"
    if _re.match(r"^(CUST|ACCOUNT|CLIENT|ACCT|USER|USR)-", value_text, _re.I):
        return "customer_id"
    if _re.match(r"^(WDG|GDG|PRO|ITEM|SW|ACC)-", value_text, _re.I):
        return "sku"
    return None


def _structured_target_hints(args: dict[str, Any]) -> dict[str, Any]:
    hints: dict[str, Any] = {}

    def _add_hint(key: str, value: Any, *, raw_name: str = "") -> None:
        if not key or value in (None, ""):
            return
        hints.setdefault(key, value)
        role_key = _commit_receipt_role_hint(str(raw_name or ""), value)
        if key == "commit_receipt" and role_key:
            hints.setdefault(role_key, value)

    for key, value in (args or {}).items():
        lowered = str(key or "").lower()
        if isinstance(value, dict):
            for field_name, field_value in value.items():
                hint_key = _lineage_hint_key(str(field_name or ""), field_value)
                if hint_key:
                    _add_hint(hint_key, field_value, raw_name=str(field_name or ""))
        else:
            hint_key = _lineage_hint_key(lowered, value)
            if hint_key:
                _add_hint(hint_key, value, raw_name=lowered)
    return hints


_FAMILY_SENSITIVE_LINEAGE_KINDS = {
    "auth_token",
    "customer_id",
    "sku",
    "reservation_id",
    "preview_ticket",
    "fee_quote_id",
    "hold_token",
    "commit_receipt",
    "primary_commit_receipt",
    "replay_commit_receipt",
    "quote_id",
    "report_id",
    "ticket",
    "trusted_branch_id",
    "rejected_branch_id",
    "attestation_packet",
    "stale_attestation_token",
    "stale_reason",
    "invoice_stage_id",
    "entitlement_stage_id",
    "confirmation_id",
    "workflow_handle",
}


def _observed_lineage_family(
    value: Any,
    *,
    name: str = "",
    json_type: str = "",
    description: str = "",
) -> str | None:
    return _lineage_hint_key(name, value, json_type, description)


def _commit_receipt_role_hint(name: str, value: Any) -> str | None:
    lowered = str(name or "").lower()
    text = str(value or "").strip()
    if not text:
        return None
    if not _re.match(r"^[A-Za-z]+-(?:commit|branch-replay)-", text, _re.I):
        return None
    if "branch-replay" in text.lower() or any(tok in lowered for tok in ("replay", "replayed", "rejected", "untrusted")):
        return "replay_commit_receipt"
    if "commit" in text.lower() or any(tok in lowered for tok in ("primary", "trusted")):
        return "primary_commit_receipt"
    return None


def _semantic_arg_kind(name: str, value: Any | None = None, json_type: str = "", description: str = "") -> str | None:
    lowered = f"{name} {description}".lower()
    if "qty" in lowered or "quantity" in lowered:
        return "quantity"
    if "hold" in lowered and ("minute" in lowered or "duration" in lowered):
        return "hold_minutes"
    if (
        any(tok in lowered for tok in ("buf", "buffer"))
        and any(tok in lowered for tok in ("size", "len", "length", "capacity", "count"))
    ) or (
        any(tok in str(name or "").lower() for tok in ("len", "size", "count", "capacity"))
        and "buffer" in lowered
    ):
        return "buffer_size"
    kind = _lineage_hint_key(name, value, json_type, description)
    if kind:
        return kind
    return None


def _extract_inline_lineage_hints(result_text: str) -> dict[str, Any]:
    text = str(result_text or "")
    hints: dict[str, Any] = {}
    branch_patterns = {
        "trusted_branch_id": r"(?:^|\b)(?:trusted_branch_id|out_trusted_branch_id)\s*=\s*['\"]?(sp-branch-[A-Za-z0-9]+)['\"]?",
        "rejected_branch_id": r"(?:^|\b)(?:rejected_branch_id|out_rejected_branch_id)\s*=\s*['\"]?(sp-branch-[A-Za-z0-9]+)['\"]?",
    }
    for key, pattern in branch_patterns.items():
        match = _re.search(pattern, text, _re.I | _re.M)
        if match:
            hints[key] = match.group(1)
    patterns = {
        "reservation_id": r"(RESV-[A-Z0-9-]+)",
        "preview_ticket": r"([A-Za-z]+-preview-[A-Za-z0-9-]+)",
        "fee_quote_id": r"([A-Za-z]+-fee-[A-Za-z0-9-]+)",
        "hold_token": r"([A-Za-z]+-hold-[A-Za-z0-9-]+)",
        "commit_receipt": r"([A-Za-z]+-(?:commit|branch-replay)-[A-Za-z0-9-]+)",
        "stale_attestation_token": r"(sp-att-stale-[A-Za-z0-9-]+)",
        "stale_reason": r"(freshness_gap\|epoch=\d+\|packet=sp-att-[A-Za-z0-9-]+(?:-packet)?)",
        "attestation_packet": r"(sp-att-[A-Za-z0-9-]+(?:-packet)?)",
        "invoice_stage_id": r"(sp-invoice-stage-[A-Za-z0-9-]+)",
        "entitlement_stage_id": r"(sp-entitlement-stage-[A-Za-z0-9-]+)",
        "confirmation_id": r"(sp-confirm-[A-Za-z0-9-]+)",
        "quote_id": r"(PRQ-[A-Z0-9-]+)",
        "report_id": r"(RPT-[A-Z0-9-]+)",
        "ticket": r"(CFG-[A-Z0-9-]+)",
        "workflow_handle": r"(WFH-[A-Z0-9-]+)",
    }
    for key, pattern in patterns.items():
        match = _re.search(pattern, text, _re.I)
        if match:
            value = match.group(1)
            hints[key] = value
            role_key = _commit_receipt_role_hint(key, value)
            if key == "commit_receipt" and role_key:
                hints.setdefault(role_key, value)
    return hints


def _is_live_lineage_hint_value(kind: str, value: Any) -> bool:
    if kind in _FAMILY_SENSITIVE_LINEAGE_KINDS:
        if not isinstance(value, str):
            return False
        text = str(value or "").strip()
        if not text or _is_placeholder_replay_value(text):
            return False
        if kind == "reservation_id":
            return bool(_re.match(r"^(?:RESV-|[A-Za-z]+-resv-)", text, _re.I))
        if kind == "preview_ticket":
            return bool(_re.match(r"^[A-Za-z]+-preview-", text, _re.I))
        if kind == "fee_quote_id":
            return bool(_re.match(r"^[A-Za-z]+-fee-", text, _re.I))
        if kind == "hold_token":
            return bool(_re.match(r"^[A-Za-z]+-hold-", text, _re.I))
        if kind == "commit_receipt":
            return bool(_re.match(r"^[A-Za-z]+-(?:commit|branch-replay)-", text, _re.I))
        if kind == "primary_commit_receipt":
            return bool(_re.match(r"^[A-Za-z]+-commit-", text, _re.I))
        if kind == "replay_commit_receipt":
            return bool(_re.match(r"^[A-Za-z]+-branch-replay-", text, _re.I))
        if kind == "attestation_packet":
            return bool(_re.match(r"^sp-att-[A-Za-z0-9-]+(?:-packet)?$", text, _re.I))
        if kind == "stale_attestation_token":
            return bool(_re.match(r"^sp-att-stale-[A-Za-z0-9-]+$", text, _re.I))
        if kind == "stale_reason":
            return bool(_re.match(r"^freshness_gap\|epoch=\d+\|packet=sp-att-[A-Za-z0-9-]+(?:-packet)?$", text, _re.I))
        if kind == "invoice_stage_id":
            return bool(_re.match(r"^sp-invoice-stage-[A-Za-z0-9-]+$", text, _re.I))
        if kind == "entitlement_stage_id":
            return bool(_re.match(r"^sp-entitlement-stage-[A-Za-z0-9-]+$", text, _re.I))
        if kind == "confirmation_id":
            return bool(_re.match(r"^sp-confirm-[A-Za-z0-9-]+$", text, _re.I))
        if kind == "quote_id":
            return bool(_re.match(r"^PRQ-", text, _re.I))
        if kind == "report_id":
            return bool(_re.match(r"^RPT-", text, _re.I))
        if kind == "ticket":
            return bool(
                _re.match(r"^CFG-", text, _re.I)
                or _re.match(r"^[A-Za-z0-9_-]+(?:\|[A-Za-z0-9_-]+=[^|]+){1,}$", text)
            )
        if kind in {"trusted_branch_id", "rejected_branch_id"}:
            return bool(_re.match(r"^sp-branch-[A-Za-z0-9]+$", text, _re.I))
        if kind == "workflow_handle":
            return bool(_re.match(r"^WFH-", text, _re.I))
        if kind == "auth_token":
            return bool(
                _re.match(r"^(?:sp-operator-[A-Za-z0-9-]+|[A-Fa-f0-9]{6,32})$", text, _re.I)
            )
        return (
            _observed_lineage_family(text) == kind
            or _observed_lineage_family(text, description=kind.replace("_", " ")) == kind
        )
    if kind == "attestation_epoch":
        return isinstance(value, int) and not isinstance(value, bool) and value >= 20250000
    if kind in {"nonce", "handle", "blob_token"}:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
    return value not in (None, "")


def _collect_live_lineage_hints(working_call: dict[str, Any], result_text: str) -> dict[str, Any]:
    promoted: dict[str, Any] = {}
    combined = dict(_structured_target_hints(working_call))
    combined.update(_extract_inline_lineage_hints(result_text))
    for kind, value in combined.items():
        if _is_live_lineage_hint_value(kind, value):
            promoted[kind] = value
    return promoted


def _consumer_ready_lineage_hints(
    args: dict[str, Any],
    *,
    fresh_lineage: bool,
) -> dict[str, Any]:
    hints = dict(_structured_target_hints(args))
    if not fresh_lineage:
        return hints
    return {
        kind: value
        for kind, value in hints.items()
        if kind not in _FAMILY_SENSITIVE_LINEAGE_KINDS
        or _is_live_lineage_hint_value(kind, value)
    }


def _consume_retryable_blocked_prereq(
    blocked_prereqs: dict[str, int],
    prereq_name: str,
    *,
    hint_generation: int,
) -> bool:
    current_generation = blocked_prereqs.get(prereq_name)
    if current_generation is None:
        return False
    if current_generation >= hint_generation:
        return False
    removed_generation = blocked_prereqs.pop(prereq_name, None)
    return removed_generation is not None


def _is_rehydratable_success_finding(finding: dict[str, Any]) -> bool:
    if not isinstance(finding, dict):
        return False
    if not isinstance(finding.get("working_call"), dict):
        return False
    reusable_truth_eligible = finding.get("reusable_truth_eligible")
    if reusable_truth_eligible is False:
        return False
    status = str(finding.get("status_canonical") or finding.get("status") or "")
    if status not in FINDING_VERIFIED_STATUSES:
        return False
    verification = str(finding.get("verification") or "").strip().lower()
    if verification == "state_drift":
        return False
    return True


def _build_direct_target_truth(
    function_name: str,
    working_call: dict[str, Any] | None,
    *,
    source: str,
    phase: str,
    result_text: str = "",
    verification: str = "",
) -> dict[str, Any]:
    truth: dict[str, Any] = {
        "function": str(function_name or "").strip(),
        "source": str(source or "").strip(),
        "phase": str(phase or "").strip(),
    }
    if isinstance(working_call, dict):
        truth["working_call"] = dict(working_call)
    return_value = _parse_runtime_return_value(result_text or "")
    if return_value is not None:
        truth["return_value"] = int(return_value)
    if verification:
        truth["verification"] = str(verification or "").strip()
    elif return_value == 0:
        truth["verification"] = "verified"
    return truth


def _assess_prerequisite_replay_admission(
    prereq_name: str,
    merged_success: dict[str, Any],
    prereq_inv: dict[str, Any] | None,
) -> dict[str, Any]:
    candidate = {
        "function": prereq_name,
        "status": "verified_success",
        "working_call": dict(merged_success or {}),
    }
    truth_assessment = assess_reusable_truth(candidate, invocable=prereq_inv)
    admitted = bool(truth_assessment.get("seed_eligible"))
    reasons = [str(reason) for reason in list(truth_assessment.get("reasons") or []) if str(reason).strip()]
    status = "verified_success" if admitted else "inferred_success"
    if not reasons and not admitted:
        reasons = ["low_expected_observed_alignment"]
    return {
        "admitted": admitted,
        "status": status,
        "truth_assessment": truth_assessment,
        "reasons": reasons,
    }


def _expected_live_output_families(inv: dict) -> set[str]:
    expected: set[str] = set()
    for idx, param in enumerate(inv.get("parameters") or []):
        if not isinstance(param, dict):
            continue
        if not _is_effective_output_param(inv, param, idx):
            continue
        kind = _semantic_arg_kind(
            str(param.get("name") or ""),
            None,
            str(param.get("json_type") or ""),
            str(param.get("description") or param.get("type") or ""),
        )
        if kind in (_FAMILY_SENSITIVE_LINEAGE_KINDS | {"nonce", "attestation_epoch", "handle", "blob_token"}):
            expected.add(kind)
    return expected


def _allow_seeded_external_success_for_fresh_lineage(
    prereq_name: str,
    *,
    runtime_prereqs: Collection[str],
    seeded_external_successes: Collection[str],
    fresh_replayed_successes: Collection[str],
    trusted_checkpoint_seed_successes: Collection[str],
) -> bool:
    if prereq_name not in seeded_external_successes:
        return True
    if prereq_name in fresh_replayed_successes:
        return True
    return prereq_name in runtime_prereqs and prereq_name in trusted_checkpoint_seed_successes


def _align_prerequisite_args(
    prereq_inv: dict,
    args: dict[str, Any],
    hints: dict[str, Any],
    vocab: dict[str, Any] | None = None,
    admission_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    aligned = {}
    function_doc = str(prereq_inv.get("doc_comment") or prereq_inv.get("doc") or "")
    fn_lower = str(prereq_inv.get("name") or "").lower()
    params = [param for param in (prereq_inv.get("parameters") or []) if isinstance(param, dict)]
    canonical_args = _canonical_args_from_doc(function_doc)
    vocab = dict(vocab or {})
    admission_trace = admission_trace if admission_trace is not None else {}

    def _looks_customer_like(value: Any) -> bool:
        upper = str(value or "").upper()
        return any(tok in upper for tok in ("CUST-", "ACCOUNT-", "CLIENT-", "USER-", "ACCT-"))

    def _looks_sku_like(value: Any) -> bool:
        upper = str(value or "").upper()
        return any(tok in upper for tok in ("WDG-", "GDG-", "PRO-", "ITEM-", "SW-", "ACC-"))

    def _semantic_kind_for_param(param: dict) -> str | None:
        return _semantic_arg_kind(
            str(param.get("name") or ""),
            None,
            str(param.get("json_type") or ""),
            str(param.get("description") or param.get("type") or ""),
        )

    def _semantic_default_value(param: dict, kind: str | None) -> Any:
        pname = str(param.get("name") or "")
        pdesc = str(param.get("description") or param.get("type") or "")
        effective_type = str(param.get("json_type") or "")
        if kind in {
            "auth_token",
            "sku",
            "customer_id",
            "reservation_id",
            "preview_ticket",
            "fee_quote_id",
            "quote_id",
            "report_id",
            "ticket",
            "workflow_handle",
            "commit_receipt",
            "primary_commit_receipt",
            "replay_commit_receipt",
            "attestation_packet",
            "stale_attestation_token",
            "stale_reason",
            "invoice_stage_id",
            "entitlement_stage_id",
            "confirmation_id",
        }:
            effective_type = "string"
        elif kind in {"quantity", "hold_minutes", "buffer_size", "nonce", "attestation_epoch", "handle", "blob_token"}:
            effective_type = "integer"
        return _default_scalar_value(pname, effective_type, pdesc, vocab)

    def _is_semantically_compatible(kind: str | None, value: Any) -> bool:
        if kind is None:
            return value is not None
        if kind in _FAMILY_SENSITIVE_LINEAGE_KINDS and _is_placeholder_replay_value(value):
            return False
        if kind == "sku":
            return (
                isinstance(value, str)
                and bool(str(value).strip())
                and not _looks_customer_like(value)
                and (
                    _looks_sku_like(value)
                    or _observed_lineage_family(value, description="sku") == "sku"
                )
            )
        if kind == "customer_id":
            return (
                isinstance(value, str)
                and bool(str(value).strip())
                and not _looks_sku_like(value)
                and (
                    _looks_customer_like(value)
                    or _observed_lineage_family(value, description="customer id") == "customer_id"
                )
            )
        if kind in {
            "reservation_id",
            "preview_ticket",
            "fee_quote_id",
            "commit_receipt",
            "primary_commit_receipt",
            "replay_commit_receipt",
            "quote_id",
            "report_id",
            "ticket",
            "workflow_handle",
            "attestation_packet",
            "stale_attestation_token",
            "stale_reason",
            "invoice_stage_id",
            "entitlement_stage_id",
            "confirmation_id",
        }:
            return (
                isinstance(value, str)
                and bool(str(value).strip())
                and _is_live_lineage_hint_value(kind, value)
            )
        if kind == "auth_token":
            return (
                isinstance(value, str)
                and bool(str(value).strip())
                and bool(
                    _re.match(
                        r"^(?:sp-operator-[A-Za-z0-9-]+|[A-Fa-f0-9]{6,32})$",
                        str(value).strip(),
                        _re.I,
                    )
                )
            )
        if kind == "buffer_size":
            return isinstance(value, int) and not isinstance(value, bool) and value >= 24
        if kind == "attestation_epoch":
            return isinstance(value, int) and not isinstance(value, bool) and value >= 20250000
        if kind in {"quantity", "hold_minutes", "nonce", "handle", "blob_token"}:
            return isinstance(value, int) and not isinstance(value, bool) and value > 0
        return value is not None

    canonical_by_kind: dict[str, tuple[str, Any]] = {}
    for ckey, cvalue in canonical_args.items():
        ckind = _semantic_arg_kind(str(ckey or ""), cvalue)
        if ckind and ckind not in canonical_by_kind:
            canonical_by_kind[ckind] = (ckey, cvalue)

    for param in params:
        pname = str(param.get("name") or "")
        if not pname:
            continue
        lowered = pname.lower()
        lowered_desc = (
            f"{pname} "
            f"{param.get('description') or ''} "
            f"{param.get('resolved_type') or param.get('type') or ''}"
        ).lower()
        pkind = _semantic_kind_for_param(param)
        if (
            pkind == "handle"
            and (
                lowered.startswith("lpsz")
                or "char" in str(param.get("resolved_type") or param.get("type") or "").lower()
                or "workflow handle" in str(param.get("description") or "").lower()
            )
        ):
            pkind = "workflow_handle"
        trace_entry = {
            "expected_family": pkind,
            "candidate_family": None,
            "source_lineage": None,
            "admission_decision": None,
            "blocked_candidate_family": None,
            "placeholder_detected": False,
        }
        if pname in canonical_args:
            aligned[pname] = canonical_args[pname]
            trace_entry["source_lineage"] = "canonical_args"
            trace_entry["admission_decision"] = "seeded_from_canonical_args"
        elif pkind and pkind in canonical_by_kind:
            _ckey, cvalue = canonical_by_kind[pkind]
            aligned[pname] = cvalue
            trace_entry["source_lineage"] = f"canonical_args.{pkind}"
            trace_entry["admission_decision"] = "seeded_from_canonical_family"
        elif pname in (args or {}):
            aligned[pname] = args[pname]
            trace_entry["source_lineage"] = "existing_args"
            trace_entry["admission_decision"] = "preserved_existing_args"
        _initial_value = aligned.get(pname)
        _initial_family = _observed_lineage_family(
            _initial_value,
            name=pname,
            json_type=str(param.get("json_type") or ""),
            description=str(param.get("description") or param.get("type") or ""),
        )
        trace_entry["placeholder_detected"] = _is_placeholder_replay_value(_initial_value)
        if ("cust" in lowered or "customer" in lowered or "account" in lowered) and "customer_id" in hints:
            aligned[pname] = hints["customer_id"]
            trace_entry["source_lineage"] = "lineage_hint.customer_id"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif ("sku" in lowered or "product" in lowered or "item" in lowered) and "sku" in hints:
            aligned[pname] = hints["sku"]
            trace_entry["source_lineage"] = "lineage_hint.sku"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif ("reserv" in lowered or "resv" in lowered) and "reservation_id" in hints:
            aligned[pname] = hints["reservation_id"]
            trace_entry["source_lineage"] = "lineage_hint.reservation_id"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "preview" in lowered and "ticket" in lowered and "preview_ticket" in hints:
            aligned[pname] = hints["preview_ticket"]
            trace_entry["source_lineage"] = "lineage_hint.preview_ticket"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif (
            "fee" in lowered
            and "quote" in lowered
            and "id" in lowered
            and "fee_quote_id" in hints
        ):
            aligned[pname] = hints["fee_quote_id"]
            trace_entry["source_lineage"] = "lineage_hint.fee_quote_id"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "quote" in lowered and "id" in lowered and "quote_id" in hints:
            aligned[pname] = hints["quote_id"]
            trace_entry["source_lineage"] = "lineage_hint.quote_id"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "primary_commit_receipt" in hints and _semantic_kind_for_param(param) == "primary_commit_receipt":
            aligned[pname] = hints["primary_commit_receipt"]
            trace_entry["source_lineage"] = "lineage_hint.primary_commit_receipt"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "replay_commit_receipt" in hints and _semantic_kind_for_param(param) == "replay_commit_receipt":
            aligned[pname] = hints["replay_commit_receipt"]
            trace_entry["source_lineage"] = "lineage_hint.replay_commit_receipt"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "commit_receipt" in lowered and "commit_receipt" in hints:
            aligned[pname] = hints["commit_receipt"]
            trace_entry["source_lineage"] = "lineage_hint.commit_receipt"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "report" in lowered and "id" in lowered and "report_id" in hints:
            aligned[pname] = hints["report_id"]
            trace_entry["source_lineage"] = "lineage_hint.report_id"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "ticket" in lowered and "ticket" in hints:
            aligned[pname] = hints["ticket"]
            trace_entry["source_lineage"] = "lineage_hint.ticket"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "nonce" in lowered and "nonce" in hints:
            aligned[pname] = hints["nonce"]
            trace_entry["source_lineage"] = "lineage_hint.nonce"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "attestation" in lowered and "epoch" in lowered and "attestation_epoch" in hints:
            aligned[pname] = hints["attestation_epoch"]
            trace_entry["source_lineage"] = "lineage_hint.attestation_epoch"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "blob" in lowered and "token" in lowered and "blob_token" in hints:
            aligned[pname] = hints["blob_token"]
            trace_entry["source_lineage"] = "lineage_hint.blob_token"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "attestation" in lowered and "packet" in lowered and "attestation_packet" in hints:
            aligned[pname] = hints["attestation_packet"]
            trace_entry["source_lineage"] = "lineage_hint.attestation_packet"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "stale" in lowered and "attestation" in lowered and "token" in lowered and "stale_attestation_token" in hints:
            aligned[pname] = hints["stale_attestation_token"]
            trace_entry["source_lineage"] = "lineage_hint.stale_attestation_token"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "stale" in lowered and "reason" in lowered and "stale_reason" in hints:
            aligned[pname] = hints["stale_reason"]
            trace_entry["source_lineage"] = "lineage_hint.stale_reason"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "invoice" in lowered and "stage" in lowered and "id" in lowered and "invoice_stage_id" in hints:
            aligned[pname] = hints["invoice_stage_id"]
            trace_entry["source_lineage"] = "lineage_hint.invoice_stage_id"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "entitlement" in lowered and "stage" in lowered and "id" in lowered and "entitlement_stage_id" in hints:
            aligned[pname] = hints["entitlement_stage_id"]
            trace_entry["source_lineage"] = "lineage_hint.entitlement_stage_id"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif "confirmation" in lowered and "id" in lowered and "confirmation_id" in hints:
            aligned[pname] = hints["confirmation_id"]
            trace_entry["source_lineage"] = "lineage_hint.confirmation_id"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif any(tok in lowered for tok in ("token", "auth")) and "auth_token" in hints:
            aligned[pname] = hints["auth_token"]
            trace_entry["source_lineage"] = "lineage_hint.auth_token"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif (
            "handle" in lowered_desc
            and "workflow_handle" in hints
            and (
                str(param.get("json_type") or "").lower() not in {"integer", "number"}
                or lowered.startswith("lpsz")
                or "char" in str(param.get("resolved_type") or param.get("type") or "").lower()
                or "workflow handle" in str(param.get("description") or "").lower()
            )
        ):
            aligned[pname] = hints["workflow_handle"]
            trace_entry["source_lineage"] = "lineage_hint.workflow_handle"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif ("handle" in lowered_desc or "session" in lowered_desc) and "handle" in hints:
            aligned[pname] = hints["handle"]
            trace_entry["source_lineage"] = "lineage_hint.handle"
            trace_entry["admission_decision"] = "admitted_same_family_hint"
        elif (
            "customer_id" in hints
            and "bind" in fn_lower
            and "customer" in fn_lower
            and len(params) == 1
            and (
                lowered.startswith("param_")
                or (
                    str(param.get("json_type") or "").lower() in {"integer", "number"}
                    and "char" in str(param.get("resolved_type") or param.get("type") or "").lower()
                )
            )
        ):
            aligned[pname] = hints["customer_id"]
            trace_entry["source_lineage"] = "lineage_hint.customer_id"
            trace_entry["admission_decision"] = "admitted_bind_customer_hint"
        elif (
            "bind" in fn_lower
            and "customer" in fn_lower
            and len(params) == 1
            and (
                pname not in aligned
                or not isinstance(aligned.get(pname), str)
                or not str(aligned.get(pname) or "").upper().startswith(("CUST-", "ACCOUNT-", "CLIENT-", "ACCT-", "USER-", "USR-"))
            )
            and (
                lowered.startswith("param_")
                or "char" in str(param.get("resolved_type") or param.get("type") or "").lower()
                or "customer" in str(param.get("description") or "").lower()
            )
        ):
            aligned[pname] = _default_scalar_value("customer_id", "string", "customer", vocab)
            trace_entry["source_lineage"] = "semantic_default.customer_id"
            trace_entry["admission_decision"] = "seeded_bind_customer_default"
        current_value = aligned.get(pname)
        current_family = _observed_lineage_family(
            current_value,
            name=pname,
            json_type=str(param.get("json_type") or ""),
            description=str(param.get("description") or param.get("type") or ""),
        )
        trace_entry["candidate_family"] = current_family
        if (
            pkind in _FAMILY_SENSITIVE_LINEAGE_KINDS
            and _initial_family
            and _initial_family != pkind
            and trace_entry["source_lineage"]
            and str(trace_entry["source_lineage"]).startswith("lineage_hint.")
        ):
            trace_entry["blocked_candidate_family"] = _initial_family
            trace_entry["admission_decision"] = "admitted_same_family_hint_after_block"
        if pkind and not _is_semantically_compatible(pkind, current_value):
            if (
                pkind in _FAMILY_SENSITIVE_LINEAGE_KINDS
                and current_value is not None
                and current_family
                and current_family != pkind
            ):
                trace_entry["admission_decision"] = "blocked_foreign_family_existing"
            if pkind in hints and _is_semantically_compatible(pkind, hints[pkind]):
                aligned[pname] = hints[pkind]
                trace_entry["candidate_family"] = _observed_lineage_family(
                    hints[pkind],
                    name=pname,
                    json_type=str(param.get("json_type") or ""),
                    description=str(param.get("description") or param.get("type") or ""),
                )
                trace_entry["source_lineage"] = f"lineage_hint.{pkind}"
                trace_entry["admission_decision"] = "admitted_same_family_hint_after_block"
            else:
                aligned[pname] = _semantic_default_value(param, pkind)
                trace_entry["candidate_family"] = _observed_lineage_family(
                    aligned[pname],
                    name=pname,
                    json_type=str(param.get("json_type") or ""),
                    description=str(param.get("description") or param.get("type") or ""),
                )
                trace_entry["source_lineage"] = f"semantic_default.{pkind or 'generic'}"
                trace_entry["admission_decision"] = "defaulted_after_incompatible_value"
        admission_trace[pname] = trace_entry

    return aligned


def _augment_structured_probe_args_for_mixed_calls(
    inv: dict,
    args: dict[str, Any],
    selection: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    augmented_args = dict(args or {})
    augmented_selection = dict(selection or {})
    for param in (inv.get("parameters") or []):
        if not isinstance(param, dict):
            continue
        if not _is_true_output_param(param):
            continue
        pname = str(param.get("name") or "")
        if not pname or pname in augmented_args:
            continue
        if str(param.get("json_type") or "").lower() not in {"integer", "number", "boolean"}:
            continue
        augmented_args[pname] = ""
        augmented_selection[pname] = {
            "source": "structured.out_slot",
            "reason": "explicit allocated placeholder for mixed struct-plus-output call",
            "score": 0.84,
            "rank": 1,
            "candidate_count": 1,
        }
    return augmented_args, augmented_selection


def _looks_runtime_output_buffer_param(inv: dict, param: dict, index: int) -> bool:
    raw_type = str(param.get("resolved_type") or param.get("type") or "").lower()
    if "*" not in raw_type and not any(tok in raw_type for tok in ("lpstr", "lpcstr", "lpwstr", "lpcwstr")):
        return False
    is_text_ptr = any(tok in raw_type for tok in (
        "char *",
        "char*",
        "wchar",
        "lpstr",
        "lpcstr",
        "lpwstr",
        "lpcwstr",
        "byte *",
        "byte*",
        "uchar *",
        "uchar*",
    ))
    if not is_text_ptr:
        return False
    fn_lower = str(inv.get("name") or "").lower()
    desc_lower = str(param.get("description") or "").lower()
    if "output" in desc_lower or "buffer" in desc_lower:
        return True
    params = [p for p in (inv.get("parameters") or []) if isinstance(p, dict)]
    next_param = params[index + 1] if index + 1 < len(params) else {}
    next_type = str(next_param.get("resolved_type") or next_param.get("type") or "").lower()
    next_name = str(next_param.get("name") or "").lower()
    has_size_follower = any(tok in next_type for tok in ("int", "uint", "dword", "size_t", "long")) or any(
        tok in next_name for tok in ("size", "len", "count", "capacity")
    )
    if not has_size_follower:
        return False
    param_name = str(param.get("name") or "").lower()
    if param_name.startswith("pout") or param_name.startswith("out_"):
        return True
    return bool(_re.search(r"version|string|name|path|directory|filename|error|message|text|label", fn_lower))


def _doc_string_prefix_hint(function_doc: str, param_name: str) -> str | None:
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


def _doc_string_default_hint(function_doc: str, param_name: str) -> str | None:
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


def _is_effective_output_param(inv: dict, param: dict, index: int) -> bool:
    return _is_true_output_param(param) or _looks_runtime_output_buffer_param(inv, param, index)


def _retag_runtime_probe_roles(inv: dict) -> None:
    params = [p for p in (inv.get("parameters") or []) if isinstance(p, dict)]
    if not params:
        return
    fn_lower = str(inv.get("name") or "").lower()
    doc_lower = str(inv.get("doc_comment") or inv.get("doc") or "").lower()
    execution = inv.get("execution") if isinstance(inv.get("execution"), dict) else None
    arg_types = execution.get("arg_types") if isinstance(execution, dict) and isinstance(execution.get("arg_types"), list) else None

    for idx, param in enumerate(params):
        raw_type = str(param.get("resolved_type") or param.get("type") or "").lower()
        pname = str(param.get("name") or f"param_{idx + 1}")
        if idx == 0 and "*" in raw_type and not any(tok in raw_type for tok in ("char", "wchar", "byte", "uchar")):
            reads_like_consumer = bool(
                _re.search(rf"\*{_re.escape(pname.lower())}\b", doc_lower)
                or _re.search(rf"{_re.escape(pname.lower())}\s*(==|!=)", doc_lower)
                or _re.search(rf"{_re.escape(pname.lower())}\s*\+", doc_lower)
            )
            if reads_like_consumer and not _re.search(r"(create|new|open|init|alloc)", fn_lower):
                param["direction"] = "in"
                param["json_type"] = "integer"
                desc = str(param.get("description") or param.get("type") or "").strip()
                if "opaque handle" not in desc.lower():
                    param["description"] = (
                        f"{desc} opaque runtime handle input from a prior create/open/init call"
                    ).strip()
        if (
            idx > 0
            and "putsamples" in fn_lower
            and "*" in raw_type
            and any(tok in raw_type for tok in ("float", "double", "short", "int16", "word", "int", "uint"))
        ):
            if "i16" in fn_lower and any(tok in raw_type for tok in ("float", "double")):
                param["type"] = "short *"
                param["resolved_type"] = "short *"
                param["json_type"] = "integer"
                raw_type = "short *"
                if arg_types is not None and idx < len(arg_types):
                    arg_types[idx] = "short *"
            param["direction"] = "in"
            desc = str(param.get("description") or param.get("type") or "").strip()
            if "input sample payload" not in desc.lower():
                param["description"] = (f"{desc} input sample payload buffer").strip()
        if _looks_runtime_output_buffer_param(inv, param, idx):
            param["direction"] = "out"
            param["json_type"] = "string"
            desc = str(param.get("description") or param.get("type") or "").strip()
            if "output text buffer" not in desc.lower():
                param["description"] = (f"{desc} output text buffer").strip()
            if idx + 1 < len(params):
                next_param = params[idx + 1]
                next_param["direction"] = "in"
                next_param["json_type"] = "integer"
                next_desc = str(next_param.get("description") or next_param.get("type") or "").strip()
                if "buffer size" not in next_desc.lower():
                    next_param["description"] = (f"{next_desc} output buffer size").strip()
            continue
        if (
            "*" in raw_type
            and any(tok in raw_type for tok in ("char", "wchar", "lpstr", "lpcstr", "lpwstr", "lpcwstr", "byte", "uchar"))
            and str(param.get("direction") or "").strip().lower() != "out"
        ):
            param["direction"] = "in"
            param["json_type"] = "string"
            desc = str(param.get("description") or param.get("type") or "").strip()
            annotations: list[str] = []
            prefix_hint = _doc_string_prefix_hint(str(inv.get("doc_comment") or inv.get("doc") or ""), pname)
            default_hint = _doc_string_default_hint(str(inv.get("doc_comment") or inv.get("doc") or ""), pname)
            if prefix_hint:
                annotations.append(f'must start with "{prefix_hint}"')
            if default_hint:
                annotations.append(f'empty string defaults to "{default_hint}"')
            if "input text" not in desc.lower():
                desc = (f"{desc} input text parameter").strip()
            if annotations:
                suffix = "; ".join(annotations)
                if suffix.lower() not in desc.lower():
                    desc = f"{desc} ({suffix})".strip()
            param["description"] = desc


def _parse_runtime_return_value(result_text: str) -> int | None:
    match = _re.search(r"Returned:\s*(-?\d+)", str(result_text or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _is_runtime_success_value(inv: dict, fn_name: str, result_text: str, sentinels: dict[int, str], is_version_fn: bool) -> bool:
    ret_val = _parse_runtime_return_value(result_text)
    if ret_val is None:
        return False
    if ret_val == 0:
        return True
    if is_version_fn and ret_val > 0 and (ret_val & 0xFFFFFFFF) not in sentinels:
        return True
    _is_creator = bool(_re.search(r"(create|new|open|init|alloc|session|handle)", fn_name, _re.I))
    ret_type = str(inv.get("return_type") or (inv.get("execution") or {}).get("return_type") or "").lower()
    if (
        ret_val > 1
        and (_is_creator and (not (inv.get("parameters") or [])) or "*" in ret_type)
        and (ret_val & 0xFFFFFFFF) not in sentinels
        and _is_creator
    ):
        return True
    return False


def _runtime_return_artifacts(inv: dict, fn_name: str, result_text: str, sentinels: dict[int, str]) -> dict[str, Any]:
    ret_val = _parse_runtime_return_value(result_text)
    if ret_val is None:
        return {}
    _is_creator = bool(_re.search(r"(create|new|open|init|alloc|session|handle)", fn_name, _re.I))
    ret_type = str(inv.get("return_type") or (inv.get("execution") or {}).get("return_type") or "").lower()
    if (
        ret_val > 1
        and (_is_creator and (not (inv.get("parameters") or [])) or "*" in ret_type)
        and (ret_val & 0xFFFFFFFF) not in sentinels
        and _is_creator
    ):
        return {"handle": ret_val}
    return {}


def _merge_runtime_success_values(
    inv: dict,
    fn_name: str,
    args: dict[str, Any],
    result_text: str,
    p_lookup: dict[str, dict],
    sentinels: dict[int, str],
) -> dict[str, Any]:
    merged = _merge_result_output_values(args, result_text, p_lookup)
    merged.update(_runtime_return_artifacts(inv, fn_name, result_text, sentinels))
    return merged


def _normalize_true_output_scalar_args(
    inv: dict,
    args: dict[str, Any],
    selection: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_args = dict(args or {})
    normalized_selection = dict(selection or {})
    params = [param for param in (inv.get("parameters") or []) if isinstance(param, dict)]
    has_output_buffer = any(
        _is_effective_output_param(inv, param, idx)
        and str(param.get("json_type") or "").lower() not in {"integer", "number", "boolean"}
        for idx, param in enumerate(params)
    )
    for idx, param in enumerate(inv.get("parameters") or []):
        if not isinstance(param, dict):
            continue
        if not _is_effective_output_param(inv, param, idx):
            continue
        pname = str(param.get("name") or "")
        if not pname:
            continue
        current = normalized_args.get(pname)
        if isinstance(current, dict):
            continue
        if current == "":
            continue
        normalized_args[pname] = ""
        normalized_selection[pname] = {
            "source": "output.bridge_slot",
            "reason": "normalized true output parameter to allocated bridge slot",
            "score": 0.86,
            "rank": 1,
            "candidate_count": 1,
        }
    if has_output_buffer:
        for param in params:
            pname = str(param.get("name") or "")
            if not pname:
                continue
            kind = _semantic_arg_kind(
                pname,
                normalized_args.get(pname),
                str(param.get("json_type") or ""),
                str(param.get("description") or param.get("type") or ""),
            )
            if kind != "buffer_size" and _re.search(r"(?:^|_)(len|size|count|capacity)(?:_|$)", pname.lower()):
                kind = "buffer_size"
            if kind != "buffer_size":
                continue
            current = normalized_args.get(pname)
            if isinstance(current, int) and not isinstance(current, bool) and current >= 24:
                continue
            normalized_args[pname] = 64
            normalized_selection[pname] = {
                "source": "output.buffer_size_default",
                "reason": "ensured minimum buffer size for output-buffer call",
                "score": 0.9,
                "rank": 1,
                "candidate_count": 1,
            }
            break
    return normalized_args, normalized_selection


def _repair_target_structured_args(
    inv: dict,
    args: dict[str, Any],
    selection: dict[str, Any],
    structured_args: dict[str, Any],
    structured_selection: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    repaired_args = dict(args or {})
    repaired_selection = dict(selection or {})
    if not structured_args:
        return repaired_args, repaired_selection
    for param in (inv.get("parameters") or []):
        if not isinstance(param, dict):
            continue
        pname = str(param.get("name") or "")
        scaffold_value = structured_args.get(pname)
        if not isinstance(scaffold_value, dict):
            continue
        if not isinstance(repaired_args.get(pname), dict):
            repaired_args[pname] = dict(scaffold_value)
            repaired_selection[pname] = dict(
                structured_selection.get(pname) or {
                    "source": "structured.scaffolder",
                    "reason": "repaired object slot from available struct scaffold",
                    "score": 0.82,
                    "rank": 1,
                    "candidate_count": 1,
                }
            )
    repaired_args, repaired_selection = _augment_structured_probe_args_for_mixed_calls(
        inv,
        repaired_args,
        repaired_selection,
    )
    return _normalize_true_output_scalar_args(inv, repaired_args, repaired_selection)


def _repair_target_input_aliases(
    inv: dict,
    args: dict[str, Any],
    selection: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    repaired_args = dict(args or {})
    repaired_selection = dict(selection or {})
    params = [p for p in (inv.get("parameters") or []) if isinstance(p, dict)]
    canonical = {
        str(p.get("name") or ""): p
        for p in params
        if str(p.get("name") or "")
    }
    if not canonical:
        return repaired_args, repaired_selection

    def _norm(name: str) -> str:
        lowered = _re.sub(r"[^a-z0-9]", "", str(name or "").lower())
        if lowered.startswith("p") and len(lowered) > 3:
            lowered = lowered[1:]
        if lowered.endswith("out") and len(lowered) > 3:
            lowered = lowered[:-3]
        return lowered

    canonical_norm = {}
    for pname in canonical:
        canonical_norm.setdefault(_norm(pname), []).append(pname)

    for key in list(repaired_args.keys()):
        if key in canonical:
            continue
        matches = canonical_norm.get(_norm(key), [])
        if len(matches) != 1:
            continue
        target = matches[0]
        if target in repaired_args:
            continue
        repaired_args[target] = repaired_args.pop(key)
        meta = dict(repaired_selection.pop(key, {}) or {})
        meta.setdefault("source", "arg.alias_repair")
        meta["reason"] = f"remapped near-match arg '{key}' to canonical '{target}'"
        repaired_selection[target] = meta
    return repaired_args, repaired_selection


def _repair_target_scalar_args(
    inv: dict,
    args: dict[str, Any],
    selection: dict[str, Any],
    vocab: dict[str, Any],
    evidence,
    lineage_hints: dict[str, Any] | None = None,
    prefer_lineage: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    repaired_args, repaired_selection = _repair_target_input_aliases(inv, args, selection)
    lineage_hints = dict(lineage_hints or {})
    protected_numeric_slots: set[str] = set()

    params = [p for p in (inv.get("parameters") or []) if isinstance(p, dict)]
    canonical_args = _canonical_args_from_doc(str(inv.get("doc_comment") or inv.get("doc") or ""))
    canonical_numeric_by_kind: dict[str, int] = {}
    canonical_string_by_kind: dict[str, str] = {}
    for ckey, cvalue in canonical_args.items():
        ckind = _semantic_arg_kind(str(ckey or ""), cvalue)
        if ckind in {"quantity", "hold_minutes", "buffer_size"} and isinstance(cvalue, int) and not isinstance(cvalue, bool):
            canonical_numeric_by_kind[ckind] = cvalue
        if isinstance(cvalue, str) and cvalue and ckind and not _is_placeholder_replay_value(cvalue):
            canonical_string_by_kind.setdefault(ckind, cvalue)

    def _semantic_numeric_default(kind: str, desc: str) -> int:
        if kind in canonical_numeric_by_kind:
            return canonical_numeric_by_kind[kind]
        if kind == "quantity":
            return 2
        if kind == "hold_minutes":
            return 30
        if kind == "buffer_size":
            return 64
        return int(_default_scalar_value(kind, "integer", desc, vocab))

    for idx, param in enumerate(params):
        if _is_effective_output_param(inv, param, idx):
            continue
        pname = str(param.get("name") or "")
        if not pname or pname not in repaired_args:
            continue
        jtype = str(param.get("json_type") or "string").lower()
        raw_type = str(param.get("resolved_type") or param.get("type") or "").lower()
        if "*" in raw_type or "[" in raw_type:
            continue
        current = repaired_args.get(pname)
        if isinstance(current, int) and not isinstance(current, bool):
            continue
        desc = str(param.get("description") or param.get("type") or "")
        pkind = _semantic_arg_kind(pname, None, jtype, desc)
        if pkind not in {"quantity", "hold_minutes", "buffer_size"}:
            continue
        repaired_args[pname] = _semantic_numeric_default(pkind, desc)
        repaired_selection[pname] = {
            "source": "semantic.numeric_guard",
            "reason": f"normalized incompatible {pkind} slot before target execution",
            "score": 0.88,
            "rank": 1,
            "candidate_count": 1,
        }
        protected_numeric_slots.add(pname)

    for idx, param in enumerate(params):
        if _is_effective_output_param(inv, param, idx):
            continue
        pname = str(param.get("name") or "")
        if not pname:
            continue
        current = repaired_args.get(pname)
        if isinstance(current, (dict, list, tuple, bytes, bytearray)):
            continue

        jtype = str(param.get("json_type") or "string").lower()
        desc = str(param.get("description") or param.get("type") or "")
        numeric_lineage_key = (
            _semantic_arg_kind(pname, None, jtype, desc)
            or _lineage_hint_key(pname, None, jtype, desc)
            or _lineage_hint_key(pname, current, jtype, desc)
        )
        if (
            jtype in {"integer", "number"}
            and numeric_lineage_key == "attestation_epoch"
            and "attestation_epoch" in lineage_hints
            and _is_live_lineage_hint_value("attestation_epoch", lineage_hints["attestation_epoch"])
            and (prefer_lineage or current != lineage_hints["attestation_epoch"])
        ):
            lineage_value = lineage_hints["attestation_epoch"]
            repaired_args[pname] = lineage_value
            repaired_selection[pname] = {
                "source": "lineage.same_run",
                "reason": "reused exact same-run attestation_epoch from prerequisite replay",
                "score": 100.0,
                "rank": 1,
                "candidate_count": 1,
                "candidate_family": "attestation_epoch",
                "expected_family": "attestation_epoch",
                "source_lineage": "lineage_hint.attestation_epoch",
                "admission_decision": "admitted_same_family_hint",
                "fresh_replay_required": prefer_lineage,
            }
            continue
        if jtype in {"integer", "number", "boolean"}:
            continue
        expected_family = (
            _semantic_arg_kind(pname, None, jtype, desc)
            or _lineage_hint_key(pname, None, jtype, desc)
            or _lineage_hint_key(pname, current, jtype, desc)
        )
        canonical_value = canonical_args.get(pname)
        canonical_source = "doc.canonical_args"
        if not (isinstance(canonical_value, str) and canonical_value and not _is_placeholder_replay_value(canonical_value)):
            canonical_value = canonical_string_by_kind.get(str(expected_family or ""))
            canonical_source = f"doc.canonical_args.{expected_family}" if canonical_value else canonical_source
        if not isinstance(canonical_value, str) or not canonical_value:
            continue

        candidate_family = _observed_lineage_family(
            canonical_value,
            name=pname,
            json_type=jtype,
            description=desc,
        )
        current_family = _observed_lineage_family(
            current,
            name="",
            json_type=jtype,
            description="",
        )
        if expected_family in {"primary_commit_receipt", "replay_commit_receipt"}:
            candidate_family = _commit_receipt_role_hint("", canonical_value) or candidate_family
            current_family = _commit_receipt_role_hint("", current) or current_family
        should_replace = current is None or _is_placeholder_replay_value(current)
        if not should_replace and expected_family and candidate_family == expected_family:
            should_replace = current_family != expected_family
        if (
            not should_replace
            and canonical_source == "doc.canonical_args"
            and isinstance(current, str)
            and current != canonical_value
            and candidate_family
        ):
            should_replace = current_family != candidate_family
        if not should_replace:
            continue

        repaired_args[pname] = canonical_value
        repaired_selection[pname] = {
            "source": canonical_source,
            "reason": "repaired target string slot from canonical args before probe",
            "score": 0.95,
            "rank": 1,
            "candidate_count": 1,
            "candidate_family": candidate_family,
            "expected_family": expected_family,
            "source_lineage": canonical_source,
            "admission_decision": "seeded_from_canonical_args",
        }

    if evidence is None and not lineage_hints:
        return repaired_args, repaired_selection

    string_count = sum(
        1 for idx, p in enumerate(params)
        if str(p.get("json_type") or "").lower() not in {"integer", "number", "boolean"}
        and not _is_effective_output_param(inv, p, idx)
    )
    integer_count = sum(
        1 for idx, p in enumerate(params)
        if str(p.get("json_type") or "").lower() in {"integer", "number"}
        and not _is_effective_output_param(inv, p, idx)
    )
    string_index = 0
    integer_index = 0

    for idx, param in enumerate(params):
        if _is_effective_output_param(inv, param, idx):
            continue
        pname = str(param.get("name") or "")
        if not pname:
            continue
        current = repaired_args.get(pname)
        if isinstance(current, (dict, list, tuple, bytes, bytearray)):
            continue

        jtype = str(param.get("json_type") or "string").lower()
        desc = str(param.get("description") or param.get("type") or "")
        semantic_numeric_kind = _semantic_arg_kind(pname, None, jtype, desc)
        if semantic_numeric_kind in {"quantity", "hold_minutes", "buffer_size"} and isinstance(current, int):
            jtype = "integer"
        if (
            pname in protected_numeric_slots
            and semantic_numeric_kind in {"quantity", "hold_minutes", "buffer_size"}
            and isinstance(current, int)
            and not isinstance(current, bool)
        ):
            continue
        lineage_key = (
            _semantic_arg_kind(pname, None, jtype, desc)
            or _lineage_hint_key(pname, None, jtype, desc)
            or _lineage_hint_key(pname, current, jtype, desc)
        )
        if semantic_numeric_kind in {"quantity", "hold_minutes", "buffer_size"}:
            lineage_key = semantic_numeric_kind
        if (
            lineage_key == "handle"
            and "workflow_handle" in lineage_hints
            and (
                pname.lower().startswith("lpsz")
                or "char" in str(param.get("resolved_type") or param.get("type") or "").lower()
                or "workflow handle" in desc.lower()
            )
        ):
            lineage_key = "workflow_handle"
        if lineage_key and lineage_key in lineage_hints:
            lineage_value = lineage_hints[lineage_key]
            allow_same_run_lineage = (
                lineage_key not in _FAMILY_SENSITIVE_LINEAGE_KINDS
                or _is_live_lineage_hint_value(lineage_key, lineage_value)
            )
            if allow_same_run_lineage and (prefer_lineage or current is None or current != lineage_value):
                expected_family = lineage_key
                candidate_family = _observed_lineage_family(
                    lineage_value,
                    name=pname,
                    json_type=jtype,
                    description=desc,
                )
                repaired_args[pname] = lineage_value
                repaired_selection[pname] = {
                    "source": "lineage.same_run",
                    "reason": f"reused exact same-run {lineage_key} from prerequisite replay",
                    "score": 100.0,
                    "rank": 1,
                    "candidate_count": 1,
                    "candidate_family": candidate_family,
                    "expected_family": expected_family,
                    "source_lineage": f"lineage_hint.{lineage_key}",
                    "admission_decision": "admitted_same_family_hint",
                    "fresh_replay_required": prefer_lineage,
                }
                current = lineage_value
                if prefer_lineage:
                    continue

        current_string_index = string_index
        current_integer_index = integer_index
        if jtype in {"integer", "number"}:
            integer_index += 1
        elif jtype != "boolean":
            string_index += 1

        if evidence is None:
            continue
        candidates = _ranked_param_candidates(
            pname,
            jtype,
            desc,
            vocab,
            fn_name=str(inv.get("name") or ""),
            resolved_type=str(param.get("resolved_type") or param.get("type") or ""),
            has_output_buffer=any(_is_effective_output_param(inv, p, pidx) for pidx, p in enumerate(params)),
            string_slot_index=current_string_index,
            string_slot_count=string_count,
            integer_slot_index=current_integer_index,
            integer_slot_count=integer_count,
            evidence=evidence,
            function_doc=str(inv.get("doc_comment") or inv.get("doc") or ""),
        )
        if not candidates:
            continue
        best = candidates[0]
        best_value = best.get("value")
        best_source = str(best.get("source") or "")
        context = f"{pname} {desc}".lower()
        replace = current is None

        if jtype in {"integer", "number"} and isinstance(best_value, int):
            if not isinstance(current, int) or isinstance(current, bool):
                replace = True
            elif (
                best_source.startswith("evidence.")
                and (
                    "handle" in context
                    or "session" in context
                    or "token" in context
                    or "nonce" in context
                )
                and int(current) <= 7
                and int(best_value) > 255
            ):
                replace = True
        elif jtype not in {"integer", "number", "boolean"} and isinstance(current, str) and isinstance(best_value, str):
            current_upper = current.upper()
            best_upper = best_value.upper()
            current_looks_sku = any(tok in current_upper for tok in ("WDG-", "GDG-", "PRO-", "ITEM-", "SW-", "ACC-"))
            best_looks_customer = any(tok in best_upper for tok in ("CUST-", "ACCOUNT-", "CLIENT-", "USER-", "ACCT-"))
            current_family = _lineage_hint_key("", current)
            best_family = str(best.get("candidate_family") or "")
            expected_family = str(best.get("expected_family") or _lineage_hint_key(pname, None, jtype, desc) or "")
            if (
                ("customer" in context or "account" in context or "custid" in context or "acct" in context)
                and current_looks_sku
                and best_looks_customer
            ):
                replace = True
            elif (
                expected_family
                and best_family == expected_family
                and current_family
                and current_family != expected_family
            ):
                replace = True
            elif best.get("guard_applied") and current != best_value:
                replace = True

        if not replace:
            continue

        repaired_args[pname] = best_value
        repaired_selection[pname] = {
            "source": best_source,
            "reason": str(best.get("reason") or "repaired scalar slot from ranked evidence"),
            "score": float(best.get("score") or 0.0),
            "rank": 1,
            "candidate_count": len(candidates),
        }
        for extra_key in ("candidate_family", "expected_family", "source_family", "selection_flags", "guard_applied"):
            if extra_key in best:
                repaired_selection[pname][extra_key] = best.get(extra_key)

    return repaired_args, repaired_selection


def _score_observed_success(inv: dict, args: dict[str, Any], vocab: dict[str, Any], evidence) -> float:
    score = 0.0
    params = [p for p in (inv.get("parameters") or []) if isinstance(p, dict)]
    for param in params:
        if _is_true_output_param(param):
            continue
        pname = str(param.get("name") or "")
        if pname not in args:
            continue
        value = args.get(pname)
        if isinstance(value, dict):
            score += 1.0
            continue

        jtype = str(param.get("json_type") or "string").lower()
        desc = str(param.get("description") or param.get("type") or "")
        context = f"{pname} {desc}".lower()
        candidates = _ranked_param_candidates(
            pname,
            jtype,
            desc,
            vocab,
            fn_name=str(inv.get("name") or ""),
            resolved_type=str(param.get("resolved_type") or param.get("type") or ""),
            evidence=evidence,
            function_doc=str(inv.get("doc_comment") or inv.get("doc") or ""),
        )
        rank_bonus = 0.0
        for idx, candidate in enumerate(candidates[:5]):
            if candidate.get("value") == value:
                rank_bonus = max(rank_bonus, 5.0 - idx)
                break
        score += rank_bonus

        if jtype in {"integer", "number"}:
            if isinstance(value, int) and not isinstance(value, bool):
                score += 0.75
            elif isinstance(value, str):
                score -= 3.0
            if (
                isinstance(value, int)
                and ("handle" in context or "session" in context or "token" in context or "nonce" in context)
                and value > 255
            ):
                score += 1.5
        elif isinstance(value, str):
            upper = value.upper()
            if "customer" in context or "account" in context or "custid" in context or "acct" in context:
                if any(tok in upper for tok in ("CUST-", "ACCOUNT-", "CLIENT-", "USER-", "ACCT-")):
                    score += 1.5
                if any(tok in upper for tok in ("WDG-", "GDG-", "PRO-", "ITEM-", "SW-", "ACC-")):
                    score -= 3.0
    return score


def _choose_best_observed_success(inv: dict, observed_successes: list[dict[str, Any]], vocab: dict[str, Any], evidence):
    if not observed_successes:
        return None
    scored = [
        (_score_observed_success(inv, success, vocab, evidence), idx, success)
        for idx, success in enumerate(observed_successes)
    ]
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return dict(scored[0][2])


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 3 – Per-function probe loop
# ══════════════════════════════════════════════════════════════════════════════


def _snapshot_probe_vocab(ctx: ExploreContext) -> dict[str, Any]:
    """Return a per-function stable vocab snapshot for probing."""
    vocab_snapshot = dict(ctx.vocab)
    static_ids = ((ctx.static_analysis_result or {}).get("binary_strings") or {}).get("ids_found") or []
    if static_ids:
        vocab_snapshot["binary_string_ids"] = list(static_ids)
    return vocab_snapshot


def _skip_with_status(ctx: ExploreContext, fn_name: str, message: str, add_to_explored: bool = False) -> None:
    if add_to_explored:
        with ctx._lock:
            ctx.already_explored.add(fn_name)
    explored_now = ctx.increment_explored()
    _set_explore_status(ctx.job_id, explored_now, ctx.total, message)


def _append_skip_pre_probe_log(ctx: ExploreContext, fn_name: str, reason: str, detail: str = "") -> None:
    try:
        _append_explore_probe_log(
            ctx.job_id,
            [{
                "phase": "skip_pre_probe",
                "function": fn_name,
                "args": {
                    "reason": str(reason or "").strip(),
                    "detail": str(detail or "").strip(),
                },
                "result_excerpt": str(detail or reason or "").strip(),
                "trace": None,
            }],
        )
    except Exception:
        pass


def _should_skip_probe_function(fn_name: str, ctx: ExploreContext) -> bool:
    with ctx._lock:
        if _should_skip_documented_function(fn_name, ctx):
            _append_skip_pre_probe_log(ctx, fn_name, "skip_documented", "already documented")
            _skip_with_status(ctx, fn_name, f"Skipped {fn_name} (already documented)")
            return True

    if ctx.runtime.focus_functions and fn_name not in ctx.runtime.focus_functions and not _must_probe_function(fn_name, ctx):
        _append_skip_pre_probe_log(ctx, fn_name, "skip_focus", "not in focus_functions")
        _skip_with_status(ctx, fn_name, f"Skipped {fn_name} (not in focus_functions)", add_to_explored=True)
        return True

    try:
        from api.pipeline.core.checkpoint import should_skip_function

        if should_skip_function(ctx._checkpoint, fn_name, ctx.runtime.focus_functions) and not _must_probe_function(fn_name, ctx):
            _append_skip_pre_probe_log(ctx, fn_name, "skip_checkpoint", "checkpoint already successful")
            _skip_with_status(
                ctx,
                fn_name,
                f"Skipped {fn_name} (checkpoint: already successful)",
                add_to_explored=True,
            )
            return True
    except Exception:
        pass
    return False


def _reinitialize_probe_runtime(fn_name: str, inv: dict, ctx: ExploreContext) -> None:
    # Q-5: Re-initialise DLL state before each function's probe sequence to
    # reset balance/points/etc. so probes don't fail due to state drained by
    # previous function probing.
    if not _INIT_RE.search(fn_name) and ctx.init_invocables:
        for reinit_inv in ctx.init_invocables:
            try:
                _execute_tool(reinit_inv, {})
            except Exception:
                pass

    # BUG-021 extension: replay unlock sequence after init for write functions.
    if _WRITE_FN_RE.search(fn_name) and ctx.unlock_result.get("unlocked"):
        for step in (ctx.unlock_result.get("sequence") or []):
            step_inv = ctx.inv_map.get(step.get("fn", ""))
            if step_inv:
                try:
                    _execute_tool(step_inv, step.get("args", {}))
                except Exception:
                    pass
        # Replay known-good write calls with ALL known customer IDs so
        # points/balances accrue for every entity the target might use.
        with ctx._lock:
            live_snapshot = list(ctx.live_findings)
        known_ids = set()
        if ctx.vocab and ctx.vocab.get("id_formats"):
            known_ids = {str(v) for v in ctx.vocab["id_formats"] if v}
        for finding in live_snapshot:
            finding_call = finding.get("working_call")
            if isinstance(finding_call, dict):
                for value in finding_call.values():
                    if isinstance(value, str) and _re.match(r"^[A-Z]+-", value):
                        known_ids.add(value)
        known_ids_list = sorted(known_ids)[:4] or ["CUST-001"]

        prereq_call_budget = 12
        prereq_calls_made = 0
        for finding in live_snapshot:
            if prereq_calls_made >= prereq_call_budget:
                break
            finding_fn = finding.get("function", "")
            if finding_fn == fn_name or finding.get("status") not in FINDING_VERIFIED_STATUSES:
                continue
            if not _WRITE_FN_RE.search(finding_fn):
                continue
            finding_call = finding.get("working_call")
            if not isinstance(finding_call, dict):
                continue
            finding_inv = ctx.inv_map.get(finding_fn)
            if not finding_inv:
                continue
            str_keys = [k for k, v in finding_call.items() if isinstance(v, str)]
            for known_id in known_ids_list:
                if prereq_calls_made >= prereq_call_budget:
                    break
                prereq_args = dict(finding_call)
                for key, value in prereq_args.items():
                    if isinstance(value, int) and value <= 1:
                        prereq_args[key] = 100
                if str_keys:
                    prereq_args[str_keys[0]] = known_id
                try:
                    _execute_tool(finding_inv, prereq_args)
                except Exception:
                    pass
                prereq_calls_made += 1


def _prepare_explore_one(inv: dict, ctx: ExploreContext) -> tuple[str, dict[str, Any]] | None:
    if _cancel_requested(ctx.job_id):
        _append_skip_pre_probe_log(ctx, str(inv.get("name") or ""), "cancel_requested", "job cancel requested")
        return None

    fn_name = inv["name"]
    vocab_snapshot = _snapshot_probe_vocab(ctx)

    if _should_skip_probe_function(fn_name, ctx):
        return None

    _reinitialize_probe_runtime(fn_name, inv, ctx)
    _set_explore_status(ctx.job_id, ctx.explored_count(), ctx.total, f"Exploring {fn_name}…")
    logger.info("[%s] explore_worker: starting %s (%d/%d)", ctx.job_id, fn_name, ctx.explored_count() + 1, ctx.total)
    return fn_name, vocab_snapshot


def _explore_one(inv: dict, ctx: ExploreContext) -> None:
    """Run the full LLM probe sequence for a single function.

    Module-level (not a closure) so it can be called directly in unit tests.
    All shared mutable state is accessed through *ctx*; thread-safety is managed
    via ctx._lock around vocab/sentinel_catalog/already_explored/_state updates.
    """
    from api.infra.storage import _load_findings

    prepared = _prepare_explore_one(inv, ctx)
    if prepared is None:
        return
    fn_name, _vocab_snap = prepared
    _retag_runtime_probe_roles(inv)

    # Build a focused conversation for this function.
    # context_density controls how much prior knowledge is injected:
    #   full    — all prior findings (default, validated overnight)
    #   minimal — only the current function's prior finding (if any)
    #   none    — no prior findings (cold start)
    _all_prior = _load_findings(ctx.job_id)
    if ctx.runtime.context_density == "none":
        prior: list = []
    elif ctx.runtime.context_density == "minimal":
        prior = [f for f in _all_prior if f.get("function") == fn_name]
    else:
        prior = _all_prior
    _loaded_prior_success_names = {
        str(f.get("function") or "")
        for f in prior
        if str(f.get("function") or "")
        and _is_rehydratable_success_finding(f)
    }

    # BUG-001 fix: merge live_findings from functions probed earlier in THIS run
    # so the LLM sees working calls discovered within the same stage.
    # Prefer live findings over stale prior entries (live may have upgraded
    # a failure to verified_success within this run).
    with ctx._lock:
        _live = list(ctx.live_findings)
    _live_fn_names = {str(f.get("function") or "") for f in _live if str(f.get("function") or "")}
    _SUCCESS_STATUSES = {"success", "verified_success", "functional_precondition_unmet", "inferred_success"}
    _live_by_fn = {}
    for lf in _live:
        lfn = lf.get("function")
        if lfn:
            _live_by_fn[lfn] = lf
    for i, pf in enumerate(prior):
        pfn = pf.get("function")
        if pfn in _live_by_fn:
            live_entry = _live_by_fn[pfn]
            if live_entry.get("status") in _SUCCESS_STATUSES and pf.get("status") not in _SUCCESS_STATUSES:
                prior[i] = live_entry
            _live_by_fn.pop(pfn)
    for lf in _live_by_fn.values():
        prior.append(lf)

    sys_msg = _build_explore_system_message(
        ctx.invocables, prior, sentinels=ctx.sentinels,
        vocab=_vocab_snap, use_cases=ctx.use_cases_text,
        data_types=getattr(ctx, "ghidra_data_types", None),
    )
    _is_write_fn = bool(_WRITE_FN_RE.search(fn_name))
    _is_version_fn = bool(_VERSION_FN_RE.search(fn_name))

    # Decompiler confidence warning for low-quality analysis
    _decomp_conf = inv.get("decompiler_confidence", 1.0)
    _confidence_warning = ""
    if isinstance(_decomp_conf, (int, float)) and _decomp_conf < 0.5:
        _confidence_warning = (
            "\n\nWARNING: Ghidra's decompilation for this function is LOW CONFIDENCE "
            f"(score: {_decomp_conf:.1f}). Parameter types, counts, and directions may be wrong. "
            "Probe more variations of argument types and counts than usual.\n"
        )

    # Extract decompiled code for this function (if available from Ghidra)
    _decompiled = inv.get("doc_comment") or inv.get("doc") or ""
    _decompiled_block = ""
    if _decompiled and _is_write_fn:
        _trunc = _decompiled[:3000]
        _decompiled_block = (
            f"\n\nDECOMPILED SOURCE CODE for {fn_name}:\n```c\n{_trunc}\n```\n"
            "READ THIS CODE CAREFULLY. It tells you exactly what conditions make "
            "this function return 0 (success) vs a sentinel error code.\n"
        )

    # For write functions, also gather decompiled code from related functions
    # (init functions and any functions this one might depend on)
    _dependency_block = ""
    if _is_write_fn:
        _dep_parts = []
        for other_inv in ctx.invocables:
            if other_inv["name"] == fn_name:
                continue
            other_doc = other_inv.get("doc_comment") or other_inv.get("doc") or ""
            if not other_doc:
                continue
            other_name = other_inv["name"]
            is_init = bool(_INIT_RE.search(other_name))
            is_unlock = "unlock" in other_name.lower()
            if is_init or is_unlock:
                _dep_parts.append(
                    f"\nRELATED FUNCTION — {other_name}:\n```c\n{other_doc[:2000]}\n```\n"
                )
        if _dep_parts:
            _dependency_block = (
                "\nDEPENDENCY ANALYSIS — These functions may need to be called "
                "before the target function will succeed:\n"
                + "".join(_dep_parts[:3])
            )

    # Build known ID hints from vocab, prioritizing lineage-compatible values
    _known_ids = _prioritized_probe_id_hints(inv, ctx.vocab)
    _id_hint = ", ".join(_known_ids) if _known_ids else "CUST-001, ORD-001, ACCT-001"
    _required_prefix_hints = _required_prefix_hints_for_inv(inv)
    _prefix_hint_text = ", ".join(
        f"{param_name} starts with '{prefix}'"
        for param_name, prefix in _required_prefix_hints.items()
    )
    _lineage_probe_instruction = ""
    if _required_prefix_hints:
        _lineage_probe_instruction = (
            "Prioritize same-run lineage or prior evidence values that satisfy the target prefix checks "
            f"before static IDs. Required prefixes: {_prefix_hint_text}.\n"
        )

    # Find init function names dynamically (not hardcoded to CS_Initialize)
    _init_names = [i["name"] for i in ctx.init_invocables] if ctx.init_invocables else []
    _has_init_callable = bool(_init_names)
    _init_call_hint = _init_names[0] if _init_names else ""

    if ctx.runtime.instruction_fragment:
        _instruction = ctx.runtime.instruction_fragment
    elif _is_write_fn:
        _step3_init = (
            f"  a. Call {_init_call_hint}() first (available init function)\n"
            if _has_init_callable
            else "  a. No init-like function is available in this session; do not invent one.\n"
        )
        _step4_init = (
            f"  - Different init modes: {_init_call_hint}(param_1=0), (param_1=1), (param_1=2)\n"
            if _has_init_callable
            else ""
        )
        _instruction = (
            "Your PRIMARY GOAL is to make this function return 0 (success).\n\n"
            "STEP 1 — READ THE DECOMPILED CODE below. It shows you:\n"
            "  - What conditions cause error returns (sentinel codes)\n"
            "  - What conditions lead to return 0 (success path)\n"
            "  - Whether this function depends on another function being called first\n"
            "  - Whether there are checksums, XOR validations, or flag checks\n\n"
            "STEP 2 — REASON about what inputs satisfy the success path:\n"
            "  - If the code checks a flag/bit set by another function, call that function first\n"
            "  - If the code has a checksum (XOR, hash), compute the correct input value\n"
            "  - If the code validates string format, use the format shown in the code\n"
            "  - If the code checks a balance/count, ensure the prerequisite state exists\n\n"
            "STEP 3 — EXECUTE your plan:\n"
            + _step3_init
            + "  b. Call any prerequisite functions identified in Step 2\n"
            + "  c. Call this function with the inputs you reasoned about\n"
            + _lineage_probe_instruction
            + f"  Use these IDs as args: {_id_hint}. For amounts start SMALL: try 1, 10, 50.\n\n"
            "STEP 4 — If still failing, try variations:\n"
            + _step4_init
            + "  - Different ID values from the static analysis hints\n"
            "  - Do not assume one global meaning for -4 or -5; use the attached [CLASSIFICATION] meaning and the decompiled code\n"
            "  - If the classification says the error is a business/runtime precondition, try satisfying that precondition before inventing new argument shapes\n\n"
            "After EACH attempt, check: did the function return 0?\n"
            "  - If YES: call record_finding(status='verified_success', working_call=<the args that worked>)\n"
            "  - If the function returns a BUSINESS ERROR like 'insufficient balance' or 'not enough points':\n"
            "    The function WORKS — it accepted your call and ran business logic.\n"
            "    Call record_finding(status='functional_precondition_unmet') and note that the function is\n"
            "    responsive and returns meaningful business errors. This is NOT a failure — it means\n"
            "    the function works but runtime preconditions (balance, points, quota) aren't met.\n"
            "  - If NO after all attempts: call record_finding(status='failure') with the sentinel codes seen.\n"
            "Do NOT waste tool calls on enrich_invocable until you find a working call.\n"
            + _decompiled_block
            + _dependency_block
        )
    else:
        if _has_init_callable:
            _step1 = (
                f"STEP 1: Call {_init_call_hint}() first — most functions require "
                "initialization before they will return useful results.\n"
            )
            _step3_retry = (
                "STEP 3: If you get sentinel error 0xFFFFFFFF (not found) or 0xFFFFFFFD "
                "(not initialized), try calling the init function with different modes: "
                f"{_init_call_hint}(param_1=0), then retry.\n"
            )
        else:
            _step1 = (
                "STEP 1: No init-like function is available in this session, so do not "
                "invent or search for one before probing the target function.\n"
            )
            _step3_retry = (
                "STEP 3: If you get sentinel error 0xFFFFFFFF (not found) or 0xFFFFFFFD "
                "(not initialized), use the static hints and prior findings to infer the "
                "missing state handoff instead of inventing a missing init call.\n"
            )
        _instruction = (
            _step1
            + f"STEP 2: Call '{fn_name}' with plausible args. "
            + (_lineage_probe_instruction if _lineage_probe_instruction else "")
            + f"Use IDs: {_id_hint}.\n"
            + _step3_retry
            + "STEP 4: Call enrich_invocable to describe what the params actually mean, "
            "then call record_finding:\n"
            "  - status='verified_success' if it returned 0\n"
            "  - status='functional_precondition_unmet' if it returned a meaningful "
            "business error (locked, not found after init, insufficient balance)\n"
            "  - status='failure' only if you exhausted all reasonable attempts\n"
        )

    conversation = [
        sys_msg,
        {
            "role": "user",
            "content": (
                f"Explore the function '{fn_name}'. "
                + _confidence_warning
                + _instruction
                + ctx.static_hints_block
                + (ctx.write_unlock_block if _is_write_fn else "")
            ),
        },
    ]

    # T-04: persist first probe user message per job as observability artifact.
    # Only written once (first function processed) — proves static hints reached
    # the probe user message and were not silently dropped.
    try:
        _sample_blob = f"{ctx.job_id}/probe_user_message_sample.txt"
        _sample_exists = True
        try:
            _download_blob(ARTIFACT_CONTAINER, _sample_blob)
        except Exception:
            _sample_exists = False
        if not _sample_exists:
            _sample_content = conversation[1]["content"]
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                _sample_blob,
                _sample_content.encode(),
            )
    except Exception as _t04_err:
        logger.debug("[%s] T-04: probe user message sample write failed: %s",
                     ctx.job_id, _t04_err)

    # Reasoning artifact: snapshot the vocab state at this function's probe start.
    # Captures what domain knowledge the model had available before probing began.
    # Writes to evidence/stage-01-pre-probe/probe-vocab-snapshot.json (appended per function).
    try:
        _vocab_snap_entry = {
            "function": fn_name,
            "vocab_keys": list(_vocab_snap.keys()),
            "vocab": _vocab_snap,
        }
        _vocab_snap_blob = (
            f"{ctx.job_id}/evidence/stage-01-pre-probe/probe-vocab-snapshot.json"
        )
        try:
            _existing_vsnaps = json.loads(
                _download_blob(ARTIFACT_CONTAINER, _vocab_snap_blob)
            )
        except Exception:
            _existing_vsnaps = []
        _existing_vsnaps.append(_vocab_snap_entry)
        _upload_to_blob(
            ARTIFACT_CONTAINER, _vocab_snap_blob,
            json.dumps(_existing_vsnaps, indent=2).encode(),
        )
    except Exception as _vsne:
        logger.debug("[%s] probe-vocab-snapshot write failed for %s: %s",
                     ctx.job_id, fn_name, _vsne)

    # Write functions get a larger tool budget — they need init+write+retry cycles
    _effective_max_tool_calls = (
        max(ctx.runtime.max_tool_calls, 14) if _is_write_fn
        else ctx.runtime.max_tool_calls
    )

    # Per-function local state (not shared; no lock required)
    _observed_successes: list[dict] = []
    _enrich_called = False
    _best_raw_result: str = ""
    _p_lookup = {p.get("name", ""): p for p in (inv.get("parameters") or [])}
    _fn_probe_log: list[dict] = []
    _fn_tool_call_count = 0
    _direct_target_tool_calls = 0
    _no_tool_call_rounds = 0
    _finding_recorded = False
    _policy_stop_reason: str | None = None
    _policy_events: list[dict] = []
    _write_retry_counts: dict[str, int] = defaultdict(int)
    _successful_call_map: dict[str, dict[str, Any]] = {}
    _seeded_external_successes: set[str] = set()
    _trusted_checkpoint_seed_successes: set[str] = set()
    _fresh_replayed_successes: set[str] = set()
    _runtime_lineage_hints: dict[str, Any] = {}
    _runtime_prereqs = list(dict.fromkeys(_infer_runtime_prerequisites(inv, ctx.inv_map)))
    _cluster_seed_active = bool(str(ctx.runtime.cluster_checkpoint_id or "").strip())
    def _tool_call_cap_reached(*, allow_direct_probe_floor: bool = False) -> bool:
        if _fn_tool_call_count < _effective_max_tool_calls:
            return False
        if allow_direct_probe_floor and _direct_target_tool_calls < ctx.runtime.min_direct_probes:
            return False
        return True

    for _known in prior:
        _known_fn = str(_known.get("function") or "")
        _known_wc = _known.get("working_call")
        if (
            _known_fn
            and isinstance(_known_wc, dict)
            and _is_rehydratable_success_finding(_known)
        ):
            _successful_call_map[_known_fn] = dict(_known_wc)
            if _known_fn not in _live_fn_names and (
                _known_fn in _loaded_prior_success_names or _is_seeded_external_success(_known)
            ):
                _seeded_external_successes.add(_known_fn)
    def _has_trustworthy_checkpoint_seed_success(prereq_name: str) -> bool:
        _seeded_success = _successful_call_map.get(prereq_name)
        if not isinstance(_seeded_success, dict) or not _seeded_success:
            return False
        _seeded_inv = ctx.inv_map.get(prereq_name) or {}
        _expected_output_families = _expected_live_output_families(_seeded_inv)
        _param_output_families: set[str] = set()
        for _idx, _param in enumerate(_seeded_inv.get("parameters") or []):
            if not isinstance(_param, dict) or not _is_effective_output_param(_seeded_inv, _param, _idx):
                continue
            _param_name = str(_param.get("name") or "")
            if not _param_name or _param_name not in _seeded_success:
                continue
            _param_value = _seeded_success.get(_param_name)
            _kind = _semantic_arg_kind(
                _param_name,
                None,
                str(_param.get("json_type") or ""),
                str(_param.get("description") or _param.get("type") or ""),
            )
            if _kind and _is_live_lineage_hint_value(_kind, _param_value):
                _param_output_families.add(_kind)
        if _expected_output_families:
            if _expected_output_families.issubset({"handle", "blob_token"}):
                return False
            return _expected_output_families.issubset(_param_output_families)
        _live_hints = _collect_live_lineage_hints(_seeded_success, "")
        _consumer_ready_hints = {
            _kind: _value
            for _kind, _value in _structured_target_hints(_seeded_success).items()
            if _is_live_lineage_hint_value(_kind, _value)
        }
        return bool(_consumer_ready_hints)

    _trusted_checkpoint_seed_successes = {
        _known_fn
        for _known_fn in _seeded_external_successes
        if _known_fn in _runtime_prereqs and _has_trustworthy_checkpoint_seed_success(_known_fn)
    }
    for _trusted_fn in _trusted_checkpoint_seed_successes:
        _trusted_success = _successful_call_map.get(_trusted_fn)
        if not isinstance(_trusted_success, dict) or not _trusted_success:
            continue
        for _kind, _value in _collect_live_lineage_hints(_trusted_success, "").items():
            if _is_live_lineage_hint_value(_kind, _value):
                _runtime_lineage_hints.setdefault(_kind, _value)

    def _is_trusted_checkpoint_seed_success(prereq_name: str) -> bool:
        return prereq_name in _trusted_checkpoint_seed_successes

    try:
        _structured_probe_args, _structured_selection = _build_ranked_fallback_probe_args(
            inv,
            _vocab_snap,
            attempt=0,
            evidence=getattr(ctx, "evidence_candidates", None),
        )
        _structured_probe_args, _structured_selection = _augment_structured_probe_args_for_mixed_calls(
            inv,
            _structured_probe_args,
            _structured_selection,
        )
        _has_structured_fallback = any(isinstance(v, dict) for v in _structured_probe_args.values())
    except Exception:
        _structured_selection = {}
        _has_structured_fallback = False

    def _refresh_structured_probe_args() -> None:
        nonlocal _structured_probe_args, _structured_selection, _has_structured_fallback
        try:
            _structured_probe_args, _structured_selection = _build_ranked_fallback_probe_args(
                inv,
                _vocab_snap,
                attempt=0,
                evidence=getattr(ctx, "evidence_candidates", None),
            )
            _structured_probe_args, _structured_selection = _augment_structured_probe_args_for_mixed_calls(
                inv,
                _structured_probe_args,
                _structured_selection,
            )
            _has_structured_fallback = any(isinstance(v, dict) for v in _structured_probe_args.values())
        except Exception:
            _structured_selection = {}
            _has_structured_fallback = False

    def _run_structured_prerequisite_chain(target_args: dict[str, Any]) -> None:
        _fresh_lineage = _requires_fresh_runtime_lineage(inv)
        _hints = dict(_runtime_lineage_hints)
        _hints.update(
            _sanitize_lineage_hints_for_prereq_replay(
                _structured_target_hints(target_args),
                fresh_lineage=_fresh_lineage,
            )
        )
        _ecr = getattr(ctx, "evidence_candidates", None)
        _visited: set[str] = set()
        _active: set[str] = set()
        _blocked_prereqs: dict[str, int] = {}
        _hint_generation = 0

        def _apply_live_lineage_promotion(
            promoted: dict[str, Any],
            *,
            source_function: str = "",
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            nonlocal _hint_generation
            applied: dict[str, Any] = {}
            materialized: dict[str, Any] = {}
            for _kind, _value in (promoted or {}).items():
                if not _is_live_lineage_hint_value(_kind, _value):
                    continue
                if _hints.get(_kind) == _value and _runtime_lineage_hints.get(_kind) == _value:
                    continue
                _hints[_kind] = _value
                _runtime_lineage_hints[_kind] = _value
                applied[_kind] = _value
            if applied:
                if _ecr is not None and source_function:
                    try:
                        _ecr.materialize_live_hints(source_function, applied)
                        materialized = dict(applied)
                    except Exception as _materialize_e:
                        logger.debug(
                            "[%s] live runtime artifact materialization failed for %s: %s",
                            ctx.job_id,
                            source_function,
                            _materialize_e,
                        )
                _hint_generation += 1
            return applied, materialized

        def _retry_blocked_prereqs() -> list[str]:
            resumed: list[str] = []
            made_progress = True
            while made_progress:
                made_progress = False
                for _blocked_name, _blocked_generation in list(_blocked_prereqs.items()):
                    if not _consume_retryable_blocked_prereq(
                        _blocked_prereqs,
                        _blocked_name,
                        hint_generation=_hint_generation,
                    ):
                        continue
                    resumed.append(_blocked_name)
                    _run_one(_blocked_name)
                    made_progress = True
            return resumed

        def _record_runtime_materialization(
            executed_log: dict[str, Any] | None,
            *,
            prereq_name: str,
            prereq_inv: dict[str, Any],
            prereq_args: dict[str, Any],
            result_text: str,
            param_lookup: dict[str, dict[str, Any]],
            arg_selection: dict[str, Any],
            merged_success: dict[str, Any],
        ) -> tuple[dict[str, Any], dict[str, Any], list[str], list[str]]:
            promoted_hints = _collect_live_lineage_hints(merged_success, result_text)
            applied_hints, materialized_hints = _apply_live_lineage_promotion(
                promoted_hints,
                source_function=prereq_name,
            )
            expected_output_families = _expected_live_output_families(prereq_inv)
            materialization_missing = sorted(
                family for family in expected_output_families if family not in promoted_hints
            )
            retry_resumed = _retry_blocked_prereqs() if applied_hints else []
            if isinstance(executed_log, dict):
                _la = dict(executed_log.get("lineage_admission") or {})
                _la["live_value_promoted"] = bool(applied_hints)
                _la["promoted_hints"] = applied_hints
                _la["materialized_runtime_artifacts"] = materialized_hints
                _la["promotion_source"] = prereq_name
                _la["retry_resumed"] = retry_resumed
                _la["materialization_missing_families"] = materialization_missing
                _observer_results = observe_live_artifact_emission(
                    contract_name="generalized runtime artifact materializer",
                    producer_function=prereq_name,
                    promoted_hints=applied_hints,
                    materialization_missing_families=materialization_missing,
                )
                _observer_results.extend(
                    observe_lineage_handoff(
                        contract_name="prerequisite replay / runtime materialization",
                        consumer_function=prereq_name,
                        consumer_args=prereq_args,
                        arg_selection=arg_selection,
                        lineage_hints=promoted_hints,
                        param_lookup=param_lookup,
                    )
                )
                if _observer_results:
                    _la["observer_results"] = _observer_results
                executed_log["lineage_admission"] = _la
            return applied_hints, materialized_hints, materialization_missing, retry_resumed

        def _promote_prereq_success(
            prereq_name: str,
            merged_success: dict[str, Any],
            result_text: str,
        ) -> dict[str, Any]:
            try:
                _existing = next(
                    (f for f in reversed(_load_findings(ctx.job_id)) if f.get("function") == prereq_name),
                    None,
                )
            except Exception:
                _existing = None
            prereq_inv = ctx.inv_map.get(prereq_name) or {}
            admission = _assess_prerequisite_replay_admission(
                prereq_name,
                merged_success,
                prereq_inv,
            )
            reasons_text = ", ".join(admission["reasons"])
            _payload = {
                "working_call": merged_success,
                "status": admission["status"],
                "stop_reason": "success" if admission["admitted"] else "prerequisite_replay_not_preservable",
                "finding": (
                    f"Verified during prerequisite replay for {fn_name}: "
                    f"returns 0 with {merged_success}."
                ),
                "notes": (
                    f"Observed as successful prerequisite replay while exploring {fn_name}."
                    if admission["admitted"]
                    else (
                        f"Observed as successful prerequisite replay while exploring {fn_name}, "
                        f"but did not admit it into reusable same-run truth: {reasons_text}."
                    )
                ),
                "reusable_truth_eligible": admission["admitted"],
                "reusable_truth_score": float(admission["truth_assessment"].get("score") or 0.0),
                "reusable_truth_reasons": list(admission["reasons"]),
            }
            try:
                if _existing:
                    _current_status = str(_existing.get("status_canonical") or _existing.get("status") or "")
                    if (
                        _current_status != "verified_success"
                        or not admission["admitted"]
                    ):
                        _patch_finding(ctx.job_id, prereq_name, _payload)
                else:
                    _save_finding(
                        ctx.job_id,
                        {
                            "function": prereq_name,
                            **_payload,
                        },
                    )
                if admission["admitted"]:
                    with ctx._lock:
                        ctx.live_findings.append({
                            "function": prereq_name,
                            "status": "verified_success",
                            "finding": _payload["finding"],
                            "working_call": merged_success,
                        })
            except Exception as _promote_e:
                logger.debug("[%s] prerequisite success promotion failed for %s: %s",
                             ctx.job_id, prereq_name, _promote_e)
            return admission

        def _collect_ordered_prereq_chain(prereq_names: list[str]) -> list[str]:
            ordered: list[str] = []
            seen: set[str] = set()

            def _visit(name: str) -> None:
                if name in seen:
                    return
                seen.add(name)
                prereq_inv = ctx.inv_map.get(name)
                if prereq_inv:
                    for upstream in _infer_runtime_prerequisites(prereq_inv, ctx.inv_map):
                        _visit(upstream)
                ordered.append(name)

            for prereq_name in prereq_names:
                _visit(prereq_name)
            return ordered

        def _rehydrate_same_run_prereq_successes() -> list[str]:
            nonlocal _fn_tool_call_count
            replayed: list[str] = []
            if not _fresh_lineage:
                return replayed
            for prereq_name in _collect_ordered_prereq_chain(_runtime_prereqs):
                if _is_trusted_checkpoint_seed_success(prereq_name):
                    continue
                if prereq_name in _seeded_external_successes:
                    continue
                known_success = _successful_call_map.get(prereq_name)
                prereq_inv = ctx.inv_map.get(prereq_name)
                if not prereq_inv or not isinstance(known_success, dict) or not known_success:
                    continue
                rehydrate_args, _ = _normalize_true_output_scalar_args(
                    prereq_inv,
                    dict(known_success),
                    {},
                )
                tc = _execute_tool_traced(prereq_inv, dict(rehydrate_args))
                res = tc["result_str"]
                cls = _classify_result_text(str(res), sentinels=ctx.sentinels)
                _fn_probe_log.append({
                    "probe_id": f"{fn_name}:structured_preflight:rehydrate:{prereq_name}",
                    "phase": "structured_preflight_prereq",
                    "function": prereq_name,
                    "round": -1,
                    "reasoning": f"same-run state rehydration replay for {fn_name}",
                    "tool": prereq_name,
                    "args": dict(rehydrate_args),
                    "arg_sources": {
                        k: _classify_arg_source(k, v, prereq_inv, _vocab_snap)
                        for k, v in rehydrate_args.items()
                    },
                    "lineage_admission": {
                        "fresh_replay_required": True,
                        "forced_live_replay": False,
                        "replay_outcome": "rehydrated_same_run_success",
                        "rehydration_source": "live_same_run_verified_success",
                    },
                    "result_excerpt": str(res)[:200],
                    "trace": tc.get("trace"),
                    "classification": cls,
                    "policy": None,
                })
                _fn_tool_call_count += 1
                if not _is_runtime_success_value(
                    prereq_inv,
                    prereq_name,
                    res,
                    ctx.sentinels,
                    bool(_VERSION_FN_RE.search(prereq_name)),
                ):
                    continue
                pmap = {p.get("name", ""): p for p in (prereq_inv.get("parameters") or [])}
                merged_success = _merge_runtime_success_values(
                    prereq_inv,
                    prereq_name,
                    rehydrate_args,
                    res,
                    pmap,
                    ctx.sentinels,
                )
                admission = _promote_prereq_success(prereq_name, merged_success, res)
                is_init_prereq = bool(_INIT_RE.search(prereq_name))
                if not admission["admitted"]:
                    if is_init_prereq:
                        _successful_call_map[prereq_name] = dict(merged_success)
                        _fresh_replayed_successes.add(prereq_name)
                        _visited.add(prereq_name)
                        replayed.append(prereq_name)
                        continue
                    _fn_probe_log.append({
                        "probe_id": f"{fn_name}:structured_preflight:rehydrate:{prereq_name}:rejected",
                        "phase": "structured_preflight_prereq",
                        "function": prereq_name,
                        "round": -1,
                        "reasoning": (
                            f"same-run state rehydration replay for {fn_name} returned 0 but "
                            "did not produce preservation-safe lower-floor truth"
                        ),
                        "tool": prereq_name,
                        "args": dict(rehydrate_args),
                        "arg_sources": {
                            k: _classify_arg_source(k, v, prereq_inv, _vocab_snap)
                            for k, v in rehydrate_args.items()
                        },
                        "lineage_admission": {
                            "fresh_replay_required": True,
                            "forced_live_replay": False,
                            "replay_outcome": "rejected_not_preservable",
                            "reasons": list(admission["reasons"]),
                        },
                        "result_excerpt": str(res)[:200],
                        "trace": tc.get("trace"),
                        "classification": cls,
                        "policy": None,
                    })
                    continue
                _successful_call_map[prereq_name] = dict(merged_success)
                _fresh_replayed_successes.add(prereq_name)
                _visited.add(prereq_name)
                if _ecr is not None:
                    _id_fmts = [str(x) for x in (ctx.vocab.get("id_formats") or []) if x]
                    _ecr.harvest_from_result(
                        function_name=prereq_name,
                        result_str=res or "",
                        trace=tc.get("trace"),
                        working_args=merged_success,
                        id_formats=_id_fmts,
                        param_lookup=pmap,
                    )
                promoted_hints = _collect_live_lineage_hints(merged_success, res)
                _apply_live_lineage_promotion(promoted_hints, source_function=prereq_name)
                replayed.append(prereq_name)
            return replayed

        def _run_one(prereq_name: str) -> None:
            nonlocal _fn_tool_call_count
            if (
                prereq_name in _visited
                or prereq_name in _active
                or _tool_call_cap_reached()
            ):
                return
            _visited.add(prereq_name)
            _active.add(prereq_name)
            _prereq_inv = ctx.inv_map.get(prereq_name)
            if not _prereq_inv:
                _active.discard(prereq_name)
                return
            try:
                _retag_runtime_probe_roles(_prereq_inv)
                for _upstream in _infer_runtime_prerequisites(_prereq_inv, ctx.inv_map):
                    _run_one(_upstream)
                _trusted_checkpoint_seed = _is_trusted_checkpoint_seed_success(prereq_name)
                _base_args = {}
                _ignore_seeded_prior = (
                    _fresh_lineage
                    and prereq_name in _seeded_external_successes
                    and prereq_name not in _fresh_replayed_successes
                    and not _trusted_checkpoint_seed
                )
                if not _ignore_seeded_prior:
                    _base_args = dict(_successful_call_map.get(prereq_name) or {})
                if not _base_args:
                    _base_args, _ = _build_ranked_fallback_probe_args(
                        _prereq_inv,
                        _vocab_snap,
                        attempt=0,
                        evidence=None if _ignore_seeded_prior else _ecr,
                    )
                _dynamic_hints = dict(_hints)
                for _known_name, _known_args in _successful_call_map.items():
                    if (
                        _fresh_lineage
                        and _known_name in _seeded_external_successes
                        and _known_name not in _fresh_replayed_successes
                        and not _is_trusted_checkpoint_seed_success(_known_name)
                    ):
                        continue
                    _dynamic_hints.update(
                        _consumer_ready_lineage_hints(
                            _known_args,
                            fresh_lineage=_fresh_lineage,
                        )
                    )
                _dynamic_hints.update(_hints)
                _lineage_admission: dict[str, Any] = {}
                _prereq_args = _align_prerequisite_args(
                    _prereq_inv,
                    _base_args,
                    _dynamic_hints,
                    _vocab_snap,
                    admission_trace=_lineage_admission,
                )
                _prereq_args, _ = _repair_target_scalar_args(
                    _prereq_inv,
                    _prereq_args,
                    {},
                    _vocab_snap,
                    _ecr,
                    lineage_hints=_dynamic_hints,
                    prefer_lineage=_fresh_lineage,
                )
                _prereq_args, _ = _normalize_true_output_scalar_args(_prereq_inv, _prereq_args, {})
                _placeholder_params = (
                    _collect_placeholder_replay_params(_prereq_inv, _prereq_args)
                    if _fresh_lineage
                    else {}
                )
                if _fresh_lineage:
                    for _param_name, _meta in _lineage_admission.items():
                        if not _meta.get("placeholder_detected"):
                            continue
                        _source_lineage = str(_meta.get("source_lineage") or "")
                        if _source_lineage.startswith("lineage_hint."):
                            continue
                        _placeholder_params.setdefault(
                            _param_name,
                            {
                                "value": _prereq_args.get(_param_name),
                                "expected_family": _meta.get("expected_family"),
                                "placeholder_detected": True,
                                "source_lineage": _source_lineage,
                            },
                        )
                if _placeholder_params:
                    _blocked_prereqs[prereq_name] = _hint_generation
                    _visited.discard(prereq_name)
                    _fn_probe_log.append({
                        "probe_id": f"{fn_name}:structured_preflight:prereq:{prereq_name}:placeholder_block",
                        "phase": "structured_preflight_prereq",
                        "function": prereq_name,
                        "round": -1,
                        "reasoning": f"prerequisite replay blocked for {fn_name} because placeholder state remained unresolved",
                        "tool": prereq_name,
                        "args": _prereq_args,
                        "arg_sources": {
                            k: _classify_arg_source(k, v, _prereq_inv, _vocab_snap)
                            for k, v in _prereq_args.items()
                        },
                        "lineage_admission": {
                            "fresh_replay_required": _fresh_lineage,
                            "forced_live_replay": True,
                            "replay_outcome": "placeholder_blocked",
                            "placeholder_params": _placeholder_params,
                            "param_trace": _lineage_admission,
                            "blocked_generation": _hint_generation,
                        },
                        "result_excerpt": "prerequisite replay blocked because unresolved placeholder inputs remained after fresh-lineage repair",
                        "trace": {"backend": "policy", "blocked": True},
                        "classification": {"has_return": False},
                        "policy": None,
                    })
                    return
                if _trusted_checkpoint_seed:
                    _trusted_success = dict(_successful_call_map.get(prereq_name) or {})
                    _promoted_hints = _collect_live_lineage_hints(_trusted_success, "")
                    _applied_hints, _materialized_hints = _apply_live_lineage_promotion(
                        _promoted_hints,
                        source_function=prereq_name,
                    )
                    _fn_probe_log.append({
                        "probe_id": f"{fn_name}:structured_preflight:prereq:{prereq_name}:trusted_checkpoint_seed",
                        "phase": "structured_preflight_prereq",
                        "function": prereq_name,
                        "round": -1,
                        "reasoning": (
                            f"trusted checkpoint seed reused for {fn_name} without replay "
                            "because bounded cluster seeding already supplied a verified producer success"
                        ),
                        "tool": prereq_name,
                        "args": _trusted_success,
                        "arg_sources": {
                            k: _classify_arg_source(k, v, _prereq_inv, _vocab_snap)
                            for k, v in _trusted_success.items()
                        },
                        "lineage_admission": {
                            "fresh_replay_required": _fresh_lineage,
                            "forced_live_replay": False,
                            "replay_outcome": "trusted_checkpoint_seed",
                            "rehydration_source": "cluster_checkpoint_seed",
                            "param_trace": _lineage_admission,
                            "promoted_hints": _applied_hints,
                            "materialized_runtime_artifacts": _materialized_hints,
                        },
                        "result_excerpt": (
                            "trusted checkpoint seed reused without replay to preserve "
                            "bounded rerun target-call budget"
                        ),
                        "trace": {"backend": "policy", "trusted_checkpoint_seed": True},
                        "classification": {"has_return": True},
                        "policy": None,
                    })
                    return
                _tc = _execute_tool_traced(_prereq_inv, _prereq_args)
                _res = _tc["result_str"]
                _cls = _classify_result_text(str(_res), sentinels=ctx.sentinels)
                _executed_log = {
                    "probe_id": f"{fn_name}:structured_preflight:prereq:{prereq_name}",
                    "phase": "structured_preflight_prereq",
                    "function": prereq_name,
                    "round": -1,
                    "reasoning": f"prerequisite replay for {fn_name}",
                    "tool": prereq_name,
                    "args": _prereq_args,
                    "arg_sources": {
                        k: _classify_arg_source(k, v, _prereq_inv, _vocab_snap)
                        for k, v in _prereq_args.items()
                    },
                    "lineage_admission": {
                        "fresh_replay_required": _fresh_lineage,
                        "forced_live_replay": bool(_placeholder_params),
                        "replay_outcome": "executed",
                        "placeholder_params": _placeholder_params,
                        "param_trace": _lineage_admission,
                    },
                    "result_excerpt": str(_res)[:200],
                    "trace": _tc.get("trace"),
                    "classification": _cls,
                    "policy": None,
                }
                _fn_probe_log.append(_executed_log)
                _fn_tool_call_count += 1
                if not _is_runtime_success_value(
                    _prereq_inv,
                    prereq_name,
                    _res,
                    ctx.sentinels,
                    bool(_VERSION_FN_RE.search(prereq_name)),
                ):
                    return
                _pmap = {p.get("name", ""): p for p in (_prereq_inv.get("parameters") or [])}
                _merged_success = _merge_runtime_success_values(
                    _prereq_inv,
                    prereq_name,
                    _prereq_args,
                    _res,
                    _pmap,
                    ctx.sentinels,
                )
                _is_init_prereq = bool(_INIT_RE.search(prereq_name))
                (
                    _applied_hints,
                    _materialized_hints,
                    _materialization_missing,
                    _retry_resumed,
                ) = _record_runtime_materialization(
                    _executed_log,
                    prereq_name=prereq_name,
                    prereq_inv=_prereq_inv,
                    prereq_args=_prereq_args,
                    result_text=_res,
                    param_lookup=_pmap,
                    arg_selection=_lineage_admission,
                    merged_success=_merged_success,
                )
                admission = _promote_prereq_success(prereq_name, _merged_success, _res)
                if not admission["admitted"]:
                    _local_only_success = (
                        not _expected_live_output_families(_prereq_inv)
                        and not _placeholder_params
                    )
                    if _is_init_prereq or _local_only_success:
                        _successful_call_map[prereq_name] = dict(_merged_success)
                        _fresh_replayed_successes.add(prereq_name)
                        return
                    _blocked_prereqs[prereq_name] = _hint_generation
                    _visited.discard(prereq_name)
                    _fn_probe_log.append({
                        "probe_id": f"{fn_name}:structured_preflight:prereq:{prereq_name}:rejected",
                        "phase": "structured_preflight_prereq",
                        "function": prereq_name,
                        "round": -1,
                        "reasoning": (
                            f"prerequisite replay for {fn_name} returned 0 but "
                            "did not produce preservation-safe lower-floor truth"
                        ),
                        "tool": prereq_name,
                        "args": _prereq_args,
                        "arg_sources": {
                            k: _classify_arg_source(k, v, _prereq_inv, _vocab_snap)
                            for k, v in _prereq_args.items()
                        },
                        "lineage_admission": {
                            "fresh_replay_required": _fresh_lineage,
                            "forced_live_replay": bool(_placeholder_params),
                            "replay_outcome": "rejected_not_preservable",
                            "reasons": list(admission["reasons"]),
                            "blocked_generation": _hint_generation,
                            "param_trace": _lineage_admission,
                        },
                        "result_excerpt": str(_res)[:200],
                        "trace": _tc.get("trace"),
                        "classification": _cls,
                        "policy": None,
                    })
                    return
                _successful_call_map[prereq_name] = dict(_merged_success)
                _fresh_replayed_successes.add(prereq_name)
                if _ecr is not None:
                    _id_fmts = [str(x) for x in (ctx.vocab.get("id_formats") or []) if x]
                    _ecr.harvest_from_result(
                        function_name=prereq_name,
                        result_str=_res or "",
                        trace=_tc.get("trace"),
                        working_args=_merged_success,
                        id_formats=_id_fmts,
                        param_lookup=_pmap,
                    )
                    if _INIT_RE.search(prereq_name):
                        _ecr.mark_init_satisfied(prereq_name)
            finally:
                _active.discard(prereq_name)

        def _run_missing_init_prereqs_first() -> None:
            for _prereq_name in _collect_ordered_prereq_chain(_runtime_prereqs):
                if not _INIT_RE.search(_prereq_name):
                    continue
                _known_success = _successful_call_map.get(_prereq_name)
                if isinstance(_known_success, dict) and _known_success:
                    continue
                _run_one(_prereq_name)

        _run_missing_init_prereqs_first()
        _rehydrate_same_run_prereq_successes()
        for _prereq in _runtime_prereqs:
            _run_one(_prereq)

    def _current_lineage_hints() -> dict[str, Any]:
        _fresh_lineage = _requires_fresh_runtime_lineage(inv)
        _hints: dict[str, Any] = dict(_runtime_lineage_hints)
        for _known_name, _known_args in _successful_call_map.items():
            if (
                _fresh_lineage
                and not _allow_seeded_external_success_for_fresh_lineage(
                    _known_name,
                    runtime_prereqs=_runtime_prereqs,
                    seeded_external_successes=_seeded_external_successes,
                    fresh_replayed_successes=_fresh_replayed_successes,
                    trusted_checkpoint_seed_successes=_trusted_checkpoint_seed_successes,
                )
            ):
                continue
            _hints.update(
                _consumer_ready_lineage_hints(
                    _known_args,
                    fresh_lineage=_fresh_lineage,
                )
            )
        return _hints

    # ── Main LLM round loop ──────────────────────────────────────────────────

    def _run_reserved_structured_preflight() -> None:
        nonlocal _fn_tool_call_count, _direct_target_tool_calls, _best_raw_result
        if not _has_structured_fallback or _observed_successes:
            return
        if _tool_call_cap_reached():
            return
        _run_structured_prerequisite_chain(_structured_probe_args)
        _refresh_structured_probe_args()
        if _tool_call_cap_reached(allow_direct_probe_floor=True):
            return
        _pb: dict | None = None
        if _is_write_fn:
            _ok, _reason, _detail = _write_policy_precheck(
                fn_name, _structured_probe_args, _vocab_snap, ctx.unlock_result,
            )
            if not _ok:
                _pb = {"allowed": False, "stop_reason": _reason, "detail": _detail}
        _arg_sources = {
            k: _classify_arg_source(k, v, inv, _vocab_snap)
            for k, v in _structured_probe_args.items()
        }
        if _pb:
            _fn_probe_log.append({
                "phase": "structured_preflight", "function": fn_name,
                "round": -1, "reasoning": "reserved structured scaffold preflight",
                "tool": fn_name, "args": _structured_probe_args,
                "arg_sources": _arg_sources,
                "arg_selection": _structured_selection,
                "result_excerpt": f"Policy blocked structured preflight: {_pb['stop_reason']}",
                "trace": {"backend": "policy", "blocked": True},
                "classification": {"has_return": False}, "policy": _pb,
            })
            return
        _structured_call_args, _structured_call_selection = _normalize_true_output_scalar_args(
            inv,
            _structured_probe_args,
            _structured_selection,
        )
        _current_hints = _current_lineage_hints()
        _structured_call_args, _structured_call_selection = _repair_target_scalar_args(
            inv,
            _structured_call_args,
            _structured_call_selection,
            _vocab_snap,
            getattr(ctx, "evidence_candidates", None),
            lineage_hints=_current_hints,
            prefer_lineage=_requires_fresh_runtime_lineage(inv),
        )
        _observer_results = observe_lineage_handoff(
            contract_name="dense-context lineage isolation",
            consumer_function=fn_name,
            consumer_args=_structured_call_args,
            arg_selection=_structured_call_selection,
            lineage_hints=_current_hints,
            param_lookup={str(p.get("name") or ""): p for p in (inv.get("parameters") or []) if isinstance(p, dict)},
        )
        _tc = _execute_tool_traced(ctx.inv_map[fn_name], _structured_call_args)
        _res = _tc["result_str"]
        _cls = _classify_result_text(str(_res), sentinels=ctx.sentinels)
        _preflight_log = {
            "probe_id": f"{fn_name}:structured_preflight",
            "phase": "structured_preflight", "function": fn_name,
            "round": -1, "reasoning": "reserved structured scaffold preflight",
            "tool": fn_name, "args": _structured_call_args,
            "arg_sources": _arg_sources,
            "arg_selection": _structured_call_selection,
            "result_excerpt": str(_res)[:200],
            "trace": _tc.get("trace"), "classification": _cls, "policy": None,
        }
        if _observer_results:
            _preflight_log["observer_results"] = _observer_results
        _fn_probe_log.append(_preflight_log)
        _fn_tool_call_count += 1
        _direct_target_tool_calls += 1
        if _is_runtime_success_value(inv, fn_name, _res, ctx.sentinels, _is_version_fn):
            _merged_success = _merge_runtime_success_values(
                inv,
                fn_name,
                _structured_call_args,
                _res,
                _p_lookup,
                ctx.sentinels,
            )
            _observed_successes.append(_merged_success)
            _best_raw_result = _res
            _ecr = getattr(ctx, "evidence_candidates", None)
            if _ecr is not None:
                _id_fmts = [str(x) for x in (ctx.vocab.get("id_formats") or []) if x]
                _ecr.harvest_from_result(
                    function_name=fn_name,
                    result_str=_res or "",
                    trace=_tc.get("trace"),
                    working_args=_merged_success,
                    id_formats=_id_fmts,
                    param_lookup=_p_lookup,
                )
                if _INIT_RE.search(fn_name):
                    _ecr.mark_init_satisfied(fn_name)

    def _run_reserved_prerequisite_replay() -> None:
        if _observed_successes:
            return
        _fresh_lineage = _requires_fresh_runtime_lineage(inv)
        if not _has_structured_fallback and not _fresh_lineage:
            return
        if not _runtime_prereqs:
            return
        if _tool_call_cap_reached():
            return
        _seed_args, _seed_selection = _build_ranked_fallback_probe_args(
            inv,
            _vocab_snap,
            attempt=0,
            evidence=getattr(ctx, "evidence_candidates", None),
        )
        _seed_args, _seed_selection = _repair_target_structured_args(
            inv,
            _seed_args,
            _seed_selection,
            _structured_probe_args if isinstance(_structured_probe_args, dict) else {},
            _structured_selection if isinstance(_structured_selection, dict) else {},
        )
        _seed_args, _seed_selection = _repair_target_scalar_args(
            inv,
            _seed_args,
            _seed_selection,
            _vocab_snap,
            getattr(ctx, "evidence_candidates", None),
            lineage_hints=_current_lineage_hints(),
            prefer_lineage=_requires_fresh_runtime_lineage(inv),
        )
        _seed_args, _seed_selection = _normalize_true_output_scalar_args(inv, _seed_args, _seed_selection)
        _run_structured_prerequisite_chain(_seed_args)

    def _run_reserved_lineage_preflight() -> None:
        nonlocal _fn_tool_call_count, _direct_target_tool_calls, _best_raw_result
        if _observed_successes or _has_structured_fallback:
            return
        if not _requires_fresh_runtime_lineage(inv):
            return
        if not _runtime_prereqs:
            return
        if _tool_call_cap_reached():
            return
        _seed_args, _seed_selection = _build_ranked_fallback_probe_args(
            inv,
            _vocab_snap,
            attempt=0,
            evidence=getattr(ctx, "evidence_candidates", None),
        )
        _current_hints = _current_lineage_hints()
        _seed_args, _seed_selection = _repair_target_scalar_args(
            inv,
            _seed_args,
            _seed_selection,
            _vocab_snap,
            getattr(ctx, "evidence_candidates", None),
            lineage_hints=_current_hints,
            prefer_lineage=True,
        )
        _seed_args, _seed_selection = _normalize_true_output_scalar_args(
            inv,
            _seed_args,
            _seed_selection,
        )
        _observer_results = observe_lineage_handoff(
            contract_name="dense-context lineage isolation",
            consumer_function=fn_name,
            consumer_args=_seed_args,
            arg_selection=_seed_selection,
            lineage_hints=_current_hints,
            param_lookup={str(p.get("name") or ""): p for p in (inv.get("parameters") or []) if isinstance(p, dict)},
        )
        _tc = _execute_tool_traced(ctx.inv_map[fn_name], _seed_args)
        _res = _tc["result_str"]
        _cls = _classify_result_text(str(_res), sentinels=ctx.sentinels)
        _arg_sources = {
            k: _classify_arg_source(k, v, inv, _vocab_snap)
            for k, v in _seed_args.items()
        }
        _lineage_log = {
            "probe_id": f"{fn_name}:lineage_preflight",
            "phase": "lineage_preflight",
            "function": fn_name,
            "round": -1,
            "reasoning": "reserved fresh-lineage preflight",
            "tool": fn_name,
            "args": _seed_args,
            "arg_sources": _arg_sources,
            "arg_selection": _seed_selection,
            "result_excerpt": str(_res)[:200],
            "trace": _tc.get("trace"),
            "classification": _cls,
            "policy": None,
        }
        if _observer_results:
            _lineage_log["observer_results"] = _observer_results
        _fn_probe_log.append(_lineage_log)
        _fn_tool_call_count += 1
        _direct_target_tool_calls += 1
        if _is_runtime_success_value(inv, fn_name, _res, ctx.sentinels, _is_version_fn):
            _merged_success = _merge_runtime_success_values(
                inv,
                fn_name,
                _seed_args,
                _res,
                _p_lookup,
                ctx.sentinels,
            )
            _observed_successes.append(_merged_success)
            _best_raw_result = _res
            _ecr = getattr(ctx, "evidence_candidates", None)
            if _ecr is not None:
                _id_fmts = [str(x) for x in (ctx.vocab.get("id_formats") or []) if x]
                _ecr.harvest_from_result(
                    function_name=fn_name,
                    result_str=_res or "",
                    trace=_tc.get("trace"),
                    working_args=_merged_success,
                    id_formats=_id_fmts,
                    param_lookup=_p_lookup,
                )
                if _INIT_RE.search(fn_name):
                    _ecr.mark_init_satisfied(fn_name)

    _run_reserved_prerequisite_replay()
    _run_reserved_structured_preflight()
    _run_reserved_lineage_preflight()

    for _round in range(ctx.runtime.max_rounds):
        if _cancel_requested(ctx.job_id):
            break
        if _tool_call_cap_reached():
            logger.info("[%s] explore_worker: %s hit tool-call cap (%d), moving on",
                        ctx.job_id, fn_name, _effective_max_tool_calls)
            break

        _llm_ok = False
        for _retry in range(4):
            try:
                from typing import cast, Any as _Any
                response = ctx.client.chat.completions.create(
                    model=ctx.model,
                    messages=conversation,
                    tools=cast(_Any, ctx.tool_schemas),
                    tool_choice="auto",
                    temperature=0,
                    timeout=90.0,
                )
                _llm_ok = True
                break
            except Exception as exc:
                _exc_type = type(exc).__name__
                _exc_status = getattr(exc, "status_code", None)
                _exc_body = str(getattr(exc, "body", None) or "")[:200]
                _is_rate_limit = (
                    _exc_status in (429, "429")
                    or "rate" in str(exc).lower()
                    or "too many" in str(exc).lower()
                )
                if _is_rate_limit and _retry < 3:
                    # Respect Retry-After header if present; otherwise exponential backoff
                    _retry_after = getattr(exc, "headers", {})
                    _ra_val = (_retry_after or {}).get("retry-after") or (_retry_after or {}).get("Retry-After")
                    _backoff = int(float(_ra_val)) + 1 if _ra_val else (2 ** _retry) * 8  # 8s, 16s, 32s
                    logger.info(
                        "[%s] %s: 429 rate limit, retry %d/3 after %ds",
                        ctx.job_id, fn_name, _retry + 1, _backoff,
                    )
                    time.sleep(_backoff)
                    continue
                logger.warning(
                    "[%s] explore_worker: OpenAI call failed for %s round %d: "
                    "type=%s status=%s body=%s msg=%s",
                    ctx.job_id, fn_name, _round,
                    _exc_type, _exc_status, _exc_body, exc,
                )
                _fn_probe_log.append({
                    "phase": "llm_error", "function": fn_name, "round": _round,
                    "tool": None, "args": {},
                    "result_excerpt": f"LLM error: {_exc_type} status={_exc_status}: {exc}",
                    "trace": None, "classification": {"has_return": False}, "policy": None,
                })
                break
        if not _llm_ok:
            break

        msg = response.choices[0].message

        if not msg.tool_calls:
            if _direct_target_tool_calls < ctx.runtime.min_direct_probes:
                _no_tool_call_rounds += 1
                _fn_probe_log.append({
                    "phase": "no_tool_call_round", "function": fn_name, "round": _round,
                    "tool": None, "args": {},
                    "result_excerpt": "assistant returned no tool calls before probe floor met",
                    "trace": None, "classification": {"has_return": False}, "policy": None,
                })
                conversation.append({
                    "role": "user",
                    "content": (
                        f"You have not directly called '{fn_name}' enough times yet. "
                        f"Make at least {ctx.runtime.min_direct_probes} direct call(s) to "
                        f"{fn_name} now using concrete test values, then continue analysis."
                    ),
                })
                continue
            break  # model finished — no more tool calls needed

        # Append assistant turn to conversation
        conversation.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id, "type": "function",
                    "function": {
                        "name": tc.function.name,       # type: ignore[union-attr]
                        "arguments": tc.function.arguments,  # type: ignore[union-attr]
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        # Execute each tool call in this round
        for tc in msg.tool_calls:
            if _cancel_requested(ctx.job_id):
                break
            _fn = tc.function  # type: ignore[union-attr]
            tc_name = _fn.name
            try:
                tc_args = json.loads(_fn.arguments)
            except json.JSONDecodeError:
                tc_args = {}

            tc_inv = ctx.inv_map.get(tc_name)
            classification: dict = {
                "has_return": False, "format_guess": "not_executed",
                "confidence": 0.0, "source": "none",
            }
            _policy_block: dict | None = None

            if _is_write_fn and tc_name == fn_name:
                _ok, _reason, _detail = _write_policy_precheck(
                    fn_name, tc_args, _vocab_snap, ctx.unlock_result,
                )
                if not _ok:
                    _policy_stop_reason = _reason or "policy_exhausted"
                    _policy_block = {
                        "allowed": False,
                        "stop_reason": _policy_stop_reason,
                        "detail": _detail,
                    }
                    _policy_events.append(_policy_block)

            if tc_inv is not None:
                try:
                    if tc_name == fn_name:
                        if _has_structured_fallback:
                            tc_args, _ = _repair_target_structured_args(
                                inv,
                                tc_args,
                                {},
                                _structured_probe_args,
                                _structured_selection,
                            )
                        tc_args, _ = _repair_target_scalar_args(
                            inv,
                            tc_args,
                            {},
                            _vocab_snap,
                            getattr(ctx, "evidence_candidates", None),
                            lineage_hints=_current_lineage_hints(),
                            prefer_lineage=_requires_fresh_runtime_lineage(inv),
                        )
                    tc_args, _ = _normalize_true_output_scalar_args(tc_inv, tc_args, {})
                    if _policy_block:
                        _tc_traced = {
                            "result_str": "",
                            "trace": {"backend": "policy", "blocked": True},
                        }
                        tool_result = (
                            f"Policy blocked write probe: {_policy_block['stop_reason']}"
                            f" ({_policy_block.get('detail') or 'no additional detail'})"
                        )
                    else:
                        _tc_traced = _execute_tool_traced(tc_inv, tc_args)
                        tool_result = _tc_traced["result_str"]

                    classification = _classify_result_text(str(tool_result), sentinels=ctx.sentinels)

                    if (
                        _is_write_fn and tc_name == fn_name
                        and classification.get("has_return")
                    ):
                        _ret_signed = int(classification.get("signed", 0))
                        if _ret_signed != 0:
                            _cls = _sentinel_class_from_classification(classification)
                            _write_retry_counts[_cls] += 1
                            _budget = _WRITE_RETRY_BUDGET_BY_CLASS.get(
                                _cls, _WRITE_RETRY_BUDGET_BY_CLASS["unknown"]
                            )
                            if _write_retry_counts[_cls] > _budget:
                                _policy_stop_reason = "policy_exhausted"
                                _pe = {
                                    "allowed": False,
                                    "stop_reason": _policy_stop_reason,
                                    "detail": (
                                        f"retry budget exceeded for class={_cls} "
                                        f"({_write_retry_counts[_cls]}/{_budget})"
                                    ),
                                    "sentinel_class": _cls,
                                }
                                _policy_events.append(_pe)

                    _llm_result = tool_result
                    if classification.get("has_return"):
                        _llm_result += (
                            "\n[CLASSIFICATION] "
                            f"format={classification.get('format_guess')} "
                            f"confidence={classification.get('confidence')} "
                            f"source={classification.get('source')} "
                            f"signed={classification.get('signed')} "
                            f"unsigned={classification.get('unsigned')} "
                            f"hex={classification.get('hex')} "
                            f"meaning={classification.get('meaning') or 'unknown'}"
                        )

                    _arg_sources = {
                        k: _classify_arg_source(k, v, inv, _vocab_snap)
                        for k, v in tc_args.items()
                    }
                    _fn_probe_log.append({
                        "probe_id": f"{fn_name}:{_round}:{_fn_tool_call_count + 1}:{tc_name}",
                        "phase": "explore", "function": fn_name, "round": _round,
                        "reasoning": (msg.content or "").strip() or None,
                        "tool": tc_name, "args": tc_args,
                        "arg_sources": _arg_sources,
                        "result_excerpt": str(tool_result)[:200],
                        "result_truncated": len(str(tool_result)) > 200,
                        "trace": _tc_traced.get("trace"),
                        "classification": classification, "policy": _policy_block,
                    })

                    # Accumulate non-zero return codes into the cross-function sentinel catalog
                    if classification.get("has_return") and classification.get("signed", 0) != 0:
                        _hex = str(classification.get("hex"))
                        _arg_shape = sorted(list(tc_args.keys()))
                        with ctx._lock:
                            _cat = ctx.sentinel_catalog.setdefault(_hex, {
                                "hex": _hex,
                                "unsigned": classification.get("unsigned"),
                                "format_guess": classification.get("format_guess"),
                                "confidence": classification.get("confidence"),
                                "source": classification.get("source"),
                                "meaning": classification.get("meaning") or "unknown",
                                "rationale_summary": (
                                    f"{classification.get('format_guess')} from "
                                    f"{classification.get('source')}; "
                                    f"meaning={classification.get('meaning') or 'unknown'}"
                                ),
                                "evidence_count": 0, "evidence_refs": [],
                                "functions": [], "arg_shapes": [],
                                "phases": [], "provisional": True,
                            })
                            _cat["evidence_count"] = int(_cat.get("evidence_count", 0)) + 1
                            if fn_name not in _cat["functions"]:
                                _cat["functions"].append(fn_name)
                            _shape_s = ",".join(_arg_shape)
                            if _shape_s not in _cat["arg_shapes"]:
                                _cat["arg_shapes"].append(_shape_s)
                            if "explore" not in _cat["phases"]:
                                _cat["phases"].append("explore")
                            _probe_ref = f"{fn_name}:{_round}:{_fn_tool_call_count + 1}:{tc_name}"
                            if _probe_ref not in _cat["evidence_refs"]:
                                _cat["evidence_refs"].append(_probe_ref)
                            _conf_now = float(classification.get("confidence") or 0.0)
                            _src_now = str(classification.get("source") or "")
                            _strong_det = (
                                _src_now.startswith("deterministic.") and _conf_now >= 0.95
                            )
                            _stable = _conf_now >= 0.85 and int(_cat["evidence_count"]) >= 2
                            _cat["provisional"] = not (_strong_det or _stable)

                except Exception as exc:
                    tool_result = f"Tool error: {exc}"
                    _llm_result = tool_result
            else:
                tool_result = f"Tool '{tc_name}' not found."
                _llm_result = tool_result

            _fn_tool_call_count += 1

            if tc_name == "enrich_invocable":
                _enrich_called = True
            elif tc_name == "record_finding":
                _finding_recorded = True

            # Harvest evidence from all successful calls (including non-target)
            if tc_name not in ("enrich_invocable", "record_finding") and tc_inv is not None:
                if _is_runtime_success_value(
                    tc_inv,
                    tc_name,
                    tool_result or "",
                    ctx.sentinels,
                    bool(_VERSION_FN_RE.search(tc_name)),
                ):
                    _ecr = getattr(ctx, "evidence_candidates", None)
                    if _ecr is not None and tc_name != fn_name:
                        _tc_lookup = {
                            p.get("name", ""): p for p in (tc_inv.get("parameters") or [])
                            if isinstance(p, dict)
                        }
                        _merged_nontarget = _merge_runtime_success_values(
                            tc_inv,
                            tc_name,
                            tc_args,
                            tool_result or "",
                            _tc_lookup,
                            ctx.sentinels,
                        )
                        _id_fmts = [str(x) for x in (ctx.vocab.get("id_formats") or []) if x]
                        _ecr.harvest_from_result(
                            function_name=tc_name,
                            result_str=tool_result or "",
                            trace=_tc_traced.get("trace") if isinstance(_tc_traced, dict) else None,
                            working_args=_merged_nontarget,
                            id_formats=_id_fmts,
                            param_lookup=_tc_lookup,
                        )
                        if _INIT_RE.search(tc_name):
                            _ecr.mark_init_satisfied(tc_name)

            if tc_name == fn_name:
                _direct_target_tool_calls += 1
                if _is_runtime_success_value(inv, tc_name, tool_result or "", ctx.sentinels, _is_version_fn):
                    _stripped_args = _strip_output_buffer_params(tc_args, _p_lookup)
                    _merged_success = _merge_runtime_success_values(
                        inv,
                        tc_name,
                        _stripped_args,
                        tool_result or "",
                        _p_lookup,
                        ctx.sentinels,
                    )
                    _observed_successes.append(_merged_success)
                    _best_raw_result = tool_result
                    _ecr = getattr(ctx, "evidence_candidates", None)
                    if _ecr is not None:
                        _id_fmts = [str(x) for x in (ctx.vocab.get("id_formats") or []) if x]
                        _ecr.harvest_from_result(
                            function_name=tc_name,
                            result_str=tool_result or "",
                            trace=_tc_traced.get("trace") if isinstance(_tc_traced, dict) else None,
                            working_args=_merged_success,
                            id_formats=_id_fmts,
                            param_lookup=_p_lookup,
                        )
                        if _INIT_RE.search(tc_name):
                            _ecr.mark_init_satisfied(tc_name)

            logger.info("[%s] explore_worker: tool=%s result=%s",
                        ctx.job_id, tc_name, str(tool_result)[:120])

            conversation.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": _llm_result,
            })

            if _policy_stop_reason in {"policy_exhausted", "dependency_missing"}:
                break
            if _policy_stop_reason == "schema_missing":
                # Don't terminate the tool-call loop: give the LLM another
                # round to retry with proper args.  Clear the stop reason so
                # the next round isn't pre-empted.
                _policy_stop_reason = ""
                break
            if _fn_tool_call_count >= _effective_max_tool_calls:
                break

        if _policy_stop_reason in {"policy_exhausted", "dependency_missing"}:
            logger.info("[%s] explore_worker: %s stopped by write policy (%s)",
                        ctx.job_id, fn_name, _policy_stop_reason)
            break

    # ── Deterministic fallback (defined after main loop so it can mutate locals above) ──

    def _run_deterministic_fallback(reason: str, max_attempts: int) -> None:
        nonlocal _fn_tool_call_count, _direct_target_tool_calls, _best_raw_result
        _is_floor_enforcement = reason.startswith("direct probe floor unmet")
        if (
            (not ctx.runtime.deterministic_fallback_enabled and not _is_floor_enforcement)
            or max_attempts <= 0
        ):
            return
        for _attempt in range(max_attempts):
            if _tool_call_cap_reached(allow_direct_probe_floor=_is_floor_enforcement):
                break
            _fb_args, _fb_selection = _build_ranked_fallback_probe_args(
                inv, _vocab_snap, attempt=_attempt,
                evidence=getattr(ctx, "evidence_candidates", None),
            )
            if _has_structured_fallback:
                _fb_args, _fb_selection = _repair_target_structured_args(
                    inv,
                    _fb_args,
                    _fb_selection,
                    _structured_probe_args,
                    _structured_selection,
                )
            _current_hints = _current_lineage_hints()
            _fb_args, _fb_selection = _repair_target_scalar_args(
                inv,
                _fb_args,
                _fb_selection,
                _vocab_snap,
                getattr(ctx, "evidence_candidates", None),
                lineage_hints=_current_hints,
                prefer_lineage=_requires_fresh_runtime_lineage(inv),
            )
            _fb_args, _fb_selection = _normalize_true_output_scalar_args(inv, _fb_args, _fb_selection)
            _observer_results = observe_lineage_handoff(
                contract_name="dense-context lineage isolation",
                consumer_function=fn_name,
                consumer_args=_fb_args,
                arg_selection=_fb_selection,
                lineage_hints=_current_hints,
                param_lookup={str(p.get("name") or ""): p for p in (inv.get("parameters") or []) if isinstance(p, dict)},
            )
            _pb: dict | None = None
            if _is_write_fn:
                _ok, _reason, _detail = _write_policy_precheck(
                    fn_name, _fb_args, _vocab_snap, ctx.unlock_result,
                )
                if not _ok:
                    _pb = {"allowed": False, "stop_reason": _reason, "detail": _detail}
            if _pb:
                _arg_sources = {
                    k: _classify_arg_source(k, v, inv, _vocab_snap)
                    for k, v in _fb_args.items()
                }
                _fn_probe_log.append({
                    "phase": "deterministic_fallback", "function": fn_name,
                    "round": _attempt, "reasoning": reason, "tool": fn_name,
                    "args": _fb_args,
                    "arg_sources": _arg_sources,
                    "arg_selection": _fb_selection,
                    "result_excerpt": f"Policy blocked fallback probe: {_pb['stop_reason']}",
                    "trace": {"backend": "policy", "blocked": True},
                    "classification": {"has_return": False}, "policy": _pb,
                })
                continue
            _arg_sources = {
                k: _classify_arg_source(k, v, inv, _vocab_snap)
                for k, v in _fb_args.items()
            }
            _tc = _execute_tool_traced(ctx.inv_map[fn_name], _fb_args)
            _res = _tc["result_str"]
            _cls = _classify_result_text(str(_res), sentinels=ctx.sentinels)
            _arg_sources = {
                k: _classify_arg_source(k, v, inv, _vocab_snap)
                for k, v in _fb_args.items()
            }
            _fallback_log = {
                "probe_id": f"{fn_name}:fb:{_attempt + 1}",
                "phase": "deterministic_fallback", "function": fn_name,
                "round": _attempt, "reasoning": reason, "tool": fn_name,
                "args": _fb_args, "result_excerpt": str(_res)[:200],
                "arg_sources": _arg_sources,
                "arg_selection": _fb_selection,
                "trace": _tc.get("trace"), "classification": _cls, "policy": None,
            }
            if _observer_results:
                _fallback_log["observer_results"] = _observer_results
            _fn_probe_log.append(_fallback_log)
            _fn_tool_call_count += 1
            _direct_target_tool_calls += 1
            if _is_runtime_success_value(inv, fn_name, _res, ctx.sentinels, _is_version_fn):
                _merged_success = _merge_runtime_success_values(
                    inv,
                    fn_name,
                    _fb_args,
                    _res,
                    _p_lookup,
                    ctx.sentinels,
                )
                _observed_successes.append(_merged_success)
                _best_raw_result = _res
                _ecr = getattr(ctx, "evidence_candidates", None)
                if _ecr is not None:
                    _id_fmts = [str(x) for x in (ctx.vocab.get("id_formats") or []) if x]
                    _ecr.harvest_from_result(
                        function_name=fn_name,
                        result_str=_res or "",
                        trace=_tc.get("trace"),
                        working_args=_merged_success,
                        id_formats=_id_fmts,
                        param_lookup=_p_lookup,
                    )
                    if _INIT_RE.search(fn_name):
                        _ecr.mark_init_satisfied(fn_name)
                break

    # ── Post-loop: direct probe floor enforcement ────────────────────────────

    _missing_direct_calls = max(0, ctx.runtime.min_direct_probes - _direct_target_tool_calls)
    if _missing_direct_calls > 0:
        _run_deterministic_fallback(
            f"direct probe floor unmet ({_direct_target_tool_calls}/{ctx.runtime.min_direct_probes})",
            _missing_direct_calls,
        )

    if _has_structured_fallback and not _observed_successes:
        _run_deterministic_fallback("structured scaffold coverage", 1)

    if _is_write_fn and not _observed_successes:
        _run_deterministic_fallback("write function fallback coverage", 2)

    # Safety net: scan probe log for a target success outcome
    # that _observed_successes might have missed (e.g., 429 killed the round
    # between the tool execution and the success tracking).
    if not _observed_successes:
        for _pe in _fn_probe_log:
            if _pe.get("tool") != fn_name:
                continue
            _rex = _pe.get("result_excerpt") or ""
            if _is_runtime_success_value(inv, fn_name, _rex, ctx.sentinels, _is_version_fn):
                _recovered_args = _pe.get("args") or {}
                _merged_success = _merge_runtime_success_values(
                    inv,
                    fn_name,
                    _recovered_args,
                    _rex,
                    _p_lookup,
                    ctx.sentinels,
                )
                _observed_successes.append(_merged_success)
                _best_raw_result = _rex
                _ecr = getattr(ctx, "evidence_candidates", None)
                if _ecr is not None:
                    _id_fmts = [str(x) for x in (ctx.vocab.get("id_formats") or []) if x]
                    _ecr.harvest_from_result(
                        function_name=fn_name,
                        result_str=_rex,
                        trace=_pe.get("trace"),
                        working_args=_merged_success,
                        id_formats=_id_fmts,
                        param_lookup=_p_lookup,
                    )
                logger.info(
                    "[%s] explore_worker: recovered success for %s from probe log safety net",
                    ctx.job_id, fn_name,
                )
                break

    _best_success = _choose_best_observed_success(
        inv,
        _observed_successes,
        _vocab_snap,
        getattr(ctx, "evidence_candidates", None),
    )

    # ── Force record_finding if LLM never called it ──────────────────────────

    if not _finding_recorded and _best_success is not None:
        # D-8: Deterministic fallback got return=0 but LLM never called record_finding.
        try:
            _auto_finding = {
                "function": fn_name,
                "status": "verified_success",
                "finding": "Deterministic fallback probe returned 0.",
                "working_call": _best_success,
                "direct_target_truth": _build_direct_target_truth(
                    fn_name,
                    _best_success,
                    source="s02_auto_record",
                    phase="deterministic_fallback",
                    result_text=str(_best_raw_result or ""),
                ),
                "notes": (
                    "Auto-recorded: deterministic fallback succeeded "
                    "but LLM never called record_finding."
                ),
                "direct_target_tool_calls": _direct_target_tool_calls,
                "no_tool_call_rounds": _no_tool_call_rounds,
                "stop_reason": _policy_stop_reason,
            }
            _truth_assessment = assess_reusable_truth(_auto_finding, invocable=inv)
            if _truth_assessment.get("demote_success"):
                _auto_finding["status"] = "inferred_success"
                _auto_finding["notes"] = (
                    f"{_auto_finding['notes']} "
                    f"Demoted before reusable promotion: {', '.join(_truth_assessment.get('reasons') or ['low_expected_observed_alignment'])}."
                )
            _auto_finding["reusable_truth_eligible"] = bool(_truth_assessment.get("seed_eligible"))
            _auto_finding["reusable_truth_score"] = float(_truth_assessment.get("score") or 0.0)
            _auto_finding["reusable_truth_reasons"] = list(_truth_assessment.get("reasons") or [])
            _save_finding(ctx.job_id, _auto_finding)
            _finding_recorded = True
            logger.info("[%s] explore_worker: D-8 forced record_finding(success) for %s — working_call=%s",
                        ctx.job_id, fn_name, _best_success)
        except Exception as _frf:
            logger.debug("[%s] D-8 forced record_finding failed for %s: %s",
                         ctx.job_id, fn_name, _frf)
    elif not _finding_recorded and not _observed_successes:
        _existing_success = next(
            (
                f for f in reversed(_load_findings(ctx.job_id))
                if f.get("function") == fn_name
                and str(f.get("status_canonical") or f.get("status") or "") == "verified_success"
            ),
            None,
        )
        if _existing_success is not None:
            _finding_recorded = True
            logger.info("[%s] explore_worker: preserved prior same-run verified success for %s",
                        ctx.job_id, fn_name)
        else:
            # Collect sentinel codes seen across all probes for this function
            _seen_codes = set()
            _seen_meanings = []
            for _pe in _fn_probe_log:
                _rex = (_pe.get("result_excerpt") or "")
                _rm = _re.search(r"Returned:\s*(-?\d+)", _rex)
                if _rm:
                    _rv = int(_rm.group(1))
                    if _rv != 0:
                        _seen_codes.add(hex(_rv) if _rv > 0xFFFFFFF0 else str(_rv))
                        _meaning = (ctx.sentinels.get(_rv & 0xFFFFFFFF) or "")
                        if _meaning:
                            _seen_meanings.append(str(_meaning))
            _code_str = ", ".join(sorted(_seen_codes)) or "unknown"
            _functional_hit = any(is_functional_precondition_text(_m) for _m in _seen_meanings)
            _forced_status = "functional_precondition_unmet" if _functional_hit else "failure"
            try:
                _policy_note = (
                    f" Stop reason: {_policy_stop_reason}." if _policy_stop_reason else ""
                )
                _save_finding(ctx.job_id, {
                    "function": fn_name, "status": _forced_status,
                    "finding": (
                        f"All {_fn_tool_call_count} probes returned sentinel codes: "
                        f"{_code_str}. No working call found.{_policy_note}"
                    ),
                    "working_call": None,
                    "notes": (
                        f"Auto-recorded: LLM exhausted {_fn_tool_call_count} tool calls "
                        "without calling record_finding."
                    ),
                    "direct_target_tool_calls": _direct_target_tool_calls,
                    "no_tool_call_rounds": _no_tool_call_rounds,
                    "stop_reason": _policy_stop_reason,
                    "write_policy_events": _policy_events,
                })
                _finding_recorded = True
                logger.info("[%s] explore_worker: forced record_finding(%s) for %s — codes: %s",
                            ctx.job_id, _forced_status, fn_name, _code_str)
            except Exception as _frf:
                logger.debug("[%s] forced record_finding failed for %s: %s",
                             ctx.job_id, fn_name, _frf)

    # Force enrich_invocable if the model skipped it and the function has params
    if not _enrich_called and inv.get("parameters"):
        _cur_findings = _load_findings(ctx.job_id)
        _last_f = next(
            (f for f in reversed(_cur_findings) if f.get("function") == fn_name), None
        )
        _finding_summary = (
            f"Finding: {_last_f.get('finding', '')}. Notes: {_last_f.get('notes', '')}"
            if _last_f else "No finding recorded."
        )
        try:
            from typing import cast, Any as _Any
            _enrich_resp = ctx.client.chat.completions.create(
                model=ctx.model,
                messages=conversation + [{
                    "role": "user",
                    "content": (
                        f"You did not call enrich_invocable for '{fn_name}'. "
                        f"Based on what you observed, call it now. "
                        "Rename each param_N to a semantic name (e.g. customer_id, balance, "
                        "output_buffer). For each parameter description, write what it does AND "
                        "include an example value from your testing. "
                        "Set the function description to a clear one-sentence summary. "
                        f"{_finding_summary}"
                    ),
                }],
                tools=cast(_Any, ctx.tool_schemas),
                tool_choice={"type": "function", "function": {"name": "enrich_invocable"}},
                temperature=0,
                timeout=90.0,
            )
            _em = _enrich_resp.choices[0].message
            if _em.tool_calls:
                _etc = _em.tool_calls[0]
                try:
                    _eargs = json.loads(_etc.function.arguments)  # type: ignore[union-attr]
                except json.JSONDecodeError:
                    _eargs = {}
                _execute_tool(ctx.inv_map["enrich_invocable"], _eargs)
                logger.info("[%s] explore_worker: forced enrich_invocable for %s",
                            ctx.job_id, fn_name)
                # Reasoning artifact: record param rename decisions from forced enrich.
                # Maps original Ghidra param names to what the model proposed.
                # Writes to evidence/stage-02-probe-loop/param-rename-decisions.json.
                try:
                    _original_params = {
                        p.get("name", ""): p.get("type", "")
                        for p in (inv.get("parameters") or [])
                        if isinstance(p, dict)
                    }
                    _rename_entry = {
                        "function": fn_name,
                        "original_params": _original_params,
                        "proposed_description": _eargs.get("description", ""),
                        "proposed_enrich_args": _eargs,
                    }
                    _rename_blob = (
                        f"{ctx.job_id}/evidence/stage-02-probe-loop/param-rename-decisions.json"
                    )
                    try:
                        _existing_renames = json.loads(
                            _download_blob(ARTIFACT_CONTAINER, _rename_blob)
                        )
                    except Exception:
                        _existing_renames = []
                    _existing_renames.append(_rename_entry)
                    _upload_to_blob(
                        ARTIFACT_CONTAINER, _rename_blob,
                        json.dumps(_existing_renames, indent=2).encode(),
                    )
                except Exception as _rde:
                    logger.debug("[%s] param-rename-decisions write failed for %s: %s",
                                 ctx.job_id, fn_name, _rde)
        except Exception as _ee:
            logger.debug("[%s] forced enrich failed for %s: %s", ctx.job_id, fn_name, _ee)

    # Update shared progress counter (thread-safe)
    with ctx._lock:
        _explored_now = ctx.increment_explored()
        ctx.already_explored.add(fn_name)
    _set_explore_status(
        ctx.job_id,
        _explored_now,
        ctx.total,
        f"Completed {fn_name}",
        stage="s02_invocation_execution",
    )

    # ── Ground-truth override (D-11) ─────────────────────────────────────────

    if _best_success is not None:
        # We observed return=0 or a valid version uint → force success and rewrite
        # finding text so synthesis doesn't see "All N probes returned sentinel codes"
        # for a function that actually works.
        _success_val_m = _re.search(r"Returned:\s*(-?\d+)", _best_raw_result or "")
        _success_val = int(_success_val_m.group(1)) if _success_val_m else 0
        _handle_return = _runtime_return_artifacts(inv, fn_name, _best_raw_result or "", ctx.sentinels).get("handle")
        if _is_version_fn and _success_val > 0:
            # Decode packed version UINT: (val>>16)&0xFF . (val>>8)&0xFF . val&0xFF
            _v_uval = _success_val & 0xFFFFFFFF
            _v_str = f"{(_v_uval >> 16) & 0xFF}.{(_v_uval >> 8) & 0xFF}.{_v_uval & 0xFF}"
            _gt_text = (
                f"Returns packed version UINT {_success_val} (decoded: {_v_str}) "
                f"when called with {_best_success}. Non-zero return is SUCCESS for version functions."
            )
        elif _handle_return is not None:
            _gt_text = (
                f"Returns live opaque handle {_handle_return} when called with {_best_success}. "
                f"That non-sentinel handle is treated as SUCCESS for creator/open/init functions."
            )
        else:
            _gt_text = (
                f"Returns 0 on success when called with {_best_success}. "
                f"Discovered via deterministic fallback (direct LLM probes: {_direct_target_tool_calls})."
            )
        try:
            _patch_finding(ctx.job_id, fn_name, {
                "working_call": _best_success,
                "status": "verified_success",
                "stop_reason": "success",
                "finding": _gt_text,
                "direct_target_truth": _build_direct_target_truth(
                    fn_name,
                    _best_success,
                    source="s02_ground_truth_override",
                    phase="deterministic_fallback",
                    result_text=str(_best_raw_result or ""),
                ),
            })
            logger.info("[%s] explore_worker: ground-truth override for %s working_call=%s",
                        ctx.job_id, fn_name, _best_success)
        except Exception as _ce:
            logger.debug("[%s] consistency patch failed for %s: %s", ctx.job_id, fn_name, _ce)

        # BUG-001 fix: propagate this success into live_findings so subsequent
        # functions in the same probe loop see it immediately as context.
        with ctx._lock:
            ctx.live_findings.append({
                "function": fn_name,
                "status": "verified_success",
                "finding": _gt_text,
                "working_call": _best_success,
            })
    else:
        # Reasoning artifact: sentinel calibration decisions with coverage metadata.
        # Writes to evidence/stage-00-calibrate/sentinel-calibration-decisions.json.
        try:
            _calib_decision = {
                "functions_calibrated": len(ctx.invocables),
                "sentinel_count": len(ctx.sentinels),
                "used_defaults": ctx.sentinels == _SENTINEL_DEFAULTS,
                "sentinels_resolved": {
                    f"0x{k:08X}": v for k, v in ctx.sentinels.items()
                },
            }
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{ctx.job_id}/evidence/stage-00-calibrate/sentinel-calibration-decisions.json",
                json.dumps(_calib_decision, indent=2).encode(),
            )
        except Exception as _cde:
            logger.debug("[%s] phase0.5: sentinel-calibration-decisions write failed: %s",
                         ctx.job_id, _cde)
        # Verify the LLM's claimed working_call by re-running it
        _cur = _load_findings(ctx.job_id)
        _ff = next((f for f in reversed(_cur) if f.get("function") == fn_name), None)
        if _ff and _ff.get("working_call") is not None:
            _vi = ctx.inv_map.get(fn_name)
            if _vi:
                try:
                    _verify_p_lookup = {
                        str(param.get("name") or ""): param
                        for param in (_vi.get("parameters") or [])
                        if isinstance(param, dict) and str(param.get("name") or "")
                    }
                    _vt = _execute_tool_traced(_vi, _ff["working_call"])
                    _vr = _vt["result_str"]
                    _vr_class = _classify_result_text(str(_vr), sentinels=ctx.sentinels)
                    _verify_args = _ff["working_call"]
                    _arg_sources = {
                        k: _classify_arg_source(k, v, _vi, _vocab_snap)
                        for k, v in _verify_args.items()
                    }
                    _fn_probe_log.append({
                        "phase": "verify", "function": fn_name, "tool": fn_name,
                        "args": _verify_args,
                        "arg_sources": _arg_sources,
                        "result_excerpt": str(_vr)[:200],
                        "trace": _vt.get("trace"), "classification": _vr_class, "policy": None,
                    })
                    if _is_runtime_success_value(_vi, fn_name, _vr or "", ctx.sentinels, _is_version_fn):
                        _vret_raw = _parse_runtime_return_value(_vr or "")
                        _vret = (_vret_raw & 0xFFFFFFFF) if _vret_raw is not None else 0
                        _verified_success = _merge_runtime_success_values(
                            _vi,
                            fn_name,
                            _verify_args,
                            _vr or "",
                            _verify_p_lookup,
                            ctx.sentinels,
                        )
                        if _runtime_return_artifacts(_vi, fn_name, _vr or "", ctx.sentinels).get("handle") is not None:
                            _verify_text = (
                                f"Verified: returned opaque handle {_vret_raw} with {_verified_success}"
                            )
                        else:
                            _verify_text = f"Verified: returns {_vret} with {_verified_success}"
                        _patch_finding(ctx.job_id, fn_name,
                                       {
                                           "working_call": _verified_success,
                                           "status": "verified_success",
                                           "stop_reason": "success",
                                           "verification": "verified",
                                           "direct_target_truth": _build_direct_target_truth(
                                               fn_name,
                                               _verified_success,
                                               source="s02_verify_replay",
                                               phase="verify",
                                               result_text=str(_vr or ""),
                                               verification="verified",
                                           ),
                                       })
                        with ctx._lock:
                            ctx.live_findings.append({
                                "function": fn_name,
                                "status": "verified_success",
                                "finding": _verify_text,
                                "working_call": _verified_success,
                            })
                    else:
                        _vret_raw = _parse_runtime_return_value(_vr or "")
                        _vret = (_vret_raw & 0xFFFFFFFF) if _vret_raw is not None else 0
                        _meaning = str(ctx.sentinels.get(_vret) or "")
                        _is_functional = is_functional_precondition_text(_meaning)
                        _patch_finding(ctx.job_id, fn_name, {
                            "working_call": None,
                            "status": "functional_precondition_unmet" if _is_functional else "failure",
                            "stop_reason": _policy_stop_reason or "policy_exhausted",
                            "verification": "state_drift",
                            "direct_target_truth_rejected_reason": (
                                f"verify_replay returned {_vret_raw} after prior direct-target success"
                            ),
                            "direct_target_truth": _build_direct_target_truth(
                                fn_name,
                                _ff["working_call"],
                                source="s02_verify_replay",
                                phase="verify",
                                result_text=str(_vr or ""),
                                verification="state_drift",
                            ),
                        })
                        logger.info("[%s] explore_worker: discarded hallucinated working_call for %s",
                                    ctx.job_id, fn_name)
                except Exception as _ve:
                    logger.debug("[%s] working_call verify failed for %s: %s",
                                 ctx.job_id, fn_name, _ve)

    # ── D-12: Auto-enrich schema when LLM skipped enrich_invocable ──────────
    # If the LLM never called enrich_invocable (e.g. all LLM rounds failed and
    # only the deterministic fallback ran), synthesise param descriptions from
    # Ghidra type info + probe findings so the schema isn't left as raw Ghidra
    # boilerplate.  Only fires when the description is still the default Ghidra
    # annotation — never overwrites a description the LLM set.

    if not _enrich_called:
        try:
            from api.pipeline.core.helpers import _infer_param_desc
            _cur_findings = _load_findings(ctx.job_id)
            _fn_findings = [f for f in _cur_findings if f.get("function") == fn_name]
            _auto_patch: dict = {}
            _cur_desc = (inv.get("description") or inv.get("doc") or "").strip()
            _is_ghidra = (
                _cur_desc.lower().startswith("recovered by ghidra")
                or not _cur_desc
            )
            # Build param-level patches first
            for _p in (inv.get("parameters") or []):
                _pname = _p.get("name", "")
                _ptype = _p.get("type", "")
                _pdesc = (_p.get("description") or "").strip()
                _pdesc_generic = (
                    not _pdesc
                    or _pdesc.lower().startswith("input ")
                    or _pdesc.lower().startswith("output ")
                    or _pdesc.lower().startswith("parameter of type")
                    or len(_pdesc) < 8
                )
                if _pdesc_generic:
                    _inferred = _infer_param_desc(_pname, _ptype, _fn_findings)
                    if _inferred and not _inferred.startswith("Parameter of type"):
                        _auto_patch[_pname] = {"description": _inferred}
            # Set a minimal function description from the finding text if still Ghidra
            if _is_ghidra and _fn_findings:
                _latest = _fn_findings[-1]
                _finding_text = (_latest.get("finding") or "").strip()
                if _finding_text and len(_finding_text) > 20:
                    _auto_patch["function_description"] = _finding_text[:300]
            if _auto_patch:
                _patch_invocable(ctx.job_id, fn_name, _auto_patch)
                logger.info("[%s] D-12: auto-enriched %s (%d fields)",
                            ctx.job_id, fn_name, len(_auto_patch))
        except Exception as _ae:
            logger.debug("[%s] D-12 auto-enrich failed for %s: %s",
                         ctx.job_id, fn_name, _ae)

    # ── Hypothesis-driven interpretation ─────────────────────────────────────

    if _best_raw_result:
        try:
            _hyp = _generate_hypothesis(
                ctx.client, ctx.model, fn_name,
                _best_raw_result, _vocab_snap, _load_findings(ctx.job_id),
            )
            if _hyp.get("interpretations"):
                _patch_finding(ctx.job_id, fn_name,
                               {"interpretation": _hyp["interpretations"]})
                if "value_semantics" not in _vocab_snap:
                    _vocab_snap["value_semantics"] = {}
                _vocab_snap["value_semantics"].update(_hyp["interpretations"])
                logger.info("[%s] hypothesis for %s: %s",
                            ctx.job_id, fn_name, _hyp["interpretations"])
            _cv = _hyp.get("cross_validation")
            if (
                _cv and isinstance(_cv, dict)
                and _cv.get("function") in ctx.inv_map
                and _cv.get("function") in ctx.already_explored
            ):
                _cv_inv = ctx.inv_map[_cv["function"]]
                _cvt = _execute_tool_traced(_cv_inv, _cv.get("args") or {})
                _cv_result = _cvt["result_str"]
                _cv_class = _classify_result_text(str(_cv_result), sentinels=ctx.sentinels)
                _cv_args = _cv.get("args") or {}
                _arg_sources = {
                    k: _classify_arg_source(k, v, _cv_inv, _vocab_snap)
                    for k, v in _cv_args.items()
                }
                _fn_probe_log.append({
                    "phase": "cross_validate", "function": fn_name,
                    "tool": _cv["function"], "args": _cv_args,
                    "arg_sources": _arg_sources,
                    "result_excerpt": str(_cv_result)[:200],
                    "trace": _cvt.get("trace"), "classification": _cv_class, "policy": None,
                })
                _patch_finding(ctx.job_id, fn_name, {
                    "cross_validation": (
                        f"{_cv['function']}({_cv.get('args')}) → {_cv_result}"
                    ),
                })
                logger.info("[%s] cross-validated %s via %s: %s",
                            ctx.job_id, fn_name, _cv["function"], str(_cv_result)[:80])
        except Exception as _hyp_e:
            logger.debug("[%s] hypothesis failed for %s: %s", ctx.job_id, fn_name, _hyp_e)

    # ── Vocab update from this function's finding ────────────────────────────

    last_finding = _load_findings(ctx.job_id)
    if last_finding:
        last = next((f for f in reversed(last_finding) if f.get("function") == fn_name), None)
        if last:
            try:
                # Mutates _vocab_snap in-place; merge learned facts into shared vocab
                _update_vocabulary(ctx.client, ctx.model, _vocab_snap, last)
                with ctx._lock:
                    for _mk, _mv in _vocab_snap.items():
                        if _mk.startswith("_"):
                            continue
                        if isinstance(_mv, list) and isinstance(ctx.vocab.get(_mk), list):
                            _existing = set(map(str, ctx.vocab[_mk]))
                            ctx.vocab[_mk] = ctx.vocab[_mk] + [
                                x for x in _mv if str(x) not in _existing
                            ]
                        elif isinstance(_mv, dict) and isinstance(ctx.vocab.get(_mk), dict):
                            ctx.vocab[_mk].update(_mv)
                        elif _mv and _mk not in ctx.vocab:
                            ctx.vocab[_mk] = _mv
                # Persist updated vocab to blob so next session starts informed
                try:
                    _upload_to_blob(
                        ARTIFACT_CONTAINER,
                        f"{ctx.job_id}/vocab.json",
                        json.dumps(_vocab_snap).encode(),
                    )
                except Exception as _vpe:
                    logger.debug("[%s] vocab persist failed: %s", ctx.job_id, _vpe)
            except Exception as _ve:
                logger.debug("[%s] vocab update failed for %s: %s", ctx.job_id, fn_name, _ve)

    # ── Flush probe log for this function ────────────────────────────────────

    # Reasoning artifact: persist model's per-round reasoning text for this function.
    # Extracts all assistant messages from the conversation that preceded tool calls.
    # Writes to evidence/stage-02-probe-loop/probe-round-reasoning.json (appended per function).
    try:
        _round_reasoning_entries = []
        _conv_round = 0
        for _cm in conversation:
            if _cm.get("role") == "assistant":
                _reasoning_text = (_cm.get("content") or "").strip()
                if _reasoning_text:
                    _round_reasoning_entries.append({
                        "function": fn_name,
                        "round": _conv_round,
                        "reasoning": _reasoning_text,
                    })
                _conv_round += 1
        if not _round_reasoning_entries:
            _round_reasoning_entries.append({
                "function": fn_name,
                "round": 0,
                "reasoning": "(model went directly to tool calls without text reasoning)",
            })
        _reasoning_blob = (
            f"{ctx.job_id}/evidence/stage-02-probe-loop/probe-round-reasoning.json"
        )
        try:
            _existing_raw = _download_blob(ARTIFACT_CONTAINER, _reasoning_blob)
            _existing = json.loads(_existing_raw)
        except Exception:
            _existing = []
        _existing.extend(_round_reasoning_entries)
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            _reasoning_blob,
            json.dumps(_existing, indent=2).encode(),
        )
    except Exception as _rre:
        logger.debug("[%s] probe-round-reasoning write failed for %s: %s",
                     ctx.job_id, fn_name, _rre)

    # Reasoning artifact: persist probe stop reason for this function.
    # Writes to evidence/stage-02-probe-loop/probe-stop-reasons.json (appended per function).
    try:
        # Determine stop reason from local state
        if _policy_stop_reason:
            _computed_stop_reason = _policy_stop_reason
        elif _fn_tool_call_count >= _effective_max_tool_calls:
            _computed_stop_reason = "cap_hit_tool_calls"
        elif _cancel_requested(ctx.job_id):
            _computed_stop_reason = "cancel"
        else:
            _computed_stop_reason = "natural"

        # Get model's final summary sentence (last assistant message)
        _final_summary = ""
        for _cm in reversed(conversation):
            if _cm.get("role") == "assistant" and (_cm.get("content") or "").strip():
                _final_summary = (_cm.get("content") or "").strip()
                break

        _stop_entry = {
            "function": fn_name,
            "stop_reason": _computed_stop_reason,
            "rounds_used": sum(1 for _cm in conversation if _cm.get("role") == "assistant"),
            "tool_calls_used": _fn_tool_call_count,
            "direct_target_calls": _direct_target_tool_calls,
            "final_summary": _final_summary[:300] if _final_summary else None,
        }
        _stop_blob = (
            f"{ctx.job_id}/evidence/stage-02-probe-loop/probe-stop-reasons.json"
        )
        try:
            _existing_stops_raw = _download_blob(ARTIFACT_CONTAINER, _stop_blob)
            _existing_stops = json.loads(_existing_stops_raw)
        except Exception:
            _existing_stops = []
        _existing_stops.append(_stop_entry)
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            _stop_blob,
            json.dumps(_existing_stops, indent=2).encode(),
        )
    except Exception as _sre:
        logger.debug("[%s] probe-stop-reasons write failed for %s: %s",
                     ctx.job_id, fn_name, _sre)

    # Reasoning artifact: probe strategy summary — which strategies fired per function.
    # Writes to evidence/stage-02-probe-loop/probe-strategy-summary.json (appended per function).
    try:
        _phases_used = sorted({e.get("phase", "unknown") for e in _fn_probe_log})
        _strategy_entry = {
            "function": fn_name,
            "phases_used": _phases_used,
            "rounds_used": sum(1 for m in conversation if m.get("role") == "assistant"),
            "tool_calls_used": _fn_tool_call_count,
            "direct_target_calls": _direct_target_tool_calls,
            "no_tool_call_rounds": _no_tool_call_rounds,
            "deterministic_fallback_fired": any(
                e.get("phase") == "deterministic_fallback" for e in _fn_probe_log
            ),
            "cross_validation_ran": any(
                e.get("phase") == "cross_validate" for e in _fn_probe_log
            ),
            "hypothesis_ran": bool(_best_raw_result),
            "is_write_fn": _is_write_fn,
            "enrich_called": _enrich_called,
            "finding_recorded": _finding_recorded,
            "stop_reason": _policy_stop_reason or (
                "cap_hit_tool_calls"
                if _fn_tool_call_count >= _effective_max_tool_calls
                else "natural"
            ),
        }
        _strategy_blob = (
            f"{ctx.job_id}/evidence/stage-02-probe-loop/probe-strategy-summary.json"
        )
        try:
            _existing_strats = json.loads(
                _download_blob(ARTIFACT_CONTAINER, _strategy_blob)
            )
        except Exception:
            _existing_strats = []
        _existing_strats.append(_strategy_entry)
        _upload_to_blob(
            ARTIFACT_CONTAINER, _strategy_blob,
            json.dumps(_existing_strats, indent=2).encode(),
        )
    except Exception as _psume:
        logger.debug("[%s] probe-strategy-summary write failed for %s: %s",
                     ctx.job_id, fn_name, _psume)

    if _fn_probe_log:
        try:
            _append_explore_probe_log(ctx.job_id, _fn_probe_log)
        except Exception as _ple:
            logger.debug("[%s] explore probe log flush failed for %s: %s",
                         ctx.job_id, fn_name, _ple)

    # Record function-level checkpoint for resumable runs
    try:
        from api.pipeline.core.checkpoint import record_function_checkpoint
        _final_findings = _load_findings(ctx.job_id)
        _fn_finding = next(
            (f for f in reversed(_final_findings) if f.get("function") == fn_name), None
        )
        if _fn_finding and hasattr(ctx, "_checkpoint") and ctx._checkpoint is not None:
            record_function_checkpoint(
                ctx._checkpoint,
                fn_name,
                status=_fn_finding.get("status_canonical") or _fn_finding.get("status", "failure"),
                working_call=_fn_finding.get("working_call"),
                finding=str(_fn_finding.get("notes", ""))[:500],
                stage="s02",
            )
    except Exception as _cpe:
        logger.debug("[%s] function checkpoint failed for %s: %s",
                     ctx.job_id, fn_name, _cpe)


def _run_phase_3_probe_loop(ctx: ExploreContext) -> None:
    """Dispatch _explore_one for each invocable — parallel if concurrency > 1.

    READS:  ctx.invocables, ctx.runtime.concurrency
    WRITES: ctx._state, ctx.sentinel_catalog, ctx.already_explored (via _explore_one)
    INVARIANT: every invocable is processed exactly once (cancel may abort early)
    HANDOFF: explore_probe_log.json continuously flushed to blob by _explore_one
    """
    def _ensure_json_array_blob(blob_rel: str) -> None:
        full_blob = f"{ctx.job_id}/{blob_rel}"
        try:
            raw = _download_blob(ARTIFACT_CONTAINER, full_blob)
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return
        except Exception:
            pass
        try:
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                full_blob,
                json.dumps([], indent=2).encode("utf-8"),
            )
        except Exception as _arr_e:
            logger.debug("[%s] phase3: ensure %s failed: %s", ctx.job_id, blob_rel, _arr_e)

    # Ensure required reasoning artifacts exist deterministically, even when no
    # probe rounds run for a given function.
    _ensure_json_array_blob("evidence/stage-02-probe-loop/probe-round-reasoning.json")
    _ensure_json_array_blob("evidence/stage-02-probe-loop/probe-stop-reasons.json")
    _ensure_json_array_blob("evidence/stage-02-probe-loop/probe-strategy-summary.json")
    _ensure_json_array_blob("evidence/stage-02-probe-loop/param-rename-decisions.json")

    # Save probe-loop model context: the full system message the LLM will receive.
    # This captures variable parts (vocab, findings, sentinels) at probe-loop start.
    try:
        from api.infra.storage import _load_findings
        _ctx_prior = _load_findings(ctx.job_id)
        _ctx_sys = _build_explore_system_message(
            ctx.invocables, _ctx_prior,
            sentinels=ctx.sentinels, vocab=ctx.vocab,
            use_cases=ctx.use_cases_text,
        )
        _ctx_text = _ctx_sys.get("content", "")
        _save_stage_context(ctx.job_id, "model_context_phase_01_probe_loop.txt",
                            _ctx_text)
        try:
            # Canonical turn-0 system context used by strict save-session audits.
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{ctx.job_id}/chat_system_context_turn0.txt",
                (_ctx_text or "").encode("utf-8"),
            )
        except Exception as _ctxe:
            logger.debug("[%s] phase3: chat_system_context_turn0 persist failed: %s", ctx.job_id, _ctxe)
    except Exception as _mce:
        logger.debug("[%s] phase3: model context save failed: %s", ctx.job_id, _mce)

    # Small inter-function delay to spread LLM calls and avoid 429 bursts.
    # Write functions get longer delays since they use more LLM rounds.
    _INTER_FN_DELAY = 1.5  # seconds between non-write functions
    _WRITE_FN_DELAY = 3.0  # seconds between write functions

    _execution_layers = getattr(ctx, "_execution_layers", None) or getattr(ctx, "execution_layers", None)
    _ecr = getattr(ctx, "evidence_candidates", None)
    _focused = set(ctx.runtime.focus_functions or [])

    if ctx.runtime.concurrency > 1:
        logger.info("[%s] phase3: running %d functions with concurrency=%d",
                    ctx.job_id, len(ctx.invocables), ctx.runtime.concurrency)
        with _TPE(max_workers=ctx.runtime.concurrency) as _pool:
            list(_pool.map(lambda inv: _explore_one(inv, ctx), ctx.invocables))
    elif _execution_layers and _ecr is not None and len(_execution_layers) > 1:
        _fn_idx = 0
        for _layer_idx, _layer in enumerate(_execution_layers):
            if _cancel_requested(ctx.job_id):
                break
            _layer_inv_map = {inv["name"]: inv for inv in ctx.invocables}
            _layer_invs = [_layer_inv_map[n] for n in _layer if n in _layer_inv_map]
            _ecr_before = _ecr.stats().get("total_candidates", 0)
            logger.info(
                "[%s] phase3: multi-pass layer %d/%d — %d functions, ECR has %d candidates",
                ctx.job_id, _layer_idx + 1, len(_execution_layers),
                len(_layer_invs), _ecr_before,
            )
            for inv in _layer_invs:
                if _cancel_requested(ctx.job_id):
                    break
                if inv["name"] in ctx.already_explored and inv["name"] not in _focused:
                    continue
                if _fn_idx > 0:
                    _delay = _WRITE_FN_DELAY if _WRITE_FN_RE.search(inv["name"]) else _INTER_FN_DELAY
                    time.sleep(_delay)
                _explore_one(inv, ctx)
                _fn_idx += 1
            _ecr_after = _ecr.stats().get("total_candidates", 0)
            _new_evidence = _ecr_after - _ecr_before
            if _new_evidence > 0:
                logger.info(
                    "[%s] phase3: layer %d produced %d new evidence candidates (total: %d)",
                    ctx.job_id, _layer_idx + 1, _new_evidence, _ecr_after,
                )
    else:
        for _fn_idx, inv in enumerate(ctx.invocables):
            if _cancel_requested(ctx.job_id):
                break
            if _fn_idx > 0:
                _delay = _WRITE_FN_DELAY if _WRITE_FN_RE.search(inv["name"]) else _INTER_FN_DELAY
                time.sleep(_delay)
            _explore_one(inv, ctx)

    if _ecr is not None:
        logger.info("[%s] phase3: final ECR stats: %s", ctx.job_id, _ecr.stats())


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 4 – AC-1 probe-log reconciliation
