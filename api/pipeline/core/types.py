"""api.pipeline.types – Shared dataclasses for the exploration pipeline.

ExploreRuntime: immutable configuration loaded from job_runtime at worker start.
ExploreContext:  mutable pipeline state threaded through all phase functions.

Using explicit types instead of ~20 closure-captured locals gives three wins:
  1. Data flow is visible: each field is annotated with the phase that writes it.
  2. Phase functions are testable in isolation — construct an ExploreContext, run
     the phase, assert on the fields it wrote.
  3. Parallel _explore_one workers share state through clearly-labelled locks,
     not implicit closure references.
"""

from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from api.pipeline.core.floor_iteration import (
    normalize_floor_scope,
    normalize_iteration_mode,
)
from api.pipeline.core.pass_scope import normalize_pass_scope_profile


# ── Campaign-level types (multi-DLL support) ─────────────────────────────────

class CampaignPhase(str, enum.Enum):
    """State machine for campaign lifecycle."""
    CREATED = "created"
    DISCOVERING = "discovering"
    PLANNING = "planning"
    EXECUTING = "executing"
    CONSOLIDATING = "consolidating"
    DONE = "done"
    PARTIAL_FAILURE = "partial_failure"
    CANCELLED_PARTIAL = "cancelled_partial"


class DllStatus(str, enum.Enum):
    """Per-DLL status within a campaign."""
    PENDING = "pending"
    DISCOVERING = "discovering"
    DISCOVERED = "discovered"
    EXPLORING = "exploring"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class PersistenceClassification(str, enum.Enum):
    """Controls what is safe to persist verbatim in campaign artifacts."""
    VERBATIM = "verbatim"
    SUMMARY_ONLY = "summary_only"
    REDACTED = "redacted"


import re as _re

_SECRET_PATTERNS = [
    _re.compile(r"sk-[A-Za-z0-9]{20,}", _re.I),       # OpenAI API keys
    _re.compile(r"AKIA[0-9A-Z]{16}", _re.I),           # AWS access keys
    _re.compile(r"(?:password|secret|token)\s*[:=]\s*\S+", _re.I),
    _re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
    _re.compile(r"DefaultEndpointsProtocol=https;AccountName=", _re.I),
]


def classify_artifact(blob_name: str) -> PersistenceClassification:
    """Classify a blob name into a persistence category.

    Rules:
    - Verbatim-safe: findings, invocables, vocab, schemas, sentinels,
      evidence graph, campaign plan, checkpoint, cohesion reports
    - Summary-only: chat transcripts, mini-session transcripts
    - Redacted: .env files, credentials
    """
    lower = blob_name.lower()
    if any(p in lower for p in (".env", "credential", "secret")):
        return PersistenceClassification.REDACTED
    if any(p in lower for p in ("transcript", "chat_", "mini_session")):
        return PersistenceClassification.SUMMARY_ONLY
    return PersistenceClassification.VERBATIM


def sensitivity_scan(text: str) -> list[str]:
    """Scan text for patterns matching known secret formats.

    Returns a list of warning messages for each match found.
    """
    warnings: list[str] = []
    for pattern in _SECRET_PATTERNS:
        matches = pattern.findall(text[:50000])
        if matches:
            warnings.append(
                f"Potential secret detected matching pattern '{pattern.pattern}' "
                f"({len(matches)} occurrence(s))"
            )
    return warnings


