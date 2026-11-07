from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.pipeline.s02_probe import curriculum
from api.pipeline.s02_probe import probe_ordering


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
def probe_ordering_tier2_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not _has_msvc_toolchain():
        pytest.skip("MSVC toolchain not available")
    output_root = tmp_path_factory.mktemp("s02a-probe-ordering-tier2")
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


def _invocable(name: str, dll_path: Path, *, parameters: list[dict[str, object]] | None = None) -> dict[str, object]:
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


def _ctx_for_scrambled_invocables(dll_path: Path) -> SimpleNamespace:
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
    return SimpleNamespace(
        job_id="job-s02a-probe-ordering-tier2",
        total=len(invocables),
        runtime=SimpleNamespace(pass_scope_profile="all", pass_index=1),
        invocables=invocables,
        call_graph={},
        vocab={"id_formats": []},
        explored_count=lambda: 0,
    )


def test_s02a_tier2_orders_medium_compiled_callable_inventory(
    monkeypatch: pytest.MonkeyPatch,
    probe_ordering_tier2_dll: Path,
) -> None:
    """Tier 2 anchor: S-02A turns noisy compiled callable inventory into a useful plan."""
    status_events: list[tuple[str, str]] = []
    uploads: dict[str, object] = {}

    def _capture_status(_ctx: object, substage_id: str, _message: str, *, state: str) -> None:
        status_events.append((substage_id, state))

    def _capture_upload(_container: str, path: str, payload: bytes) -> None:
        uploads[path] = json.loads(payload.decode("utf-8"))

    monkeypatch.setattr(probe_ordering, "emit_s02_substage_status", _capture_status)
    monkeypatch.setattr(curriculum, "_upload_to_blob", _capture_upload)
    ctx = _ctx_for_scrambled_invocables(probe_ordering_tier2_dll)
    original_names = [str(inv["name"]) for inv in ctx.invocables]

    probe_ordering.run_probe_ordering(ctx)

    assert status_events == [
        ("s02_probe_ordering", "start"),
        ("s02_probe_ordering", "done"),
    ]
    ordered_names = [str(inv["name"]) for inv in ctx.invocables]
    assert sorted(ordered_names) == sorted(original_names)
    assert len(ordered_names) == len(set(ordered_names))

    init_idx = ordered_names.index("S02A_T2_InitSession")
    producer_indexes = [
        ordered_names.index("S02A_T2_ListReservationCandidates"),
        ordered_names.index("S02A_T2_QueryReservationCatalog"),
    ]
    consumer_indexes = [
        ordered_names.index("S02A_T2_WriteReservationUpdate"),
        ordered_names.index("S02A_T2_CommitReservation"),
        ordered_names.index("S02A_T2_UpdateReservationNote"),
    ]
    assert init_idx < min(producer_indexes)
    assert init_idx < min(consumer_indexes)
    assert max(producer_indexes) < min(consumer_indexes)
    assert ordered_names.index("S02A_T2_GetVersion") < min(consumer_indexes)

    sequence_roles = getattr(ctx, "sequence_roles", {})
    assert sequence_roles["S02A_T2_InitSession"]["role"] == "init"
    assert sequence_roles["S02A_T2_ListReservationCandidates"]["role"] == "producer"
    assert sequence_roles["S02A_T2_QueryReservationCatalog"]["role"] == "producer"
    assert sequence_roles["S02A_T2_WriteReservationUpdate"]["role"] == "consumer"
    assert sequence_roles["S02A_T2_CommitReservation"]["role"] == "consumer"
    assert sequence_roles["S02A_T2_UpdateReservationNote"]["role"] == "consumer"

    assert ctx.execution_layers
    first_layer = ctx.execution_layers[0]
    assert "S02A_T2_InitSession" in first_layer
    assert "S02A_T2_GetVersion" in first_layer

    upload_path = "job-s02a-probe-ordering-tier2/prerequisite_state_machine.json"
    payload = uploads[upload_path]
    assert payload["layers"] == ctx.execution_layers
    role_rows = {row["name"]: row for row in payload["roles"]}
    assert set(role_rows) == set(original_names)
    assert role_rows["S02A_T2_InitSession"]["role"] == "init"
    assert role_rows["S02A_T2_WriteReservationUpdate"]["role"] == "consumer"
    assert payload["pass_scope_profile"] == "all"

