from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

from api.infra import storage
from api.pipeline import runner
from api.pipeline import s07_finalize
from api.pipeline.s05_enrichment.verify import _run_direct_replay
from api.pipeline.s07_finalize.harmonize import _run_finalize, _run_phase_10_harmonize


def test_patch_finding_promotion_ignores_stale_canonical_status(monkeypatch) -> None:
    job_id = "job-stale-canonical-promotion"
    storage._JOB_FINDINGS[job_id] = [  # noqa: SLF001
        {
            "function": "SP_OpenOperatorSession",
            "status": "partial",
            "status_canonical": "inferred_success",
            "working_call": {
                "operator_id": "easy01-operator",
                "out_operator_token": "sp-operator-easy01-operator-session",
                "out_len": 64,
            },
            "reusable_truth_eligible": False,
            "reusable_truth_reasons": ["status_not_verified_success"],
        }
    ]
    storage._JOB_INVOCABLE_MAPS[job_id] = {  # noqa: SLF001
        "SP_OpenOperatorSession": {
            "parameters": [
                {
                    "name": "operator_id",
                    "json_type": "string",
                    "resolved_type": "char*",
                    "description": "The ID of the operator to open a session for.",
                },
                {
                    "name": "out_operator_token",
                    "json_type": "string",
                    "resolved_type": "char*",
                    "direction": "out",
                    "description": "The session token for the operator.",
                },
                {
                    "name": "out_len",
                    "json_type": "integer",
                    "description": "The output token buffer length.",
                },
            ]
        }
    }
    monkeypatch.setattr(storage, "_upload_to_blob", lambda *args, **kwargs: None)

    storage._patch_finding(  # noqa: SLF001
        job_id,
        "SP_OpenOperatorSession",
        {
            "status": "verified_success",
            "verification": "verified",
            "working_call": {
                "operator_id": "easy01-operator",
                "out_operator_token": "sp-operator-easy01-operator-session",
                "out_len": 64,
            },
        },
    )

    row = storage._JOB_FINDINGS[job_id][-1]  # noqa: SLF001
    assert row["status_canonical"] == "verified_success"
    assert row["reusable_truth_eligible"] is True
    assert "status_not_verified_success" not in row["reusable_truth_reasons"]


def test_direct_target_truth_preserves_verified_status_when_output_is_not_reusable(monkeypatch) -> None:
    job_id = "job-direct-target-nonreusable-output"
    storage._JOB_FINDINGS[job_id] = [  # noqa: SLF001
        {
            "function": "SP_InvalidateUntrustedBranch",
            "status": "partial",
            "working_call": {
                "trusted_branch_id": "sp-branch-primary",
                "rejected_branch_id": "sp-branch-replay",
                "out_audit_token": "sp-audit-branch-invalidated",
                "out_len": 64,
            },
        }
    ]
    storage._JOB_INVOCABLE_MAPS[job_id] = {  # noqa: SLF001
        "SP_InvalidateUntrustedBranch": {
            "parameters": [
                {"name": "trusted_branch_id", "json_type": "string", "resolved_type": "const char*"},
                {"name": "rejected_branch_id", "json_type": "string", "resolved_type": "const char*"},
                {
                    "name": "out_audit_token",
                    "json_type": "string",
                    "resolved_type": "char*",
                    "direction": "out",
                    "description": "Object-bound audit token for the rejected branch.",
                },
                {"name": "out_len", "json_type": "integer", "resolved_type": "DWORD"},
            ]
        }
    }
    monkeypatch.setattr(storage, "_upload_to_blob", lambda *args, **kwargs: None)

    storage._patch_finding(  # noqa: SLF001
        job_id,
        "SP_InvalidateUntrustedBranch",
        {
            "status": "verified_success",
            "working_call": {
                "trusted_branch_id": "sp-branch-primary",
                "rejected_branch_id": "sp-branch-replay",
                "out_audit_token": "sp-audit-branch-invalidated",
                "out_len": 64,
            },
            "direct_target_truth": {
                "function": "SP_InvalidateUntrustedBranch",
                "working_call": {
                    "trusted_branch_id": "sp-branch-primary",
                    "rejected_branch_id": "sp-branch-replay",
                    "out_audit_token": "sp-audit-branch-invalidated",
                    "out_len": 64,
                },
                "return_value": 0,
                "verification": "verified",
                "source": "s02_ground_truth_override",
            },
        },
    )

    row = storage._JOB_FINDINGS[job_id][-1]  # noqa: SLF001
    assert row["status_canonical"] == "verified_success"
    assert row["reusable_truth_eligible"] is False
    assert "out_audit_token_expected_blob_token" in row["reusable_truth_reasons"]


