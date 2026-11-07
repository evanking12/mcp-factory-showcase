from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.pipeline.s07_finalize import run_s07


def test_run_s07_emits_contract_artifacts_synchronously(monkeypatch) -> None:
    calls: list[str] = []
    spans: list[tuple[str, str, str]] = []

    monkeypatch.setattr(
        "api.pipeline.s07_finalize._run_phase_10_harmonize",
        lambda ctx: calls.append(f"harmonize:{ctx.job_id}"),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize._run_finalize",
        lambda ctx: calls.append(f"finalize:{ctx.job_id}"),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize._emit_contract_artifacts_with_timeout",
        lambda job_id, _timeout_sec: calls.append(f"emit:{job_id}"),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize._record_contract_artifact_span",
        lambda job_id, state, message: spans.append((job_id, state, message)),
    )

    ctx = SimpleNamespace(job_id="job-s07")
    run_s07(ctx)

    assert calls == ["harmonize:job-s07", "finalize:job-s07", "emit:job-s07"]
    assert spans[0][1] == "start"
    assert spans[-1][1] == "done"


def test_run_s07_propagates_contract_emission_failure(monkeypatch) -> None:
    monkeypatch.setattr("api.pipeline.s07_finalize._run_phase_10_harmonize", lambda ctx: None)
    monkeypatch.setattr("api.pipeline.s07_finalize._run_finalize", lambda ctx: None)
    monkeypatch.setattr(
        "api.pipeline.s07_finalize._emit_contract_artifacts_with_timeout",
        lambda job_id, _timeout_sec: (_ for _ in ()).throw(RuntimeError("emit failed")),
    )

    ctx = SimpleNamespace(job_id="job-s07")
    with pytest.raises(RuntimeError, match="emit failed"):
        run_s07(ctx)


def test_run_s07_bounds_contract_emission_timeout(monkeypatch) -> None:
    import api.pipeline.s07_finalize as finalize

    monkeypatch.setattr(finalize, "_run_phase_10_harmonize", lambda ctx: None)
    monkeypatch.setattr(finalize, "_run_finalize", lambda ctx: None)
    monkeypatch.setattr(finalize, "_contract_artifact_timeout_sec", lambda: 0.01)
    monkeypatch.setattr(finalize, "_record_contract_artifact_span", lambda *_args, **_kwargs: None)

    monkeypatch.setattr(
        finalize,
        "_emit_contract_artifacts_with_timeout",
        lambda _job_id, _timeout_sec: (_ for _ in ()).throw(TimeoutError("s07_emit_contract_artifacts_timeout")),
    )

    with pytest.raises(TimeoutError, match="s07_emit_contract_artifacts_timeout"):
        finalize.run_s07(SimpleNamespace(job_id="job-s07-timeout"))


def test_s07_contract_emission_returns_artifact_keys(monkeypatch) -> None:
    import api.pipeline.s07_finalize as finalize

    monkeypatch.setattr(
        finalize,
        "_run_contract_artifact_subprocess",
        lambda _job_id, _timeout_sec: {
            "returncode": 0,
            "stdout": '{"ok": true, "keys": ["stage_index", "transition_index"]}\n',
            "stderr": "",
            "recovered_after_timeout": False,
        },
    )

    result = finalize._emit_contract_artifacts_with_timeout("job-s07", 30)

    assert result["returncode"] == 0
    assert result["keys"] == ["stage_index", "transition_index"]
    assert result["recovered_after_timeout"] is False


def test_s07_contract_emission_failure_fails_closed(monkeypatch) -> None:
    import api.pipeline.s07_finalize as finalize

    monkeypatch.setattr(
        finalize,
        "_run_contract_artifact_subprocess",
        lambda _job_id, _timeout_sec: {
            "returncode": 2,
            "stdout": "",
            "stderr": "contract failure",
            "recovered_after_timeout": False,
        },
    )

    with pytest.raises(RuntimeError, match="s07_emit_contract_artifacts_failed"):
        finalize._emit_contract_artifacts_with_timeout("job-s07", 30)


def test_s07_contract_emission_timeout_fails_closed(monkeypatch) -> None:
    import api.pipeline.s07_finalize as finalize

    def timeout(_job_id, _timeout_sec):
        raise TimeoutError("s07_emit_contract_artifacts_timeout")

    monkeypatch.setattr(finalize, "_run_contract_artifact_subprocess", timeout)

    with pytest.raises(TimeoutError, match="s07_emit_contract_artifacts_timeout"):
        finalize._emit_contract_artifacts_with_timeout("job-s07", 0.01)


