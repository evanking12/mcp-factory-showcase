from __future__ import annotations

import pytest

from runtime.runtime_contract import (
    alive_path,
    health_path,
    local_lane_admission_path,
    load_local_runtime_contract,
    local_api_base_url,
    local_api_candidate_urls,
    local_bridge_base_url,
    required_bridge_capabilities,
    required_env_keys,
    runner_output_packets,
    runtime_contract_id,
    runtime_port,
    runtime_system,
    trust_contract_version,
)


def test_runtime_contract_pins_api_bridge_and_runner_basics() -> None:
    contract = load_local_runtime_contract()

    assert contract["contract_id"] == "local_runtime_contract_v1"
    assert trust_contract_version() == "trust_contract_v1"

    api = runtime_system("api")
    bridge = runtime_system("bridge")
    runner = runtime_system("runner")

    assert api["component"] == "api"
    assert api["role"] == "pipeline_control_plane"
    assert api["port"] == 8201
    assert api["alive_path"] == "/alive"
    assert api["health_path"] == "/health"
    assert api["identity_path"] == "/identity"
    assert api["readiness_path"] == "/readiness"
    assert api["local_lane_admission_path"] == "/local-lane-admission"

    assert bridge["component"] == "bridge"
    assert bridge["role"] == "execution_bridge"
    assert bridge["port"] == 8090
    assert bridge["alive_path"] == "/alive"
    assert bridge["health_path"] == "/health"
    assert bridge["auth_header"] == "X-Bridge-Key"
    assert bridge["local_lane_admission_path"] == "/local-lane-admission"
    assert required_bridge_capabilities() == ("execute", "flush_dll_cache")

    assert runner["component"] == "runner"
    assert runner["runner_name"] == "run_proving_lane_canary"
    assert "api" in runner["consumes"]
    assert "bridge" in runner["consumes"]


def test_runtime_contract_helpers_return_canonical_local_urls_and_packets() -> None:
    assert runtime_contract_id() == "local_runtime_contract_v1"
    assert local_api_base_url() == "http://127.0.0.1:8201"
    assert local_bridge_base_url() == "http://127.0.0.1:8090"
    assert local_api_candidate_urls()[0] == "http://127.0.0.1:8201"
    assert "http://localhost:8001" not in local_api_candidate_urls()
    assert alive_path("api") == "/alive"
    assert health_path("api") == "/health"
    assert alive_path("bridge") == "/alive"
    assert health_path("bridge") == "/health"
    assert local_lane_admission_path("api") == "/local-lane-admission"
    assert local_lane_admission_path("bridge") == "/local-lane-admission"
    assert "lane-identity.json" in runner_output_packets()
    assert "analyze-only-canary.json" in runner_output_packets()
    assert "bridge-execution-canary.json" in runner_output_packets()
    assert "lane-trust-packet.json" in runner_output_packets()
    assert "session-capture-canary.json" not in runner_output_packets()
    assert "job-progress-tail.json" not in runner_output_packets()


def test_runtime_contract_required_env_keys_cover_local_lane_operator_surface() -> None:
    keys = set(required_env_keys())
    assert "OPENAI_API_KEY" in keys
    assert "MCP_STORAGE_BACKEND" in keys
    assert "GUI_BRIDGE_URL" in keys
    assert "GUI_BRIDGE_SECRET" in keys


def test_runtime_helpers_allow_explicit_port_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_FACTORY_API_PORT", "18201")
    monkeypatch.setenv("MCP_FACTORY_BRIDGE_PORT", "18090")

    assert runtime_port("api") == 18201
    assert runtime_port("bridge") == 18090
    assert local_api_base_url() == "http://127.0.0.1:18201"
    assert local_bridge_base_url() == "http://127.0.0.1:18090"
    assert local_api_candidate_urls()[0] == "http://127.0.0.1:18201"
