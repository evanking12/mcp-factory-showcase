from __future__ import annotations

import json
import os


def _clear_job_status_state(storage, job_id: str) -> None:
    with storage._JOB_STATUS_LOCK:
        storage._JOB_STATUS.pop(job_id, None)
    with storage._JOB_STATUS_WRITE_STATE_LOCK:
        storage._JOB_STATUS_SEQUENCE.pop(job_id, None)
        storage._JOB_STATUS_WRITE_LOCKS.pop(job_id, None)


def test_upload_to_blob_uses_atomic_local_replace(monkeypatch, tmp_path) -> None:
    from api.infra import storage

    monkeypatch.setattr(storage, "LOCAL_DATA_ROOT", tmp_path)

    storage._upload_to_blob("artifacts", "job-1/status.json", b'{"status":"running"}')
    storage._upload_to_blob("artifacts", "job-1/status.json", b'{"status":"done"}')

    path = tmp_path / "artifacts" / "job-1" / "status.json"
    assert path.read_bytes() == b'{"status":"done"}'
    assert not list(path.parent.glob("*.tmp"))


def test_upload_to_blob_retries_transient_atomic_replace_failure(monkeypatch, tmp_path) -> None:
    from api.infra import storage

    monkeypatch.setattr(storage, "LOCAL_DATA_ROOT", tmp_path)
    original_replace = storage.os.replace
    attempts = {"count": 0}

    def flaky_replace(src, dst):  # noqa: ANN001
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise PermissionError("transient replace contention")
        return original_replace(src, dst)

    monkeypatch.setattr(storage.os, "replace", flaky_replace)
    monkeypatch.setattr(storage.time, "sleep", lambda _seconds: None)

    storage._upload_to_blob("artifacts", "job-1/status.json", b'{"status":"running"}')

    path = tmp_path / "artifacts" / "job-1" / "status.json"
    assert path.read_bytes() == b'{"status":"running"}'
    assert attempts["count"] == 2
    assert not list(path.parent.glob("*.tmp"))


def test_stale_async_status_persist_cannot_overwrite_later_terminal(monkeypatch) -> None:
    from api.infra import storage

    job_id = "job-status-sequence"
    _clear_job_status_state(storage, job_id)
    uploads: list[dict] = []
    pending_targets: list[object] = []

    class CapturedThread:
        def __init__(self, *, target, daemon=True, name="") -> None:  # noqa: ANN001
            self.target = target

        def start(self) -> None:
            pending_targets.append(self.target)

    monkeypatch.setattr(storage.threading, "Thread", CapturedThread)
    monkeypatch.setattr(
        storage,
        "_upload_to_blob",
        lambda _container, _blob_name, data: uploads.append(json.loads(data.decode("utf-8"))) or "ok",
    )

    assert storage._persist_job_status(job_id, {"status": "running", "progress": 90}, sync=False)
    assert len(pending_targets) == 1
    assert storage._persist_job_status(job_id, {"status": "done", "progress": 100}, sync=True)

    pending_targets[0]()

    assert uploads == [{"status": "done", "progress": 100}]


def test_sync_status_persist_times_out_waiting_for_prior_writer(monkeypatch) -> None:
    from api.infra import storage

    job_id = "job-status-lock-timeout"
    _clear_job_status_state(storage, job_id)
    uploads: list[dict] = []
    lock = storage.threading.Lock()
    assert lock.acquire(blocking=False)

    with storage._JOB_STATUS_WRITE_STATE_LOCK:
        storage._JOB_STATUS_WRITE_LOCKS[job_id] = lock

    monkeypatch.setenv("MCP_STATUS_SYNC_WRITE_LOCK_TIMEOUT_SEC", "0.01")
    monkeypatch.setattr(
        storage,
        "_upload_to_blob",
        lambda _container, _blob_name, data: uploads.append(json.loads(data.decode("utf-8"))) or "ok",
    )

    try:
        assert not storage._persist_job_status(job_id, {"status": "running", "progress": 10}, sync=True)
    finally:
        lock.release()

    with storage._JOB_STATUS_LOCK:
        cached = storage._JOB_STATUS[job_id]
    assert cached == {"status": "running", "progress": 10}
    assert uploads == []


