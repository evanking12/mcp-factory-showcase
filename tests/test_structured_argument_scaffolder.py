from __future__ import annotations

from types import SimpleNamespace

from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry
from api.pipeline.core.helpers import (
    _build_tool_schemas,
    _build_ranked_fallback_probe_args,
    _canonical_args_from_doc,
    _default_scalar_value,
    _ranked_param_candidates,
)
from api.pipeline.core.types import ExploreContext, ExploreRuntime
from api.pipeline.s02_probe.probe_loop import (
    _augment_structured_probe_args_for_mixed_calls,
    _align_prerequisite_args,
    _choose_best_observed_success,
    _consumer_ready_lineage_hints,
    _consume_retryable_blocked_prereq,
    _extract_inline_lineage_hints,
    _infer_runtime_prerequisites,
    _is_rehydratable_success_finding,
    _is_seeded_external_success,
    _semantic_arg_kind,
    _explore_one,
    _extract_required_preconditions,
    _is_runtime_success_value,
    _merge_runtime_success_values,
    _normalize_true_output_scalar_args,
    _repair_target_input_aliases,
    _repair_target_scalar_args,
    _repair_target_structured_args,
    _requires_fresh_runtime_lineage,
    _sanitize_lineage_hints_for_prereq_replay,
    _retag_runtime_probe_roles,
    _structured_target_hints,
)
from scripts.bridge.gui_bridge import (
    _bridge_build_flat_struct_instance,
    _bridge_struct_to_dict,
)


_TRANSPORT_OPEN_INV = {
    "name": "TP_OpenSession",
    "parameters": [
        {
            "name": "pReq",
            "type": "TP_OPEN_REQ*",
            "resolved_type": "TP_OPEN_REQ*",
            "direction": "in",
            "json_type": "string",
            "description": "Input transport open struct",
        },
        {
            "name": "pdwHandleOut",
            "type": "DWORD*",
            "resolved_type": "DWORD*",
            "direction": "out",
            "json_type": "integer",
            "description": "Output session handle",
        },
    ],
    "doc_comment": (
        'Required preconditions: TP_BindCustomer | Canonical args: '
        '{"pReq": {"dwFlags": 1, "dwMode": 2, "szCustId": "CUST-001"}}'
    ),
    "_ghidra_extras": {
        "data_types": [
            {
                "kind": "struct",
                "name": "TP_OPEN_REQ",
                "fields": [
                    {"name": "szCustId", "type": "char[16]"},
                    {"name": "dwFlags", "type": "DWORD"},
                    {"name": "dwMode", "type": "DWORD"},
                ],
            }
        ]
    },
}


_TRANSPORT_PACKET_INV = {
    "name": "TP_SubmitPacket",
    "parameters": [
        {
            "name": "pReq",
            "type": "TP_PACKET_REQ*",
            "resolved_type": "TP_PACKET_REQ*",
            "direction": "in",
            "json_type": "string",
            "description": "Input packet struct",
        },
        {
            "name": "pdwAuthCodeOut",
            "type": "DWORD*",
            "resolved_type": "DWORD*",
            "direction": "out",
            "json_type": "integer",
            "description": "Output auth code",
        },
    ],
    "doc_comment": (
        'Required preconditions: TP_GetSessionNonce | Canonical args: '
        '{"pReq": {"dwNonce": "nonce-from-read", "dwSessionHandle": "handle-from-open", '
        '"szSku": "ACC-USB-C", "wQty": 2}}'
    ),
    "_ghidra_extras": {
        "data_types": [
            {
                "kind": "struct",
                "name": "TP_PACKET_REQ",
                "fields": [
                    {"name": "dwSessionHandle", "type": "DWORD"},
                    {"name": "szSku", "type": "char[24]"},
                    {"name": "wQty", "type": "WORD"},
                    {"name": "dwNonce", "type": "DWORD"},
                ],
            }
        ]
    },
}


def test_ranked_fallback_scaffolds_flat_struct_from_canonical_args() -> None:
    args, selection = _build_ranked_fallback_probe_args(_TRANSPORT_OPEN_INV, vocab={})

    assert args["pReq"] == {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2}
    assert selection["pReq"]["source"] == "structured.scaffolder"
    assert selection["pReq"]["fields"]["szCustId"]["source"] == "doc.canonical_args"


def test_ranked_fallback_scaffolds_struct_fields_from_runtime_artifacts() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.add(1073745921, 2, "runtime:TP_OpenSession", "handle", 1.0, "TP_OpenSession")
    ecr.add(16818177, 2, "runtime:TP_GetSessionNonce", "nonce", 1.0, "TP_GetSessionNonce")

    args, selection = _build_ranked_fallback_probe_args(_TRANSPORT_PACKET_INV, vocab={}, evidence=ecr)

    assert args["pReq"]["dwSessionHandle"] == 1073745921
    assert args["pReq"]["dwNonce"] == 16818177
    assert args["pReq"]["szSku"] == "ACC-USB-C"
    assert selection["pReq"]["fields"]["dwSessionHandle"]["source"].startswith("evidence.")
    assert selection["pReq"]["fields"]["dwNonce"]["source"].startswith("evidence.")


def test_customer_context_demotes_sku_like_values() -> None:
    candidates = _ranked_param_candidates(
        "lpszCustId",
        "string",
        "Customer identifier",
        {"id_formats": ["CUST-001"], "binary_string_ids": ["ACC-USB-C", "CUST-001"]},
        fn_name="TP_BindCustomer",
    )

    assert candidates[0]["value"] == "CUST-001"
    assert all(c["value"] != "ACC-USB-C" for c in candidates[:1])


def test_ranked_candidates_skip_foreign_static_ids_for_report_slot() -> None:
    candidates = _ranked_param_candidates(
        "param_1",
        "string",
        "input string parameter",
        {"binary_string_ids": ["RESV-69D095E2-0000", "RPT-CUST-001-02"]},
        fn_name="RP_CloseReport",
    )

    assert candidates[0]["value"] == "RPT-CUST-001-02"
    assert all(str(candidate["value"]).upper() != "RESV-69D095E2-0000" for candidate in candidates[:2])