def test_worker_close_trace_is_nonblocking(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def slow_append(job_id: str, artifact_name: str, entry: dict) -> None:
        calls.append((job_id, artifact_name))
        time.sleep(0.25)

    monkeypatch.setattr(runner, "_append_job_debug_event", slow_append)

    started = time.perf_counter()
    runner._record_worker_close_step("job-close", "macro_verdict_persisted")  # noqa: SLF001
    elapsed = time.perf_counter() - started

    assert elapsed < 0.1
    deadline = time.time() + 1.0
    while not calls and time.time() < deadline:
        time.sleep(0.01)
    assert calls == [("job-close", "worker_close_trace.json")]


def test_macro_verdict_evaluation_timeout_uses_close_path_fallback(monkeypatch) -> None:
    blocker = threading.Event()
    ctx = SimpleNamespace(
        job_id="job-macro-timeout",
        total=1,
        explored_count=lambda: 1,
    )

    monkeypatch.setattr(runner, "_evaluate_run", lambda _ctx: blocker.wait(timeout=1.0))  # noqa: SLF001
    monkeypatch.setattr(
        runner,
        "_get_job_status",
        lambda _job_id: {"final_phase_suggestion": "done"},
    )

    started = time.perf_counter()
    verdict, fallback = runner._evaluate_macro_verdict_bounded(ctx, timeout_s=0.01)  # noqa: SLF001

    assert time.perf_counter() - started < 0.5
    assert fallback is True
    assert verdict.status == "done"
    assert verdict.coverage_pct == 100.0
    assert "fallback used" in verdict.reasoning


def test_macro_verdict_persistence_timeout_does_not_block_worker_close(monkeypatch) -> None:
    blocker = threading.Event()
    ctx = SimpleNamespace(job_id="job-macro-persist-timeout")

    monkeypatch.setattr(runner, "_persist_verdict", lambda *_args: blocker.wait(timeout=1.0))  # noqa: SLF001

    started = time.perf_counter()
    persisted = runner._persist_macro_verdict_bounded(  # noqa: SLF001
        ctx,
        runner.RunVerdict(status="done", coverage_pct=100.0, verified_count=1, total_count=1),
        timeout_s=0.01,
    )

    assert time.perf_counter() - started < 0.5
    assert persisted is None


def test_worker_close_progress_marks_macro_span(monkeypatch) -> None:
    recorded: list[dict] = []
    monkeypatch.setattr(runner, "_get_job_status", lambda _job_id: {"status": "running"})
    monkeypatch.setattr(
        runner,
        "_persist_job_status",
        lambda _job_id, payload, sync=True: recorded.append({**payload, "_sync": sync}),
    )

    runner._persist_worker_close_progress(  # noqa: SLF001
        "job-macro-span",
        "Finalize complete — computing macro verdict",
        span="s07_macro_verdict_evaluate",
        span_state="start",
        span_message="S-07 close: evaluating macro verdict.",
    )

    assert recorded[-1]["explore_stage"] == "s07_finalize"
    assert recorded[-1]["explore_span"] == "s07_macro_verdict_evaluate"
    assert recorded[-1]["explore_span_state"] == "start"
    assert recorded[-1]["_sync"] is False


def test_patch_finding_preserves_direct_target_truth_on_weaker_patch(monkeypatch) -> None:
    job_id = "job-direct-target"
    storage._JOB_FINDINGS[job_id] = [  # noqa: SLF001
        {
            "function": "CFG_RunCustomerSync",
            "status": "verified_success",
            "status_canonical": "verified_success",
            "working_call": {"param_1": "TICK-001"},
            "direct_target_truth": {
                "function": "CFG_RunCustomerSync",
                "working_call": {"param_1": "TICK-001"},
                "verification": "verified",
                "source": "s02_ground_truth_override",
            },
        }
    ]
    monkeypatch.setattr(storage, "_upload_to_blob", lambda *args, **kwargs: None)

    storage._patch_finding(  # noqa: SLF001
        job_id,
        "CFG_RunCustomerSync",
        {
            "working_call": None,
            "status": "failure",
            "verification": "state_drift",
            "direct_target_truth_rejected_reason": "verify replay failed",
        },
    )

    row = storage._JOB_FINDINGS[job_id][-1]  # noqa: SLF001
    assert row["working_call"] is None
    assert row["direct_target_truth"]["working_call"] == {"param_1": "TICK-001"}
    assert row["direct_target_truth"]["verification"] == "verified"


def test_direct_replay_prefers_preserved_direct_target_truth(monkeypatch) -> None:
    ctx = SimpleNamespace(
        inv_map={"CFG_RunCustomerSync": {"name": "CFG_RunCustomerSync", "parameters": []}},
        sentinels={},
    )
    finding = {
        "function": "CFG_RunCustomerSync",
        "status": "failure",
        "working_call": None,
        "direct_target_truth": {
            "function": "CFG_RunCustomerSync",
            "working_call": {"param_1": "TICK-001"},
            "verification": "verified",
            "source": "s02_ground_truth_override",
        },
    }

    monkeypatch.setattr("api.pipeline.s05_enrichment.verify._execute_session_prereqs", lambda ctx: None)
    monkeypatch.setattr("api.pipeline.s05_enrichment.verify._execute_tool", lambda inv, args: "Returned: 0")

    report_entry, patch, bridge_error = _run_direct_replay(ctx, finding, [], [finding])

    assert bridge_error == ""
    assert report_entry["args"] == {"param_1": "TICK-001"}
    assert patch["status"] == "verified_success"
    assert patch["verification"] == "verified"
    assert patch["direct_target_truth"]["working_call"] == {"param_1": "TICK-001"}


def test_harmonize_promotes_preserved_direct_target_truth(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-harmonize",
        vocab={},
        run_started_at=0.0,
        total=1,
        explored_count=lambda: 0,
    )
    recorded_patches: list[dict] = []

    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._set_explore_status",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._set_s07_span_status",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._load_findings",
        lambda job_id: [
            {
                "function": "RP_SelectFormat",
                "status": "failure",
                "status_canonical": "failure",
                "direct_target_truth": {
                    "function": "RP_SelectFormat",
                    "working_call": {"lpszReportId": "RPT-001", "dwFormat": 2},
                    "verification": "verified",
                    "source": "s05_probe_log",
                },
            }
        ],
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._download_blob",
        lambda *args, **kwargs: json.dumps([]).encode("utf-8"),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._patch_finding",
        lambda job_id, function_name, patch: recorded_patches.append({"function": function_name, **patch}),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._upload_to_blob",
        lambda *args, **kwargs: None,
    )

    _run_phase_10_harmonize(ctx)

    assert recorded_patches
    assert recorded_patches[0]["function"] == "RP_SelectFormat"
    assert recorded_patches[0]["status"] == "success"
    assert recorded_patches[0]["stop_reason"] == "harmonized_direct_target_truth"


