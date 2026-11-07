from __future__ import annotations

import json


def test_persist_campaign_status_snapshots_payload_before_upload(monkeypatch) -> None:
    from api.infra import storage

    campaign_id = "camp-snapshot"
    payload = {
        "campaign_id": campaign_id,
        "phase": "discovering",
        "dll_entries": [{"dll_id": "a", "job_id": "job-a"}],
    }
    uploads: list[dict] = []

    def _fake_upload(container: str, blob_name: str, data: bytes) -> str:
        uploads.append(json.loads(data.decode()))
        return blob_name

    monkeypatch.setattr(storage, "_upload_to_blob", _fake_upload)

    storage._persist_campaign_status(campaign_id, payload)
    payload["dll_entries"].append({"dll_id": "b", "job_id": "job-b"})

    with storage._CAMPAIGN_STATUS_LOCK:
        cached = storage._CAMPAIGN_STATUS[campaign_id]

    assert len(cached["dll_entries"]) == 1
    assert len(uploads) == 1
    assert len(uploads[0]["dll_entries"]) == 1


def test_get_campaign_status_prefers_live_cache_over_stale_blob(monkeypatch) -> None:
    from api.infra import storage

    campaign_id = "camp-live-cache"
    cached = {
        "campaign_id": campaign_id,
        "phase": "discovering",
        "dll_entries": [
            {"dll_id": "a", "job_id": "job-a"},
            {"dll_id": "b", "job_id": "job-b"},
        ],
    }
    stale_blob = {
        "campaign_id": campaign_id,
        "phase": "discovering",
        "dll_entries": [
            {"dll_id": "a", "job_id": "job-a"},
        ],
    }

    with storage._CAMPAIGN_STATUS_LOCK:
        storage._CAMPAIGN_STATUS[campaign_id] = cached

    monkeypatch.setattr(
        storage,
        "_download_blob",
        lambda container, blob_name: json.dumps(stale_blob).encode(),
    )

    result = storage._get_campaign_status(campaign_id)

    assert result == cached


def test_get_campaign_status_falls_back_to_blob_when_cache_missing(monkeypatch) -> None:
    from api.infra import storage

    campaign_id = "camp-blob-fallback"
    blob_value = {
        "campaign_id": campaign_id,
        "phase": "planning",
        "dll_entries": [
            {"dll_id": "a", "job_id": "job-a"},
            {"dll_id": "b", "job_id": "job-b"},
        ],
    }

    with storage._CAMPAIGN_STATUS_LOCK:
        storage._CAMPAIGN_STATUS.pop(campaign_id, None)

    monkeypatch.setattr(
        storage,
        "_download_blob",
        lambda container, blob_name: json.dumps(blob_value).encode(),
    )

    result = storage._get_campaign_status(campaign_id)

    assert result == blob_value


def test_persist_campaign_status_preserves_package_and_dll_metadata(monkeypatch) -> None:
    from api.infra import storage

    campaign_id = "camp-metadata"
    payload = {
        "campaign_id": campaign_id,
        "phase": "planning",
        "package_id": "pkg-1",
        "package_label": "Legacy bundle",
        "doc_visibility": "unknown",
        "dll_entries": [
            {
                "dll_id": "dll-a",
                "job_id": "job-a",
                "filename": "a.dll",
                "lane_id": "lane-1",
                "selection_reason": "top_candidate",
                "dependency_confidence": "high",
                "blocker_family_primary": "struct/payload shaping",
            }
        ],
    }
    uploads: list[dict] = []

    monkeypatch.setattr(
        storage,
        "_upload_to_blob",
        lambda _container, _blob_name, data: uploads.append(json.loads(data.decode("utf-8"))) or "ok",
    )

    storage._persist_campaign_status(campaign_id, payload)

    with storage._CAMPAIGN_STATUS_LOCK:
        cached = storage._CAMPAIGN_STATUS[campaign_id]

    assert cached["package_id"] == "pkg-1"
    assert cached["package_label"] == "Legacy bundle"
    assert cached["dll_entries"][0]["selection_reason"] == "top_candidate"
    assert uploads[0]["dll_entries"][0]["blocker_family_primary"] == "struct/payload shaping"
