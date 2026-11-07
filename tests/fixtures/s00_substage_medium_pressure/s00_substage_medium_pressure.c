#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define S00M_EXPORT __declspec(dllexport)
#define S00M_CALL __cdecl
#define S00M_OK 0
#define S00M_BADPARAM -8201

static const char* MEDIUM_IDS[] = {
    "MEDACC-ACCOUNT-001",
    "MEDACC-ACCOUNT-002",
    "MEDLED-LEDGER-003",
    "MEDLED-LEDGER-004",
    "MEDORD-ORDER-005",
    "MEDORD-ORDER-006",
    "MEDTEN-TENANT-007",
    "MEDTEN-TENANT-008",
    "MEDINV-INVOICE-009",
    "MEDINV-INVOICE-010",
    "MEDBAT-BATCH-011",
    "MEDBAT-BATCH-012",
    "MEDUSR-USER-013",
    "MEDUSR-USER-014",
    "MEDAUD-AUDIT-015",
    "MEDAUD-AUDIT-016",
    "MEDREF-REFUND-017",
    "MEDREF-REFUND-018",
    "MEDRTE-ROUTE-019",
    "MEDRTE-ROUTE-020",
    "MEDCAP-CAP-021",
    "MEDCAP-CAP-022",
    "MEDDEF-DEFER-023",
    "MEDDEF-DEFER-024",
    "MEDAMB-AMBIG-025",
    "MEDAMB-AMBIG-026",
    "MEDXRF-XREF-027",
    "MEDXRF-XREF-028",
    "MEDSPL-SPLIT-029",
    "MEDSPL-SPLIT-030",
    "MEDNSE-NOISE-031",
    "MEDNSE-NOISE-032"
};

static const char* MEDIUM_EMAILS[] = {
    "ops.medium@example.com",
    "audit.medium@example.com",
    "handoff.medium@example.com",
    "owner.medium@example.com"
};

static const char* MEDIUM_STATUS[] = {
    "PENDING",
    "ACTIVE",
    "LOCKED",
    "COMPLETE",
    "UNKNOWN",
    "OPEN",
    "CLOSED",
    "ENABLED",
    "DISABLED"
};

static const char* MEDIUM_FORMATS[] = {
    "medium account %s opened with status %s",
    "medium ledger %s committed with receipt %s",
    "medium target %s deferred for review %s",
    "medium ambiguity %s preserved by packet %s",
    "medium audit %s routed to owner %s"
};

static int s00m_copy_out(char* out_buf, unsigned long out_len, const char* text) {
    if (!out_buf || out_len == 0) {
        return S00M_BADPARAM;
    }
    if (!text) {
        text = "";
    }
    _snprintf(out_buf, out_len - 1, "%s", text);
    out_buf[out_len - 1] = '\0';
    return S00M_OK;
}

static int s00m_emit_token(const char* prefix, const char* value, char* out_buf, unsigned long out_len) {
    char token[192];
    const char* safe_value = (value && *value) ? value : MEDIUM_IDS[0];
    _snprintf(token, sizeof(token) - 1, "%s-%s", prefix, safe_value);
    token[sizeof(token) - 1] = '\0';
    return s00m_copy_out(out_buf, out_len, token);
}

#define DEFINE_INIT_FN(fn_name, prefix_text) \
    S00M_EXPORT int S00M_CALL fn_name(const char* account_id, char* out_token, unsigned long out_len) { \
        return s00m_emit_token(prefix_text, account_id, out_token, out_len); \
    }

#define DEFINE_WRITE_FN(fn_name, prefix_text) \
    S00M_EXPORT int S00M_CALL fn_name(const char* session_token, const char* account_id, char* out_receipt, unsigned long out_len) { \
        if (!session_token || !*session_token) { \
            return S00M_BADPARAM; \
        } \
        return s00m_emit_token(prefix_text, account_id, out_receipt, out_len); \
    }

#define DEFINE_READ_FN(fn_name, prefix_text) \
    S00M_EXPORT int S00M_CALL fn_name(const char* account_id, char* out_value, unsigned long out_len) { \
        return s00m_emit_token(prefix_text, account_id, out_value, out_len); \
    }

DEFINE_INIT_FN(S00M_InitTenantSession01, "init-tenant-01")
DEFINE_INIT_FN(S00M_InitializeAccountWindow02, "init-account-02")
DEFINE_INIT_FN(S00M_OpenLedgerBridge03, "init-ledger-03")
DEFINE_INIT_FN(S00M_ConnectOperatorLane04, "init-operator-04")
DEFINE_INIT_FN(S00M_LoginBatchWorkspace05, "init-batch-05")
DEFINE_INIT_FN(S00M_AuthorizeMediumAccount06, "init-authorize-06")
DEFINE_INIT_FN(S00M_StartSettlementSession07, "init-settlement-07")
DEFINE_INIT_FN(S00M_UnlockMediumWorkspace08, "init-unlock-08")
DEFINE_INIT_FN(S00M_OpenReviewBatch09, "init-review-09")
DEFINE_INIT_FN(S00M_ConnectAuditContext10, "init-audit-10")
DEFINE_INIT_FN(S00M_SetupDeferredLedger11, "init-deferred-11")
DEFINE_INIT_FN(S00M_StartAmbiguityReview12, "init-ambiguity-12")
DEFINE_INIT_FN(S00M_OpenNoiseControlledContext13, "init-noise-13")
DEFINE_INIT_FN(S00M_InitializeMediumRoute14, "init-route-14")
DEFINE_INIT_FN(S00M_LoginMediumOperator15, "init-login-15")
DEFINE_INIT_FN(S00M_AuthorizeMediumBatch16, "init-batch-16")
DEFINE_INIT_FN(S00M_StartMediumCatalog17, "init-catalog-17")
DEFINE_INIT_FN(S00M_OpenMediumFallback18, "init-fallback-18")

