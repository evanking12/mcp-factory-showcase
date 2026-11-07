#include <windows.h>
#include <strsafe.h>

static int g_state_value = 0;

__declspec(dllexport) int S05BASE_ReplayOk(void) {
    return 0;
}

__declspec(dllexport) int S05BASE_StateDrift(void) {
    return 0xFFFFFFFD;
}

__declspec(dllexport) int S05BASE_EchoInt(int value) {
    return value == 42 ? 0 : 0xFFFFFFFB;
}

__declspec(dllexport) int S05BU_ReadCustomer(char *out_customer_id, unsigned int out_customer_id_size) {
    if (out_customer_id == NULL || out_customer_id_size < 9) {
        return 0xFFFFFFFC;
    }
    StringCchCopyA(out_customer_id, out_customer_id_size, "CUST-300");
    return 0;
}

__declspec(dllexport) int S05FAM_create(void) {
    g_state_value = 0;
    return 1;
}

__declspec(dllexport) int S05FAM_write(int handle, int value) {
    if (handle != 1) {
        return 0xFFFFFFFD;
    }
    g_state_value = value;
    return 77;
}

__declspec(dllexport) int S05FAM_read(int handle) {
    if (handle != 1) {
        return 0xFFFFFFFD;
    }
    return g_state_value;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)module;
    (void)reason;
    (void)reserved;
    return TRUE;
}
