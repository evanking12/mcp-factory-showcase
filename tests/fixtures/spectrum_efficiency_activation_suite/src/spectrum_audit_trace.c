#include "..\include\spectrum_suite.h"

SP_EXPORT int SP_CALL SP_RecordReleaseReceipt(
    const char* attestation_packet,
    const char* operator_token,
    char* out_audit_receipt,
    DWORD out_len
) {
    char audit_receipt[96];
    if (sp_require_dependency("spectrum_attestation_stage.dll", "SP_EmitReleaseAttestation") != SP_OK) {
        return SP_ERR_DEPENDENCY;
    }
    if (!sp_has_prefix(attestation_packet, "sp-att-")) {
        return SP_ERR_BADTOKEN;
    }
    if (operator_token && *operator_token && !sp_has_prefix(operator_token, "sp-operator-")) {
        return SP_ERR_BADTOKEN;
    }
    sp_make_token(audit_receipt, sizeof(audit_receipt), "sp-audit", attestation_packet + 7, "receipt");
    return sp_copy_out(out_audit_receipt, out_len, audit_receipt);
}

SP_EXPORT int SP_CALL SP_DescribeAuditCoverage(
    const char* audit_receipt,
    char* out_summary,
    DWORD out_len
) {
    if (!sp_has_prefix(audit_receipt, "sp-audit-")) {
        return SP_ERR_BADTOKEN;
    }
    return sp_copy_out(out_summary, out_len, "audit_coverage=wide|frontier=false_positive|looks_rich=true");
}

SP_EXPORT int SP_CALL SP_RehydrateAuditWindow(
    const char* reservation_handle,
    char* out_audit_window,
    DWORD out_len
) {
    if (!sp_has_prefix(reservation_handle, "sp-resv-")) {
        return SP_ERR_BADTOKEN;
    }
    return sp_copy_out(out_audit_window, out_len, "audit_window=replayable_without_improving_primary_goal");
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpReserved;
    return TRUE;
}
