#include <windows.h>

static int g_initialized = 0;

__declspec(dllexport) int S02B_PRE_T2_CommitBeforeInit(int amount_cents) {
    if (!g_initialized) {
        return -3;
    }
    return amount_cents > 0 ? 0 : -1;
}

__declspec(dllexport) int S02B_PRE_T2_InitSession(void) {
    g_initialized = 1;
    return 0;
}

__declspec(dllexport) int S02B_PRE_T2_CommitAfterInit(int amount_cents) {
    if (!g_initialized) {
        return -3;
    }
    return amount_cents > 0 ? 0 : -1;
}

__declspec(dllexport) int S02B_PRE_T2_ReadStatus(void) {
    return g_initialized ? 7 : -3;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)module;
    (void)reason;
    (void)reserved;
    return TRUE;
}
