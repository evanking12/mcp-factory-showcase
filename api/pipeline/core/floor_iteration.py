from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from api.pipeline.core.cluster_checkpoint import (
    CLUSTER_CHECKPOINTS_BY_ID,
    infer_cluster_checkpoint_id,
)
from api.pipeline.core.finding_status import normalize_status
from api.pipeline.core.prerequisite_state_groups import PREREQUISITE_STATE_GROUPS_BY_ID


FLOOR_CONTRACT_SCHEMA_VERSION = "1.0.0"
PACKAGE_FLOOR_EVIDENCE_CLASSES = (
    "valid_frontier_rehearsal",
    "overlap_comparable_confirmation",
    "non_comparable_package_run",
)


@dataclass(frozen=True)
class FloorContract:
    floor_scope: str
    summary: str
    allowed_seed_sources: tuple[str, ...]
    preserved_statuses: tuple[str, ...]
    observer_contracts: tuple[str, ...]
    exported_artifacts: tuple[str, ...]
    stop_conditions: tuple[str, ...]


@dataclass(frozen=True)
class FloorPlan:
    schema_version: str
    iteration_mode: str
    iteration_index: int
    floor_scope: str
    cluster_checkpoint_id: str = ""
    prerequisite_state_group_ids: tuple[str, ...] = ()
    ceiling_functions: tuple[str, ...] = ()
    preserved_lower_floor_functions: tuple[str, ...] = ()
    seed_function_allowlist: tuple[str, ...] = ()
    protected_functions: tuple[str, ...] = ()
    root_ceiling_functions: tuple[str, ...] = ()
    imported_dependency_classes: tuple[str, ...] = ()
    observer_contracts: tuple[str, ...] = ()
    stop_gates: tuple[str, ...] = ()
    cycle_focus_functions: tuple[str, ...] = ()
    ceiling_dependency_map: dict[str, list[str]] = field(default_factory=dict)
    prerequisite_state_groups: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FloorIterationState:
    schema_version: str
    iteration_mode: str
    iteration_index: int
    floor_scope: str
    previous_ceiling_functions: tuple[str, ...]
    next_ceiling_functions: tuple[str, ...]
    preserved_lower_floor_functions: tuple[str, ...]
    reopened_functions: tuple[str, ...]
    ceiling_shrank: bool
    localized_more: bool
    contradiction_count: int
    carryover_status: str
    status: str
    observer_verdicts: dict[str, Any]
    next_cycle_recommendation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _prerequisite_group_gate_color(
    row: dict[str, Any],
    states: dict[str, dict[str, Any]],
) -> str:
    members = [
        str(fn_name).strip()
        for fn_name in list((row or {}).get("member_functions") or [])
        if str(fn_name).strip()
    ]
    if not members:
        return "red"
    trusted = sum(1 for fn_name in members if _row_is_preservable_success(states.get(fn_name)))
    if trusted == 0:
        return "red"
    if trusted == len(members):
        return "green"
    return "amber"


def _first_broken_handoff_ceiling(
    plan: FloorPlan,
    states: dict[str, dict[str, Any]],
) -> tuple[list[str], str]:
    for ceiling_name in plan.ceiling_functions:
        for group_id in list(plan.ceiling_dependency_map.get(ceiling_name) or []):
            row = next(
                (
                    candidate
                    for candidate in list(plan.prerequisite_state_groups or [])
                    if str((candidate or {}).get("group_id") or "").strip() == str(group_id).strip()
                ),
                None,
            )
            if not isinstance(row, dict):
                continue
            for fn_name in list(row.get("member_functions") or []):
                text = str(fn_name or "").strip()
                if text and not _row_is_preservable_success(states.get(text)):
                    return [text], str(group_id).strip()
    return [], ""


