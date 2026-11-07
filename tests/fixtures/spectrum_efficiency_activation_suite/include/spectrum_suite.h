#ifndef SPECTRUM_SUITE_H
#define SPECTRUM_SUITE_H

#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SP_EXPORT __declspec(dllexport)
#define SP_CALL __cdecl

#define SP_OK               0
#define SP_ERR_BADPARAM  -7101
#define SP_ERR_PRECONDITION -7102
#define SP_ERR_DEPENDENCY -7103
#define SP_ERR_BADTOKEN  -7104
#define SP_ERR_CONFLICT  -7105
#define SP_ERR_STALE     -7106

static __inline int sp_copy_out(char* out_buf, DWORD out_len, const char* text) {
    if (!out_buf || out_len == 0) {
        return SP_ERR_BADPARAM;
    }
    if (!text) {
        text = "";
    }
    _snprintf(out_buf, out_len - 1, "%s", text);
    out_buf[out_len - 1] = '\0';
    return SP_OK;
}

static __inline int sp_has_prefix(const char* value, const char* prefix) {
    size_t prefix_len = 0;
    if (!value || !prefix) {
        return 0;
    }
    prefix_len = strlen(prefix);
    if (strlen(value) < prefix_len) {
        return 0;
    }
    return strncmp(value, prefix, prefix_len) == 0;
}

static __inline void sp_make_token(
    char* out_buf,
    size_t out_len,
    const char* prefix,
    const char* part_a,
    const char* part_b
) {
    const char* safe_a = (part_a && *part_a) ? part_a : "none";
    const char* safe_b = (part_b && *part_b) ? part_b : "none";
    _snprintf(out_buf, out_len - 1, "%s-%s-%s", prefix, safe_a, safe_b);
    out_buf[out_len - 1] = '\0';
}

static __inline int sp_require_dependency(const char* dll_name, const char* symbol_name) {
    HMODULE module_handle = NULL;
    FARPROC symbol = NULL;
    if (!dll_name || !symbol_name) {
        return SP_ERR_BADPARAM;
    }
    module_handle = LoadLibraryA(dll_name);
    if (!module_handle) {
        return SP_ERR_DEPENDENCY;
    }
    symbol = GetProcAddress(module_handle, symbol_name);
    if (!symbol) {
        return SP_ERR_DEPENDENCY;
    }
    return SP_OK;
}

SP_EXPORT int SP_CALL SP_OpenOperatorSession(const char* operator_id, char* out_operator_token, DWORD out_len);
SP_EXPORT int SP_CALL SP_DescribeSessionBootstrapWindow(
    const char* operator_token,
    char* out_summary,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_ProjectSessionHandshakeFloor(
    const char* operator_id,
    char* out_projection,
    DWORD out_len
);

SP_EXPORT int SP_CALL SP_IssueReleaseHold(
    const char* operator_token,
    const char* order_id,
    uint32_t amount_cents,
    char* out_reservation_handle,
    DWORD reservation_len,
    char* out_hold_token,
    DWORD hold_len
);
SP_EXPORT int SP_CALL SP_DescribeReservationFanout(
    const char* reservation_handle,
    char* out_summary,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_ProjectReservationSeed(
    const char* order_id,
    uint32_t amount_cents,
    char* out_seed,
    DWORD out_len
);

SP_EXPORT int SP_CALL SP_PrepareReleasePreview(
    const char* reservation_handle,
    const char* operator_token,
    char* out_preview_ticket,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_DescribeDispatchWindow(
    const char* preview_ticket,
    char* out_summary,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_ClassifyDispatchDeferralRisk(
    const char* reservation_handle,
    char* out_risk_code,
    DWORD out_len
);

SP_EXPORT int SP_CALL SP_StageReleaseFeeQuote(
    const char* reservation_handle,
    const char* operator_token,
    char* out_fee_quote_id,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_DescribeFeeQuoteInputs(
    const char* fee_quote_id,
    char* out_summary,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_ProjectPriorityFeeWindow(
    const char* reservation_handle,
    char* out_projection,
    DWORD out_len
);

SP_EXPORT int SP_CALL SP_EmitReleaseAttestation(
    const char* preview_ticket,
    const char* fee_quote_id,
    char* out_attestation_packet,
    DWORD packet_len,
    uint32_t* out_attestation_nonce,
    uint32_t* out_attestation_epoch
);
SP_EXPORT int SP_CALL SP_SummarizeAttestationReuse(
    const char* attestation_packet,
    char* out_summary,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_PreviewAttestationEnvelope(
    const char* preview_ticket,
    const char* fee_quote_id,
    char* out_envelope_id,
    DWORD out_len
);

SP_EXPORT int SP_CALL SP_StageReleaseInvoice(
    const char* attestation_packet,
    char* out_invoice_stage_id,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_DescribeInvoiceCarryForward(
    const char* invoice_stage_id,
    char* out_summary,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_ProjectInvoicePostingWindow(
    const char* attestation_packet,
    char* out_projection,
    DWORD out_len
);

SP_EXPORT int SP_CALL SP_StageCustomerEntitlementUpdate(
    const char* attestation_packet,
    char* out_entitlement_stage_id,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_DescribeEntitlementCarryForward(
    const char* entitlement_stage_id,
    char* out_summary,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_ProjectEntitlementPostingWindow(
    const char* attestation_packet,
    char* out_projection,
    DWORD out_len
);

SP_EXPORT int SP_CALL SP_ConfirmAttestedRelease(
    const char* attestation_packet,
    const char* invoice_stage_id,
    const char* entitlement_stage_id,
    char* out_confirmation_id,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_VerifyReservedRelease(
    const char* reservation_handle,
    const char* preview_ticket,
    const char* fee_quote_id,
    char* out_verification_ticket,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_DescribeSettlementProofWindow(
    const char* confirmation_id,
    char* out_summary,
    DWORD out_len
);

SP_EXPORT int SP_CALL SP_RecordReleaseReceipt(
    const char* attestation_packet,
    const char* operator_token,
    char* out_audit_receipt,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_DescribeAuditCoverage(
    const char* audit_receipt,
    char* out_summary,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_RehydrateAuditWindow(
    const char* reservation_handle,
    char* out_audit_window,
    DWORD out_len
);

SP_EXPORT int SP_CALL SP_ReplayReleaseBranch(
    const char* reservation_handle,
    const char* hold_token,
    char* out_replay_receipt,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_DescribeReplayVariance(
    const char* replay_receipt,
    char* out_summary,
    DWORD out_len
);
SP_EXPORT int SP_CALL SP_SelectTrustedBranch(
    const char* confirmation_id,
    const char* replay_receipt,
    char* out_trusted_branch_id,
    DWORD trusted_len,
    char* out_rejected_branch_id,
    DWORD rejected_len
);

#ifdef __cplusplus
}
#endif

#endif
