from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx

from api.infra.config import GUI_BRIDGE_SECRET, GUI_BRIDGE_URL
from api.pipeline.core.finding_status import normalize_status


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_LEDGER_PATH = REPO_ROOT / "sessions" / "ledger" / "run_ledger.jsonl"


BLOCKER_FAMILY_TAXONOMY: dict[str, dict[str, str]] = {
    "string/artifact chain": {
        "candidate_system": "generalized runtime artifact materializer",
        "suite_family": "string/artifact chain",
    },
    "output/readback": {
        "candidate_system": "output and observer verification lane",
        "suite_family": "output/readback",
    },
    "sequencing/state machine": {
        "candidate_system": "prerequisite and state-machine classifier",
        "suite_family": "sequencing/state machine",
    },
    "business-rule gating": {
        "candidate_system": "business-rule and approval classifier",
        "suite_family": "business-rule gating",
    },
    "environment gating": {
        "candidate_system": "environment dependency classifier",
        "suite_family": "environment gating",
    },
    "opaque handle routing": {
        "candidate_system": "generalized runtime artifact materializer",
        "suite_family": "opaque handle routing",
    },
    "struct/payload shaping": {
        "candidate_system": "structured argument scaffolder",
        "suite_family": "struct/payload shaping",
    },
    "wide-string/reduced discovery": {
        "candidate_system": "wide-string and reduced-discovery augmenter",
        "suite_family": "wide-string/reduced discovery",
    },
    "callback/flag-space": {
        "candidate_system": "callback and flag-space system",
        "suite_family": "callback/flag-space",
    },
    "discovery opacity": {
        "candidate_system": "discovery opacity augmenter",
        "suite_family": "discovery opacity",
    },
    "measurement": {
        "candidate_system": "lane trust and measurement hardening",
        "suite_family": "",
    },
    "state": {
        "candidate_system": "state correctness and prerequisite capture",
        "suite_family": "",
    },
}


def read_run_ledger_rows() -> list[dict[str, Any]]:
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


def _openapi_paths(base_url: str, headers: dict[str, str]) -> set[str]:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return set()
    for suffix in ("/openapi.json", "/docs/openapi.json"):
        try:
            with httpx.Client(timeout=10.0, headers=headers) as client:
                resp = client.get(f"{base}{suffix}")
            if resp.status_code != 200:
                continue
            payload = resp.json()
            paths = payload.get("paths") if isinstance(payload, dict) else {}
            if isinstance(paths, dict):
                return {str(k) for k in paths.keys()}
        except Exception:
            continue
    return set()


def verify_bridge_identity(bridge_url: str, bridge_key: str = "") -> tuple[bool, str]:
    base = str(bridge_url or "").strip().rstrip("/")
    if not base:
        return False, "bridge_url_missing"
    headers = {"X-Bridge-Key": bridge_key} if bridge_key else {}
    try:
        with httpx.Client(timeout=10.0, headers=headers) as client:
            health = client.get(f"{base}/health")
    except Exception as exc:
        return False, f"bridge_health_unreachable:{exc}"
    if health.status_code != 200:
        return False, f"bridge_health_non_200:{health.status_code}"
    paths = _openapi_paths(base, headers)
    if not paths:
        return False, "bridge_openapi_unavailable"
    has_execute = "/execute" in paths
    api_like = any(path.startswith("/api/jobs") for path in paths)
    if api_like and not has_execute:
        return False, "bridge_api_shaped_endpoint_detected"
    if not has_execute:
        return False, "bridge_missing_execute_route"
    if api_like:
        return False, "bridge_api_shaped_endpoint_detected"
    return True, f"bridge_ok:routes={len(paths)}"


