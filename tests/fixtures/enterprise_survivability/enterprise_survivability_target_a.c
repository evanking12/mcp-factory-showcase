#include <windows.h>

__declspec(dllexport) int ES_TargetA_ComparableSuccess(void) {
    return 101;
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpvReserved;
    return TRUE;
}
