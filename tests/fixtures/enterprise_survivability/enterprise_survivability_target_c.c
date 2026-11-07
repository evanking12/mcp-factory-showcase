#include <windows.h>

__declspec(dllexport) int ES_TargetC_DependsOnB(void) {
    return 303;
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpvReserved;
    return TRUE;
}
