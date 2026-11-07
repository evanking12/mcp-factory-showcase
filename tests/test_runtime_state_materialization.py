from __future__ import annotations

from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry


def test_harvest_from_result_promotes_output_handle_nonce_and_token() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.harvest_from_result(
        function_name="WF_OpenFulfillment",
        result_str="Returned: 0\nparam_2='WFH-OPEN-001'\nparam_3=287454020\nparam_4='E5414243'",
        working_args={
            "param_2": "WFH-OPEN-001",
            "param_3": 287454020,
            "param_4": "E5414243",
        },
        param_lookup={
            "param_2": {"name": "pOutHandle", "description": "Output workflow handle"},
            "param_3": {"name": "pdwNonceOut", "description": "Output workflow nonce"},
            "param_4": {"name": "pOutToken", "description": "Unlock token hex"},
        },
    )

    assert ecr.query("handle", "string", max_results=1)[0].value == "WFH-OPEN-001"
    assert ecr.query("nonce", "integer", max_results=1)[0].value == 287454020
    assert ecr.query("auth_token", "string", max_results=1)[0].value == "E5414243"


def test_harvest_from_result_parses_named_outputs_for_runtime_artifacts() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.harvest_from_result(
        function_name="PR_BeginQuote",
        result_str="Returned: 0\npOutQuoteId=PRQ-CUST-001-01\npdwNonceOut=1500755888",
        working_args={"lpszCustId": "CUST-001"},
        param_lookup={
            "pOutQuoteId": {"name": "pOutQuoteId", "description": "Quote identifier output"},
            "pdwNonceOut": {"name": "pdwNonceOut", "description": "Quote nonce output"},
        },
    )

    assert ecr.query("quote_id", "string", max_results=1)[0].value == "PRQ-CUST-001-01"
    assert ecr.query("nonce", "integer", max_results=1)[0].value == 1500755888


def test_harvest_from_result_skips_zero_numeric_runtime_artifacts() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.harvest_from_result(
        function_name="TP_AllocBlobToken",
        result_str="Returned: 0\npdwBlobTokenOut=0\npdwNonceOut=0",
        working_args={"dwSessionHandle": 1073745926},
        param_lookup={
            "pdwBlobTokenOut": {"name": "pdwBlobTokenOut", "description": "Output opaque blob token"},
            "pdwNonceOut": {"name": "pdwNonceOut", "description": "Output nonce"},
        },
    )

    assert ecr.query("blob_token", "integer", max_results=1) == []
    assert ecr.query("nonce", "integer", max_results=1) == []


def test_get_best_for_param_prefers_materialized_handle_and_nonce() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.add("WFH-OPEN-001", 2, "runtime:WF_OpenFulfillment", "handle", 1.0, "WF_OpenFulfillment")
    ecr.add(287454020, 2, "runtime:WF_GetWorkflowNonce", "nonce", 1.0, "WF_GetWorkflowNonce")

    handle_candidates = ecr.get_best_for_param(
        "lpszHandle",
        "string",
        "Workflow handle returned by WF_OpenFulfillment",
        fn_name="WF_ConfirmWorkflow",
    )
    nonce_candidates = ecr.get_best_for_param(
        "dwNonce",
        "integer",
        "Workflow nonce returned by WF_GetWorkflowNonce",
        fn_name="WF_ConfirmWorkflow",
    )

    assert handle_candidates[0]["value"] == "WFH-OPEN-001"
    assert handle_candidates[0]["source"].startswith("evidence.")
    assert nonce_candidates[0]["value"] == 287454020
    assert nonce_candidates[0]["source"].startswith("evidence.")


def test_harvest_from_result_promotes_numeric_handle_from_output_scalar_and_return_value() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.harvest_from_result(
        function_name="TP_OpenSession",
        result_str="Returned: 1073745921\nparam_2=1073745921\nparam_3=287454020",
        working_args={"param_2": 1073745921, "param_3": 287454020},
        param_lookup={
            "param_2": {"name": "pdwSessionHandleOut", "description": "Opaque session handle"},
            "param_3": {"name": "pdwNonceOut", "description": "Session nonce"},
        },
    )

    handle_candidates = ecr.query("handle", "integer", max_results=3)
    nonce_candidates = ecr.query("nonce", "integer", max_results=1)

    assert handle_candidates[0].value == 1073745921
    assert nonce_candidates[0].value == 287454020


def test_get_best_for_param_prefers_numeric_handle_for_integer_session_slots() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.add(1073745921, 2, "runtime:TP_OpenSession", "handle", 1.0, "TP_OpenSession")

    handle_candidates = ecr.get_best_for_param(
        "dwSessionHandle",
        "integer",
        "Opaque session handle returned by TP_OpenSession",
        fn_name="TP_SubmitPacket",
    )

    assert handle_candidates[0]["value"] == 1073745921
    assert "handle" in handle_candidates[0]["reason"]