def test_s07_contract_emission_uses_process_group_on_windows(monkeypatch) -> None:
    import api.pipeline.s07_finalize as finalize

    calls: list[dict] = []

    class FakeProcess:
        returncode = 0

        def poll(self):
            return 0

        def communicate(self, timeout=None):
            return '{"ok": true, "keys": []}\n', ""

    def fake_popen(*args, **kwargs):
        calls.append(dict(kwargs))
        return FakeProcess()

    monkeypatch.setattr(finalize.os, "name", "nt")
    monkeypatch.setattr(finalize.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
    monkeypatch.setattr(finalize.subprocess, "Popen", fake_popen)

    finalize._emit_contract_artifacts_with_timeout("job-s07", 30)

    assert calls
    assert calls[0]["creationflags"] == 512


def test_s07_contract_emission_recovers_when_child_hangs_after_artifacts(monkeypatch) -> None:
    import api.pipeline.s07_finalize as finalize

    killed: list[bool] = []

    class HangingProcess:
        returncode = None

        def poll(self):
            return None

        def kill(self):
            killed.append(True)

    monkeypatch.setattr(finalize, "_start_contract_artifact_subprocess", lambda _job_id: HangingProcess())
    monkeypatch.setattr(finalize, "_contract_artifacts_present", lambda _job_id: True)

    result = finalize._emit_contract_artifacts_with_timeout("job-s07", 0.01)

    assert result["returncode"] == 0
    assert result["recovered_after_timeout"] is True
    assert result["recovered_without_child_return"] is True
    assert sorted(result["keys"]) == sorted(finalize.REQUIRED_CONTRACT_ARTIFACTS)
    assert killed == [True]


def test_s07_bounded_blob_download_times_out(monkeypatch) -> None:
    from api.pipeline.s07_finalize import harmonize

    def slow_download(*_args, **_kwargs):
        harmonize.time.sleep(0.05)
        return b"late"

    monkeypatch.setattr(harmonize, "_download_blob", slow_download)

    with pytest.raises(TimeoutError, match="s07 schema evolution read exceeded"):
        harmonize._download_blob_bounded("artifacts", "job/blob.json", timeout_sec=0.01)


def test_s07_bounded_blob_download_returns_payload(monkeypatch) -> None:
    from api.pipeline.s07_finalize import harmonize

    monkeypatch.setattr(harmonize, "_download_blob", lambda *_args, **_kwargs: b"ok")

    assert harmonize._download_blob_bounded("artifacts", "job/blob.json", timeout_sec=0.1) == b"ok"


def test_s07_bounded_findings_load_times_out(monkeypatch) -> None:
    from api.pipeline.s07_finalize import harmonize

    def slow_load(_job_id):
        harmonize.time.sleep(0.05)
        return []

    monkeypatch.setattr(harmonize, "_load_findings", slow_load)

    with pytest.raises(TimeoutError, match="s07 findings load exceeded"):
        harmonize._load_findings_bounded("job-s07", timeout_sec=0.01)


def test_s07_span_status_is_diagnostic_non_blocking(monkeypatch) -> None:
    from api.pipeline.s07_finalize import harmonize

    writes: list[tuple[bool, dict]] = []
    monkeypatch.setattr(harmonize, "_get_job_status", lambda _job_id: {"status": "running"})
    monkeypatch.setattr(
        harmonize,
        "_persist_job_status",
        lambda _job_id, payload, *, sync=True: writes.append((sync, dict(payload))) or True,
    )

    harmonize._set_s07_span_status(SimpleNamespace(job_id="job-s07", total=1, explored_count=lambda: 1), "span", "done", "ok")

    assert writes
    assert writes[0][0] is False
    assert writes[0][1]["explore_span"] == "span"


def test_s07_direct_truth_promotion_timeout_does_not_block_closeout(monkeypatch) -> None:
    from api.pipeline.s07_finalize import harmonize

    def slow_promotions(*_args, **_kwargs):
        harmonize.time.sleep(0.05)
        return [{"function": "late"}]

    monkeypatch.setattr(harmonize, "_evaluate_direct_truth_promotions", slow_promotions)

    upgrades, completed = harmonize._evaluate_direct_truth_promotions_bounded(
        SimpleNamespace(job_id="job-s07"),
        [],
        {},
        timeout_sec=0.01,
    )

    assert upgrades == []
    assert completed is False


def test_final_worker_verdict_bounded_persists_terminal_status(monkeypatch) -> None:
    import api.pipeline.runner as runner

    writes: list[tuple[bool, dict]] = []
    authority_packets: list[dict] = []
    monkeypatch.setattr(runner, "_get_job_status", lambda _job_id: {"status": "running"})
    monkeypatch.setattr(
        runner,
        "_persist_job_status",
        lambda _job_id, payload, *, sync=True: writes.append((sync, dict(payload))) or True,
    )
    monkeypatch.setattr(
        runner,
        "_verify_final_worker_status_persisted",
        lambda job_id: {
            "status_blob": f"{job_id}/status.json",
            "status_sha256": "fed789",
            "status_bytes": 112,
            "terminal_status": "done",
            "predecessor_verdict_blob": f"{job_id}/macro_verdict.json",
            "predecessor_verdict_sha256": "def456",
            "predecessor_verdict_status": "done",
            "predecessor_authority_blob": f"{job_id}/macro_verdict_persist_authority.json",
            "predecessor_authority_sha256": "abc123",
        },
    )
    monkeypatch.setattr(
        runner,
        "_persist_final_status_authority",
        lambda _job_id, **fields: authority_packets.append(dict(fields)),
    )

    assert runner._finalize_worker_verdict_bounded("job-final", SimpleNamespace(total=7), "done", 100) == {
        "status_blob": "job-final/status.json",
        "status_sha256": "fed789",
        "status_bytes": 112,
        "terminal_status": "done",
        "predecessor_verdict_blob": "job-final/macro_verdict.json",
        "predecessor_verdict_sha256": "def456",
        "predecessor_verdict_status": "done",
        "predecessor_authority_blob": "job-final/macro_verdict_persist_authority.json",
        "predecessor_authority_sha256": "abc123",
    }
    assert writes == [
        (
            True,
            {
                "status": "done",
                "explore_phase": "done",
                "explore_stage": "done",
                "explore_progress": "7/7",
                "explore_message": "Complete â€” done (100% coverage)",
                "updated_at": writes[0][1]["updated_at"],
            },
        )
    ]
    assert authority_packets == [
        {
            "state": "returned",
            "status_blob": "job-final/status.json",
            "status_sha256": "fed789",
            "status_bytes": 112,
            "terminal_status": "done",
            "predecessor_verdict_blob": "job-final/macro_verdict.json",
            "predecessor_verdict_sha256": "def456",
            "predecessor_verdict_status": "done",
            "predecessor_authority_blob": "job-final/macro_verdict_persist_authority.json",
            "predecessor_authority_sha256": "abc123",
        }
    ]


def test_final_worker_verdict_bounded_timeout_defers_terminal_status(monkeypatch) -> None:
    import api.pipeline.runner as runner

    writes: list[tuple[bool, dict]] = []
    close_steps: list[str] = []
    authority_packets: list[dict] = []
    monkeypatch.setattr(runner, "_FINAL_WORKER_VERDICT_PERSIST_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(runner, "_get_job_status", lambda _job_id: {"status": "running"})
    monkeypatch.setattr(
        runner,
        "_persist_final_status_authority",
        lambda _job_id, **fields: authority_packets.append(dict(fields)),
    )
    monkeypatch.setattr(
        runner,
        "_record_worker_close_step_sync",
        lambda _job_id, step, **_fields: close_steps.append(step),
    )

    def persist(_job_id, payload, *, sync=True):
        if sync:
            runner.time.sleep(0.05)
        writes.append((sync, dict(payload)))
        return True

    monkeypatch.setattr(runner, "_persist_job_status", persist)

    assert runner._finalize_worker_verdict_bounded("job-final", SimpleNamespace(total=7), "done", 100) is None
    assert "final_worker_verdict_persist_timeout" in close_steps
    assert any(not sync and payload["status"] == "done" for sync, payload in writes)
    assert authority_packets == [
        {
            "state": "timeout",
            "terminal_status": "done",
            "error": "final_worker_verdict_persist_timeout",
        }
    ]


def test_final_worker_verdict_bounded_fails_when_terminal_status_not_verified(monkeypatch) -> None:
    import api.pipeline.runner as runner

    authority_packets: list[dict] = []
    close_steps: list[tuple[str, dict]] = []
    monkeypatch.setattr(runner, "_get_job_status", lambda _job_id: {"status": "running"})
    monkeypatch.setattr(runner, "_persist_job_status", lambda _job_id, _payload, *, sync=True: True)
    monkeypatch.setattr(
        runner,
        "_verify_final_worker_status_persisted",
        lambda _job_id: (_ for _ in ()).throw(RuntimeError("final_status_persist_missing_or_nonterminal")),
    )
    monkeypatch.setattr(
        runner,
        "_persist_final_status_authority",
        lambda _job_id, **fields: authority_packets.append(dict(fields)),
    )
    monkeypatch.setattr(
        runner,
        "_record_worker_close_step_sync",
        lambda _job_id, step, **fields: close_steps.append((step, dict(fields))),
    )

    result = runner._finalize_worker_verdict_bounded("job-final", SimpleNamespace(total=7), "done", 100)

    assert result is None
    assert close_steps == [
        ("final_worker_verdict_persist_failed", {"error": "final_status_persist_missing_or_nonterminal"})
    ]
    assert authority_packets == [
        {
            "state": "failed",
            "terminal_status": "done",
            "error": "final_status_persist_missing_or_nonterminal",
        }
    ]


def test_s07_checkpoint_save_bounded_records_timeout(monkeypatch) -> None:
    import api.pipeline.runner as runner

    close_steps: list[str] = []
    progress_writes: list[dict] = []
    monkeypatch.setattr(runner, "_S07_CHECKPOINT_SAVE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(runner, "save_checkpoint", lambda _checkpoint, **_kwargs: runner.time.sleep(0.05))
    monkeypatch.setattr(runner, "_persist_s07_checkpoint_save_authority", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runner,
        "_record_worker_close_step_sync",
        lambda _job_id, step, **_fields: close_steps.append(step),
    )
    monkeypatch.setattr(runner, "_get_job_status", lambda _job_id: {"status": "running"})
    monkeypatch.setattr(
        runner,
        "_persist_job_status",
        lambda _job_id, payload, *, sync=False: progress_writes.append(dict(payload)) or True,
    )

    assert not runner._save_s07_checkpoint_bounded("job-s07", object())
    assert "s07_checkpoint_save_timeout" in close_steps
    assert progress_writes[-1]["explore_span"] == "s07_checkpoint_save"
    assert progress_writes[-1]["explore_span_state"] == "timeout"


def test_s07_checkpoint_save_bounded_returns_success(monkeypatch) -> None:
    import api.pipeline.runner as runner

    calls: list[object] = []
    kwargs_seen: list[dict] = []
    monkeypatch.setattr(
        runner,
        "save_checkpoint",
        lambda checkpoint, **kwargs: calls.append(checkpoint) or kwargs_seen.append(dict(kwargs)),
    )
    monkeypatch.setattr(
        runner,
        "_verify_s07_checkpoint_save_returned",
        lambda job_id: {
            "checkpoint_blob": f"{job_id}/checkpoints/s07_finalize.json",
            "checkpoint_sha256": "abc123",
            "checkpoint_bytes": 42,
        },
    )
    authority_packets: list[dict] = []
    monkeypatch.setattr(
        runner,
        "_persist_s07_checkpoint_save_authority",
        lambda _job_id, **fields: authority_packets.append(dict(fields)),
    )

    checkpoint = object()
    result = runner._save_s07_checkpoint_bounded("job-s07", checkpoint)
    assert result == {
        "checkpoint_blob": "job-s07/checkpoints/s07_finalize.json",
        "checkpoint_sha256": "abc123",
        "checkpoint_bytes": 42,
    }
    assert calls == [checkpoint]
    assert kwargs_seen == [{"write_stage_snapshots": False}]
    assert authority_packets == [
        {
            "state": "returned",
            "checkpoint_blob": "job-s07/checkpoints/s07_finalize.json",
            "checkpoint_sha256": "abc123",
            "checkpoint_bytes": 42,
        }
    ]


def test_s07_checkpoint_save_bounded_fails_when_stage_artifact_missing(monkeypatch) -> None:
    import api.pipeline.runner as runner

    close_steps: list[tuple[str, dict]] = []
    progress_writes: list[dict] = []
    authority_packets: list[dict] = []
    monkeypatch.setattr(runner, "save_checkpoint", lambda _checkpoint, **_kwargs: "job-s07/checkpoints/latest.json")
    monkeypatch.setattr(
        runner,
        "_verify_s07_checkpoint_save_returned",
        lambda _job_id: (_ for _ in ()).throw(RuntimeError("s07_checkpoint_save_missing_or_incomplete")),
    )
    monkeypatch.setattr(
        runner,
        "_persist_s07_checkpoint_save_authority",
        lambda _job_id, **fields: authority_packets.append(dict(fields)),
    )
    monkeypatch.setattr(
        runner,
        "_record_worker_close_step_sync",
        lambda _job_id, step, **fields: close_steps.append((step, dict(fields))),
    )
    monkeypatch.setattr(runner, "_get_job_status", lambda _job_id: {"status": "running"})
    monkeypatch.setattr(
        runner,
        "_persist_job_status",
        lambda _job_id, payload, *, sync=False: progress_writes.append(dict(payload)) or True,
    )

    assert runner._save_s07_checkpoint_bounded("job-s07", object()) is None
    assert close_steps == [
        ("s07_checkpoint_save_failed", {"error": "s07_checkpoint_save_missing_or_incomplete"})
    ]
    assert authority_packets == [
        {"state": "failed", "error": "s07_checkpoint_save_missing_or_incomplete"}
    ]
    assert progress_writes[-1]["explore_span"] == "s07_checkpoint_save"
    assert progress_writes[-1]["explore_span_state"] == "fail"


def test_s07_macro_verdict_persist_bounded_returns_verified_authority(monkeypatch) -> None:
    import api.pipeline.runner as runner

    persisted: list[str] = []
    authority_packets: list[dict] = []
    monkeypatch.setattr(
        runner,
        "_persist_verdict",
        lambda ctx, _verdict: persisted.append(ctx.job_id),
    )
    monkeypatch.setattr(
        runner,
        "_verify_macro_verdict_persisted",
        lambda _ctx, _verdict: {
            "verdict_blob": "job-s07/macro_verdict.json",
            "verdict_sha256": "def456",
            "verdict_bytes": 54,
            "verdict_status": "done",
        },
    )
    monkeypatch.setattr(
        runner,
        "_persist_macro_verdict_authority",
        lambda _job_id, **fields: authority_packets.append(dict(fields)),
    )

    result = runner._persist_macro_verdict_bounded(
        SimpleNamespace(job_id="job-s07"),
        runner.RunVerdict(status="done"),
    )

    assert result == {
        "verdict_blob": "job-s07/macro_verdict.json",
        "verdict_sha256": "def456",
        "verdict_bytes": 54,
        "verdict_status": "done",
    }
    assert persisted == ["job-s07"]
    assert authority_packets == [
        {
            "state": "returned",
            "verdict_blob": "job-s07/macro_verdict.json",
            "verdict_sha256": "def456",
            "verdict_bytes": 54,
            "verdict_status": "done",
        }
    ]


def test_s07_macro_verdict_persist_bounded_fails_when_verification_missing(monkeypatch) -> None:
    import api.pipeline.runner as runner

    authority_packets: list[dict] = []
    monkeypatch.setattr(runner, "_persist_verdict", lambda _ctx, _verdict: None)
    monkeypatch.setattr(
        runner,
        "_verify_macro_verdict_persisted",
        lambda _ctx, _verdict: (_ for _ in ()).throw(RuntimeError("macro_verdict_persist_missing_or_mismatched")),
    )
    monkeypatch.setattr(
        runner,
        "_persist_macro_verdict_authority",
        lambda _job_id, **fields: authority_packets.append(dict(fields)),
    )

    result = runner._persist_macro_verdict_bounded(
        SimpleNamespace(job_id="job-s07"),
        runner.RunVerdict(status="done"),
    )

    assert result is None
    assert authority_packets == [
        {
            "state": "failed",
            "verdict_status": "done",
            "error": "macro_verdict_persist_missing_or_mismatched",
        }
    ]


def test_s07_macro_verdict_persist_bounded_records_timeout(monkeypatch) -> None:
    import api.pipeline.runner as runner

    authority_packets: list[dict] = []

    def slow_persist(_ctx, _verdict):
        runner.time.sleep(0.05)

    monkeypatch.setattr(runner, "_persist_verdict", slow_persist)
    monkeypatch.setattr(runner, "_persist_macro_verdict_authority", lambda _job_id, **fields: authority_packets.append(dict(fields)))

    result = runner._persist_macro_verdict_bounded(
        SimpleNamespace(job_id="job-s07"),
        runner.RunVerdict(status="done"),
        timeout_s=0.01,
    )

    assert result is None
    assert authority_packets == [
        {
            "state": "timeout",
            "verdict_status": "done",
            "error": "macro_verdict_persist_timeout",
        }
    ]
