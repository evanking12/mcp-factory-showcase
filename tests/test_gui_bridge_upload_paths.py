import asyncio
import json
import subprocess
from pathlib import Path

import ctypes
from types import SimpleNamespace

from scripts.bridge.gui_bridge import (
    ExecuteRequest,
    _activate_runtime_dll_directory,
    _bridge_param_argtype,
    _copy_runtime_sibling_dlls,
    _execute_dll_bridge_isolated,
    _flush_dll_cache,
    _looks_like_bridge_output_buffer_param,
    _persistent_upload_path,
    _runtime_execution_copy_path,
    _summarize_execute_args,
    _write_execute_breadcrumb,
    execute,
)


def test_persistent_upload_path_changes_when_content_changes(tmp_path: Path) -> None:
    first = _persistent_upload_path(tmp_path, "contoso_payments.dll", b"first")
    second = _persistent_upload_path(tmp_path, "contoso_payments.dll", b"second")

    assert first != second
    assert first.name.startswith("contoso_payments-")
    assert second.name.startswith("contoso_payments-")
    assert first.suffix == ".dll"
    assert second.suffix == ".dll"


def test_persistent_upload_path_is_stable_for_same_content(tmp_path: Path) -> None:
    first = _persistent_upload_path(tmp_path, "contoso_payments.dll", b"same-bytes")
    second = _persistent_upload_path(tmp_path, "contoso_payments.dll", b"same-bytes")

    assert first == second


def test_runtime_execution_copy_path_changes_across_generations(tmp_path: Path) -> None:
    first = _runtime_execution_copy_path(tmp_path, r"C:\mcp-factory\uploads\contoso_payments-abcd.dll", 1)
    second = _runtime_execution_copy_path(tmp_path, r"C:\mcp-factory\uploads\contoso_payments-abcd.dll", 2)

    assert first != second
    assert first.name.endswith("-g1.dll")
    assert second.name.endswith("-g2.dll")


def test_runtime_execution_copy_path_is_stable_within_generation(tmp_path: Path) -> None:
    first = _runtime_execution_copy_path(tmp_path, r"C:\mcp-factory\uploads\contoso_payments-abcd.dll", 7)
    second = _runtime_execution_copy_path(tmp_path, r"C:\mcp-factory\uploads\contoso_payments-abcd.dll", 7)

    assert first == second