def infer_blocker_family_and_system(
    dll_row: dict[str, Any],
    function_row: dict[str, Any],
) -> tuple[str, str, str]:
    status = normalize_status(function_row.get("status_canonical") or function_row.get("status"))
    if status == "verified_success":
        return "", "", "high"

    fn = str(function_row.get("function") or "")
    fn_lower = fn.lower()
    text = " ".join(
        str(function_row.get(key) or "")
        for key in ("finding", "notes", "technical_detail", "technical_question", "cross_validation")
    ).lower()
    component = str(dll_row.get("component") or dll_row.get("filename") or "").lower()
    corpus = f"{fn_lower} {text} {component}".strip()

    if any(token in corpus for token in ("bridge /execute", "401 unauthorized", "timeout", "openapi", "health_non_200", "missing_execute_route", "api_shaped_endpoint")):
        family = "measurement"
    elif any(token in corpus for token in ("runtime path mismatch", "state incorrect", "stale state", "same-session", "fresh handle", "stateful", "prerequisite replay failed")):
        family = "state"
    elif any(token in corpus for token in ("callback", "handler", "event", "enum", "mask", "flag")):
        family = "callback/flag-space"
    elif fn.endswith("W") or any(token in corpus for token in ("wchar", "wide", "unicode", "lpwstr", "lpcwstr")):
        family = "wide-string/reduced discovery"
    elif any(token in corpus for token in ("config", "license", "licensed", "trial", "capability", "environment", "dependency missing")):
        family = "environment gating"
    elif any(token in corpus for token in ("sample", "buffer", "payload", "pcm", "struct", "request", "response", "frame count")):
        family = "struct/payload shaping"
    elif any(token in corpus for token in ("num", "receive", "readback", "version string", "output buffer", "observer", "getsetting", "isempty", "unprocessed")):
        family = "output/readback"
    elif any(token in corpus for token in ("handle", "session", "nonce", "token", "reservation", "workflow", "instance", "createinstance")):
        family = "opaque handle routing"
    elif any(token in corpus for token in ("prepare", "approve", "commit", "confirm", "cancel", "export", "preview", "render", "flush", "putsamples", "setsamplerate", "settempo")):
        family = "sequencing/state machine"
    elif any(token in corpus for token in ("pricing window", "approval", "policy", "quote", "business rule")):
        family = "business-rule gating"
    elif any(token in corpus for token in ("artifact", "report id", "quote id", "string id", "token chain")):
        family = "string/artifact chain"
    else:
        family = "discovery opacity"

    meta = BLOCKER_FAMILY_TAXONOMY.get(family, {})
    confidence = "medium" if family not in {"measurement", "state", "discovery opacity"} else ("high" if family in {"measurement", "state"} else "low")
    return family, str(meta.get("candidate_system") or ""), confidence


def first_blocking_stage_from_finding(row: dict[str, Any]) -> str:
    source_stage = str(row.get("source_stage") or "").strip()
    if source_stage:
        return source_stage
    text = " ".join(
        str(row.get(key) or "")
        for key in ("finding", "notes", "technical_detail", "technical_question", "cross_validation")
    ).lower()
    if "gap resolution" in text:
        return "s06_gaps"
    if str(row.get("verification") or "").strip().lower() == "verified":
        return "s05_enrichment"
    return "s02_probe"


def build_package_context_artifact(
    campaign: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "campaign_id": str(campaign.get("campaign_id") or ""),
        "package_id": str(campaign.get("package_id") or ""),
        "package_label": str(campaign.get("package_label") or ""),
        "package_context": dict(campaign.get("package_context", {}) or {}),
        "source_origin": str(campaign.get("source_origin") or ""),
        "package_purpose": str(campaign.get("package_purpose") or ""),
        "doc_visibility": str(campaign.get("doc_visibility") or ""),
        "dependency_context": str(campaign.get("dependency_context") or ""),
        "operator_notes": str(campaign.get("operator_notes") or ""),
        "dll": {
            "dll_id": str(entry.get("dll_id") or ""),
            "job_id": str(entry.get("job_id") or ""),
            "filename": str(entry.get("filename") or ""),
            "dll_path": str(entry.get("dll_path") or ""),
            "selection_reason": str(entry.get("selection_reason") or ""),
            "dependency_confidence": str(entry.get("dependency_confidence") or ""),
            "lane_id": str(entry.get("lane_id") or ""),
        },
    }


