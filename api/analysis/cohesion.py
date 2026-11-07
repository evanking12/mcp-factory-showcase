from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _download_blob, _get_job_status, _load_findings, _upload_to_blob
from api.analysis.blocker_harvest import (
    infer_blocker_family_and_system,
    summarize_campaign_blocker_harvest,
)
from api.pipeline.core.cluster_checkpoint import CLUSTER_CHECKPOINTS_BY_ID
from api.pipeline.core.cross_dll_contracts import (
    build_business_object_contract_surface,
    latest_findings_by_job as _latest_findings_by_job,
)
from api.pipeline.core.floor_iteration import classify_package_floor_evidence
from api.pipeline.core.finding_status import STATUS_ORDER as _STATUS_ORDER, normalize_status
from api.pipeline.core.handoff_contract import (
    AUDITOR_VERSION,
    CONTRACT_VERSION,
    STAGE_CONTRACTS,
    TRANSITION_CONTRACT_BY_ID,
    TRANSITION_SEVERITY,
    stage_optional_skip_reasons,
    stage_skip_reason_is_allowed,
)
from api.pipeline.core.package_frontier_planner import resolve_campaign_package_baseline_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_LEDGER_PATH = REPO_ROOT / "sessions" / "ledger" / "run_ledger.jsonl"
LOCAL_ARTIFACTS_ROOT = REPO_ROOT / "local-data" / "artifacts"
FUNCTION_CLUSTERS: dict[str, tuple[str, ...]] = {}
for _cluster_id, _cluster in CLUSTER_CHECKPOINTS_BY_ID.items():
    for _function_name in _cluster.function_names:
        FUNCTION_CLUSTERS.setdefault(str(_function_name), []).append(_cluster_id)
FUNCTION_CLUSTERS = {
    function_name: tuple(cluster_ids)
    for function_name, cluster_ids in FUNCTION_CLUSTERS.items()
}


def _try_blob(job_id: str, blob_name: str) -> bytes | None:
    try:
        return _download_blob(ARTIFACT_CONTAINER, f"{job_id}/{blob_name}")
    except Exception:
        return None


def _try_json(job_id: str, blob_name: str) -> Any | None:
    raw = _try_blob(job_id, blob_name)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _as_text(data: bytes | None) -> str:
    if not data:
        return ""
    return data.decode("utf-8", errors="replace")


def _hash(data: bytes | None) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def _latest_status_by_function(findings: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for f in findings:
        fn = str(f.get("function") or "").strip()
        if fn:
            latest[fn] = f
    return latest


def _campaign_blob_name(campaign_id: str, blob_name: str) -> str:
    return f"campaigns/{campaign_id}/{blob_name}"


def _try_campaign_json(campaign_id: str, blob_name: str) -> dict[str, Any] | None:
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, _campaign_blob_name(campaign_id, blob_name))
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _count_verified_rows(latest_rows: dict[str, dict]) -> int:
    return sum(
        1
        for row in latest_rows.values()
        if str((row or {}).get("status") or (row or {}).get("status_canonical") or "")
        in {"success", "verified_success"}
    )


def _read_run_ledger_rows() -> list[dict[str, Any]]:
    if not RUN_LEDGER_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in RUN_LEDGER_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _latest_ledger_index_for_job(rows: list[dict[str, Any]], job_id: str) -> int:
    latest_idx = -1
    latest_capture = -1
    for idx, row in enumerate(rows):
        if str(row.get("job_id") or "") != job_id:
            continue
        capture_seq = int(row.get("capture_seq") or 0)
        if capture_seq >= latest_capture:
            latest_capture = capture_seq
            latest_idx = idx
    return latest_idx


def _previous_comparable_ledger_row(rows: list[dict[str, Any]], current_idx: int) -> dict[str, Any] | None:
    if current_idx < 0 or current_idx >= len(rows):
        return None
    current = rows[current_idx]
    comparable_key = str(current.get("comparable_profile_key") or "").strip()
    dll_fingerprint = str(current.get("dll_fingerprint") or "").strip()
    component = str(current.get("component") or "").strip()
    current_job_id = str(current.get("job_id") or "").strip()
    if not comparable_key:
        return None
    for idx in range(current_idx - 1, -1, -1):
        row = rows[idx]
        if str(row.get("job_id") or "").strip() == current_job_id:
            continue
        if str(row.get("comparable_profile_key") or "").strip() != comparable_key:
            continue
        same_dll = dll_fingerprint and str(row.get("dll_fingerprint") or "").strip() == dll_fingerprint
        same_component = component and str(row.get("component") or "").strip() == component
        if same_dll or same_component:
            return row
    return None


def _status_rank(status: str) -> int:
    return dict(_STATUS_ORDER).get(normalize_status(status), 0)


def _status_delta(current_status: str, baseline_status: str) -> str:
    current = normalize_status(current_status)
    baseline = normalize_status(baseline_status)
    if not baseline:
        return "no_baseline"
    if current == baseline:
        return "flat"
    if _status_rank(current) > _status_rank(baseline):
        return "improved"
    if _status_rank(current) < _status_rank(baseline):
        return "regressed"
    return "changed"


def _surface_context_for_job(job_id: str) -> dict[str, str]:
    if not job_id:
        return {}
    status = _get_job_status(job_id) or {}
    runtime = status.get("explore_runtime") or {}
    return {
        "analysis_entrypoint": str(status.get("analysis_entrypoint") or "").strip(),
        "binary_origin": str(status.get("binary_origin") or "").strip(),
        "analysis_profile": str(runtime.get("analysis_profile") or status.get("analysis_profile") or "").strip(),
    }


def _surface_mismatch_reasons(
    current_surface: dict[str, str],
    baseline_surface: dict[str, str],
) -> list[str]:
    reasons: list[str] = []
    for key in ("analysis_entrypoint", "binary_origin", "analysis_profile"):
        current_value = str(current_surface.get(key) or "").strip()
        baseline_value = str(baseline_surface.get(key) or "").strip()
        if current_value and baseline_value and current_value != baseline_value:
            reasons.append(f"{key}:{baseline_value}->{current_value}")
    return reasons


def _baseline_contract_index(campaign: dict[str, Any]) -> dict[str, dict[str, Any]]:
    baseline_contract = campaign.get("baseline_contract") or {}
    entries = []
    if isinstance(baseline_contract, dict):
        entries = list(baseline_contract.get("dll_entries") or [])
    elif isinstance(baseline_contract, list):
        entries = list(baseline_contract)
    index: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        keys = [
            str(entry.get("component") or "").strip(),
            str(entry.get("dll_id") or "").strip(),
            str(entry.get("filename") or "").strip(),
        ]
        for key in keys:
            if key:
                index[key] = entry
    return index


