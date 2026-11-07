import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "discovery"))

from ghidra_analyzer import _ghidra_param_direction, _prioritize_ghidra_data_types


def test_ghidra_param_direction_keeps_lpcstr_inputs():
    assert _ghidra_param_direction("typedef LPCSTR CHAR *", "LPCSTR") == "in"


def test_ghidra_param_direction_keeps_byte_star_inputs():
    assert _ghidra_param_direction("byte *", "byte *") == "in"


def test_ghidra_param_direction_preserves_lpstr_output_buffers():
    assert _ghidra_param_direction("typedef LPSTR CHAR *", "LPSTR") == "out"


def test_ghidra_param_direction_keeps_scalar_output_pointers():
    assert _ghidra_param_direction("uint *", "uint *") == "out"
    assert _ghidra_param_direction("undefined *", "") == "out"


def test_prioritize_ghidra_data_types_keeps_referenced_structs_first():
    functions = [
        {
            "name": "TP_OpenSession",
            "parameters": [
                {"name": "pReq", "type": "TP_OPEN_REQ *", "resolved_type": "TP_OPEN_REQ*"},
                {"name": "pdwHandleOut", "type": "DWORD *", "resolved_type": "DWORD*"},
            ],
            "return_type": "undefined8",
        },
        {
            "name": "TP_ReadSessionState",
            "parameters": [
                {"name": "dwSessionHandle", "type": "DWORD", "resolved_type": "DWORD"},
                {"name": "pOutState", "type": "TP_SESSION_STATE *", "resolved_type": "TP_SESSION_STATE*"},
            ],
            "return_type": "undefined8",
        },
    ]
    data_types = [
        {"kind": "struct", "name": "IMAGE_DOS_HEADER", "fields": [{"name": "e_magic", "type": "char[2]"}]},
        {"kind": "struct", "name": "TP_OPEN_REQ", "fields": [{"name": "szCustId", "type": "char[16]"}]},
        {"kind": "struct", "name": "IMAGE_FILE_HEADER", "fields": [{"name": "Machine", "type": "word"}]},
        {"kind": "struct", "name": "TP_SESSION_STATE", "fields": [{"name": "dwNonce", "type": "dword"}]},
    ]

    prioritized = _prioritize_ghidra_data_types(functions, data_types, max_items=4)

    assert [row["name"] for row in prioritized[:2]] == ["TP_OPEN_REQ", "TP_SESSION_STATE"]


def test_prioritize_ghidra_data_types_truncates_after_prioritized_types():
    functions = [
        {
            "name": "TP_SubmitPacket",
            "parameters": [
                {"name": "pReq", "type": "TP_PACKET_REQ *", "resolved_type": "TP_PACKET_REQ*"},
            ],
            "return_type": "undefined8",
        }
    ]
    data_types = [
        {"kind": "struct", "name": "IMAGE_DOS_HEADER", "fields": [{"name": "e_magic", "type": "char[2]"}]},
        {"kind": "struct", "name": "TP_PACKET_REQ", "fields": [{"name": "dwSessionHandle", "type": "dword"}]},
        {"kind": "struct", "name": "IMAGE_FILE_HEADER", "fields": [{"name": "Machine", "type": "word"}]},
        {"kind": "typedef", "name": "DWORD", "base_type": "uint"},
    ]

    prioritized = _prioritize_ghidra_data_types(functions, data_types, max_items=2)

    assert [row["name"] for row in prioritized] == ["TP_PACKET_REQ", "IMAGE_DOS_HEADER"]
