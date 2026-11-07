"""api/worker.py – Local/queue dispatch worker and per-job analysis runner.

_queue_worker_loop: background thread that polls the queue path when enabled.
_analyze_worker:    runs _run_discovery for one job and persists status.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

from api.infra.config import UPLOAD_CONTAINER, ANALYSIS_QUEUE, STORAGE_BACKEND
from api.infra.storage import (
    _queue_service_client,
    _download_blob,
    _get_job_status,
    _persist_job_status,
    _register_invocables,
)
from api.infra.telemetry import _ai_span, _warmup_openai
from api.infra.storage_api import append_job_debug_event

logger = logging.getLogger("mcp_factory.api")

_UPLOAD_INVESTIGATION_ARTIFACT = "upload_investigation.json"
_ACTIVE_ANALYSES: set[str] = set()
_ACTIVE_ANALYSES_LOCK = threading.Lock()

_ABLATION_STATUS_FIELDS = (
    "prompt_profile_id",
    "layer",
    "ablation_variable",
    "ablation_value",
    "run_set_id",
    "coordinator_cycle",
    "playbook_step",
)


def _record_upload_event(job_id: str, phase: str, **fields: object) -> None:
    try:
        append_job_debug_event(
            job_id,
            _UPLOAD_INVESTIGATION_ARTIFACT,
            {
                "source": "worker",
                "phase": phase,
                "pid": os.getpid(),
                "thread_name": threading.current_thread().name,
                **fields,
            },
        )
    except Exception as exc:
        logger.warning("[%s] Failed to append upload investigation event (%s): %s", job_id, phase, exc)


def _record_progress10_control_event(
    job_id: str,
    phase: str,
    *,
    worker_started_monotonic: float,
    original_name: str,
    dispatch_mode: str,
    **fields: object,
) -> None:
    """Record progress-10 control breadcrumbs outside the status packet under diagnosis."""
    now_monotonic = time.monotonic()
    _record_upload_event(
        job_id,
        phase,
        original_name=original_name,
        dispatch_mode=dispatch_mode,
        worker_pid=os.getpid(),
        worker_thread_name=threading.current_thread().name,
        monotonic_ts=now_monotonic,
        wall_ts=time.time(),
        elapsed_ms_since_worker_start=round((now_monotonic - worker_started_monotonic) * 1000, 3),
        **fields,
    )


def _status_persist_boundary_timeout_sec() -> float:
    raw = os.getenv("MCP_WORKER_STATUS_PERSIST_BOUNDARY_TIMEOUT_SEC", "5")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 5.0
    return max(0.1, value)


def _persist_job_status_with_boundary(
    job_id: str,
    payload: dict,
    *,
    boundary: str,
    timeout_sec: float | None = None,
) -> dict[str, object]:
    """Keep early status durability bounded so analysis can still reach authority artifacts."""
    result: dict[str, object] = {
        "boundary": boundary,
        "returned": False,
        "persist_ok": False,
        "timed_out": False,
        "elapsed_ms": 0.0,
    }
    started = time.time()

    def _target() -> None:
        try:
            result["persist_ok"] = bool(_persist_job_status(job_id, payload, sync=True))
        except Exception as exc:
            result["exception_class"] = type(exc).__name__
            result["exception_message"] = str(exc)
        finally:
            result["returned"] = True
            result["elapsed_ms"] = round((time.time() - started) * 1000, 3)

    thread = threading.Thread(
        target=_target,
        daemon=True,
        name=f"status-persist-boundary-{job_id}-{boundary}",
    )
    thread.start()
    thread.join(_status_persist_boundary_timeout_sec() if timeout_sec is None else timeout_sec)
    if thread.is_alive():
        result["timed_out"] = True
        result["elapsed_ms"] = round((time.time() - started) * 1000, 3)
    return result


def _mark_active_analysis(job_id: str) -> list[str]:
    with _ACTIVE_ANALYSES_LOCK:
        peers = sorted(_ACTIVE_ANALYSES)
        _ACTIVE_ANALYSES.add(job_id)
    return peers


def _clear_active_analysis(job_id: str) -> list[str]:
    with _ACTIVE_ANALYSES_LOCK:
        _ACTIVE_ANALYSES.discard(job_id)
        remaining = sorted(_ACTIVE_ANALYSES)
    return remaining


def _analyze_worker(
    job_id: str,
    tmp_path: Path,
    hints: str,
    original_name: str,
    cleanup_dir: Path | None = None,
    skip_cache: bool = False,
) -> None:
    """Background worker — runs discovery and updates job status durably."""
    # Deferred import avoids a load-time cycle: worker → discovery → storage
    # (discovery imports storage; both are already imported above, so CPython's
    # module cache makes this effectively free after the first import).
    from api.services.discovery import _emit_analyzer_runtime_authority, _run_discovery

    # Snapshot fields written at job-creation time (component_name, hints,
    # use_cases, created_at) so every subsequent status overwrite preserves them.
    _init = _get_job_status(job_id) or {}
    _analysis_profile = str(_init.get("analysis_profile") or "strict_dll").strip().lower()
    if _analysis_profile not in {"strict_dll", "greybox_dll", "full_surface"}:
        _analysis_profile = "strict_dll"
    _selected_bridge_url = str(_init.get("selected_bridge_url") or "").strip()
    _ghidra_required = bool(_init.get("ghidra_required"))
    _thread = threading.current_thread()
    _dispatch_mode = "queue-worker" if _thread.name.startswith("queue-job-") else "direct-thread"
    _worker_started_monotonic = time.monotonic()
    _active_mark_started = time.time()
    _active_peers = _mark_active_analysis(job_id)
    _active_mark_elapsed_ms = round((time.time() - _active_mark_started) * 1000, 3)
    _record_upload_event(
        job_id,
        "worker_entry",
        dispatch_mode=_dispatch_mode,
        temp_upload_path=str(tmp_path),
        cleanup_dir=str(cleanup_dir) if cleanup_dir else "",
        original_name=original_name,
        hints=hints,
        analysis_profile=_analysis_profile,
        analysis_entrypoint=str(_init.get("analysis_entrypoint") or ""),
        binary_origin=str(_init.get("binary_origin") or ""),
        lane_id=str(_init.get("lane_id") or ""),
        selected_bridge_url=_selected_bridge_url,
        ghidra_required=_ghidra_required,
        playbook_step=str(_init.get("playbook_step") or ""),
        run_set_id=str(_init.get("run_set_id") or ""),
        component_name=str(_init.get("component_name") or ""),
        active_analysis_count_before=len(_active_peers),
        active_job_ids_before=_active_peers,
        active_analysis_lock_wait_ms=_active_mark_elapsed_ms,
        worker_pid=os.getpid(),
        worker_thread_name=_thread.name,
    )

    _record_progress10_control_event(
        job_id,
        "progress_10_status_persist_start",
        worker_started_monotonic=_worker_started_monotonic,
        original_name=original_name,
        dispatch_mode=_dispatch_mode,
    )
    _progress_10_status_result = _persist_job_status_with_boundary(job_id, {
        **_init,
        "status": "running",
        "progress": 10,
        "message": f"Discovery started for {original_name}",
        "result": None,
        "error": None,
        "updated_at": time.time(),
    }, boundary="progress_10_status")
    _record_progress10_control_event(
        job_id,
        (
            "progress_10_status_persist_timeout"
            if _progress_10_status_result.get("timed_out")
            else "progress_10_status_persist_returned"
        ),
        worker_started_monotonic=_worker_started_monotonic,
        original_name=original_name,
        dispatch_mode=_dispatch_mode,
        persist_ok=bool(_progress_10_status_result.get("persist_ok")),
        persist_returned=bool(_progress_10_status_result.get("returned")),
        persist_timed_out=bool(_progress_10_status_result.get("timed_out")),
        persist_elapsed_ms=_progress_10_status_result.get("elapsed_ms"),
        exception_class=_progress_10_status_result.get("exception_class"),
        exception_message=_progress_10_status_result.get("exception_message"),
    )
    _record_progress10_control_event(
        job_id,
        "progress_10_authority_emit_start",
        worker_started_monotonic=_worker_started_monotonic,
        original_name=original_name,
        dispatch_mode=_dispatch_mode,
        authority_phase="worker_progress_10_persisted",
    )
    _emit_analyzer_runtime_authority(
        job_id,
        "worker_progress_10_persisted",
        binary_path=tmp_path,
        extra={
            "dispatch_mode": _dispatch_mode,
            "original_name": original_name,
            "worker_pid": os.getpid(),
            "worker_thread_name": _thread.name,
            "active_analysis_count_before": len(_active_peers),
            "active_job_ids_before": _active_peers,
            "active_analysis_lock_wait_ms": _active_mark_elapsed_ms,
        },
    )
    _record_progress10_control_event(
        job_id,
        "progress_10_authority_emit_returned",
        worker_started_monotonic=_worker_started_monotonic,
        original_name=original_name,
        dispatch_mode=_dispatch_mode,
        authority_phase="worker_progress_10_persisted",
    )
    _record_progress10_control_event(
        job_id,
        "progress_10_authority_return_marker_emit_start",
        worker_started_monotonic=_worker_started_monotonic,
        original_name=original_name,
        dispatch_mode=_dispatch_mode,
        authority_phase="worker_progress_10_authority_returned",
    )
    _emit_analyzer_runtime_authority(
        job_id,
        "worker_progress_10_authority_returned",
        binary_path=tmp_path,
        extra={
            "dispatch_mode": _dispatch_mode,
            "original_name": original_name,
            "worker_pid": os.getpid(),
            "worker_thread_name": _thread.name,
        },
    )
    _record_progress10_control_event(
        job_id,
        "progress_10_authority_return_marker_emit_returned",
        worker_started_monotonic=_worker_started_monotonic,
        original_name=original_name,
        dispatch_mode=_dispatch_mode,
        authority_phase="worker_progress_10_authority_returned",
    )
    try:
        _progress_30_started = time.time()
        _record_progress10_control_event(
            job_id,
            "progress_30_persist_start_boundary",
            worker_started_monotonic=_worker_started_monotonic,
            original_name=original_name,
            dispatch_mode=_dispatch_mode,
        )
        _emit_analyzer_runtime_authority(
            job_id,
            "worker_progress_30_persist_start",
            binary_path=tmp_path,
            extra={
                "dispatch_mode": _dispatch_mode,
                "original_name": original_name,
                "worker_pid": os.getpid(),
                "worker_thread_name": _thread.name,
            },
        )
        try:
            _record_progress10_control_event(
                job_id,
                "progress_30_status_persist_start",
                worker_started_monotonic=_worker_started_monotonic,
                original_name=original_name,
                dispatch_mode=_dispatch_mode,
            )
            _progress_30_status_result = _persist_job_status_with_boundary(job_id, {
                **_init,
                "status": "running",
                "progress": 30,
                "message": "Running binary analysis pipeline…",
                "result": None,
                "error": None,
                "updated_at": time.time(),
            }, boundary="progress_30_status")
            _record_progress10_control_event(
                job_id,
                (
                    "progress_30_status_persist_timeout"
                    if _progress_30_status_result.get("timed_out")
                    else "progress_30_status_persist_returned"
                ),
                worker_started_monotonic=_worker_started_monotonic,
                original_name=original_name,
                dispatch_mode=_dispatch_mode,
                persist_ok=bool(_progress_30_status_result.get("persist_ok")),
                persist_returned=bool(_progress_30_status_result.get("returned")),
                persist_timed_out=bool(_progress_30_status_result.get("timed_out")),
                persist_elapsed_ms=_progress_30_status_result.get("elapsed_ms"),
                exception_class=_progress_30_status_result.get("exception_class"),
                exception_message=_progress_30_status_result.get("exception_message"),
            )
        except Exception as exc:
            _record_progress10_control_event(
                job_id,
                "worker_pre_progress_30_exception",
                worker_started_monotonic=_worker_started_monotonic,
                original_name=original_name,
                dispatch_mode=_dispatch_mode,
                exception_class=type(exc).__name__,
                exception_message=str(exc),
                failed_boundary="progress_30_persist",
                progress_30_persist_elapsed_ms=round((time.time() - _progress_30_started) * 1000, 3),
            )
            _emit_analyzer_runtime_authority(
                job_id,
                "worker_pre_discovery_exception",
                binary_path=tmp_path,
                extra={
                    "dispatch_mode": _dispatch_mode,
                    "original_name": original_name,
                    "exception_class": type(exc).__name__,
                    "exception_message": str(exc),
                    "failed_boundary": "progress_30_persist",
                    "progress_30_persist_elapsed_ms": round((time.time() - _progress_30_started) * 1000, 3),
                },
            )
            raise
        _emit_analyzer_runtime_authority(
            job_id,
            (
                "worker_progress_30_persist_timeout"
                if _progress_30_status_result.get("timed_out")
                else "worker_progress_30_persisted"
            ),
            binary_path=tmp_path,
            extra={
                "dispatch_mode": _dispatch_mode,
                "original_name": original_name,
                "worker_pid": os.getpid(),
                "worker_thread_name": _thread.name,
                "progress_30_persist_elapsed_ms": round((time.time() - _progress_30_started) * 1000, 3),
                "persist_ok": bool(_progress_30_status_result.get("persist_ok")),
                "persist_returned": bool(_progress_30_status_result.get("returned")),
                "persist_timed_out": bool(_progress_30_status_result.get("timed_out")),
            },
        )
        logger.debug("[%s] entering _run_discovery", job_id)
        _record_upload_event(job_id, "worker_before_discovery", dispatch_mode=_dispatch_mode)
        _emit_analyzer_runtime_authority(
            job_id,
            "worker_before_discovery",
            binary_path=tmp_path,
            extra={"dispatch_mode": _dispatch_mode, "original_name": original_name},
        )
        with _ai_span("analyze_async", job_id=job_id, filename=original_name, hints=hints):
            result = _run_discovery(
                tmp_path,
                job_id,
                hints,
                skip_cache=skip_cache,
                analysis_profile=_analysis_profile,
                bridge_url_override=_selected_bridge_url,
                ghidra_required=_ghidra_required,
            )
        logger.debug("[%s] _run_discovery returned %d invocables", job_id, len(result.get("invocables", [])))
        _record_upload_event(
            job_id,
            "worker_after_discovery",
            dispatch_mode=_dispatch_mode,
            invocable_count=len(result.get("invocables", [])),
        )
        _result_invocables = list(result.get("invocables") or [])
        if _result_invocables:
            try:
                _register_invocables(job_id, _result_invocables)
            except Exception as exc:
                logger.warning("[%s] Failed to persist invocables_map after discovery: %s", job_id, exc)
        # Re-read current status to pick up explore_phase/explore_questions written
        # by explore.py during the run, then layer the final fields on top.
        _current = _get_job_status(job_id) or _init
        _ablation_fields = {name: _current.get(name, _init.get(name)) for name in _ABLATION_STATUS_FIELDS}
        _final_payload = {
            **_current,
            **_ablation_fields,
            "status": "done",
            "progress": 100,
            "message": f"Analysis complete \u2014 {len(_result_invocables)} invocables found",
            "result": result,
            "error": None,
            "updated_at": time.time(),
        }
        ok = _persist_job_status(job_id, _final_payload, sync=True)
        if ok:
            logger.info("[%s] STEP 10 \u2713  Final status persisted to Blob", job_id)
        else:
            logger.error("[%s] STEP 10 \u2717  Final status failed to persist \u2014 retrying for up to 60 s", job_id)
            for _p in range(10):
                time.sleep(6)
                _final_payload["updated_at"] = time.time()
                ok = _persist_job_status(job_id, _final_payload, sync=True)
                if ok:
                    logger.info("[%s] STEP 10 \u2713  Final status persisted on retry %d", job_id, _p + 1)
                    break
            else:
                logger.critical(
                    "[%s] STEP 10 \u2717\u2717  Final status could not be persisted after 10 retries "
                    "\u2014 result exists in memory only and will be lost on container restart.",
                    job_id,
                )
        # Warm up the direct OpenAI path now; the user will often open the chat
        # panel shortly after discovery completes.
        threading.Thread(target=_warmup_openai, daemon=True, name=f"warmup-{job_id}").start()
    except Exception as exc:
        logger.error("[%s] Async discovery failed: %s", job_id, exc)
        _record_upload_event(
            job_id,
            "worker_exception",
            dispatch_mode=_dispatch_mode,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        _persist_job_status(job_id, {
            **(_get_job_status(job_id) or _init),
            "status": "error",
            "progress": 0,
            "message": "Analysis failed",
            "result": None,
            "error": str(exc),
            "updated_at": time.time(),
        }, sync=True)
    finally:
        try:
            if cleanup_dir is not None:
                cleanup_root = cleanup_dir.resolve()
                tmp_resolved = tmp_path.resolve()
                try:
                    tmp_resolved.relative_to(cleanup_root)
                    if tmp_path.exists():
                        tmp_path.unlink(missing_ok=True)
                except ValueError:
                    logger.warning(
                        "[%s] Refusing to delete non-owned analysis target during cleanup: %s",
                        job_id,
                        tmp_path,
                    )
                if cleanup_dir.exists():
                    cleanup_dir.rmdir()
        except Exception as exc:
            logger.warning("[%s] Temp file cleanup failed: %s", job_id, exc)
            _record_upload_event(job_id, "worker_cleanup_warning", warning=str(exc))
        finally:
            _remaining = _clear_active_analysis(job_id)
            _record_upload_event(
                job_id,
                "worker_exit",
                dispatch_mode=_dispatch_mode,
                remaining_active_analysis_count=len(_remaining),
                remaining_active_job_ids=_remaining,
            )


def _queue_worker_loop() -> None:
    """Background thread: poll the analysis queue and process jobs durably.

    - Picks one message at a time with a 10-minute visibility timeout.
    - Downloads the uploaded binary from Blob Storage, runs _analyze_worker.
    - Deletes the message only after the worker finishes (done OR error).
    - If the container restarts mid-analysis the msg becomes visible again
      and is retried automatically by the next instance.
    """
    svc = _queue_service_client()
    if not svc:
        if STORAGE_BACKEND == "local":
            logger.info("Local storage backend active — queue worker not started.")
        else:
            logger.info("No queue configured — queue worker not started.")
        return

    qc = svc.get_queue_client(ANALYSIS_QUEUE)
    try:
        qc.create_queue()
    except Exception as exc:
        logger.warning("Queue create failed (may already exist): %s", exc)

    logger.info("Queue worker started — polling '%s'.", ANALYSIS_QUEUE)
    while True:
        try:
            messages = list(qc.receive_messages(max_messages=1, visibility_timeout=600))
            if not messages:
                time.sleep(3)
                continue

            msg = messages[0]
            try:
                data         = json.loads(msg.content)
                job_id        = data["job_id"]
                blob_name     = data["blob_name"]
                hints         = data.get("hints", "")
                original_name = data.get("original_name", "upload.bin")
                _skip_cache   = bool(data.get("skip_cache", False))
            except Exception as exc:
                logger.error("Malformed queue message, discarding: %s", exc)
                qc.delete_message(msg)
                continue

            logger.info("[%s] STEP 5 \u2713  Queue worker picked up job", job_id)

            # Download the uploaded file from Blob Storage.
            try:
                content = _download_blob(UPLOAD_CONTAINER, blob_name)
                logger.info("[%s] STEP 6 \u2713  Binary downloaded from Blob (%d bytes)", job_id, len(content))
            except Exception as exc:
                logger.error("[%s] STEP 6 \u2717  Binary download from Blob failed: %s", job_id, exc)
                _persist_job_status(job_id, {
                    "status": "error", "progress": 0,
                    "message": "Blob download failed",
                    "result": None, "error": str(exc),
                    "created_at": time.time(), "updated_at": time.time(),
                }, sync=True)
                qc.delete_message(msg)
                continue

            tmp_dir  = Path(tempfile.mkdtemp(prefix=f"queue_{job_id}_"))
            tmp_path = tmp_dir / original_name
            tmp_path.write_bytes(content)

            # Run synchronously in this thread (one job at a time per worker).
            t = threading.Thread(
                target=_analyze_worker,
                args=(job_id, tmp_path, hints, original_name, tmp_dir, _skip_cache),
                daemon=True,
                name=f"queue-job-{job_id}",
            )
            t.start()
            t.join()  # wait before deleting — ensures at-least-once delivery

            qc.delete_message(msg)
            logger.info("[%s] Queue message deleted after completion.", job_id)

        except Exception as exc:
            logger.warning("Queue worker poll error: %s", exc)
            time.sleep(5)
