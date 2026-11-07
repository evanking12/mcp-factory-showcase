from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient


def test_analyze_upload_requires_initial_status_snapshot(monkeypatch) -> None:
    import api.routes.main as main

    enqueue_calls: list[tuple] = []

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(main, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_persist_job_status", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        main,
        "_enqueue_analysis",
        lambda *args, **kwargs: enqueue_calls.append((args, kwargs)) or True,
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/analyze",
            files={"file": ("demo.dll", b"demo-bytes", "application/octet-stream")},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to persist initial job status"
    assert enqueue_calls == []


def test_analyze_upload_rejects_unallowed_bridge_override(monkeypatch) -> None:
    import api.routes.main as main

    enqueue_calls: list[tuple] = []

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setenv("GUI_BRIDGE_CANDIDATE_URLS", "http://127.0.0.1:8090")
    monkeypatch.setattr(main, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_persist_job_status", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        main,
        "_enqueue_analysis",
        lambda *args, **kwargs: enqueue_calls.append((args, kwargs)) or True,
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/analyze",
            files={"file": ("demo.dll", b"demo-bytes", "application/octet-stream")},
            data={"selected_bridge_url": "http://example.com:8090"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["reason_code"] == "bridge_override_not_allowed"
    assert enqueue_calls == []


def test_analyze_upload_blob_timeout_falls_back_without_blocking(monkeypatch) -> None:
    import api.routes.main as main

    enqueue_calls: list[tuple] = []
    worker_calls: list[tuple] = []
    upload_events: list[tuple[str, dict]] = []

    def slow_upload(*_args, **_kwargs) -> None:  # noqa: ANN001
        time.sleep(0.05)

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(main, "_blob_upload_timeout_sec", lambda: 0.01)
    monkeypatch.setattr(main, "_upload_to_blob", slow_upload)
    monkeypatch.setattr(main, "_persist_job_status", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        main,
        "_enqueue_analysis",
        lambda *args, **kwargs: enqueue_calls.append((args, kwargs)) or True,
    )
    monkeypatch.setattr(
        main,
        "_analyze_worker",
        lambda *args, **kwargs: worker_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        main,
        "_record_upload_event",
        lambda job_id, event, **kwargs: upload_events.append((event, kwargs)),
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/analyze",
            files={"file": ("demo.dll", b"demo-bytes", "application/octet-stream")},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert enqueue_calls == []
    assert any(event == "blob_upload_timeout" for event, _ in upload_events)


def test_analyze_upload_slow_diagnostic_event_does_not_block_route(monkeypatch) -> None:
    import api.routes.main as main

    calls: list[tuple] = []

    def slow_append(*args, **kwargs) -> None:  # noqa: ANN001
        calls.append((args, kwargs))
        time.sleep(0.05)

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(main, "_UPLOAD_EVENT_QUEUE", queue.Queue(maxsize=16))
    monkeypatch.setattr(main, "_UPLOAD_EVENT_WORKER_STARTED", False)
    monkeypatch.setattr(main, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_persist_job_status", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "_enqueue_analysis", lambda *args, **kwargs: False)
    monkeypatch.setattr(main, "_analyze_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "append_job_debug_event", slow_append)

    started = time.time()
    with TestClient(main.app) as client:
        response = client.post(
            "/api/analyze",
            files={"file": ("demo.dll", b"demo-bytes", "application/octet-stream")},
        )
    elapsed = time.time() - started

    assert response.status_code == 202
    assert elapsed < 0.5
    main._UPLOAD_EVENT_QUEUE.join()
    assert calls


def test_analyze_upload_diagnostic_events_are_serialized(monkeypatch) -> None:
    import api.routes.main as main

    active = 0
    max_active = 0
    phases: list[str] = []
    lock = threading.Lock()

    def slow_append(_job_id: str, _artifact_name: str, payload: dict) -> None:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.01)
        phases.append(str(payload["phase"]))
        with lock:
            active -= 1

    monkeypatch.setattr(main, "_UPLOAD_EVENT_QUEUE", queue.Queue(maxsize=16))
    monkeypatch.setattr(main, "_UPLOAD_EVENT_WORKER_STARTED", False)
    monkeypatch.setattr(main, "append_job_debug_event", slow_append)

    main._record_upload_event("job-1", "first")
    main._record_upload_event("job-1", "second")
    main._record_upload_event("job-1", "third")
    main._UPLOAD_EVENT_QUEUE.join()

    assert phases == ["first", "second", "third"]
    assert max_active == 1


def test_analyze_upload_diagnostic_event_queue_drops_when_full(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_UPLOAD_EVENT_QUEUE", queue.Queue(maxsize=1))
    monkeypatch.setattr(main, "_UPLOAD_EVENT_WORKER_STARTED", True)

    assert main._enqueue_upload_event("job-1", "first", {"phase": "first"}) is True
    assert main._enqueue_upload_event("job-1", "second", {"phase": "second"}) is False


def test_analyze_upload_diagnostic_event_enqueue_failure_is_fail_open(monkeypatch) -> None:
    import api.routes.main as main

    def fail_enqueue(*_args, **_kwargs) -> bool:  # noqa: ANN002, ANN003
        raise RuntimeError("queue-start-failed")

    monkeypatch.setattr(main, "_enqueue_upload_event", fail_enqueue)

    main._record_upload_event("job-1", "first")


def test_json_list_appends_are_serialized(monkeypatch, tmp_path: Path) -> None:
    import api.infra.storage as storage

    blob_path = tmp_path / "upload_investigation.json"

    def download_blob(_container: str, _blob_name: str) -> bytes:
        time.sleep(0.01)
        if not blob_path.exists():
            raise FileNotFoundError
        return blob_path.read_bytes()

    def upload_blob(_container: str, _blob_name: str, content: bytes) -> None:
        time.sleep(0.01)
        blob_path.write_bytes(content)

    monkeypatch.setattr(storage, "_download_blob", download_blob)
    monkeypatch.setattr(storage, "_upload_to_blob", upload_blob)

    threads = [
        threading.Thread(
            target=storage._append_json_list,
            args=("job-1", "upload_investigation.json", [{"phase": phase}]),
        )
        for phase in ("route", "worker", "discovery")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert {row["phase"] for row in json.loads(blob_path.read_text())} == {
        "route",
        "worker",
        "discovery",
    }
