from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from api.pipeline.s03_reconcile import reconcile


def _ctx(job_id: str = "job-s02c-s03-consumability-tier2") -> SimpleNamespace:
    return SimpleNamespace(job_id=job_id, total=3, explored_count=lambda: 3)


def _success_probe(function: str, args: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "phase": "explore",
        "function": function,
        "tool": function,
        "args": args or {},
        "result_excerpt": "Returned: 0",
        "classification": {
            "status": "observed",
            "boundary": "raw_execution",
            "has_return": True,
            "signed": 0,
        },
        "trace": {
            "backend": "dll",
            "function_name": function,
            "raw_result": 0,
            "c_args_count": len(args or {}),
        },
        "probe_id": f"{function}-probe-001",
    }


def _blocked_probe(function: str) -> dict[str, object]:
    return {
        "phase": "explore",
        "function": function,
        "tool": function,
        "args": {},
        "result_excerpt": "Returned: -5",
        "classification": {
            "status": "blocked",
            "boundary": "raw_execution",
            "has_return": True,
            "signed": -5,
        },
        "trace": {
            "backend": "dll",
            "function_name": function,
            "raw_result": -5,
            "c_args_count": 0,
        },
        "probe_id": f"{function}-probe-001",
    }


def test_s02c_s03_tier2_consumes_durable_probe_evidence_without_false_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 2 seam anchor: S-03 consumes S-02C durable evidence boundaries."""
    ctx = _ctx()
    durable_rows = [
        _success_probe("S02C_S03_ReconcileOk", {"value": 7}),
        _blocked_probe("S02C_S03_BlockedPrecondition"),
    ]
    findings = [
        {"function": "S02C_S03_ReconcileOk", "status": "error"},
        {"function": "S02C_S03_BlockedPrecondition", "status": "error"},
        {"function": "S02C_S03_MissingObservation", "status": "error"},
    ]
    patches: list[tuple[str, dict[str, object]]] = []
    requested_blobs: list[str] = []

    def fake_download(_container: str, blob_name: str) -> bytes:
        requested_blobs.append(blob_name)
        assert blob_name == f"{ctx.job_id}/{reconcile.S02C_PROBE_LOG_ALIAS}"
        return json.dumps(durable_rows).encode("utf-8")

    monkeypatch.setattr(reconcile, "_download_blob", fake_download)
    monkeypatch.setattr(reconcile, "_load_findings", lambda _job_id: list(findings))
    monkeypatch.setattr(reconcile, "_patch_finding", lambda _job_id, fn, patch: patches.append((fn, patch)))
    monkeypatch.setattr(reconcile, "_set_explore_status", lambda *_args, **_kwargs: None)

    reconcile._run_phase_4_reconcile(ctx)

    assert requested_blobs == [f"{ctx.job_id}/{reconcile.S02C_PROBE_LOG_ALIAS}"]
    assert [fn for fn, _patch in patches] == ["S02C_S03_ReconcileOk"]
    patch = patches[0][1]
    assert patch["status"] == "success"
    assert patch["working_call"] == {"value": 7}
    assert patch["stop_reason"] == "reconciled_from_probe_log"
    assert "returned 0" in str(patch["finding"])


def test_s02c_s03_tier2_falls_back_to_legacy_probe_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S-03 keeps legacy compatibility when the S-02C alias is absent."""
    ctx = _ctx("job-s02c-s03-legacy-fallback")
    legacy_rows = [_success_probe("S02C_S03_LegacyFallback")]
    patches: list[tuple[str, dict[str, object]]] = []
    requested_blobs: list[str] = []

    def fake_download(_container: str, blob_name: str) -> bytes:
        requested_blobs.append(blob_name)
        if blob_name == f"{ctx.job_id}/{reconcile.S02C_PROBE_LOG_ALIAS}":
            raise FileNotFoundError(blob_name)
        assert blob_name == f"{ctx.job_id}/explore_probe_log.json"
        return json.dumps(legacy_rows).encode("utf-8")

    monkeypatch.setattr(reconcile, "_download_blob", fake_download)
    monkeypatch.setattr(
        reconcile,
        "_load_findings",
        lambda _job_id: [{"function": "S02C_S03_LegacyFallback", "status": "error"}],
    )
    monkeypatch.setattr(reconcile, "_patch_finding", lambda _job_id, fn, patch: patches.append((fn, patch)))
    monkeypatch.setattr(reconcile, "_set_explore_status", lambda *_args, **_kwargs: None)

    reconcile._run_phase_4_reconcile(ctx)

    assert requested_blobs == [
        f"{ctx.job_id}/{reconcile.S02C_PROBE_LOG_ALIAS}",
        f"{ctx.job_id}/explore_probe_log.json",
    ]
    assert [fn for fn, _patch in patches] == ["S02C_S03_LegacyFallback"]
