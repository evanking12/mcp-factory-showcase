from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


FailureKindFn = Callable[[dict[str, Any]], str]


def record_safe_to_compare(record: dict[str, Any]) -> bool:
    if record.get("safe_to_compare") is not None:
        return bool(record.get("safe_to_compare"))
    control_plane = dict(record.get("measurement_control_plane") or {})
    if control_plane and not bool(control_plane.get("safe_to_compare")):
        return False
    terminalization = dict(record.get("measurement_terminalization") or {})
    if terminalization and not bool(terminalization.get("safe_to_compare", False)):
        return False
    analyzer_authority = dict(record.get("analyzer_authority") or {})
    discovery_authority = dict(analyzer_authority.get("discovery_output_authority") or {})
    if discovery_authority and not bool(discovery_authority.get("safe_to_compare")):
        return False
    return str(record.get("status") or "").strip().lower() == "ok"


def default_failure_kind_for_record(record: dict[str, Any]) -> str:
    terminalization = dict(record.get("job_terminalization") or {})
    kind = str(terminalization.get("terminalization_kind") or terminalization.get("kind") or "").strip()
    phase = str(record.get("phase") or "").strip().lower()
    if kind == "timeout":
        if phase.startswith("analy"):
            return "analyze_timeout"
        if phase.startswith("explor"):
            return "explore_timeout"
        return "timeout"
    if kind and kind != "done":
        return f"runner_{kind}"
    if str(record.get("failure_domain") or "").strip():
        return str(record.get("failure_domain") or "").strip()
    if str(record.get("error") or "").strip():
        return "runner_error"
    if str(record.get("status") or "").strip().lower() != "ok":
        return f"status_{str(record.get('status') or '').strip().lower()}"
    return ""


def canonical_blocking_signal_for_record(
    record: dict[str, Any],
    *,
    failure_kind_for_record: FailureKindFn = default_failure_kind_for_record,
) -> str:
    product_route_authority = dict(record.get("product_route_authority") or {})
    product_route_blocking = str(product_route_authority.get("blocking_signal") or "").strip()
    analyzer_authority = dict(record.get("analyzer_authority") or {})
    discovery_authority = dict(analyzer_authority.get("discovery_output_authority") or {})
    if not discovery_authority:
        discovery_authority = dict(record.get("discovery_output_authority") or {})
    if str(discovery_authority.get("reason_code") or "").strip():
        return str(discovery_authority.get("reason_code") or "").strip()
    if product_route_blocking and product_route_blocking != "product_route_gap":
        return product_route_blocking
    terminalization = dict(record.get("measurement_terminalization") or record.get("job_terminalization") or {})
    terminal_reason = dict(terminalization.get("reason") or {})
    for value in (
        terminalization.get("reason_code"),
        terminal_reason.get("code"),
        terminalization.get("terminalization_kind"),
        terminalization.get("kind"),
    ):
        text = str(value or "").strip()
        if text and text != "done" and not text.startswith("job_completed_"):
            return text
    failure_kind = str(failure_kind_for_record(record) or "").strip()
    if failure_kind:
        return failure_kind
    if product_route_blocking:
        return product_route_blocking
    return "non_comparable_record"


def _read_json_object(path: Path) -> Any:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _session_dir_for_record(record: dict[str, Any]) -> Path | None:
    run_dir = str(record.get("run_dir") or "").strip()
    if not run_dir:
        return None
    return Path(run_dir) / "session"


def _invocable_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("invocables"), list):
            return [dict(item) for item in payload["invocables"] if isinstance(item, dict)]
        entries: list[dict[str, Any]] = []
        for key, value in payload.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("name", str(key))
                entries.append(row)
        return entries
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    return []


def _selected_invocable_entry(
    invocables_payload: Any,
    required_checkpoint: str,
) -> dict[str, Any] | None:
    entries = _invocable_entries(invocables_payload)
    if required_checkpoint:
        for entry in entries:
            if str(entry.get("name") or "").strip() == required_checkpoint:
                return entry
        return None
    return entries[0] if entries else None


def _entry_has_ghidra_route_evidence(entry: dict[str, Any] | None) -> bool:
    if not entry:
        return False
    source_type = str(entry.get("source_type") or "").strip()
    return bool(
        source_type == "ghidra_export"
        or entry.get("_ghidra_provenance")
        or entry.get("_ghidra_extras")
    )


def _record_has_decision_bearing_authority(record: dict[str, Any]) -> bool:
    run_authority = dict(record.get("run_authority") or {})
    return bool(
        record.get("authoritative_proving")
        or run_authority.get("authoritative_proving")
        or run_authority.get("decision_bearing")
        or str(run_authority.get("authority_level") or "").strip() == "decision_bearing"
    )