def test_repair_target_scalar_args_uses_report_family_for_generic_report_slot() -> None:
    inv = {
        "name": "RP_CloseReport",
        "parameters": [
            {
                "name": "param_1",
                "json_type": "string",
                "type": "LPCSTR",
                "resolved_type": "LPCSTR",
                "description": "input string parameter",
            }
        ],
    }
    ecr = EvidenceCandidateRegistry()
    ecr.add(
        "RESV-69D095E2-0000",
        3,
        "overlap_baseline:working_call:WF_CreateReservation",
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

    args, selection = _repair_target_scalar_args(
        inv,
        {"param_1": "RESV-69D095E2-0000"},
        {"param_1": {"source": "llm"}},
        {"binary_string_ids": ["RESV-69D095E2-0000", "RPT-CUST-001-02"]},
        ecr,
    )

    assert args["param_1"] == "RPT-CUST-001-02"
    assert selection["param_1"]["candidate_family"] == "report_id"
    assert selection["param_1"]["expected_family"] == "report_id"


def test_repair_target_input_aliases_maps_near_match_scalar_name() -> None:
    inv = {
        "name": "TP_FreeBlobToken",
        "parameters": [
            {
                "name": "dwBlobToken",
                "json_type": "integer",
                "description": "Opaque blob token to release",
            }
        ],
    }

    args, selection = _repair_target_input_aliases(
        inv,
        {"pdwBlobToken": 1879048198},
        {"pdwBlobToken": {"source": "llm"}},
    )

    assert args == {"dwBlobToken": 1879048198}
    assert selection["dwBlobToken"]["reason"].startswith("remapped near-match arg")


def test_structured_target_hints_extracts_customer_handle_and_nonce() -> None:
    hints = _structured_target_hints({
        "pReq": {
            "szCustId": "CUST-001",
            "dwSessionHandle": 1073745921,
            "dwNonce": 16818177,
            "szSku": "ACC-USB-C",
        }
    })

    assert hints == {
        "customer_id": "CUST-001",
        "handle": 1073745921,
        "nonce": 16818177,
        "sku": "ACC-USB-C",
    }


def test_structured_target_hints_extracts_reservation_id() -> None:
    hints = _structured_target_hints({
        "pOutResvId": "RESV-69CCA03E-0000",
    })

    assert hints == {"reservation_id": "RESV-69CCA03E-0000"}


def test_structured_target_hints_extracts_customer_and_sku_from_generic_arg_values() -> None:
    hints = _structured_target_hints({
        "param_1": "CUST-001",
        "param_2": "ACC-USB-C",
    })

    assert hints["customer_id"] == "CUST-001"
    assert hints["sku"] == "ACC-USB-C"


def test_structured_target_hints_extracts_lineage_from_generic_output_value_shape() -> None:
    hints = _structured_target_hints({
        "pOutBuf": "RESV-69CCA03E-0000",
        "nextHandle": "WFH-CUST-001-01",
        "ticket": "CFG-CUST-001-86",
    })

    assert hints["reservation_id"] == "RESV-69CCA03E-0000"
    assert hints["workflow_handle"] == "WFH-CUST-001-01"
    assert hints["ticket"] == "CFG-CUST-001-86"


def test_structured_target_hints_extracts_spectrum_runtime_lineage_families() -> None:
    hints = _structured_target_hints({
        "output_buffer": "sp-resv-easy01-order-211137360",
        "output_buffer__2": "sp-hold-easy01-order-37360",
        "receipt": "sp-commit-easy01-order-991",
        "preview": "sp-preview-easy01-order-211137360-gate",
        "fee": "sp-fee-easy01-order-211137360-quote",
    })

    assert hints["reservation_id"] == "sp-resv-easy01-order-211137360"
    assert hints["hold_token"] == "sp-hold-easy01-order-37360"
    assert hints["commit_receipt"] == "sp-commit-easy01-order-991"
    assert hints["preview_ticket"] == "sp-preview-easy01-order-211137360-gate"
    assert hints["fee_quote_id"] == "sp-fee-easy01-order-211137360-quote"


def test_structured_target_hints_ignores_empty_family_sensitive_output_values() -> None:
    hints = _structured_target_hints({
        "pOutHandle": "",
        "pOutResvId": "",
        "lpszCustId": "CUST-001",
    })

    assert "workflow_handle" not in hints
    assert "reservation_id" not in hints
    assert hints["customer_id"] == "CUST-001"


def test_extract_inline_lineage_hints_reads_runtime_result_strings() -> None:
    hints = _extract_inline_lineage_hints(
        "Returned: 0\nRESV-69CCA2E7-0000\nWFH-CUST-001-01\nPRQ-CUST-001-01\nRPT-CUST-001-02"
    )

    assert hints["reservation_id"] == "RESV-69CCA2E7-0000"
    assert hints["workflow_handle"] == "WFH-CUST-001-01"
    assert hints["quote_id"] == "PRQ-CUST-001-01"
    assert hints["report_id"] == "RPT-CUST-001-02"


def test_extract_inline_lineage_hints_reads_spectrum_preview_and_fee_strings() -> None:
    hints = _extract_inline_lineage_hints(
        "Returned: 0\nsp-preview-ORD-001-64-gate\nsp-fee-ORD-001-64-quote"
    )

    assert hints["preview_ticket"] == "sp-preview-ORD-001-64-gate"
    assert hints["fee_quote_id"] == "sp-fee-ORD-001-64-quote"


def test_is_rehydratable_success_finding_rejects_state_drift_success() -> None:
    assert _is_rehydratable_success_finding({
        "function": "WF_CreateReservation",
        "status": "success",
        "status_canonical": "verified_success",
        "verification": "state_drift",
        "working_call": {"lpszSku": "GDG-SM-RED", "wQty": 1},
    }) is False

    assert _is_rehydratable_success_finding({
        "function": "WF_CreateReservation",
        "status": "success",
        "status_canonical": "verified_success",
        "verification": "verified",
        "working_call": {"lpszSku": "GDG-SM-RED", "wQty": 1},
    }) is True


def test_retag_runtime_probe_roles_marks_first_pointer_param_as_input_handle() -> None:
    inv = {
        "name": "soundtouch_setTempo",
        "parameters": [
            {
                "name": "param_1",
                "type": "int *",
                "resolved_type": "int *",
                "direction": "out",
                "json_type": "integer",
                "description": "Output - receives integer result",
            },
            {
                "name": "param_2",
                "type": "float",
                "resolved_type": "float",
                "direction": "in",
                "json_type": "number",
                "description": "tempo value",
            },
        ],
        "doc_comment": "if (*param_1 == 0x1770c001) return 0x50000001;",
    }

    _retag_runtime_probe_roles(inv)

    assert inv["parameters"][0]["direction"] == "in"
    assert inv["parameters"][0]["json_type"] == "integer"
    assert "opaque runtime handle input" in inv["parameters"][0]["description"]


def test_retag_runtime_probe_roles_marks_version_string_buffer_and_size() -> None:
    inv = {
        "name": "soundtouch_getVersionString2",
        "parameters": [
            {
                "name": "param_1",
                "type": "char *",
                "resolved_type": "char *",
                "direction": "in",
                "json_type": "integer",
                "description": "Parameter of type char *",
            },
            {
                "name": "param_2",
                "type": "int",
                "resolved_type": "int",
                "direction": "in",
                "json_type": "integer",
                "description": "Parameter of type int",
            },
        ],
    }

    _retag_runtime_probe_roles(inv)

    assert inv["parameters"][0]["direction"] == "out"
    assert inv["parameters"][0]["json_type"] == "string"
    assert "output text buffer" in inv["parameters"][0]["description"]
    assert "output buffer size" in inv["parameters"][1]["description"]


def test_retag_runtime_probe_roles_marks_generic_output_id_buffer_size_as_input() -> None:
    inv = {
        "name": "CFG_OpenLicensedWindow",
        "parameters": [
            {
                "name": "pOutTicket",
                "type": "LPSTR",
                "resolved_type": "LPSTR",
                "direction": "out",
                "json_type": "string",
                "description": "Pointer to receive the license ticket.",
            },
            {
                "name": "dwBufLen",
                "type": "DWORD",
                "resolved_type": "DWORD",
                "direction": "out",
                "json_type": "integer",
                "description": "Length of the output buffer for the ticket string.",
            },
        ],
    }

    _retag_runtime_probe_roles(inv)

    assert inv["parameters"][0]["direction"] == "out"
    assert inv["parameters"][1]["direction"] == "in"
    assert inv["parameters"][1]["json_type"] == "integer"
    assert "output buffer size" in inv["parameters"][1]["description"]


def test_retag_runtime_probe_roles_marks_generic_char_pointer_inputs_as_strings_with_doc_hints() -> None:
    inv = {
        "name": "SP_CommitRelease",
        "parameters": [
            {
                "name": "param_1",
                "type": "char *",
                "resolved_type": "char *",
                "direction": "in",
                "json_type": "integer",
                "description": "Parameter recovered by Ghidra decompiler",
            },
            {
                "name": "param_2",
                "type": "char *",
                "resolved_type": "char *",
                "direction": "in",
                "json_type": "integer",
                "description": "Parameter recovered by Ghidra decompiler",
            },
        ],
        "doc_comment": (
            'strncmp(param_1,"sp-resv-",8) != 0 || '
            'strncmp(param_2,"sp-hold-",8) != 0'
        ),
    }

    _retag_runtime_probe_roles(inv)

    assert inv["parameters"][0]["json_type"] == "string"
    assert inv["parameters"][0]["direction"] == "in"
    assert 'must start with "sp-resv-"' in inv["parameters"][0]["description"]
    assert inv["parameters"][1]["json_type"] == "string"
    assert 'must start with "sp-hold-"' in inv["parameters"][1]["description"]


def test_default_scalar_value_uses_doc_prefix_hint_for_string_inputs() -> None:
    value = _default_scalar_value(
        "param_1",
        "string",
        'Parameter recovered by Ghidra input text parameter (must start with "sp-resv-")',
        {},
        attempt=2,
    )

    assert value == "sp-resv-2"


def test_build_tool_schemas_projects_generic_char_pointer_inputs_as_strings_with_doc_hints() -> None:
    schemas = _build_tool_schemas([
        {
            "name": "SP_CommitRelease",
            "parameters": [
                {
                    "name": "param_1",
                    "type": "char *",
                    "resolved_type": "char *",
                    "direction": "in",
                    "json_type": "integer",
                    "description": "Parameter recovered by Ghidra decompiler",
                },
                {
                    "name": "param_2",
                    "type": "char *",
                    "resolved_type": "char *",
                    "direction": "in",
                    "json_type": "integer",
                    "description": "Parameter recovered by Ghidra decompiler",
                },
            ],
            "doc_comment": (
                'strncmp(param_1,"sp-resv-",8) != 0 || '
                'strncmp(param_2,"sp-hold-",8) != 0'
            ),
        }
    ])

    props = schemas[0]["function"]["parameters"]["properties"]
    assert props["param_1"]["type"] == "string"
    assert 'must start with "sp-resv-"' in props["param_1"]["description"]
    assert props["param_2"]["type"] == "string"
    assert 'must start with "sp-hold-"' in props["param_2"]["description"]


def test_semantic_arg_kind_treats_length_style_output_buffer_size_as_buffer_size() -> None:
    kind = _semantic_arg_kind(
        "dwBufLen",
        None,
        "integer",
        "Length of the output buffer for the report ID.",
    )

    assert kind == "buffer_size"


def test_semantic_arg_kind_prefers_report_id_when_name_is_report_shaped() -> None:
    kind = _semantic_arg_kind(
        "lpszReportId",
        None,
        "string",
        "Reservation report identifier",
    )

    assert kind == "report_id"


def test_repair_target_scalar_args_keeps_quantity_slot_numeric_when_description_mentions_product() -> None:
    inv = {
        "name": "WF_CreateReservation",
        "doc_comment": 'Required preconditions: WF_BindCustomer | Canonical args: {"dwHoldMinutes": 30, "lpszSku": "ACC-USB-C", "wQty": 2}',
        "parameters": [
            {
                "name": "lpszSku",
                "json_type": "string",
                "resolved_type": "LPCSTR",
                "description": "SKU of the product being reserved, such as 'GDG-SM-RED'.",
            },
            {
                "name": "wQty",
                "json_type": "integer",
                "resolved_type": "WORD",
                "description": "Quantity of the product to reserve, e.g., 1.",
            },
            {
                "name": "dwHoldMinutes",
                "json_type": "integer",
                "resolved_type": "DWORD",
                "description": "Duration in minutes for which the reservation is held, e.g., 30.",
            },
            {
                "name": "pOutResvId",
                "json_type": "string",
                "direction": "out",
                "description": "Reservation output",
            },
            {
                "name": "dwBufLen",
                "json_type": "integer",
                "resolved_type": "DWORD",
                "description": "Length of the output buffer, e.g., 64.",
            },
        ],
    }
    admission_trace = {}

    aligned = _align_prerequisite_args(
        inv,
        {
            "lpszSku": "GDG-SM-RED",
            "wQty": "GDG-SM-RED",
            "dwHoldMinutes": 30,
            "pOutResvId": "",
            "dwBufLen": 64,
        },
        {"sku": "GDG-SM-RED"},
        {},
        admission_trace=admission_trace,
    )

    repaired, selection = _repair_target_scalar_args(
        inv,
        aligned,
        {},
        {},
        None,
        lineage_hints={"sku": "GDG-SM-RED"},
        prefer_lineage=True,
    )

    assert aligned["wQty"] == 2
    assert repaired["wQty"] == 2
    assert "wQty" not in selection
    assert admission_trace["wQty"]["expected_family"] == "quantity"


def test_repair_target_scalar_args_prefers_expected_nonce_family_over_ticket_shaped_current_value() -> None:
    inv = {
        "name": "CFG_ApproveLicensedCall",
        "doc_comment": (
            'Required preconditions: CFG_GetLicenseNonce | Canonical args: '
            '{"dwNonce": "nonce-from-read", "lpszTicket": "ticket-from-open"}'
        ),
        "parameters": [
            {
                "name": "lpszTicket",
                "json_type": "string",
                "resolved_type": "LPCSTR",
                "description": "Ticket returned by CFG_OpenLicensedWindow",
            },
            {
                "name": "dwNonce",
                "json_type": "integer",
                "resolved_type": "DWORD",
                "description": "Nonce returned by CFG_GetLicenseNonce",
            },
        ],
    }

    repaired, selection = _repair_target_scalar_args(
        inv,
        {
            "lpszTicket": "CFG-CUST-001-38",
            "dwNonce": "CFG-CUST-001-38",
        },
        {},
        {},
        None,
        lineage_hints={"ticket": "CFG-CUST-001-38", "nonce": 3235774499},
        prefer_lineage=True,
    )

    assert repaired["lpszTicket"] == "CFG-CUST-001-38"
    assert repaired["dwNonce"] == 3235774499
    assert selection["dwNonce"]["expected_family"] == "nonce"
    assert selection["dwNonce"]["source_lineage"] == "lineage_hint.nonce"


def test_repair_target_scalar_args_prefers_spectrum_preview_and_fee_families() -> None:
    inv = {
        "name": "SP_VerifyReservedRelease",
        "parameters": [
            {
                "name": "preview_ticket",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "Preview ticket returned by SP_PrepareReleasePreview",
            },
            {
                "name": "fee_quote_id",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "Fee quote id returned by SP_StageReleaseFeeQuote",
            },
        ],
    }

    repaired, selection = _repair_target_scalar_args(
        inv,
        {
            "preview_ticket": "ORD-001",
            "fee_quote_id": "sp-resv-ORD-001-64",
        },
        {},
        {},
        None,
        lineage_hints={
            "preview_ticket": "sp-preview-ORD-001-64-gate",
            "fee_quote_id": "sp-fee-ORD-001-64-quote",
        },
        prefer_lineage=True,
    )

    assert repaired["preview_ticket"] == "sp-preview-ORD-001-64-gate"
    assert repaired["fee_quote_id"] == "sp-fee-ORD-001-64-quote"
    assert selection["preview_ticket"]["expected_family"] == "preview_ticket"
    assert selection["preview_ticket"]["source_lineage"] == "lineage_hint.preview_ticket"
    assert selection["fee_quote_id"]["expected_family"] == "fee_quote_id"
    assert selection["fee_quote_id"]["source_lineage"] == "lineage_hint.fee_quote_id"


def test_consumer_ready_lineage_hints_drop_non_live_family_sensitive_values_in_fresh_mode() -> None:
    hints = _consumer_ready_lineage_hints(
        {
            "reservation_handle": "sp-resv-ORD-001-64",
            "out_preview_ticket": "ORD-001",
            "out_fee_quote_id": "ORD-001",
        },
        fresh_lineage=True,
    )

    assert hints["reservation_id"] == "sp-resv-ORD-001-64"
    assert "preview_ticket" not in hints
    assert "fee_quote_id" not in hints


def test_repair_target_scalar_args_rejects_non_live_spectrum_family_lineage_hints() -> None:
    inv = {
        "name": "SP_VerifyReservedRelease",
        "doc_comment": (
            'Canonical args: {"preview_ticket": "sp-preview-ORD-001-64-gate", '
            '"fee_quote_id": "sp-fee-ORD-001-64-quote"}'
        ),
        "parameters": [
            {
                "name": "preview_ticket",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "Preview ticket returned by SP_PrepareReleasePreview",
            },
            {
                "name": "fee_quote_id",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "Fee quote id returned by SP_StageReleaseFeeQuote",
            },
        ],
    }

    repaired, selection = _repair_target_scalar_args(
        inv,
        {
            "preview_ticket": "sp-preview-ORD-001-64-gate",
            "fee_quote_id": "sp-fee-ORD-001-64-quote",
        },
        {},
        {},
        None,
        lineage_hints={
            "preview_ticket": "ORD-001",
            "fee_quote_id": "ORD-001",
        },
        prefer_lineage=True,
    )

    assert repaired["preview_ticket"] == "sp-preview-ORD-001-64-gate"
    assert repaired["fee_quote_id"] == "sp-fee-ORD-001-64-quote"
    assert "preview_ticket" not in selection
    assert "fee_quote_id" not in selection


def test_repair_target_scalar_args_repairs_settlement_receipts_from_canonical_args_without_evidence() -> None:
    inv = {
        "name": "SP_SelectTrustedBranch",
        "doc_comment": (
            'Required preconditions: SP_CommitRelease, SP_ReplayReleaseBranch | '
            'Canonical args: {"primary_commit_receipt": "sp-commit-ORD-001-4200-receipt", '
            '"replay_commit_receipt": "sp-branch-replay-ORD-001-64-receipt"}'
        ),
        "parameters": [
            {
                "name": "primary_commit_receipt",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "Primary commit receipt returned by SP_CommitRelease",
            },
            {
                "name": "replay_commit_receipt",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "Replay receipt returned by SP_ReplayReleaseBranch",
            },
        ],
    }

    repaired, selection = _repair_target_scalar_args(
        inv,
        {
            "primary_commit_receipt": "sp-resv-ORD-001-64",
            "replay_commit_receipt": "sp-hold-ORD-001-64",
        },
        {},
        {},
        None,
        lineage_hints=None,
        prefer_lineage=False,
    )

    assert repaired["primary_commit_receipt"] == "sp-commit-ORD-001-4200-receipt"
    assert repaired["replay_commit_receipt"] == "sp-branch-replay-ORD-001-64-receipt"
    assert selection["primary_commit_receipt"]["source"] == "doc.canonical_args"
    assert selection["primary_commit_receipt"]["expected_family"] == "primary_commit_receipt"
    assert selection["replay_commit_receipt"]["source"] == "doc.canonical_args"
    assert selection["replay_commit_receipt"]["expected_family"] == "replay_commit_receipt"


def test_repair_target_scalar_args_uses_exact_canonical_receipts_when_descriptions_are_generic() -> None:
    inv = {
        "name": "SP_SelectTrustedBranch",
        "doc_comment": (
            'Canonical args: {"primary_commit_receipt": "sp-commit-ORD-001-4200-receipt", '
            '"replay_commit_receipt": "sp-branch-replay-ORD-001-64-receipt"}'
        ),
        "parameters": [
            {
                "name": "primary_commit_receipt",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "SP_SelectTrustedBranch parameter",
            },
            {
                "name": "replay_commit_receipt",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "SP_SelectTrustedBranch parameter",
            },
        ],
    }

    repaired, selection = _repair_target_scalar_args(
        inv,
        {
            "primary_commit_receipt": "sp-resv-ORD-001-64",
            "replay_commit_receipt": "sp-hold-ORD-001-64",
        },
        {},
        {},
        None,
        lineage_hints=None,
        prefer_lineage=False,
    )

    assert repaired["primary_commit_receipt"] == "sp-commit-ORD-001-4200-receipt"
    assert repaired["replay_commit_receipt"] == "sp-branch-replay-ORD-001-64-receipt"
    assert selection["primary_commit_receipt"]["source"] == "doc.canonical_args"
    assert selection["replay_commit_receipt"]["source"] == "doc.canonical_args"


def test_repair_target_scalar_args_rejects_invalid_preserved_commit_receipt_placeholders() -> None:
    inv = {
        "name": "SP_SelectTrustedBranch",
        "doc_comment": (
            'Required preconditions: SP_CommitRelease, SP_ReplayReleaseBranch | '
            'Canonical args: {"primary_commit_receipt": "sp-commit-ORD-001-4200-receipt", '
            '"replay_commit_receipt": "sp-branch-replay-ORD-001-64-receipt"}'
        ),
        "parameters": [
            {
                "name": "primary_commit_receipt",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "Primary commit receipt returned by SP_CommitRelease",
            },
            {
                "name": "replay_commit_receipt",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "Replay receipt returned by SP_ReplayReleaseBranch",
            },
        ],
    }
    ecr = EvidenceCandidateRegistry()
    ecr.add("valid_receipt", 2, "runtime:SP_CommitRelease", "commit_receipt", 1.0, "probe")
    ecr.add(
        "sp-branch-replay-ORD-001-64-receipt",
        2,
        "runtime:SP_ReplayReleaseBranch",
        "commit_receipt",
        1.0,
        "probe",
    )

    repaired, selection = _repair_target_scalar_args(
        inv,
        {
            "primary_commit_receipt": "valid_receipt",
            "replay_commit_receipt": "sp-branch-replay-ORD-001-64-receipt",
        },
        {},
        {},
        ecr,
        lineage_hints=None,
        prefer_lineage=False,
    )

    assert repaired["primary_commit_receipt"] == "sp-commit-ORD-001-4200-receipt"
    assert repaired["replay_commit_receipt"] == "sp-branch-replay-ORD-001-64-receipt"
    assert selection["primary_commit_receipt"]["source"] == "doc.canonical_args"
    assert "replay_commit_receipt" not in selection


def test_canonical_args_from_doc_ignores_trailing_doc_sections() -> None:
    parsed = _canonical_args_from_doc(
        'Required preconditions: SP_CommitRelease | Canonical args: '
        '{"primary_commit_receipt": "sp-commit-ORD-001-4200-receipt"} | '
        'Functional precondition example: "SP_CommitRelease(...) -> out_commit_receipt=\'sp-commit-ORD-001-4200-receipt\'"'
    )

    assert parsed == {"primary_commit_receipt": "sp-commit-ORD-001-4200-receipt"}


def test_align_prerequisite_args_prefers_nonce_family_when_nonce_description_mentions_ticket() -> None:
    prereq_inv = {
        "name": "CFG_ApproveLicensedCall",
        "parameters": [
            {
                "name": "lpszTicket",
                "json_type": "string",
                "resolved_type": "LPCSTR",
                "description": "Ticket identifier, e.g., 'CFG-CUST-001-55'. This ticket must be valid and previously obtained.",
            },
            {
                "name": "dwNonce",
                "json_type": "integer",
                "resolved_type": "DWORD",
                "description": "Nonce value for the request, which must match the nonce retrieved for the ticket.",
            },
        ],
    }
    trace: dict[str, dict] = {}

    aligned = _align_prerequisite_args(
        prereq_inv,
        {
            "lpszTicket": "CFG-CUST-001-38",
            "dwNonce": "CFG-CUST-001-38",
        },
        {"ticket": "CFG-CUST-001-38", "nonce": 3235774499},
        {},
        admission_trace=trace,
    )

    assert aligned["lpszTicket"] == "CFG-CUST-001-38"
    assert aligned["dwNonce"] == 3235774499
    assert trace["lpszTicket"]["expected_family"] == "ticket"
    assert trace["dwNonce"]["expected_family"] == "nonce"
    assert trace["dwNonce"]["source_lineage"] == "lineage_hint.nonce"


def test_retag_runtime_probe_roles_marks_putsamples_payload_buffer_as_input() -> None:
    inv = {
        "name": "soundtouch_putSamples_i16",
        "parameters": [
            {
                "name": "param_1",
                "type": "int *",
                "resolved_type": "int *",
                "direction": "out",
                "json_type": "integer",
                "description": "Output - receives integer result",
            },
            {
                "name": "param_2",
                "type": "float *",
                "resolved_type": "float *",
                "direction": "out",
                "json_type": "number",
                "description": "Parameter of type float *",
            },
            {
                "name": "param_3",
                "type": "uint",
                "resolved_type": "uint",
                "direction": "in",
                "json_type": "integer",
                "description": "sample count",
            },
        ],
        "execution": {
            "arg_types": ["int *", "float *", "uint"],
        },
        "doc_comment": "if (*param_1 == 0x1770c001) return 0x50000001;",
    }

    _retag_runtime_probe_roles(inv)

    assert inv["parameters"][0]["direction"] == "in"
    assert inv["parameters"][1]["direction"] == "in"
    assert inv["parameters"][1]["type"] == "short *"
    assert inv["parameters"][1]["resolved_type"] == "short *"
    assert "input sample payload" in inv["parameters"][1]["description"]
    assert inv["execution"]["arg_types"][1] == "short *"


def test_infer_runtime_prerequisites_bootstraps_soundtouch_family_chain() -> None:
    create_inv = {
        "name": "soundtouch_createInstance",
        "parameters": [],
        "return_type": "void *",
    }
    set_channels_inv = {
        "name": "soundtouch_setChannels",
        "parameters": [
            {
                "name": "param_1",
                "type": "int *",
                "resolved_type": "int *",
                "direction": "in",
                "json_type": "integer",
                "description": "opaque runtime handle input from a prior create/open/init call",
            },
            {
                "name": "param_2",
                "type": "uint",
                "resolved_type": "uint",
                "direction": "in",
                "json_type": "integer",
                "description": "channel count",
            },
        ],
    }
    set_rate_inv = {
        "name": "soundtouch_setSampleRate",
        "parameters": [
            {
                "name": "param_1",
                "type": "int *",
                "resolved_type": "int *",
                "direction": "in",
                "json_type": "integer",
                "description": "opaque runtime handle input from a prior create/open/init call",
            },
            {
                "name": "param_2",
                "type": "uint",
                "resolved_type": "uint",
                "direction": "in",
                "json_type": "integer",
                "description": "sample rate",
            },
        ],
    }
    put_samples_inv = {
        "name": "soundtouch_putSamples_i16",
        "parameters": [
            {
                "name": "param_1",
                "type": "int *",
                "resolved_type": "int *",
                "direction": "in",
                "json_type": "integer",
                "description": "opaque runtime handle input from a prior create/open/init call",
            },
            {
                "name": "param_2",
                "type": "short *",
                "resolved_type": "short *",
                "direction": "in",
                "json_type": "integer",
                "description": "input sample payload buffer",
            },
            {
                "name": "param_3",
                "type": "uint",
                "resolved_type": "uint",
                "direction": "in",
                "json_type": "integer",
                "description": "sample count",
            },
        ],
    }
    inv_map = {
        create_inv["name"]: create_inv,
        set_channels_inv["name"]: set_channels_inv,
        set_rate_inv["name"]: set_rate_inv,
        put_samples_inv["name"]: put_samples_inv,
    }

    assert _infer_runtime_prerequisites(set_rate_inv, inv_map) == ["soundtouch_createInstance"]
    assert _infer_runtime_prerequisites(put_samples_inv, inv_map) == [
        "soundtouch_createInstance",
        "soundtouch_setChannels",
        "soundtouch_setSampleRate",
    ]


def test_runtime_success_accepts_creator_handle_returns_and_merges_handle_artifact() -> None:
    inv = {
        "name": "soundtouch_createInstance",
        "return_type": "void *",
        "parameters": [],
    }
    sentinels = {0x50000001: "failure"}

    assert _is_runtime_success_value(
        inv,
        inv["name"],
        "Returned: 140733193388032 (pointer=0x00007FFAAABBCC00)",
        sentinels,
        False,
    )

    merged = _merge_runtime_success_values(
        inv,
        inv["name"],
        {},
        "Returned: 140733193388032 (pointer=0x00007FFAAABBCC00)",
        {},
        sentinels,
    )

    assert merged["handle"] == 140733193388032


def test_ranked_fallback_scaffolds_audio_pointer_payload_and_count() -> None:
    inv = {
        "name": "soundtouch_putSamples_i16",
        "parameters": [
            {
                "name": "param_1",
                "type": "int *",
                "resolved_type": "int *",
                "direction": "in",
                "json_type": "integer",
                "description": "opaque runtime handle input from a prior create/open/init call",
            },
            {
                "name": "param_2",
                "type": "float *",
                "resolved_type": "float *",
                "direction": "in",
                "json_type": "string",
                "description": "Parameter of type float *",
            },
            {
                "name": "param_3",
                "type": "uint",
                "resolved_type": "uint",
                "direction": "in",
                "json_type": "integer",
                "description": "sample count",
            },
        ],
    }

    args, selection = _build_ranked_fallback_probe_args(inv, vocab={})

    assert args["param_2"] == [0.0, 0.25, -0.25, 0.5, -0.5, 0.75, -0.75, 1.0]
    assert args["param_3"] == 4
    assert selection["param_2"]["source"] == "function_context.payload"
    assert selection["param_3"]["source"] == "payload.derived_count"


def test_ranked_fallback_retypes_misclassified_audio_scalars() -> None:
    inv = {
        "name": "bpm_createInstance",
        "parameters": [
            {
                "name": "param_1",
                "type": "undefined4",
                "resolved_type": "undefined4",
                "direction": "in",
                "json_type": "string",
                "description": "Parameter of type undefined4",
            },
            {
                "name": "param_2",
                "type": "int",
                "resolved_type": "int",
                "direction": "in",
                "json_type": "integer",
                "description": "Integer input parameter",
            },
        ],
    }

    args, selection = _build_ranked_fallback_probe_args(inv, vocab={})

    assert args["param_1"] == 2
    assert args["param_2"] == 44100
    assert selection["param_1"]["source"] == "function_context.audio"
    assert selection["param_2"]["source"] == "function_context.audio"


def test_ranked_fallback_prefers_tempo_scalar_values_over_generic_audio_slot() -> None:
    inv = {
        "name": "soundtouch_setTempo",
        "parameters": [
            {
                "name": "param_1",
                "type": "int *",
                "resolved_type": "int *",
                "direction": "in",
                "json_type": "integer",
                "description": "opaque runtime handle input from a prior create/open/init call",
            },
            {
                "name": "param_2",
                "type": "float",
                "resolved_type": "float",
                "direction": "in",
                "json_type": "number",
                "description": "Parameter of type float",
            },
        ],
    }

    args, selection = _build_ranked_fallback_probe_args(inv, vocab={})

    assert args["param_2"] == 1.0
    assert selection["param_2"]["source"] == "function_context.scalar"


def test_extract_required_preconditions_reads_doc_comment_contract() -> None:
    assert _extract_required_preconditions(_TRANSPORT_OPEN_INV) == ["TP_BindCustomer"]


def test_requires_fresh_runtime_lineage_for_blob_token_consumers() -> None:
    inv = {
        "name": "TP_FreeBlobToken",
        "parameters": [
            {"name": "dwBlobToken", "json_type": "integer", "description": "Opaque blob token to release"}
        ],
    }

    assert _requires_fresh_runtime_lineage(inv) is True


def test_requires_fresh_runtime_lineage_for_sequence_bound_ticket_and_nonce_consumers() -> None:
    inv = {
        "name": "CFG_ApproveLicensedCall",
        "_required_preconditions": ["CFG_GetLicenseNonce"],
        "_sequence_role": "lifecycle_transition",
        "parameters": [
            {"name": "lpszTicket", "json_type": "string", "description": "Licensed config ticket"},
            {"name": "dwNonce", "json_type": "integer", "description": "License nonce"},
        ],
    }

    assert _requires_fresh_runtime_lineage(inv) is True


def test_requires_fresh_runtime_lineage_for_prefix_hinted_lifecycle_consumers() -> None:
    inv = {
        "name": "SP_EmitReleaseAttestation",
        "parameters": [
            {"name": "param_1", "json_type": "string", "description": "generic input"},
            {"name": "param_2", "json_type": "string", "description": "generic input"},
        ],
        "doc_comment": (
            'if (strncmp(param_1, "sp-preview-", 0xb) != 0) return 0xFFFFFFFF; '
            'if (strncmp(param_2, "sp-fee-", 0x7) != 0) return 0xFFFFFFFF;'
        ),
    }

    assert _requires_fresh_runtime_lineage(inv) is True


def test_align_prerequisite_args_prefers_target_struct_customer_and_handle() -> None:
    prereq_inv = {
        "name": "TP_BindCustomer",
        "parameters": [
            {
                "name": "lpszCustId",
                "json_type": "string",
                "description": "Customer identifier",
            }
        ],
    }
    aligned = _align_prerequisite_args(
        prereq_inv,
        {"lpszCustId": "ACC-USB-C"},
        {"customer_id": "CUST-001"},
        {},
    )

    assert aligned["lpszCustId"] == "CUST-001"


def test_align_prerequisite_args_seeds_canonical_values_before_lineage_overlay() -> None:
    prereq_inv = {
        "name": "WF_CreateReservation",
        "parameters": [
            {"name": "lpszSku", "json_type": "string", "description": "SKU"},
            {"name": "wQty", "json_type": "integer", "description": "Quantity"},
            {"name": "dwHoldMinutes", "json_type": "integer", "description": "Hold duration"},
        ],
        "doc_comment": 'Required preconditions: WF_BindCustomer | Canonical args: {"lpszSku":"ACC-USB-C","wQty":2,"dwHoldMinutes":30}',
    }

    aligned = _align_prerequisite_args(
        prereq_inv,
        {"lpszSku": "CUST-001", "wQty": 1, "dwHoldMinutes": 1},
        {"customer_id": "CUST-001"},
        {},
    )

    assert aligned == {"lpszSku": "ACC-USB-C", "wQty": 2, "dwHoldMinutes": 30}


def test_align_prerequisite_args_overlays_reservation_lineage_on_placeholder() -> None:
    prereq_inv = {
        "name": "WF_OpenFulfillment",
        "parameters": [
            {"name": "lpszResvId", "json_type": "string", "description": "Reservation identifier"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
        "doc_comment": 'Required preconditions: WF_CreateReservation | Canonical args: {"lpszResvId":"reservation-from-create"}',
    }

    aligned = _align_prerequisite_args(
        prereq_inv,
        {"lpszResvId": "reservation-from-create", "dwBufLen": 64},
        {"reservation_id": "RESV-69CCA03E-0000"},
        {},
    )

    assert aligned["lpszResvId"] == "RESV-69CCA03E-0000"
    assert aligned["dwBufLen"] == 64


def test_align_prerequisite_args_prefers_workflow_handle_for_string_style_handle_param() -> None:
    prereq_inv = {
        "name": "WF_GetWorkflowNonce",
        "parameters": [
            {
                "name": "lpszHandle",
                "json_type": "integer",
                "type": "char*",
                "resolved_type": "LPCSTR",
                "description": "Workflow handle returned by WF_OpenFulfillment",
            },
            {
                "name": "pdwNonceOut",
                "json_type": "integer",
                "direction": "out",
                "description": "Workflow nonce output",
            },
        ],
    }

    aligned = _align_prerequisite_args(
        prereq_inv,
        {"lpszHandle": 1, "pdwNonceOut": ""},
        {"workflow_handle": "WFH-CUST-001-02"},
        {},
    )

    assert aligned["lpszHandle"] == "WFH-CUST-001-02"


def test_align_prerequisite_args_blocks_foreign_ticket_for_workflow_handle_and_records_trace() -> None:
    prereq_inv = {
        "name": "WF_GetWorkflowNonce",
        "parameters": [
            {
                "name": "lpszHandle",
                "json_type": "string",
                "type": "LPCSTR",
                "resolved_type": "LPCSTR",
                "description": "Workflow handle returned by WF_OpenFulfillment",
            },
            {
                "name": "pdwNonceOut",
                "json_type": "integer",
                "direction": "out",
                "description": "Workflow nonce output",
            },
        ],
    }
    trace: dict[str, dict] = {}

    aligned = _align_prerequisite_args(
        prereq_inv,
        {"lpszHandle": "CFG-CUST-001-09", "pdwNonceOut": ""},
        {"workflow_handle": "WFH-CUST-001-02"},
        {},
        admission_trace=trace,
    )

    assert aligned["lpszHandle"] == "WFH-CUST-001-02"
    assert trace["lpszHandle"]["expected_family"] == "workflow_handle"
    assert trace["lpszHandle"]["candidate_family"] == "workflow_handle"
    assert trace["lpszHandle"]["source_lineage"] == "lineage_hint.workflow_handle"
    assert trace["lpszHandle"]["admission_decision"] == "admitted_same_family_hint_after_block"


def test_align_prerequisite_args_defaults_nonce_after_ticket_envelope_contamination() -> None:
    prereq_inv = {
        "name": "CFG_GetLicenseNonce",
        "parameters": [
            {
                "name": "dwNonce",
                "json_type": "integer",
                "type": "DWORD",
                "resolved_type": "DWORD",
                "description": "License nonce",
            }
        ],
    }
    trace: dict[str, dict] = {}

    aligned = _align_prerequisite_args(
        prereq_inv,
        {"dwNonce": "licensed|cust=CUST-001|approved=1"},
        {},
        {},
        admission_trace=trace,
    )

    assert isinstance(aligned["dwNonce"], int)
    assert aligned["dwNonce"] > 0
    assert trace["dwNonce"]["source_lineage"] == "semantic_default.nonce"
    assert trace["dwNonce"]["admission_decision"] == "defaulted_after_incompatible_value"


def test_align_prerequisite_args_rejects_placeholder_quote_id_and_defaults_trace() -> None:
    prereq_inv = {
        "name": "PR_GetQuoteNonce",
        "parameters": [
            {
                "name": "lpszQuoteId",
                "json_type": "string",
                "type": "LPCSTR",
                "resolved_type": "LPCSTR",
                "description": "Quote identifier",
            }
        ],
        "doc_comment": 'Canonical args: {"lpszQuoteId":"quote-from-begin"}',
    }
    trace: dict[str, dict] = {}

    aligned = _align_prerequisite_args(
        prereq_inv,
        {},
        {},
        {},
        admission_trace=trace,
    )

    assert aligned["lpszQuoteId"] == "TEST"
    assert trace["lpszQuoteId"]["placeholder_detected"] is True
    assert trace["lpszQuoteId"]["source_lineage"] == "semantic_default.quote_id"
    assert trace["lpszQuoteId"]["admission_decision"] == "defaulted_after_incompatible_value"


def test_align_prerequisite_args_rejects_placeholder_report_id_and_defaults_trace() -> None:
    prereq_inv = {
        "name": "RP_GetReportNonce",
        "parameters": [
            {
                "name": "lpszReportId",
                "json_type": "string",
                "type": "LPCSTR",
                "resolved_type": "LPCSTR",
                "description": "Report identifier",
            }
        ],
        "doc_comment": 'Canonical args: {"lpszReportId":"report-from-prepare"}',
    }
    trace: dict[str, dict] = {}

    aligned = _align_prerequisite_args(
        prereq_inv,
        {},
        {},
        {},
        admission_trace=trace,
    )

    assert aligned["lpszReportId"] == "TEST"
    assert trace["lpszReportId"]["placeholder_detected"] is True
    assert trace["lpszReportId"]["source_lineage"] == "semantic_default.report_id"
    assert trace["lpszReportId"]["admission_decision"] == "defaulted_after_incompatible_value"


def test_align_prerequisite_args_maps_canonical_customer_to_generic_param_from_description() -> None:
    prereq_inv = {
        "name": "WF_BindCustomer",
        "parameters": [
            {
                "name": "param_1",
                "json_type": "integer",
                "description": "Customer ID as a string (e.g., 'CUST-001').",
            }
        ],
        "doc_comment": 'Required preconditions: WF_Initialize | Canonical args: {"lpszCustId":"CUST-001"}',
    }

    aligned = _align_prerequisite_args(
        prereq_inv,
        {"param_1": 1},
        {"customer_id": "CUST-001"},
        {},
    )

    assert aligned["param_1"] == "CUST-001"


def test_align_prerequisite_args_maps_lineage_handle_to_generic_runtime_handle_param() -> None:
    prereq_inv = {
        "name": "soundtouch_setChannels",
        "parameters": [
            {
                "name": "param_1",
                "json_type": "integer",
                "type": "int *",
                "resolved_type": "int *",
                "description": "opaque runtime handle input from a prior create/open/init call",
            },
            {
                "name": "param_2",
                "json_type": "integer",
                "description": "channel count",
            },
        ],
    }

    aligned = _align_prerequisite_args(
        prereq_inv,
        {"param_1": "", "param_2": 2},
        {"handle": 140733193388032},
        {},
    )

    assert aligned["param_1"] == 140733193388032
    assert aligned["param_2"] == 2


def test_align_prerequisite_args_maps_canonical_prepare_report_values_to_generic_params() -> None:
    prereq_inv = {
        "name": "RP_PrepareReservationReport",
        "parameters": [
            {"name": "param_1", "json_type": "integer", "description": "SKU to include in the report."},
            {"name": "param_2", "json_type": "integer", "description": "Quantity to reserve for the report."},
            {"name": "param_3", "json_type": "integer", "description": "How many minutes to hold the reservation."},
            {"name": "param_4", "json_type": "integer", "description": "Output report buffer."},
            {"name": "param_5", "json_type": "integer", "description": "Output buffer size."},
        ],
        "doc_comment": (
            'Required preconditions: RP_BindCustomer | Canonical args: '
            '{"lpszSku":"ACC-USB-C","wQty":2,"dwHoldMinutes":30}'
        ),
    }

    aligned = _align_prerequisite_args(
        prereq_inv,
        {"param_1": 1, "param_2": 1, "param_3": "RESV-69C715E0-000B", "param_5": 64},
        {"customer_id": "CUST-001", "sku": "ACC-USB-C"},
        {},
    )

    assert aligned["param_1"] == "ACC-USB-C"
    assert aligned["param_2"] == 2
    assert aligned["param_3"] == 30
    assert aligned["param_5"] == 64


def test_align_prerequisite_args_repairs_live_workflow_reservation_producer_semantics() -> None:
    prereq_inv = {
        "name": "WF_CreateReservation",
        "parameters": [
            {
                "name": "lpszSku",
                "json_type": "integer",
                "description": "The SKU of the product being reserved (e.g., 'ACC-USB-C').",
            },
            {
                "name": "wQty",
                "json_type": "integer",
                "description": "The quantity of the product to reserve (must be greater than 0, e.g., 2).",
            },
            {
                "name": "dwHoldMinutes",
                "json_type": "string",
                "description": "Duration in minutes for which the reservation is held (e.g., 30).",
            },
            {
                "name": "dwBufLen",
                "json_type": "integer",
                "description": "Buffer length for the operation (e.g., 64).",
            },
        ],
    }

    aligned = _align_prerequisite_args(
        prereq_inv,
        {"lpszSku": 1, "wQty": 1, "dwHoldMinutes": "CUST-001", "dwBufLen": 64},
        {"customer_id": "CUST-001"},
        {"binary_string_ids": ["ACC-USB-C"]},
    )

    assert aligned["lpszSku"] == "ACC-USB-C"
    assert aligned["wQty"] == 1
    assert aligned["dwHoldMinutes"] == 30
    assert aligned["dwBufLen"] == 64


def test_align_prerequisite_args_seeds_customer_for_generic_bind_param_without_hints() -> None:
    prereq_inv = {
        "name": "WF_BindCustomer",
        "parameters": [
            {
                "name": "param_1",
                "json_type": "integer",
                "description": "Parameter recovered by Ghidra decompiler",
                "resolved_type": "char *",
            }
        ],
    }

    aligned = _align_prerequisite_args(
        prereq_inv,
        {"param_1": 1},
        {},
        {"id_formats": ["CUST-001", "CUST-004"]},
    )

    assert aligned["param_1"] == "CUST-001"


def test_bridge_build_flat_struct_instance_handles_char_arrays_and_scalars() -> None:
    struct_def = _TRANSPORT_OPEN_INV["_ghidra_extras"]["data_types"][0]

    instance = _bridge_build_flat_struct_instance(
        struct_def,
        {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2},
    )

    assert instance is not None
    assert bytes(instance.szCustId).split(b"\x00", 1)[0] == b"CUST-001"
    assert instance.dwFlags == 1
    assert instance.dwMode == 2


def test_bridge_struct_to_dict_serializes_output_structs() -> None:
    struct_def = {
        "kind": "struct",
        "name": "TP_SESSION_STATE",
        "fields": [
            {"name": "dwSessionHandle", "type": "DWORD"},
            {"name": "dwLastNonce", "type": "DWORD"},
            {"name": "dwFlags", "type": "DWORD"},
            {"name": "dwBlobToken", "type": "DWORD"},
        ],
    }
    instance = _bridge_build_flat_struct_instance(
        struct_def,
        {
            "dwSessionHandle": 1073745921,
            "dwLastNonce": 16818177,
            "dwFlags": 1,
            "dwBlobToken": 1879048193,
        },
    )

    assert instance is not None
    assert _bridge_struct_to_dict(instance, struct_def) == {
        "dwSessionHandle": 1073745921,
        "dwLastNonce": 16818177,
        "dwFlags": 1,
        "dwBlobToken": 1879048193,
    }


def test_augment_structured_probe_args_adds_required_scalar_out_slot() -> None:
    inv = {
        "name": "TP_OpenSession",
        "parameters": [
            {
                "name": "pReq",
                "type": "TP_OPEN_REQ*",
                "resolved_type": "TP_OPEN_REQ*",
                "direction": "in",
                "json_type": "object",
            },
            {
                "name": "pdwHandleOut",
                "type": "DWORD*",
                "resolved_type": "DWORD*",
                "direction": "out",
                "json_type": "integer",
            },
        ],
    }
    args = {"pReq": {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2}}
    selection = {"pReq": {"source": "structured.scaffolder"}}

    augmented_args, augmented_selection = _augment_structured_probe_args_for_mixed_calls(
        inv, args, selection
    )

    assert augmented_args["pdwHandleOut"] == ""
    assert augmented_selection["pdwHandleOut"]["source"] == "structured.out_slot"


def test_repair_target_structured_args_replaces_scalar_object_slot() -> None:
    inv = {
        "name": "TP_OpenSession",
        "parameters": [
            {
                "name": "pReq",
                "type": "TP_OPEN_REQ*",
                "resolved_type": "TP_OPEN_REQ*",
                "direction": "in",
                "json_type": "object",
            },
            {
                "name": "pdwHandleOut",
                "type": "DWORD*",
                "resolved_type": "DWORD*",
                "direction": "out",
                "json_type": "integer",
            },
        ],
    }
    repaired_args, repaired_selection = _repair_target_structured_args(
        inv,
        {"pReq": "CUST-001"},
        {},
        {"pReq": {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2}},
        {"pReq": {"source": "structured.scaffolder"}},
    )

    assert repaired_args["pReq"] == {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2}
    assert repaired_args["pdwHandleOut"] == ""
    assert repaired_selection["pReq"]["source"] == "structured.scaffolder"


def test_repair_target_structured_args_uses_scaffold_when_live_json_type_is_string() -> None:
    inv = {
        "name": "TP_OpenSession",
        "parameters": [
            {
                "name": "pReq",
                "type": "TP_OPEN_REQ*",
                "resolved_type": "TP_OPEN_REQ*",
                "direction": "in",
                "json_type": "string",
            },
            {
                "name": "pdwHandleOut",
                "type": "DWORD*",
                "resolved_type": "DWORD*",
                "direction": "out",
                "json_type": "integer",
            },
        ],
    }

    repaired_args, repaired_selection = _repair_target_structured_args(
        inv,
        {"pReq": "ACC-USB-C"},
        {},
        {"pReq": {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2}},
        {"pReq": {"source": "structured.scaffolder"}},
    )

    assert repaired_args["pReq"] == {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2}
    assert repaired_args["pdwHandleOut"] == ""


def test_repair_target_scalar_args_prefers_runtime_handle_for_session_param() -> None:
    inv = {
        "name": "TP_GetSessionNonce",
        "parameters": [
            {
                "name": "dwSessionHandle",
                "type": "DWORD",
                "json_type": "integer",
                "description": "Opaque session handle returned by TP_OpenSession",
            },
            {
                "name": "pdwNonceOut",
                "type": "DWORD*",
                "direction": "out",
                "json_type": "integer",
                "description": "Output nonce",
            },
        ],
    }
    ecr = EvidenceCandidateRegistry()
    ecr.add(1073745921, 2, "runtime:TP_OpenSession", "handle", 1.0, "TP_OpenSession")

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {"dwSessionHandle": 1, "pdwNonceOut": ""},
        {},
        {},
        ecr,
    )

    assert repaired_args["dwSessionHandle"] == 1073745921
    assert repaired_selection["dwSessionHandle"]["source"].startswith("evidence.")


def test_repair_target_scalar_args_preserves_pointer_payload_lists() -> None:
    inv = {
        "name": "soundtouch_putSamples_i16",
        "parameters": [
            {
                "name": "param_1",
                "type": "int *",
                "resolved_type": "int *",
                "direction": "in",
                "json_type": "integer",
                "description": "opaque runtime handle input from a prior create/open/init call",
            },
            {
                "name": "param_2",
                "type": "short *",
                "resolved_type": "short *",
                "direction": "in",
                "json_type": "integer",
                "description": "input sample payload buffer",
            },
            {
                "name": "param_3",
                "type": "uint",
                "resolved_type": "uint",
                "direction": "in",
                "json_type": "integer",
                "description": "sample count",
            },
        ],
    }
    ecr = EvidenceCandidateRegistry()

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {"param_1": 2, "param_2": [0, 512, -512, 1024], "param_3": 4},
        {},
        {},
        ecr,
        lineage_hints={"handle": 140733193388032},
        prefer_lineage=True,
    )

    assert repaired_args["param_1"] == 140733193388032
    assert repaired_args["param_2"] == [0, 512, -512, 1024]
    assert repaired_selection["param_1"]["source"] == "lineage.same_run"


def test_repair_target_scalar_args_replaces_sku_like_customer_value() -> None:
    inv = {
        "name": "TP_BindCustomer",
        "parameters": [
            {
                "name": "lpszCustId",
                "type": "LPCSTR",
                "json_type": "string",
                "description": "Customer identifier",
            }
        ],
    }
    ecr = EvidenceCandidateRegistry()
    ecr.add("CUST-001", 2, "runtime:TP_BindCustomer", "customer_id", 1.0, "TP_BindCustomer")

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {"lpszCustId": "ACC-USB-C"},
        {},
        {"id_formats": ["CUST-001"], "binary_string_ids": ["ACC-USB-C", "CUST-001"]},
        ecr,
    )

    assert repaired_args["lpszCustId"] == "CUST-001"
    assert repaired_selection["lpszCustId"]["source"].startswith("evidence.")


