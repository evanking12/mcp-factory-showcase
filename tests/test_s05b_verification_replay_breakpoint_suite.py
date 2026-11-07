from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.pipeline.s05_enrichment import status as s05_status
from api.pipeline.s05_enrichment import verification_replay
from api.pipeline.s05_enrichment import verify as verify_mod
from api.services import executor


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s05b_verification_replay_direct_truth"
BUILD_SCRIPT = FIXTURE_ROOT / "build.ps1"
DLL_NAME = "s05b_verification_replay_direct_truth.dll"


def _has_msvc_toolchain() -> bool:
    if sys.platform != "win32":
        return False
    vswhere = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
    if vswhere.exists():
        return True
    return any(
        Path(path).exists()
        for path in (
            r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat",
            r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
            r"C:\Program Files\Microsoft Visual Studio\2022\Professional\Common7\Tools\VsDevCmd.bat",
            r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\Tools\VsDevCmd.bat",
        )
    )


@pytest.fixture(scope="module")
def direct_truth_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not _has_msvc_toolchain():
        pytest.skip("MSVC toolchain not available")
    output_root = tmp_path_factory.mktemp("s05b-verification-replay-direct-truth")
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
    dll_path = output_root / "bin" / DLL_NAME
    assert dll_path.exists(), completed.stdout + completed.stderr
    return dll_path


def _invocable(name: str, dll_path: Path, parameters: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "name": name,
        "type": "function",
        "return_type": "int",
        "parameters": parameters or [],
        "execution": {
            "method": "dll_import",
            "dll_path": str(dll_path),
            "function_name": name,
        },
    }


def _ctx(job_id: str, dll_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        job_id=job_id,
        _state={"explored": 5},
        total=5,
        init_invocables=[],
        sentinels={0xFFFFFFFD: "not initialized"},
        inv_map={
            "S05B_T1_ReplayOk": _invocable("S05B_T1_ReplayOk", dll_path),
            "S05B_T2_ReplayOk": _invocable("S05B_T2_ReplayOk", dll_path),
            "S05B_T2_StateDrift": _invocable("S05B_T2_StateDrift", dll_path),
            "S05B_T2_EchoInt": _invocable(
                "S05B_T2_EchoInt",
                dll_path,
                [{"name": "value", "type": "int", "json_type": "integer"}],
            ),
        },
        explored_count=lambda: 5,
    )


