from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SystemContract:
    name: str
    owner_layer: str
    home_module: str
    purpose: str
    consumes: tuple[str, ...]
    emits: tuple[str, ...]
    decisions: tuple[str, ...]
    required_evidence_artifacts: tuple[str, ...]
    adjacent_systems: tuple[str, ...]
    handoff_invariants: tuple[str, ...]
    success_signals: tuple[str, ...]
    failure_signals: tuple[str, ...]
    monitoring_fields: tuple[str, ...]
    expected_test_surfaces: tuple[str, ...]
    do_not_use_when: tuple[str, ...] = ()
    overfitting_risks: tuple[str, ...] = ()


@dataclass(frozen=True)
class SystemObserverResult:
    observer_id: str
    contract_name: str
    status: str
    target_function: str
    summary: str
    expected: dict[str, Any] = field(default_factory=dict)
    observed: dict[str, Any] = field(default_factory=dict)
    violation: str = ""
    likely_fault_scope: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_system_contracts(contracts: tuple[SystemContract, ...]) -> None:
    seen: set[str] = set()
    for contract in contracts:
        if not contract.name.strip():
            raise ValueError("system contract name must be non-empty")
        if contract.name in seen:
            raise ValueError(f"duplicate system contract: {contract.name}")
        seen.add(contract.name)
        for attr_name in (
            "owner_layer",
            "home_module",
            "purpose",
        ):
            if not str(getattr(contract, attr_name) or "").strip():
                raise ValueError(f"{contract.name}: {attr_name} must be non-empty")
        for attr_name in (
            "consumes",
            "emits",
            "decisions",
            "required_evidence_artifacts",
            "adjacent_systems",
            "handoff_invariants",
            "success_signals",
            "failure_signals",
            "monitoring_fields",
            "expected_test_surfaces",
        ):
            values = tuple(getattr(contract, attr_name) or ())
            if not values:
                raise ValueError(f"{contract.name}: {attr_name} must be non-empty")


