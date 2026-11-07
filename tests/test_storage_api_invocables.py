from __future__ import annotations

import json

from api.infra import storage_api


def test_get_invocables_map_prefers_in_memory_registry(monkeypatch) -> None:
    monkeypatch.setattr(
        storage_api,
        "_get_current_invocables",
        lambda job_id: [{"name": "FnA", "description": "from-memory"}],
    )

    def _unexpected_download(*args, **kwargs):
        raise AssertionError("blob fallback should not run when memory is populated")

    monkeypatch.setattr(storage_api, "_download_blob", _unexpected_download)

    result = storage_api.get_invocables_map("job-1")

    assert result == {"FnA": {"name": "FnA", "description": "from-memory"}}


def test_get_invocables_map_reads_blob_without_registering(monkeypatch) -> None:
    monkeypatch.setattr(storage_api, "_get_current_invocables", lambda job_id: [])
    monkeypatch.setattr(
        storage_api,
        "_download_blob",
        lambda container, blob_name: json.dumps(
            {"FnB": {"name": "FnB", "description": "from-blob"}}
        ).encode("utf-8"),
    )

    def _unexpected_register(job_id: str, invocables: list[dict[str, object]]) -> None:
        raise AssertionError("read helper should not register or persist on blob fallback")

    monkeypatch.setattr(storage_api, "_register_invocables", _unexpected_register)

    result = storage_api.get_invocables_map("job-2")

    assert result == {"FnB": {"name": "FnB", "description": "from-blob"}}


def test_get_invocables_map_returns_empty_dict_on_blob_miss(monkeypatch) -> None:
    monkeypatch.setattr(storage_api, "_get_current_invocables", lambda job_id: [])

    def _blob_miss(container: str, blob_name: str) -> bytes:
        raise FileNotFoundError(blob_name)

    monkeypatch.setattr(storage_api, "_download_blob", _blob_miss)

    result = storage_api.get_invocables_map("job-3")

    assert result == {}


def test_get_invocables_map_returns_empty_dict_on_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(storage_api, "_get_current_invocables", lambda job_id: [])
    monkeypatch.setattr(
        storage_api,
        "_download_blob",
        lambda container, blob_name: b"{not-json",
    )

    result = storage_api.get_invocables_map("job-invalid-json")

    assert result == {}


def test_get_invocables_map_returns_empty_dict_on_non_dict_payload(monkeypatch) -> None:
    monkeypatch.setattr(storage_api, "_get_current_invocables", lambda job_id: [])
    monkeypatch.setattr(
        storage_api,
        "_download_blob",
        lambda container, blob_name: json.dumps(["FnD"]).encode("utf-8"),
    )

    result = storage_api.get_invocables_map("job-non-dict")

    assert result == {}


def test_get_invocables_map_returns_empty_dict_on_blob_read_failure(monkeypatch) -> None:
    monkeypatch.setattr(storage_api, "_get_current_invocables", lambda job_id: [])

    def _blob_failure(container: str, blob_name: str) -> bytes:
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(storage_api, "_download_blob", _blob_failure)

    result = storage_api.get_invocables_map("job-read-failure")

    assert result == {}


def test_prime_invocables_cache_updates_memory_without_registering(monkeypatch) -> None:
    captured: list[tuple[str, dict[str, dict[str, object]]]] = []

    monkeypatch.setattr(
        storage_api,
        "_prime_invocables_cache",
        lambda job_id, invocables_map: captured.append((job_id, dict(invocables_map))),
    )

    storage_api.prime_invocables_cache(
        "job-4",
        {"FnC": {"name": "FnC", "description": "memory-only"}},
    )

    assert captured == [
        (
            "job-4",
            {"FnC": {"name": "FnC", "description": "memory-only"}},
        )
    ]
