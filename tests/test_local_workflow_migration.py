from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_local_storage_roundtrip_and_list(monkeypatch, tmp_path: Path) -> None:
    from api.infra import storage

    monkeypatch.setattr(storage, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(storage, "LOCAL_DATA_ROOT", tmp_path)

    blob_name = "job-1/status.json"
    payload = {"status": "running"}

    storage._upload_to_blob("artifacts", blob_name, json.dumps(payload).encode("utf-8"))

    raw = storage._download_blob("artifacts", blob_name)
    listed = storage._list_blob_names("artifacts", "job-1/")

    assert json.loads(raw.decode("utf-8")) == payload
    assert listed == [blob_name]


def test_enqueue_analysis_uses_local_worker_path(monkeypatch, tmp_path: Path) -> None:
    from api.infra import storage
    from api.infra import worker

    monkeypatch.setattr(storage, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(storage, "LOCAL_DATA_ROOT", tmp_path)

    storage._upload_to_blob("uploads", "job-123/input.dll", b"binary")

    captured: dict[str, object] = {}

    def _fake_worker(job_id, tmp_path_arg, hints, original_name, cleanup_dir=None, skip_cache=False):
        captured["job_id"] = job_id
        captured["tmp_path"] = str(tmp_path_arg)
        captured["hints"] = hints
        captured["original_name"] = original_name
        captured["cleanup_dir"] = str(cleanup_dir) if cleanup_dir is not None else None
        captured["skip_cache"] = skip_cache

    class _ImmediateThread:
        def __init__(self, *, target, args=(), daemon=None, name=None):
            self._target = target
            self._args = args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr(worker, "_analyze_worker", _fake_worker)
    monkeypatch.setattr(storage.threading, "Thread", _ImmediateThread)

    ok = storage._enqueue_analysis(
        "job-123",
        "job-123/input.dll",
        "hello",
        "input.dll",
        skip_cache=True,
    )

    assert ok is True
    assert captured["job_id"] == "job-123"
    assert captured["original_name"] == "input.dll"
    assert captured["hints"] == "hello"
    assert captured["skip_cache"] is True
    assert Path(str(captured["tmp_path"])).name == "input.dll"


def test_openai_client_requires_direct_openai_key(monkeypatch) -> None:
    from api.infra import telemetry

    monkeypatch.setattr(telemetry, "_cached_client", None)
    monkeypatch.setattr(telemetry, "OPENAI_API_KEY", "")

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        telemetry._openai_client()


def test_openai_client_uses_direct_openai_only(monkeypatch) -> None:
    from api.infra import telemetry

    monkeypatch.setattr(telemetry, "_cached_client", None)
    monkeypatch.setattr(telemetry, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(telemetry, "OPENAI_MODEL", "gpt-4o-mini")

    client = telemetry._openai_client()

    assert client is not None