SYSTEM_CONTRACTS: tuple[SystemContract, ...] = (
    SystemContract(
        name="generalized runtime artifact materializer",
        owner_layer="s02_probe",
        home_module="api/pipeline/core/evidence_candidates.py",
        purpose="Capture runtime-produced artifacts, classify their likely family, and publish reusable same-run evidence.",
        consumes=(
            "runtime result text",
            "tool trace metadata",
            "working-call args",
            "parameter metadata",
        ),
        emits=(
            "tiered runtime evidence candidates",
            "materialized live lineage hints",
            "family-labeled runtime artifacts",
        ),
        decisions=(
            "capture runtime artifact",
            "demote empty or zero artifacts",
            "materialize live hints into reusable evidence",
        ),
        required_evidence_artifacts=(
            "evidence candidate registry entries",
            "materialized runtime artifact metadata",
        ),
        adjacent_systems=(
            "prerequisite replay / runtime materialization",
            "dense-context lineage isolation",
            "structured argument scaffolder",
        ),
        handoff_invariants=(
            "live family-sensitive artifacts must not be emitted as empty values",
            "zero or empty numeric outputs must not masquerade as live runtime state",
            "materialized live hints must remain reusable by downstream replay",
        ),
        success_signals=(
            "same-run runtime artifacts are reused by downstream consumers",
            "live promotions become reusable evidence instead of transient hints only",
        ),
        failure_signals=(
            "materialization missing families stay unresolved after producer success",
            "downstream replay falls back despite a live runtime artifact having been observed",
        ),
        monitoring_fields=(
            "materialized_runtime_artifacts",
            "promoted_hints",
            "materialization_missing_families",
        ),
        expected_test_surfaces=(
            "unit artifact-capture tests",
            "workflow stage-window seam checks",
            "Batch B confirmation reruns",
        ),
        do_not_use_when=(
            "runtime result is classified as failure and no live artifact is present",
        ),
        overfitting_risks=(
            "treating one fixture's ID shapes as globally authoritative",
        ),
    ),
    SystemContract(
        name="prerequisite replay / runtime materialization",
        owner_layer="s02_probe",
        home_module="api/pipeline/s02_probe/probe_loop.py",
        purpose="Rebuild required same-run state through prerequisite replay before downstream consumer calls execute.",
        consumes=(
            "required preconditions",
            "successful call map",
            "lineage hints",
            "structured fallback args",
            "runtime prerequisite graph",
        ),
        emits=(
            "rehydrated prerequisite successes",
            "fresh replay call args",
            "live lineage hints",
            "prerequisite replay logs",
        ),
        decisions=(
            "replay prerequisite",
            "block placeholder replay",
            "retry blocked prerequisite after live promotion",
            "promote prerequisite success",
        ),
        required_evidence_artifacts=(
            "structured_preflight_prereq logs",
            "rehydrated same-run success traces",
            "promoted prerequisite findings",
        ),
        adjacent_systems=(
            "generalized runtime artifact materializer",
            "dense-context lineage isolation",
            "structured argument scaffolder",
            "prerequisite and state-machine classifier",
        ),
        handoff_invariants=(
            "fresh-lineage chains must prefer live rebuilt state over placeholder replay",
            "non-rehydratable prior successes must not seed same-run truth",
            "successful prerequisite replay must publish enough evidence for the next step",
        ),
        success_signals=(
            "blocked prerequisite chains resume after live promotion",
            "consumer calls receive live reservation, handle, report, quote, or ticket values",
        ),
        failure_signals=(
            "placeholder replay remains unresolved",
            "consumer calls still execute on stale or weak prerequisite state",
        ),
        monitoring_fields=(
            "replay_outcome",
            "forced_live_replay",
            "retry_resumed",
            "promotion_source",
        ),
        expected_test_surfaces=(
            "workflow branch checkpoint tests",
            "targeted stage-window reruns",
            "Batch B overlap checks",
        ),
        do_not_use_when=(
            "state, contract, or capture layers are still too weak to audit replay behavior",
        ),
        overfitting_risks=(
            "encoding one fixture's lifecycle order as a universal replay policy",
        ),
    ),
    SystemContract(
        name="dense-context lineage isolation",
        owner_layer="s02_probe",
        home_module="api/pipeline/s02_probe/probe_loop.py",
        purpose="Protect family-sensitive replay and selection from wrong-family or weak dense-context artifacts.",
        consumes=(
            "lineage hints",
            "successful call map",
            "candidate families",
            "overlap-baseline evidence",
            "seeded prior successes",
        ),
        emits=(
            "lineage admission traces",
            "blocked placeholder metadata",
            "family-safe repaired args",
        ),
        decisions=(
            "admit lineage hint",
            "reject foreign-family artifact",
            "block placeholder replay",
            "prefer fresh same-family replay",
        ),
        required_evidence_artifacts=(
            "lineage_admission param traces",
            "placeholder_params",
            "candidate family selections",
        ),
        adjacent_systems=(
            "generalized runtime artifact materializer",
            "prerequisite replay / runtime materialization",
            "structured argument scaffolder",
            "prerequisite and state-machine classifier",
        ),
        handoff_invariants=(
            "foreign-family artifacts must not outrank same-family live lineage",
            "empty family-sensitive outputs must not clobber live promoted lineage",
            "placeholder values must not terminate fresh-lineage chains",
        ),
        success_signals=(
            "family-sensitive target slots use same-family lineage values",
            "placeholder or foreign-family artifacts are recorded but blocked",
        ),
        failure_signals=(
            "wrong-family artifacts are admitted as trusted replay state",
            "live promoted lineage is overwritten before downstream use",
        ),
        monitoring_fields=(
            "param_trace",
            "expected_family",
            "candidate_family",
            "source_lineage",
            "placeholder_detected",
        ),
        expected_test_surfaces=(
            "lineage repair unit tests",
            "workflow stage-window seam checks",
            "Batch B overlap comparisons",
        ),
        do_not_use_when=(
            "the relevant slot is not family-sensitive or lacks meaningful lineage context",
        ),
        overfitting_risks=(
            "too many special-case family guards turning into a hidden policy engine",
        ),
    ),
    SystemContract(
        name="structured argument scaffolder",
        owner_layer="s02_probe",
        home_module="api/pipeline/s02_probe/probe_loop.py",
        purpose="Build minimal structured or mixed probe arguments from canonical docs, evidence, and safe fallbacks.",
        consumes=(
            "canonical args",
            "parameter metadata",
            "runtime evidence candidates",
            "lineage hints",
        ),
        emits=(
            "structured probe args",
            "field-level argument selection metadata",
            "repaired mixed call args",
        ),
        decisions=(
            "scaffold struct fields",
            "repair scalar aliases",
            "retag mixed-call roles",
        ),
        required_evidence_artifacts=(
            "arg_selection metadata",
            "field-level selection metadata",
        ),
        adjacent_systems=(
            "generalized runtime artifact materializer",
            "dense-context lineage isolation",
            "prerequisite replay / runtime materialization",
            "prerequisite and state-machine classifier",
        ),
        handoff_invariants=(
            "canonical numeric fields must stay numeric after repair",
            "field-level selections must explain how repaired args were chosen",
        ),
        success_signals=(
            "structured calls are built with semantically aligned fields",
            "mixed scalar and struct calls keep coherent field provenance",
        ),
        failure_signals=(
            "numeric fields degrade into identifier-shaped strings",
            "repaired args lose source selection visibility",
        ),
        monitoring_fields=(
            "arg_selection",
            "fields",
            "source",
        ),
        expected_test_surfaces=(
            "unit scaffolder tests",
            "transport struct-shaping checks",
            "workflow branch argument repair checks",
        ),
        do_not_use_when=(
            "a call has no structured or mixed argument surface to scaffold",
        ),
        overfitting_risks=(
            "hardcoding fixture-specific field semantics instead of using generic evidence and docs",
        ),
    ),
    SystemContract(
        name="prerequisite and state-machine classifier",
        owner_layer="s02_probe",
        home_module="api/pipeline/core/evidence_candidates.py",
        purpose="Infer prerequisite DAGs, sequence roles, and execution ordering from invocable metadata and evidence-aware heuristics.",
        consumes=(
            "invocable metadata",
            "doc comments",
            "parameter kinds",
            "id formats",
            "call graph hints",
        ),
        emits=(
            "function role classifications",
            "prerequisite edges",
            "execution-layer hints",
            "per-invocable sequence metadata",
        ),
        decisions=(
            "infer prerequisite edge",
            "classify sequence role",
            "rank execution layer",
            "refuse weak sequence claim",
        ),
        required_evidence_artifacts=(
            "prerequisite_state_machine.json",
            "_required_preconditions metadata",
            "_sequence_role metadata",
        ),
        adjacent_systems=(
            "structured argument scaffolder",
            "prerequisite replay / runtime materialization",
            "runner stage orchestration",
        ),
        handoff_invariants=(
            "weak heuristic sequence claims must not become hard prerequisites",
            "explicit preconditions must survive ordering and reach replay consumers",
            "producer input fields must not be misclassified as produced runtime identifiers",
        ),
        success_signals=(
            "execution layers reflect explicit and high-confidence heuristic prerequisites",
            "probe loop receives stable prerequisite metadata before replay decisions",
        ),
        failure_signals=(
            "lifecycle consumers run without required producer ordering",
            "reservation, report, or quote producers are inferred from weak or contradictory sequence claims",
        ),
        monitoring_fields=(
            "prerequisite_state_machine",
            "_required_preconditions",
            "_sequence_role",
            "_prerequisite_edges",
        ),
        expected_test_surfaces=(
            "prerequisite state-machine classifier tests",
            "curriculum ordering tests",
            "workflow checkpoint seam checks",
        ),
        do_not_use_when=(
            "invocable metadata is too weak to support more than unknown sequence role",
        ),
        overfitting_risks=(
            "turning one fixture's lifecycle vocabulary into a universal prerequisite policy",
        ),
    ),
    SystemContract(
        name="environment dependency classifier",
        owner_layer="s02_probe",
        home_module="api/pipeline/core/evidence_candidates.py",
        purpose="Infer and preserve environment and setup gates so consumers that require approved, licensed, or initialized state do not execute on undeclared preconditions.",
        consumes=(
            "doc comments",
            "function names",
            "parameter metadata",
            "runtime error text",
            "family-labeled ticket and nonce evidence",
        ),
        emits=(
            "environment gate hints",
            "licensed/setup prerequisite edges",
            "ticket and nonce gating metadata",
        ),
        decisions=(
            "infer environment gate",
            "promote licensed setup prerequisite",
            "refuse weak environment dependency claim",
            "prefer family-safe ticket and nonce gating",
        ),
        required_evidence_artifacts=(
            "prerequisite_state_machine.json",
            "_required_preconditions metadata",
            "lineage admission traces for ticket and nonce consumers",
        ),
        adjacent_systems=(
            "prerequisite and state-machine classifier",
            "prerequisite replay / runtime materialization",
            "dense-context lineage isolation",
            "structured argument scaffolder",
        ),
        handoff_invariants=(
            "licensed or setup-gated consumers must not run before approval state is established",
            "ticket and nonce consumers must preserve same-family gating artifacts through replay and repair",
            "environment gate hints must remain explicit enough for downstream replay and observer checks",
        ),
        success_signals=(
            "config approval and sync consumers receive live approved ticket and nonce state",
            "licensed/setup prerequisite edges remain visible in sequence metadata and replay traces",
        ),
        failure_signals=(
            "approval or sync consumers run on placeholder or weak ticket state",
            "licensed/setup gating remains implicit and only appears as late package failure",
        ),
        monitoring_fields=(
            "_required_preconditions",
            "_sequence_reasons",
            "lineage_admission",
            "promoted_hints",
        ),
        expected_test_surfaces=(
            "prerequisite state-machine classifier tests",
            "config ticket and nonce replay tests",
            "Batch B config overlap checks",
        ),
        do_not_use_when=(
            "the target function has no credible setup, approval, license, ticket, or nonce gating signal",
        ),
        overfitting_risks=(
            "turning fixture-specific licensing language into a universal environment policy",
        ),
    ),
    SystemContract(
        name="business-rule and approval classifier",
        owner_layer="s02_probe",
        home_module="api/pipeline/core/evidence_candidates.py",
        purpose="Identify rule-window and approval-gated business transitions so pricing and similar consumers execute only after their required policy state is actually established.",
        consumes=(
            "doc comments",
            "function names",
            "parameter metadata",
            "quote-family evidence",
            "sequence-role hints",
        ),
        emits=(
            "business-rule gating hints",
            "approval-window prerequisite edges",
            "quote-state sequence metadata",
        ),
        decisions=(
            "infer business-rule gate",
            "promote approval-window prerequisite",
            "refuse weak business-rule ordering claim",
            "preserve quote-family state as business-rule input",
        ),
        required_evidence_artifacts=(
            "prerequisite_state_machine.json",
            "_required_preconditions metadata",
            "arg_selection metadata for quote-family consumers",
        ),
        adjacent_systems=(
            "prerequisite and state-machine classifier",
            "prerequisite replay / runtime materialization",
            "dense-context lineage isolation",
            "structured argument scaffolder",
        ),
        handoff_invariants=(
            "business-rule consumers must not outrun required approval-window or quote-state producers",
            "quote-family consumers must not degrade into foreign-family or placeholder state during repair",
            "policy gating hints must remain explicit enough for replay and observer surfaces",
        ),
        success_signals=(
            "pricing quote, state, and seal consumers receive live quote-family state after required approval transitions",
            "rule-window gating survives into replay, repair, and downstream verification traces",
        ),
        failure_signals=(
            "quote-state and seal consumers run without required approval-window state",
            "business-rule gating is only visible as late failure instead of explicit sequence metadata",
        ),
        monitoring_fields=(
            "_required_preconditions",
            "_sequence_role",
            "arg_selection",
            "lineage_admission",
        ),
        expected_test_surfaces=(
            "prerequisite state-machine classifier tests",
            "pricing quote-family repair and replay tests",
            "Batch B pricing overlap checks",
        ),
        do_not_use_when=(
            "the target function has no credible approval, policy, quote-state, or rule-window signal",
        ),
        overfitting_risks=(
            "treating one fixture's approval window names as universal business-rule truth",
        ),
    ),
    SystemContract(
        name="checkpoint and resume coordinator",
        owner_layer="pipeline_core",
        home_module="api/pipeline/core/checkpoint.py",
        purpose="Persist resumable pipeline and campaign state, seed bounded reruns, and enforce stage-boundary reuse without losing trustworthy prior context.",
        consumes=(
            "stage completion state",
            "function findings",
            "evidence candidate snapshots",
            "campaign resume points",
            "checkpoint boundary requests",
        ),
        emits=(
            "pipeline checkpoints",
            "stage snapshots",
            "campaign checkpoints",
            "seeded resume context",
        ),
        decisions=(
            "mark stage complete",
            "seed resumable context",
            "skip completed stage",
            "load checkpoint boundary",
        ),
        required_evidence_artifacts=(
            "checkpoints/latest.json",
            "checkpoints/stage_snapshots/*.json",
            "campaign_checkpoint.json",
        ),
        adjacent_systems=(
            "runner stage orchestration",
            "prerequisite replay / runtime materialization",
            "enrichment verification classifier",
        ),
        handoff_invariants=(
            "resume boundaries must preserve only trustworthy prior state",
            "narrow reruns must distinguish fresh job surfaces from stale terminal job reuse",
            "stage snapshots must remain backward-tolerant for readers",
        ),
        success_signals=(
            "targeted reruns resume from the intended stage boundary",
            "skippable functions stay stable without hiding new regressions",
        ),
        failure_signals=(
            "stale terminal job reuse makes a narrow rerun ambiguous",
            "checkpoint seeding revives weak or outdated state as if it were fresh",
        ),
        monitoring_fields=(
            "source_job_id",
            "checkpoint_recommended_boundary",
            "stage_kpis",
            "resume_points",
        ),
        expected_test_surfaces=(
            "checkpoint unit tests",
            "targeted stage-window reruns",
            "campaign resume tests",
        ),
        do_not_use_when=(
            "the requested rerun surface cannot prove whether a reused job is fresh or stale",
        ),
        overfitting_risks=(
            "treating one campaign's checkpoint layout as the only valid resume shape",
        ),
    ),
    SystemContract(
        name="runner stage orchestration",
        owner_layer="pipeline_runner",
        home_module="api/pipeline/runner.py",
        purpose="Drive stage execution, checkpoint boundaries, service bootstrap, and bounded campaign orchestration with contract-aware skip and resume behavior.",
        consumes=(
            "explore runtime config",
            "stage contracts",
            "pipeline checkpoints",
            "campaign checkpoints",
            "prior session artifacts",
        ),
        emits=(
            "stage execution order",
            "stage_kpis.json",
            "campaign progress updates",
            "seeded runtime context",
        ),
        decisions=(
            "skip stage",
            "resume from boundary",
            "seed prior context",
            "persist stage KPI",
        ),
        required_evidence_artifacts=(
            "stage_kpis.json",
            "campaign polls",
            "checkpoint stage snapshots",
        ),
        adjacent_systems=(
            "checkpoint and resume coordinator",
            "enrichment verification classifier",
            "prerequisite and state-machine classifier",
        ),
        handoff_invariants=(
            "stage dispatch must stay aligned with the canonical stage contract registry",
            "resume boundaries must not silently widen the intended rerun surface",
            "prior-session seeding must preserve trust and comparability metadata",
        ),
        success_signals=(
            "narrow reruns execute only the intended stage surface",
            "campaign progress and stage KPIs stay coherent with checkpoint state",
        ),
        failure_signals=(
            "stage skip or resume choices diverge from the requested run surface",
            "campaign orchestration advances while trust or comparability metadata is incomplete",
        ),
        monitoring_fields=(
            "explore_runtime",
            "stage_kpis",
            "campaign_poll",
            "checkpoint_recommended_boundary",
        ),
        expected_test_surfaces=(
            "runner seeded-findings tests",
            "checkpoint boundary tests",
            "targeted stage-window reruns",
        ),
        do_not_use_when=(
            "API, bridge, or lab health is not confirmed for non-trivial local-first validation",
        ),
        overfitting_risks=(
            "letting one campaign's orchestration shortcuts become universal runner behavior",
        ),
    ),
    SystemContract(
        name="enrichment verification classifier",
        owner_layer="s05_enrichment",
        home_module="api/pipeline/s05_enrichment/verify.py",
        purpose="Verify findings against probe evidence, normalize statuses, and distinguish real functional behavior from transport, handle, and state-drift noise.",
        consumes=(
            "findings",
            "probe log rows",
            "bridge execution results",
            "sentinel map",
            "invocable metadata",
        ),
        emits=(
            "patched findings",
            "verification classifications",
            "rebound handle attempts",
            "verification audit traces",
        ),
        decisions=(
            "normalize status",
            "select strongest probe row",
            "rebind likely handle args",
            "promote or demote verification confidence",
        ),
        required_evidence_artifacts=(
            "verification-report.json",
            "patched findings",
            "probe-log phase selection traces",
        ),
        adjacent_systems=(
            "checkpoint and resume coordinator",
            "runner stage orchestration",
            "prerequisite replay / runtime materialization",
        ),
        handoff_invariants=(
            "bridge transport failures must not be misclassified as functional behavior",
            "best-probe selection must prefer stronger phases over weaker generic rows",
            "handle rebinding must only target semantically likely handle slots",
        ),
        success_signals=(
            "verification distinguishes real state drift from ordinary success",
            "stronger probe rows are selected consistently for the same function family",
        ),
        failure_signals=(
            "transport noise is promoted into functional regression claims",
            "verification patches hide upstream replay or sequencing faults instead of exposing them",
        ),
        monitoring_fields=(
            "verification_report",
            "phase_priority",
            "handle_rebinding",
            "state_drift_count",
        ),
        expected_test_surfaces=(
            "enrichment verification tests",
            "runner seeded-findings tests",
            "Batch B trust and comparability checks",
        ),
        do_not_use_when=(
            "probe evidence is too incomplete to distinguish transport noise from functional behavior",
        ),
        overfitting_risks=(
            "teaching verification to recognize one fixture's handle layout as universal truth",
        ),
    ),
)