def test_repair_target_scalar_args_normalizes_incompatible_numeric_semantic_slots() -> None:
    inv = {
        "name": "RP_PrepareReservationReport",
        "parameters": [
            {"name": "lpszSku", "json_type": "string", "description": "SKU"},
            {"name": "wQty", "json_type": "integer", "description": "Quantity to reserve"},
            {"name": "dwHoldMinutes", "json_type": "integer", "description": "Hold duration in minutes"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Output buffer size"},
        ],
    }

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {
            "lpszSku": "ACC-USB-C",
            "wQty": "ACC-USB-C",
            "dwHoldMinutes": "ACC-USB-C",
            "dwBufLen": "RPT-CUST-001-02",
        },
        {
            "lpszSku": {"source": "static_id"},
            "wQty": {"source": "static_id"},
            "dwHoldMinutes": {"source": "static_id"},
            "dwBufLen": {"source": "static_id"},
        },
        {},
        evidence=None,
    )

    assert repaired_args["wQty"] == 2
    assert repaired_args["dwHoldMinutes"] == 30
    assert repaired_args["dwBufLen"] == 64
    assert repaired_selection["wQty"]["source"] == "semantic.numeric_guard"
    assert repaired_selection["dwHoldMinutes"]["source"] == "semantic.numeric_guard"
    assert repaired_selection["dwBufLen"]["source"] == "semantic.numeric_guard"