def build_lane_trust_report(
    *,
    campaign: dict[str, Any],
    entry: dict[str, Any],
    status: dict[str, Any],
    ledger_rows: list[dict[str, Any]],
    runtime_settings: dict[str, Any],
) -> dict[str, Any]:
    job_id = str(entry.get("job_id") or "")
    lane_id = str(entry.get("lane_id") or runtime_settings.get("lane_id") or status.get("lane_id") or "lane-1").strip()
    discovery_meta = status.get("discovery_meta") if isinstance(status.get("discovery_meta"), dict) else {}
    target_path = str(status.get("target_path") or status.get("file_path") or "").strip()
    expected_path = str(entry.get("dll_path") or "").strip()
    bridge_ok, bridge_msg = verify_bridge_identity(GUI_BRIDGE_URL, GUI_BRIDGE_SECRET)
    bridge_reachable = bool(discovery_meta.get("bridge_reachable"))
    lane_ids = {str((dll or {}).get("lane_id") or lane_id).strip() or lane_id for dll in list(campaign.get("dll_entries") or [])}
    runtime_path_trust = "not_applicable"
    if expected_path and target_path:
        runtime_path_trust = "matched" if expected_path == target_path else "mismatch"
    elif target_path:
        runtime_path_trust = "echoed"
    elif expected_path:
        runtime_path_trust = "missing_echo"
    ledger_row_present = any(str(row.get("job_id") or "") == job_id for row in ledger_rows)
    checks = {
        "lane_id_recorded": bool(lane_id),
        "lane_policy_ok": int(runtime_settings.get("parallel_runs") or 1) <= 2,
        "lane_count_within_v1": len(lane_ids) <= 2,
        "bridge_reachable": bridge_reachable,
        "bridge_identity_ok": bridge_ok,
        "execute_route_ok": bridge_ok,
        "runtime_path_trust": runtime_path_trust,
        "ledger_row_present": ledger_row_present,
    }
    reasons: list[str] = []
    if not checks["lane_policy_ok"]:
        reasons.append("parallel_runs_exceeds_v1_limit")
    if not checks["lane_count_within_v1"]:
        reasons.append("lane_count_exceeds_v1_limit")
    if not checks["lane_id_recorded"]:
        reasons.append("lane_id_missing")
    if not bridge_ok:
        reasons.append(bridge_msg)
    if not bridge_reachable:
        reasons.append("discovery_bridge_unreachable")
    if runtime_path_trust == "mismatch":
        reasons.append("runtime_path_mismatch")
    if not ledger_row_present:
        reasons.append("ledger_row_missing")
    if bridge_ok and bridge_reachable and runtime_path_trust != "mismatch":
        trust_status = "trusted"
        if not ledger_row_present:
            trust_status = "degraded"
    else:
        trust_status = "blocked" if (not bridge_ok or runtime_path_trust == "mismatch") else "degraded"
    return {
        "schema_version": "1.0.0",
        "campaign_id": str(campaign.get("campaign_id") or ""),
        "job_id": job_id,
        "dll_id": str(entry.get("dll_id") or ""),
        "filename": str(entry.get("filename") or ""),
        "lane_id": lane_id,
        "package_id": str(campaign.get("package_id") or ""),
        "package_label": str(campaign.get("package_label") or ""),
        "trust_status": trust_status,
        "bridge_identity_message": bridge_msg,
        "runtime_path_trust": runtime_path_trust,
        "checks": checks,
        "reasons": reasons,
        "trustworthy_for_architecture": trust_status == "trusted",
    }


def build_blocker_classification_report(
    *,
    campaign: dict[str, Any],
    entry: dict[str, Any],
    findings: list[dict[str, Any]],
    lane_trust: dict[str, Any],
) -> dict[str, Any]:
    job_id = str(entry.get("job_id") or "")
    unresolved_rows = [
        row for row in findings
        if normalize_status(row.get("status_canonical") or row.get("status")) != "verified_success"
    ]
    family_rows: list[dict[str, Any]] = []
    family_counts: Counter[str] = Counter()
    family_systems: defaultdict[str, set[str]] = defaultdict(set)
    family_stages: defaultdict[str, set[str]] = defaultdict(set)
    family_confidence: dict[str, str] = {}
    for row in unresolved_rows:
        family, system, confidence = infer_blocker_family_and_system(entry, row)
        if family:
            family_counts[family] += 1
            if system:
                family_systems[family].add(system)
            family_stages[family].add(first_blocking_stage_from_finding(row))
            family_confidence[family] = confidence
        family_rows.append(
            {
                "function": str(row.get("function") or ""),
                "status": normalize_status(row.get("status_canonical") or row.get("status")),
                "blocker_family": family,
                "candidate_system": system,
                "confidence": confidence,
                "first_blocking_stage": first_blocking_stage_from_finding(row),
            }
        )

    if lane_trust.get("trust_status") == "blocked":
        primary_family = "measurement"
        secondary = ["state"] if unresolved_rows else []
        blocker_confidence = "high"
        candidate_system = BLOCKER_FAMILY_TAXONOMY[primary_family]["candidate_system"]
    elif lane_trust.get("trust_status") == "degraded" and not family_counts:
        primary_family = "state"
        secondary = []
        blocker_confidence = "medium"
        candidate_system = BLOCKER_FAMILY_TAXONOMY[primary_family]["candidate_system"]
    else:
        ranked = family_counts.most_common()
        primary_family = ranked[0][0] if ranked else ""
        secondary = [family for family, _count in ranked[1:3]]
        blocker_confidence = family_confidence.get(primary_family, "low") if primary_family else "low"
        systems = sorted(family_systems.get(primary_family) or [])
        candidate_system = systems[0] if systems else str(BLOCKER_FAMILY_TAXONOMY.get(primary_family, {}).get("candidate_system") or "")

    architecture_relevance = "low"
    if primary_family:
        architecture_relevance = "medium"
    if lane_trust.get("trust_status") == "trusted" and unresolved_rows:
        architecture_relevance = "high" if len(unresolved_rows) >= 2 else "medium"
    if lane_trust.get("trust_status") == "blocked":
        architecture_relevance = "low"

    evidence_basis: list[dict[str, Any]] = []
    for family, count in family_counts.most_common():
        evidence_basis.append(
            {
                "family": family,
                "function_count": count,
                "stages": sorted(family_stages.get(family) or []),
                "artifacts": [f"{job_id}/findings.json", f"{job_id}/verification-report.json"],
                "confidence": family_confidence.get(family, "low"),
                "maps_to_existing_suite_family": bool(BLOCKER_FAMILY_TAXONOMY.get(family, {}).get("suite_family")),
            }
        )

    return {
        "schema_version": "1.0.0",
        "campaign_id": str(campaign.get("campaign_id") or ""),
        "package_id": str(campaign.get("package_id") or ""),
        "package_label": str(campaign.get("package_label") or ""),
        "job_id": job_id,
        "dll_id": str(entry.get("dll_id") or ""),
        "filename": str(entry.get("filename") or ""),
        "lane_trust_status": str(lane_trust.get("trust_status") or ""),
        "primary_blocker_family": primary_family,
        "secondary_blocker_families": secondary,
        "blocker_confidence": blocker_confidence,
        "candidate_next_system": candidate_system,
        "architecture_relevance": architecture_relevance,
        "runtime_path_trust": str(lane_trust.get("runtime_path_trust") or ""),
        "trustworthy_for_architecture": bool(lane_trust.get("trustworthy_for_architecture")),
        "function_rows": family_rows,
        "evidence_basis": evidence_basis,
        "unresolved_function_count": len(unresolved_rows),
    }


