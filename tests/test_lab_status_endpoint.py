from __future__ import annotations

from fastapi.testclient import TestClient


def test_model_probe_uses_short_timeout(monkeypatch) -> None:
    import api.routes.health_probes as probes

    observed = {}

    class FakeCompletions:
        def create(self, **kwargs):  # noqa: ANN001
            observed["create_kwargs"] = kwargs
            raise TimeoutError("model probe timed out")

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

        def with_options(self, **kwargs):  # noqa: ANN001
            observed["with_options"] = kwargs
            return self

    monkeypatch.setattr(probes, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(probes, "MODEL_PROBE_TIMEOUT_SECONDS", 3.0)
    monkeypatch.setattr(probes, "_openai_client", lambda: FakeClient())

    result = probes._probe_model_status()

    assert observed["with_options"] == {"timeout": 3.0}
    assert observed["create_kwargs"]["max_tokens"] == 1
    assert result["status"] == "invalid"
    assert result["reachable"] is False
    assert "model probe timed out" in result["detail"]


def test_lab_status_reports_valid_lane_when_support_systems_are_healthy(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    main._LAB_PROBE_CACHE.clear()

    monkeypatch.setattr(
        main,
        "_recent_job_entries",
        lambda limit=20: [
            {
                "job_id": "job-123",
                "component_name": "contoso_cs",
                "status": "done",
                "explore_phase": "done",
                "coverage_pct": 100,
                "verified_count": 12,
                "total_count": 12,
                "macro_status": "done",
                "created_at": 123.0,
            }
        ],
    )
    monkeypatch.setattr(main, "_probe_bridge_status", lambda: {"status": "ok", "detail": "reachable", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_model_status", lambda: {"status": "ok", "detail": "reachable", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_storage_status", lambda: {"status": "ok", "detail": "ok", "backend": "local"})
    monkeypatch.setattr(main, "_probe_queue_status", lambda: {"status": "ok", "detail": "local dispatch", "backend": "local_dispatch"})

    with TestClient(main.app) as client:
        response = client.get("/api/lab/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "valid"
    assert payload["lane_validity"]["promotion_safe"] is True
    assert payload["active_run"]["job_id"] == "job-123"
    assert payload["recent_jobs"][0]["component_name"] == "contoso_cs"


def test_lab_status_marks_lane_degraded_when_bridge_is_down(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    main._LAB_PROBE_CACHE.clear()

    monkeypatch.setattr(main, "_recent_job_entries", lambda limit=20: [])
    monkeypatch.setattr(main, "_probe_bridge_status", lambda: {"status": "degraded", "detail": "bridge unavailable", "configured": True, "reachable": False})
    monkeypatch.setattr(main, "_probe_model_status", lambda: {"status": "ok", "detail": "reachable", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_storage_status", lambda: {"status": "ok", "detail": "ok", "backend": "local"})
    monkeypatch.setattr(main, "_probe_queue_status", lambda: {"status": "ok", "detail": "local dispatch", "backend": "local_dispatch"})

    with TestClient(main.app) as client:
        response = client.get("/api/lab/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["lane_validity"]["promotion_safe"] is False
    assert "GUI bridge is unavailable or degraded" in payload["lane_validity"]["warnings"]


def test_lab_status_allows_active_running_explore_job(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    main._LAB_PROBE_CACHE.clear()

    monkeypatch.setattr(
        main,
        "_recent_job_entries",
        lambda limit=20: [
            {
                "job_id": "job-456",
                "component_name": "contoso_reporting",
                "status": "running",
                "explore_phase": "exploring",
                "coverage_pct": 0,
                "verified_count": 0,
                "total_count": 0,
                "macro_status": "",
                "created_at": 456.0,
            }
        ],
    )
    monkeypatch.setattr(main, "_probe_bridge_status", lambda: {"status": "ok", "detail": "reachable", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_model_status", lambda: {"status": "ok", "detail": "reachable", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_storage_status", lambda: {"status": "ok", "detail": "ok", "backend": "local"})
    monkeypatch.setattr(main, "_probe_queue_status", lambda: {"status": "ok", "detail": "local dispatch", "backend": "local_dispatch"})

    with TestClient(main.app) as client:
        response = client.get("/api/lab/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "valid"
    assert payload["lane_validity"]["promotion_safe"] is True
    assert payload["active_run"]["job_id"] == "job-456"


def test_lab_status_ignores_stale_cancel_requested_job(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    main._LAB_PROBE_CACHE.clear()

    stale_updated_at = 1.0
    monkeypatch.setattr(
        main,
        "_recent_job_entries",
        lambda limit=20: [
            {
                "job_id": "job-stale-cancel",
                "component_name": "contoso_reporting",
                "status": "running",
                "explore_phase": "cancel_requested",
                "coverage_pct": 0,
                "verified_count": 0,
                "total_count": 0,
                "macro_status": "",
                "updated_at": stale_updated_at,
                "created_at": stale_updated_at,
            },
            {
                "job_id": "job-done",
                "component_name": "contoso_workflow",
                "status": "done",
                "explore_phase": "done",
                "coverage_pct": 100,
                "verified_count": 12,
                "total_count": 12,
                "macro_status": "done",
                "created_at": 2.0,
            },
        ],
    )
    monkeypatch.setattr(main, "_probe_bridge_status", lambda: {"status": "ok", "detail": "reachable", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_model_status", lambda: {"status": "ok", "detail": "reachable", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_storage_status", lambda: {"status": "ok", "detail": "ok", "backend": "local"})
    monkeypatch.setattr(main, "_probe_queue_status", lambda: {"status": "ok", "detail": "local dispatch", "backend": "local_dispatch"})

    with TestClient(main.app) as client:
        response = client.get("/api/lab/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "valid"
    assert payload["active_run"]["job_id"] == "job-done"


def test_lab_status_keeps_fresh_cancel_requested_job_active(monkeypatch) -> None:
    import time
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    main._LAB_PROBE_CACHE.clear()

    fresh_updated_at = time.time()
    monkeypatch.setattr(
        main,
        "_recent_job_entries",
        lambda limit=20: [
            {
                "job_id": "job-fresh-cancel",
                "component_name": "contoso_reporting",
                "status": "running",
                "explore_phase": "cancel_requested",
                "coverage_pct": 0,
                "verified_count": 0,
                "total_count": 0,
                "macro_status": "",
                "updated_at": fresh_updated_at,
                "created_at": fresh_updated_at,
            },
            {
                "job_id": "job-done",
                "component_name": "contoso_workflow",
                "status": "done",
                "explore_phase": "done",
                "coverage_pct": 100,
                "verified_count": 12,
                "total_count": 12,
                "macro_status": "done",
                "created_at": 2.0,
            },
        ],
    )
    monkeypatch.setattr(main, "_probe_bridge_status", lambda: {"status": "ok", "detail": "reachable", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_model_status", lambda: {"status": "ok", "detail": "reachable", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_storage_status", lambda: {"status": "ok", "detail": "ok", "backend": "local"})
    monkeypatch.setattr(main, "_probe_queue_status", lambda: {"status": "ok", "detail": "local dispatch", "backend": "local_dispatch"})

    with TestClient(main.app) as client:
        response = client.get("/api/lab/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "valid"
    assert payload["active_run"]["job_id"] == "job-fresh-cancel"


def test_lab_status_ignores_stale_nonterminal_job(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    main._LAB_PROBE_CACHE.clear()

    stale_updated_at = 1.0
    monkeypatch.setattr(
        main,
        "_recent_job_entries",
        lambda limit=20: [
            {
                "job_id": "job-stale-running",
                "component_name": "contoso_gateway",
                "status": "running",
                "explore_phase": "exploring",
                "coverage_pct": 0,
                "verified_count": 0,
                "total_count": 0,
                "macro_status": "",
                "updated_at": stale_updated_at,
                "created_at": stale_updated_at,
            },
            {
                "job_id": "job-done",
                "component_name": "contoso_workflow",
                "status": "done",
                "explore_phase": "done",
                "coverage_pct": 100,
                "verified_count": 12,
                "total_count": 12,
                "macro_status": "done",
                "created_at": 2.0,
            },
        ],
    )
    monkeypatch.setattr(main, "_probe_bridge_status", lambda: {"status": "ok", "detail": "reachable", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_model_status", lambda: {"status": "ok", "detail": "reachable", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_storage_status", lambda: {"status": "ok", "detail": "ok", "backend": "local"})
    monkeypatch.setattr(main, "_probe_queue_status", lambda: {"status": "ok", "detail": "local dispatch", "backend": "local_dispatch"})

    with TestClient(main.app) as client:
        response = client.get("/api/lab/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "valid"
    assert payload["active_run"]["job_id"] == "job-done"
