from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


CLUSTER_CHECKPOINT_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class ClusterCheckpoint:
    cluster_id: str
    label: str
    owning_scope: str
    active_seam: str
    state_story: str
    adjacent_prerequisite_state_groups: tuple[str, ...]
    function_names: tuple[str, ...]
    producer_functions: tuple[str, ...]
    consumer_functions: tuple[str, ...]
    live_artifact_families: tuple[str, ...]
    satisfied_invariants: tuple[str, ...]
    unresolved_blockers: tuple[str, ...]
    lineage_sources: tuple[str, ...]
    reuse_eligibility: tuple[str, ...]
    adjacent_clusters: tuple[str, ...]
    observer_contracts: tuple[str, ...]
    expected_test_surfaces: tuple[str, ...]
    formation_rules: tuple[str, ...]
    gate_color: str
    latest_trusted_proof_jobs: tuple[str, ...]
    expected_next_move: str
    notes: str


CLUSTER_FORMATION_RULES: tuple[str, ...] = (
    "Cluster functions must share one dominant state story.",
    "Clusters should preserve a bounded producer-consumer chain rather than a whole DLL by default.",
    "Clusters must share a compact artifact vocabulary that can survive dense-context reuse.",
    "Clusters should expose explicit adjacent clusters and reuse boundaries.",
    "Clusters should stay small enough to load as dense context without becoming a mini session dump.",
)


def validate_cluster_checkpoints(checkpoints: tuple[ClusterCheckpoint, ...]) -> None:
    seen: set[str] = set()
    for checkpoint in checkpoints:
        if not checkpoint.cluster_id.strip():
            raise ValueError("cluster checkpoint id must be non-empty")
        if checkpoint.cluster_id in seen:
            raise ValueError(f"duplicate cluster checkpoint: {checkpoint.cluster_id}")
        seen.add(checkpoint.cluster_id)
        for attr_name in (
            "label",
            "owning_scope",
            "active_seam",
            "state_story",
            "gate_color",
            "expected_next_move",
            "notes",
        ):
            if not str(getattr(checkpoint, attr_name) or "").strip():
                raise ValueError(f"{checkpoint.cluster_id}: {attr_name} must be non-empty")
        for attr_name in (
            "adjacent_prerequisite_state_groups",
            "function_names",
            "producer_functions",
            "consumer_functions",
            "live_artifact_families",
            "satisfied_invariants",
            "unresolved_blockers",
            "lineage_sources",
            "reuse_eligibility",
            "adjacent_clusters",
            "observer_contracts",
            "expected_test_surfaces",
            "formation_rules",
        ):
            if not tuple(getattr(checkpoint, attr_name) or ()):
                raise ValueError(f"{checkpoint.cluster_id}: {attr_name} must be non-empty")