def test_repair_target_scalar_args_normalizes_misclassified_quantity_slot() -> None:
    inv = {
        "name": "WF_CreateReservation",
        "parameters": [
            {"name": "lpszSku", "json_type": "string", "description": "SKU"},
            {
                "name": "wQty",
                "json_type": "string",
                "description": "Quantity to reserve",
            },
            {
                "name": "dwHoldMinutes",
                "json_type": "string",
                "description": "Hold duration in minutes",
            },
        ],
    }

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {
            "lpszSku": "ACC-USB-C",
            "wQty": "ACC-USB-C",
            "dwHoldMinutes": "ACC-USB-C",
        },
        {},
        {},
        evidence=None,
    )

    assert repaired_args["wQty"] == 2
    assert repaired_args["dwHoldMinutes"] == 30
    assert repaired_selection["wQty"]["source"] == "semantic.numeric_guard"
    assert repaired_selection["dwHoldMinutes"]["source"] == "semantic.numeric_guard"


def test_repair_target_scalar_args_keeps_repaired_quantity_numeric_under_evidence_ranking() -> None:
    inv = {
        "name": "WF_CreateReservation",
        "parameters": [
            {"name": "lpszSku", "json_type": "string", "description": "SKU"},
            {
                "name": "wQty",
                "json_type": "string",
                "description": "Quantity to reserve",
            },
        ],
        "doc_comment": 'Canonical args: {"lpszSku":"ACC-USB-C","wQty":"ACC-USB-C"}',
    }
    ecr = EvidenceCandidateRegistry()
    ecr.add("ACC-USB-C", 2, "runtime:WF_CreateReservation", "sku", 0.9, "WF_CreateReservation")

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {
            "lpszSku": "ACC-USB-C",
            "wQty": "ACC-USB-C",
        },
        {},
        {"binary_string_ids": ["ACC-USB-C"]},
        evidence=ecr,
    )

    assert repaired_args["wQty"] == 2
    assert repaired_selection["wQty"]["source"] == "semantic.numeric_guard"


def test_repair_target_scalar_args_preserves_integer_prereq_numeric_slots_under_evidence_ranking() -> None:
    inv = {
        "name": "WF_CreateReservation",
        "parameters": [
            {"name": "lpszSku", "json_type": "string", "description": "SKU"},
            {"name": "wQty", "json_type": "integer", "description": "Quantity to reserve"},
            {
                "name": "dwHoldMinutes",
                "json_type": "integer",
                "description": "Hold duration in minutes",
            },
        ],
        "doc_comment": 'Canonical args: {"lpszSku":"ACC-USB-C","wQty":2,"dwHoldMinutes":30}',
    }
    ecr = EvidenceCandidateRegistry()
    ecr.add("ACC-USB-C", 2, "runtime:WF_CreateReservation", "sku", 0.9, "WF_CreateReservation")
    ecr.add("ACC-USB-C", 30, "runtime:WF_CreateReservation", "sku", 0.85, "WF_CreateReservation")

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {
            "lpszSku": "ACC-USB-C",
            "wQty": "ACC-USB-C",
            "dwHoldMinutes": "ACC-USB-C",
        },
        {},
        {"binary_string_ids": ["ACC-USB-C"]},
        evidence=ecr,
    )

    assert repaired_args["wQty"] == 2
    assert repaired_args["dwHoldMinutes"] == 30
    assert repaired_selection["wQty"]["source"] == "semantic.numeric_guard"
    assert repaired_selection["dwHoldMinutes"]["source"] == "semantic.numeric_guard"


def test_repair_target_scalar_args_does_not_reuse_sku_lineage_for_integer_quantity_slot() -> None:
    inv = {
        "name": "WF_CreateReservation",
        "parameters": [
            {
                "name": "lpszSku",
                "json_type": "string",
                "resolved_type": "LPCSTR",
                "description": "SKU of the product being reserved, such as 'GDG-SM-RED'.",
            },
            {
                "name": "wQty",
                "json_type": "integer",
                "resolved_type": "WORD",
                "description": "Quantity of the product to reserve, e.g., 1.",
            },
            {
                "name": "dwHoldMinutes",
                "json_type": "integer",
                "resolved_type": "DWORD",
                "description": "Duration in minutes for which the reservation is held, e.g., 30.",
            },
        ],
        "doc_comment": 'Canonical args: {"dwHoldMinutes": 30, "lpszSku": "ACC-USB-C", "wQty": 2}',
    }

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {
            "lpszSku": "GDG-SM-RED",
            "wQty": "GDG-SM-RED",
            "dwHoldMinutes": 30,
        },
        {},
        {},
        evidence=None,
        lineage_hints={"sku": "GDG-SM-RED"},
        prefer_lineage=True,
    )

    assert repaired_args["lpszSku"] == "GDG-SM-RED"
    assert repaired_args["wQty"] == 2
    assert repaired_args["dwHoldMinutes"] == 30
    assert repaired_selection["wQty"]["source"] == "semantic.numeric_guard"


def test_repair_target_scalar_args_prefers_same_run_ticket_and_nonce_lineage() -> None:
    inv = {
        "name": "CFG_ApproveLicensedCall",
        "parameters": [
            {
                "name": "lpszTicket",
                "type": "LPCSTR",
                "json_type": "string",
                "description": "Licensed config ticket",
            },
            {
                "name": "dwNonce",
                "type": "DWORD",
                "json_type": "integer",
                "description": "License nonce",
            },
        ],
    }
    ecr = EvidenceCandidateRegistry()
    ecr.add("CFG-CUST-001-01", 2, "runtime:CFG_OpenLicensedWindow", "string_id", 0.9, "CFG_OpenLicensedWindow")
    ecr.add(3235774513, 2, "runtime:CFG_GetLicenseNonce", "nonce", 0.9, "CFG_GetLicenseNonce")

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {"lpszTicket": "CFG-CUST-001-01", "dwNonce": 3235774513},
        {},
        {},
        ecr,
        lineage_hints={"ticket": "CFG-CUST-001-86", "nonce": 3235774548},
        prefer_lineage=True,
    )

    assert repaired_args == {"lpszTicket": "CFG-CUST-001-86", "dwNonce": 3235774548}
    assert repaired_selection["lpszTicket"]["source"] == "lineage.same_run"
    assert repaired_selection["dwNonce"]["source"] == "lineage.same_run"


def test_is_seeded_external_success_only_marks_seeded_prior_sources() -> None:
    assert _is_seeded_external_success(
        {"source": "prior_session", "working_call": {"lpszHandle": "WFH-CUST-001-02"}}
    ) is True
    assert _is_seeded_external_success(
        {"source": "cross_dll_prior", "working_call": {"lpszHandle": "WFH-CUST-001-02"}}
    ) is True
    assert _is_seeded_external_success(
        {"working_call": {"lpszHandle": "WFH-CUST-001-02"}}
    ) is False


def test_sanitize_lineage_hints_for_prereq_replay_drops_rebuilt_state_keys() -> None:
    sanitized = _sanitize_lineage_hints_for_prereq_replay(
        {
            "customer_id": "CUST-001",
            "sku": "ACC-USB-C",
            "ticket": "CFG-CUST-001-09",
            "workflow_handle": "WFH-CUST-001-02",
            "quote_id": "PRQ-CUST-001-01",
            "report_id": "RPT-CUST-001-02",
            "nonce": 2511030275,
        },
        fresh_lineage=True,
    )

    assert sanitized == {
        "customer_id": "CUST-001",
        "sku": "ACC-USB-C",
    }


def test_repair_target_scalar_args_prefers_same_run_quote_id_over_generic_customer_id() -> None:
    inv = {
        "name": "PR_GetQuoteNonce",
        "parameters": [
            {
                "name": "lpszQuoteId",
                "type": "LPCSTR",
                "json_type": "string",
                "description": "Open quote identifier",
            },
            {
                "name": "pdwNonceOut",
                "type": "DWORD*",
                "direction": "out",
                "json_type": "integer",
                "description": "Quote nonce output",
            },
        ],
    }

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {"lpszQuoteId": "CUST-001", "pdwNonceOut": ""},
        {},
        {"id_formats": ["CUST-001", "PRQ-CUST-001-01"]},
        None,
        lineage_hints={"quote_id": "PRQ-CUST-001-01"},
        prefer_lineage=True,
    )

    assert repaired_args["lpszQuoteId"] == "PRQ-CUST-001-01"
    assert repaired_selection["lpszQuoteId"]["source"] == "lineage.same_run"


def test_repair_target_scalar_args_maps_workflow_handle_lineage_to_misclassified_string_slot() -> None:
    inv = {
        "name": "WF_GetWorkflowState",
        "parameters": [
            {
                "name": "lpszHandle",
                "type": "char *",
                "resolved_type": "LPCSTR",
                "json_type": "integer",
                "description": "Workflow handle returned by WF_OpenFulfillment",
            },
            {
                "name": "pOutBuf",
                "type": "LPSTR",
                "resolved_type": "LPSTR",
                "direction": "out",
                "json_type": "string",
                "description": "Workflow state output buffer",
            },
            {
                "name": "dwBufLen",
                "type": "DWORD",
                "resolved_type": "DWORD",
                "json_type": "integer",
                "description": "Output buffer size",
            },
        ],
    }

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {"lpszHandle": 1073745928, "pOutBuf": "", "dwBufLen": 64},
        {},
        {},
        None,
        lineage_hints={"workflow_handle": "WFH-CUST-001-02"},
        prefer_lineage=True,
    )

    assert repaired_args["lpszHandle"] == "WFH-CUST-001-02"
    assert repaired_selection["lpszHandle"]["source"] == "lineage.same_run"
    assert repaired_selection["lpszHandle"]["candidate_family"] == "workflow_handle"
    assert repaired_selection["lpszHandle"]["expected_family"] == "workflow_handle"
    assert repaired_selection["lpszHandle"]["source_lineage"] == "lineage_hint.workflow_handle"
    assert repaired_selection["lpszHandle"]["fresh_replay_required"] is True


def test_repair_target_scalar_args_replaces_foreign_ticket_with_overlap_quote_id() -> None:
    inv = {
        "name": "PR_SealQuote",
        "parameters": [
            {
                "name": "lpszQuoteId",
                "type": "LPCSTR",
                "json_type": "string",
                "description": "Quote identifier",
            }
        ],
    }
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

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {"lpszQuoteId": "licensed|cust=CUST-001|approved=1"},
        {},
        {},
        ecr,
    )

    assert repaired_args["lpszQuoteId"] == "PRQ-CUST-001-03"
    assert repaired_selection["lpszQuoteId"]["candidate_family"] == "quote_id"
    assert "same_identifier_family" in repaired_selection["lpszQuoteId"]["selection_flags"]


def test_repair_target_scalar_args_replaces_foreign_ticket_with_overlap_workflow_handle() -> None:
    inv = {
        "name": "WF_CancelWorkflow",
        "parameters": [
            {
                "name": "lpszHandle",
                "type": "LPCSTR",
                "json_type": "string",
                "description": "Workflow handle",
            }
        ],
    }
    ecr = EvidenceCandidateRegistry()
    ecr.add(
        "CFG-CUST-001-09",
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

    repaired_args, repaired_selection = _repair_target_scalar_args(
        inv,
        {"lpszHandle": "CFG-CUST-001-09"},
        {},
        {},
        ecr,
    )

    assert repaired_args["lpszHandle"] == "WFH-CUST-001-02"
    assert repaired_selection["lpszHandle"]["candidate_family"] == "workflow_handle"
    assert "same_identifier_family" in repaired_selection["lpszHandle"]["selection_flags"]


def test_choose_best_observed_success_prefers_semantically_aligned_customer_value() -> None:
    inv = {
        "name": "TP_BindCustomer",
        "parameters": [
            {
                "name": "lpszCustId",
                "type": "LPCSTR",
                "json_type": "string",
                "description": "Customer identifier",
            }
        ],
    }
    ecr = EvidenceCandidateRegistry()
    ecr.add("CUST-001", 2, "runtime:TP_BindCustomer", "customer_id", 1.0, "TP_BindCustomer")

    best = _choose_best_observed_success(
        inv,
        [{"lpszCustId": "ACC-USB-C"}, {"lpszCustId": "CUST-001"}],
        {"id_formats": ["CUST-001"], "binary_string_ids": ["ACC-USB-C", "CUST-001"]},
        ecr,
    )

    assert best == {"lpszCustId": "CUST-001"}


def test_choose_best_observed_success_prefers_fresher_state_when_scores_tie() -> None:
    inv = {
        "name": "TP_OpenSession",
        "parameters": [
            {
                "name": "pReq",
                "type": "TP_OPEN_REQ*",
                "resolved_type": "TP_OPEN_REQ*",
                "direction": "in",
                "json_type": "object",
                "description": "Input transport open struct",
            },
            {
                "name": "pdwHandleOut",
                "type": "DWORD*",
                "resolved_type": "DWORD*",
                "direction": "out",
                "json_type": "integer",
                "description": "Output session handle",
            },
        ],
    }

    best = _choose_best_observed_success(
        inv,
        [
            {"pReq": {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2}, "pdwHandleOut": 1073745921},
            {"pReq": {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2}, "pdwHandleOut": 1073745925},
        ],
        {"id_formats": ["CUST-001"]},
        None,
    )

    assert best["pdwHandleOut"] == 1073745925


def test_normalize_true_output_scalar_args_rewrites_numeric_placeholder_to_allocated_slot() -> None:
    inv = {
        "name": "TP_GetSessionNonce",
        "parameters": [
            {
                "name": "dwSessionHandle",
                "type": "DWORD",
                "resolved_type": "DWORD",
                "direction": "in",
                "json_type": "integer",
            },
            {
                "name": "pdwNonceOut",
                "type": "DWORD*",
                "resolved_type": "DWORD*",
                "direction": "out",
                "json_type": "integer",
            },
        ],
    }

    normalized_args, normalized_selection = _normalize_true_output_scalar_args(
        inv,
        {"dwSessionHandle": 1, "pdwNonceOut": 0},
        {},
    )

    assert normalized_args["pdwNonceOut"] == ""
    assert normalized_selection["pdwNonceOut"]["source"] == "output.bridge_slot"


def test_normalize_true_output_scalar_args_rewrites_string_output_buffer_to_bridge_slot() -> None:
    inv = {
        "name": "WF_GetWorkflowState",
        "parameters": [
            {
                "name": "lpszHandle",
                "type": "LPCSTR",
                "direction": "in",
                "json_type": "string",
            },
            {
                "name": "pOutBuf",
                "type": "LPSTR",
                "resolved_type": "LPSTR",
                "direction": "out",
                "json_type": "string",
            },
            {
                "name": "dwBufLen",
                "type": "DWORD",
                "direction": "in",
                "json_type": "integer",
            },
        ],
    }

    normalized_args, normalized_selection = _normalize_true_output_scalar_args(
        inv,
        {"lpszHandle": "WFH-CUST-001-02", "pOutBuf": "CUST-001", "dwBufLen": 256},
        {},
    )

    assert normalized_args["pOutBuf"] == ""
    assert normalized_selection["pOutBuf"]["source"] == "output.bridge_slot"


def test_normalize_true_output_scalar_args_repairs_missing_buffer_size_for_output_buffer_call() -> None:
    inv = {
        "name": "WF_GetReservationEcho",
        "parameters": [
            {"name": "lpszHandle", "type": "LPCSTR", "resolved_type": "LPCSTR", "direction": "in", "json_type": "string"},
            {"name": "pOutBuf", "type": "LPSTR", "resolved_type": "LPSTR", "direction": "out", "json_type": "string"},
            {"name": "dwBufLen", "type": "DWORD", "resolved_type": "DWORD", "direction": "in", "json_type": "integer", "description": "Reservation echo output buffer size"},
        ],
    }

    normalized_args, normalized_selection = _normalize_true_output_scalar_args(
        inv,
        {"lpszHandle": "WFH-CUST-001-02", "pOutBuf": "", "dwBufLen": ""},
        {},
    )

    assert normalized_args["dwBufLen"] == 64
    assert normalized_selection["dwBufLen"]["source"] == "output.buffer_size_default"


def test_explore_one_repairs_string_struct_arg_before_target_execution(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []
    saved_findings: list[tuple[str, dict]] = []

    class _ToolCall:
        def __init__(self, name: str, arguments: str, tc_id: str = "tc-1") -> None:
            self.id = tc_id
            self.function = SimpleNamespace(name=name, arguments=arguments)

    class _Message:
        def __init__(self, tool_calls: list[_ToolCall]) -> None:
            self.content = ""
            self.tool_calls = tool_calls

    class _Choice:
        def __init__(self, message: _Message) -> None:
            self.message = message

    class _Response:
        def __init__(self, message: _Message) -> None:
            self.choices = [_Choice(message)]

    class _FakeCompletions:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return _Response(
                    _Message([
                        _ToolCall("TP_OpenSession", '{"pReq":"ACC-USB-C","pdwHandleOut":0}')
                    ])
                )
            return _Response(_Message([]))

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=_FakeCompletions())
    )

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], args))
        if inv["name"] == "TP_Initialize":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        if inv["name"] == "TP_BindCustomer":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 4294961294", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_explore_probe_log", lambda job_id, entries: probe_log_batches.append(entries))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda job_id, fn, payload: saved_findings.append((fn, payload)))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])

    runtime = ExploreRuntime(
        max_rounds=1,
        max_tool_calls=4,
        min_direct_probes=1,
        deterministic_fallback_enabled=False,
    )
    ctx = ExploreContext(
        job_id="job-struct-repair",
        runtime=runtime,
        client=fake_client,
        model="test-model",
        invocables=[_TRANSPORT_OPEN_INV, {"name": "TP_Initialize", "parameters": []}, {"name": "TP_BindCustomer", "parameters": [{"name": "lpszCustId", "json_type": "string"}]}],
        inv_map={
            "TP_OpenSession": _TRANSPORT_OPEN_INV,
            "TP_Initialize": {"name": "TP_Initialize", "parameters": []},
            "TP_BindCustomer": {"name": "TP_BindCustomer", "parameters": [{"name": "lpszCustId", "json_type": "string"}]},
        },
        tool_schemas=[],
        total=1,
        sentinels={4294961294: "transport failure"},
        ghidra_data_types=[],
    )

    _explore_one(_TRANSPORT_OPEN_INV, ctx)

    target_calls = [args for name, args in captured_calls if name == "TP_OpenSession"]
    assert target_calls
    assert target_calls[0]["pReq"] == {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2}
    assert target_calls[-1]["pReq"] == {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2}
    assert target_calls[-1]["pdwHandleOut"] == ""


