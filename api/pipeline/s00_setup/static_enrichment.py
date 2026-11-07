"""S-00 static evidence normalization.

This artifact is additive. It organizes already-available static/Ghidra-derived
surfaces into a bounded, provenance-labeled packet for later admission, without
making Ghidra availability a runtime or CI requirement.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _upload_to_blob

logger = logging.getLogger("mcp_factory.api")

STATIC_ENRICHMENT_BLOB = "static_enrichment.json"

_MAX_CALLABLES = 50
_MAX_ROLE_HINTS = 24
_MAX_PREREQS = 24
_MAX_DEFERRED = 12
_MAX_TEXT = 240

_INIT_RE = re.compile(r"(init|initialize|open|connect|login|session|start|setup)", re.I)
_WRITE_RE = re.compile(
    r"(pay|redeem|unlock|process|write|commit|transfer|debit|credit|set|update|create|delete|reserve)",
    re.I,
)
_READ_RE = re.compile(r"(get|query|lookup|read|list|check|validate|verify|status|version)", re.I)


def build_static_enrichment(ctx: Any) -> dict[str, Any]:
    """Build a normalized static-enrichment artifact from current S-00 state."""
    invocables = list(getattr(ctx, "invocables", []) or [])
    static_result = dict(getattr(ctx, "static_analysis_result", {}) or {})
    call_graph = dict(getattr(ctx, "call_graph", {}) or {})
    ghidra_data_types = list(getattr(ctx, "ghidra_data_types", []) or [])
    extras_count = sum(1 for inv in invocables if isinstance(inv, dict) and inv.get("_ghidra_extras"))
    provenance_count = sum(
        1
        for inv in invocables
        if isinstance(inv, dict) and _has_ghidra_provenance(inv)
    )

    callable_entries: list[dict[str, Any]] = []
    role_hints: list[dict[str, Any]] = []
    prereq_entries: list[dict[str, Any]] = []
    deferred_snippets: list[dict[str, Any]] = []
    xref_notes: list[dict[str, Any]] = []

    for inv in invocables[:_MAX_CALLABLES]:
        if not isinstance(inv, dict):
            continue
        entry = _callable_entry(inv, call_graph)
        callable_entries.append(entry)
        for hint in _role_hints_for_invocable(inv):
            if len(role_hints) < _MAX_ROLE_HINTS:
                role_hints.append(hint)
        for prereq in _prerequisite_hints_for_invocable(inv, call_graph):
            if len(prereq_entries) < _MAX_PREREQS:
                prereq_entries.append(prereq)
        for snippet in _bounded_decompile_snippets(inv):
            if len(deferred_snippets) < _MAX_DEFERRED:
                deferred_snippets.append(snippet)
        for note in _xref_notes(inv):
            if len(xref_notes) < _MAX_DEFERRED:
                xref_notes.append(note)

    strong_init = [
        hint["name"]
        for hint in role_hints
        if hint.get("role") == "init" and float(hint.get("confidence") or 0) >= 0.65
    ][:_MAX_ROLE_HINTS]
    strong_write = [
        hint["name"]
        for hint in role_hints
        if hint.get("role") == "write" and float(hint.get("confidence") or 0) >= 0.65
    ][:_MAX_ROLE_HINTS]

    ambiguities = _ambiguities(
        static_result=static_result,
        invocables=invocables,
        extras_count=extras_count,
        role_hints=role_hints,
        prereq_entries=prereq_entries,
    )
    admitted_names = _dedupe(strong_init + strong_write)[:12]
    usable_for_targets = bool(admitted_names)
    artifact = {
        "schema_version": 1,
        "producer_stage": "S-00",
        "source_status": {
            "static_analysis": "available" if static_result else "absent",
            "ghidra_extras": _ghidra_status(extras_count, len(invocables)),
            "ghidra_provenance_invocables": provenance_count,
            "headlessability": "unknown" if extras_count else "not_required",
            "fallback_safe": True,
        },
        "callable_inventory": {
            "total": len(invocables),
            "emitted": len(callable_entries),
            "cap": _MAX_CALLABLES,
            "entries": callable_entries,
            "role_hints": role_hints,
            "provenance": {
                "ghidra_extras_invocables": extras_count,
                "ghidra_provenance_invocables": provenance_count,
                "call_graph_functions": len(call_graph),
                "ghidra_data_types_count": len(ghidra_data_types),
            },
        },
        "prerequisite_hints": {
            "entries": prereq_entries,
            "strong_init_candidates": strong_init,
            "strong_write_candidates": strong_write,
        },
        "deferred_static": {
            "bounded_decompile_snippets": deferred_snippets,
            "xref_notes": xref_notes,
            "data_type_preview": _data_type_preview(ghidra_data_types),
        },
        "ambiguities": ambiguities,
        "admission_recommendation": {
            "usable_for_s01_targets": usable_for_targets,
            "admitted_target_names": admitted_names,
            "kept_deferred": ["deferred_static", "ambiguities"],
            "admission_risk": "usable_static_hints" if usable_for_targets else "thin_static_signal",
        },
    }
    return artifact


def write_static_enrichment(ctx: Any) -> dict[str, Any]:
    """Build, attach, and upload the additive static-enrichment artifact."""
    artifact = build_static_enrichment(ctx)
    ctx.static_enrichment = artifact
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/{STATIC_ENRICHMENT_BLOB}",
            json.dumps(artifact, indent=2).encode("utf-8"),
        )
        logger.info("[%s] phase0b: static_enrichment.json uploaded", ctx.job_id)
    except Exception as exc:
        logger.debug("[%s] phase0b: static_enrichment.json upload failed: %s", ctx.job_id, exc)
    return artifact


def _callable_entry(inv: dict[str, Any], call_graph: dict[str, Any]) -> dict[str, Any]:
    name = str(inv.get("name") or "").strip()
    params = list(inv.get("parameters") or [])
    callees = [_clip(str(callee)) for callee in list(call_graph.get(name) or inv.get("call_graph_callees") or [])[:8]]
    extras = inv.get("_ghidra_extras") if isinstance(inv.get("_ghidra_extras"), dict) else {}
    return {
        "name": name,
        "parameter_count": len(params),
        "has_ghidra_extras": bool(extras),
        "has_ghidra_provenance": _has_ghidra_provenance(inv),
        "call_graph_callees": callees,
        "static_roles": [hint["role"] for hint in _role_hints_for_invocable(inv)],
    }


def _role_hints_for_invocable(inv: dict[str, Any]) -> list[dict[str, Any]]:
    name = str(inv.get("name") or "").strip()
    if not name:
        return []
    hints: list[dict[str, Any]] = []
    if _INIT_RE.search(name):
        hints.append(_role_hint(name, "init", 0.75, "name_pattern"))
    if _WRITE_RE.search(name):
        hints.append(_role_hint(name, "write", 0.72, "name_pattern"))
    if _READ_RE.search(name):
        hints.append(_role_hint(name, "read", 0.62, "name_pattern"))
    if _has_output_param(inv) and not any(h["role"] == "write" for h in hints):
        hints.append(_role_hint(name, "producer", 0.6, "output_parameter"))
    return hints


def _role_hint(name: str, role: str, confidence: float, source: str) -> dict[str, Any]:
    return {
        "name": name,
        "role": role,
        "confidence": confidence,
        "source": source,
        "provenance": "static_enrichment_v1",
    }


def _prerequisite_hints_for_invocable(
    inv: dict[str, Any],
    call_graph: dict[str, Any],
) -> list[dict[str, Any]]:
    name = str(inv.get("name") or "").strip()
    if not name:
        return []
    hints: list[dict[str, Any]] = []
    for callee in list(call_graph.get(name) or inv.get("call_graph_callees") or [])[:8]:
        callee_name = str(callee or "").strip()
        if callee_name:
            hints.append(
                {
                    "function": name,
                    "prerequisite_or_related": callee_name,
                    "kind": "call_graph_edge",
                    "confidence": 0.55,
                    "provenance": "call_graph",
                }
            )
    extras = inv.get("_ghidra_extras") if isinstance(inv.get("_ghidra_extras"), dict) else {}
    for key in ("prerequisites", "preconditions", "required_preconditions"):
        values = extras.get(key) or inv.get(key) or []
        if isinstance(values, str):
            values = [values]
        for value in list(values or [])[:6]:
            hint = str(value or "").strip()
            if hint:
                hints.append(
                    {
                        "function": name,
                        "prerequisite_or_related": _clip(hint),
                        "kind": key,
                        "confidence": 0.65,
                        "provenance": "ghidra_extras" if extras.get(key) else "invocable",
                    }
                )
    return hints


def _bounded_decompile_snippets(inv: dict[str, Any]) -> list[dict[str, Any]]:
    extras = inv.get("_ghidra_extras") if isinstance(inv.get("_ghidra_extras"), dict) else {}
    name = str(inv.get("name") or "").strip()
    snippets: list[dict[str, Any]] = []
    for key in ("decompile", "decompiled", "decompilation", "pseudocode", "decompile_snippet"):
        value = extras.get(key) or inv.get(key)
        if not value:
            continue
        if isinstance(value, dict):
            value = value.get("text") or value.get("body") or value.get("snippet")
        text = str(value or "").strip()
        if text:
            snippets.append(
                {
                    "function": name,
                    "source": key,
                    "excerpt": _clip(text),
                    "policy": "deferred_static_not_s01_truth",
                }
            )
            break
    return snippets


def _xref_notes(inv: dict[str, Any]) -> list[dict[str, Any]]:
    extras = inv.get("_ghidra_extras") if isinstance(inv.get("_ghidra_extras"), dict) else {}
    name = str(inv.get("name") or "").strip()
    notes: list[dict[str, Any]] = []
    for key in ("xrefs", "references", "incoming_xrefs", "outgoing_xrefs"):
        values = extras.get(key) or inv.get(key) or []
        if isinstance(values, dict):
            values = list(values.values())
        if isinstance(values, str):
            values = [values]
        values = list(values or [])[:6]
        if values:
            notes.append(
                {
                    "function": name,
                    "source": key,
                    "count": len(values),
                    "preview": [_clip(str(value)) for value in values[:3]],
                    "policy": "deferred_static_not_s01_truth",
                }
            )
    return notes


def _data_type_preview(data_types: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in data_types[:10]:
        if isinstance(entry, dict):
            out.append(
                {
                    "name": str(entry.get("name") or "").strip(),
                    "kind": str(entry.get("kind") or entry.get("type") or "").strip(),
                }
            )
    return [entry for entry in out if entry.get("name")]


def _ambiguities(
    *,
    static_result: dict[str, Any],
    invocables: list[dict[str, Any]],
    extras_count: int,
    role_hints: list[dict[str, Any]],
    prereq_entries: list[dict[str, Any]],
) -> list[str]:
    notes: list[str] = []
    if not static_result:
        notes.append("static_analysis_absent")
    if not invocables:
        notes.append("callable_inventory_empty")
    if not extras_count:
        notes.append("ghidra_extras_absent")
    else:
        notes.append("ghidra_headlessability_not_proven")
    if not role_hints:
        notes.append("no_static_role_hints")
    if not prereq_entries:
        notes.append("no_prerequisite_hints")
    return notes


def _ghidra_status(extras_count: int, invocable_count: int) -> str:
    if extras_count <= 0:
        return "absent"
    if extras_count < invocable_count:
        return "partial"
    return "available"


def _has_ghidra_provenance(inv: dict[str, Any]) -> bool:
    params = inv.get("parameters") or []
    if any(isinstance(param, dict) and param.get("_ghidra_provenance") for param in params):
        return True
    return bool(inv.get("_ghidra_provenance"))


def _has_output_param(inv: dict[str, Any]) -> bool:
    for param in inv.get("parameters") or []:
        if not isinstance(param, dict):
            continue
        if str(param.get("direction") or "").lower() == "out":
            return True
    return False


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _clip(value: str) -> str:
    value = " ".join(str(value or "").split())
    return value[:_MAX_TEXT]