def test_harvest_from_result_does_not_promote_version_return_as_handle() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.harvest_from_result(
        function_name="TP_GetStructVersion",
        result_str="Returned: 2",
        working_args={},
        param_lookup={},
    )

    assert ecr.query("handle", "integer", max_results=1) == []


def test_numeric_blob_token_routes_like_opaque_handle_in_first_wave() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.harvest_from_result(
        function_name="TP_AllocBlobToken",
        result_str="Returned: 0\nparam_2=1879048193",
        working_args={"param_2": 1879048193},
        param_lookup={
            "param_2": {"name": "pdwBlobTokenOut", "description": "Opaque blob token"},
        },
    )

    token_candidates = ecr.get_best_for_param(
        "dwBlobToken",
        "integer",
        "Opaque blob token returned by TP_AllocBlobToken",
        fn_name="TP_FreeBlobToken",
    )

    assert token_candidates[0]["value"] == 1879048193
    assert "blob_token" in token_candidates[0]["reason"]


def test_get_best_for_param_prefers_fresher_runtime_candidates_on_ties() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.add(1073745921, 2, "runtime:TP_OpenSession", "handle", 1.0, "TP_OpenSession")
    ecr.add(1073745925, 2, "runtime:TP_OpenSession", "handle", 1.0, "TP_OpenSession")

    handle_candidates = ecr.get_best_for_param(
        "dwSessionHandle",
        "integer",
        "Opaque session handle",
        fn_name="TP_GetSessionNonce",
    )

    assert handle_candidates[0]["value"] == 1073745925
    assert handle_candidates[1]["value"] == 1073745921


def test_harvest_from_result_promotes_string_handle_from_handle_output_context() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.harvest_from_result(
        function_name="WF_OpenFulfillment",
        result_str="Returned: 0\nWFH-CUST-001-02",
        working_args={"pOutHandle": ""},
        param_lookup={
            "pOutHandle": {"name": "pOutHandle", "description": "Workflow handle output"},
        },
    )

    handle_candidates = ecr.query("handle", "string", max_results=1)

    assert handle_candidates[0].value == "WFH-CUST-001-02"


def test_get_best_for_param_prefers_same_family_runtime_string_handle_over_stale_integer_handle() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.add(1073745928, 4, "cross_dll:TP_OpenSession", "handle", 1.0, "TP_OpenSession")
    ecr.add("WFH-CUST-001-02", 2, "runtime:WF_OpenFulfillment", "handle", 1.0, "WF_OpenFulfillment")

    handle_candidates = ecr.get_best_for_param(
        "lpszHandle",
        "string",
        "Workflow handle returned by WF_OpenFulfillment",
        fn_name="WF_GetWorkflowState",
    )

    assert handle_candidates[0]["value"] == "WFH-CUST-001-02"


def test_blob_token_param_prefers_blob_token_evidence_over_generic_handle() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.add(1073745925, 2, "runtime:TP_OpenSession", "handle", 1.0, "TP_OpenSession")
    ecr.add(1879048197, 2, "runtime:TP_AllocBlobToken", "blob_token", 1.0, "TP_AllocBlobToken")

    token_candidates = ecr.get_best_for_param(
        "dwBlobToken",
        "integer",
        "Opaque blob token returned by TP_AllocBlobToken",
        fn_name="TP_FreeBlobToken",
    )

    assert token_candidates[0]["value"] == 1879048197
    assert "blob_token" in token_candidates[0]["reason"]


def test_overlap_baseline_same_family_string_id_beats_unrelated_cross_dll_seed() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.add(
        "RPT-QT-001",
        3,
        "overlap_baseline:working_call:RP_CreatePreview",
        "string_id",
        1.0,
        "RP_CreatePreview",
        source_job="job-batch-a-reporting",
    )
    ecr.add(
        "RESV-69D095E2-0000",
        4,
        "cross_dll:runtime:WF_CreateReservation",
        "reservation_id",
        1.0,
        "WF_CreateReservation",
        source_job="job-batch-b-workflow",
    )

    candidates = ecr.get_best_for_param(
        "lpszReportId",
        "string",
        "Report identifier used by RP_RenderPreview",
        fn_name="RP_RenderPreview",
    )

    assert candidates[0]["value"] == "RPT-QT-001"
    assert candidates[0]["source"].startswith("evidence.tier3.overlap_baseline:")


