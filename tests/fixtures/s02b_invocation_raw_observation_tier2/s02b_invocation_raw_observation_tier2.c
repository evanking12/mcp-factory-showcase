#include <windows.h>

__declspec(dllexport) int S02B_T2_StatusOk(void) {
    return 0;
}

__declspec(dllexport) int S02B_T2_StatusBlocked(void) {
    return -5;
}

__declspec(dllexport) int S02B_T2_StatusWarning(void) {
    return 7;
}

__declspec(dllexport) int S02B_T2_StateCounter(void) {
    static int counter = 0;
    counter += 1;
    return counter;
}

__declspec(dllexport) int S02B_T2_EchoInt(int value) {
    return value + 100;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)module;
    (void)reason;
    (void)reserved;
    return TRUE;
}
