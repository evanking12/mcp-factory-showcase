from __future__ import annotations

import json


def test_execute_gap_tool_traced_records_bridge_health_and_trace(monkeypatch) -> None:
    from api.pipeline.s06_gaps import gap_resolution as mod

    uploaded: dict[str, bytes] = {}

    monkeypatch.setattr(mod, "_download_blob", lambda *args, **kwargs: b"[]")
    monkeypatch.setattr(
        mod,
        "_upload_to_blob",
        lambda _container, blob_name, payload: uploaded.__setitem__(blob_name, payload),
    )
    monkeypatch.setattr(mod, "_probe_bridge_now", lambda: True)
    monkeypatch.setattr(
        mod,
        "_execute_tool_traced",
        lambda inv, args: {
            "result_str": "Returned: 0",
            "trace": {"backend": "bridge", "fn": inv.get("name", ""), "args_keys": sorted(args.keys())},
        },
    )

    result, trace = mod._execute_gap_tool_traced(
        "job-1",
        {"name": "RP_GetLastErrorText"},
        {"dwBufLen": 100},
        stage="s06_gaps",
        target_function="RP_GetLastErrorText",
        note="gap_round_tool_call",
    )

    assert result == "Returned: 0"
    assert trace == {"backend": "bridge", "fn": "RP_GetLastErrorText", "args_keys": ["dwBufLen"]}

    saved = json.loads(uploaded["job-1/gap_execution_trace.json"].decode())
    assert saved[-1]["tool"] == "RP_GetLastErrorText"
    assert saved[-1]["bridge_before"] is True
    assert saved[-1]["bridge_after"] is True
    assert saved[-1]["note"] == "gap_round_tool_call"


def test_build_gap_observed_success_patch_stays_cautious() -> None:
    from api.pipeline.s06_gaps import gap_resolution as mod

    patch = mod._build_gap_observed_success_patch(  # noqa: SLF001
        "SP_IssueReleaseHold",
        {"param_1": "sess-1"},
        source="Gap resolution",
    )

    assert patch["status"] == "partial"
    assert "replay validation still required" in patch["finding"]
    assert "returned 0" not in patch["finding"]
    assert patch["stop_reason"] == "gap_observed_success_pending_validation"


def test_build_gap_verification_downgrade_patch_carries_rejection_provenance() -> None:
    from api.pipeline.s06_gaps import gap_resolution as mod

    patch = mod._build_gap_verification_downgrade_patch(  # noqa: SLF001
        "SP_IssueReleaseHold",
        {"param_1": "sess-1"},
        4294960193,
        sentinel_meaning="operator session open failed",
        source="Gap resolution verify",
    )

    assert patch["status"] == "failure"
    assert patch["working_call"] is None
    assert patch["verification"] == "state_drift"
    assert patch["direct_target_truth_rejected_reason"] == patch["finding"]
    assert patch["stop_reason"] == "gap_verify_state_drift"


def test_resolve_gap_observed_success_requires_same_branch_replay(monkeypatch) -> None:
    from api.pipeline.s06_gaps import gap_resolution as mod

    monkeypatch.setattr(
        mod,
        "_execute_gap_tool_traced",
        lambda *args, **kwargs: ("Returned: 4294960193", {"backend": "bridge"}),
    )

    patch = mod._resolve_gap_observed_success(  # noqa: SLF001
        "job-1",
        "SP_IssueReleaseHold",
        {"name": "SP_IssueReleaseHold"},
        {"session_handle": "WFH-CUST-001-02", "output_buffer": "sp-hold-CUST-001-0001"},
        source="Gap resolution",
        truth_source="s06_gap_resolution",
        stage="s06_gaps",
        sentinels={4294960193: "operator session open failed"},
    )

    assert patch["status"] == "failure"
    assert patch["working_call"] is None
    assert patch["verification"] == "state_drift"
    assert "replay rejected" in patch["finding"]


def test_resolve_gap_observed_success_promotes_verified_truth(monkeypatch) -> None:
    from api.pipeline.s06_gaps import gap_resolution as mod

    monkeypatch.setattr(
        mod,
        "_execute_gap_tool_traced",
        lambda *args, **kwargs: ("Returned: 0", {"backend": "bridge"}),
    )

    working_call = {
        "session_handle": "WFH-CUST-001-02",
        "output_buffer": "sp-hold-CUST-001-0001",
        "output_buffer__2": "sp-resv-CUST-001-0001",
    }
    patch = mod._resolve_gap_observed_success(  # noqa: SLF001
        "job-1",
        "SP_IssueReleaseHold",
        {"name": "SP_IssueReleaseHold"},
        working_call,
        source="Gap resolution",
        truth_source="s06_gap_resolution",
        stage="s06_gaps",
        sentinels={},
    )

    assert patch["status"] == "verified_success"
    assert patch["working_call"] == working_call
    assert patch["verification"] == "verified"
    assert patch["direct_target_truth"]["working_call"] == working_call
    assert patch["direct_target_truth"]["source"] == "s06_gap_resolution"
