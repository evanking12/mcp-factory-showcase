from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from api.infra import storage
from api.pipeline.core.types import ExploreContext, ExploreRuntime
from api.pipeline.s02_probe import curriculum
from api.pipeline.s02_probe import invocation_execution
from api.pipeline.s02_probe import probe_loop
from api.pipeline.s02_probe import probe_ordering
from api.services import executor


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s02a_probe_ordering_tier2"
BUILD_SCRIPT = FIXTURE_ROOT / "build.ps1"


def _has_msvc_toolchain() -> bool:
    if sys.platform != "win32":
        return False
    script = (
        "$vswhere = Join-Path ${env:ProgramFiles(x86)} "
        "'Microsoft Visual Studio\\Installer\\vswhere.exe'; "
        "$install = ''; "
        "if (Test-Path $vswhere) { "
        "$install = & $vswhere -latest -products * "
        "-requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 "
        "-property installationPath 2>$null "
        "}; "
        "$cl = Get-Command cl.exe -ErrorAction SilentlyContinue; "
        "if ($install -or $cl) { exit 0 } else { exit 1 }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


@pytest.fixture(scope="module")
def seam_tier2_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not _has_msvc_toolchain():
        pytest.skip("MSVC toolchain not available")
    output_root = tmp_path_factory.mktemp("s02a-s02b-seam-tier2")
    completed = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD_SCRIPT),
            "-OutputRoot",
            str(output_root),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    dll_path = output_root / "bin" / "s02a_probe_ordering_tier2.dll"
    assert dll_path.exists(), completed.stdout + completed.stderr
    return dll_path


def _param(name: str, description: str = "") -> dict[str, object]:
    return {
        "name": name,
        "type": "int",
        "json_type": "integer",
        "description": description or name.replace("_", " "),
        "direction": "in",
    }


def _invocable(
    name: str,
    dll_path: Path,
    *,
    parameters: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "return_type": "int",
        "parameters": parameters or [],
        "execution": {
            "method": "dll_import",
            "dll_path": str(dll_path),
            "function_name": name,
        },
    }


def _ctx_for_seam(dll_path: Path) -> ExploreContext:
    invocables = [
        _invocable(
            "S02A_T2_WriteReservationUpdate",
            dll_path,
            parameters=[_param("reservation_id"), _param("status_code")],
        ),
        _invocable(
            "S02A_T2_CommitReservation",
            dll_path,
            parameters=[_param("reservation_id")],
        ),
        _invocable("S02A_T2_QueryReservationCatalog", dll_path),
        _invocable(
            "S02A_T2_UpdateReservationNote",
            dll_path,
            parameters=[_param("reservation_id"), _param("note_code")],
        ),
        _invocable("S02A_T2_ListReservationCandidates", dll_path),
        _invocable(
            "S02A_T2_FormatReservationPreview",
            dll_path,
            parameters=[_param("reservation_id")],
        ),
        _invocable("S02A_T2_GetVersion", dll_path),
        _invocable(
            "S02A_T2_CalculateReservationQuote",
            dll_path,
            parameters=[_param("reservation_id")],
        ),
        _invocable("S02A_T2_InitSession", dll_path),
    ]
    runtime = ExploreRuntime(
        max_rounds=0,
        max_tool_calls=4,
        min_direct_probes=1,
        skip_documented=False,
        deterministic_fallback_enabled=True,
        concurrency=1,
        pass_scope_profile="all",
    )
    ctx = ExploreContext(
        job_id="job-s02a-s02b-ordering-execution-seam-tier2",
        runtime=runtime,
        client=object(),
        model="no-model",
        invocables=invocables,
        inv_map={str(inv["name"]): inv for inv in invocables},
        tool_schemas=[],
        total=len(invocables),
    )
    ctx.call_graph = {}
    ctx.vocab = {"id_formats": []}
    ctx.sentinels = {}
    ctx.unlock_result = {"unlocked": False, "sequence": []}
    return ctx


def _install_quiet_execution(monkeypatch: pytest.MonkeyPatch, probe_log: list[dict[str, object]]) -> None:
    monkeypatch.setattr(storage, "_load_findings", lambda _job_id: [])
    monkeypatch.setattr(probe_loop, "_download_blob", lambda *_args, **_kwargs: b"[]")
    monkeypatch.setattr(probe_loop, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_save_stage_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_append_transcript", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_append_executor_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_patch_invocable", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_patch_finding", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_save_finding", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_cancel_requested", lambda _job_id: False)
    monkeypatch.setattr(probe_loop, "_set_explore_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(probe_loop, "_update_vocabulary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_generate_hypothesis", lambda *_args, **_kwargs: {}, raising=False)
    monkeypatch.setattr(
        probe_loop,
        "_append_explore_probe_log",
        lambda _job_id, rows: probe_log.extend(dict(row) for row in rows),
    )


def test_s02a_to_s02b_tier2_preserves_ordered_plan_into_execution(
    monkeypatch: pytest.MonkeyPatch,
    seam_tier2_dll: Path,
) -> None:
    """Tier 2 seam anchor: S-02B consumes S-02A's ordered plan, not the scrambled input."""
    statuses: list[tuple[str, str]] = []
    uploads: dict[str, object] = {}
    probe_log: list[dict[str, object]] = []

    def _capture_status(_ctx: object, substage_id: str, _message: str, *, state: str) -> None:
        statuses.append((substage_id, state))

    def _capture_upload(_container: str, path: str, payload: bytes) -> None:
        uploads[path] = json.loads(payload.decode("utf-8"))

    monkeypatch.setattr(probe_ordering, "emit_s02_substage_status", _capture_status)
    monkeypatch.setattr(invocation_execution, "emit_s02_substage_status", _capture_status)
    monkeypatch.setattr(curriculum, "_upload_to_blob", _capture_upload)
    monkeypatch.setattr(executor, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(executor, "GUI_BRIDGE_SECRET", "")
    _install_quiet_execution(monkeypatch, probe_log)

    ctx = _ctx_for_seam(seam_tier2_dll)
    scrambled_names = [str(inv["name"]) for inv in ctx.invocables]

    probe_ordering.run_probe_ordering(ctx)
    ordered_names = [str(inv["name"]) for inv in ctx.invocables]

    invocation_execution.run_invocation_execution(ctx)

    assert statuses == [
        ("s02_probe_ordering", "start"),
        ("s02_probe_ordering", "done"),
        ("s02_invocation_execution", "start"),
        ("s02_invocation_execution", "done"),
    ]
    assert ordered_names != scrambled_names
    assert sorted(ordered_names) == sorted(scrambled_names)
    assert len(ordered_names) == len(set(ordered_names))

    executed_names: list[str] = []
    for row in probe_log:
        if row.get("phase") != "deterministic_fallback":
            continue
        function = str(row.get("function"))
        if function not in executed_names:
            executed_names.append(function)

    assert executed_names == ordered_names
    assert executed_names != scrambled_names
    assert set(ctx.already_explored) == set(ordered_names)

    upload_path = "job-s02a-s02b-ordering-execution-seam-tier2/prerequisite_state_machine.json"
    payload = uploads[upload_path]
    assert payload["layers"] == ctx.execution_layers
    assert payload["pass_scope_profile"] == "all"
    for row in probe_log:
        if row.get("phase") != "deterministic_fallback":
            continue
        trace = row["trace"]
        assert isinstance(trace, dict)
        assert trace["backend"] in {"dll", "policy"}
        if trace["backend"] == "dll":
            assert trace["function_name"] == row["function"]
