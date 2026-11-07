#include <windows.h>

__declspec(dllexport) int S02A_T2_InitSession(void) {
    return 10;
}

__declspec(dllexport) int S02A_T2_GetVersion(void) {
    return 202;
}

__declspec(dllexport) int S02A_T2_ListReservationCandidates(void) {
    return 3;
}

__declspec(dllexport) int S02A_T2_QueryReservationCatalog(void) {
    return 4;
}

__declspec(dllexport) int S02A_T2_CalculateReservationQuote(int reservation_id) {
    return reservation_id + 20;
}

__declspec(dllexport) int S02A_T2_FormatReservationPreview(int reservation_id) {
    return reservation_id + 30;
}

__declspec(dllexport) int S02A_T2_WriteReservationUpdate(int reservation_id, int status_code) {
    return reservation_id + status_code;
}

__declspec(dllexport) int S02A_T2_CommitReservation(int reservation_id) {
    return reservation_id + 40;
}

__declspec(dllexport) int S02A_T2_UpdateReservationNote(int reservation_id, int note_code) {
    return reservation_id + note_code + 50;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)module;
    (void)reason;
    (void)reserved;
    return TRUE;
}

