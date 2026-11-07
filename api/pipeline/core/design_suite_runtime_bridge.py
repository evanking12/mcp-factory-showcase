from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from api.pipeline.core.design_suite_artifacts import (
    NORTHSTAR_EXPECTED_OBSERVED_ARTIFACT,
    NORTHSTAR_FAMILY_BLOCKER_ARTIFACT,
    NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT,
    NORTHSTAR_SHARED_STATE_ARTIFACT,
    NorthstarFamilyBlockerReport,
    NorthstarProducerConsumerReport,
    NorthstarSharedStateReport,
)


DESIGN_SUITE_RUNTIME_PLAN_SCHEMA_VERSION = "1.0.0"
DESIGN_SUITE_PACKAGE_TRUTH_SCHEMA_VERSION = "1.0.0"
DESIGN_SUITE_COHESION_REPORT_SCHEMA_VERSION = "1.0.0"

DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT = "design-suite-runtime-plan.json"
DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT = "design-suite-package-truth.json"
DESIGN_SUITE_COHESION_REPORT_ARTIFACT = "design-suite-cohesion-report.json"
DESIGN_SUITE_EXECUTION_TRACE_ARTIFACT = "design-suite-execution-trace.json"

DESIGN_SUITE_PRESSURE_MODES = (
    "base",
    "overlap",
    "late_confirmation",
    "forked_state",
    "mutual_pressure",
)


def resolve_design_suite_pressure_mode(
    mode: str | None = None,
    *,
    include_overlap: bool = False,
    include_late_confirmation: bool = False,
    include_forked_state: bool = False,
) -> str:
    explicit_mode = str(mode or "").strip().lower()
    if explicit_mode:
        if explicit_mode not in DESIGN_SUITE_PRESSURE_MODES:
            raise ValueError(f"unknown design-suite pressure mode: {mode!r}")
        if any((include_overlap, include_late_confirmation, include_forked_state)):
            raise ValueError("pressure mode must not be combined with legacy boolean pressure flags")
        return explicit_mode
    selected = [
        pressure_mode
        for pressure_mode, enabled in (
            ("overlap", include_overlap),
            ("late_confirmation", include_late_confirmation),
            ("forked_state", include_forked_state),
        )
        if enabled
    ]
    if len(selected) > 1:
        raise ValueError("design-suite runtime pressure must remain bounded to one pressure at a time")
    return selected[0] if selected else "base"


def _coerce_producer_consumer_reports(payloads: Any) -> tuple[NorthstarProducerConsumerReport, ...]:
    rows: list[NorthstarProducerConsumerReport] = []
    for item in list(payloads or []):
        if isinstance(item, NorthstarProducerConsumerReport):
            rows.append(item)
        elif isinstance(item, Mapping):
            payload = dict(item)
            payload.pop("artifact_type", None)
            payload.pop("contract_version", None)
            rows.append(NorthstarProducerConsumerReport(**payload))
    return tuple(rows)


def _coerce_shared_state_reports(payloads: Any) -> tuple[NorthstarSharedStateReport, ...]:
    rows: list[NorthstarSharedStateReport] = []
    for item in list(payloads or []):
        if isinstance(item, NorthstarSharedStateReport):
            rows.append(item)
        elif isinstance(item, Mapping):
            payload = dict(item)
            payload.pop("artifact_type", None)
            payload.pop("contract_version", None)
            rows.append(NorthstarSharedStateReport(**payload))
    return tuple(rows)


def _coerce_family_blocker_reports(payloads: Any) -> tuple[NorthstarFamilyBlockerReport, ...]:
    rows: list[NorthstarFamilyBlockerReport] = []
    for item in list(payloads or []):
        if isinstance(item, NorthstarFamilyBlockerReport):
            rows.append(item)
        elif isinstance(item, Mapping):
            payload = dict(item)
            payload.pop("artifact_type", None)
            payload.pop("contract_version", None)
            rows.append(NorthstarFamilyBlockerReport(**payload))
    return tuple(rows)


def _collect_execution_order(execution_trace: Mapping[str, Any] | None) -> list[str]:
    order: list[str] = []
    for row in list(dict(execution_trace or {}).get("steps") or []):
        if not isinstance(row, Mapping):
            continue
        module_name = str(row.get("module") or "").strip()
        function_name = str(row.get("function") or "").strip()
        if module_name and function_name:
            order.append(f"{module_name}.{function_name}")
    return order


