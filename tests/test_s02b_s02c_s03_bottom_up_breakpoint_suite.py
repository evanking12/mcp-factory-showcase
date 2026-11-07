from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from api.infra import storage
from api.pipeline.core.types import ExploreContext, ExploreRuntime
from api.pipeline.s02_probe import evidence_capture
from api.pipeline.s02_probe import invocation_execution
from api.pipeline.s02_probe import probe_loop
from api.pipeline.s02_probe import status as s02_status
from api.pipeline.s03_reconcile import reconcile
from api.services import executor


REPO_ROOT = Path(__file__).resolve().parents[1]
TIER2_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s02b_invocation_raw_observation_tier2"
TIER2_BUILD_SCRIPT = TIER2_FIXTURE_ROOT / "build.ps1"


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
def raw_observation_tier2_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not _has_msvc_toolchain():
        pytest.skip("MSVC toolchain not available")
    output_root = tmp_path_factory.mktemp("s02b-s02c-s03-bottom-up-tier2")
    completed = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(TIER2_BUILD_SCRIPT),
            "-OutputRoot",
            str(output_root),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    dll_path = output_root / "bin" / "s02b_invocation_raw_observation_tier2.dll"
    assert dll_path.exists(), completed.stdout + completed.stderr
    return dll_path


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


def _ctx_for_invocables(
    *,
    job_id: str,
    invocables: list[dict[str, object]],
) -> ExploreContext:
    runtime = ExploreRuntime(
        max_rounds=0,
        max_tool_calls=len(invocables),
        min_direct_probes=1,
        skip_documented=False,
        deterministic_fallback_enabled=True,
        concurrency=1,
    )
    ctx = ExploreContext(
        job_id=job_id,
        runtime=runtime,
        client=object(),
        model="no-model",
        invocables=invocables,
        inv_map={str(inv["name"]): inv for inv in invocables},
        tool_schemas=[],
        total=len(invocables),
    )
    ctx.vocab = {}
    ctx.sentinels = {}
    ctx.unlock_result = {"unlocked": False, "sequence": []}
    return ctx


def _install_bottom_up_storage(
    monkeypatch: pytest.MonkeyPatch,
    *,
    legacy_probe_log: list[dict[str, object]],
    uploads: dict[str, object],
    findings: list[dict[str, object]],
    patches: list[tuple[str, dict[str, object]]],
) -> list[dict[str, object]]:
    statuses: list[dict[str, object]] = []

    monkeypatch.setattr(s02_status, "_get_job_status", lambda _job_id: {})
    monkeypatch.setattr(s02_status, "_persist_job_status", lambda _job_id, payload: statuses.append(dict(payload)))
    monkeypatch.setattr(s02_status, "_set_explore_status", lambda *_args, **_kwargs: None)

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
        lambda _job_id, rows: legacy_probe_log.extend(dict(row) for row in rows),
    )

    def evidence_download(_container: str, blob_name: str) -> bytes:
        if blob_name.endswith("/explore_probe_log.json"):
            return json.dumps(legacy_probe_log, default=str).encode("utf-8")
        return b"[]"

    def upload(_container: str, blob_name: str, data: bytes) -> str:
        uploads[blob_name] = json.loads(data.decode("utf-8"))
        return blob_name

    def reconcile_download(_container: str, blob_name: str) -> bytes:
        assert blob_name.endswith(f"/{reconcile.S02C_PROBE_LOG_ALIAS}")
        return json.dumps(uploads[blob_name], default=str).encode("utf-8")

    monkeypatch.setattr(evidence_capture, "_download_blob", evidence_download)
    monkeypatch.setattr(evidence_capture, "_upload_to_blob", upload)
    monkeypatch.setattr(
        evidence_capture,
        "_name_sentinel_candidates",
        lambda *_args, **_kwargs: pytest.fail("bottom-up Tier 2 should not trigger recalibration"),
    )
    monkeypatch.setattr(
        evidence_capture,
        "_probe_write_unlock",
        lambda *_args, **_kwargs: pytest.fail("bottom-up Tier 2 should not re-probe unlock"),
    )

    monkeypatch.setattr(reconcile, "_download_blob", reconcile_download)
    monkeypatch.setattr(reconcile, "_load_findings", lambda _job_id: list(findings))
    monkeypatch.setattr(reconcile, "_patch_finding", lambda _job_id, fn, patch: patches.append((fn, patch)))
    monkeypatch.setattr(reconcile, "_set_explore_status", lambda *_args, **_kwargs: None)
    return statuses


