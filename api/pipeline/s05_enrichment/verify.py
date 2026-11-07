"""api.pipeline.s05_enrichment.verify -- Phase 7b: enrichment verification."""

from __future__ import annotations

import json
import logging
import re as _re
from typing import Any

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import (
    _download_blob,
    _get_job_status,
    _load_findings,
    _patch_finding,
    _persist_job_status,
    _upload_to_blob,
)
from api.pipeline.core.evidence_candidates import (
    infer_expected_identifier_family,
    infer_identifier_family_from_value,
)
from api.pipeline.core.finding_status import normalize_status
from api.pipeline.core.helpers import _ctx_explored_count, _set_explore_status
from api.pipeline.core.helpers import _merge_result_output_values
from api.services.executor import _execute_tool

logger = logging.getLogger("mcp_factory.api")

_MUTATOR_RE = _re.compile(r"(?:^|_)(set|put|write|enable|configure|append|push)", _re.I)
_CREATOR_RE = _re.compile(r"(?:^|_)(create|open|init|initialize|new)", _re.I)
_OBSERVER_RE = _re.compile(
    r"(?:^|_)(get|is|has|num|count|status|read|receive|available|empty|unprocessed)",
    _re.I,
)
_CONSUMER_RE = _re.compile(r"(?:^|_)(put|write|append|push|send|process|receive)", _re.I)
_FINALIZER_RE = _re.compile(r"(?:^|_)(flush|commit|finalize|finish)", _re.I)
_BOOTSTRAP_RE = _re.compile(r"(?:^|_)(bind|init|initialize|setup|configure|attach|login|select)", _re.I)
_SUCCESS_STATUSES = {"success", "verified_success"}
_WEAK_REPLAY_VERIFICATIONS = {"inferred", "partial", "state_drift", "error"}
_PHASE_PRIORITY = {
    "lineage_preflight": 5,
    "structured_preflight_prereq": 4,
    "deterministic_fallback": 3,
    "explore": 2,
    "cross_validate": 1,
}


def _is_bridge_transport_failure(result: str) -> bool:
    text = str(result or "")
    return (
        "Bridge /execute error:" in text
        or "Windows VM bridge is temporarily unreachable" in text
    )


