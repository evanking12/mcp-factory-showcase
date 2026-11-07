from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from api.pipeline.core.handoff_contract import CONTRACT_VERSION as PIPELINE_CONTRACT_VERSION


REPO_ROOT = Path(__file__).resolve().parents[2]
TRUST_CONTRACT_VERSION = "trust_contract_v1"
PIPELINE_SCHEMA_VERSION = f"handoff_contract_v{PIPELINE_CONTRACT_VERSION}"
STATUS_SCHEMA_VERSION = "job_status_v1"
REQUIRED_BRIDGE_CAPABILITIES = ("execute", "flush_dll_cache")


def utc_iso_from_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(value)))
    except Exception:
        return None


def _stable_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


@lru_cache(maxsize=32)
def _fingerprint_resolved_paths(paths: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for raw_path in paths:
        path = Path(raw_path)
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except Exception:
            digest.update(b"<unreadable>")
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def build_fingerprint(paths: Sequence[Path | str]) -> str:
    resolved_paths = tuple(
        str(Path(path).resolve())
        for path in paths
        if str(path).strip() and Path(path).exists()
    )
    return _fingerprint_resolved_paths(resolved_paths) if resolved_paths else "sha256:unavailable"


def config_fingerprint(payload: Mapping[str, Any]) -> str:
    return f"sha256:{hashlib.sha256(_stable_json_bytes(payload)).hexdigest()}"


@lru_cache(maxsize=1)
def _git_sha(repo_root: str) -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "-C", repo_root, "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            .strip()
        )
    except Exception:
        return ""


