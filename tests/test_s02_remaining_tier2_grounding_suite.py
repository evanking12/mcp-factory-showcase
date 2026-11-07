from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.infra import storage
from api.pipeline.core.types import ExploreContext, ExploreRuntime
from api.pipeline.s02_probe import curriculum
from api.pipeline.s02_probe import evidence_capture
from api.pipeline.s02_probe import invocation_execution
from api.pipeline.s02_probe import probe_loop
from api.pipeline.s02_probe import probe_ordering
from api.pipeline.s02_probe import status as s02_status
from api.pipeline.s03_reconcile import reconcile
from api.services import executor


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s02_remaining_tier2"
BUILD_SCRIPT = FIXTURE_ROOT / "build.ps1"


def _has_msvc_toolchain() -> bool:
    if sys.platform != "win32":
        return False
    script = (
        "$vswhere = Join-Path ${env:ProgramFiles(x86)} "
        "'Microsoft Visual Studio\\Installer\\vswhere.exe'; "
        "$install = ''; "
        "if (Test-Path $vswhere) { "
        "$install = & $vswhere -latest -products * "
        "-requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 "
        "-property installationPath 2>$null "
        "}; "
        "$cl = Get-Command cl.exe -ErrorAction SilentlyContinue; "
        "if ($install -or $cl) { exit 0 } else { exit 1 }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


@pytest.fixture(scope="module")
def remaining_tier2_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not _has_msvc_toolchain():
        pytest.skip("MSVC toolchain not available")
    output_root = tmp_path_factory.mktemp("s02-remaining-tier2")
    completed = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD_SCRIPT),
            "-OutputRoot",
            str(output_root),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    dll_path = output_root / "bin" / "s02_remaining_tier2.dll"
    assert dll_path.exists(), completed.stdout + completed.stderr
    return dll_path


def _param(name: str, description: str = "") -> dict[str, object]:
    return {
        "name": name,
        "type": "int",
        "json_type": "integer",
        "description": description or name.replace("_", " "),
        "direction": "in",
    }


def _invocable(
    name: str,
    dll_path: Path,
    *,
    parameters: list[dict[str, object]] | None = None,
    description: str = "",
) -> dict[str, object]:
    return {
        "name": name,
        "description": description,
        "return_type": "int",
        "parameters": parameters or [],
        "execution": {
            "method": "dll_import",
            "dll_path": str(dll_path),
            "function_name": name,
        },
    }


def _probe_ordering_ctx(dll_path: Path) -> SimpleNamespace:
    invocables = [
        _invocable(
            "S02_REM_T2_DangerousUnsupportedCommit",
            dll_path,
            parameters=[_param("amount_cents", "amount in cents")],
            description="dangerous write distractor that should not become early pass-scope work",
        ),
        _invocable("S02_REM_T2_PrereqFalseFriend", dll_path, description="mentions prerequisite but is not required"),
        _invocable(
            "S02_REM_T2_PrereqOpenWindow",
            dll_path,
            parameters=[_param("customer_id", "customer id from BindCustomer")],
            description="requires customer context from S02_REM_T2_PrereqBindCustomer",
        ),
        _invocable("S02_REM_T2_ReadUnlockedCatalog", dll_path, description="read unlocked catalog"),
        _invocable(
            "S02_REM_T2_PrereqBindCustomer",
            dll_path,
            parameters=[_param("customer_id", "customer id")],
            description="bind customer before opening a window",
        ),
        _invocable("S02_REM_T2_StateRead", dll_path, description="read state counter"),
        _invocable("S02_REM_T2_StateIncrement", dll_path, description="increment state counter"),
        _invocable(
            "S02_REM_T2_WriteUnlockedCommit",
            dll_path,
            parameters=[_param("amount_cents", "amount in cents")],
            description="write commit after unlock",
        ),
        _invocable("S02_REM_T2_InitUnlockedSession", dll_path, description="initialize unlocked session"),
    ]
    return SimpleNamespace(
        job_id="job-s02-remaining-tier2-ordering",
        total=len(invocables),
        runtime=SimpleNamespace(
            pass_scope_profile="foundation",
            pass_index=1,
            selected_invocable_names=[
                "S02_REM_T2_InitUnlockedSession",
                "S02_REM_T2_ReadUnlockedCatalog",
                "S02_REM_T2_PrereqBindCustomer",
            ],
        ),
        invocables=invocables,
        call_graph={},
        vocab={"id_formats": ["customer_id", "amount_cents"]},
        unlock_result={
            "unlocked": True,
            "sequence": [
                {"function": "S02_REM_T2_InitUnlockedSession"},
                {"function": "S02_REM_T2_ReadUnlockedCatalog"},
            ],
        },
        explored_count=lambda: 0,
    )