FLOOR_CONTRACTS: tuple[FloorContract, ...] = (
    FloorContract(
        floor_scope="ground",
        summary="Preserve reusable producer, environment, and read-surface truth for later floors.",
        allowed_seed_sources=("checkpoint_resume", "prior_session"),
        preserved_statuses=("success", "verified_success"),
        observer_contracts=(
            "truth-quality gate",
            "prerequisite replay / runtime materialization",
        ),
        exported_artifacts=(
            "floor_plan.json",
            "prerequisite_state_groups.json",
            "ceiling_frontier.json",
            "floor_iteration_state.json",
        ),
        stop_conditions=(
            "ceiling_stagnated",
            "contradiction_growth",
            "reopened_preserved_truth",
        ),
    ),
    FloorContract(
        floor_scope="cluster",
        summary="Preserve coherent local seam truth and narrow the active ceiling to unresolved cluster consumers.",
        allowed_seed_sources=("checkpoint_resume", "prior_session"),
        preserved_statuses=("success", "verified_success"),
        observer_contracts=(
            "cluster checkpoint observer",
            "prerequisite replay / runtime materialization",
            "dense-context lineage isolation",
        ),
        exported_artifacts=(
            "floor_plan.json",
            "prerequisite_state_groups.json",
            "ceiling_frontier.json",
            "floor_iteration_state.json",
        ),
        stop_conditions=(
            "ceiling_stagnated",
            "contradiction_growth",
            "reopened_preserved_truth",
        ),
    ),
    FloorContract(
        floor_scope="composition",
        summary="Preserve lower-floor truth while auditing composition and carryover failures.",
        allowed_seed_sources=("checkpoint_resume", "prior_session"),
        preserved_statuses=("success", "verified_success"),
        observer_contracts=(
            "cluster checkpoint observer",
            "carryover observer",
            "business_object_continuity",
        ),
        exported_artifacts=(
            "floor_plan.json",
            "prerequisite_state_groups.json",
            "ceiling_frontier.json",
            "floor_iteration_state.json",
        ),
        stop_conditions=(
            "ceiling_stagnated",
            "contradiction_growth",
            "reopened_preserved_truth",
            "package_confirmation_required",
        ),
    ),
    FloorContract(
        floor_scope="package",
        summary="Preserve imported lower-floor truth while restricting package work to the active frontier and package-level observers.",
        allowed_seed_sources=("checkpoint_resume", "prior_session"),
        preserved_statuses=("success", "verified_success"),
        observer_contracts=(
            "package frontier planner",
            "carryover observer",
            "campaign cohesion",
            "business_object_continuity",
        ),
        exported_artifacts=(
            "package-frontier-plan.json",
            "campaign-truth.json",
            "campaign-cohesion-report.json",
            "campaign-attribution-report.json",
        ),
        stop_conditions=(
            "ceiling_stagnated",
            "contradiction_growth",
            "reopened_preserved_truth",
            "package_confirmation_required",
        ),
    ),
)

FLOOR_CONTRACTS_BY_SCOPE = {
    contract.floor_scope: contract for contract in FLOOR_CONTRACTS
}


def normalize_iteration_mode(value: str | None) -> str:
    return "floor_to_ceiling" if str(value or "").strip().lower() == "floor_to_ceiling" else "single_pass"


def normalize_floor_scope(value: str | None) -> str:
    scope = str(value or "").strip().lower()
    return scope if scope in FLOOR_CONTRACTS_BY_SCOPE else "cluster"


def classify_package_floor_evidence(
    *,
    baseline_contract_present: bool,
    active_frontier_defined: bool,
    imported_lower_floor_truth_recorded: bool,
    comparable_profile_consistent: bool,
    run_valid_green: bool,
) -> str:
    if not run_valid_green or not active_frontier_defined or not imported_lower_floor_truth_recorded:
        return "non_comparable_package_run"
    if baseline_contract_present and comparable_profile_consistent:
        return "overlap_comparable_confirmation"
    return "valid_frontier_rehearsal"