def _baseline_entry_for_dll(
    dll_row: dict[str, Any],
    baseline_index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = [
        str(dll_row.get("component") or "").strip(),
        str(dll_row.get("dll_id") or "").strip(),
        str(dll_row.get("filename") or "").strip(),
    ]
    for key in candidates:
        if key and key in baseline_index:
            return baseline_index[key]
    return None


def _baseline_requirement_for_dll(
    dll_row: dict[str, Any],
    baseline_index: dict[str, dict[str, Any]],
    campaign: dict[str, Any],
) -> tuple[bool, bool]:
    baseline_entry = _baseline_entry_for_dll(dll_row, baseline_index)
    if baseline_entry:
        return True, False
    baseline_contract = campaign.get("baseline_contract") or {}
    overlap_set = {
        str(item).strip()
        for item in list((baseline_contract or {}).get("overlap_dll_set") or [])
        if str(item).strip()
    }
    no_baseline_required = {
        str(item).strip()
        for item in list((baseline_contract or {}).get("no_baseline_required_dlls") or [])
        if str(item).strip()
    }
    candidates = {
        str(dll_row.get("component") or "").strip(),
        str(dll_row.get("dll_id") or "").strip(),
        str(dll_row.get("filename") or "").strip(),
    }
    requires_baseline = bool(candidates & overlap_set)
    baseline_not_required = bool(candidates & no_baseline_required)
    return requires_baseline, baseline_not_required


def _artifact_refs(job_id: str, baseline_job_id: str = "") -> dict[str, Any]:
    refs = {
        "findings": f"{job_id}/findings.json",
        "status": f"{job_id}/status.json",
        "stage_kpis": f"{job_id}/stage_kpis.json",
        "verification_report": f"{job_id}/verification-report.json",
        "gap_execution_trace": f"{job_id}/gap_execution_trace.json",
    }
    if baseline_job_id:
        refs["baseline_findings"] = f"{baseline_job_id}/findings.json"
        refs["baseline_status"] = f"{baseline_job_id}/status.json"
    return refs


def _first_blocking_stage(row: dict[str, Any]) -> str:
    source_stage = str(row.get("source_stage") or "").strip()
    if source_stage:
        return source_stage
    finding_text = " ".join(
        str(row.get(k) or "")
        for k in ("finding", "notes", "technical_detail", "technical_question", "cross_validation")
    ).lower()
    if "gap resolution" in finding_text:
        return "s06_gaps"
    if str(row.get("verification") or "").strip().lower() == "verified":
        return "s05_enrichment"
    return "s02_probe"


def _evidence_seen(
    function_row: dict[str, Any],
    dll_row: dict[str, Any],
    verification_report: dict[str, Any] | None,
) -> list[str]:
    seen: list[str] = []
    if dll_row.get("bridge_reachable") is True:
        seen.append("bridge_backed_discovery")
    if function_row.get("working_call"):
        seen.append("working_call")
    if dll_row.get("prior_job_id"):
        seen.append("same_dll_prior")
    if dll_row.get("cross_dll_prior_job_ids"):
        seen.append("cross_dll_prior")
    if verification_report:
        entries = list((verification_report or {}).get("entries") or [])
        if any(str((entry or {}).get("function") or "") == str(function_row.get("function") or "") for entry in entries):
            seen.append("verification_entry")
    if function_row.get("interpretation"):
        seen.append("interpretation")
    return seen


def _infer_blocker_family_and_system(
    dll_row: dict[str, Any],
    function_row: dict[str, Any],
) -> tuple[str, str, str]:
    return infer_blocker_family_and_system(dll_row, function_row)


def _confidence_label(
    function_row: dict[str, Any],
    blocker_confidence: str,
    evidence_seen: list[str],
) -> str:
    status = normalize_status(function_row.get("status_canonical") or function_row.get("status"))
    if status == "verified_success":
        return "high"
    if blocker_confidence == "medium" and evidence_seen:
        return "medium"
    return "low"


def _build_function_rows(
    dll_row: dict[str, Any],
    ledger_rows: list[dict[str, Any]],
    explicit_baseline: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    job_id = str(dll_row.get("job_id") or "").strip()
    findings = _load_findings(job_id)
    latest = _latest_status_by_function(findings)
    verification_report = _try_json(job_id, "verification-report.json") or {}
    current_ledger_idx = _latest_ledger_index_for_job(ledger_rows, job_id)
    baseline_source = "missing"
    baseline_note = ""
    baseline_provisional = False
    baseline_row = None
    baseline_job_id = ""
    baseline_required = bool(dll_row.get("baseline_required"))
    no_baseline_required = bool(dll_row.get("no_baseline_required"))
    current_surface = {
        "analysis_entrypoint": str(dll_row.get("analysis_entrypoint") or "").strip(),
        "binary_origin": str(dll_row.get("binary_origin") or "").strip(),
        "analysis_profile": str(dll_row.get("analysis_profile") or "").strip(),
    }
    if explicit_baseline:
        baseline_job_id = str(explicit_baseline.get("baseline_job_id") or "").strip()
        baseline_source = str(explicit_baseline.get("source_type") or "explicit_curated").strip() or "explicit_curated"
        baseline_note = str(explicit_baseline.get("note") or "").strip()
        baseline_provisional = bool(explicit_baseline.get("provisional"))
    if not baseline_job_id:
        baseline_row = _previous_comparable_ledger_row(ledger_rows, current_ledger_idx)
        baseline_job_id = str((baseline_row or {}).get("job_id") or "").strip()
        if baseline_job_id:
            baseline_source = "nearest_comparable_ledger"
    if no_baseline_required and not baseline_job_id:
        baseline_source = "not_required_for_expansion"
        baseline_note = baseline_note or "newly added expansion-wave DLL"
    elif baseline_required and not baseline_job_id:
        baseline_source = "missing_required_overlap_baseline"
        baseline_note = baseline_note or "required overlap baseline missing"
    baseline_latest = _latest_status_by_function(_load_findings(baseline_job_id)) if baseline_job_id else {}
    baseline_surface = _surface_context_for_job(baseline_job_id) if baseline_job_id else {}
    surface_mismatch = _surface_mismatch_reasons(current_surface, baseline_surface)
    rows: list[dict[str, Any]] = []
    for function_name, row in latest.items():
        current_status = normalize_status(row.get("status_canonical") or row.get("status"))
        baseline_status = normalize_status((baseline_latest.get(function_name) or {}).get("status_canonical") or (baseline_latest.get(function_name) or {}).get("status"))
        blocker_family, missing_system, blocker_confidence = _infer_blocker_family_and_system(dll_row, row)
        evidence_seen = _evidence_seen(row, dll_row, verification_report)
        delta_vs_baseline = _status_delta(current_status, baseline_status)
        if baseline_required and not baseline_job_id:
            delta_vs_baseline = "incomparable"
        elif surface_mismatch and baseline_source != "nearest_comparable_ledger":
            delta_vs_baseline = "incomparable"
        rows.append(
            {
                "dll": dll_row.get("filename", ""),
                "component": dll_row.get("component", ""),
                "job_id": job_id,
                "function": function_name,
                "final_status": current_status,
                "baseline_status": baseline_status,
                "delta_vs_baseline": delta_vs_baseline,
                "baseline_job_id": baseline_job_id,
                "baseline_source": baseline_source,
                "baseline_note": baseline_note,
                "baseline_provisional": baseline_provisional,
                "baseline_required": baseline_required,
                "no_baseline_required": no_baseline_required,
                "baseline_surface_mismatch": list(surface_mismatch),
                "first_blocking_stage": _first_blocking_stage(row),
                "likely_blocker_family": blocker_family,
                "likely_missing_system": missing_system,
                "evidence_seen": evidence_seen,
                "working_call_present": bool(row.get("working_call")),
                "confidence": "low" if surface_mismatch or (baseline_required and not baseline_job_id) else _confidence_label(row, blocker_confidence, evidence_seen),
                "artifact_refs": _artifact_refs(job_id, baseline_job_id),
            }
        )
    return rows


def build_function_matrix_for_dll(
    dll_row: dict[str, Any],
    ledger_rows: list[dict[str, Any]],
    explicit_baseline: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Public wrapper for reusable per-DLL function attribution rows."""
    return _build_function_rows(dll_row, ledger_rows, explicit_baseline=explicit_baseline)


def _summarize_blocker_families(function_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for row in function_rows:
        family = str(row.get("likely_blocker_family") or "").strip()
        if not family or family == "unknown":
            continue
        entry = summary.setdefault(
            family,
            {"blocker_family": family, "function_count": 0, "dlls": set(), "representative_functions": [], "confidence": "medium"},
        )
        entry["function_count"] += 1
        entry["dlls"].add(str(row.get("dll") or ""))
        reps = entry["representative_functions"]
        if len(reps) < 3:
            reps.append(str(row.get("function") or ""))
    result: list[dict[str, Any]] = []
    for entry in summary.values():
        result.append(
            {
                "blocker_family": entry["blocker_family"],
                "function_count": entry["function_count"],
                "dll_count": len(entry["dlls"]),
                "representative_functions": entry["representative_functions"],
                "confidence": entry["confidence"],
            }
        )
    return sorted(result, key=lambda item: (-int(item["function_count"]), item["blocker_family"]))


def _summarize_system_opportunities(function_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for row in function_rows:
        system = str(row.get("likely_missing_system") or "").strip()
        if not system or system == "unknown":
            continue
        entry = summary.setdefault(
            system,
            {"candidate_system": system, "functions": [], "dlls": set(), "blocker_families": set(), "confidence": "medium", "risk": "bounded-first-wave"},
        )
        entry["functions"].append(str(row.get("function") or ""))
        entry["dlls"].add(str(row.get("dll") or ""))
        family = str(row.get("likely_blocker_family") or "").strip()
        if family:
            entry["blocker_families"].add(family)
    result: list[dict[str, Any]] = []
    for entry in summary.values():
        result.append(
            {
                "candidate_system": entry["candidate_system"],
                "functions_plausibly_helped": len(entry["functions"]),
                "dlls_touched": len(entry["dlls"]),
                "blocker_families_reduced": sorted(entry["blocker_families"]),
                "confidence": entry["confidence"],
                "risk": entry["risk"],
                "superseded_by": "",
            }
        )
    return sorted(result, key=lambda item: (-int(item["functions_plausibly_helped"]), item["candidate_system"]))


def _summarize_regressions(function_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    regressions: list[dict[str, Any]] = []
    for row in function_rows:
        if str(row.get("delta_vs_baseline") or "") != "regressed":
            continue
        regressions.append(
            {
                "dll": row.get("dll", ""),
                "function": row.get("function", ""),
                "old_status": row.get("baseline_status", ""),
                "new_status": row.get("final_status", ""),
                "likely_regression_cause": "unknown",
                "follow_up_class": "immediate_follow_up",
                "baseline_required": bool(row.get("baseline_required")),
            }
        )
    return regressions


def _summarize_stage_breakdown(function_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for row in function_rows:
        stage = str(row.get("first_blocking_stage") or "").strip()
        if not stage:
            continue
        entry = summary.setdefault(stage, {"stage": stage, "functions": 0, "families": set(), "systems": set()})
        entry["functions"] += 1
        family = str(row.get("likely_blocker_family") or "").strip()
        system = str(row.get("likely_missing_system") or "").strip()
        if family:
            entry["families"].add(family)
        if system:
            entry["systems"].add(system)
    return [
        {
            "stage": entry["stage"],
            "functions_first_blocked": entry["functions"],
            "blocker_family_mix": sorted(entry["families"]),
            "likely_missing_system_mix": sorted(entry["systems"]),
        }
        for entry in sorted(summary.values(), key=lambda item: (-int(item["functions"]), item["stage"]))
    ]


def _summarize_evidence_surface(function_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rows_with_working_call": sum(1 for row in function_rows if row.get("working_call_present")),
        "rows_with_same_dll_prior": sum(1 for row in function_rows if "same_dll_prior" in list(row.get("evidence_seen") or [])),
        "rows_with_cross_dll_prior": sum(1 for row in function_rows if "cross_dll_prior" in list(row.get("evidence_seen") or [])),
        "rows_with_verification_entry": sum(1 for row in function_rows if "verification_entry" in list(row.get("evidence_seen") or [])),
        "rows_with_bridge_backed_discovery": sum(1 for row in function_rows if "bridge_backed_discovery" in list(row.get("evidence_seen") or [])),
        "confidence_counts": {
            "high": sum(1 for row in function_rows if row.get("confidence") == "high"),
            "medium": sum(1 for row in function_rows if row.get("confidence") == "medium"),
            "low": sum(1 for row in function_rows if row.get("confidence") == "low"),
        },
    }


def _build_architect_summary(
    function_rows: list[dict[str, Any]],
    system_opportunities: list[dict[str, Any]],
    blocker_families: list[dict[str, Any]],
    regressions: list[dict[str, Any]],
) -> dict[str, Any]:
    improved = sum(1 for row in function_rows if row.get("delta_vs_baseline") == "improved")
    flat = sum(1 for row in function_rows if row.get("delta_vs_baseline") == "flat")
    regressed = len(regressions)
    leading_system = system_opportunities[0]["candidate_system"] if system_opportunities else ""
    dominant_family = blocker_families[0]["blocker_family"] if blocker_families else ""
    recommendation = "build_or_continue_reported_next_system" if leading_system else "collect_more_attribution"
    return {
        "improved_functions": improved,
        "flat_functions": flat,
        "regressed_functions": regressed,
        "dominant_blocker_family": dominant_family,
        "leading_candidate_system": leading_system,
        "recommended_next_move": recommendation,
    }


def _local_artifact_job_ids() -> list[str]:
    if not LOCAL_ARTIFACTS_ROOT.exists():
        return []
    return sorted(
        path.name
        for path in LOCAL_ARTIFACTS_ROOT.iterdir()
        if path.is_dir()
    )


def _try_local_artifact_json(job_id: str, filename: str) -> Any | None:
    path = LOCAL_ARTIFACTS_ROOT / str(job_id or "").strip() / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _function_cluster_ids(function_name: str) -> tuple[str, ...]:
    return FUNCTION_CLUSTERS.get(str(function_name or "").strip(), ())


def _verification_entry(
    report: dict[str, Any] | None,
    function_name: str,
) -> dict[str, Any] | None:
    for entry in list((report or {}).get("entries") or []):
        if str((entry or {}).get("function") or "").strip() == str(function_name or "").strip():
            return entry if isinstance(entry, dict) else None
    return None


def _status_strength(status: str) -> int:
    return int(_STATUS_ORDER.get(normalize_status(status), 0))


def _current_function_row(job_id: str, function_name: str) -> dict[str, Any] | None:
    latest = _latest_status_by_function(_load_findings(job_id))
    row = latest.get(str(function_name or "").strip())
    return row if isinstance(row, dict) else None


def _local_proof_candidate(
    job_id: str,
    component: str,
    function_name: str,
    cluster_id: str,
) -> dict[str, Any] | None:
    status = _try_local_artifact_json(job_id, "status.json") or {}
    if str(status.get("component_name") or "").strip() != component:
        return None
    runtime = dict(status.get("explore_runtime") or {})
    focus_functions = {
        str(name or "").strip()
        for name in list(runtime.get("focus_functions") or [])
        if str(name or "").strip()
    }
    if cluster_id:
        runtime_cluster = str(runtime.get("cluster_checkpoint_id") or "").strip()
        if runtime_cluster and runtime_cluster != cluster_id and function_name not in focus_functions:
            return None
    findings = _try_local_artifact_json(job_id, "findings.json") or []
    latest = _latest_status_by_function(findings if isinstance(findings, list) else [])
    target_row = latest.get(function_name)
    if not isinstance(target_row, dict):
        return None
    target_status = normalize_status(target_row.get("status_canonical") or target_row.get("status"))
    if target_status != "verified_success":
        return None
    verification_report = _try_local_artifact_json(job_id, "verification-report.json") or {}
    verification_entry = _verification_entry(verification_report, function_name)
    checkpoint = _try_local_artifact_json(job_id, "checkpoints/latest.json") or {}
    cluster_row = {}
    if cluster_id:
        cluster_row = dict(((checkpoint or {}).get("cluster_checkpoints") or {}).get(cluster_id) or {})
    return {
        "job_id": job_id,
        "status": status,
        "runtime": runtime,
        "target_row": target_row,
        "verification_entry": verification_entry,
        "checkpoint_cluster_row": cluster_row,
        "updated_at": float(status.get("updated_at") or 0.0),
        "gate_color": str(cluster_row.get("gate_color") or "").strip(),
    }


def _find_local_proof_job(
    *,
    current_job_id: str,
    component: str,
    function_name: str,
    cluster_id: str,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for job_id in _local_artifact_job_ids():
        candidate_id = str(job_id or "").strip()
        if not candidate_id or candidate_id == current_job_id:
            continue
        candidate = _local_proof_candidate(candidate_id, component, function_name, cluster_id)
        if candidate is not None:
            candidates.append(candidate)
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            1 if row.get("verification_entry") else 0,
            1 if str(row.get("gate_color") or "").strip().lower() == "green" else 0,
            float(row.get("updated_at") or 0.0),
            str(row.get("job_id") or ""),
        ),
        reverse=True,
    )
    return candidates[0]


def _target_probe_entries(job_id: str, function_name: str) -> list[dict[str, Any]]:
    probe_log = _try_json(job_id, "explore_probe_log.json") or []
    return [
        entry for entry in list(probe_log or [])
        if isinstance(entry, dict)
        and str(entry.get("function") or "").strip() == str(function_name or "").strip()
        and str(entry.get("phase") or "").strip() != "calibrate_sentinels"
    ]


def _direct_target_probe_entries(job_id: str, function_name: str) -> list[dict[str, Any]]:
    return [
        entry for entry in _target_probe_entries(job_id, function_name)
        if str(entry.get("tool") or "").strip() == str(function_name or "").strip()
        and str(entry.get("phase") or "").strip() in {"explore", "deterministic_fallback"}
    ]


def _entry_is_success(entry: dict[str, Any]) -> bool:
    classification = dict(entry.get("classification") or {})
    if classification.get("signed") == 0:
        return True
    result_excerpt = str(entry.get("result_excerpt") or "")
    return result_excerpt.startswith("Returned: 0")


def _finding_mentions_target(row: dict[str, Any], function_name: str) -> bool:
    corpus = " ".join(
        str(row.get(key) or "")
        for key in ("finding", "notes", "technical_detail", "technical_question", "cross_validation")
    ).lower()
    return f"for {str(function_name or '').strip().lower()}" in corpus


def _row_has_preserved_direct_target_truth(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    truth = row.get("direct_target_truth")
    if not isinstance(truth, dict):
        return False
    if truth.get("rejected_by_verification"):
        return False
    if str(truth.get("verification") or "").strip().lower() == "verified":
        return True
    try:
        return int(truth.get("return_value") or 1) == 0 and isinstance(truth.get("working_call"), dict)
    except Exception:
        return isinstance(truth.get("working_call"), dict)


def _carryover_failure_shape(
    *,
    target_function: str,
    cluster_id: str,
    producer_rows: list[dict[str, Any]],
    package_target_row: dict[str, Any] | None,
    package_target_entries: list[dict[str, Any]],
    package_direct_entries: list[dict[str, Any]],
    package_verification_entry: dict[str, Any] | None,
) -> tuple[str, str, str, str]:
    replayed_producers = [
        str(row.get("function") or "").strip()
        for row in producer_rows
        if _finding_mentions_target(row, target_function)
    ]
    preserved_direct_target_truth = _row_has_preserved_direct_target_truth(package_target_row)
    if replayed_producers and not package_direct_entries and package_verification_entry is None and not preserved_direct_target_truth:
        handoff_from = replayed_producers[-1]
        return (
            "package_orchestration_drop",
            "carryover_missing_direct_target_persistence",
            f"{handoff_from} -> {target_function}",
            "same-run producer proof was rebuilt for the target, but package mode never carried that state into a direct target execution or verification pass",
        )
    if (package_direct_entries and any(_entry_is_success(entry) for entry in package_direct_entries)) or preserved_direct_target_truth:
        return (
            "finding_recording_conflict",
            "carryover_probe_truth_not_persisted",
            f"{target_function} direct probe -> final finding",
            "package mode observed a direct target success, but the authoritative finding or verification surface did not preserve that stronger truth",
        )
    if (package_direct_entries or preserved_direct_target_truth) and package_verification_entry is None:
        return (
            "verifier_disagreement",
            "carryover_verification_gap_after_probe",
            f"{target_function} probe -> verification",
            "package mode reached the target probe surface, but verification did not preserve or confirm the probe truth before the final package summary was written",
        )
    return (
        "unexplained",
        "unknown",
        f"{cluster_id or 'package'} -> {target_function}",
        "carryover evidence is still too weak to isolate the first broken handoff from the available package and local proof artifacts",
    )


def _build_package_carryover_audits(
    function_rows: list[dict[str, Any]],
    per_dll_reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_job = {
        str(row.get("job_id") or "").strip(): row
        for row in per_dll_reports
        if str(row.get("job_id") or "").strip()
    }
    audits: list[dict[str, Any]] = []
    for row in function_rows:
        if str(row.get("delta_vs_baseline") or "") != "regressed":
            continue
        job_id = str(row.get("job_id") or "").strip()
        function_name = str(row.get("function") or "").strip()
        dll_row = by_job.get(job_id)
        if dll_row is None or not function_name:
            continue
        cluster_ids = _function_cluster_ids(function_name)
        if not cluster_ids:
            continue
        cluster_id = cluster_ids[0]
        cluster = CLUSTER_CHECKPOINTS_BY_ID.get(cluster_id)
        if cluster is None:
            continue
        local_proof = _find_local_proof_job(
            current_job_id=job_id,
            component=str(dll_row.get("component") or "").strip(),
            function_name=function_name,
            cluster_id=cluster_id,
        )
        if local_proof is None:
            continue
        package_latest = _latest_status_by_function(_load_findings(job_id))
        package_target_row = package_latest.get(function_name)
        package_verification_entry = _verification_entry(
            _try_json(job_id, "verification-report.json") or {},
            function_name,
        )
        producer_rows = []
        for producer in cluster.producer_functions:
            producer_row = package_latest.get(producer)
            if not isinstance(producer_row, dict):
                continue
            if normalize_status(producer_row.get("status_canonical") or producer_row.get("status")) != "verified_success":
                continue
            producer_rows.append(producer_row)
        package_target_entries = _target_probe_entries(job_id, function_name)
        package_direct_entries = _direct_target_probe_entries(job_id, function_name)
        failure_class, likely_cause, first_broken_handoff, first_broken_invariant = _carryover_failure_shape(
            target_function=function_name,
            cluster_id=cluster_id,
            producer_rows=producer_rows,
            package_target_row=package_target_row,
            package_target_entries=package_target_entries,
            package_direct_entries=package_direct_entries,
            package_verification_entry=package_verification_entry,
        )
        audits.append(
            {
                "dll": row.get("dll", ""),
                "component": row.get("component", ""),
                "function": function_name,
                "cluster_id": cluster_id,
                "cluster_label": cluster.label,
                "package_job_id": job_id,
                "local_proof_job_id": local_proof["job_id"],
                "local_proof_status": normalize_status(
                    (local_proof["target_row"] or {}).get("status_canonical")
                    or (local_proof["target_row"] or {}).get("status")
                ),
                "local_proof_verified": bool(local_proof.get("verification_entry")),
                "package_status": normalize_status(
                    (package_target_row or {}).get("status_canonical")
                    or (package_target_row or {}).get("status")
                ),
                "package_direct_target_calls": len(package_direct_entries),
                "package_probe_entries": len(package_target_entries),
                "package_verification_present": package_verification_entry is not None,
                "package_direct_target_truth_present": _row_has_preserved_direct_target_truth(package_target_row),
                "package_direct_target_truth_rejected": bool(
                    ((package_target_row or {}).get("direct_target_truth") or {}).get("rejected_by_verification")
                ),
                "producer_replay_successes": [str(row.get("function") or "") for row in producer_rows],
                "failure_class": failure_class,
                "likely_regression_cause": likely_cause,
                "first_broken_handoff": first_broken_handoff,
                "first_broken_invariant": first_broken_invariant,
                "smallest_failure_scope": function_name,
                "evidence_refs": {
                    "package_findings": f"{job_id}/findings.json",
                    "package_probe_log": f"{job_id}/explore_probe_log.json",
                    "package_verification": f"{job_id}/verification-report.json",
                    "local_proof_findings": f"{local_proof['job_id']}/findings.json",
                    "local_proof_verification": f"{local_proof['job_id']}/verification-report.json",
                },
            }
        )
    return audits


def _summarize_carryover_audits(audits: list[dict[str, Any]]) -> dict[str, Any]:
    explained = [audit for audit in audits if str(audit.get("failure_class") or "") != "unexplained"]
    by_class: dict[str, int] = {}
    for audit in explained:
        failure_class = str(audit.get("failure_class") or "").strip()
        if not failure_class:
            continue
        by_class[failure_class] = by_class.get(failure_class, 0) + 1
    return {
        "audited_regressions": len(audits),
        "explained_regressions": len(explained),
        "mystery_regressions_remaining": max(0, len(audits) - len(explained)),
        "failure_classes": [
            {"failure_class": failure_class, "count": count}
            for failure_class, count in sorted(by_class.items(), key=lambda item: (-int(item[1]), item[0]))
        ],
    }


def _id_patterns_from_hints(hints: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"[A-Z]{2,6}-[\w-]+", hints or "")))


def _first_system_block(transcript: str) -> str:
    if not transcript:
        return ""
    return transcript[:4000]


def _extract_turn0_system_context(transcript: str) -> str:
    """Best-effort extraction of turn-0 system context from chat transcript text.

    The chat transcript format has evolved over time, so we support multiple
    lightweight patterns and fall back to the first transcript block.
    """
    if not transcript:
        return ""

    # Common tagged formats from transcript dumps.
    tagged_patterns = [
        r"(?is)^\s*\[system\]\s*(.+?)(?:\n\s*\[[a-z_]+\]|\Z)",
        r"(?is)^\s*role\s*:\s*system\s*\n(.+?)(?:\n\s*role\s*:|\Z)",
        r"(?is)^\s*SYSTEM\s*:\s*(.+?)(?:\n\s*(?:USER|ASSISTANT|TOOL)\s*:|\Z)",
    ]
    for pat in tagged_patterns:
        m = re.search(pat, transcript)
        if m:
            return str(m.group(1) or "").strip()

    return _first_system_block(transcript).strip()


def _ev(stage_slug: str, filename: str) -> str:
    return f"evidence/{stage_slug}/{filename}"


def _has_any_blob(job_id: str, candidates: list[str]) -> bool:
    return any(_try_blob(job_id, c) for c in candidates)


def _canonical_or_legacy(canonical: str, legacy: str, exists: bool) -> str:
    return canonical if exists else legacy


def _build_stage_index(job_id: str, run_started: int, run_finished: int, gap_triggered: bool) -> dict:
    status = _get_job_status(job_id) or {}
    stage_skip_reasons = dict(status.get("stage_skip_reasons") or {})
    stage_by_id = {stage.id: stage for stage in STAGE_CONTRACTS}
    artifact_producer_stages: dict[str, set[str]] = {}
    for stage in STAGE_CONTRACTS:
        for req in (
            *list(stage.required_outputs),
            *list(stage.required_reasoning),
            *list(stage.required_context),
        ):
            artifact_producer_stages.setdefault(req.canonical_path, set()).add(stage.id)

    def _stage_optional_skip(stage_id: str) -> bool:
        stage = stage_by_id.get(stage_id)
        if stage is None:
            return False
        skip_record = stage_skip_reasons.get(stage_id) or {}
        skip_reason = str((skip_record or {}).get("reason") or "").strip()
        floor_broadening_blocked = skip_reason.split(":", 1)[0] == "floor_broadening_blocked"
        return stage_skip_reason_is_allowed(
            stage,
            skip_reason,
            gap_triggered=gap_triggered,
            floor_broadening_blocked=floor_broadening_blocked,
        )

    def _requirement_missing(req: Any, *, allow_optional_upstream_skip: bool = False) -> bool:
        if req.canonical_path in synthesized_canonical_outputs.get(stage.id, set()):
            return False
        if _has_any_blob(job_id, list(req.blob_candidates)):
            return False
        if allow_optional_upstream_skip:
            producer_stage_ids = artifact_producer_stages.get(req.canonical_path, set())
            if any(_stage_optional_skip(stage_id) for stage_id in producer_stage_ids):
                return False
        return True

    checks_by_stage: dict[str, dict[str, Any]] = {
        "S-00": {
            "schema_generated": bool(_try_blob(job_id, "mcp_schema_t0.json")),
            "invocables_map_generated": bool(_try_blob(job_id, "invocables_map.json")),
        },
        "S-01": {
            "vocab_seeded": bool(_try_blob(job_id, "vocab.json")),
            "static_analysis_ran": bool(_try_blob(job_id, "static_analysis.json")),
            "sentinel_calibration_ran": bool(_try_blob(job_id, "sentinel_calibration.json")),
        },
        "S-02": {
            "probe_loop_ran": bool(_try_blob(job_id, "explore_probe_log.json")),
            "findings_written": bool(_try_blob(job_id, "findings.json")),
        },
        "S-03": {
            "sentinel_catalog_written": bool(_try_blob(job_id, "sentinel_catalog.json")),
            "mc3_decision_written": bool(_try_blob(job_id, "mc-decisions/mc3-post-reconcile.json")),
        },
        "S-04": {
            "synthesis_ran": bool(_try_blob(job_id, "api_reference.md")),
            "mc4_decision_written": bool(_try_blob(job_id, "mc-decisions/mc4-post-synthesis.json")),
        },
        "S-05": {
            "backfill_ran": bool(_try_blob(job_id, "backfill_result.json")),
            "mc5_decision_written": bool(_try_blob(job_id, "mc-decisions/mc5-post-verification.json")),
        },
        "S-06": {
            "gap_resolution_ran": bool(_try_blob(job_id, "gap_resolution_log.json")),
            "answer_gaps_triggered": gap_triggered,
        },
        "S-04R": {
            "refresh_possible": gap_triggered,
            "api_reference_present": bool(_try_blob(job_id, "api_reference.md")),
        },
        "S-07": {
            "behavioral_spec_written": bool(_try_blob(job_id, "behavioral_spec.py")),
            "final_schema_written": bool(_try_blob(job_id, "mcp_schema.json")),
            "status_written": bool(_try_blob(job_id, "status.json")),
        },
    }

    synthesized_canonical_outputs: dict[str, set[str]] = {
        "S-00": set(),
    }
    if checks_by_stage["S-00"].get("schema_generated"):
        synthesized_canonical_outputs["S-00"].add(_ev("stage-00-setup", "schema-t0.json"))
    if checks_by_stage["S-00"].get("invocables_map_generated"):
        synthesized_canonical_outputs["S-00"].add(_ev("stage-00-setup", "invocables-map.json"))

    out_stages: list[dict] = []
    for stage in STAGE_CONTRACTS:
        missing = []
        for req in stage.required_inputs:
            if _requirement_missing(req, allow_optional_upstream_skip=True):
                missing.append(req.canonical_path)
        for req in (*list(stage.required_outputs), *list(stage.required_context), *list(stage.required_reasoning)):
            if _requirement_missing(req, allow_optional_upstream_skip=False):
                missing.append(req.canonical_path)
        requirements = (
            list(stage.required_inputs)
            + list(stage.required_outputs)
            + list(stage.required_context)
            + list(stage.required_reasoning)
        )
        artifacts = [req.canonical_path for req in requirements]
        skip_record = stage_skip_reasons.get(stage.id) or {}
        skip_reason = str((skip_record or {}).get("reason") or "").strip()
        skip_detail = str((skip_record or {}).get("detail") or "").strip()
        floor_broadening_blocked = skip_reason.split(":", 1)[0] == "floor_broadening_blocked"
        allowed_skip_reasons = list(
            stage_optional_skip_reasons(
                stage,
                gap_triggered=gap_triggered,
                floor_broadening_blocked=floor_broadening_blocked,
            )
        )
        allow_skip = stage_skip_reason_is_allowed(
            stage,
            skip_reason,
            gap_triggered=gap_triggered,
            floor_broadening_blocked=floor_broadening_blocked,
        )
        if not skip_reason and missing:
            implied_reasons = stage_optional_skip_reasons(
                stage,
                gap_triggered=gap_triggered,
                floor_broadening_blocked=False,
            )
            if implied_reasons:
                skip_reason = implied_reasons[0]
                allowed_skip_reasons = list(implied_reasons)
                allow_skip = True
        if allow_skip and missing:
            status = "skipped"
            errors: list[str] = []
        else:
            status = "completed" if not missing else "failed"
            errors = [f"missing artifact: {m}" for m in missing]
        out_stages.append(
            {
                "id": stage.id,
                "name": stage.name,
                "status": status,
                "started_at": run_started,
                "finished_at": run_finished,
                "artifacts": artifacts,
                "checks": checks_by_stage.get(stage.id, {}),
                "skip_reason": skip_reason,
                "skip_detail": skip_detail,
                "allowed_skip_reasons": allowed_skip_reasons,
                "errors": errors,
            }
        )

    return {
        "version": "1.0",
        "contract_version": CONTRACT_VERSION,
        "auditor_version": AUDITOR_VERSION,
        "stages": out_stages,
    }


def emit_contract_artifacts(job_id: str) -> dict[str, dict]:
    status = _get_job_status(job_id) or {}
    now = int(time.time())
    run_started = int(float(status.get("explore_started_at") or status.get("created_at") or now))
    run_finished = int(float(status.get("updated_at") or now))

    final_phase = str(status.get("explore_phase") or "error")
    if final_phase not in {"done", "awaiting_clarification", "canceled", "error"}:
        final_phase = "error"

    hints = str(status.get("hints") or "")
    findings = _load_findings(job_id)
    latest_findings = _latest_status_by_function(findings)
    vocab = _try_json(job_id, "vocab.json") or {}
    static_analysis = _try_json(job_id, "static_analysis.json") or {}
    probe_log = _try_json(job_id, "explore_probe_log.json") or []
    sentinels = _try_json(job_id, "sentinel_calibration.json") or {}
    inv_map = _try_json(job_id, "invocables_map.json") or {}
    backfill_result = _try_json(job_id, "backfill_result.json") or {}
    schema_t0 = _try_blob(job_id, "mcp_schema_t0.json")
    schema_now = _try_blob(job_id, "mcp_schema.json")
    schema_pre_mini = _try_blob(job_id, "mcp_schema_pre_mini_session.json")
    schema_post_mini = _try_blob(job_id, "mcp_schema_post_mini_session.json")
    api_reference = _as_text(_try_blob(job_id, "api_reference.md"))
    probe_context = _as_text(_try_blob(job_id, "model_context_phase_01_probe_loop.txt"))
    chat_transcript = _as_text(_try_blob(job_id, "chat_transcript.txt"))
    chat_system_turn0_blob = _as_text(_try_blob(job_id, "chat_system_context_turn0.txt"))
    mini_transcript = _as_text(_try_blob(job_id, "mini_session_transcript.txt"))
    schema_evolution = _try_json(job_id, "schema_evolution.json") or []

    chat_system_turn0 = chat_system_turn0_blob.strip() if chat_system_turn0_blob else ""
    if not chat_system_turn0 and chat_transcript:
        chat_system_turn0 = _extract_turn0_system_context(chat_transcript)
    if chat_system_turn0 and not chat_system_turn0_blob:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/chat_system_context_turn0.txt",
            chat_system_turn0.encode("utf-8"),
        )

    gap_answers = (vocab.get("gap_answers") or {}) if isinstance(vocab, dict) else {}
    answered_gap_functions = sorted(
        [k for k, v in gap_answers.items() if k != "general" and str(v or "").strip()]
    )
    gap_triggered = bool(answered_gap_functions) or ("DOMAIN ANSWER" in hints) or bool(mini_transcript)

    id_formats = vocab.get("id_formats") or []
    if not id_formats:
        id_formats = _id_patterns_from_hints(hints)
    if isinstance(id_formats, str):
        id_formats = [id_formats]

    finding_functions = sorted(k for k in latest_findings.keys())
    finding_success_functions = sorted(
        fn for fn, row in latest_findings.items() if str(row.get("status")) == "success"
    )

    transitions: list[dict] = []
    stage_skip_reasons = dict(status.get("stage_skip_reasons") or {})

    def _stage_runtime_optional_skip(stage_id: str) -> bool:
        stage = next((candidate for candidate in STAGE_CONTRACTS if candidate.id == stage_id), None)
        if stage is None:
            return False
        skip_record = stage_skip_reasons.get(stage_id) or {}
        skip_reason = str((skip_record or {}).get("reason") or "").strip()
        floor_broadening_blocked = skip_reason.split(":", 1)[0] == "floor_broadening_blocked"
        return stage_skip_reason_is_allowed(
            stage,
            skip_reason,
            gap_triggered=gap_triggered,
            floor_broadening_blocked=floor_broadening_blocked,
        )

    def add_transition(
        tid: str,
        name: str,
        status_value: str,
        reason: str,
        producer_stage: str,
        consumer_stage: str,
        producer: list[str],
        consumer: list[str],
        effect: list[str],
    ) -> None:
        contract = TRANSITION_CONTRACT_BY_ID.get(tid)
        if contract is not None:
            name = contract.name
            producer_stage = contract.producer_stage
            consumer_stage = contract.consumer_stage
            producer = list(contract.producer_evidence)
            consumer = list(contract.consumer_evidence)
            effect = list(contract.effect_evidence)
        skipped_stages = [
            sid
            for sid in (producer_stage, consumer_stage)
            if _stage_runtime_optional_skip(sid)
        ]
        if skipped_stages:
            status_value = "not_applicable"
            reason = f"stage skipped by floor contract: {', '.join(skipped_stages)}"
        transitions.append(
            {
                "id": tid,
                "name": name,
                "status": status_value,
                "tier": "NOW",
                "severity": TRANSITION_SEVERITY.get(tid, "medium"),
                "producer_stage": producer_stage,
                "consumer_stage": consumer_stage,
                "producer_evidence": producer,
                "consumer_evidence": consumer,
                "effect_evidence": effect,
                "reason": reason,
            }
        )

    hint_ids = _id_patterns_from_hints(hints)
    stale_hint = bool(hint_ids) and not any(str(h) in [str(v) for v in id_formats] for h in hint_ids)
    e_hints = _canonical_or_legacy(
        _ev("stage-01-pre-probe", "hints.txt"),
        "hints.txt",
        bool(_try_blob(job_id, "hints.txt")),
    )
    e_vocab = _ev("stage-01-pre-probe", "vocab.json")
    e_probe_ctx = _ev("stage-02-probe-loop", "stage-context.txt")
    e_probe_log = _ev("stage-02-probe-loop", "probe-log.json")
    e_static = _ev("stage-01-pre-probe", "static-analysis.json")
    e_probe_user = _ev("stage-02-probe-loop", "probe-user-message-sample.txt")
    e_findings = _ev("stage-02-probe-loop", "findings.json")
    e_synth_ctx = _ev("stage-04-synthesis", "stage-context.txt")
    e_api_ref = _ev("stage-04-synthesis", "api-reference.md")
    e_backfill = _ev("stage-05-backfill", "backfill-report.json")
    e_schema_post_backfill = _ev("stage-05-backfill", "schema-post-backfill.json")
    e_inv_map = _ev("stage-00-setup", "invocables-map.json")
    e_mini_tx = _ev("stage-06-gap-resolution", "mini-session-transcript.txt")
    e_gap_log = _ev("stage-06-gap-resolution", "gap-resolution-log.json")
    e_schema_pre_mini = _ev("stage-06-gap-resolution", "schema-pre-mini-session.json")
    e_schema_post_mini = _ev("stage-06-gap-resolution", "schema-post-mini-session.json")
    e_chat_tx = "diagnostics/transcript.txt"
    e_chat_system = "diagnostics/chat-system-context-turn0.txt"
    e_exec_trace = "diagnostics/executor-trace.json"
    e_schema_t0 = _ev("stage-00-setup", "schema-t0.json")
    e_schema_evolution = _ev("stage-07-finalize", "schema-evolution.json")
    e_schema_final = _ev("stage-07-finalize", "schema-final.json")
    e_sentinel_calibration = _ev("stage-01-pre-probe", "sentinel-calibration.json")
    e_write_unlock = _ev("stage-01-pre-probe", "write-unlock-probe.json")

    if id_formats and not stale_hint:
        add_transition(
            "T-01", "hints_to_vocab", "pass", "id_formats present and aligned with current hints",
            "S-01", "S-02", [e_hints], [e_vocab], [e_probe_ctx],
        )
    elif id_formats and stale_hint:
        add_transition(
            "T-01", "hints_to_vocab", "warn", "id_formats present but may be stale vs current hints",
            "S-01", "S-02", [e_hints], [e_vocab], [e_probe_ctx],
        )
    else:
        add_transition(
            "T-01", "hints_to_vocab", "fail", "id_formats missing",
            "S-01", "S-02", [e_hints], [e_vocab], [e_probe_ctx],
        )

    hint_hexes = {h.lower() for h in re.findall(r"0x[0-9a-fA-F]{8}", hints or "")}
    sentinel_keys = {str(k).lower() for k in (sentinels.keys() if isinstance(sentinels, dict) else [])}
    missing_hexes = sorted(h for h in hint_hexes if h not in sentinel_keys)
    add_transition(
        "T-02",
        "hint_error_codes_to_sentinels",
        "pass" if not missing_hexes else "fail",
        "all hint error codes merged into sentinel calibration"
        if not missing_hexes
        else f"missing hint codes in sentinel map: {', '.join(missing_hexes)}",
        "S-01",
        "S-01",
        [e_hints],
        [e_sentinel_calibration],
        [e_vocab],
    )

    id_hits = [x for x in id_formats if str(x) and str(x) in probe_context]
    if not id_formats:
        t03_status = "partial"
        t03_reason = "id_formats unavailable"
    elif id_hits:
        t03_status = "pass"
        t03_reason = "id formats present in probe context"
    else:
        t03_status = "warn"
        t03_reason = "could not confirm id formats in probe context"
    add_transition(
        "T-03", "vocab_to_probe_prompt", t03_status, t03_reason,
        "S-01", "S-02", [e_vocab], [e_probe_ctx], [e_probe_log],
    )

    sh_len = int((static_analysis.get("static_hints_block_length") or 0)) if isinstance(static_analysis, dict) else 0
    if sh_len <= 0:
        t04_status = "fail"
        t04_reason = "static_hints_block_length is zero"
    else:
        user_prompt_sample = _as_text(_try_blob(job_id, "probe_user_message_sample.txt"))
        if user_prompt_sample and user_prompt_sample.strip():
            t04_status = "pass"
            t04_reason = "static hints block and probe user prompt sample present"
        else:
            t04_status = "warn"
            t04_reason = "static hints block present but probe user prompt sample not yet instrumented"
    add_transition(
        "T-04", "static_analysis_to_probe_prompt", t04_status, t04_reason,
        "S-01", "S-02", [e_static], [e_probe_user], [e_probe_log],
    )

    static_ids = set()
    if isinstance(static_analysis, dict):
        static_ids = set(((static_analysis.get("binary_strings") or {}).get("ids_found") or []))
    fallback_args: list[str] = []
    for row in probe_log if isinstance(probe_log, list) else []:
        if row.get("phase") == "deterministic_fallback" and isinstance(row.get("args"), dict):
            fallback_args.extend(str(v) for v in row.get("args", {}).values())
    t05_hit = bool(static_ids) and any(v in static_ids for v in fallback_args)
    t05_status = "pass" if t05_hit else ("warn" if static_ids else "partial")
    t05_reason = "fallback args include static IDs" if t05_hit else "could not prove static IDs propagated into fallback args"
    add_transition(
        "T-05", "static_ids_to_fallback_args", t05_status, t05_reason,
        "S-01", "S-02", [e_static], [e_probe_log], [e_findings],
    )

    missing_in_synth = [fn for fn in finding_success_functions if fn not in api_reference]
    add_transition(
        "T-06",
        "probe_findings_to_synthesis",
        "pass" if not missing_in_synth else "fail",
        "all successful finding functions reflected in synthesis"
        if not missing_in_synth
        else f"missing in api_reference.md: {', '.join(missing_in_synth[:8])}",
        "S-02",
        "S-04",
        [e_findings],
        [e_api_ref],
        [e_synth_ctx],
    )

    if backfill_result:
        add_transition(
            "T-07",
            "synthesis_to_backfill_patches",
            "pass",
            f"backfill_result.json emitted; patches_applied={int(backfill_result.get('patches_applied') or 0)}",
            "S-04",
            "S-05",
            [e_api_ref],
            [e_backfill],
            [e_schema_post_backfill],
        )
    else:
        add_transition(
            "T-07",
            "synthesis_to_backfill_patches",
            "partial",
            "backfill_result.json missing",
            "S-04",
            "S-05",
            [e_api_ref],
            [e_backfill],
            [e_schema_post_backfill],
        )

    enrich_functions = {
        str(r.get("function"))
        for r in (probe_log if isinstance(probe_log, list) else [])
        if str(r.get("tool") or "") == "enrich_invocable" and str(r.get("function") or "")
    }
    t08_missing = []
    for fn in sorted(enrich_functions):
        inv = inv_map.get(fn) if isinstance(inv_map, dict) else None
        params = (inv or {}).get("parameters") or []
        if not any(isinstance(p, dict) and not re.match(r"^param_\d+$", str(p.get("name") or "")) for p in params):
            t08_missing.append(fn)
    add_transition(
        "T-08",
        "enrich_call_to_schema",
        "pass" if not t08_missing else "fail",
        "enriched functions have semantic parameter names"
        if not t08_missing
        else f"semantic names missing after enrich for: {', '.join(t08_missing[:8])}",
        "S-02",
        "S-05",
        [e_probe_log],
        [e_inv_map],
        [e_schema_post_backfill],
    )

    auto_enrich_functions = {
        str(r.get("function"))
        for r in (probe_log if isinstance(probe_log, list) else [])
        if str(r.get("phase") or "") == "d12_autoenrich" and str(r.get("function") or "")
    }
    if auto_enrich_functions:
        weak_desc = []
        for fn in sorted(auto_enrich_functions):
            inv = inv_map.get(fn) if isinstance(inv_map, dict) else None
            desc = str((inv or {}).get("description") or (inv or {}).get("doc") or "")
            if not desc or "ghidra" in desc.lower():
                weak_desc.append(fn)
        t09_status = "pass" if not weak_desc else "warn"
        t09_reason = "auto-enriched descriptions applied" if not weak_desc else "some auto-enriched functions still have generic descriptions"
    else:
        t09_status = "not_applicable"
        t09_reason = "no d12_autoenrich events in this run"
    add_transition(
        "T-09", "auto_enrich_to_schema", t09_status, t09_reason,
        "S-02", "S-05", [e_probe_log], [e_inv_map], [e_schema_post_backfill],
    )

    all_param_names: list[str] = []
    if isinstance(inv_map, dict):
        for inv in inv_map.values():
            for p in (inv.get("parameters") or []):
                if isinstance(p, dict):
                    all_param_names.append(str(p.get("name") or ""))
    all_generic = bool(all_param_names) and all(re.match(r"^param_\d+$", n or "") for n in all_param_names)
    t10_status = "fail" if all_generic else "pass"
    t10_reason = "parameter names show semantic vocab transfer" if not all_generic else "all parameter names remain generic param_N"
    add_transition(
        "T-10", "vocab_to_param_names", t10_status, t10_reason,
        "S-01", "S-05", [e_vocab], [e_inv_map], [e_schema_post_backfill],
    )

    semantic_tokens: list[str] = []
    if isinstance(vocab, dict):
        semantic_tokens.extend(str(x) for x in (vocab.get("id_formats") or [])[:3])
        semantic_tokens.extend(
            str(k) for k in list((vocab.get("value_semantics") or {}).keys())[:3]
        )
    has_semantic_signal = any(tok and tok in api_reference for tok in semantic_tokens)
    if missing_in_synth:
        t11_status = "fail"
        t11_reason = "synthesis misses functions from findings"
    elif semantic_tokens and not has_semantic_signal:
        t11_status = "warn"
        t11_reason = "findings reached synthesis but vocab semantic signals are weak"
    else:
        t11_status = "pass"
        t11_reason = "synthesis reflects findings and vocabulary semantics"
    add_transition(
        "T-11", "enriched_knowledge_to_synthesis_input", t11_status, t11_reason,
        "S-02", "S-04", [e_findings, e_vocab], [e_synth_ctx], [e_api_ref],
    )

    if not gap_triggered:
        t12_status = "not_applicable"
        t12_reason = "answer-gaps flow not triggered"
    elif answered_gap_functions and mini_transcript:
        missing_fn = [fn for fn in answered_gap_functions if fn not in mini_transcript]
        t12_status = "pass" if not missing_fn else "fail"
        t12_reason = "all answered functions appear in mini-session transcript" if not missing_fn else f"missing in mini-session transcript: {', '.join(missing_fn)}"
    else:
        t12_status = "partial"
        t12_reason = "answer-gaps triggered but transcript evidence incomplete"
    add_transition(
        "T-12", "gap_answers_to_mini_session_context", t12_status, t12_reason,
        "S-06", "S-06", [e_vocab], [e_mini_tx], [e_gap_log],
    )

    if not gap_triggered:
        t13_status = "not_applicable"
        t13_reason = "answer-gaps flow not triggered"
    elif schema_pre_mini and schema_post_mini:
        changed = _hash(schema_pre_mini) != _hash(schema_post_mini)
        t13_status = "pass" if changed else "fail"
        t13_reason = "schema changed across mini-session" if changed else "schema unchanged across mini-session"
    else:
        t13_status = "partial"
        t13_reason = "mini-session schema snapshots incomplete"
    add_transition(
        "T-13", "mini_session_to_schema_evolution", t13_status, t13_reason,
        "S-06", "S-06", [e_mini_tx], [e_schema_pre_mini], [e_schema_post_mini],
    )

    if not chat_system_turn0 and not chat_transcript:
        t14_status = "not_applicable"
        t14_reason = "chat context artifacts not present in this run (explore-only session)"
    else:
        _ctx = chat_system_turn0 or _first_system_block(chat_transcript)
        fn_hits = [fn for fn in finding_functions[:20] if fn in _ctx]
        t14_status = "pass" if fn_hits else "warn"
        t14_reason = "finding functions are present in chat context" if fn_hits else "could not confirm findings injection in chat context"
    add_transition(
        "T-14", "findings_to_chat_prompt", t14_status, t14_reason,
        "S-02", "S-07", [e_findings], [e_chat_system], [e_exec_trace],
    )

    chat_probe = (chat_system_turn0 or chat_transcript).lower()
    vocab_markers = ["id formats", "error codes", "value semantics"]
    if not chat_system_turn0 and not chat_transcript:
        t15_status = "not_applicable"
        t15_reason = "chat context artifacts not present in this run (explore-only session)"
    elif any(m in chat_probe for m in vocab_markers):
        t15_status = "pass"
        t15_reason = "vocab sections detected in chat context"
    else:
        t15_status = "warn"
        t15_reason = "could not confirm vocab block markers in chat context"
    add_transition(
        "T-15", "vocab_to_chat_prompt", t15_status, t15_reason,
        "S-01", "S-07", [e_vocab], [e_chat_system], [e_exec_trace],
    )

    if schema_evolution and isinstance(schema_evolution, list):
        changed_entries = [e for e in schema_evolution if bool((e or {}).get("changed"))]
        present_entries = [e for e in schema_evolution if bool((e or {}).get("present"))]
        if changed_entries:
            t16_status = "pass"
            t16_reason = "schema_evolution.json includes changed=true checkpoints"
        elif present_entries:
            t16_status = "warn"
            t16_reason = "schema_evolution.json present but no changed checkpoints were recorded"
        else:
            t16_status = "fail"
            t16_reason = "schema_evolution.json exists but no schema checkpoints were present"
    else:
        if schema_t0 and schema_now and _hash(schema_t0) != _hash(schema_now):
            t16_status = "pass"
            t16_reason = "schema changed between t0 and final snapshot"
        elif schema_now:
            t16_status = "warn"
            t16_reason = "final schema exists but no evolution delta was available"
        else:
            t16_status = "fail"
            t16_reason = "final schema snapshot missing"
    add_transition(
        "T-16", "schema_evolution_present", t16_status, t16_reason,
        "S-00", "S-07", [e_schema_t0], [e_schema_evolution], [e_schema_final],
    )

    # T-17: sentinel_calibration_outcome — did Phase 0.5 calibration name DLL-specific codes?
    sentinel_default_hexes = {"0xffffffff", "0xfffffffe", "0xfffffffd", "0xfffffffc", "0xfffffffb"}
    if not isinstance(sentinels, dict) or not sentinels:
        t17_status = "fail"
        t17_reason = "sentinel_calibration.json missing or empty"
    else:
        non_default_codes = [k for k in sentinels if str(k).lower() not in sentinel_default_hexes]
        sentinel_new_count = int(status.get("sentinel_new_codes_this_run") or 0)
        if non_default_codes or sentinel_new_count > 0:
            t17_status = "pass"
            t17_reason = (
                f"calibration produced {len(non_default_codes)} DLL-specific code(s)"
                + (f"; {sentinel_new_count} new code(s) named this run" if sentinel_new_count else "")
            )
        else:
            t17_status = "warn"
            t17_reason = "sentinel calibration present but returned only default fallback codes"
    add_transition(
        "T-17", "sentinel_calibration_outcome", t17_status, t17_reason,
        "S-01", "S-02", [e_sentinel_calibration], [e_probe_ctx], [e_probe_log],
    )

    # T-18: write_unlock_probe_outcome — did the write-mode unlock probe succeed?
    write_unlock_outcome = str(status.get("write_unlock_outcome") or "")
    if write_unlock_outcome == "resolved":
        t18_status = "pass"
        t18_reason = "write-unlock probe succeeded; write-mode functions are accessible"
    elif write_unlock_outcome == "blocked":
        sentinel_label = str(status.get("write_unlock_sentinel") or "unknown")
        t18_status = "warn"
        t18_reason = f"write-unlock probe could not unlock write mode; blocking sentinel={sentinel_label}"
    elif write_unlock_outcome == "not_attempted":
        t18_status = "not_applicable"
        t18_reason = "no write-style functions detected in this DLL; write-unlock probe skipped"
    else:
        t18_status = "partial"
        t18_reason = "write_unlock_outcome not recorded (probe may not have run or predates Q16)"
    add_transition(
        "T-18", "write_unlock_probe_outcome", t18_status, t18_reason,
        "S-01", "S-02", [e_write_unlock], [e_probe_log], [e_probe_log],
    )

    # T-19: mc_coordinator_decisions — did MCs produce reasoning artifacts?
    e_mc3 = "evidence/mc-decisions/mc3-post-reconcile.json"
    e_mc4 = "evidence/mc-decisions/mc4-post-synthesis.json"
    e_mc5 = "evidence/mc-decisions/mc5-post-verification.json"
    e_mc6 = "evidence/mc-decisions/mc6-post-gap-resolution.json"
    mc_blobs_present = sum(1 for b in [
        f"mc-decisions/mc3-post-reconcile.json",
        f"mc-decisions/mc4-post-synthesis.json",
        f"mc-decisions/mc5-post-verification.json",
        f"mc-decisions/mc6-post-gap-resolution.json",
    ] if _try_blob(job_id, b))
    if mc_blobs_present == 4:
        t19_status = "pass"
        t19_reason = f"all 4 micro coordinator decisions recorded"
    elif mc_blobs_present > 0:
        t19_status = "partial"
        t19_reason = f"{mc_blobs_present}/4 micro coordinator decisions recorded"
    else:
        t19_status = "not_applicable"
        t19_reason = "no micro coordinator decisions found (pre-MC pipeline version)"
    add_transition(
        "T-19", "mc_coordinator_decisions", t19_status, t19_reason,
        "S-02", "S-06", [e_mc3, e_mc4], [e_mc5, e_mc6], [e_findings],
    )

    # T-20: enrichment_verification_outcome — did Phase 7b verify enriched findings?
    v_verified = int(status.get("verification_verified") or 0)
    v_inferred = int(status.get("verification_inferred") or 0)
    v_error = int(status.get("verification_error") or 0)
    v_total = v_verified + v_inferred + v_error
    e_verification = "evidence/mc-decisions/verification-report.json"
    if v_total > 0 and v_verified > 0:
        t20_status = "pass"
        t20_reason = f"{v_verified}/{v_total} enriched functions verified by DLL execution"
    elif v_total > 0:
        t20_status = "warn"
        t20_reason = f"0/{v_total} enriched functions verified (all inferred or error)"
    else:
        t20_status = "not_applicable"
        t20_reason = "enrichment verification not run (no enriched findings)"
    add_transition(
        "T-20", "enrichment_verification_outcome", t20_status, t20_reason,
        "S-05", "S-06", [e_backfill, e_findings], [e_verification], [e_findings],
    )

    # T-21: winning_init_sequence — was the write-unlock sequence persisted for future runs?
    e_winning = "evidence/mc-decisions/winning-init-sequence.json"
    write_resolved_at = str(status.get("write_unlock_resolved_at") or "")
    _winning_init_blob = _try_blob(job_id, "winning_init_sequence.json")
    if write_resolved_at:
        t21_status = "pass"
        if not _winning_init_blob:
            t21_status = "fail"
            t21_reason = f"write-unlock cracked at {write_resolved_at} but winning_init_sequence.json is missing"
        else:
            t21_reason = f"write-unlock cracked at {write_resolved_at}; init sequence persisted"
    elif write_unlock_outcome == "blocked":
        t21_status = "warn"
        t21_reason = "write-unlock remained blocked; no winning init sequence exists yet"
    else:
        t21_status = "not_applicable"
        t21_reason = "no write functions detected or unlock not attempted"
    add_transition(
        "T-21", "winning_init_sequence_persistence", t21_status, t21_reason,
        "S-02", "S-07", [e_mc6], [e_winning], [e_findings],
    )

    transition_index = {
        "version": "1.0",
        "contract_version": CONTRACT_VERSION,
        "auditor_version": AUDITOR_VERSION,
        "transitions": transitions,
    }

    stage_index = _build_stage_index(job_id, run_started, run_finished, gap_triggered)

    stage_pass = sum(1 for s in stage_index["stages"] if s["status"] == "completed")
    stage_fail = sum(1 for s in stage_index["stages"] if s["status"] == "failed")
    t_counts = {
        "transition_pass": 0,
        "transition_fail": 0,
        "transition_warn": 0,
        "transition_partial": 0,
        "transition_na": 0,
    }
    for t in transitions:
        st = t["status"]
        if st == "pass":
            t_counts["transition_pass"] += 1
        elif st == "fail":
            t_counts["transition_fail"] += 1
        elif st == "warn":
            t_counts["transition_warn"] += 1
        elif st == "partial":
            t_counts["transition_partial"] += 1
        elif st == "not_applicable":
            t_counts["transition_na"] += 1

    high_fail = [t["id"] for t in transitions if t["status"] == "fail" and t["severity"] == "high"]
    failed_transitions = [t["id"] for t in transitions if t["status"] == "fail"]
    failed_stages = [s["id"] for s in stage_index["stages"] if s["status"] == "failed"]
    explore_cfg = _try_json(job_id, "explore_config.json") or {}
    floor_plan = _try_json(job_id, "floor_plan.json") or {}
    floor_state = _try_json(job_id, "floor_iteration_state.json") or {}

    cohesion_report = {
        "version": "1.0",
        "contract_version": CONTRACT_VERSION,
        "auditor_version": AUDITOR_VERSION,
        "run": {
            "job_id": job_id,
            "component": status.get("component_name", "unknown"),
            "final_phase": final_phase,
        },
        "totals": {
            "stage_pass": stage_pass,
            "stage_fail": stage_fail,
            **t_counts,
        },
        "gates": {
            "hard_fail": bool(high_fail),
            "reasons": [f"high-severity transition failed: {tid}" for tid in high_fail],
        },
        "failed_transitions": failed_transitions,
        "failed_stages": failed_stages,
        "floor_iteration": {
            "iteration_mode": str((explore_cfg or {}).get("iteration_mode") or "single_pass"),
            "floor_scope": str((floor_plan or {}).get("floor_scope") or (explore_cfg or {}).get("floor_scope") or ""),
            "cluster_checkpoint_id": str((floor_plan or {}).get("cluster_checkpoint_id") or ""),
            "prerequisite_state_group_ids": list((floor_plan or {}).get("prerequisite_state_group_ids") or []),
            "imported_dependency_classes": list((floor_plan or {}).get("imported_dependency_classes") or []),
            "preserved_lower_floor_functions": list((floor_plan or {}).get("preserved_lower_floor_functions") or []),
            "previous_ceiling_functions": list((floor_state or {}).get("previous_ceiling_functions") or (floor_plan or {}).get("ceiling_functions") or []),
            "next_ceiling_functions": list((floor_state or {}).get("next_ceiling_functions") or []),
            "reopened_functions": list((floor_state or {}).get("reopened_functions") or []),
            "ceiling_shrank": bool((floor_state or {}).get("ceiling_shrank")),
            "localized_more": bool((floor_state or {}).get("localized_more")),
            "carryover_status": str((floor_state or {}).get("carryover_status") or ""),
            "ceiling_dependency_map": dict((floor_plan or {}).get("ceiling_dependency_map") or {}),
            "first_broken_handoff_group": str(((floor_state or {}).get("observer_verdicts") or {}).get("first_broken_handoff_group") or ""),
            "first_broken_handoff_layer": str(((floor_state or {}).get("observer_verdicts") or {}).get("first_broken_handoff_layer") or ""),
            "first_broken_handoff_by_function": dict(((floor_state or {}).get("observer_verdicts") or {}).get("first_broken_handoff_by_function") or {}),
        },
    }

    profile = "default"
    if isinstance(explore_cfg, dict):
        profile = str(explore_cfg.get("cap_profile") or explore_cfg.get("mode") or "default")

    code_commit = "unknown"
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
        code_commit = out.decode("utf-8", errors="replace").strip() or "unknown"
    except Exception:
        pass

    from api.pipeline.core.finding_status import DISCOVERED_STATUSES, normalize_status
    from api.pipeline.core.scoring_scope import canonical_status_map, target_scope_names

    scoring_scope = target_scope_names(status.get("explore_runtime") or {})
    scoped_status_map = canonical_status_map(list(latest_findings.values()), scoring_scope)
    if not scoring_scope:
        scoped_status_map = {
            fn: normalize_status((row or {}).get("status_canonical") or (row or {}).get("status"))
            for fn, row in latest_findings.items()
        }
    functions_success = sum(1 for status_value in scoped_status_map.values() if status_value == "verified_success")
    functions_error = sum(1 for status_value in scoped_status_map.values() if status_value not in DISCOVERED_STATUSES)

    session_meta = {
        "contract_version": CONTRACT_VERSION,
        "auditor_version": AUDITOR_VERSION,
        "job_id": job_id,
        "component": status.get("component_name", "unknown"),
        "dll_path": status.get("target_path") or status.get("file_path"),
        "dll_sha256": status.get("dll_sha256"),
        "analysis_entrypoint": status.get("analysis_entrypoint"),
        "binary_origin": status.get("binary_origin"),
        "run_started_at": run_started,
        "run_finished_at": run_finished,
        "code_commit": code_commit,
        "profile": profile,
        "final_phase": final_phase,
        "functions_total": len(scoped_status_map),
        "functions_success": functions_success,
        "functions_error": functions_error,
        # Q15: ablation tagging fields (pass-through from job submission)
        "prompt_profile_id": status.get("prompt_profile_id"),
        "layer": status.get("layer"),
        "ablation_variable": status.get("ablation_variable"),
        "ablation_value": status.get("ablation_value"),
        "run_set_id": status.get("run_set_id"),
        "coordinator_cycle": status.get("coordinator_cycle"),
        "playbook_step": status.get("playbook_step"),
        "chain_step_target": (status.get("explore_runtime") or {}).get("chain_step_target"),
        "required_semantic_checkpoint": (status.get("explore_runtime") or {}).get("required_semantic_checkpoint"),
        "selected_invocable_names": (status.get("explore_runtime") or {}).get("selected_invocable_names") or [],
        # Q16: sentinel + write-unlock emission fields
        "write_unlock_outcome": status.get("write_unlock_outcome"),
        "write_unlock_sentinel": status.get("write_unlock_sentinel"),
        "write_unlock_resolved_at": status.get("write_unlock_resolved_at"),
        "sentinel_new_codes_this_run": status.get("sentinel_new_codes_this_run", 0),
        # Circular feedback fields
        "prior_job_id": status.get("prior_job_id"),
        "cross_dll_prior_job_ids": (status.get("explore_runtime") or {}).get("cross_dll_prior_job_ids") or [],
        "campaign_id": (status.get("explore_runtime") or {}).get("campaign_id") or status.get("campaign_id") or "",
        "graph_epoch": (status.get("explore_runtime") or {}).get("graph_epoch") or status.get("graph_epoch"),
        "iteration_mode": (explore_cfg or {}).get("iteration_mode") or "single_pass",
        "floor_scope": (floor_plan or {}).get("floor_scope") or (explore_cfg or {}).get("floor_scope") or "",
        "ceiling_function_count": len((floor_state or {}).get("next_ceiling_functions") or (floor_plan or {}).get("ceiling_functions") or []),
        "preserved_function_count": len((floor_plan or {}).get("preserved_lower_floor_functions") or []),
        "prior_findings_seeded": status.get("prior_findings_seeded", 0),
        # Phase 7b verification counts
        "verification_verified": status.get("verification_verified", 0),
        "verification_inferred": status.get("verification_inferred", 0),
        "verification_error": status.get("verification_error", 0),
        "stage_skip_reasons": dict(status.get("stage_skip_reasons") or {}),
        # Blocker-harvest additive fields
        "package_id": status.get("package_id"),
        "package_label": status.get("package_label"),
        "lane_id": status.get("lane_id") or (status.get("explore_runtime") or {}).get("lane_id"),
        "lane_trust_status": status.get("lane_trust_status"),
        "selection_reason": status.get("selection_reason"),
        "doc_visibility": status.get("doc_visibility"),
        "dependency_context": status.get("dependency_context"),
        "blocker_family_primary": status.get("blocker_family_primary"),
        "blocker_family_secondary": status.get("blocker_family_secondary") or [],
        "blocker_confidence": status.get("blocker_confidence"),
        "architecture_relevance": status.get("architecture_relevance"),
        "runtime_path_trust": status.get("runtime_path_trust"),
    }

    _upload_to_blob(
        ARTIFACT_CONTAINER,
        f"{job_id}/session-meta.json",
        json.dumps(session_meta, indent=2).encode("utf-8"),
    )
    _upload_to_blob(
        ARTIFACT_CONTAINER,
        f"{job_id}/stage-index.json",
        json.dumps(stage_index, indent=2).encode("utf-8"),
    )
    _upload_to_blob(
        ARTIFACT_CONTAINER,
        f"{job_id}/transition-index.json",
        json.dumps(transition_index, indent=2).encode("utf-8"),
    )
    _upload_to_blob(
        ARTIFACT_CONTAINER,
        f"{job_id}/cohesion-report.json",
        json.dumps(cohesion_report, indent=2).encode("utf-8"),
    )

    return {
        "session_meta": session_meta,
        "stage_index": stage_index,
        "transition_index": transition_index,
        "cohesion_report": cohesion_report,
    }


def emit_campaign_cohesion_report(campaign_id: str, campaign: dict) -> dict:
    """Emit a campaign-level cohesion report checking cross-DLL artifact completeness.

    Returns the report dict and uploads it to blob storage.
    """
    entries = campaign.get("dll_entries", [])
    per_dll_reports: list[dict] = []
    total_verified = 0
    total_functions = 0
    missing_artifacts: list[dict] = []
    campaign_truth = _try_campaign_json(campaign_id, "campaign-truth.json") or {}
    floor_plan = _try_campaign_json(campaign_id, "package-frontier-plan.json") or _try_campaign_json(campaign_id, "batch-b-ceiling-plan.json") or {}
    decomposition_plan = _try_campaign_json(campaign_id, "decomposition-campaign-plan.json") or {}
    baseline_contract = resolve_campaign_package_baseline_contract(
        campaign,
        package_frontier_plan=floor_plan,
        campaign_truth=campaign_truth,
    )
    truth_per_dll = {
        str(row.get("job_id") or ""): row
        for row in list(campaign_truth.get("per_dll") or [])
        if isinstance(row, dict) and str(row.get("job_id") or "").strip()
    }

    for entry in entries:
        jid = entry.get("job_id", "")
        if not jid:
            continue

        dll_report: dict = {"job_id": jid, "filename": entry.get("filename", ""), "status": entry.get("status", "")}
        if jid in truth_per_dll:
            dll_report.update(
                {
                    "dll_id": truth_per_dll[jid].get("dll_id", entry.get("dll_id", "")),
                    "attribution_mode": truth_per_dll[jid].get("attribution_mode", "none"),
                    "campaign_truth_present": True,
                    "lane_id": truth_per_dll[jid].get("lane_id", entry.get("lane_id", "")),
                    "lane_trust_status": truth_per_dll[jid].get("lane_trust_status", entry.get("lane_trust_status", "")),
                    "runtime_path_trust": truth_per_dll[jid].get("runtime_path_trust", entry.get("runtime_path_trust", "")),
                    "blocker_family_primary": truth_per_dll[jid].get("blocker_family_primary", entry.get("blocker_family_primary", "")),
                    "blocker_family_secondary": truth_per_dll[jid].get("blocker_family_secondary", entry.get("blocker_family_secondary", [])),
                    "blocker_confidence": truth_per_dll[jid].get("blocker_confidence", entry.get("blocker_confidence", "")),
                    "architecture_relevance": truth_per_dll[jid].get("architecture_relevance", entry.get("architecture_relevance", "")),
                    "selection_reason": truth_per_dll[jid].get("selection_reason", entry.get("selection_reason", "")),
                    "dependency_confidence": truth_per_dll[jid].get("dependency_confidence", entry.get("dependency_confidence", "")),
                }
            )

        # Check required per-DLL blobs exist
        required_blobs = [
            "findings.json",
            "invocables_map.json",
            "status.json",
            "lane-trust.json",
            "package-context.json",
            "blocker-classification.json",
        ]
        for blob_name in required_blobs:
            try:
                _download_blob(ARTIFACT_CONTAINER, f"{jid}/{blob_name}")
                dll_report[blob_name] = "present"
            except Exception:
                dll_report[blob_name] = "missing"
                missing_artifacts.append({"job_id": jid, "blob": blob_name})

        findings = _load_findings(jid)
        latest = _latest_status_by_function(findings)
        if jid in truth_per_dll:
            verified = int(truth_per_dll[jid].get("verified_count") or 0)
            total_count = int(truth_per_dll[jid].get("total_functions") or len(latest))
        else:
            verified = _count_verified_rows(latest)
            total_count = len(latest)
        dll_report["verified_count"] = verified
        dll_report["total_functions"] = total_count
        total_verified += verified
        total_functions += total_count
        per_dll_reports.append(dll_report)

    # Check campaign-level blobs
    campaign_blobs = [
        "campaign_plan.json",
        "evidence_graph.json",
        "campaign-truth.json",
        "package-frontier-plan.json",
        "batch-b-ceiling-plan.json",
        "decomposition-campaign-plan.json",
    ]
    campaign_blob_status: dict[str, str] = {}
    for blob_name in campaign_blobs:
        try:
            _download_blob(ARTIFACT_CONTAINER, f"campaigns/{campaign_id}/{blob_name}")
            campaign_blob_status[blob_name] = "present"
        except Exception:
            campaign_blob_status[blob_name] = "missing"
            missing_artifacts.append({"campaign_id": campaign_id, "blob": blob_name})

    report = {
        "schema_version": "1.0.0",
        "campaign_id": campaign_id,
        "package_id": campaign.get("package_id", ""),
        "package_label": campaign.get("package_label", ""),
        "package_context": campaign.get("package_context", {}) or {},
        "source_origin": campaign.get("source_origin", ""),
        "package_purpose": campaign.get("package_purpose", ""),
        "doc_visibility": campaign.get("doc_visibility", ""),
        "dependency_context": campaign.get("dependency_context", ""),
        "phase": campaign.get("phase", ""),
        "dll_count": len(entries),
        "package_floor": dict(floor_plan.get("package_floor") or {}),
        "floor_to_ceiling_plan_present": bool(floor_plan),
        "package_frontier_plan_present": bool(floor_plan),
        "decomposition_plan_present": bool(decomposition_plan),
        "active_frontier_dlls": list(campaign_truth.get("active_frontier_dlls") or floor_plan.get("active_frontier_dlls") or []),
        "imported_lower_floor_dlls": list(campaign_truth.get("imported_lower_floor_dlls") or floor_plan.get("imported_lower_floor_dlls") or []),
        "active_frontier_slice_ids": list(campaign_truth.get("active_frontier_slice_ids") or decomposition_plan.get("active_frontier_slice_ids") or []),
        "imported_to_active_ratio": campaign_truth.get("imported_to_active_ratio", decomposition_plan.get("imported_to_active_ratio", 0.0)),
        "deferred_initialization_group_ids": list(campaign_truth.get("deferred_initialization_group_ids") or decomposition_plan.get("deferred_initialization_group_ids") or []),
        "deferred_dependency_class_ids": list(campaign_truth.get("deferred_dependency_class_ids") or decomposition_plan.get("deferred_dependency_class_ids") or []),
        "interwoven_artifact_presence": bool(
            campaign_truth.get("interwoven_artifact_presence")
            or decomposition_plan.get("interwoven_artifact_presence")
        ),
        "interwoven_subject_ids": list(
            campaign_truth.get("interwoven_subject_ids")
            or decomposition_plan.get("interwoven_subject_ids")
            or []
        ),
        "interwoven_contradiction_summary": dict(
            campaign_truth.get("interwoven_contradiction_summary")
            or decomposition_plan.get("interwoven_contradiction_summary")
            or {}
        ),
        "interwoven_attribution_present": bool(
            campaign_truth.get("interwoven_attribution_present")
            or decomposition_plan.get("interwoven_attribution_present")
        ),
        "slice_execution_attribution_present": bool(
            campaign_truth.get("slice_execution_attribution_present")
            or decomposition_plan.get("slice_execution_attribution_present")
        ),
        "total_verified": total_verified,
        "total_functions": total_functions,
        "verified_rate": total_verified / total_functions if total_functions else 0.0,
        "per_dll": per_dll_reports,
        "campaign_blobs": campaign_blob_status,
        "campaign_truth_present": bool(campaign_truth),
        "baseline_contract_present": bool(baseline_contract),
        "package_floor_evidence_class": str(
            campaign_truth.get("package_floor_evidence_class")
            or classify_package_floor_evidence(
                baseline_contract_present=bool(baseline_contract),
                active_frontier_defined=bool(campaign_truth.get("active_frontier_dlls") or floor_plan.get("active_frontier_dlls") or []),
                imported_lower_floor_truth_recorded=bool(
                    campaign_truth.get("imported_lower_floor_dlls")
                    or floor_plan.get("imported_lower_floor_dlls")
                    or []
                ),
                comparable_profile_consistent=bool(campaign_truth.get("overlap_baseline_comparable")),
                run_valid_green=len(missing_artifacts) == 0,
            )
        ),
        "package_floor_confirmation_ready": bool(
            campaign_truth.get("package_floor_confirmation_ready")
            if "package_floor_confirmation_ready" in campaign_truth
            else str(
                campaign_truth.get("package_floor_evidence_class")
                or classify_package_floor_evidence(
                    baseline_contract_present=bool(baseline_contract),
                    active_frontier_defined=bool(campaign_truth.get("active_frontier_dlls") or floor_plan.get("active_frontier_dlls") or []),
                    imported_lower_floor_truth_recorded=bool(
                        campaign_truth.get("imported_lower_floor_dlls")
                        or floor_plan.get("imported_lower_floor_dlls")
                        or []
                    ),
                    comparable_profile_consistent=bool(campaign_truth.get("overlap_baseline_comparable")),
                    run_valid_green=len(missing_artifacts) == 0,
                )
            ) == "overlap_comparable_confirmation"
        ),
        "lane_gate": campaign_truth.get("lane_gate") or campaign.get("lane_gate") or {},
        "blocker_harvest_summary": campaign_truth.get("blocker_harvest_summary")
        or summarize_campaign_blocker_harvest(per_dll_reports),
        "missing_artifacts": missing_artifacts,
        "complete": len(missing_artifacts) == 0,
        "created_at": time.time(),
    }

    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"campaigns/{campaign_id}/campaign-cohesion-report.json",
            json.dumps(report, indent=2).encode("utf-8"),
        )
    except Exception:
        pass

    return report


def emit_campaign_attribution_report(campaign_id: str, campaign: dict) -> dict:
    """Emit campaign attribution boundaries for same-DLL vs cross-DLL claims."""
    entries = campaign.get("dll_entries", [])
    per_dll_reports: list[dict[str, Any]] = []
    findings_by_job: dict[str, list[dict[str, Any]]] = {}
    hidden_variable_warnings: list[str] = []
    attribution_mode_counts = {"none": 0, "same_dll": 0, "cross_dll": 0, "overlap_baseline": 0}
    ledger_rows = _read_run_ledger_rows()
    campaign_truth = _try_campaign_json(campaign_id, "campaign-truth.json") or {}
    floor_plan = _try_campaign_json(campaign_id, "package-frontier-plan.json") or _try_campaign_json(campaign_id, "batch-b-ceiling-plan.json") or {}
    decomposition_plan = _try_campaign_json(campaign_id, "decomposition-campaign-plan.json") or {}
    effective_baseline_contract = resolve_campaign_package_baseline_contract(
        campaign,
        package_frontier_plan=floor_plan,
        campaign_truth=campaign_truth,
    )
    baseline_index = _baseline_contract_index({"baseline_contract": effective_baseline_contract})
    truth_per_dll = {
        str(row.get("job_id") or ""): row
        for row in list(campaign_truth.get("per_dll") or [])
        if isinstance(row, dict) and str(row.get("job_id") or "").strip()
    }

    for entry in entries:
        jid = str(entry.get("job_id", "") or "").strip()
        if not jid:
            continue

        baseline_entry = _baseline_entry_for_dll(entry, baseline_index)
        baseline_required, no_baseline_required = _baseline_requirement_for_dll(
            entry,
            baseline_index,
            {"baseline_contract": effective_baseline_contract},
        )
        if jid in truth_per_dll:
            row = dict(truth_per_dll[jid])
            attribution_mode = str(row.get("attribution_mode") or "none")
            attribution_mode_counts[attribution_mode] = attribution_mode_counts.get(attribution_mode, 0) + 1
            if "component" not in row:
                row["component"] = str(entry.get("filename") or "").rsplit(".", 1)[0]
            if baseline_entry:
                row["baseline"] = baseline_entry
            row.setdefault("baseline_required", baseline_required)
            row.setdefault("no_baseline_required", no_baseline_required)
            row.setdefault("overlap_baseline_match", bool(baseline_entry))
            row.setdefault("lane_id", entry.get("lane_id", ""))
            row.setdefault("lane_trust_status", entry.get("lane_trust_status", ""))
            row.setdefault("runtime_path_trust", entry.get("runtime_path_trust", ""))
            row.setdefault("selection_reason", entry.get("selection_reason", ""))
            row.setdefault("dependency_confidence", entry.get("dependency_confidence", ""))
            row.setdefault("blocker_family_primary", entry.get("blocker_family_primary", ""))
            row.setdefault("blocker_family_secondary", entry.get("blocker_family_secondary", []))
            row.setdefault("blocker_confidence", entry.get("blocker_confidence", ""))
            row.setdefault("architecture_relevance", entry.get("architecture_relevance", ""))
            per_dll_reports.append(row)
            if not row.get("comparable_surface_ready"):
                hidden_variable_warnings.append(
                    f"{jid}: missing comparison fields "
                    f"(analysis_entrypoint={bool(row.get('analysis_entrypoint'))}, "
                    f"binary_origin={bool(row.get('binary_origin'))}, "
                    f"analysis_profile={bool(row.get('analysis_profile'))}, "
                    f"cache_state={bool(row.get('cache_state'))}, graph_epoch={bool(row.get('graph_epoch'))})"
                )
            if row.get("baseline_required") and not row.get("baseline"):
                hidden_variable_warnings.append(
                    f"{jid}: required overlap baseline missing for {row.get('filename') or row.get('component') or jid}"
                )
            continue

        status = _get_job_status(jid) or {}
        runtime = status.get("explore_runtime") or {}
        discovery_meta = status.get("discovery_meta") or {}
        findings = _load_findings(jid)
        findings_by_job[jid] = findings
        latest = _latest_status_by_function(findings)

        prior_job_id = str(runtime.get("prior_job_id") or "").strip()
        cross_dll_prior_job_ids = list(runtime.get("cross_dll_prior_job_ids") or [])
        attribution_mode = "none"
        if cross_dll_prior_job_ids:
            attribution_mode = "cross_dll"
        elif prior_job_id:
            attribution_mode = "same_dll"
        attribution_mode_counts[attribution_mode] += 1

        analysis_entrypoint = str(status.get("analysis_entrypoint") or "")
        binary_origin = str(status.get("binary_origin") or "")
        analysis_profile = str(runtime.get("analysis_profile") or status.get("analysis_profile") or "")
        graph_epoch = str(runtime.get("graph_epoch") or status.get("graph_epoch") or "none")
        cache_state = str(discovery_meta.get("cache_state") or "")
        bridge_reachable = discovery_meta.get("bridge_reachable")
        component = str(status.get("component_name") or entry.get("filename") or "").rsplit(".", 1)[0]
        baseline_entry = _baseline_entry_for_dll(
            {
                "component": component,
                "dll_id": entry.get("dll_id", ""),
                "filename": entry.get("filename", ""),
            },
            baseline_index,
        )
        baseline_required, no_baseline_required = _baseline_requirement_for_dll(
            {
                "component": component,
                "dll_id": entry.get("dll_id", ""),
                "filename": entry.get("filename", ""),
            },
            baseline_index,
            {"baseline_contract": effective_baseline_contract},
        )
        comparable_surface_ready = all(
            [
                analysis_entrypoint,
                binary_origin,
                analysis_profile,
                cache_state,
                graph_epoch,
            ]
        )
        if not comparable_surface_ready:
            hidden_variable_warnings.append(
                f"{jid}: missing comparison fields "
                f"(analysis_entrypoint={bool(analysis_entrypoint)}, "
                f"binary_origin={bool(binary_origin)}, "
                f"analysis_profile={bool(analysis_profile)}, "
                f"cache_state={bool(cache_state)}, graph_epoch={bool(graph_epoch)})"
            )
        if baseline_required and not baseline_entry:
            hidden_variable_warnings.append(
                f"{jid}: required overlap baseline missing for {entry.get('filename') or component or jid}"
            )

        per_dll_reports.append(
            {
                "job_id": jid,
                "dll_id": entry.get("dll_id", ""),
                "filename": entry.get("filename", ""),
                "component": component,
                "status": entry.get("status", ""),
                "package_id": campaign.get("package_id", ""),
                "package_label": campaign.get("package_label", ""),
                "selection_reason": entry.get("selection_reason", ""),
                "dependency_confidence": entry.get("dependency_confidence", ""),
                "lane_id": entry.get("lane_id", "") or status.get("lane_id", ""),
                "dll_fingerprint": str(entry.get("dll_fingerprint") or status.get("dll_fingerprint") or ""),
                "analysis_entrypoint": analysis_entrypoint,
                "binary_origin": binary_origin,
                "analysis_profile": analysis_profile,
                "cache_state": cache_state,
                "bridge_reachable": bridge_reachable,
                "graph_epoch": graph_epoch,
                "prior_job_id": prior_job_id,
                "cross_dll_prior_job_ids": cross_dll_prior_job_ids,
                "cross_dll_prior_job_count": len(cross_dll_prior_job_ids),
                "attribution_mode": attribution_mode,
                "comparable_surface_ready": comparable_surface_ready,
                "verified_count": _count_verified_rows(latest),
                "total_functions": len(latest),
                "lane_trust_status": status.get("lane_trust_status") or entry.get("lane_trust_status", ""),
                "runtime_path_trust": status.get("runtime_path_trust") or entry.get("runtime_path_trust", ""),
                "blocker_family_primary": status.get("blocker_family_primary") or entry.get("blocker_family_primary", ""),
                "blocker_family_secondary": status.get("blocker_family_secondary") or entry.get("blocker_family_secondary", []),
                "blocker_confidence": status.get("blocker_confidence") or entry.get("blocker_confidence", ""),
                "architecture_relevance": status.get("architecture_relevance") or entry.get("architecture_relevance", ""),
                "baseline": baseline_entry or {},
                "baseline_required": baseline_required,
                "no_baseline_required": no_baseline_required,
                "overlap_baseline_match": bool(baseline_entry),
            }
        )

    function_rows: list[dict[str, Any]] = []
    for dll_row in per_dll_reports:
        function_rows.extend(_build_function_rows(dll_row, ledger_rows, explicit_baseline=dll_row.get("baseline") or None))

    for row in function_rows:
        mismatch = list(row.get("baseline_surface_mismatch") or [])
        if not mismatch:
            continue
        hidden_variable_warnings.append(
            f"{row.get('job_id')}/{row.get('function')}: explicit baseline surface mismatch "
            f"({', '.join(mismatch)})"
        )

    blocker_family_summary = _summarize_blocker_families(function_rows)
    system_opportunity_summary = _summarize_system_opportunities(function_rows)
    carryover_audits = _build_package_carryover_audits(function_rows, per_dll_reports)
    carryover_by_key = {
        (str(audit.get("dll") or ""), str(audit.get("function") or "")): audit
        for audit in carryover_audits
    }
    regression_summary = []
    for row in _summarize_regressions(function_rows):
        audit = carryover_by_key.get((str(row.get("dll") or ""), str(row.get("function") or "")))
        if audit is None:
            regression_summary.append(row)
            continue
        regression_summary.append(
            {
                **row,
                "likely_regression_cause": audit.get("likely_regression_cause", row.get("likely_regression_cause", "")),
                "carryover_failure_class": audit.get("failure_class", ""),
                "cluster_id": audit.get("cluster_id", ""),
                "local_proof_job_id": audit.get("local_proof_job_id", ""),
                "local_proof_verified": bool(audit.get("local_proof_verified")),
                "package_direct_target_calls": int(audit.get("package_direct_target_calls") or 0),
                "package_verification_present": bool(audit.get("package_verification_present")),
                "producer_replay_successes": list(audit.get("producer_replay_successes") or []),
                "first_broken_handoff": audit.get("first_broken_handoff", ""),
                "first_broken_invariant": audit.get("first_broken_invariant", ""),
                "smallest_failure_scope": audit.get("smallest_failure_scope", ""),
                "evidence_refs": dict(audit.get("evidence_refs") or {}),
            }
        )
    overlap_rows = [row for row in function_rows if bool(row.get("baseline_required"))]
    overlap_regression_summary = [row for row in regression_summary if bool(row.get("baseline_required"))]
    overlap_dll_reports = [row for row in per_dll_reports if bool(row.get("baseline_required"))]
    no_baseline_required_dlls = sorted(
        {
            str(row.get("filename") or "")
            for row in per_dll_reports
            if bool(row.get("no_baseline_required")) and str(row.get("filename") or "")
        }
    )
    overlap_baseline_comparable = False
    if overlap_dll_reports:
        overlap_baseline_comparable = (
            all(bool(row.get("comparable_surface_ready")) for row in overlap_dll_reports)
            and all(bool(row.get("baseline")) for row in overlap_dll_reports)
            and all(str(row.get("delta_vs_baseline") or "") != "incomparable" for row in overlap_rows)
        )
    overlap_verified_delta = 0
    for row in overlap_dll_reports:
        baseline = dict(row.get("baseline") or {})
        overlap_verified_delta += int(row.get("verified_count") or 0) - int(
            baseline.get("baseline_verified_count")
            or baseline.get("verified_count")
            or 0
        )
    stage_breakdown_summary = _summarize_stage_breakdown(function_rows)
    evidence_surface_summary = _summarize_evidence_surface(function_rows)
    architect_summary = _build_architect_summary(
        function_rows,
        system_opportunity_summary,
        blocker_family_summary,
        regression_summary,
    )
    if campaign_truth.get("cross_dll_contracts"):
        cross_dll_contracts = dict(campaign_truth.get("cross_dll_contracts") or {})
    else:
        evidence_graph = _try_campaign_json(campaign_id, "evidence_graph.json") or {}
        cross_dll_contracts = build_business_object_contract_surface(
            campaign_id=campaign_id,
            campaign_graph_epoch=str(campaign.get("graph_epoch") or campaign_id),
            per_dll_rows=per_dll_reports,
            latest_findings_by_job=_latest_findings_by_job(findings_by_job),
            evidence_graph=evidence_graph if isinstance(evidence_graph, dict) else {},
        )

    package_floor_evidence_class = classify_package_floor_evidence(
        baseline_contract_present=bool(effective_baseline_contract),
        active_frontier_defined=bool(campaign_truth.get("active_frontier_dlls") or floor_plan.get("active_frontier_dlls") or []),
        imported_lower_floor_truth_recorded=bool(campaign_truth.get("imported_lower_floor_dlls") or floor_plan.get("imported_lower_floor_dlls") or []),
        comparable_profile_consistent=overlap_baseline_comparable,
        run_valid_green=bool(per_dll_reports) and len(per_dll_reports) == len(entries),
    )

    report = {
        "schema_version": "1.0.0",
        "campaign_id": campaign_id,
        "package_id": campaign.get("package_id", ""),
        "package_label": campaign.get("package_label", ""),
        "package_context": campaign.get("package_context", {}) or {},
        "source_origin": campaign.get("source_origin", ""),
        "package_purpose": campaign.get("package_purpose", ""),
        "doc_visibility": campaign.get("doc_visibility", ""),
        "dependency_context": campaign.get("dependency_context", ""),
        "phase": campaign.get("phase", ""),
        "dll_count": len(entries),
        "attribution_mode_counts": attribution_mode_counts,
        "per_dll": per_dll_reports,
        "hidden_variable_warnings": hidden_variable_warnings,
        "campaign_truth_present": bool(campaign_truth),
        "package_internal_truth_ready": bool(per_dll_reports) and len(per_dll_reports) == len(entries),
        "baseline_contract_present": bool(effective_baseline_contract),
        "package_floor": dict((campaign_truth.get("package_floor") or floor_plan.get("package_floor") or {})),
        "package_floor_evidence_class": str(campaign_truth.get("package_floor_evidence_class") or package_floor_evidence_class),
        "package_floor_confirmation_ready": bool(
            campaign_truth.get("package_floor_confirmation_ready")
            if "package_floor_confirmation_ready" in campaign_truth
            else package_floor_evidence_class == "overlap_comparable_confirmation"
        ),
        "decomposition_plan_present": bool(decomposition_plan),
        "active_frontier_slice_ids": list(campaign_truth.get("active_frontier_slice_ids") or decomposition_plan.get("active_frontier_slice_ids") or []),
        "imported_to_active_ratio": campaign_truth.get("imported_to_active_ratio", decomposition_plan.get("imported_to_active_ratio", 0.0)),
        "deferred_initialization_group_ids": list(campaign_truth.get("deferred_initialization_group_ids") or decomposition_plan.get("deferred_initialization_group_ids") or []),
        "deferred_dependency_class_ids": list(campaign_truth.get("deferred_dependency_class_ids") or decomposition_plan.get("deferred_dependency_class_ids") or []),
        "interwoven_artifact_presence": bool(
            campaign_truth.get("interwoven_artifact_presence")
            or decomposition_plan.get("interwoven_artifact_presence")
        ),
        "interwoven_subject_ids": list(
            campaign_truth.get("interwoven_subject_ids")
            or decomposition_plan.get("interwoven_subject_ids")
            or []
        ),
        "interwoven_contradiction_summary": dict(
            campaign_truth.get("interwoven_contradiction_summary")
            or decomposition_plan.get("interwoven_contradiction_summary")
            or {}
        ),
        "interwoven_attribution_present": bool(
            campaign_truth.get("interwoven_attribution_present")
            or decomposition_plan.get("interwoven_attribution_present")
        ),
        "slice_execution_attribution_present": bool(
            campaign_truth.get("slice_execution_attribution_present")
            or decomposition_plan.get("slice_execution_attribution_present")
        ),
        "overlap_baseline_comparable": overlap_baseline_comparable,
        "overlap_dll_count": len(overlap_dll_reports),
        "overlap_verified_delta": overlap_verified_delta,
        "overlap_regression_summary": overlap_regression_summary,
        "no_baseline_required_dlls": no_baseline_required_dlls,
        "package_wide_comparable": overlap_baseline_comparable and not no_baseline_required_dlls and bool(per_dll_reports),
        "lane_gate": campaign_truth.get("lane_gate") or campaign.get("lane_gate") or {},
        "blocker_harvest_summary": campaign_truth.get("blocker_harvest_summary")
        or summarize_campaign_blocker_harvest(per_dll_reports),
        "same_dll_comparison_ready": [
            row["job_id"]
            for row in per_dll_reports
            if row["attribution_mode"] in {"none", "same_dll"} and row["comparable_surface_ready"]
        ],
        "cross_dll_comparison_ready": [
            row["job_id"]
            for row in per_dll_reports
            if row["attribution_mode"] == "cross_dll" and row["comparable_surface_ready"]
        ],
        "created_at": time.time(),
        "architect_summary": architect_summary,
        "cross_dll_contracts": cross_dll_contracts,
        "function_matrix": function_rows,
        "blocker_family_summary": blocker_family_summary,
        "system_opportunity_summary": system_opportunity_summary,
        "carryover_audits": carryover_audits,
        "carryover_audit_summary": _summarize_carryover_audits(carryover_audits),
        "regression_summary": regression_summary,
        "stage_breakdown_summary": stage_breakdown_summary,
        "evidence_surface_summary": evidence_surface_summary,
        "baseline_contract": {
            "source_wave_id": str((effective_baseline_contract or {}).get("source_wave_id") or ""),
            "source_campaign_id": str((effective_baseline_contract or {}).get("source_campaign_id") or ""),
            "baseline_graph_epoch": str((effective_baseline_contract or {}).get("baseline_graph_epoch") or ""),
            "baseline_seeding_mode": str((effective_baseline_contract or {}).get("baseline_seeding_mode") or ""),
            "baseline_package_dll_set": list((effective_baseline_contract or {}).get("baseline_package_dll_set") or []),
            "overlap_dll_set": list((effective_baseline_contract or {}).get("overlap_dll_set") or []),
            "no_baseline_required_dlls": list((effective_baseline_contract or {}).get("no_baseline_required_dlls") or []),
            "entries": sorted(
                {
                    json.dumps(value, sort_keys=True): dict(value)
                    for value in baseline_index.values()
                    if isinstance(value, dict)
                }.values(),
                key=lambda item: (
                    str(item.get("component") or ""),
                    str(item.get("dll_id") or ""),
                    str(item.get("filename") or ""),
                ),
            ),
        },
    }
    report["baseline_contract"]["dll_count"] = len(report["baseline_contract"]["entries"])

    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"campaigns/{campaign_id}/campaign-attribution-report.json",
            json.dumps(report, indent=2).encode("utf-8"),
        )
    except Exception:
        pass

    return report