def _install_probe_ordering_capture(monkeypatch: pytest.MonkeyPatch) -> tuple[list[tuple[str, str]], dict[str, object]]:
    status_events: list[tuple[str, str]] = []
    uploads: dict[str, object] = {}

    monkeypatch.setattr(
        probe_ordering,
        "emit_s02_substage_status",
        lambda _ctx, substage_id, _message, *, state: status_events.append((substage_id, state)),
    )
    monkeypatch.setattr(
        curriculum,
        "_upload_to_blob",
        lambda _container, path, payload: uploads.setdefault(path, json.loads(payload.decode("utf-8"))),
    )
    return status_events, uploads


def test_s01_to_s02a_tier2_unlock_handoff_guides_ordering_without_losing_fallback(
    monkeypatch: pytest.MonkeyPatch,
    remaining_tier2_dll: Path,
) -> None:
    """Tier 2 seam: unlock evidence guides S-02A order but remains ordering guidance only."""
    status_events, uploads = _install_probe_ordering_capture(monkeypatch)
    ctx = _probe_ordering_ctx(remaining_tier2_dll)
    original_names = [str(inv["name"]) for inv in ctx.invocables]

    probe_ordering.run_probe_ordering(ctx)

    assert status_events == [("s02_probe_ordering", "start"), ("s02_probe_ordering", "done")]
    ordered_names = [str(inv["name"]) for inv in ctx.invocables]
    assert ordered_names[:2] == ["S02_REM_T2_InitUnlockedSession", "S02_REM_T2_ReadUnlockedCatalog"]
    assert sorted(ordered_names) == sorted(original_names)
    assert "S02_REM_T2_WriteUnlockedCommit" in ordered_names
    assert "S02_REM_T2_DangerousUnsupportedCommit" in ordered_names

    handoff = getattr(ctx, "unlock_ordering_handoff", {})
    assert handoff["claim_boundary"] == "ordering_guidance_only"
    assert handoff["matched_names"] == ["S02_REM_T2_InitUnlockedSession", "S02_REM_T2_ReadUnlockedCatalog"]
    payload = uploads[f"{ctx.job_id}/prerequisite_state_machine.json"]
    assert payload["unlock_ordering_handoff"] == handoff


def test_s02a_tier2_records_prerequisite_dag_as_guidance_not_truth(
    monkeypatch: pytest.MonkeyPatch,
    remaining_tier2_dll: Path,
) -> None:
    """Tier 2 stage: prerequisite-looking evidence is bounded guidance, not final truth."""
    _status_events, uploads = _install_probe_ordering_capture(monkeypatch)
    ctx = _probe_ordering_ctx(remaining_tier2_dll)

    probe_ordering.run_probe_ordering(ctx)

    payload = uploads[f"{ctx.job_id}/prerequisite_state_machine.json"]
    role_rows = {row["name"]: row for row in payload["roles"]}
    assert role_rows["S02_REM_T2_PrereqBindCustomer"]["role"] in {"producer", "consumer", "unknown"}
    assert role_rows["S02_REM_T2_PrereqOpenWindow"]["role"] in {"consumer", "unknown"}
    assert role_rows["S02_REM_T2_PrereqOpenWindow"]["sequence_confidence"] < 1.0
    assert "sequence_reasons" in role_rows["S02_REM_T2_PrereqOpenWindow"]
    assert role_rows["S02_REM_T2_PrereqFalseFriend"]["prerequisites"] == []

    open_window = next(inv for inv in ctx.invocables if inv["name"] == "S02_REM_T2_PrereqOpenWindow")
    assert open_window.get("_sequence_confidence", 0.0) < 1.0
    assert open_window.get("_sequence_reasons") is not None


