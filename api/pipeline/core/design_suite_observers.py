from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from api.pipeline.core.decomposition_contract import normalize_contradiction_state


DESIGN_SUITE_OBSERVER_SCHEMA_VERSION = "1.0.0"

DESIGN_SUITE_OBSERVER_NAMES = (
    "family_blocker_plausibility",
    "shared_state_carrier_plausibility",
    "forked_state_visibility",
    "late_confirmation_visibility",
)


def _normalize_status(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate not in {"pass", "warn", "fail"}:
        raise ValueError("status must be pass, warn, or fail")
    return candidate


def _normalize_confidence(value: float | int | None) -> float:
    if value is None:
        return 0.0
    candidate = float(value)
    if candidate < 0.0 or candidate > 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")
    return candidate


def _normalized_tuple(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return tuple(str(value or "").strip() for value in tuple(values or ()) if str(value or "").strip())


@dataclass(frozen=True)
class DesignSuiteObserverSummary:
    observer_name: str
    subject_ids: tuple[str, ...]
    blocker_family: str
    status: str
    contradiction_state: str
    expected_behavior: str
    observed_behavior: str
    explanation: str
    review_notes: tuple[str, ...]
    canonical_sources: tuple[str, ...]
    confidence: float = 0.0
    schema_version: str = DESIGN_SUITE_OBSERVER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        observer_name = str(self.observer_name or "").strip().lower()
        blocker_family = str(self.blocker_family or "").strip().lower()
        expected_behavior = str(self.expected_behavior or "").strip()
        observed_behavior = str(self.observed_behavior or "").strip()
        explanation = str(self.explanation or "").strip()
        if observer_name not in DESIGN_SUITE_OBSERVER_NAMES:
            raise ValueError(f"unknown design-suite observer: {self.observer_name!r}")
        if not blocker_family:
            raise ValueError("blocker_family must be non-empty")
        if not expected_behavior or not observed_behavior or not explanation:
            raise ValueError("expected_behavior, observed_behavior, and explanation must be non-empty")
        object.__setattr__(self, "observer_name", observer_name)
        object.__setattr__(self, "subject_ids", _normalized_tuple(self.subject_ids))
        object.__setattr__(self, "blocker_family", blocker_family)
        object.__setattr__(self, "status", _normalize_status(self.status))
        object.__setattr__(self, "contradiction_state", normalize_contradiction_state(self.contradiction_state))
        object.__setattr__(self, "expected_behavior", expected_behavior)
        object.__setattr__(self, "observed_behavior", observed_behavior)
        object.__setattr__(self, "explanation", explanation)
        object.__setattr__(self, "review_notes", _normalized_tuple(self.review_notes))
        object.__setattr__(self, "canonical_sources", _normalized_tuple(self.canonical_sources))
        object.__setattr__(self, "confidence", _normalize_confidence(self.confidence))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_family_blocker_plausibility_observer(
    *,
    subject_ids: tuple[str, ...] | list[str],
    blocker_family: str,
    contradiction_state: str,
    expected_behavior: str,
    observed_behavior: str,
    confidence: float,
    canonical_sources: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    contradiction = normalize_contradiction_state(contradiction_state)
    status = "pass"
    explanation = "The shared blocker explanation remained bounded and attributable."
    notes: list[str] = ["family_blocker_bounded"]
    if contradiction in {"tentative", "superseded"} or confidence < 0.75:
        status = "warn"
        notes.append("family_blocker_needs_more_evidence")
    if contradiction in {"blocked", "contradicted", "quarantined"}:
        status = "fail"
        explanation = "The blocker family remained too contradictory to trust as a bounded explanation."
        notes.append("family_blocker_contradicted")
    return DesignSuiteObserverSummary(
        observer_name="family_blocker_plausibility",
        subject_ids=tuple(subject_ids),
        blocker_family=blocker_family,
        status=status,
        contradiction_state=contradiction,
        expected_behavior=expected_behavior,
        observed_behavior=observed_behavior,
        explanation=explanation,
        review_notes=tuple(notes),
        canonical_sources=tuple(canonical_sources),
        confidence=confidence,
    ).to_dict()


def build_shared_state_carrier_plausibility_observer(
    *,
    subject_ids: tuple[str, ...] | list[str],
    blocker_family: str,
    contradiction_state: str,
    expected_behavior: str,
    observed_behavior: str,
    confidence: float,
    canonical_sources: tuple[str, ...] | list[str],
    downstream_consumer_count: int,
) -> dict[str, Any]:
    contradiction = normalize_contradiction_state(contradiction_state)
    status = "pass"
    explanation = "The shared-state carrier remained explicit across more than one consumer."
    notes: list[str] = ["shared_state_reuse_visible"]
    if downstream_consumer_count < 2:
        status = "warn"
        notes.append("shared_state_not_yet_reused_across_multiple_consumers")
    if contradiction in {"tentative", "superseded"} or confidence < 0.75:
        status = "warn"
        notes.append("shared_state_needs_more_evidence")
    if contradiction in {"blocked", "contradicted", "quarantined"}:
        status = "fail"
        explanation = "The shared-state carrier was too contradictory to trust for family-level planning."
        notes.append("shared_state_contradicted")
    return DesignSuiteObserverSummary(
        observer_name="shared_state_carrier_plausibility",
        subject_ids=tuple(subject_ids),
        blocker_family=blocker_family,
        status=status,
        contradiction_state=contradiction,
        expected_behavior=expected_behavior,
        observed_behavior=observed_behavior,
        explanation=explanation,
        review_notes=tuple(notes),
        canonical_sources=tuple(canonical_sources),
        confidence=confidence,
    ).to_dict()


def build_late_confirmation_visibility_observer(
    *,
    subject_ids: tuple[str, ...] | list[str],
    blocker_family: str,
    contradiction_state: str,
    expected_behavior: str,
    observed_behavior: str,
    confidence: float,
    canonical_sources: tuple[str, ...] | list[str],
    provisional_subject_count: int,
    confirmation_site_count: int,
) -> dict[str, Any]:
    contradiction = normalize_contradiction_state(contradiction_state)
    status = "pass"
    explanation = "Late confirmation remained explicit and preserved downstream uncertainty."
    notes: list[str] = ["late_confirmation_visible"]
    if provisional_subject_count < 1 or confirmation_site_count < 1:
        status = "warn"
        notes.append("late_confirmation_structure_incomplete")
    if contradiction in {"tentative", "superseded"} or confidence < 0.78:
        status = "warn"
        notes.append("late_confirmation_needs_more_evidence")
    if contradiction in {"blocked", "contradicted", "quarantined"}:
        status = "fail"
        explanation = "Late confirmation remained too contradictory to trust as a downstream confirmation surface."
        notes.append("late_confirmation_contradicted")
    return DesignSuiteObserverSummary(
        observer_name="late_confirmation_visibility",
        subject_ids=tuple(subject_ids),
        blocker_family=blocker_family,
        status=status,
        contradiction_state=contradiction,
        expected_behavior=expected_behavior,
        observed_behavior=observed_behavior,
        explanation=explanation,
        review_notes=tuple(notes),
        canonical_sources=tuple(canonical_sources),
        confidence=confidence,
    ).to_dict()


def build_forked_state_visibility_observer(
    *,
    subject_ids: tuple[str, ...] | list[str],
    blocker_family: str,
    contradiction_state: str,
    expected_behavior: str,
    observed_behavior: str,
    confidence: float,
    canonical_sources: tuple[str, ...] | list[str],
    lineage_branch_count: int,
    accepted_branch_present: bool,
    rejected_branch_count: int,
) -> dict[str, Any]:
    contradiction = normalize_contradiction_state(contradiction_state)
    status = "pass"
    explanation = "Forked-state lineage remained explicit and one accepted branch stayed distinct from rejected lookalike branches."
    notes: list[str] = ["forked_state_visible"]
    if lineage_branch_count < 2 or not accepted_branch_present or rejected_branch_count < 1:
        status = "warn"
        notes.append("forked_state_structure_incomplete")
    if contradiction in {"tentative", "superseded"} or confidence < 0.78:
        status = "warn"
        notes.append("forked_state_needs_more_evidence")
    if contradiction in {"blocked", "contradicted", "quarantined"}:
        status = "fail"
        explanation = "Forked-state lineage remained too contradictory to trust as a branch-selection surface."
        notes.append("forked_state_contradicted")
    return DesignSuiteObserverSummary(
        observer_name="forked_state_visibility",
        subject_ids=tuple(subject_ids),
        blocker_family=blocker_family,
        status=status,
        contradiction_state=contradiction,
        expected_behavior=expected_behavior,
        observed_behavior=observed_behavior,
        explanation=explanation,
        review_notes=tuple(notes),
        canonical_sources=tuple(canonical_sources),
        confidence=confidence,
    ).to_dict()
