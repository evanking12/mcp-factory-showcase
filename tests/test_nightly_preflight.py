from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path
import subprocess

from api.services import discovery
from api.infra.local_lane_admission import LOCAL_LANE_ADMISSION_VERSION


_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "ops" / "nightly_groundtruth.py"
_SPEC = importlib.util.spec_from_file_location("nightly_groundtruth_test_harness", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
nightly_groundtruth = importlib.util.module_from_spec(_SPEC)
sys.modules["nightly_groundtruth_test_harness"] = nightly_groundtruth
_SPEC.loader.exec_module(nightly_groundtruth)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.response = self

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise nightly_groundtruth.requests.HTTPError(response=self)


def test_verify_bridge_identity_rejects_api_shaped_endpoint(monkeypatch) -> None:
    def fake_get(url: str, headers=None, timeout=0):  # noqa: ANN001
        if url.endswith("/identity"):
            return _FakeResponse(
                200,
                {
                    "component": "api",
                    "role": "pipeline_control_plane",
                    "contract_version": "trust_contract_v1",
                },
            )
        if url.endswith("/openapi.json"):
            return _FakeResponse(
                200,
                {
                    "paths": {
                        "/api/jobs/{job_id}": {},
                        "/api/analyze": {},
                    }
                },
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(nightly_groundtruth.requests, "get", fake_get)
    ok, reason = nightly_groundtruth.verify_bridge_identity("http://localhost:8090", "secret")
    assert ok is False
    assert reason == "bridge_api_shaped_endpoint_detected"


def test_verify_bridge_identity_requires_explicit_readiness_route(monkeypatch) -> None:
    def fake_get(url: str, headers=None, timeout=0):  # noqa: ANN001
        if url.endswith("/identity"):
            return _FakeResponse(
                200,
                {
                    "component": "bridge",
                    "role": "execution_bridge",
                    "contract_version": "trust_contract_v1",
                    "capabilities": ["execute", "flush_dll_cache"],
                },
            )
        if url.endswith("/readiness"):
            return _FakeResponse(404, {"detail": "not found"})
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(nightly_groundtruth.requests, "get", fake_get)
    ok, reason = nightly_groundtruth.verify_bridge_identity("http://localhost:8090", "secret")
    assert ok is False
    assert reason == "bridge_readiness_unavailable"


def test_verify_api_identity_accepts_pipeline_api_shape(monkeypatch) -> None:
    def fake_get(url: str, headers=None, timeout=0):  # noqa: ANN001
        if url.endswith("/identity"):
            return _FakeResponse(
                200,
                {
                    "component": "api",
                    "role": "pipeline_control_plane",
                    "contract_version": "trust_contract_v1",
                    "status_schema_version": "job_status_v1",
                },
            )
        if url.endswith("/openapi.json"):
            return _FakeResponse(
                200,
                {
                    "paths": {
                        "/api/analyze": {},
                        "/api/jobs/{job_id}": {},
                        "/api/jobs/{job_id}/explore": {},
                    }
                },
            )
        if url.endswith("/readiness"):
            return _FakeResponse(
                200,
                {
                    "ready": True,
                    "blocking_reasons": [],
                },
            )
        if url.endswith("/local-lane-admission"):
            return _FakeResponse(
                200,
                {
                    "contract_version": "local_lane_admission_v1",
                    "runtime_contract_id": "local_runtime_contract_v1",
                    "admitted": True,
                    "blocking_reasons": [],
                },
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(nightly_groundtruth.requests, "get", fake_get)
    ok, reason = nightly_groundtruth.verify_api_identity("http://localhost:8001", "")
    assert ok is True
    assert reason == "api_ok:admission=local_lane_admission_v1"


def test_api_identity_smoke_green(monkeypatch) -> None:
    def fake_get(url: str, headers=None, timeout=0):  # noqa: ANN001
        if url.endswith("/identity"):
            return _FakeResponse(
                200,
                {
                    "component": "api",
                    "role": "pipeline_control_plane",
                    "contract_version": "trust_contract_v1",
                    "status_schema_version": "job_status_v1",
                },
            )
        if url.endswith("/readiness"):
            return _FakeResponse(200, {"ready": True, "blocking_reasons": []})
        if url.endswith("/local-lane-admission"):
            return _FakeResponse(
                200,
                {
                    "contract_version": LOCAL_LANE_ADMISSION_VERSION,
                    "runtime_contract_id": "local_runtime_contract_v1",
                    "admitted": True,
                    "blocking_reasons": [],
                },
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(nightly_groundtruth.requests, "get", fake_get)
    packet = nightly_groundtruth.build_api_identity_smoke_packet("http://127.0.0.1:8201")

    assert packet["reason_code"] == "api_identity_green"
    assert packet["safe_to_run"] is True
    assert packet["safe_to_compare"] is True


def test_api_identity_smoke_classifies_process_not_running(monkeypatch) -> None:
    def fake_get(*args, **kwargs):  # noqa: ANN002, ANN003
        raise nightly_groundtruth.requests.exceptions.ConnectionError(
            "No connection could be made because the target machine actively refused it"
        )

    monkeypatch.setattr(nightly_groundtruth.requests, "get", fake_get)
    packet = nightly_groundtruth.build_api_identity_smoke_packet("http://127.0.0.1:8201")

    assert packet["reason_code"] == "api_process_not_running"
    assert packet["safe_to_run"] is False


def test_api_identity_smoke_classifies_openapi_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(nightly_groundtruth.requests, "get", lambda *args, **kwargs: _FakeResponse(404, {}))

    packet = nightly_groundtruth.build_api_identity_smoke_packet("http://127.0.0.1:8201")

    assert packet["reason_code"] == "api_openapi_unavailable"
    assert packet["safe_to_run"] is False


def test_api_identity_smoke_classifies_bridge_shaped_endpoint(monkeypatch) -> None:
    def fake_get(url: str, headers=None, timeout=0):  # noqa: ANN001
        if url.endswith("/identity"):
            return _FakeResponse(
                200,
                {
                    "component": "bridge",
                    "role": "execution_bridge",
                    "contract_version": "trust_contract_v1",
                },
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(nightly_groundtruth.requests, "get", fake_get)
    packet = nightly_groundtruth.build_api_identity_smoke_packet("http://127.0.0.1:8090")

    assert packet["reason_code"] == "api_bridge_shaped_endpoint_detected"
    assert packet["safe_to_run"] is False


def test_api_identity_smoke_classifies_local_lane_admission_red(monkeypatch) -> None:
    def fake_get(url: str, headers=None, timeout=0):  # noqa: ANN001
        if url.endswith("/identity"):
            return _FakeResponse(
                200,
                {
                    "component": "api",
                    "role": "pipeline_control_plane",
                    "contract_version": "trust_contract_v1",
                    "status_schema_version": "job_status_v1",
                },
            )
        if url.endswith("/readiness"):
            return _FakeResponse(200, {"ready": True, "blocking_reasons": []})
        if url.endswith("/local-lane-admission"):
            return _FakeResponse(
                200,
                {
                    "contract_version": LOCAL_LANE_ADMISSION_VERSION,
                    "runtime_contract_id": "local_runtime_contract_v1",
                    "admitted": False,
                    "blocking_reasons": ["bridge_not_ready"],
                },
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(nightly_groundtruth.requests, "get", fake_get)
    packet = nightly_groundtruth.build_api_identity_smoke_packet("http://127.0.0.1:8201")

    assert packet["reason_code"] == "api_local_lane_admission_red"
    assert packet["blocking_reasons"] == ["bridge_not_ready"]
    assert packet["safe_to_run"] is False


def test_strict_local_lane_preflight_fails_when_bridge_admission_is_red(monkeypatch) -> None:
    monkeypatch.setattr(
        nightly_groundtruth,
        "fetch_api_admission",
        lambda api_url, api_key="": {
            "contract_version": "local_lane_admission_v1",
            "runtime_contract_id": "local_runtime_contract_v1",
            "admitted": True,
            "blocking_reasons": [],
        },
    )
    monkeypatch.setattr(
        nightly_groundtruth,
        "fetch_bridge_admission",
        lambda bridge_url, bridge_key="": {
            "contract_version": "local_lane_admission_v1",
            "runtime_contract_id": "local_runtime_contract_v1",
            "admitted": False,
            "blocking_reasons": ["bridge_secret_missing"],
        },
    )

    try:
        nightly_groundtruth.ensure_strict_local_lane_preflight(
            api_url="http://127.0.0.1:8201",
            api_key="",
            bridge_url="http://127.0.0.1:8090",
            bridge_key="secret",
        )
    except RuntimeError as exc:
        assert "bridge_local_lane_admission_red" in str(exc)
        assert "bridge:bridge_secret_missing" in str(exc)
    else:
        raise AssertionError("expected strict local preflight to fail when bridge admission is red")


def test_build_lane_readiness_packet_reports_incompatible_contract() -> None:
    payload = nightly_groundtruth.build_lane_readiness_packet(
        api_identity={
            "component": "api",
            "role": "pipeline_control_plane",
            "contract_version": "trust_contract_v1",
            "pipeline_schema_version": "handoff_contract_v1.0.0",
            "status_schema_version": "job_status_v1",
            "git_sha": "abc",
        },
        bridge_identity={
            "component": "bridge",
            "role": "execution_bridge",
            "contract_version": "trust_contract_v1",
            "capabilities": ["execute"],
            "git_sha": "def",
        },
        api_readiness={"ready": True},
        bridge_readiness={"ready": True},
        freshness={"freshness_verdict": "fresh", "restart_required": False, "restart_performed": False},
    )

    assert payload["ready"] is False
    assert payload["api_bridge_compatible"] is False
    assert "git_sha_mismatch" in payload["blocking_reasons"]
    assert any(reason.startswith("bridge_capability_missing:") for reason in payload["blocking_reasons"])


def test_build_lane_readiness_packet_rejects_runner_api_bridge_sha_mismatch() -> None:
    payload = nightly_groundtruth.build_lane_readiness_packet(
        runner_identity={
            "component": "runner",
            "runner_git_sha": "runner-sha",
            "runner_dirty": False,
            "contract_version": "trust_contract_v1",
        },
        api_identity={
            "component": "api",
            "role": "pipeline_control_plane",
            "contract_version": "trust_contract_v1",
            "pipeline_schema_version": "handoff_contract_v1.0.0",
            "status_schema_version": "job_status_v1",
            "git_sha": "api-sha",
            "dirty": False,
        },
        bridge_identity={
            "component": "bridge",
            "role": "execution_bridge",
            "contract_version": "trust_contract_v1",
            "capabilities": ["execute", "flush_dll_cache"],
            "git_sha": "bridge-sha",
            "dirty": False,
        },
        api_readiness={"ready": True},
        bridge_readiness={"ready": True},
        freshness={"freshness_verdict": "fresh", "restart_required": False, "restart_performed": False},
    )

    assert payload["ready"] is False
    assert payload["lane_comparable"] is False
    assert "runner_api_git_sha_mismatch" in payload["blocking_reasons"]
    assert "runner_bridge_git_sha_mismatch" in payload["blocking_reasons"]
    assert "api_bridge_git_sha_mismatch" in payload["blocking_reasons"]


def test_build_lane_readiness_packet_accepts_matching_runner_api_bridge_identity() -> None:
    payload = nightly_groundtruth.build_lane_readiness_packet(
        runner_identity={
            "component": "runner",
            "runner_git_sha": "same-sha",
            "runner_dirty": False,
            "contract_version": "trust_contract_v1",
        },
        api_identity={
            "component": "api",
            "role": "pipeline_control_plane",
            "contract_version": "trust_contract_v1",
            "pipeline_schema_version": "handoff_contract_v1.0.0",
            "status_schema_version": "job_status_v1",
            "git_sha": "same-sha",
            "dirty": False,
        },
        bridge_identity={
            "component": "bridge",
            "role": "execution_bridge",
            "contract_version": "trust_contract_v1",
            "capabilities": ["execute", "flush_dll_cache"],
            "git_sha": "same-sha",
            "dirty": False,
        },
        api_readiness={"ready": True},
        bridge_readiness={"ready": True},
        freshness={"freshness_verdict": "fresh", "restart_required": False, "restart_performed": False},
    )

    assert payload["ready"] is True
    assert payload["lane_comparable"] is True
    assert payload["blocking_reasons"] == []


def test_build_lane_readiness_packet_requires_explicit_readiness_payloads() -> None:
    payload = nightly_groundtruth.build_lane_readiness_packet(
        api_identity={
            "component": "api",
            "role": "pipeline_control_plane",
            "contract_version": "trust_contract_v1",
            "pipeline_schema_version": "pipeline_v7",
            "status_schema_version": "job_status_v3",
            "git_sha": "abc",
        },
        bridge_identity={
            "component": "bridge",
            "role": "execution_bridge",
            "contract_version": "trust_contract_v1",
            "capabilities": ["execute", "flush_dll_cache"],
            "git_sha": "abc",
        },
        api_readiness=None,
        bridge_readiness=None,
        freshness={"freshness_verdict": "fresh", "restart_required": False, "restart_performed": False},
    )

    assert payload["ready"] is False
    assert "api_readiness_unavailable" in payload["blocking_reasons"]
    assert "bridge_readiness_unavailable" in payload["blocking_reasons"]


def test_resolve_api_url_autodetects_8201_before_8001(monkeypatch) -> None:
    def fake_verify(api_url: str, api_key: str) -> tuple[bool, str]:
        if api_url == "http://127.0.0.1:8201":
            return True, "api_ok:routes=30"
        return False, f"api_health_unreachable:{api_url}"

    resolved_url, reason, source = nightly_groundtruth.resolve_api_url(
        "",
        "",
        env={},
        verify_identity=fake_verify,
    )

    assert resolved_url == "http://127.0.0.1:8201"
    assert source == "auto-detected"
    assert reason == "api_ok:routes=30"


def test_resolve_api_url_rejects_broken_explicit_url_without_falling_back() -> None:
    def fake_verify(api_url: str, api_key: str) -> tuple[bool, str]:
        return False, f"api_health_unreachable:{api_url}"

    try:
        nightly_groundtruth.resolve_api_url(
            "http://localhost:8001",
            "",
            env={},
            verify_identity=fake_verify,
        )
    except RuntimeError as exc:
        assert "api_identity_failed:explicit:http://localhost:8001" in str(exc)
    else:
        raise AssertionError("expected explicit API URL failure to stop resolution")


def test_ensure_local_api_freshness_keeps_fresh_managed_lane(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = "api.routes.main:app --host 0.0.0.0 --port 8201"
    monkeypatch.setattr(
        nightly_groundtruth,
        "_read_local_api_process_info",
        lambda port: {
            "pid": 123,
            "command_line": f"python -m uvicorn {marker}",
            "created_at": 10_000.0,
            "started_at": "1970-01-01T02:46:40Z",
        },
    )
    monkeypatch.setattr(nightly_groundtruth, "_latest_tree_mtime", lambda root: 9_500.0)
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 10_600.0)

    freshness = nightly_groundtruth.ensure_local_api_freshness(
        tmp_path,
        "http://localhost:8201",
    )

    assert freshness["freshness_verdict"] == "fresh"
    assert freshness["restart_required"] is False
    assert freshness["restart_performed"] is False
    assert freshness["is_managed_owner"] is True


def test_ensure_local_api_freshness_restarts_old_managed_lane(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = "api.routes.main:app --host 0.0.0.0 --port 8201"
    monkeypatch.setattr(
        nightly_groundtruth,
        "_read_local_api_process_info",
        lambda port: {
            "pid": 123,
            "command_line": f"python -m uvicorn {marker}",
            "created_at": 1_000.0,
            "started_at": "1970-01-01T00:16:40Z",
        },
    )
    monkeypatch.setattr(nightly_groundtruth, "_latest_tree_mtime", lambda root: 900.0)
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 1_000.0 + 18_001.0)
    monkeypatch.setattr(
        nightly_groundtruth,
        "relaunch_local_api_lane",
        lambda repo_root, api_url, api_key, campaign_log=None: {
            "restart_performed": True,
            "post_restart_identity": "api_ok:test",
            "post_restart_owner": {
                "pid": 456,
                "command_line": f"python -m uvicorn {marker}",
                "created_at": 20_000.0,
                "started_at": "1970-01-01T05:33:20Z",
            },
        },
    )

    freshness = nightly_groundtruth.ensure_local_api_freshness(
        tmp_path,
        "http://localhost:8201",
    )

    assert freshness["freshness_verdict"] == "restart_required_age"
    assert freshness["restart_required"] is True
    assert freshness["restart_performed"] is True
    assert freshness["api_process"]["pid"] == 456


def test_ensure_local_api_freshness_restarts_when_code_is_newer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = "api.routes.main:app --host 0.0.0.0 --port 8201"
    monkeypatch.setattr(
        nightly_groundtruth,
        "_read_local_api_process_info",
        lambda port: {
            "pid": 123,
            "command_line": f"python -m uvicorn {marker}",
            "created_at": 10_000.0,
            "started_at": "1970-01-01T02:46:40Z",
        },
    )
    monkeypatch.setattr(nightly_groundtruth, "_latest_tree_mtime", lambda root: 10_100.0)
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 10_200.0)
    monkeypatch.setattr(
        nightly_groundtruth,
        "relaunch_local_api_lane",
        lambda repo_root, api_url, api_key, campaign_log=None: {
            "restart_performed": True,
            "post_restart_identity": "api_ok:test",
            "post_restart_owner": {
                "pid": 789,
                "command_line": f"python -m uvicorn {marker}",
                "created_at": 10_300.0,
                "started_at": "1970-01-01T02:51:40Z",
            },
        },
    )

    freshness = nightly_groundtruth.ensure_local_api_freshness(
        tmp_path,
        "http://127.0.0.1:8201",
    )

    assert freshness["freshness_verdict"] == "restart_required_code_newer"
    assert freshness["restart_required"] is True
    assert freshness["restart_performed"] is True


def test_ensure_local_api_freshness_restarts_when_identity_git_sha_is_stale(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = "api.routes.main:app --host 0.0.0.0 --port 8201"
    monkeypatch.setattr(
        nightly_groundtruth,
        "_read_local_api_process_info",
        lambda port: {
            "pid": 123,
            "command_line": f"python -m uvicorn {marker}",
            "created_at": 10_000.0,
            "started_at": "1970-01-01T02:46:40Z",
        },
    )
    monkeypatch.setattr(nightly_groundtruth, "_latest_tree_mtime", lambda root: 9_500.0)
    monkeypatch.setattr(nightly_groundtruth, "_current_repo_git_sha", lambda repo_root: "new-sha")
    identities = iter([{"git_sha": "old-sha"}, {"git_sha": "new-sha"}])
    monkeypatch.setattr(nightly_groundtruth, "fetch_api_identity", lambda api_url, api_key="": next(identities))
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 10_200.0)
    monkeypatch.setattr(
        nightly_groundtruth,
        "relaunch_local_api_lane",
        lambda repo_root, api_url, api_key, campaign_log=None: {
            "restart_performed": True,
            "post_restart_identity": "api_ok:test",
            "post_restart_owner": {
                "pid": 456,
                "command_line": f"python -m uvicorn {marker}",
                "created_at": 10_300.0,
                "started_at": "1970-01-01T02:51:40Z",
            },
        },
    )

    freshness = nightly_groundtruth.ensure_local_api_freshness(
        tmp_path,
        "http://127.0.0.1:8201",
    )

    assert freshness["freshness_verdict"] == "restart_required_git_sha_mismatch"
    assert freshness["restart_required"] is True
    assert freshness["restart_performed"] is True
    assert freshness["identity_git_sha"] == "new-sha"
    assert freshness["identity_git_sha_matched"] is True


def test_ensure_local_api_freshness_suppresses_stale_identity_restart_when_requested(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = "api.routes.main:app --host 0.0.0.0 --port 8201"
    monkeypatch.setattr(
        nightly_groundtruth,
        "_read_local_api_process_info",
        lambda port: {
            "pid": 123,
            "command_line": f"python -m uvicorn {marker}",
            "created_at": 10_000.0,
            "started_at": "1970-01-01T02:46:40Z",
        },
    )
    monkeypatch.setattr(nightly_groundtruth, "_latest_tree_mtime", lambda root: 9_500.0)
    monkeypatch.setattr(nightly_groundtruth, "_current_repo_git_sha", lambda repo_root: "new-sha")
    monkeypatch.setattr(nightly_groundtruth, "fetch_api_identity", lambda api_url, api_key="": {"git_sha": "old-sha"})
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 10_200.0)

    freshness = nightly_groundtruth.ensure_local_api_freshness(
        tmp_path,
        "http://127.0.0.1:8201",
        allow_relaunch=False,
    )

    assert freshness["freshness_verdict"] == "restart_suppressed_git_sha_mismatch"
    assert freshness["restart_required"] is True
    assert freshness["restart_performed"] is False
    assert freshness["restart_suppressed"] is True


def test_ensure_local_api_freshness_restarts_when_bridge_was_restarted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = "api.routes.main:app --host 0.0.0.0 --port 8201"
    monkeypatch.setattr(
        nightly_groundtruth,
        "_read_local_api_process_info",
        lambda port: {
            "pid": 123,
            "command_line": f"python -m uvicorn {marker}",
            "created_at": 10_000.0,
            "started_at": "1970-01-01T02:46:40Z",
        },
    )
    monkeypatch.setattr(nightly_groundtruth, "_latest_tree_mtime", lambda root: 9_500.0)
    monkeypatch.setattr(nightly_groundtruth, "_current_repo_git_sha", lambda repo_root: "same-sha")
    monkeypatch.setattr(nightly_groundtruth, "fetch_api_identity", lambda api_url, api_key="": {"git_sha": "same-sha"})
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 10_200.0)
    monkeypatch.setattr(
        nightly_groundtruth,
        "relaunch_local_api_lane",
        lambda repo_root, api_url, api_key, campaign_log=None: {
            "restart_performed": True,
            "post_restart_identity": "api_ok:test",
            "post_restart_owner": {
                "pid": 456,
                "command_line": f"python -m uvicorn {marker}",
                "created_at": 10_300.0,
                "started_at": "1970-01-01T02:51:40Z",
            },
        },
    )

    freshness = nightly_groundtruth.ensure_local_api_freshness(
        tmp_path,
        "http://127.0.0.1:8201",
        force_restart_reason="restart_required_bridge_restarted",
    )

    assert freshness["freshness_verdict"] == "restart_required_bridge_restarted"
    assert freshness["restart_required"] is True
    assert freshness["restart_performed"] is True
    assert freshness["force_restart_reason"] == "restart_required_bridge_restarted"


def test_ensure_local_bridge_freshness_restarts_when_contract_routes_are_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = "scripts\\bridge\\gui_bridge.py"
    monkeypatch.setattr(
        nightly_groundtruth,
        "_read_local_bridge_process_info",
        lambda port: {
            "pid": 321,
            "command_line": f"python {marker}",
            "created_at": 10_000.0,
            "started_at": "1970-01-01T02:46:40Z",
        },
    )
    monkeypatch.setattr(nightly_groundtruth, "_latest_tree_mtime", lambda root: 9_500.0)
    monkeypatch.setattr(nightly_groundtruth, "fetch_bridge_identity", lambda bridge_url, bridge_key="": None)
    monkeypatch.setattr(nightly_groundtruth, "fetch_bridge_readiness", lambda bridge_url, bridge_key="": None)
    monkeypatch.setattr(
        nightly_groundtruth,
        "relaunch_local_bridge_lane",
        lambda repo_root, bridge_url, bridge_key, campaign_log=None: {
            "restart_performed": True,
            "post_restart_identity": "bridge_ok:test",
            "post_restart_owner": {
                "pid": 654,
                "command_line": f"python {marker}",
                "created_at": 20_000.0,
                "started_at": "1970-01-01T05:33:20Z",
            },
        },
    )
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 10_600.0)

    freshness = nightly_groundtruth.ensure_local_bridge_freshness(
        tmp_path,
        "http://localhost:8090",
        "secret",
    )

    assert freshness["freshness_verdict"] == "restart_required_contract_missing"
    assert freshness["restart_required"] is True
    assert freshness["restart_performed"] is True
    assert freshness["bridge_process"]["pid"] == 654


def test_ensure_local_bridge_freshness_restarts_when_identity_git_sha_is_stale(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = "scripts\\bridge\\gui_bridge.py"
    monkeypatch.setattr(
        nightly_groundtruth,
        "_read_local_bridge_process_info",
        lambda port: {
            "pid": 321,
            "command_line": f"python {marker}",
            "created_at": 10_000.0,
            "started_at": "1970-01-01T02:46:40Z",
        },
    )
    monkeypatch.setattr(nightly_groundtruth, "_latest_tree_mtime", lambda root: 9_500.0)
    monkeypatch.setattr(nightly_groundtruth, "_current_repo_git_sha", lambda repo_root: "new-sha")
    identities = iter([{"git_sha": "old-sha"}, {"git_sha": "new-sha"}])
    monkeypatch.setattr(nightly_groundtruth, "fetch_bridge_identity", lambda bridge_url, bridge_key="": next(identities))
    monkeypatch.setattr(nightly_groundtruth, "fetch_bridge_readiness", lambda bridge_url, bridge_key="": {"ready": True})
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 10_200.0)
    monkeypatch.setattr(
        nightly_groundtruth,
        "relaunch_local_bridge_lane",
        lambda repo_root, bridge_url, bridge_key, campaign_log=None: {
            "restart_performed": True,
            "post_restart_identity": "bridge_ok:test",
            "post_restart_owner": {
                "pid": 654,
                "command_line": f"python {marker}",
                "created_at": 10_300.0,
                "started_at": "1970-01-01T02:51:40Z",
            },
        },
    )

    freshness = nightly_groundtruth.ensure_local_bridge_freshness(
        tmp_path,
        "http://localhost:8090",
        "secret",
    )

    assert freshness["freshness_verdict"] == "restart_required_git_sha_mismatch"
    assert freshness["restart_required"] is True
    assert freshness["restart_performed"] is True
    assert freshness["identity_git_sha"] == "new-sha"
    assert freshness["identity_git_sha_matched"] is True


def test_ensure_local_bridge_freshness_blocks_unmanaged_stale_identity_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        nightly_groundtruth,
        "_read_local_bridge_process_info",
        lambda port: {
            "pid": 321,
            "command_line": "python other_bridge.py",
            "created_at": 10_000.0,
            "started_at": "1970-01-01T02:46:40Z",
        },
    )
    monkeypatch.setattr(nightly_groundtruth, "_latest_tree_mtime", lambda root: 9_500.0)
    monkeypatch.setattr(nightly_groundtruth, "_current_repo_git_sha", lambda repo_root: "new-sha")
    monkeypatch.setattr(nightly_groundtruth, "fetch_bridge_identity", lambda bridge_url, bridge_key="": {"git_sha": "old-sha"})
    monkeypatch.setattr(nightly_groundtruth, "fetch_bridge_readiness", lambda bridge_url, bridge_key="": {"ready": True})
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 10_200.0)

    freshness = nightly_groundtruth.ensure_local_bridge_freshness(
        tmp_path,
        "http://localhost:8090",
        "secret",
    )

    assert freshness["freshness_verdict"] == "restart_blocked_unmanaged_owner"
    assert freshness["restart_required"] is True
    assert freshness["restart_performed"] is False
    assert freshness["identity_git_sha_matched"] is False


def test_ensure_local_bridge_freshness_blocks_unmanaged_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        nightly_groundtruth,
        "_read_local_bridge_process_info",
        lambda port: {
            "pid": 321,
            "command_line": "python other_bridge.py",
            "created_at": 10_000.0,
            "started_at": "1970-01-01T02:46:40Z",
        },
    )
    monkeypatch.setattr(nightly_groundtruth, "_latest_tree_mtime", lambda root: 9_500.0)
    monkeypatch.setattr(nightly_groundtruth, "fetch_bridge_identity", lambda bridge_url, bridge_key="": None)
    monkeypatch.setattr(nightly_groundtruth, "fetch_bridge_readiness", lambda bridge_url, bridge_key="": None)
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 10_600.0)

    freshness = nightly_groundtruth.ensure_local_bridge_freshness(
        tmp_path,
        "http://localhost:8090",
        "secret",
    )

    assert freshness["freshness_verdict"] == "restart_blocked_unmanaged_owner"
    assert freshness["restart_required"] is True
    assert freshness["restart_performed"] is False
    assert freshness["bridge_process"]["pid"] == 321


