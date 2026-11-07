from __future__ import annotations

from fastapi.testclient import TestClient


def test_explore_route_reads_json_body_runtime_settings(monkeypatch) -> None:
    import api.routes.main as main

    persisted: list[dict] = []

    class _DummyThread:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        def start(self) -> None:
            return None

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(main.threading, "Thread", _DummyThread)
    monkeypatch.setattr(main, "_get_job_status", lambda job_id: {"job_id": job_id, "status": "done"})
    monkeypatch.setattr(
        main,
        "_persist_job_status",
        lambda job_id, payload, sync=False: persisted.append(payload),
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/jobs/job-1/explore",
            json={
                "invocables": [
                    {
                        "name": "RP_Initialize",
                        "execution": {"method": "dll_import"},
                        "parameters": [],
                    }
                ],
                "checkpoint_id": "fe87f8c6",
                "checkpoint_stage": "s04_synthesis",
            },
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["explore_runtime"]["checkpoint_id"] == "fe87f8c6"
    assert payload["explore_runtime"]["checkpoint_stage"] == "s04_synthesis"
    assert persisted[-1]["explore_runtime"]["checkpoint_id"] == "fe87f8c6"
    assert persisted[-1]["explore_runtime"]["checkpoint_stage"] == "s04_synthesis"


def test_refine_route_passes_full_invocable_set_to_worker_while_targeting_subset(monkeypatch) -> None:
    import api.routes.main as main
    import api.infra.storage as storage

    persisted: list[dict] = []
    thread_args: list[tuple] = []

    class _DummyThread:
        def __init__(self, *args, **kwargs) -> None:
            thread_args.append(tuple(kwargs.get("args") or ()))

        def start(self) -> None:
            return None

    inv_map = {
        "WF_OpenFulfillment": {"name": "WF_OpenFulfillment", "parameters": []},
        "WF_GetWorkflowNonce": {"name": "WF_GetWorkflowNonce", "parameters": []},
        "WF_ConfirmWorkflow": {"name": "WF_ConfirmWorkflow", "parameters": []},
    }

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(main.threading, "Thread", _DummyThread)
    monkeypatch.setattr(main, "_get_job_status", lambda job_id: {"job_id": job_id, "status": "done"})
    monkeypatch.setattr(
        main,
        "_persist_job_status",
        lambda job_id, payload, sync=False: persisted.append(payload),
    )
    monkeypatch.setattr(storage, "_patch_finding", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "get_invocables_map", lambda job_id: dict(inv_map))

    with TestClient(main.app) as client:
        response = client.post(
            "/api/jobs/job-2/refine",
            json={
                "target_functions": ["WF_GetWorkflowNonce", "WF_ConfirmWorkflow"],
                "checkpoint_id": "job-2-checkpoint",
            },
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["target_functions"] == ["WF_GetWorkflowNonce", "WF_ConfirmWorkflow"]
    assert persisted[-1]["explore_runtime"]["checkpoint_id"] == "job-2-checkpoint"
    assert thread_args
    job_id, worker_invocables = thread_args[-1]
    assert job_id == "job-2"
    assert {inv["name"] for inv in worker_invocables} == set(inv_map)


def test_explore_route_defaults_repeat_investigation_to_cluster_seed(monkeypatch) -> None:
    import api.routes.main as main

    persisted: list[dict] = []

    class _DummyThread:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        def start(self) -> None:
            return None

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(main.threading, "Thread", _DummyThread)
    monkeypatch.setattr(main, "_get_job_status", lambda job_id: {"job_id": job_id, "status": "done"})
    monkeypatch.setattr(
        main,
        "_persist_job_status",
        lambda job_id, payload, sync=False: persisted.append(payload),
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/jobs/job-3/explore",
            json={
                "invocables": [
                    {
                        "name": "PR_GetQuoteState",
                        "execution": {"method": "dll_import"},
                        "parameters": [],
                    }
                ],
                "prior_job_id": "26ddca42",
                "focus_functions": ["PR_GetQuoteState", "PR_SealQuote"],
            },
        )

    assert response.status_code == 202
    runtime = response.json()["explore_runtime"]
    assert runtime["checkpoint_id"] == "26ddca42"
    assert runtime["checkpoint_stage"] == "s02_probe"
    assert runtime["cluster_checkpoint_id"] == "pricing_quote_lifecycle"
    assert runtime["seed_strategy"] == "default_cluster_seed"
    assert runtime["seed_default_applied"] is True
    assert persisted[-1]["explore_runtime"]["cluster_checkpoint_id"] == "pricing_quote_lifecycle"


def test_explore_route_preserves_chain_step_scope_fields(monkeypatch) -> None:
    import api.routes.main as main

    persisted: list[dict] = []

    class _DummyThread:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        def start(self) -> None:
            return None

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(main.threading, "Thread", _DummyThread)
    monkeypatch.setattr(main, "_get_job_status", lambda job_id: {"job_id": job_id, "status": "done"})
    monkeypatch.setattr(
        main,
        "_persist_job_status",
        lambda job_id, payload, sync=False: persisted.append(payload),
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/jobs/job-4/explore",
            json={
                "invocables": [
                    {
                        "name": "SP_CommitRelease",
                        "execution": {"method": "dll_import"},
                        "parameters": [],
                    }
                ],
                "chain_step_target": "release_commit",
                "required_semantic_checkpoint": "SP_CommitRelease",
                "selected_invocable_names": ["SP_CommitRelease"],
            },
        )

    assert response.status_code == 202
    runtime = response.json()["explore_runtime"]
    assert runtime["chain_step_target"] == "release_commit"
    assert runtime["required_semantic_checkpoint"] == "SP_CommitRelease"
    assert runtime["selected_invocable_names"] == ["SP_CommitRelease"]
    assert persisted[-1]["explore_runtime"]["required_semantic_checkpoint"] == "SP_CommitRelease"


def test_answer_gaps_route_uses_public_invocables_map(monkeypatch) -> None:
    import api.routes.main as main

    persisted: list[dict] = []
    thread_args: list[tuple] = []

    class _DummyThread:
        def __init__(self, *args, **kwargs) -> None:
            thread_args.append(tuple(kwargs.get("args") or ()))

        def start(self) -> None:
            return None

    inv_map = {
        "WF_OpenFulfillment": {"name": "WF_OpenFulfillment", "parameters": []},
        "WF_ConfirmWorkflow": {"name": "WF_ConfirmWorkflow", "parameters": []},
    }

    def _blob_miss(*args, **kwargs):
        raise FileNotFoundError("vocab.json")

    monkeypatch.setattr(main, "_queue_worker_loop", lambda: None)
    monkeypatch.setattr(main, "_local_startup_probe", lambda: None)
    monkeypatch.setattr(main, "PIPELINE_API_KEY", "")
    monkeypatch.setattr(main.threading, "Thread", _DummyThread)
    monkeypatch.setattr(
        main,
        "_get_job_status",
        lambda job_id: {
            "job_id": job_id,
            "status": "done",
            "explore_runtime": {"gap_resolution_enabled": True},
        },
    )
    monkeypatch.setattr(
        main,
        "_persist_job_status",
        lambda job_id, payload, sync=False: persisted.append(payload),
    )
    monkeypatch.setattr(main, "_download_blob", _blob_miss)
    monkeypatch.setattr(main, "_upload_to_blob", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "get_invocables_map", lambda job_id: dict(inv_map))

    with TestClient(main.app) as client:
        response = client.post(
            "/api/jobs/job-5/answer-gaps",
            json={
                "answers": [
                    {"function": "WF_ConfirmWorkflow", "answer": "Use the workflow nonce"}
                ]
            },
        )

    assert response.status_code == 202
    assert response.json()["status"] == "re_exploring"
    assert persisted
    assert persisted[-1]["explore_questions"] == []
    assert thread_args
    job_id, worker_invocables = thread_args[-1]
    assert job_id == "job-5"
    assert {inv["name"] for inv in worker_invocables} == set(inv_map)
