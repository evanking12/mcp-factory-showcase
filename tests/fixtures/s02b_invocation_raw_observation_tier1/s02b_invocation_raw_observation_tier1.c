#include <windows.h>

static int g_counter = 0;

__declspec(dllexport) int S02B_StatusOk(void) {
    return 0;
}

__declspec(dllexport) int S02B_StatusBlocked(void) {
    return -5;
}

__declspec(dllexport) int S02B_StateCounter(void) {
    g_counter += 1;
    return g_counter;
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpvReserved;
    return TRUE;
}

