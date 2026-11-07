from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


RUNTIME_ROOT = Path(__file__).resolve().parent
REPO_ROOT = RUNTIME_ROOT.parent
CONTRACT_PATH = RUNTIME_ROOT / "local-runtime-contract.json"
DEFAULT_LOOPBACK_HOST = "127.0.0.1"


@lru_cache(maxsize=1)
def load_local_runtime_contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def runtime_system(name: str) -> dict[str, Any]:
    systems = dict(load_local_runtime_contract().get("systems") or {})
    try:
        payload = systems[str(name).strip()]
    except KeyError as exc:
        raise KeyError(f"unknown_runtime_system:{name}") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"runtime_system_not_object:{name}")
    return payload


def trust_contract_version() -> str:
    return str(load_local_runtime_contract().get("trust_contract_version") or "").strip()


def runtime_contract_id() -> str:
    return str(load_local_runtime_contract().get("contract_id") or "").strip()


def runtime_base_url(name: str, *, host: str | None = None) -> str:
    system = runtime_system(name)
    scheme = str(system.get("scheme") or "http").strip() or "http"
    resolved_host = str(host or system.get("host") or DEFAULT_LOOPBACK_HOST).strip()
    port = runtime_port(name)
    return f"{scheme}://{resolved_host}:{port}"


def runtime_port(name: str) -> int:
    system = runtime_system(name)
    canonical_port = int(system["port"])
    override_candidates = {
        "api": (
            str(os.getenv("MCP_FACTORY_API_PORT") or "").strip(),
            str(os.getenv("API_PORT") or "").strip(),
        ),
        "bridge": (
            str(os.getenv("MCP_FACTORY_BRIDGE_PORT") or "").strip(),
            str(os.getenv("BRIDGE_PORT") or "").strip(),
        ),
    }.get(str(name).strip(), ())
    for candidate in override_candidates:
        if not candidate:
            continue
        try:
            resolved = int(candidate)
        except ValueError:
            continue
        if resolved > 0:
            return resolved
    return canonical_port


def local_api_base_url(*, host: str | None = None) -> str:
    return runtime_base_url("api", host=host)


def local_bridge_base_url(*, host: str | None = None) -> str:
    return runtime_base_url("bridge", host=host)


def local_api_candidate_urls() -> tuple[str, ...]:
    candidates = [
        local_api_base_url(),
    ]
    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return tuple(deduped)


def required_bridge_capabilities() -> tuple[str, ...]:
    bridge = runtime_system("bridge")
    return tuple(str(item).strip() for item in list(bridge.get("required_capabilities") or []) if str(item).strip())


def required_env_keys(*system_names: str) -> tuple[str, ...]:
    names = system_names or ("api", "bridge")
    keys: list[str] = []
    for name in names:
        for key in list(runtime_system(name).get("required_env_keys") or []):
            normalized = str(key).strip()
            if normalized and normalized not in keys:
                keys.append(normalized)
    return tuple(keys)


def runner_output_packets() -> tuple[str, ...]:
    runner = runtime_system("runner")
    return tuple(
        str(item).strip()
        for item in list(runner.get("authoritative_output_packets") or [])
        if str(item).strip()
    )


def local_lane_admission_path(name: str) -> str:
    system = runtime_system(name)
    return str(system.get("local_lane_admission_path") or "/local-lane-admission").strip()


def alive_path(name: str) -> str:
    system = runtime_system(name)
    return str(system.get("alive_path") or "/alive").strip()


def health_path(name: str) -> str:
    system = runtime_system(name)
    return str(system.get("health_path") or "/health").strip()
