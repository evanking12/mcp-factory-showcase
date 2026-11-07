from __future__ import annotations

from typing import Any

from api.pipeline.core.evidence_graph import EDGE_CONFIDENCE_WORKING_CALL_ENTITY
from api.pipeline.core.finding_status import normalize_status

CONTRACT_SCHEMA_VERSION = "1.0.0"
DEPENDENCY_CLASS = "business_object_continuity"
ARTIFACT_KIND = "shared_entity_id"


def _edge_value(edge: dict[str, Any]) -> str:
    return str(edge.get("entity_type") or "").strip()


def _latest_row_map(rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        function_name = str(row.get("function") or "").strip()
        if function_name:
            latest[function_name] = row
    return latest


def _row_mentions_entity(row: dict[str, Any] | None, entity_value: str) -> bool:
    shared_entity = str(entity_value or "").strip().upper()
    if not shared_entity or not isinstance(row, dict):
        return False
    working_call = row.get("working_call")
    if isinstance(working_call, dict):
        for value in working_call.values():
            if isinstance(value, str) and shared_entity in value.strip().upper():
                return True
    corpus = " ".join(
        str(row.get(key) or "")
        for key in ("finding", "notes", "technical_detail", "technical_question", "cross_validation")
    ).upper()
    return shared_entity in corpus


def _row_status_ok(row: dict[str, Any] | None) -> bool:
    return normalize_status((row or {}).get("status_canonical") or (row or {}).get("status")) in {
        "success",
        "verified_success",
    }


def _campaign_epoch_aligned(campaign_graph_epoch: str, producer_row: dict[str, Any], consumer_row: dict[str, Any]) -> bool:
    campaign_epoch = str(campaign_graph_epoch or "").strip()
    if not campaign_epoch:
        return True
    producer_epoch = str(producer_row.get("graph_epoch") or "").strip()
    consumer_epoch = str(consumer_row.get("graph_epoch") or "").strip()
    if producer_epoch and producer_epoch != campaign_epoch:
        return False
    if consumer_epoch and consumer_epoch != campaign_epoch:
        return False
    return True


def build_business_object_contract_surface(
    *,
    campaign_id: str,
    campaign_graph_epoch: str,
    per_dll_rows: list[dict[str, Any]],
    latest_findings_by_job: dict[str, dict[str, dict[str, Any]]] | None,
    evidence_graph: dict[str, Any] | None,
) -> dict[str, Any]:
    latest_by_job = {
        str(job_id or "").strip(): {
            str(function_name or "").strip(): dict(row)
            for function_name, row in dict(rows or {}).items()
            if str(function_name or "").strip() and isinstance(row, dict)
        }
        for job_id, rows in dict(latest_findings_by_job or {}).items()
        if str(job_id or "").strip()
    }
    rows_by_fingerprint = {
        str(row.get("dll_fingerprint") or "").strip(): row
        for row in list(per_dll_rows or [])
        if str(row.get("dll_fingerprint") or "").strip()
    }
    contracts: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    edges = list((evidence_graph or {}).get("edges") or []) if isinstance(evidence_graph, dict) else []

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        producer_fingerprint = str(edge.get("producer_dll") or "").strip()
        consumer_fingerprint = str(edge.get("consumer_dll") or "").strip()
        if not producer_fingerprint or not consumer_fingerprint or producer_fingerprint == consumer_fingerprint:
            continue
        producer_row = rows_by_fingerprint.get(producer_fingerprint)
        consumer_row = rows_by_fingerprint.get(consumer_fingerprint)
        if producer_row is None or consumer_row is None:
            continue
        shared_entity_value = _edge_value(edge)
        if not shared_entity_value or shared_entity_value == "intra_dll_dependency":
            continue

        producer_job_id = str(producer_row.get("job_id") or "").strip()
        consumer_job_id = str(consumer_row.get("job_id") or "").strip()
        producer_function = str(edge.get("producer_fn") or "").strip()
        consumer_function = str(edge.get("consumer_fn") or "").strip()
        if not producer_job_id or not consumer_job_id or not producer_function or not consumer_function:
            continue
        key = (producer_job_id, producer_function, consumer_job_id, consumer_function, shared_entity_value)
        if key in seen:
            continue
        seen.add(key)

        producer_finding = (latest_by_job.get(producer_job_id) or {}).get(producer_function) or {}
        consumer_finding = (latest_by_job.get(consumer_job_id) or {}).get(consumer_function) or {}
        producer_status_ok = _row_status_ok(producer_finding)
        producer_export_observed = _row_mentions_entity(producer_finding, shared_entity_value)
        consumer_import_observed = _row_mentions_entity(consumer_finding, shared_entity_value)
        consumer_seed_sources = [
            str(item).strip()
            for item in list(consumer_row.get("cross_dll_prior_job_ids") or [])
            if str(item).strip()
        ]
        consumer_seed_declared = producer_job_id in consumer_seed_sources
        edge_confidence = float(edge.get("confidence") or 0.0)
        confidence_ok = edge_confidence >= EDGE_CONFIDENCE_WORKING_CALL_ENTITY
        epoch_aligned = _campaign_epoch_aligned(campaign_graph_epoch, producer_row, consumer_row)
        consumer_executed = bool(consumer_finding)

        invariants = [
            {
                "name": "producer_verified_export",
                "expected": True,
                "observed": bool(producer_status_ok and producer_export_observed),
                "details": producer_function,
            },
            {
                "name": "consumer_declared_source_job",
                "expected": True,
                "observed": bool(consumer_seed_declared),
                "details": producer_job_id,
            },
            {
                "name": "consumer_import_observed",
                "expected": True,
                "observed": bool(consumer_import_observed),
                "details": consumer_function,
            },
            {
                "name": "graph_epoch_aligned",
                "expected": True,
                "observed": bool(epoch_aligned),
                "details": str(campaign_graph_epoch or "").strip(),
            },
            {
                "name": "edge_confidence_floor",
                "expected": True,
                "observed": bool(confidence_ok),
                "details": round(edge_confidence, 2),
            },
        ]

        reasons: list[str] = []
        if not producer_status_ok:
            reasons.append("producer_not_verified")
        if not producer_export_observed:
            reasons.append("producer_export_not_observed")
        if not consumer_seed_declared:
            reasons.append("consumer_missing_source_job_seed")
        if not epoch_aligned:
            reasons.append("graph_epoch_mismatch")
        if not confidence_ok:
            reasons.append("edge_confidence_below_floor")
        if consumer_executed and not consumer_import_observed:
            reasons.append("consumer_missing_import_observation")

        if (
            producer_status_ok
            and producer_export_observed
            and consumer_seed_declared
            and consumer_import_observed
            and epoch_aligned
            and confidence_ok
        ):
            observer_status = "pass"
        elif (
            producer_status_ok
            and producer_export_observed
            and consumer_seed_declared
            and epoch_aligned
            and confidence_ok
            and not consumer_executed
        ):
            observer_status = "warn"
            reasons.append("consumer_execution_not_yet_observed")
        else:
            observer_status = "fail"

        contracts.append(
            {
                "contract_id": f"{producer_job_id}:{producer_function}->{consumer_job_id}:{consumer_function}:{shared_entity_value}",
                "dependency_class": DEPENDENCY_CLASS,
                "producer": {
                    "job_id": producer_job_id,
                    "dll_id": producer_row.get("dll_id", ""),
                    "filename": producer_row.get("filename", ""),
                    "dll_fingerprint": producer_fingerprint,
                    "function": producer_function,
                },
                "consumer": {
                    "job_id": consumer_job_id,
                    "dll_id": consumer_row.get("dll_id", ""),
                    "filename": consumer_row.get("filename", ""),
                    "dll_fingerprint": consumer_fingerprint,
                    "function": consumer_function,
                },
                "exported_truth": {
                    "artifact_kind": ARTIFACT_KIND,
                    "entity_value": shared_entity_value,
                    "source": "working_call_entity_overlap",
                    "evidence_job": str(edge.get("evidence_job") or "").strip(),
                },
                "import_expectations": {
                    "consumer_must_reference_exported_entity": True,
                    "required_cross_dll_source_job_id": producer_job_id,
                    "allowed_downstream_consumers": [consumer_function],
                },
                "confidence_requirements": {
                    "minimum_edge_confidence": EDGE_CONFIDENCE_WORKING_CALL_ENTITY,
                    "observed_edge_confidence": round(edge_confidence, 2),
                    "producer_statuses": ["success", "verified_success"],
                    "same_graph_epoch_required": bool(str(campaign_graph_epoch or "").strip()),
                },
                "handoff_invariants": invariants,
                "boundary_observer": {
                    "status": observer_status,
                    "reasons": reasons,
                    "consumer_executed": consumer_executed,
                },
            }
        )

    summary = {"pass": 0, "warn": 0, "fail": 0}
    for contract in contracts:
        status = str((contract.get("boundary_observer") or {}).get("status") or "fail")
        summary[status] = summary.get(status, 0) + 1

    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "dependency_class": DEPENDENCY_CLASS,
        "contract_scope": "verified_runtime_entity_continuity",
        "artifact_kind": ARTIFACT_KIND,
        "minimum_edge_confidence": EDGE_CONFIDENCE_WORKING_CALL_ENTITY,
        "contract_count": len(contracts),
        "summary": {
            "pass": summary.get("pass", 0),
            "warn": summary.get("warn", 0),
            "fail": summary.get("fail", 0),
        },
        "contracts": contracts,
    }


def latest_findings_by_job(findings_by_job: dict[str, list[dict[str, Any]]] | None) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        str(job_id or "").strip(): _latest_row_map(rows)
        for job_id, rows in dict(findings_by_job or {}).items()
        if str(job_id or "").strip()
    }
