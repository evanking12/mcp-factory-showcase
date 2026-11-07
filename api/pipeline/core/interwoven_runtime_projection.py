from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from api.pipeline.core.interwoven_artifacts import (
    InterwovenProducerConsumerReport,
    InterwovenSharedStateReport,
    InterwovenStagedChainReport,
)


def _normalize_str_tuple(values: Any) -> tuple[str, ...]:
    return tuple(str(value or "").strip() for value in list(values or []) if str(value or "").strip())


def _coerce_producer_consumer_reports(
    payloads: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> tuple[InterwovenProducerConsumerReport, ...]:
    rows: list[InterwovenProducerConsumerReport] = []
    for item in list(payloads or []):
        if isinstance(item, InterwovenProducerConsumerReport):
            rows.append(item)
        elif isinstance(item, Mapping):
            rows.append(InterwovenProducerConsumerReport.from_dict(dict(item)))
    return tuple(rows)


def _coerce_shared_state_reports(
    payloads: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> tuple[InterwovenSharedStateReport, ...]:
    rows: list[InterwovenSharedStateReport] = []
    for item in list(payloads or []):
        if isinstance(item, InterwovenSharedStateReport):
            rows.append(item)
        elif isinstance(item, Mapping):
            rows.append(InterwovenSharedStateReport.from_dict(dict(item)))
    return tuple(rows)


def _coerce_staged_chain_reports(
    payloads: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> tuple[InterwovenStagedChainReport, ...]:
    rows: list[InterwovenStagedChainReport] = []
    for item in list(payloads or []):
        if isinstance(item, InterwovenStagedChainReport):
            rows.append(item)
        elif isinstance(item, Mapping):
            rows.append(InterwovenStagedChainReport.from_dict(dict(item)))
    return tuple(rows)


def _normalize_subject_hints(subject_dll_hints: Mapping[str, Any] | None) -> dict[str, tuple[str, ...]]:
    normalized: dict[str, tuple[str, ...]] = {}
    for key, values in dict(subject_dll_hints or {}).items():
        subject_id = str(key or "").strip()
        if not subject_id:
            continue
        dlls = _normalize_str_tuple(values)
        if dlls:
            normalized[subject_id] = dlls
    return normalized


def build_interwoven_runtime_projection(
    interwoven_context: dict[str, Any] | None,
) -> dict[str, Any]:
    context = dict(interwoven_context or {})
    subject_hints = _normalize_subject_hints(context.get("subject_dll_hints") or {})
    subjects: list[dict[str, Any]] = []

    for report in _coerce_producer_consumer_reports(context.get("producer_consumer_reports")):
        related_dlls = subject_hints.get(report.family, ())
        if not related_dlls:
            continue
        subjects.append(
            {
                "subject_id": report.family,
                "subject_kind": "producer_consumer",
                "related_dlls": related_dlls,
                "contradiction_state": report.contradiction_state,
            }
        )

    for report in _coerce_shared_state_reports(context.get("shared_state_reports")):
        related_dlls = subject_hints.get(report.carrier_id, ())
        if not related_dlls:
            continue
        subjects.append(
            {
                "subject_id": report.carrier_id,
                "subject_kind": "shared_state",
                "related_dlls": related_dlls,
                "contradiction_state": report.contradiction_state,
            }
        )

    for report in _coerce_staged_chain_reports(context.get("staged_chain_reports")):
        related_dlls = subject_hints.get(report.chain_id, ())
        if not related_dlls:
            continue
        subjects.append(
            {
                "subject_id": report.chain_id,
                "subject_kind": "staged_chain",
                "related_dlls": related_dlls,
                "contradiction_state": report.contradiction_state,
            }
        )

    contradiction_counts = Counter(str(row.get("contradiction_state") or "none").strip() or "none" for row in subjects)
    return {
        "interwoven_artifact_presence": bool(subjects),
        "interwoven_subjects": subjects,
        "interwoven_subject_ids": [str(row.get("subject_id") or "").strip() for row in subjects],
        "interwoven_contradiction_summary": dict(contradiction_counts),
        "interwoven_attribution_present": bool(subjects),
    }


def project_interwoven_for_dlls(
    interwoven_projection: dict[str, Any] | None,
    *,
    dll_names: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    normalized_dlls = {str(name or "").strip() for name in list(dll_names or []) if str(name or "").strip()}
    subjects = []
    for row in list(dict(interwoven_projection or {}).get("interwoven_subjects") or []):
        if not isinstance(row, dict):
            continue
        related = {str(name or "").strip() for name in list(row.get("related_dlls") or []) if str(name or "").strip()}
        if normalized_dlls & related:
            subjects.append(
                {
                    "subject_id": str(row.get("subject_id") or "").strip(),
                    "subject_kind": str(row.get("subject_kind") or "").strip(),
                    "related_dlls": tuple(sorted(related)),
                    "contradiction_state": str(row.get("contradiction_state") or "none").strip() or "none",
                }
            )
    contradiction_counts = Counter(str(row.get("contradiction_state") or "none").strip() or "none" for row in subjects)
    return {
        "interwoven_artifact_presence": bool(subjects),
        "interwoven_subject_ids": [str(row.get("subject_id") or "").strip() for row in subjects],
        "interwoven_contradiction_summary": dict(contradiction_counts),
        "interwoven_attribution_present": bool(subjects),
    }