@dataclass
class DllEntry:
    """One DLL within a campaign."""
    dll_id: str
    dll_fingerprint: str = ""
    job_id: str = ""
    dll_path: str = ""
    filename: str = ""
    status: str = DllStatus.PENDING.value
    lane_id: str = ""
    selection_reason: str = ""
    dependency_confidence: str = ""
    blocker_family_primary: str = ""
    blocker_family_secondary: list[str] = field(default_factory=list)
    blocker_confidence: str = ""
    architecture_relevance: str = ""
    lane_trust_status: str = ""
    runtime_path_trust: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dll_id": self.dll_id,
            "dll_fingerprint": self.dll_fingerprint,
            "job_id": self.job_id,
            "dll_path": self.dll_path,
            "filename": self.filename,
            "status": self.status,
            "lane_id": self.lane_id,
            "selection_reason": self.selection_reason,
            "dependency_confidence": self.dependency_confidence,
            "blocker_family_primary": self.blocker_family_primary,
            "blocker_family_secondary": list(self.blocker_family_secondary),
            "blocker_confidence": self.blocker_confidence,
            "architecture_relevance": self.architecture_relevance,
            "lane_trust_status": self.lane_trust_status,
            "runtime_path_trust": self.runtime_path_trust,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DllEntry":
        return cls(
            dll_id=d.get("dll_id", ""),
            dll_fingerprint=d.get("dll_fingerprint", ""),
            job_id=d.get("job_id", ""),
            dll_path=d.get("dll_path", ""),
            filename=d.get("filename", ""),
            status=d.get("status", DllStatus.PENDING.value),
            lane_id=d.get("lane_id", ""),
            selection_reason=d.get("selection_reason", ""),
            dependency_confidence=d.get("dependency_confidence", ""),
            blocker_family_primary=d.get("blocker_family_primary", ""),
            blocker_family_secondary=list(d.get("blocker_family_secondary", []) or []),
            blocker_confidence=d.get("blocker_confidence", ""),
            architecture_relevance=d.get("architecture_relevance", ""),
            lane_trust_status=d.get("lane_trust_status", ""),
            runtime_path_trust=d.get("runtime_path_trust", ""),
            error=d.get("error", ""),
        )


@dataclass
class Campaign:
    """Top-level campaign grouping multiple DLLs."""
    campaign_id: str
    dll_entries: list[DllEntry] = field(default_factory=list)
    phase: str = CampaignPhase.CREATED.value
    graph_epoch: str = ""
    hints: str = ""
    use_cases: str = ""
    analysis_profile: str = "strict_dll"
    max_dlls: int = 100
    package_id: str = ""
    package_label: str = ""
    package_context: dict[str, Any] = field(default_factory=dict)
    source_origin: str = ""
    package_purpose: str = ""
    doc_visibility: str = ""
    dependency_context: str = ""
    operator_notes: str = ""
    baseline_contract: dict[str, Any] = field(default_factory=dict)
    cancel_requested: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    schema_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "dll_entries": [e.to_dict() for e in self.dll_entries],
            "phase": self.phase,
            "graph_epoch": self.graph_epoch,
            "hints": self.hints,
            "use_cases": self.use_cases,
            "analysis_profile": self.analysis_profile,
            "max_dlls": self.max_dlls,
            "package_id": self.package_id,
            "package_label": self.package_label,
            "package_context": dict(self.package_context),
            "source_origin": self.source_origin,
            "package_purpose": self.package_purpose,
            "doc_visibility": self.doc_visibility,
            "dependency_context": self.dependency_context,
            "operator_notes": self.operator_notes,
            "baseline_contract": dict(self.baseline_contract),
            "cancel_requested": self.cancel_requested,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Campaign":
        entries = [DllEntry.from_dict(e) for e in d.get("dll_entries", [])]
        return cls(
            campaign_id=d.get("campaign_id", ""),
            dll_entries=entries,
            phase=d.get("phase", CampaignPhase.CREATED.value),
            graph_epoch=d.get("graph_epoch", ""),
            hints=d.get("hints", ""),
            use_cases=d.get("use_cases", ""),
            analysis_profile=d.get("analysis_profile", "strict_dll"),
            max_dlls=d.get("max_dlls", 100),
            package_id=d.get("package_id", ""),
            package_label=d.get("package_label", ""),
            package_context=dict(d.get("package_context", {}) or {}),
            source_origin=d.get("source_origin", ""),
            package_purpose=d.get("package_purpose", ""),
            doc_visibility=d.get("doc_visibility", ""),
            dependency_context=d.get("dependency_context", ""),
            operator_notes=d.get("operator_notes", ""),
            baseline_contract=dict(d.get("baseline_contract", {}) or {}),
            cancel_requested=d.get("cancel_requested", False),
            created_at=d.get("created_at", 0.0),
            updated_at=d.get("updated_at", 0.0),
            schema_version=d.get("schema_version", "1.0.0"),
        )


