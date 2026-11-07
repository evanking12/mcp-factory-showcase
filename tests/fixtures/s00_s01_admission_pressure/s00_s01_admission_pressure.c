#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define S00P_EXPORT __declspec(dllexport)
#define S00P_CALL __cdecl
#define S00P_OK 0
#define S00P_BADPARAM -8101

static const char* PRESSURE_IDS[] = {
    "PRESS-ACCOUNT-001",
    "PRESS-ACCOUNT-002",
    "PRESS-ORDER-010",
    "PRESS-ORDER-011",
    "PRESS-LEDGER-020",
    "PRESS-TENANT-030"
};

static const char* PRESSURE_STATUS[] = {
    "PENDING",
    "ACTIVE",
    "LOCKED",
    "COMPLETE",
    "UNKNOWN"
};

static const char* PRESSURE_FORMATS[] = {
    "pressure account %s opened",
    "pressure ledger %s committed",
    "pressure target %s deferred"
};

static int s00p_copy_out(char* out_buf, unsigned long out_len, const char* text) {
    if (!out_buf || out_len == 0) {
        return S00P_BADPARAM;
    }
    if (!text) {
        text = "";
    }
    _snprintf(out_buf, out_len - 1, "%s", text);
    out_buf[out_len - 1] = '\0';
    return S00P_OK;
}

static int s00p_emit_token(const char* prefix, const char* value, char* out_buf, unsigned long out_len) {
    char token[128];
    const char* safe_value = (value && *value) ? value : PRESSURE_IDS[0];
    _snprintf(token, sizeof(token) - 1, "%s-%s", prefix, safe_value);
    token[sizeof(token) - 1] = '\0';
    return s00p_copy_out(out_buf, out_len, token);
}

#define DEFINE_INIT_FN(fn_name, prefix_text) \
    S00P_EXPORT int S00P_CALL fn_name(const char* account_id, char* out_token, unsigned long out_len) { \
        return s00p_emit_token(prefix_text, account_id, out_token, out_len); \
    }

#define DEFINE_WRITE_FN(fn_name, prefix_text) \
    S00P_EXPORT int S00P_CALL fn_name(const char* session_token, const char* account_id, char* out_receipt, unsigned long out_len) { \
        if (!session_token || !*session_token) { \
            return S00P_BADPARAM; \
        } \
        return s00p_emit_token(prefix_text, account_id, out_receipt, out_len); \
    }

#define DEFINE_READ_FN(fn_name, prefix_text) \
    S00P_EXPORT int S00P_CALL fn_name(const char* account_id, char* out_value, unsigned long out_len) { \
        return s00p_emit_token(prefix_text, account_id, out_value, out_len); \
    }

DEFINE_READ_FN(S00P_QueryPressureVersion, "version")
DEFINE_READ_FN(S00P_CheckPressureStatus, "status")
DEFINE_READ_FN(S00P_ListPressureFamilies, "families")
DEFINE_READ_FN(S00P_GetPressureCatalog, "catalog")

DEFINE_INIT_FN(S00P_InitAccountSession01, "init-01")
DEFINE_INIT_FN(S00P_InitAccountSession02, "init-02")
DEFINE_INIT_FN(S00P_InitializeLedgerWindow03, "init-03")
DEFINE_INIT_FN(S00P_OpenTenantBridge04, "init-04")
DEFINE_INIT_FN(S00P_ConnectPressureLane05, "init-05")
DEFINE_INIT_FN(S00P_LoginPressureOperator06, "init-06")
DEFINE_INIT_FN(S00P_AuthorizePressureAccount07, "init-07")
DEFINE_INIT_FN(S00P_StartPressureSession08, "init-08")
DEFINE_INIT_FN(S00P_UnlockPressureWorkspace09, "init-09")
DEFINE_INIT_FN(S00P_OpenPressureBatch10, "init-10")
DEFINE_INIT_FN(S00P_ConnectPressureBatch11, "init-11")
DEFINE_INIT_FN(S00P_InitializePressureBatch12, "init-12")
DEFINE_INIT_FN(S00P_StartPressureBatch13, "init-13")
DEFINE_INIT_FN(S00P_AuthorizePressureBatch14, "init-14")
DEFINE_INIT_FN(S00P_LoginPressureBatch15, "init-15")

DEFINE_WRITE_FN(S00P_ProcessPressurePayment01, "write-01")
DEFINE_WRITE_FN(S00P_WritePressureLedger02, "write-02")
DEFINE_WRITE_FN(S00P_CommitPressureLedger03, "write-03")
DEFINE_WRITE_FN(S00P_UpdatePressureAccount04, "write-04")
DEFINE_WRITE_FN(S00P_SetPressureStatus05, "write-05")
DEFINE_WRITE_FN(S00P_CreatePressureRecord06, "write-06")
DEFINE_WRITE_FN(S00P_DeletePressureDraft07, "write-07")
DEFINE_WRITE_FN(S00P_TransferPressureCredit08, "write-08")
DEFINE_WRITE_FN(S00P_DebitPressureBalance09, "write-09")
DEFINE_WRITE_FN(S00P_CreditPressureBalance10, "write-10")
DEFINE_WRITE_FN(S00P_PayPressureInvoice11, "write-11")
DEFINE_WRITE_FN(S00P_RedeemPressureCredit12, "write-12")
DEFINE_WRITE_FN(S00P_ProcessPressureAdjustment13, "write-13")
DEFINE_WRITE_FN(S00P_WritePressureAudit14, "write-14")
DEFINE_WRITE_FN(S00P_CommitPressureAudit15, "write-15")

S00P_EXPORT int S00P_CALL S00P_GetPressureCatalogCount(void) {
    return (int)(
        (sizeof(PRESSURE_IDS) / sizeof(PRESSURE_IDS[0])) +
        (sizeof(PRESSURE_STATUS) / sizeof(PRESSURE_STATUS[0])) +
        (sizeof(PRESSURE_FORMATS) / sizeof(PRESSURE_FORMATS[0]))
    );
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpReserved;
    return TRUE;
}

