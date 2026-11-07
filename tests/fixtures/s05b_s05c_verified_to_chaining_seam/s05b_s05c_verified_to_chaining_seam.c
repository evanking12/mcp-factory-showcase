#include <windows.h>
#include <strsafe.h>

__declspec(dllexport) int S05_SEAM_ReadVerifiedCustomer(char *out_customer_id, unsigned int out_customer_id_size) {
    if (out_customer_id == NULL || out_customer_id_size < 9) {
        return 0xFFFFFFFC;
    }
    StringCchCopyA(out_customer_id, out_customer_id_size, "CUST-100");
    return 0;
}

__declspec(dllexport) int S05_SEAM_ReadInferredWouldPass(void) {
    return 0;
}

__declspec(dllexport) int S05_SEAM_ReadPartialWouldPass(void) {
    return 0;
}

__declspec(dllexport) int S05_SEAM_ReadFailedWouldPass(void) {
    return 0;
}

__declspec(dllexport) int S05_SEAM_ReadStateDrift(void) {
    return 0xFFFFFFFD;
}

__declspec(dllexport) int S05_SEAM_WriteCustomer(const char *customer_id) {
    if (customer_id == NULL) {
        return 0xFFFFFFFC;
    }
    return lstrcmpA(customer_id, "CUST-100") == 0 ? 0 : 0xFFFFFFFB;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)module;
    (void)reason;
    (void)reserved;
    return TRUE;
}
