from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from api.pipeline.s05_enrichment import verify as verify_mod


def test_verify_enrichment_raises_when_bridge_transport_fails(monkeypatch) -> None:
    findings = [
        {
            "function": "RP_BindCustomer",
            "status": "verified_success",
            "working_call": {"lpszCustId": "CUST-001"},
        }
    ]
    patched: list[tuple[str, dict]] = []
    persisted: list[dict] = []
    uploads: dict[str, dict] = {}

    monkeypatch.setattr(verify_mod, "_load_findings", lambda job_id: findings)
    monkeypatch.setattr(
        verify_mod,
        "_execute_tool",
        lambda inv, args: "Bridge /execute error: [WinError 10061] No connection could be made",
    )
    monkeypatch.setattr(
        verify_mod,
        "_patch_finding",
        lambda job_id, fn_name, payload: patched.append((fn_name, payload)),
    )
    monkeypatch.setattr(
        verify_mod,
        "_upload_to_blob",
        lambda container, path, payload: uploads.setdefault(path, json.loads(payload.decode("utf-8"))),
    )
    monkeypatch.setattr(
        verify_mod,
        "_get_job_status",
        lambda job_id: {"status": "done", "explore_phase": "s05_enrichment"},
    )
    monkeypatch.setattr(
        verify_mod,
        "_persist_job_status",
        lambda job_id, payload: persisted.append(payload),
    )
    monkeypatch.setattr(verify_mod, "_set_explore_status", lambda *args, **kwargs: None)

    ctx = SimpleNamespace(
        job_id="job-bridge",
        _state={"explored": 13},
        total=13,
        inv_map={"RP_BindCustomer": {"name": "RP_BindCustomer"}},
        init_invocables=[],
        sentinels={},
    )

    with pytest.raises(RuntimeError, match="Bridge verification lane degraded"):
        verify_mod._run_phase_7b_verify_enrichment(ctx)  # noqa: SLF001

    assert patched == [("RP_BindCustomer", {"verification": "error"})]
    assert persisted[0]["verification_error"] == 1
    report = uploads["job-bridge/verification-report.json"]
    assert report["error_count"] == 1
    assert report["entries"][0]["verification"] == "error"