def test_nested_overlap_baseline_same_family_handle_survives_dense_cross_dll_pool() -> None:
    ecr = EvidenceCandidateRegistry()
    for idx in range(6):
        ecr.add(
            1073745928 + idx,
            4,
            "cross_dll:overlap_baseline:working_call:TP_OpenSession",
            "handle",
            1.0,
            "TP_OpenSession",
        )
    ecr.add(
        "WFH-CUST-001-02",
        4,
        "cross_dll:overlap_baseline:working_call:WF_OpenFulfillment",
        "handle",
        1.0,
        "WF_OpenFulfillment",
    )

    candidates = ecr.get_best_for_param(
        "lpszHandle",
        "string",
        "Workflow handle returned by WF_OpenFulfillment",
        fn_name="WF_GetWorkflowState",
    )

    assert candidates[0]["value"] == "WFH-CUST-001-02"
    assert "cross_dll:overlap_baseline:" in candidates[0]["source"]


def test_nested_overlap_baseline_same_family_string_id_beats_wrong_foreign_ids() -> None:
    ecr = EvidenceCandidateRegistry()
    for idx in range(6):
        ecr.add(
            f"CFG-CUST-001-{idx:02d}",
            4,
            "cross_dll:overlap_baseline:working_call:CFG_GetConfigState",
            "string_id",
            1.0,
            "CFG_GetConfigState",
        )
    ecr.add(
        "PRQ-CUST-001-03",
        4,
        "cross_dll:overlap_baseline:working_call:PR_GetQuoteState",
        "string_id",
        1.0,
        "PR_GetQuoteState",
    )

    candidates = ecr.get_best_for_param(
        "lpszQuoteId",
        "string",
        "Quote identifier used by PR_SealQuote",
        fn_name="PR_ApplyTierDiscount",
    )

    assert candidates[0]["value"] == "PRQ-CUST-001-03"
    assert "cross_dll:overlap_baseline:" in candidates[0]["source"]


def test_foreign_overlap_baseline_ticket_is_not_admitted_for_workflow_handle_slot() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.add(
        "CFG-CUST-001-109",
        3,
        "overlap_baseline:working_call:CFG_GetLicenseNonce",
        "ticket",
        1.0,
        "CFG_GetLicenseNonce",
    )

    candidates = ecr.get_best_for_param(
        "lpszHandle",
        "string",
        "Opaque workflow handle",
        fn_name="WF_GetWorkflowState",
        resolved_type="LPCWSTR",
    )

    assert all(str(candidate["value"]).upper() != "CFG-CUST-001-109" for candidate in candidates)


def test_quote_id_param_prefers_specific_quote_family_over_ticket_like_string() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.add(
        "licensed|cust=CUST-001|approved=1",
        4,
        "cross_dll:runtime:CFG_ApproveLicensedCall",
        "ticket",
        1.0,
        "CFG_ApproveLicensedCall",
    )
    ecr.add(
        "PRQ-CUST-001-03",
        3,
        "overlap_baseline:working_call:PR_GetQuoteState",
        "quote_id",
        1.0,
        "PR_GetQuoteState",
    )

    candidates = ecr.get_best_for_param(
        "lpszQuoteId",
        "string",
        "Quote identifier used by PR_SealQuote",
        fn_name="PR_SealQuote",
    )

    assert candidates[0]["value"] == "PRQ-CUST-001-03"
    assert candidates[0]["candidate_family"] == "quote_id"
    assert "same_identifier_family" in candidates[0]["selection_flags"]


def test_workflow_handle_param_demotes_foreign_ticket_ids_in_dense_pool() -> None:
    ecr = EvidenceCandidateRegistry()
    for idx in range(4):
        ecr.add(
            f"CFG-CUST-001-{idx:02d}",
            4,
            "cross_dll:runtime:CFG_GetConfigState",
            "ticket",
            1.0,
            "CFG_GetConfigState",
        )
    ecr.add(
        "WFH-CUST-001-02",
        3,
        "overlap_baseline:working_call:WF_OpenFulfillment",
        "handle",
        1.0,
        "WF_OpenFulfillment",
    )

    candidates = ecr.get_best_for_param(
        "lpszHandle",
        "string",
        "Workflow handle returned by WF_OpenFulfillment",
        fn_name="WF_GetWorkflowState",
    )

    assert candidates[0]["value"] == "WFH-CUST-001-02"
    assert candidates[0]["candidate_family"] == "workflow_handle"
    assert "same_identifier_family" in candidates[0]["selection_flags"]


def test_report_id_param_prefers_overlap_report_id_over_reservation_id() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.add(
        "RESV-69D095E2-0000",
        4,
        "cross_dll:runtime:WF_CreateReservation",
        "reservation_id",
        1.0,
        "WF_CreateReservation",
    )
    ecr.add(
        "RPT-CUST-001-02",
        3,
        "overlap_baseline:working_call:RP_CreatePreview",
        "report_id",
        1.0,
        "RP_CreatePreview",
    )

    candidates = ecr.get_best_for_param(
        "lpszReportId",
        "string",
        "Report identifier used by RP_CloseReport",
        fn_name="RP_CloseReport",
    )

    assert candidates[0]["value"] == "RPT-CUST-001-02"
    assert candidates[0]["candidate_family"] == "report_id"
