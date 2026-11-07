#include "..\include\spectrum_suite.h"

SP_EXPORT int SP_CALL SP_StageReleaseInvoice(
    const char* attestation_packet,
    char* out_invoice_stage_id,
    DWORD out_len
) {
    char invoice_stage_id[96];
    if (sp_require_dependency("spectrum_attestation_stage.dll", "SP_EmitReleaseAttestation") != SP_OK) {
        return SP_ERR_DEPENDENCY;
    }
    if (!sp_has_prefix(attestation_packet, "sp-att-")) {
        return SP_ERR_BADTOKEN;
    }
    sp_make_token(invoice_stage_id, sizeof(invoice_stage_id), "sp-invoice-stage", attestation_packet + 7, "queued");
    return sp_copy_out(out_invoice_stage_id, out_len, invoice_stage_id);
}

SP_EXPORT int SP_CALL SP_DescribeInvoiceCarryForward(
    const char* invoice_stage_id,
    char* out_summary,
    DWORD out_len
) {
    if (!sp_has_prefix(invoice_stage_id, "sp-invoice-stage-")) {
        return SP_ERR_BADTOKEN;
    }
    return sp_copy_out(out_summary, out_len, "invoice_carry_forward=attestation_reuse|pass=two");
}

SP_EXPORT int SP_CALL SP_ProjectInvoicePostingWindow(
    const char* attestation_packet,
    char* out_projection,
    DWORD out_len
) {
    if (!sp_has_prefix(attestation_packet, "sp-att-")) {
        return SP_ERR_BADTOKEN;
    }
    return sp_copy_out(out_projection, out_len, "invoice_posting_window=late_if-confirmation-missing");
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpReserved;
    return TRUE;
}
