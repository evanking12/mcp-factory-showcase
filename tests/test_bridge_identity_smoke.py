from __future__ import annotations

from pathlib import Path

import pytest
import requests

from api.infra.local_lane_admission import LOCAL_LANE_ADMISSION_VERSION
from api.infra.service_identity import TRUST_CONTRACT_VERSION
from runtime.runtime_contract import runtime_contract_id
from scripts.ops import nightly_groundtruth as ng


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


def _bridge_identity(*, capabilities: list[str] | None = None) -> dict:
    return {
        "component": "bridge",
        "role": "execution_bridge",
        "contract_version": TRUST_CONTRACT_VERSION,
        "capabilities": capabilities if capabilities is not None else ["analyze", "execute"],
    }


def _ready() -> dict:
    return {
        "component": "bridge",
        "ready": True,
        "contract_version": TRUST_CONTRACT_VERSION,
        "capabilities": ["analyze", "execute"],
        "blocking_reasons": [],
    }


def _admitted() -> dict:
    return {
        "component": "bridge",
        "role": "execution_bridge",
        "contract_version": LOCAL_LANE_ADMISSION_VERSION,
        "runtime_contract_id": runtime_contract_id(),
        "admitted": True,
        "blocking_reasons": [],
    }


def test_bridge_identity_smoke_green(monkeypatch) -> None:
    def fake_get(url: str, headers: dict[str, str], timeout: int) -> _Response:
        assert headers == {"X-Bridge-Key": "secret"}
        if url.endswith("/identity"):
            return _Response(200, _bridge_identity())
        if url.endswith("/readiness"):
            return _Response(200, _ready())
        if url.endswith("/local-lane-admission"):
            return _Response(200, _admitted())
        return _Response(404, text="not found")

    monkeypatch.setattr(ng.requests, "get", fake_get)
    packet = ng.build_bridge_identity_smoke_packet("http://127.0.0.1:8090", "secret")

    assert packet["reason_code"] == "bridge_identity_green"
    assert packet["safe_to_run"] is True
    assert packet["safe_to_compare"] is True


def test_bridge_identity_smoke_classifies_missing_secret(monkeypatch) -> None:
    monkeypatch.delenv("GUI_BRIDGE_SECRET", raising=False)
    monkeypatch.setattr(ng, "BRIDGE_SECRET_ENV_FILES", ())
    monkeypatch.setattr(ng.requests, "get", lambda *args, **kwargs: _Response(401, text="unauthorized"))

    packet = ng.build_bridge_identity_smoke_packet("http://127.0.0.1:8090")

    assert packet["reason_code"] == "bridge_secret_missing"
    assert packet["safe_to_run"] is False


def test_bridge_identity_smoke_classifies_secret_mismatch(monkeypatch) -> None:
    monkeypatch.setattr(ng.requests, "get", lambda *args, **kwargs: _Response(401, text="unauthorized"))

    packet = ng.build_bridge_identity_smoke_packet("http://127.0.0.1:8090", "wrong")

    assert packet["reason_code"] == "bridge_secret_mismatch"
    assert packet["safe_to_run"] is False


def test_bridge_identity_smoke_classifies_process_not_running(monkeypatch) -> None:
    def fake_get(*args, **kwargs):
        raise requests.exceptions.ConnectionError("No connection could be made because the target machine actively refused it")

    monkeypatch.setattr(ng.requests, "get", fake_get)
    packet = ng.build_bridge_identity_smoke_packet("http://127.0.0.1:8090", "secret")

    assert packet["reason_code"] == "bridge_process_not_running"


def test_bridge_identity_smoke_classifies_api_shaped_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        ng.requests,
        "get",
        lambda *args, **kwargs: _Response(
            200,
            {
                "component": "api",
                "role": "pipeline_control_plane",
                "contract_version": TRUST_CONTRACT_VERSION,
            },
        ),
    )

    packet = ng.build_bridge_identity_smoke_packet("http://127.0.0.1:8201", "secret")

    assert packet["reason_code"] == "bridge_api_shaped_endpoint_detected"


def test_bridge_identity_smoke_classifies_capability_gap(monkeypatch) -> None:
    monkeypatch.setattr(
        ng.requests,
        "get",
        lambda *args, **kwargs: _Response(200, _bridge_identity(capabilities=["execute"])),
    )

    packet = ng.build_bridge_identity_smoke_packet("http://127.0.0.1:8090", "secret")

    assert packet["reason_code"] == "bridge_capabilities_incomplete"
    assert packet["missing_capabilities"] == ["analyze"]


def test_resolve_bridge_secret_uses_ignored_bridge_env(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".bridge.env"
    env_path.write_text("GUI_BRIDGE_SECRET=local-secret\n", encoding="utf-8")
    monkeypatch.delenv("GUI_BRIDGE_SECRET", raising=False)
    monkeypatch.setattr(ng, "BRIDGE_SECRET_ENV_FILES", (env_path,))

    assert ng.resolve_bridge_secret("") == "local-secret"


def test_resolve_bridge_secret_uses_root_env_fallback(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("GUI_BRIDGE_SECRET=root-secret\n", encoding="utf-8")
    monkeypatch.delenv("GUI_BRIDGE_SECRET", raising=False)
    monkeypatch.setattr(ng, "BRIDGE_SECRET_ENV_FILES", (tmp_path / "missing.env", env_path))

    assert ng.resolve_bridge_secret("") == "root-secret"
