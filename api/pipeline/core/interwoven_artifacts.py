from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from api.pipeline.core.decomposition_contract import normalize_contradiction_state


INTERWOVEN_ARTIFACT_SCHEMA_VERSION = "1.0.0"

PRODUCER_CONSUMER_ARTIFACT = "interwoven-producer-consumer-report.json"
SHARED_STATE_ARTIFACT = "interwoven-shared-state-report.json"
STAGED_CHAIN_ARTIFACT = "interwoven-staged-chain-report.json"
INTERWOVEN_OBSERVER_SUMMARY_ARTIFACT = "interwoven-observer-summary.json"

INTERWOVEN_CANONICAL_ARTIFACTS = (
    PRODUCER_CONSUMER_ARTIFACT,
    SHARED_STATE_ARTIFACT,
    STAGED_CHAIN_ARTIFACT,
)

INTERWOVEN_SUMMARY_ONLY_ARTIFACTS = (
    INTERWOVEN_OBSERVER_SUMMARY_ARTIFACT,
)

DEFAULT_INTERWOVEN_ARTIFACT_PLACEMENT = {
    "canonical_scope": "session_only",
    "campaign_projection": False,
    "ledger_projection": False,
    "collector_projection": False,
}

_ALLOWED_VERDICTS = {"", "pass", "warn", "fail"}