@dataclass
class ExploreRuntime:
    """Immutable pipeline configuration — set once at worker start.

    All fields default to the same values as the module-level constants so
    unit tests can construct an ``ExploreRuntime()`` without a live job.
    """

    max_rounds: int = 8
    max_tool_calls: int = 24
    max_functions: int = 50
    min_direct_probes: int = 1
    cap_profile: str = "default"
    skip_documented: bool = True
    deterministic_fallback_enabled: bool = True
    gap_resolution_enabled: bool = True
    clarification_enabled: bool = True
    model_override: str = ""
    concurrency: int = 1
    instruction_fragment: str = ""
    context_density: str = "full"
    analysis_profile: str = "strict_dll"
    variant_configs: list[dict[str, Any]] = field(default_factory=list)
    parallel_runs: int = 1
    lane_id: str = ""
    variant_id: str = ""
    prior_job_id: str = ""
    overlap_baseline_job_id: str = ""
    cross_dll_prior_job_ids: list[str] = field(default_factory=list)
    chain_step_target: str = ""
    required_semantic_checkpoint: str = ""
    selected_invocable_names: list[str] = field(default_factory=list)
    graph_epoch: str = ""
    checkpoint_id: str = ""
    checkpoint_stage: str = ""
    cluster_checkpoint_id: str = ""
    adjacent_cluster_id: str = ""
    cluster_confidence_floor: float = 0.5
    focus_functions: list = field(default_factory=list)
    pass_index: int = 1
    pass_scope_profile: str = "foundation"
    iteration_mode: str = "single_pass"
    iteration_index: int = 1
    floor_scope: str = "cluster"
    ceiling_functions: list = field(default_factory=list)
    ceiling_origin_functions: list = field(default_factory=list)
    prerequisite_state_group_ids: list = field(default_factory=list)
    max_iteration_cycles: int = 1
    skip_to_stage: str = ""
    skip_to_stage_reason: str = ""
    campaign_id: str = ""
    seed_strategy: str = "cold_start"
    seed_default_applied: bool = False
    seed_default_reason: str = ""

    @classmethod
    def from_job_runtime(cls, job_runtime: dict) -> "ExploreRuntime":
        """Construct from the ``explore_runtime`` sub-dict in job status."""
        import os as _os
        from api.pipeline.core.explore_config import (
            CAP_PROFILE,
            GAP_RESOLUTION_ENABLED,
            MAX_EXPLORE_ROUNDS_PER_FUNCTION,
            MAX_FUNCTIONS_PER_SESSION,
            MAX_TOOL_CALLS_PER_FUNCTION,
        )

        try:
            cluster_confidence_floor = float(job_runtime.get("cluster_confidence_floor") or 0.5)
        except (TypeError, ValueError):
            cluster_confidence_floor = 0.5
        try:
            pass_index = max(1, int(job_runtime.get("pass_index") or 1))
        except (TypeError, ValueError):
            pass_index = 1
        pass_scope_profile = normalize_pass_scope_profile(
            pass_index,
            str(job_runtime.get("pass_scope_profile") or ""),
        )
        try:
            iteration_index = max(1, int(job_runtime.get("iteration_index") or 1))
        except (TypeError, ValueError):
            iteration_index = 1
        try:
            max_iteration_cycles = max(1, int(job_runtime.get("max_iteration_cycles") or 1))
        except (TypeError, ValueError):
            max_iteration_cycles = 1
        iteration_mode = normalize_iteration_mode(str(job_runtime.get("iteration_mode") or ""))
        floor_scope = normalize_floor_scope(str(job_runtime.get("floor_scope") or ""))
        ceiling_functions = list(job_runtime.get("ceiling_functions") or [])
        if not ceiling_functions and iteration_mode == "floor_to_ceiling":
            ceiling_functions = list(job_runtime.get("focus_functions") or [])
        ceiling_origin_functions = list(job_runtime.get("ceiling_origin_functions") or [])
        if not ceiling_origin_functions and iteration_mode == "floor_to_ceiling":
            ceiling_origin_functions = list(ceiling_functions)

        return cls(
            max_rounds=int(job_runtime.get("max_rounds") or MAX_EXPLORE_ROUNDS_PER_FUNCTION),
            max_tool_calls=int(job_runtime.get("max_tool_calls") or MAX_TOOL_CALLS_PER_FUNCTION),
            max_functions=int(job_runtime.get("max_functions") or MAX_FUNCTIONS_PER_SESSION),
            min_direct_probes=max(1, int(job_runtime.get("min_direct_probes_per_function") or 1)),
            cap_profile=str(job_runtime.get("cap_profile") or CAP_PROFILE),
            skip_documented=bool(job_runtime.get("skip_documented", True)),
            deterministic_fallback_enabled=bool(
                job_runtime.get("deterministic_fallback_enabled", True)
            ),
            gap_resolution_enabled=bool(
                job_runtime.get("gap_resolution_enabled", GAP_RESOLUTION_ENABLED)
            ),
            clarification_enabled=bool(
                job_runtime.get("clarification_questions_enabled", True)
            ),
            model_override=str(job_runtime.get("model") or "").strip(),
            concurrency=int(_os.getenv("EXPLORE_CONCURRENCY", "1")),
            instruction_fragment=str(job_runtime.get("instruction_fragment") or "").strip(),
            context_density=str(job_runtime.get("context_density") or "full").strip().lower(),
            analysis_profile=str(job_runtime.get("analysis_profile") or "strict_dll").strip().lower(),
            variant_configs=list(job_runtime.get("variant_configs") or []),
            parallel_runs=max(1, int(job_runtime.get("parallel_runs") or 1)),
            lane_id=str(job_runtime.get("lane_id") or "").strip(),
            variant_id=str(job_runtime.get("variant_id") or "").strip(),
            prior_job_id=str(job_runtime.get("prior_job_id") or "").strip(),
            overlap_baseline_job_id=str(
                job_runtime.get("overlap_baseline_job_id") or ""
            ).strip(),
            cross_dll_prior_job_ids=[
                str(x).strip() for x in (job_runtime.get("cross_dll_prior_job_ids") or [])
                if str(x).strip()
            ],
            chain_step_target=str(job_runtime.get("chain_step_target") or "").strip(),
            required_semantic_checkpoint=str(job_runtime.get("required_semantic_checkpoint") or "").strip(),
            selected_invocable_names=[
                str(x).strip() for x in (job_runtime.get("selected_invocable_names") or [])
                if str(x).strip()
            ],
            graph_epoch=str(job_runtime.get("graph_epoch") or "").strip(),
            checkpoint_id=str(job_runtime.get("checkpoint_id") or "").strip(),
            checkpoint_stage=str(job_runtime.get("checkpoint_stage") or "").strip(),
            cluster_checkpoint_id=str(job_runtime.get("cluster_checkpoint_id") or "").strip(),
            adjacent_cluster_id=str(job_runtime.get("adjacent_cluster_id") or "").strip(),
            cluster_confidence_floor=cluster_confidence_floor,
            focus_functions=list(job_runtime.get("focus_functions") or []),
            pass_index=pass_index,
            pass_scope_profile=pass_scope_profile,
            iteration_mode=iteration_mode,
            iteration_index=iteration_index,
            floor_scope=floor_scope,
            ceiling_functions=ceiling_functions,
            ceiling_origin_functions=ceiling_origin_functions,
            prerequisite_state_group_ids=list(job_runtime.get("prerequisite_state_group_ids") or []),
            max_iteration_cycles=max_iteration_cycles,
            skip_to_stage=str(job_runtime.get("skip_to_stage") or "").strip(),
            skip_to_stage_reason=str(job_runtime.get("skip_to_stage_reason") or "").strip(),
            campaign_id=str(job_runtime.get("campaign_id") or "").strip(),
            seed_strategy=str(job_runtime.get("seed_strategy") or "cold_start").strip() or "cold_start",
            seed_default_applied=bool(job_runtime.get("seed_default_applied", False)),
            seed_default_reason=str(job_runtime.get("seed_default_reason") or "").strip(),
        )


