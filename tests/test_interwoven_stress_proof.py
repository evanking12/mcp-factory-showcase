from api.pipeline.core.interwoven_stress_proof import InterwovenStressScenario, run_interwoven_stress_proof


def test_interwoven_stress_proof_surfaces_visible_ambiguity_without_collapsing() -> None:
    result = run_interwoven_stress_proof(
        scenarios=[
            InterwovenStressScenario(
                label="competing-producers-and-ambiguous-state",
                producer_consumer_reports=(
                    {
                        "family": "config_ticket_to_reporting_export",
                        "producer_id": "config_approval_license:CFG_ApproveLicensedCall",
                        "producer_kind": "producer",
                        "consumer_id": "reporting_preview_render_export:RP_ExportLedger",
                        "consumer_kind": "consumer",
                        "state_tokens": ("ticket", "nonce"),
                        "evidence_edges": ("CFG_ApproveLicensedCall->RP_ExportLedger",),
                        "dependency_mode": "shared_state_mediated",
                        "confidence": 0.84,
                        "contradiction_state": "tentative",
                        "observer_verdict": "warn",
                    },
                    {
                        "family": "config_ticket_to_reporting_export",
                        "producer_id": "config_licensed_ticket_bootstrap:CFG_RunCustomerSync",
                        "producer_kind": "producer",
                        "consumer_id": "reporting_preview_render_export:RP_ExportLedger",
                        "consumer_kind": "consumer",
                        "state_tokens": ("ticket",),
                        "evidence_edges": ("CFG_RunCustomerSync->RP_PrepareReservationReport",),
                        "dependency_mode": "shared_state_mediated",
                        "confidence": 0.79,
                        "contradiction_state": "tentative",
                        "observer_verdict": "warn",
                    },
                ),
                shared_state_reports=(
                    {
                        "carrier_id": "events_session_mask",
                        "carrier_kind": "shared_state_carrier",
                        "state_tokens": ("dwEventSession", "dwEventMask"),
                        "downstream_consumers": ("EV_RegisterMask", "EV_ReplayMask"),
                        "exporting_seams": ("EV_OpenEventSession",),
                        "importing_seams": ("EV_RegisterMask", "EV_ReplayMask"),
                        "staleness_risk": "medium",
                        "confidence": 0.72,
                        "contradiction_state": "tentative",
                        "observer_verdict": "warn",
                    }
                ),
                expected_proof_status="pass",
                expected_competing_producer_count_min=1,
                expected_ambiguous_shared_state_count_min=1,
            ),
            InterwovenStressScenario(
                label="overlapping-chains-and-stale-state",
                shared_state_reports=(
                    {
                        "carrier_id": "workflow_handle_cache",
                        "carrier_kind": "shared_state_carrier",
                        "state_tokens": ("reservation_id", "workflow_handle", "nonce"),
                        "downstream_consumers": ("WF_ConfirmWorkflow", "WF_CommitShipment"),
                        "exporting_seams": ("WF_OpenFulfillment", "WF_GetWorkflowNonce"),
                        "importing_seams": ("WF_ConfirmWorkflow", "WF_CommitShipment"),
                        "staleness_risk": "high",
                        "confidence": 0.68,
                        "contradiction_state": "contradicted",
                        "observer_verdict": "fail",
                    }
                ),
                staged_chain_reports=(
                    {
                        "chain_id": "workflow_commit_path",
                        "ordered_steps": (
                            "WF_CreateReservation",
                            "WF_OpenFulfillment",
                            "WF_GetWorkflowNonce",
                            "WF_CommitShipment",
                        ),
                        "required_state_tokens": ("reservation_id", "workflow_handle", "nonce"),
                        "producer_steps": ("WF_CreateReservation", "WF_OpenFulfillment"),
                        "consumer_steps": ("WF_GetWorkflowNonce", "WF_CommitShipment"),
                        "blocking_step": "WF_GetWorkflowNonce",
                        "confidence": 0.71,
                        "contradiction_state": "tentative",
                        "observer_verdict": "warn",
                    },
                    {
                        "chain_id": "workflow_confirm_path",
                        "ordered_steps": (
                            "WF_CreateReservation",
                            "WF_OpenFulfillment",
                            "WF_GetWorkflowNonce",
                            "WF_ConfirmWorkflow",
                        ),
                        "required_state_tokens": ("reservation_id", "workflow_handle", "nonce"),
                        "producer_steps": ("WF_CreateReservation",),
                        "consumer_steps": ("WF_OpenFulfillment", "WF_GetWorkflowNonce", "WF_ConfirmWorkflow"),
                        "blocking_step": "",
                        "confidence": 0.77,
                        "contradiction_state": "tentative",
                        "observer_verdict": "warn",
                    },
                ),
                expected_proof_status="pass",
                expected_overlapping_chain_count_min=1,
                expected_stale_or_forked_state_count_min=1,
            ),
        ]
    )

    assert result["status"] == "pass"
    by_label = {row["label"]: row for row in result["scenario_reports"]}
    assert by_label["competing-producers-and-ambiguous-state"]["proof_summary"]["ambiguity_visibility_ok"] is True
    assert by_label["competing-producers-and-ambiguous-state"]["checks"]["competing_producer_count_min"]["ok"] is True
    assert by_label["overlapping-chains-and-stale-state"]["checks"]["overlapping_chain_count_min"]["ok"] is True
    assert by_label["overlapping-chains-and-stale-state"]["checks"]["stale_or_forked_state_count_min"]["ok"] is True


def test_interwoven_stress_proof_can_expect_hidden_ambiguity_failure() -> None:
    result = run_interwoven_stress_proof(
        scenarios=[
            InterwovenStressScenario(
                label="hidden-competing-producers",
                producer_consumer_reports=(
                    {
                        "family": "config_ticket_to_reporting_export",
                        "producer_id": "config_approval_license:CFG_ApproveLicensedCall",
                        "producer_kind": "producer",
                        "consumer_id": "reporting_preview_render_export:RP_ExportLedger",
                        "consumer_kind": "consumer",
                        "state_tokens": ("ticket", "nonce"),
                        "evidence_edges": ("CFG_ApproveLicensedCall->RP_ExportLedger",),
                        "dependency_mode": "shared_state_mediated",
                        "confidence": 0.92,
                        "contradiction_state": "none",
                        "observer_verdict": "pass",
                    },
                    {
                        "family": "config_ticket_to_reporting_export",
                        "producer_id": "config_licensed_ticket_bootstrap:CFG_RunCustomerSync",
                        "producer_kind": "producer",
                        "consumer_id": "reporting_preview_render_export:RP_ExportLedger",
                        "consumer_kind": "consumer",
                        "state_tokens": ("ticket",),
                        "evidence_edges": ("CFG_RunCustomerSync->RP_PrepareReservationReport",),
                        "dependency_mode": "shared_state_mediated",
                        "confidence": 0.91,
                        "contradiction_state": "none",
                        "observer_verdict": "pass",
                    },
                ),
                expected_proof_status="fail",
                expected_competing_producer_count_min=1,
            )
        ]
    )

    assert result["status"] == "pass"
    scenario = result["scenario_reports"][0]
    assert scenario["proof_summary"]["proof_status"] == "fail"
    assert scenario["checks"]["expected_proof_status"]["ok"] is True
    assert scenario["proof_summary"]["bounded_readability"] is True
