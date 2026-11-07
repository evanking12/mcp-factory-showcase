#include <windows.h>

__declspec(dllexport) int ES_TargetB_NonComparableSource(void) {
    return -404;
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpvReserved;
    return TRUE;
}
