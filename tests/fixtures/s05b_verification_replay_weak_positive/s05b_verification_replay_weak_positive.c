#include <windows.h>

__declspec(dllexport) int S05B_WP_VerifiedOk(void) {
    return 0;
}

__declspec(dllexport) int S05B_WP_InferredWouldPass(void) {
    return 0;
}

__declspec(dllexport) int S05B_WP_PartialWouldPass(void) {
    return 0;
}

__declspec(dllexport) int S05B_WP_FailedWouldPass(void) {
    return 0;
}

__declspec(dllexport) int S05B_WP_StateDrift(void) {
    return 0xFFFFFFFD;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)module;
    (void)reason;
    (void)reserved;
    return TRUE;
}