def test_explore_one_runs_reserved_lineage_preflight_for_fresh_workflow_consumer(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []
    ecr = EvidenceCandidateRegistry()
    ecr.add(1073745928, 4, "cross_dll:TP_OpenSession", "handle", 1.0, "TP_OpenSession")
    ecr.add("CFG-CUST-001-09", 4, "cross_dll:runtime:CFG_GetConfigState", "ticket", 1.0, "CFG_GetConfigState")

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "WF_CreateReservation":
            return {"result_str": "Returned: 0\nRESV-69CD5E9F-0009", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_OpenFulfillment":
            return {"result_str": "Returned: 0\nWFH-CUST-001-02", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_GetWorkflowNonce":
            return {"result_str": "Returned: 0\npdwNonceOut=2511030275", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_CommitShipment":
            return {"result_str": "Returned: -2004\npdwAuthCode=0", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.infra.storage._load_findings",
        lambda job_id: [
            {
                "function": "WF_OpenFulfillment",
                "source": "cross_dll_prior",
                "status": "verified_success",
                "status_canonical": "verified_success",
                "working_call": {"lpszResvId": "RESV-STALE-0001", "pOutHandle": "CFG-CUST-001-09"},
            }
        ],
    )

    bind_inv = {
        "name": "WF_BindCustomer",
        "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}],
    }
    create_inv = {
        "name": "WF_CreateReservation",
        "parameters": [
            {"name": "lpszSku", "json_type": "string", "description": "SKU"},
            {"name": "wQty", "json_type": "integer", "description": "Quantity"},
            {"name": "dwHoldMinutes", "json_type": "integer", "description": "Hold minutes"},
            {"name": "pOutResvId", "json_type": "string", "direction": "out", "description": "Reservation output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
    }
    open_inv = {
        "name": "WF_OpenFulfillment",
        "parameters": [
            {"name": "lpszResvId", "json_type": "string", "description": "Reservation identifier"},
            {"name": "pOutHandle", "json_type": "string", "direction": "out", "description": "Workflow handle output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
    }
    nonce_inv = {
        "name": "WF_GetWorkflowNonce",
        "parameters": [
            {"name": "lpszHandle", "json_type": "string", "description": "Workflow handle"},
            {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Workflow nonce output"},
        ],
    }
    confirm_inv = {
        "name": "WF_ConfirmWorkflow",
        "parameters": [
            {"name": "lpszHandle", "json_type": "string", "description": "Workflow handle"},
            {"name": "dwNonce", "json_type": "integer", "description": "Workflow nonce"},
        ],
    }
    commit_inv = {
        "name": "WF_CommitShipment",
        "_required_preconditions": [
            "WF_BindCustomer",
            "WF_CreateReservation",
            "WF_OpenFulfillment",
            "WF_GetWorkflowNonce",
            "WF_ConfirmWorkflow",
        ],
        "parameters": [
            {"name": "lpszHandle", "json_type": "string", "description": "Workflow handle"},
            {"name": "pdwAuthCode", "json_type": "integer", "direction": "out", "description": "Auth code output"},
        ],
    }

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=8, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-workflow-lineage-preflight",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda *a, **k: None))),
        model="test-model",
        invocables=[commit_inv, bind_inv, create_inv, open_inv, nonce_inv, confirm_inv],
        inv_map={
            "WF_CommitShipment": commit_inv,
            "WF_BindCustomer": bind_inv,
            "WF_CreateReservation": create_inv,
            "WF_OpenFulfillment": open_inv,
            "WF_GetWorkflowNonce": nonce_inv,
            "WF_ConfirmWorkflow": confirm_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294965292: "bad handle"},
        ghidra_data_types=[],
        evidence_candidates=ecr,
    )

    _explore_one(commit_inv, ctx)

    commit_calls = [args for name, args in captured_calls if name == "WF_CommitShipment"]
    nonce_calls = [args for name, args in captured_calls if name == "WF_GetWorkflowNonce"]
    confirm_calls = [args for name, args in captured_calls if name == "WF_ConfirmWorkflow"]
    assert nonce_calls
    assert nonce_calls[0]["lpszHandle"] == "WFH-CUST-001-02"
    assert nonce_calls[0]["pdwNonceOut"] == ""
    assert confirm_calls
    assert confirm_calls[0]["lpszHandle"] == "WFH-CUST-001-02"
    assert confirm_calls[0]["dwNonce"] == 2511030275
    assert commit_calls
    assert commit_calls[0]["lpszHandle"] == "WFH-CUST-001-02"
    assert commit_calls[0]["pdwAuthCode"] == ""
    prereq_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") == "structured_preflight_prereq"
        and entry.get("function") == "WF_GetWorkflowNonce"
    ]
    create_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") == "structured_preflight_prereq"
        and entry.get("function") == "WF_CreateReservation"
    ]
    open_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") == "structured_preflight_prereq"
        and entry.get("function") == "WF_OpenFulfillment"
    ]
    assert create_logs
    assert open_logs
    assert prereq_logs
    create_observers = create_logs[0]["lineage_admission"]["observer_results"]
    assert any(
        row["observer_id"] == "emit:reservation_id" and row["status"] == "pass"
        for row in create_observers
    )
    open_observers = open_logs[0]["lineage_admission"]["observer_results"]
    assert any(
        row["observer_id"] == "handoff:reservation_id" and row["status"] == "pass"
        for row in open_observers
    )
    assert prereq_logs[0]["lineage_admission"]["fresh_replay_required"] is True
    assert prereq_logs[0]["lineage_admission"]["param_trace"]["lpszHandle"]["expected_family"] == "workflow_handle"
    nonce_observers = prereq_logs[0]["lineage_admission"]["observer_results"]
    assert any(
        row["observer_id"] == "handoff:workflow_handle" and row["status"] == "pass"
        for row in nonce_observers
    )


def test_explore_one_preserves_numeric_reservation_prereq_args_under_static_sku_pressure(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "WF_CreateReservation":
            return {"result_str": "Returned: 0\nRESV-69CD5E9F-0009", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_OpenFulfillment":
            return {"result_str": "Returned: 0\nWFH-CUST-001-02", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])

    bind_inv = {
        "name": "WF_BindCustomer",
        "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}],
    }
    create_inv = {
        "name": "WF_CreateReservation",
        "doc_comment": 'Required preconditions: WF_BindCustomer | Canonical args: {"dwHoldMinutes": 30, "lpszSku": "ACC-USB-C", "wQty": 2}',
        "parameters": [
            {"name": "lpszSku", "json_type": "string", "description": "SKU of the product being reserved, such as 'GDG-SM-RED'."},
            {"name": "wQty", "json_type": "integer", "resolved_type": "WORD", "description": "Quantity of the product to reserve, e.g., 1."},
            {"name": "dwHoldMinutes", "json_type": "integer", "resolved_type": "DWORD", "description": "Duration in minutes for which the reservation is held, e.g., 30."},
            {"name": "pOutResvId", "json_type": "string", "direction": "out", "description": "Reservation output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
    }
    open_inv = {
        "name": "WF_OpenFulfillment",
        "_required_preconditions": ["WF_BindCustomer", "WF_CreateReservation"],
        "parameters": [
            {"name": "lpszResvId", "json_type": "string", "description": "Reservation identifier"},
            {"name": "pOutHandle", "json_type": "string", "direction": "out", "description": "Workflow handle output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
    }

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=6, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-workflow-prereq-numeric-guard",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda *a, **k: None))),
        model="test-model",
        invocables=[open_inv, bind_inv, create_inv],
        inv_map={
            "WF_OpenFulfillment": open_inv,
            "WF_BindCustomer": bind_inv,
            "WF_CreateReservation": create_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294965292: "bad handle"},
        ghidra_data_types=[],
    )
    ctx.vocab["binary_string_ids"] = ["GDG-SM-RED", "CUST-004"]

    _explore_one(open_inv, ctx)

    prereq_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") == "structured_preflight_prereq"
        and entry.get("function") == "WF_CreateReservation"
        and entry.get("tool") == "WF_CreateReservation"
    ]
    assert prereq_logs
    latest = prereq_logs[-1]
    assert isinstance(latest["args"]["lpszSku"], str)
    assert latest["args"]["lpszSku"] in {"GDG-SM-RED", "ACC-USB-C"}
    assert latest["args"]["wQty"] == 2
    assert latest["args"]["dwHoldMinutes"] == 30


def test_explore_one_rehydrates_same_run_workflow_chain_before_fresh_replay(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "WF_CreateReservation":
            return {"result_str": "Returned: 0\nRESV-69CD5E9F-0009", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_OpenFulfillment":
            return {"result_str": "Returned: 0\nWFH-CUST-001-02", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_GetWorkflowNonce":
            return {"result_str": "Returned: 0\npdwNonceOut=2511030275", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_ConfirmWorkflow":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_GetWorkflowState":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])

    bind_inv = {
        "name": "WF_BindCustomer",
        "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}],
    }
    create_inv = {
        "name": "WF_CreateReservation",
        "parameters": [
            {"name": "lpszSku", "json_type": "string", "description": "SKU"},
            {"name": "wQty", "json_type": "integer", "description": "Quantity"},
            {"name": "dwHoldMinutes", "json_type": "integer", "description": "Hold minutes"},
            {"name": "pOutResvId", "json_type": "string", "direction": "out", "description": "Reservation output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
    }
    open_inv = {
        "name": "WF_OpenFulfillment",
        "parameters": [
            {"name": "lpszResvId", "json_type": "string", "description": "Reservation identifier"},
            {"name": "pOutHandle", "json_type": "string", "direction": "out", "description": "Workflow handle output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
    }
    nonce_inv = {
        "name": "WF_GetWorkflowNonce",
        "parameters": [
            {"name": "lpszHandle", "json_type": "string", "description": "Workflow handle"},
            {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Workflow nonce output"},
        ],
    }
    confirm_inv = {
        "name": "WF_ConfirmWorkflow",
        "parameters": [
            {"name": "lpszHandle", "json_type": "string", "description": "Workflow handle"},
            {"name": "dwNonce", "json_type": "integer", "description": "Workflow nonce"},
        ],
    }
    state_inv = {
        "name": "WF_GetWorkflowState",
        "_required_preconditions": [
            "WF_BindCustomer",
            "WF_CreateReservation",
            "WF_OpenFulfillment",
            "WF_GetWorkflowNonce",
            "WF_ConfirmWorkflow",
        ],
        "parameters": [
            {"name": "lpszHandle", "json_type": "string", "description": "Workflow handle"},
            {"name": "pdwStateOut", "json_type": "integer", "direction": "out", "description": "State output"},
        ],
    }

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=10, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-workflow-state-rehydrate",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda *a, **k: None))),
        model="test-model",
        invocables=[state_inv, bind_inv, create_inv, open_inv, nonce_inv, confirm_inv],
        inv_map={
            "WF_GetWorkflowState": state_inv,
            "WF_BindCustomer": bind_inv,
            "WF_CreateReservation": create_inv,
            "WF_OpenFulfillment": open_inv,
            "WF_GetWorkflowNonce": nonce_inv,
            "WF_ConfirmWorkflow": confirm_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294965292: "bad handle"},
        ghidra_data_types=[],
    )
    ctx.live_findings.extend([
        {
            "function": "WF_CreateReservation",
            "status": "verified_success",
            "working_call": {
                "lpszSku": "ACC-USB-C",
                "wQty": 2,
                "dwHoldMinutes": 30,
                "pOutResvId": "RESV-69CD5E9F-0009",
                "dwBufLen": 64,
            },
        },
        {
            "function": "WF_OpenFulfillment",
            "status": "verified_success",
            "working_call": {
                "lpszResvId": "RESV-69CD5E9F-0009",
                "pOutHandle": "WFH-CUST-001-02",
                "dwBufLen": 64,
            },
        },
        {
            "function": "WF_GetWorkflowNonce",
            "status": "verified_success",
            "working_call": {
                "lpszHandle": "WFH-CUST-001-02",
                "pdwNonceOut": 2511030275,
            },
        },
        {
            "function": "WF_ConfirmWorkflow",
            "status": "verified_success",
            "working_call": {
                "lpszHandle": "WFH-CUST-001-02",
                "dwNonce": 2511030275,
            },
        },
    ])

    _explore_one(state_inv, ctx)

    rehydrate_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if (entry.get("lineage_admission") or {}).get("replay_outcome") == "rehydrated_same_run_success"
    ]
    assert [entry["function"] for entry in rehydrate_logs[:4]] == [
        "WF_CreateReservation",
        "WF_OpenFulfillment",
        "WF_GetWorkflowNonce",
        "WF_ConfirmWorkflow",
    ]


def test_explore_one_preserves_live_promoted_workflow_handle_over_empty_output_field(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "WF_CreateReservation":
            return {"result_str": "Returned: 0\nRESV-69CD5E9F-0009", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_OpenFulfillment":
            return {"result_str": "Returned: 0\nWFH-CUST-001-02", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_GetWorkflowNonce":
            return {"result_str": "Returned: 0\npdwNonceOut=2511030275", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])

    bind_inv = {
        "name": "WF_BindCustomer",
        "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}],
    }
    create_inv = {
        "name": "WF_CreateReservation",
        "parameters": [
            {"name": "lpszSku", "json_type": "string", "description": "SKU"},
            {"name": "wQty", "json_type": "integer", "description": "Quantity"},
            {"name": "dwHoldMinutes", "json_type": "integer", "description": "Hold minutes"},
            {"name": "pOutResvId", "json_type": "string", "direction": "out", "description": "Reservation output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
        "doc_comment": 'Required preconditions: WF_BindCustomer | Canonical args: {"dwHoldMinutes": 30, "lpszSku": "ACC-USB-C", "wQty": 2}',
    }
    open_inv = {
        "name": "WF_OpenFulfillment",
        "parameters": [
            {"name": "lpszResvId", "json_type": "string", "description": "Reservation identifier"},
            {"name": "pOutHandle", "json_type": "string", "direction": "out", "description": "Workflow handle output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
        "doc_comment": 'Required preconditions: WF_CreateReservation | Canonical args: {"lpszResvId":"reservation-from-create"}',
    }
    nonce_inv = {
        "name": "WF_GetWorkflowNonce",
        "_required_preconditions": ["WF_BindCustomer", "WF_CreateReservation", "WF_OpenFulfillment"],
        "parameters": [
            {"name": "lpszHandle", "json_type": "string", "description": "Workflow handle returned by WF_OpenFulfillment"},
            {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Workflow nonce output"},
        ],
        "doc_comment": 'Required preconditions: WF_OpenFulfillment | Canonical args: {"lpszHandle":"handle-from-open"}',
    }

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=8, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-workflow-live-handle-promotion",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda *a, **k: None))),
        model="test-model",
        invocables=[nonce_inv, bind_inv, create_inv, open_inv],
        inv_map={
            "WF_GetWorkflowNonce": nonce_inv,
            "WF_BindCustomer": bind_inv,
            "WF_CreateReservation": create_inv,
            "WF_OpenFulfillment": open_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294965292: "bad handle"},
        ghidra_data_types=[],
    )

    _explore_one(nonce_inv, ctx)

    nonce_calls = [args for name, args in captured_calls if name == "WF_GetWorkflowNonce"]
    assert nonce_calls
    assert nonce_calls[0]["lpszHandle"] == "WFH-CUST-001-02"
    open_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") == "structured_preflight_prereq"
        and entry.get("function") == "WF_OpenFulfillment"
        and (entry.get("lineage_admission") or {}).get("replay_outcome") == "executed"
    ]
    assert open_logs
    emitted = (open_logs[-1].get("lineage_admission") or {}).get("observer_results") or []
    workflow_emit = next(result for result in emitted if result.get("observer_id") == "emit:workflow_handle")
    assert workflow_emit["status"] == "pass"

    nonce_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") in {"structured_preflight", "lineage_preflight", "deterministic_fallback"}
        and entry.get("function") == "WF_GetWorkflowNonce"
    ]
    assert nonce_logs
    handoff = next(
        result
        for result in (nonce_logs[-1].get("observer_results") or [])
        if result.get("observer_id") == "handoff:workflow_handle"
    )
    assert handoff["status"] == "pass"


def test_explore_one_does_not_rehydrate_state_drift_prereq_success(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "WF_BindCustomer":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_CreateReservation":
            return {"result_str": "Returned: 0\nRESV-69CD5E9F-0009", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_OpenFulfillment":
            return {"result_str": "Returned: 0\nWFH-CUST-001-02", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    seeded_findings = [
        {
            "function": "WF_CreateReservation",
            "status": "success",
            "status_canonical": "verified_success",
            "verification": "state_drift",
            "working_call": {
                "lpszSku": "GDG-SM-RED",
                "wQty": 1,
                "dwHoldMinutes": 30,
                "dwBufLen": 64,
                "pOutResvId": "",
            },
        }
    ]

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: seeded_findings)

    bind_inv = {
        "name": "WF_BindCustomer",
        "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}],
    }
    create_inv = {
        "name": "WF_CreateReservation",
        "parameters": [
            {"name": "lpszSku", "json_type": "string", "description": "SKU such as ACC-USB-C"},
            {"name": "wQty", "json_type": "integer", "description": "Item quantity"},
            {"name": "dwHoldMinutes", "json_type": "integer", "description": "Hold duration in minutes"},
            {"name": "pOutResvId", "json_type": "string", "direction": "out", "description": "Reservation output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Reservation output buffer size"},
        ],
        "doc_comment": 'Required preconditions: WF_BindCustomer | Canonical args: {"dwHoldMinutes": 30, "lpszSku": "ACC-USB-C", "wQty": 2}',
    }
    open_inv = {
        "name": "WF_OpenFulfillment",
        "_required_preconditions": ["WF_BindCustomer", "WF_CreateReservation"],
        "parameters": [
            {"name": "lpszResvId", "json_type": "string", "description": "Reservation identifier returned by WF_CreateReservation"},
            {"name": "pOutHandle", "json_type": "string", "direction": "out", "description": "Workflow handle output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
        "doc_comment": 'Required preconditions: WF_CreateReservation | Canonical args: {"lpszResvId":"reservation-from-create"}',
    }

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=8, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-workflow-ignore-state-drift-rehydrate",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda *a, **k: None))),
        model="test-model",
        invocables=[open_inv, bind_inv, create_inv],
        inv_map={
            "WF_OpenFulfillment": open_inv,
            "WF_BindCustomer": bind_inv,
            "WF_CreateReservation": create_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294965292: "bad handle"},
        ghidra_data_types=[],
    )

    _explore_one(open_inv, ctx)

    rehydrate_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if (entry.get("lineage_admission") or {}).get("replay_outcome") == "rehydrated_same_run_success"
        and entry.get("function") == "WF_CreateReservation"
    ]
    assert not rehydrate_logs

    create_calls = [args for name, args in captured_calls if name == "WF_CreateReservation"]
    assert create_calls
    assert create_calls[0]["wQty"] == 2


def test_explore_one_blocks_placeholder_workflow_handle_replay_until_live_handle_exists(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "WF_CreateReservation":
            return {"result_str": "Returned: 0\nRESV-69CD5E9F-0009", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_OpenFulfillment":
            return {"result_str": "Returned: 4294965292\npOutHandle=0", "trace": {"backend": "bridge"}}
        if inv["name"] == "WF_CommitShipment":
            return {"result_str": "Returned: -2004\npdwAuthCode=0", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])

    bind_inv = {
        "name": "WF_BindCustomer",
        "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}],
    }
    create_inv = {
        "name": "WF_CreateReservation",
        "parameters": [
            {"name": "lpszSku", "json_type": "string", "description": "SKU"},
            {"name": "wQty", "json_type": "integer", "description": "Quantity"},
            {"name": "dwHoldMinutes", "json_type": "integer", "description": "Hold minutes"},
            {"name": "pOutResvId", "json_type": "string", "direction": "out", "description": "Reservation output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
    }
    open_inv = {
        "name": "WF_OpenFulfillment",
        "parameters": [
            {"name": "lpszResvId", "json_type": "string", "description": "Reservation identifier"},
            {"name": "pOutHandle", "json_type": "string", "direction": "out", "description": "Workflow handle output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
    }
    nonce_inv = {
        "name": "WF_GetWorkflowNonce",
        "parameters": [
            {"name": "lpszHandle", "json_type": "string", "description": "Workflow handle"},
            {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Workflow nonce output"},
        ],
        "doc_comment": 'Canonical args: {"lpszHandle":"handle-from-open"}',
    }
    commit_inv = {
        "name": "WF_CommitShipment",
        "_required_preconditions": [
            "WF_BindCustomer",
            "WF_CreateReservation",
            "WF_OpenFulfillment",
            "WF_GetWorkflowNonce",
        ],
        "parameters": [
            {"name": "lpszHandle", "json_type": "string", "description": "Workflow handle"},
            {"name": "pdwAuthCode", "json_type": "integer", "direction": "out", "description": "Auth code output"},
        ],
    }

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=8, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-workflow-placeholder-block",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda *a, **k: None))),
        model="test-model",
        invocables=[commit_inv, bind_inv, create_inv, open_inv, nonce_inv],
        inv_map={
            "WF_CommitShipment": commit_inv,
            "WF_BindCustomer": bind_inv,
            "WF_CreateReservation": create_inv,
            "WF_OpenFulfillment": open_inv,
            "WF_GetWorkflowNonce": nonce_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294965292: "bad handle"},
        ghidra_data_types=[],
    )

    _explore_one(commit_inv, ctx)

    nonce_calls = [args for name, args in captured_calls if name == "WF_GetWorkflowNonce"]
    assert not nonce_calls
    blocked_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") == "structured_preflight_prereq"
        and entry.get("function") == "WF_GetWorkflowNonce"
        and (entry.get("lineage_admission") or {}).get("replay_outcome") == "placeholder_blocked"
    ]
    assert blocked_logs
    assert blocked_logs[0]["lineage_admission"]["forced_live_replay"] is True
    assert "lpszHandle" in blocked_logs[0]["lineage_admission"]["placeholder_params"]


def test_structured_preflight_refreshes_struct_fields_from_prerequisite_evidence(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], args))
        if inv["name"] == "TP_GetSessionNonce":
            return {
                "result_str": "Returned: 0\npdwNonceOut=16818177",
                "trace": {"backend": "bridge"},
            }
        if inv["name"] == "TP_SubmitPacket":
            return {
                "result_str": "Returned: 4294961291\npdwAuthCodeOut=0",
                "trace": {"backend": "bridge"},
            }
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_explore_probe_log", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.infra.storage._load_findings",
        lambda job_id: [
            {
                "function": "TP_OpenSession",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {
                    "pReq": {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2},
                    "pdwHandleOut": 1073745921,
                },
            }
        ],
    )

    runtime = ExploreRuntime(
        max_rounds=0,
        max_tool_calls=4,
        min_direct_probes=1,
        deterministic_fallback_enabled=False,
    )
    ecr = EvidenceCandidateRegistry()
    ecr.add(1073745921, 2, "runtime:TP_OpenSession", "handle", 1.0, "TP_OpenSession")

    ctx = ExploreContext(
        job_id="job-struct-refresh",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda *a, **k: None))),
        model="test-model",
        invocables=[
            _TRANSPORT_PACKET_INV,
            {
                "name": "TP_GetSessionNonce",
                "parameters": [
                    {"name": "dwSessionHandle", "type": "DWORD", "resolved_type": "DWORD", "direction": "in", "json_type": "integer"},
                    {"name": "pdwNonceOut", "type": "DWORD*", "resolved_type": "DWORD*", "direction": "out", "json_type": "integer"},
                ],
            },
        ],
        inv_map={
            "TP_SubmitPacket": _TRANSPORT_PACKET_INV,
            "TP_GetSessionNonce": {
                "name": "TP_GetSessionNonce",
                "parameters": [
                    {"name": "dwSessionHandle", "type": "DWORD", "resolved_type": "DWORD", "direction": "in", "json_type": "integer"},
                    {"name": "pdwNonceOut", "type": "DWORD*", "resolved_type": "DWORD*", "direction": "out", "json_type": "integer"},
                ],
            },
        },
        tool_schemas=[],
        total=1,
        sentinels={4294961291: "transport failure"},
        ghidra_data_types=[],
        evidence_candidates=ecr,
    )

    _explore_one(_TRANSPORT_PACKET_INV, ctx)

    submit_calls = [args for name, args in captured_calls if name == "TP_SubmitPacket"]
    assert submit_calls
    assert submit_calls[0]["pReq"]["dwSessionHandle"] == 1073745921
    assert submit_calls[0]["pReq"]["dwNonce"] == 16818177
    assert submit_calls[0]["pdwAuthCodeOut"] == ""


def test_free_blob_token_replay_ignores_seeded_prior_success_chain(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []

    free_blob_inv = {
        "name": "TP_FreeBlobToken",
        "parameters": [
            {"name": "dwBlobToken", "type": "DWORD", "resolved_type": "DWORD", "direction": "in", "json_type": "integer", "description": "Opaque blob token to release"}
        ],
        "doc_comment": "Required preconditions: TP_AllocBlobToken",
    }
    alloc_inv = {
        "name": "TP_AllocBlobToken",
        "parameters": [
            {"name": "dwSessionHandle", "type": "DWORD", "resolved_type": "DWORD", "direction": "in", "json_type": "integer", "description": "Opaque session handle"},
            {"name": "pdwBlobTokenOut", "type": "DWORD*", "resolved_type": "DWORD*", "direction": "out", "json_type": "integer", "description": "Output opaque blob token"},
        ],
        "doc_comment": "Required preconditions: TP_OpenSession | Canonical args: {\"dwSessionHandle\": \"handle-from-open\"}",
    }
    open_inv = dict(_TRANSPORT_OPEN_INV)
    bind_inv = {
        "name": "TP_BindCustomer",
        "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}],
    }
    init_inv = {"name": "TP_Initialize", "parameters": []}

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "TP_Initialize":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        if inv["name"] == "TP_BindCustomer":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        if inv["name"] == "TP_OpenSession":
            return {"result_str": "Returned: 0\npdwHandleOut=1073745926", "trace": {"backend": "bridge"}}
        if inv["name"] == "TP_AllocBlobToken":
            assert args["dwSessionHandle"] == 1073745926
            return {"result_str": "Returned: 0\npdwBlobTokenOut=1879048198", "trace": {"backend": "bridge"}}
        if inv["name"] == "TP_FreeBlobToken":
            assert args["dwBlobToken"] == 1879048198
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 4294961292", "trace": {"backend": "bridge"}}

    class _EmptyCompletions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_explore_probe_log", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.infra.storage._load_findings",
        lambda job_id: [
            {
                "function": "TP_OpenSession",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {
                    "pReq": {"szCustId": "CUST-001", "dwFlags": 1, "dwMode": 2},
                    "pdwHandleOut": 1073745925,
                },
            },
            {
                "function": "TP_AllocBlobToken",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"dwSessionHandle": 1073745925, "pdwBlobTokenOut": 1879048198},
            },
        ],
    )

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=8, min_direct_probes=1, deterministic_fallback_enabled=False)
    ecr = EvidenceCandidateRegistry()
    ctx = ExploreContext(
        job_id="job-free-blob-fresh",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_EmptyCompletions())),
        model="test-model",
        invocables=[free_blob_inv, alloc_inv, open_inv, bind_inv, init_inv],
        inv_map={
            "TP_FreeBlobToken": free_blob_inv,
            "TP_AllocBlobToken": alloc_inv,
            "TP_OpenSession": open_inv,
            "TP_BindCustomer": bind_inv,
            "TP_Initialize": init_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294961292: "transport failure", 4294961294: "transport failure"},
        ghidra_data_types=[],
        evidence_candidates=ecr,
    )

    _explore_one(free_blob_inv, ctx)

    alloc_calls = [args for name, args in captured_calls if name == "TP_AllocBlobToken"]
    open_calls = [args for name, args in captured_calls if name == "TP_OpenSession"]
    free_calls = [args for name, args in captured_calls if name == "TP_FreeBlobToken"]
    assert open_calls
    assert open_calls[0]["pReq"]["szCustId"]
    assert alloc_calls
    assert alloc_calls[0]["dwSessionHandle"] == 1073745926
    assert free_calls
    assert free_calls[0]["dwBlobToken"] == 1879048198


def test_blob_token_replay_blocks_placeholder_handle_until_live_session_exists(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []

    free_blob_inv = {
        "name": "TP_FreeBlobToken",
        "parameters": [
            {"name": "dwBlobToken", "type": "DWORD", "resolved_type": "DWORD", "direction": "in", "json_type": "integer", "description": "Opaque blob token to release"}
        ],
        "doc_comment": "Required preconditions: TP_AllocBlobToken",
    }
    alloc_inv = {
        "name": "TP_AllocBlobToken",
        "parameters": [
            {"name": "dwSessionHandle", "type": "DWORD", "resolved_type": "DWORD", "direction": "in", "json_type": "integer", "description": "Opaque session handle"},
            {"name": "pdwBlobTokenOut", "type": "DWORD*", "resolved_type": "DWORD*", "direction": "out", "json_type": "integer", "description": "Output opaque blob token"},
        ],
        "doc_comment": 'Required preconditions: TP_OpenSession | Canonical args: {"dwSessionHandle": "handle-from-open"}',
    }
    open_inv = dict(_TRANSPORT_OPEN_INV)
    bind_inv = {
        "name": "TP_BindCustomer",
        "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}],
    }
    init_inv = {"name": "TP_Initialize", "parameters": []}

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "TP_Initialize":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        if inv["name"] == "TP_BindCustomer":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        if inv["name"] == "TP_OpenSession":
            return {"result_str": "Returned: 4294961292\npdwHandleOut=0", "trace": {"backend": "bridge"}}
        if inv["name"] == "TP_FreeBlobToken":
            return {"result_str": "Returned: 4294961292", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 4294961292", "trace": {"backend": "bridge"}}

    class _EmptyCompletions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])
    from api.pipeline.s02_probe import probe_loop as _probe_loop

    _original_collect_placeholder = _probe_loop._collect_placeholder_replay_params

    def _patched_collect_placeholder(inv, args):
        if inv.get("name") == "CFG_OpenLicensedWindow":
            return {}
        return _original_collect_placeholder(inv, args)

    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._collect_placeholder_replay_params",
        _patched_collect_placeholder,
    )

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=8, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-blob-placeholder-block",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_EmptyCompletions())),
        model="test-model",
        invocables=[free_blob_inv, alloc_inv, open_inv, bind_inv, init_inv],
        inv_map={
            "TP_FreeBlobToken": free_blob_inv,
            "TP_AllocBlobToken": alloc_inv,
            "TP_OpenSession": open_inv,
            "TP_BindCustomer": bind_inv,
            "TP_Initialize": init_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294961292: "transport failure", 4294961294: "transport failure"},
        ghidra_data_types=[],
    )

    _explore_one(free_blob_inv, ctx)

    alloc_calls = [args for name, args in captured_calls if name == "TP_AllocBlobToken"]
    assert not alloc_calls
    blocked_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") == "structured_preflight_prereq"
        and entry.get("function") == "TP_AllocBlobToken"
        and (entry.get("lineage_admission") or {}).get("replay_outcome") == "placeholder_blocked"
    ]
    assert blocked_logs
    assert blocked_logs[0]["lineage_admission"]["forced_live_replay"] is True
    assert "dwSessionHandle" in blocked_logs[0]["lineage_admission"]["placeholder_params"]


def test_prerequisite_replay_promotes_later_success_into_prereq_finding(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    stored_findings: list[dict] = []

    preview_inv = {
        "name": "RP_RenderPreview",
        "parameters": [
            {"name": "lpszReportId", "json_type": "string", "description": "Report identifier"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Preview buffer size"},
        ],
        "doc_comment": 'Canonical args: {"lpszReportId":"RPT-CUST-001-02","dwBufLen":64}',
    }
    export_inv = {
        "name": "RP_ExportLedger",
        "parameters": [
            {"name": "lpszReportId", "json_type": "string", "description": "Report identifier"},
            {"name": "dwNonce", "json_type": "integer", "description": "Report nonce"},
        ],
        "doc_comment": 'Required preconditions: RP_RenderPreview | Canonical args: {"lpszReportId":"RPT-CUST-001-02","dwNonce":3911728039}',
    }

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "RP_RenderPreview":
            return {
                "result_str": "Returned: 0\nreport=RPT-CUST-001-02|format=CSV|customer=CUST-001",
                "trace": {"backend": "bridge"},
            }
        if inv["name"] == "RP_ExportLedger":
            return {"result_str": "Returned: -4004", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    def _load(job_id):
        return list(stored_findings)

    def _save(job_id, payload):
        stored_findings.append(dict(payload))

    def _patch(job_id, fn_name, payload):
        for finding in reversed(stored_findings):
            if finding.get("function") == fn_name:
                finding.update(payload)
                return
        stored_findings.append({"function": fn_name, **payload})

    class _EmptyCompletions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_explore_probe_log", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", _patch)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", _save)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", _load)

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=4, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-prereq-promotion",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_EmptyCompletions())),
        model="test-model",
        invocables=[export_inv, preview_inv],
        inv_map={"RP_ExportLedger": export_inv, "RP_RenderPreview": preview_inv},
        tool_schemas=[],
        total=1,
        sentinels={4294963292: "reporting gate unmet", 4294963293: "reporting gate unmet"},
        ghidra_data_types=[],
    )

    _explore_one(export_inv, ctx)

    preview_finding = next((f for f in stored_findings if f.get("function") == "RP_RenderPreview"), None)
    assert preview_finding is not None
    assert preview_finding["status"] == "verified_success"
    assert preview_finding["working_call"]["dwBufLen"] == 64


def test_config_prereq_retries_after_live_ticket_promotion(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []
    promoted_ticket = "licensed|cust=CUST-001|approved=1"

    get_nonce_inv = {
        "name": "CFG_GetLicenseNonce",
        "parameters": [
            {"name": "lpszTicket", "json_type": "string", "description": "License ticket"},
            {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "License nonce output"},
        ],
        "doc_comment": 'Canonical args: {"lpszTicket":"ticket-from-open"}',
    }
    open_window_inv = {
        "name": "CFG_OpenLicensedWindow",
        "parameters": [
            {"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"},
            {"name": "pOutTicket", "json_type": "string", "direction": "out", "description": "License ticket output"},
        ],
        "doc_comment": 'Canonical args: {"lpszCustId":"CUST-001"}',
    }
    approve_inv = {
        "name": "CFG_ApproveLicensedCall",
        "_required_preconditions": ["CFG_GetLicenseNonce", "CFG_OpenLicensedWindow"],
        "parameters": [
            {"name": "lpszTicket", "json_type": "string", "description": "License ticket"},
            {"name": "dwNonce", "json_type": "integer", "description": "License nonce"},
        ],
    }

    class _EmptyCompletions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "CFG_OpenLicensedWindow":
            return {
                "result_str": f"Returned: 0\npOutTicket={promoted_ticket}",
                "trace": {"backend": "bridge"},
            }
        if inv["name"] == "CFG_GetLicenseNonce":
            assert args["lpszTicket"] == promoted_ticket
            return {
                "result_str": "Returned: 0\npdwNonceOut=1500755888",
                "trace": {"backend": "bridge"},
            }
        if inv["name"] == "CFG_ApproveLicensedCall":
            assert args["lpszTicket"] == promoted_ticket
            assert args["dwNonce"] == 1500755888
            return {"result_str": "Returned: -3004", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=6, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-config-live-promotion",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_EmptyCompletions())),
        model="test-model",
        invocables=[approve_inv, get_nonce_inv, open_window_inv],
        inv_map={
            "CFG_ApproveLicensedCall": approve_inv,
            "CFG_GetLicenseNonce": get_nonce_inv,
            "CFG_OpenLicensedWindow": open_window_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294964292: "config failure"},
        ghidra_data_types=[],
    )

    _explore_one(approve_inv, ctx)

    get_nonce_calls = [args for name, args in captured_calls if name == "CFG_GetLicenseNonce"]
    assert get_nonce_calls
    assert get_nonce_calls[-1]["lpszTicket"] == promoted_ticket
    open_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") == "structured_preflight_prereq"
        and entry.get("function") == "CFG_OpenLicensedWindow"
        and (entry.get("lineage_admission") or {}).get("replay_outcome") == "executed"
    ]
    assert open_logs
    assert open_logs[-1]["lineage_admission"]["live_value_promoted"] is True
    assert open_logs[-1]["lineage_admission"]["promoted_hints"]["ticket"] == promoted_ticket
    call_names = [name for name, _ in captured_calls]
    assert "CFG_OpenLicensedWindow" in call_names
    assert "CFG_GetLicenseNonce" in call_names
    assert "CFG_ApproveLicensedCall" in call_names
    assert call_names.index("CFG_OpenLicensedWindow") < call_names.index("CFG_GetLicenseNonce")
    assert call_names.index("CFG_GetLicenseNonce") < call_names.index("CFG_ApproveLicensedCall")
    config_observers = open_logs[-1]["lineage_admission"]["observer_results"]
    assert any(
        row["observer_id"] == "emit:ticket"
        and row["status"] == "pass"
        and row["likely_fault_scope"] == "none"
        for row in config_observers
    )


def test_config_nested_blocked_prereq_retry_does_not_double_delete(monkeypatch) -> None:
    blocked = {
        "CFG_GetLicenseNonce": 0,
        "CFG_ApproveLicensedCall": 0,
    }

    assert _consume_retryable_blocked_prereq(
        blocked,
        "CFG_GetLicenseNonce",
        hint_generation=1,
    ) is True
    assert "CFG_GetLicenseNonce" not in blocked

    blocked.pop("CFG_ApproveLicensedCall", None)

    assert _consume_retryable_blocked_prereq(
        blocked,
        "CFG_ApproveLicensedCall",
        hint_generation=1,
    ) is False


def test_pricing_prereq_retries_after_live_quote_id_promotion(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []
    promoted_quote = "PRQ-CUST-001-01"

    get_nonce_inv = {
        "name": "PR_GetQuoteNonce",
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string", "description": "Quote identifier"},
            {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Quote nonce output"},
        ],
        "doc_comment": 'Canonical args: {"lpszQuoteId":"quote-from-begin"}',
    }
    begin_inv = {
        "name": "PR_BeginQuote",
        "parameters": [
            {"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"},
            {"name": "pOutQuoteId", "json_type": "string", "direction": "out", "description": "Quote identifier output"},
        ],
        "doc_comment": 'Canonical args: {"lpszCustId":"CUST-001"}',
    }
    approve_inv = {
        "name": "PR_ApproveRuleWindow",
        "_required_preconditions": ["PR_GetQuoteNonce", "PR_BeginQuote"],
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string", "description": "Quote identifier"},
            {"name": "dwNonce", "json_type": "integer", "description": "Quote nonce"},
        ],
    }

    class _EmptyCompletions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "PR_BeginQuote":
            return {
                "result_str": f"Returned: 0\npOutQuoteId={promoted_quote}",
                "trace": {"backend": "bridge"},
            }
        if inv["name"] == "PR_GetQuoteNonce":
            assert args["lpszQuoteId"] == promoted_quote
            return {
                "result_str": "Returned: 0\npdwNonceOut=1500755888",
                "trace": {"backend": "bridge"},
            }
        if inv["name"] == "PR_ApproveRuleWindow":
            assert args["lpszQuoteId"] == promoted_quote
            assert args["dwNonce"] == 1500755888
            return {"result_str": "Returned: -4004", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=6, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-pricing-live-promotion",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_EmptyCompletions())),
        model="test-model",
        invocables=[approve_inv, get_nonce_inv, begin_inv],
        inv_map={
            "PR_ApproveRuleWindow": approve_inv,
            "PR_GetQuoteNonce": get_nonce_inv,
            "PR_BeginQuote": begin_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294963292: "pricing failure"},
        ghidra_data_types=[],
        evidence_candidates=EvidenceCandidateRegistry(),
    )

    _explore_one(approve_inv, ctx)

    get_nonce_calls = [args for name, args in captured_calls if name == "PR_GetQuoteNonce"]
    assert get_nonce_calls
    assert get_nonce_calls[-1]["lpszQuoteId"] == promoted_quote
    begin_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") == "structured_preflight_prereq"
        and entry.get("function") == "PR_BeginQuote"
        and (entry.get("lineage_admission") or {}).get("replay_outcome") == "executed"
    ]
    assert begin_logs
    assert begin_logs[-1]["lineage_admission"]["live_value_promoted"] is True
    assert begin_logs[-1]["lineage_admission"]["promoted_hints"]["quote_id"] == promoted_quote
    assert begin_logs[-1]["lineage_admission"]["materialized_runtime_artifacts"]["quote_id"] == promoted_quote
    assert "PR_GetQuoteNonce" in begin_logs[-1]["lineage_admission"]["retry_resumed"]
    pricing_observers = begin_logs[-1]["lineage_admission"]["observer_results"]
    assert any(
        row["observer_id"] == "emit:quote_id"
        and row["status"] == "pass"
        and row["likely_fault_scope"] == "none"
        for row in pricing_observers
    )
    quote_candidates = ctx.evidence_candidates.query("quote_id", "string", max_results=1)
    nonce_candidates = ctx.evidence_candidates.query("nonce", "integer", max_results=1)
    assert quote_candidates[0].value == promoted_quote
    assert nonce_candidates[0].value == 1500755888


def test_cluster_seeded_pricing_rerun_preserves_target_call_budget(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []
    promoted_quote = "PRQ-CUST-001-01"
    promoted_nonce = 1500755888

    seal_inv = {
        "name": "PR_SealQuote",
        "_required_preconditions": ["PR_GetQuoteNonce", "PR_ApproveRuleWindow"],
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string", "description": "Quote identifier"},
            {"name": "dwNonce", "json_type": "integer", "description": "Quote nonce"},
        ],
        "doc_comment": 'Canonical args: {"lpszQuoteId":"quote-from-begin","dwNonce":"nonce-from-read"}',
    }
    get_nonce_inv = {
        "name": "PR_GetQuoteNonce",
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string", "description": "Quote identifier"},
            {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Quote nonce output"},
        ],
        "doc_comment": 'Canonical args: {"lpszQuoteId":"quote-from-begin"}',
    }
    approve_inv = {
        "name": "PR_ApproveRuleWindow",
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string", "description": "Quote identifier"},
            {"name": "dwNonce", "json_type": "integer", "description": "Quote nonce"},
        ],
    }

    class _EmptyCompletions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "PR_SealQuote":
            assert args["lpszQuoteId"] == promoted_quote
            assert args["dwNonce"] == promoted_nonce
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        raise AssertionError(f"unexpected replay for {inv['name']}")

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.infra.storage._load_findings",
        lambda job_id: [
            {
                "function": "PR_GetQuoteNonce",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszQuoteId": promoted_quote, "pdwNonceOut": promoted_nonce},
                "verification": "verified",
                "notes": "Seeded from checkpoint 26ddca42",
                "source": "checkpoint_resume",
            },
            {
                "function": "PR_ApproveRuleWindow",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszQuoteId": promoted_quote, "dwNonce": promoted_nonce},
                "verification": "verified",
                "notes": "Seeded from checkpoint 26ddca42",
                "source": "checkpoint_resume",
            },
        ],
    )

    runtime = ExploreRuntime(
        max_rounds=0,
        max_tool_calls=1,
        min_direct_probes=1,
        deterministic_fallback_enabled=False,
        cluster_checkpoint_id="pricing_quote_lifecycle",
    )
    ctx = ExploreContext(
        job_id="job-pricing-cluster-seed-budget",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_EmptyCompletions())),
        model="test-model",
        invocables=[seal_inv, get_nonce_inv, approve_inv],
        inv_map={
            "PR_SealQuote": seal_inv,
            "PR_GetQuoteNonce": get_nonce_inv,
            "PR_ApproveRuleWindow": approve_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294963292: "pricing failure"},
        ghidra_data_types=[],
        evidence_candidates=EvidenceCandidateRegistry(),
    )

    _explore_one(seal_inv, ctx)

    assert captured_calls == [("PR_SealQuote", {"lpszQuoteId": promoted_quote, "dwNonce": promoted_nonce})]
    trusted_seed_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") == "structured_preflight_prereq"
        and (entry.get("lineage_admission") or {}).get("replay_outcome") == "trusted_checkpoint_seed"
    ]
    assert {entry["function"] for entry in trusted_seed_logs} == {"PR_GetQuoteNonce", "PR_ApproveRuleWindow"}
    target_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("function") == "PR_SealQuote"
    ]
    assert target_logs


def test_cluster_seeded_pricing_rerun_replays_untrustworthy_begin_quote_seed(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []
    promoted_quote = "PRQ-CUST-001-01"

    get_nonce_inv = {
        "name": "PR_GetQuoteNonce",
        "_required_preconditions": ["PR_BeginQuote"],
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string", "description": "Quote identifier"},
            {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Quote nonce output"},
        ],
        "doc_comment": 'Canonical args: {"lpszQuoteId":"quote-from-begin"}',
    }
    begin_inv = {
        "name": "PR_BeginQuote",
        "parameters": [
            {"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"},
            {"name": "pOutQuoteId", "json_type": "string", "direction": "out", "description": "Quote identifier output"},
        ],
        "doc_comment": 'Canonical args: {"lpszCustId":"CUST-001"}',
    }

    class _EmptyCompletions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "PR_BeginQuote":
            return {
                "result_str": f"Returned: 0\npOutQuoteId={promoted_quote}",
                "trace": {"backend": "bridge"},
            }
        if inv["name"] == "PR_GetQuoteNonce":
            assert args["lpszQuoteId"] == promoted_quote
            return {
                "result_str": "Returned: 0\npdwNonceOut=1500755888",
                "trace": {"backend": "bridge"},
            }
        raise AssertionError(f"unexpected replay for {inv['name']}")

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.infra.storage._load_findings",
        lambda job_id: [
            {
                "function": "PR_BeginQuote",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszCustId": "CUST-001", "pOutQuoteId": ""},
                "verification": "verified",
                "notes": "Seeded from checkpoint 26ddca42",
                "source": "checkpoint_resume",
            },
        ],
    )

    runtime = ExploreRuntime(
        max_rounds=0,
        max_tool_calls=2,
        min_direct_probes=1,
        deterministic_fallback_enabled=False,
        cluster_checkpoint_id="pricing_quote_lifecycle",
    )
    ctx = ExploreContext(
        job_id="job-pricing-cluster-seed-untrustworthy-producer",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_EmptyCompletions())),
        model="test-model",
        invocables=[get_nonce_inv, begin_inv],
        inv_map={
            "PR_GetQuoteNonce": get_nonce_inv,
            "PR_BeginQuote": begin_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294963292: "pricing failure"},
        ghidra_data_types=[],
        evidence_candidates=EvidenceCandidateRegistry(),
    )

    _explore_one(get_nonce_inv, ctx)

    assert [name for name, _ in captured_calls] == ["PR_BeginQuote", "PR_GetQuoteNonce"]
    trusted_seed_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("function") == "PR_BeginQuote"
        and (entry.get("lineage_admission") or {}).get("replay_outcome") == "trusted_checkpoint_seed"
    ]
    assert not trusted_seed_logs
    executed_begin_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("function") == "PR_BeginQuote"
        and (entry.get("lineage_admission") or {}).get("replay_outcome") == "executed"
    ]
    assert executed_begin_logs


