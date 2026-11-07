from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from api.pipeline.core.enterprise_survivability import write_enterprise_survivability_summary


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "enterprise_survivability"
BUILD_SCRIPT = FIXTURE_ROOT / "build.ps1"

_SCRIPT_PATH = REPO_ROOT / "scripts" / "ops" / "nightly_groundtruth.py"
_SPEC = importlib.util.spec_from_file_location("enterprise_survivability_nightly_harness", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
nightly_groundtruth = importlib.util.module_from_spec(_SPEC)
sys.modules["enterprise_survivability_nightly_harness"] = nightly_groundtruth
_SPEC.loader.exec_module(nightly_groundtruth)


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
def survivability_dlls(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    if not _has_msvc_toolchain():
        pytest.skip("MSVC toolchain not available")
    output_root = tmp_path_factory.mktemp("enterprise-survivability-fixtures")
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
    dlls = {
        "target_a": output_root / "bin" / "enterprise_survivability_target_a.dll",
        "target_b": output_root / "bin" / "enterprise_survivability_target_b.dll",
        "target_c": output_root / "bin" / "enterprise_survivability_target_c.dll",
    }
    for dll_path in dlls.values():
        assert dll_path.exists(), completed.stdout + completed.stderr
        assert dll_path.read_bytes().startswith(b"MZ")
    return dlls


def _successful_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dll_path: Path) -> dict:
    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-a"

        def post_json(self, path: str, payload: dict, timeout: int = 0):  # noqa: ANN001
            return {}

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-a/terminalization":
                return {
                    "job_id": "job-a",
                    "terminal": True,
                    "terminalization_kind": "done",
                    "reason": {"code": "job_completed_done", "message": "done"},
                }
            if path == "/api/jobs/job-a/verdict":
                return {"verdict": {"status": "done", "verified_count": 1, "total_count": 1}}
            if path == "/api/findings/job-a":
                return {"findings": [{"function": "ES_TargetA_ComparableSuccess", "status": "success"}]}
            raise AssertionError(f"unexpected client path: {path}")

    wait_states = iter(
        [
            {
                "status": "done",
                "result": {"invocables": [{"name": "ES_TargetA_ComparableSuccess", "kind": "export"}]},
            },
            {
                "status": "done",
                "explore_phase": "done",
                "explore_stage": "s07_finalize",
                "explore_message": "done",
                "explore_progress": "1/1",
                "verification_verified": 1,
                "updated_at": 1005.0,
                "explore_started_at": 1000.0,
            },
        ]
    )
    monkeypatch.setattr(nightly_groundtruth, "wait_job", lambda *args, **kwargs: next(wait_states))
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 1006.0)
    monkeypatch.setattr(
        nightly_groundtruth,
        "canonical_status_map",
        lambda findings, scope: {"ES_TargetA_ComparableSuccess": "verified_success"},
    )

    def fake_subprocess_run(cmd, cwd=None, capture_output=False, text=False, timeout=None):  # noqa: ANN001
        out_dir = Path(cmd[cmd.index("-OutDir") + 1])
        session_payloads = {
            "verification-report.json": {"verified_count": 1, "inferred_count": 0},
            "run-validity.json": {"valid": True},
            "kpi_run.json": {"totals": {"total_functions": 1, "verified_success": 1}},
            "session-meta.json": {"job_id": "job-a"},
            "stage-index.json": {"stages": ["s07_finalize"]},
            "human/collect-session-result.json": {"ledger": {"appended": True, "reason": "ok"}},
        }
        for name, payload in session_payloads.items():
            path = out_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
            os.utime(path, (1005.0, 1005.0))

        class Result:
            returncode = 0
            stdout = "saved"
            stderr = ""

        return Result()

    monkeypatch.setattr(nightly_groundtruth.subprocess, "run", fake_subprocess_run)
    return nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        tmp_path / "runs" / "01-target_a",
        "http://api.test",
        "",
        "target_a",
        dll_path,
        "compiled_enterprise_survivability",
        {
            "lane_id": "lane-a",
            "variant_id": "compiled_enterprise_survivability",
            "selected_invocable_names": ["ES_TargetA_ComparableSuccess"],
        },
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )


def _non_comparable_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dll_path: Path) -> dict:
    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-b"

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-b":
                return {
                    "job_id": "job-b",
                    "status": "error",
                    "error": "Discovery produced no output files.",
                    "progress": 100,
                }
            raise AssertionError(f"unexpected client path: {path}")

    monkeypatch.setattr(
        nightly_groundtruth,
        "wait_job",
        lambda *args, **kwargs: {
            "job_id": "job-b",
            "status": "error",
            "error": "Discovery produced no output files.",
            "progress": 100,
        },
    )
    return nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        tmp_path / "runs" / "02-target_b",
        "http://api.test",
        "",
        "target_b",
        dll_path,
        "compiled_enterprise_survivability",
        {
            "lane_id": "lane-b",
            "variant_id": "compiled_enterprise_survivability",
            "selected_invocable_names": ["ES_TargetB_NonComparableSource"],
        },
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )


def test_compiled_fixture_ladder_reaches_tier3_with_bounded_runner_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    survivability_dlls: dict[str, Path],
) -> None:
    target_a = _successful_record(tmp_path, monkeypatch, survivability_dlls["target_a"])
    target_b = _non_comparable_record(tmp_path, monkeypatch, survivability_dlls["target_b"])
    target_a["dll_path"] = str(survivability_dlls["target_a"])
    target_b["dll_path"] = str(survivability_dlls["target_b"])

    summary = write_enterprise_survivability_summary(
        output_dir=tmp_path,
        suite_id="compiled_enterprise_survivability",
        case_id="tier3_compiled_dependency_chain",
        run_records=[target_a, target_b],
        chain_plan=[
            {"target_name": "target_a", "predecessor_targets": []},
            {"target_name": "target_b", "predecessor_targets": ["target_a"]},
            {"target_name": "target_c", "predecessor_targets": ["target_b"]},
        ],
    )

    rows_by_target = {row["target"]: row for row in summary["targets"]}
    assert target_a["status"] == "ok"
    assert target_a["authoritative_proving"] is True
    assert target_b["measurement_terminalization"]["reason_code"] == "discovery_empty"
    assert (tmp_path / "runs" / "02-target_b" / "measurement-terminalization.json").exists()
    assert (tmp_path / "runs" / "02-target_b" / "run-authority.json").exists()
    assert (tmp_path / "runs" / "02-target_b" / "run_result.json").exists()
    assert (tmp_path / "enterprise-survivability-summary.json").exists()
    assert rows_by_target["target_a"]["state"] == "comparable"
    assert rows_by_target["target_b"]["state"] == "non_comparable"
    assert rows_by_target["target_c"]["state"] == "skipped_dependency_blocked"
    assert rows_by_target["target_c"]["blocked_by"] == ["target_b"]
    assert summary["safe_to_compare"] is False
    assert summary["semantic_proof_satisfied"] is False