FIRST_CLUSTER_CHECKPOINTS: tuple[ClusterCheckpoint, ...] = (
    ClusterCheckpoint(
        cluster_id="workflow_reservation_open_state",
        label="Workflow Reservation/Open/State",
        owning_scope="contoso_workflow",
        active_seam="reservation_id to workflow_handle continuity into workflow state and confirm consumers",
        state_story="Reservation creation establishes the artifact chain required to open fulfillment, derive workflow handle state, and read workflow state safely.",
        adjacent_prerequisite_state_groups=("workflow_reservation_bootstrap",),
        function_names=(
            "WF_CreateReservation",
            "WF_OpenFulfillment",
            "WF_GetWorkflowNonce",
            "WF_GetWorkflowState",
            "WF_ConfirmWorkflow",
        ),
        producer_functions=(
            "WF_CreateReservation",
            "WF_OpenFulfillment",
            "WF_GetWorkflowNonce",
        ),
        consumer_functions=(
            "WF_GetWorkflowState",
            "WF_ConfirmWorkflow",
        ),
        live_artifact_families=(
            "reservation_id",
            "workflow_handle",
            "nonce",
        ),
        satisfied_invariants=(
            "reservation_id must exist before workflow open",
            "workflow_handle must survive producer to consumer handoff",
            "workflow state consumers must not fall back to placeholder handle state",
        ),
        unresolved_blockers=(
            "WF_GetWorkflowState remains overlap-regressed under package density",
        ),
        lineage_sources=(
            "same-run prerequisite replay",
            "runtime artifact materialization",
            "lineage admission traces",
        ),
        reuse_eligibility=(
            "only reuse when workflow_handle and reservation_id lineage are same-run or overlap-trusted",
            "do not reuse placeholder or foreign-family workflow state",
        ),
        adjacent_clusters=(
            "config_approval_license",
            "pricing_quote_lifecycle",
        ),
        observer_contracts=(
            "generalized runtime artifact materializer",
            "prerequisite replay / runtime materialization",
            "dense-context lineage isolation",
        ),
        expected_test_surfaces=(
            "workflow stage-window seam checks",
            "Batch B workflow overlap checks",
        ),
        formation_rules=CLUSTER_FORMATION_RULES,
        gate_color="amber",
        latest_trusted_proof_jobs=(),
        expected_next_move="re-run the workflow state reader and confirm consumer from a trusted reservation/open checkpoint.",
        notes="Current highest-value state continuity cluster for remaining workflow overlap pressure.",
    ),
    ClusterCheckpoint(
        cluster_id="pricing_quote_lifecycle",
        label="Pricing Quote Lifecycle",
        owning_scope="contoso_pricing",
        active_seam="quote_id and nonce continuity through approval-window transitions into quote state and seal consumers",
        state_story="Quote creation, nonce acquisition, approval-window transitions, and final seal/state reads must preserve a coherent quote-family artifact chain.",
        adjacent_prerequisite_state_groups=("pricing_quote_bootstrap",),
        function_names=(
            "PR_BeginQuote",
            "PR_GetQuoteNonce",
            "PR_ApproveRuleWindow",
            "PR_ApplyBundleOverride",
            "PR_GetQuoteState",
            "PR_SealQuote",
        ),
        producer_functions=(
            "PR_BeginQuote",
            "PR_GetQuoteNonce",
            "PR_ApproveRuleWindow",
        ),
        consumer_functions=(
            "PR_ApplyBundleOverride",
            "PR_GetQuoteState",
            "PR_SealQuote",
        ),
        live_artifact_families=(
            "quote_id",
            "nonce",
        ),
        satisfied_invariants=(
            "quote_id must survive approval-window and quote-state transitions",
            "business-rule consumers must not outrun required approval state",
            "quote consumers must not degrade into ticket-like or placeholder state",
        ),
        unresolved_blockers=(
            "PR_ApplyBundleOverride remains overlap-regressed under package density",
            "PR_GetQuoteState remains overlap-regressed under package density",
            "PR_SealQuote remains overlap-regressed under package density",
        ),
        lineage_sources=(
            "same-run prerequisite replay",
            "runtime artifact materialization",
            "arg_selection traces",
        ),
        reuse_eligibility=(
            "only reuse when quote_id lineage is same-family and nonce lineage is trusted",
            "do not reuse quote-family state when approval-window invariant is unresolved",
        ),
        adjacent_clusters=(
            "config_approval_license",
            "workflow_reservation_open_state",
        ),
        observer_contracts=(
            "business-rule and approval classifier",
            "prerequisite replay / runtime materialization",
            "dense-context lineage isolation",
            "structured argument scaffolder",
        ),
        expected_test_surfaces=(
            "pricing stage-window seam checks",
            "Batch B pricing overlap checks",
        ),
        formation_rules=CLUSTER_FORMATION_RULES,
        gate_color="amber",
        latest_trusted_proof_jobs=(),
        expected_next_move="bound the next rerun to quote-state and seal carryover after replaying trusted quote producers.",
        notes="Current largest remaining package-density coordination pocket in Batch B.",
    ),
    ClusterCheckpoint(
        cluster_id="config_approval_license",
        label="Config Approval/License",
        owning_scope="contoso_config",
        active_seam="licensed ticket and nonce continuity into approved-call and sync consumers",
        state_story="Licensed setup, ticket creation, nonce recovery, and approved-call consumers must preserve environment and approval state as explicit gating artifacts.",
        adjacent_prerequisite_state_groups=("config_licensed_ticket_bootstrap",),
        function_names=(
            "CFG_OpenLicensedWindow",
            "CFG_GetLicenseNonce",
            "CFG_ApproveLicensedCall",
            "CFG_RunCustomerSync",
        ),
        producer_functions=(
            "CFG_OpenLicensedWindow",
            "CFG_GetLicenseNonce",
        ),
        consumer_functions=(
            "CFG_ApproveLicensedCall",
            "CFG_RunCustomerSync",
        ),
        live_artifact_families=(
            "ticket",
            "nonce",
        ),
        satisfied_invariants=(
            "approved ticket state must survive into licensed consumers",
            "nonce consumers must not reuse envelope or placeholder ticket state",
            "environment gating must remain explicit rather than only surfacing as package failure",
        ),
        unresolved_blockers=(
            "CFG_ApproveLicensedCall remains overlap-regressed under package density",
            "CFG_RunCustomerSync remains overlap-regressed under package density",
        ),
        lineage_sources=(
            "same-run prerequisite replay",
            "runtime artifact materialization",
            "lineage admission traces",
        ),
        reuse_eligibility=(
            "only reuse when ticket and nonce lineage are trusted and same-family",
            "do not reuse environment state when approval or license gate remains unresolved",
        ),
        adjacent_clusters=(
            "workflow_reservation_open_state",
            "pricing_quote_lifecycle",
        ),
        observer_contracts=(
            "environment dependency classifier",
            "prerequisite replay / runtime materialization",
            "dense-context lineage isolation",
            "structured argument scaffolder",
        ),
        expected_test_surfaces=(
            "config ticket and nonce seam checks",
            "Batch B config overlap checks",
        ),
        formation_rules=CLUSTER_FORMATION_RULES,
        gate_color="amber",
        latest_trusted_proof_jobs=(),
        expected_next_move="confirm ticket and nonce continuity into the licensed consumer lane before broader package confirmation.",
        notes="Current environment-gating cluster for the remaining config overlap regressions.",
    ),
    ClusterCheckpoint(
        cluster_id="reporting_preview_render_export",
        label="Reporting Preview/Render/Export",
        owning_scope="contoso_reporting",
        active_seam="report_id, format, and nonce continuity from report preparation into preview, render, and export readback",
        state_story="Report preparation, format selection, nonce recovery, preview creation, and export surfaces must preserve a coherent report-family artifact chain so rendering and ledger export do not rebuild context from scratch.",
        adjacent_prerequisite_state_groups=("reporting_report_bootstrap",),
        function_names=(
            "RP_PrepareReservationReport",
            "RP_GetReportNonce",
            "RP_SelectFormat",
            "RP_CreatePreview",
            "RP_RenderPreview",
            "RP_ExportLedger",
            "RP_CloseReport",
        ),
        producer_functions=(
            "RP_PrepareReservationReport",
            "RP_GetReportNonce",
            "RP_CreatePreview",
        ),
        consumer_functions=(
            "RP_SelectFormat",
            "RP_RenderPreview",
            "RP_ExportLedger",
            "RP_CloseReport",
        ),
        live_artifact_families=(
            "report_id",
            "format_code",
            "nonce",
        ),
        satisfied_invariants=(
            "report_id must survive from preparation into preview and export consumers",
            "format selection must remain explicit before preview and export consumers run",
            "render and export consumers must not degrade into placeholder or foreign-family report state",
            "preview and close paths must preserve the same report-family lineage",
        ),
        unresolved_blockers=(
            "RP_SelectFormat remains overlap-regressed under package density",
            "RP_ExportLedger remains a dry-run carryover target until bounded report_id reuse proves stable",
        ),
        lineage_sources=(
            "same-run prerequisite replay",
            "runtime artifact materialization",
            "preview/render readback traces",
        ),
        reuse_eligibility=(
            "only reuse when report_id lineage is same-family, format lineage is explicit, and nonce lineage is trusted",
            "do not reuse reporting state when preview/readback observers disagree on the active report family",
        ),
        adjacent_clusters=(
            "workflow_reservation_open_state",
            "pricing_quote_lifecycle",
        ),
        observer_contracts=(
            "preview/render readback observer",
            "prerequisite replay / runtime materialization",
            "structured argument scaffolder",
        ),
        expected_test_surfaces=(
            "reporting format/preview/export seam checks",
            "reporting bounded carryover dry runs",
        ),
        formation_rules=CLUSTER_FORMATION_RULES,
        gate_color="amber",
        latest_trusted_proof_jobs=(),
        expected_next_move="prove report_id and format continuity into render/export readback on a bounded reporting rerun before package-level carryover work.",
        notes="Reporting cluster now includes the format-selection seam because the current Batch B residual breaks before render/export can be trusted.",
    ),
)

