from __future__ import annotations

import inspect

from fastapi.testclient import TestClient


def test_api_identity_exposes_machine_readable_contract(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")

    with TestClient(main.app) as client:
        response = client.get("/identity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["component"] == "api"
    assert payload["role"] == "pipeline_control_plane"
    assert payload["contract_version"] == "trust_contract_v1"
    assert payload["pipeline_schema_version"]
    assert payload["status_schema_version"]
    assert payload["build_fingerprint"].startswith("sha256:")
    assert payload["config_fingerprint"].startswith("sha256:")


def test_api_readiness_turns_red_when_bridge_dependency_is_down(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    main._LAB_PROBE_CACHE.clear()
    monkeypatch.setattr(main, "_probe_bridge_status", lambda: {"status": "degraded", "configured": True, "reachable": False})
    monkeypatch.setattr(main, "_probe_model_status", lambda: {"status": "ok", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_storage_status", lambda: {"status": "ok", "backend": "local"})
    monkeypatch.setattr(main, "_probe_queue_status", lambda: {"status": "ok", "backend": "local_dispatch"})

    with TestClient(main.app) as client:
        response = client.get("/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["blocking_reason"] == "bridge_not_ready"
    assert payload["contract_version"] == "trust_contract_v1"


def test_api_readiness_and_admission_handlers_do_not_block_event_loop() -> None:
    import api.routes.main as main

    assert inspect.iscoroutinefunction(main.readiness) is False
    assert inspect.iscoroutinefunction(main.local_lane_admission) is False


def test_api_alive_is_shallow_but_health_requires_green_local_lane(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(
        main,
        "_api_local_lane_admission_payload",
        lambda: {
            "contract_version": "local_lane_admission_v1",
            "admitted": False,
            "blocking_reasons": ["bridge_admission_not_green"],
        },
    )

    with TestClient(main.app) as client:
        alive = client.get("/alive")
        health = client.get("/health")

    assert alive.status_code == 200
    assert alive.json()["status"] == "alive"

    assert health.status_code == 503
    payload = health.json()
    assert payload["healthy"] is False
    assert payload["blocking_reason"] == "bridge_admission_not_green"
    assert payload["diagnostics"]["readiness"] == "/readiness"


def test_api_local_lane_admission_requires_local_storage_and_green_bridge(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(main, "STORAGE_BACKEND", "azure", raising=False)
    main._LAB_PROBE_CACHE.clear()
    monkeypatch.setattr(
        main,
        "_probe_bridge_status",
        lambda: {
            "status": "degraded",
            "configured": True,
            "reachable": True,
            "detail": "bridge_admission_not_green",
            "identity": {
                "component": "bridge",
                "role": "execution_bridge",
                "contract_version": "trust_contract_v1",
                "capabilities": ["execute", "flush_dll_cache"],
            },
            "readiness": {"ready": False, "blocking_reason": "bridge_secret_missing"},
            "admission": {"admitted": False, "blocking_reasons": ["bridge_secret_missing"]},
        },
    )
    monkeypatch.setattr(main, "_probe_model_status", lambda: {"status": "ok", "configured": True, "reachable": True})
    monkeypatch.setattr(main, "_probe_storage_status", lambda: {"status": "ok", "backend": "azure"})
    monkeypatch.setattr(main, "_probe_queue_status", lambda: {"status": "ok", "backend": "local_dispatch"})

    with TestClient(main.app) as client:
        response = client.get("/local-lane-admission")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "local_lane_admission_v1"
    assert payload["runtime_mode"] == "strict_local"
    assert payload["storage_backend"] == "azure"
    assert payload["storage_local_ok"] is False
    assert payload["bridge_admission_ok"] is False
    assert payload["admitted"] is False
    assert "storage_backend_not_local" in payload["blocking_reasons"]
    assert "bridge_admission_not_green" in payload["blocking_reasons"]


def test_api_local_lane_admission_treats_model_unreachable_as_diagnostic(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(main, "STORAGE_BACKEND", "local", raising=False)
    main._LAB_PROBE_CACHE.clear()
    monkeypatch.setattr(
        main,
        "_probe_bridge_status",
        lambda: {
            "status": "ok",
            "configured": True,
            "reachable": True,
            "detail": "admitted",
            "identity": {
                "component": "bridge",
                "role": "execution_bridge",
                "contract_version": "trust_contract_v1",
                "capabilities": ["execute", "flush_dll_cache"],
            },
            "readiness": {"ready": True, "blocking_reasons": []},
            "admission": {"admitted": True, "blocking_reasons": []},
        },
    )
    monkeypatch.setattr(
        main,
        "_probe_model_status",
        lambda: {"status": "invalid", "configured": True, "reachable": False},
    )
    monkeypatch.setattr(main, "_probe_storage_status", lambda: {"status": "ok", "backend": "local"})
    monkeypatch.setattr(main, "_probe_queue_status", lambda: {"status": "ok", "backend": "local_dispatch"})

    with TestClient(main.app) as client:
        readiness_response = client.get("/readiness")
        admission_response = client.get("/local-lane-admission")

    assert readiness_response.status_code == 200
    readiness_payload = readiness_response.json()
    assert readiness_payload["ready"] is False
    assert readiness_payload["blocking_reason"] == "model_not_ready"

    assert admission_response.status_code == 200
    admission_payload = admission_response.json()
    assert admission_payload["admitted"] is True
    assert admission_payload["readiness_ok"] is True
    assert admission_payload["model_reachable"] is False
    assert "model_not_ready" not in admission_payload["blocking_reasons"]


def test_bridge_identity_and_readiness_are_explicit(monkeypatch) -> None:
    import scripts.bridge.gui_bridge as gui_bridge

    monkeypatch.setattr(gui_bridge, "BRIDGE_SECRET", "secret", raising=False)

    with TestClient(gui_bridge.app) as client:
        identity = client.get("/identity", headers={"X-Bridge-Key": "secret"})
        readiness = client.get("/readiness", headers={"X-Bridge-Key": "secret"})
        admission = client.get("/local-lane-admission", headers={"X-Bridge-Key": "secret"})

    assert identity.status_code == 200
    identity_payload = identity.json()
    assert identity_payload["component"] == "bridge"
    assert identity_payload["role"] == "execution_bridge"
    assert identity_payload["contract_version"] == "trust_contract_v1"
    assert "execute" in identity_payload["capabilities"]

    assert readiness.status_code == 200
    readiness_payload = readiness.json()
    assert readiness_payload["ready"] is True
    assert readiness_payload["contract_version"] == "trust_contract_v1"
    assert "flush_dll_cache" in readiness_payload["capabilities"]

    assert admission.status_code == 200
    admission_payload = admission.json()
    assert admission_payload["contract_version"] == "local_lane_admission_v1"
    assert admission_payload["runtime_mode"] == "strict_local"
    assert admission_payload["capability_compatibility_ok"] is True
    assert admission_payload["secret_configured"] is True
    assert admission_payload["admitted"] is True


def test_bridge_alive_is_shallow_but_health_requires_green_local_lane(monkeypatch) -> None:
    import scripts.bridge.gui_bridge as gui_bridge

    monkeypatch.setattr(gui_bridge, "BRIDGE_SECRET", "", raising=False)

    with TestClient(gui_bridge.app) as client:
        alive = client.get("/alive")
        health = client.get("/health")

    assert alive.status_code == 200
    assert alive.json()["status"] == "alive"

    assert health.status_code == 503
    payload = health.json()
    assert payload["healthy"] is False
    assert payload["blocking_reason"] == "bridge_secret_missing"
    assert payload["diagnostics"]["identity"] == "/identity"


def test_bridge_does_not_fallback_missing_dll_temp_path_to_plain_upload(monkeypatch, tmp_path) -> None:
    import scripts.bridge.gui_bridge as gui_bridge

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "fixture.dll").write_bytes(b"stale")
    monkeypatch.setattr(gui_bridge.Path, "exists", lambda self: str(self) == r"C:\Windows\System32\calc.exe")

    resolved = gui_bridge._resolve_exe_path(
        r"C:\Example\AppData\Local\Temp\local_queue_deadbeef\fixture.dll"
    )

    assert resolved == r"C:\Example\AppData\Local\Temp\local_queue_deadbeef\fixture.dll"


def test_api_execute_refuses_when_local_lane_admission_is_red(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(
        main,
        "_api_local_lane_admission_payload",
        lambda: {
            "contract_version": "local_lane_admission_v1",
            "admitted": False,
            "blocking_reasons": ["bridge_admission_not_green"],
        },
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/execute",
            json={
                "tool_name": "SP_Test",
                "invocable": {"name": "SP_Test", "execution": {"method": "cli"}},
                "arguments": {},
            },
        )

    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"]["error"] == "local_lane_admission_failed"
    assert "bridge_admission_not_green" in payload["detail"]["blocking_reasons"]


def test_api_job_terminalization_route_reports_done(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(
        main,
        "_get_job_status",
        lambda job_id: {
            "job_id": job_id,
            "status": "done",
            "explore_phase": "done",
            "explore_stage": "s07_finalize",
            "explore_message": "done",
            "updated_at": 100.0,
        },
    )
    monkeypatch.setattr(main, "_download_blob", lambda *args, **kwargs: b'{"status":"done"}')

    with TestClient(main.app) as client:
        response = client.get("/api/jobs/job-1/terminalization")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-1"
    assert payload["terminal"] is True
    assert payload["terminalization_kind"] == "done"
    assert payload["contract_version"] == "trust_contract_v1"


def test_api_job_terminalization_route_reports_quasi_terminal_stall(monkeypatch) -> None:
    import api.routes.main as main

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(
        main,
        "_get_job_status",
        lambda job_id: {
            "job_id": job_id,
            "status": "running",
            "explore_phase": "awaiting_clarification",
            "explore_stage": "s06_gaps",
            "explore_message": "Finalizing harmonized state...",
            "explore_progress": "1/1",
            "updated_at": 100.0,
        },
    )
    monkeypatch.setattr(main, "_download_blob", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))

    with TestClient(main.app) as client:
        response = client.get("/api/jobs/job-2/terminalization?observed_stable_for_seconds=120")

    assert response.status_code == 200
    payload = response.json()
    assert payload["terminal"] is True
    assert payload["terminalization_kind"] == "quasi_terminal_stall"
    assert payload["reason"]["code"] == "awaiting_clarification_stable_without_authoritative_close"
