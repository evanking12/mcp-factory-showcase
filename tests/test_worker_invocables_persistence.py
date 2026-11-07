from __future__ import annotations

from contextlib import nullcontext


def test_progress10_control_breadcrumb_records_out_of_band_fields(monkeypatch) -> None:
    import api.infra.worker as worker

    captured: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(
        worker,
        "append_job_debug_event",
        lambda job_id, artifact, entry: captured.append((job_id, artifact, dict(entry))),
    )

    worker._record_progress10_control_event(
        "job-progress10",
        "progress_10_authority_emit_start",
        worker_started_monotonic=worker.time.monotonic() - 1,
        original_name="spectrum_reservation_stage.dll",
        dispatch_mode="direct-thread",
        authority_phase="worker_progress_10_persisted",
    )

    assert captured
    job_id, artifact, entry = captured[0]
    assert job_id == "job-progress10"
    assert artifact == "upload_investigation.json"
    assert entry["source"] == "worker"
    assert entry["phase"] == "progress_10_authority_emit_start"
    assert entry["original_name"] == "spectrum_reservation_stage.dll"
    assert entry["dispatch_mode"] == "direct-thread"
    assert entry["authority_phase"] == "worker_progress_10_persisted"
    assert "monotonic_ts" in entry
    assert "wall_ts" in entry
    assert entry["elapsed_ms_since_worker_start"] >= 0


def test_status_persist_boundary_returns_success(monkeypatch) -> None:
    import api.infra.worker as worker

    monkeypatch.setattr(worker, "_persist_job_status", lambda *_args, **_kwargs: True)

    result = worker._persist_job_status_with_boundary(
        "job-status-fast",
        {"status": "running"},
        boundary="progress_10_status",
        timeout_sec=0.1,
    )

    assert result["boundary"] == "progress_10_status"
    assert result["returned"] is True
    assert result["persist_ok"] is True
    assert result["timed_out"] is False


def test_status_persist_boundary_times_out_without_blocking(monkeypatch) -> None:
    import api.infra.worker as worker

    def slow_persist(*_args, **_kwargs):
        worker.time.sleep(0.05)
        return True

    monkeypatch.setattr(worker, "_persist_job_status", slow_persist)

    result = worker._persist_job_status_with_boundary(
        "job-status-slow",
        {"status": "running"},
        boundary="progress_10_status",
        timeout_sec=0.01,
    )

    assert result["boundary"] == "progress_10_status"
    assert result["returned"] is False
    assert result["persist_ok"] is False
    assert result["timed_out"] is True
    assert result["elapsed_ms"] >= 0


def test_analyze_worker_registers_invocables_after_discovery(monkeypatch, tmp_path) -> None:
    import api.infra.worker as worker
    import api.services.discovery as discovery

    job_id = "job-invocables"
    dll_path = tmp_path / "sample.dll"
    dll_path.write_bytes(b"binary")

    persisted_statuses: list[dict] = []
    registered: list[tuple[str, list[dict]]] = []

    monkeypatch.setattr(
        worker,
        "_get_job_status",
        lambda _job_id: {
            "status": "queued",
            "analysis_profile": "strict_dll",
            "created_at": 1.0,
            "updated_at": 1.0,
        },
    )
    monkeypatch.setattr(
        worker,
        "_persist_job_status",
        lambda _job_id, payload, sync=False: persisted_statuses.append(dict(payload)) or True,
    )
    monkeypatch.setattr(
        worker,
        "_register_invocables",
        lambda _job_id, invocables: registered.append((_job_id, list(invocables))),
    )
    monkeypatch.setattr(worker, "_warmup_openai", lambda: None)
    monkeypatch.setattr(worker, "_ai_span", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(
        discovery,
        "_run_discovery",
        lambda *_args, **_kwargs: {
            "job_id": job_id,
            "artifact_blob": f"{job_id}/exports.json",
            "invocables": [{"name": "Demo_Fn", "parameters": []}],
        },
    )

    worker._analyze_worker(job_id, dll_path, "", dll_path.name, None, False)

    assert dll_path.exists()
    assert registered == [(job_id, [{"name": "Demo_Fn", "parameters": []}])]
    assert persisted_statuses[-1]["status"] == "done"
    assert persisted_statuses[-1]["result"]["artifact_blob"] == f"{job_id}/exports.json"


def test_analyze_worker_removes_worker_owned_temp_file(monkeypatch, tmp_path) -> None:
    import api.infra.worker as worker
    import api.services.discovery as discovery

    job_id = "job-temp-cleanup"
    cleanup_dir = tmp_path / "owned"
    cleanup_dir.mkdir()
    dll_path = cleanup_dir / "sample.dll"
    dll_path.write_bytes(b"binary")

    monkeypatch.setattr(
        worker,
        "_get_job_status",
        lambda _job_id: {
            "status": "queued",
            "analysis_profile": "strict_dll",
            "created_at": 1.0,
            "updated_at": 1.0,
        },
    )
    monkeypatch.setattr(worker, "_persist_job_status", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(worker, "_register_invocables", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(worker, "_warmup_openai", lambda: None)
    monkeypatch.setattr(worker, "_ai_span", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(
        discovery,
        "_run_discovery",
        lambda *_args, **_kwargs: {
            "job_id": job_id,
            "artifact_blob": f"{job_id}/exports.json",
            "invocables": [],
        },
    )

    worker._analyze_worker(job_id, dll_path, "", dll_path.name, cleanup_dir, False)

    assert not dll_path.exists()
    assert not cleanup_dir.exists()
