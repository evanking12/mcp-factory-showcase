from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


DECOMPOSITION_CONTRACT_SCHEMA_VERSION = "1.0.0"

DECOMPOSITION_OBJECT_TYPES = (
    "shard",
    "cluster_candidate",
    "init_group_candidate",
    "dependency_class",
    "frontier_slice",
)

CONTRADICTION_STATES = (
    "none",
    "tentative",
    "blocked",
    "contradicted",
    "quarantined",
    "superseded",
    "confirmed",
)

CLOSURE_REASONS = (
    "merged_forward",
    "replaced_by_higher_confidence",
    "invalidated_by_contradiction",
    "retired_as_noise",
    "promoted_to_verified_structure",
)

DECOMPOSITION_OBSERVER_NAMES = (
    "shard_validity",
    "merge_coherence",
    "initialization_group_plausibility",
    "dependency_class_plausibility",
    "frontier_slice_boundedness",
)

DECOMPOSITION_RETENTION_CLASSES = (
    "canonical",
    "summary_only",
    "superseded_or_compacted",
)

_DEFAULT_CONTRADICTION_STATE = "none"
_DEFAULT_CLOSURE_REASON = ""


def normalize_contradiction_state(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in CONTRADICTION_STATES else _DEFAULT_CONTRADICTION_STATE


def normalize_closure_reason(value: str | None) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in CLOSURE_REASONS else _DEFAULT_CLOSURE_REASON


def normalize_object_type(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in DECOMPOSITION_OBJECT_TYPES:
        return candidate
    raise ValueError(f"unknown decomposition object type: {value!r}")


def normalize_observer_name(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in DECOMPOSITION_OBSERVER_NAMES:
        return candidate
    raise ValueError(f"unknown decomposition observer name: {value!r}")


def build_decomposition_object_id(
    object_type: str,
    package_id: str,
    *,
    graph_epoch: str = "",
    ordinal: int | None = None,
    stable_hash: str = "",
) -> str:
    normalized_type = normalize_object_type(object_type)
    normalized_package = str(package_id or "").strip()
    if not normalized_package:
        raise ValueError("package_id must be non-empty")
    if normalized_type in {"shard", "frontier_slice"}:
        normalized_epoch = str(graph_epoch or "").strip()
        if not normalized_epoch:
            raise ValueError(f"{normalized_type} ids require graph_epoch")
        if ordinal is None or int(ordinal) < 0:
            raise ValueError(f"{normalized_type} ids require a non-negative ordinal")
        return f"{normalized_type}::{normalized_package}::{normalized_epoch}::{int(ordinal)}"
    normalized_hash = str(stable_hash or "").strip()
    if not normalized_hash:
        raise ValueError(f"{normalized_type} ids require stable_hash")
    return f"{normalized_type}::{normalized_package}::{normalized_hash}"


@dataclass(frozen=True)
class DecompositionLifecycle:
    id: str
    object_type: str
    package_id: str
    graph_epoch: str = ""
    source_ids: tuple[str, ...] = ()
    supersedes_id: str = ""
    supersedes_reason: str = ""
    contradiction_state: str = _DEFAULT_CONTRADICTION_STATE
    active: bool = True
    closed_at: str = ""
    closure_reason: str = _DEFAULT_CLOSURE_REASON
    schema_version: str = DECOMPOSITION_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "object_type", normalize_object_type(self.object_type))
        object.__setattr__(self, "package_id", str(self.package_id or "").strip())
        object.__setattr__(self, "graph_epoch", str(self.graph_epoch or "").strip())
        object.__setattr__(
            self,
            "source_ids",
            tuple(
                str(source_id or "").strip()
                for source_id in tuple(self.source_ids or ())
                if str(source_id or "").strip()
            ),
        )
        object.__setattr__(self, "supersedes_id", str(self.supersedes_id or "").strip())
        object.__setattr__(self, "supersedes_reason", str(self.supersedes_reason or "").strip())
        object.__setattr__(
            self,
            "contradiction_state",
            normalize_contradiction_state(self.contradiction_state),
        )
        object.__setattr__(self, "closed_at", str(self.closed_at or "").strip())
        object.__setattr__(self, "closure_reason", normalize_closure_reason(self.closure_reason))
        if not str(self.id or "").strip():
            raise ValueError("decomposition lifecycle id must be non-empty")
        if not self.package_id:
            raise ValueError("decomposition lifecycle package_id must be non-empty")
        if bool(self.closed_at) != bool(self.closure_reason):
            raise ValueError("closed_at and closure_reason must be provided together")
        if self.supersedes_id and not self.supersedes_reason:
            raise ValueError("supersedes_reason required when supersedes_id is present")
        if self.closure_reason and self.active:
            raise ValueError("closed lifecycle objects must not remain active")
        if self.object_type in {"shard", "frontier_slice"} and not self.graph_epoch:
            raise ValueError(f"{self.object_type} lifecycle requires graph_epoch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DecompositionLifecycle":
        return cls(
            id=payload.get("id", ""),
            object_type=payload.get("object_type", ""),
            package_id=payload.get("package_id", ""),
            graph_epoch=payload.get("graph_epoch", ""),
            source_ids=tuple(payload.get("source_ids") or ()),
            supersedes_id=payload.get("supersedes_id", ""),
            supersedes_reason=payload.get("supersedes_reason", ""),
            contradiction_state=payload.get("contradiction_state", ""),
            active=bool(payload.get("active", True)),
            closed_at=payload.get("closed_at", ""),
            closure_reason=payload.get("closure_reason", ""),
            schema_version=payload.get("schema_version", DECOMPOSITION_CONTRACT_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class ShardEconomics:
    target_shard_width: int = 10
    actual_shard_width: int = 0
    target_runtime_budget_minutes: int = 12
    actual_runtime_minutes: float = 0.0
    hard_runtime_ceiling_minutes: int = 20
    hard_split_threshold: int = 15
    target_deep_follow_up_budget: int = 0
    actual_deep_follow_up_count: int = 0
    intake_mode: str = "intake_only"
    budget_breached: bool = False
    schema_version: str = DECOMPOSITION_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.target_shard_width <= 0:
            raise ValueError("target_shard_width must be positive")
        if self.actual_shard_width < 0:
            raise ValueError("actual_shard_width must be non-negative")
        if self.target_runtime_budget_minutes <= 0:
            raise ValueError("target_runtime_budget_minutes must be positive")
        if self.actual_runtime_minutes < 0:
            raise ValueError("actual_runtime_minutes must be non-negative")
        if self.hard_runtime_ceiling_minutes < self.target_runtime_budget_minutes:
            raise ValueError("hard_runtime_ceiling_minutes must be >= target_runtime_budget_minutes")
        if self.hard_split_threshold <= 0:
            raise ValueError("hard_split_threshold must be positive")
        if self.target_deep_follow_up_budget < 0 or self.actual_deep_follow_up_count < 0:
            raise ValueError("deep follow-up counts must be non-negative")
        if str(self.intake_mode or "").strip() != "intake_only":
            raise ValueError("Phase 0 shard economics only supports intake_only mode")

    @property
    def runtime_budget_ok(self) -> bool:
        return self.actual_runtime_minutes <= self.hard_runtime_ceiling_minutes

    @property
    def shard_width_ok(self) -> bool:
        return self.actual_shard_width <= self.hard_split_threshold

    @property
    def deep_follow_up_budget_ok(self) -> bool:
        return self.actual_deep_follow_up_count <= self.target_deep_follow_up_budget

    def evaluate_budget_breached(self) -> bool:
        return not (self.runtime_budget_ok and self.shard_width_ok and self.deep_follow_up_budget_ok)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["runtime_budget_ok"] = self.runtime_budget_ok
        payload["shard_width_ok"] = self.shard_width_ok
        payload["deep_follow_up_budget_ok"] = self.deep_follow_up_budget_ok
        payload["budget_breached"] = bool(self.budget_breached or self.evaluate_budget_breached())
        return payload


@dataclass(frozen=True)
class DecompositionObserverBase:
    observer_name: str
    object_id: str
    status: str
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    schema_version: str = DECOMPOSITION_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observer_name", normalize_observer_name(self.observer_name))
        normalized_status = str(self.status or "").strip().lower()
        if normalized_status not in {"pass", "warn", "fail"}:
            raise ValueError("observer status must be pass, warn, or fail")
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(
            self,
            "reasons",
            tuple(str(reason or "").strip() for reason in tuple(self.reasons or ()) if str(reason or "").strip()),
        )
        object.__setattr__(
            self,
            "warnings",
            tuple(str(warning or "").strip() for warning in tuple(self.warnings or ()) if str(warning or "").strip()),
        )
        if not str(self.object_id or "").strip():
            raise ValueError("observer object_id must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShardValidityObserverResult(DecompositionObserverBase):
    capture_valid: bool = False
    runtime_budget_ok: bool = False
    required_artifacts_present: bool = False
    hidden_variable_state_recorded: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.observer_name != "shard_validity":
            raise ValueError("ShardValidityObserverResult requires observer_name='shard_validity'")


@dataclass(frozen=True)
class MergeCoherenceObserverResult(DecompositionObserverBase):
    provenance_complete: bool = False
    stable_identity_present: bool = False
    contradictions_visible: bool = False
    ambiguity_score: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.observer_name != "merge_coherence":
            raise ValueError("MergeCoherenceObserverResult requires observer_name='merge_coherence'")
        if self.ambiguity_score < 0:
            raise ValueError("ambiguity_score must be non-negative")


@dataclass(frozen=True)
class FrontierSliceBoundednessObserverResult(DecompositionObserverBase):
    imported_truth_explicit: bool = False
    active_work_explicit: bool = False
    slice_width: int = 0
    dll_count: int = 0
    cluster_count: int = 0
    init_group_count: int = 0
    reopened_imported_truth: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.observer_name != "frontier_slice_boundedness":
            raise ValueError(
                "FrontierSliceBoundednessObserverResult requires observer_name='frontier_slice_boundedness'"
            )
        for field_name in ("slice_width", "dll_count", "cluster_count", "init_group_count"):
            if int(getattr(self, field_name)) < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True)
class DecompositionRetentionPolicy:
    canonical_artifacts: tuple[str, ...] = (
        "shard_identity",
        "shard_summary",
        "candidate_clusters",
        "candidate_init_groups",
        "candidate_dependency_classes",
        "frontier_slices",
        "observer_summaries",
    )
    summary_only_artifacts: tuple[str, ...] = (
        "raw_shard_note_aggregation",
        "intermediate_merge_traces",
        "temporary_scoring_detail",
        "decomposition_dashboard",
        "merge_ambiguity_report",
        "slice_inspection_report",
    )
    superseded_or_compacted_artifacts: tuple[str, ...] = (
        "prior_candidate_versions",
        "redundant_merge_attempts",
        "detail_traces_represented_in_canonical_summaries",
    )
    schema_version: str = DECOMPOSITION_CONTRACT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def classify_artifact(self, artifact_name: str) -> str:
        normalized_name = str(artifact_name or "").strip().lower()
        canonical = {name.lower() for name in self.canonical_artifacts}
        summary_only = {name.lower() for name in self.summary_only_artifacts}
        compacted = {name.lower() for name in self.superseded_or_compacted_artifacts}
        if normalized_name in canonical:
            return "canonical"
        if normalized_name in summary_only:
            return "summary_only"
        if normalized_name in compacted:
            return "superseded_or_compacted"
        return "canonical"


DEFAULT_DECOMPOSITION_RETENTION_POLICY = DecompositionRetentionPolicy()


def build_shard_validity_observer(
    *,
    object_id: str,
    status: str,
    capture_valid: bool,
    runtime_budget_ok: bool,
    required_artifacts_present: bool,
    hidden_variable_state_recorded: bool,
    reasons: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
) -> dict[str, Any]:
    return ShardValidityObserverResult(
        observer_name="shard_validity",
        object_id=object_id,
        status=status,
        capture_valid=capture_valid,
        runtime_budget_ok=runtime_budget_ok,
        required_artifacts_present=required_artifacts_present,
        hidden_variable_state_recorded=hidden_variable_state_recorded,
        reasons=reasons,
        warnings=warnings,
    ).to_dict()


def build_merge_coherence_observer(
    *,
    object_id: str,
    status: str,
    provenance_complete: bool,
    stable_identity_present: bool,
    contradictions_visible: bool,
    ambiguity_score: float,
    reasons: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
) -> dict[str, Any]:
    return MergeCoherenceObserverResult(
        observer_name="merge_coherence",
        object_id=object_id,
        status=status,
        provenance_complete=provenance_complete,
        stable_identity_present=stable_identity_present,
        contradictions_visible=contradictions_visible,
        ambiguity_score=ambiguity_score,
        reasons=reasons,
        warnings=warnings,
    ).to_dict()


def build_frontier_slice_boundedness_observer(
    *,
    object_id: str,
    status: str,
    imported_truth_explicit: bool,
    active_work_explicit: bool,
    slice_width: int,
    dll_count: int,
    cluster_count: int,
    init_group_count: int,
    reopened_imported_truth: bool,
    reasons: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
) -> dict[str, Any]:
    return FrontierSliceBoundednessObserverResult(
        observer_name="frontier_slice_boundedness",
        object_id=object_id,
        status=status,
        imported_truth_explicit=imported_truth_explicit,
        active_work_explicit=active_work_explicit,
        slice_width=slice_width,
        dll_count=dll_count,
        cluster_count=cluster_count,
        init_group_count=init_group_count,
        reopened_imported_truth=reopened_imported_truth,
        reasons=reasons,
        warnings=warnings,
    ).to_dict()
