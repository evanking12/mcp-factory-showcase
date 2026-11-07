#include "..\include\spectrum_suite.h"

SP_EXPORT int SP_CALL SP_ReplayReleaseBranch(
    const char* reservation_handle,
    const char* hold_token,
    char* out_replay_receipt,
    DWORD out_len
) {
    char replay_receipt[96];
    if (sp_require_dependency("spectrum_reservation_stage.dll", "SP_IssueReleaseHold") != SP_OK) {
        return SP_ERR_DEPENDENCY;
    }
    if (!sp_has_prefix(reservation_handle, "sp-resv-") || !sp_has_prefix(hold_token, "sp-hold-")) {
        return SP_ERR_BADTOKEN;
    }
    sp_make_token(replay_receipt, sizeof(replay_receipt), "sp-replay", reservation_handle + 8, "branch");
    return sp_copy_out(out_replay_receipt, out_len, replay_receipt);
}

SP_EXPORT int SP_CALL SP_DescribeReplayVariance(
    const char* replay_receipt,
    char* out_summary,
    DWORD out_len
) {
    if (!sp_has_prefix(replay_receipt, "sp-replay-")) {
        return SP_ERR_BADTOKEN;
    }
    return sp_copy_out(out_summary, out_len, "replay_variance=interesting|frontier=false_positive|decision_bearing=no");
}

SP_EXPORT int SP_CALL SP_SelectTrustedBranch(
    const char* confirmation_id,
    const char* replay_receipt,
    char* out_trusted_branch_id,
    DWORD trusted_len,
    char* out_rejected_branch_id,
    DWORD rejected_len
) {
    if (!sp_has_prefix(confirmation_id, "sp-confirm-") || !sp_has_prefix(replay_receipt, "sp-replay-")) {
        return SP_ERR_BADTOKEN;
    }
    if (!out_trusted_branch_id || trusted_len < 16 || !out_rejected_branch_id || rejected_len < 16) {
        return SP_ERR_BADPARAM;
    }
    if (sp_copy_out(out_trusted_branch_id, trusted_len, "sp-branch-primary") != SP_OK) {
        return SP_ERR_BADPARAM;
    }
    return sp_copy_out(out_rejected_branch_id, rejected_len, "sp-branch-replay");
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpReserved;
    return TRUE;
}
