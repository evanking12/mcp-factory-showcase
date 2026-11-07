from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


PREREQUISITE_STATE_GROUP_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class PrerequisiteStateGroup:
    group_id: str
    label: str
    owning_scope: str
    bounded_purpose: str
    member_functions: tuple[str, ...]
    exported_artifact_families: tuple[str, ...]
    satisfied_invariants: tuple[str, ...]
    downstream_clusters: tuple[str, ...]
    observer_contracts: tuple[str, ...]
    expected_test_surfaces: tuple[str, ...]
    gate_color: str
    latest_trusted_proof_jobs: tuple[str, ...]
    expected_next_move: str
    notes: str


def validate_prerequisite_state_groups(groups: tuple[PrerequisiteStateGroup, ...]) -> None:
    seen: set[str] = set()
    for group in groups:
        if not group.group_id.strip():
            raise ValueError("prerequisite state group id must be non-empty")
        if group.group_id in seen:
            raise ValueError(f"duplicate prerequisite state group: {group.group_id}")
        seen.add(group.group_id)
        for attr_name in (
            "label",
            "owning_scope",
            "bounded_purpose",
            "gate_color",
            "expected_next_move",
            "notes",
        ):
            if not str(getattr(group, attr_name) or "").strip():
                raise ValueError(f"{group.group_id}: {attr_name} must be non-empty")
        for attr_name in (
            "member_functions",
            "exported_artifact_families",
            "satisfied_invariants",
            "downstream_clusters",
            "observer_contracts",
            "expected_test_surfaces",
        ):
            if not tuple(getattr(group, attr_name) or ()):
                raise ValueError(f"{group.group_id}: {attr_name} must be non-empty")


FIRST_PREREQUISITE_STATE_GROUPS: tuple[PrerequisiteStateGroup, ...] = (
    PrerequisiteStateGroup(
        group_id="workflow_reservation_bootstrap",
        label="Workflow Reservation Bootstrap",
        owning_scope="contoso_workflow",
        bounded_purpose="Establish reservation, fulfillment-open, and nonce state required before workflow state consumers can be trusted.",
        member_functions=(
            "WF_CreateReservation",
            "WF_OpenFulfillment",
            "WF_GetWorkflowNonce",
        ),
        exported_artifact_families=(
            "reservation_id",
            "workflow_handle",
            "nonce",
        ),
        satisfied_invariants=(
            "reservation_id must exist before workflow open",
            "workflow_handle must survive into state readers",
            "nonce must remain same-family before confirm consumers run",
        ),
        downstream_clusters=("workflow_reservation_open_state",),
        observer_contracts=(
            "prerequisite replay / runtime materialization",
            "dense-context lineage isolation",
        ),
        expected_test_surfaces=(
            "workflow stage-window seam checks",
            "workflow bounded checkpoint reruns",
        ),
        gate_color="amber",
        latest_trusted_proof_jobs=(),
        expected_next_move="replay trusted reservation bootstrap state before workflow state confirmation.",
        notes="Prerequisite-state group for workflow continuity before consumer confirmation.",
    ),
    PrerequisiteStateGroup(
        group_id="pricing_quote_bootstrap",
        label="Pricing Quote Bootstrap",
        owning_scope="contoso_pricing",
        bounded_purpose="Establish quote, nonce, and approval-window state required before quote consumers can be trusted.",
        member_functions=(
            "PR_BeginQuote",
            "PR_GetQuoteNonce",
            "PR_ApproveRuleWindow",
        ),
        exported_artifact_families=(
            "quote_id",
            "nonce",
        ),
        satisfied_invariants=(
            "quote_id must exist before quote consumers run",
            "approval-window state must remain explicit before bundle override or seal consumers",
            "nonce lineage must remain same-family before downstream quote reads",
        ),
        downstream_clusters=("pricing_quote_lifecycle",),
        observer_contracts=(
            "prerequisite replay / runtime materialization",
            "business-rule and approval classifier",
        ),
        expected_test_surfaces=(
            "pricing stage-window seam checks",
            "pricing bounded carryover reruns",
        ),
        gate_color="amber",
        latest_trusted_proof_jobs=(),
        expected_next_move="reuse trusted quote bootstrap state before quote consumer carryover attempts.",
        notes="Prerequisite-state group for pricing quote continuity ahead of consumer replay.",
    ),
    PrerequisiteStateGroup(
        group_id="config_licensed_ticket_bootstrap",
        label="Config Licensed Ticket Bootstrap",
        owning_scope="contoso_config",
        bounded_purpose="Establish environment, customer binding, licensed window, nonce, and approved-call state required before config sync consumers can be trusted.",
        member_functions=(
            "CFG_SetupEnvironment",
            "CFG_BindCustomer",
            "CFG_OpenLicensedWindow",
            "CFG_GetLicenseNonce",
            "CFG_ApproveLicensedCall",
        ),
        exported_artifact_families=(
            "environment_state",
            "customer_id",
            "ticket",
            "nonce",
        ),
        satisfied_invariants=(
            "environment setup must complete before customer-bound config consumers run",
            "customer binding must remain explicit before licensed window and sync consumers run",
            "ticket state must remain explicit before sync consumers run",
            "nonce lineage must remain same-family across approval and sync consumers",
            "approved-call state must not degrade into placeholder ticket state",
        ),
        downstream_clusters=("config_approval_license",),
        observer_contracts=(
            "prerequisite replay / runtime materialization",
            "environment dependency classifier",
        ),
        expected_test_surfaces=(
            "config environment, ticket, and nonce seam checks",
            "config bounded floor-to-ceiling reruns",
        ),
        gate_color="amber",
        latest_trusted_proof_jobs=(),
        expected_next_move="reuse environment, customer binding, and licensed ticket bootstrap state before the config sync ceiling is attempted.",
        notes="Primary prerequisite-state group for the first floor-to-ceiling live lane, including the lower-floor setup truth that must be preserved before sync reruns are honest.",
    ),
    PrerequisiteStateGroup(
        group_id="reporting_report_bootstrap",
        label="Reporting Report Bootstrap",
        owning_scope="contoso_reporting",
        bounded_purpose="Establish report, nonce, and preview state required before render and export consumers can be trusted.",
        member_functions=(
            "RP_PrepareReservationReport",
            "RP_GetReportNonce",
            "RP_CreatePreview",
        ),
        exported_artifact_families=(
            "report_id",
            "nonce",
        ),
        satisfied_invariants=(
            "report_id must exist before render and export consumers run",
            "preview state must preserve the same report-family lineage",
            "nonce lineage must remain explicit before export readback",
        ),
        downstream_clusters=("reporting_preview_render_export",),
        observer_contracts=(
            "prerequisite replay / runtime materialization",
            "preview/render readback observer",
        ),
        expected_test_surfaces=(
            "reporting preview/export seam checks",
            "reporting bounded carryover dry runs",
        ),
        gate_color="amber",
        latest_trusted_proof_jobs=(),
        expected_next_move="reuse report bootstrap state before export and close consumers are revisited.",
        notes="Calmer prerequisite-state group used to validate schema reuse outside the config lane.",
    ),
)