def _parse_return_value(result: str) -> int | None:
    match = _re.search(r"Returned:\s*(-?\d+)", str(result or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _family_prefix(fn_name: str) -> str:
    text = str(fn_name or "").strip()
    if "_" in text:
        return text.split("_", 1)[0].lower()
    return text.lower()


def _args_from_working_call(working_call: Any) -> dict[str, Any]:
    if not isinstance(working_call, dict):
        return {}
    if "args" in working_call and isinstance(working_call["args"], dict):
        return dict(working_call["args"] or {})
    if "arguments" in working_call and isinstance(working_call["arguments"], dict):
        return dict(working_call["arguments"] or {})
    return dict(working_call)


def _normalize_direct_target_truth(truth: Any) -> dict[str, Any] | None:
    if not isinstance(truth, dict):
        return None
    normalized = dict(truth)
    working_call = normalized.get("working_call")
    if isinstance(working_call, dict):
        normalized["working_call"] = dict(working_call)
    else:
        normalized.pop("working_call", None)
    return normalized


def _direct_target_truth_rank(truth: dict[str, Any] | None) -> tuple[int, int]:
    if not isinstance(truth, dict):
        return (0, 0)
    verification = str(truth.get("verification") or "").strip().lower()
    if verification == "verified":
        return (4, len(dict(truth.get("working_call") or {})))
    if truth.get("rejected_by_verification"):
        return (3, len(dict(truth.get("working_call") or {})))
    try:
        if int(truth.get("return_value") or 1) == 0:
            return (2, len(dict(truth.get("working_call") or {})))
    except Exception:
        pass
    return (1, len(dict(truth.get("working_call") or {})))


def _eligible_for_direct_replay(finding: dict[str, Any]) -> bool:
    """Only replay rows that are not explicitly marked as weak evidence."""
    if normalize_status(finding.get("status")) not in _SUCCESS_STATUSES:
        return False
    if not finding.get("working_call"):
        return False
    verification = str(finding.get("verification") or "").strip().lower()
    if verification in _WEAK_REPLAY_VERIFICATIONS:
        truth = _normalize_direct_target_truth(finding.get("direct_target_truth"))
        return bool(
            isinstance(truth, dict)
            and str(truth.get("verification") or "").strip().lower() == "verified"
            and isinstance(truth.get("working_call"), dict)
        )
    return True


def _build_direct_target_truth_from_probe(fn_name: str, probe: dict[str, Any]) -> dict[str, Any]:
    probe_return = _parse_return_value(str(probe.get("result_excerpt") or ""))
    probe_success = probe_return == 0
    return {
        "function": str(fn_name or "").strip(),
        "source": "s05_probe_log",
        "phase": str(probe.get("phase") or "").strip(),
        "probe_id": str(probe.get("probe_id") or "").strip(),
        "working_call": dict(probe.get("args") or {}),
        "return_value": int(probe_return or 0),
        "verification": "verified" if probe_success else "",
    }


def _best_direct_target_truth(
    finding: dict[str, Any],
    probe_log: list[dict[str, Any]],
    sentinels: dict[Any, Any],
) -> dict[str, Any] | None:
    best = _normalize_direct_target_truth(finding.get("direct_target_truth"))
    probe = _best_probe_for_function(probe_log, str(finding.get("function") or ""), sentinels)
    if probe and isinstance(probe.get("args"), dict):
        probe_truth = _build_direct_target_truth_from_probe(str(finding.get("function") or ""), probe)
        if best is None or _direct_target_truth_rank(probe_truth) >= _direct_target_truth_rank(best):
            best = probe_truth
    if best is None and isinstance(finding.get("working_call"), dict):
        best = {
            "function": str(finding.get("function") or "").strip(),
            "source": "s05_finding",
            "phase": "finding",
            "working_call": _args_from_working_call(finding.get("working_call")),
            "verification": str(finding.get("verification") or "").strip().lower(),
        }
    return best


def _load_probe_log(job_id: str) -> list[dict[str, Any]]:
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/explore_probe_log.json")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _is_handle_like_value(value: Any) -> bool:
    if value in ("", None):
        return True
    if isinstance(value, int):
        return value == 0 or value > 0x10000
    return False


def _is_likely_handle_param(inv: dict[str, Any] | None, param_name: str) -> bool:
    if not param_name:
        return False
    text = str(param_name)
    if text == "param_1":
        return True
    if _re.search(r"(handle|instance|context|object|state|session)", text, _re.I):
        return True
    for param in list((inv or {}).get("parameters") or []):
        if str(param.get("name") or "") != text:
            continue
        haystack = " ".join(
            str(param.get(k) or "")
            for k in ("name", "description", "semantic_name", "role", "type")
        )
        return bool(_re.search(r"(handle|instance|context|object|state|session)", haystack, _re.I))
    return False


def _bind_handle_args(
    inv: dict[str, Any] | None,
    args: dict[str, Any],
    handle_value: Any,
) -> dict[str, Any]:
    rebound = dict(args or {})
    if handle_value is None:
        return rebound
    handle_keys = [
        key
        for key in rebound
        if _is_likely_handle_param(inv, key) or _is_handle_like_value(rebound.get(key))
    ]
    if not handle_keys and "param_1" in rebound:
        handle_keys = ["param_1"]
    if handle_keys:
        rebound[handle_keys[0]] = handle_value
    return rebound


def _extract_prereq_rows_for_target(
    probe_log: list[dict[str, Any]],
    target_fn: str,
) -> list[dict[str, Any]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    needles = (
        f"{target_fn}:structured_preflight:prereq:",
        f"{target_fn}:structured_preflight:rehydrate:",
    )
    for idx, row in enumerate(probe_log):
        probe_id = str(row.get("probe_id") or "")
        if any(probe_id.startswith(needle) for needle in needles):
            rows.append((idx, row))
            continue
        if str(row.get("phase") or "") != "explore":
            continue
        if not probe_id.startswith(f"{target_fn}:"):
            continue
        parts = probe_id.split(":")
        if len(parts) < 4:
            continue
        prereq_fn = str(parts[-1] or "").strip()
        if not prereq_fn or prereq_fn == target_fn:
            continue
        if prereq_fn not in {"record_finding", "enrich_invocable"} and not prereq_fn.startswith("_"):
            rows.append((idx, row))
    rows.sort(key=lambda item: item[0])
    return [row for _, row in rows]


def _is_non_sentinel_probe(row: dict[str, Any], sentinels: dict[Any, Any]) -> bool:
    result_excerpt = str(row.get("result_excerpt") or "")
    if _is_bridge_transport_failure(result_excerpt):
        return False
    classification = row.get("classification") if isinstance(row.get("classification"), dict) else {}
    if not classification.get("has_return"):
        return False
    fmt = str(classification.get("format_guess") or "")
    if fmt in {"no_return_detected", "hresult_like"}:
        return False
    ret_val = _parse_return_value(result_excerpt)
    if ret_val is None:
        return False
    unsigned = ret_val & 0xFFFFFFFF
    if unsigned in (sentinels or {}):
        return False
    # Verification replay should only reuse rows that plausibly represent a
    # working call, not NTSTATUS-like failure paths that happened to carry args.
    if ret_val < 0 or unsigned > 0x80000000:
        return False
    return True


def _best_probe_for_function(
    probe_log: list[dict[str, Any]],
    fn_name: str,
    sentinels: dict[Any, Any],
) -> dict[str, Any] | None:
    best: tuple[int, int, int, dict[str, Any]] | None = None
    for idx, row in enumerate(probe_log):
        if str(row.get("function") or "") != fn_name:
            continue
        if not _is_non_sentinel_probe(row, sentinels):
            continue
        phase = str(row.get("phase") or "")
        score = _PHASE_PRIORITY.get(phase, 0)
        arg_count = len(dict(row.get("args") or {}))
        candidate = (score, arg_count, idx, row)
        if best is None or candidate > best:
            best = candidate
    return best[-1] if best else None


def _best_creator_spec(
    ctx,
    findings: list[dict[str, Any]],
    probe_log: list[dict[str, Any]],
    family: str,
) -> dict[str, Any] | None:
    options: list[tuple[int, int, str, dict[str, Any]]] = []
    for fn_name, inv in (ctx.inv_map or {}).items():
        if _family_prefix(fn_name) != family or not _CREATOR_RE.search(fn_name):
            continue
        args: dict[str, Any] = {}
        source = "default"
        for finding in findings:
            if str(finding.get("function") or "") != fn_name:
                continue
            if normalize_status(finding.get("status")) not in _SUCCESS_STATUSES:
                continue
            args = _args_from_working_call(finding.get("working_call"))
            source = "finding"
            break
        probe = _best_probe_for_function(probe_log, fn_name, getattr(ctx, "sentinels", {}))
        if probe and (not args or len(dict(probe.get("args") or {})) < len(args)):
            args = dict(probe.get("args") or {})
            source = "probe_log"
        options.append((1 if source == "probe_log" else 0, -len(args), fn_name, {
            "function": fn_name,
            "inv": inv,
            "args": args,
            "source": source,
        }))
    if not options:
        return None
    options.sort(reverse=True)
    return options[0][-1]


def _collect_same_family_findings(
    findings: list[dict[str, Any]],
    family: str,
) -> list[dict[str, Any]]:
    return [
        row for row in findings
        if _family_prefix(row.get("function") or "") == family
    ]


def _select_consumer_candidate(
    ctx,
    findings: list[dict[str, Any]],
    probe_log: list[dict[str, Any]],
    family: str,
    target_fn: str,
) -> dict[str, Any] | None:
    best: tuple[int, int, str, dict[str, Any]] | None = None
    for finding in _collect_same_family_findings(findings, family):
        fn_name = str(finding.get("function") or "")
        if fn_name == target_fn or not _CONSUMER_RE.search(fn_name):
            continue
        if normalize_status(finding.get("status")) not in _SUCCESS_STATUSES:
            continue
        call_args = _args_from_working_call(finding.get("working_call"))
        if not call_args:
            continue
        prereqs = _extract_prereq_rows_for_target(probe_log, fn_name)
        score = (2 if prereqs else 0) + (1 if any(isinstance(v, list) for v in call_args.values()) else 0)
        candidate = {
            "function": fn_name,
            "inv": ctx.inv_map.get(fn_name),
            "args": call_args,
            "prereqs": prereqs,
            "source": "finding",
        }
        ranked = (score, len(prereqs), fn_name, candidate)
        if best is None or ranked > best:
            best = ranked
    return best[-1] if best else None


def _select_observer_candidates(
    ctx,
    findings: list[dict[str, Any]],
    family: str,
    target_fn: str,
    limit: int = 2,
) -> list[dict[str, Any]]:
    selected: list[tuple[int, str, dict[str, Any]]] = []
    for finding in _collect_same_family_findings(findings, family):
        fn_name = str(finding.get("function") or "")
        if fn_name == target_fn or not _OBSERVER_RE.search(fn_name):
            continue
        call_args = _args_from_working_call(finding.get("working_call"))
        if not call_args:
            continue
        score = 1 if normalize_status(finding.get("status")) in _SUCCESS_STATUSES else 0
        selected.append((score, fn_name, {
            "function": fn_name,
            "inv": ctx.inv_map.get(fn_name),
            "args": call_args,
            "source": "finding",
        }))
    selected.sort(reverse=True)
    return [item[-1] for item in selected[:limit]]


def _select_finalizer(ctx, family: str) -> dict[str, Any] | None:
    for fn_name, inv in (ctx.inv_map or {}).items():
        if _family_prefix(fn_name) != family or not _FINALIZER_RE.search(fn_name):
            continue
        return {"function": fn_name, "inv": inv, "args": {"param_1": 0}}
    return None


def _execute_session_prereqs(ctx) -> str | None:
    for init_inv in ctx.init_invocables:
        result = _execute_tool(init_inv, {})
        if _is_bridge_transport_failure(result):
            return str(result)
    return None


def _execute_call(inv: dict[str, Any] | None, args: dict[str, Any]) -> str:
    if not inv:
        return "Tool not found."
    return _execute_tool(inv, args)


def _run_creator(ctx, creator: dict[str, Any]) -> tuple[Any, str]:
    result = _execute_call(creator.get("inv"), dict(creator.get("args") or {}))
    return _parse_return_value(result), result


def _build_stateful_candidates(
    ctx,
    findings: list[dict[str, Any]],
    probe_log: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[tuple[int, int, str, dict[str, Any]]] = []
    for finding in findings:
        fn_name = str(finding.get("function") or "")
        if normalize_status(finding.get("status")) in _SUCCESS_STATUSES:
            continue
        if not _MUTATOR_RE.search(fn_name):
            continue
        best_probe = _best_probe_for_function(probe_log, fn_name, getattr(ctx, "sentinels", {}))
        if not best_probe:
            continue
        family = _family_prefix(fn_name)
        creator = _best_creator_spec(ctx, findings, probe_log, family)
        if not creator:
            continue
        candidate = {
            "function": fn_name,
            "inv": ctx.inv_map.get(fn_name),
            "source_row": best_probe,
            "candidate_source": "probe_log",
            "family": family,
            "creator": creator,
        }
        phase_rank = _PHASE_PRIORITY.get(str(best_probe.get("phase") or ""), 0)
        arg_count = len(dict(best_probe.get("args") or {}))
        candidates.append((phase_rank, arg_count, fn_name, candidate))
    candidates.sort(reverse=True)
    return [item[-1] for item in candidates]


def _bind_same_session_call(
    ctx,
    spec: dict[str, Any],
    handle_value: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    fn_name = str(spec.get("function") or "")
    inv = spec.get("inv") if isinstance(spec.get("inv"), dict) else ctx.inv_map.get(fn_name)
    args = _bind_handle_args(inv, dict(spec.get("args") or {}), handle_value)
    return inv, args


def _probe_row_function_name(target_fn: str, row: dict[str, Any]) -> str:
    fn_name = str(row.get("function") or "").strip()
    if str(row.get("phase") or "") != "explore":
        return fn_name
    probe_id = str(row.get("probe_id") or "")
    if not probe_id.startswith(f"{target_fn}:"):
        return fn_name
    parts = probe_id.split(":")
    if len(parts) >= 4 and str(parts[-1] or "").strip():
        return str(parts[-1] or "").strip()
    return fn_name


def _call_spec_from_probe_row(ctx, row: dict[str, Any], target_fn: str = "") -> dict[str, Any]:
    fn_name = _probe_row_function_name(target_fn, row)
    return {
        "function": fn_name,
        "inv": ctx.inv_map.get(fn_name),
        "args": dict(row.get("args") or {}),
        "source": "probe_log",
    }


def _expand_prereq_specs(
    ctx,
    probe_log: list[dict[str, Any]],
    target_fn: str,
    seen: set[str] | None = None,
) -> list[dict[str, Any]]:
    seen = set(seen or set())
    expanded: list[dict[str, Any]] = []
    for row in _extract_prereq_rows_for_target(probe_log, target_fn):
        spec = _call_spec_from_probe_row(ctx, row, target_fn)
        prereq_fn = str(spec.get("function") or "").strip()
        if prereq_fn and prereq_fn in seen:
            continue
        if prereq_fn:
            seen.add(prereq_fn)
            expanded.extend(_expand_prereq_specs(ctx, probe_log, prereq_fn, seen))
        expanded.append(spec)
    return expanded


def _param_meta(inv: dict[str, Any] | None, param_name: str) -> dict[str, Any]:
    for param in list((inv or {}).get("parameters") or []):
        if str(param.get("name") or "") == str(param_name or ""):
            return dict(param)
    return {}


def _param_lookup(inv: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        str(param.get("name") or ""): dict(param)
        for param in list((inv or {}).get("parameters") or [])
        if isinstance(param, dict) and str(param.get("name") or "")
    }


def _expected_family_for_param(inv: dict[str, Any] | None, fn_name: str, param_name: str) -> str | None:
    meta = _param_meta(inv, param_name)
    inferred_kinds = list(meta.get("inferred_kinds") or [])
    expected = infer_expected_identifier_family(
        str(param_name or ""),
        str(meta.get("description") or ""),
        str(meta.get("json_type") or ""),
        str(fn_name or ""),
        inferred_kinds,
        resolved_type=str(meta.get("resolved_type") or meta.get("type") or ""),
    )
    if expected:
        return expected
    param_context = " ".join(
        [
            str(param_name or ""),
            str(meta.get("description") or ""),
            str(meta.get("resolved_type") or meta.get("type") or ""),
        ]
    ).lower()
    fn_context = str(fn_name or "").lower()
    if "nonce" in param_context or ("nonce" in fn_context and "nonce" in str(param_name or "").lower()):
        return "nonce"
    if ("reserv" in param_context or "resv" in param_context) and "workflow" not in param_context:
        return "reservation_id"
    if ("workflow" in param_context and "handle" in param_context) or "lpszhandle" in param_context:
        return "workflow_handle"
    if "handle" in param_context and "workflow" in fn_context:
        return "workflow_handle"
    if "quote" in param_context:
        return "quote_id"
    if "ticket" in param_context:
        return "ticket"
    return None


def _coerce_result_value(raw_value: str) -> Any:
    text = str(raw_value or "").strip()
    if not text:
        return ""
    if _re.fullmatch(r"-?\d+", text):
        try:
            return int(text)
        except Exception:
            return text
    match = _re.match(r"^\s*(-?\d+)\b", text)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return text
    return text


def _collect_runtime_lineage_hints(
    inv: dict[str, Any] | None,
    fn_name: str,
    result_text: str,
) -> dict[str, Any]:
    hints: dict[str, Any] = {}
    lines = [str(line).strip() for line in str(result_text or "").splitlines() if str(line).strip()]
    if not lines:
        return hints
    for line in lines[1:]:
        if "=" in line:
            raw_name, raw_value = line.split("=", 1)
            value = _coerce_result_value(raw_value)
            family = (
                _expected_family_for_param(inv, fn_name, raw_name.strip())
                or infer_identifier_family_from_value(value, param_kind=raw_name.strip(), source_function=fn_name)
            )
            if family:
                hints[family] = value
            continue
        value = _coerce_result_value(line)
        family = infer_identifier_family_from_value(value, source_function=fn_name)
        if family:
            hints[family] = value
    return hints


def _apply_runtime_lineage_hints(
    inv: dict[str, Any] | None,
    fn_name: str,
    args: dict[str, Any],
    lineage_hints: dict[str, Any],
) -> dict[str, Any]:
    rebound = dict(args or {})
    if not lineage_hints:
        return rebound
    for key, current in list(rebound.items()):
        meta = _param_meta(inv, key)
        context = " ".join(
            [
                str(key or ""),
                str(meta.get("description") or ""),
                str(meta.get("direction") or ""),
            ]
        ).lower()
        if _re.search(r"(^pout|out\b|output|direction.+out)", context):
            continue
        expected_family = _expected_family_for_param(inv, fn_name, key)
        if not expected_family or expected_family not in lineage_hints:
            continue
        replacement = lineage_hints[expected_family]
        current_family = infer_identifier_family_from_value(current, param_kind=expected_family, source_function=fn_name)
        if current in ("", None) or current_family == expected_family:
            rebound[key] = replacement
    return rebound


def _bootstrap_specs_from_findings(
    ctx,
    findings: list[dict[str, Any]],
    probe_log: list[dict[str, Any]],
    target_fn: str,
) -> list[dict[str, Any]]:
    family = _family_prefix(target_fn)
    selected: list[tuple[int, str, dict[str, Any]]] = []
    for finding in findings:
        fn_name = str(finding.get("function") or "").strip()
        if not fn_name or fn_name == target_fn or _family_prefix(fn_name) != family:
            continue
        if normalize_status(finding.get("status")) not in _SUCCESS_STATUSES:
            continue
        if not _BOOTSTRAP_RE.search(fn_name):
            continue
        args = _args_from_working_call(finding.get("working_call"))
        probe = _best_probe_for_function(probe_log, fn_name, getattr(ctx, "sentinels", {}))
        if probe and isinstance(probe.get("args"), dict):
            args = dict(probe.get("args") or {})
        spec = {
            "function": fn_name,
            "inv": ctx.inv_map.get(fn_name),
            "args": args,
            "source": "bootstrap_finding",
        }
        rank = 0 if _re.search(r"(?:^|_)(init|initialize)", fn_name, _re.I) else 1
        selected.append((rank, fn_name, spec))
    selected.sort(key=lambda item: (item[0], item[1]))

    seen: set[str] = set()
    expanded: list[dict[str, Any]] = []
    for _, fn_name, spec in selected:
        if fn_name in seen:
            continue
        seen.add(fn_name)
        for prereq in _expand_prereq_specs(ctx, probe_log, fn_name, seen):
            prereq_fn = str(prereq.get("function") or "").strip()
            if prereq_fn and prereq_fn not in seen:
                seen.add(prereq_fn)
                expanded.append(prereq)
        expanded.append(spec)
    return expanded


def _run_sequence(
    ctx,
    handle_value: Any,
    call_specs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    executed: list[dict[str, Any]] = []
    for spec in call_specs:
        inv, args = _bind_same_session_call(ctx, spec, handle_value)
        result = _execute_call(inv, args)
        executed.append({
            "function": spec.get("function"),
            "args": args,
            "result": str(result or "")[:200],
            "return_value": _parse_return_value(result),
        })
        if _is_bridge_transport_failure(result):
            return executed, str(result)
    return executed, None


def _observer_effects(
    control_rows: list[dict[str, Any]],
    treatment_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    for control_row, treatment_row in zip(control_rows, treatment_rows):
        if str(control_row.get("function") or "") != str(treatment_row.get("function") or ""):
            continue
        control_result = str(control_row.get("result") or "")
        treatment_result = str(treatment_row.get("result") or "")
        control_return = control_row.get("return_value")
        treatment_return = treatment_row.get("return_value")
        if control_return != treatment_return or control_result != treatment_result:
            effects.append({
                "function": control_row.get("function"),
                "control_return": control_return,
                "treatment_return": treatment_return,
                "control_result": control_result,
                "treatment_result": treatment_result,
            })
    return effects


def _run_stateful_candidate(
    ctx,
    candidate: dict[str, Any],
    findings: list[dict[str, Any]],
    probe_log: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None, str]:
    fn_name = str(candidate.get("function") or "")
    source_row = candidate.get("source_row") if isinstance(candidate.get("source_row"), dict) else {}
    family = str(candidate.get("family") or _family_prefix(fn_name))
    creator = candidate.get("creator") if isinstance(candidate.get("creator"), dict) else None
    consumer = _select_consumer_candidate(ctx, findings, probe_log, family, fn_name)
    observers = _select_observer_candidates(ctx, findings, family, fn_name, limit=2)
    finalizer = _select_finalizer(ctx, family)
    custom_return = _parse_return_value(str(source_row.get("result_excerpt") or ""))

    report_entry: dict[str, Any] = {
        "function": fn_name,
        "verification": "inferred",
        "verification_mode": "stateful_mutator",
        "candidate_source": "probe_log",
        "args": dict(source_row.get("args") or {}),
        "result": str(source_row.get("result_excerpt") or "")[:200],
        "return_value": str(custom_return) if custom_return is not None else None,
        "prerequisite_chain": [],
        "observer_calls": [],
        "observed_effects": [],
        "promotion_decision": "not_promoted",
        "custom_return_semantics": {
            "raw_return": custom_return,
            "source_phase": str(source_row.get("phase") or ""),
            "format_guess": ((source_row.get("classification") or {}).get("format_guess") if isinstance(source_row.get("classification"), dict) else ""),
            "requires_effect_evidence": True,
        },
    }
    if not creator:
        report_entry["custom_return_semantics"]["reason"] = "no_creator_found"
        return report_entry, None, ""

    consumer_specs = []
    if consumer:
        report_entry["prerequisite_chain"] = [
            {"function": creator.get("function"), "source": creator.get("source"), "args": dict(creator.get("args") or {})}
        ]
        for prereq_row in list(consumer.get("prereqs") or []):
            prereq_spec = _call_spec_from_probe_row(ctx, prereq_row)
            prereq_fn = str(prereq_spec.get("function") or "")
            if prereq_fn == fn_name or prereq_fn == str(creator.get("function") or ""):
                continue
            consumer_specs.append(prereq_spec)
            report_entry["prerequisite_chain"].append({
                "function": prereq_fn,
                "source": "probe_log",
                "args": dict(prereq_spec.get("args") or {}),
            })
    else:
        report_entry["prerequisite_chain"] = [
            {"function": creator.get("function"), "source": creator.get("source"), "args": dict(creator.get("args") or {})}
        ]

    observer_specs = list(observers)
    report_entry["observer_calls"] = [
        {"function": obs.get("function"), "source": obs.get("source"), "args": dict(obs.get("args") or {})}
        for obs in observer_specs
    ]
    if not consumer and not observer_specs:
        report_entry["custom_return_semantics"]["reason"] = "no_consumer_or_observer_surface"
        return report_entry, None, ""

    bridge_error_message = _execute_session_prereqs(ctx)
    if bridge_error_message:
        report_entry["verification"] = "error"
        report_entry["promotion_decision"] = "bridge_error"
        return report_entry, None, bridge_error_message
    control_handle, control_create_result = _run_creator(ctx, creator)
    report_entry["control_create_result"] = str(control_create_result)[:200]
    if _is_bridge_transport_failure(control_create_result):
        report_entry["verification"] = "error"
        report_entry["promotion_decision"] = "bridge_error"
        return report_entry, None, str(control_create_result)
    if control_handle in (None, 0):
        report_entry["custom_return_semantics"]["reason"] = "control_creator_failed"
        return report_entry, None, ""
    control_sequence = list(consumer_specs)
    if consumer:
        control_sequence.append(consumer)
    if finalizer:
        control_sequence.append(finalizer)
    control_sequence.extend(observer_specs)
    control_rows, bridge_error_message = _run_sequence(ctx, control_handle, control_sequence)
    if bridge_error_message:
        report_entry["verification"] = "error"
        report_entry["promotion_decision"] = "bridge_error"
        return report_entry, None, bridge_error_message

    bridge_error_message = _execute_session_prereqs(ctx)
    if bridge_error_message:
        report_entry["verification"] = "error"
        report_entry["promotion_decision"] = "bridge_error"
        return report_entry, None, bridge_error_message
    treatment_handle, treatment_create_result = _run_creator(ctx, creator)
    report_entry["treatment_create_result"] = str(treatment_create_result)[:200]
    if _is_bridge_transport_failure(treatment_create_result):
        report_entry["verification"] = "error"
        report_entry["promotion_decision"] = "bridge_error"
        return report_entry, None, str(treatment_create_result)
    if treatment_handle in (None, 0):
        report_entry["custom_return_semantics"]["reason"] = "treatment_creator_failed"
        return report_entry, None, ""

    treatment_sequence = list(consumer_specs)
    treatment_sequence.append(_call_spec_from_probe_row(ctx, source_row))
    if consumer:
        treatment_sequence.append(consumer)
    if finalizer:
        treatment_sequence.append(finalizer)
    treatment_sequence.extend(observer_specs)
    treatment_rows, bridge_error_message = _run_sequence(ctx, treatment_handle, treatment_sequence)
    if bridge_error_message:
        report_entry["verification"] = "error"
        report_entry["promotion_decision"] = "bridge_error"
        return report_entry, None, bridge_error_message

    control_consumer_row = next((row for row in control_rows if row.get("function") == (consumer or {}).get("function")), None)
    treatment_consumer_row = next((row for row in treatment_rows if row.get("function") == (consumer or {}).get("function")), None)
    observer_effects = _observer_effects(
        [row for row in control_rows if row.get("function") in {obs.get("function") for obs in observer_specs}],
        [row for row in treatment_rows if row.get("function") in {obs.get("function") for obs in observer_specs}],
    )
    consumer_effects: list[dict[str, Any]] = []
    if control_consumer_row and treatment_consumer_row:
        control_ok = control_consumer_row.get("return_value") == 0
        treatment_ok = treatment_consumer_row.get("return_value") == 0
        if control_ok != treatment_ok:
            consumer_effects.append({
                "function": treatment_consumer_row.get("function"),
                "control_return": control_consumer_row.get("return_value"),
                "treatment_return": treatment_consumer_row.get("return_value"),
                "control_result": control_consumer_row.get("result"),
                "treatment_result": treatment_consumer_row.get("result"),
            })

    observed_effects = consumer_effects + observer_effects
    report_entry["observed_effects"] = observed_effects
    report_entry["control_sequence"] = control_rows
    report_entry["treatment_sequence"] = treatment_rows
    if observed_effects:
        promoted_args = dict(source_row.get("args") or {})
        promoted_args = _bind_handle_args(candidate.get("inv"), promoted_args, treatment_handle)
        finding_patch = {
            "status": "success",
            "working_call": promoted_args,
            "status_canonical": "verified_success",
            "status_legacy": "success",
            "verification": "verified",
            "stop_reason": "stateful_mutator_verified",
            "finding": (
                f"Stateful verification confirmed {fn_name} via observed effect; "
                f"custom return {custom_return} was corroborated by downstream state."
            ),
            "cross_validation": json.dumps(observed_effects, ensure_ascii=True)[:500],
        }
        report_entry["verification"] = "verified"
        report_entry["promotion_decision"] = "promoted"
        return report_entry, finding_patch, ""

    report_entry["custom_return_semantics"]["reason"] = "no_effect_delta"
    return report_entry, None, ""


def _run_direct_replay(
    ctx,
    finding: dict[str, Any],
    probe_log: list[dict[str, Any]],
    findings: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, str]:
    fn_name = finding.get("function", "")
    strongest_truth = _best_direct_target_truth(finding, probe_log, getattr(ctx, "sentinels", {}))
    working_call = (
        strongest_truth.get("working_call")
        if isinstance(strongest_truth, dict) and isinstance(strongest_truth.get("working_call"), dict)
        else finding.get("working_call")
    )
    inv = ctx.inv_map.get(fn_name)
    if not inv:
        return {}, None, ""

    call_args = _args_from_working_call(working_call)
    best_probe = _best_probe_for_function(probe_log, fn_name, getattr(ctx, "sentinels", {}))
    candidate_source = str((strongest_truth or {}).get("source") or "finding")
    if (
        best_probe
        and isinstance(best_probe.get("args"), dict)
        and dict(best_probe.get("args") or {})
        and len(dict(best_probe.get("args") or {})) >= len(call_args)
    ):
        call_args = dict(best_probe.get("args") or {})
        candidate_source = "probe_log"
    findings = list(findings or [])
    prereq_specs = _expand_prereq_specs(ctx, probe_log, fn_name)
    if _CREATOR_RE.search(fn_name):
        bootstrap_specs = _bootstrap_specs_from_findings(ctx, findings, probe_log, fn_name)
        seen_specs = {str(spec.get("function") or "") for spec in prereq_specs}
        for spec in bootstrap_specs:
            spec_fn = str(spec.get("function") or "")
            if spec_fn and spec_fn not in seen_specs:
                prereq_specs.append(spec)
                seen_specs.add(spec_fn)
    report_entry: dict[str, Any] = {
        "function": fn_name,
        "verification_mode": "direct_replay",
        "candidate_source": candidate_source,
        "prerequisite_chain": [
            {
                "function": str(spec.get("function") or ""),
                "source": str(spec.get("source") or ""),
                "args": dict(spec.get("args") or {}),
            }
            for spec in prereq_specs
        ],
        "observer_calls": [],
        "observed_effects": [],
        "promotion_decision": "existing_success",
        "custom_return_semantics": {},
        "args": call_args,
        "direct_target_truth": dict(strongest_truth or {}),
    }
    try:
        bridge_error_message = _execute_session_prereqs(ctx)
        if bridge_error_message:
            report_entry.update({
                "verification": "error",
                "error": bridge_error_message[:200],
            })
            return report_entry, {"verification": "error"}, bridge_error_message
        if prereq_specs:
            runtime_hints: dict[str, Any] = {}
            executed_prereqs: list[dict[str, Any]] = []
            for spec in prereq_specs:
                prereq_fn = str(spec.get("function") or "")
                prereq_inv = spec.get("inv") if isinstance(spec.get("inv"), dict) else ctx.inv_map.get(prereq_fn)
                prereq_args = _apply_runtime_lineage_hints(
                    prereq_inv,
                    prereq_fn,
                    dict(spec.get("args") or {}),
                    runtime_hints,
                )
                result_str = _execute_call(prereq_inv, prereq_args)
                executed_prereqs.append({
                    "function": prereq_fn,
                    "source": str(spec.get("source") or ""),
                    "args": dict(prereq_args),
                })
                if _is_bridge_transport_failure(result_str):
                    bridge_error_message = str(result_str)
                    report_entry["prerequisite_chain"] = executed_prereqs
                    report_entry.update({
                        "verification": "error",
                        "error": bridge_error_message[:200],
                    })
                    return report_entry, {"verification": "error"}, bridge_error_message
                runtime_hints.update(_collect_runtime_lineage_hints(prereq_inv, prereq_fn, result_str))
            report_entry["prerequisite_chain"] = executed_prereqs
            call_args = _apply_runtime_lineage_hints(inv, fn_name, call_args, runtime_hints)
            report_entry["args"] = call_args

        result_str = _execute_tool(inv, call_args)
        if _is_bridge_transport_failure(result_str):
            report_entry.update({
                "verification": "error",
                "error": str(result_str)[:200],
            })
            return report_entry, {"verification": "error"}, str(result_str)

        ret_val = _parse_return_value(result_str)
        if ret_val is None:
            verification = "inferred"
        else:
            unsigned = ret_val & 0xFFFFFFFF
            is_sentinel = unsigned in ctx.sentinels or unsigned > 0x80000000
            if ret_val == 0:
                verification = "verified"
            elif is_sentinel:
                verification = "state_drift"
            else:
                verification = "verified"
        report_entry.update({
            "verification": verification,
            "result": str(result_str or "")[:200],
            "return_value": str(ret_val) if ret_val is not None else None,
        })
        preserved_working_call = dict(call_args)
        if verification == "verified":
            preserved_working_call = _merge_result_output_values(
                call_args,
                result_str,
                _param_lookup(inv),
            )
            if isinstance(report_entry.get("direct_target_truth"), dict):
                report_entry["direct_target_truth"] = {
                    **dict(report_entry["direct_target_truth"] or {}),
                    "function": fn_name,
                    "working_call": dict(preserved_working_call),
                    "verification": verification,
                    "return_value": ret_val,
                    "source": candidate_source,
                }
            report_entry["preserved_working_call"] = dict(preserved_working_call)
        patch: dict[str, Any] = {
            "verification": verification,
            "direct_target_truth": {
                **dict(strongest_truth or {}),
                "function": fn_name,
                "working_call": dict(preserved_working_call),
                "verification": verification,
                "return_value": ret_val,
                "source": candidate_source,
            },
        }
        if verification == "verified":
            patch.update({
                "status": "verified_success",
                "status_canonical": "verified_success",
                "status_legacy": "success",
                "working_call": dict(preserved_working_call),
            })
        elif verification == "state_drift":
            patch.update({
                "working_call": None,
                "direct_target_truth_rejected_reason": (
                    f"verification replay returned {ret_val} after prior direct-target success"
                ),
            })
            if isinstance(patch.get("direct_target_truth"), dict):
                patch["direct_target_truth"]["rejected_by_verification"] = True
        return report_entry, patch, ""
    except Exception as exc:
        report_entry.update({
            "verification": "error",
            "error": str(exc)[:200],
        })
        return report_entry, {"verification": "error"}, ""


def _run_phase_7b_verify_enrichment(ctx) -> None:
    """Verify working calls and promote stateful mutators when effect evidence exists."""
    try:
        logger.info("[%s] phase7b: enrichment verification pass...", ctx.job_id)
        _set_explore_status(
            ctx.job_id,
            _ctx_explored_count(ctx),
            ctx.total,
            "Verifying enriched function calls...",
        )
        findings = _load_findings(ctx.job_id)
        if not findings:
            return
        probe_log = _load_probe_log(ctx.job_id)

        report_entries: list[dict[str, Any]] = []
        verified_count = 0
        inferred_count = 0
        state_drift_count = 0
        error_count = 0
        bridge_error_message = ""

        for finding in findings:
            fn_name = finding.get("function", "")
            if not _eligible_for_direct_replay(finding):
                continue
            report_entry, patch, bridge_error_message = _run_direct_replay(ctx, finding, probe_log, findings)
            if not report_entry:
                continue
            if patch:
                _patch_finding(ctx.job_id, fn_name, patch)
            report_entries.append(report_entry)
            verification = str(report_entry.get("verification") or "")
            if verification == "verified":
                verified_count += 1
            elif verification == "state_drift":
                state_drift_count += 1
            elif verification == "error":
                error_count += 1
            else:
                inferred_count += 1
            if bridge_error_message:
                logger.warning(
                    "[%s] phase7b: bridge transport failed while verifying %s",
                    ctx.job_id,
                    fn_name,
                )
                break

        if not bridge_error_message:
            for candidate in _build_stateful_candidates(ctx, findings, probe_log):
                fn_name = str(candidate.get("function") or "")
                report_entry, patch, bridge_error_message = _run_stateful_candidate(
                    ctx,
                    candidate,
                    findings,
                    probe_log,
                )
                if patch:
                    _patch_finding(ctx.job_id, fn_name, patch)
                report_entries.append(report_entry)
                verification = str(report_entry.get("verification") or "")
                if verification == "verified":
                    verified_count += 1
                elif verification == "state_drift":
                    state_drift_count += 1
                elif verification == "error":
                    error_count += 1
                else:
                    inferred_count += 1
                if bridge_error_message:
                    logger.warning(
                        "[%s] phase7b: bridge transport failed while verifying stateful candidate %s",
                        ctx.job_id,
                        fn_name,
                    )
                    break

        logger.info(
            "[%s] phase7b: verified=%d, inferred=%d, state_drift=%d, error=%d out of %d checked entries",
            ctx.job_id,
            verified_count,
            inferred_count,
            state_drift_count,
            error_count,
            len(report_entries),
        )

        try:
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{ctx.job_id}/verification-report.json",
                json.dumps({
                    "verified_count": verified_count,
                    "inferred_count": inferred_count,
                    "state_drift_count": state_drift_count,
                    "error_count": error_count,
                    "total_checked": len(report_entries),
                    "entries": report_entries,
                }, indent=2).encode(),
            )
        except Exception as exc:
            logger.debug("[%s] phase7b: verification report upload failed: %s", ctx.job_id, exc)

        try:
            current_status = _get_job_status(ctx.job_id) or {}
            _persist_job_status(ctx.job_id, {
                **current_status,
                "verification_verified": verified_count,
                "verification_inferred": inferred_count + state_drift_count,
                "verification_error": error_count,
            })
        except Exception:
            pass

        if bridge_error_message:
            raise RuntimeError(
                "Bridge verification lane degraded during s05_enrichment: "
                f"{bridge_error_message[:200]}"
            )

    except Exception as exc:
        logger.debug("[%s] phase7b: enrichment verification failed: %s", ctx.job_id, exc)
        raise
