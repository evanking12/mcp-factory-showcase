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
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s05b_verification_replay_weak_positive"
BUILD_SCRIPT = FIXTURE_ROOT / "build.ps1"
DLL_NAME = "s05b_verification_replay_weak_positive.dll"


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
def weak_positive_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not _has_msvc_toolchain():
        pytest.skip("MSVC toolchain not available")
    output_root = tmp_path_factory.mktemp("s05b-verification-replay-weak-positive")
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


def _invocable(name: str, dll_path: Path) -> dict[str, object]:
    return {
        "name": name,
        "type": "function",
        "return_type": "int",
        "parameters": [],
        "execution": {
            "method": "dll_import",
            "dll_path": str(dll_path),
            "function_name": name,
        },
    }


def _ctx(job_id: str, dll_path: Path) -> SimpleNamespace:
    names = [
        "S05B_WP_VerifiedOk",
        "S05B_WP_InferredWouldPass",
        "S05B_WP_PartialWouldPass",
        "S05B_WP_FailedWouldPass",
        "S05B_WP_StateDrift",
    ]
    return SimpleNamespace(
        job_id=job_id,
        _state={"explored": len(names)},
        total=len(names),
        init_invocables=[],
        sentinels={0xFFFFFFFD: "not initialized"},
        inv_map={name: _invocable(name, dll_path) for name in names},
        explored_count=lambda: len(names),
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


def test_s05b_tier2_keeps_weak_positive_rows_out_of_verified_replay(
    monkeypatch: pytest.MonkeyPatch,
    weak_positive_dll: Path,
) -> None:
    findings: list[dict[str, object]] = [
        {
            "function": "S05B_WP_VerifiedOk",
            "status": "verified_success",
            "verification": "verified",
            "working_call": {"args": {}},
        },
        {
            "function": "S05B_WP_InferredWouldPass",
            "status": "success",
            "verification": "inferred",
            "working_call": {"args": {}},
        },
        {
            "function": "S05B_WP_PartialWouldPass",
            "status": "partial",
            "verification": "inferred",
            "working_call": {"args": {}},
        },
        {
            "function": "S05B_WP_FailedWouldPass",
            "status": "failure",
            "verification": "error",
            "working_call": {"args": {}},
        },
        {
            "function": "S05B_WP_StateDrift",
            "status": "verified_success",
            "verification": "verified",
            "working_call": {"args": {}},
        },
    ]
    uploads, patches, persisted = _install_storage(monkeypatch, findings)

    verification_replay.run_verification_replay(_ctx("job-s05b-weak-positive", weak_positive_dll))

    report = uploads["job-s05b-weak-positive/verification-report.json"]
    entries = {entry["function"]: entry for entry in report["entries"]}
    assert set(entries) == {"S05B_WP_VerifiedOk", "S05B_WP_StateDrift"}
    assert report["verified_count"] == 1
    assert report["state_drift_count"] == 1
    assert report["inferred_count"] == 0

    patches_by_fn = {fn: patch for fn, patch in patches}
    assert patches_by_fn["S05B_WP_VerifiedOk"]["status"] == "verified_success"
    assert patches_by_fn["S05B_WP_VerifiedOk"]["verification"] == "verified"
    assert patches_by_fn["S05B_WP_StateDrift"]["verification"] == "state_drift"
    assert patches_by_fn["S05B_WP_StateDrift"]["working_call"] is None
    assert "S05B_WP_InferredWouldPass" not in patches_by_fn
    assert "S05B_WP_PartialWouldPass" not in patches_by_fn
    assert "S05B_WP_FailedWouldPass" not in patches_by_fn

    states = [
        row.get("s05_stage_status", {}).get("s05_verification_replay", {}).get("state")
        for row in persisted
    ]
    assert "start" in states
    assert "done" in states