validate_system_contracts(SYSTEM_CONTRACTS)

SYSTEM_CONTRACTS_BY_NAME = {contract.name: contract for contract in SYSTEM_CONTRACTS}
_contracts_by_owner_layer: dict[str, list[str]] = defaultdict(list)
for _contract in SYSTEM_CONTRACTS:
    _contracts_by_owner_layer[_contract.owner_layer].append(_contract.name)
SYSTEM_CONTRACTS_BY_OWNER_LAYER: dict[str, tuple[str, ...]] = {
    owner_layer: tuple(names)
    for owner_layer, names in _contracts_by_owner_layer.items()
}

_SEAM_OBSERVER_FAMILIES = {
    "blob_token",
    "handle",
    "nonce",
    "quote_id",
    "report_id",
    "reservation_id",
    "ticket",
    "workflow_handle",
}


def build_system_contract_snapshot(
    contracts: tuple[SystemContract, ...] | None = None,
) -> list[dict[str, Any]]:
    active_contracts = tuple(contracts or SYSTEM_CONTRACTS)
    return [asdict(contract) for contract in active_contracts]


def observe_live_artifact_emission(
    *,
    contract_name: str,
    producer_function: str,
    promoted_hints: dict[str, Any] | None,
    materialization_missing_families: list[str] | None,
) -> list[dict[str, Any]]:
    promoted = dict(promoted_hints or {})
    missing = set(materialization_missing_families or [])
    families = sorted((set(promoted) | missing) & _SEAM_OBSERVER_FAMILIES)
    results: list[dict[str, Any]] = []
    for family in families:
        promoted_value = promoted.get(family)
        emitted = promoted_value not in (None, "")
        missing_family = family in missing
        status = "pass" if emitted and not missing_family else "fail"
        violation = ""
        if status == "fail":
            violation = (
                "expected live family artifact was not emitted for downstream replay"
            )
        likely_fault_scope = "none" if status == "pass" else "local"
        results.append(
            SystemObserverResult(
                observer_id=f"emit:{family}",
                contract_name=contract_name,
                status=status,
                target_function=producer_function,
                summary=f"{family} emission {'succeeded' if status == 'pass' else 'failed'} for {producer_function}",
                expected={"family": family, "emitted_live_artifact": True},
                observed={
                    "promoted_value": promoted_value,
                    "missing_family": missing_family,
                },
                violation=violation,
                likely_fault_scope=likely_fault_scope,
            ).to_dict()
        )
    return results