def test_ensure_local_api_freshness_skips_nonlocal_urls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        nightly_groundtruth,
        "_read_local_api_process_info",
        lambda port: (_ for _ in ()).throw(AssertionError("should not inspect local pid")),
    )

    freshness = nightly_groundtruth.ensure_local_api_freshness(
        tmp_path,
        "https://example.com/api",
    )

    assert freshness["freshness_verdict"] == "restart_skipped_nonlocal"
    assert freshness["restart_required"] is False
    assert freshness["restart_performed"] is False


def test_ensure_local_api_freshness_blocks_unmanaged_stale_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        nightly_groundtruth,
        "_read_local_api_process_info",
        lambda port: {
            "pid": 321,
            "command_line": "python other_service.py",
            "created_at": 1_000.0,
            "started_at": "1970-01-01T00:16:40Z",
        },
    )
    monkeypatch.setattr(nightly_groundtruth, "_latest_tree_mtime", lambda root: 1_500.0)
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 2_000.0)

    freshness = nightly_groundtruth.ensure_local_api_freshness(
        tmp_path,
        "http://localhost:8201",
    )

    assert freshness["freshness_verdict"] == "restart_blocked_unmanaged_owner"
    assert freshness["restart_required"] is True
    assert freshness["restart_performed"] is False


def test_wait_job_keeps_polling_when_awaiting_clarification_is_still_running(monkeypatch) -> None:
    states = iter(
        [
            {
                "status": "running",
                "explore_phase": "awaiting_clarification",
                "updated_at": 1.0,
            },
            {
                "status": "done",
                "explore_phase": "done",
                "updated_at": 2.0,
            },
        ]
    )

    class FakeClient:
        def get(self, path: str, timeout: int = 60):  # noqa: ANN001
            assert path == "/api/jobs/job-1"
            return next(states)

    monkeypatch.setattr(nightly_groundtruth.time, "sleep", lambda _seconds: None)

    finished = nightly_groundtruth.wait_job(
        FakeClient(),
        "job-1",
        phase="explore",
        timeout_sec=5,
        poll_sec=0,
        stuck_seconds=5,
    )

    assert finished["status"] == "done"
    assert finished["explore_phase"] == "done"


def test_wait_job_accepts_macro_verdict_awaiting_clarification_as_terminal(monkeypatch) -> None:
    states = iter(
        [
            {
                "status": "running",
                "explore_phase": "awaiting_clarification",
                "macro_verdict": {"status": "awaiting_clarification"},
                "updated_at": 1.0,
            },
        ]
    )

    class FakeClient:
        def get(self, path: str, timeout: int = 60):  # noqa: ANN001
            assert path == "/api/jobs/job-1"
            return next(states)

    monkeypatch.setattr(nightly_groundtruth.time, "sleep", lambda _seconds: None)

    finished = nightly_groundtruth.wait_job(
        FakeClient(),
        "job-1",
        phase="explore",
        timeout_sec=5,
        poll_sec=0,
        stuck_seconds=5,
    )

    assert finished["status"] == "running"
    assert finished["explore_phase"] == "awaiting_clarification"
    assert finished["macro_verdict"]["status"] == "awaiting_clarification"


def test_wait_job_does_not_accept_done_phase_without_terminal_status(monkeypatch) -> None:
    states = iter(
        [
            {
                "status": "running",
                "explore_phase": "done",
                "explore_stage": "s06_gaps",
                "explore_message": "Finalizing harmonized state...",
                "updated_at": 1.0,
            },
            {
                "status": "done",
                "explore_phase": "done",
                "explore_stage": "done",
                "explore_message": "Complete",
                "updated_at": 2.0,
            },
        ]
    )

    class FakeClient:
        def get(self, path: str, timeout: int = 60):  # noqa: ANN001
            assert path == "/api/jobs/job-1"
            return next(states)

    monkeypatch.setattr(nightly_groundtruth.time, "sleep", lambda _seconds: None)

    finished = nightly_groundtruth.wait_job(
        FakeClient(),
        "job-1",
        phase="explore",
        timeout_sec=5,
        poll_sec=0,
        stuck_seconds=5,
    )

    assert finished["status"] == "done"
    assert finished["explore_phase"] == "done"