@dataclass
class ExploreContext:
    """Mutable pipeline state — threaded through each phase function.

    Fields are grouped by the phase that produces them.  A phase function
    must only *write* to its own group; it may *read* from any earlier group.
    Forward reads (reading a field before its producing phase has run) are bugs.

    Thread safety
    -------------
    ``vocab``, ``sentinel_catalog``, ``already_explored``, and ``_state``
    are shared across parallel ``_explore_one`` workers.  Always acquire
    ``_lock`` before mutating them.
    """

    # ── Identity (set at construction, never mutated) ─────────────────────────
    job_id: str
    runtime: ExploreRuntime
    client: Any          # openai.OpenAI
    model: str
    run_started_at: float = field(default_factory=time.time)
    lane_id: str = ""
    variant_id: str = ""
    campaign_id: str = ""

    # ── Built from invocables at construction ─────────────────────────────────
    invocables: list[dict] = field(default_factory=list)
    inv_map: dict[str, dict] = field(default_factory=dict)
    tool_schemas: list[dict] = field(default_factory=list)
    total: int = 0

    # ── PRODUCED BY S-00 (run_baseline_truth) ────────────────────────────────
    sentinels: dict = field(default_factory=dict)

    # ── PRODUCED BY S-00 (_run_phase_0_vocab_seed) ────────────────────────────
    vocab: dict = field(default_factory=dict)
    use_cases_text: str = ""

    # ── PRODUCED BY S-00 (_run_phase_0_static) ────────────────────────────────
    static_hints_block: str = ""
    dll_strings: dict = field(default_factory=dict)
    static_analysis_result: dict = field(default_factory=dict)
    static_enrichment: dict = field(default_factory=dict)
    s00_s01_handoff_packet: dict = field(default_factory=dict)

    # ── PRODUCED BY S-00 (Ghidra enhanced extraction) ─────────────────────────
    call_graph: dict = field(default_factory=dict)
    ghidra_data_types: list = field(default_factory=list)

    # ── PRODUCED BY S-01 (_run_phase_1_write_unlock) ──────────────────────────
    unlock_result: dict = field(default_factory=lambda: {
        "unlocked": False, "sequence": [], "notes": "not attempted"
    })
    write_unlock_block: str = ""

    # ── Sentinel tracking ─────────────────────────────────────────────────────
    sentinel_new_codes_this_run: int = 0

    # ── PRODUCED BY S-02 (_run_phase_2_curriculum_order) ──────────────────────
    init_invocables: list[dict] = field(default_factory=list)
    execution_layers: list[list[str]] = field(default_factory=list)
    prerequisite_map: dict[str, list[str]] = field(default_factory=dict)
    sequence_roles: dict[str, dict[str, Any]] = field(default_factory=dict)

    # ── ACCUMULATED DURING S-02 probe loop (thread-safe) ──────────────────────
    sentinel_catalog: dict = field(default_factory=dict)
    already_explored: set = field(default_factory=set)
    live_findings: list = field(default_factory=list)
    _state: dict = field(default_factory=lambda: {"explored": 0})
    _lock: threading.RLock = field(default_factory=threading.RLock)

    # ── Evidence candidate registry (progressive specialization) ────────────
    evidence_candidates: Any = None  # EvidenceCandidateRegistry, lazily set

    # ── Cost tracking (accumulated during pipeline run) ─────────────────────
    cost_llm_calls: int = 0
    cost_llm_tokens_in: int = 0
    cost_llm_tokens_out: int = 0
    cost_bridge_calls: int = 0
    cost_wall_time_start: float = field(default_factory=time.time)
    floor_plan: Any = None
    floor_iteration_state: Any = None

    def explored_count(self) -> int:
        state = self._state if isinstance(self._state, dict) else {}
        try:
            return int(state.get("explored") or 0)
        except Exception:
            return 0

    def increment_explored(self, amount: int = 1) -> int:
        with self._lock:
            state = self._state if isinstance(self._state, dict) else {}
            current = int(state.get("explored") or 0)
            current += int(amount)
            state["explored"] = current
            self._state = state
            return current

    def latest_mc_decision(self, mc_id: str) -> dict[str, Any]:
        state = self._state if isinstance(self._state, dict) else {}
        mc_state = state.get("mc_decisions") or {}
        if isinstance(mc_state, dict):
            latest = mc_state.get(mc_id)
            if isinstance(latest, dict):
                return latest
        return {}

    def persist_mc_decision(self, mc_id: str, decision: dict[str, Any]) -> None:
        with self._lock:
            state = self._state if isinstance(self._state, dict) else {}
            mc_state = state.setdefault("mc_decisions", {})
            if isinstance(mc_state, dict):
                mc_state[mc_id] = dict(decision or {})
            self._state = state

    def cost_summary(self) -> dict[str, Any]:
        return {
            "llm_calls": self.cost_llm_calls,
            "llm_tokens_in": self.cost_llm_tokens_in,
            "llm_tokens_out": self.cost_llm_tokens_out,
            "bridge_calls": self.cost_bridge_calls,
            "wall_time_s": round(time.time() - self.cost_wall_time_start, 2),
        }

    # ── Checkpoint reference (set by orchestrator, used by probe loop) ────────
    _checkpoint: Any = None