def _normalize_verdict(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate not in _ALLOWED_VERDICTS:
        raise ValueError(f"unsupported observer verdict: {value!r}")
    return candidate


def _normalize_confidence(value: float | int | None) -> float:
    if value is None:
        return 0.0
    candidate = float(value)
    if candidate < 0.0 or candidate > 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")
    return candidate


def _normalized_tuple(values: tuple[str, ...] | list[str] | None, *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(str(value or "").strip() for value in tuple(values or ()) if str(value or "").strip())
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


@dataclass(frozen=True)
class InterwovenProducerConsumerReport:
    family: str
    producer_id: str
    producer_kind: str
    consumer_id: str
    consumer_kind: str
    state_tokens: tuple[str, ...]
    evidence_edges: tuple[str, ...]
    dependency_mode: str
    confidence: float
    contradiction_state: str = "none"
    observer_verdict: str = ""
    artifact_type: str = PRODUCER_CONSUMER_ARTIFACT
    contract_version: str = INTERWOVEN_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        family = str(self.family or "").strip()
        producer_id = str(self.producer_id or "").strip()
        producer_kind = str(self.producer_kind or "").strip()
        consumer_id = str(self.consumer_id or "").strip()
        consumer_kind = str(self.consumer_kind or "").strip()
        dependency_mode = str(self.dependency_mode or "").strip().lower()
        if not family:
            raise ValueError("family must be non-empty")
        if not producer_id or not producer_kind:
            raise ValueError("producer_id and producer_kind must be non-empty")
        if not consumer_id or not consumer_kind:
            raise ValueError("consumer_id and consumer_kind must be non-empty")
        if dependency_mode not in {"direct", "shared_state_mediated", "staged"}:
            raise ValueError("dependency_mode must be direct, shared_state_mediated, or staged")
        object.__setattr__(self, "family", family)
        object.__setattr__(self, "producer_id", producer_id)
        object.__setattr__(self, "producer_kind", producer_kind)
        object.__setattr__(self, "consumer_id", consumer_id)
        object.__setattr__(self, "consumer_kind", consumer_kind)
        object.__setattr__(self, "state_tokens", _normalized_tuple(self.state_tokens, field_name="state_tokens"))
        object.__setattr__(self, "evidence_edges", _normalized_tuple(self.evidence_edges, field_name="evidence_edges"))
        object.__setattr__(self, "dependency_mode", dependency_mode)
        object.__setattr__(self, "confidence", _normalize_confidence(self.confidence))
        object.__setattr__(self, "contradiction_state", normalize_contradiction_state(self.contradiction_state))
        object.__setattr__(self, "observer_verdict", _normalize_verdict(self.observer_verdict))
        if self.artifact_type != PRODUCER_CONSUMER_ARTIFACT:
            raise ValueError("artifact_type mismatch for producer-consumer report")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InterwovenProducerConsumerReport":
        return cls(
            family=payload.get("family", ""),
            producer_id=payload.get("producer_id", ""),
            producer_kind=payload.get("producer_kind", ""),
            consumer_id=payload.get("consumer_id", ""),
            consumer_kind=payload.get("consumer_kind", ""),
            state_tokens=tuple(payload.get("state_tokens") or ()),
            evidence_edges=tuple(payload.get("evidence_edges") or ()),
            dependency_mode=payload.get("dependency_mode", ""),
            confidence=payload.get("confidence", 0.0),
            contradiction_state=payload.get("contradiction_state", "none"),
            observer_verdict=payload.get("observer_verdict", ""),
            artifact_type=payload.get("artifact_type", PRODUCER_CONSUMER_ARTIFACT),
            contract_version=payload.get("contract_version", INTERWOVEN_ARTIFACT_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class InterwovenSharedStateReport:
    carrier_id: str
    carrier_kind: str
    state_tokens: tuple[str, ...]
    downstream_consumers: tuple[str, ...]
    exporting_seams: tuple[str, ...]
    importing_seams: tuple[str, ...]
    staleness_risk: str
    confidence: float
    contradiction_state: str = "none"
    observer_verdict: str = ""
    artifact_type: str = SHARED_STATE_ARTIFACT
    contract_version: str = INTERWOVEN_ARTIFACT_SCHEMA_VERSION

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
        object.__setattr__(
            self,
            "downstream_consumers",
            _normalized_tuple(self.downstream_consumers, field_name="downstream_consumers"),
        )
        object.__setattr__(self, "exporting_seams", _normalized_tuple(self.exporting_seams, field_name="exporting_seams"))
        object.__setattr__(self, "importing_seams", _normalized_tuple(self.importing_seams, field_name="importing_seams"))
        object.__setattr__(self, "staleness_risk", staleness_risk)
        object.__setattr__(self, "confidence", _normalize_confidence(self.confidence))
        object.__setattr__(self, "contradiction_state", normalize_contradiction_state(self.contradiction_state))
        object.__setattr__(self, "observer_verdict", _normalize_verdict(self.observer_verdict))
        if self.artifact_type != SHARED_STATE_ARTIFACT:
            raise ValueError("artifact_type mismatch for shared-state report")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InterwovenSharedStateReport":
        return cls(
            carrier_id=payload.get("carrier_id", ""),
            carrier_kind=payload.get("carrier_kind", ""),
            state_tokens=tuple(payload.get("state_tokens") or ()),
            downstream_consumers=tuple(payload.get("downstream_consumers") or ()),
            exporting_seams=tuple(payload.get("exporting_seams") or ()),
            importing_seams=tuple(payload.get("importing_seams") or ()),
            staleness_risk=payload.get("staleness_risk", "low"),
            confidence=payload.get("confidence", 0.0),
            contradiction_state=payload.get("contradiction_state", "none"),
            observer_verdict=payload.get("observer_verdict", ""),
            artifact_type=payload.get("artifact_type", SHARED_STATE_ARTIFACT),
            contract_version=payload.get("contract_version", INTERWOVEN_ARTIFACT_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class InterwovenStagedChainReport:
    chain_id: str
    ordered_steps: tuple[str, ...]
    required_state_tokens: tuple[str, ...]
    producer_steps: tuple[str, ...]
    consumer_steps: tuple[str, ...]
    blocking_step: str
    confidence: float
    contradiction_state: str = "none"
    observer_verdict: str = ""
    artifact_type: str = STAGED_CHAIN_ARTIFACT
    contract_version: str = INTERWOVEN_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        chain_id = str(self.chain_id or "").strip()
        blocking_step = str(self.blocking_step or "").strip()
        if not chain_id:
            raise ValueError("chain_id must be non-empty")
        object.__setattr__(self, "chain_id", chain_id)
        object.__setattr__(self, "ordered_steps", _normalized_tuple(self.ordered_steps, field_name="ordered_steps"))
        object.__setattr__(
            self,
            "required_state_tokens",
            _normalized_tuple(self.required_state_tokens, field_name="required_state_tokens"),
        )
        object.__setattr__(self, "producer_steps", _normalized_tuple(self.producer_steps, field_name="producer_steps"))
        object.__setattr__(self, "consumer_steps", _normalized_tuple(self.consumer_steps, field_name="consumer_steps"))
        if not set(self.producer_steps).issubset(set(self.ordered_steps)):
            raise ValueError("producer_steps must be a subset of ordered_steps")
        if not set(self.consumer_steps).issubset(set(self.ordered_steps)):
            raise ValueError("consumer_steps must be a subset of ordered_steps")
        if blocking_step and blocking_step not in self.ordered_steps:
            raise ValueError("blocking_step must be empty or a member of ordered_steps")
        object.__setattr__(self, "blocking_step", blocking_step)
        object.__setattr__(self, "confidence", _normalize_confidence(self.confidence))
        object.__setattr__(self, "contradiction_state", normalize_contradiction_state(self.contradiction_state))
        object.__setattr__(self, "observer_verdict", _normalize_verdict(self.observer_verdict))
        if self.artifact_type != STAGED_CHAIN_ARTIFACT:
            raise ValueError("artifact_type mismatch for staged-chain report")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InterwovenStagedChainReport":
        return cls(
            chain_id=payload.get("chain_id", ""),
            ordered_steps=tuple(payload.get("ordered_steps") or ()),
            required_state_tokens=tuple(payload.get("required_state_tokens") or ()),
            producer_steps=tuple(payload.get("producer_steps") or ()),
            consumer_steps=tuple(payload.get("consumer_steps") or ()),
            blocking_step=payload.get("blocking_step", ""),
            confidence=payload.get("confidence", 0.0),
            contradiction_state=payload.get("contradiction_state", "none"),
            observer_verdict=payload.get("observer_verdict", ""),
            artifact_type=payload.get("artifact_type", STAGED_CHAIN_ARTIFACT),
            contract_version=payload.get("contract_version", INTERWOVEN_ARTIFACT_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class InterwovenObserverSummary:
    subject_id: str
    subject_kind: str
    observer_name: str
    verdict: str
    reasons: tuple[str, ...]
    blocking_risks: tuple[str, ...]
    confidence: float
    contradiction_state: str
    canonical_sources: tuple[str, ...]
    artifact_type: str = INTERWOVEN_OBSERVER_SUMMARY_ARTIFACT
    contract_version: str = INTERWOVEN_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        subject_id = str(self.subject_id or "").strip()
        subject_kind = str(self.subject_kind or "").strip()
        observer_name = str(self.observer_name or "").strip().lower()
        verdict = str(self.verdict or "").strip().lower()
        if not subject_id or not subject_kind:
            raise ValueError("subject_id and subject_kind must be non-empty")
        if not observer_name:
            raise ValueError("observer_name must be non-empty")
        if verdict not in {"pass", "warn", "fail"}:
            raise ValueError("observer summary verdict must be pass, warn, or fail")
        object.__setattr__(self, "subject_id", subject_id)
        object.__setattr__(self, "subject_kind", subject_kind)
        object.__setattr__(self, "observer_name", observer_name)
        object.__setattr__(self, "verdict", verdict)
        object.__setattr__(self, "reasons", _normalized_tuple(self.reasons, field_name="reasons"))
        object.__setattr__(self, "blocking_risks", tuple(str(item or "").strip() for item in tuple(self.blocking_risks or ()) if str(item or "").strip()))
        object.__setattr__(self, "confidence", _normalize_confidence(self.confidence))
        object.__setattr__(self, "contradiction_state", normalize_contradiction_state(self.contradiction_state))
        object.__setattr__(self, "canonical_sources", _normalized_tuple(self.canonical_sources, field_name="canonical_sources"))
        if self.artifact_type != INTERWOVEN_OBSERVER_SUMMARY_ARTIFACT:
            raise ValueError("artifact_type mismatch for interwoven observer summary")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InterwovenObserverSummary":
        return cls(
            subject_id=payload.get("subject_id", ""),
            subject_kind=payload.get("subject_kind", ""),
            observer_name=payload.get("observer_name", ""),
            verdict=payload.get("verdict", ""),
            reasons=tuple(payload.get("reasons") or ()),
            blocking_risks=tuple(payload.get("blocking_risks") or ()),
            confidence=payload.get("confidence", 0.0),
            contradiction_state=payload.get("contradiction_state", "none"),
            canonical_sources=tuple(payload.get("canonical_sources") or ()),
            artifact_type=payload.get("artifact_type", INTERWOVEN_OBSERVER_SUMMARY_ARTIFACT),
            contract_version=payload.get("contract_version", INTERWOVEN_ARTIFACT_SCHEMA_VERSION),
        )