def test_harmonize_does_not_promote_semantically_rejected_direct_target_truth(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-harmonize-rejected",
        vocab={},
        run_started_at=0.0,
        total=1,
        explored_count=lambda: 0,
    )
    recorded_patches: list[dict] = []

    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._set_explore_status",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._set_s07_span_status",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._load_findings",
        lambda job_id: [
            {
                "function": "SP_PrepareReleasePreview",
                "status": "partial",
                "status_canonical": "inferred_success",
                "direct_target_truth": {
                    "function": "SP_PrepareReleasePreview",
                    "working_call": {
                        "reservation_handle": "sp-resv-ORD-20040301-0042",
                        "operator_token": "sp-operator-0-session",
                        "out_preview_ticket": "CUST-001|name=Alice Contoso|email=alice@contoso.com",
                        "out_len": 64,
                    },
                    "verification": "verified",
                    "source": "s02_ground_truth_override",
                },
                "cross_validation": (
                    "SP_PrepareReleasePreview({'reservation_handle': 'sp-resv-ORD-20040301-0042', "
                    "'operator_token': 'sp-operator-0-session'}) \u2192 Returned: 0\n"
                    "out_preview_ticket='sp-preview-ORD-20040301-0042-gate'"
                ),
            }
        ],
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._get_invocable",
        lambda *args, **kwargs: {
            "parameters": [
                {"name": "reservation_handle", "direction": "in", "type": "char*"},
                {"name": "operator_token", "direction": "in", "type": "char*"},
                {"name": "out_preview_ticket", "direction": "out", "type": "char*"},
                {"name": "out_len", "direction": "in", "type": "uint32_t"},
            ]
        },
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._download_blob",
        lambda *args, **kwargs: json.dumps([]).encode("utf-8"),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._patch_finding",
        lambda job_id, function_name, patch: recorded_patches.append({"function": function_name, **patch}),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._upload_to_blob",
        lambda *args, **kwargs: None,
    )

    _run_phase_10_harmonize(ctx)

    assert recorded_patches == []