def test_same_run_pricing_rehydrate_normalizes_outputs_and_skips_duplicate_replay(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []
    promoted_quote = "PRQ-CUST-001-03"
    promoted_nonce = 1500757424

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "PR_BeginQuote":
            assert args["pOutQuoteId"] == ""
            return {"result_str": f"Returned: 0\n{promoted_quote}", "trace": {"backend": "bridge"}}
        if inv["name"] == "PR_GetQuoteNonce":
            assert args["lpszQuoteId"] == promoted_quote
            assert args["pdwNonceOut"] == ""
            return {"result_str": f"Returned: 0\npdwNonceOut={promoted_nonce}", "trace": {"backend": "bridge"}}
        if inv["name"] == "PR_ApproveRuleWindow":
            assert args["lpszQuoteId"] == promoted_quote
            assert args["dwNonce"] == promoted_nonce
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        if inv["name"] == "PR_SealQuote":
            assert args["lpszQuoteId"] == promoted_quote
            assert args["dwNonce"] == promoted_nonce
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        raise AssertionError(f"unexpected function {inv['name']}")

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])

    begin_inv = {
        "name": "PR_BeginQuote",
        "parameters": [
            {"name": "pOutQuoteId", "json_type": "string", "direction": "out", "description": "Quote identifier output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
    }
    get_nonce_inv = {
        "name": "PR_GetQuoteNonce",
        "_required_preconditions": ["PR_BeginQuote"],
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string", "description": "Quote identifier"},
            {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Quote nonce output"},
        ],
    }
    approve_inv = {
        "name": "PR_ApproveRuleWindow",
        "_required_preconditions": ["PR_GetQuoteNonce", "PR_Initialize"],
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string", "description": "Quote identifier"},
            {"name": "dwNonce", "json_type": "integer", "description": "Quote nonce"},
        ],
    }
    seal_inv = {
        "name": "PR_SealQuote",
        "_required_preconditions": ["PR_ApproveRuleWindow"],
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string", "description": "Quote identifier"},
            {"name": "dwNonce", "json_type": "integer", "description": "Quote nonce"},
        ],
    }

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=4, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-pricing-rehydrate-budget",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda *a, **k: None))),
        model="test-model",
        invocables=[seal_inv, begin_inv, get_nonce_inv, approve_inv],
        inv_map={
            "PR_SealQuote": seal_inv,
            "PR_BeginQuote": begin_inv,
            "PR_GetQuoteNonce": get_nonce_inv,
            "PR_ApproveRuleWindow": approve_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294963292: "pricing failure"},
        ghidra_data_types=[],
    )
    ctx.live_findings.extend([
        {
            "function": "PR_BeginQuote",
            "status": "verified_success",
            "working_call": {"pOutQuoteId": promoted_quote, "dwBufLen": 64},
        },
        {
            "function": "PR_GetQuoteNonce",
            "status": "verified_success",
            "working_call": {"lpszQuoteId": promoted_quote, "pdwNonceOut": promoted_nonce},
        },
        {
            "function": "PR_ApproveRuleWindow",
            "status": "verified_success",
            "working_call": {"lpszQuoteId": promoted_quote, "dwNonce": promoted_nonce},
        },
    ])

    _explore_one(seal_inv, ctx)

    assert [name for name, _ in captured_calls] == [
        "PR_BeginQuote",
        "PR_GetQuoteNonce",
        "PR_ApproveRuleWindow",
        "PR_SealQuote",
    ]
    rehydrate_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if (entry.get("lineage_admission") or {}).get("replay_outcome") == "rehydrated_same_run_success"
    ]
    assert [entry["function"] for entry in rehydrate_logs] == [
        "PR_BeginQuote",
        "PR_GetQuoteNonce",
        "PR_ApproveRuleWindow",
    ]
    assert rehydrate_logs[0]["args"]["pOutQuoteId"] == ""
    assert rehydrate_logs[1]["args"]["pdwNonceOut"] == ""


