from __future__ import annotations

from api.infra import storage
from api.pipeline.core.reusable_truth import assess_reusable_truth


def _customer_purchase_invocable() -> dict:
    return {
        "name": "CP_ProcessPurchase",
        "parameters": [
            {
                "name": "lpszCustomerId",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "Customer identifier",
            },
            {
                "name": "dwQuantity",
                "json_type": "integer",
                "description": "Quantity to purchase",
            },
        ],
    }


def _pricing_begin_quote_invocable() -> dict:
    return {
        "name": "PR_BeginQuote",
        "parameters": [
            {
                "name": "pOutQuoteId",
                "json_type": "string",
                "resolved_type": "char*",
                "direction": "out",
                "description": "Output quote id",
            },
            {
                "name": "dwBufLen",
                "json_type": "integer",
                "description": "Quote id buffer size",
            },
        ],
    }


def _spectrum_session_invocable() -> dict:
    return {
        "name": "SP_OpenOperatorSession",
        "parameters": [
            {
                "name": "operator_id",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "The ID of the operator to open a session for.",
            },
            {
                "name": "out_operator_token",
                "json_type": "string",
                "resolved_type": "char*",
                "direction": "out",
                "description": "The session token for the operator, populated with a string value upon successful session opening.",
            },
            {
                "name": "out_len",
                "json_type": "integer",
                "description": "The length of the output token buffer, which should be sufficient to hold the session token.",
            },
        ],
    }


def _spectrum_stale_invalidation_invocable() -> dict:
    return {
        "name": "SP_InvalidateStaleAttestedRelease",
        "parameters": [
            {
                "name": "attestation_packet",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "Release attestation packet.",
            },
            {
                "name": "attestation_nonce",
                "json_type": "integer",
                "resolved_type": "uint32_t",
                "description": "Workflow/session nonce derived from the preceding read step.",
            },
            {
                "name": "attestation_epoch",
                "json_type": "integer",
                "resolved_type": "uint32_t",
                "description": "Release attestation epoch.",
            },
            {
                "name": "out_stale_attestation_token",
                "json_type": "string",
                "resolved_type": "char*",
                "direction": "out",
                "description": "Output value populated by SP_InvalidateStaleAttestedRelease.",
            },
            {
                "name": "token_len",
                "json_type": "integer",
                "resolved_type": "DWORD",
                "description": "Unlock token buffer size.",
            },
            {
                "name": "out_stale_reason",
                "json_type": "string",
                "resolved_type": "char*",
                "direction": "out",
                "description": "Output value populated by SP_InvalidateStaleAttestedRelease.",
            },
            {
                "name": "reason_len",
                "json_type": "integer",
                "resolved_type": "DWORD",
                "description": "Buffer size.",
            },
        ],
    }


def _spectrum_stale_audit_invocable() -> dict:
    return {
        "name": "SP_RecordStaleAttestationInvalidation",
        "parameters": [
            {
                "name": "stale_attestation_token",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "Verified stale attestation token from settlement.",
            },
            {
                "name": "stale_reason",
                "json_type": "string",
                "resolved_type": "const char*",
                "description": "Verified stale attestation reason from settlement.",
            },
            {
                "name": "out_audit_token",
                "json_type": "string",
                "resolved_type": "char*",
                "direction": "out",
                "description": "Output value populated by SP_RecordStaleAttestationInvalidation.",
            },
            {
                "name": "out_len",
                "json_type": "integer",
                "resolved_type": "DWORD",
                "description": "Audit token buffer size.",
            },
        ],
    }


def _spectrum_reservation_invocable() -> dict:
    return {
        "name": "SP_IssueReleaseHold",
        "parameters": [
            {
                "name": "operator_token",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "Session identifier for the operator, e.g., 'sp-operator-0-session'.",
            },
            {
                "name": "order_id",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "Unique identifier for the order.",
            },
            {
                "name": "amount_cents",
                "json_type": "integer",
                "description": "Amount in cents to hold.",
            },
            {
                "name": "out_reservation_handle",
                "json_type": "string",
                "resolved_type": "char*",
                "direction": "out",
                "description": "Unique identifier for the reservation, populated as an output parameter.",
            },
            {
                "name": "reservation_len",
                "json_type": "integer",
                "description": "Buffer size",
            },
            {
                "name": "out_hold_token",
                "json_type": "string",
                "resolved_type": "char*",
                "direction": "out",
                "description": "Unique identifier for the hold, populated as an output parameter.",
            },
            {
                "name": "hold_len",
                "json_type": "integer",
                "description": "Buffer size",
            },
        ],
    }


