#include "..\include\spectrum_suite.h"

SP_EXPORT int SP_CALL SP_PrepareReleasePreview(
    const char* reservation_handle,
    const char* operator_token,
    char* out_preview_ticket,
    DWORD out_len
) {
    char preview_ticket[96];
    if (sp_require_dependency("spectrum_reservation_stage.dll", "SP_IssueReleaseHold") != SP_OK) {
        return SP_ERR_DEPENDENCY;
    }
    if (!sp_has_prefix(reservation_handle, "sp-resv-") || !sp_has_prefix(operator_token, "sp-operator-")) {
        return SP_ERR_BADTOKEN;
    }
    if (!out_preview_ticket || out_len < 24) {
        return SP_ERR_BADPARAM;
    }
    sp_make_token(preview_ticket, sizeof(preview_ticket), "sp-preview", reservation_handle + 8, "dispatch");
    return sp_copy_out(out_preview_ticket, out_len, preview_ticket);
}

SP_EXPORT int SP_CALL SP_DescribeDispatchWindow(
    const char* preview_ticket,
    char* out_summary,
    DWORD out_len
) {
    if (!sp_has_prefix(preview_ticket, "sp-preview-")) {
        return SP_ERR_BADTOKEN;
    }
    return sp_copy_out(out_summary, out_len, "dispatch_window=curated|frontier=pass_one|depth=medium");
}

SP_EXPORT int SP_CALL SP_ClassifyDispatchDeferralRisk(
    const char* reservation_handle,
    char* out_risk_code,
    DWORD out_len
) {
    if (!sp_has_prefix(reservation_handle, "sp-resv-")) {
        return SP_ERR_BADTOKEN;
    }
    return sp_copy_out(out_risk_code, out_len, "dispatch-risk=bounded-if-fee-quote-present");
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpReserved;
    return TRUE;
}