validate_cluster_checkpoints(FIRST_CLUSTER_CHECKPOINTS)

CLUSTER_CHECKPOINTS_BY_ID = {
    checkpoint.cluster_id: checkpoint for checkpoint in FIRST_CLUSTER_CHECKPOINTS
}


def infer_cluster_checkpoint_id(focus_functions: list[str] | tuple[str, ...] | None) -> str:
    requested = {
        str(fn_name or "").strip()
        for fn_name in (focus_functions or [])
        if str(fn_name or "").strip()
    }
    if not requested:
        return ""

    matches = [
        checkpoint.cluster_id
        for checkpoint in FIRST_CLUSTER_CHECKPOINTS
        if requested.issubset(set(checkpoint.function_names))
    ]
    if len(matches) != 1:
        return ""
    return matches[0]


def _function_state_value(state: Any, field: str, default: Any = None) -> Any:
    if isinstance(state, dict):
        return state.get(field, default)
    return getattr(state, field, default)


def _function_state_is_trusted(state: Any) -> bool:
    status = str(_function_state_value(state, "status", "") or "").strip().lower()
    working_call = _function_state_value(state, "working_call")
    return status in {"success", "verified_success"} and working_call is not None


def _derive_cluster_gate_color(
    checkpoint: ClusterCheckpoint,
    function_states: dict[str, Any],
) -> str:
    trusted_producers = sum(
        1 for fn_name in checkpoint.producer_functions
        if _function_state_is_trusted(function_states.get(fn_name))
    )
    trusted_functions = sum(
        1 for fn_name in checkpoint.function_names
        if _function_state_is_trusted(function_states.get(fn_name))
    )
    if trusted_producers == 0:
        return "red"
    if trusted_functions == len(checkpoint.function_names) and not checkpoint.unresolved_blockers:
        return "green"
    return checkpoint.gate_color or "amber"