def _spectrum_preview_invocable() -> dict:
    return {
        "name": "SP_PrepareReleasePreview",
        "parameters": [
            {
                "name": "reservation_handle",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "Workflow handle returned by WF_OpenFulfillment",
            },
            {
                "name": "operator_token",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "Unlock token hex returned by the fixture",
            },
            {
                "name": "out_preview_ticket",
                "json_type": "string",
                "resolved_type": "char*",
                "direction": "out",
                "description": "The generated preview ticket identifier.",
            },
            {
                "name": "out_len",
                "json_type": "integer",
                "description": "The length of the preview ticket in bytes.",
            },
        ],
    }


def _spectrum_replay_invocable() -> dict:
    return {
        "name": "SP_ReplayReleaseBranch",
        "parameters": [
            {
                "name": "reservation_handle",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "The handle for the reservation to replay, typically formatted as 'sp-resv-<order_id>-<unique_id>'.",
            },
            {
                "name": "hold_token",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "The token associated with the hold, usually a hex string returned by the hold operation.",
            },
            {
                "name": "out_replay_receipt",
                "json_type": "string",
                "resolved_type": "char*",
                "direction": "out",
                "description": "Output replay receipt.",
            },
            {
                "name": "out_len",
                "json_type": "integer",
                "description": "The length of the output buffer, which should be sufficient to hold the replay receipt.",
            },
        ],
    }


def _spectrum_verify_reserved_release_invocable() -> dict:
    return {
        "name": "SP_VerifyReservedRelease",
        "parameters": [
            {
                "name": "reservation_handle",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "Reservation handle produced by the release hold stage.",
            },
            {
                "name": "preview_ticket",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "Preview ticket returned by SP_PrepareReleasePreview.",
            },
            {
                "name": "fee_quote_id",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "Fee quote identifier.",
            },
            {
                "name": "out_verification_ticket",
                "json_type": "string",
                "resolved_type": "char*",
                "direction": "out",
                "description": "Output verification ticket for the reserved release.",
            },
            {
                "name": "out_len",
                "json_type": "integer",
                "description": "Verification ticket buffer size.",
            },
        ],
    }


def test_assess_reusable_truth_rejects_semantically_misaligned_customer_success() -> None:
    assessment = assess_reusable_truth(
        {
            "status": "success",
            "working_call": {
                "lpszCustomerId": "ACC-USB-C",
                "dwQuantity": 1,
            },
        },
        invocable=_customer_purchase_invocable(),
    )

    assert assessment["seed_eligible"] is False
    assert assessment["demote_success"] is True
    assert assessment["mismatch_count"] == 1


def test_save_finding_demotes_semantically_misaligned_success(monkeypatch) -> None:
    monkeypatch.setattr(storage, "_upload_to_blob", lambda *_args, **_kwargs: "")
    storage._JOB_FINDINGS.clear()
    storage._JOB_INVOCABLE_MAPS.clear()
    storage._JOB_INVOCABLE_MAPS["job-1"] = {
        "CP_ProcessPurchase": _customer_purchase_invocable(),
    }

    storage._save_finding(
        "job-1",
        {
            "function": "CP_ProcessPurchase",
            "status": "success",
            "finding": "Returned 0 with a SKU-like customer value.",
            "working_call": {
                "lpszCustomerId": "ACC-USB-C",
                "dwQuantity": 1,
            },
        },
    )

    row = storage._JOB_FINDINGS["job-1"][-1]
    assert row["status_canonical"] == "inferred_success"
    assert row["reusable_truth_eligible"] is False
    assert "lpszCustomerId_expected_customer_id" in row["reusable_truth_reasons"]


def test_assess_reusable_truth_rejects_empty_semantic_output_on_realistic_producer_success() -> None:
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "pOutQuoteId": "",
                "dwBufLen": 64,
            },
            "finding": "Verified during prerequisite replay for PR_GetQuoteState: returns 0.",
        },
        invocable=_pricing_begin_quote_invocable(),
    )

    assert assessment["seed_eligible"] is False
    assert "pOutQuoteId_expected_quote_id" in assessment["reasons"]