def test_copy_runtime_sibling_dlls_copies_neighbor_dependencies(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    runtime_dir = tmp_path / "runtime"
    source_dir.mkdir()
    runtime_dir.mkdir()

    source = source_dir / "contoso_cs_interwoven.dll"
    dep = source_dir / "contoso_cs.dll"
    other = source_dir / "notes.txt"
    source.write_bytes(b"source")
    dep.write_bytes(b"dep")
    other.write_text("ignore me", encoding="utf-8")

    copied = _copy_runtime_sibling_dlls(source, runtime_dir)

    assert runtime_dir.joinpath("contoso_cs.dll").read_bytes() == b"dep"
    assert not runtime_dir.joinpath("notes.txt").exists()
    assert [p.name for p in copied] == ["contoso_cs.dll"]


def test_activate_runtime_dll_directory_registers_generation_dir(monkeypatch, tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    calls: list[str] = []

    class _Handle:
        def __init__(self, label: str) -> None:
            self.label = label

        def close(self) -> None:
            calls.append(f"close:{self.label}")

    kernel32 = SimpleNamespace(
        SetDllDirectoryW=lambda path: calls.append(f"set:{path}") or 1,
        FreeLibrary=lambda _handle: 1,
    )
    monkeypatch.setattr("scripts.bridge.gui_bridge.ctypes.windll", SimpleNamespace(kernel32=kernel32), raising=False)
    monkeypatch.setattr("scripts.bridge.gui_bridge.os.add_dll_directory", lambda path: _Handle(path), raising=False)
    monkeypatch.setattr("scripts.bridge.gui_bridge._DLL_DIR_HANDLES", {}, raising=False)
    monkeypatch.setattr("scripts.bridge.gui_bridge._DLL_ACTIVE_RUNTIME_DIR", None, raising=False)

    _activate_runtime_dll_directory(runtime_dir)

    assert calls == [f"set:{runtime_dir}"]


def test_flush_dll_cache_resets_runtime_directory_handles(monkeypatch) -> None:
    calls: list[str] = []

    class _Handle:
        def close(self) -> None:
            calls.append("close")

    kernel32 = SimpleNamespace(
        SetDllDirectoryW=lambda path: calls.append(f"set:{path}") or 1,
        FreeLibrary=lambda _handle: 1,
    )
    monkeypatch.setattr("scripts.bridge.gui_bridge.ctypes.windll", SimpleNamespace(kernel32=kernel32), raising=False)
    monkeypatch.setattr("scripts.bridge.gui_bridge._DLL_CACHE", {}, raising=False)
    monkeypatch.setattr("scripts.bridge.gui_bridge._DLL_DIR_HANDLES", {"c:\\mcp-factory\\runtime-dlls\\g0": _Handle()}, raising=False)
    monkeypatch.setattr("scripts.bridge.gui_bridge._DLL_ACTIVE_RUNTIME_DIR", "c:\\mcp-factory\\runtime-dlls\\g0", raising=False)
    monkeypatch.setattr("scripts.bridge.gui_bridge._DLL_CACHE_GENERATION", 0, raising=False)

    _flush_dll_cache()

    assert calls == ["close", "set:None"]


def test_bridge_param_argtype_understands_win32_string_aliases() -> None:
    assert _bridge_param_argtype({"type": "typedef LPCSTR CHAR *", "resolved_type": "LPCSTR"}) is ctypes.c_char_p
    assert _bridge_param_argtype({"type": "typedef LPSTR CHAR *", "resolved_type": "LPSTR"}) is ctypes.c_char_p


def test_bridge_param_argtype_maps_scalar_output_pointers() -> None:
    argtype = _bridge_param_argtype({"type": "uint *", "resolved_type": "uint *"})
    assert getattr(argtype, "_type_", None) in (ctypes.c_uint, ctypes.c_ulong)


def test_bridge_param_argtype_maps_dword_output_pointers_consistently() -> None:
    argtype = _bridge_param_argtype({"type": "DWORD *", "resolved_type": "DWORD *"})
    assert getattr(argtype, "_type_", None) in (ctypes.c_uint, ctypes.c_ulong)


def test_bridge_param_argtype_maps_plain_dword_without_word_collision() -> None:
    assert _bridge_param_argtype({"type": "DWORD", "resolved_type": "DWORD"}) in (ctypes.c_uint, ctypes.c_ulong)


def test_bridge_param_argtype_maps_dword_pointer_without_word_collision() -> None:
    argtype = _bridge_param_argtype({"type": "DWORD*", "resolved_type": "DWORD*"})
    assert getattr(argtype, "_type_", None) in (ctypes.c_uint, ctypes.c_ulong)


def test_looks_like_bridge_output_buffer_param_detects_named_char_buffer_with_size() -> None:
    params = [
        {"name": "pOutBuf", "type": "char *"},
        {"name": "dwBufLen", "type": "DWORD"},
    ]

    assert _looks_like_bridge_output_buffer_param(params, 0) is True


def test_looks_like_bridge_output_buffer_param_does_not_flag_regular_input_string() -> None:
    params = [
        {"name": "lpszCustId", "type": "char *"},
        {"name": "dwNonce", "type": "DWORD"},
    ]

    assert _looks_like_bridge_output_buffer_param(params, 0) is False


def test_summarize_execute_args_truncates_and_tags_bytes() -> None:
    summary = _summarize_execute_args({
        "count": 7,
        "payload": b"abc",
        "long_text": "x" * 100,
    })

    assert summary["count"] == 7
    assert summary["payload"] == "<bytes:3>"
    assert summary["long_text"].endswith("...")
    assert len(summary["long_text"]) == 80


def test_write_execute_breadcrumb_appends_jsonl(monkeypatch, tmp_path: Path) -> None:
    breadcrumb_path = tmp_path / "bridge-execute-breadcrumbs.jsonl"
    monkeypatch.setattr("scripts.bridge.gui_bridge._BRIDGE_BREADCRUMB_PATH", breadcrumb_path, raising=False)

    _write_execute_breadcrumb({"event": "execute_enter", "tool": "CS_Init"})
    _write_execute_breadcrumb({"event": "native_call_enter", "tool": "CS_Init"})

    lines = breadcrumb_path.read_text(encoding="utf-8").strip().splitlines()

    assert len(lines) == 2
    assert '"event": "execute_enter"' in lines[0]
    assert '"event": "native_call_enter"' in lines[1]


def test_execute_dll_bridge_isolated_returns_worker_result(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def _fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        output_path = Path(cmd[3])
        output_path.write_text(
            json.dumps({"status": "ok", "result": "Returned: 7"}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("scripts.bridge.gui_bridge._DLL_EXECUTE_WORKER_PATH", tmp_path / "worker.py", raising=False)
    monkeypatch.setattr("scripts.bridge.gui_bridge.subprocess.run", _fake_run)

    result = _execute_dll_bridge_isolated(
        {"name": "SP_OpenOperatorSession", "_bridge_call_id": "call-1"},
        {"function_name": "SP_OpenOperatorSession", "method": "dll_import"},
        {"customer_id": "1042"},
    )

    assert result == "Returned: 7"
    assert calls
    assert calls[0][2].endswith("request.json")
    assert calls[0][3].endswith("response.json")


def test_execute_dll_bridge_isolated_reports_worker_crash_without_output(monkeypatch, tmp_path: Path) -> None:
    events: list[dict] = []

    def _fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, -1073741819, "", "")

    monkeypatch.setattr("scripts.bridge.gui_bridge._DLL_EXECUTE_WORKER_PATH", tmp_path / "worker.py", raising=False)
    monkeypatch.setattr("scripts.bridge.gui_bridge.subprocess.run", _fake_run)
    monkeypatch.setattr("scripts.bridge.gui_bridge._write_execute_breadcrumb", events.append)

    result = _execute_dll_bridge_isolated(
        {"name": "SP_OpenOperatorSession", "_bridge_call_id": "call-2"},
        {"function_name": "SP_OpenOperatorSession", "method": "dll_import"},
        {},
    )

    assert "crashed before returning a result" in result
    assert events[-1]["event"] == "native_call_error"
    assert events[-1]["error_class"] == "BridgeWorkerCrash"


def test_execute_route_uses_direct_dll_bridge(monkeypatch) -> None:
    calls: list[tuple[dict, dict, dict]] = []

    def _fake_direct(inv, execution, args):
        calls.append((inv, execution, args))
        return "Returned: 9"

    def _unexpected_isolated(*args, **kwargs):
        raise AssertionError("_execute_dll_bridge_isolated should not be called")

    monkeypatch.setattr("scripts.bridge.gui_bridge.BRIDGE_SECRET", "secret", raising=False)
    monkeypatch.setattr("scripts.bridge.gui_bridge._execute_dll_bridge", _fake_direct)
    monkeypatch.setattr("scripts.bridge.gui_bridge._execute_dll_bridge_isolated", _unexpected_isolated)

    response = asyncio.run(
        execute(
            ExecuteRequest(
                invocable={
                    "name": "SP_OpenOperatorSession",
                    "execution": {"method": "dll_import", "function_name": "SP_OpenOperatorSession"},
                },
                args={"customer_id": "1042"},
            ),
            x_bridge_key="secret",
        )
    )

    payload = json.loads(response.body.decode("utf-8"))
    assert payload["result"] == "Returned: 9"
    assert calls