def test_harmonize_does_not_promote_cross_validation_divergent_fee_truth(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-harmonize-fee-divergent",
        vocab={},
        run_started_at=0.0,
        total=1,
        explored_count=lambda: 0,
    )
    recorded_patches: list[dict] = []

    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._set_explore_status",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._set_s07_span_status",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._load_findings",
        lambda job_id: [
            {
                "function": "SP_StageReleaseFeeQuote",
                "status": "partial",
                "status_canonical": "inferred_success",
                "direct_target_truth": {
                    "function": "SP_StageReleaseFeeQuote",
                    "working_call": {
                        "reservation_handle": "sp-resv-ORD-20040301-0042",
                        "operator_token": "sp-operator-0-session",
                        "out_fee_quote_id": "PRQ-CUST-001-01",
                        "out_len": 64,
                    },
                    "verification": "verified",
                    "source": "s02_ground_truth_override",
                },
                "cross_validation": (
                    "SP_StageReleaseFeeQuote({'reservation_handle': 'sp-resv-ORD-20040301-0042', "
                    "'operator_token': 'sp-operator-0-session'}) \u2192 Returned: 0\n"
                    "out_fee_quote_id='sp-fee-ORD-20040301-0042-quote'"
                ),
            }
        ],
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._get_invocable",
        lambda *args, **kwargs: {
            "parameters": [
                {"name": "reservation_handle", "direction": "in", "type": "char*"},
                {"name": "operator_token", "direction": "in", "type": "char*"},
                {"name": "out_fee_quote_id", "direction": "out", "type": "char*"},
                {"name": "out_len", "direction": "in", "type": "uint32_t"},
            ]
        },
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._download_blob",
        lambda *args, **kwargs: json.dumps([]).encode("utf-8"),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._patch_finding",
        lambda job_id, function_name, patch: recorded_patches.append({"function": function_name, **patch}),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._upload_to_blob",
        lambda *args, **kwargs: None,
    )

    _run_phase_10_harmonize(ctx)

    assert recorded_patches == []