def _row_is_success(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    status = normalize_status(row.get("status_canonical") or row.get("status"))
    return status in {"success", "verified_success"} and bool(row.get("working_call"))


def _row_is_preservable_success(row: dict[str, Any] | None) -> bool:
    if not _row_is_success(row):
        return False
    if isinstance(row, dict) and "reusable_truth_eligible" in row:
        return bool(row.get("reusable_truth_eligible"))
    return True


def _checkpoint_function_state_map(checkpoint: Any) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for fn_name, fc in dict(getattr(checkpoint, "functions", {}) or {}).items():
        states[str(fn_name)] = {
            "status": getattr(fc, "status", ""),
            "working_call": getattr(fc, "working_call", None),
        }
    return states


def _latest_findings_by_function(rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        fn_name = str(row.get("function") or "").strip()
        if fn_name:
            latest[fn_name] = dict(row)
    return latest


def _merged_states(checkpoint: Any, current_findings: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    states = _checkpoint_function_state_map(checkpoint)
    for fn_name, row in _latest_findings_by_function(current_findings).items():
        states[fn_name] = row
    return states


def _default_prerequisite_groups(
    cluster_id: str,
    runtime_group_ids: list[str] | tuple[str, ...] | None,
    checkpoint: Any,
) -> list[str]:
    explicit = [str(group_id).strip() for group_id in (runtime_group_ids or []) if str(group_id).strip()]
    if explicit:
        return explicit
    cluster_row = dict((getattr(checkpoint, "cluster_checkpoints", {}) or {}).get(cluster_id) or {})
    checkpoint_groups = [
        str(group_id).strip()
        for group_id in list(cluster_row.get("adjacent_prerequisite_state_groups") or [])
        if str(group_id).strip()
    ]
    if checkpoint_groups:
        return checkpoint_groups
    canonical = CLUSTER_CHECKPOINTS_BY_ID.get(cluster_id)
    if canonical is None:
        return []
    return [
        str(group_id).strip()
        for group_id in list(getattr(canonical, "adjacent_prerequisite_state_groups", ()) or ())
        if str(group_id).strip()
    ]


def _default_ceiling_functions(
    floor_scope: str,
    cluster_id: str,
    runtime_ceiling: list[str] | tuple[str, ...] | None,
    runtime_focus: list[str] | tuple[str, ...] | None,
    states: dict[str, dict[str, Any]],
) -> list[str]:
    explicit = [str(fn_name).strip() for fn_name in (runtime_ceiling or []) if str(fn_name).strip()]
    if explicit:
        return explicit
    canonical = CLUSTER_CHECKPOINTS_BY_ID.get(cluster_id)
    if canonical is not None:
        candidates = list(canonical.producer_functions) if floor_scope == "ground" else list(canonical.consumer_functions)
        unresolved = [fn_name for fn_name in candidates if not _row_is_success(states.get(fn_name))]
        if unresolved:
            return unresolved
        unresolved_cluster = [
            fn_name for fn_name in canonical.function_names
            if not _row_is_success(states.get(fn_name))
        ]
        if unresolved_cluster:
            return unresolved_cluster
    return [str(fn_name).strip() for fn_name in (runtime_focus or []) if str(fn_name).strip()]


def _dedupe_nonempty(values: list[str] | tuple[str, ...] | None) -> list[str]:
    ordered: list[str] = []
    for value in list(values or []):
        text = str(value or "").strip()
        if text and text not in ordered:
            ordered.append(text)
    return ordered


def build_floor_plan(
    runtime: Any,
    checkpoint: Any,
    *,
    current_findings: list[dict[str, Any]] | None = None,
) -> FloorPlan | None:
    iteration_mode = normalize_iteration_mode(getattr(runtime, "iteration_mode", "single_pass"))
    if iteration_mode != "floor_to_ceiling":
        return None

    cluster_id = str(getattr(runtime, "cluster_checkpoint_id", "") or "").strip()
    if not cluster_id:
        cluster_id = infer_cluster_checkpoint_id(
            list(getattr(runtime, "ceiling_functions", []) or [])
            or list(getattr(runtime, "focus_functions", []) or [])
        )
    if not cluster_id:
        return None

    floor_scope = normalize_floor_scope(getattr(runtime, "floor_scope", "cluster"))
    contract = FLOOR_CONTRACTS_BY_SCOPE[floor_scope]
    iteration_index = max(1, int(getattr(runtime, "iteration_index", 1) or 1))
    states = _merged_states(checkpoint, current_findings)
    prerequisite_group_ids = _default_prerequisite_groups(
        cluster_id,
        getattr(runtime, "prerequisite_state_group_ids", []) or [],
        checkpoint,
    )
    ceiling_functions = _default_ceiling_functions(
        floor_scope,
        cluster_id,
        getattr(runtime, "ceiling_functions", []) or [],
        getattr(runtime, "focus_functions", []) or [],
        states,
    )
    root_ceiling_functions = [
        str(fn_name).strip()
        for fn_name in list(getattr(runtime, "ceiling_origin_functions", []) or [])
        if str(fn_name).strip()
    ]
    if not root_ceiling_functions:
        root_ceiling_functions = list(ceiling_functions)

    canonical = CLUSTER_CHECKPOINTS_BY_ID.get(cluster_id)
    cluster_functions = list(canonical.function_names) if canonical is not None else []
    prerequisite_rows: list[dict[str, Any]] = []
    prerequisite_functions: list[str] = []
    for group_id in prerequisite_group_ids:
        row = dict((getattr(checkpoint, "prerequisite_state_groups", {}) or {}).get(group_id) or {})
        if not row:
            canonical_group = PREREQUISITE_STATE_GROUPS_BY_ID.get(group_id)
            if canonical_group is not None:
                row = {
                    **asdict(canonical_group),
                    "schema_version": "1.0.0",
                }
        if row:
            prerequisite_rows.append(row)
            for fn_name in list(row.get("member_functions") or []):
                text = str(fn_name or "").strip()
                if text and text not in prerequisite_functions:
                    prerequisite_functions.append(text)

    preserved_candidates = list(prerequisite_functions)
    if canonical is not None:
        for fn_name in canonical.producer_functions:
            text = str(fn_name or "").strip()
            if text and text not in preserved_candidates:
                preserved_candidates.append(text)
    elif not preserved_candidates:
        preserved_candidates = _dedupe_nonempty(cluster_functions)
    preserved = [
        fn_name for fn_name in preserved_candidates
        if fn_name not in ceiling_functions and _row_is_preservable_success(states.get(fn_name))
    ]
    observer_contracts: list[str] = list(contract.observer_contracts)
    if canonical is not None:
        for contract_name in canonical.observer_contracts:
            if contract_name not in observer_contracts:
                observer_contracts.append(contract_name)
    for row in prerequisite_rows:
        for contract_name in list(row.get("observer_contracts") or []):
            text = str(contract_name or "").strip()
            if text and text not in observer_contracts:
                observer_contracts.append(text)

    imported_dependency_classes = (
        ("business_object_continuity",)
        if list(getattr(runtime, "cross_dll_prior_job_ids", []) or [])
        else ()
    )
    return FloorPlan(
        schema_version=FLOOR_CONTRACT_SCHEMA_VERSION,
        iteration_mode=iteration_mode,
        iteration_index=iteration_index,
        floor_scope=floor_scope,
        cluster_checkpoint_id=cluster_id,
        prerequisite_state_group_ids=tuple(prerequisite_group_ids),
        ceiling_functions=tuple(ceiling_functions),
        preserved_lower_floor_functions=tuple(preserved),
        seed_function_allowlist=tuple(preserved),
        protected_functions=tuple(preserved),
        root_ceiling_functions=tuple(root_ceiling_functions),
        imported_dependency_classes=tuple(imported_dependency_classes),
        observer_contracts=tuple(observer_contracts),
        stop_gates=tuple(contract.stop_conditions),
        cycle_focus_functions=tuple(ceiling_functions),
        ceiling_dependency_map={fn_name: list(prerequisite_group_ids) for fn_name in ceiling_functions},
        prerequisite_state_groups=prerequisite_rows,
    )


def build_floor_iteration_state(
    plan: FloorPlan,
    checkpoint: Any,
    *,
    current_findings: list[dict[str, Any]] | None = None,
    previous_contradiction_count: int = 0,
) -> FloorIterationState:
    states = _merged_states(checkpoint, current_findings)
    next_ceiling = [
        fn_name for fn_name in plan.ceiling_functions
        if not _row_is_success(states.get(fn_name))
    ]
    broken_handoff_ceiling, broken_handoff_group = _first_broken_handoff_ceiling(plan, states)
    if (
        next_ceiling
        and tuple(next_ceiling) == tuple(plan.ceiling_functions)
        and broken_handoff_ceiling
        and tuple(broken_handoff_ceiling) != tuple(next_ceiling)
    ):
        next_ceiling = list(broken_handoff_ceiling)
    root_ceiling = [
        fn_name for fn_name in list(plan.root_ceiling_functions or ())
        if str(fn_name).strip()
    ]
    if not root_ceiling:
        root_ceiling = list(plan.ceiling_functions)
    if not next_ceiling and tuple(plan.ceiling_functions) != tuple(root_ceiling):
        unresolved_root = [
            fn_name for fn_name in root_ceiling
            if not _row_is_success(states.get(fn_name))
        ]
        if unresolved_root:
            next_ceiling = unresolved_root
    reopened = [
        fn_name for fn_name in plan.protected_functions
        if states.get(fn_name) and not _row_is_preservable_success(states.get(fn_name))
    ]
    contradiction_count = max(0, int(previous_contradiction_count or 0))
    ceiling_shrank = len(next_ceiling) < len(plan.ceiling_functions)
    localized_more = ceiling_shrank or (
        len(next_ceiling) <= 1 and tuple(next_ceiling) != tuple(plan.ceiling_functions)
    )
    carryover_status = "pass" if not next_ceiling else ("warn" if localized_more else "fail")
    first_broken_handoff_by_function: dict[str, dict[str, str]] = {}
    if broken_handoff_group:
        affected = _dedupe_nonempty(next_ceiling or root_ceiling or plan.ceiling_functions)
        for fn_name in affected:
            first_broken_handoff_by_function[fn_name] = {
                "group_id": broken_handoff_group,
                "layer": "prerequisite_state",
            }

    if reopened:
        status = "stop"
        recommendation = "reopened_preserved_truth"
    elif contradiction_count > int(previous_contradiction_count or 0):
        status = "stop"
        recommendation = "contradiction_growth"
    elif not next_ceiling:
        status = "done"
        recommendation = "ceiling_resolved"
    elif (
        not [
            fn_name for fn_name in plan.ceiling_functions
            if not _row_is_success(states.get(fn_name))
        ]
        and tuple(plan.ceiling_functions) != tuple(root_ceiling)
    ):
        status = "loop_again"
        recommendation = "resume_root_ceiling"
    elif ceiling_shrank or localized_more:
        status = "loop_again"
        recommendation = "continue_narrow_ceiling"
    else:
        status = "stop"
        recommendation = "ceiling_stagnated"

    return FloorIterationState(
        schema_version=FLOOR_CONTRACT_SCHEMA_VERSION,
        iteration_mode=plan.iteration_mode,
        iteration_index=plan.iteration_index,
        floor_scope=plan.floor_scope,
        previous_ceiling_functions=tuple(plan.ceiling_functions),
        next_ceiling_functions=tuple(next_ceiling),
        preserved_lower_floor_functions=tuple(plan.preserved_lower_floor_functions),
        reopened_functions=tuple(reopened),
        ceiling_shrank=ceiling_shrank,
        localized_more=localized_more,
        contradiction_count=contradiction_count,
        carryover_status=carryover_status,
        status=status,
        observer_verdicts={
            "carryover_status": carryover_status,
            "reopened_functions": list(reopened),
            "ceiling_dependency_map": dict(plan.ceiling_dependency_map),
            "preserved_lower_floor_functions": list(plan.preserved_lower_floor_functions),
            "first_broken_handoff_group": broken_handoff_group,
            "first_broken_handoff_layer": "prerequisite_state" if broken_handoff_group else "",
            "first_broken_handoff_by_function": first_broken_handoff_by_function,
            "root_ceiling_functions": list(root_ceiling),
        },
        next_cycle_recommendation={
            "status": recommendation,
            "focus_functions": list(next_ceiling),
            "skip_to_stage": "s02_probe" if next_ceiling else "",
            "skip_to_stage_reason": "floor_to_ceiling_iteration" if next_ceiling else "",
            "floor_scope": plan.floor_scope,
            "ceiling_origin_functions": list(root_ceiling),
        },
    )


def evaluate_floor_broadening_gate(
    plan: FloorPlan,
    checkpoint: Any,
    *,
    current_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    states = _merged_states(checkpoint, current_findings)
    blocked_groups: list[str] = []
    group_gates: dict[str, str] = {}
    for row in list(plan.prerequisite_state_groups or []):
        group_id = str((row or {}).get("group_id") or "").strip()
        if not group_id:
            continue
        gate_color = _prerequisite_group_gate_color(row, states)
        group_gates[group_id] = gate_color
        if gate_color != "green":
            blocked_groups.append(group_id)
    preserved = [
        fn_name
        for fn_name in list(plan.preserved_lower_floor_functions or [])
        if _row_is_preservable_success(states.get(fn_name))
    ]
    allow_broadening = not blocked_groups and bool(preserved or not plan.prerequisite_state_group_ids)
    if blocked_groups:
        reason = "prerequisite_state_groups_untrusted"
    elif not preserved and plan.prerequisite_state_group_ids:
        reason = "no_preserved_lower_floor_truth"
    else:
        reason = "broadening_allowed"
    return {
        "allow_broadening": allow_broadening,
        "reason": reason,
        "blocked_groups": blocked_groups,
        "group_gates": group_gates,
        "preserved_lower_floor_functions": preserved,
    }
