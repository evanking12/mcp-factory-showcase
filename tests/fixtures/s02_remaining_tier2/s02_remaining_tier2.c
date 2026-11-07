#include <windows.h>

static int g_state_counter = 0;

__declspec(dllexport) int S02_REM_T2_InitUnlockedSession(void) {
    g_state_counter = 0;
    return 0;
}

__declspec(dllexport) int S02_REM_T2_ReadUnlockedCatalog(void) {
    return 2;
}

__declspec(dllexport) int S02_REM_T2_WriteUnlockedCommit(int amount_cents) {
    if (amount_cents <= 0) {
        return -5;
    }
    return 0;
}

__declspec(dllexport) int S02_REM_T2_PrereqBindCustomer(int customer_id) {
    if (customer_id <= 0) {
        return -3;
    }
    return customer_id + 10;
}

__declspec(dllexport) int S02_REM_T2_PrereqOpenWindow(int customer_id) {
    if (customer_id <= 0) {
        return -3;
    }
    return customer_id + 20;
}

__declspec(dllexport) int S02_REM_T2_PrereqFalseFriend(void) {
    return 77;
}

__declspec(dllexport) int S02_REM_T2_StateIncrement(void) {
    g_state_counter += 1;
    return g_state_counter;
}

__declspec(dllexport) int S02_REM_T2_StateRead(void) {
    return g_state_counter;
}

__declspec(dllexport) int S02_REM_T2_DangerousUnsupportedCommit(int amount_cents) {
    (void)amount_cents;
    return -9;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)module;
    (void)reason;
    (void)reserved;
    return TRUE;
}