DEFINE_WRITE_FN(S00M_ProcessMediumPayment01, "write-payment-01")
DEFINE_WRITE_FN(S00M_WriteMediumLedger02, "write-ledger-02")
DEFINE_WRITE_FN(S00M_CommitMediumLedger03, "write-commit-03")
DEFINE_WRITE_FN(S00M_UpdateMediumAccount04, "write-update-04")
DEFINE_WRITE_FN(S00M_SetMediumStatus05, "write-status-05")
DEFINE_WRITE_FN(S00M_CreateMediumRecord06, "write-create-06")
DEFINE_WRITE_FN(S00M_DeleteMediumDraft07, "write-delete-07")
DEFINE_WRITE_FN(S00M_TransferMediumCredit08, "write-transfer-08")
DEFINE_WRITE_FN(S00M_DebitMediumBalance09, "write-debit-09")
DEFINE_WRITE_FN(S00M_CreditMediumBalance10, "write-credit-10")
DEFINE_WRITE_FN(S00M_PayMediumInvoice11, "write-invoice-11")
DEFINE_WRITE_FN(S00M_RedeemMediumCredit12, "write-redeem-12")
DEFINE_WRITE_FN(S00M_ProcessMediumAdjustment13, "write-adjust-13")
DEFINE_WRITE_FN(S00M_WriteMediumAudit14, "write-audit-14")
DEFINE_WRITE_FN(S00M_CommitMediumAudit15, "write-audit-15")
DEFINE_WRITE_FN(S00M_UpdateDeferredTarget16, "write-deferred-16")
DEFINE_WRITE_FN(S00M_SetAmbiguousTarget17, "write-ambiguous-17")
DEFINE_WRITE_FN(S00M_CreateNoisyCandidate18, "write-noisy-18")
DEFINE_WRITE_FN(S00M_ProcessFallbackRecord19, "write-fallback-19")
DEFINE_WRITE_FN(S00M_WriteReviewOutcome20, "write-review-20")
DEFINE_WRITE_FN(S00M_CommitReviewOutcome21, "write-review-21")
DEFINE_WRITE_FN(S00M_TransferReviewCredit22, "write-review-22")
DEFINE_WRITE_FN(S00M_UpdateAuditRoute23, "write-route-23")
DEFINE_WRITE_FN(S00M_SetAuditStatus24, "write-status-24")
DEFINE_WRITE_FN(S00M_CreateAuditRecord25, "write-audit-25")
DEFINE_WRITE_FN(S00M_DeleteAuditDraft26, "write-audit-26")

DEFINE_READ_FN(S00M_QueryMediumVersion01, "read-version-01")
DEFINE_READ_FN(S00M_CheckMediumStatus02, "read-status-02")
DEFINE_READ_FN(S00M_ListMediumFamilies03, "read-family-03")
DEFINE_READ_FN(S00M_GetMediumCatalog04, "read-catalog-04")
DEFINE_READ_FN(S00M_ReadMediumAudit05, "read-audit-05")
DEFINE_READ_FN(S00M_VerifyMediumRoute06, "read-route-06")
DEFINE_READ_FN(S00M_ValidateMediumAccount07, "read-account-07")
DEFINE_READ_FN(S00M_LookupMediumTarget08, "read-target-08")
DEFINE_READ_FN(S00M_CountMediumCandidates09, "read-count-09")
DEFINE_READ_FN(S00M_FetchMediumDeferred10, "read-deferred-10")
DEFINE_READ_FN(S00M_CalculateMediumPreview11, "distractor-preview-11")
DEFINE_READ_FN(S00M_MirrorMediumNoise12, "distractor-noise-12")
DEFINE_READ_FN(S00M_FormatMediumReceipt13, "distractor-format-13")
DEFINE_READ_FN(S00M_RenderMediumTemplate14, "distractor-template-14")
DEFINE_READ_FN(S00M_ArchiveMediumSnapshot15, "distractor-archive-15")
DEFINE_READ_FN(S00M_DescribeMediumFamily16, "distractor-describe-16")

S00M_EXPORT int S00M_CALL S00M_GetMediumFixtureCatalogCount(void) {
    return (int)(
        (sizeof(MEDIUM_IDS) / sizeof(MEDIUM_IDS[0])) +
        (sizeof(MEDIUM_EMAILS) / sizeof(MEDIUM_EMAILS[0])) +
        (sizeof(MEDIUM_STATUS) / sizeof(MEDIUM_STATUS[0])) +
        (sizeof(MEDIUM_FORMATS) / sizeof(MEDIUM_FORMATS[0]))
    );
}

S00M_EXPORT int S00M_CALL S00M_GetMediumFixtureString(int bucket, int index, char* out_value, unsigned long out_len) {
    if (bucket == 0) {
        return s00m_copy_out(out_value, out_len, MEDIUM_IDS[index % (sizeof(MEDIUM_IDS) / sizeof(MEDIUM_IDS[0]))]);
    }
    if (bucket == 1) {
        return s00m_copy_out(out_value, out_len, MEDIUM_EMAILS[index % (sizeof(MEDIUM_EMAILS) / sizeof(MEDIUM_EMAILS[0]))]);
    }
    if (bucket == 2) {
        return s00m_copy_out(out_value, out_len, MEDIUM_STATUS[index % (sizeof(MEDIUM_STATUS) / sizeof(MEDIUM_STATUS[0]))]);
    }
    return s00m_copy_out(out_value, out_len, MEDIUM_FORMATS[index % (sizeof(MEDIUM_FORMATS) / sizeof(MEDIUM_FORMATS[0]))]);
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpReserved;
    return TRUE;
}

