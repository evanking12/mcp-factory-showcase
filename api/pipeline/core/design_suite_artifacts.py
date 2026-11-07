from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from api.pipeline.core.decomposition_contract import normalize_contradiction_state
from api.pipeline.core.interwoven_artifacts import (
    InterwovenProducerConsumerReport,
    InterwovenSharedStateReport,
)


DESIGN_SUITE_ARTIFACT_SCHEMA_VERSION = "1.0.0"

NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT = "northstar-producer-consumer-report.json"
NORTHSTAR_SHARED_STATE_ARTIFACT = "northstar-shared-state-report.json"
NORTHSTAR_FAMILY_BLOCKER_ARTIFACT = "northstar-family-blocker-report.json"
NORTHSTAR_OBSERVER_SUMMARY_ARTIFACT = "northstar-interwoven-observer-summary.json"
NORTHSTAR_EXPECTED_OBSERVED_ARTIFACT = "northstar-expected-observed-report.json"

NORTHSTAR_CANONICAL_ARTIFACTS = (
    NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT,
    NORTHSTAR_SHARED_STATE_ARTIFACT,
    NORTHSTAR_FAMILY_BLOCKER_ARTIFACT,
    NORTHSTAR_EXPECTED_OBSERVED_ARTIFACT,
)

NORTHSTAR_SUMMARY_ONLY_ARTIFACTS = (
    NORTHSTAR_OBSERVER_SUMMARY_ARTIFACT,
)

DEFAULT_NORTHSTAR_ARTIFACT_PLACEMENT = {
    "canonical_scope": "session_only",
    "campaign_projection": False,
    "ledger_projection": False,
    "collector_projection": False,
}


