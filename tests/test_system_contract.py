from api.pipeline.core.system_contract import (
    SYSTEM_CONTRACTS,
    SYSTEM_CONTRACTS_BY_NAME,
    SYSTEM_CONTRACTS_BY_OWNER_LAYER,
    build_system_contract_snapshot,
    observe_lineage_handoff,
    observe_live_artifact_emission,
    validate_system_contracts,
)


def test_system_contract_registry_covers_first_rollout_slice() -> None:
    validate_system_contracts(SYSTEM_CONTRACTS)

    assert "generalized runtime artifact materializer" in SYSTEM_CONTRACTS_BY_NAME
    assert "prerequisite replay / runtime materialization" in SYSTEM_CONTRACTS_BY_NAME
    assert "dense-context lineage isolation" in SYSTEM_CONTRACTS_BY_NAME
    assert "structured argument scaffolder" in SYSTEM_CONTRACTS_BY_NAME
    assert "prerequisite and state-machine classifier" in SYSTEM_CONTRACTS_BY_NAME
    assert "environment dependency classifier" in SYSTEM_CONTRACTS_BY_NAME
    assert "business-rule and approval classifier" in SYSTEM_CONTRACTS_BY_NAME
    assert "checkpoint and resume coordinator" in SYSTEM_CONTRACTS_BY_NAME
    assert "runner stage orchestration" in SYSTEM_CONTRACTS_BY_NAME
    assert "enrichment verification classifier" in SYSTEM_CONTRACTS_BY_NAME


def test_system_contract_snapshot_and_owner_layer_views_cover_broader_rollout() -> None:
    snapshot = build_system_contract_snapshot()

    assert snapshot
    assert any(
        row["name"] == "checkpoint and resume coordinator"
        and row["owner_layer"] == "pipeline_core"
        for row in snapshot
    )
    assert "s02_probe" in SYSTEM_CONTRACTS_BY_OWNER_LAYER
    assert "pipeline_runner" in SYSTEM_CONTRACTS_BY_OWNER_LAYER
    assert "runner stage orchestration" in SYSTEM_CONTRACTS_BY_OWNER_LAYER["pipeline_runner"]
    assert "prerequisite and state-machine classifier" in SYSTEM_CONTRACTS_BY_OWNER_LAYER["s02_probe"]
    assert "environment dependency classifier" in SYSTEM_CONTRACTS_BY_OWNER_LAYER["s02_probe"]
    assert "business-rule and approval classifier" in SYSTEM_CONTRACTS_BY_OWNER_LAYER["s02_probe"]


def test_remaining_batch_b_regression_systems_are_contract_shaped() -> None:
    regression_surface = {
        "environment dependency classifier",
        "business-rule and approval classifier",
        "generalized runtime artifact materializer",
        "prerequisite and state-machine classifier",
        "dense-context lineage isolation",
        "prerequisite replay / runtime materialization",
        "structured argument scaffolder",
    }

    for name in regression_surface:
        contract = SYSTEM_CONTRACTS_BY_NAME[name]
        assert contract.consumes
        assert contract.emits
        assert contract.decisions
        assert contract.handoff_invariants
        assert contract.expected_test_surfaces


def test_observe_live_artifact_emission_reports_workflow_handle_success() -> None:
    results = observe_live_artifact_emission(
        contract_name="generalized runtime artifact materializer",
        producer_function="WF_OpenFulfillment",
        promoted_hints={"workflow_handle": "WFH-CUST-001-02"},
        materialization_missing_families=[],
    )

    assert results
    assert results[0]["observer_id"] == "emit:workflow_handle"
    assert results[0]["status"] == "pass"
    assert results[0]["likely_fault_scope"] == "none"


def test_observe_lineage_handoff_reports_workflow_handle_use() -> None:
    results = observe_lineage_handoff(
        contract_name="dense-context lineage isolation",
        consumer_function="WF_GetWorkflowNonce",
        consumer_args={"lpszHandle": "WFH-CUST-001-02"},
        arg_selection={
            "lpszHandle": {
                "expected_family": "workflow_handle",
                "candidate_family": "workflow_handle",
                "source_lineage": "lineage_hint.workflow_handle",
            }
        },
        lineage_hints={"workflow_handle": "WFH-CUST-001-02"},
    )

    assert results
    assert results[0]["observer_id"] == "handoff:workflow_handle"
    assert results[0]["status"] == "pass"
    assert results[0]["likely_fault_scope"] == "none"


def test_observe_lineage_handoff_reports_reservation_id_use() -> None:
    results = observe_lineage_handoff(
        contract_name="prerequisite replay / runtime materialization",
        consumer_function="WF_OpenFulfillment",
        consumer_args={"lpszResvId": "RESV-69CD5E9F-0009"},
        arg_selection={
            "lpszResvId": {
                "expected_family": "reservation_id",
                "candidate_family": "reservation_id",
                "source_lineage": "lineage_hint.reservation_id",
            }
        },
        lineage_hints={"reservation_id": "RESV-69CD5E9F-0009"},
    )

    assert results
    assert results[0]["observer_id"] == "handoff:reservation_id"
    assert results[0]["status"] == "pass"
    assert results[0]["likely_fault_scope"] == "none"


def test_observe_lineage_handoff_ignores_true_output_slots() -> None:
    results = observe_lineage_handoff(
        contract_name="prerequisite replay / runtime materialization",
        consumer_function="WF_OpenFulfillment",
        consumer_args={"pOutHandle": ""},
        arg_selection={
            "pOutHandle": {
                "expected_family": "workflow_handle",
                "candidate_family": "workflow_handle",
                "source_lineage": "lineage_hint.workflow_handle",
            }
        },
        lineage_hints={"workflow_handle": "WFH-CUST-001-02"},
        param_lookup={
            "pOutHandle": {
                "name": "pOutHandle",
                "direction": "out",
                "json_type": "string",
            }
        },
    )

    assert results == []


def test_observe_live_artifact_emission_marks_local_failure_scope() -> None:
    results = observe_live_artifact_emission(
        contract_name="generalized runtime artifact materializer",
        producer_function="CFG_OpenLicensedWindow",
        promoted_hints={},
        materialization_missing_families=["ticket"],
    )

    assert results
    assert results[0]["observer_id"] == "emit:ticket"
    assert results[0]["status"] == "fail"
    assert results[0]["likely_fault_scope"] == "local"


def test_observe_lineage_handoff_marks_upstream_and_downstream_failure_scope() -> None:
    upstream = observe_lineage_handoff(
        contract_name="prerequisite replay / runtime materialization",
        consumer_function="CFG_ApproveLicensedCall",
        consumer_args={"lpszTicket": "TEST"},
        arg_selection={
            "lpszTicket": {
                "expected_family": "ticket",
                "candidate_family": "ticket",
                "source_lineage": "lineage_hint.ticket",
            }
        },
        lineage_hints={},
    )
    downstream = observe_lineage_handoff(
        contract_name="dense-context lineage isolation",
        consumer_function="PR_GetQuoteState",
        consumer_args={"lpszQuoteId": "TEST"},
        arg_selection={
            "lpszQuoteId": {
                "expected_family": "quote_id",
                "candidate_family": "ticket",
                "source_lineage": "lineage_hint.quote_id",
            }
        },
        lineage_hints={"quote_id": "PRQ-CUST-001-01"},
    )

    assert upstream[0]["status"] == "fail"
    assert upstream[0]["likely_fault_scope"] == "upstream"
    assert downstream[0]["status"] == "fail"
    assert downstream[0]["likely_fault_scope"] == "downstream"
