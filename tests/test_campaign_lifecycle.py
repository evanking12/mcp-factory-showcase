from __future__ import annotations

from fastapi.testclient import TestClient


def test_finalize_worker_verdict_persists_terminal_pair_without_stale_readback(monkeypatch) -> None:
    from api.pipeline import runner

    persisted: list[tuple[str, dict, bool]] = []

    monkeypatch.setattr(
        runner,
        "_get_job_status",
        lambda job_id: {
            "status": "done",
            "explore_phase": "exploring",
            "explore_message": "Analysis complete - 13 invocables found",
        },
    )
    monkeypatch.setattr(
        runner,
        "_persist_job_status",
        lambda job_id, payload, sync=False: persisted.append((job_id, payload, sync)) or True,
    )

    class _Ctx:
        total = 13

    runner._finalize_worker_verdict("job-finalize-1", _Ctx(), "done", 100)  # noqa: SLF001

    assert len(persisted) == 1
    job_id, payload, sync = persisted[0]
    assert job_id == "job-finalize-1"
    assert sync is True
    assert payload["status"] == "done"
    assert payload["explore_phase"] == "done"
    assert payload["explore_stage"] == "done"
    assert payload["explore_progress"] == "13/13"


def test_campaign_child_terminal_view_flags_done_exploring_as_lifecycle_inconsistency() -> None:
    from api.pipeline import runner

    view = runner._campaign_child_terminal_view(  # noqa: SLF001
        {"status": "done", "explore_phase": "exploring"}
    )

    assert view["is_terminal"] is True
    assert view["dll_status"] == "failed"
    assert view["reason"] == "lifecycle_inconsistency"


def test_prime_campaign_child_job_for_explore_sets_running_status(monkeypatch) -> None:
    from api.pipeline import runner

    persisted: list[tuple[str, dict, bool]] = []

    monkeypatch.setattr(runner, "_get_job_status", lambda job_id: {"status": "done", "message": "Analysis complete"})
    monkeypatch.setattr(
        runner,
        "_persist_job_status",
        lambda job_id, payload, sync=False: persisted.append((job_id, payload, sync)) or True,
    )

    payload = runner._prime_campaign_child_job_for_explore(  # noqa: SLF001
        "job-campaign-child-1",
        explore_runtime={"campaign_id": "camp-1", "lane_id": "lane-1"},
    )

    assert payload["status"] == "running"
    assert payload["explore_phase"] == "queued"
    assert payload["explore_message"] == "Exploration queued"
    assert payload["explore_runtime"]["campaign_id"] == "camp-1"
    assert persisted[0][0] == "job-campaign-child-1"
    assert persisted[0][2] is True


def test_select_active_job_uses_canonical_terminal_rule() -> None:
    import api.routes.main as main

    active = main._select_active_job(  # noqa: SLF001
        [
            {"job_id": "job-stale", "status": "done", "explore_phase": "exploring"},
            {"job_id": "job-terminal", "status": "done", "explore_phase": "done"},
        ]
    )

    assert active is not None
    assert active["job_id"] == "job-stale"


def test_get_campaign_status_marks_lifecycle_inconsistency_as_partial_failure(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")

    campaign = {
        "campaign_id": "camp-life-1",
        "phase": "executing",
        "dll_entries": [
            {
                "job_id": "job-life-1",
                "filename": "contoso_transport.dll",
                "status": "exploring",
            }
        ],
    }
    persisted: list[tuple[str, dict, bool]] = []

    monkeypatch.setattr(main, "_get_campaign_status", lambda campaign_id: campaign)
    monkeypatch.setattr(
        main,
        "_persist_campaign_status",
        lambda campaign_id, payload, sync=False: persisted.append((campaign_id, payload, sync)) or True,
    )
    monkeypatch.setattr(
        main,
        "_get_job_status",
        lambda job_id: {"status": "done", "explore_phase": "exploring"},
    )

    with TestClient(main.app) as client:
        response = client.get("/api/campaigns/camp-life-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == "partial_failure"
    assert payload["dll_entries"][0]["status"] == "failed"
    assert "Lifecycle inconsistency" in payload["dll_entries"][0]["error"]
    assert persisted
    assert persisted[0][0] == "camp-life-1"
    assert persisted[0][2] is True
