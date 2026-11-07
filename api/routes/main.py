"""
api/main.py – MCP Factory REST API
Exposes the discovery pipeline and MCP generation over HTTP.
Integrates with local artifact storage, direct OpenAI, and optional telemetry.

Logic lives in the sub-modules imported below; this file contains only the
FastAPI app, middleware, endpoint handlers (thin wrappers), and startup event.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import re
import secrets as _secrets
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

# ── Sub-module imports — constants, telemetry, helpers ────────────────────
from api.infra.config import (
    PIPELINE_API_KEY,
    UPLOAD_CONTAINER,
    ARTIFACT_CONTAINER,
    ANALYSIS_QUEUE,
    STORAGE_BACKEND,
    GUI_BRIDGE_SECRET,
    GUI_BRIDGE_URL,
    LOCAL_DATA_ROOT,
    OPENAI_API_KEY,
    OPENAI_EXPLORE_MODEL,
    OPENAI_MAX_TOOLS,
    OPENAI_MODEL,
    _SAFE_PATH_PREFIXES,
)
from api.infra.local_lane_admission import (
    build_api_local_lane_admission,
    canonical_runtime_base_url,
)
from api.infra.service_identity import (
    PIPELINE_SCHEMA_VERSION,
    STATUS_SCHEMA_VERSION,
    TRUST_CONTRACT_VERSION,
    build_api_identity,
    git_identity,
)
from api.infra.storage import (
    _upload_to_blob,
    _download_blob,
    _list_blob_names,
    _persist_job_status,
    _get_job_status,
    _get_invocable,
    _enqueue_analysis,
    _load_findings,
    _persist_campaign_status,
    _get_campaign_status,
    _queue_service_client,
)
from api.infra.storage_api import (
    append_job_debug_event,
    get_invocables_map,
    patch_finding,
    register_invocables,
)
from api.infra.telemetry import _openai_client
from api.infra.worker import _queue_worker_loop, _analyze_worker
from api.services.executor import _execute_tool
from api.services.chat import stream_chat
from api.services.discovery import validate_gui_bridge_url_override
from api.services.generate import run_generate
from api.pipeline.core.helpers import _infer_param_desc
from api.pipeline.core.explore_config import GAP_RESOLUTION_ENABLED as _GAP_RESOLUTION_ENABLED
from api.pipeline.core.finding_status import normalize_status
from api.pipeline.core.runtime_api import (
    has_job_lifecycle_inconsistency,
    is_stale_cancel_requested_job_record,
    is_stale_nonterminal_job_record,
    is_terminal_job_record,
)
from api.pipeline.core.job_terminalization import build_job_terminalization_payload

from api.routes.body_parsers import (
    _as_bool,
    _as_int,
    _as_float,
    _normalize_explore_runtime_settings,
    _normalize_campaign_per_dll_explore_settings,
    _normalize_campaign_active_dll_targets,
    _extract_campaign_floor_plan,
    _extract_campaign_decomposition_plan,
    _apply_default_repeat_seed,
    _normalize_ablation_tags,
)
from api.routes.health_probes import (
    _LAB_PROBE_LOCK,
    _LAB_PROBE_CACHE,
    _LAB_PROBE_TTLS,
    _cached_lab_probe,
    _recent_job_entries,
    _probe_bridge_status,
    _probe_model_status,
    _probe_storage_status,
    _probe_queue_status,
    _select_active_job,
    _compute_lane_validity,
    _refresh_campaign_poll_state,
)
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("mcp_factory.api")
# Attach a dedicated stdout handler so our logs survive uvicorn's
# logging.config.dictConfig() which resets root handlers on startup.
if not logger.handlers:
    _stdout_handler = logging.StreamHandler(sys.stdout)
    _stdout_handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.addHandler(_stdout_handler)
    logger.propagate = False  # don't double-log through the root logger

# Serialize analyze-path requests so concurrent calls don't compete on the
# bridge's cancel-and-replace logic (_active_kill_event / _active_target_stem).
_analyze_path_lock = threading.Lock()
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SESSIONS_ROOT = _REPO_ROOT / "sessions"
_UPLOAD_INVESTIGATION_ARTIFACT = "upload_investigation.json"
_SAVED_SESSION_DIR_CACHE: dict[str, Path] = {}
_API_PROCESS_STARTED_AT = time.time()
_API_PROCESS_GIT_SHA, _API_PROCESS_DIRTY = git_identity(_REPO_ROOT)
_UPLOAD_EVENT_QUEUE: queue.Queue[tuple[str, str, dict[str, object]]] = queue.Queue(maxsize=512)
_UPLOAD_EVENT_WORKER_STARTED = False
_UPLOAD_EVENT_WORKER_LOCK = threading.Lock()


def _blob_upload_timeout_sec() -> float:
    raw = str(os.getenv("MCP_FACTORY_ANALYZE_BLOB_UPLOAD_TIMEOUT_SEC", "15")).strip()
    try:
        return max(0.1, float(raw))
    except ValueError:
        return 15.0


def _upload_to_blob_bounded(container: str, blob_name: str, content: bytes) -> dict[str, Any]:
    started = time.time()
    result: dict[str, Any] = {
        "returned": False,
        "timed_out": False,
        "ok": False,
        "elapsed_ms": None,
        "exception_class": "",
        "exception_message": "",
    }

    def _target() -> None:
        try:
            _upload_to_blob(container, blob_name, content)
            result["ok"] = True
        except Exception as exc:  # noqa: BLE001 - this is a route-level fail-open boundary.
            result["exception_class"] = type(exc).__name__
            result["exception_message"] = str(exc)
        finally:
            result["returned"] = True
            result["elapsed_ms"] = round((time.time() - started) * 1000, 3)

    thread = threading.Thread(
        target=_target,
        daemon=True,
        name=f"blob-upload-boundary-{blob_name.replace('/', '-')}",
    )
    thread.start()
    thread.join(_blob_upload_timeout_sec())
    if thread.is_alive():
        result["timed_out"] = True
        result["elapsed_ms"] = round((time.time() - started) * 1000, 3)
    return result


def _api_identity_payload() -> dict[str, Any]:
    return build_api_identity(
        service_version=app.version,
        process_started_at=_API_PROCESS_STARTED_AT,
        source_paths=(
            Path(__file__),
            _REPO_ROOT / "api" / "routes" / "health_probes.py",
            _REPO_ROOT / "api" / "infra" / "config.py",
        ),
        config_payload={
            "storage_backend": STORAGE_BACKEND,
            "gui_bridge_url": GUI_BRIDGE_URL,
            "pipeline_api_key_configured": bool(PIPELINE_API_KEY),
            "gui_bridge_secret_configured": bool(GUI_BRIDGE_SECRET),
            "openai_api_key_configured": bool(OPENAI_API_KEY),
            "openai_model": OPENAI_MODEL,
            "openai_explore_model": OPENAI_EXPLORE_MODEL,
            "openai_max_tools": OPENAI_MAX_TOOLS,
            "analysis_queue": ANALYSIS_QUEUE,
            "artifact_container": ARTIFACT_CONTAINER,
            "local_data_root": str(LOCAL_DATA_ROOT),
        },
        status_schema_version=STATUS_SCHEMA_VERSION,
        pipeline_schema_version=PIPELINE_SCHEMA_VERSION,
        git_sha=_API_PROCESS_GIT_SHA,
        dirty=_API_PROCESS_DIRTY,
    )


def _api_dependency_snapshots() -> dict[str, dict[str, Any]]:
    return {
        "bridge": _cached_lab_probe("bridge", _probe_bridge_status),
        "model": _cached_lab_probe("model", _probe_model_status),
        "storage": _cached_lab_probe("storage", _probe_storage_status),
        "queue": _cached_lab_probe("queue", _probe_queue_status),
    }


def _api_readiness_payload() -> dict[str, Any]:
    dependencies = _api_dependency_snapshots()
    bridge = dependencies["bridge"]
    model = dependencies["model"]
    storage = dependencies["storage"]
    queue = dependencies["queue"]

    blocking_reasons: list[str] = []
    if storage.get("status") != "ok":
        blocking_reasons.append("storage_not_ready")
    if queue.get("status") != "ok":
        blocking_reasons.append("queue_not_ready")
    if model.get("status") != "ok":
        blocking_reasons.append("model_not_ready")
    if bridge.get("status") != "ok":
        blocking_reasons.append("bridge_not_ready")

    ready = not blocking_reasons
    return {
        "component": "api",
        "ready": ready,
        "checked_at": time.time(),
        "contract_version": TRUST_CONTRACT_VERSION,
        "pipeline_schema_version": PIPELINE_SCHEMA_VERSION,
        "status_schema_version": STATUS_SCHEMA_VERSION,
        "dependencies": dependencies,
        "blocking_reason": "" if ready else blocking_reasons[0],
        "blocking_reasons": blocking_reasons,
    }


def _api_local_lane_admission_payload() -> dict[str, Any]:
    readiness_payload = _api_readiness_payload()
    bridge = dict((readiness_payload.get("dependencies") or {}).get("bridge") or {})
    model = dict((readiness_payload.get("dependencies") or {}).get("model") or {})
    return build_api_local_lane_admission(
        identity_payload=_api_identity_payload(),
        readiness_payload=readiness_payload,
        process_started_at=_API_PROCESS_STARTED_AT,
        source_paths=(
            Path(__file__),
            _REPO_ROOT / "api" / "routes" / "health_probes.py",
            _REPO_ROOT / "api" / "infra" / "config.py",
            _REPO_ROOT / "api" / "infra" / "local_lane_admission.py",
        ),
        configured_base_url=canonical_runtime_base_url("api"),
        storage_backend=STORAGE_BACKEND,
        bridge_identity_payload=bridge.get("identity") or {},
        bridge_readiness_payload=bridge.get("readiness") or {},
        bridge_admission_payload=bridge.get("admission") or {},
        model_provider="openai_direct",
        model_reachable=bool(model.get("reachable")),
    )


def _ensure_upload_event_worker() -> None:
    global _UPLOAD_EVENT_WORKER_STARTED
    if _UPLOAD_EVENT_WORKER_STARTED:
        return
    with _UPLOAD_EVENT_WORKER_LOCK:
        if _UPLOAD_EVENT_WORKER_STARTED:
            return

        def _worker() -> None:
            while True:
                job_id, phase, payload = _UPLOAD_EVENT_QUEUE.get()
                try:
                    append_job_debug_event(job_id, _UPLOAD_INVESTIGATION_ARTIFACT, payload)
                except Exception as exc:  # noqa: BLE001 - diagnostic writes must fail open.
                    logger.warning(
                        "[%s] Failed to append upload investigation event (%s): %s",
                        job_id,
                        phase,
                        exc,
                    )
                finally:
                    _UPLOAD_EVENT_QUEUE.task_done()

        thread = threading.Thread(
            target=_worker,
            daemon=True,
            name="upload-investigation-event-writer",
        )
        thread.start()
        _UPLOAD_EVENT_WORKER_STARTED = True


def _enqueue_upload_event(job_id: str, phase: str, payload: dict[str, object]) -> bool:
    _ensure_upload_event_worker()
    try:
        _UPLOAD_EVENT_QUEUE.put_nowait((job_id, phase, payload))
        return True
    except queue.Full:
        logger.warning("[%s] Upload investigation event queue full; dropping %s", job_id, phase)
        return False


def _record_upload_event(job_id: str, phase: str, **fields: object) -> None:
    try:
        payload = {
            "source": "route",
            "phase": phase,
            "pid": os.getpid(),
            "thread_name": threading.current_thread().name,
            **fields,
        }
        _enqueue_upload_event(job_id, phase, payload)
    except Exception as exc:  # noqa: BLE001 - diagnostic writes must fail open.
        logger.warning("[%s] Failed to enqueue upload investigation event (%s): %s", job_id, phase, exc)

# ── FastAPI app ────────────────────────────────────────────────────────────
app = FastAPI(title="MCP Factory API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _pipeline_api_key_guard(request: Request, call_next):
    """If PIPELINE_API_KEY is set, every non-liveness request must present it."""
    if not PIPELINE_API_KEY:
        return await call_next(request)
    if request.url.path in {"/alive", "/health"}:
        return await call_next(request)
    provided = request.headers.get("X-Pipeline-Key", "")
    if not provided or not _secrets.compare_digest(provided, PIPELINE_API_KEY):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.middleware("http")
async def _request_timing(request: Request, call_next):
    """Emit per-request latency so az containerapp logs can act as an APM-lite."""
    t0 = time.perf_counter()
    response = await call_next(request)
    dt_ms = (time.perf_counter() - t0) * 1000.0
    logger.info(
        "[http] %s %s -> %s in %.1f ms",
        request.method,
        request.url.path,
        response.status_code,
        dt_ms,
    )
    return response


# ── Startup ────────────────────────────────────────────────────────────────

def _startup_probe() -> None:
    from api.infra.storage import _upload_to_blob, _queue_service_client
    from api.infra.config import ARTIFACT_CONTAINER, GUI_BRIDGE_URL, GUI_BRIDGE_SECRET

    # Probe 1: artifact storage
    try:
        _upload_to_blob(ARTIFACT_CONTAINER, "_probe/startup.txt", b"ok")
        logger.info("STARTUP ✓ Blob Storage reachable (container: %s)", ARTIFACT_CONTAINER)
    except Exception as exc:
        logger.error("STARTUP ✗ Blob Storage unreachable: %s", exc)

    # Probe 2: Storage Queue
    try:
        svc = _queue_service_client()
        if svc:
            svc.get_queue_client(ANALYSIS_QUEUE).get_queue_properties()
            logger.info("STARTUP ✓ Storage Queue reachable (queue: %s)", ANALYSIS_QUEUE)
        else:
            logger.warning("STARTUP — Storage Queue not configured")
    except Exception as exc:
        logger.error("STARTUP ✗ Storage Queue unreachable: %s", exc)

    # Probe 3: GUI Bridge
    if GUI_BRIDGE_URL and GUI_BRIDGE_SECRET:
        try:
            import httpx
            r = httpx.get(
                f"{GUI_BRIDGE_URL}/health",
                headers={"X-Bridge-Key": GUI_BRIDGE_SECRET},
                timeout=10,
            )
            r.raise_for_status()
            logger.info("STARTUP ✓ GUI Bridge reachable (%s)", GUI_BRIDGE_URL)
        except Exception as exc:
            logger.error("STARTUP ✗ GUI Bridge unreachable: %s", exc)
    else:
        logger.warning("STARTUP — GUI Bridge not configured (GUI_BRIDGE_URL or GUI_BRIDGE_SECRET missing)")


def _local_startup_probe() -> None:
    from api.infra.storage import _upload_to_blob, _queue_service_client
    from api.infra.config import ARTIFACT_CONTAINER, GUI_BRIDGE_URL, GUI_BRIDGE_SECRET

    try:
        _upload_to_blob(ARTIFACT_CONTAINER, "_probe/startup.txt", b"ok")
        logger.info("STARTUP OK artifact storage reachable (container: %s)", ARTIFACT_CONTAINER)
    except Exception as exc:
        logger.error("STARTUP FAIL artifact storage unreachable: %s", exc)

    if STORAGE_BACKEND == "local":
        logger.info("STARTUP OK local dispatch active (in-process worker)")
    else:
        try:
            svc = _queue_service_client()
            if svc:
                svc.get_queue_client(ANALYSIS_QUEUE).get_queue_properties()
                logger.info("STARTUP OK queue reachable (queue: %s)", ANALYSIS_QUEUE)
            else:
                logger.warning("STARTUP WARN queue not configured")
        except Exception as exc:
            logger.error("STARTUP FAIL queue unreachable: %s", exc)

    if GUI_BRIDGE_URL and GUI_BRIDGE_SECRET:
        try:
            import httpx

            r = httpx.get(
                f"{GUI_BRIDGE_URL}/health",
                headers={"X-Bridge-Key": GUI_BRIDGE_SECRET},
                timeout=10,
            )
            r.raise_for_status()
            logger.info("STARTUP OK GUI Bridge reachable (%s)", GUI_BRIDGE_URL)
        except Exception as exc:
            logger.error("STARTUP FAIL GUI Bridge unreachable: %s", exc)
    else:
        logger.warning("STARTUP WARN GUI Bridge not configured (GUI_BRIDGE_URL or GUI_BRIDGE_SECRET missing)")


@app.on_event("startup")
async def _startup():
    threading.Thread(target=_queue_worker_loop, daemon=True, name="queue-worker").start()
    threading.Thread(target=_local_startup_probe, daemon=True, name="startup-probe").start()


# ── Endpoints ──────────────────────────────────────────────────────────────


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _read_json_if_exists(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text_if_exists(path: Path) -> str:
    try:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _find_saved_session_dir(job_id: str) -> Path | None:
    if not job_id or not _SESSIONS_ROOT.exists():
        return None
    cached = _SAVED_SESSION_DIR_CACHE.get(job_id)
    if cached is not None and cached.exists():
        return cached
    _SAVED_SESSION_DIR_CACHE.pop(job_id, None)
    for candidate in _SESSIONS_ROOT.rglob("kpi_run.json"):
        payload = _read_json_if_exists(candidate)
        if isinstance(payload, dict) and str(payload.get("job_id") or "") == job_id:
            _SAVED_SESSION_DIR_CACHE[job_id] = candidate.parent
            return candidate.parent
    for candidate in _SESSIONS_ROOT.rglob("session-meta.json"):
        payload = _read_json_if_exists(candidate)
        if isinstance(payload, dict) and str(payload.get("job_id") or "") == job_id:
            _SAVED_SESSION_DIR_CACHE[job_id] = candidate.parent
            return candidate.parent
    return None


def _artifact_issue_detail(exc: Exception) -> str:
    detail = str(exc).strip()
    if detail:
        return f"{type(exc).__name__}: {detail.splitlines()[0][:200]}"
    return type(exc).__name__


def _is_missing_artifact_error(exc: Exception) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True
    for cls in type(exc).__mro__:
        if cls.__name__ in {"ResourceNotFoundError", "BlobNotFoundError"}:
            return True
    return False


def _artifact_read_issue(
    rel_path: str,
    source_kind: str,
    issue_kind: str,
    detail: str,
    *,
    session_dir: Path | None = None,
) -> dict[str, Any]:
    issue = {
        "path": rel_path,
        "source_kind": source_kind,
        "issue_kind": issue_kind,
        "detail": detail,
    }
    if session_dir is not None:
        issue["session_dir"] = str(session_dir)
    return issue


def _artifact_issue_notes(issues: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for issue in issues:
        path = str(issue.get("path") or "unknown")
        source_kind = str(issue.get("source_kind") or "unknown")
        issue_kind = str(issue.get("issue_kind") or "unknown")
        detail = str(issue.get("detail") or "unknown")
        notes.append(f"artifact_read_issue:{source_kind}:{path}:{issue_kind}:{detail}")
    return notes


def _overlay_artifact_issue_summary(summary: str, issues: list[dict[str, Any]]) -> str:
    if not issues:
        return summary
    lead = issues[0]
    path = str(lead.get("path") or "unknown")
    source_kind = str(lead.get("source_kind") or "unknown")
    issue_kind = str(lead.get("issue_kind") or "unknown")
    lead_summary = f"Artifact retrieval degraded for {path} via {source_kind} ({issue_kind})"
    if len(issues) > 1:
        lead_summary = f"{lead_summary}; +{len(issues) - 1} more issue(s)"
    if summary:
        return f"{lead_summary}. {summary}"
    return lead_summary


def _native_route_artifact_status(has_payload: bool, issues: list[dict[str, Any]]) -> str:
    if issues:
        return "degraded"
    return "native" if has_payload else "partial"


def _dedupe_artifact_read_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for issue in issues:
        key = (
            str(issue.get("path") or ""),
            str(issue.get("source_kind") or ""),
            str(issue.get("issue_kind") or ""),
            str(issue.get("detail") or ""),
            str(issue.get("session_dir") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


def _load_job_artifact_json(job_id: str, rel_path: str) -> tuple[dict[str, Any] | list[Any] | None, list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    source_artifacts: list[dict[str, Any]] = []
    derived_from: list[str] = []
    issues: list[dict[str, Any]] = []
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/{rel_path}")
    except Exception as exc:
        if _is_missing_artifact_error(exc):
            raw = None
        else:
            raw = None
            issues.append(_artifact_read_issue(rel_path, "blob", "read_error", _artifact_issue_detail(exc)))
    if raw is not None:
        try:
            payload = json.loads(raw)
            source_artifacts.append({"kind": "blob", "path": rel_path})
            derived_from.append(f"blob:{rel_path}")
            return payload, source_artifacts, derived_from, issues
        except Exception as exc:
            issues.append(_artifact_read_issue(rel_path, "blob", "parse_error", _artifact_issue_detail(exc)))
    session_dir = _find_saved_session_dir(job_id)
    if session_dir is not None:
        session_path = session_dir / rel_path
        if session_path.exists():
            try:
                payload = json.loads(session_path.read_text(encoding="utf-8"))
                source_artifacts.append({"kind": "session", "path": rel_path, "session_dir": str(session_dir)})
                derived_from.append(f"session:{rel_path}")
                return payload, source_artifacts, derived_from, issues
            except json.JSONDecodeError as exc:
                issues.append(
                    _artifact_read_issue(
                        rel_path,
                        "session",
                        "parse_error",
                        _artifact_issue_detail(exc),
                        session_dir=session_dir,
                    )
                )
            except Exception as exc:
                issues.append(
                    _artifact_read_issue(
                        rel_path,
                        "session",
                        "read_error",
                        _artifact_issue_detail(exc),
                        session_dir=session_dir,
                    )
                )
    return None, source_artifacts, derived_from, issues


def _load_job_artifact_text(job_id: str, rel_path: str) -> tuple[str, list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    source_artifacts: list[dict[str, Any]] = []
    derived_from: list[str] = []
    issues: list[dict[str, Any]] = []
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/{rel_path}")
    except Exception as exc:
        if _is_missing_artifact_error(exc):
            raw = None
        else:
            raw = None
            issues.append(_artifact_read_issue(rel_path, "blob", "read_error", _artifact_issue_detail(exc)))
    if raw is not None:
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            source_artifacts.append({"kind": "blob", "path": rel_path})
            derived_from.append(f"blob:{rel_path}")
            return text, source_artifacts, derived_from, issues
        except Exception as exc:
            issues.append(_artifact_read_issue(rel_path, "blob", "read_error", _artifact_issue_detail(exc)))
    session_dir = _find_saved_session_dir(job_id)
    if session_dir is not None:
        session_path = session_dir / rel_path
        if session_path.exists():
            try:
                text = session_path.read_text(encoding="utf-8")
                source_artifacts.append({"kind": "session", "path": rel_path, "session_dir": str(session_dir)})
                derived_from.append(f"session:{rel_path}")
                return text, source_artifacts, derived_from, issues
            except Exception as exc:
                issues.append(
                    _artifact_read_issue(
                        rel_path,
                        "session",
                        "read_error",
                        _artifact_issue_detail(exc),
                        session_dir=session_dir,
                    )
                )
    return "", source_artifacts, derived_from, issues


def _route_artifact(job_id: str, label: str, url: str, tier: str, summary: str = "") -> dict[str, Any]:
    return {
        "label": label,
        "url": url,
        "tier": tier,
        "kind": "native-route",
        "summary": summary,
        "evidence_type": "supporting",
        "why_it_matters": summary,
    }


def _classify_validation(validation_report: dict[str, Any] | None, fallback_text: str = "") -> dict[str, Any]:
    report = validation_report if isinstance(validation_report, dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    checked = _safe_int(summary.get("checked"), -1)
    verified_1to1 = _safe_int(summary.get("verified_1to1"))
    mismatch = _safe_int(summary.get("mismatch"))
    wrapper_unavailable = _safe_int(summary.get("wrapper_unavailable"))
    direct_error = _safe_int(summary.get("direct_error"))
    wrapper_error = _safe_int(summary.get("wrapper_error"))
    skipped = _safe_int(summary.get("skipped"))
    wrapper_load_error = str(report.get("wrapper_load_error") or "").strip()
    if checked == 0:
        status = "invalid"
        operator_summary = "Validation did not actually run."
    elif checked < 0:
        status = "unknown"
        operator_summary = "Validation status is missing."
    elif direct_error or wrapper_error or mismatch:
        status = "warn"
        operator_summary = "Validation ran with errors or mismatches."
    elif wrapper_unavailable or wrapper_load_error:
        status = "partial"
        operator_summary = "Validation ran, but wrapper coverage is incomplete."
    elif checked > 0 and verified_1to1 >= checked:
        status = "pass"
        operator_summary = "Validation completed with wrapper and direct checks aligned."
    else:
        status = "partial"
        operator_summary = "Validation completed only partially."
    notes: list[str] = []
    if not report and fallback_text:
        notes.append("validation-report.json missing; using markdown fallback text only")
    if wrapper_load_error:
        notes.append(f"wrapper_load_error:{wrapper_load_error}")
    return {
        "status": status,
        "checked": checked if checked >= 0 else 0,
        "verified_1to1": verified_1to1,
        "mismatch": mismatch,
        "wrapper_unavailable": wrapper_unavailable,
        "direct_error": direct_error,
        "wrapper_error": wrapper_error,
        "skipped": skipped,
        "wrapper_source": str(report.get("wrapper_source") or ""),
        "wrapper_load_error": wrapper_load_error,
        "operator_summary": operator_summary if not fallback_text or report else fallback_text.splitlines()[0].strip(),
        "analysis_basis": {
            "summary": summary,
            "entry_count": len(report.get("entries") or []) if isinstance(report.get("entries"), list) else 0,
            "wrapper_load_error": wrapper_load_error,
            "fallback_text_present": bool(fallback_text),
        },
        "notes": notes,
    }


def _verdict_layer_entry(status: str, summary: str, artifacts: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "summary": summary,
        "source_artifacts": artifacts,
    }


def _native_envelope(
    job_id: str,
    operator_view: dict[str, Any],
    analysis_view: dict[str, Any],
    source_artifacts: list[dict[str, Any]],
    derived_from: list[str],
    native_status: str,
    notes: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "job_id": job_id,
        "operator_summary": operator_view.get("summary") or operator_view.get("headline") or "",
        "analysis_basis": analysis_view,
        "operator_view": operator_view,
        "analysis_view": analysis_view,
        "source_artifacts": source_artifacts,
        "derived_from": derived_from,
        "native_status": native_status,
        "notes": notes or [],
    }
    payload.update(extra)
    return payload


def _family_bucket(value: str, owner_layer: str) -> str:
    raw = f"{value} {owner_layer}".lower()
    if "analysis-entry" in raw or "artifact emission" in raw or "discovery produced no output files" in raw:
        return "analysis-entry-failure"
    if "lineage" in raw or "state" in raw:
        return "state-lineage"
    if "contract" in raw:
        return "contract-mismatch"
    if "capture" in raw or "artifact" in raw:
        return "capture-gap"
    if "validation" in raw:
        return "validation-failure"
    if "architect" in raw or "cross-dll" in raw:
        return "architecture-bottleneck"
    if "contradict" in raw:
        return "contradiction-cluster"
    if "measure" in raw:
        return "measurement-gap"
    return "measurement-gap"


def _job_error_excerpt(job: dict[str, Any]) -> str:
    error = str(job.get("error") or "").strip()
    if error:
        return error.splitlines()[0].strip()
    message = str(job.get("message") or "").strip()
    if message:
        return message
    return "Job ended in error before trustworthy artifacts were emitted."


def _status_artifact(job_id: str) -> dict[str, Any]:
    return {"kind": "blob", "path": "status.json", "job_id": job_id}


def _detect_pre_artifact_failure(
    job_id: str,
    job: dict[str, Any],
    findings: list[dict[str, Any]] | None = None,
    *,
    report_text: str = "",
    stage_index: dict[str, Any] | list[Any] | None = None,
    transition_index: dict[str, Any] | list[Any] | None = None,
    run_validity: dict[str, Any] | list[Any] | None = None,
    kpi_run: dict[str, Any] | list[Any] | None = None,
    cohesion_report: dict[str, Any] | list[Any] | None = None,
) -> dict[str, Any] | None:
    job_status = str(job.get("status") or "").lower()
    if job_status != "error":
        return None
    finding_rows = findings if isinstance(findings, list) else []
    has_stage_artifacts = bool(stage_index) or bool(transition_index)
    has_core_artifacts = bool(run_validity) or bool(kpi_run) or bool(cohesion_report)
    report_documented_match = re.search(r"Functions documented:\s*(\d+)", report_text or "")
    documented_count = _safe_int(report_documented_match.group(1), -1) if report_documented_match else -1
    no_report_output = documented_count == 0 or not str(report_text or "").strip()
    error_text = f"{job.get('message') or ''}\n{job.get('error') or ''}".lower()
    discovery_failure = "discovery produced no output files" in error_text
    if not (
        not finding_rows
        and (discovery_failure or no_report_output or (not has_core_artifacts and not has_stage_artifacts))
    ):
        return None
    playbook_step = str(job.get("playbook_step") or "").strip()
    component = str(job.get("component_name") or job_id)
    chain_summary = (
        f"{playbook_step} for {component} failed before downstream chained steps could run."
        if playbook_step
        else f"{component} failed before downstream chained steps could run."
    )
    return {
        "title": "Analysis failed before discovery artifacts were emitted",
        "summary": _job_error_excerpt(job),
        "root_summary": "No trustworthy verdict can be formed because the iteration failed before core artifacts existed.",
        "stage": "analysis-entry",
        "family_id": "analysis-entry-failure",
        "blast_radius_summary": chain_summary,
        "recommended_next_action": "Inspect the job error and discovery entrypoint before rerunning downstream stages.",
        "analysis_view": {
            "job_status": job_status,
            "job_message": str(job.get("message") or ""),
            "error_excerpt": _job_error_excerpt(job),
            "has_findings": bool(finding_rows),
            "documented_function_count": documented_count,
            "has_stage_index": bool(stage_index),
            "has_transition_index": bool(transition_index),
            "has_run_validity": bool(run_validity),
            "has_kpi_run": bool(kpi_run),
            "has_cohesion_report": bool(cohesion_report),
            "discovery_output_missing": discovery_failure,
        },
        "source_artifacts": [_status_artifact(job_id)],
        "derived_from": ["status:error", "artifact-absence"],
    }


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(str(value or "").lower(), 5)


def _api_health_payload() -> dict[str, Any]:
    admission_payload = _api_local_lane_admission_payload()
    healthy = bool(admission_payload.get("admitted"))
    blocking_reasons = list(admission_payload.get("blocking_reasons") or [])
    return {
        "component": "api",
        "status": "ok" if healthy else "blocked",
        "healthy": healthy,
        "checked_at": time.time(),
        "contract_version": TRUST_CONTRACT_VERSION,
        "runtime_mode": "strict_local",
        "configured_base_url": canonical_runtime_base_url("api"),
        "blocking_reason": "" if healthy else (blocking_reasons[0] if blocking_reasons else "local_lane_not_admitted"),
        "blocking_reasons": blocking_reasons,
        "diagnostics": {
            "alive": "/alive",
            "identity": "/identity",
            "readiness": "/readiness",
            "local_lane_admission": "/local-lane-admission",
        },
    }


@app.get("/alive")
def alive():
    return {"status": "alive", "component": "api", "contract_version": TRUST_CONTRACT_VERSION}


@app.get("/health")
def health():
    payload = _api_health_payload()
    return JSONResponse(status_code=200 if payload["healthy"] else 503, content=payload)


@app.get("/identity")
def identity():
    return JSONResponse(_api_identity_payload())


@app.get("/readiness")
def readiness():
    return JSONResponse(_api_readiness_payload())


@app.get("/local-lane-admission")
def local_lane_admission():
    return JSONResponse(_api_local_lane_admission_payload())


@app.get("/api/lab/status")
async def lab_status():
    jobs = _recent_job_entries(limit=20)
    active_job = _select_active_job(jobs)
    dependencies = _api_dependency_snapshots()
    bridge = dependencies["bridge"]
    model = dependencies["model"]
    storage = dependencies["storage"]
    queue = dependencies["queue"]
    lane = _compute_lane_validity(
        bridge=bridge,
        model=model,
        storage=storage,
        queue=queue,
        active_job=active_job,
    )
    return JSONResponse({
        "status": lane["status"],
        "checked_at": time.time(),
        "api": {
            "status": "ok",
            "version": app.version,
        },
        "bridge": bridge,
        "model": model,
        "storage": storage,
        "queue": queue,
        "lane_validity": lane,
        "local_lane_admission": _api_local_lane_admission_payload(),
        "active_run": active_job,
        "recent_jobs": jobs[:5],
    })


@app.post("/api/check-cache")
async def check_cache(body: dict[str, Any]):
    """Pre-flight cache check: given a binary's SHA-256, report if a cached
    discovery result exists in blob storage.
    Body: {sha256: "<64 hex chars>"}.
    """
    sha = (body.get("sha256") or "").strip().lower()
    if not sha or len(sha) != 64:
        raise HTTPException(400, "sha256 is required (64 hex chars)")
    blob_name = f"discovery-cache/{sha}/discovery_result.json"
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, blob_name)
        data = json.loads(raw)
        invocables = data.get("invocables", [])
        return JSONResponse({
            "cached": True,
            "sha256": sha,
            "invocable_count": len(invocables),
            "cached_at": data.get("cached_at"),
            "invocable_names": [inv.get("name", "") for inv in invocables[:30]],
        })
    except Exception:
        return JSONResponse({"cached": False, "sha256": sha})


@app.post("/api/analyze-path")
async def analyze_path(body: dict[str, Any]):
    """Section 2.b: Analyze a file path already on the server's filesystem.
    Body: {path, hints?}. Returns {job_id, status_url}; poll GET /api/jobs/{id}.
    """
    path_str  = (body.get("path") or "").strip()
    hints     = (body.get("hints") or "").strip()
    use_cases = (body.get("use_cases") or "").strip()
    skip_cache = _as_bool(body.get("skip_cache"), False)
    ghidra_required = _as_bool(body.get("ghidra_required"), False)
    analysis_profile = str(body.get("analysis_profile") or "strict_dll").strip().lower()
    if analysis_profile not in {"strict_dll", "greybox_dll", "full_surface"}:
        analysis_profile = "strict_dll"
    lane_id = str(body.get("lane_id") or "").strip()
    ablation_tags = _normalize_ablation_tags(body)

    if not path_str:
        raise HTTPException(400, "path is required")

    # Resolve symlinks/".." before prefix check to block path-traversal.
    target = Path(path_str).resolve()
    if not any(str(target).startswith(str(p.resolve())) for p in _SAFE_PATH_PREFIXES):
        raise HTTPException(
            403,
            f"Path {path_str!r} is outside the allowed directories. "
            "Upload the file instead.",
        )
    if not target.exists():
        raise HTTPException(
            400,
            f"Path not found on the server: {path_str!r}. "
            "In the cloud deployment the container does not have access to your "
            "local Windows filesystem — upload the file instead.",
        )

    job_id = str(uuid.uuid4())[:8]
    logger.info(f"[{job_id}] Async analyze installed path: {target}")

    _persist_job_status(job_id, {
        "status": "queued",
        "progress": 0,
        "message": f"Queued analysis for {target.name}",
        "hints": hints,
        "use_cases": use_cases,
        "component_name": target.stem,
        "target_path": str(target),
        "analysis_entrypoint": "analyze_path",
        "binary_origin": (
            "repo_fixture"
            if "tests" in str(target).lower().replace("\\", "/")
            or "fixtures" in str(target).lower().replace("\\", "/")
            else "filesystem_path"
        ),
        "analysis_profile": analysis_profile,
        "skip_cache_requested": skip_cache,
        "lane_id": lane_id,
        "ghidra_required": ghidra_required,
        **ablation_tags,
        "result": None,
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    })

    def _guarded_analyze():
        """Run under _analyze_path_lock so concurrent path-analyses are serialized."""
        with _analyze_path_lock:
            _analyze_worker(job_id, target, hints, target.name, None, skip_cache)

    t = threading.Thread(
        target=_guarded_analyze,
        daemon=True,
        name=f"worker-{job_id}",
    )
    t.start()

    return JSONResponse({
        "job_id": job_id,
        "status": "queued",
        "status_url": f"/api/jobs/{job_id}",
    }, status_code=202)


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    hints: str = Form(default=""),
    use_cases: str = Form(default=""),
    skip_cache: str = Form(default=""),
    prompt_profile_id: str | None = Form(default=None),
    layer: int | None = Form(default=None),
    ablation_variable: str | None = Form(default=None),
    ablation_value: str | None = Form(default=None),
    run_set_id: str | None = Form(default=None),
    coordinator_cycle: int | None = Form(default=None),
    playbook_step: str | None = Form(default=None),
    analysis_profile: str | None = Form(default=None),
    lane_id: str | None = Form(default=None),
    selected_bridge_url: str | None = Form(default=None),
    bridge_url_override: str | None = Form(default=None),
    ghidra_required: str | None = Form(default=None),
):
    """Section 2-3: Upload a binary, start async discovery.
    Returns {job_id, status_url}; poll GET /api/jobs/{id}.
    """
    job_id = str(uuid.uuid4())[:8]
    suffix = Path(file.filename).suffix or ".bin"
    blob_name = f"{job_id}/input{suffix}"

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Empty file uploaded")

    logger.info("[%s] STEP 1 \u2713  Received %s (%d bytes)", job_id, file.filename, len(content))

    original_name = Path(file.filename).name or f"upload{suffix}"
    _skip = skip_cache.lower() in ("1", "true", "yes")
    _ghidra_required = _as_bool(ghidra_required, False)
    requested_bridge_url = str(bridge_url_override or selected_bridge_url or "").strip()
    try:
        effective_selected_bridge_url = validate_gui_bridge_url_override(requested_bridge_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "reason_code": "bridge_override_not_allowed",
                "message": "selected bridge URL is not in the configured local bridge candidate allowlist",
            },
        ) from exc
    ablation_tags = _normalize_ablation_tags(
        {
            "prompt_profile_id": prompt_profile_id,
            "layer": layer,
            "ablation_variable": ablation_variable,
            "ablation_value": ablation_value,
            "run_set_id": run_set_id,
            "coordinator_cycle": coordinator_cycle,
            "playbook_step": playbook_step,
            "analysis_profile": analysis_profile,
            "lane_id": lane_id,
        }
    )
    _record_upload_event(
        job_id,
        "analyze_route_received",
        original_name=original_name,
        component_name=Path(file.filename).stem,
        content_bytes=len(content),
        hints=hints,
        use_cases=use_cases,
        skip_cache_requested=_skip,
        analysis_profile=str(analysis_profile or "strict_dll"),
        lane_id=str(lane_id or ""),
        selected_bridge_url=effective_selected_bridge_url,
        ghidra_required=_ghidra_required,
        playbook_step=str(playbook_step or ""),
        run_set_id=str(run_set_id or ""),
        binary_origin="temp_upload",
        analysis_entrypoint="upload",
        storage_backend=STORAGE_BACKEND,
    )

    blob_upload = _upload_to_blob_bounded(UPLOAD_CONTAINER, blob_name, content)
    blob_uploaded = bool(blob_upload.get("ok")) and bool(blob_upload.get("returned"))
    if blob_uploaded:
        logger.info("[%s] STEP 2 \u2713  Binary uploaded to Blob (uploads/%s)", job_id, blob_name)
    elif blob_upload.get("timed_out"):
        logger.error("[%s] STEP 2 \u2717  Binary upload to Blob timed out: %s", job_id, blob_upload)
        _record_upload_event(
            job_id,
            "blob_upload_timeout",
            blob_name=blob_name,
            elapsed_ms=blob_upload.get("elapsed_ms"),
            timeout_sec=_blob_upload_timeout_sec(),
        )
    else:
        logger.error(
            "[%s] STEP 2 \u2717  Binary upload to Blob failed: %s",
            job_id,
            blob_upload.get("exception_message") or blob_upload,
        )

    ok = _persist_job_status(job_id, {
        "status": "queued",
        "progress": 0,
        "message": f"Queued analysis for {original_name}",
        "hints": hints,
        "use_cases": use_cases,
        "component_name": Path(file.filename).stem,
        "file_path": original_name,
        "analysis_entrypoint": "upload",
        "binary_origin": "temp_upload",
        "analysis_profile": (analysis_profile or "strict_dll"),
        "lane_id": (lane_id or ""),
        "selected_bridge_url": effective_selected_bridge_url,
        "ghidra_required": _ghidra_required,
        **ablation_tags,
        "result": None,
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    })
    if ok:
        logger.info("[%s] STEP 3 \u2713  Initial status written to Blob", job_id)
    else:
        logger.error("[%s] STEP 3 \u2717  Initial status failed to write to Blob", job_id)
        raise HTTPException(status_code=500, detail="Failed to persist initial job status")

    # Enqueue for durable processing; fall back to a direct thread if unavailable.
    enqueued = blob_uploaded and _enqueue_analysis(job_id, blob_name, hints, original_name,
                                                        skip_cache=_skip)
    if enqueued:
        logger.info("[%s] STEP 4 \u2713  Job enqueued to Storage Queue", job_id)
        _record_upload_event(
            job_id,
            "analyze_route_dispatch",
            dispatch_mode="queue",
            blob_uploaded=blob_uploaded,
            enqueued=True,
            blob_name=blob_name,
            temp_upload_path="",
        )
    else:
        logger.warning(
            "[%s] STEP 4 \u2717  Queue unavailable (blob_uploaded=%s) \u2014 falling back to direct thread. "
            "Job status may be lost on pod restart or cross-pod poll.",
            job_id, blob_uploaded,
        )
        tmp_dir  = Path(tempfile.mkdtemp(prefix=f"upload_{job_id}_"))
        tmp_path = tmp_dir / original_name
        tmp_path.write_bytes(content)
        _record_upload_event(
            job_id,
            "analyze_route_dispatch",
            dispatch_mode="direct-thread",
            blob_uploaded=blob_uploaded,
            enqueued=False,
            blob_name=blob_name,
            temp_upload_path=str(tmp_path),
        )
        threading.Thread(
            target=_analyze_worker,
            args=(job_id, tmp_path, hints, original_name, tmp_dir, _skip),
            daemon=True,
            name=f"worker-{job_id}",
        ).start()

    return JSONResponse({
        "job_id": job_id,
        "status": "queued",
        "status_url": f"/api/jobs/{job_id}",
    }, status_code=202)


@app.get("/api/jobs/recent")
async def recent_jobs():
    """Return the most recent 20 jobs with summary metadata.

    Scans in-memory job status cache, falling back to blob listing.
    Each entry includes job_id, component_name, status, explore_phase,
    coverage_pct, and created_at for UI job pickers.
    """
    return JSONResponse({"jobs": _recent_job_entries(limit=20)})


@app.get("/api/fixtures")
async def list_fixtures():
    """List DLL/EXE files available for pipeline analysis.

    Scans tests/fixtures/ recursively for .dll/.exe targets and includes a
    curated set of common Windows system binaries so new users have ready-made
    demo targets without needing to supply their own files.
    Returns: {fixtures: [{name, path, category, type}]}
    """
    _root = Path(__file__).resolve().parents[2]   # repo root
    fixtures_dir = _root / "tests" / "fixtures"
    fixtures: list[dict] = []
    seen: set[str] = set()

    def _add(name: str, path: str, category: str, ftype: str) -> None:
        key = path.lower()
        if key in seen:
            return
        seen.add(key)
        fixtures.append({"name": name, "path": path, "category": category, "type": ftype})

    # Scan repo fixture directories
    if fixtures_dir.exists():
        for p in sorted(fixtures_dir.rglob("*.dll")):
            _add(p.name, str(p), p.parent.name, "dll")
        for p in sorted(fixtures_dir.rglob("*.exe")):
            _add(p.name, str(p), p.parent.name, "exe")

    # Well-known Windows system DLLs that are always present on any Windows box
    system_targets = [
        ("user32.dll",   r"C:\Windows\System32\user32.dll",   "system", "dll"),
        ("kernel32.dll", r"C:\Windows\System32\kernel32.dll", "system", "dll"),
        ("ntdll.dll",    r"C:\Windows\System32\ntdll.dll",    "system", "dll"),
        ("advapi32.dll", r"C:\Windows\System32\advapi32.dll", "system", "dll"),
        ("ws2_32.dll",   r"C:\Windows\System32\ws2_32.dll",   "system", "dll"),
        ("notepad.exe",  r"C:\Windows\System32\notepad.exe",  "system", "exe"),
    ]
    for name, path, cat, ftype in system_targets:
        if Path(path).exists():
            _add(name, path, cat, ftype)

    return JSONResponse({"fixtures": fixtures})


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    """SSE stream that pushes job status updates every second until the job
    reaches a terminal state (done / error / canceled).

    Each event is a JSON object with all fields from GET /api/jobs/{job_id}.
    A synthetic {"__done": true} event is emitted as the final frame.
    """
    initial = _get_job_status(job_id)
    if initial is None:
        raise HTTPException(404, f"Job '{job_id}' not found")

    async def _generate():
        last_fingerprint: str | None = None
        # Max 30 minutes of streaming (1800 ticks × 1 s)
        for _ in range(1800):
            state = _get_job_status(job_id)
            if state is None:
                break
            fp = f"{state.get('status')}:{state.get('progress')}:{state.get('message')}:{state.get('explore_phase')}"
            if fp != last_fingerprint:
                last_fingerprint = fp
                payload = json.dumps({"job_id": job_id, **state})
                yield f"data: {payload}\n\n"
            if is_terminal_job_record(state):
                break
            await asyncio.sleep(1.0)
        yield 'data: {"__done": true}\n\n'

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/jobs/{job_id}/invocables")
def get_job_invocables(job_id: str):
    """Return invocables for an analyzed job (status.result or invocables_map blob)."""
    st_main = _get_job_status(job_id)
    if st_main is None:
        raise HTTPException(404, f"Job '{job_id}' not found")
    inv: list | None = None
    res = st_main.get("result")
    if isinstance(res, dict):
        raw_inv = res.get("invocables")
        if isinstance(raw_inv, list) and raw_inv:
            inv = raw_inv
    if inv:
        return JSONResponse({"job_id": job_id, "invocables": inv, "source": "status"})
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/invocables_map.json")
        inv_map = json.loads(raw)
        if isinstance(inv_map, dict):
            inv_list = list(inv_map.values())
        elif isinstance(inv_map, list):
            inv_list = inv_map
        else:
            inv_list = []
        if not inv_list:
            raise HTTPException(404, f"No invocables for job '{job_id}'")
        return JSONResponse({"job_id": job_id, "invocables": inv_list, "source": "invocables_map"})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(404, f"No invocables for job '{job_id}'")


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """P3: Poll async job status. status ∈ {queued, running, done, error}."""
    state = _get_job_status(job_id)
    if state is None:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return JSONResponse({"job_id": job_id, **state})


@app.get("/api/jobs/{job_id}/terminalization")
async def get_job_terminalization(
    job_id: str,
    observed_stable_for_seconds: int | None = Query(default=None),
    observed_timeout: bool = Query(default=False),
):
    state = _get_job_status(job_id)
    if state is None:
        raise HTTPException(404, f"Job '{job_id}' not found")
    verdict: dict[str, Any] = {}
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/macro_verdict.json")
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            verdict = loaded
    except Exception:
        verdict = {}
    payload = build_job_terminalization_payload(
        job_id,
        state,
        now=time.time(),
        observed_stable_for_seconds=observed_stable_for_seconds,
        observed_timeout=observed_timeout,
        verdict_payload=verdict,
    )
    payload["contract_version"] = TRUST_CONTRACT_VERSION
    return JSONResponse(payload)


@app.get("/api/jobs/{job_id}/mc-decisions")
async def get_mc_decisions(job_id: str):
    """Return all micro coordinator decisions for a job."""
    from api.pipeline.core.macro_coordinator import _load_mc_decision_history
    history = _load_mc_decision_history(job_id)
    return JSONResponse({"job_id": job_id, "decisions": history})


@app.get("/api/jobs/{job_id}/verdict")
async def get_verdict(job_id: str):
    """Return the macro coordinator verdict for a completed job."""
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/macro_verdict.json")
        verdict = json.loads(raw)
        return JSONResponse({"job_id": job_id, "verdict": verdict})
    except Exception:
        return JSONResponse({"job_id": job_id, "verdict": None})


@app.get("/api/jobs/{job_id}/validation-status")
async def get_validation_status(job_id: str):
    validation_report, source_artifacts, derived_from, validation_issues = _load_job_artifact_json(job_id, "validation-report.json")
    markdown_text, text_sources, text_derived, text_issues = _load_job_artifact_text(job_id, "human/validation-report.md")
    source_artifacts.extend(text_sources)
    derived_from.extend(text_derived)
    artifact_read_issues = _dedupe_artifact_read_issues([*validation_issues, *text_issues])
    validation = _classify_validation(validation_report if isinstance(validation_report, dict) else None, markdown_text)
    analysis_notes = [*validation["notes"], *_artifact_issue_notes(artifact_read_issues)]
    operator_view = {
        "headline": "Validation status",
        "summary": _overlay_artifact_issue_summary(validation["operator_summary"], artifact_read_issues),
        "status": validation["status"],
        "next_action": (
            "Repair wrapper validation or publish a valid validation report before claiming trustworthy coverage."
            if validation["status"] in {"invalid", "partial", "warn", "unknown"}
            else "Validation layer is usable as trust evidence."
        ),
    }
    analysis_view = {
        "checked": validation["checked"],
        "verified_1to1": validation["verified_1to1"],
        "mismatch": validation["mismatch"],
        "wrapper_unavailable": validation["wrapper_unavailable"],
        "direct_error": validation["direct_error"],
        "wrapper_error": validation["wrapper_error"],
        "skipped": validation["skipped"],
        "wrapper_source": validation["wrapper_source"],
        "wrapper_load_error": validation["wrapper_load_error"],
        "notes": analysis_notes,
        "artifact_read_issues": artifact_read_issues,
    }
    native_status = _native_route_artifact_status(bool(validation_report or markdown_text), artifact_read_issues)
    return JSONResponse(
        _native_envelope(
            job_id,
            operator_view,
            analysis_view,
            source_artifacts,
            derived_from,
            native_status,
            notes=analysis_notes,
            artifact_read_issues=artifact_read_issues,
            validation_status=validation["status"],
            status=validation["status"],
            checked=validation["checked"],
            verified_1to1=validation["verified_1to1"],
            mismatch=validation["mismatch"],
            wrapper_unavailable=validation["wrapper_unavailable"],
            direct_error=validation["direct_error"],
            wrapper_error=validation["wrapper_error"],
            skipped=validation["skipped"],
            wrapper_source=validation["wrapper_source"],
            wrapper_load_error=validation["wrapper_load_error"],
        )
    )


@app.get("/api/jobs/{job_id}/verdict-hierarchy")
async def get_verdict_hierarchy(job_id: str):
    job = _get_job_status(job_id) or {"job_id": job_id}
    macro_verdict, source_artifacts, derived_from, macro_issues = _load_job_artifact_json(job_id, "macro_verdict.json")
    run_validity, validity_sources, validity_derived, validity_issues = _load_job_artifact_json(job_id, "run-validity.json")
    kpi_run, kpi_sources, kpi_derived, kpi_issues = _load_job_artifact_json(job_id, "kpi_run.json")
    cohesion_report, cohesion_sources, cohesion_derived, cohesion_issues = _load_job_artifact_json(job_id, "cohesion-report.json")
    validation_payload = await get_validation_status(job_id)
    validation_status = validation_payload.body.decode("utf-8")
    validation_data = json.loads(validation_status)
    source_artifacts.extend(validity_sources + kpi_sources + cohesion_sources)
    derived_from.extend(validity_derived + kpi_derived + cohesion_derived)
    artifact_read_issues = _dedupe_artifact_read_issues(
        [
            *macro_issues,
            *validity_issues,
            *kpi_issues,
            *cohesion_issues,
            *(validation_data.get("artifact_read_issues") or []),
        ]
    )
    run_valid = bool((run_validity or {}).get("valid")) if isinstance(run_validity, dict) else False
    totals = (kpi_run or {}).get("totals") if isinstance(kpi_run, dict) else {}
    totals = totals if isinstance(totals, dict) else {}
    unknown_count = _safe_int(totals.get("unknown"))
    failure_count = _safe_int(totals.get("failure"))
    verified_success = _safe_int(totals.get("verified_success"))
    gates = (cohesion_report or {}).get("gates") if isinstance(cohesion_report, dict) else {}
    hard_fail = bool((gates or {}).get("hard_fail")) if isinstance(gates, dict) else False

    ingest_status = "pass" if any([macro_verdict, run_validity, kpi_run, cohesion_report]) else "unknown"
    semantic_status = "fail" if failure_count else ("warn" if unknown_count else ("pass" if verified_success else "unknown"))
    validity_status = "pass" if run_valid else ("fail" if run_validity else "unknown")
    validation_layer_status = str(validation_data.get("status") or "unknown")
    cohesion_status = "fail" if hard_fail else ("pass" if cohesion_report else "unknown")
    root_failure = _detect_pre_artifact_failure(
        job_id,
        job,
        _load_findings(job_id),
        run_validity=run_validity,
        kpi_run=kpi_run,
        cohesion_report=cohesion_report,
    )
    if root_failure:
        validity_status = "fail"

    layers = {
        "ingest_success": _verdict_layer_entry(ingest_status, "Core run artifacts were emitted." if ingest_status == "pass" else "No core run artifacts were found.", ["macro_verdict.json", "run-validity.json", "kpi_run.json"]),
        "semantic_success": _verdict_layer_entry(semantic_status, f"verified={verified_success}, failure={failure_count}, unknown={unknown_count}", ["kpi_run.json"]),
        "run_validity": _verdict_layer_entry(
            validity_status,
            root_failure["summary"] if root_failure else f"run-validity valid={run_valid}",
            ["run-validity.json"] if run_validity else ["status.json"],
        ),
        "validation_completeness": _verdict_layer_entry(validation_layer_status, validation_data.get("operator_summary") or "Validation status unavailable.", ["validation-report.json"]),
        "cohesion_gate": _verdict_layer_entry(cohesion_status, "Cohesion hard fail present." if hard_fail else "No cohesion hard fail.", ["cohesion-report.json"]),
    }
    conflicts: list[str] = []
    if semantic_status in {"pass", "warn"} and validity_status == "fail":
        conflicts.append("semantic layer reports progress while run validity is red")
    if semantic_status in {"pass", "warn"} and validation_layer_status in {"invalid", "partial", "warn"}:
        conflicts.append("semantic layer reports progress while validation completeness is not trustworthy")
    if ingest_status == "pass" and (
        validity_status == "fail"
        or validation_layer_status in {"invalid", "partial", "warn"}
        or cohesion_status == "fail"
    ):
        conflicts.append("ingest succeeded but one or more trust-bearing layers failed or degraded")
    macro_verdict_value = str((macro_verdict or {}).get("verdict") or "").lower()
    if cohesion_status == "fail" and macro_verdict_value:
        if macro_verdict_value not in {"fail", "failed", "invalid"}:
            conflicts.append("macro verdict is softer than the cohesion gate failure")
    if root_failure:
        operator_summary = root_failure["root_summary"]
    else:
        operator_summary = "Ingest reached artifact emission, but downstream trust layers disagree." if conflicts else "Verdict layers are aligned enough for operator use."
    analysis_notes = _artifact_issue_notes(artifact_read_issues)
    operator_view = {
        "headline": "Verdict hierarchy",
        "summary": _overlay_artifact_issue_summary(operator_summary, artifact_read_issues) if not root_failure else operator_summary,
        "status": "fail" if root_failure else ("warn" if conflicts else ("pass" if semantic_status == "pass" and validity_status == "pass" else semantic_status)),
        "next_action": (
            root_failure["recommended_next_action"]
            if root_failure
            else ("Inspect the first conflicting layer before broad reruns." if conflicts else "Use the verdict layers as the current trust summary.")
        ),
    }
    analysis_view = {
        "layers": layers,
        "macro_verdict": macro_verdict,
        "run_validity": run_validity,
        "kpi_run": kpi_run,
        "cohesion_report": cohesion_report,
        "root_failure": root_failure["analysis_view"] if root_failure else None,
        "conflicts": conflicts,
        "artifact_read_issues": artifact_read_issues,
        "verdict_precedence": [
            "ingest_success",
            "semantic_success",
            "run_validity",
            "validation_completeness",
            "cohesion_gate",
        ],
    }
    native_status = _native_route_artifact_status(bool(run_validity and kpi_run), artifact_read_issues)
    return JSONResponse(
        _native_envelope(
            job_id,
            operator_view,
            analysis_view,
            source_artifacts + (root_failure["source_artifacts"] if root_failure else []),
            derived_from + (root_failure["derived_from"] if root_failure else []),
            native_status,
            notes=analysis_notes,
            artifact_read_issues=artifact_read_issues,
            layers=layers,
            conflicts=conflicts,
            verdict_precedence=analysis_view["verdict_precedence"],
        )
    )


@app.get("/api/jobs/{job_id}/causal-summary")
async def get_causal_summary(job_id: str):
    job = _get_job_status(job_id) or {"job_id": job_id}
    stage_index, stage_sources, stage_derived, stage_issues = _load_job_artifact_json(job_id, "stage-index.json")
    transition_index, transition_sources, transition_derived, transition_issues = _load_job_artifact_json(job_id, "transition-index.json")
    cohesion_report, cohesion_sources, cohesion_derived, cohesion_issues = _load_job_artifact_json(job_id, "cohesion-report.json")
    findings = _load_findings(job_id)
    source_artifacts = stage_sources + transition_sources + cohesion_sources
    derived_from = stage_derived + transition_derived + cohesion_derived
    artifact_read_issues = _dedupe_artifact_read_issues([*stage_issues, *transition_issues, *cohesion_issues])
    root_failure = _detect_pre_artifact_failure(
        job_id,
        job,
        findings,
        stage_index=stage_index,
        transition_index=transition_index,
        cohesion_report=cohesion_report,
    )

    stages = (stage_index or {}).get("stages") if isinstance(stage_index, dict) else []
    stages = [item for item in stages if isinstance(item, dict)]
    failed_stage = next((stage for stage in stages if str(stage.get("status") or "").lower() == "failed"), None)
    first_failing_stage = str((failed_stage or {}).get("id") or "")
    stage_errors = (failed_stage or {}).get("errors") if isinstance(failed_stage, dict) else []
    stage_errors = [str(item) for item in stage_errors or []]

    transitions = (transition_index or {}).get("transitions") if isinstance(transition_index, dict) else []
    transitions = [item for item in transitions if isinstance(item, dict)]
    first_transition_ids = [
        str(item.get("id"))
        for item in transitions
        if str(item.get("status") or "").lower() == "fail"
        and (
            str(item.get("producer_stage") or "") == first_failing_stage
            or str(item.get("consumer_stage") or "") == first_failing_stage
            or not first_failing_stage
        )
    ]
    if not first_transition_ids:
        first_transition_ids = [str(item.get("id")) for item in transitions if str(item.get("status") or "").lower() == "fail"][:3]
    affected_stages = list(((cohesion_report or {}).get("failed_stages") or [])) if isinstance(cohesion_report, dict) else []
    if not affected_stages:
        affected_stages = [str(stage.get("id")) for stage in stages if str(stage.get("status") or "").lower() in {"failed", "skipped"}]
    affected_transitions = list(((cohesion_report or {}).get("failed_transitions") or [])) if isinstance(cohesion_report, dict) else []
    if not affected_transitions:
        affected_transitions = [str(item.get("id")) for item in transitions if str(item.get("status") or "").lower() in {"fail", "warn", "partial"}]
    cause_summary = stage_errors[0] if stage_errors else ""
    if not cause_summary:
        first_transition = next((item for item in transitions if str(item.get("id")) in first_transition_ids), None)
        cause_summary = str((first_transition or {}).get("reason") or "")
    if not cause_summary and findings:
        cause_summary = str((findings[0] or {}).get("finding") or (findings[0] or {}).get("summary") or "")
    if not cause_summary and root_failure:
        cause_summary = root_failure["summary"]
    if not cause_summary:
        cause_summary = "No canonical causal explanation emitted yet."
    blast_radius_summary = (
        root_failure["blast_radius_summary"]
        if root_failure
        else (
            f"{len(affected_stages)} stage(s) and {len(affected_transitions)} transition(s) are affected."
            if affected_stages or affected_transitions
            else "No affected stages or transitions were identified."
        )
    )
    if root_failure and not first_failing_stage:
        first_failing_stage = root_failure["stage"]
    operator_summary = (
        f"{first_failing_stage} failed first. {cause_summary}"
        if first_failing_stage
        else f"Unknown stage failed first. {cause_summary}"
    )
    analysis_notes = _artifact_issue_notes(artifact_read_issues)
    operator_view = {
        "headline": "Causal summary",
        "summary": _overlay_artifact_issue_summary(operator_summary, artifact_read_issues) if not root_failure else operator_summary,
        "status": "fail" if first_failing_stage or root_failure else "warn",
        "next_action": (
            root_failure["recommended_next_action"]
            if root_failure
            else (
                f"Repair {first_failing_stage} and the first failing transitions before broader exploration."
                if first_failing_stage
                else "Inspect stage-index and transition-index before broader reruns."
            )
        ),
    }
    analysis_view = {
        "first_failing_stage": first_failing_stage,
        "first_failing_transition_ids": first_transition_ids,
        "cause_summary": cause_summary,
        "blast_radius_summary": blast_radius_summary,
        "affected_stages": affected_stages,
        "affected_transitions": affected_transitions,
        "stage_errors": stage_errors,
        "root_failure": root_failure["analysis_view"] if root_failure else None,
        "artifact_read_issues": artifact_read_issues,
    }
    native_status = _native_route_artifact_status(bool(stage_index and transition_index), artifact_read_issues)
    return JSONResponse(
        _native_envelope(
            job_id,
            operator_view,
            analysis_view,
            source_artifacts + (root_failure["source_artifacts"] if root_failure else []),
            derived_from + (root_failure["derived_from"] if root_failure else []),
            native_status,
            notes=analysis_notes,
            artifact_read_issues=artifact_read_issues,
            first_failing_stage=first_failing_stage,
            first_failing_transition_ids=first_transition_ids,
            cause_summary=cause_summary,
            blast_radius_summary=blast_radius_summary,
            affected_stages=affected_stages,
            affected_transitions=affected_transitions,
            recommended_next_action=operator_view["next_action"],
        )
    )


@app.get("/api/jobs/{job_id}/artifacts")
async def get_artifacts(job_id: str):
    job = _get_job_status(job_id) or {"job_id": job_id}
    artifact_index, artifact_sources, artifact_derived, artifact_issues = _load_job_artifact_json(job_id, "artifact-index.json")
    l3_index, l3_sources, l3_derived, l3_issues = _load_job_artifact_json(job_id, "human/l3-forensics-index.json")
    session_manifest, manifest_sources, manifest_derived, manifest_issues = _load_job_artifact_json(job_id, "session-manifest.json")
    source_artifacts = artifact_sources + l3_sources + manifest_sources
    derived_from = artifact_derived + l3_derived + manifest_derived
    artifact_read_issues = _dedupe_artifact_read_issues([*artifact_issues, *l3_issues, *manifest_issues])
    findings = _load_findings(job_id)
    root_failure = _detect_pre_artifact_failure(job_id, job, findings)

    operator_bundle = [
        {
            **_route_artifact(job_id, "Current job status", f"/api/jobs/{job_id}", "tier1", _job_error_excerpt(job) if root_failure else "Current job status and terminal message."),
            "evidence_type": "proving evidence" if root_failure else "supporting evidence",
            "why_it_matters": "Shows whether analysis ended before trustworthy artifacts were emitted.",
        },
        {
            **_route_artifact(job_id, "Verdict hierarchy", f"/api/jobs/{job_id}/verdict-hierarchy", "tier1", "Operator trust layers."),
            "evidence_type": "proving evidence",
            "why_it_matters": "Summarizes the strongest currently trustworthy success and failure layers.",
        },
        {
            **_route_artifact(job_id, "Causal summary", f"/api/jobs/{job_id}/causal-summary", "tier1", "First failure and blocked downstream chain."),
            "evidence_type": "proving evidence",
            "why_it_matters": "Shows where the iteration failed first and what was blocked downstream.",
        },
        {
            **_route_artifact(job_id, "Diagnostics", f"/api/jobs/{job_id}/diagnostics", "tier1", "Ranked diagnosis feed."),
            "evidence_type": "proving evidence",
            "why_it_matters": "Provides the canonical blocker and next action.",
        },
        {
            **_route_artifact(job_id, "Validation status", f"/api/jobs/{job_id}/validation-status", "tier2", "Wrapper and behavior validation trust."),
            "evidence_type": "missing evidence" if root_failure else "supporting evidence",
            "why_it_matters": "Validation gaps matter, but they should not outrank an earlier analysis-entry failure.",
        },
        {
            **_route_artifact(job_id, "Findings", f"/api/findings/{job_id}", "tier3", "Recorded findings."),
            "evidence_type": "empty evidence" if not findings else "supporting evidence",
            "why_it_matters": "An empty findings set can be evidence that analysis failed before usable outputs were emitted.",
        },
        {
            **_route_artifact(job_id, "Report", f"/api/jobs/{job_id}/report", "tier3", "Human-readable report."),
            "evidence_type": "empty evidence" if root_failure else "supporting evidence",
            "why_it_matters": "A report with zero documented functions supports the artifact-emission failure story.",
        },
        {
            **_route_artifact(job_id, "Session snapshot", f"/api/jobs/{job_id}/session-snapshot", "tier3", "Full forensics bundle."),
            "evidence_type": "supporting evidence",
            "why_it_matters": "Use only for deep inspection after Tier 1 and Tier 2 remain insufficient.",
        },
    ]
    canonical_map = (artifact_index or {}).get("canonical_map") if isinstance(artifact_index, dict) else []
    key_artifacts = (l3_index or {}).get("key_artifacts") if isinstance(l3_index, dict) else []
    key_artifacts = [str(item) for item in key_artifacts or []]
    primary_artifacts = operator_bundle[:3]
    supporting_artifacts = [
        {"path": "stage-index.json", "tier": "tier2"},
        {"path": "transition-index.json", "tier": "tier2"},
        {"path": "cohesion-report.json", "tier": "tier2"},
        {"path": "validation-report.json", "tier": "tier2"},
    ]
    forensics_artifacts = [
        {"path": item, "tier": "tier3"} for item in key_artifacts
    ]
    analysis_bundle = {
        "canonical_map": canonical_map,
        "key_artifacts": key_artifacts,
        "artifact_count": _safe_int((artifact_index or {}).get("file_count")) if isinstance(artifact_index, dict) else 0,
        "manifest_present": bool(session_manifest),
        "artifact_read_issues": artifact_read_issues,
    }
    analysis_notes = _artifact_issue_notes(artifact_read_issues)
    operator_view = {
        "headline": "Artifact bundle",
        "summary": _overlay_artifact_issue_summary(
            (
                "Tier 1 artifacts show the root failure first; Tier 2 and Tier 3 support deeper analysis."
                if root_failure
                else "Tier 1 artifacts are the operator-first proof bundle. Tier 2 and Tier 3 support deeper analysis."
            ),
            artifact_read_issues,
        ),
        "status": "pass" if artifact_index else "partial",
        "next_action": (
            "Start with job status, verdict hierarchy, causal summary, and diagnostics before reading lower-tier evidence."
            if root_failure
            else "Start with Tier 1 artifacts, then move to Tier 2 or Tier 3 only if the diagnosis remains unclear."
        ),
    }
    return JSONResponse(
        _native_envelope(
            job_id,
            operator_view,
            analysis_bundle,
            source_artifacts + (root_failure["source_artifacts"] if root_failure else []),
            derived_from + (root_failure["derived_from"] if root_failure else []),
            _native_route_artifact_status(bool(artifact_index), artifact_read_issues),
            notes=analysis_notes,
            artifact_read_issues=artifact_read_issues,
            primary_artifacts=primary_artifacts,
            supporting_artifacts=supporting_artifacts,
            forensics_artifacts=forensics_artifacts,
            canonical_map=canonical_map,
            artifact_count=analysis_bundle["artifact_count"],
            operator_bundle=operator_bundle,
            analysis_bundle=analysis_bundle,
        )
    )


@app.get("/api/jobs/{job_id}/diagnostics")
async def get_diagnostics(job_id: str):
    verdict_payload = json.loads((await get_verdict_hierarchy(job_id)).body.decode("utf-8"))
    validation_payload = json.loads((await get_validation_status(job_id)).body.decode("utf-8"))
    causal_payload = json.loads((await get_causal_summary(job_id)).body.decode("utf-8"))
    artifacts_payload = json.loads((await get_artifacts(job_id)).body.decode("utf-8"))
    artifact_read_issues = _dedupe_artifact_read_issues(
        [
            *(verdict_payload.get("artifact_read_issues") or []),
            *(validation_payload.get("artifact_read_issues") or []),
            *(causal_payload.get("artifact_read_issues") or []),
            *(artifacts_payload.get("artifact_read_issues") or []),
        ]
    )
    findings = _load_findings(job_id)
    job = _get_job_status(job_id) or {"job_id": job_id}
    diagnoses: list[dict[str, Any]] = []
    root_failure = _detect_pre_artifact_failure(
        job_id,
        job,
        findings,
        stage_index={},
        transition_index={},
        run_validity=verdict_payload.get("analysis_view", {}).get("run_validity"),
        kpi_run=verdict_payload.get("analysis_view", {}).get("kpi_run"),
        cohesion_report=verdict_payload.get("analysis_view", {}).get("cohesion_report"),
    )
    if root_failure:
        diagnoses.append(
            {
                "diagnosis_id": f"{job_id}-analysis-entry",
                "title": root_failure["title"],
                "class": "analysis entry failure",
                "severity": "critical",
                "trust_impact": "high",
                "first_failing_stage": root_failure["stage"],
                "first_failing_iteration": str(job.get("iteration") or f"job:{job_id}"),
                "affected_targets": [str(job.get("component_name") or job_id)],
                "primary_evidence": {
                    "label": "Current job status",
                    "url": f"/api/jobs/{job_id}",
                    "summary": root_failure["summary"],
                    "tier": "tier1",
                },
                "blast_radius": {
                    "summary": root_failure["blast_radius_summary"],
                    "affected_stages": [],
                    "affected_transitions": [],
                },
                "recommended_next_action": root_failure["recommended_next_action"],
                "confidence": 0.98,
                "owner_layer": "capture",
                "family_id": root_failure["family_id"],
                "operator_view": {
                    "headline": "Analysis entry failure",
                    "summary": root_failure["summary"],
                    "status": "fail",
                    "next_action": root_failure["recommended_next_action"],
                },
                "analysis_view": root_failure["analysis_view"],
                "source_artifacts": root_failure["source_artifacts"],
                "derived_from": root_failure["derived_from"],
                "native_status": "native",
            }
        )
    if artifact_read_issues and not root_failure:
        diagnoses.append(
            {
                "diagnosis_id": f"{job_id}-artifact-read-degraded",
                "title": "Native artifact retrieval is degraded",
                "class": "capture degradation",
                "severity": "high",
                "trust_impact": "high",
                "first_failing_stage": str(causal_payload.get("first_failing_stage") or "capture"),
                "first_failing_iteration": str(job.get("iteration") or f"job:{job_id}"),
                "affected_targets": [str(job.get("component_name") or job_id)],
                "primary_evidence": {
                    "label": "Diagnostics route",
                    "url": f"/api/jobs/{job_id}/diagnostics",
                    "summary": _overlay_artifact_issue_summary("", artifact_read_issues),
                    "tier": "tier1",
                },
                "blast_radius": {
                    "summary": "Operator-facing native routes are reading incomplete or unreadable artifacts.",
                    "affected_stages": causal_payload.get("affected_stages") or [],
                    "affected_transitions": causal_payload.get("affected_transitions") or [],
                },
                "recommended_next_action": "Repair artifact retrieval or parsing before trusting route-level summaries for proving decisions.",
                "confidence": 0.94,
                "owner_layer": "capture",
                "family_id": "capture-gap",
                "operator_view": {
                    "headline": "Artifact retrieval degraded",
                    "summary": _overlay_artifact_issue_summary("", artifact_read_issues),
                    "status": "warn",
                    "next_action": "Repair artifact retrieval or parsing before trusting route-level summaries for proving decisions.",
                },
                "analysis_view": {"artifact_read_issues": artifact_read_issues},
                "source_artifacts": sorted(
                    [
                        *verdict_payload.get("source_artifacts", []),
                        *validation_payload.get("source_artifacts", []),
                        *causal_payload.get("source_artifacts", []),
                        *artifacts_payload.get("source_artifacts", []),
                    ],
                    key=lambda item: f"{item.get('kind')}:{item.get('path')}",
                ),
                "derived_from": [
                    *verdict_payload.get("derived_from", []),
                    *validation_payload.get("derived_from", []),
                    *causal_payload.get("derived_from", []),
                    *artifacts_payload.get("derived_from", []),
                ],
                "native_status": "degraded",
            }
        )
    for idx, finding in enumerate(findings):
        status = normalize_status(finding.get("status_canonical") or finding.get("status"))
        contradiction = str(finding.get("contradiction_state") or "").lower()
        if status == "verified_success" and contradiction in {"", "none"}:
            continue
        owner_layer = "measurement" if "validation" in str(finding.get("blocker_family") or "").lower() else "state"
        family_id = _family_bucket(
            str(finding.get("blocker_family") or finding.get("likely_regression_cause") or status),
            owner_layer,
        )
        severity = "critical" if contradiction in {"blocked", "confirmed"} else ("high" if status == "failure" else "medium")
        primary_evidence = {
            "label": f"Finding evidence for {finding.get('function') or 'unknown'}",
            "url": f"/api/findings/{job_id}",
            "summary": str(finding.get("finding") or finding.get("summary") or finding.get("detail") or "No finding summary emitted."),
            "tier": "tier1",
        }
        diagnoses.append(
            {
                "diagnosis_id": f"{job_id}-finding-{idx}",
                "title": str(finding.get("finding") or finding.get("summary") or finding.get("function") or f"Finding {idx + 1}"),
                "class": "contradiction" if contradiction in {"tentative", "blocked", "confirmed"} else ("blocker" if status == "failure" else "warning"),
                "severity": severity,
                "trust_impact": "high" if severity in {"critical", "high"} else "medium",
                "first_failing_stage": str(finding.get("first_blocking_stage") or causal_payload.get("first_failing_stage") or job.get("explore_phase") or "s02"),
                "first_failing_iteration": str(job.get("iteration") or f"job:{job_id}"),
                "affected_targets": [name for name in [finding.get("function"), *(finding.get("dependent_functions") or [])] if name],
                "primary_evidence": primary_evidence,
                "blast_radius": {
                    "summary": causal_payload.get("blast_radius_summary") or str(finding.get("blocker_family") or "No blast radius emitted."),
                    "affected_stages": causal_payload.get("affected_stages") or [],
                    "affected_transitions": causal_payload.get("affected_transitions") or [],
                },
                "recommended_next_action": causal_payload.get("recommended_next_action") or "Inspect the first failing stage before broad reruns.",
                "confidence": 0.85 if status == "failure" else 0.65,
                "owner_layer": owner_layer,
                "family_id": family_id,
                "operator_view": {
                    "summary": str(finding.get("finding") or finding.get("summary") or finding.get("detail") or ""),
                },
                "analysis_view": {
                    "finding": finding,
                    "verdict_status": verdict_payload.get("operator_view", {}).get("status"),
                    "causal_stage": causal_payload.get("first_failing_stage"),
                },
                "source_artifacts": [
                    {"kind": "native-route", "path": f"/api/findings/{job_id}"},
                    *causal_payload.get("source_artifacts", []),
                ],
                "derived_from": ["findings", *causal_payload.get("derived_from", [])],
                "native_status": "native",
            }
        )
    if validation_payload.get("status") in {"invalid", "partial", "warn", "unknown"} and not root_failure:
        diagnoses.append(
            {
                "diagnosis_id": f"{job_id}-validation",
                "title": "Validation completeness is broken or missing",
                "class": "readiness failure",
                "severity": "high",
                "trust_impact": "high",
                "first_failing_stage": "analysis-entry" if str(validation_payload.get("status") or "") == "unknown" else "s06",
                "first_failing_iteration": str(job.get("iteration") or f"job:{job_id}"),
                "affected_targets": [str(job.get("component_name") or job_id)],
                "primary_evidence": {
                    "label": "Validation status",
                    "url": f"/api/jobs/{job_id}/validation-status",
                    "summary": validation_payload.get("operator_summary") or "Validation route did not emit an operator summary.",
                    "tier": "tier1",
                },
                "blast_radius": {
                    "summary": "Validation weakness lowers trust in otherwise green surfaces.",
                    "affected_stages": ["s06", "s07"],
                    "affected_transitions": [],
                },
                "recommended_next_action": "Repair wrapper validation or treat current coverage as triage-only.",
                "confidence": 0.95,
                "owner_layer": "measurement",
                "family_id": "validation-failure",
                "operator_view": validation_payload.get("operator_view"),
                "analysis_view": validation_payload.get("analysis_view"),
                "source_artifacts": validation_payload.get("source_artifacts", []),
                "derived_from": validation_payload.get("derived_from", []),
                "native_status": validation_payload.get("native_status", "partial"),
            }
        )
    if not diagnoses:
        diagnoses.append(
            {
                "diagnosis_id": f"{job_id}-placeholder",
                "title": "No blocker-class diagnosis emitted",
                "class": "warning",
                "severity": "low",
                "trust_impact": "low",
                "first_failing_stage": str(causal_payload.get("first_failing_stage") or job.get("explore_phase") or "s07"),
                "first_failing_iteration": str(job.get("iteration") or f"job:{job_id}"),
                "affected_targets": [str(job.get("component_name") or job_id)],
                "primary_evidence": {
                    "label": "Diagnostics route",
                    "url": f"/api/jobs/{job_id}/diagnostics",
                    "summary": "The pipeline emitted no blocker-class diagnosis from current artifacts.",
                    "tier": "tier1",
                },
                "blast_radius": {
                    "summary": causal_payload.get("blast_radius_summary") or "No blast radius summary available.",
                    "affected_stages": causal_payload.get("affected_stages") or [],
                    "affected_transitions": causal_payload.get("affected_transitions") or [],
                },
                "recommended_next_action": "Inspect causal summary, verdict hierarchy, and findings before rerunning.",
                "confidence": 0.3,
                "owner_layer": "measurement",
                "family_id": "measurement-gap",
                "operator_view": {"summary": "No blocker-class diagnosis emitted"},
                "analysis_view": {"artifacts": artifacts_payload.get("analysis_bundle", {})},
                "source_artifacts": artifacts_payload.get("source_artifacts", []),
                "derived_from": artifacts_payload.get("derived_from", []),
                "native_status": "partial",
            }
        )
    diagnoses.sort(key=lambda item: (_severity_rank(item["severity"]), item["first_failing_stage"], item["title"]))
    operator_view = {
        "headline": "Diagnostics",
        "summary": diagnoses[0]["title"],
        "status": diagnoses[0]["severity"],
        "next_action": diagnoses[0]["recommended_next_action"],
    }
    analysis_view = {
        "count": len(diagnoses),
        "family_ids": sorted({item["family_id"] for item in diagnoses}),
        "top_diagnosis": diagnoses[0]["diagnosis_id"],
        "artifact_read_issues": artifact_read_issues,
    }
    source_artifacts = sorted(
        [*verdict_payload.get("source_artifacts", []), *validation_payload.get("source_artifacts", []), *causal_payload.get("source_artifacts", []), *artifacts_payload.get("source_artifacts", [])],
        key=lambda item: f"{item.get('kind')}:{item.get('path')}"
    )
    return JSONResponse(
        _native_envelope(
            job_id,
            operator_view,
            analysis_view,
            source_artifacts,
            [
                *verdict_payload.get("derived_from", []),
                *validation_payload.get("derived_from", []),
                *causal_payload.get("derived_from", []),
                *artifacts_payload.get("derived_from", []),
            ],
            "degraded" if artifact_read_issues else "native",
            notes=_artifact_issue_notes(artifact_read_issues),
            artifact_read_issues=artifact_read_issues,
            diagnoses=diagnoses,
        )
    )


@app.post("/api/generate")
async def generate(body: dict[str, Any]):
    """
    Section 4: Accept selected invocables, generate MCP server JSON definition.
    Returns the MCP tool schema ready for an LLM to consume.
    """
    return JSONResponse(run_generate(body))


@app.post("/api/execute")
def execute_tool(body: dict[str, Any]):
    """Execute a tool call. Body: {job_id?, tool_name, arguments, invocable?}."""
    tool_name  = body.get("tool_name", "")
    arguments  = body.get("arguments", {})
    job_id     = body.get("job_id", "")
    inline_inv = body.get("invocable")

    if not tool_name:
        raise HTTPException(400, "tool_name is required")

    if inline_inv:
        inv = inline_inv
    elif job_id:
        inv = _get_invocable(job_id, tool_name)
        if inv is None:
            raise HTTPException(
                404,
                f"Tool '{tool_name}' not found for job '{job_id}'. "
                "Register invocables via /api/generate first.",
            )
    else:
        raise HTTPException(400, "Provide job_id or invocable")

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}

    local_admission = _api_local_lane_admission_payload()
    if not bool(local_admission.get("admitted")):
        raise HTTPException(
            503,
            {
                "error": "local_lane_admission_failed",
                "blocking_reasons": list(local_admission.get("blocking_reasons") or []),
                "contract_version": str(local_admission.get("contract_version") or ""),
            },
        )

    logger.info(f"[execute] {tool_name} args={arguments}")
    result = _execute_tool(inv, arguments)
    return JSONResponse({"tool_name": tool_name, "result": result})


@app.post("/api/chat")
async def chat(body: dict[str, Any]):
    """Streaming agentic chat — yields SSE events as tool calls execute."""
    return StreamingResponse(
        stream_chat(body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/download/{job_id}/{filename}")
def download(job_id: str, filename: str):
    """Section 5: Download a generated artifact from Blob Storage."""
    blob_name = f"{job_id}/{filename}"
    try:
        data = _download_blob(ARTIFACT_CONTAINER, blob_name)
    except Exception as e:
        raise HTTPException(404, f"Artifact not found: {e}")

    return StreamingResponse(
        iter([data]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/findings/{job_id}")
def get_findings(job_id: str):
    """Return all LLM-recorded findings for a job as JSON.

    Findings are written by the record_finding synthetic tool during chat
    sessions and persist in Blob Storage.  Clients can download this to get
    a human-readable reverse-engineering document produced by the LLM.
    """
    findings = _load_findings(job_id)
    return JSONResponse(content={"job_id": job_id, "findings": findings})


@app.post("/api/jobs/{job_id}/explore")
async def explore_job(job_id: str, body: dict[str, Any] | None = Body(default=None)):
    """Spawn an autonomous exploration worker for a job.

    The worker iterates over the job's invocables, calls each with probe values,
    and calls enrich_invocable + record_finding to enrich the schema.
    Returns immediately; poll GET /api/jobs/{job_id} for explore_phase progress.

    Optional body: {"invocables": [...]}  — if omitted, uses the invocables
    already registered for this job.
    """
    from api.pipeline.runner import _explore_worker

    body = body or {}
    invocables: list | None = body.get("invocables") if body else None
    runtime_settings = _normalize_explore_runtime_settings(body)
    runtime_settings = _apply_default_repeat_seed(runtime_settings)

    if not invocables:
        inv_map = get_invocables_map(job_id)

        if not inv_map:
            # Fallback: extract from job status result (set by /api/analyze)
            _status = _get_job_status(job_id) or {}
            _result_invocables = (_status.get("result") or {}).get("invocables")
            if _result_invocables:
                inv_map = {inv["name"]: inv for inv in _result_invocables}
                register_invocables(job_id, _result_invocables)

        if not inv_map:
            raise HTTPException(
                404,
                f"No invocables found for job '{job_id}'. "
                "Call /api/generate first, or pass invocables in the request body.",
            )
        invocables = list(inv_map.values())

    current = _get_job_status(job_id)
    if current is None:
        # Create a minimal status entry so the worker can update it
        _persist_job_status(job_id, {
            "status": "done",
            "explore_phase": "queued",
            "progress": 100,
            "message": "Exploration queued",
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        })

    _persist_job_status(job_id, {
        **(_get_job_status(job_id) or {}),
        "status": "running",
        "explore_phase": "queued",
        "explore_progress": "0/0",
        "explore_message": "Exploration queued",
        "explore_runtime": runtime_settings,
        "explore_cancel_requested": False,
        "explore_started_at": time.time(),
        "updated_at": time.time(),
    })

    t = threading.Thread(
        target=_explore_worker,
        args=(job_id, invocables),
        daemon=True,
        name=f"explore-{job_id}",
    )
    t.start()

    logger.info("[%s] Exploration worker spawned for %d invocables", job_id, len(invocables))
    return JSONResponse(
        {
            "job_id": job_id,
            "status": "exploring",
            "invocable_count": len(invocables),
            "explore_runtime": runtime_settings,
        },
        status_code=202,
    )


@app.post("/api/jobs/{job_id}/refine")
async def refine_job(job_id: str, body: dict[str, Any] | None = Body(default=None)):
    """Targeted re-exploration based on user feedback after initial discovery.

    Accepts user corrections and a list of specific functions to re-explore.
    Only re-runs the named functions — already-correct functions are untouched.
    Also accepts free-text feedback that is injected as high-priority hints.

    Body:
      {
        "corrections": "CS_GetAccountBalance description is wrong — amounts are millicents",
        "target_functions": ["CS_GetAccountBalance", "CS_ProcessRefund"],
        "missing": "CS_ApplyDiscount — applies a percentage discount to an order"
      }

    Returns 202 immediately; poll GET /api/jobs/{job_id} for explore_phase progress.
    """
    from api.pipeline.runner import _explore_worker

    body = body or {}
    runtime_settings = _normalize_explore_runtime_settings(body)
    corrections: str = (body.get("corrections") or "").strip()
    target_names: list[str] = body.get("target_functions") or []
    missing_desc: str = (body.get("missing") or "").strip()
    if not runtime_settings.get("focus_functions") and target_names:
        runtime_settings["focus_functions"] = list(target_names)
    runtime_settings = _apply_default_repeat_seed(runtime_settings)

    # Load all invocables for this job
    inv_map = get_invocables_map(job_id)
    if not inv_map:
        raise HTTPException(404, f"No invocables found for job '{job_id}'.")

    all_invocables = list(inv_map.values())

    # Determine target set — default to all if none specified
    if target_names:
        target_invocables = [inv for inv in all_invocables if inv["name"] in target_names]
        if not target_invocables:
            raise HTTPException(400, f"None of the specified functions found in job '{job_id}'.")
    else:
        target_invocables = all_invocables

    # Clear existing findings for targeted functions so re-exploration is clean
    for fn_name in [inv["name"] for inv in target_invocables]:
        try:
            patch_finding(job_id, fn_name, {"status": "pending_refinement", "finding": "", "working_call": None})
        except Exception:
            pass

    # Inject corrections + missing info into job status as high-priority hints
    current = _get_job_status(job_id) or {}
    existing_hints = current.get("hints", "")
    new_hints_parts = [existing_hints] if existing_hints else []
    if corrections:
        new_hints_parts.append(f"CORRECTION: {corrections}")
    if missing_desc:
        new_hints_parts.append(f"MISSING FUNCTION: {missing_desc}")
    combined_hints = " | ".join(new_hints_parts)
    _persist_job_status(job_id, {
        **current,
        "status": "running",
        "hints": combined_hints,
        "explore_phase": "queued",
        "explore_progress": "0/0",
        "explore_message": "Refinement queued…",
        "explore_runtime": runtime_settings,
        "explore_cancel_requested": False,
        "explore_started_at": time.time(),
        "updated_at": time.time(),
    })

    # Preserve the full same-DLL surface for curriculum ordering and prerequisite replay.
    # focus_functions still narrows which functions actually get re-probed.
    t = threading.Thread(
        target=_explore_worker,
        args=(job_id, all_invocables),
        daemon=True,
        name=f"refine-{job_id}",
    )
    t.start()

    logger.info(
        "[%s] Refinement worker spawned: %d target functions, corrections=%r, missing=%r",
        job_id, len(target_invocables), corrections[:80] if corrections else "", missing_desc[:80] if missing_desc else "",
    )
    return JSONResponse(
        {
            "job_id": job_id,
            "status": "refining",
            "target_functions": [inv["name"] for inv in target_invocables],
            "corrections_applied": bool(corrections),
            "missing_added": bool(missing_desc),
            "explore_runtime": runtime_settings,
        },
        status_code=202,
    )


@app.post("/api/jobs/{job_id}/explore-cancel")
async def cancel_explore(job_id: str):
    """Request cancellation of an active explore/refine run.

    Cancellation is cooperative: the worker checks this flag between operations,
    then finalizes and persists partial artifacts before exiting.
    """
    current = _get_job_status(job_id)
    if current is None:
        raise HTTPException(404, f"Job '{job_id}' not found")

    _persist_job_status(
        job_id,
        {
            **current,
            "explore_cancel_requested": True,
            "explore_phase": "cancel_requested",
            "explore_message": "Cancellation requested — stopping after current step…",
            "updated_at": time.time(),
        },
    )
    return JSONResponse({"job_id": job_id, "status": "cancel_requested"}, status_code=202)


@app.post("/api/jobs/{job_id}/answer-gaps")
async def answer_gaps(job_id: str, body: dict[str, Any] | None = Body(default=None)):
    """Accept user answers to gap questions and merge them into vocab + hints.

    Body: {"answers": [{"function": "CS_ProcessPayment", "question": "...", "answer": "..."}]}

    Each answer is:
    - Written into vocab.json under gap_answers so the chat LLM sees it in context
    - Appended to status.json hints
    - Triggers a targeted mini-session per function and re-runs gap generation
    """
    body = body or {}
    answers: list[dict] = body.get("answers") or []
    if not answers:
        raise HTTPException(400, "No answers provided.")

    _cur_settings = (_get_job_status(job_id) or {}).get("explore_runtime") or {}
    _gap_enabled = _as_bool(_cur_settings.get("gap_resolution_enabled"), _GAP_RESOLUTION_ENABLED)
    if not _gap_enabled:
        return JSONResponse(
            {
                "job_id": job_id,
                "status": "gap_resolution_disabled",
                "message": "Gap resolution/mini-sessions are disabled for this run.",
            },
            status_code=202,
        )

    # Merge into vocab.json
    vocab: dict = {}
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/vocab.json")
        vocab = json.loads(raw)
    except Exception:
        pass

    gap_answers = vocab.get("gap_answers") or {}
    for a in answers:
        fn = a.get("function") or "general"
        ans_text = (a.get("answer") or "").strip()
        if ans_text:
            gap_answers[fn] = ans_text
    vocab["gap_answers"] = gap_answers

    try:
        _upload_to_blob(ARTIFACT_CONTAINER, f"{job_id}/vocab.json", json.dumps(vocab).encode())
    except Exception as e:
        logger.warning("[%s] answer-gaps: failed to persist vocab: %s", job_id, e)

    # Append answers as hint corrections so next re-explore uses them
    current = _get_job_status(job_id) or {}
    existing_hints = current.get("hints", "")
    new_parts = [existing_hints] if existing_hints else []
    _answers_by_fn: dict[str, str] = {}
    for a in answers:
        fn = a.get("function") or "general"
        ans_text = (a.get("answer") or "").strip()
        if ans_text:
            new_parts.append(f"DOMAIN ANSWER ({fn}): {ans_text}")
            _answers_by_fn[fn] = ans_text
    combined = " | ".join(new_parts)

    # Mark matching clarification questions as answered so phase closure can
    # deterministically transition to done when applicable.
    _updated_questions = []
    for _q in (current.get("explore_questions") or []):
        if not isinstance(_q, dict):
            _updated_questions.append(_q)
            continue
        _fn = _q.get("function") or "general"
        _ans = _answers_by_fn.get(_fn)
        if _ans:
            _updated_questions.append({**_q, "answered": True, "answer": _ans})
        else:
            _updated_questions.append(_q)

    _persist_job_status(
        job_id,
        {
            **current,
            "hints": combined,
            "explore_questions": _updated_questions,
            "updated_at": time.time(),
        },
    )

    logger.info("[%s] answer-gaps: stored %d answers", job_id, len([a for a in answers if a.get("answer", "").strip()]))

    # Trigger targeted mini-sessions for every function that received an answer,
    # then re-run gap generation to surface any remaining unknowns.
    from api.pipeline.s06_gaps.gap_resolution import _run_gap_answer_mini_sessions
    inv_map = get_invocables_map(job_id)
    if inv_map:
        all_invocables = list(inv_map.values())
        t = threading.Thread(
            target=_run_gap_answer_mini_sessions,
            args=(job_id, all_invocables),
            daemon=True,
            name=f"gap-refinement-{job_id}",
        )
        t.start()
        logger.info("[%s] answer-gaps: spawned gap mini-session worker for %d invocables",
                    job_id, len(all_invocables))
        return JSONResponse(
            {"job_id": job_id, "answers_stored": len(gap_answers), "status": "re_exploring"},
            status_code=202,
        )
    else:
        logger.warning("[%s] answer-gaps: no invocables found — answers stored but no re-exploration triggered", job_id)
        return JSONResponse({"job_id": job_id, "answers_stored": len(gap_answers)})



# ── Campaign endpoints (multi-DLL support) ─────────────────────────────────


@app.post("/api/campaigns")
async def create_campaign(body: dict[str, Any] | None = Body(default=None)):
    """Create a new multi-DLL campaign shell.

    Body: {hints?, use_cases?, analysis_profile?, max_dlls?, package_id?, package_label?,
           package_context?, source_origin?, package_purpose?, doc_visibility?,
           dependency_context?, operator_notes?, baseline_contract?}
    Returns {campaign_id, status_url}.  Attach DLLs incrementally via
    POST /api/campaigns/{campaign_id}/attach, then finalize discovery.
    """
    from api.pipeline.core.types import Campaign, CampaignPhase

    body = body or {}
    campaign_id = str(uuid.uuid4())[:8]
    analysis_profile = str(body.get("analysis_profile") or "strict_dll").strip().lower()
    if analysis_profile not in {"strict_dll", "greybox_dll", "full_surface"}:
        analysis_profile = "strict_dll"

    campaign = Campaign(
        campaign_id=campaign_id,
        hints=str(body.get("hints") or "").strip(),
        use_cases=str(body.get("use_cases") or "").strip(),
        analysis_profile=analysis_profile,
        max_dlls=_as_int(body.get("max_dlls"), 100, 1, 500),
        package_id=str(body.get("package_id") or campaign_id).strip(),
        package_label=str(body.get("package_label") or body.get("package_id") or campaign_id).strip(),
        package_context=dict(body.get("package_context", {}) or {}),
        source_origin=str(body.get("source_origin") or "").strip(),
        package_purpose=str(body.get("package_purpose") or "").strip(),
        doc_visibility=str(body.get("doc_visibility") or "").strip(),
        dependency_context=str(body.get("dependency_context") or "").strip(),
        operator_notes=str(body.get("operator_notes") or "").strip(),
        baseline_contract=dict(body.get("baseline_contract", {}) or {}),
        phase=CampaignPhase.CREATED.value,
    )
    _persist_campaign_status(campaign_id, campaign.to_dict())
    logger.info("[campaign:%s] created (profile=%s)", campaign_id, analysis_profile)

    return JSONResponse({
        "campaign_id": campaign_id,
        "status_url": f"/api/campaigns/{campaign_id}",
        "phase": campaign.phase,
    })


@app.post("/api/campaigns/{campaign_id}/attach")
async def campaign_attach(
    campaign_id: str,
    file: UploadFile = File(...),
    hints: str = Form(default=""),
    selection_reason: str = Form(default=""),
    dependency_confidence: str = Form(default=""),
    lane_id: str = Form(default=""),
):
    """Attach one DLL to a campaign.  Can be called repeatedly.

    Each call creates a new job_id, uploads the file, and starts discovery
    (same as /api/analyze but scoped to the campaign).
    """
    from api.pipeline.core.types import DllEntry, DllStatus, CampaignPhase

    camp = _get_campaign_status(campaign_id)
    if camp is None:
        raise HTTPException(404, f"Campaign '{campaign_id}' not found")
    if camp.get("phase") not in (CampaignPhase.CREATED.value, CampaignPhase.DISCOVERING.value):
        raise HTTPException(
            409,
            f"Campaign is in phase '{camp.get('phase')}'; cannot attach more files.",
        )
    if len(camp.get("dll_entries", [])) >= camp.get("max_dlls", 100):
        raise HTTPException(400, f"Campaign has reached the max DLL limit ({camp.get('max_dlls', 100)}).")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Empty file uploaded")

    job_id = str(uuid.uuid4())[:8]
    dll_id = str(uuid.uuid4())[:8]
    suffix = Path(file.filename).suffix or ".bin"
    blob_name = f"{job_id}/input{suffix}"
    original_name = Path(file.filename).name or f"upload{suffix}"

    try:
        _upload_to_blob(UPLOAD_CONTAINER, blob_name, content)
    except Exception as exc:
        raise HTTPException(500, f"Failed to upload file: {exc}")

    _persist_job_status(job_id, {
        "status": "queued",
        "progress": 0,
        "message": f"Queued analysis for {original_name} (campaign {campaign_id})",
        "hints": hints or camp.get("hints", ""),
        "use_cases": camp.get("use_cases", ""),
        "component_name": Path(file.filename).stem,
        "file_path": original_name,
        "analysis_entrypoint": "upload",
        "binary_origin": "temp_upload",
        "analysis_profile": camp.get("analysis_profile", "strict_dll"),
        "campaign_id": campaign_id,
        "result": None,
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    })

    entry = DllEntry(
        dll_id=dll_id,
        job_id=job_id,
        filename=original_name,
        status=DllStatus.DISCOVERING.value,
        lane_id=str(lane_id or "lane-1").strip(),
        selection_reason=str(selection_reason or "").strip(),
        dependency_confidence=str(dependency_confidence or "").strip(),
    )
    entries = [DllEntry.from_dict(e) for e in camp.get("dll_entries", [])]
    entries.append(entry)

    camp["dll_entries"] = [e.to_dict() for e in entries]
    camp["phase"] = CampaignPhase.DISCOVERING.value
    camp["updated_at"] = time.time()
    _persist_campaign_status(campaign_id, camp)

    # Start discovery in a background thread (same as /api/analyze fallback)
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"upload_{job_id}_"))
    tmp_path = tmp_dir / original_name
    tmp_path.write_bytes(content)
    threading.Thread(
        target=_analyze_worker,
        args=(job_id, tmp_path, hints or camp.get("hints", ""), original_name, tmp_dir, False),
        daemon=True,
        name=f"worker-campaign-{campaign_id}-{job_id}",
    ).start()

    logger.info("[campaign:%s] attached %s as job %s (dll_id=%s)", campaign_id, original_name, job_id, dll_id)
    return JSONResponse({
        "campaign_id": campaign_id,
        "job_id": job_id,
        "dll_id": dll_id,
        "filename": original_name,
        "status_url": f"/api/jobs/{job_id}",
    })


@app.post("/api/campaigns/{campaign_id}/finalize-discovery")
async def campaign_finalize_discovery(campaign_id: str):
    """Signal that all DLLs are attached.  Waits for pending discovery workers,
    then runs the campaign discovery merge (shared evidence graph + plan).
    """
    from api.pipeline.core.types import CampaignPhase, DllStatus

    camp = _get_campaign_status(campaign_id)
    if camp is None:
        raise HTTPException(404, f"Campaign '{campaign_id}' not found")
    entries = camp.get("dll_entries", [])
    if not entries:
        raise HTTPException(400, "No DLLs attached to this campaign.")

    # Poll until all discovery workers finish (up to 10 minutes)
    deadline = time.time() + 600
    while time.time() < deadline:
        all_done = True
        for entry in entries:
            jid = entry.get("job_id", "")
            if not jid:
                continue
            st = _get_job_status(jid)
            if st is None or st.get("status") not in ("done", "error"):
                all_done = False
                break
        if all_done:
            break
        time.sleep(2)

    # Update DLL entry statuses from their job statuses
    for entry in entries:
        jid = entry.get("job_id", "")
        st = _get_job_status(jid) if jid else None
        if st and st.get("status") == "done":
            entry["status"] = DllStatus.DISCOVERED.value
            entry["dll_fingerprint"] = st.get("dll_fingerprint", "")
        elif st and st.get("status") == "error":
            entry["status"] = DllStatus.FAILED.value
            entry["error"] = str(st.get("error", ""))[:500]
        else:
            entry["status"] = DllStatus.FAILED.value
            entry["error"] = "Discovery timed out"

    camp["dll_entries"] = entries
    camp["phase"] = CampaignPhase.PLANNING.value
    camp["updated_at"] = time.time()
    _persist_campaign_status(campaign_id, camp, sync=True)

    # Run campaign discovery merge in-line (produces plan + graph)
    from api.pipeline.runner import _campaign_discovery_merge
    try:
        plan_summary = _campaign_discovery_merge(campaign_id, camp)
    except Exception as exc:
        logger.error("[campaign:%s] discovery merge failed: %s", campaign_id, exc)
        plan_summary = {"error": str(exc)}

    logger.info("[campaign:%s] finalize-discovery complete, %d DLLs", campaign_id, len(entries))
    return JSONResponse({
        "campaign_id": campaign_id,
        "phase": camp["phase"],
        "dll_count": len(entries),
        "plan_summary": plan_summary,
    })


@app.post("/api/campaigns/{campaign_id}/explore")
async def campaign_explore(campaign_id: str, body: dict[str, Any] | None = Body(default=None)):
    """Trigger the multi-DLL explore flow for a finalized campaign.

    Dispatches _explore_worker for each DLL in dependency order, then runs
    S-post consolidation.  Returns 202 immediately; poll GET /api/campaigns/{id}.
    """
    from api.pipeline.core.types import CampaignPhase
    from api.pipeline.runner import _campaign_explore_orchestrator

    camp = _get_campaign_status(campaign_id)
    if camp is None:
        raise HTTPException(404, f"Campaign '{campaign_id}' not found")
    allowed = {CampaignPhase.PLANNING.value, CampaignPhase.CANCELLED_PARTIAL.value}
    if camp.get("phase") not in allowed:
        raise HTTPException(
            409,
            f"Campaign is in phase '{camp.get('phase')}'; explore requires 'planning' or 'cancelled_partial'.",
        )

    body = body or {}
    runtime_settings = _normalize_explore_runtime_settings(body)
    per_dll_runtime_settings = _normalize_campaign_per_dll_explore_settings(body)
    active_dll_targets = _normalize_campaign_active_dll_targets(body)
    floor_plan = _extract_campaign_floor_plan(body)
    decomposition_plan = _extract_campaign_decomposition_plan(body)
    if not floor_plan and isinstance(decomposition_plan.get("package_frontier_plan"), dict):
        floor_plan = dict(decomposition_plan.get("package_frontier_plan") or {})
    if not per_dll_runtime_settings and isinstance(decomposition_plan.get("per_dll_runtime_settings"), dict):
        per_dll_runtime_settings = dict(decomposition_plan.get("per_dll_runtime_settings") or {})
    if not active_dll_targets and isinstance(decomposition_plan.get("active_dll_targets"), list):
        active_dll_targets = [
            str(value or "").strip()
            for value in list(decomposition_plan.get("active_dll_targets") or [])
            if str(value or "").strip()
        ]
    runtime_settings["lane_id"] = str(runtime_settings.get("lane_id") or "lane-1").strip()
    runtime_settings["campaign_id"] = campaign_id

    from api.analysis.blocker_harvest import build_campaign_lane_gate

    job_statuses = []
    for entry in list(camp.get("dll_entries") or []):
        jid = str((entry or {}).get("job_id") or "").strip()
        if not jid:
            continue
        job_statuses.append(_get_job_status(jid) or {})
    lane_gate = build_campaign_lane_gate(
        campaign=camp,
        runtime_settings=runtime_settings,
        job_statuses=job_statuses,
    )
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"campaigns/{campaign_id}/lane-gate.json",
            json.dumps(lane_gate, indent=2).encode("utf-8"),
        )
    except Exception:
        pass
    if lane_gate.get("trust_status") == "blocked":
        raise HTTPException(409, {"detail": "campaign_lane_gate_failed", "lane_gate": lane_gate})

    camp["phase"] = CampaignPhase.EXECUTING.value
    camp["lane_gate"] = lane_gate
    camp["active_dll_targets"] = list(active_dll_targets)
    camp["package_frontier_plan"] = dict(floor_plan)
    camp["floor_to_ceiling_plan"] = dict(floor_plan)
    if decomposition_plan:
        camp["decomposition_campaign_plan"] = dict(decomposition_plan)
    if not dict(camp.get("baseline_contract") or {}) and isinstance(floor_plan.get("baseline_contract"), dict):
        camp["baseline_contract"] = dict(floor_plan.get("baseline_contract") or {})
    camp["updated_at"] = time.time()
    _persist_campaign_status(campaign_id, camp)
    if floor_plan:
        try:
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"campaigns/{campaign_id}/package-frontier-plan.json",
                json.dumps(floor_plan, indent=2).encode("utf-8"),
            )
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"campaigns/{campaign_id}/batch-b-ceiling-plan.json",
                json.dumps(floor_plan, indent=2).encode("utf-8"),
            )
        except Exception:
            pass
    if decomposition_plan:
        try:
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"campaigns/{campaign_id}/decomposition-campaign-plan.json",
                json.dumps(decomposition_plan, indent=2).encode("utf-8"),
            )
        except Exception:
            pass

    threading.Thread(
        target=_campaign_explore_orchestrator,
        args=(campaign_id, camp, runtime_settings, per_dll_runtime_settings, active_dll_targets),
        daemon=True,
        name=f"campaign-explore-{campaign_id}",
    ).start()

    logger.info("[campaign:%s] explore started", campaign_id)
    return JSONResponse({"campaign_id": campaign_id, "phase": "executing"}, status_code=202)


@app.post("/api/campaigns/{campaign_id}/cancel")
async def campaign_cancel(campaign_id: str):
    """Request cancellation of an active campaign.

    Active DLL finishes its current probe step then exits.
    Pending DLLs are skipped.  Completed DLLs are preserved.
    Partial consolidation runs over completed DLLs.
    """
    from api.pipeline.core.types import CampaignPhase

    camp = _get_campaign_status(campaign_id)
    if camp is None:
        raise HTTPException(404, f"Campaign '{campaign_id}' not found")
    camp["cancel_requested"] = True
    camp["updated_at"] = time.time()

    # Propagate cancel to all active DLL jobs
    for entry in camp.get("dll_entries", []):
        jid = entry.get("job_id", "")
        if not jid:
            continue
        st = _get_job_status(jid)
        if st and st.get("status") not in ("done", "error"):
            _persist_job_status(jid, {
                **st,
                "explore_cancel_requested": True,
                "explore_phase": "cancel_requested",
                "updated_at": time.time(),
            })

    _persist_campaign_status(campaign_id, camp)
    logger.info("[campaign:%s] cancel requested", campaign_id)
    return JSONResponse({"campaign_id": campaign_id, "status": "cancel_requested"}, status_code=202)


@app.get("/api/campaigns/{campaign_id}")
async def get_campaign_status(campaign_id: str):
    """Poll campaign state, per-DLL statuses, and overall phase."""
    camp = _get_campaign_status(campaign_id)
    if camp is None:
        raise HTTPException(404, f"Campaign '{campaign_id}' not found")
    camp = _refresh_campaign_poll_state(
        camp,
        get_job_status_fn=_get_job_status,
        persist_campaign_status_fn=_persist_campaign_status,
    )
    return JSONResponse({"campaign_id": campaign_id, **camp})


@app.get("/api/campaigns/{campaign_id}/session-snapshot")
async def campaign_session_snapshot(campaign_id: str):
    """Download a campaign-scoped ZIP with per-DLL session dirs + campaign summary."""
    import io
    import zipfile

    camp = _get_campaign_status(campaign_id)
    if camp is None:
        raise HTTPException(404, f"Campaign '{campaign_id}' not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("campaign.json", json.dumps(camp, indent=2))
        zf.writestr("campaign/campaign.json", json.dumps(camp, indent=2))
        # Include campaign-level blobs if they exist
        for blob_name in (
            "campaign_plan.json",
            "evidence_graph.json",
            "campaign_checkpoint.json",
            "campaign-truth.json",
            "campaign-cohesion-report.json",
            "campaign-attribution-report.json",
        ):
            try:
                data = _download_blob(ARTIFACT_CONTAINER, f"campaigns/{campaign_id}/{blob_name}")
                zf.writestr(blob_name, data)
                if blob_name == "campaign_plan.json":
                    zf.writestr("shared/plans/campaign_plan.json", data)
                elif blob_name == "evidence_graph.json":
                    zf.writestr("shared/evidence-graph/evidence_graph.json", data)
                elif blob_name == "campaign_checkpoint.json":
                    zf.writestr("campaign/checkpoints/campaign_checkpoint.json", data)
                elif blob_name == "campaign-truth.json":
                    zf.writestr("campaign/campaign-truth.json", data)
                elif blob_name == "campaign-cohesion-report.json":
                    zf.writestr("audits/campaign-cohesion-report.json", data)
                elif blob_name == "campaign-attribution-report.json":
                    zf.writestr("audits/campaign-attribution-report.json", data)
            except Exception:
                pass
        # Include per-DLL session snapshots as subdirectories (with sensitivity classification)
        from api.pipeline.core.types import classify_artifact, PersistenceClassification, sensitivity_scan
        sensitivity_warnings: list[str] = []
        for entry in camp.get("dll_entries", []):
            jid = entry.get("job_id", "")
            if not jid:
                continue
            prefix = f"{jid}/"
            try:
                blobs = _list_blob_names(ARTIFACT_CONTAINER, prefix)
                for blob_path in blobs:
                    try:
                        classification = classify_artifact(blob_path)
                        if classification == PersistenceClassification.REDACTED:
                            continue
                        data = _download_blob(ARTIFACT_CONTAINER, blob_path)
                        if classification == PersistenceClassification.SUMMARY_ONLY:
                            text = data.decode("utf-8", errors="replace")
                            lines = text.splitlines()
                            summary = "\n".join(lines[:50])
                            if len(lines) > 50:
                                summary += f"\n\n... ({len(lines) - 50} lines omitted, summary_only) ..."
                            data = summary.encode("utf-8")
                        else:
                            scan = sensitivity_scan(data.decode("utf-8", errors="replace")[:50000])
                            sensitivity_warnings.extend(scan)
                        arc_path = f"dlls/{entry.get('filename', jid)}/{blob_path[len(prefix):]}"
                        zf.writestr(arc_path, data)
                    except Exception:
                        pass
            except Exception:
                pass
        if sensitivity_warnings:
            zf.writestr("sensitivity_warnings.txt", "\n".join(sensitivity_warnings))
            zf.writestr("audits/sensitivity_warnings.txt", "\n".join(sensitivity_warnings))
        zf.writestr(
            "campaign/session-manifest.json",
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "snapshot_kind": "campaign",
                    "campaign_id": campaign_id,
                    "roots": [
                        "campaign/",
                        "dlls/",
                        "shared/",
                        "audits/",
                    ],
                    "origin_semantics": {
                        "emitted": "campaign blob downloaded directly from storage",
                        "summary_only": "artifact included in summarized form for archival safety",
                        "redacted": "artifact intentionally omitted from the campaign snapshot",
                    },
                    "dll_count": len(camp.get("dll_entries", [])),
                },
                indent=2,
            ),
        )

    buf.seek(0)
    from fastapi.responses import StreamingResponse as _SR
    return _SR(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=campaign-{campaign_id}.zip"},
    )


# Session-snapshot and report endpoints live in routes_session.py
from api.routes.routes_session import router as session_router  # noqa: E402
app.include_router(session_router)