def product_route_authority_for_record(record: dict[str, Any]) -> dict[str, Any]:
    existing = record.get("product_route_authority")
    if isinstance(existing, dict) and existing:
        return dict(existing)

    target_name = str((record.get("chain_context") or {}).get("target_name") or record.get("target") or "").strip()
    required_checkpoint = str(
        (record.get("chain_context") or {}).get("required_semantic_checkpoint") or ""
    ).strip()
    session_dir = _session_dir_for_record(record)
    evidence_paths: list[str] = []
    discovery_meta: dict[str, Any] = {}
    invocables_payload: Any = None
    ghidra_static_present = False

    if session_dir is not None:
        discovery_meta_path = session_dir / "discovery_meta.json"
        raw_discovery_meta = _read_json_object(discovery_meta_path)
        if isinstance(raw_discovery_meta, dict):
            discovery_meta = raw_discovery_meta
            evidence_paths.append(str(discovery_meta_path))

        invocable_paths = [
            session_dir / "invocables_map.json",
            session_dir / "evidence" / "stage-00-setup" / "invocables-map.json",
        ]
        for path in invocable_paths:
            invocables_payload = _read_json_object(path)
            if invocables_payload is not None:
                evidence_paths.append(str(path))
                break

        ghidra_static_paths = [
            session_dir / "evidence" / "stage-00b-static-evidence" / "ghidra-data-types.json",
            session_dir / "evidence" / "stage-00b-static-evidence" / "static-analysis.json",
        ]
        for path in ghidra_static_paths:
            if path.exists() and path.stat().st_size > 0:
                ghidra_static_present = True
                evidence_paths.append(str(path))

    selected_entry = _selected_invocable_entry(invocables_payload, required_checkpoint)
    durable_discovery_output = selected_entry is not None
    ghidra_invocable_evidence = _entry_has_ghidra_route_evidence(selected_entry)
    decision_bearing = _record_has_decision_bearing_authority(record)
    route_authority_present = bool(
        durable_discovery_output
        and ghidra_invocable_evidence
        and decision_bearing
        and record_safe_to_compare(record)
    )

    if route_authority_present:
        reason_code = "ghidra_route_authority_present"
        blocking_signal = ""
        route_source = "session_invocables_ghidra_provenance"
    elif not durable_discovery_output:
        reason_code = "durable_discovery_output_missing"
        blocking_signal = "product_route_gap"
        route_source = ""
    elif ghidra_static_present and not ghidra_invocable_evidence:
        reason_code = "ghidra_static_only_not_route_authority"
        blocking_signal = "product_route_gap"
        route_source = "static_evidence_only"
    elif not ghidra_invocable_evidence:
        reason_code = "ghidra_invocable_evidence_missing"
        blocking_signal = "product_route_gap"
        route_source = ""
    elif not decision_bearing:
        reason_code = "decision_bearing_run_authority_missing"
        blocking_signal = "product_route_gap"
        route_source = "session_invocables_ghidra_provenance"
    else:
        reason_code = "product_route_authority_missing"
        blocking_signal = "product_route_gap"
        route_source = ""

    return {
        "schema_version": "1.0.0",
        "target": target_name,
        "required_semantic_checkpoint": required_checkpoint,
        "ghidra_required": True,
        "route_authority_required": True,
        "route_authority_present": route_authority_present,
        "route_authority_source": route_source,
        "ghidra_evidence_paths": evidence_paths,
        "durable_discovery_output": durable_discovery_output,
        "ghidra_invocable_evidence": ghidra_invocable_evidence,
        "ghidra_static_evidence_present": ghidra_static_present,
        "decision_bearing_run_authority": decision_bearing,
        "bridge_reachable": bool(discovery_meta.get("bridge_reachable")),
        "safe_to_compare": bool(route_authority_present),
        "reason_code": reason_code,
        "blocking_signal": blocking_signal,
    }


def record_route_authority_present(record: dict[str, Any]) -> bool:
    route_authority = dict(record.get("product_route_authority") or {})
    if route_authority:
        return bool(route_authority.get("route_authority_present"))
    if record.get("route_authority_present") is not None:
        return bool(record.get("route_authority_present"))
    analyzer_authority = dict(record.get("analyzer_authority") or {})
    discovery_authority = dict(analyzer_authority.get("discovery_output_authority") or {})
    if not discovery_authority:
        discovery_authority = dict(record.get("discovery_output_authority") or {})
    if not discovery_authority:
        return False
    return (
        bool(discovery_authority.get("ghidra_required"))
        and bool(discovery_authority.get("ghidra_entered"))
        and bool(discovery_authority.get("safe_to_compare"))
        and str(discovery_authority.get("reason_code") or "")
        in {"ghidra_discovery_output_present", "ghidra_route_selected"}
    )