def build_campaign_lane_gate(
    *,
    campaign: dict[str, Any],
    runtime_settings: dict[str, Any],
    job_statuses: list[dict[str, Any]],
) -> dict[str, Any]:
    lane_id = str(runtime_settings.get("lane_id") or "lane-1").strip()
    parallel_runs = max(1, int(runtime_settings.get("parallel_runs") or 1))
    bridge_ok, bridge_msg = verify_bridge_identity(GUI_BRIDGE_URL, GUI_BRIDGE_SECRET)
    discovery_bridge_reachable = all(
        bool((status.get("discovery_meta") or {}).get("bridge_reachable"))
        for status in job_statuses
        if isinstance(status, dict)
    )
    trust_status = "trusted"
    reasons: list[str] = []
    if parallel_runs > 2:
        trust_status = "blocked"
        reasons.append("parallel_runs_exceeds_v1_limit")
    if not bridge_ok:
        trust_status = "blocked"
        reasons.append(bridge_msg)
    if not discovery_bridge_reachable:
        trust_status = "degraded" if trust_status != "blocked" else trust_status
        reasons.append("discovery_bridge_unreachable")
    report = {
        "schema_version": "1.0.0",
        "campaign_id": str(campaign.get("campaign_id") or ""),
        "package_id": str(campaign.get("package_id") or ""),
        "package_label": str(campaign.get("package_label") or ""),
        "lane_id": lane_id,
        "parallel_runs": parallel_runs,
        "trust_status": trust_status,
        "checks": {
            "lane_id_recorded": bool(lane_id),
            "parallel_runs_within_v1": parallel_runs <= 2,
            "bridge_identity_ok": bridge_ok,
            "execute_route_ok": bridge_ok,
            "discovery_bridge_reachable": discovery_bridge_reachable,
        },
        "reasons": reasons,
    }
    return report


def summarize_campaign_blocker_harvest(
    per_dll_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    families = Counter(str(row.get("blocker_family_primary") or "") for row in per_dll_rows if str(row.get("blocker_family_primary") or ""))
    trust = Counter(str(row.get("lane_trust_status") or "") for row in per_dll_rows if str(row.get("lane_trust_status") or ""))
    relevance = Counter(str(row.get("architecture_relevance") or "") for row in per_dll_rows if str(row.get("architecture_relevance") or ""))
    return {
        "dominant_blocker_families": [
            {"family": family, "dll_count": count}
            for family, count in families.most_common()
        ],
        "lane_trust_summary": dict(trust),
        "architecture_relevance_summary": dict(relevance),
    }