@lru_cache(maxsize=1)
def _git_dirty(repo_root: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", repo_root, "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return False
    return bool((proc.stdout or "").strip())


def git_identity(repo_root: Path | None = None) -> tuple[str, bool]:
    root = str((repo_root or REPO_ROOT).resolve())
    return _git_sha(root), _git_dirty(root)


def host_identity() -> str:
    return str(os.getenv("COMPUTERNAME") or socket.gethostname() or "unknown-host").strip()


def build_runner_identity(
    *,
    runner_name: str,
    runner_version: str,
    started_at: float,
    source_paths: Sequence[Path | str],
    config_payload: Mapping[str, Any],
    role: str = "proving_driver",
) -> dict[str, Any]:
    git_sha, dirty = git_identity()
    return {
        "component": "runner",
        "role": role,
        "runner_name": str(runner_name or "").strip(),
        "runner_version": str(runner_version or "").strip(),
        "runner_git_sha": git_sha,
        "runner_dirty": bool(dirty),
        "contract_version": TRUST_CONTRACT_VERSION,
        "started_at": utc_iso_from_timestamp(started_at),
        "host": host_identity(),
        "build_fingerprint": build_fingerprint(source_paths),
        "config_fingerprint": config_fingerprint(config_payload),
    }


def build_api_identity(
    *,
    service_version: str,
    process_started_at: float,
    source_paths: Sequence[Path | str],
    config_payload: Mapping[str, Any],
    status_schema_version: str = STATUS_SCHEMA_VERSION,
    pipeline_schema_version: str = PIPELINE_SCHEMA_VERSION,
    git_sha: str | None = None,
    dirty: bool | None = None,
) -> dict[str, Any]:
    resolved_git_sha, resolved_dirty = git_identity()
    if git_sha is not None:
        resolved_git_sha = str(git_sha or "").strip()
    if dirty is not None:
        resolved_dirty = bool(dirty)
    return {
        "component": "api",
        "role": "pipeline_control_plane",
        "service_name": "mcp_factory_api",
        "service_version": str(service_version or "").strip(),
        "git_sha": resolved_git_sha,
        "dirty": bool(resolved_dirty),
        "process_started_at": utc_iso_from_timestamp(process_started_at),
        "build_fingerprint": build_fingerprint(source_paths),
        "config_fingerprint": config_fingerprint(config_payload),
        "contract_version": TRUST_CONTRACT_VERSION,
        "pipeline_schema_version": str(pipeline_schema_version or "").strip(),
        "status_schema_version": str(status_schema_version or "").strip(),
    }


def build_bridge_identity(
    *,
    service_version: str,
    process_started_at: float,
    source_paths: Sequence[Path | str],
    config_payload: Mapping[str, Any],
    capabilities: Sequence[str],
    git_sha: str | None = None,
    dirty: bool | None = None,
) -> dict[str, Any]:
    resolved_git_sha, resolved_dirty = git_identity()
    if git_sha is not None:
        resolved_git_sha = str(git_sha or "").strip()
    if dirty is not None:
        resolved_dirty = bool(dirty)
    return {
        "component": "bridge",
        "role": "execution_bridge",
        "service_name": "gui_bridge",
        "service_version": str(service_version or "").strip(),
        "git_sha": resolved_git_sha,
        "dirty": bool(resolved_dirty),
        "process_started_at": utc_iso_from_timestamp(process_started_at),
        "build_fingerprint": build_fingerprint(source_paths),
        "config_fingerprint": config_fingerprint(config_payload),
        "contract_version": TRUST_CONTRACT_VERSION,
        "capabilities": [str(item).strip() for item in capabilities if str(item).strip()],
    }


def build_minimal_compatibility_contract(
    api_identity: Mapping[str, Any],
    bridge_identity: Mapping[str, Any],
) -> dict[str, Any]:
    blocking_reasons: list[str] = []

    api_contract_version = str(api_identity.get("contract_version") or "").strip()
    bridge_contract_version = str(bridge_identity.get("contract_version") or "").strip()
    api_pipeline_schema = str(api_identity.get("pipeline_schema_version") or "").strip()
    api_status_schema = str(api_identity.get("status_schema_version") or "").strip()
    bridge_capabilities = {
        str(item).strip()
        for item in list(bridge_identity.get("capabilities") or [])
        if str(item).strip()
    }

    if api_contract_version != TRUST_CONTRACT_VERSION:
        blocking_reasons.append("api_contract_version_mismatch")
    if bridge_contract_version != TRUST_CONTRACT_VERSION:
        blocking_reasons.append("bridge_contract_version_mismatch")
    if api_pipeline_schema != PIPELINE_SCHEMA_VERSION:
        blocking_reasons.append("api_pipeline_schema_version_mismatch")
    if api_status_schema != STATUS_SCHEMA_VERSION:
        blocking_reasons.append("api_status_schema_version_mismatch")
    missing_capabilities = [
        capability for capability in REQUIRED_BRIDGE_CAPABILITIES if capability not in bridge_capabilities
    ]
    if missing_capabilities:
        blocking_reasons.append(
            "bridge_capability_missing:" + ",".join(sorted(missing_capabilities))
        )

    api_git_sha = str(api_identity.get("git_sha") or "").strip()
    bridge_git_sha = str(bridge_identity.get("git_sha") or "").strip()
    git_sha_matched = not api_git_sha or not bridge_git_sha or api_git_sha == bridge_git_sha
    if not git_sha_matched:
        blocking_reasons.append("git_sha_mismatch")

    return {
        "contract_version": TRUST_CONTRACT_VERSION,
        "pipeline_schema_version": PIPELINE_SCHEMA_VERSION,
        "status_schema_version": STATUS_SCHEMA_VERSION,
        "required_bridge_capabilities": list(REQUIRED_BRIDGE_CAPABILITIES),
        "capability_compatibility_ok": not missing_capabilities,
        "git_sha_matched": git_sha_matched,
        "compatible": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
    }


def _identity_git_sha(identity: Mapping[str, Any], key: str = "git_sha") -> str:
    return str(identity.get(key) or "").strip()


def build_lane_comparability_contract(
    *,
    runner_identity: Mapping[str, Any],
    api_identity: Mapping[str, Any],
    bridge_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Hard-family local evidence requires runner/API/bridge code identity parity."""

    minimal = build_minimal_compatibility_contract(api_identity, bridge_identity)
    blocking_reasons = [str(item) for item in list(minimal.get("blocking_reasons") or [])]

    runner_git_sha = _identity_git_sha(runner_identity, "runner_git_sha")
    api_git_sha = _identity_git_sha(api_identity)
    bridge_git_sha = _identity_git_sha(bridge_identity)

    runner_api_git_sha_matched = bool(runner_git_sha and api_git_sha and runner_git_sha == api_git_sha)
    runner_bridge_git_sha_matched = bool(runner_git_sha and bridge_git_sha and runner_git_sha == bridge_git_sha)
    api_bridge_git_sha_matched = bool(api_git_sha and bridge_git_sha and api_git_sha == bridge_git_sha)

    if not runner_git_sha:
        blocking_reasons.append("runner_git_sha_missing")
    if not api_git_sha:
        blocking_reasons.append("api_git_sha_missing")
    if not bridge_git_sha:
        blocking_reasons.append("bridge_git_sha_missing")
    if runner_git_sha and api_git_sha and not runner_api_git_sha_matched:
        blocking_reasons.append("runner_api_git_sha_mismatch")
    if runner_git_sha and bridge_git_sha and not runner_bridge_git_sha_matched:
        blocking_reasons.append("runner_bridge_git_sha_mismatch")
    if api_git_sha and bridge_git_sha and not api_bridge_git_sha_matched:
        blocking_reasons.append("api_bridge_git_sha_mismatch")

    return {
        "contract_version": TRUST_CONTRACT_VERSION,
        "policy": "local_hard_family_exact_runner_api_bridge_git_sha_match_v1",
        "minimal_compatibility_contract": minimal,
        "runner_git_sha": runner_git_sha,
        "api_git_sha": api_git_sha,
        "bridge_git_sha": bridge_git_sha,
        "runner_dirty": bool(runner_identity.get("runner_dirty")),
        "api_dirty": bool(api_identity.get("dirty")),
        "bridge_dirty": bool(bridge_identity.get("dirty")),
        "runner_api_git_sha_matched": runner_api_git_sha_matched,
        "runner_bridge_git_sha_matched": runner_bridge_git_sha_matched,
        "api_bridge_git_sha_matched": api_bridge_git_sha_matched,
        "comparable": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
    }