validate_prerequisite_state_groups(FIRST_PREREQUISITE_STATE_GROUPS)

PREREQUISITE_STATE_GROUPS_BY_ID = {
    group.group_id: group for group in FIRST_PREREQUISITE_STATE_GROUPS
}


def _function_state_value(state: Any, field: str, default: Any = None) -> Any:
    if isinstance(state, dict):
        return state.get(field, default)
    return getattr(state, field, default)


def _function_state_is_trusted(state: Any) -> bool:
    status = str(_function_state_value(state, "status", "") or "").strip().lower()
    working_call = _function_state_value(state, "working_call")
    return status in {"success", "verified_success"} and working_call is not None


def _derive_group_gate_color(
    group: PrerequisiteStateGroup,
    function_states: dict[str, Any],
) -> str:
    trusted = sum(
        1 for fn_name in group.member_functions
        if _function_state_is_trusted(function_states.get(fn_name))
    )
    if trusted == 0:
        return "red"
    if trusted == len(group.member_functions):
        return "green"
    return group.gate_color or "amber"


def build_prerequisite_state_group_snapshot(
    groups: tuple[PrerequisiteStateGroup, ...] | None = None,
    *,
    function_states: dict[str, Any] | None = None,
    source_job_id: str = "",
) -> list[dict[str, object]]:
    active_groups = tuple(groups or FIRST_PREREQUISITE_STATE_GROUPS)
    function_states = dict(function_states or {})
    rows: list[dict[str, object]] = []
    for group in active_groups:
        row = json.loads(json.dumps(asdict(group)))
        row["schema_version"] = PREREQUISITE_STATE_GROUP_SCHEMA_VERSION
        trusted_group = any(
            _function_state_is_trusted(function_states.get(fn_name))
            for fn_name in group.member_functions
        )
        if trusted_group and source_job_id:
            row["latest_trusted_proof_jobs"] = [source_job_id]
        row["gate_color"] = _derive_group_gate_color(group, function_states)
        rows.append(row)
    return rows


def backfill_prerequisite_state_group_rows(
    rows: Any,
    *,
    function_states: dict[str, Any] | None = None,
    source_job_id: str = "",
) -> dict[str, dict[str, object]]:
    canonical_rows = {
        row["group_id"]: row
        for row in build_prerequisite_state_group_snapshot(
            function_states=function_states,
            source_job_id=source_job_id,
        )
    }
    if not rows:
        return canonical_rows

    if isinstance(rows, list):
        existing_rows = {
            str(row.get("group_id") or "").strip(): dict(row)
            for row in rows
            if isinstance(row, dict) and str(row.get("group_id") or "").strip()
        }
    elif isinstance(rows, dict):
        existing_rows = {
            str(group_id or "").strip(): dict(row)
            for group_id, row in rows.items()
            if str(group_id or "").strip() and isinstance(row, dict)
        }
    else:
        existing_rows = {}

    merged: dict[str, dict[str, object]] = {}
    for group_id, canonical_row in canonical_rows.items():
        current = dict(canonical_row)
        existing = existing_rows.get(group_id, {})
        for key, value in existing.items():
            if value not in (None, "", []):
                current[key] = value
        current["schema_version"] = PREREQUISITE_STATE_GROUP_SCHEMA_VERSION
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
        merged[group_id] = current
    return merged