def test_pricing_init_prereq_executes_before_same_run_quote_rehydrate(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "PR_Initialize":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        if inv["name"] == "PR_BeginQuote":
            return {"result_str": "Returned: 0\nPRQ-CUST-001-03", "trace": {"backend": "bridge"}}
        if inv["name"] == "PR_GetQuoteNonce":
            return {"result_str": "Returned: 0\npdwNonceOut=1500757424", "trace": {"backend": "bridge"}}
        if inv["name"] == "PR_ApproveRuleWindow":
            assert args["lpszQuoteId"] == "PRQ-CUST-001-03"
            assert args["dwNonce"] == 1500757424
            return {"result_str": "Returned: -3004", "trace": {"backend": "bridge"}}
        raise AssertionError(f"unexpected function {inv['name']}")

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_explore_probe_log", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])

    init_inv = {"name": "PR_Initialize", "parameters": []}
    begin_inv = {
        "name": "PR_BeginQuote",
        "parameters": [
            {"name": "pOutQuoteId", "json_type": "string", "direction": "out", "description": "Quote identifier output"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Buffer size"},
        ],
    }
    get_nonce_inv = {
        "name": "PR_GetQuoteNonce",
        "_required_preconditions": ["PR_BeginQuote"],
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string", "description": "Quote identifier"},
            {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Quote nonce output"},
        ],
    }
    approve_inv = {
        "name": "PR_ApproveRuleWindow",
        "_required_preconditions": ["PR_GetQuoteNonce", "PR_Initialize"],
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string", "description": "Quote identifier"},
            {"name": "dwNonce", "json_type": "integer", "description": "Quote nonce"},
        ],
    }

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=6, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-pricing-init-before-rehydrate",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda *a, **k: None))),
        model="test-model",
        invocables=[approve_inv, init_inv, begin_inv, get_nonce_inv],
        inv_map={
            "PR_ApproveRuleWindow": approve_inv,
            "PR_Initialize": init_inv,
            "PR_BeginQuote": begin_inv,
            "PR_GetQuoteNonce": get_nonce_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294964292: "pricing failure"},
        ghidra_data_types=[],
        evidence_candidates=EvidenceCandidateRegistry(),
    )
    ctx.live_findings.extend([
        {
            "function": "PR_BeginQuote",
            "status": "verified_success",
            "working_call": {"pOutQuoteId": "PRQ-CUST-001-03", "dwBufLen": 64},
        },
        {
            "function": "PR_GetQuoteNonce",
            "status": "verified_success",
            "working_call": {"lpszQuoteId": "PRQ-CUST-001-03", "pdwNonceOut": 1500757424},
        },
    ])

    _explore_one(approve_inv, ctx)

    assert [name for name, _ in captured_calls[:4]] == [
        "PR_Initialize",
        "PR_BeginQuote",
        "PR_GetQuoteNonce",
        "PR_ApproveRuleWindow",
    ]