def test_wait_job_classifies_quasi_terminal_clarify_stall(monkeypatch) -> None:
    states = iter(
        [
            {
                "status": "running",
                "explore_phase": "awaiting_clarification",
                "explore_stage": "s06_gaps",
                "explore_message": "Finalizing harmonized state...",
                "explore_progress": "1/1",
                "updated_at": 1.0,
            },
            {
                "status": "running",
                "explore_phase": "awaiting_clarification",
                "explore_stage": "s06_gaps",
                "explore_message": "Finalizing harmonized state...",
                "explore_progress": "1/1",
                "updated_at": 2.0,
            },
        ]
    )

    class FakeClient:
        def get(self, path: str, timeout: int = 60):  # noqa: ANN001
            assert path == "/api/jobs/job-1"
            return next(states)

    clock = {"t": 0.0}

    def fake_time() -> float:
        current = clock["t"]
        clock["t"] += 61.0
        return current

    monkeypatch.setattr(nightly_groundtruth.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(nightly_groundtruth.time, "time", fake_time)

    try:
        nightly_groundtruth.wait_job(
            FakeClient(),
            "job-1",
            phase="explore",
            timeout_sec=500,
            poll_sec=0,
            stuck_seconds=60,
        )
    except nightly_groundtruth.QuasiTerminalClarifyStall as exc:
        assert exc.job_id == "job-1"
        assert exc.status_payload["explore_stage"] == "s06_gaps"
    else:
        raise AssertionError("expected quasi-terminal clarify stall")


def test_wait_job_emits_live_checkpoint_observation_with_soft_stall(monkeypatch) -> None:
    states = iter(
        [
            {
                "job_id": "job-1",
                "status": "running",
                "explore_phase": "exploring",
                "explore_stage": "s07_finalize",
                "explore_message": "Finalizing harmonized state...",
                "explore_progress": "1/1",
                "updated_at": 1.0,
            },
            {
                "job_id": "job-1",
                "status": "done",
                "explore_phase": "done",
                "explore_stage": "s07_finalize",
                "explore_message": "done",
                "explore_progress": "1/1",
                "updated_at": 2.0,
            },
        ]
    )
    observations: list[dict] = []

    class FakeClient:
        def get(self, path: str, timeout: int = 60):  # noqa: ANN001
            assert path == "/api/jobs/job-1"
            return next(states)

    clock = {"t": 0.0}

    def fake_time() -> float:
        current = clock["t"]
        clock["t"] += 61.0
        return current

    monkeypatch.setattr(nightly_groundtruth.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(nightly_groundtruth.time, "time", fake_time)

    finished = nightly_groundtruth.wait_job(
        FakeClient(),
        "job-1",
        phase="explore",
        timeout_sec=500,
        poll_sec=0,
        stuck_seconds=500,
        observation_cb=lambda observation: observations.append(dict(observation)),
        soft_stall_seconds=60,
    )

    assert finished["status"] == "done"
    assert observations
    assert observations[0]["stage"] == "s07_finalize"
    assert observations[0]["message"] == "Finalizing harmonized state..."
    assert observations[0]["signature_stable_seconds"] >= 60
    assert observations[0]["soft_stall_hint"] == "s07_finalization_no_close"
    assert observations[0]["claim_ceiling"] == "live_observation_only"


def test_live_checkpoint_observation_reports_s07_span_soft_stall(monkeypatch) -> None:
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 100.0)
    observation = nightly_groundtruth.build_live_checkpoint_observation(
        {
            "job_id": "job-1",
            "status": "running",
            "explore_phase": "exploring",
            "explore_stage": "s07_finalize",
            "explore_span": "s07_harmonize_promote_findings",
            "explore_span_state": "start",
            "explore_span_message": "S-07 harmonize: evaluating direct-truth promotions...",
            "explore_span_updated_at": 30.0,
            "explore_message": "S-07 harmonize: evaluating direct-truth promotions...",
            "explore_progress": "1/1",
            "updated_at": 30.0,
        },
        job_id="job-1",
        phase="explore",
        elapsed_seconds=75.0,
        status_age_seconds=70.0,
        status_stability_seconds=70.0,
        signature_stable_seconds=70.0,
        soft_stall_seconds=60,
    )

    assert observation["stage"] == "s07_finalize"
    assert observation["span"] == "s07_harmonize_promote_findings"
    assert observation["span_state"] == "start"
    assert observation["span_stable_seconds"] == 70.0
    assert observation["soft_stall_hint"] == "s07_harmonize_promote_findings_no_close"
    line = nightly_groundtruth.live_checkpoint_observation_line(observation)
    assert "span=s07_harmonize_promote_findings" in line
    assert "span_stable=70.0s" in line


def test_record_live_checkpoint_observation_updates_heartbeat_and_log(tmp_path: Path, capsys) -> None:
    observation = {
        "job_id": "job-1",
        "phase": "explore",
        "explore_phase": "exploring",
        "stage": "s07_finalize",
        "span": "s07_harmonize_promote_findings",
        "span_state": "start",
        "span_stable_seconds": 61.0,
        "message": "Finalizing harmonized state...",
        "progress": "1/1",
        "elapsed_seconds": 90.0,
        "signature_stable_seconds": 61.0,
        "soft_stall_hint": "s07_harmonize_promote_findings_no_close",
    }

    nightly_groundtruth.record_live_checkpoint_observation(
        observation,
        heartbeat_path=tmp_path / "heartbeats.json",
        lane_id="lane-1",
        run_id="01-session_bootstrap",
        status="explore",
        job_id="job-1",
        campaign_log=tmp_path / "compiled-ingest.log",
    )

    heartbeats = json.loads((tmp_path / "heartbeats.json").read_text(encoding="utf-8"))
    details = heartbeats["lane-1"]["details"]
    assert details["last_observation"]["stage"] == "s07_finalize"
    assert details["last_observation"]["span"] == "s07_harmonize_promote_findings"
    assert details["last_observation"]["soft_stall_hint"] == "s07_harmonize_promote_findings_no_close"
    log_text = (tmp_path / "compiled-ingest.log").read_text(encoding="utf-8")
    assert "checkpoint-observer" in log_text
    stdout = capsys.readouterr().out
    assert "span=s07_harmonize_promote_findings" in stdout
    assert "soft_stall_hint=s07_harmonize_promote_findings_no_close" in stdout


def test_wait_job_recovers_terminal_done_after_transport_reset(monkeypatch) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.status_calls = 0

        def get(self, path: str, timeout: int = 60):  # noqa: ANN001
            if path == "/api/jobs/job-1":
                self.status_calls += 1
                if self.status_calls == 1:
                    return {
                        "job_id": "job-1",
                        "status": "running",
                        "explore_phase": "exploring",
                        "explore_stage": "s07_finalize",
                        "explore_message": "Finalize complete - awaiting macro verdict persistence",
                        "explore_progress": "1/1",
                        "updated_at": 1.0,
                    }
                raise nightly_groundtruth.requests.ConnectionError("connection reset by peer")
            if path == "/api/jobs/job-1/terminalization":
                return {
                    "job_id": "job-1",
                    "terminal": True,
                    "terminalization_kind": "done",
                    "reason": {"code": "job_completed_done", "message": "Complete - done (100.0% coverage)"},
                }
            raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(nightly_groundtruth.time, "sleep", lambda _seconds: None)

    finished = nightly_groundtruth.wait_job(
        FakeClient(),
        "job-1",
        phase="explore",
        timeout_sec=5,
        poll_sec=0,
        stuck_seconds=5,
    )

    assert finished["status"] == "done"
    assert finished["explore_phase"] == "done"
    assert finished["_transport_recovered_terminalization_kind"] == "done"


def test_wait_job_recovers_terminal_done_after_stale_s07_stuck_readthrough(monkeypatch) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.status_calls = 0

        def get(self, path: str, timeout: int = 60):  # noqa: ANN001
            assert path == "/api/jobs/job-1"
            self.status_calls += 1
            if self.status_calls == 1:
                return {
                    "job_id": "job-1",
                    "status": "running",
                    "explore_phase": "exploring",
                    "explore_stage": "s07_finalize",
                    "explore_message": "S-07 harmonize: loaded 3 probe rows.",
                    "explore_progress": "1/1",
                    "updated_at": 0.0,
                }
            return {
                "job_id": "job-1",
                "status": "done",
                "explore_phase": "done",
                "explore_stage": "s07_finalize",
                "explore_message": "done",
                "explore_progress": "1/1",
                "updated_at": 2.0,
            }

    clock = {"t": 0.0}

    def fake_time() -> float:
        current = clock["t"]
        clock["t"] += 61.0
        return current

    monkeypatch.setattr(nightly_groundtruth.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(nightly_groundtruth.time, "time", fake_time)

    finished = nightly_groundtruth.wait_job(
        FakeClient(),
        "job-1",
        phase="explore",
        timeout_sec=500,
        poll_sec=0,
        stuck_seconds=60,
    )

    assert finished["status"] == "done"
    assert finished["explore_phase"] == "done"


def test_wait_job_stale_s07_readthrough_remains_fail_closed_when_nonterminal(monkeypatch) -> None:
    class FakeClient:
        def get(self, path: str, timeout: int = 60):  # noqa: ANN001
            if path == "/api/jobs/job-1":
                return {
                    "job_id": "job-1",
                    "status": "running",
                    "explore_phase": "exploring",
                    "explore_stage": "s07_finalize",
                    "explore_message": "S-07 harmonize: loaded 3 probe rows.",
                    "explore_progress": "1/1",
                    "updated_at": 0.0,
                }
            if path.startswith("/api/jobs/job-1/terminalization"):
                return {
                    "job_id": "job-1",
                    "terminal": False,
                    "terminalization_kind": "",
                    "reason": {"code": "job_nonterminal", "message": "still running"},
                }
            raise AssertionError(f"unexpected path: {path}")

    clock = {"t": 0.0}

    def fake_time() -> float:
        current = clock["t"]
        clock["t"] += 61.0
        return current

    monkeypatch.setattr(nightly_groundtruth.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(nightly_groundtruth.time, "time", fake_time)

    try:
        nightly_groundtruth.wait_job(
            FakeClient(),
            "job-1",
            phase="explore",
            timeout_sec=500,
            poll_sec=0,
            stuck_seconds=60,
        )
    except TimeoutError as exc:
        assert "stuck" in str(exc)
    else:
        raise AssertionError("expected stale nonterminal status to remain fail-closed")


def test_resolve_job_terminalization_retries_transport_error(monkeypatch) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, path: str, timeout: int = 60):  # noqa: ANN001
            assert path == "/api/jobs/job-1/terminalization"
            self.calls += 1
            if self.calls == 1:
                raise nightly_groundtruth.requests.ConnectionError("connection reset by peer")
            return {
                "job_id": "job-1",
                "terminal": True,
                "terminalization_kind": "done",
                "reason": {"code": "job_completed_done", "message": "done"},
            }

    monkeypatch.setattr(nightly_groundtruth.time, "sleep", lambda _seconds: None)

    payload = nightly_groundtruth.resolve_job_terminalization(
        FakeClient(),
        "job-1",
        status_payload={"job_id": "job-1", "status": "running", "explore_phase": "exploring"},
    )

    assert payload["source"] == "api_contract"
    assert payload["kind"] == "done"


def test_wait_job_nonmatching_stall_remains_generic_timeout(monkeypatch) -> None:
    states = iter(
        [
            {
                "status": "running",
                "explore_phase": "running",
                "explore_stage": "s02_probe",
                "explore_message": "still exploring",
                "explore_progress": "0/1",
                "updated_at": 1.0,
            },
            {
                "status": "running",
                "explore_phase": "running",
                "explore_stage": "s02_probe",
                "explore_message": "still exploring",
                "explore_progress": "0/1",
                "updated_at": 1.0,
            },
        ]
    )

    class FakeClient:
        def get(self, path: str, timeout: int = 60):  # noqa: ANN001
            if path.startswith("/api/jobs/job-1/terminalization"):
                return {
                    "job_id": "job-1",
                    "terminal": False,
                    "terminalization_kind": "",
                    "reason": {"code": "job_nonterminal", "message": "still running"},
                }
            assert path == "/api/jobs/job-1"
            return next(states)

    clock = {"t": 0.0}

    def fake_time() -> float:
        current = clock["t"]
        clock["t"] += 61.0
        return current

    monkeypatch.setattr(nightly_groundtruth.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(nightly_groundtruth.time, "time", fake_time)

    try:
        nightly_groundtruth.wait_job(
            FakeClient(),
            "job-1",
            phase="explore",
            timeout_sec=500,
            poll_sec=0,
            stuck_seconds=60,
        )
    except nightly_groundtruth.QuasiTerminalClarifyStall as exc:  # pragma: no cover - explicit failure path
        raise AssertionError(f"unexpected quasi-terminal classification: {exc}") from exc
    except TimeoutError as exc:
        assert "stuck" in str(exc)
    else:
        raise AssertionError("expected generic timeout")


def test_resolve_job_terminalization_prefers_api_contract() -> None:
    class FakeClient:
        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-1/terminalization":
                return {
                    "job_id": "job-1",
                    "terminal": True,
                    "terminalization_kind": "done",
                    "reason": {"code": "job_completed_done", "message": "done"},
                }
            raise AssertionError(f"unexpected path: {path}")

    payload = nightly_groundtruth.resolve_job_terminalization(FakeClient(), "job-1", status_payload={"status": "done"})
    assert payload["source"] == "api_contract"
    assert payload["kind"] == "done"
    assert payload["terminalization_kind"] == "done"


def test_resolve_job_terminalization_falls_back_when_route_missing() -> None:
    class FakeClient:
        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            response = _FakeResponse(404, {"detail": "not found"})
            raise nightly_groundtruth.requests.HTTPError(response=response)

    payload = nightly_groundtruth.resolve_job_terminalization(
        FakeClient(),
        "job-1",
        status_payload={
            "job_id": "job-1",
            "status": "running",
            "explore_phase": "awaiting_clarification",
            "explore_stage": "s06_gaps",
            "explore_message": "Finalizing harmonized state...",
            "explore_progress": "1/1",
            "updated_at": 1.0,
        },
        observed_stable_for_seconds=120,
    )
    assert payload["source"] == "runner_fallback"
    assert payload["kind"] == "quasi_terminal_stall"
    assert payload["terminalization_kind"] == "quasi_terminal_stall"


def test_build_run_authority_payload_decision_bearing() -> None:
    payload = nightly_groundtruth.build_run_authority_payload(
        run_id="hard-01-rerun-15",
        job_id="job-1",
        lane_readiness={"ready": True},
        terminalization={"terminalization_kind": "done"},
        valid_run=True,
        session_capture_complete=True,
        verdict_status="done",
        job_status="done",
        save_session_exit=0,
        save_session_timed_out=False,
    )

    assert payload["authoritative_proving"] is True
    assert payload["authority_level"] == "decision_bearing"
    assert payload["failure_domain"] == ""
    assert payload["safe_to_steer_next_prompt"] is True


def test_build_run_authority_payload_review_only_for_authoritative_clarification() -> None:
    payload = nightly_groundtruth.build_run_authority_payload(
        run_id="hard-01-rerun-15",
        job_id="job-1",
        lane_readiness={"ready": True},
        terminalization={"terminalization_kind": "awaiting_clarification_authoritative"},
        valid_run=True,
        session_capture_complete=True,
        verdict_status="awaiting_clarification",
        job_status="running",
    )

    assert payload["authoritative_proving"] is False
    assert payload["authority_level"] == "review_only"
    assert payload["failure_domain"] == "pipeline"
    assert payload["safe_to_steer_next_prompt"] is False


def test_build_run_authority_payload_classifies_session_capture_failure() -> None:
    payload = nightly_groundtruth.build_run_authority_payload(
        run_id="hard-01-rerun-15",
        job_id="job-1",
        lane_readiness={"ready": True},
        terminalization={"terminalization_kind": "done"},
        valid_run=False,
        session_capture_complete=False,
        verdict_status="done",
        job_status="done",
        save_session_exit=1,
    )

    assert payload["authoritative_proving"] is False
    assert payload["authority_level"] == "non_authoritative"
    assert payload["failure_domain"] == "session_capture"


def test_post_restart_readiness_probe_reports_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-1"

        def post_json(self, path: str, payload: dict, timeout: int = 0):  # noqa: ANN001
            return {}

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-1/terminalization":
                return {
                    "job_id": "job-1",
                    "terminal": True,
                    "terminalization_kind": "done",
                    "reason": {"code": "job_completed_done", "message": "done"},
                }
            raise AssertionError(f"unexpected client path: {path}")

    wait_states = iter(
        [
            {"status": "done", "result": {"invocables": [{"name": "SP_OpenOperatorSession", "kind": "export"}]}},
            {
                "status": "done",
                "explore_phase": "done",
                "explore_stage": "s07_finalize",
                "explore_message": "done",
                "explore_progress": "1/1",
                "updated_at": 2.0,
            },
        ]
    )

    monkeypatch.setattr(nightly_groundtruth, "wait_job", lambda *args, **kwargs: next(wait_states))

    readiness = nightly_groundtruth.run_post_restart_readiness_probe(
        FakeClient(),
        tmp_path,
        tmp_path / "out",
        "http://localhost:8201",
        "",
        tmp_path / "session_bootstrap.dll",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    assert readiness["performed"] is True
    assert readiness["ready"] is True
    assert readiness["verdict"] == "ready"
    assert (tmp_path / "out" / "post-restart-readiness.json").exists()


def test_discovery_output_authority_classifies_output_persistence_gap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_path = tmp_path / "spectrum_reservation_stage.dll"
    dll_path.write_bytes(b"fake-pe")
    monkeypatch.setattr(
        discovery,
        "_inspect_pe_exports",
        lambda _path: {"available": True, "exports": ["SP_IssueReleaseHold"], "error": ""},
    )

    authority = discovery._build_discovery_output_authority(
        job_id="job-empty",
        binary_path=dll_path,
        out_dir=tmp_path / "empty-out",
        analysis_profile="strict_dll",
        returncode=0,
        output_files=[],
        invocable_count=0,
    )

    assert authority["status"] == "non_comparable_discovery_failure"
    assert authority["reason_code"] == "output_persistence_gap"
    assert authority["owner"] == "discovery_output_persistence"
    assert authority["exports_detected"] == ["SP_IssueReleaseHold"]
    assert authority["safe_to_compare"] is False


def test_discovery_output_authority_classifies_zero_invocable_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_path = tmp_path / "spectrum_reservation_stage.dll"
    dll_path.write_bytes(b"fake-pe")
    output_file = tmp_path / "reservation_mcp.json"
    output_file.write_text(json.dumps({"invocables": []}), encoding="utf-8")
    monkeypatch.setattr(
        discovery,
        "_inspect_pe_exports",
        lambda _path: {"available": True, "exports": ["SP_IssueReleaseHold"], "error": ""},
    )

    authority = discovery._build_discovery_output_authority(
        job_id="job-zero",
        binary_path=dll_path,
        out_dir=tmp_path,
        analysis_profile="strict_dll",
        returncode=0,
        output_files=[output_file],
        invocable_count=0,
    )

    assert authority["reason_code"] == "unsupported_or_unparsed_dll_shape"
    assert authority["owner"] == "discovery_extractor"
    assert authority["discovery_files_found"] == ["reservation_mcp.json"]
    assert authority["safe_to_compare"] is False


def test_discovery_output_authority_classifies_subprocess_interrupt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_path = tmp_path / "spectrum_reservation_stage.dll"
    dll_path.write_bytes(b"fake-pe")
    monkeypatch.setattr(
        discovery,
        "_inspect_pe_exports",
        lambda _path: {"available": True, "exports": ["SP_IssueReleaseHold"], "error": ""},
    )

    authority = discovery._build_discovery_output_authority(
        job_id="job-interrupt",
        binary_path=dll_path,
        out_dir=tmp_path / "empty-out",
        analysis_profile="strict_dll",
        returncode=0xC000013A,
        stderr=(
            'File "C:\\Python311\\Lib\\subprocess.py", line 1579, in _communicate\n'
            "    self.stdout_thread.join(self._remaining_time(endtime))\n"
            'File "C:\\Python311\\Lib\\threading.py", line 1132, in _wait_for_tstate_lock\n'
            "KeyboardInterrupt\n"
        ),
        output_files=[],
        invocable_count=0,
        child_pid=123,
        parent_pid=456,
        command=["python", "src/discovery/main.py", "--dll", str(dll_path)],
        cwd=str(tmp_path),
        env_overrides={"PYTHONPATH": "src/discovery"},
        process_lifetime_sec=9.73,
    )

    assert authority["reason_code"] == "discovery_subprocess_interrupt"
    assert authority["owner"] == "discovery_subprocess_orchestration"
    assert authority["subprocess_control_c_exit"] is True
    assert authority["subprocess_keyboard_interrupt"] is True
    assert authority["subprocess_child_pid"] == 123
    assert authority["subprocess_parent_pid"] == 456
    assert authority["subprocess_command"][0] == "python"
    assert authority["subprocess_cwd"] == str(tmp_path)
    assert authority["subprocess_env_overrides"] == {"PYTHONPATH": "src/discovery"}
    assert authority["subprocess_lifetime_sec"] == 9.73
    assert authority["subprocess_interrupt_diagnostics"]["subreason_code"] == "child_nested_subprocess_interrupt"
    assert authority["subprocess_interrupt_diagnostics"]["owner"] == "discovery_nested_subprocess_wait"
    assert authority["subprocess_interrupt_diagnostics"]["classification_precision"] == "precise"
    assert authority["subprocess_interrupt_diagnostics"]["stderr_traceback_shape"][
        "has_subprocess_communicate"
    ] is True
    assert authority["subprocess_interrupt_diagnostics"]["stderr_traceback_shape"][
        "has_stdout_thread_join"
    ] is True
    assert authority["safe_to_compare"] is False


def test_discovery_subprocess_interrupt_classifier_distinguishes_subreasons() -> None:
    bootstrap = discovery._classify_discovery_subprocess_interrupt(
        returncode=0xC000013A,
        stderr=(
            'File "<frozen importlib._bootstrap>", line 1204, in _find_and_load\n'
            'File "<frozen importlib._bootstrap_external>", line 140, in _path_stat\n'
            "KeyboardInterrupt\n"
        ),
    )
    assert bootstrap["subreason_code"] == "child_python_startup_interrupt"
    assert bootstrap["source_reason_code"] == "child_bootstrap_entry_missing"
    assert bootstrap["owner"] == "discovery_child_python_startup"
    assert bootstrap["import_bootstrap_interrupt"] is True
    assert bootstrap["bootstrap_trace_hint"] == "child_bootstrap_path_stat_interrupted"
    assert bootstrap["stderr_traceback_shape"]["has_importlib_bootstrap"] is True
    assert bootstrap["stderr_traceback_shape"]["has_import_path_stat"] is True
    assert bootstrap["child_runtime_diagnostic_present"] is False

    diagnostic_written = discovery._classify_discovery_subprocess_interrupt(
        returncode=0xC000013A,
        stderr=(
            'File "<frozen importlib._bootstrap>", line 1204, in _find_and_load\n'
            "KeyboardInterrupt\n"
        ),
        child_interrupt_diagnostic={
            "reason_code": "child_keyboard_interrupt",
            "source_hint": "child_bootstrap_module_load_interrupted",
        },
    )
    assert diagnostic_written["subreason_code"] == "child_bootstrap_import_interrupt"
    assert diagnostic_written["source_reason_code"] == "child_bootstrap_module_load_interrupted"
    assert diagnostic_written["child_interrupt_diagnostic_present"] is True

    nested = discovery._classify_discovery_subprocess_interrupt(
        returncode=0xC000013A,
        stderr=(
            'File "subprocess.py", line 1579, in _communicate\n'
            "self.stdout_thread.join(self._remaining_time(endtime))\n"
            'File "threading.py", line 1132, in _wait_for_tstate_lock\n'
            "KeyboardInterrupt\n"
        ),
    )
    assert nested["subreason_code"] == "child_nested_subprocess_interrupt"
    assert nested["owner"] == "discovery_nested_subprocess_wait"

    child = discovery._classify_discovery_subprocess_interrupt(
        returncode=0xC000013A,
        stderr="Traceback...\nKeyboardInterrupt\n",
    )
    assert child["subreason_code"] == "child_keyboard_interrupt"
    assert child["owner"] == "discovery_child_process"

    parent = discovery._classify_discovery_subprocess_interrupt(
        returncode=0xC000013A,
        stderr="",
    )
    assert parent["subreason_code"] == "parent_wait_interrupted"
    assert parent["owner"] == "discovery_parent_process_control"


def test_discovery_subprocess_interrupt_classifier_uses_child_source_diagnostic() -> None:
    result = discovery._classify_discovery_subprocess_interrupt(
        returncode=0xC000013A,
        stderr=(
            'File "subprocess.py", line 1579, in _communicate\n'
            "self.stdout_thread.join(self._remaining_time(endtime))\n"
            "KeyboardInterrupt\n"
        ),
        child_interrupt_diagnostic={
            "reason_code": "child_keyboard_interrupt",
            "source_hint": "nested_undname_wait_interrupt",
        },
    )

    assert result["subreason_code"] == "child_nested_subprocess_interrupt"
    assert result["source_reason_code"] == "nested_undname_wait_interrupt"
    assert result["child_interrupt_diagnostic_present"] is True
    assert result["child_interrupt_source_hint"] == "nested_undname_wait_interrupt"


def test_discovery_output_authority_preserves_child_interrupt_diagnostic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_path = tmp_path / "spectrum_reservation_stage.dll"
    dll_path.write_bytes(b"fake-pe")
    monkeypatch.setattr(
        discovery,
        "_inspect_pe_exports",
        lambda _path: {"available": True, "exports": ["SP_IssueReleaseHold"], "error": ""},
    )
    child_diagnostic = {
        "schema_version": "1.0.0",
        "reason_code": "child_keyboard_interrupt",
        "source_hint": "nested_import_analysis_wait_interrupt",
    }

    authority = discovery._build_discovery_output_authority(
        job_id="job-interrupt-source",
        binary_path=dll_path,
        out_dir=tmp_path / "empty-out",
        analysis_profile="strict_dll",
        returncode=0xC000013A,
        stderr=(
            'File "subprocess.py", line 1579, in _communicate\n'
            "self.stdout_thread.join(self._remaining_time(endtime))\n"
            "KeyboardInterrupt\n"
        ),
        output_files=[],
        invocable_count=0,
        child_interrupt_diagnostic=child_diagnostic,
    )

    diagnostics = authority["subprocess_interrupt_diagnostics"]
    assert diagnostics["subreason_code"] == "child_nested_subprocess_interrupt"
    assert diagnostics["source_reason_code"] == "nested_import_analysis_wait_interrupt"
    assert authority["subprocess_child_interrupt_diagnostic"] == child_diagnostic


def test_ghidra_required_route_preserves_python_startup_interrupt_reason(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_path = tmp_path / "spectrum_reservation_stage.dll"
    dll_path.write_bytes(b"fake-pe")
    monkeypatch.setattr(
        discovery,
        "_inspect_pe_exports",
        lambda _path: {"available": True, "exports": ["SP_IssueReleaseHold"], "error": ""},
    )

    authority = discovery._build_discovery_output_authority(
        job_id="job-ghidra-startup",
        binary_path=dll_path,
        out_dir=tmp_path / "empty-out",
        analysis_profile="strict_dll",
        returncode=0xC000013A,
        stderr=(
            'File "<frozen importlib._bootstrap>", line 1178, in _find_and_load\n'
            'File "<frozen importlib._bootstrap_external>", line 1659, in _fill_cache\n'
            "KeyboardInterrupt\n"
        ),
        output_files=[],
        invocable_count=0,
        ghidra_required=True,
        bridge_configured=True,
        bridge_attempted=False,
        ghidra_entered=False,
    )

    assert authority["reason_code"] == "child_python_startup_interrupt"
    assert authority["owner"] == "discovery_child_python_startup"
    assert authority["subprocess_interrupt_diagnostics"]["source_reason_code"] == "child_bootstrap_entry_missing"


def test_discovery_child_interrupt_diagnostic_writer_records_source_hint(tmp_path: Path) -> None:
    discovery_root = Path(__file__).resolve().parent.parent / "src" / "discovery"
    module_path = discovery_root / "main.py"
    spec = importlib.util.spec_from_file_location("discovery_cli_main_test", module_path)
    assert spec and spec.loader
    sys.path.insert(0, str(discovery_root))
    try:
        discovery_cli_main = importlib.util.module_from_spec(spec)
        sys.modules["discovery_cli_main_test"] = discovery_cli_main
        spec.loader.exec_module(discovery_cli_main)
    finally:
        sys.path.remove(str(discovery_root))

    try:
        raise KeyboardInterrupt()
    except KeyboardInterrupt as exc:
        discovery_cli_main._write_child_interrupt_diagnostic(
            exc,
            ["main.py", "--dll", "reservation.dll", "--out", str(tmp_path)],
        )

    packet = json.loads((tmp_path / "discovery-child-interrupt.json").read_text(encoding="utf-8"))
    assert packet["reason_code"] == "child_keyboard_interrupt"
    assert packet["source_hint"] == "child_top_level_keyboard_interrupt"
    assert packet["pid"] == os.getpid()
    assert packet["argv"][-1] == str(tmp_path)


def test_discovery_bootstrap_writes_import_interrupt_diagnostic(tmp_path: Path) -> None:
    discovery_root = Path(__file__).resolve().parent.parent / "src" / "discovery"
    module_path = discovery_root / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("discovery_bootstrap_test", module_path)
    assert spec and spec.loader
    bootstrap = importlib.util.module_from_spec(spec)
    sys.modules["discovery_bootstrap_test"] = bootstrap
    spec.loader.exec_module(bootstrap)

    def interrupted_importer(_module_name: str):
        raise KeyboardInterrupt()

    argv = ["bootstrap.py", "--dll", "reservation.dll", "--out", str(tmp_path)]
    try:
        bootstrap.run(argv, importer=interrupted_importer)
    except KeyboardInterrupt:
        pass

    packet = json.loads((tmp_path / "discovery-child-interrupt.json").read_text(encoding="utf-8"))
    assert packet["reason_code"] == "child_keyboard_interrupt"
    assert packet["source_hint"] == "child_bootstrap_import_interrupted"
    assert packet["bootstrap_phase"] == "bootstrap_import_or_main"
    assert packet["parent_pid"] == os.getppid()
    assert packet["argv"] == argv
    assert packet["python_executable"] == sys.executable


def test_discovery_bootstrap_delegates_to_main_with_original_argv(tmp_path: Path) -> None:
    discovery_root = Path(__file__).resolve().parent.parent / "src" / "discovery"
    module_path = discovery_root / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("discovery_bootstrap_delegate_test", module_path)
    assert spec and spec.loader
    bootstrap = importlib.util.module_from_spec(spec)
    sys.modules["discovery_bootstrap_delegate_test"] = bootstrap
    spec.loader.exec_module(bootstrap)

    seen = {}

    def fake_importer(module_name: str):
        assert module_name == "main"

        def fake_main() -> int:
            seen["argv"] = list(sys.argv)
            return 0

        return types.SimpleNamespace(main=fake_main)

    argv = ["bootstrap.py", "--dll", "reservation.dll", "--out", str(tmp_path)]
    assert bootstrap.run(argv, importer=fake_importer) == 0
    assert seen["argv"] == argv
    packet = json.loads((tmp_path / "discovery-child-runtime.json").read_text(encoding="utf-8"))
    phases = [entry["phase"] for entry in packet["phase_history"]]
    assert phases[:3] == [
        "bootstrap_import_start",
        "bootstrap_import_success",
        "bootstrap_main_calling",
    ]
    assert phases[-1] == "bootstrap_main_returned"


def test_discovery_child_runtime_phase_writer_records_main_phase(tmp_path: Path) -> None:
    discovery_root = Path(__file__).resolve().parent.parent / "src" / "discovery"
    module_path = discovery_root / "main.py"
    spec = importlib.util.spec_from_file_location("discovery_cli_runtime_test", module_path)
    assert spec and spec.loader
    sys.path.insert(0, str(discovery_root))
    try:
        discovery_cli_main = importlib.util.module_from_spec(spec)
        sys.modules["discovery_cli_runtime_test"] = discovery_cli_main
        spec.loader.exec_module(discovery_cli_main)
    finally:
        sys.path.remove(str(discovery_root))

    discovery_cli_main._write_child_runtime_phase(
        tmp_path,
        "main_args_parsed",
        argv=["main.py", "--dll", "reservation.dll", "--out", str(tmp_path)],
        details={"analysis_profile": "strict_dll"},
    )
    discovery_cli_main._write_child_runtime_phase(
        tmp_path,
        "main_pe_exports_start",
        argv=["main.py", "--dll", "reservation.dll", "--out", str(tmp_path)],
        details={"source": "pefile"},
    )

    packet = json.loads((tmp_path / "discovery-child-runtime.json").read_text(encoding="utf-8"))
    phases = [entry["phase"] for entry in packet["phase_history"]]
    assert phases == ["main_args_parsed", "main_pe_exports_start"]
    assert packet["phase"] == "main_pe_exports_start"
    assert packet["last_observation"]["source"] == "pefile"


def test_discovery_output_authority_non_interrupt_cases_do_not_get_interrupt_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_path = tmp_path / "spectrum_reservation_stage.dll"
    dll_path.write_bytes(b"fake-pe")
    monkeypatch.setattr(
        discovery,
        "_inspect_pe_exports",
        lambda _path: {"available": True, "exports": ["SP_IssueReleaseHold"], "error": ""},
    )

    extraction_gap = discovery._build_discovery_output_authority(
        job_id="job-gap",
        binary_path=dll_path,
        out_dir=tmp_path / "empty-out",
        analysis_profile="strict_dll",
        returncode=2,
        stderr="extractor failed without keyboard interrupt",
        output_files=[],
        invocable_count=0,
    )
    assert extraction_gap["reason_code"] == "discovery_extraction_gap"
    assert extraction_gap["subprocess_interrupt_diagnostics"] is None

    persisted_file = tmp_path / "out" / "spectrum_reservation_stage_exports_mcp.json"
    persisted_file.parent.mkdir()
    persisted_file.write_text('{"invocables":[]}', encoding="utf-8")
    zero_invocable = discovery._build_discovery_output_authority(
        job_id="job-zero",
        binary_path=dll_path,
        out_dir=persisted_file.parent,
        analysis_profile="strict_dll",
        returncode=0,
        output_files=[persisted_file],
        invocable_count=0,
    )
    assert zero_invocable["reason_code"] == "unsupported_or_unparsed_dll_shape"
    assert zero_invocable["subprocess_interrupt_diagnostics"] is None


def test_discovery_output_authority_marks_valid_discovery_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_path = tmp_path / "spectrum_reservation_stage.dll"
    dll_path.write_bytes(b"fake-pe")
    output_file = tmp_path / "reservation_mcp.json"
    output_file.write_text(json.dumps({"invocables": [{"name": "SP_IssueReleaseHold"}]}), encoding="utf-8")
    monkeypatch.setattr(
        discovery,
        "_inspect_pe_exports",
        lambda _path: {"available": True, "exports": ["SP_IssueReleaseHold"], "error": ""},
    )

    authority = discovery._build_discovery_output_authority(
        job_id="job-ok",
        binary_path=dll_path,
        out_dir=tmp_path,
        analysis_profile="strict_dll",
        returncode=0,
        output_files=[output_file],
        invocable_count=1,
    )

    assert authority["status"] == "comparable_discovery_success"
    assert authority["reason_code"] == "discovery_output_present"
    assert authority["owner"] == "analyzer_discovery"
    assert authority["safe_to_compare"] is True


def test_ghidra_required_discovery_blocks_pe_only_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_path = tmp_path / "spectrum_reservation_stage.dll"
    dll_path.write_bytes(b"fake-pe")
    output_file = tmp_path / "reservation_mcp.json"
    output_file.write_text(json.dumps({"invocables": [{"name": "SP_IssueReleaseHold"}]}), encoding="utf-8")
    monkeypatch.setattr(
        discovery,
        "_inspect_pe_exports",
        lambda _path: {"available": True, "exports": ["SP_IssueReleaseHold"], "error": ""},
    )

    authority = discovery._build_discovery_output_authority(
        job_id="job-pe-only",
        binary_path=dll_path,
        out_dir=tmp_path,
        analysis_profile="strict_dll",
        returncode=0,
        output_files=[output_file],
        invocable_count=1,
        child_runtime_diagnostic={
            "phase": "main_output_write_done",
            "phase_history": [
                {"phase": "main_args_parsed"},
                {"phase": "main_pe_exports_start"},
                {"phase": "main_pe_exports_done"},
                {"phase": "main_output_write_done"},
            ],
        },
        ghidra_required=True,
        bridge_configured=True,
        bridge_attempted=True,
        ghidra_entered=False,
    )

    assert authority["route_policy"] == "ghidra_first_required"
    assert authority["legacy_pe_parser_entered"] is True
    assert authority["reason_code"] == "ghidra_output_missing"
    assert authority["safe_to_compare"] is False
    assert authority["owner"] == "bridge_ghidra_discovery"


def test_ghidra_required_discovery_records_not_entered_before_pe_cleanup_interrupt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_path = tmp_path / "spectrum_reservation_stage.dll"
    dll_path.write_bytes(b"fake-pe")
    monkeypatch.setattr(
        discovery,
        "_inspect_pe_exports",
        lambda _path: {"available": True, "exports": ["SP_IssueReleaseHold"], "error": ""},
    )

    authority = discovery._build_discovery_output_authority(
        job_id="job-pe-interrupt",
        binary_path=dll_path,
        out_dir=tmp_path,
        analysis_profile="strict_dll",
        returncode=0xC000013A,
        stderr='File "pefile.py", line 300, in close\nKeyboardInterrupt\n',
        output_files=[],
        invocable_count=0,
        child_runtime_diagnostic={
            "phase": "main_pe_exports_start",
            "phase_history": [
                {"phase": "main_args_parsed"},
                {"phase": "main_pe_exports_start"},
            ],
        },
        ghidra_required=True,
        bridge_configured=True,
        bridge_attempted=False,
        ghidra_entered=False,
    )

    assert authority["reason_code"] == "legacy_pe_discovery_blocked_for_hard_family"
    assert authority["owner"] == "discovery_route_policy"
    assert authority["ghidra_required"] is True
    assert authority["bridge_attempted"] is False
    assert authority["legacy_pe_parser_entered"] is True
    assert authority["safe_to_compare"] is False
    assert authority["subprocess_interrupt_diagnostics"]["subreason_code"] == "child_keyboard_interrupt"


def test_ghidra_required_discovery_succeeds_only_with_ghidra_entry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_path = tmp_path / "spectrum_reservation_stage.dll"
    dll_path.write_bytes(b"fake-pe")
    output_file = tmp_path / "reservation_mcp.json"
    output_file.write_text(json.dumps({"invocables": [{"name": "SP_IssueReleaseHold"}]}), encoding="utf-8")
    monkeypatch.setattr(
        discovery,
        "_inspect_pe_exports",
        lambda _path: {"available": True, "exports": ["SP_IssueReleaseHold"], "error": ""},
    )

    authority = discovery._build_discovery_output_authority(
        job_id="job-ghidra",
        binary_path=dll_path,
        out_dir=tmp_path,
        analysis_profile="strict_dll",
        returncode=0,
        output_files=[output_file],
        invocable_count=1,
        ghidra_required=True,
        bridge_configured=True,
        bridge_attempted=True,
        ghidra_entered=True,
    )

    assert authority["reason_code"] == "ghidra_discovery_output_present"
    assert authority["owner"] == "bridge_ghidra_discovery"
    assert authority["safe_to_compare"] is True


def test_ghidra_required_discovery_fails_closed_when_bridge_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dll_path = tmp_path / "spectrum_reservation_stage.dll"
    dll_path.write_bytes(b"fake-pe")
    output_file = tmp_path / "reservation_mcp.json"
    output_file.write_text(json.dumps({"invocables": [{"name": "SP_IssueReleaseHold"}]}), encoding="utf-8")
    monkeypatch.setattr(
        discovery,
        "_inspect_pe_exports",
        lambda _path: {"available": True, "exports": ["SP_IssueReleaseHold"], "error": ""},
    )

    authority = discovery._build_discovery_output_authority(
        job_id="job-no-bridge",
        binary_path=dll_path,
        out_dir=tmp_path,
        analysis_profile="strict_dll",
        returncode=0,
        output_files=[output_file],
        invocable_count=1,
        ghidra_required=True,
        bridge_configured=False,
        bridge_attempted=False,
        ghidra_entered=False,
    )

    assert authority["reason_code"] == "ghidra_bridge_unavailable"
    assert authority["safe_to_compare"] is False
    assert authority["owner"] == "discovery_route_policy"


def test_bridge_analyzer_authority_classifies_transport_and_stream_stalls(tmp_path: Path) -> None:
    dll_path = tmp_path / "reservation.dll"
    dll_path.write_bytes(b"placeholder")

    not_sent = discovery._build_bridge_analyzer_authority(
        job_id="job-bridge",
        binary_path=dll_path,
        analysis_profile="strict_dll",
        bridge_url="http://bridge.test",
        attempts=[],
        started_at=100.0,
    )
    assert not_sent["reason_code"] == "bridge_request_not_sent"
    assert not_sent["owner"] == "api_to_bridge_transport"
    assert not_sent["safe_to_compare"] is False

    rejected = discovery._build_bridge_analyzer_authority(
        job_id="job-bridge",
        binary_path=dll_path,
        analysis_profile="strict_dll",
        bridge_url="http://bridge.test",
        attempts=[{"attempt": 1, "http_status": 503, "heartbeat_count": 0}],
        http_status=503,
    )
    assert rejected["reason_code"] == "bridge_request_rejected"

    no_heartbeat = discovery._build_bridge_analyzer_authority(
        job_id="job-bridge",
        binary_path=dll_path,
        analysis_profile="strict_dll",
        bridge_url="http://bridge.test",
        attempts=[{"attempt": 1, "http_status": 200, "heartbeat_count": 0}],
    )
    assert no_heartbeat["reason_code"] == "bridge_stream_no_heartbeat"


def test_bridge_analyzer_authority_classifies_ghidra_hung_and_zero_result(tmp_path: Path) -> None:
    dll_path = tmp_path / "reservation.dll"
    dll_path.write_bytes(b"placeholder")

    ghidra_hung = discovery._build_bridge_analyzer_authority(
        job_id="job-bridge",
        binary_path=dll_path,
        analysis_profile="strict_dll",
        bridge_url="http://bridge.test",
        attempts=[
            {
                "attempt": 1,
                "http_status": 200,
                "heartbeat_count": 3,
                "bridge_worker_phase": "ghidra_running",
                "first_heartbeat_at": 100.0,
                "last_heartbeat_at": 130.0,
            }
        ],
    )
    assert ghidra_hung["reason_code"] == "ghidra_analysis_hung"
    assert ghidra_hung["owner"] == "bridge_ghidra_analyzer"
    assert ghidra_hung["heartbeat_count"] == 3

    zero_result = discovery._build_bridge_analyzer_authority(
        job_id="job-bridge",
        binary_path=dll_path,
        analysis_profile="strict_dll",
        bridge_url="http://bridge.test",
        attempts=[{"attempt": 1, "http_status": 200, "heartbeat_count": 1}],
        result_emitted=True,
        invocable_count=0,
    )
    assert zero_result["reason_code"] == "unsupported_target_at_bridge_boundary"
    assert zero_result["stream_result_present"] is True
    assert zero_result["safe_to_compare"] is False

    successful_result = discovery._build_bridge_analyzer_authority(
        job_id="job-bridge",
        binary_path=dll_path,
        analysis_profile="strict_dll",
        bridge_url="http://bridge.test",
        attempts=[{"attempt": 1, "http_status": 200, "heartbeat_count": 1}],
        result_emitted=True,
        invocable_count=2,
    )
    assert successful_result["reason_code"] == "bridge_result_emitted"
    assert successful_result["safe_to_compare"] is True


def test_run_one_terminalizes_analyze_discovery_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    producer_authority = {
        "schema_version": "1.0.0",
        "target": "spectrum_reservation_stage",
        "reason_code": "output_persistence_gap",
        "owner": "discovery_output_persistence",
        "safe_to_compare": False,
        "exports_detected": ["SP_IssueReleaseHold"],
        "discovery_files_found": [],
        "invocable_count": 0,
        "evidence_paths": ["discovery-output-authority.json"],
        "next_action": "repair discovery artifact persistence before semantic comparison",
    }

    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-empty"

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-empty":
                return {
                    "job_id": "job-empty",
                    "status": "error",
                    "error": "Discovery produced no output files.",
                    "progress": 100,
                    "discovery_output_authority": producer_authority,
                }
            raise AssertionError(f"unexpected client path: {path}")

    monkeypatch.setattr(
        nightly_groundtruth,
        "wait_job",
        lambda *args, **kwargs: {
            "job_id": "job-empty",
            "status": "error",
            "error": "Discovery produced no output files.",
            "progress": 100,
            "discovery_output_authority": producer_authority,
        },
    )

    run_dir = tmp_path / "runs" / "02-reservation_stage"
    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        run_dir,
        "http://api.test",
        "",
        "reservation_stage",
        tmp_path / "fake.dll",
        "compiled_test",
        {"lane_id": "lane-1", "variant_id": "compiled_test", "selected_invocable_names": ["SP_Test"]},
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    assert result["status"] == "failed"
    assert result["phase"] == "analyze"
    assert result["measurement_terminalization"]["status"] == "non_comparable_failure"
    assert result["measurement_terminalization"]["reason_code"] == "discovery_empty"
    assert result["measurement_terminalization"]["safe_to_compare"] is False
    assert result["measurement_terminalization"]["analyzer_authority"]["reason_code"] == "discovery_empty"
    assert result["measurement_terminalization"]["analyzer_authority"]["classification_precision"] == "precise"
    assert result["measurement_terminalization"]["analyzer_authority"]["invocable_count"] == 0
    assert result["measurement_terminalization"]["analyzer_authority"]["discovery_output_present"] is False
    assert result["measurement_terminalization"]["analyzer_authority"]["safe_to_compare"] is False
    assert result["measurement_terminalization"]["analyzer_authority"]["producer_reason_code"] == "output_persistence_gap"
    assert result["measurement_terminalization"]["analyzer_authority"]["producer_owner"] == "discovery_output_persistence"
    assert result["measurement_terminalization"]["analyzer_authority"]["discovery_output_authority"] == producer_authority
    assert "discovery-output-authority.json" in result["measurement_terminalization"]["evidence_paths"]
    assert "analyzer-authority.json" in result["measurement_terminalization"]["evidence_paths"]
    assert result["run_authority"]["authority_level"] == "non_authoritative"
    assert result["run_authority"]["authoritative_proving"] is False
    assert result["run_authority"]["safe_to_steer_next_prompt"] is False
    assert (run_dir / "discovery-output-authority.json").exists()
    assert (run_dir / "analyzer-authority.json").exists()
    assert (run_dir / "measurement-terminalization.json").exists()
    assert (run_dir / "run-authority.json").exists()
    assert (run_dir / "run_result.json").exists()


def test_run_one_forwards_skip_cache_tag_to_analyze(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured_tags: dict[str, object] = {}

    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            captured_tags.update(tags)
            return "job-skip"

    monkeypatch.setattr(
        nightly_groundtruth,
        "wait_job",
        lambda *args, **kwargs: {
            "job_id": "job-skip",
            "status": "error",
            "error": "forced test failure",
            "progress": 0,
        },
    )

    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        tmp_path / "runs" / "01-test",
        "http://api.test",
        "",
        "reservation_stage",
        tmp_path / "fake.dll",
        "compiled_test",
        {
            "lane_id": "lane-1",
            "variant_id": "compiled_test",
            "selected_invocable_names": ["SP_Test"],
            "skip_cache": True,
        },
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    assert captured_tags["skip_cache"] is True
    assert result["status"] == "failed"


def test_run_one_keeps_interrupted_discovery_non_decision_bearing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    producer_authority = {
        "schema_version": "1.0.0",
        "target": "spectrum_reservation_stage",
        "reason_code": "discovery_subprocess_interrupt",
        "owner": "discovery_subprocess_orchestration",
        "safe_to_compare": False,
        "exports_detected": ["SP_IssueReleaseHold"],
        "discovery_files_found": [],
        "invocable_count": 0,
        "subprocess_returncode": 0xC000013A,
        "subprocess_interrupt_diagnostics": {
            "subreason_code": "child_nested_subprocess_interrupt",
            "owner": "discovery_nested_subprocess_wait",
            "classification_precision": "precise",
        },
        "evidence_paths": ["discovery-output-authority.json"],
        "next_action": "isolate the nested analyzer subprocess and control-event propagation",
    }

    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-interrupt"

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-interrupt":
                return {
                    "job_id": "job-interrupt",
                    "status": "error",
                    "error": "Discovery produced no output files.",
                    "progress": 0,
                    "discovery_output_authority": producer_authority,
                }
            raise AssertionError(f"unexpected client path: {path}")

    monkeypatch.setattr(
        nightly_groundtruth,
        "wait_job",
        lambda *args, **kwargs: {
            "job_id": "job-interrupt",
            "status": "error",
            "error": "Discovery produced no output files.",
            "progress": 0,
            "discovery_output_authority": producer_authority,
        },
    )

    run_dir = tmp_path / "runs" / "02-reservation_stage"
    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        run_dir,
        "http://api.test",
        "",
        "reservation_stage",
        tmp_path / "fake.dll",
        "compiled_test",
        {"lane_id": "lane-1", "variant_id": "compiled_test", "selected_invocable_names": ["SP_Test"]},
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    assert result["status"] == "failed"
    assert result["measurement_terminalization"]["status"] == "non_comparable_failure"
    assert result["measurement_terminalization"]["reason_code"] == "discovery_empty"
    analyzer_authority = result["measurement_terminalization"]["analyzer_authority"]
    assert analyzer_authority["producer_reason_code"] == "discovery_subprocess_interrupt"
    assert analyzer_authority["producer_owner"] == "discovery_subprocess_orchestration"
    assert analyzer_authority["discovery_output_authority"]["subprocess_interrupt_diagnostics"][
        "subreason_code"
    ] == "child_nested_subprocess_interrupt"
    assert result["run_authority"]["authority_level"] == "non_authoritative"
    assert result["run_authority"]["authoritative_proving"] is False
    assert result["run_authority"]["safe_to_steer_next_prompt"] is False


def test_run_one_terminalizes_analyze_timeout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-timeout"

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-timeout":
                return {
                    "job_id": "job-timeout",
                    "status": "running",
                    "progress": 60,
                    "message": "Local analysis complete - calling Windows GUI bridge...",
                    "explore_stage": "analyze",
                    "ghidra_required": True,
                }
            raise AssertionError(f"unexpected client path: {path}")

    def fake_wait_job(*args, **kwargs):  # noqa: ANN001
        raise TimeoutError("analyze stuck for job-timeout")

    monkeypatch.setattr(nightly_groundtruth, "wait_job", fake_wait_job)

    run_dir = tmp_path / "runs" / "02-reservation_stage"
    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        run_dir,
        "http://api.test",
        "",
        "reservation_stage",
        tmp_path / "fake.dll",
        "compiled_test",
        {
            "lane_id": "lane-1",
            "variant_id": "compiled_test",
            "selected_invocable_names": ["SP_Test"],
            "analysis_profile": "strict_dll",
            "ghidra_required": True,
            "selected_bridge_url": "http://127.0.0.1:8090",
        },
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    assert result["status"] == "failed"
    assert result["measurement_terminalization"]["reason_code"] == "analyzer_timeout"
    assert result["measurement_terminalization"]["status_payload"]["progress"] == 60
    assert result["measurement_terminalization"]["exception"] == "analyze stuck for job-timeout"
    assert result["measurement_terminalization"]["analyzer_authority"]["reason_code"] == "analyzer_timeout"
    assert result["measurement_terminalization"]["analyzer_authority"]["timeout_or_stall"]["timed_out"] is True
    assert result["measurement_terminalization"]["analyzer_authority"]["timeout_or_stall"]["last_observed_progress"] == 60
    assert result["measurement_terminalization"]["analyzer_authority"]["producer_reason_code"] == "analyzer_timeout"
    assert result["measurement_terminalization"]["analyzer_authority"]["producer_owner"] == "analyzer_runtime"
    assert result["measurement_terminalization"]["analyzer_authority"]["discovery_output_authority"]["source"] == "runner_fallback"
    assert result["measurement_terminalization"]["analyzer_authority"]["discovery_output_authority"][
        "route_policy"
    ] == "ghidra_first_required"
    assert result["measurement_terminalization"]["analyzer_authority"]["discovery_output_authority"][
        "bridge_attempted"
    ] is True
    assert result["measurement_terminalization"]["analyzer_authority"]["discovery_output_authority"][
        "ghidra_required"
    ] is True
    bridge_authority = result["measurement_terminalization"]["analyzer_authority"]["bridge_analyzer_authority"]
    assert bridge_authority["reason_code"] == "bridge_stream_no_heartbeat"
    assert bridge_authority["owner"] == "api_to_bridge_stream"
    assert bridge_authority["safe_to_compare"] is False
    assert result["measurement_terminalization"]["analyzer_authority"]["bridge_reason_code"] == "bridge_stream_no_heartbeat"
    assert "discovery-output-authority.json" in result["measurement_terminalization"]["evidence_paths"]
    assert "bridge-analyzer-authority.json" in result["measurement_terminalization"]["evidence_paths"]
    assert result["analyzer_authority"]["classification_precision"] == "precise"
    assert result["analyzer_authority"]["discovery_output_present"] is False
    assert result["analyzer_authority"]["bridge_analyzer_authority"]["source"] == "runner_fallback"
    discovery_output_authority = json.loads(
        (run_dir / "discovery-output-authority.json").read_text(encoding="utf-8")
    )
    assert discovery_output_authority["reason_code"] == "analyzer_timeout"
    assert discovery_output_authority["route_policy"] == "ghidra_first_required"
    assert discovery_output_authority["bridge_attempted"] is True
    assert discovery_output_authority["selected_bridge_url"] == "http://127.0.0.1:8090"
    assert json.loads((run_dir / "bridge-analyzer-authority.json").read_text(encoding="utf-8"))[
        "reason_code"
    ] == "bridge_stream_no_heartbeat"
    assert json.loads((run_dir / "analyzer-runtime-authority.json").read_text(encoding="utf-8"))[
        "reason_code"
    ] == "unknown_analyzer_runtime_stall"
    assert json.loads((run_dir / "analyzer-authority.json").read_text(encoding="utf-8"))[
        "reason_code"
    ] == "analyzer_timeout"
    assert json.loads((run_dir / "measurement-terminalization.json").read_text(encoding="utf-8"))[
        "reason_code"
    ] == "analyzer_timeout"


def test_measurement_terminalization_writes_false_done_reconciliation_packet(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-false-done"

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-false-done":
                return {
                    "job_id": "job-false-done",
                    "status": "done",
                    "progress": 100,
                    "message": "Analysis complete - 2 invocables found",
                    "analyzer_runtime_authority": {
                        "phase": "bridge_pending",
                        "status": "runtime_observed",
                        "phase_history": [{"phase": "bridge_pending"}],
                        "bridge_attempted": True,
                        "ghidra_entered": False,
                        "output_file_count": 1,
                    },
                }
            raise AssertionError(f"unexpected client path: {path}")

    monkeypatch.setattr(
        nightly_groundtruth,
        "wait_job",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("analyze request error")),
    )

    run_dir = tmp_path / "runs" / "04-fee_quote"
    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        run_dir,
        "http://api.test",
        "",
        "fee_quote",
        tmp_path / "fake.dll",
        "compiled_test",
        {
            "lane_id": "lane-1",
            "variant_id": "compiled_test",
            "selected_invocable_names": ["SP_StageReleaseFeeQuote"],
            "analysis_profile": "strict_dll",
            "ghidra_required": True,
        },
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    packet = result["authority_completion_reconciliation"]
    assert packet["classification"] == "false_done_status_without_authority_completion"
    assert packet["decision_bearing_blocker"] == "fee_quote_false_done_status_without_authority_completion"
    assert packet["public_status"]["status"] == "done"
    assert packet["public_status"]["progress"] == 100
    assert packet["run_authority"]["authority_level"] == "non_authoritative"
    assert packet["completion_requirements"]["valid_run"] is False
    assert packet["completion_requirements"]["session_capture_complete"] is False
    assert "authority-completion-reconciliation.json" in result["measurement_terminalization"]["evidence_paths"]
    saved = json.loads((run_dir / "authority-completion-reconciliation.json").read_text(encoding="utf-8"))
    assert saved["classification"] == "false_done_status_without_authority_completion"


def test_run_one_recovers_analyze_timeout_when_done_status_has_invocables(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_payloads = {
        "verification-report.json": {"verified_count": 1, "inferred_count": 0},
        "run-validity.json": {"valid": True},
        "kpi_run.json": {"verified_success": 1},
        "stage-index.json": {"stages": ["discover", "explore"]},
        "session-meta.json": {"job_id": "job-recovered"},
        "human/collect-session-result.json": {"ledger": {"appended": True}},
    }

    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-recovered"

        def post_json(self, path: str, payload: dict, timeout: int = 0):  # noqa: ANN001
            return {}

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-recovered":
                return {
                    "job_id": "job-recovered",
                    "status": "done",
                    "progress": 100,
                    "message": "Analysis complete - 1 invocable found",
                    "result": {"invocables": [{"name": "SP_IssueReleaseHold"}]},
                }
            if path == "/api/jobs/job-recovered/terminalization":
                return {
                    "job_id": "job-recovered",
                    "terminal": True,
                    "terminalization_kind": "done",
                    "reason": {"code": "job_completed_done", "message": "done"},
                }
            if path == "/api/jobs/job-recovered/verdict":
                return {"verdict": {"status": "done", "verified_count": 1, "total_count": 1}}
            if path == "/api/findings/job-recovered":
                return {
                    "findings": [
                        {
                            "function": "SP_IssueReleaseHold",
                            "status": "success",
                            "status_canonical": "verified_success",
                        }
                    ]
                }
            raise AssertionError(f"unexpected client path: {path}")

    wait_states = iter(
        [
            TimeoutError("analyze wait timed out after terminal output"),
            {"status": "done", "explore_phase": "done", "verification_verified": 1, "updated_at": 2.0},
        ]
    )

    def fake_wait_job(*args, **kwargs):  # noqa: ANN001
        value = next(wait_states)
        if isinstance(value, BaseException):
            raise value
        return value

    def fake_subprocess_run(cmd, cwd=None, capture_output=False, text=False, timeout=None):  # noqa: ANN001
        out_dir = Path(cmd[cmd.index("-OutDir") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in session_payloads.items():
            path = out_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="saved", stderr="")

    monkeypatch.setattr(nightly_groundtruth, "wait_job", fake_wait_job)
    monkeypatch.setattr(nightly_groundtruth, "target_scope_names", lambda settings: ["SP_IssueReleaseHold"])
    monkeypatch.setattr(
        nightly_groundtruth,
        "canonical_status_map",
        lambda findings, scope: {"SP_IssueReleaseHold": "verified_success"},
    )
    monkeypatch.setattr(nightly_groundtruth.subprocess, "run", fake_subprocess_run)

    run_dir = tmp_path / "runs" / "02-reservation_stage"
    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        run_dir,
        "http://api.test",
        "",
        "reservation_stage",
        tmp_path / "fake.dll",
        "compiled_test",
        {
            "lane_id": "lane-1",
            "variant_id": "compiled_test",
            "selected_invocable_names": ["SP_IssueReleaseHold"],
            "analysis_profile": "strict_dll",
            "ghidra_required": True,
        },
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    assert result["status"] == "ok"
    assert "measurement_terminalization" not in result
    assert result["run_authority"]["authority_level"] == "decision_bearing"
    recovery = json.loads((run_dir / "analyze-timeout-recovery-authority.json").read_text(encoding="utf-8"))
    assert recovery["status"] == "recovered"
    assert recovery["claim"] == "analyze_timeout_recovered_from_terminal_done_status"
    assert recovery["selected_invocable_names"] == ["SP_IssueReleaseHold"]
    assert recovery["product_green_claimed"] is False
    assert recovery["safe_to_compare"] is False


def test_run_one_terminalizes_progress_10_without_embedded_authority_as_control_stall(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-progress-10"

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-progress-10":
                return {
                    "job_id": "job-progress-10",
                    "status": "running",
                    "progress": 10,
                    "message": "Discovery started for spectrum_reservation_stage.dll",
                }
            raise AssertionError(f"unexpected client path: {path}")

    monkeypatch.setattr(
        nightly_groundtruth,
        "wait_job",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("analyze stuck for job-progress-10")),
    )

    run_dir = tmp_path / "runs" / "02-reservation_stage"
    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        run_dir,
        "http://api.test",
        "",
        "reservation_stage",
        tmp_path / "fake.dll",
        "compiled_test",
        {"lane_id": "lane-1", "variant_id": "compiled_test", "selected_invocable_names": ["SP_Test"]},
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    runtime_authority = result["measurement_terminalization"]["analyzer_authority"]["analyzer_runtime_authority"]
    assert result["measurement_terminalization"]["reason_code"] == "analyzer_timeout"
    assert runtime_authority["reason_code"] == "post_progress_10_control_stall"
    assert runtime_authority["safe_to_compare"] is False
    assert runtime_authority["embedded_authority_present"] is False
    assert "analyzer-runtime-authority.json" in result["measurement_terminalization"]["evidence_paths"]
    assert json.loads((run_dir / "analyzer-runtime-authority.json").read_text(encoding="utf-8"))[
        "reason_code"
    ] == "post_progress_10_control_stall"
    assert result["run_authority"]["authority_level"] == "non_authoritative"
    assert result["run_authority"]["authoritative_proving"] is False


def test_run_one_writes_analyzer_runtime_authority_for_analyze_api_read_timeout(
    tmp_path: Path,
) -> None:
    class FakeClient:
        def analyze(self, *args, **kwargs):  # noqa: ANN001
            raise nightly_groundtruth.requests.exceptions.ReadTimeout(
                "HTTPConnectionPool(host='127.0.0.1', port=8201): Read timed out. (read timeout=180)"
            )

    run_dir = tmp_path / "runs" / "02-reservation_stage"
    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        run_dir,
        "http://api.test",
        "",
        "reservation_stage",
        tmp_path / "fake.dll",
        "compiled_test",
        {
            "lane_id": "lane-1",
            "variant_id": "compiled_test",
            "selected_invocable_names": ["SP_Test"],
            "analysis_profile": "strict_dll",
            "ghidra_required": True,
        },
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    runtime_authority = result["measurement_terminalization"]["analyzer_authority"][
        "analyzer_runtime_authority"
    ]
    assert result["measurement_terminalization"]["reason_code"] == "analyzer_error"
    assert runtime_authority["status"] == "non_comparable_analyze_launch_error"
    assert runtime_authority["reason_code"] == "analyze_api_read_timeout"
    assert runtime_authority["owner"] == "api_analyze_launch"
    assert runtime_authority["safe_to_compare"] is False
    assert runtime_authority["bridge_attempted"] is False
    assert runtime_authority["ghidra_entered"] is False
    assert "analyzer-runtime-authority.json" in result["measurement_terminalization"]["evidence_paths"]
    assert json.loads((run_dir / "analyzer-runtime-authority.json").read_text(encoding="utf-8"))[
        "reason_code"
    ] == "analyze_api_read_timeout"


def test_analyzer_runtime_authority_distinguishes_startup_child_and_stale_status(tmp_path: Path) -> None:
    base_rec = {
        "target": "reservation_stage",
        "target_dll": "C:/tmp/spectrum_reservation_stage.dll",
        "settings": {"analysis_profile": "strict_dll"},
    }

    progress_10_return_marker_missing = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 10,
            "message": "Discovery started for spectrum_reservation_stage.dll",
            "analyzer_runtime_authority": {
                "phase": "worker_progress_10_persisted",
                "post_progress_10_seen": False,
                "worker_before_discovery_seen": False,
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert progress_10_return_marker_missing["reason_code"] == "progress_10_authority_return_marker_missing"

    progress_10_status_persist_stall = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 10,
            "message": "Discovery started for spectrum_reservation_stage.dll",
        },
        last_observation={
            "worker_progress_10_breadcrumbs": [
                {"phase": "progress_10_status_persist_start", "elapsed_ms_since_worker_start": 1.0}
            ]
        },
        exc=TimeoutError("stalled"),
    )
    assert progress_10_status_persist_stall["reason_code"] == "progress_10_status_persist_stall"
    assert progress_10_status_persist_stall["progress_10_control_last_phase"] == "progress_10_status_persist_start"

    progress_10_authority_emit_stall = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 10,
            "message": "Discovery started for spectrum_reservation_stage.dll",
        },
        last_observation={
            "worker_progress_10_breadcrumbs": [
                {"phase": "progress_10_status_persist_start"},
                {"phase": "progress_10_status_persist_returned"},
                {"phase": "progress_10_authority_emit_start"},
            ]
        },
        exc=TimeoutError("stalled"),
    )
    assert progress_10_authority_emit_stall["reason_code"] == "progress_10_authority_emit_stall"

    progress_10_authority_return_marker_missing = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 10,
            "message": "Discovery started for spectrum_reservation_stage.dll",
        },
        last_observation={
            "worker_progress_10_breadcrumbs": [
                {"phase": "progress_10_status_persist_returned"},
                {"phase": "progress_10_authority_emit_returned"},
                {"phase": "progress_10_authority_return_marker_emit_start"},
            ]
        },
        exc=TimeoutError("stalled"),
    )
    assert (
        progress_10_authority_return_marker_missing["reason_code"]
        == "progress_10_authority_return_marker_missing"
    )

    progress_30_start_missing = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 10,
            "message": "Discovery started for spectrum_reservation_stage.dll",
        },
        last_observation={
            "worker_progress_10_breadcrumbs": [
                {"phase": "progress_10_status_persist_returned"},
                {"phase": "progress_10_authority_emit_returned"},
                {"phase": "progress_10_authority_return_marker_emit_returned"},
            ]
        },
        exc=TimeoutError("stalled"),
    )
    assert progress_30_start_missing["reason_code"] == "progress_30_persist_start_missing"

    pre_progress_30_exception = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 10,
            "message": "Discovery started for spectrum_reservation_stage.dll",
        },
        last_observation={
            "worker_progress_10_breadcrumbs": [
                {"phase": "worker_pre_progress_30_exception", "exception_class": "RuntimeError"}
            ]
        },
        exc=TimeoutError("stalled"),
    )
    assert pre_progress_30_exception["reason_code"] == "worker_pre_progress_30_exception"

    progress_30_persist_stall = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 10,
            "message": "Discovery started for spectrum_reservation_stage.dll",
            "analyzer_runtime_authority": {
                "phase": "worker_progress_30_persist_start",
                "post_progress_10_seen": True,
                "progress_30_persist_started": True,
                "progress_30_persisted": False,
                "worker_before_discovery_seen": False,
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert progress_30_persist_stall["reason_code"] == "progress_30_persist_stall"

    pre_discovery_exception = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 10,
            "message": "Discovery started for spectrum_reservation_stage.dll",
            "analyzer_runtime_authority": {
                "phase": "worker_pre_discovery_exception",
                "post_progress_10_seen": True,
                "progress_30_persist_started": True,
                "progress_30_persisted": False,
                "worker_pre_discovery_exception": True,
                "worker_before_discovery_seen": False,
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert pre_discovery_exception["reason_code"] == "worker_pre_discovery_exception"

    no_child_launch = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 30,
            "message": "Running binary analysis pipeline...",
            "analyzer_runtime_authority": {
                "phase": "run_discovery_entered",
                "worker_before_discovery_seen": True,
                "run_discovery_entered": True,
                "child_launch_attempted": False,
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert no_child_launch["reason_code"] == "discovery_child_launch_missing"

    popen_calling = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 30,
            "message": "Running binary analysis pipeline...",
            "analyzer_runtime_authority": {
                "phase": "discovery_child_popen_calling",
                "worker_before_discovery_seen": True,
                "run_discovery_entered": True,
                "child_launch_attempted": True,
                "child_started": False,
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert popen_calling["reason_code"] == "discovery_child_popen_stall"

    popen_exception = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 30,
            "message": "Running binary analysis pipeline...",
            "analyzer_runtime_authority": {
                "phase": "discovery_child_popen_exception",
                "worker_before_discovery_seen": True,
                "run_discovery_entered": True,
                "child_launch_attempted": True,
                "child_started": False,
            },
        },
        last_observation={},
        exc=RuntimeError("popen failed"),
    )
    assert popen_exception["reason_code"] == "discovery_child_popen_exception"

    child_running = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 30,
            "message": "Running binary analysis pipeline...",
            "analyzer_runtime_authority": {
                "phase": "discovery_child_started",
                "worker_before_discovery_seen": True,
                "run_discovery_entered": True,
                "child_launch_attempted": True,
                "child_started": True,
                "child_completed": False,
                "child_pid": 1234,
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert child_running["reason_code"] == "child_runtime_diagnostic_missing"

    child_runtime_hung = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 30,
            "message": "Running binary analysis pipeline...",
            "analyzer_runtime_authority": {
                "phase": "discovery_child_timeout",
                "worker_before_discovery_seen": True,
                "run_discovery_entered": True,
                "child_launch_attempted": True,
                "child_started": True,
                "child_completed": False,
                "child_pid": 1234,
                "last_observation": {
                    "child_runtime_diagnostic": {
                        "phase": "main_pe_exports_start",
                        "phase_history": [{"phase": "main_pe_exports_start"}],
                    }
                },
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert child_runtime_hung["reason_code"] == "child_analysis_phase_hung"
    assert child_runtime_hung["child_runtime_phase"] == "main_pe_exports_start"
    assert child_runtime_hung["child_runtime_diagnostic_present"] is True

    child_output_hung = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 30,
            "message": "Running binary analysis pipeline...",
            "analyzer_runtime_authority": {
                "phase": "discovery_child_timeout",
                "worker_before_discovery_seen": True,
                "run_discovery_entered": True,
                "child_launch_attempted": True,
                "child_started": True,
                "child_completed": False,
                "last_observation": {
                    "child_runtime_diagnostic": {
                        "phase": "main_output_write_start",
                        "phase_history": [{"phase": "main_output_write_start"}],
                    }
                },
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert child_output_hung["reason_code"] == "child_output_write_hung"

    runtime_out = tmp_path / "runtime-out"
    runtime_out.mkdir()
    (runtime_out / "discovery-child-runtime.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "phase": "bootstrap_main_returned",
                "pid": 47556,
                "parent_pid": 25204,
                "phase_history": [{"phase": "bootstrap_main_returned"}],
                "last_observation": {"returncode": 0},
            }
        ),
        encoding="utf-8",
    )
    wrapper_wait = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 30,
            "message": "Running binary analysis pipeline...",
            "analyzer_runtime_authority": {
                "phase": "discovery_child_started",
                "worker_before_discovery_seen": True,
                "run_discovery_entered": True,
                "child_launch_attempted": True,
                "child_started": True,
                "child_completed": False,
                "child_pid": 25204,
                "out_dir": str(runtime_out),
                "phase_history": [
                    {"phase": "discovery_child_started"},
                    {"phase": "discovery_child_wait_start"},
                ],
                "last_observation": {"out_dir": str(runtime_out)},
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert wrapper_wait["reason_code"] == "child_wrapper_wait_return_missing"
    assert wrapper_wait["child_runtime_diagnostic_present"] is True
    assert wrapper_wait["child_runtime_diagnostic"]["pid"] == 47556
    assert "discovery_child_wait_start" in wrapper_wait["parent_wrapper_phases_seen"]

    returncode_missing = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 30,
            "message": "Running binary analysis pipeline...",
            "analyzer_runtime_authority": {
                "phase": "discovery_child_wait_returned",
                "worker_before_discovery_seen": True,
                "run_discovery_entered": True,
                "child_launch_attempted": True,
                "child_started": True,
                "child_completed": False,
                "child_pid": 25204,
                "out_dir": str(runtime_out),
                "phase_history": [
                    {"phase": "discovery_child_started"},
                    {"phase": "discovery_child_wait_start"},
                    {"phase": "discovery_child_wait_returned"},
                ],
                "last_observation": {"out_dir": str(runtime_out)},
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert returncode_missing["reason_code"] == "child_returncode_observation_missing"

    output_scan_missing = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 30,
            "message": "Running binary analysis pipeline...",
            "analyzer_runtime_authority": {
                "phase": "discovery_child_returncode_observed",
                "worker_before_discovery_seen": True,
                "run_discovery_entered": True,
                "child_launch_attempted": True,
                "child_started": True,
                "child_completed": False,
                "child_pid": 25204,
                "child_returncode": 0,
                "out_dir": str(runtime_out),
                "phase_history": [
                    {"phase": "discovery_child_started"},
                    {"phase": "discovery_child_wait_start"},
                    {"phase": "discovery_child_wait_returned"},
                    {"phase": "discovery_child_returncode_observed"},
                ],
                "last_observation": {"out_dir": str(runtime_out)},
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert output_scan_missing["reason_code"] == "child_output_scan_missing"

    child_completed_no_output = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 30,
            "message": "Running binary analysis pipeline...",
            "analyzer_runtime_authority": {
                "phase": "discovery_output_scan_completed",
                "worker_before_discovery_seen": True,
                "run_discovery_entered": True,
                "child_launch_attempted": True,
                "child_started": True,
                "child_completed": False,
                "child_pid": 25204,
                "child_returncode": 0,
                "out_dir": str(runtime_out),
                "output_file_count": 0,
                "output_files_found": [],
                "phase_history": [
                    {"phase": "discovery_child_started"},
                    {"phase": "discovery_child_wait_start"},
                    {"phase": "discovery_child_wait_returned"},
                    {"phase": "discovery_child_returncode_observed"},
                    {"phase": "discovery_output_scan_started"},
                    {"phase": "discovery_output_scan_completed"},
                ],
                "last_observation": {"out_dir": str(runtime_out)},
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert child_completed_no_output["reason_code"] == "status_packet_missing_parent_closeout"

    completed_no_output_non_stale = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 100,
            "message": "Running binary analysis pipeline...",
            "analyzer_runtime_authority": {
                "phase": "discovery_output_scan_completed",
                "worker_before_discovery_seen": True,
                "run_discovery_entered": True,
                "child_launch_attempted": True,
                "child_started": True,
                "child_completed": False,
                "child_pid": 25204,
                "child_returncode": 0,
                "out_dir": str(runtime_out),
                "output_file_count": 0,
                "output_files_found": [],
                "phase_history": [
                    {"phase": "discovery_child_started"},
                    {"phase": "discovery_child_wait_start"},
                    {"phase": "discovery_child_wait_returned"},
                    {"phase": "discovery_child_returncode_observed"},
                    {"phase": "discovery_output_scan_started"},
                    {"phase": "discovery_output_scan_completed"},
                ],
                "last_observation": {"out_dir": str(runtime_out)},
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert completed_no_output_non_stale["reason_code"] == "child_completed_no_output"

    stale_status = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 10,
            "message": "Discovery started for spectrum_reservation_stage.dll",
            "analyzer_runtime_authority": {
                "phase": "run_discovery_entered",
                "worker_before_discovery_seen": True,
                "run_discovery_entered": True,
            },
        },
        last_observation={},
        exc=TimeoutError("stalled"),
    )
    assert stale_status["reason_code"] == "status_persistence_stale"

    stale_status_from_breadcrumb = nightly_groundtruth._runner_analyzer_runtime_authority(
        rec=base_rec,
        status_payload={
            "status": "running",
            "progress": 10,
            "message": "Discovery started for spectrum_reservation_stage.dll",
        },
        last_observation={
            "worker_progress_10_breadcrumbs": [
                {"phase": "progress_30_status_persist_returned"},
                {"phase": "worker_before_discovery"},
            ]
        },
        exc=TimeoutError("stalled"),
    )
    assert stale_status_from_breadcrumb["reason_code"] == "status_persistence_stale"


def test_discovery_child_launch_diagnostics_records_pre_popen_facts(tmp_path: Path) -> None:
    bootstrap = tmp_path / "bootstrap.py"
    binary = tmp_path / "target.dll"
    out_dir = tmp_path / "out"
    bootstrap.write_text("print('ok')", encoding="utf-8")
    binary.write_bytes(b"MZ")
    out_dir.mkdir()

    payload = discovery._discovery_child_launch_diagnostics(
        cmd=[sys.executable, str(bootstrap), "--dll", str(binary), "--out", str(out_dir)],
        binary_path=binary,
        out_dir=out_dir,
        discovery_env={"PYTHONPATH": str(tmp_path)},
        analysis_profile="strict_dll",
    )

    assert payload["python_executable"] == sys.executable
    assert payload["python_executable_exists"] is True
    assert payload["bootstrap_path"] == str(bootstrap)
    assert payload["bootstrap_exists"] is True
    assert payload["binary_path_exists"] is True
    assert payload["out_dir_exists"] is True
    assert payload["pythonpath_exists"] is True
    assert payload["analysis_profile"] == "strict_dll"


def test_read_child_runtime_diagnostic_preserves_last_phase(tmp_path: Path) -> None:
    packet = {
        "schema_version": "1.0.0",
        "phase": "main_output_write_start",
        "phase_history": [{"phase": "main_args_parsed"}, {"phase": "main_output_write_start"}],
    }
    (tmp_path / "discovery-child-runtime.json").write_text(json.dumps(packet), encoding="utf-8")

    loaded = discovery._read_child_runtime_diagnostic(tmp_path)

    assert loaded == packet


def test_discovery_output_files_ignores_child_diagnostics(tmp_path: Path) -> None:
    (tmp_path / "discovery-child-runtime.json").write_text("{}", encoding="utf-8")
    (tmp_path / "discovery-child-interrupt.json").write_text("{}", encoding="utf-8")

    assert discovery._discovery_output_files(tmp_path) == []

    output = tmp_path / "reservation_exports_mcp.json"
    output.write_text("{}", encoding="utf-8")

    assert discovery._discovery_output_files(tmp_path) == [output]


def test_run_one_terminalizes_analyze_output_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-output-missing"

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            raise AssertionError(f"unexpected client path: {path}")

    monkeypatch.setattr(
        nightly_groundtruth,
        "wait_job",
        lambda *args, **kwargs: {
            "job_id": "job-output-missing",
            "status": "error",
            "error": "Analyzer completed but output missing from discovery bundle.",
            "progress": 100,
        },
    )

    run_dir = tmp_path / "runs" / "02-reservation_stage"
    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        run_dir,
        "http://api.test",
        "",
        "reservation_stage",
        tmp_path / "fake.dll",
        "compiled_test",
        {"lane_id": "lane-1", "variant_id": "compiled_test", "selected_invocable_names": ["SP_Test"]},
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    assert result["measurement_terminalization"]["reason_code"] == "output_missing"
    assert result["measurement_terminalization"]["analyzer_authority"]["reason_code"] == "output_missing"
    assert result["measurement_terminalization"]["analyzer_authority"]["analyzer_progress"] == 100
    assert result["measurement_terminalization"]["analyzer_authority"]["classification_precision"] == "precise"
    assert result["measurement_terminalization"]["analyzer_authority"]["discovery_output_present"] is False
    assert result["run_authority"]["authority_level"] == "non_authoritative"
    assert result["authoritative_proving"] is False
    assert (run_dir / "analyzer-authority.json").exists()


def _run_one_post_explore_fetch_failure(
    tmp_path: Path,
    monkeypatch,
    *,
    failing_endpoint: str,
    exc: Exception,
) -> dict:
    monkeypatch.setattr(nightly_groundtruth.time, "sleep", lambda seconds: None)

    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-post-explore"

        def post_json(self, path: str, payload: dict, timeout: int = 0):  # noqa: ANN001
            return {}

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-post-explore/terminalization":
                return {
                    "job_id": "job-post-explore",
                    "terminal": True,
                    "terminalization_kind": "done",
                    "reason": {"code": "job_completed_done", "message": "done"},
                }
            if path == failing_endpoint:
                raise exc
            if path == "/api/jobs/job-post-explore/verdict":
                return {"verdict": {"status": "done", "verified_count": 1, "total_count": 1}}
            if path == "/api/findings/job-post-explore":
                return {"findings": [{"function": "SP_Test", "status": "success"}]}
            raise AssertionError(f"unexpected client path: {path}")

    wait_states = iter(
        [
            {"status": "done", "result": {"invocables": [{"name": "SP_Test", "kind": "export"}]}},
            {
                "job_id": "job-post-explore",
                "status": "done",
                "explore_phase": "done",
                "macro_verdict": {"status": "done", "verified_count": 1, "total_count": 1},
                "verification_verified": 1,
                "updated_at": 2.0,
            },
        ]
    )
    monkeypatch.setattr(nightly_groundtruth, "wait_job", lambda *args, **kwargs: next(wait_states))

    return nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        tmp_path / "runs" / "01-test",
        "http://api.test",
        "",
        "session_bootstrap",
        tmp_path / "fake.dll",
        "compiled_test",
        {"lane_id": "lane-1", "variant_id": "compiled_test", "selected_invocable_names": ["SP_Test"]},
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )


def test_run_one_fails_closed_on_post_explore_verdict_connection_reset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    exc = nightly_groundtruth.requests.ConnectionError(
        ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")
    )

    result = _run_one_post_explore_fetch_failure(
        tmp_path,
        monkeypatch,
        failing_endpoint="/api/jobs/job-post-explore/verdict",
        exc=exc,
    )
    run_dir = tmp_path / "runs" / "01-test"

    assert result["status"] == "failed"
    assert result["phase"] == "post_explore_artifact_fetch"
    packet = result["post_explore_artifact_fetch_authority"]
    assert packet["reason_code"] == "post_explore_verdict_fetch_connection_reset"
    assert packet["artifact"] == "verdict"
    assert packet["fallback_macro_verdict_present"] is True
    assert packet["fallback_macro_verdict"]["status"] == "done"
    retry_packet = json.loads(
        (run_dir / "post-explore-artifact-fetch-retries.json").read_text(encoding="utf-8")
    )
    assert len(retry_packet) == 3
    assert retry_packet[-1]["verdict"] == "fail"
    assert result["verdict"] == {}
    assert result["run_authority"]["authority_level"] == "non_authoritative"
    assert result["run_authority"]["authoritative_proving"] is False
    assert result["run_authority"]["safe_to_steer_next_prompt"] is False
    assert result["authoritative_proving"] is False
    assert (run_dir / "post-explore-artifact-fetch-authority.json").exists()
    assert (run_dir / "measurement-terminalization.json").exists()
    assert (run_dir / "run-authority.json").exists()
    assert (run_dir / "run_result.json").exists()


def test_post_explore_verdict_connection_reset_recovers_after_retry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(nightly_groundtruth.time, "sleep", lambda seconds: None)

    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            self.calls += 1
            if self.calls == 1:
                raise nightly_groundtruth.requests.ConnectionError(
                    ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")
                )
            return {"verdict": {"status": "done", "verified_count": 1, "total_count": 1}}

    run_dir = tmp_path / "runs" / "01-test"
    run_dir.mkdir(parents=True)

    payload = nightly_groundtruth._fetch_post_explore_artifact_with_retry(
        FakeClient(),
        "/api/jobs/job-post-explore/verdict",
        artifact="verdict",
        run_dir=run_dir,
    )

    assert payload["verdict"]["status"] == "done"
    retry_packet = json.loads(
        (run_dir / "post-explore-artifact-fetch-retries.json").read_text(encoding="utf-8")
    )
    assert [row["verdict"] for row in retry_packet] == ["retry", "pass"]
    assert retry_packet[0]["reason_code"] == "post_explore_verdict_fetch_connection_reset"


def test_run_one_fails_closed_on_post_explore_verdict_generic_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result = _run_one_post_explore_fetch_failure(
        tmp_path,
        monkeypatch,
        failing_endpoint="/api/jobs/job-post-explore/verdict",
        exc=RuntimeError("verdict route unavailable"),
    )

    assert result["post_explore_artifact_fetch_authority"]["reason_code"] == "post_explore_verdict_fetch_failed"
    assert result["measurement_terminalization"]["safe_to_compare"] is False
    assert result["run_authority"]["authority_level"] == "non_authoritative"
    assert result["latest_status_map"] == {}


def test_run_one_fails_closed_on_post_explore_findings_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result = _run_one_post_explore_fetch_failure(
        tmp_path,
        monkeypatch,
        failing_endpoint="/api/findings/job-post-explore",
        exc=RuntimeError("findings route unavailable"),
    )
    run_dir = tmp_path / "runs" / "01-test"

    assert result["post_explore_artifact_fetch_authority"]["reason_code"] == "post_explore_findings_fetch_failed"
    assert result["post_explore_artifact_fetch_authority"]["artifact"] == "findings"
    assert result["measurement_terminalization"]["semantic_proof_satisfied"] is False
    assert result["run_authority"]["authoritative_proving"] is False
    assert (run_dir / "verdict.json").exists()
    assert (run_dir / "findings.json").exists() is False


def test_run_one_terminalizes_lane_unavailable_before_analyze(
    tmp_path: Path,
) -> None:
    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            raise AssertionError("analyze should not launch when lane readiness is red")

    run_dir = tmp_path / "runs" / "01-session_bootstrap"
    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        run_dir,
        "http://api.test",
        "",
        "session_bootstrap",
        tmp_path / "fake.dll",
        "compiled_test",
        {"lane_id": "lane-1", "variant_id": "compiled_test", "selected_invocable_names": ["SP_Test"]},
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
        lane_readiness={
            "ready": False,
            "blocking_reasons": ["api_readiness_unavailable"],
        },
    )

    assert result["status"] == "failed"
    assert result["phase"] == "preflight"
    assert result["measurement_terminalization"]["reason_code"] == "lane_or_infra_unavailable"
    assert result["measurement_terminalization"]["owner"] == "lane_or_infra"
    assert result["run_authority"]["lane_ready"] is False
    assert (run_dir / "run_result.json").exists()


def test_hard_report_preserves_non_comparable_measurement_packet(tmp_path: Path) -> None:
    from api.pipeline.core import spectrum_compiled_ingest

    run_dir = tmp_path / "runs" / "02-reservation_stage"
    run_dir.mkdir(parents=True)
    (run_dir / "job-status-analyze.json").write_text(
        json.dumps(
            {
                "job_id": "job-empty",
                "status": "error",
                "error": "Discovery produced no output files.",
            }
        ),
        encoding="utf-8",
    )
    measurement_packet = {
        "status": "non_comparable_failure",
        "reason_code": "discovery_empty",
        "safe_to_compare": False,
    }

    report = spectrum_compiled_ingest.build_spectrum_compiled_hard01_report(
        output_dir=tmp_path,
        package_manifest=spectrum_compiled_ingest.load_spectrum_compiled_package_manifest(),
        compiled_truth_manifest=spectrum_compiled_ingest.load_spectrum_compiled_truth_manifest(),
        authored_truth_manifest=spectrum_compiled_ingest.load_spectrum_authored_truth_manifest(),
        authored_hard_manifest=spectrum_compiled_ingest.load_spectrum_authored_hard01_manifest(),
        run_records=[
            {
                "dll_name": "spectrum_reservation_stage.dll",
                "job_id": "job-empty",
                "run_dir": str(run_dir),
                "valid_run": False,
                "phase": "analyze",
                "latest_status_map": {},
                "verdict": {},
                "job_status_snapshot": {"status": "error"},
                "run_authority": {
                    "authority_level": "non_authoritative",
                    "safe_to_steer_next_prompt": False,
                },
                "measurement_terminalization": measurement_packet,
            }
        ],
    )

    assert report["binary_ingest_proof_succeeded"] is False
    assert report["semantic_checkpoint_alignment_succeeded"] is False
    assert report["per_run"][0]["safe_to_compare"] is False
    assert report["per_run"][0]["measurement_reason_code"] == "discovery_empty"
    assert report["per_run"][0]["measurement_terminalization"] == measurement_packet


def test_run_one_tolerates_save_session_timeout_when_artifacts_already_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    started_at = 1_000.0
    session_payloads = {
        "verification-report.json": {"verified_count": 1, "inferred_count": 0},
        "run-validity.json": {"valid": True},
        "kpi_run.json": {"verified_success": 1},
        "session-manifest.json": {"schema_version": "1.0.0"},
        "stage-index.json": {"stages": ["discover", "explore"]},
        "session-meta.json": {"job_id": "job-1"},
        "human/collect-session-result.json": {"ledger": {"appended": True, "reason": "ok"}},
    }

    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-1"

        def post_json(self, path: str, payload: dict, timeout: int = 0):  # noqa: ANN001
            return {}

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-1/terminalization":
                return {
                    "job_id": "job-1",
                    "terminal": True,
                    "terminalization_kind": "done",
                    "reason": {"code": "job_completed_done", "message": "done"},
                }
            if path == "/api/jobs/job-1/verdict":
                return {"verdict": {"status": "done", "verified_count": 1, "total_count": 1}}
            if path == "/api/findings/job-1":
                return {
                    "findings": [
                        {
                            "function": "SP_Test",
                            "status": "success",
                            "status_canonical": "verified_success",
                        }
                    ]
                }
            raise AssertionError(f"unexpected client path: {path}")

    wait_states = iter(
        [
            {"status": "done", "result": {"invocables": [{"name": "SP_Test", "kind": "export"}]}},
            {"status": "done", "explore_phase": "done", "verification_verified": 1, "updated_at": 2.0},
        ]
    )

    monkeypatch.setattr(nightly_groundtruth, "wait_job", lambda *args, **kwargs: next(wait_states))
    monkeypatch.setattr(nightly_groundtruth, "target_scope_names", lambda settings: ["SP_Test"])
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: started_at)
    monkeypatch.setattr(
        nightly_groundtruth,
        "canonical_status_map",
        lambda findings, scope: {"SP_Test": "verified_success"},
    )

    def fake_subprocess_run(cmd, cwd=None, capture_output=False, text=False, timeout=None):  # noqa: ANN001
        out_dir = Path(cmd[cmd.index("-OutDir") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in session_payloads.items():
            path = out_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(__import__("json").dumps(payload), encoding="utf-8")
            os.utime(path, (started_at + 5, started_at + 5))
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(nightly_groundtruth.subprocess, "run", fake_subprocess_run)

    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        tmp_path / "runs" / "01-test",
        "http://api.test",
        "",
        "target",
        tmp_path / "fake.dll",
        "compiled_test",
        {"lane_id": "lane-1", "variant_id": "compiled_test", "selected_invocable_names": ["SP_Test"]},
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    assert result["status"] == "ok"
    assert result["save_session_exit"] == 0
    assert result["save_session_timed_out"] is True
    assert result["run_authority"]["authority_level"] == "decision_bearing"
    packet = result["authority_completion_reconciliation"]
    assert packet["source"] == "runner_terminal_authority_completion"
    assert packet["status"] == "reconciled"
    assert packet["classification"] == "authority_completion_reconciled"
    assert packet["decision_bearing_blocker"] == ""
    assert packet["completion_requirements"]["valid_run"] is True
    assert packet["completion_requirements"]["session_capture_complete"] is True
    assert packet["completion_requirements"]["verdict_status"] == "done"
    saved = json.loads(
        (tmp_path / "runs" / "01-test" / "authority-completion-reconciliation.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved["classification"] == "authority_completion_reconciled"
    log_text = (tmp_path / "runs" / "01-test" / "save-session.log").read_text(encoding="utf-8")
    assert "timeout tolerated" in log_text


def test_run_one_terminalizes_quasi_terminal_clarify_stall(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-1"

        def post_json(self, path: str, payload: dict, timeout: int = 0):  # noqa: ANN001
            return {}

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path.startswith("/api/jobs/job-1/terminalization"):
                return {
                    "job_id": "job-1",
                    "terminal": True,
                    "terminalization_kind": "quasi_terminal_stall",
                    "reason": {
                        "code": "awaiting_clarification_stable_without_authoritative_close",
                        "message": "Clarification-shaped state remained stable without authoritative finalization.",
                    },
                }
            raise AssertionError(f"unexpected client path after terminalization: {path}")

    wait_states = iter(
        [
            {"status": "done", "result": {"invocables": [{"name": "SP_Test", "kind": "export"}]}},
            nightly_groundtruth.QuasiTerminalClarifyStall(
                "job-1",
                {
                    "status": "running",
                    "explore_phase": "awaiting_clarification",
                    "explore_stage": "s06_gaps",
                    "explore_message": "Finalizing harmonized state...",
                    "explore_progress": "1/1",
                },
                stable_for_seconds=90,
            ),
        ]
    )

    def fake_wait_job(*args, **kwargs):  # noqa: ANN001
        next_item = next(wait_states)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item

    monkeypatch.setattr(nightly_groundtruth, "wait_job", fake_wait_job)
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: 1_000.0)

    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        tmp_path / "runs" / "01-test",
        "http://api.test",
        "",
        "session_bootstrap",
        tmp_path / "fake.dll",
        "compiled_test",
        {"lane_id": "lane-1", "variant_id": "compiled_test", "selected_invocable_names": ["SP_Test"]},
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    assert result["status"] == "failed"
    assert result["authoritative_proving"] is False
    assert result["job_terminalization"]["kind"] == "quasi_terminal_stall"
    assert result["runner_terminalization"] is None
    assert result["run_authority"]["authority_level"] == "non_authoritative"
    assert result["failure_domain"] == "pipeline"
    assert result["job_status_snapshot"]["explore_stage"] == "s06_gaps"


def test_run_one_persists_awaiting_clarification_packet_without_timeout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    started_at = 1_000.0
    session_payloads = {
        "verification-report.json": {"verified_count": 1, "inferred_count": 0},
        "run-validity.json": {"valid": True},
        "kpi_run.json": {"verified_success": 1},
        "session-manifest.json": {"schema_version": "1.0.0"},
        "stage-index.json": {"stages": ["discover", "explore"]},
        "session-meta.json": {"job_id": "job-1"},
        "human/collect-session-result.json": {"ledger": {"appended": True, "reason": "ok"}},
    }

    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-1"

        def post_json(self, path: str, payload: dict, timeout: int = 0):  # noqa: ANN001
            return {}

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-1/terminalization":
                return {
                    "job_id": "job-1",
                    "terminal": True,
                    "terminalization_kind": "awaiting_clarification_authoritative",
                    "reason": {
                        "code": "awaiting_clarification_closed_by_pipeline",
                        "message": "Pipeline closed in awaiting_clarification with an explicit terminal verdict.",
                    },
                }
            if path == "/api/jobs/job-1/verdict":
                return {
                    "verdict": {
                        "status": "awaiting_clarification",
                        "verified_count": 1,
                        "total_count": 1,
                    }
                }
            if path == "/api/findings/job-1":
                return {
                    "findings": [
                        {
                            "function": "SP_Test",
                            "status": "success",
                            "status_canonical": "verified_success",
                        }
                    ]
                }
            raise AssertionError(f"unexpected client path: {path}")

    wait_states = iter(
        [
            {"status": "done", "result": {"invocables": [{"name": "SP_Test", "kind": "export"}]}},
            {
                "status": "running",
                "explore_phase": "awaiting_clarification",
                "macro_verdict": {"status": "awaiting_clarification"},
                "verification_verified": 1,
                "updated_at": 2.0,
            },
        ]
    )

    monkeypatch.setattr(nightly_groundtruth, "wait_job", lambda *args, **kwargs: next(wait_states))
    monkeypatch.setattr(nightly_groundtruth, "target_scope_names", lambda settings: ["SP_Test"])
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: started_at)
    monkeypatch.setattr(
        nightly_groundtruth,
        "canonical_status_map",
        lambda findings, scope: {"SP_Test": "verified_success"},
    )

    def fake_subprocess_run(cmd, cwd=None, capture_output=False, text=False, timeout=None):  # noqa: ANN001
        out_dir = Path(cmd[cmd.index("-OutDir") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in session_payloads.items():
            path = out_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(__import__("json").dumps(payload), encoding="utf-8")
            os.utime(path, (started_at + 5, started_at + 5))

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(nightly_groundtruth.subprocess, "run", fake_subprocess_run)

    result = nightly_groundtruth.run_one(
        FakeClient(),
        tmp_path,
        tmp_path / "runs" / "01-test",
        "http://api.test",
        "",
        "target",
        tmp_path / "fake.dll",
        "compiled_test",
        {"lane_id": "lane-1", "variant_id": "compiled_test", "selected_invocable_names": ["SP_Test"]},
        poll_sec=0,
        analyze_timeout_sec=1,
        explore_timeout_sec=1,
        stuck_seconds=1,
        snapshot_profile="full",
        heartbeat_path=tmp_path / "heartbeats.json",
    )

    assert result["status"] == "ok"
    assert result["phase"] == "awaiting_clarification"
    assert result["verdict"]["status"] == "awaiting_clarification"
    assert result["job_status_snapshot"]["status"] == "running"
    assert result["run_authority"]["authority_level"] == "review_only"
    assert result["run_authority"]["failure_domain"] == "pipeline"


def test_run_one_does_not_tolerate_timeout_from_stale_session_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stale_session_dir = tmp_path / "runs" / "01-test" / "session"
    stale_session_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "verification-report.json",
        "run-validity.json",
        "kpi_run.json",
        "session-manifest.json",
    ):
        (stale_session_dir / name).write_text("{}", encoding="utf-8")

    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-1"

        def post_json(self, path: str, payload: dict, timeout: int = 0):  # noqa: ANN001
            return {}

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-1/terminalization":
                return {
                    "job_id": "job-1",
                    "terminal": True,
                    "terminalization_kind": "done",
                    "reason": {"code": "job_completed_done", "message": "done"},
                }
            if path == "/api/jobs/job-1/verdict":
                return {"verdict": {"status": "done", "verified_count": 1, "total_count": 1}}
            if path == "/api/findings/job-1":
                return {"findings": [{"function": "SP_Test", "status": "success"}]}
            raise AssertionError(f"unexpected client path: {path}")

    wait_states = iter(
        [
            {"status": "done", "result": {"invocables": [{"name": "SP_Test", "kind": "export"}]}},
            {"status": "done", "explore_phase": "done", "verification_verified": 1, "updated_at": 2.0},
        ]
    )

    monkeypatch.setattr(nightly_groundtruth, "wait_job", lambda *args, **kwargs: next(wait_states))
    monkeypatch.setattr(nightly_groundtruth, "target_scope_names", lambda settings: ["SP_Test"])
    monkeypatch.setattr(
        nightly_groundtruth,
        "canonical_status_map",
        lambda findings, scope: {"SP_Test": "verified_success"},
    )

    def fake_subprocess_run(cmd, cwd=None, capture_output=False, text=False, timeout=None):  # noqa: ANN001
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(nightly_groundtruth.subprocess, "run", fake_subprocess_run)

    try:
        nightly_groundtruth.run_one(
            FakeClient(),
            tmp_path,
            tmp_path / "runs" / "01-test",
            "http://api.test",
            "",
            "target",
            tmp_path / "fake.dll",
            "compiled_test",
            {"lane_id": "lane-1", "variant_id": "compiled_test", "selected_invocable_names": ["SP_Test"]},
            poll_sec=0,
            analyze_timeout_sec=1,
            explore_timeout_sec=1,
            stuck_seconds=1,
            snapshot_profile="full",
            heartbeat_path=tmp_path / "heartbeats.json",
        )
    except subprocess.TimeoutExpired:
        pass
    else:
        raise AssertionError("expected TimeoutExpired when only stale session artifacts exist")


def test_run_one_does_not_tolerate_timeout_without_ledger_completion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    started_at = 1000.0
    session_payloads = {
        "verification-report.json": {"verified_count": 1, "entries": []},
        "run-validity.json": {"valid": True},
        "kpi_run.json": {"totals": {"total_functions": 1, "verified_success": 1}},
        "session-manifest.json": {"job_id": "job-1"},
        "human/collect-session-result.json": {"ledger": {"appended": False, "reason": "error:timeout"}},
    }

    class FakeClient:
        def analyze(self, dll_path, hints, use_cases, tags):  # noqa: ANN001
            return "job-1"

        def post_json(self, path: str, payload: dict, timeout: int = 0):  # noqa: ANN001
            return {}

        def get(self, path: str, timeout: int = 0):  # noqa: ANN001
            if path == "/api/jobs/job-1/terminalization":
                return {
                    "job_id": "job-1",
                    "terminal": True,
                    "terminalization_kind": "done",
                    "reason": {"code": "job_completed_done", "message": "done"},
                }
            if path == "/api/jobs/job-1/verdict":
                return {"verdict": {"status": "done", "verified_count": 1, "total_count": 1}}
            if path == "/api/findings/job-1":
                return {"findings": [{"function": "SP_Test", "status": "success"}]}
            raise AssertionError(f"unexpected client path: {path}")

    wait_states = iter(
        [
            {"status": "done", "result": {"invocables": [{"name": "SP_Test", "kind": "export"}]}},
            {"status": "done", "explore_phase": "done", "verification_verified": 1, "updated_at": 2.0},
        ]
    )

    monkeypatch.setattr(nightly_groundtruth, "wait_job", lambda *args, **kwargs: next(wait_states))
    monkeypatch.setattr(nightly_groundtruth, "target_scope_names", lambda settings: ["SP_Test"])
    monkeypatch.setattr(nightly_groundtruth.time, "time", lambda: started_at)
    monkeypatch.setattr(
        nightly_groundtruth,
        "canonical_status_map",
        lambda findings, scope: {"SP_Test": "verified_success"},
    )

    def fake_subprocess_run(cmd, cwd=None, capture_output=False, text=False, timeout=None):  # noqa: ANN001
        out_dir = Path(cmd[cmd.index("-OutDir") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in session_payloads.items():
            path = out_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(__import__("json").dumps(payload), encoding="utf-8")
            os.utime(path, (started_at + 5, started_at + 5))
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(nightly_groundtruth.subprocess, "run", fake_subprocess_run)

    try:
        nightly_groundtruth.run_one(
            FakeClient(),
            tmp_path,
            tmp_path / "runs" / "01-test",
            "http://api.test",
            "",
            "target",
            tmp_path / "fake.dll",
            "compiled_test",
            {"lane_id": "lane-1", "variant_id": "compiled_test", "selected_invocable_names": ["SP_Test"]},
            poll_sec=0,
            analyze_timeout_sec=1,
            explore_timeout_sec=1,
            stuck_seconds=1,
            snapshot_profile="full",
            heartbeat_path=tmp_path / "heartbeats.json",
        )
    except subprocess.TimeoutExpired:
        pass
    else:
        raise AssertionError("expected TimeoutExpired when ledger completion is missing or errored")