def observe_lineage_handoff(
    *,
    contract_name: str,
    consumer_function: str,
    consumer_args: dict[str, Any] | None,
    arg_selection: dict[str, Any] | None,
    lineage_hints: dict[str, Any] | None,
    param_lookup: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    args = dict(consumer_args or {})
    selection = dict(arg_selection or {})
    hints = dict(lineage_hints or {})
    params = dict(param_lookup or {})
    results: list[dict[str, Any]] = []
    for param_name, meta in selection.items():
        if not isinstance(meta, dict):
            continue
        param_meta = params.get(param_name)
        if isinstance(param_meta, dict):
            direction = str(param_meta.get("direction") or "").strip().lower()
            if direction == "out":
                continue
        expected_family = str(meta.get("expected_family") or "")
        source_lineage = str(meta.get("source_lineage") or "")
        if (
            expected_family not in _SEAM_OBSERVER_FAMILIES
            or not source_lineage.startswith("lineage_hint.")
        ):
            continue
        expected_value = hints.get(expected_family)
        observed_value = args.get(param_name)
        candidate_family = str(meta.get("candidate_family") or "")
        passed = (
            expected_value not in (None, "")
            and observed_value == expected_value
            and candidate_family == expected_family
        )
        violation = ""
        if not passed:
            violation = (
                "consumer did not preserve the live lineage artifact through replay admission"
            )
        likely_fault_scope = "none"
        if not passed:
            likely_fault_scope = "upstream" if expected_value in (None, "") else "downstream"
        results.append(
            SystemObserverResult(
                observer_id=f"handoff:{expected_family}",
                contract_name=contract_name,
                status="pass" if passed else "fail",
                target_function=consumer_function,
                summary=f"{expected_family} handoff {'held' if passed else 'broke'} for {consumer_function}",
                expected={
                    "family": expected_family,
                    "source_lineage": f"lineage_hint.{expected_family}",
                    "value": expected_value,
                },
                observed={
                    "param_name": param_name,
                    "value": observed_value,
                    "candidate_family": candidate_family,
                    "source_lineage": source_lineage,
                },
                violation=violation,
                likely_fault_scope=likely_fault_scope,
            ).to_dict()
        )
    return results