def test_nonterminal_status_is_ignored_after_terminal_close(monkeypatch) -> None:
    from api.infra import storage

    job_id = "job-terminal-guard"
    _clear_job_status_state(storage, job_id)
    uploads: list[dict] = []
    monkeypatch.setattr(
        storage,
        "_upload_to_blob",
        lambda _container, _blob_name, data: uploads.append(json.loads(data.decode("utf-8"))) or "ok",
    )

    assert storage._persist_job_status(
        job_id,
        {"status": "done", "explore_phase": "done", "progress": 100},
        sync=True,
    )
    assert storage._persist_job_status(job_id, {"status": "running", "progress": 95}, sync=True)

    with storage._JOB_STATUS_LOCK:
        cached = storage._JOB_STATUS[job_id]
    assert cached["status"] == "done"
    assert uploads == [{"status": "done", "explore_phase": "done", "progress": 100}]


def test_analyze_done_can_transition_to_explore_running(monkeypatch) -> None:
    from api.infra import storage

    job_id = "job-analyze-to-explore"
    _clear_job_status_state(storage, job_id)
    uploads: list[dict] = []
    monkeypatch.setattr(
        storage,
        "_upload_to_blob",
        lambda _container, _blob_name, data: uploads.append(json.loads(data.decode("utf-8"))) or "ok",
    )

    assert storage._persist_job_status(job_id, {"status": "done", "progress": 100}, sync=True)
    assert storage._persist_job_status(
        job_id,
        {
            "status": "running",
            "explore_phase": "queued",
            "explore_runtime": {"prior_job_id": "prior-1"},
            "progress": 100,
        },
        sync=True,
    )

    with storage._JOB_STATUS_LOCK:
        cached = storage._JOB_STATUS[job_id]
    assert cached["status"] == "running"
    assert cached["explore_runtime"] == {"prior_job_id": "prior-1"}
    assert uploads == [
        {"status": "done", "progress": 100},
        {
            "status": "running",
            "explore_phase": "queued",
            "explore_runtime": {"prior_job_id": "prior-1"},
            "progress": 100,
        },
    ]


def test_get_job_status_recovers_newer_valid_local_temp(monkeypatch, tmp_path) -> None:
    from api.infra import storage

    job_id = "job-status-temp-recovery"
    _clear_job_status_state(storage, job_id)
    monkeypatch.setattr(storage, "LOCAL_DATA_ROOT", tmp_path)

    job_dir = tmp_path / "artifacts" / job_id
    job_dir.mkdir(parents=True)
    status_path = job_dir / "status.json"
    tmp_status_path = job_dir / ".status.json.1.2.tmp"
    status_path.write_text(json.dumps({"status": "running", "explore_stage": "stale"}))
    tmp_status_path.write_text(json.dumps({"status": "running", "explore_span": "s07_harmonize_load_findings"}))
    os.utime(status_path, (10, 10))
    os.utime(tmp_status_path, (20, 20))

    status = storage._get_job_status(job_id)

    assert status is not None
    assert status["explore_span"] == "s07_harmonize_load_findings"


def test_get_job_status_ignores_invalid_or_older_local_temp(monkeypatch, tmp_path) -> None:
    from api.infra import storage

    job_id = "job-status-temp-ignore"
    _clear_job_status_state(storage, job_id)
    monkeypatch.setattr(storage, "LOCAL_DATA_ROOT", tmp_path)

    job_dir = tmp_path / "artifacts" / job_id
    job_dir.mkdir(parents=True)
    status_path = job_dir / "status.json"
    invalid_tmp = job_dir / ".status.json.1.2.tmp"
    older_tmp = job_dir / ".status.json.3.4.tmp"
    status_path.write_text(json.dumps({"status": "running", "explore_stage": "current"}))
    invalid_tmp.write_text("{not-json")
    older_tmp.write_text(json.dumps({"status": "running", "explore_stage": "older"}))
    os.utime(status_path, (20, 20))
    os.utime(invalid_tmp, (30, 30))
    os.utime(older_tmp, (10, 10))

    status = storage._get_job_status(job_id)

    assert status is not None
    assert status["explore_stage"] == "current"
