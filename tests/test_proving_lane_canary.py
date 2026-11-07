from __future__ import annotations

import json
from pathlib import Path

from scripts.runs.run_proving_lane_canary import run_proving_lane_canary


def _identity(component: str, role: str) -> dict:
    payload = {
        "component": component,
        "role": role,
        "contract_version": "trust_contract_v1",
        "git_sha": "abc123",
        "build_fingerprint": "sha256:test",
        "config_fingerprint": "sha256:test",
    }
    if component == "api":
        payload.update(
            {
                "service_name": "mcp_factory_api",
                "service_version": "1.0.0",
                "process_started_at": "2026-04-13T00:00:00Z",
                "pipeline_schema_version": "handoff_contract_v1.0.0",
                "status_schema_version": "job_status_v1",
            }
        )
    elif component == "bridge":
        payload.update(
            {
                "service_name": "gui_bridge",
                "service_version": "1.0.0",
                "process_started_at": "2026-04-13T00:00:00Z",
                "capabilities": ["execute", "flush_dll_cache"],
            }
        )
    else:
        payload.update(
            {
                "runner_name": "run_proving_lane_canary",
                "runner_version": "1.0.0",
                "runner_git_sha": "abc123",
                "runner_dirty": False,
                "started_at": "2026-04-13T00:00:00Z",
                "host": "test-host",
            }
        )
    return payload