def test_harmonize_allows_output_mismatch_when_cross_validation_inputs_differ(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-harmonize-input-dependent-output",
        vocab={},
        run_started_at=0.0,
        total=1,
        explored_count=lambda: 0,
    )
    recorded_patches: list[dict] = []

    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._set_explore_status",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._set_s07_span_status",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._load_findings",
        lambda job_id: [
            {
                "function": "SP_OpenOperatorSession",
                "status": "partial",
                "status_canonical": "inferred_success",
                "direct_target_truth": {
                    "function": "SP_OpenOperatorSession",
                    "working_call": {
                        "operator_id": "easy01-operator",
                        "out_operator_token": "sp-operator-easy01-operator-session",
                        "out_len": 64,
                    },
                    "verification": "verified",
                    "source": "s02_ground_truth_override",
                },
                "cross_validation": (
                    "SP_OpenOperatorSession({'operator_id': 'ORD-001'}) \u2192 Returned: 0\n"
                    "out_operator_token='sp-operator-ORD-001-session'"
                ),
            }
        ],
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._get_invocable",
        lambda *args, **kwargs: {
            "parameters": [
                {"name": "operator_id", "direction": "in", "type": "char*"},
                {"name": "out_operator_token", "direction": "out", "type": "char*"},
                {"name": "out_len", "direction": "in", "type": "uint32_t"},
            ]
        },
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._download_blob",
        lambda *args, **kwargs: json.dumps([]).encode("utf-8"),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._patch_finding",
        lambda job_id, function_name, patch: recorded_patches.append({"function": function_name, **patch}),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._upload_to_blob",
        lambda *args, **kwargs: None,
    )

    _run_phase_10_harmonize(ctx)

    assert recorded_patches
    assert recorded_patches[0]["function"] == "SP_OpenOperatorSession"
    assert recorded_patches[0]["status"] == "success"
    assert recorded_patches[0]["stop_reason"] == "harmonized_direct_target_truth"


def test_dispatch_postclose_writebacks_defers_for_single_pass(monkeypatch) -> None:
    started: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class _FakeThread:
        def __init__(self, *, target=None, args=(), daemon=None, name=None):  # noqa: ANN001
            started.append((args, {"target": target, "daemon": daemon, "name": name}))

        def start(self) -> None:
            started.append((("started",), {}))

    monkeypatch.setattr(runner.threading, "Thread", _FakeThread)
    monkeypatch.setattr(runner, "_record_worker_close_step", lambda *args, **kwargs: None)

    ctx = SimpleNamespace(runtime=SimpleNamespace(iteration_mode="single_pass"))
    runner._dispatch_postclose_writebacks("job-1", ctx, "checkpoint", "graph", "dll-fp")

    assert started
    assert started[0][1]["daemon"] is True
    assert started[0][1]["target"] is runner._run_postclose_writebacks
    assert started[0][0] == ("job-1", ctx, "checkpoint", "graph", "dll-fp")
    assert started[1][0] == ("started",)


def test_dispatch_postclose_writebacks_stays_sync_for_floor_to_ceiling(monkeypatch) -> None:
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(runner, "_record_worker_close_step", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runner,
        "_run_postclose_writebacks",
        lambda *args: calls.append(args),
    )

    ctx = SimpleNamespace(runtime=SimpleNamespace(iteration_mode="floor_to_ceiling"))
    runner._dispatch_postclose_writebacks("job-2", ctx, "checkpoint", "graph", "dll-fp")

    assert calls == [("job-2", ctx, "checkpoint", "graph", "dll-fp")]


def test_harmonize_reassesses_preserved_direct_target_truth_after_stale_demotion(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-harmonize-stale-demotion",
        vocab={},
        run_started_at=0.0,
        total=1,
        explored_count=lambda: 0,
    )
    recorded_patches: list[dict] = []

    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._set_explore_status",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._set_s07_span_status",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._load_findings",
        lambda job_id: [
            {
                "function": "SP_PrepareReleasePreview",
                "status": "partial",
                "status_canonical": "inferred_success",
                "reusable_truth_eligible": False,
                "expected_observed_alignment": "rejected",
                "direct_target_truth": {
                    "function": "SP_PrepareReleasePreview",
                    "working_call": {
                        "reservation_handle": "sp-resv-ORD-20040301-0042",
                        "operator_token": "sp-operator-0-session",
                        "out_preview_ticket": "sp-preview-ORD-20040301-0042-gate",
                        "out_len": 64,
                    },
                    "verification": "verified",
                    "source": "s02_ground_truth_override",
                },
                "cross_validation": (
                    "SP_PrepareReleasePreview({'reservation_handle': 'sp-resv-ORD-20040301-0042', "
                    "'operator_token': 'sp-operator-0-session'}) → Returned: 0\n"
                    "out_preview_ticket='sp-preview-ORD-20040301-0042-gate'"
                ),
            }
        ],
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._get_invocable",
        lambda *args, **kwargs: {
            "parameters": [
                {
                    "name": "reservation_handle",
                    "direction": "in",
                    "type": "char*",
                    "description": "Reservation handle for the release preview request.",
                },
                {
                    "name": "operator_token",
                    "direction": "in",
                    "type": "char*",
                    "description": "Operator token for the release preview request.",
                },
                {
                    "name": "out_preview_ticket",
                    "direction": "out",
                    "type": "char*",
                    "description": "Output preview ticket.",
                },
                {"name": "out_len", "direction": "in", "type": "uint32_t"},
            ]
        },
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._download_blob",
        lambda *args, **kwargs: json.dumps([]).encode("utf-8"),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._patch_finding",
        lambda job_id, function_name, patch: recorded_patches.append({"function": function_name, **patch}),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._upload_to_blob",
        lambda *args, **kwargs: None,
    )

    _run_phase_10_harmonize(ctx)

    assert recorded_patches
    assert recorded_patches[0]["function"] == "SP_PrepareReleasePreview"
    assert recorded_patches[0]["status"] == "success"
    assert recorded_patches[0]["stop_reason"] == "harmonized_direct_target_truth"


