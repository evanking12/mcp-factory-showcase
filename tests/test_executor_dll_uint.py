import sys
import ctypes
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only ctypes DLL test")


def _redeem_invocable() -> dict:
    dll_path = str((ROOT / "tests" / "fixtures" / "contoso_legacy" / "contoso_cs.dll").resolve())
    return {
        "name": "CS_RedeemLoyaltyPoints",
        "return_type": "undefined8",
        "parameters": [
            {"name": "param_1", "type": "byte *", "direction": "in"},
            {"name": "param_2", "type": "uint", "direction": "in"},
            {"name": "param_3", "type": "uint *", "direction": "out"},
        ],
        "execution": {
            "method": "dll_import",
            "dll_path": dll_path,
            "function_name": "CS_RedeemLoyaltyPoints",
            "calling_convention": "fastcall",
        },
    }


def _process_purchase_invocable() -> dict:
    dll_path = str((ROOT / "tests" / "fixtures" / "contoso_legacy" / "contoso_payments.dll").resolve())
    return {
        "name": "CP_ProcessPurchase",
        "return_type": "undefined8",
        "parameters": [
            {"name": "param_1", "type": "typedef LPCSTR CHAR *", "direction": "in", "resolved_type": "LPCSTR"},
            {"name": "param_2", "type": "byte *", "direction": "in", "resolved_type": "byte *"},
            {"name": "param_3", "type": "ushort", "direction": "in", "resolved_type": "ushort"},
            {"name": "param_4", "type": "uint", "direction": "in", "resolved_type": "uint"},
            {"name": "param_5", "type": "uint *", "direction": "out", "resolved_type": "uint *"},
        ],
        "execution": {
            "method": "dll_import",
            "dll_path": dll_path,
            "function_name": "CP_ProcessPurchase",
            "calling_convention": "stdcall",
        },
    }


def _reserve_stock_invocable() -> dict:
    dll_path = str((ROOT / "tests" / "fixtures" / "contoso_legacy" / "contoso_payments.dll").resolve())
    return {
        "name": "CP_ReserveStock",
        "return_type": "undefined8",
        "parameters": [
            {"name": "customer_id", "type": "typedef LPCSTR CHAR *", "direction": "in", "resolved_type": "LPCSTR"},
            {"name": "acc_id", "type": "byte *", "direction": "in", "resolved_type": "byte *"},
            {"name": "param_3", "type": "ushort", "direction": "in", "resolved_type": "ushort"},
            {"name": "param_4", "type": "int", "direction": "in", "resolved_type": "int"},
            {"name": "param_5", "type": "typedef LPSTR CHAR *", "direction": "out", "resolved_type": "LPSTR"},
            {"name": "param_6", "type": "uint", "direction": "in", "resolved_type": "uint"},
        ],
        "execution": {
            "method": "dll_import",
            "dll_path": dll_path,
            "function_name": "CP_ReserveStock",
            "calling_convention": "stdcall",
        },
    }


def test_execute_dll_handles_uint_scalar_inputs():
    from api.services.executor import _execute_dll

    inv = _redeem_invocable()
    result, trace = _execute_dll(inv, inv["execution"], {"param_1": "CUST-001", "param_2": 1})

    assert "Returned: 0" in result
    assert "param_3=1" in result
    assert trace["raw_result"] == 0


def test_execute_dll_bridge_handles_uint_scalar_inputs():
    from scripts.bridge.gui_bridge import _execute_dll_bridge, _flush_dll_cache

    inv = _redeem_invocable()
    _flush_dll_cache()
    result = _execute_dll_bridge(inv, inv["execution"], {"param_1": "CUST-001", "param_2": 1})

    assert "Returned: 0" in result
    assert "param_3=1" in result


def test_execute_dll_bridge_handles_ushort_scalar_inputs():
    from scripts.bridge.gui_bridge import _execute_dll_bridge, _flush_dll_cache

    inv = _process_purchase_invocable()
    _flush_dll_cache()
    result = _execute_dll_bridge(
        inv,
        inv["execution"],
        {"param_1": "CUST-001", "param_2": "WDG-XL-BLU", "param_3": 1, "param_4": 0},
    )

    assert "Returned: 0" in result
    assert "param_5=" in result


def test_execute_dll_treats_blank_explicit_out_string_as_output_buffer():
    from api.services.executor import _execute_dll

    inv = _reserve_stock_invocable()
    result, trace = _execute_dll(
        inv,
        inv["execution"],
        {
            "customer_id": "CUST-001",
            "acc_id": "ACC-USB-C",
            "param_3": 1,
            "param_4": 1,
            "param_5": "",
            "param_6": 32,
        },
    )

    assert "Returned:" in result
    assert "param_5" in (trace.get("out_str_bufs") or [])


def test_execute_dll_bridge_treats_blank_explicit_out_string_as_output_buffer():
    from scripts.bridge.gui_bridge import _execute_dll_bridge, _flush_dll_cache

    inv = _reserve_stock_invocable()
    _flush_dll_cache()
    result = _execute_dll_bridge(
        inv,
        inv["execution"],
        {
            "customer_id": "CUST-001",
            "acc_id": "ACC-USB-C",
            "param_3": 1,
            "param_4": 1,
            "param_5": "",
            "param_6": 32,
        },
    )

    assert "Returned: 0" in result
    assert "RESV-" in result


