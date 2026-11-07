#include <windows.h>

__declspec(dllexport) int S05B_T1_ReplayOk(void) {
    return 0;
}

__declspec(dllexport) int S05B_T2_ReplayOk(void) {
    return 0;
}

__declspec(dllexport) int S05B_T2_StateDrift(void) {
    return 0xFFFFFFFD;
}

__declspec(dllexport) int S05B_T2_EchoInt(int value) {
    return value + 10;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)module;
    (void)reason;
    (void)reserved;
    return TRUE;
}
