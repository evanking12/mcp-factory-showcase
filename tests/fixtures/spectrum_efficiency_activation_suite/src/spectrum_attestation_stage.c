#include "..\include\spectrum_suite.h"

SP_EXPORT int SP_CALL SP_EmitReleaseAttestation(
    const char* preview_ticket,
    const char* fee_quote_id,
    char* out_attestation_packet,
    DWORD packet_len,
    uint32_t* out_attestation_nonce,
    uint32_t* out_attestation_epoch
) {
    char attestation_packet[96];
    int dep_preview = sp_require_dependency("spectrum_dispatch_preview.dll", "SP_PrepareReleasePreview");
    int dep_fee = sp_require_dependency("spectrum_fee_quote.dll", "SP_StageReleaseFeeQuote");
    if (dep_preview != SP_OK || dep_fee != SP_OK) {
        return SP_ERR_DEPENDENCY;
    }
    if (!sp_has_prefix(preview_ticket, "sp-preview-") || !sp_has_prefix(fee_quote_id, "sp-fee-")) {
        return SP_ERR_BADTOKEN;
    }
    if (!out_attestation_packet || packet_len < 24 || !out_attestation_nonce || !out_attestation_epoch) {
        return SP_ERR_BADPARAM;
    }
    sp_make_token(attestation_packet, sizeof(attestation_packet), "sp-att", preview_ticket + 11, "packet");
    *out_attestation_nonce = 0xA7700000UL | ((uint32_t)strlen(fee_quote_id) & 0xFFFFU);
    *out_attestation_epoch = 20260413U;
    return sp_copy_out(out_attestation_packet, packet_len, attestation_packet);
}

SP_EXPORT int SP_CALL SP_SummarizeAttestationReuse(
    const char* attestation_packet,
    char* out_summary,
    DWORD out_len
) {
    if (!sp_has_prefix(attestation_packet, "sp-att-")) {
        return SP_ERR_BADTOKEN;
    }
    return sp_copy_out(out_summary, out_len, "reuse_story=delayed_attestation|eligible_for_pass_two=true");
}

SP_EXPORT int SP_CALL SP_PreviewAttestationEnvelope(
    const char* preview_ticket,
    const char* fee_quote_id,
    char* out_envelope_id,
    DWORD out_len
) {
    char envelope_id[96];
    if (!sp_has_prefix(preview_ticket, "sp-preview-") || !sp_has_prefix(fee_quote_id, "sp-fee-")) {
        return SP_ERR_BADTOKEN;
    }
    sp_make_token(envelope_id, sizeof(envelope_id), "sp-att-envelope", preview_ticket + 11, fee_quote_id + 7);
    return sp_copy_out(out_envelope_id, out_len, envelope_id);
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpReserved;
    return TRUE;
}