def test_run_proving_lane_canary_writes_passed_lane_trust_packet(tmp_path: Path, monkeypatch) -> None:
    dll_path = tmp_path / "spectrum_session_bootstrap.dll"
    dll_path.write_bytes(b"binary")

    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.CANARY_DLL_PATH", dll_path)
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.resolve_api_url",
        lambda api_url, api_key, verify_identity: ("http://api.test", "api_ok:test", "explicit"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.ensure_local_api_freshness",
        lambda repo_root, api_url, api_key, campaign_log=None, allow_relaunch=True: {
            "freshness_verdict": "fresh",
            "restart_required": False,
            "restart_performed": False,
        },
        raising=False,
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_runner_identity",
        lambda **kwargs: _identity("runner", "proving_driver"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_api_identity",
        lambda api_url, api_key, api_msg: _identity("api", "pipeline_control_plane"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_bridge_identity",
        lambda bridge_url, bridge_key, bridge_msg: _identity("bridge", "execution_bridge"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.fetch_api_readiness",
        lambda api_url, api_key: {"ready": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.fetch_bridge_readiness",
        lambda bridge_url, bridge_key: {"ready": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary._analyze_only_canary",
        lambda client, dll_path, heartbeat_path, campaign_log=None: {
            "job_id": "job-analyze",
            "passed": True,
            "duration_sec": 1.0,
            "status": "done",
            "invocable_count": 1,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.run_one",
        lambda *args, **kwargs: {
            "job_id": "job-1",
            "duration_sec": 4.0,
            "valid_run": True,
            "save_session_exit": 0,
            "save_session_timed_out": False,
            "run_authority": {
                "authority_level": "decision_bearing",
                "authoritative_proving": True,
                "failure_domain": "",
                "safe_to_steer_next_prompt": True,
            },
            "job_terminalization": {"terminalization_kind": "done"},
            "job_status_snapshot": {"status": "done"},
            "failure_domain": "",
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary._bridge_execution_canary",
        lambda bridge_url, bridge_key: {"action": "flush_dll_cache", "passed": True, "duration_sec": 1.0},
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.ApiClient", FakeClient)

    result = run_proving_lane_canary(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out",
    )

    output_dir = Path(result["output_dir"])
    lane_trust = json.loads((output_dir / "lane-trust-packet.json").read_text(encoding="utf-8"))
    lane_readiness = json.loads((output_dir / "lane-readiness.json").read_text(encoding="utf-8"))

    assert lane_trust["canary_verdict"] == "passed"
    assert lane_trust["scope"] == "lane_trust_floor"
    assert "session_capture_canary" not in lane_trust
    assert "job_progress_tail" not in lane_trust
    assert lane_readiness["canary_verdict"] == "passed"


def test_run_proving_lane_canary_bootstraps_fixture_before_dll_check(tmp_path: Path, monkeypatch) -> None:
    dll_path = tmp_path / "spectrum_session_bootstrap.dll"
    bootstrap_called: list[bool] = []

    def _bootstrap() -> dict:
        bootstrap_called.append(True)
        dll_path.write_bytes(b"binary")
        return {"ok": True}

    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.CANARY_DLL_PATH", dll_path)
    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.ensure_spectrum_compiled_package_built", _bootstrap)
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.resolve_api_url",
        lambda api_url, api_key, verify_identity: ("http://api.test", "api_ok:test", "explicit"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.ensure_local_api_freshness",
        lambda repo_root, api_url, api_key, campaign_log=None, allow_relaunch=True: {
            "freshness_verdict": "fresh",
            "restart_required": False,
            "restart_performed": False,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_runner_identity",
        lambda **kwargs: _identity("runner", "proving_driver"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_api_identity",
        lambda api_url, api_key, api_msg: _identity("api", "pipeline_control_plane"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_bridge_identity",
        lambda bridge_url, bridge_key, bridge_msg: _identity("bridge", "execution_bridge"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.fetch_api_readiness",
        lambda api_url, api_key: {"ready": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.fetch_bridge_readiness",
        lambda bridge_url, bridge_key: {"ready": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary._analyze_only_canary",
        lambda client, dll_path, heartbeat_path, campaign_log=None: {
            "job_id": "job-analyze",
            "passed": True,
            "duration_sec": 1.0,
            "status": "done",
            "invocable_count": 1,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.run_one",
        lambda *args, **kwargs: {
            "job_id": "job-1",
            "duration_sec": 4.0,
            "valid_run": True,
            "save_session_exit": 0,
            "save_session_timed_out": False,
            "run_authority": {
                "authority_level": "decision_bearing",
                "authoritative_proving": True,
                "failure_domain": "",
                "safe_to_steer_next_prompt": True,
            },
            "job_terminalization": {"terminalization_kind": "done"},
            "job_status_snapshot": {"status": "done"},
            "failure_domain": "",
        },
        raising=False,
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary._bridge_execution_canary",
        lambda bridge_url, bridge_key: {"action": "flush_dll_cache", "passed": True, "duration_sec": 1.0},
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.ApiClient", FakeClient)

    result = run_proving_lane_canary(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-bootstrap",
    )

    assert bootstrap_called == [True]
    assert Path(result["output_dir"]).exists()


def test_run_proving_lane_canary_observe_only_suppresses_freshness_relaunch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_path = tmp_path / "spectrum_session_bootstrap.dll"
    dll_path.write_bytes(b"binary")
    freshness_calls: dict[str, bool] = {}

    def _api_freshness(repo_root, api_url, api_key, campaign_log=None, allow_relaunch=True):
        freshness_calls["api_allow_relaunch"] = bool(allow_relaunch)
        return {
            "freshness_verdict": "restart_suppressed_age",
            "restart_required": True,
            "restart_performed": False,
            "restart_suppressed": True,
            "allow_relaunch": allow_relaunch,
        }

    def _bridge_freshness(repo_root, bridge_url, bridge_key, campaign_log=None, allow_relaunch=True):
        freshness_calls["bridge_allow_relaunch"] = bool(allow_relaunch)
        return {
            "freshness_verdict": "restart_suppressed_age",
            "restart_required": True,
            "restart_performed": False,
            "restart_suppressed": True,
            "allow_relaunch": allow_relaunch,
        }

    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.CANARY_DLL_PATH", dll_path)
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.resolve_api_url",
        lambda api_url, api_key, verify_identity: ("http://api.test", "api_ok:test", "explicit"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )
    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.ensure_local_api_freshness", _api_freshness)
    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.ensure_local_bridge_freshness", _bridge_freshness)
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_runner_identity",
        lambda **kwargs: _identity("runner", "proving_driver"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_api_identity",
        lambda api_url, api_key, api_msg: _identity("api", "pipeline_control_plane"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_bridge_identity",
        lambda bridge_url, bridge_key, bridge_msg: _identity("bridge", "execution_bridge"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.fetch_api_readiness",
        lambda api_url, api_key: {"ready": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.fetch_bridge_readiness",
        lambda bridge_url, bridge_key: {"ready": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary._analyze_only_canary",
        lambda client, dll_path, heartbeat_path, campaign_log=None: {
            "job_id": "job-analyze",
            "passed": True,
            "duration_sec": 1.0,
            "status": "done",
            "invocable_count": 1,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.run_one",
        lambda *args, **kwargs: {
            "job_id": "job-1",
            "duration_sec": 4.0,
            "valid_run": True,
            "save_session_exit": 0,
            "save_session_timed_out": False,
            "run_authority": {
                "authority_level": "decision_bearing",
                "authoritative_proving": True,
                "failure_domain": "",
                "safe_to_steer_next_prompt": True,
            },
            "job_terminalization": {"terminalization_kind": "done"},
            "job_status_snapshot": {"status": "done"},
            "failure_domain": "",
        },
        raising=False,
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary._bridge_execution_canary",
        lambda bridge_url, bridge_key: {"action": "flush_dll_cache", "passed": True, "duration_sec": 1.0},
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.ApiClient", FakeClient)

    result = run_proving_lane_canary(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-observe-only",
        freshness_mode="observe_only",
    )

    lane_trust = json.loads((Path(result["output_dir"]) / "lane-trust-packet.json").read_text(encoding="utf-8"))

    assert freshness_calls == {
        "api_allow_relaunch": False,
        "bridge_allow_relaunch": False,
    }
    assert lane_trust["freshness_mode"] == "observe_only"
    assert lane_trust["api_freshness"]["restart_suppressed"] is True
    assert lane_trust["bridge_freshness"]["restart_suppressed"] is True


def test_run_proving_lane_canary_surfaces_analyze_only_failure(tmp_path: Path, monkeypatch) -> None:
    dll_path = tmp_path / "spectrum_session_bootstrap.dll"
    dll_path.write_bytes(b"binary")

    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.CANARY_DLL_PATH", dll_path)
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.resolve_api_url",
        lambda api_url, api_key, verify_identity: ("http://api.test", "api_ok:test", "explicit"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.ensure_local_api_freshness",
        lambda repo_root, api_url, api_key, campaign_log=None, allow_relaunch=True: {
            "freshness_verdict": "fresh",
            "restart_required": False,
            "restart_performed": False,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_runner_identity",
        lambda **kwargs: _identity("runner", "proving_driver"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_api_identity",
        lambda api_url, api_key, api_msg: _identity("api", "pipeline_control_plane"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_bridge_identity",
        lambda bridge_url, bridge_key, bridge_msg: _identity("bridge", "execution_bridge"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.fetch_api_readiness",
        lambda api_url, api_key: {"ready": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.fetch_bridge_readiness",
        lambda bridge_url, bridge_key: {"ready": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary._analyze_only_canary",
        lambda client, dll_path, heartbeat_path, campaign_log=None: {
            "job_id": "job-analyze",
            "passed": False,
            "duration_sec": 1.0,
            "status": "error",
            "invocable_count": 0,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.run_one",
        lambda *args, **kwargs: {
            "job_id": "job-1",
            "duration_sec": 4.0,
            "valid_run": False,
            "save_session_exit": 0,
            "save_session_timed_out": False,
            "run_authority": {
                "authority_level": "non_authoritative",
                "authoritative_proving": False,
                "failure_domain": "pipeline",
                "safe_to_steer_next_prompt": False,
            },
            "job_terminalization": {"terminalization_kind": "quasi_terminal_stall"},
            "job_status_snapshot": {"status": "running"},
            "failure_domain": "pipeline",
        },
        raising=False,
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary._bridge_execution_canary",
        lambda bridge_url, bridge_key: {"action": "flush_dll_cache", "passed": True, "duration_sec": 1.0},
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.ApiClient", FakeClient)

    result = run_proving_lane_canary(
        api_url="http://api.test",
        api_key="secret",
        bridge_url="http://bridge.test",
        bridge_key="bridge-secret",
        output_root=tmp_path / "out-failed",
    )

    output_dir = Path(result["output_dir"])
    lane_trust = json.loads((output_dir / "lane-trust-packet.json").read_text(encoding="utf-8"))

    assert lane_trust["canary_verdict"] == "failed"
    assert lane_trust["blocking_reason"] == "analyze_only_failed"


def test_run_proving_lane_canary_loads_bridge_secret_from_repo_env(tmp_path: Path, monkeypatch) -> None:
    dll_path = tmp_path / "spectrum_session_bootstrap.dll"
    dll_path.write_bytes(b"binary")
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".env").write_text(
        "GUI_BRIDGE_URL=http://bridge.test\nGUI_BRIDGE_SECRET=bridge-from-env\n",
        encoding="utf-8",
    )
    captured: dict[str, str] = {}

    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.CANARY_DLL_PATH", dll_path)
    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.REPO_ROOT", repo_root)
    monkeypatch.delenv("GUI_BRIDGE_SECRET", raising=False)
    monkeypatch.delenv("BRIDGE_SECRET", raising=False)
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.resolve_api_url",
        lambda api_url, api_key, verify_identity: ("http://api.test", "api_ok:test", "explicit"),
    )

    def fake_verify_bridge_identity(bridge_url: str, bridge_key: str) -> tuple[bool, str]:
        captured["bridge_url"] = bridge_url
        captured["bridge_key"] = bridge_key
        return True, "bridge_ok:test"

    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.verify_bridge_identity",
        fake_verify_bridge_identity,
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.ensure_local_api_freshness",
        lambda repo_root_arg, api_url, api_key, campaign_log=None, allow_relaunch=True: {
            "freshness_verdict": "fresh",
            "restart_required": False,
            "restart_performed": False,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_runner_identity",
        lambda **kwargs: _identity("runner", "proving_driver"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_api_identity",
        lambda api_url, api_key, api_msg: _identity("api", "pipeline_control_plane"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.collect_bridge_identity",
        lambda bridge_url, bridge_key, bridge_msg: _identity("bridge", "execution_bridge"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.fetch_api_readiness",
        lambda api_url, api_key: {"ready": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.fetch_bridge_readiness",
        lambda bridge_url, bridge_key: {"ready": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary._analyze_only_canary",
        lambda client, dll_path, heartbeat_path, campaign_log=None: {
            "job_id": "job-analyze",
            "passed": True,
            "duration_sec": 1.0,
            "status": "done",
            "invocable_count": 1,
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary.run_one",
        lambda *args, **kwargs: {
            "job_id": "job-1",
            "duration_sec": 4.0,
            "valid_run": True,
            "save_session_exit": 0,
            "save_session_timed_out": False,
            "run_authority": {
                "authority_level": "decision_bearing",
                "authoritative_proving": True,
                "failure_domain": "",
                "safe_to_steer_next_prompt": True,
            },
            "job_terminalization": {"terminalization_kind": "done"},
            "job_status_snapshot": {"status": "done"},
            "failure_domain": "",
        },
        raising=False,
    )
    monkeypatch.setattr(
        "scripts.runs.run_proving_lane_canary._bridge_execution_canary",
        lambda bridge_url, bridge_key: {"action": "flush_dll_cache", "passed": True, "duration_sec": 1.0},
    )

    class FakeClient:
        def __init__(self, api_url: str, api_key: str) -> None:
            self.api_url = api_url
            self.api_key = api_key

    monkeypatch.setattr("scripts.runs.run_proving_lane_canary.ApiClient", FakeClient)

    run_proving_lane_canary(
        api_url="http://api.test",
        api_key="secret",
        output_root=tmp_path / "out-env",
    )

    assert captured["bridge_url"] == "http://bridge.test"
    assert captured["bridge_key"] == "bridge-from-env"