def _normalized_tuple(values: tuple[str, ...] | list[str] | None, *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(str(value or "").strip() for value in tuple(values or ()) if str(value or "").strip())
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _normalized_optional_tuple(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return tuple(str(value or "").strip() for value in tuple(values or ()) if str(value or "").strip())


def _normalize_confidence(value: float | int | None) -> float:
    if value is None:
        return 0.0
    candidate = float(value)
    if candidate < 0.0 or candidate > 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")
    return candidate


@dataclass(frozen=True)
class NorthstarProducerConsumerReport:
    family: str
    blocker_family: str
    producer_module: str
    producer_step: str
    consumer_module: str
    consumer_step: str
    state_tokens: tuple[str, ...]
    evidence_edges: tuple[str, ...]
    dependency_mode: str
    confidence: float
    contradiction_state: str = "none"
    artifact_type: str = NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT
    contract_version: str = DESIGN_SUITE_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        family = str(self.family or "").strip()
        blocker_family = str(self.blocker_family or "").strip().lower()
        producer_module = str(self.producer_module or "").strip()
        producer_step = str(self.producer_step or "").strip()
        consumer_module = str(self.consumer_module or "").strip()
        consumer_step = str(self.consumer_step or "").strip()
        dependency_mode = str(self.dependency_mode or "").strip().lower()
        if not family or not blocker_family:
            raise ValueError("family and blocker_family must be non-empty")
        if not producer_module or not producer_step or not consumer_module or not consumer_step:
            raise ValueError("producer/consumer modules and steps must be non-empty")
        if dependency_mode not in {"direct", "shared_state_mediated", "staged"}:
            raise ValueError("dependency_mode must be direct, shared_state_mediated, or staged")
        object.__setattr__(self, "family", family)
        object.__setattr__(self, "blocker_family", blocker_family)
        object.__setattr__(self, "producer_module", producer_module)
        object.__setattr__(self, "producer_step", producer_step)
        object.__setattr__(self, "consumer_module", consumer_module)
        object.__setattr__(self, "consumer_step", consumer_step)
        object.__setattr__(self, "state_tokens", _normalized_tuple(self.state_tokens, field_name="state_tokens"))
        object.__setattr__(self, "evidence_edges", _normalized_tuple(self.evidence_edges, field_name="evidence_edges"))
        object.__setattr__(self, "dependency_mode", dependency_mode)
        object.__setattr__(self, "confidence", _normalize_confidence(self.confidence))
        object.__setattr__(self, "contradiction_state", normalize_contradiction_state(self.contradiction_state))
        if self.artifact_type != NORTHSTAR_PRODUCER_CONSUMER_ARTIFACT:
            raise ValueError("artifact_type mismatch for Northstar producer-consumer report")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_interwoven_report(self) -> InterwovenProducerConsumerReport:
        return InterwovenProducerConsumerReport(
            family=self.family,
            producer_id=f"{self.producer_module}.{self.producer_step}",
            producer_kind="producer",
            consumer_id=f"{self.consumer_module}.{self.consumer_step}",
            consumer_kind="consumer",
            state_tokens=self.state_tokens,
            evidence_edges=self.evidence_edges,
            dependency_mode=self.dependency_mode,
            confidence=self.confidence,
            contradiction_state=self.contradiction_state,
        )


@dataclass(frozen=True)
class NorthstarSharedStateReport:
    carrier_id: str
    carrier_kind: str
    state_tokens: tuple[str, ...]
    downstream_consumers: tuple[str, ...]
    exporting_seams: tuple[str, ...]
    importing_seams: tuple[str, ...]
    staleness_risk: str
    confidence: float
    contradiction_state: str = "none"
    artifact_type: str = NORTHSTAR_SHARED_STATE_ARTIFACT
    contract_version: str = DESIGN_SUITE_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        carrier_id = str(self.carrier_id or "").strip()
        carrier_kind = str(self.carrier_kind or "").strip()
        staleness_risk = str(self.staleness_risk or "").strip().lower()
        if not carrier_id or not carrier_kind:
            raise ValueError("carrier_id and carrier_kind must be non-empty")
        if staleness_risk not in {"low", "medium", "high", "critical"}:
            raise ValueError("staleness_risk must be low, medium, high, or critical")
        object.__setattr__(self, "carrier_id", carrier_id)
        object.__setattr__(self, "carrier_kind", carrier_kind)
        object.__setattr__(self, "state_tokens", _normalized_tuple(self.state_tokens, field_name="state_tokens"))
        object.__setattr__(self, "downstream_consumers", _normalized_tuple(self.downstream_consumers, field_name="downstream_consumers"))
        object.__setattr__(self, "exporting_seams", _normalized_tuple(self.exporting_seams, field_name="exporting_seams"))
        object.__setattr__(self, "importing_seams", _normalized_tuple(self.importing_seams, field_name="importing_seams"))
        object.__setattr__(self, "staleness_risk", staleness_risk)
        object.__setattr__(self, "confidence", _normalize_confidence(self.confidence))
        object.__setattr__(self, "contradiction_state", normalize_contradiction_state(self.contradiction_state))
        if self.artifact_type != NORTHSTAR_SHARED_STATE_ARTIFACT:
            raise ValueError("artifact_type mismatch for Northstar shared-state report")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_interwoven_report(self) -> InterwovenSharedStateReport:
        return InterwovenSharedStateReport(
            carrier_id=self.carrier_id,
            carrier_kind=self.carrier_kind,
            state_tokens=self.state_tokens,
            downstream_consumers=self.downstream_consumers,
            exporting_seams=self.exporting_seams,
            importing_seams=self.importing_seams,
            staleness_risk=self.staleness_risk,
            confidence=self.confidence,
            contradiction_state=self.contradiction_state,
        )


@dataclass(frozen=True)
class NorthstarFamilyBlockerReport:
    blocker_family: str
    subjects: tuple[str, ...]
    upstream_requirements: tuple[str, ...]
    shared_state_carriers: tuple[str, ...]
    failure_or_pressure_sites: tuple[str, ...]
    contradiction_state: str
    explanation: str
    confidence: float
    provisional_subjects: tuple[str, ...] = ()
    confirmation_sites: tuple[str, ...] = ()
    lineage_branches: tuple[str, ...] = ()
    accepted_branch: str = ""
    rejected_branches: tuple[str, ...] = ()
    artifact_type: str = NORTHSTAR_FAMILY_BLOCKER_ARTIFACT
    contract_version: str = DESIGN_SUITE_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        blocker_family = str(self.blocker_family or "").strip().lower()
        explanation = str(self.explanation or "").strip()
        if not blocker_family:
            raise ValueError("blocker_family must be non-empty")
        if not explanation:
            raise ValueError("explanation must be non-empty")
        object.__setattr__(self, "blocker_family", blocker_family)
        object.__setattr__(self, "subjects", _normalized_tuple(self.subjects, field_name="subjects"))
        object.__setattr__(self, "upstream_requirements", _normalized_tuple(self.upstream_requirements, field_name="upstream_requirements"))
        object.__setattr__(self, "shared_state_carriers", _normalized_tuple(self.shared_state_carriers, field_name="shared_state_carriers"))
        object.__setattr__(self, "failure_or_pressure_sites", _normalized_tuple(self.failure_or_pressure_sites, field_name="failure_or_pressure_sites"))
        object.__setattr__(self, "provisional_subjects", _normalized_optional_tuple(self.provisional_subjects))
        object.__setattr__(self, "confirmation_sites", _normalized_optional_tuple(self.confirmation_sites))
        object.__setattr__(self, "lineage_branches", _normalized_optional_tuple(self.lineage_branches))
        object.__setattr__(self, "accepted_branch", str(self.accepted_branch or "").strip())
        object.__setattr__(self, "rejected_branches", _normalized_optional_tuple(self.rejected_branches))
        object.__setattr__(self, "contradiction_state", normalize_contradiction_state(self.contradiction_state))
        object.__setattr__(self, "explanation", explanation)
        object.__setattr__(self, "confidence", _normalize_confidence(self.confidence))
        if self.accepted_branch and self.lineage_branches and self.accepted_branch not in self.lineage_branches:
            raise ValueError("accepted_branch must be one of lineage_branches when lineage branches are present")
        if self.rejected_branches and self.lineage_branches and not set(self.rejected_branches).issubset(set(self.lineage_branches)):
            raise ValueError("rejected_branches must be a subset of lineage_branches")
        if self.artifact_type != NORTHSTAR_FAMILY_BLOCKER_ARTIFACT:
            raise ValueError("artifact_type mismatch for Northstar family blocker report")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