def test_save_finding_demotes_empty_semantic_output_success(monkeypatch) -> None:
    monkeypatch.setattr(storage, "_upload_to_blob", lambda *_args, **_kwargs: "")
    storage._JOB_FINDINGS.clear()
    storage._JOB_INVOCABLE_MAPS.clear()
    storage._JOB_INVOCABLE_MAPS["job-2"] = {
        "PR_BeginQuote": _pricing_begin_quote_invocable(),
    }

    storage._save_finding(
        "job-2",
        {
            "function": "PR_BeginQuote",
            "status": "success",
            "finding": "Returned 0 with empty quote output.",
            "working_call": {
                "pOutQuoteId": "",
                "dwBufLen": 64,
            },
        },
    )

    row = storage._JOB_FINDINGS["job-2"][-1]
    assert row["status_canonical"] == "inferred_success"
    assert row["reusable_truth_eligible"] is False
    assert "pOutQuoteId_expected_quote_id" in row["reusable_truth_reasons"]


def test_assess_reusable_truth_accepts_spectrum_session_operator_token_output() -> None:
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "operator_id": "easy01-operator",
                "out_operator_token": "sp-operator-easy01-operator-session",
                "out_len": 64,
            },
            "verification": "verified",
        },
        invocable=_spectrum_session_invocable(),
    )

    assert assessment["seed_eligible"] is True
    assert assessment["mismatch_count"] == 0


def test_assess_reusable_truth_accepts_stale_attestation_outputs() -> None:
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "attestation_packet": "sp-att-ORD-20040301-0042-2500-gate-packet",
                "attestation_nonce": 2809135139,
                "attestation_epoch": 20260408,
                "out_stale_attestation_token": "sp-att-stale-35",
                "token_len": 64,
                "out_stale_reason": "freshness_gap|epoch=20260408|packet=sp-att-ORD-20040301-0042-25",
                "reason_len": 64,
            },
            "verification": "verified",
        },
        invocable=_spectrum_stale_invalidation_invocable(),
    )

    assert assessment["seed_eligible"] is True
    assert assessment["mismatch_count"] == 0
    assert "out_stale_attestation_token_expected_blob_token" not in assessment["reasons"]
    assert "out_stale_reason_expected_blob_token" not in assessment["reasons"]


def test_assess_reusable_truth_accepts_stale_attestation_audit_token_output() -> None:
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "stale_attestation_token": "sp-att-stale-35",
                "stale_reason": "freshness_gap|epoch=20260408|packet=sp-att-ORD-20040301-0042-25",
                "out_audit_token": "sp-audit-stale-attestation",
                "out_len": 64,
            },
            "verification": "verified",
        },
        invocable=_spectrum_stale_audit_invocable(),
    )

    assert assessment["seed_eligible"] is True
    assert assessment["mismatch_count"] == 0
    assert "out_audit_token_expected_stale_attestation_token" not in assessment["reasons"]


def test_assess_reusable_truth_keeps_customer_id_and_operator_id_distinct() -> None:
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "lpszCustomerId": "easy01-operator",
                "dwQuantity": 1,
            },
            "verification": "verified",
        },
        invocable=_customer_purchase_invocable(),
    )

    assert assessment["seed_eligible"] is False
    assert "lpszCustomerId_expected_customer_id" in assessment["reasons"]


def test_assess_reusable_truth_rejects_operator_tokens_as_operator_ids() -> None:
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "operator_id": "sp-operator-easy01-operator-session",
                "out_operator_token": "sp-operator-easy01-operator-session",
                "out_len": 64,
            },
            "verification": "verified",
        },
        invocable=_spectrum_session_invocable(),
    )

    assert assessment["seed_eligible"] is False
    assert "operator_id_expected_operator_id" in assessment["reasons"]


def test_assess_reusable_truth_rejects_degenerate_operator_id_strings() -> None:
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "operator_id": "not-an-operator",
                "out_operator_token": "sp-operator-not-an-operator-session",
                "out_len": 64,
            },
            "verification": "verified",
        },
        invocable=_spectrum_session_invocable(),
    )

    assert assessment["seed_eligible"] is False
    assert "operator_id_expected_operator_id" in assessment["reasons"]