def test_patch_finding_clears_gap_exhaustion_fields_on_observed_success(monkeypatch) -> None:
    job_id = "job-gap-observed"
    storage._JOB_FINDINGS[job_id] = [  # noqa: SLF001
        {
            "function": "SP_IssueReleaseHold",
            "status": "failure",
            "finding": "Auto-recorded fallback",
            "notes": "Auto-recorded: exhausted tool calls.",
            "direct_target_tool_calls": 4,
            "no_tool_call_rounds": 0,
            "write_policy_events": [],
        }
    ]
    monkeypatch.setattr(storage, "_upload_to_blob", lambda *args, **kwargs: None)

    storage._patch_finding(  # noqa: SLF001
        job_id,
        "SP_IssueReleaseHold",
        {
            "working_call": {"param_1": "sess-1"},
            "status": "partial",
            "finding": "Gap resolution: observed SP_IssueReleaseHold return 0 during probing; replay validation still required.",
            "notes": "Observed probe success superseded the earlier exhaustion fallback; replay validation still required before confirmed success.",
        },
    )

    row = storage._JOB_FINDINGS[job_id][-1]  # noqa: SLF001
    assert row["status_canonical"] == "inferred_success"
    assert "direct_target_tool_calls" not in row
    assert "no_tool_call_rounds" not in row
    assert "write_policy_events" not in row


def test_patch_finding_downgrade_replaces_success_wording(monkeypatch) -> None:
    job_id = "job-gap-downgrade"
    storage._JOB_FINDINGS[job_id] = [  # noqa: SLF001
        {
            "function": "SP_IssueReleaseHold",
            "status": "success",
            "status_canonical": "verified_success",
            "finding": "Gap resolution: SP_IssueReleaseHold({'param_1': 'sess-1'}) returned 0",
            "working_call": {"param_1": "sess-1"},
            "direct_target_truth": {
                "function": "SP_IssueReleaseHold",
                "working_call": {"param_1": "sess-1"},
                "verification": "verified",
                "source": "s06_gap_resolution",
            },
        }
    ]
    monkeypatch.setattr(storage, "_upload_to_blob", lambda *args, **kwargs: None)

    storage._patch_finding(  # noqa: SLF001
        job_id,
        "SP_IssueReleaseHold",
        {
            "working_call": None,
            "status": "failure",
            "finding": "Gap resolution verify: replay rejected SP_IssueReleaseHold({'param_1': 'sess-1'}) with return 4294960193",
            "verification": "state_drift",
            "direct_target_truth_rejected_reason": "Gap resolution verify: replay rejected SP_IssueReleaseHold({'param_1': 'sess-1'}) with return 4294960193",
            "stop_reason": "gap_verify_state_drift",
        },
    )

    row = storage._JOB_FINDINGS[job_id][-1]  # noqa: SLF001
    assert row["status_canonical"] == "failure"
    assert row["working_call"] is None
    assert "returned 0" not in row["finding"]
    assert row["verification"] == "state_drift"
    assert row["direct_target_truth"]["working_call"] == {"param_1": "sess-1"}


