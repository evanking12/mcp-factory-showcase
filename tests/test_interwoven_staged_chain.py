from __future__ import annotations

import json
from pathlib import Path

from api.pipeline.core.cluster_checkpoint import CLUSTER_CHECKPOINTS_BY_ID
from api.pipeline.core.interwoven_artifacts import InterwovenStagedChainReport
from api.pipeline.core.interwoven_observers import (
    INTERWOVEN_OBSERVER_NAMES,
    build_staged_chain_ordering_plausibility_observer,
)
from api.pipeline.core.prerequisite_state_groups import PREREQUISITE_STATE_GROUPS_BY_ID


ROOT = Path(__file__).resolve().parent.parent


def _load_manifest(fixture_name: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / fixture_name / "truth_manifest.json").read_text(encoding="utf-8"))


def test_staged_chain_report_round_trips_for_workflow_chain() -> None:
    workflow = _load_manifest("contoso_workflow")
    assert PREREQUISITE_STATE_GROUPS_BY_ID["workflow_reservation_bootstrap"].group_id == "workflow_reservation_bootstrap"
    assert CLUSTER_CHECKPOINTS_BY_ID["workflow_reservation_open_state"].cluster_id == "workflow_reservation_open_state"
    assert any(item["name"] == "WF_CommitShipment" for item in workflow["functions"])

    report = InterwovenStagedChainReport(
        chain_id="workflow_handle_nonce_commit_chain",
        ordered_steps=(
            "WF_CreateReservation",
            "WF_OpenFulfillment",
            "WF_GetWorkflowNonce",
            "WF_ConfirmWorkflow",
            "WF_CommitShipment",
        ),
        required_state_tokens=("reservation_id", "workflow_handle", "nonce"),
        producer_steps=("WF_CreateReservation", "WF_OpenFulfillment", "WF_GetWorkflowNonce"),
        consumer_steps=("WF_ConfirmWorkflow", "WF_CommitShipment"),
        blocking_step="",
        confidence=0.83,
        contradiction_state="none",
    )

    restored = InterwovenStagedChainReport.from_dict(report.to_dict())

    assert restored == report
    assert restored.producer_steps == (
        "WF_CreateReservation",
        "WF_OpenFulfillment",
        "WF_GetWorkflowNonce",
    )


def test_staged_chain_observer_passes_for_ordered_workflow_chain() -> None:
    report = InterwovenStagedChainReport(
        chain_id="workflow_handle_nonce_commit_chain",
        ordered_steps=(
            "WF_CreateReservation",
            "WF_OpenFulfillment",
            "WF_GetWorkflowNonce",
            "WF_ConfirmWorkflow",
            "WF_CommitShipment",
        ),
        required_state_tokens=("reservation_id", "workflow_handle", "nonce"),
        producer_steps=("WF_CreateReservation", "WF_OpenFulfillment", "WF_GetWorkflowNonce"),
        consumer_steps=("WF_ConfirmWorkflow", "WF_CommitShipment"),
        blocking_step="",
        confidence=0.83,
        contradiction_state="none",
    )

    observer = build_staged_chain_ordering_plausibility_observer(
        report,
        canonical_sources=(str(ROOT / "tests" / "fixtures" / "contoso_workflow" / "truth_manifest.json"),),
    )

    assert "staged_chain_ordering_plausibility" in INTERWOVEN_OBSERVER_NAMES
    assert observer["observer_name"] == "staged_chain_ordering_plausibility"
    assert observer["verdict"] == "pass"
    assert "ordered_dependency_chain_present" in observer["reasons"]


def test_staged_chain_observer_warns_when_blocking_step_is_still_open() -> None:
    report = InterwovenStagedChainReport(
        chain_id="workflow_handle_nonce_commit_chain",
        ordered_steps=(
            "WF_CreateReservation",
            "WF_OpenFulfillment",
            "WF_GetWorkflowNonce",
            "WF_ConfirmWorkflow",
            "WF_CommitShipment",
        ),
        required_state_tokens=("reservation_id", "workflow_handle", "nonce"),
        producer_steps=("WF_CreateReservation", "WF_OpenFulfillment", "WF_GetWorkflowNonce"),
        consumer_steps=("WF_ConfirmWorkflow", "WF_CommitShipment"),
        blocking_step="WF_ConfirmWorkflow",
        confidence=0.71,
        contradiction_state="tentative",
    )

    observer = build_staged_chain_ordering_plausibility_observer(
        report,
        canonical_sources=(str(ROOT / "tests" / "fixtures" / "contoso_workflow" / "truth_manifest.json"),),
    )

    assert observer["verdict"] == "warn"
    assert "chain_ordering_needs_more_evidence" in observer["reasons"]
