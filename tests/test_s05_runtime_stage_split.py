from __future__ import annotations

import importlib
from types import SimpleNamespace


def test_run_s05_preserves_legacy_entrypoint_order(monkeypatch) -> None:
    module = importlib.import_module("api.pipeline.s05_enrichment")
    calls: list[str] = []

    monkeypatch.setattr(module, "run_schema_backfill", lambda _ctx, _report: calls.append("backfill"))
    monkeypatch.setattr(module, "run_verification_replay", lambda _ctx: calls.append("verify"))
    monkeypatch.setattr(module, "run_read_to_write_chaining", lambda _ctx: calls.append("chain"))

    module.run_s05(SimpleNamespace(), "api reference")

    assert calls == ["backfill", "verify", "chain"]


def test_s05_stage_status_records_parent_and_labels(monkeypatch) -> None:
    status = importlib.import_module("api.pipeline.s05_enrichment.status")
    persisted: dict[str, object] = {}
    explore_statuses: list[tuple[str, str]] = []

    monkeypatch.setattr(status, "_get_job_status", lambda _job_id: {"existing": True})
    monkeypatch.setattr(status, "_persist_job_status", lambda _job_id, payload: persisted.update(payload))
    monkeypatch.setattr(
        status,
        "_set_explore_status",
        lambda _job_id, _explored, _total, message, *, stage="": explore_statuses.append((stage, message)),
    )

    ctx = SimpleNamespace(job_id="job-s05", total=3, explored_count=lambda: 1)

    status.emit_s05_stage_status(
        ctx,
        "s05_verification_replay",
        "S-05B: Replaying verification evidence...",
        state="start",
    )

    assert explore_statuses == [
        ("s05_verification_replay", "S-05B: Replaying verification evidence...")
    ]
    assert persisted["explore_parent_stage"] == "s05_enrichment"
    assert persisted["explore_substage"] == "s05_verification_replay"
    assert persisted["explore_substage_state"] == "start"
    assert persisted["explore_substage_label"] == "S-05B verification_replay"
    stage = persisted["s05_stage_status"]["s05_verification_replay"]
    assert stage["parent_stage"] == "s05_enrichment"
    assert stage["short_name"] == "verification_replay"


def test_s05_runtime_aliases_are_declared() -> None:
    artifacts = importlib.import_module("api.pipeline.s05_enrichment.session_artifacts")

    assert artifacts.FUTURE_RUNTIME_ALIASES == {
        "evidence/stage-05a-schema-backfill/backfill-report.json": "backfill_result.json",
        "evidence/stage-05a-schema-backfill/schema-post-backfill.json": "mcp_schema_post_discovery.json",
        "evidence/stage-05b-verification-replay/verification-report.json": "verification-report.json",
        "evidence/stage-05c-read-to-write-chaining/mc5-post-verification.json": "mc-decisions/mc5-post-verification.json",
    }