def test_run_finalize_keeps_explore_phase_nonterminal_until_worker_close(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-finalize",
        vocab={},
        run_started_at=10.0,
        total=1,
        sentinel_new_codes_this_run=0,
        explored_count=lambda: 1,
    )
    recorded_statuses: list[dict] = []
    recorded_sync_modes: list[bool] = []

    monkeypatch.setattr("api.pipeline.s07_finalize.harmonize._upload_to_blob", lambda *args, **kwargs: None)
    monkeypatch.setattr("api.pipeline.s07_finalize.harmonize._cancel_requested", lambda _job_id: False)
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._get_job_status",
        lambda _job_id: {"status": "running", "explore_questions": []},
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._persist_job_status",
        lambda _job_id, payload, sync=True: (
            recorded_statuses.append(dict(payload)),
            recorded_sync_modes.append(sync),
        ),
    )
    monkeypatch.setattr("api.pipeline.s07_finalize.harmonize.time.time", lambda: 70.0)

    _run_finalize(ctx)

    assert recorded_statuses
    payload = next(row for row in reversed(recorded_statuses) if "final_phase_suggestion" in row)
    assert payload["status"] == "running"
    assert payload["explore_phase"] == "exploring"
    assert payload["explore_stage"] == "s07_finalize"
    assert payload["final_phase_suggestion"] == "done"
    assert recorded_sync_modes[-1] is False
    assert payload["explore_message"] == "Finalize complete — awaiting macro verdict persistence"
    assert any(row.get("explore_span") == "s07_finalize_schema_evolution" for row in recorded_statuses)
    assert any(row.get("explore_span") == "s07_finalize_status_persist" for row in recorded_statuses)


def test_run_finalize_degrades_when_description_synthesis_times_out(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-finalize-timeout",
        vocab={"user_context": "checkout session"},
        client=SimpleNamespace(),
        model="test-model",
        run_started_at=10.0,
        total=1,
        sentinel_new_codes_this_run=0,
        explored_count=lambda: 1,
    )
    recorded_statuses: list[dict] = []
    recorded_sync_modes: list[bool] = []

    def fake_bounded_completion(*args, **kwargs):  # noqa: ANN002, ANN003
        raise TimeoutError("s07 description synthesis exceeded 30.0s")

    monkeypatch.setenv("MCP_ENABLE_S07_DESCRIPTION_SYNTHESIS", "1")
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._chat_completion_create_bounded",
        fake_bounded_completion,
    )
    monkeypatch.setattr("api.pipeline.s07_finalize.harmonize._upload_to_blob", lambda *args, **kwargs: None)
    monkeypatch.setattr("api.pipeline.s07_finalize.harmonize._cancel_requested", lambda _job_id: False)
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._get_job_status",
        lambda _job_id: {"status": "running", "explore_questions": []},
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._persist_job_status",
        lambda _job_id, payload, sync=True: (
            recorded_statuses.append(dict(payload)),
            recorded_sync_modes.append(sync),
        ),
    )
    monkeypatch.setattr("api.pipeline.s07_finalize.harmonize.time.time", lambda: 70.0)

    _run_finalize(ctx)

    assert "description" not in ctx.vocab
    assert any(
        row.get("explore_span") == "s07_finalize_description"
        and row.get("explore_span_state") == "fail"
        for row in recorded_statuses
    )
    payload = next(row for row in reversed(recorded_statuses) if "final_phase_suggestion" in row)
    assert payload["final_phase_suggestion"] == "done"
    assert payload["explore_span"] == "s07_finalize_status_persist"


