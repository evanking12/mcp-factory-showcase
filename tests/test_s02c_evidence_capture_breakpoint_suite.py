from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from api.pipeline.s02_probe import evidence_capture
from api.pipeline.s02_probe import status as s02_status


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-s02c-probe-log-durability-tier1",
        total=1,
        explored_count=lambda: 1,
        sentinels={},
        sentinel_new_codes_this_run=0,
        client=object(),
        model="no-model",
        unlock_result={"unlocked": False, "sequence": []},
        invocables=[],
        dll_strings={},
        vocab={},
    )


def _install_status_capture(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    statuses: list[dict[str, object]] = []
    monkeypatch.setattr(s02_status, "_get_job_status", lambda _job_id: {})
    monkeypatch.setattr(s02_status, "_persist_job_status", lambda _job_id, payload: statuses.append(dict(payload)))
    monkeypatch.setattr(s02_status, "_set_explore_status", lambda *_args, **_kwargs: None)
    return statuses


def test_s02c_tier1_persists_probe_log_snapshot_without_rewriting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 1 anchor: S-02C preserves one S-02B-shaped raw observation durably."""
    ctx = _ctx()
    statuses = _install_status_capture(monkeypatch)
    raw_observation = {
        "phase": "deterministic_fallback",
        "function": "S02B_StatusOk",
        "tool": "S02B_StatusOk",
        "args": {"operator_id": "OP-1001"},
        "result_excerpt": "Returned: 0",
        "classification": {"status": "observed", "boundary": "raw_execution"},
        "trace": {
            "backend": "dll",
            "function_name": "S02B_StatusOk",
            "raw_result": 0,
            "dll_path": "C:/fixtures/s02b_invocation_raw_observation_tier1.dll",
        },
    }
    uploads: dict[str, object] = {}

    def fake_download(_container: str, blob_name: str) -> bytes:
        assert blob_name == f"{ctx.job_id}/explore_probe_log.json"
        return json.dumps([raw_observation]).encode("utf-8")

    def fake_upload(_container: str, blob_name: str, data: bytes) -> str:
        uploads[blob_name] = json.loads(data.decode("utf-8"))
        return blob_name

    monkeypatch.setattr(evidence_capture, "_download_blob", fake_download)
    monkeypatch.setattr(evidence_capture, "_upload_to_blob", fake_upload)
    monkeypatch.setattr(
        evidence_capture,
        "_name_sentinel_candidates",
        lambda *_args, **_kwargs: pytest.fail("easy Tier 1 case should not trigger recalibration"),
    )
    monkeypatch.setattr(
        evidence_capture,
        "_probe_write_unlock",
        lambda *_args, **_kwargs: pytest.fail("easy Tier 1 case should not re-probe unlock"),
    )

    evidence_capture.run_evidence_capture(ctx)

    substage_states = [
        row.get("s02_substage_status", {}).get("s02_evidence_capture", {}).get("state")
        for row in statuses
    ]
    assert substage_states == ["start", "done"]

    alias_blob = f"{ctx.job_id}/{evidence_capture.S02C_PROBE_LOG_ALIAS}"
    status_blob = f"{ctx.job_id}/{evidence_capture.S02C_FINDING_STATUS_ALIAS}"
    assert alias_blob in uploads
    assert status_blob in uploads
    persisted_rows = uploads[alias_blob]
    assert persisted_rows == [raw_observation]
    persisted = persisted_rows[0]
    assert persisted["function"] == "S02B_StatusOk"
    assert persisted["args"] == {"operator_id": "OP-1001"}
    assert persisted["result_excerpt"] == "Returned: 0"
    assert persisted["trace"]["backend"] == "dll"
    assert persisted["trace"]["function_name"] == "S02B_StatusOk"
    assert persisted["trace"]["raw_result"] == 0
    assert persisted["classification"] == {"status": "observed", "boundary": "raw_execution"}
    assert uploads[status_blob] == [
        {
            "index": 0,
            "function": "S02B_StatusOk",
            "tool": "S02B_StatusOk",
            "status": "observed",
            "boundary": "raw_execution",
            "classification": {"status": "observed", "boundary": "raw_execution"},
            "args": {"operator_id": "OP-1001"},
            "result_excerpt": "Returned: 0",
            "phase": "deterministic_fallback",
            "trace": raw_observation["trace"],
        }
    ]


def test_s02c_tier2_persists_multiple_probe_log_rows_without_rewriting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 2 anchor: S-02C preserves multiple S-02B-shaped rows under medium pressure."""
    ctx = _ctx()
    ctx.job_id = "job-s02c-probe-log-durability-tier2"
    statuses = _install_status_capture(monkeypatch)
    raw_observations = [
        {
            "phase": "deterministic_fallback",
            "function": "S02B_T2_StatusOk",
            "tool": "S02B_T2_StatusOk",
            "args": {},
            "result_excerpt": "Returned: 0",
            "classification": {"status": "observed", "boundary": "raw_execution"},
            "trace": {
                "backend": "dll",
                "function_name": "S02B_T2_StatusOk",
                "raw_result": 0,
                "c_args_count": 0,
            },
        },
        {
            "phase": "deterministic_fallback",
            "function": "S02B_T2_StatusBlocked",
            "tool": "S02B_T2_StatusBlocked",
            "args": {},
            "result_excerpt": "Returned: -5",
            "classification": {"status": "blocked", "boundary": "raw_execution"},
            "trace": {
                "backend": "dll",
                "function_name": "S02B_T2_StatusBlocked",
                "raw_result": -5,
                "c_args_count": 0,
            },
        },
        {
            "phase": "deterministic_fallback",
            "function": "S02B_T2_StatusWarning",
            "tool": "S02B_T2_StatusWarning",
            "args": {},
            "result_excerpt": "Returned: 7",
            "classification": {"status": "warning", "boundary": "raw_execution"},
            "trace": {
                "backend": "dll",
                "function_name": "S02B_T2_StatusWarning",
                "raw_result": 7,
                "c_args_count": 0,
            },
        },
        {
            "phase": "deterministic_fallback",
            "function": "S02B_T2_StateCounter",
            "tool": "S02B_T2_StateCounter",
            "args": {},
            "result_excerpt": "Returned: 1",
            "classification": {"status": "observed", "boundary": "raw_execution"},
            "trace": {
                "backend": "dll",
                "function_name": "S02B_T2_StateCounter",
                "raw_result": 1,
                "c_args_count": 0,
            },
        },
        {
            "phase": "deterministic_fallback",
            "function": "S02B_T2_EchoInt",
            "tool": "S02B_T2_EchoInt",
            "args": {"value": 10},
            "result_excerpt": "Returned: 110",
            "classification": {"status": "observed", "boundary": "raw_execution"},
            "trace": {
                "backend": "dll",
                "function_name": "S02B_T2_EchoInt",
                "raw_result": 110,
                "c_args_count": 1,
            },
        },
    ]
    uploads: dict[str, object] = {}

    def fake_download(_container: str, blob_name: str) -> bytes:
        assert blob_name == f"{ctx.job_id}/explore_probe_log.json"
        return json.dumps(raw_observations).encode("utf-8")

    def fake_upload(_container: str, blob_name: str, data: bytes) -> str:
        uploads[blob_name] = json.loads(data.decode("utf-8"))
        return blob_name

    monkeypatch.setattr(evidence_capture, "_download_blob", fake_download)
    monkeypatch.setattr(evidence_capture, "_upload_to_blob", fake_upload)
    monkeypatch.setattr(
        evidence_capture,
        "_name_sentinel_candidates",
        lambda *_args, **_kwargs: pytest.fail("Tier 2 durability case should not trigger recalibration"),
    )
    monkeypatch.setattr(
        evidence_capture,
        "_probe_write_unlock",
        lambda *_args, **_kwargs: pytest.fail("Tier 2 durability case should not re-probe unlock"),
    )

    evidence_capture.run_evidence_capture(ctx)

    substage_states = [
        row.get("s02_substage_status", {}).get("s02_evidence_capture", {}).get("state")
        for row in statuses
    ]
    assert substage_states == ["start", "done"]

    alias_blob = f"{ctx.job_id}/{evidence_capture.S02C_PROBE_LOG_ALIAS}"
    status_blob = f"{ctx.job_id}/{evidence_capture.S02C_FINDING_STATUS_ALIAS}"
    assert alias_blob in uploads
    assert status_blob in uploads
    persisted_rows = uploads[alias_blob]
    assert persisted_rows == raw_observations
    assert [row["function"] for row in persisted_rows] == [row["function"] for row in raw_observations]
    for expected, persisted in zip(raw_observations, persisted_rows, strict=True):
        assert persisted["tool"] == expected["tool"]
        assert persisted["args"] == expected["args"]
        assert persisted["result_excerpt"] == expected["result_excerpt"]
        assert persisted["classification"] == expected["classification"]
        assert persisted["trace"]["backend"] == expected["trace"]["backend"]
        assert persisted["trace"]["function_name"] == expected["trace"]["function_name"]
        assert persisted["trace"]["raw_result"] == expected["trace"]["raw_result"]
        assert persisted["trace"]["c_args_count"] == expected["trace"]["c_args_count"]


def test_s02c_tier2_preserves_finding_status_distinctions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 2 anchor: S-02C keeps status distinctions reviewable."""
    ctx = _ctx()
    ctx.job_id = "job-s02c-finding-status-persistence-tier2"
    statuses = _install_status_capture(monkeypatch)
    raw_observations = [
        {
            "phase": "deterministic_fallback",
            "function": "S02C_StatusObserved",
            "tool": "S02C_StatusObserved",
            "args": {"value": 10},
            "result_excerpt": "Returned: 0",
            "classification": {"status": "observed", "boundary": "raw_execution"},
            "trace": {"backend": "dll", "function_name": "S02C_StatusObserved", "raw_result": 0},
        },
        {
            "phase": "deterministic_fallback",
            "function": "S02C_StatusBlocked",
            "tool": "S02C_StatusBlocked",
            "args": {"amount_cents": 2500},
            "result_excerpt": "Returned: -3",
            "classification": {"status": "blocked", "boundary": "raw_execution"},
            "trace": {"backend": "dll", "function_name": "S02C_StatusBlocked", "raw_result": -3},
        },
        {
            "phase": "deterministic_fallback",
            "function": "S02C_StatusAmbiguous",
            "tool": "S02C_StatusAmbiguous",
            "args": {},
            "result_excerpt": "Returned: 2147483647",
            "classification": {"status": "ambiguous", "boundary": "raw_execution"},
            "trace": {
                "backend": "dll",
                "function_name": "S02C_StatusAmbiguous",
                "raw_result": 2147483647,
            },
        },
        {
            "phase": "deterministic_fallback",
            "function": "S02C_StatusUnresolved",
            "tool": "S02C_StatusUnresolved",
            "args": {},
            "result_excerpt": "Exception: timeout",
            "classification": {"status": "unresolved", "boundary": "raw_execution"},
            "trace": {
                "backend": "deterministic_harness",
                "function_name": "S02C_StatusUnresolved",
                "raw_result": None,
            },
        },
    ]
    uploads: dict[str, object] = {}

    def fake_download(_container: str, blob_name: str) -> bytes:
        assert blob_name == f"{ctx.job_id}/explore_probe_log.json"
        return json.dumps(raw_observations).encode("utf-8")

    def fake_upload(_container: str, blob_name: str, data: bytes) -> str:
        uploads[blob_name] = json.loads(data.decode("utf-8"))
        return blob_name

    monkeypatch.setattr(evidence_capture, "_download_blob", fake_download)
    monkeypatch.setattr(evidence_capture, "_upload_to_blob", fake_upload)
    monkeypatch.setattr(evidence_capture, "_name_sentinel_candidates", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(evidence_capture, "_probe_write_unlock", lambda *_args, **_kwargs: None)

    evidence_capture.run_evidence_capture(ctx)

    substage_states = [
        row.get("s02_substage_status", {}).get("s02_evidence_capture", {}).get("state")
        for row in statuses
    ]
    assert substage_states == ["start", "done"]

    status_blob = f"{ctx.job_id}/{evidence_capture.S02C_FINDING_STATUS_ALIAS}"
    status_rows = uploads[status_blob]
    assert [row["status"] for row in status_rows] == [
        "observed",
        "blocked",
        "ambiguous",
        "unresolved",
    ]
    assert [row["boundary"] for row in status_rows] == ["raw_execution"] * 4
    assert [row["function"] for row in status_rows] == [
        "S02C_StatusObserved",
        "S02C_StatusBlocked",
        "S02C_StatusAmbiguous",
        "S02C_StatusUnresolved",
    ]
    assert status_rows[0]["args"] == {"value": 10}
    assert status_rows[1]["args"] == {"amount_cents": 2500}
    assert status_rows[2]["result_excerpt"] == "Returned: 2147483647"
    assert status_rows[3]["result_excerpt"] == "Exception: timeout"
    assert status_rows[3]["trace"]["backend"] == "deterministic_harness"
    assert uploads[f"{ctx.job_id}/{evidence_capture.S02C_PROBE_LOG_ALIAS}"] == raw_observations


def test_s02c_probe_log_snapshot_degrades_safely_when_source_log_is_malformed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _ctx()
    _install_status_capture(monkeypatch)
    uploads: dict[str, object] = {}

    monkeypatch.setattr(evidence_capture, "_download_blob", lambda *_args, **_kwargs: b'{"not": "a-list"}')
    monkeypatch.setattr(
        evidence_capture,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, json.loads(data.decode("utf-8"))),
    )
    monkeypatch.setattr(evidence_capture, "_name_sentinel_candidates", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(evidence_capture, "_probe_write_unlock", lambda *_args, **_kwargs: None)

    evidence_capture.run_evidence_capture(ctx)

    alias_blob = f"{ctx.job_id}/{evidence_capture.S02C_PROBE_LOG_ALIAS}"
    assert uploads[alias_blob] == []
    status_blob = f"{ctx.job_id}/{evidence_capture.S02C_FINDING_STATUS_ALIAS}"
    assert uploads[status_blob] == []


def test_s02c_probe_log_snapshot_degrades_safely_when_source_log_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _ctx()
    ctx.job_id = "job-s02c-missing-source-log"
    _install_status_capture(monkeypatch)
    uploads: dict[str, object] = {}

    monkeypatch.setattr(evidence_capture, "_download_blob", lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("missing")))
    monkeypatch.setattr(
        evidence_capture,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, json.loads(data.decode("utf-8"))),
    )
    monkeypatch.setattr(evidence_capture, "_name_sentinel_candidates", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(evidence_capture, "_probe_write_unlock", lambda *_args, **_kwargs: None)

    evidence_capture.run_evidence_capture(ctx)

    alias_blob = f"{ctx.job_id}/{evidence_capture.S02C_PROBE_LOG_ALIAS}"
    assert uploads[alias_blob] == []
    status_blob = f"{ctx.job_id}/{evidence_capture.S02C_FINDING_STATUS_ALIAS}"
    assert uploads[status_blob] == []
