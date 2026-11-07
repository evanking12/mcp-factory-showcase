from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import api.services.discovery as discovery


class _FakeProc:
    def __init__(self, cmd, *, created_files: list[str]) -> None:
        self.cmd = cmd
        self.pid = 4242
        self.returncode = 0
        out_dir = Path(cmd[cmd.index("--out") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "sample_exports_mcp.json").write_text(json.dumps({"invocables": []}), encoding="utf-8")
        created_files.append(str(out_dir / "sample_exports_mcp.json"))

    def communicate(self, timeout=None):
        return ("ok", "")

    def poll(self):
        return self.returncode


class _CompletedOutputHungWrapperProc:
    def __init__(self, cmd) -> None:
        self.args = list(cmd)
        self.pid = 4343
        self.returncode = None
        self.killed = False
        out_dir = Path(cmd[cmd.index("--out") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "discovery-child-runtime.json").write_text(
            json.dumps(
                {
                    "phase": "bootstrap_main_returned",
                    "last_observation": {"returncode": 0},
                }
            ),
            encoding="utf-8",
        )
        (out_dir / "sample_exports_mcp.json").write_text(
            json.dumps({"invocables": [{"name": "SP_IssueReleaseHold"}]}),
            encoding="utf-8",
        )

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9

    def communicate(self, timeout=None):
        if not self.killed:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return ("", "")


class _CompletedNoOutputHungWrapperProc:
    def __init__(self, cmd) -> None:
        self.args = list(cmd)
        self.pid = 4444
        self.returncode = None
        self.killed = False
        out_dir = Path(cmd[cmd.index("--out") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "discovery-child-runtime.json").write_text(
            json.dumps(
                {
                    "phase": "bootstrap_main_returned",
                    "last_observation": {"returncode": 0},
                }
            ),
            encoding="utf-8",
        )

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9

    def communicate(self, timeout=None):
        if not self.killed:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return ("", "")


def _run_with_profile(monkeypatch, tmp_path: Path, profile: str) -> tuple[list[str], dict]:
    binary_path = tmp_path / "sample.dll"
    binary_path.write_bytes(b"binary")
    captured_cmds: list[list[str]] = []
    captured_kwargs: list[dict] = []
    created_files: list[str] = []

    monkeypatch.setattr(discovery, "_try_cached_discovery_result", lambda **kwargs: (None, "a" * 64, "cold"))
    monkeypatch.setattr(discovery, "_resolve_discovery_main", lambda: tmp_path / "fake_main.py")
    monkeypatch.setattr(discovery, "_record_upload_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery, "_upload_to_blob", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery, "_write_cache_blob", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery, "_apply_fixture_manifest_overlay", lambda binary, invocables: invocables)
    monkeypatch.setattr(discovery, "_call_gui_bridge", lambda *args, **kwargs: ([], ""))
    monkeypatch.setattr(discovery, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(discovery, "GUI_BRIDGE_SECRET", "")

    def _fake_popen(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        captured_kwargs.append(dict(kwargs))
        return _FakeProc(cmd, created_files=created_files)

    monkeypatch.setattr(discovery.subprocess, "Popen", _fake_popen)

    result = discovery._run_discovery(binary_path, "job-123", analysis_profile=profile)

    assert result["job_id"] == "job-123"
    assert created_files
    return captured_cmds[0], captured_kwargs[0]


def test_run_discovery_forwards_analysis_profile_to_subprocess(monkeypatch, tmp_path: Path) -> None:
    cmd, kwargs = _run_with_profile(monkeypatch, tmp_path, "strict_dll")

    assert "--analysis-profile" in cmd
    assert cmd[cmd.index("--analysis-profile") + 1] == "strict_dll"
    assert "--registry" not in cmd
    assert "creationflags" in kwargs


def test_run_discovery_keeps_registry_scan_scoped_to_full_surface(monkeypatch, tmp_path: Path) -> None:
    cmd, _kwargs = _run_with_profile(monkeypatch, tmp_path, "full_surface")

    assert "--analysis-profile" in cmd
    assert cmd[cmd.index("--analysis-profile") + 1] == "full_surface"
    assert "--registry" in cmd


def test_discovery_child_creationflags_isolates_windows_process_group(monkeypatch) -> None:
    monkeypatch.setattr(discovery, "IS_WINDOWS", True)
    monkeypatch.setattr(discovery.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)

    assert discovery._discovery_child_creationflags() == 512


def test_discovery_child_creationflags_zero_off_windows(monkeypatch) -> None:
    monkeypatch.setattr(discovery, "IS_WINDOWS", False)
    monkeypatch.setattr(discovery.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)

    assert discovery._discovery_child_creationflags() == 0


def test_run_discovery_recovers_when_wrapper_wait_stalls_after_child_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "sample.dll"
    binary_path.write_bytes(b"binary")
    emitted: list[tuple[str, dict]] = []

    monkeypatch.setattr(discovery, "_try_cached_discovery_result", lambda **kwargs: (None, "a" * 64, "cold"))
    monkeypatch.setattr(discovery, "_resolve_discovery_main", lambda: tmp_path / "fake_main.py")
    monkeypatch.setattr(discovery, "_record_upload_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery, "_upload_to_blob", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery, "_write_cache_blob", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery, "_emit_discovery_meta", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery, "_apply_fixture_manifest_overlay", lambda binary, invocables: invocables)
    monkeypatch.setattr(discovery, "_call_gui_bridge", lambda *args, **kwargs: ([], ""))
    monkeypatch.setattr(discovery, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(discovery, "GUI_BRIDGE_SECRET", "")
    monkeypatch.setattr(discovery.subprocess, "Popen", lambda cmd, **kwargs: _CompletedOutputHungWrapperProc(cmd))
    monkeypatch.setattr(
        discovery,
        "_emit_analyzer_runtime_authority",
        lambda _job_id, phase, **kwargs: emitted.append((phase, dict(kwargs))),
    )

    result = discovery._run_discovery(binary_path, "job-123", analysis_profile="strict_dll")

    assert [item["name"] for item in result["invocables"]] == ["SP_IssueReleaseHold"]
    wait_returned = [kwargs for phase, kwargs in emitted if phase == "discovery_child_wait_returned"]
    assert wait_returned
    assert wait_returned[-1]["extra"]["wait_recovered_from_output"] is True
    returncodes = [kwargs for phase, kwargs in emitted if phase == "discovery_child_returncode_observed"]
    assert returncodes
    assert returncodes[-1]["child_returncode"] == 0


def test_run_discovery_recovers_when_wrapper_wait_stalls_after_child_no_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "sample.dll"
    binary_path.write_bytes(b"binary")
    emitted: list[tuple[str, dict]] = []
    output_authorities: list[dict] = []

    monkeypatch.setattr(discovery, "_try_cached_discovery_result", lambda **kwargs: (None, "a" * 64, "cold"))
    monkeypatch.setattr(discovery, "_resolve_discovery_main", lambda: tmp_path / "fake_main.py")
    monkeypatch.setattr(discovery, "_record_upload_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery, "_upload_to_blob", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery, "_write_cache_blob", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery, "_emit_discovery_meta", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery, "_apply_fixture_manifest_overlay", lambda binary, invocables: invocables)
    monkeypatch.setattr(discovery, "_call_gui_bridge", lambda *args, **kwargs: ([], ""))
    monkeypatch.setattr(discovery, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(discovery, "GUI_BRIDGE_SECRET", "")
    monkeypatch.setattr(discovery.subprocess, "Popen", lambda cmd, **kwargs: _CompletedNoOutputHungWrapperProc(cmd))
    monkeypatch.setattr(
        discovery,
        "_emit_analyzer_runtime_authority",
        lambda _job_id, phase, **kwargs: emitted.append((phase, dict(kwargs))),
    )
    monkeypatch.setattr(
        discovery,
        "_emit_discovery_output_authority",
        lambda _job_id, authority: output_authorities.append(dict(authority)),
    )

    try:
        discovery._run_discovery(binary_path, "job-123", analysis_profile="strict_dll")
    except RuntimeError as exc:
        assert "Discovery produced no output files" in str(exc)
    else:
        raise AssertionError("expected no-output discovery failure")

    wait_returned = [kwargs for phase, kwargs in emitted if phase == "discovery_child_wait_returned"]
    assert wait_returned
    assert wait_returned[-1]["extra"]["wait_recovered_from_output"] is False
    assert wait_returned[-1]["extra"]["wait_recovery_reason"] == "child_runtime_completed_no_output"
    assert [phase for phase, _ in emitted if phase == "discovery_child_returncode_observed"]
    output_scans = [kwargs for phase, kwargs in emitted if phase == "discovery_output_scan_completed"]
    assert output_scans
    assert output_scans[-1]["extra"]["output_file_count"] == 0
    assert output_authorities


def test_communicate_discovery_child_recovers_before_first_liveness_emit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "sample.dll"
    binary_path.write_bytes(b"binary")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    calls = {"completed": 0}
    emitted: list[str] = []

    class _Proc:
        args = ["python", "bootstrap.py"]
        pid = 4545
        returncode = None

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9

        def communicate(self, timeout=None):
            return "", ""

    def fake_completed(_out_dir):
        calls["completed"] += 1
        if calls["completed"] == 1:
            return False, None, [], None
        return True, {"phase": "bootstrap_main_returned"}, [out_dir / "sample_mcp.json"], 0

    monkeypatch.setattr(discovery, "_child_runtime_completed", fake_completed)
    monkeypatch.setattr(
        discovery,
        "_emit_analyzer_runtime_authority",
        lambda _job_id, phase, **_kwargs: emitted.append(phase),
    )

    stdout, stderr, returncode, recovered, wrapper_returncode, reason = discovery._communicate_discovery_child(
        _Proc(),
        job_id="job-123",
        binary_path=binary_path,
        out_dir=out_dir,
        analysis_profile="strict_dll",
        started_at=time.time(),
        timeout_sec=5.0,
        poll_sec=0.01,
    )

    assert (stdout, stderr) == ("", "")
    assert returncode == 0
    assert recovered is True
    assert wrapper_returncode == -9
    assert reason == "child_runtime_completed_with_outputs"
    assert "discovery_child_wait_liveness" not in emitted