def test_s02a_tier2_preserves_pass_scope_containment_under_medium_candidates(
    monkeypatch: pytest.MonkeyPatch,
    remaining_tier2_dll: Path,
) -> None:
    """Tier 2 stage: a selected pass scope stays first without dropping fallback candidates."""
    _status_events, uploads = _install_probe_ordering_capture(monkeypatch)
    ctx = _probe_ordering_ctx(remaining_tier2_dll)

    probe_ordering.run_probe_ordering(ctx)

    selected = set(ctx.runtime.selected_invocable_names)
    ordered_names = [str(inv["name"]) for inv in ctx.invocables]
    assert set(ordered_names[: len(selected)]) == selected
    assert "S02_REM_T2_DangerousUnsupportedCommit" in ordered_names[len(selected) :]
    assert "S02_REM_T2_WriteUnlockedCommit" in ordered_names
    assert len(ordered_names) == len(set(ordered_names))

    containment = getattr(ctx, "pass_scope_containment", {})
    assert containment["claim_boundary"] == "scope_ordering_only"
    assert set(containment["matched_names"]) == selected
    payload = uploads[f"{ctx.job_id}/prerequisite_state_machine.json"]
    assert payload["pass_scope_containment"] == containment


def _ctx_for_invocables(
    *,
    job_id: str,
    invocables: list[dict[str, object]],
    max_tool_calls: int | None = None,
) -> ExploreContext:
    runtime = ExploreRuntime(
        max_rounds=0,
        max_tool_calls=max_tool_calls or len(invocables),
        min_direct_probes=1,
        skip_documented=False,
        deterministic_fallback_enabled=True,
        concurrency=1,
    )
    ctx = ExploreContext(
        job_id=job_id,
        runtime=runtime,
        client=object(),
        model="no-model",
        invocables=invocables,
        inv_map={str(inv["name"]): inv for inv in invocables},
        tool_schemas=[],
        total=len(invocables),
    )
    ctx.vocab = {"id_formats": ["customer_id", "amount_cents"]}
    ctx.sentinels = {}
    ctx.unlock_result = {"unlocked": True, "sequence": []}
    return ctx


