#include "..\include\spectrum_suite.h"

SP_EXPORT int SP_CALL SP_OpenOperatorSession(const char* operator_id, char* out_operator_token, DWORD out_len) {
    char token[96];
    const char* effective_operator_id = (operator_id && *operator_id) ? operator_id : "activation-operator";
    if (!out_operator_token || out_len < 24) {
        return SP_ERR_BADPARAM;
    }
    sp_make_token(token, sizeof(token), "sp-operator", effective_operator_id, "session");
    return sp_copy_out(out_operator_token, out_len, token);
}

SP_EXPORT int SP_CALL SP_DescribeSessionBootstrapWindow(
    const char* operator_token,
    char* out_summary,
    DWORD out_len
) {
    if (!sp_has_prefix(operator_token, "sp-operator-")) {
        return SP_ERR_BADTOKEN;
    }
    return sp_copy_out(out_summary, out_len, "bootstrap_window=session_anchor|depth=floor0|reuse=allowed");
}

SP_EXPORT int SP_CALL SP_ProjectSessionHandshakeFloor(
    const char* operator_id,
    char* out_projection,
    DWORD out_len
) {
    char projection[128];
    const char* effective_operator_id = (operator_id && *operator_id) ? operator_id : "activation-operator";
    _snprintf(
        projection,
        sizeof(projection) - 1,
        "handshake_floor|operator=%s|artifact=session_bootstrap|priority=high",
        effective_operator_id
    );
    projection[sizeof(projection) - 1] = '\0';
    return sp_copy_out(out_projection, out_len, projection);
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpReserved;
    return TRUE;
}