def test_run_finalize_uses_deterministic_description_by_default(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-finalize-deterministic",
        vocab={"user_context": "checkout session"},
        client=SimpleNamespace(),
        model="test-model",
        run_started_at=10.0,
        total=1,
        sentinel_new_codes_this_run=0,
        explored_count=lambda: 1,
    )
    recorded_statuses: list[dict] = []
    recorded_sync_modes: list[bool] = []

    def unexpected_completion(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("description synthesis should be opt-in")

    monkeypatch.delenv("MCP_ENABLE_S07_DESCRIPTION_SYNTHESIS", raising=False)
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._chat_completion_create_bounded",
        unexpected_completion,
    )
    monkeypatch.setattr("api.pipeline.s07_finalize.harmonize._upload_to_blob", lambda *args, **kwargs: None)
    monkeypatch.setattr("api.pipeline.s07_finalize.harmonize._cancel_requested", lambda _job_id: False)
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._get_job_status",
        lambda _job_id: {"status": "running", "explore_questions": []},
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._persist_job_status",
        lambda _job_id, payload, sync=True: (
            recorded_statuses.append(dict(payload)),
            recorded_sync_modes.append(sync),
        ),
    )
    monkeypatch.setattr("api.pipeline.s07_finalize.harmonize.time.time", lambda: 70.0)

    _run_finalize(ctx)

    assert ctx.vocab["description"] == "Integration surface for checkout session."
    assert any(
        row.get("explore_span") == "s07_finalize_description"
        and row.get("explore_span_state") == "done"
        and row.get("explore_span_message") == "S-07 finalize: deterministic description applied."
        for row in recorded_statuses
    )


def test_run_s07_blocks_until_contract_artifact_emission_completes(monkeypatch) -> None:
    ctx = SimpleNamespace(job_id="job-contract-artifact-stall")
    recorded_statuses: list[dict] = []

    monkeypatch.setattr(s07_finalize, "_run_phase_10_harmonize", lambda _ctx: None)
    monkeypatch.setattr(s07_finalize, "_run_finalize", lambda _ctx: None)

    def _emit(_job_id: str) -> None:
        time.sleep(0.15)

    monkeypatch.setattr(
        s07_finalize,
        "emit_contract_artifacts",
        _emit,
    )
    monkeypatch.setattr(s07_finalize, "_get_job_status", lambda _job_id: {"status": "running"})
    monkeypatch.setattr(
        s07_finalize,
        "_persist_job_status",
        lambda _job_id, payload, sync=False: recorded_statuses.append(dict(payload)),
    )

    started = time.monotonic()
    s07_finalize.run_s07(ctx)

    assert time.monotonic() - started >= 0.15
    assert any(
        row.get("explore_span") == "s07_emit_contract_artifacts"
        and row.get("explore_span_state") == "start"
        for row in recorded_statuses
    )
    assert any(
        row.get("explore_span") == "s07_emit_contract_artifacts"
        and row.get("explore_span_state") == "done"
        for row in recorded_statuses
    )


def test_phase_10_harmonize_reports_s07_stage_for_finalizing_status(monkeypatch) -> None:
    ctx = SimpleNamespace(job_id="job-harmonize", total=1, explored_count=lambda: 1)
    recorded_statuses: list[dict] = []
    recorded_spans: list[dict] = []

    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._set_explore_status",
        lambda job_id, explored, total, message, **kwargs: recorded_statuses.append(
            {
                "job_id": job_id,
                "explored": explored,
                "total": total,
                "message": message,
                **kwargs,
            }
        ),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._set_s07_span_status",
        lambda ctx, span, state, message: recorded_spans.append(
            {"span": span, "state": state, "message": message}
        ),
    )
    monkeypatch.setattr("api.pipeline.s07_finalize.harmonize._load_findings", lambda _job_id: [])
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._download_blob",
        lambda *args, **kwargs: json.dumps([]).encode("utf-8"),
    )
    monkeypatch.setattr(
        "api.pipeline.s07_finalize.harmonize._get_job_status",
        lambda _job_id: {"status": "running", "explore_questions": []},
    )
    monkeypatch.setattr("api.pipeline.s07_finalize.harmonize._upload_to_blob", lambda *args, **kwargs: None)

    _run_phase_10_harmonize(ctx)

    assert recorded_statuses
    assert recorded_statuses[0]["message"] == "Finalizing harmonized state..."
    assert recorded_statuses[0]["stage"] == "s07_finalize"
    assert {row["span"] for row in recorded_spans} >= {
        "s07_harmonize_load_findings",
        "s07_harmonize_load_probe_log",
        "s07_harmonize_index_direct_successes",
        "s07_harmonize_promote_findings",
        "s07_harmonize_reload_findings",
        "s07_harmonize_write_report",
    }
    assert any(row["state"] == "start" for row in recorded_spans)
    assert any(row["state"] == "done" for row in recorded_spans)
