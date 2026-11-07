from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import httpx

from api.infra.service_identity import (
    REQUIRED_BRIDGE_CAPABILITIES,
    TRUST_CONTRACT_VERSION,
    build_minimal_compatibility_contract,
    utc_iso_from_timestamp,
)
from runtime.runtime_contract import runtime_contract_id, runtime_system


LOCAL_LANE_ADMISSION_VERSION = "local_lane_admission_v1"
STRICT_LOCAL_RUNTIME_MODE = "strict_local"
LOCAL_RUNTIME_MAX_AGE_SECONDS = 5 * 60 * 60
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def canonical_runtime_base_url(system_name: str) -> str:
    system = runtime_system(system_name)
    scheme = str(system.get("scheme") or "http").strip() or "http"
    host = str(system.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    port = int(system["port"])
    return f"{scheme}://{host}:{port}"


def admission_path(system_name: str) -> str:
    system = runtime_system(system_name)
    return str(system.get("local_lane_admission_path") or "/local-lane-admission").strip()


def _host_from_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    return str(parsed.hostname or "").strip().lower()


def is_loopback_url(value: str) -> bool:
    return _host_from_url(value) in _LOOPBACK_HOSTS


def _latest_source_mtime(source_paths: Sequence[Path | str]) -> float | None:
    latest: float | None = None
    for raw_path in source_paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        try:
            if path.is_dir():
                candidates = [path, *path.rglob("*")]
            else:
                candidates = [path]
        except Exception:
            candidates = [path]
        for candidate in candidates:
            try:
                stamp = float(candidate.stat().st_mtime)
            except Exception:
                continue
            latest = stamp if latest is None else max(latest, stamp)
    return latest


def freshness_payload(
    *,
    process_started_at: float | None,
    source_paths: Sequence[Path | str],
) -> dict[str, Any]:
    started_at = float(process_started_at) if process_started_at is not None else None
    now = time.time()
    age_seconds = max(now - started_at, 0.0) if started_at is not None else None
    source_latest_mtime = _latest_source_mtime(source_paths)
    verdict = "fresh"
    if started_at is None:
        verdict = "freshness_unknown"
    elif source_latest_mtime is not None and source_latest_mtime > started_at:
        verdict = "stale_code_newer"
    elif age_seconds is not None and age_seconds > LOCAL_RUNTIME_MAX_AGE_SECONDS:
        verdict = "stale_age"
    return {
        "freshness_verdict": verdict,
        "fresh": verdict == "fresh",
        "process_started_at": utc_iso_from_timestamp(started_at),
        "process_started_at_epoch": started_at,
        "age_seconds": age_seconds,
        "age_threshold_seconds": LOCAL_RUNTIME_MAX_AGE_SECONDS,
        "source_latest_mtime_epoch": source_latest_mtime,
        "source_latest_mtime": utc_iso_from_timestamp(source_latest_mtime),
    }


def fetch_json_payload(
    *,
    base_url: str,
    path: str,
    headers: Mapping[str, str] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any] | None:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return None
    try:
        response = httpx.get(
            f"{base}{path}",
            headers=dict(headers or {}),
            timeout=timeout,
        )
        response.raise_for_status()
    except Exception:
        return None
    try:
        payload = response.json()
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def fetch_api_admission(api_url: str, api_key: str = "") -> dict[str, Any] | None:
    headers = {"X-Pipeline-Key": api_key} if api_key else {}
    return fetch_json_payload(
        base_url=api_url,
        path=admission_path("api"),
        headers=headers,
        timeout=15.0,
    )


def fetch_bridge_admission(bridge_url: str, bridge_key: str = "") -> dict[str, Any] | None:
    headers = {"X-Bridge-Key": bridge_key} if bridge_key else {}
    return fetch_json_payload(
        base_url=bridge_url,
        path=admission_path("bridge"),
        headers=headers,
        timeout=15.0,
    )


def _local_readiness_ok(readiness_payload: Mapping[str, Any] | None) -> tuple[bool, list[str]]:
    readiness = dict(readiness_payload or {})
    if not readiness:
        return False, ["readiness_unavailable"]
    if bool(readiness.get("ready")):
        return True, []
    blocking = [
        str(item).strip()
        for item in list(readiness.get("blocking_reasons") or [])
        if str(item).strip() and str(item).strip() != "model_not_ready"
    ]
    if not blocking:
        blocking = [
            str(readiness.get("blocking_reason") or "").strip()
        ]
        blocking = [item for item in blocking if item and item != "model_not_ready"]
    return not blocking, blocking


def build_bridge_local_lane_admission(
    *,
    identity_payload: Mapping[str, Any],
    readiness_payload: Mapping[str, Any],
    process_started_at: float | None,
    source_paths: Sequence[Path | str],
    configured_base_url: str,
    secret_configured: bool,
) -> dict[str, Any]:
    canonical_base_url = canonical_runtime_base_url("bridge")
    readiness_ok, readiness_blockers = _local_readiness_ok(readiness_payload)
    identity = dict(identity_payload or {})
    capabilities = {
        str(item).strip()
        for item in list(identity.get("capabilities") or [])
        if str(item).strip()
    }
    missing_capabilities = [
        capability
        for capability in REQUIRED_BRIDGE_CAPABILITIES
        if capability not in capabilities
    ]
    compatibility_ok = not missing_capabilities
    host_is_loopback = is_loopback_url(configured_base_url)
    identity_ok = (
        str(identity.get("component") or "").strip() == "bridge"
        and str(identity.get("role") or "").strip() == "execution_bridge"
        and str(identity.get("contract_version") or "").strip() == TRUST_CONTRACT_VERSION
    )
    freshness = freshness_payload(
        process_started_at=process_started_at,
        source_paths=source_paths,
    )
    managed_owner = host_is_loopback and configured_base_url == canonical_base_url and identity_ok
    blocking_reasons: list[str] = []
    if not host_is_loopback:
        blocking_reasons.append("bridge_not_loopback")
    if configured_base_url != canonical_base_url:
        blocking_reasons.append("bridge_base_url_not_canonical")
    if not identity_ok:
        blocking_reasons.append("bridge_identity_invalid")
    if not readiness_ok:
        blocking_reasons.extend(
            [f"bridge_{item}" if not item.startswith("bridge_") else item for item in readiness_blockers]
        )
    if not secret_configured:
        blocking_reasons.append("bridge_secret_missing")
    if not compatibility_ok:
        blocking_reasons.extend(
            f"bridge_capability_missing:{capability}" for capability in missing_capabilities
        )
    if freshness["freshness_verdict"] != "fresh":
        blocking_reasons.append(f"bridge_{freshness['freshness_verdict']}")
    if not managed_owner:
        blocking_reasons.append("bridge_managed_owner_false")
    blocking_reasons = list(dict.fromkeys(blocking_reasons))
    return {
        "contract_version": LOCAL_LANE_ADMISSION_VERSION,
        "runtime_contract_id": runtime_contract_id(),
        "component": "bridge",
        "role": "execution_bridge",
        "runtime_mode": STRICT_LOCAL_RUNTIME_MODE,
        "canonical_base_url": canonical_base_url,
        "configured_base_url": configured_base_url,
        "host_is_loopback": host_is_loopback,
        "managed_owner": managed_owner,
        "freshness_verdict": freshness["freshness_verdict"],
        "identity_ok": identity_ok,
        "readiness_ok": readiness_ok,
        "admitted": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "required_capabilities": list(REQUIRED_BRIDGE_CAPABILITIES),
        "capability_compatibility_ok": compatibility_ok,
        "secret_configured": bool(secret_configured),
        "freshness": freshness,
    }


def build_api_local_lane_admission(
    *,
    identity_payload: Mapping[str, Any],
    readiness_payload: Mapping[str, Any],
    process_started_at: float | None,
    source_paths: Sequence[Path | str],
    configured_base_url: str,
    storage_backend: str,
    bridge_identity_payload: Mapping[str, Any] | None,
    bridge_readiness_payload: Mapping[str, Any] | None,
    bridge_admission_payload: Mapping[str, Any] | None,
    model_provider: str,
    model_reachable: bool,
) -> dict[str, Any]:
    canonical_base_url = canonical_runtime_base_url("api")
    readiness_ok, readiness_blockers = _local_readiness_ok(readiness_payload)
    identity = dict(identity_payload or {})
    bridge_identity = dict(bridge_identity_payload or {})
    bridge_readiness = dict(bridge_readiness_payload or {})
    bridge_admission = dict(bridge_admission_payload or {})
    identity_ok = (
        str(identity.get("component") or "").strip() == "api"
        and str(identity.get("role") or "").strip() == "pipeline_control_plane"
        and str(identity.get("contract_version") or "").strip() == TRUST_CONTRACT_VERSION
    )
    host_is_loopback = is_loopback_url(configured_base_url)
    freshness = freshness_payload(
        process_started_at=process_started_at,
        source_paths=source_paths,
    )
    bridge_identity_ok = (
        str(bridge_identity.get("component") or "").strip() == "bridge"
        and str(bridge_identity.get("role") or "").strip() == "execution_bridge"
        and str(bridge_identity.get("contract_version") or "").strip() == TRUST_CONTRACT_VERSION
    )
    bridge_readiness_ok = bool(bridge_readiness.get("ready"))
    compatibility = build_minimal_compatibility_contract(identity, bridge_identity) if bridge_identity_ok else {
        "compatible": False,
        "blocking_reasons": ["bridge_identity_invalid"],
        "capability_compatibility_ok": False,
    }
    bridge_capability_compatibility_ok = bool(compatibility.get("capability_compatibility_ok"))
    bridge_admission_ok = bool(bridge_admission.get("admitted"))
    storage_backend_norm = str(storage_backend or "").strip().lower()
    storage_local_ok = storage_backend_norm == "local"
    managed_owner = host_is_loopback and configured_base_url == canonical_base_url and identity_ok
    blocking_reasons: list[str] = []
    if not host_is_loopback:
        blocking_reasons.append("api_not_loopback")
    if configured_base_url != canonical_base_url:
        blocking_reasons.append("api_base_url_not_canonical")
    if not identity_ok:
        blocking_reasons.append("api_identity_invalid")
    if not readiness_ok:
        blocking_reasons.extend(
            [f"api_{item}" if not item.startswith("api_") else item for item in readiness_blockers]
        )
    if freshness["freshness_verdict"] != "fresh":
        blocking_reasons.append(f"api_{freshness['freshness_verdict']}")
    if not storage_local_ok:
        blocking_reasons.append("storage_backend_not_local")
    if not bridge_identity_ok:
        blocking_reasons.append("bridge_identity_invalid")
    if not bridge_readiness_ok:
        blocking_reason = str(bridge_readiness.get("blocking_reason") or "bridge_not_ready").strip()
        blocking_reasons.append(blocking_reason or "bridge_not_ready")
    if not bridge_capability_compatibility_ok:
        blocking_reasons.extend(str(item) for item in list(compatibility.get("blocking_reasons") or []) if str(item))
    if not bridge_admission_ok:
        blocking_reasons.append("bridge_admission_not_green")
        blocking_reasons.extend(
            f"bridge_admission:{item}"
            for item in list(bridge_admission.get("blocking_reasons") or [])
            if str(item).strip()
        )
    if not managed_owner:
        blocking_reasons.append("api_managed_owner_false")
    blocking_reasons = list(dict.fromkeys(blocking_reasons))
    return {
        "contract_version": LOCAL_LANE_ADMISSION_VERSION,
        "runtime_contract_id": runtime_contract_id(),
        "component": "api",
        "role": "pipeline_control_plane",
        "runtime_mode": STRICT_LOCAL_RUNTIME_MODE,
        "canonical_base_url": canonical_base_url,
        "configured_base_url": configured_base_url,
        "host_is_loopback": host_is_loopback,
        "managed_owner": managed_owner,
        "freshness_verdict": freshness["freshness_verdict"],
        "identity_ok": identity_ok,
        "readiness_ok": readiness_ok,
        "admitted": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "storage_backend": storage_backend_norm,
        "storage_local_ok": storage_local_ok,
        "bridge_identity_ok": bridge_identity_ok,
        "bridge_readiness_ok": bridge_readiness_ok,
        "bridge_capability_compatibility_ok": bridge_capability_compatibility_ok,
        "bridge_admission_ok": bridge_admission_ok,
        "model_provider": str(model_provider or "").strip(),
        "model_reachable": bool(model_reachable),
        "freshness": freshness,
    }