def test_structured_preflight_preserves_one_direct_target_call_after_prereq_cap(monkeypatch) -> None:
    captured_calls: list[str] = []

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append(inv["name"])
        if inv["name"] == "PR_GetQuoteState":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_explore_probe_log", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])

    init_inv = {"name": "PR_Initialize", "parameters": []}
    bind_inv = {"name": "PR_BindCustomer", "parameters": [{"name": "lpszCustId", "json_type": "string"}]}
    load_sku_inv = {
        "name": "PR_LoadSkuContext",
        "parameters": [
            {"name": "lpszSku", "json_type": "string"},
            {"name": "wQty", "json_type": "integer"},
        ],
    }
    begin_inv = {
        "name": "PR_BeginQuote",
        "parameters": [
            {"name": "pOutQuoteId", "json_type": "string", "direction": "out"},
            {"name": "dwBufLen", "json_type": "integer"},
        ],
    }
    get_nonce_inv = {
        "name": "PR_GetQuoteNonce",
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string"},
            {"name": "pdwNonceOut", "json_type": "integer", "direction": "out"},
        ],
    }
    approve_inv = {
        "name": "PR_ApproveRuleWindow",
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string"},
            {"name": "dwNonce", "json_type": "integer"},
        ],
    }
    target_inv = {
        "name": "PR_GetQuoteState",
        "_required_preconditions": [
            "PR_Initialize",
            "PR_BindCustomer",
            "PR_LoadSkuContext",
            "PR_BeginQuote",
            "PR_GetQuoteNonce",
            "PR_ApproveRuleWindow",
        ],
        "parameters": [
            {"name": "lpszQuoteId", "json_type": "string"},
            {"name": "dwNonce", "json_type": "integer"},
        ],
    }

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=6, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-pricing-direct-target-budget-floor",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda *a, **k: None))),
        model="test-model",
        invocables=[target_inv, init_inv, bind_inv, load_sku_inv, begin_inv, get_nonce_inv, approve_inv],
        inv_map={
            "PR_GetQuoteState": target_inv,
            "PR_Initialize": init_inv,
            "PR_BindCustomer": bind_inv,
            "PR_LoadSkuContext": load_sku_inv,
            "PR_BeginQuote": begin_inv,
            "PR_GetQuoteNonce": get_nonce_inv,
            "PR_ApproveRuleWindow": approve_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294964292: "pricing failure"},
        ghidra_data_types=[],
        evidence_candidates=EvidenceCandidateRegistry(),
    )

    _explore_one(target_inv, ctx)

    assert captured_calls[-1] == "PR_GetQuoteState"
    assert captured_calls[:7] == [
        "PR_Initialize",
        "PR_BindCustomer",
        "PR_LoadSkuContext",
        "PR_BeginQuote",
        "PR_GetQuoteNonce",
        "PR_ApproveRuleWindow",
        "PR_GetQuoteState",
    ]


def test_reporting_prereq_retries_after_live_report_id_promotion(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []
    promoted_report = "RPT-CUST-001-02"

    get_nonce_inv = {
        "name": "RP_GetReportNonce",
        "parameters": [
            {"name": "lpszReportId", "json_type": "string", "description": "Report identifier"},
            {"name": "pdwNonceOut", "json_type": "integer", "direction": "out", "description": "Report nonce output"},
        ],
        "doc_comment": 'Canonical args: {"lpszReportId":"report-from-prepare"}',
    }
    render_inv = {
        "name": "RP_RenderPreview",
        "parameters": [
            {"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"},
            {"name": "pOutReportId", "json_type": "string", "direction": "out", "description": "Report identifier output"},
        ],
        "doc_comment": 'Canonical args: {"lpszCustId":"CUST-001"}',
    }
    close_inv = {
        "name": "RP_CloseReport",
        "_required_preconditions": ["RP_GetReportNonce", "RP_RenderPreview"],
        "parameters": [
            {"name": "lpszReportId", "json_type": "string", "description": "Report identifier"},
            {"name": "dwNonce", "json_type": "integer", "description": "Report nonce"},
        ],
    }

    class _EmptyCompletions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "RP_RenderPreview":
            return {
                "result_str": f"Returned: 0\npOutReportId={promoted_report}",
                "trace": {"backend": "bridge"},
            }
        if inv["name"] == "RP_GetReportNonce":
            assert args["lpszReportId"] == promoted_report
            return {
                "result_str": "Returned: 0\npdwNonceOut=3911728039",
                "trace": {"backend": "bridge"},
            }
        if inv["name"] == "RP_CloseReport":
            assert args["lpszReportId"] == promoted_report
            assert args["dwNonce"] == 3911728039
            return {"result_str": "Returned: -5004", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=6, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-reporting-live-promotion",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_EmptyCompletions())),
        model="test-model",
        invocables=[close_inv, get_nonce_inv, render_inv],
        inv_map={
            "RP_CloseReport": close_inv,
            "RP_GetReportNonce": get_nonce_inv,
            "RP_RenderPreview": render_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294962292: "reporting failure"},
        ghidra_data_types=[],
    )

    _explore_one(close_inv, ctx)

    get_nonce_calls = [args for name, args in captured_calls if name == "RP_GetReportNonce"]
    assert get_nonce_calls
    assert get_nonce_calls[-1]["lpszReportId"] == promoted_report
    render_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") == "structured_preflight_prereq"
        and entry.get("function") == "RP_RenderPreview"
        and (entry.get("lineage_admission") or {}).get("replay_outcome") == "executed"
    ]
    assert render_logs
    assert render_logs[-1]["lineage_admission"]["live_value_promoted"] is True
    assert render_logs[-1]["lineage_admission"]["promoted_hints"]["report_id"] == promoted_report
    assert "RP_GetReportNonce" in render_logs[-1]["lineage_admission"]["retry_resumed"]


def test_blob_token_materialization_failure_is_traced_after_live_handle_promotion(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    probe_log_batches: list[list[dict]] = []

    free_blob_inv = {
        "name": "TP_FreeBlobToken",
        "parameters": [
            {"name": "dwBlobToken", "type": "DWORD", "resolved_type": "DWORD", "direction": "in", "json_type": "integer", "description": "Opaque blob token to release"}
        ],
        "doc_comment": "Required preconditions: TP_AllocBlobToken",
    }
    alloc_inv = {
        "name": "TP_AllocBlobToken",
        "parameters": [
            {"name": "dwSessionHandle", "type": "DWORD", "resolved_type": "DWORD", "direction": "in", "json_type": "integer", "description": "Opaque session handle"},
            {"name": "pdwBlobTokenOut", "type": "DWORD*", "resolved_type": "DWORD*", "direction": "out", "json_type": "integer", "description": "Output opaque blob token"},
        ],
        "doc_comment": 'Required preconditions: TP_OpenSession | Canonical args: {"dwSessionHandle": "handle-from-open"}',
    }
    open_inv = dict(_TRANSPORT_OPEN_INV)
    bind_inv = {
        "name": "TP_BindCustomer",
        "parameters": [{"name": "lpszCustId", "json_type": "string", "description": "Customer identifier"}],
    }
    init_inv = {"name": "TP_Initialize", "parameters": []}

    class _EmptyCompletions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "TP_Initialize":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        if inv["name"] == "TP_BindCustomer":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        if inv["name"] == "TP_OpenSession":
            return {"result_str": "Returned: 0\npdwHandleOut=1073745926", "trace": {"backend": "bridge"}}
        if inv["name"] == "TP_AllocBlobToken":
            assert args["dwSessionHandle"] == 1073745926
            return {"result_str": "Returned: 0\npdwBlobTokenOut=0", "trace": {"backend": "bridge"}}
        if inv["name"] == "TP_FreeBlobToken":
            return {"result_str": "Returned: 4294961292", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 4294961292", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._append_explore_probe_log",
        lambda job_id, entries: probe_log_batches.append(entries),
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: [])

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=8, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-blob-materialization-trace",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_EmptyCompletions())),
        model="test-model",
        invocables=[free_blob_inv, alloc_inv, open_inv, bind_inv, init_inv],
        inv_map={
            "TP_FreeBlobToken": free_blob_inv,
            "TP_AllocBlobToken": alloc_inv,
            "TP_OpenSession": open_inv,
            "TP_BindCustomer": bind_inv,
            "TP_Initialize": init_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={4294961292: "transport failure", 4294961294: "transport failure"},
        ghidra_data_types=[],
    )

    _explore_one(free_blob_inv, ctx)

    alloc_calls = [args for name, args in captured_calls if name == "TP_AllocBlobToken"]
    assert alloc_calls
    assert alloc_calls[0]["dwSessionHandle"] == 1073745926
    alloc_logs = [
        entry
        for batch in probe_log_batches
        for entry in batch
        if entry.get("phase") == "structured_preflight_prereq"
        and entry.get("function") == "TP_AllocBlobToken"
        and (entry.get("lineage_admission") or {}).get("replay_outcome") == "executed"
    ]
    assert alloc_logs
    assert alloc_logs[-1]["lineage_admission"]["materialization_missing_families"] == ["blob_token"]


def test_explore_one_replays_inferred_soundtouch_creator_before_setter(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    stored_findings: list[dict] = []

    create_inv = {
        "name": "soundtouch_createInstance",
        "return_type": "void *",
        "parameters": [],
    }
    tempo_inv = {
        "name": "soundtouch_setTempo",
        "parameters": [
            {
                "name": "param_1",
                "type": "int *",
                "resolved_type": "int *",
                "direction": "out",
                "json_type": "integer",
                "description": "Output - receives integer result",
            },
            {
                "name": "param_2",
                "type": "float",
                "resolved_type": "float",
                "direction": "in",
                "json_type": "number",
                "description": "tempo value",
            },
        ],
        "doc_comment": "if (*param_1 == 0x1770c001) return 0x50000001;",
    }

    class _EmptyCompletions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "soundtouch_createInstance":
            return {
                "result_str": "Returned: 140733193388032 (pointer=0x00007FFAAABBCC00)",
                "trace": {"backend": "bridge"},
            }
        if inv["name"] == "soundtouch_setTempo":
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_explore_probe_log", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._save_finding",
        lambda *a, **k: stored_findings.append(dict(a[1])) if len(a) > 1 else None,
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: list(stored_findings))

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=3, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-soundtouch-lineage",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_EmptyCompletions())),
        model="test-model",
        invocables=[tempo_inv, create_inv],
        inv_map={
            "soundtouch_setTempo": tempo_inv,
            "soundtouch_createInstance": create_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={0x50000001: "failure"},
        ghidra_data_types=[],
    )

    _explore_one(tempo_inv, ctx)

    assert [name for name, _ in captured_calls[:2]] == [
        "soundtouch_createInstance",
        "soundtouch_setTempo",
    ]
    assert captured_calls[1][1]["param_1"] == 140733193388032
    assert captured_calls[1][1]["param_2"] == 1.0


def test_explore_one_retags_prerequisite_replay_and_preserves_putsamples_payload(monkeypatch) -> None:
    captured_calls: list[tuple[str, dict]] = []
    stored_findings: list[dict] = []
    handle = 140733193388032

    create_inv = {
        "name": "soundtouch_createInstance",
        "return_type": "void *",
        "parameters": [],
    }
    set_channels_inv = {
        "name": "soundtouch_setChannels",
        "parameters": [
            {
                "name": "param_1",
                "type": "int *",
                "resolved_type": "int *",
                "direction": "out",
                "json_type": "integer",
                "description": "Output - receives integer result",
            },
            {
                "name": "param_2",
                "type": "uint",
                "resolved_type": "uint",
                "direction": "in",
                "json_type": "integer",
                "description": "Integer input parameter",
            },
        ],
        "doc_comment": "if (*param_1 == 0x1770c001) return 0x50000001;",
    }
    set_rate_inv = {
        "name": "soundtouch_setSampleRate",
        "parameters": [
            {
                "name": "param_1",
                "type": "int *",
                "resolved_type": "int *",
                "direction": "out",
                "json_type": "integer",
                "description": "Output - receives integer result",
            },
            {
                "name": "param_2",
                "type": "int",
                "resolved_type": "int",
                "direction": "in",
                "json_type": "integer",
                "description": "Integer input parameter",
            },
        ],
        "doc_comment": "if (*param_1 == 0x1770c001) return 0x50000001;",
    }
    put_samples_inv = {
        "name": "soundtouch_putSamples_i16",
        "parameters": [
            {
                "name": "param_1",
                "type": "int *",
                "resolved_type": "int *",
                "direction": "out",
                "json_type": "integer",
                "description": "Input sample count. Example: `64`.",
            },
            {
                "name": "param_2",
                "type": "float *",
                "resolved_type": "float *",
                "direction": "out",
                "json_type": "number",
                "description": "Buffer length for the operation. Example: `128`.",
            },
            {
                "name": "param_3",
                "type": "uint",
                "resolved_type": "uint",
                "direction": "in",
                "json_type": "integer",
                "description": "Additional processing parameter. Example: `1`.",
            },
        ],
        "execution": {
            "arg_types": ["int *", "float *", "uint"],
        },
        "doc_comment": "if (*param_1 == 0x1770c001) return 0x50000001;",
    }

    class _EmptyCompletions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])

    def _fake_execute_tool_traced(inv, args):
        captured_calls.append((inv["name"], dict(args)))
        if inv["name"] == "soundtouch_createInstance":
            return {
                "result_str": f"Returned: {handle} (pointer=0x00007FFAAABBCC00)",
                "trace": {"backend": "bridge"},
            }
        if inv["name"] in {"soundtouch_setChannels", "soundtouch_setSampleRate"}:
            return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}
        if inv["name"] == "soundtouch_putSamples_i16":
            return {"result_str": "DLL call error: exception: integer divide by zero", "trace": {"backend": "bridge"}}
        return {"result_str": "Returned: 0", "trace": {"backend": "bridge"}}

    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool_traced", _fake_execute_tool_traced)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_explore_probe_log", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._save_finding",
        lambda *a, **k: stored_findings.append(dict(a[1])) if len(a) > 1 else None,
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: list(stored_findings))

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=6, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-soundtouch-putsamples-lineage",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_EmptyCompletions())),
        model="test-model",
        invocables=[put_samples_inv, create_inv, set_channels_inv, set_rate_inv],
        inv_map={
            "soundtouch_putSamples_i16": put_samples_inv,
            "soundtouch_createInstance": create_inv,
            "soundtouch_setChannels": set_channels_inv,
            "soundtouch_setSampleRate": set_rate_inv,
        },
        tool_schemas=[],
        total=1,
        sentinels={0x50000001: "failure"},
        ghidra_data_types=[],
    )

    _explore_one(put_samples_inv, ctx)

    set_channels_call = next(args for name, args in captured_calls if name == "soundtouch_setChannels")
    set_rate_call = next(args for name, args in captured_calls if name == "soundtouch_setSampleRate")
    put_samples_call = next(args for name, args in captured_calls if name == "soundtouch_putSamples_i16")

    assert set_channels_call["param_1"] == handle
    assert set_rate_call["param_1"] == handle
    assert isinstance(put_samples_call["param_2"], list)
    assert put_samples_call["param_2"] == [0, 512, -512, 1024, -1024, 1536, -1536, 2048]


def test_existing_same_run_verified_success_is_not_downgraded_by_later_failed_reprobe(monkeypatch) -> None:
    stored_findings = [
        {
            "function": "RP_RenderPreview",
            "status": "verified_success",
            "status_canonical": "verified_success",
            "working_call": {"lpszReportId": "RPT-CUST-001-02", "dwBufLen": 64},
            "finding": "Verified during prerequisite replay for RP_ExportLedger.",
        }
    ]

    preview_inv = {
        "name": "RP_RenderPreview",
        "parameters": [
            {"name": "lpszReportId", "json_type": "string", "description": "Report identifier"},
            {"name": "dwBufLen", "json_type": "integer", "description": "Preview buffer size"},
        ],
    }

    class _EmptyCompletions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])

    monkeypatch.setattr(
        "api.pipeline.s02_probe.probe_loop._execute_tool_traced",
        lambda inv, args: {"result_str": "Returned: 4294963292", "trace": {"backend": "bridge"}},
    )
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._execute_tool", lambda inv, args: "Returned: 0")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._cancel_requested", lambda job_id: False)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._set_explore_status", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_explore_probe_log", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_stage_context", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_transcript", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._append_executor_trace", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._upload_to_blob", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._download_blob", lambda *a, **k: b"[]")
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_invocable", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._patch_finding", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._save_finding", lambda *a, **k: stored_findings.append(dict(a[1])))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._write_policy_precheck", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_hypothesis", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._update_vocabulary", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._synthesize", lambda *a, **k: {})
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._generate_confidence_gaps", lambda *a, **k: [])
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._backfill_schema_from_synthesis", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._attempt_gap_resolution", lambda *a, **k: None)
    monkeypatch.setattr("api.pipeline.s02_probe.probe_loop._run_gap_answer_mini_sessions", lambda *a, **k: None)
    monkeypatch.setattr("api.infra.storage._load_findings", lambda job_id: list(stored_findings))

    runtime = ExploreRuntime(max_rounds=0, max_tool_calls=2, min_direct_probes=1, deterministic_fallback_enabled=False)
    ctx = ExploreContext(
        job_id="job-preserve-success",
        runtime=runtime,
        client=SimpleNamespace(chat=SimpleNamespace(completions=_EmptyCompletions())),
        model="test-model",
        invocables=[preview_inv],
        inv_map={"RP_RenderPreview": preview_inv},
        tool_schemas=[],
        total=1,
        sentinels={4294963292: "reporting gate unmet"},
        ghidra_data_types=[],
    )

    _explore_one(preview_inv, ctx)

    latest = next(f for f in reversed(stored_findings) if f.get("function") == "RP_RenderPreview")
    assert latest["status"] == "verified_success"
