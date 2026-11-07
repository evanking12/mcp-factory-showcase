#include <windows.h>

__declspec(dllexport) int S02B_ARG_T2_Quantity(int quantity) {
    return quantity;
}

__declspec(dllexport) int S02B_ARG_T2_AmountCents(int amount_cents) {
    return amount_cents;
}

__declspec(dllexport) int S02B_ARG_T2_ModeFlag(int mode_flag) {
    return mode_flag;
}

__declspec(dllexport) int S02B_ARG_T2_QuantityAmount(int quantity, int amount_cents) {
    return (quantity * 10000) + amount_cents;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)module;
    (void)reason;
    (void)reserved;
    return TRUE;
}