def _install_quiet_s02_storage(
    monkeypatch: pytest.MonkeyPatch,
    *,
    probe_log: list[dict[str, object]],
) -> list[dict[str, object]]:
    statuses: list[dict[str, object]] = []

    monkeypatch.setattr(s02_status, "_get_job_status", lambda _job_id: {})
    monkeypatch.setattr(s02_status, "_persist_job_status", lambda _job_id, payload: statuses.append(dict(payload)))
    monkeypatch.setattr(s02_status, "_set_explore_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(storage, "_load_findings", lambda _job_id: [])
    monkeypatch.setattr(probe_loop, "_download_blob", lambda *_args, **_kwargs: b"[]")
    monkeypatch.setattr(probe_loop, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_save_stage_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_append_transcript", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_append_executor_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_patch_invocable", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_patch_finding", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_save_finding", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_cancel_requested", lambda _job_id: False)
    monkeypatch.setattr(probe_loop, "_set_explore_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(probe_loop, "_update_vocabulary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe_loop, "_generate_hypothesis", lambda *_args, **_kwargs: {}, raising=False)
    monkeypatch.setattr(
        probe_loop,
        "_append_explore_probe_log",
        lambda _job_id, rows: probe_log.extend(dict(row) for row in rows),
    )
    return statuses


def test_s02c_tier2_preserves_state_effect_lineage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 2 stage: S-02C copies state-effect lineage without rewriting it."""
    ctx = SimpleNamespace(
        job_id="job-s02c-state-effect-preservation-tier2",
        total=2,
        explored_count=lambda: 2,
        sentinels={},
        sentinel_new_codes_this_run=0,
        client=object(),
        model="no-model",
        unlock_result={"unlocked": True, "sequence": []},
        invocables=[],
        dll_strings={},
        vocab={},
    )
    statuses: list[dict[str, object]] = []
    raw_rows = [
        {
            "phase": "deterministic_fallback",
            "function": "S02_REM_T2_StateIncrement",
            "tool": "S02_REM_T2_StateIncrement",
            "args": {},
            "result_excerpt": "Returned: 1",
            "classification": {"status": "observed", "boundary": "raw_execution", "signed": 1},
            "trace": {
                "backend": "dll",
                "function_name": "S02_REM_T2_StateIncrement",
                "raw_result": 1,
                "state_effect": {"counter_before": 0, "counter_after": 1},
            },
        },
        {
            "phase": "deterministic_fallback",
            "function": "S02_REM_T2_StateRead",
            "tool": "S02_REM_T2_StateRead",
            "args": {},
            "result_excerpt": "Returned: 1",
            "classification": {"status": "observed", "boundary": "raw_execution", "signed": 1},
            "trace": {
                "backend": "dll",
                "function_name": "S02_REM_T2_StateRead",
                "raw_result": 1,
                "state_effect": {"counter_observed": 1},
            },
        },
    ]
    uploads: dict[str, object] = {}

    monkeypatch.setattr(s02_status, "_get_job_status", lambda _job_id: {})
    monkeypatch.setattr(s02_status, "_persist_job_status", lambda _job_id, payload: statuses.append(dict(payload)))
    monkeypatch.setattr(s02_status, "_set_explore_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(evidence_capture, "_download_blob", lambda *_args, **_kwargs: json.dumps(raw_rows).encode("utf-8"))
    monkeypatch.setattr(
        evidence_capture,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, json.loads(data.decode("utf-8"))),
    )
    monkeypatch.setattr(evidence_capture, "_name_sentinel_candidates", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(evidence_capture, "_probe_write_unlock", lambda *_args, **_kwargs: None)

    evidence_capture.run_evidence_capture(ctx)

    alias_blob = f"{ctx.job_id}/{evidence_capture.S02C_PROBE_LOG_ALIAS}"
    persisted = uploads[alias_blob]
    assert persisted == raw_rows
    assert persisted[0]["trace"]["state_effect"] == {"counter_before": 0, "counter_after": 1}
    assert persisted[1]["trace"]["state_effect"] == {"counter_observed": 1}


def test_s02c_tier2_recalibration_is_additive_and_does_not_rewrite_probe_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 2 stage: post-probe recalibration adds reviewable hints without editing raw rows."""
    ctx = SimpleNamespace(
        job_id="job-s02c-recalibration-honesty-tier2",
        total=1,
        explored_count=lambda: 1,
        sentinels={},
        sentinel_new_codes_this_run=0,
        client=object(),
        model="no-model",
        unlock_result={"unlocked": True, "sequence": []},
        invocables=[],
        dll_strings={},
        vocab={},
    )
    raw_rows = [
        {
            "phase": "deterministic_fallback",
            "function": "S02_REM_T2_WriteUnlockedCommit",
            "tool": "S02_REM_T2_WriteUnlockedCommit",
            "args": {"amount_cents": 2500},
            "result_excerpt": "Returned: 4294967294",
            "classification": {"status": "ambiguous", "boundary": "raw_execution", "signed": -2},
            "trace": {"backend": "dll", "function_name": "S02_REM_T2_WriteUnlockedCommit", "raw_result": 4294967294},
        }
    ]
    uploads: dict[str, object] = {}
    appended_rows: list[dict[str, object]] = []

    monkeypatch.setattr(s02_status, "_get_job_status", lambda _job_id: {})
    monkeypatch.setattr(s02_status, "_persist_job_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(s02_status, "_set_explore_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(evidence_capture, "_download_blob", lambda *_args, **_kwargs: json.dumps(raw_rows).encode("utf-8"))
    monkeypatch.setattr(
        evidence_capture,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, json.loads(data.decode("utf-8"))),
    )
    monkeypatch.setattr(evidence_capture, "_name_sentinel_candidates", lambda *_args, **_kwargs: {4294967294: "S02_RECAL_NEG2"})
    monkeypatch.setattr(evidence_capture, "_append_explore_probe_log", lambda _job_id, rows: appended_rows.extend(rows))
    monkeypatch.setattr(
        evidence_capture,
        "_probe_write_unlock",
        lambda *_args, **_kwargs: pytest.fail("unlocked ctx should not re-probe write unlock"),
    )

    evidence_capture.run_evidence_capture(ctx)

    alias_blob = f"{ctx.job_id}/{evidence_capture.S02C_PROBE_LOG_ALIAS}"
    assert uploads[alias_blob] == raw_rows
    assert ctx.sentinels == {4294967294: "S02_RECAL_NEG2"}
    assert ctx.sentinel_new_codes_this_run == 1
    assert len(appended_rows) == 1
    assert appended_rows[0]["phase"] == "stage_boundary_name_sentinel_candidates"
    assert appended_rows[0]["args"]["candidate_codes"] == ["0xFFFFFFFE"]


def test_s02c_s03_tier2_missing_observation_defers_without_false_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 2 seam: missing/blocked S-02C evidence stays deferred in S-03."""
    ctx = SimpleNamespace(job_id="job-s02c-s03-missing-deferral-tier2", total=3, explored_count=lambda: 3)
    durable_rows = [
        {
            "phase": "deterministic_fallback",
            "function": "S02_MissingDeferral_Success",
            "tool": "S02_MissingDeferral_Success",
            "args": {"value": 1},
            "result_excerpt": "Returned: 0",
            "classification": {"status": "observed", "boundary": "raw_execution", "has_return": True, "signed": 0},
            "trace": {"backend": "dll", "function_name": "S02_MissingDeferral_Success", "raw_result": 0},
        },
        {
            "phase": "deterministic_fallback",
            "function": "S02_MissingDeferral_Blocked",
            "tool": "S02_MissingDeferral_Blocked",
            "args": {},
            "result_excerpt": "Returned: -5",
            "classification": {"status": "blocked", "boundary": "raw_execution", "has_return": True, "signed": -5},
            "trace": {"backend": "dll", "function_name": "S02_MissingDeferral_Blocked", "raw_result": -5},
        },
        {
            "phase": "deterministic_fallback",
            "function": "S02_MissingDeferral_NoReturn",
            "tool": "S02_MissingDeferral_NoReturn",
            "args": {},
            "result_excerpt": "Exception: timeout",
            "classification": {"status": "unresolved", "boundary": "raw_execution", "has_return": False},
            "trace": {"backend": "deterministic_harness", "function_name": "S02_MissingDeferral_NoReturn"},
        },
    ]
    findings = [
        {"function": "S02_MissingDeferral_Success", "status": "error"},
        {"function": "S02_MissingDeferral_Blocked", "status": "error"},
        {"function": "S02_MissingDeferral_NoReturn", "status": "error"},
        {"function": "S02_MissingDeferral_Absent", "status": "error"},
    ]
    patches: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(reconcile, "_download_blob", lambda _container, blob_name: json.dumps(durable_rows).encode("utf-8"))
    monkeypatch.setattr(reconcile, "_load_findings", lambda _job_id: list(findings))
    monkeypatch.setattr(reconcile, "_patch_finding", lambda _job_id, fn, patch: patches.append((fn, patch)))
    monkeypatch.setattr(reconcile, "_set_explore_status", lambda *_args, **_kwargs: None)

    reconcile._run_phase_4_reconcile(ctx)

    assert [fn for fn, _patch in patches] == ["S02_MissingDeferral_Success"]
    assert patches[0][1]["status"] == "success"
    assert patches[0][1]["working_call"] == {"value": 1}


@pytest.mark.xfail(
    reason=(
        "blocked_at_tier2: current S-02B execution duplicates the read target and drops the "
        "write target under S-02A ordered scope, so ordered S-02A->S-02B->S-02C composition "
        "cannot yet be claimed honestly"
    ),
    strict=True,
)
def test_s02a_s02b_s02c_tier2_bottom_up_ordered_evidence_window(
    monkeypatch: pytest.MonkeyPatch,
    remaining_tier2_dll: Path,
) -> None:
    """Tier 2 bottom-up window: S-02A order becomes S-02B execution and S-02C evidence."""
    _status_events, _uploads = _install_probe_ordering_capture(monkeypatch)
    legacy_probe_log: list[dict[str, object]] = []
    statuses = _install_quiet_s02_storage(monkeypatch, probe_log=legacy_probe_log)
    monkeypatch.setattr(executor, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(executor, "GUI_BRIDGE_SECRET", "")
    ctx = _ctx_for_invocables(
        job_id="job-s02a-s02b-s02c-ordered-window-tier2",
        invocables=[
            _invocable(
                "S02_REM_T2_WriteUnlockedCommit",
                remaining_tier2_dll,
                parameters=[_param("amount_cents", "amount in cents")],
            ),
            _invocable("S02_REM_T2_ReadUnlockedCatalog", remaining_tier2_dll),
            _invocable("S02_REM_T2_StateIncrement", remaining_tier2_dll),
            _invocable("S02_REM_T2_InitUnlockedSession", remaining_tier2_dll),
        ],
        max_tool_calls=4,
    )
    ctx.runtime.selected_invocable_names = [
        "S02_REM_T2_InitUnlockedSession",
        "S02_REM_T2_ReadUnlockedCatalog",
        "S02_REM_T2_StateIncrement",
        "S02_REM_T2_WriteUnlockedCommit",
    ]
    ctx.unlock_result = {
        "unlocked": True,
        "sequence": [
            {"function": "S02_REM_T2_InitUnlockedSession"},
            {"function": "S02_REM_T2_ReadUnlockedCatalog"},
        ],
    }
    uploads: dict[str, object] = {}

    def evidence_download(_container: str, blob_name: str) -> bytes:
        assert blob_name == f"{ctx.job_id}/explore_probe_log.json"
        return json.dumps(legacy_probe_log, default=str).encode("utf-8")

    monkeypatch.setattr(evidence_capture, "_download_blob", evidence_download)
    monkeypatch.setattr(
        evidence_capture,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, json.loads(data.decode("utf-8"))),
    )
    monkeypatch.setattr(evidence_capture, "_name_sentinel_candidates", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(evidence_capture, "_probe_write_unlock", lambda *_args, **_kwargs: None)

    probe_ordering.run_probe_ordering(ctx)
    ordered_names = [str(inv["name"]) for inv in ctx.invocables]
    assert ordered_names[:2] == ["S02_REM_T2_InitUnlockedSession", "S02_REM_T2_ReadUnlockedCatalog"]

    invocation_execution.run_invocation_execution(ctx)
    evidence_capture.run_evidence_capture(ctx)

    s02b_states = [
        row.get("s02_substage_status", {}).get("s02_invocation_execution", {}).get("state")
        for row in statuses
        if row.get("s02_substage_status", {}).get("s02_invocation_execution")
    ]
    s02c_states = [
        row.get("s02_substage_status", {}).get("s02_evidence_capture", {}).get("state")
        for row in statuses
        if row.get("s02_substage_status", {}).get("s02_evidence_capture")
    ]
    assert s02b_states == ["start", "done"]
    assert s02c_states == ["start", "done"]

    executed_rows = [row for row in legacy_probe_log if row.get("phase") == "deterministic_fallback"]
    assert [row["function"] for row in executed_rows] == ordered_names
    alias_blob = f"{ctx.job_id}/{evidence_capture.S02C_PROBE_LOG_ALIAS}"
    assert uploads[alias_blob] == legacy_probe_log
    for expected, persisted in zip(executed_rows, uploads[alias_blob], strict=True):
        assert persisted["function"] == expected["function"]
        assert persisted["args"] == expected["args"]
        assert persisted["result_excerpt"] == expected["result_excerpt"]
        assert persisted["trace"]["function_name"] == expected["trace"]["function_name"]
        assert persisted["classification"] == expected["classification"]