def record_semantic_proof_satisfied(record: dict[str, Any]) -> bool:
    if record.get("semantic_proof_satisfied") is not None:
        return bool(record.get("semantic_proof_satisfied"))
    checkpoint = str(
        (record.get("chain_context") or {}).get("required_semantic_checkpoint") or ""
    ).strip()
    if not checkpoint:
        return False
    latest_status = str((record.get("latest_status_map") or {}).get(checkpoint) or "").strip().lower()
    return latest_status in {"verified_success", "success", "passed", "ok", "inferred_success"}


def product_contract_fields_for_record(
    record: dict[str, Any],
    *,
    failure_kind_for_record: FailureKindFn = default_failure_kind_for_record,
) -> dict[str, Any]:
    route_authority_present = record_route_authority_present(record)
    safe_to_compare = record_safe_to_compare(record)
    semantic_proof_satisfied = record_semantic_proof_satisfied(record)
    authoritative_proving = bool(record.get("authoritative_proving"))
    if record.get("authoritative_proving") is None:
        authoritative_proving = safe_to_compare and semantic_proof_satisfied
    enterprise_authority = dict(record.get("enterprise_survivability_authority") or {})
    enterprise_authority_present = True
    enterprise_blocking_signal = ""
    if enterprise_authority:
        enterprise_authority_present = bool(enterprise_authority.get("authority_present"))
        enterprise_blocking_signal = str(
            enterprise_authority.get("blocking_signal")
            or enterprise_authority.get("reason_code")
            or ""
        ).strip()
        safe_to_compare = safe_to_compare and bool(enterprise_authority.get("safe_to_compare"))
        semantic_proof_satisfied = semantic_proof_satisfied and bool(
            enterprise_authority.get("semantic_proof_satisfied")
        )
        authoritative_proving = authoritative_proving and enterprise_authority_present
    return {
        "green_contract_level": "product_route_probe",
        "product_green_eligible": bool(
            route_authority_present
            and safe_to_compare
            and semantic_proof_satisfied
            and authoritative_proving
        ),
        "route_authority_required": True,
        "ghidra_required": True,
        "route_authority_present": route_authority_present,
        "safe_to_compare": safe_to_compare,
        "semantic_proof_satisfied": semantic_proof_satisfied,
        "authoritative_proving": authoritative_proving,
        "blocking_signal": (
            enterprise_blocking_signal
            if enterprise_blocking_signal and not enterprise_authority_present
            else
            "product_route_gap"
            if not route_authority_present and safe_to_compare
            else ""
            if safe_to_compare
            else canonical_blocking_signal_for_record(
                record,
                failure_kind_for_record=failure_kind_for_record,
            )
        ),
    }


def product_contract_summary(
    run_records: list[dict[str, Any]],
    report: dict[str, Any],
    *,
    expected_target_count: int,
    failure_kind_for_record: FailureKindFn = default_failure_kind_for_record,
) -> dict[str, Any]:
    fields_by_target = {
        str((record.get("chain_context") or {}).get("target_name") or record.get("target") or "").strip():
        product_contract_fields_for_record(record, failure_kind_for_record=failure_kind_for_record)
        for record in run_records
    }
    all_targets_present = len(run_records) == expected_target_count
    all_product_eligible = all_targets_present and all(
        bool(fields.get("product_green_eligible")) for fields in fields_by_target.values()
    )
    semantic_alignment = bool(report.get("semantic_checkpoint_alignment_succeeded"))
    product_green = all_product_eligible and semantic_alignment
    blocking_signal = ""
    for record in run_records:
        target_name = str((record.get("chain_context") or {}).get("target_name") or "").strip()
        fields = fields_by_target.get(target_name, {})
        if not bool(fields.get("product_green_eligible")):
            blocking_signal = str(
                fields.get("blocking_signal")
                or failure_kind_for_record(record)
                or "product_route_gap"
            )
            break
    if not blocking_signal and not product_green:
        blocking_signal = "semantic_checkpoint_gap" if not semantic_alignment else "incomplete_product_chain"
    return {
        "green_contract_level": "product_green" if product_green else "measurement_green",
        "product_green_eligible": product_green,
        "route_authority_required": True,
        "ghidra_required": True,
        "route_authority_present": all_targets_present and all(
            bool(fields.get("route_authority_present")) for fields in fields_by_target.values()
        ),
        "safe_to_compare": all_targets_present and all(
            bool(fields.get("safe_to_compare")) for fields in fields_by_target.values()
        ),
        "semantic_proof_satisfied": product_green,
        "authoritative_proving": all_targets_present and all(
            bool(fields.get("authoritative_proving")) for fields in fields_by_target.values()
        ),
        "blocking_signal": blocking_signal,
        "per_target_green_contract": fields_by_target,
    }
