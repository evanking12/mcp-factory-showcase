from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.pipeline.core.floor_iteration import classify_package_floor_evidence


PACKAGE_FLOOR_VALIDITY_SCHEMA_VERSION = "1.0.0"
PACKAGE_FLOOR_GATE_ARTIFACT = "package-floor-validity-gate.json"
PACKAGE_FLOOR_REPLAY_AUDIT_ARTIFACT = "replay-entry-surface-audit.json"

UPLOAD_ORIGINS = {"temp_upload", "bridge_cache"}
ANALYZE_PATH_ORIGINS = {"repo_fixture", "filesystem_path"}
VALID_PACKAGE_FLOOR_CLAIM_SCOPES = (
    "debug_only",
    "frontier_rehearsal_only",
    "overlap_comparable_confirmation",
)


def _nonempty_text(value: Any) -> str:
    return str(value or "").strip()


def _nonempty_list(values: Any) -> list[str]:
    ordered: list[str] = []
    for value in list(values or []):
        text = _nonempty_text(value)
        if text and text not in ordered:
            ordered.append(text)
    return ordered


def _unique_nonempty(values: list[str]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        text = _nonempty_text(value)
        if text and text not in ordered:
            ordered.append(text)
    return ordered


def resolve_package_floor_entry_surface(
    *,
    baseline_contract: dict[str, Any] | None,
    active_frontier_rows: list[dict[str, Any]] | None,
) -> str:
    baseline_entries = list((baseline_contract or {}).get("entries") or [])
    baseline_surfaces = _unique_nonempty(
        [_nonempty_text(entry.get("analysis_entrypoint")) for entry in baseline_entries]
    )
    if len(baseline_surfaces) == 1:
        return baseline_surfaces[0]
    frontier_surfaces = _unique_nonempty(
        [_nonempty_text(row.get("analysis_entrypoint")) for row in list(active_frontier_rows or [])]
    )
    if len(frontier_surfaces) == 1:
        return frontier_surfaces[0]
    return ""


def _allowed_binary_origins_for_surface(entry_surface: str) -> list[str]:
    surface = _nonempty_text(entry_surface).lower()
    if surface == "upload":
        return sorted(UPLOAD_ORIGINS)
    if surface == "analyze_path":
        return sorted(ANALYZE_PATH_ORIGINS)
    return []


def build_package_floor_validity_gate(
    *,
    campaign_truth: dict[str, Any],
    final_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_status = dict(final_status or {})
    baseline_contract = dict(campaign_truth.get("baseline_contract") or {})
    per_dll = [dict(row) for row in list(campaign_truth.get("per_dll") or [])]
    active_frontier_rows = [row for row in per_dll if bool(row.get("active_frontier"))]
    imported_rows = [row for row in per_dll if bool(row.get("imported_lower_floor"))]
    active_frontier_dlls = _nonempty_list(campaign_truth.get("active_frontier_dlls"))
    phase = _nonempty_text(final_status.get("phase") or campaign_truth.get("phase"))

    active_frontier_defined = bool(active_frontier_rows) and bool(active_frontier_dlls)
    imported_lower_floor_truth_recorded = bool(imported_rows) and bool(
        campaign_truth.get("imported_lower_floor_dlls")
    )
    comparable_profile_consistent = bool(campaign_truth.get("overlap_baseline_comparable"))
    run_valid_green = bool(campaign_truth.get("package_internal_truth_ready"))
    package_floor_evidence_class = _nonempty_text(
        campaign_truth.get("package_floor_evidence_class")
    ) or classify_package_floor_evidence(
        baseline_contract_present=bool(baseline_contract),
        active_frontier_defined=active_frontier_defined,
        imported_lower_floor_truth_recorded=imported_lower_floor_truth_recorded,
        comparable_profile_consistent=comparable_profile_consistent,
        run_valid_green=run_valid_green,
    )

    canonical_entry_surface = resolve_package_floor_entry_surface(
        baseline_contract=baseline_contract,
        active_frontier_rows=active_frontier_rows,
    )
    allowed_binary_origins = _allowed_binary_origins_for_surface(canonical_entry_surface)

    frontier_job_ids = _unique_nonempty([_nonempty_text(row.get("job_id")) for row in active_frontier_rows])
    baseline_job_ids = _unique_nonempty(
        [_nonempty_text(entry.get("baseline_job_id")) for entry in list(baseline_contract.get("entries") or [])]
    )
    imported_source_job_ids = _unique_nonempty(
        [_nonempty_text(row.get("imported_from_job_id")) for row in imported_rows]
    )

    entry_surface_mismatches: list[dict[str, Any]] = []
    stale_replay_rows: list[dict[str, Any]] = []
    fresh_frontier_rows: list[str] = []
    for row in active_frontier_rows:
        job_id = _nonempty_text(row.get("job_id"))
        analysis_entrypoint = _nonempty_text(row.get("analysis_entrypoint"))
        binary_origin = _nonempty_text(row.get("binary_origin"))
        stale_reasons: list[str] = []
        if job_id and job_id == _nonempty_text(row.get("prior_job_id")):
            stale_reasons.append("job_id_equals_prior_job_id")
        if job_id and job_id in _nonempty_list(row.get("cross_dll_prior_job_ids")):
            stale_reasons.append("job_id_reused_from_cross_dll_prior")
        if job_id and job_id in baseline_job_ids:
            stale_reasons.append("job_id_reused_from_overlap_baseline")
        if job_id and job_id in imported_source_job_ids:
            stale_reasons.append("job_id_reused_from_imported_lower_floor")
        if stale_reasons:
            stale_replay_rows.append(
                {
                    "job_id": job_id,
                    "filename": _nonempty_text(row.get("filename")),
                    "reasons": stale_reasons,
                }
            )
        elif job_id:
            fresh_frontier_rows.append(job_id)

        if canonical_entry_surface and analysis_entrypoint != canonical_entry_surface:
            entry_surface_mismatches.append(
                {
                    "job_id": job_id,
                    "filename": _nonempty_text(row.get("filename")),
                    "field": "analysis_entrypoint",
                    "expected": canonical_entry_surface,
                    "actual": analysis_entrypoint,
                }
            )
        if allowed_binary_origins and binary_origin not in allowed_binary_origins:
            entry_surface_mismatches.append(
                {
                    "job_id": job_id,
                    "filename": _nonempty_text(row.get("filename")),
                    "field": "binary_origin",
                    "expected": allowed_binary_origins,
                    "actual": binary_origin,
                }
            )

    active_status_rows = [dict(row) for row in list(final_status.get("dll_entries") or []) if _nonempty_text(row.get("filename")) in active_frontier_dlls]
    active_status_map = {
        _nonempty_text(row.get("filename")): dict(row)
        for row in active_status_rows
        if _nonempty_text(row.get("filename"))
    }
    terminal_frontier_statuses = {"done", "partial_failure", "cancelled_partial"}
    nonterminal_frontier_rows = [
        {
            "filename": filename,
            "job_status": _nonempty_text(row.get("job_status") or row.get("status")),
            "explore_phase": _nonempty_text(row.get("explore_phase")),
        }
        for filename, row in active_status_map.items()
        if _nonempty_text(row.get("job_status") or row.get("status")).lower() not in terminal_frontier_statuses
    ]

    phase_terminal = phase.lower() in terminal_frontier_statuses | {"done"}
    frontier_jobs_terminal = not nonterminal_frontier_rows and bool(active_status_rows)
    frontier_rows_fresh = bool(fresh_frontier_rows) and not stale_replay_rows
    entry_surface_consistent = bool(canonical_entry_surface) and not entry_surface_mismatches
    runtime_path_trusted = all(
        _nonempty_text(row.get("runtime_path_trust")).lower() in {"echoed", "trusted"}
        for row in active_frontier_rows
    )
    lane_trusted = all(
        _nonempty_text(row.get("lane_trust_status")).lower() == "trusted"
        for row in active_frontier_rows
    )
    all_frontier_jobs_present = len(frontier_job_ids) == len(active_frontier_rows) and bool(active_frontier_rows)

    if package_floor_evidence_class == "overlap_comparable_confirmation":
        claim_scope = "overlap_comparable_confirmation"
    elif package_floor_evidence_class == "valid_frontier_rehearsal":
        claim_scope = "frontier_rehearsal_only"
    else:
        claim_scope = "debug_only"

    valid_for_package_floor_claim = all(
        [
            claim_scope in VALID_PACKAGE_FLOOR_CLAIM_SCOPES,
            claim_scope != "debug_only",
            entry_surface_consistent,
            frontier_rows_fresh,
            phase_terminal,
            frontier_jobs_terminal,
            all_frontier_jobs_present,
            runtime_path_trusted,
            lane_trusted,
        ]
    )
    valid_for_comparable_policy = valid_for_package_floor_claim and (
        package_floor_evidence_class == "overlap_comparable_confirmation"
    )

    disqualifiers: list[str] = []
    if not active_frontier_defined:
        disqualifiers.append("active_frontier_missing")
    if not imported_lower_floor_truth_recorded:
        disqualifiers.append("imported_lower_floor_truth_missing")
    if not phase_terminal:
        disqualifiers.append("campaign_not_terminal")
    if not frontier_jobs_terminal:
        disqualifiers.append("frontier_jobs_not_terminal")
    if not all_frontier_jobs_present:
        disqualifiers.append("frontier_job_ids_missing")
    if not canonical_entry_surface:
        disqualifiers.append("canonical_entry_surface_missing")
    if entry_surface_mismatches:
        disqualifiers.append("entry_surface_mismatch")
    if stale_replay_rows:
        disqualifiers.append("stale_replay_reuse_detected")
    if not runtime_path_trusted:
        disqualifiers.append("runtime_path_untrusted")
    if not lane_trusted:
        disqualifiers.append("lane_not_trusted")
    if claim_scope == "debug_only":
        disqualifiers.append("package_floor_debug_only")
    if not comparable_profile_consistent:
        disqualifiers.append("overlap_profile_inconsistent")

    replay_entry_surface_audit = {
        "schema_version": PACKAGE_FLOOR_VALIDITY_SCHEMA_VERSION,
        "campaign_id": _nonempty_text(campaign_truth.get("campaign_id")),
        "package_id": _nonempty_text(campaign_truth.get("package_id")),
        "active_frontier_dlls": active_frontier_dlls,
        "canonical_entry_surface": canonical_entry_surface,
        "allowed_binary_origins": allowed_binary_origins,
        "frontier_job_ids": frontier_job_ids,
        "fresh_frontier_job_ids": fresh_frontier_rows,
        "baseline_job_ids": baseline_job_ids,
        "imported_source_job_ids": imported_source_job_ids,
        "stale_replay_rows": stale_replay_rows,
        "entry_surface_mismatches": entry_surface_mismatches,
        "nonterminal_frontier_rows": nonterminal_frontier_rows,
        "runtime_path_trusted": runtime_path_trusted,
        "lane_trusted": lane_trusted,
    }

    return {
        "schema_version": PACKAGE_FLOOR_VALIDITY_SCHEMA_VERSION,
        "campaign_id": _nonempty_text(campaign_truth.get("campaign_id")),
        "package_id": _nonempty_text(campaign_truth.get("package_id")),
        "package_label": _nonempty_text(campaign_truth.get("package_label")),
        "phase": phase,
        "package_floor_evidence_class": package_floor_evidence_class,
        "claim_scope": claim_scope,
        "valid_for_package_floor_claim": valid_for_package_floor_claim,
        "valid_for_comparable_policy": valid_for_comparable_policy,
        "active_frontier_defined": active_frontier_defined,
        "imported_lower_floor_truth_recorded": imported_lower_floor_truth_recorded,
        "comparable_profile_consistent": comparable_profile_consistent,
        "run_valid_green": run_valid_green,
        "canonical_entry_surface": canonical_entry_surface,
        "entry_surface_consistent": entry_surface_consistent,
        "frontier_jobs_fresh": frontier_rows_fresh,
        "frontier_jobs_terminal": frontier_jobs_terminal,
        "all_frontier_jobs_present": all_frontier_jobs_present,
        "runtime_path_trusted": runtime_path_trusted,
        "lane_trusted": lane_trusted,
        "disqualifiers": disqualifiers,
        "replay_entry_surface_audit": replay_entry_surface_audit,
    }


def write_package_floor_validity_artifacts(
    output_dir: Path,
    gate: dict[str, Any],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    gate_path = output_dir / PACKAGE_FLOOR_GATE_ARTIFACT
    replay_audit_path = output_dir / PACKAGE_FLOOR_REPLAY_AUDIT_ARTIFACT
    gate_path.write_text(json.dumps(gate, indent=2), encoding="utf-8")
    replay_audit_path.write_text(
        json.dumps(gate.get("replay_entry_surface_audit") or {}, indent=2),
        encoding="utf-8",
    )
    return {
        "gate_path": str(gate_path),
        "replay_audit_path": str(replay_audit_path),
    }
