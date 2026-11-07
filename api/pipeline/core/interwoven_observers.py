from __future__ import annotations

from api.pipeline.core.interwoven_artifacts import (
    InterwovenObserverSummary,
    InterwovenProducerConsumerReport,
    InterwovenSharedStateReport,
    InterwovenStagedChainReport,
)


INTERWOVEN_OBSERVER_NAMES = (
    "producer_consumer_plausibility",
    "shared_state_reuse_plausibility",
    "staged_chain_ordering_plausibility",
    "interwoven_state_staleness_risk",
)


def _normalized_sources(canonical_sources: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return tuple(str(item or "").strip() for item in tuple(canonical_sources or ()) if str(item or "").strip())


def build_producer_consumer_plausibility_observer(
    report: InterwovenProducerConsumerReport,
    *,
    canonical_sources: tuple[str, ...] | list[str],
) -> dict[str, object]:
    reasons: list[str] = ["producer_consumer_edge_present"]
    blocking_risks: list[str] = []
    verdict = "pass"
    if report.contradiction_state in {"blocked", "contradicted", "quarantined"}:
        verdict = "fail"
        blocking_risks.append("contradiction_state_blocks_consumer_admission")
    elif report.contradiction_state in {"tentative", "superseded"} or report.confidence < 0.75:
        verdict = "warn"
        reasons.append("producer_consumer_edge_needs_more_evidence")
    if report.dependency_mode == "staged":
        reasons.append("edge_looks_order_sensitive")
    summary = InterwovenObserverSummary(
        subject_id=report.family,
        subject_kind="producer_consumer",
        observer_name="producer_consumer_plausibility",
        verdict=verdict,
        reasons=tuple(reasons),
        blocking_risks=tuple(blocking_risks),
        confidence=report.confidence,
        contradiction_state=report.contradiction_state,
        canonical_sources=_normalized_sources(canonical_sources),
    )
    return summary.to_dict()


def build_shared_state_reuse_plausibility_observer(
    report: InterwovenSharedStateReport,
    *,
    canonical_sources: tuple[str, ...] | list[str],
) -> dict[str, object]:
    reasons: list[str] = ["shared_state_reused_across_boundaries"]
    blocking_risks: list[str] = []
    verdict = "pass"
    if len(report.downstream_consumers) < 2:
        verdict = "warn"
        reasons.append("shared_state_has_only_one_confirmed_consumer")
    if report.contradiction_state in {"blocked", "contradicted", "quarantined"}:
        verdict = "fail"
        blocking_risks.append("shared_state_contradiction_blocks_reuse")
    elif report.confidence < 0.75 and verdict == "pass":
        verdict = "warn"
        reasons.append("shared_state_reuse_confidence_not_yet_strong")
    summary = InterwovenObserverSummary(
        subject_id=report.carrier_id,
        subject_kind="shared_state",
        observer_name="shared_state_reuse_plausibility",
        verdict=verdict,
        reasons=tuple(reasons),
        blocking_risks=tuple(blocking_risks),
        confidence=report.confidence,
        contradiction_state=report.contradiction_state,
        canonical_sources=_normalized_sources(canonical_sources),
    )
    return summary.to_dict()


def build_interwoven_state_staleness_risk_observer(
    report: InterwovenSharedStateReport,
    *,
    canonical_sources: tuple[str, ...] | list[str],
) -> dict[str, object]:
    reasons: list[str] = []
    blocking_risks: list[str] = []
    if report.staleness_risk == "low":
        verdict = "pass"
        reasons.append("shared_state_staleness_risk_low")
    elif report.staleness_risk == "medium":
        verdict = "warn"
        reasons.append("shared_state_staleness_risk_medium")
    else:
        verdict = "fail"
        reasons.append("shared_state_staleness_risk_high")
        blocking_risks.append("state_reuse_may_be_stale_or_forked")
    summary = InterwovenObserverSummary(
        subject_id=report.carrier_id,
        subject_kind="shared_state",
        observer_name="interwoven_state_staleness_risk",
        verdict=verdict,
        reasons=tuple(reasons),
        blocking_risks=tuple(blocking_risks),
        confidence=report.confidence,
        contradiction_state=report.contradiction_state,
        canonical_sources=_normalized_sources(canonical_sources),
    )
    return summary.to_dict()


def build_staged_chain_ordering_plausibility_observer(
    report: InterwovenStagedChainReport,
    *,
    canonical_sources: tuple[str, ...] | list[str],
) -> dict[str, object]:
    reasons: list[str] = ["ordered_dependency_chain_present"]
    blocking_risks: list[str] = []
    verdict = "pass"
    if report.contradiction_state in {"blocked", "contradicted", "quarantined"}:
        verdict = "fail"
        blocking_risks.append("staged_chain_contradiction_blocks_reuse")
    elif report.blocking_step or report.confidence < 0.75:
        verdict = "warn"
        reasons.append("chain_ordering_needs_more_evidence")
    if len(report.ordered_steps) <= len(report.producer_steps):
        verdict = "fail"
        blocking_risks.append("chain_does_not_extend_past_producer_steps")
    summary = InterwovenObserverSummary(
        subject_id=report.chain_id,
        subject_kind="staged_chain",
        observer_name="staged_chain_ordering_plausibility",
        verdict=verdict,
        reasons=tuple(reasons),
        blocking_risks=tuple(blocking_risks),
        confidence=report.confidence,
        contradiction_state=report.contradiction_state,
        canonical_sources=_normalized_sources(canonical_sources),
    )
    return summary.to_dict()