def test_assess_reusable_truth_accepts_operator_id_alias_names() -> None:
    invocable = {
        "name": "SP_OpenOperatorSession",
        "parameters": [
            {
                "name": "lpszOperatorId",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "Operator identifier.",
            },
            {
                "name": "out_operator_token",
                "json_type": "string",
                "resolved_type": "char*",
                "direction": "out",
                "description": "The session token for the operator.",
            },
        ],
    }
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "lpszOperatorId": "easy01-operator",
                "out_operator_token": "sp-operator-easy01-operator-session",
            },
            "verification": "verified",
        },
        invocable=invocable,
    )

    assert assessment["seed_eligible"] is True
    assert assessment["mismatch_count"] == 0


def test_assess_reusable_truth_rejects_malformed_operator_id_alias_names() -> None:
    invocable = {
        "name": "SP_OpenOperatorSession",
        "parameters": [
            {
                "name": "operatorIdentifier",
                "json_type": "string",
                "resolved_type": "char*",
                "description": "Operator identifier.",
            },
            {
                "name": "out_operator_token",
                "json_type": "string",
                "resolved_type": "char*",
                "direction": "out",
                "description": "The session token for the operator.",
            },
        ],
    }
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "operatorIdentifier": "not-an-operator",
                "out_operator_token": "sp-operator-not-an-operator-session",
            },
            "verification": "verified",
        },
        invocable=invocable,
    )

    assert assessment["seed_eligible"] is False
    assert "operatorIdentifier_expected_operator_id" in assessment["reasons"]


def test_assess_reusable_truth_accepts_spectrum_reservation_contract_shapes() -> None:
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "operator_token": "sp-operator-0-session",
                "order_id": "ORD-20040301-0042",
                "amount_cents": 2500,
                "out_reservation_handle": "sp-resv-ORD-20040301-0042-2500",
                "reservation_len": 64,
                "out_hold_token": "sp-hold-ORD-20040301-0042-2500",
                "hold_len": 64,
            },
            "verification": "verified",
        },
        invocable=_spectrum_reservation_invocable(),
    )

    assert assessment["seed_eligible"] is True
    assert assessment["mismatch_count"] == 0


def test_assess_reusable_truth_accepts_spectrum_preview_contract_shapes() -> None:
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "reservation_handle": "sp-resv-0",
                "operator_token": "sp-operator-0-session",
                "out_preview_ticket": "sp-preview-0-gate",
                "out_len": 64,
            },
            "verification": "verified",
        },
        invocable=_spectrum_preview_invocable(),
    )

    assert assessment["seed_eligible"] is True
    assert assessment["mismatch_count"] == 0


def test_assess_reusable_truth_accepts_spectrum_replay_contract_shapes() -> None:
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "reservation_handle": "sp-resv-ORD-001-4200",
                "hold_token": "sp-hold-ORD-001-4200",
                "out_replay_receipt": "sp-branch-replay-ORD-001-4200-receipt",
                "out_len": 256,
            },
            "verification": "verified",
        },
        invocable=_spectrum_replay_invocable(),
    )

    assert assessment["seed_eligible"] is True
    assert assessment["mismatch_count"] == 0


def test_assess_reusable_truth_accepts_spectrum_verification_ticket_output() -> None:
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "reservation_handle": "sp-resv-ORD-001-2500",
                "preview_ticket": "sp-preview-ORD-001-64-gate",
                "fee_quote_id": "sp-fee-ORD-001-2500-quote",
                "out_verification_ticket": "sp-verify-ORD-001-2500-reserved",
                "out_len": 64,
            },
            "verification": "verified",
        },
        invocable=_spectrum_verify_reserved_release_invocable(),
    )

    assert assessment["seed_eligible"] is True
    assert assessment["mismatch_count"] == 0
    assert "out_verification_ticket_expected_ticket" not in assessment["reasons"]


def test_assess_reusable_truth_rejects_malformed_spectrum_verification_ticket_output() -> None:
    assessment = assess_reusable_truth(
        {
            "status_canonical": "verified_success",
            "working_call": {
                "reservation_handle": "sp-resv-ORD-001-2500",
                "preview_ticket": "sp-preview-ORD-001-64-gate",
                "fee_quote_id": "sp-fee-ORD-001-2500-quote",
                "out_verification_ticket": "sp-att-stale-100",
                "out_len": 64,
            },
            "verification": "verified",
        },
        invocable=_spectrum_verify_reserved_release_invocable(),
    )

    assert assessment["seed_eligible"] is False
    assert "out_verification_ticket_expected_ticket" in assessment["reasons"]
