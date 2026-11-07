#include "..\include\spectrum_suite.h"

SP_EXPORT int SP_CALL SP_StageCustomerEntitlementUpdate(
    const char* attestation_packet,
    char* out_entitlement_stage_id,
    DWORD out_len
) {
    char entitlement_stage_id[96];
    if (sp_require_dependency("spectrum_attestation_stage.dll", "SP_EmitReleaseAttestation") != SP_OK) {
        return SP_ERR_DEPENDENCY;
    }
    if (!sp_has_prefix(attestation_packet, "sp-att-")) {
        return SP_ERR_BADTOKEN;
    }
    sp_make_token(
        entitlement_stage_id,
        sizeof(entitlement_stage_id),
        "sp-entitlement-stage",
        attestation_packet + 7,
        "queued"
    );
    return sp_copy_out(out_entitlement_stage_id, out_len, entitlement_stage_id);
}

SP_EXPORT int SP_CALL SP_DescribeEntitlementCarryForward(
    const char* entitlement_stage_id,
    char* out_summary,
    DWORD out_len
) {
    if (!sp_has_prefix(entitlement_stage_id, "sp-entitlement-stage-")) {
        return SP_ERR_BADTOKEN;
    }
    return sp_copy_out(out_summary, out_len, "entitlement_carry_forward=attestation_reuse|pass=two");
}

SP_EXPORT int SP_CALL SP_ProjectEntitlementPostingWindow(
    const char* attestation_packet,
    char* out_projection,
    DWORD out_len
) {
    if (!sp_has_prefix(attestation_packet, "sp-att-")) {
        return SP_ERR_BADTOKEN;
    }
    return sp_copy_out(out_projection, out_len, "entitlement_window=late_if-confirmation-missing");
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpReserved;
    return TRUE;
}
