from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Mapping

from api.pipeline.core.interwoven_artifacts import (
    InterwovenProducerConsumerReport,
    InterwovenSharedStateReport,
    InterwovenStagedChainReport,
)
from api.pipeline.core.interwoven_observers import (
    build_interwoven_state_staleness_risk_observer,
    build_producer_consumer_plausibility_observer,
    build_shared_state_reuse_plausibility_observer,
    build_staged_chain_ordering_plausibility_observer,
)


_CONTRADICTION_VISIBLE_STATES = {"tentative", "blocked", "contradicted", "quarantined", "superseded"}
_FAIL_OR_WARN = {"warn", "fail"}
_EXPECTED_PROOF_STATUSES = {"pass", "fail"}


def _coerce_producer_consumer_reports(
    payloads: tuple[InterwovenProducerConsumerReport | Mapping[str, Any], ...] | list[InterwovenProducerConsumerReport | Mapping[str, Any]] | None,
) -> tuple[InterwovenProducerConsumerReport, ...]:
    if isinstance(payloads, (InterwovenProducerConsumerReport, Mapping)):
        payloads = (payloads,)
    reports: list[InterwovenProducerConsumerReport] = []
    for item in tuple(payloads or ()):
        if isinstance(item, InterwovenProducerConsumerReport):
            reports.append(item)
        else:
            reports.append(InterwovenProducerConsumerReport.from_dict(dict(item)))
    return tuple(reports)


def _coerce_shared_state_reports(
    payloads: tuple[InterwovenSharedStateReport | Mapping[str, Any], ...] | list[InterwovenSharedStateReport | Mapping[str, Any]] | None,
) -> tuple[InterwovenSharedStateReport, ...]:
    if isinstance(payloads, (InterwovenSharedStateReport, Mapping)):
        payloads = (payloads,)
    reports: list[InterwovenSharedStateReport] = []
    for item in tuple(payloads or ()):
        if isinstance(item, InterwovenSharedStateReport):
            reports.append(item)
        else:
            reports.append(InterwovenSharedStateReport.from_dict(dict(item)))
    return tuple(reports)


def _coerce_staged_chain_reports(
    payloads: tuple[InterwovenStagedChainReport | Mapping[str, Any], ...] | list[InterwovenStagedChainReport | Mapping[str, Any]] | None,
) -> tuple[InterwovenStagedChainReport, ...]:
    if isinstance(payloads, (InterwovenStagedChainReport, Mapping)):
        payloads = (payloads,)
    reports: list[InterwovenStagedChainReport] = []
    for item in tuple(payloads or ()):
        if isinstance(item, InterwovenStagedChainReport):
            reports.append(item)
        else:
            reports.append(InterwovenStagedChainReport.from_dict(dict(item)))
    return tuple(reports)


def _preview(values: list[str], *, limit: int) -> list[str]:
    return values[: max(limit, 1)]


@dataclass(frozen=True)
class InterwovenStressScenario:
    label: str
    producer_consumer_reports: tuple[InterwovenProducerConsumerReport | Mapping[str, Any], ...] = ()
    shared_state_reports: tuple[InterwovenSharedStateReport | Mapping[str, Any], ...] = ()
    staged_chain_reports: tuple[InterwovenStagedChainReport | Mapping[str, Any], ...] = ()
    expected_proof_status: str = "pass"
    expected_competing_producer_count_min: int = 0
    expected_ambiguous_shared_state_count_min: int = 0
    expected_overlapping_chain_count_min: int = 0
    expected_stale_or_forked_state_count_min: int = 0
    max_preview_items: int = 3

    def __post_init__(self) -> None:
        label = str(self.label or "").strip()
        if not label:
            raise ValueError("label must be non-empty")
        expected_proof_status = str(self.expected_proof_status or "").strip().lower()
        if expected_proof_status not in _EXPECTED_PROOF_STATUSES:
            raise ValueError("expected_proof_status must be pass or fail")
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "expected_proof_status", expected_proof_status)
        object.__setattr__(self, "producer_consumer_reports", _coerce_producer_consumer_reports(self.producer_consumer_reports))
        object.__setattr__(self, "shared_state_reports", _coerce_shared_state_reports(self.shared_state_reports))
        object.__setattr__(self, "staged_chain_reports", _coerce_staged_chain_reports(self.staged_chain_reports))
        if self.max_preview_items < 1:
            raise ValueError("max_preview_items must be at least 1")


def _producer_family_sources(report: InterwovenProducerConsumerReport) -> tuple[str, ...]:
    return tuple(report.evidence_edges)


