"""
api/routes/health_probes.py – Lab status probing and polling helpers.

Extracted from api/routes/main.py to keep endpoint handlers focused on HTTP
routing.  Functions here perform I/O (storage round-trips, HTTP probes, queue
checks) and maintain a module-level TTL cache to avoid hammering services on
every /api/lab/status request.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import httpx

from api.infra.config import (
    ARTIFACT_CONTAINER,
    ANALYSIS_QUEUE,
    STORAGE_BACKEND,
    GUI_BRIDGE_SECRET,
    GUI_BRIDGE_URL,
    LOCAL_DATA_ROOT,
    OPENAI_API_KEY,
    OPENAI_EXPLORE_MODEL,
    OPENAI_MODEL,
)
from api.infra.local_lane_admission import fetch_bridge_admission, is_loopback_url
from api.infra.storage import (
    _download_blob,
    _get_job_status,
    _persist_campaign_status,
    _queue_service_client,
    _upload_to_blob,
)
from api.infra.telemetry import _openai_client
from api.pipeline.core.runtime_api import (
    has_job_lifecycle_inconsistency,
    is_stale_cancel_requested_job_record,
    is_stale_nonterminal_job_record,
    is_terminal_job_record,
)

# ── TTL probe cache ────────────────────────────────────────────────────────

_LAB_PROBE_LOCK = threading.Lock()
_LAB_PROBE_CACHE: dict[str, dict[str, Any]] = {}
_LAB_PROBE_TTLS = {
    "bridge": 20.0,
    "model": 120.0,
    "storage": 20.0,
    "queue": 30.0,
}


def _configured_model_probe_timeout_seconds() -> float:
    try:
        return float(os.getenv("MCP_FACTORY_MODEL_PROBE_TIMEOUT_SEC", "5"))
    except (TypeError, ValueError):
        return 5.0


MODEL_PROBE_TIMEOUT_SECONDS = _configured_model_probe_timeout_seconds()


def _cached_lab_probe(name: str, fn) -> dict[str, Any]:
    ttl = float(_LAB_PROBE_TTLS.get(name, 30.0))
    now = time.time()
    with _LAB_PROBE_LOCK:
        cached = _LAB_PROBE_CACHE.get(name)
        if cached and (now - float(cached.get("checked_at") or 0.0)) < ttl:
            return dict(cached["value"])
    value = fn()
    value["checked_at"] = now
    with _LAB_PROBE_LOCK:
        _LAB_PROBE_CACHE[name] = {"checked_at": now, "value": dict(value)}
    return value


# ── Recent-job summary ─────────────────────────────────────────────────────

def _recent_job_entries(limit: int = 20) -> list[dict[str, Any]]:
    from api.infra.storage import _JOB_STATUS

    entries: list[dict[str, Any]] = []
    for jid, st in list(_JOB_STATUS.items()):
        if not isinstance(st, dict):
            continue
        verdict = st.get("macro_verdict") or {}
        entries.append({
            "job_id": jid,
            "component_name": st.get("component_name", ""),
            "status": st.get("status", "unknown"),
            "explore_phase": st.get("explore_phase", ""),
            "coverage_pct": verdict.get("coverage_pct", 0),
            "verified_count": verdict.get("verified_count", 0),
            "total_count": verdict.get("total_count", 0),
            "macro_status": verdict.get("status", ""),
            "created_at": st.get("created_at", 0),
        })
    entries.sort(key=lambda e: e.get("created_at", 0), reverse=True)
    return entries[:limit]


# ── Service health probes ──────────────────────────────────────────────────

def _probe_bridge_status() -> dict[str, Any]:
    if not GUI_BRIDGE_URL or not GUI_BRIDGE_SECRET:
        return {
            "status": "degraded",
            "configured": False,
            "reachable": False,
            "detail": "GUI bridge is not configured",
            "base_url": GUI_BRIDGE_URL or "",
        }
    try:
        headers = {"X-Bridge-Key": GUI_BRIDGE_SECRET}
        identity = httpx.get(
            f"{GUI_BRIDGE_URL}/identity",
            headers=headers,
            timeout=10.0,
        )
        identity.raise_for_status()
        readiness = httpx.get(
            f"{GUI_BRIDGE_URL}/readiness",
            headers=headers,
            timeout=10.0,
        )
        readiness.raise_for_status()
        identity_payload = identity.json() if identity.content else {}
        readiness_payload = readiness.json() if readiness.content else {}
        admission_payload = fetch_bridge_admission(GUI_BRIDGE_URL, GUI_BRIDGE_SECRET) or {}
        bridge_status = "ok"
        if not bool(admission_payload.get("admitted")):
            bridge_status = "degraded"
        elif not bool(readiness_payload.get("ready")):
            bridge_status = "degraded"
        return {
            "status": bridge_status,
            "configured": True,
            "reachable": True,
            "detail": "admitted" if bridge_status == "ok" else str(
                (admission_payload.get("blocking_reasons") or readiness_payload.get("blocking_reasons") or ["bridge_not_ready"])[0]
            ),
            "base_url": GUI_BRIDGE_URL,
            "host_is_loopback": is_loopback_url(GUI_BRIDGE_URL),
            "identity": identity_payload,
            "readiness": readiness_payload,
            "admission": admission_payload,
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "configured": True,
            "reachable": False,
            "detail": str(exc),
            "base_url": GUI_BRIDGE_URL,
            "host_is_loopback": is_loopback_url(GUI_BRIDGE_URL),
        }


def _probe_model_status() -> dict[str, Any]:
    if not OPENAI_API_KEY:
        return {
            "status": "invalid",
            "configured": False,
            "reachable": False,
            "default_model": OPENAI_MODEL,
            "explore_model": OPENAI_EXPLORE_MODEL,
            "detail": "OPENAI_API_KEY is not configured",
        }
    try:
        client = _openai_client()
        if hasattr(client, "with_options"):
            client = client.with_options(timeout=MODEL_PROBE_TIMEOUT_SECONDS)
        client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Reply with OK."},
                {"role": "user", "content": "OK"},
            ],
            max_tokens=1,
        )
        return {
            "status": "ok",
            "configured": True,
            "reachable": True,
            "default_model": OPENAI_MODEL,
            "explore_model": OPENAI_EXPLORE_MODEL,
            "detail": "Direct OpenAI path reachable",
        }
    except Exception as exc:
        return {
            "status": "invalid",
            "configured": True,
            "reachable": False,
            "default_model": OPENAI_MODEL,
            "explore_model": OPENAI_EXPLORE_MODEL,
            "detail": str(exc),
        }


def _probe_storage_status() -> dict[str, Any]:
    probe_blob = "_probe/lab-status.txt"
    payload = f"lab-ok:{int(time.time())}".encode("utf-8")
    try:
        _upload_to_blob(ARTIFACT_CONTAINER, probe_blob, payload)
        echoed = _download_blob(ARTIFACT_CONTAINER, probe_blob)
        if echoed != payload:
            raise RuntimeError("artifact storage round-trip mismatch")
        return {
            "status": "ok",
            "backend": STORAGE_BACKEND,
            "detail": "Artifact storage round-trip succeeded",
            "artifact_container": ARTIFACT_CONTAINER,
            "local_data_root": str(LOCAL_DATA_ROOT),
        }
    except Exception as exc:
        return {
            "status": "invalid",
            "backend": STORAGE_BACKEND,
            "detail": str(exc),
            "artifact_container": ARTIFACT_CONTAINER,
            "local_data_root": str(LOCAL_DATA_ROOT),
        }


def _probe_queue_status() -> dict[str, Any]:
    if STORAGE_BACKEND == "local":
        return {
            "status": "ok",
            "backend": "local_dispatch",
            "detail": "Local workflow uses in-process dispatch",
            "queue_name": ANALYSIS_QUEUE,
        }
    try:
        svc = _queue_service_client()
        if svc is None:
            return {
                "status": "degraded",
                "backend": STORAGE_BACKEND,
                "detail": "Storage queue client not configured",
                "queue_name": ANALYSIS_QUEUE,
            }
        svc.get_queue_client(ANALYSIS_QUEUE).get_queue_properties()
        return {
            "status": "ok",
            "backend": STORAGE_BACKEND,
            "detail": "Storage queue reachable",
            "queue_name": ANALYSIS_QUEUE,
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "backend": STORAGE_BACKEND,
            "detail": str(exc),
            "queue_name": ANALYSIS_QUEUE,
        }


# ── Job and lane helpers ───────────────────────────────────────────────────

def _select_active_job(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible_entries = [
        entry
        for entry in entries
        if not is_stale_cancel_requested_job_record(entry)
        and not is_stale_nonterminal_job_record(entry)
    ]
    for entry in eligible_entries:
        if not is_terminal_job_record(entry):
            return entry
    return eligible_entries[0] if eligible_entries else (entries[0] if entries else None)


def _compute_lane_validity(
    *,
    bridge: dict[str, Any],
    model: dict[str, Any],
    storage: dict[str, Any],
    queue: dict[str, Any],
    active_job: dict[str, Any] | None,
) -> dict[str, Any]:
    status = "valid"
    reasons: list[str] = []
    warnings: list[str] = []
    promotion_safe = True

    if storage.get("status") != "ok":
        status = "invalid"
        promotion_safe = False
        reasons.append("artifact storage is not healthy")
    if model.get("status") != "ok":
        status = "invalid"
        promotion_safe = False
        reasons.append("OpenAI model path is not healthy")
    if bridge.get("status") != "ok":
        if status != "invalid":
            status = "degraded"
        promotion_safe = False
        warnings.append("GUI bridge is unavailable or degraded")
    if queue.get("status") != "ok":
        if status == "valid":
            status = "degraded"
        warnings.append("dispatch queue is degraded")
    if active_job:
        if has_job_lifecycle_inconsistency(active_job):
            if status == "valid":
                status = "degraded"
            promotion_safe = False
            warnings.append("active job reports done while explore_phase is still exploring")

    return {
        "status": status,
        "promotion_safe": promotion_safe,
        "reasons": reasons,
        "warnings": warnings,
    }


def _refresh_campaign_poll_state(
    camp: dict[str, Any],
    *,
    get_job_status_fn=None,
    persist_campaign_status_fn=None,
) -> dict[str, Any]:
    get_job_status_fn = get_job_status_fn or _get_job_status
    persist_campaign_status_fn = persist_campaign_status_fn or _persist_campaign_status
    entries = list(camp.get("dll_entries") or [])
    changed = False
    inconsistent = False

    for entry in entries:
        jid = str(entry.get("job_id") or "").strip()
        if not jid:
            continue
        job_status = get_job_status_fn(jid) or {}
        if not job_status:
            continue
        raw_status = str(job_status.get("status") or "").strip().lower()
        raw_phase = str(job_status.get("explore_phase") or "").strip().lower()
        if entry.get("job_status") != raw_status:
            entry["job_status"] = raw_status
            changed = True
        if entry.get("explore_phase") != raw_phase:
            entry["explore_phase"] = raw_phase
            changed = True
        if has_job_lifecycle_inconsistency(job_status):
            inconsistent = True
            desired_error = (
                "Lifecycle inconsistency: child job reached status=done while "
                "explore_phase remained exploring"
            )
            if entry.get("status") != "failed":
                entry["status"] = "failed"
                changed = True
            if entry.get("error") != desired_error:
                entry["error"] = desired_error
                changed = True
            continue
        if is_terminal_job_record(job_status):
            desired = "failed" if raw_status == "error" else "done"
            if entry.get("status") != desired:
                entry["status"] = desired
                changed = True

    if inconsistent and str(camp.get("phase") or "").lower() not in {"done", "partial_failure", "cancelled_partial"}:
        camp["phase"] = "partial_failure"
        changed = True

    if changed:
        camp["dll_entries"] = entries
        camp["updated_at"] = time.time()
        persist_campaign_status_fn(str(camp.get("campaign_id") or ""), camp, sync=True)
    return camp