def test_s02b_s02c_s03_tier2_bottom_up_raw_evidence_flow(
    monkeypatch: pytest.MonkeyPatch,
    raw_observation_tier2_dll: Path,
) -> None:
    """Tier 2 bottom-up window: raw execution evidence reaches reconciliation."""
    legacy_probe_log: list[dict[str, object]] = []
    uploads: dict[str, object] = {}
    patches: list[tuple[str, dict[str, object]]] = []
    findings = [
        {"function": "S02B_T2_StatusOk", "status": "error"},
        {"function": "S02B_T2_StatusBlocked", "status": "error"},
        {"function": "S02B_T2_StatusWarning", "status": "error"},
        {"function": "S02B_T2_EchoInt", "status": "error"},
        {"function": "S02B_T2_MissingObservation", "status": "error"},
    ]
    statuses = _install_bottom_up_storage(
        monkeypatch,
        legacy_probe_log=legacy_probe_log,
        uploads=uploads,
        findings=findings,
        patches=patches,
    )
    monkeypatch.setattr(executor, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(executor, "GUI_BRIDGE_SECRET", "")
    invocables = [
        _invocable("S02B_T2_StatusOk", raw_observation_tier2_dll),
        _invocable("S02B_T2_StatusBlocked", raw_observation_tier2_dll),
        _invocable("S02B_T2_StatusWarning", raw_observation_tier2_dll),
        _invocable("S02B_T2_StateCounter", raw_observation_tier2_dll),
        _invocable(
            "S02B_T2_EchoInt",
            raw_observation_tier2_dll,
            parameters=[
                {
                    "name": "value",
                    "type": "int",
                    "json_type": "integer",
                    "description": "integer probe value",
                    "direction": "in",
                }
            ],
        ),
    ]
    ctx = _ctx_for_invocables(
        job_id="job-s02b-s02c-s03-bottom-up-tier2",
        invocables=invocables,
    )

    invocation_execution.run_invocation_execution(ctx)
    evidence_capture.run_evidence_capture(ctx)
    reconcile._run_phase_4_reconcile(ctx)

    s02b_states = [
        row.get("s02_substage_status", {}).get("s02_invocation_execution", {}).get("state")
        for row in statuses
        if row.get("s02_substage_status", {}).get("s02_invocation_execution")
    ]
    s02c_states = [
        row.get("s02_substage_status", {}).get("s02_evidence_capture", {}).get("state")
        for row in statuses
        if row.get("s02_substage_status", {}).get("s02_evidence_capture")
    ]
    assert s02b_states == ["start", "done"]
    assert s02c_states == ["start", "done"]

    legacy_rows = [
        row
        for row in legacy_probe_log
        if row.get("phase") == "deterministic_fallback"
    ]
    assert [row.get("function") for row in legacy_rows] == [inv["name"] for inv in invocables]

    alias_blob = f"{ctx.job_id}/{evidence_capture.S02C_PROBE_LOG_ALIAS}"
    assert alias_blob in uploads
    persisted_rows = [
        row
        for row in uploads[alias_blob]
        if row.get("phase") == "deterministic_fallback"
    ]
    assert persisted_rows == legacy_rows

    assert [fn for fn, _patch in patches] == ["S02B_T2_StatusOk"]
    patch = patches[0][1]
    assert patch["status"] == "success"
    assert patch["working_call"] == {}
    assert patch["stop_reason"] == "reconciled_from_probe_log"
    assert "returned 0" in str(patch["finding"])

    observations = {str(row["function"]): row for row in persisted_rows}
    assert observations["S02B_T2_StatusOk"]["classification"]["signed"] == 0
    assert observations["S02B_T2_StatusBlocked"]["classification"]["signed"] == -5
    assert observations["S02B_T2_StatusWarning"]["classification"]["signed"] == 7
    assert observations["S02B_T2_EchoInt"]["trace"]["c_args_count"] == 1
    assert set(observations["S02B_T2_EchoInt"]["args"]) == {"value"}