def _shared_state_sources(report: InterwovenSharedStateReport) -> tuple[str, ...]:
    return tuple(report.exporting_seams + report.importing_seams)


def _staged_chain_sources(report: InterwovenStagedChainReport) -> tuple[str, ...]:
    return tuple(report.ordered_steps)


def _competing_producer_families(
    reports: tuple[InterwovenProducerConsumerReport, ...],
) -> list[dict[str, Any]]:
    by_consumer: dict[tuple[str, str], list[InterwovenProducerConsumerReport]] = defaultdict(list)
    for report in reports:
        by_consumer[(report.family, report.consumer_id)].append(report)
    families: list[dict[str, Any]] = []
    for (family, consumer_id), family_reports in by_consumer.items():
        producer_ids = {item.producer_id for item in family_reports}
        if len(producer_ids) <= 1:
            continue
        ambiguity_visible = any(
            item.contradiction_state in _CONTRADICTION_VISIBLE_STATES or item.observer_verdict in _FAIL_OR_WARN
            for item in family_reports
        )
        families.append(
            {
                "family": family,
                "consumer_id": consumer_id,
                "producer_ids": sorted(producer_ids),
                "ambiguity_visible": ambiguity_visible,
            }
        )
    return families


def _ambiguous_shared_state_rows(
    reports: tuple[InterwovenSharedStateReport, ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        is_ambiguous = (
            report.contradiction_state in _CONTRADICTION_VISIBLE_STATES
            or report.staleness_risk in {"medium", "high", "critical"}
            or report.observer_verdict in _FAIL_OR_WARN
        )
        if not is_ambiguous:
            continue
        rows.append(
            {
                "carrier_id": report.carrier_id,
                "staleness_risk": report.staleness_risk,
                "ambiguity_visible": (
                    report.contradiction_state in _CONTRADICTION_VISIBLE_STATES
                    or report.observer_verdict in _FAIL_OR_WARN
                ),
            }
        )
    return rows


def _overlapping_chain_rows(
    reports: tuple[InterwovenStagedChainReport, ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for left, right in combinations(reports, 2):
        overlapping_steps = sorted(set(left.ordered_steps).intersection(right.ordered_steps))
        overlapping_tokens = sorted(set(left.required_state_tokens).intersection(right.required_state_tokens))
        if not overlapping_steps and not overlapping_tokens:
            continue
        ambiguity_visible = any(
            candidate.contradiction_state in _CONTRADICTION_VISIBLE_STATES or candidate.observer_verdict in _FAIL_OR_WARN
            for candidate in (left, right)
        )
        rows.append(
            {
                "chain_ids": [left.chain_id, right.chain_id],
                "overlapping_steps": overlapping_steps,
                "overlapping_tokens": overlapping_tokens,
                "ambiguity_visible": ambiguity_visible,
            }
        )
    return rows


def _stale_or_forked_rows(
    reports: tuple[InterwovenSharedStateReport, ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        if report.staleness_risk not in {"high", "critical"}:
            continue
        rows.append(
            {
                "carrier_id": report.carrier_id,
                "staleness_risk": report.staleness_risk,
                "ambiguity_visible": (
                    report.contradiction_state in _CONTRADICTION_VISIBLE_STATES
                    or report.observer_verdict in _FAIL_OR_WARN
                ),
            }
        )
    return rows


def _check_minimum(actual: int, minimum: int) -> dict[str, Any]:
    return {"ok": actual >= minimum, "actual": actual, "minimum": minimum}


def _build_scenario_report(scenario: InterwovenStressScenario) -> dict[str, Any]:
    producer_reports = tuple(scenario.producer_consumer_reports)
    shared_reports = tuple(scenario.shared_state_reports)
    chain_reports = tuple(scenario.staged_chain_reports)

    producer_observers = tuple(
        build_producer_consumer_plausibility_observer(report, canonical_sources=_producer_family_sources(report))
        for report in producer_reports
    )
    shared_reuse_observers = tuple(
        build_shared_state_reuse_plausibility_observer(report, canonical_sources=_shared_state_sources(report))
        for report in shared_reports
    )
    shared_staleness_observers = tuple(
        build_interwoven_state_staleness_risk_observer(report, canonical_sources=_shared_state_sources(report))
        for report in shared_reports
    )
    chain_observers = tuple(
        build_staged_chain_ordering_plausibility_observer(report, canonical_sources=_staged_chain_sources(report))
        for report in chain_reports
    )

    report_contradictions = sum(
        1
        for report in producer_reports + shared_reports + chain_reports
        if report.contradiction_state in _CONTRADICTION_VISIBLE_STATES
    )
    observer_verdict_counts = Counter(
        observer["verdict"]
        for observer in producer_observers + shared_reuse_observers + shared_staleness_observers + chain_observers
    )

    competing_producers = _competing_producer_families(producer_reports)
    ambiguous_shared_state = _ambiguous_shared_state_rows(shared_reports)
    overlapping_chains = _overlapping_chain_rows(chain_reports)
    stale_or_forked = _stale_or_forked_rows(shared_reports)

    ambiguity_visibility_ok = all(row["ambiguity_visible"] for row in competing_producers)
    ambiguity_visibility_ok = ambiguity_visibility_ok and all(row["ambiguity_visible"] for row in ambiguous_shared_state)
    ambiguity_visibility_ok = ambiguity_visibility_ok and all(row["ambiguity_visible"] for row in overlapping_chains)
    ambiguity_visibility_ok = ambiguity_visibility_ok and all(row["ambiguity_visible"] for row in stale_or_forked)

    preview_limit = scenario.max_preview_items
    contradiction_subjects = _preview(
        [
            *(f"producer:{report.family}" for report in producer_reports if report.contradiction_state in _CONTRADICTION_VISIBLE_STATES),
            *(f"shared:{report.carrier_id}" for report in shared_reports if report.contradiction_state in _CONTRADICTION_VISIBLE_STATES),
            *(f"chain:{report.chain_id}" for report in chain_reports if report.contradiction_state in _CONTRADICTION_VISIBLE_STATES),
        ],
        limit=preview_limit,
    )
    bounded_readability = (
        len(contradiction_subjects) <= preview_limit
        and len(_preview([row["family"] for row in competing_producers], limit=preview_limit)) <= preview_limit
        and len(_preview([row["carrier_id"] for row in ambiguous_shared_state], limit=preview_limit)) <= preview_limit
        and len(_preview([",".join(row["chain_ids"]) for row in overlapping_chains], limit=preview_limit)) <= preview_limit
    )
    proof_status = "pass" if ambiguity_visibility_ok and bounded_readability else "fail"

    return {
        "label": scenario.label,
        "proof_summary": {
            "proof_status": proof_status,
            "ambiguity_visibility_ok": ambiguity_visibility_ok,
            "bounded_readability": bounded_readability,
            "contradiction_count": report_contradictions,
        },
        "artifact_counts": {
            "producer_consumer_reports": len(producer_reports),
            "shared_state_reports": len(shared_reports),
            "staged_chain_reports": len(chain_reports),
        },
        "observer_verdict_counts": dict(observer_verdict_counts),
        "competing_producer_count": len(competing_producers),
        "ambiguous_shared_state_count": len(ambiguous_shared_state),
        "overlapping_chain_count": len(overlapping_chains),
        "stale_or_forked_state_count": len(stale_or_forked),
        "checks": {
            "competing_producer_count_min": _check_minimum(
                len(competing_producers),
                scenario.expected_competing_producer_count_min,
            ),
            "ambiguous_shared_state_count_min": _check_minimum(
                len(ambiguous_shared_state),
                scenario.expected_ambiguous_shared_state_count_min,
            ),
            "overlapping_chain_count_min": _check_minimum(
                len(overlapping_chains),
                scenario.expected_overlapping_chain_count_min,
            ),
            "stale_or_forked_state_count_min": _check_minimum(
                len(stale_or_forked),
                scenario.expected_stale_or_forked_state_count_min,
            ),
            "expected_proof_status": {
                "ok": proof_status == scenario.expected_proof_status,
                "actual": proof_status,
                "expected": scenario.expected_proof_status,
            },
        },
        "contradiction_subjects_preview": contradiction_subjects,
        "competing_producer_families_preview": _preview(
            [row["family"] for row in competing_producers],
            limit=preview_limit,
        ),
        "ambiguous_shared_state_preview": _preview(
            [row["carrier_id"] for row in ambiguous_shared_state],
            limit=preview_limit,
        ),
        "overlapping_chains_preview": _preview(
            [",".join(row["chain_ids"]) for row in overlapping_chains],
            limit=preview_limit,
        ),
    }


def run_interwoven_stress_proof(
    *,
    scenarios: tuple[InterwovenStressScenario, ...] | list[InterwovenStressScenario],
) -> dict[str, Any]:
    normalized = tuple(scenarios)
    scenario_reports = tuple(_build_scenario_report(scenario) for scenario in normalized)
    suite_status = "pass"
    for report in scenario_reports:
        checks = report["checks"]
        if not all(check["ok"] for check in checks.values()):
            suite_status = "fail"
            break
    return {
        "status": suite_status,
        "scenario_reports": list(scenario_reports),
    }