def test_execute_dll_bridge_names_duplicate_output_buffers(monkeypatch):
    from scripts.bridge.gui_bridge import _execute_dll_bridge

    class _FakeFunction:
        def __init__(self) -> None:
            self.restype = None
            self.argtypes = None

        def __call__(self, session_handle, mode, hold_buf, hold_len, resv_buf, resv_len):
            hold_buf.value = b"sp-hold-CUST-001-0001"
            resv_buf.value = b"sp-resv-CUST-001-0001"
            return 0

    fake_fn = _FakeFunction()
    monkeypatch.setattr(
        "scripts.bridge.gui_bridge._get_cached_dll",
        lambda *_args, **_kwargs: type("L", (), {"SP_IssueReleaseHold": fake_fn})(),
    )

    inv = {
        "name": "SP_IssueReleaseHold",
        "return_type": "int",
        "parameters": [
            {"name": "session_handle", "type": "byte *", "direction": "in"},
            {"name": "mode", "type": "uint", "direction": "in"},
            {"name": "output_buffer", "type": "char *", "direction": "out"},
            {"name": "output_len", "type": "uint", "direction": "in"},
            {"name": "output_buffer", "type": "char *", "direction": "out"},
            {"name": "output_len", "type": "uint", "direction": "in"},
        ],
        "execution": {
            "method": "dll_import",
            "dll_path": str(ROOT / "tests" / "fixtures" / "contoso_legacy" / "contoso_cs.dll"),
            "function_name": "SP_IssueReleaseHold",
            "calling_convention": "fastcall",
        },
    }

    result = _execute_dll_bridge(
        inv,
        inv["execution"],
        {"session_handle": "WFH-CUST-001-02", "mode": 1, "output_len": 64},
    )

    assert "Returned: 0" in result
    assert "output_buffer='sp-hold-CUST-001-0001'" in result
    assert "output_buffer__2='sp-resv-CUST-001-0001'" in result


def test_executor_return_type_and_float_coercion_helpers():
    from api.services.executor import _coerce_scalar_for_ctype, _ctypes_restype_for_return

    assert _ctypes_restype_for_return("void *") is ctypes.c_void_p
    assert _ctypes_restype_for_return("HANDLE") is ctypes.c_void_p
    assert _coerce_scalar_for_ctype(ctypes.c_float, 1.25).value == pytest.approx(1.25)
    assert _coerce_scalar_for_ctype(ctypes.c_double, 2.5).value == pytest.approx(2.5)


def test_bridge_return_type_and_float_coercion_helpers():
    from scripts.bridge.gui_bridge import _bridge_coerce_scalar_value, _bridge_restype_for_return

    assert _bridge_restype_for_return("void *") is ctypes.c_void_p
    assert _bridge_restype_for_return("HANDLE") is ctypes.c_void_p
    assert float(_bridge_coerce_scalar_value(ctypes.c_float, 1.25)) == pytest.approx(1.25)
    assert float(_bridge_coerce_scalar_value(ctypes.c_double, 2.5)) == pytest.approx(2.5)


def test_execute_dll_accepts_float_pointer_payload_lists(monkeypatch):
    from api.services.executor import _execute_dll

    class _FakeFunction:
        def __init__(self) -> None:
            self.restype = None
            self.argtypes = None
            self.payload = None

        def __call__(self, payload, count):
            self.payload = payload
            assert count.value == 4
            assert float(payload[1]) == pytest.approx(0.25)
            return 0

    fake_fn = _FakeFunction()
    monkeypatch.setattr("api.services.executor.ctypes.CDLL", lambda _path: type("L", (), {"soundtouch_putSamples": fake_fn})())

    inv = {
        "name": "soundtouch_putSamples",
        "return_type": "int",
        "parameters": [
            {"name": "param_1", "type": "float *", "direction": "in"},
            {"name": "param_2", "type": "uint", "direction": "in"},
        ],
        "execution": {
            "method": "dll_import",
            "dll_path": str(ROOT / "tests" / "fixtures" / "contoso_legacy" / "contoso_cs.dll"),
            "function_name": "soundtouch_putSamples",
            "calling_convention": "fastcall",
        },
    }

    result, _trace = _execute_dll(inv, inv["execution"], {"param_1": [0.0, 0.25, -0.25, 0.5], "param_2": 4})

    assert "Returned: 0" in result
    assert fake_fn.argtypes[0]._type_ is ctypes.c_float


def test_execute_dll_bridge_accepts_float_pointer_payload_lists(monkeypatch):
    from scripts.bridge.gui_bridge import _execute_dll_bridge

    class _FakeFunction:
        def __init__(self) -> None:
            self.restype = None
            self.argtypes = None

        def __call__(self, payload, count):
            assert getattr(count, "value", count) == 4
            assert float(payload[2]) == pytest.approx(-0.25)
            return 0

    fake_fn = _FakeFunction()
    monkeypatch.setattr("scripts.bridge.gui_bridge._get_cached_dll", lambda *_args, **_kwargs: type("L", (), {"soundtouch_putSamples": fake_fn})())

    inv = {
        "name": "soundtouch_putSamples",
        "return_type": "int",
        "parameters": [
            {"name": "param_1", "type": "float *", "resolved_type": "float *", "direction": "in"},
            {"name": "param_2", "type": "uint", "resolved_type": "uint", "direction": "in"},
        ],
        "execution": {
            "method": "dll_import",
            "dll_path": str(ROOT / "tests" / "fixtures" / "contoso_legacy" / "contoso_cs.dll"),
            "function_name": "soundtouch_putSamples",
            "calling_convention": "fastcall",
        },
    }

    result = _execute_dll_bridge(inv, inv["execution"], {"param_1": [0.0, 0.25, -0.25, 0.5], "param_2": 4})

    assert "Returned: 0" in result
    assert fake_fn.argtypes[0]._type_ is ctypes.c_float
