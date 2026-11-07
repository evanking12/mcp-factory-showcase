from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


def _utc_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _target_name(record: Mapping[str, Any]) -> str:
    chain_context = record.get("chain_context") if isinstance(record.get("chain_context"), Mapping) else {}
    return str(
        record.get("target")
        or record.get("target_name")
        or (chain_context or {}).get("target_name")
        or record.get("dll_name")
        or ""
    ).strip()


def _safe_to_compare(record: Mapping[str, Any]) -> bool:
    branch_authority = dict(record.get("enterprise_survivability_authority") or {})
    if branch_authority:
        return bool(branch_authority.get("safe_to_compare"))
    measurement = dict(record.get("measurement_terminalization") or {})
    if measurement:
        return bool(measurement.get("safe_to_compare"))
    authority = dict(record.get("run_authority") or {})
    if authority:
        return bool(authority.get("safe_to_steer_next_prompt"))
    return bool(record.get("safe_to_compare"))


def _record_state(record: Mapping[str, Any]) -> str:
    if str(record.get("skipped_reason") or "").strip() == "dependency_blocked":
        return "skipped_dependency_blocked"
    measurement = dict(record.get("measurement_terminalization") or {})
    if measurement:
        return "non_comparable"
    warnings = list(record.get("critical_warnings") or [])
    if _safe_to_compare(record) and warnings:
        return "comparable_with_warnings"
    if _safe_to_compare(record):
        return "comparable"
    return "non_comparable"


def _row_from_record(record: Mapping[str, Any], *, state: str | None = None) -> dict[str, Any]:
    measurement = dict(record.get("measurement_terminalization") or {})
    branch_authority = dict(record.get("enterprise_survivability_authority") or {})
    warnings = list(record.get("critical_warnings") or [])
    row_state = state or _record_state(record)
    evidence_paths = list(measurement.get("evidence_paths") or record.get("evidence_paths") or [])
    if branch_authority:
        evidence_paths.extend(str(path) for path in list(branch_authority.get("evidence_refs") or []) if str(path))
    return {
        "target": _target_name(record),
        "state": row_state,
        "safe_to_compare": row_state == "comparable" or row_state == "comparable_with_warnings",
        "reason_code": str(
            record.get("skipped_reason")
            or branch_authority.get("blocking_signal")
            or branch_authority.get("reason_code")
            or measurement.get("reason_code")
            or record.get("reason_code")
            or ""
        ),
        "owner": str(
            branch_authority.get("authority_name")
            or measurement.get("owner")
            or record.get("owner")
            or ""
        ),
        "phase": str(record.get("phase") or measurement.get("phase") or ""),
        "job_id": str(record.get("job_id") or measurement.get("job_id") or ""),
        "critical_warnings": warnings,
        "evidence_paths": evidence_paths,
    }


def build_enterprise_survivability_summary(
    *,
    suite_id: str,
    case_id: str,
    records: Sequence[Mapping[str, Any]],
    dependency_graph: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Build a final suite packet that preserves comparable and blocked boundaries."""

    rows: list[dict[str, Any]] = []
    state_by_target: dict[str, str] = {}
    record_by_target = {_target_name(record): dict(record) for record in records if _target_name(record)}

    for record in records:
        target = _target_name(record)
        if not target:
            continue
        row = _row_from_record(record)
        rows.append(row)
        state_by_target[target] = row["state"]

    blocked_states = {"non_comparable", "skipped_dependency_blocked"}
    for target, predecessors in dependency_graph.items():
        if target in record_by_target:
            continue
        blocked_by = [name for name in predecessors if state_by_target.get(str(name)) in blocked_states]
        if not blocked_by:
            continue
        row = _row_from_record(
            {
                "target": target,
                "skipped_reason": "dependency_blocked",
                "phase": "pre-execution",
                "critical_warnings": [
                    {
                        "code": "dependency_blocked",
                        "blocked_by": blocked_by,
                    }
                ],
            },
            state="skipped_dependency_blocked",
        )
        row["blocked_by"] = blocked_by
        rows.append(row)
        state_by_target[target] = row["state"]

    counts = {
        "comparable": sum(1 for row in rows if row["state"] == "comparable"),
        "comparable_with_warnings": sum(1 for row in rows if row["state"] == "comparable_with_warnings"),
        "non_comparable": sum(1 for row in rows if row["state"] == "non_comparable"),
        "skipped_dependency_blocked": sum(1 for row in rows if row["state"] == "skipped_dependency_blocked"),
    }
    suite_state = (
        "comparable_success"
        if rows and counts["non_comparable"] == 0 and counts["skipped_dependency_blocked"] == 0
        else "partial_result_with_warnings"
        if rows and (counts["comparable"] or counts["comparable_with_warnings"])
        else "non_comparable_failure"
    )
    return {
        "schema_version": "1.0.0",
        "suite_id": suite_id,
        "case_id": case_id,
        "status": suite_state,
        "safe_to_compare": suite_state == "comparable_success",
        "target_counts": counts,
        "targets": rows,
        "claim_ceiling": "enterprise_survivability_only",
        "semantic_proof_satisfied": False,
        "created_at": _utc_iso(),
    }


def dependency_graph_from_chain_plan(chain_plan: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for step in chain_plan:
        target = str(step.get("target_name") or "").strip()
        if not target:
            continue
        graph[target] = [str(item).strip() for item in list(step.get("predecessor_targets") or []) if str(item).strip()]
    return graph


def write_enterprise_survivability_summary(
    *,
    output_dir: Path,
    suite_id: str,
    case_id: str,
    run_records: Sequence[Mapping[str, Any]],
    chain_plan: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    summary = build_enterprise_survivability_summary(
        suite_id=suite_id,
        case_id=case_id,
        records=run_records,
        dependency_graph=dependency_graph_from_chain_plan(chain_plan),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "enterprise-survivability-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary
