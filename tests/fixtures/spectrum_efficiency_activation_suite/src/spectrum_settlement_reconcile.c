#include "..\include\spectrum_suite.h"

SP_EXPORT int SP_CALL SP_ConfirmAttestedRelease(
    const char* attestation_packet,
    const char* invoice_stage_id,
    const char* entitlement_stage_id,
    char* out_confirmation_id,
    DWORD out_len
) {
    char confirmation_id[96];
    if (sp_require_dependency("spectrum_invoice_sync.dll", "SP_StageReleaseInvoice") != SP_OK) {
        return SP_ERR_DEPENDENCY;
    }
    if (sp_require_dependency("spectrum_entitlement_sync.dll", "SP_StageCustomerEntitlementUpdate") != SP_OK) {
        return SP_ERR_DEPENDENCY;
    }
    if (!sp_has_prefix(attestation_packet, "sp-att-") ||
        !sp_has_prefix(invoice_stage_id, "sp-invoice-stage-") ||
        !sp_has_prefix(entitlement_stage_id, "sp-entitlement-stage-")) {
        return SP_ERR_BADTOKEN;
    }
    if (!out_confirmation_id || out_len < 24) {
        return SP_ERR_BADPARAM;
    }
    sp_make_token(confirmation_id, sizeof(confirmation_id), "sp-confirm", attestation_packet + 7, "attested");
    return sp_copy_out(out_confirmation_id, out_len, confirmation_id);
}

SP_EXPORT int SP_CALL SP_VerifyReservedRelease(
    const char* reservation_handle,
    const char* preview_ticket,
    const char* fee_quote_id,
    char* out_verification_ticket,
    DWORD out_len
) {
    char verification_ticket[96];
    if (sp_require_dependency("spectrum_dispatch_preview.dll", "SP_PrepareReleasePreview") != SP_OK) {
        return SP_ERR_DEPENDENCY;
    }
    if (sp_require_dependency("spectrum_fee_quote.dll", "SP_StageReleaseFeeQuote") != SP_OK) {
        return SP_ERR_DEPENDENCY;
    }
    if (!sp_has_prefix(reservation_handle, "sp-resv-") ||
        !sp_has_prefix(preview_ticket, "sp-preview-") ||
        !sp_has_prefix(fee_quote_id, "sp-fee-")) {
        return SP_ERR_BADTOKEN;
    }
    sp_make_token(verification_ticket, sizeof(verification_ticket), "sp-verify", reservation_handle + 8, "reserved");
    return sp_copy_out(out_verification_ticket, out_len, verification_ticket);
}

SP_EXPORT int SP_CALL SP_DescribeSettlementProofWindow(
    const char* confirmation_id,
    char* out_summary,
    DWORD out_len
) {
    if (!sp_has_prefix(confirmation_id, "sp-confirm-")) {
        return SP_ERR_BADTOKEN;
    }
    return sp_copy_out(out_summary, out_len, "late_truth_surface=settlement_confirmation|can_falsify_bad_frontier");
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpReserved;
    return TRUE;
}
