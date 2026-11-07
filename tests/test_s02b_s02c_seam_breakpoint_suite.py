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
    output_root = tmp_path_factory.mktemp("s02b-s02c-raw-observation-seam-tier2")
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


def _install_seam_storage(
    monkeypatch: pytest.MonkeyPatch,
    *,
    legacy_probe_log: list[dict[str, object]],
    uploads: dict[str, object],
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

    def fake_download(_container: str, blob_name: str) -> bytes:
        if blob_name.endswith("/explore_probe_log.json"):
            return json.dumps(legacy_probe_log, default=str).encode("utf-8")
        return b"[]"

    def fake_upload(_container: str, blob_name: str, data: bytes) -> str:
        uploads[blob_name] = json.loads(data.decode("utf-8"))
        return blob_name

    monkeypatch.setattr(evidence_capture, "_download_blob", fake_download)
    monkeypatch.setattr(evidence_capture, "_upload_to_blob", fake_upload)
    monkeypatch.setattr(
        evidence_capture,
        "_name_sentinel_candidates",
        lambda *_args, **_kwargs: pytest.fail("seam Tier 2 case should not trigger recalibration"),
    )
    monkeypatch.setattr(
        evidence_capture,
        "_probe_write_unlock",
        lambda *_args, **_kwargs: pytest.fail("seam Tier 2 case should not re-probe unlock"),
    )
    return statuses


def test_s02b_s02c_tier2_preserves_raw_observations_through_live_handoff(
    monkeypatch: pytest.MonkeyPatch,
    raw_observation_tier2_dll: Path,
) -> None:
    """Tier 2 seam anchor: S-02B raw rows survive S-02C durable capture."""
    legacy_probe_log: list[dict[str, object]] = []
    uploads: dict[str, object] = {}
    statuses = _install_seam_storage(
        monkeypatch,
        legacy_probe_log=legacy_probe_log,
        uploads=uploads,
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
        job_id="job-s02b-s02c-raw-observation-seam-tier2",
        invocables=invocables,
    )

    invocation_execution.run_invocation_execution(ctx)
    legacy_rows = [
        row
        for row in legacy_probe_log
        if row.get("phase") == "deterministic_fallback"
    ]
    assert [row.get("function") for row in legacy_rows] == [inv["name"] for inv in invocables]

    evidence_capture.run_evidence_capture(ctx)

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

    alias_blob = f"{ctx.job_id}/{evidence_capture.S02C_PROBE_LOG_ALIAS}"
    status_blob = f"{ctx.job_id}/{evidence_capture.S02C_FINDING_STATUS_ALIAS}"
    assert alias_blob in uploads
    assert status_blob in uploads

    persisted_rows = [
        row
        for row in uploads[alias_blob]
        if row.get("phase") == "deterministic_fallback"
    ]
    assert persisted_rows == legacy_rows
    assert [row["function"] for row in persisted_rows] == [inv["name"] for inv in invocables]

    for source, persisted in zip(legacy_rows, persisted_rows, strict=True):
        assert persisted["tool"] == source["tool"]
        assert persisted["args"] == source["args"]
        assert persisted["result_excerpt"] == source["result_excerpt"]
        assert persisted["classification"] == source["classification"]
        assert persisted["trace"]["backend"] == "dll"
        assert persisted["trace"]["function_name"] == source["function"]
        assert persisted["trace"]["raw_result"] == source["trace"]["raw_result"]
        assert persisted["trace"]["c_args_count"] == source["trace"]["c_args_count"]

    echo_row = next(row for row in persisted_rows if row["function"] == "S02B_T2_EchoInt")
    assert set(echo_row["args"]) == {"value"}
    assert echo_row["trace"]["raw_result"] == echo_row["args"]["value"] + 100

    status_rows = uploads[status_blob]
    assert [row["function"] for row in status_rows] == [row["function"] for row in legacy_rows]
    for source, status_row in zip(legacy_rows, status_rows, strict=True):
        source_classification = source["classification"]
        assert status_row["classification"] == source_classification
        assert status_row["args"] == source["args"]
        assert status_row["result_excerpt"] == source["result_excerpt"]
        assert status_row["trace"] == source["trace"]
        assert status_row["status"] == source_classification.get("status", "unresolved")
        assert status_row["boundary"] == source_classification.get("boundary", "unknown")