def _install_storage(
    monkeypatch: pytest.MonkeyPatch,
    findings: list[dict[str, object]],
) -> tuple[dict[str, object], list[tuple[str, dict[str, object]]], list[dict[str, object]]]:
    uploads: dict[str, object] = {}
    patches: list[tuple[str, dict[str, object]]] = []
    persisted: list[dict[str, object]] = []

    def upload(_container: str, path: str, payload: bytes | str) -> None:
        raw = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
        uploads[path] = json.loads(raw)

    monkeypatch.setattr(verify_mod, "_load_findings", lambda _job_id: findings)
    monkeypatch.setattr(verify_mod, "_download_blob", lambda _container, _path: b"[]")
    monkeypatch.setattr(verify_mod, "_upload_to_blob", upload)
    monkeypatch.setattr(verify_mod, "_patch_finding", lambda _job_id, fn, patch: patches.append((fn, patch)))
    monkeypatch.setattr(verify_mod, "_get_job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(verify_mod, "_persist_job_status", lambda _job_id, payload: persisted.append(payload))
    monkeypatch.setattr(verify_mod, "_set_explore_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(s05_status, "_get_job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(s05_status, "_persist_job_status", lambda _job_id, payload: persisted.append(payload))
    monkeypatch.setattr(s05_status, "_set_explore_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(executor, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(executor, "GUI_BRIDGE_SECRET", "")
    return uploads, patches, persisted


def test_s05b_tier1_replays_one_easy_compiled_working_call(
    monkeypatch: pytest.MonkeyPatch,
    direct_truth_dll: Path,
) -> None:
    findings: list[dict[str, object]] = [
        {
            "function": "S05B_T1_ReplayOk",
            "status": "success",
            "working_call": {"args": {}},
        }
    ]
    uploads, patches, persisted = _install_storage(monkeypatch, findings)

    verification_replay.run_verification_replay(_ctx("job-s05b-tier1", direct_truth_dll))

    report = uploads["job-s05b-tier1/verification-report.json"]
    assert report["verified_count"] == 1
    assert report["inferred_count"] == 0
    assert report["state_drift_count"] == 0
    assert report["error_count"] == 0
    entry = report["entries"][0]
    assert entry["function"] == "S05B_T1_ReplayOk"
    assert entry["verification_mode"] == "direct_replay"
    assert entry["verification"] == "verified"
    assert entry["result"].startswith("Returned: 0")
    assert entry["direct_target_truth"]["source"] == "s05_finding"
    assert [fn for fn, _patch in patches] == ["S05B_T1_ReplayOk"]
    replay_patch = patches[0][1]
    assert replay_patch["verification"] == "verified"
    assert replay_patch["status"] == "verified_success"
    assert replay_patch["status_canonical"] == "verified_success"
    assert replay_patch["status_legacy"] == "success"
    assert replay_patch["working_call"] == {}
    assert replay_patch["direct_target_truth"]["function"] == "S05B_T1_ReplayOk"
    assert replay_patch["direct_target_truth"]["working_call"] == {}
    assert replay_patch["direct_target_truth"]["verification"] == "verified"
    assert replay_patch["direct_target_truth"]["return_value"] == 0
    assert replay_patch["direct_target_truth"]["source"] == "s05_finding"
    states = [
        row.get("s05_stage_status", {}).get("s05_verification_replay", {}).get("state")
        for row in persisted
    ]
    assert "start" in states
    assert "done" in states


def test_s05b_tier2_distinguishes_replay_truth_from_inherited_confidence(
    monkeypatch: pytest.MonkeyPatch,
    direct_truth_dll: Path,
) -> None:
    findings: list[dict[str, object]] = [
        {
            "function": "S05B_T2_ReplayOk",
            "status": "success",
            "working_call": {"args": {}},
        },
        {
            "function": "S05B_T2_StateDrift",
            "status": "success",
            "working_call": {"args": {}},
        },
        {
            "function": "S05B_T2_EchoInt",
            "status": "success",
            "working_call": {"args": {"value": 42}},
        },
        {
            "function": "S05B_T2_Unsupported",
            "status": "success",
            "working_call": {"args": {}},
        },
        {
            "function": "S05B_T2_MissingWorkingCall",
            "status": "success",
            "working_call": None,
        },
    ]
    uploads, patches, persisted = _install_storage(monkeypatch, findings)

    verification_replay.run_verification_replay(_ctx("job-s05b-tier2", direct_truth_dll))

    report = uploads["job-s05b-tier2/verification-report.json"]
    assert report["verified_count"] == 2
    assert report["state_drift_count"] == 1
    assert report["inferred_count"] == 0
    assert report["error_count"] == 0
    assert report["total_checked"] == 3

    entries = {entry["function"]: entry for entry in report["entries"]}
    assert set(entries) == {"S05B_T2_ReplayOk", "S05B_T2_StateDrift", "S05B_T2_EchoInt"}
    assert entries["S05B_T2_ReplayOk"]["verification"] == "verified"
    assert entries["S05B_T2_ReplayOk"]["result"].startswith("Returned: 0")
    assert entries["S05B_T2_StateDrift"]["verification"] == "state_drift"
    assert "not initialized" in entries["S05B_T2_StateDrift"]["result"]
    assert entries["S05B_T2_EchoInt"]["verification"] == "verified"
    assert entries["S05B_T2_EchoInt"]["args"] == {"value": 42}
    assert entries["S05B_T2_EchoInt"]["preserved_working_call"]["value"] == 42
    assert entries["S05B_T2_EchoInt"]["result"].startswith("Returned: 52")

    patches_by_fn = {fn: patch for fn, patch in patches}
    assert patches_by_fn["S05B_T2_ReplayOk"]["status"] == "verified_success"
    assert patches_by_fn["S05B_T2_EchoInt"]["working_call"]["value"] == 42
    drift_patch = patches_by_fn["S05B_T2_StateDrift"]
    assert drift_patch["verification"] == "state_drift"
    assert drift_patch["working_call"] is None
    assert drift_patch["direct_target_truth_rejected_reason"].startswith("verification replay returned -3")
    assert drift_patch["direct_target_truth"]["rejected_by_verification"] is True
    assert "S05B_T2_Unsupported" not in patches_by_fn
    assert "S05B_T2_MissingWorkingCall" not in patches_by_fn

    states = [
        row.get("s05_stage_status", {}).get("s05_verification_replay", {}).get("state")
        for row in persisted
    ]
    assert "start" in states
    assert "done" in states