def build_cluster_checkpoint_snapshot(
    checkpoints: tuple[ClusterCheckpoint, ...] | None = None,
    *,
    function_states: dict[str, Any] | None = None,
    source_job_id: str = "",
) -> list[dict[str, object]]:
    active_checkpoints = tuple(checkpoints or FIRST_CLUSTER_CHECKPOINTS)
    function_states = dict(function_states or {})
    rows: list[dict[str, object]] = []
    for checkpoint in active_checkpoints:
        row = json.loads(json.dumps(asdict(checkpoint)))
        row["schema_version"] = CLUSTER_CHECKPOINT_SCHEMA_VERSION
        trusted_cluster = any(
            _function_state_is_trusted(function_states.get(fn_name))
            for fn_name in checkpoint.function_names
        )
        if trusted_cluster and source_job_id:
            row["latest_trusted_proof_jobs"] = [source_job_id]
        row["gate_color"] = _derive_cluster_gate_color(checkpoint, function_states)
        rows.append(row)
    return rows


def backfill_cluster_checkpoint_rows(
    rows: Any,
    *,
    function_states: dict[str, Any] | None = None,
    source_job_id: str = "",
) -> dict[str, dict[str, object]]:
    canonical_rows = {
        row["cluster_id"]: row
        for row in build_cluster_checkpoint_snapshot(
            function_states=function_states,
            source_job_id=source_job_id,
        )
    }
    if not rows:
        return canonical_rows

    if isinstance(rows, list):
        existing_rows = {
            str(row.get("cluster_id") or "").strip(): dict(row)
            for row in rows
            if isinstance(row, dict) and str(row.get("cluster_id") or "").strip()
        }
    elif isinstance(rows, dict):
        existing_rows = {
            str(cluster_id or "").strip(): dict(row)
            for cluster_id, row in rows.items()
            if str(cluster_id or "").strip() and isinstance(row, dict)
        }
    else:
        existing_rows = {}

    merged: dict[str, dict[str, object]] = {}
    for cluster_id, canonical_row in canonical_rows.items():
        current = dict(canonical_row)
        existing = existing_rows.get(cluster_id, {})
        for key, value in existing.items():
            if value not in (None, "", []):
                current[key] = value
        current["schema_version"] = CLUSTER_CHECKPOINT_SCHEMA_VERSION
        for key, value in canonical_row.items():
            if current.get(key) in (None, "", []):
                current[key] = value
        current["gate_color"] = canonical_row["gate_color"]
        proof_jobs: list[str] = []
        for job_id in list(existing.get("latest_trusted_proof_jobs") or []) + list(
            canonical_row.get("latest_trusted_proof_jobs") or []
        ):
            text = str(job_id or "").strip()
            if text and text not in proof_jobs:
                proof_jobs.append(text)
        current["latest_trusted_proof_jobs"] = proof_jobs
        merged[cluster_id] = current
    return merged