def _collect_per_module(execution_trace: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    per_module: dict[str, dict[str, Any]] = {}
    for row in list(dict(execution_trace or {}).get("steps") or []):
        if not isinstance(row, Mapping):
            continue
        module_name = str(row.get("module") or "").strip()
        function_name = str(row.get("function") or "").strip()
        if not module_name:
            continue
        record = per_module.setdefault(
            module_name,
            {
                "module": module_name,
                "steps": [],
                "status": "not_run",
                "outputs": [],
            },
        )
        status = str(row.get("status") or "").strip().lower() or "unknown"
        record["steps"].append(function_name)
        if status == "success":
            record["status"] = "success"
        elif status in {"rejected", "error"} and record["status"] != "success":
            record["status"] = status
        output_keys = [str(key).strip() for key in list(row.get("output_keys") or []) if str(key).strip()]
        for item in output_keys:
            if item not in record["outputs"]:
                record["outputs"].append(item)
    return [per_module[key] for key in sorted(per_module)]


def _derive_interwoven_projection(
    producer_reports: tuple[NorthstarProducerConsumerReport, ...],
    shared_state_reports: tuple[NorthstarSharedStateReport, ...],
) -> dict[str, Any]:
    subjects: list[dict[str, Any]] = []
    for report in producer_reports:
        subjects.append(
            {
                "subject_id": report.family,
                "subject_kind": "producer_consumer",
                "contradiction_state": report.contradiction_state,
            }
        )
    for report in shared_state_reports:
        subjects.append(
            {
                "subject_id": report.carrier_id,
                "subject_kind": "shared_state",
                "contradiction_state": report.contradiction_state,
            }
        )
    contradiction_counts = Counter(
        str(row.get("contradiction_state") or "none").strip() or "none"
        for row in subjects
    )
    return {
        "interwoven_artifact_presence": bool(subjects),
        "interwoven_subject_ids": [str(row.get("subject_id") or "").strip() for row in subjects],
        "interwoven_subjects": subjects,
        "interwoven_contradiction_summary": dict(contradiction_counts),
        "interwoven_attribution_present": bool(subjects),
    }


def build_design_suite_runtime_projection(
    suite_contract: Mapping[str, Any],
    truth_manifest: Mapping[str, Any],
    observed_bundle: Mapping[str, Any],
    execution_trace: Mapping[str, Any],
    pressure_mode: str,
) -> dict[str, Any]:
    normalized_mode = resolve_design_suite_pressure_mode(pressure_mode)
    contract = dict(suite_contract or {})
    manifest = dict(truth_manifest or {})
    producer_reports = _coerce_producer_consumer_reports(observed_bundle.get(NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT))
    shared_state_reports = _coerce_shared_state_reports(observed_bundle.get(NORTHSTAR_SHARED_STATE_ARTIFACT))
    blocker_reports = _coerce_family_blocker_reports(observed_bundle.get(NORTHSTAR_FAMILY_BLOCKER_ARTIFACT))
    interwoven_projection = _derive_interwoven_projection(producer_reports, shared_state_reports)
    contradiction_counts = Counter(report.contradiction_state for report in blocker_reports)

    active_modules = tuple(str(item).strip() for item in list((execution_trace or {}).get("active_modules") or []) if str(item).strip())
    if not active_modules:
        active_modules = tuple(str(item).strip() for item in list(manifest.get("active_modules") or []) if str(item).strip())
    deferred_modules = tuple(
        str((item or {}).get("module") if isinstance(item, Mapping) else item).strip()
        for item in list(manifest.get("deferred_modules") or [])
        if str((item or {}).get("module") if isinstance(item, Mapping) else item).strip()
    )
    if active_modules:
        deferred_modules = tuple(module_name for module_name in deferred_modules if module_name not in active_modules)
    provisional_subject_ids = sorted(
        {
            item
            for report in blocker_reports
            for item in report.provisional_subjects
            if str(item or "").strip()
        }
    )
    confirmation_sites = sorted(
        {
            item
            for report in blocker_reports
            for item in report.confirmation_sites
            if str(item or "").strip()
        }
    )
    lineage_branches = sorted(
        {
            item
            for report in blocker_reports
            for item in report.lineage_branches
            if str(item or "").strip()
        }
    )
    accepted_branches = sorted(
        {
            report.accepted_branch
            for report in blocker_reports
            if str(report.accepted_branch or "").strip()
        }
    )
    rejected_branches = sorted(
        {
            item
            for report in blocker_reports
            for item in report.rejected_branches
            if str(item or "").strip()
        }
    )
    blocker_family_ids = sorted({report.blocker_family for report in blocker_reports})

    return {
        "schema_version": DESIGN_SUITE_RUNTIME_PLAN_SCHEMA_VERSION,
        "artifact_type": DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT,
        "suite_id": str(contract.get("suite_id") or manifest.get("suite_id") or "").strip(),
        "suite_name": str(contract.get("suite_name") or manifest.get("suite_name") or "").strip(),
        "pressure_mode": normalized_mode,
        "package_surface": "local_design_suite",
        "compare_boundary": "architecture_proof_only",
        "active_modules": list(active_modules),
        "deferred_modules": list(deferred_modules),
        "execution_order": _collect_execution_order(execution_trace),
        "blocker_family_ids": blocker_family_ids,
        "design_suite_subject_ids": list(interwoven_projection.get("interwoven_subject_ids") or []),
        "design_suite_contradiction_summary": dict(contradiction_counts),
        "runtime_attribution_present": bool(interwoven_projection.get("interwoven_attribution_present")),
        "provisional_subject_ids": provisional_subject_ids,
        "confirmation_sites": confirmation_sites,
        "lineage_branches": lineage_branches,
        "accepted_branches": accepted_branches,
        "rejected_branches": rejected_branches,
        "interwoven_projection": interwoven_projection,
    }


def build_design_suite_package_truth(
    runtime_projection: Mapping[str, Any],
    execution_trace: Mapping[str, Any],
) -> dict[str, Any]:
    projection = dict(runtime_projection or {})
    return {
        "schema_version": DESIGN_SUITE_PACKAGE_TRUTH_SCHEMA_VERSION,
        "artifact_type": DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT,
        "suite_id": str(projection.get("suite_id") or "").strip(),
        "pressure_mode": str(projection.get("pressure_mode") or "").strip(),
        "active_modules": list(projection.get("active_modules") or []),
        "per_module": _collect_per_module(execution_trace),
        "blocker_family_ids": list(projection.get("blocker_family_ids") or []),
        "provisional_subject_ids": list(projection.get("provisional_subject_ids") or []),
        "confirmation_sites": list(projection.get("confirmation_sites") or []),
        "lineage_branches": list(projection.get("lineage_branches") or []),
        "accepted_branches": list(projection.get("accepted_branches") or []),
        "rejected_branches": list(projection.get("rejected_branches") or []),
        "design_suite_projection_present": True,
        "package_runtime_evidence_class": "design_suite_local_projection",
        "compare_ready": False,
        "promotion_ready": False,
    }


def build_design_suite_cohesion_report(
    runtime_projection: Mapping[str, Any],
    package_truth: Mapping[str, Any],
) -> dict[str, Any]:
    projection = dict(runtime_projection or {})
    truth = dict(package_truth or {})
    return {
        "schema_version": DESIGN_SUITE_COHESION_REPORT_SCHEMA_VERSION,
        "artifact_type": DESIGN_SUITE_COHESION_REPORT_ARTIFACT,
        "suite_id": str(projection.get("suite_id") or "").strip(),
        "pressure_mode": str(projection.get("pressure_mode") or "").strip(),
        "active_modules": list(projection.get("active_modules") or []),
        "blocker_family_ids": list(projection.get("blocker_family_ids") or []),
        "design_suite_subject_ids": list(projection.get("design_suite_subject_ids") or []),
        "provisional_subject_ids": list(projection.get("provisional_subject_ids") or []),
        "confirmation_sites": list(projection.get("confirmation_sites") or []),
        "lineage_branches": list(projection.get("lineage_branches") or []),
        "accepted_branches": list(projection.get("accepted_branches") or []),
        "design_suite_contradiction_summary": dict(projection.get("design_suite_contradiction_summary") or {}),
        "runtime_attribution_present": bool(projection.get("runtime_attribution_present")),
        "complete": bool(truth.get("design_suite_projection_present")),
        "readable": True,
    }
