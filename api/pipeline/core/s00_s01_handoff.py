"""Helpers for the first live S-00 -> S-01 handoff packet seam.

This seam is intentionally additive. It does not replace the canonical 7-stage
contract or legacy S-00 artifacts; it normalizes the static/setup slice so S-01
can read an admitted packet instead of reconstructing the seam from scattered
surfaces alone.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _download_blob, _upload_to_blob

logger = logging.getLogger("mcp_factory.api")

S00_S01_HANDOFF_BLOB = "s01_handoff_packet.json"
S00_S01_HANDOFF_CANONICAL_PATH = "evidence/stage-00-setup/s01-handoff-packet.json"

_INIT_FN_PATTERN = re.compile(
    r"(init|initialize|open|connect|login|unlock|authorize|session|start)",
    re.I,
)
_WRITE_FN_PATTERN = re.compile(
    r"(pay|redeem|unlock|process|write|commit|transfer|debit|credit|set|update|create|delete)",
    re.I,
)


def _hexify_sentinels(sentinels: dict[Any, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (sentinels or {}).items():
        try:
            out[f"0x{int(key):08X}"] = value
        except Exception:
            out[str(key)] = value
    return out


def _packet_targets(invocables: list[dict[str, Any]], dll_strings: dict[str, Any]) -> dict[str, Any]:
    init_candidates: list[str] = []
    write_candidates: list[str] = []
    for inv in invocables or []:
        name = str(inv.get("name") or "").strip()
        if not name:
            continue
        if _INIT_FN_PATTERN.search(name):
            init_candidates.append(name)
        if _WRITE_FN_PATTERN.search(name):
            write_candidates.append(name)
    focus_ids = list((dll_strings or {}).get("ids") or [])[:12]
    focus_emails = list((dll_strings or {}).get("emails") or [])[:12]
    emitted_init = init_candidates[:12]
    emitted_write = write_candidates[:12]
    quality_flags: list[str] = []
    if not emitted_init:
        quality_flags.append("no_init_candidates")
    if not emitted_write:
        quality_flags.append("no_write_candidates")
    if not focus_ids:
        quality_flags.append("no_focus_ids")
    if len(init_candidates) > len(emitted_init) or len(write_candidates) > len(emitted_write):
        quality_flags.append("target_cap_applied")
    return {
        "init_candidates": emitted_init,
        "write_candidates": emitted_write,
        "focus_ids": focus_ids,
        "focus_emails": focus_emails,
        "quality": {
            "invocable_count": len(invocables or []),
            "raw_init_candidate_count": len(init_candidates),
            "raw_write_candidate_count": len(write_candidates),
            "emitted_init_candidate_count": len(emitted_init),
            "emitted_write_candidate_count": len(emitted_write),
            "target_cap": 12,
            "target_cap_applied": "target_cap_applied" in quality_flags,
            "unmatched_targets": [],
            "quality_flags": quality_flags,
        },
    }


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = str(value or "").strip()
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _static_enrichment_summary(static_enrichment: dict[str, Any]) -> dict[str, Any]:
    if not static_enrichment:
        return {"available": False}
    inventory = dict(static_enrichment.get("callable_inventory") or {})
    prereqs = dict(static_enrichment.get("prerequisite_hints") or {})
    deferred = dict(static_enrichment.get("deferred_static") or {})
    recommendation = dict(static_enrichment.get("admission_recommendation") or {})
    return {
        "available": True,
        "schema_version": static_enrichment.get("schema_version"),
        "source_status": dict(static_enrichment.get("source_status") or {}),
        "callable_total": int(inventory.get("total") or 0),
        "callable_emitted": int(inventory.get("emitted") or 0),
        "role_hint_count": len(list(inventory.get("role_hints") or [])),
        "prerequisite_hint_count": len(list(prereqs.get("entries") or [])),
        "deferred_snippet_count": len(list(deferred.get("bounded_decompile_snippets") or [])),
        "xref_note_count": len(list(deferred.get("xref_notes") or [])),
        "usable_for_s01_targets": bool(recommendation.get("usable_for_s01_targets")),
        "admission_risk": str(recommendation.get("admission_risk") or ""),
    }


def _static_enrichment_deferred(static_enrichment: dict[str, Any]) -> dict[str, Any]:
    if not static_enrichment:
        return {"available": False}
    deferred = dict(static_enrichment.get("deferred_static") or {})
    return {
        "available": True,
        "bounded_decompile_snippets": list(deferred.get("bounded_decompile_snippets") or [])[:5],
        "xref_notes": list(deferred.get("xref_notes") or [])[:5],
        "data_type_preview": list(deferred.get("data_type_preview") or [])[:10],
        "policy": "deferred_static_not_s01_truth",
    }


def _admitted_static_targets(
    s01_targets: dict[str, Any],
    static_enrichment: dict[str, Any],
    invocables: list[dict[str, Any]],
) -> dict[str, Any]:
    if not static_enrichment:
        return s01_targets
    invocable_names = {
        str(inv.get("name") or "").strip()
        for inv in invocables or []
        if isinstance(inv, dict) and str(inv.get("name") or "").strip()
    }
    prereqs = dict(static_enrichment.get("prerequisite_hints") or {})
    init_from_enrichment = _dedupe([
        name for name in list(prereqs.get("strong_init_candidates") or [])
        if str(name or "").strip() in invocable_names
    ])
    write_from_enrichment = _dedupe([
        name for name in list(prereqs.get("strong_write_candidates") or [])
        if str(name or "").strip() in invocable_names
    ])
    unmatched = _dedupe([
        name for name in list(prereqs.get("strong_init_candidates") or []) + list(prereqs.get("strong_write_candidates") or [])
        if str(name or "").strip() and str(name or "").strip() not in invocable_names
    ])
    if not init_from_enrichment and not write_from_enrichment and not unmatched:
        return s01_targets

    target_cap = int((s01_targets.get("quality") or {}).get("target_cap") or 12)
    merged_init_raw = _dedupe(init_from_enrichment + list(s01_targets.get("init_candidates") or []))
    merged_write_raw = _dedupe(write_from_enrichment + list(s01_targets.get("write_candidates") or []))
    merged_init = merged_init_raw[:target_cap]
    merged_write = merged_write_raw[:target_cap]
    quality_flags: list[str] = []
    if not merged_init:
        quality_flags.append("no_init_candidates")
    if not merged_write:
        quality_flags.append("no_write_candidates")
    if not (s01_targets.get("focus_ids") or []):
        quality_flags.append("no_focus_ids")
    if len(merged_init_raw) > len(merged_init) or len(merged_write_raw) > len(merged_write):
        quality_flags.append("target_cap_applied")
    if init_from_enrichment or write_from_enrichment:
        quality_flags.append("static_enrichment_targets_admitted")
    if unmatched:
        quality_flags.append("static_enrichment_targets_unmatched")

    merged = dict(s01_targets)
    merged["init_candidates"] = merged_init
    merged["write_candidates"] = merged_write
    merged["quality"] = {
        **dict(s01_targets.get("quality") or {}),
        "raw_init_candidate_count": len(merged_init_raw),
        "raw_write_candidate_count": len(merged_write_raw),
        "emitted_init_candidate_count": len(merged_init),
        "emitted_write_candidate_count": len(merged_write),
        "static_enrichment_init_candidate_count": len(init_from_enrichment),
        "static_enrichment_write_candidate_count": len(write_from_enrichment),
        "target_cap": target_cap,
        "target_cap_applied": "target_cap_applied" in quality_flags,
        "unmatched_targets": unmatched,
        "quality_flags": quality_flags,
    }
    return merged


def _coordinator_review_seed(s01_targets: dict[str, Any], admission_risk: list[str]) -> dict[str, Any]:
    quality = dict(s01_targets.get("quality") or {})
    flags = set(quality.get("quality_flags") or [])
    return {
        "rubric_version": "coordinator_review_draft_v0",
        "status": "deterministic_pre_coordinator_review",
        "categories": {
            "admission_precision": (
                "bounded_by_regex_and_cap"
                if "target_cap_applied" not in flags
                else "cap_applied_review_breadth"
            ),
            "admission_recall": "heuristic_only_not_semantic_truth",
            "deferral_quality": "deferred_static_and_ambiguity_register_kept_out_of_active_slice",
            "revival_judgment": "not_attempted_by_current_deterministic_packet",
            "repair_routing": (
                "review_required"
                if admission_risk or flags
                else "no_repair_signal_from_current_packet"
            ),
            "target_narrowing": (
                "usable_targets_present"
                if s01_targets.get("init_candidates") or s01_targets.get("write_candidates")
                else "target_set_thin"
            ),
            "risk_honesty": "admission_risk_and_quality_flags_present",
            "non_ownership_discipline": "admission_guidance_only_not_semantic_truth",
            "downstream_usefulness": "S-01_can_prioritize_matching_targets",
            "breakage_attribution": "producer_coordinator_consumer_surfaces_remain_distinct",
        },
    }


def build_s00_s01_handoff_packet(ctx) -> dict[str, Any]:
    """Normalize S-00 setup/static outputs into one additive handoff packet."""
    static_result = dict(getattr(ctx, "static_analysis_result", {}) or {})
    dll_strings = dict(getattr(ctx, "dll_strings", {}) or {})
    vocab = dict(getattr(ctx, "vocab", {}) or {})
    sentinels = dict(getattr(ctx, "sentinels", {}) or {})
    call_graph = dict(getattr(ctx, "call_graph", {}) or {})
    ghidra_data_types = list(getattr(ctx, "ghidra_data_types", []) or [])
    static_enrichment = dict(getattr(ctx, "static_enrichment", {}) or {})

    ambiguity_notes: list[str] = []
    if not dll_strings.get("ids"):
        ambiguity_notes.append("static ids surface is thin")
    if not sentinels:
        ambiguity_notes.append("no calibrated sentinels available")
    if not static_result:
        ambiguity_notes.append("static analysis result unavailable")
    for note in list(static_enrichment.get("ambiguities") or []):
        note = str(note or "").strip()
        if note:
            ambiguity_notes.append(f"static enrichment: {note}")

    baseline_truth = {
        "sentinels": _hexify_sentinels(sentinels),
        "user_context": str(getattr(ctx, "use_cases_text", "") or ""),
        "sentinel_count": len(sentinels),
    }
    surface_inventory = {
        "dll_strings": dll_strings,
        "static_analysis_summary": {
            "binary_string_ids": len(list((static_result.get("binary_strings") or {}).get("ids_found") or [])),
            "binary_string_emails": len(list((static_result.get("binary_strings") or {}).get("emails_found") or [])),
            "iat_categories": sorted(list(((static_result.get("iat_capabilities") or {}).get("categories") or {}).keys())),
            "call_graph_functions": len(call_graph),
            "ghidra_data_types_count": len(ghidra_data_types),
        },
        "static_enrichment_summary": _static_enrichment_summary(static_enrichment),
    }
    prior_hints = {
        "id_formats": list(vocab.get("id_formats") or []),
        "error_codes": dict(vocab.get("error_codes") or {}),
        "value_semantics": dict(vocab.get("value_semantics") or {}),
        "user_context": str(vocab.get("user_context") or getattr(ctx, "use_cases_text", "") or ""),
    }
    deferred_static = {
        "available_artifacts": [
            name for name, enabled in (
                ("call_graph.json", bool(call_graph)),
                ("ghidra_data_types.json", bool(ghidra_data_types)),
                ("static_analysis.json", bool(static_result)),
                ("static_enrichment.json", bool(static_enrichment)),
            )
            if enabled
        ],
        "call_graph_preview": sorted(list(call_graph.keys()))[:10],
        "ghidra_data_type_names": [
            str(entry.get("name") or "")
            for entry in ghidra_data_types[:10]
            if isinstance(entry, dict) and str(entry.get("name") or "").strip()
        ],
        "static_enrichment": _static_enrichment_deferred(static_enrichment),
    }
    invocables = list(getattr(ctx, "invocables", []) or [])
    s01_targets = _admitted_static_targets(
        _packet_targets(invocables, dll_strings),
        static_enrichment,
        invocables,
    )
    target_quality = dict(s01_targets.get("quality") or {})
    for flag in target_quality.get("quality_flags") or []:
        ambiguity_notes.append(f"s01 target quality flag: {flag}")
    coordinator_review = _coordinator_review_seed(s01_targets, ambiguity_notes)

    admitted_forward = {
        "baseline_truth": baseline_truth,
        "surface_inventory": {
            "dll_strings": dll_strings,
            "static_enrichment_summary": surface_inventory["static_enrichment_summary"],
        },
        "s01_targets": s01_targets,
    }
    if any(prior_hints.get(key) for key in ("id_formats", "error_codes", "value_semantics", "user_context")):
        admitted_forward["prior_hints"] = prior_hints

    packet = {
        "packet_version": "1.0.0",
        "producer_stage": "S-00",
        "consumer_stage": "S-01",
        "baseline_truth": baseline_truth,
        "surface_inventory": surface_inventory,
        "prior_hints": prior_hints,
        "deferred_static": deferred_static,
        "ambiguity_register": {
            "notes": ambiguity_notes,
        },
        "s01_targets": s01_targets,
        "review_verdict": {
            "handoff_legal": True,
            "contract_met": bool(static_result or dll_strings or vocab or sentinels),
            "notes": "additive first-pass S-00 -> S-01 handoff packet",
        },
        "coordination_decision": {
            "flow_outcome": "advance",
            "admitted_forward": admitted_forward,
            "kept_deferred": ["deferred_static", "ambiguity_register"],
            "revived_from_deferred": [],
            "target_narrowing": {
                "init_candidates": s01_targets.get("init_candidates", []),
                "write_candidates": s01_targets.get("write_candidates", []),
                "quality": target_quality,
            },
            "admission_risk": ambiguity_notes,
            "admission_quality": {
                "s01_target_quality": target_quality,
                "coordinator_review_seed": coordinator_review,
            },
        },
    }

    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/{S00_S01_HANDOFF_BLOB}",
            json.dumps(packet, indent=2).encode(),
        )
    except Exception as exc:
        logger.debug("[%s] s00->s01 handoff packet upload failed: %s", ctx.job_id, exc)

    ctx.s00_s01_handoff_packet = packet
    return packet


def load_s00_s01_handoff_packet(ctx) -> dict[str, Any]:
    """Load the additive packet from context first, then blob storage."""
    packet = dict(getattr(ctx, "s00_s01_handoff_packet", {}) or {})
    if packet:
        return packet
    try:
        data = _download_blob(ARTIFACT_CONTAINER, f"{ctx.job_id}/{S00_S01_HANDOFF_BLOB}")
    except Exception:
        return {}
    try:
        packet = json.loads(data.decode("utf-8"))
    except Exception:
        return {}
    ctx.s00_s01_handoff_packet = packet
    return packet


def admit_s00_s01_handoff(ctx) -> dict[str, Any]:
    """Return the admitted S-00 working slice for S-01 with legacy fallback."""
    packet = load_s00_s01_handoff_packet(ctx)
    admitted = dict(((packet.get("coordination_decision") or {}).get("admitted_forward")) or {})
    baseline_truth = dict(admitted.get("baseline_truth") or {})
    surface_inventory = dict(admitted.get("surface_inventory") or {})
    prior_hints = dict(admitted.get("prior_hints") or {})
    s01_targets = dict(admitted.get("s01_targets") or packet.get("s01_targets") or {})

    packet_dll_strings = dict(surface_inventory.get("dll_strings") or {})
    if any(packet_dll_strings.get(key) for key in ("ids", "emails", "all")):
        admitted_dll_strings = packet_dll_strings
    else:
        admitted_dll_strings = dict(getattr(ctx, "dll_strings", {}) or {})

    admitted_sentinels = dict(getattr(ctx, "sentinels", {}) or {})
    for key, value in (baseline_truth.get("sentinels") or {}).items():
        try:
            admitted_sentinels[int(str(key), 16)] = value
        except Exception:
            admitted_sentinels[key] = value

    admitted_vocab = dict(getattr(ctx, "vocab", {}) or {})
    for key, value in prior_hints.items():
        admitted_vocab[key] = value

    if packet:
        ctx.s00_s01_handoff_packet = packet
    return {
        "packet": packet,
        "vocab": admitted_vocab,
        "dll_strings": admitted_dll_strings,
        "sentinels": admitted_sentinels,
        "s01_targets": s01_targets,
    }
