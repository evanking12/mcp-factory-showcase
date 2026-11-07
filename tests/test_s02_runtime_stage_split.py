from __future__ import annotations

import importlib
from types import SimpleNamespace


def test_run_s02_preserves_legacy_entrypoint_order(monkeypatch) -> None:
    module = importlib.import_module("api.pipeline.s02_probe")
    calls: list[str] = []

    monkeypatch.setattr(module, "run_probe_ordering", lambda _ctx: calls.append("ordering"))
    monkeypatch.setattr(module, "run_invocation_execution", lambda _ctx: calls.append("execution"))
    monkeypatch.setattr(module, "run_evidence_capture", lambda _ctx: calls.append("capture"))

    module.run_s02(SimpleNamespace())

    assert calls == ["ordering", "execution", "capture"]


def test_s02_substage_status_records_parent_and_labels(monkeypatch) -> None:
    status = importlib.import_module("api.pipeline.s02_probe.status")
    persisted: dict[str, object] = {}
    explore_statuses: list[tuple[str, str]] = []

    monkeypatch.setattr(status, "_get_job_status", lambda _job_id: {"existing": True})
    monkeypatch.setattr(status, "_persist_job_status", lambda _job_id, payload: persisted.update(payload))
    monkeypatch.setattr(
        status,
        "_set_explore_status",
        lambda _job_id, _explored, _total, message, *, stage="": explore_statuses.append((stage, message)),
    )

    ctx = SimpleNamespace(job_id="job-s02", total=3, explored_count=lambda: 1)

    status.emit_s02_substage_status(
        ctx,
        "s02_invocation_execution",
        "S-02B: Executing probe invocations...",
        state="start",
    )

    assert explore_statuses == [
        ("s02_invocation_execution", "S-02B: Executing probe invocations...")
    ]
    assert persisted["explore_parent_stage"] == "s02_probe"
    assert persisted["explore_substage"] == "s02_invocation_execution"
    assert persisted["explore_substage_state"] == "start"
    assert persisted["explore_substage_label"] == "S-02B invocation_execution"
    substage = persisted["s02_substage_status"]["s02_invocation_execution"]
    assert substage["parent_stage"] == "s02_probe"
    assert substage["short_name"] == "invocation_execution"
