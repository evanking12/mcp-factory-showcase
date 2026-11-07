from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.pipeline.s05_enrichment import backfill as backfill_mod
from api.pipeline.s05_enrichment import mc5_chain_reads
from api.pipeline.s05_enrichment import read_to_write_chaining
from api.pipeline.s05_enrichment import schema_backfill
from api.pipeline.s05_enrichment import status as s05_status
from api.pipeline.s05_enrichment import verification_replay
from api.pipeline.s05_enrichment import verify as verify_mod
from api.services import executor


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s05_full_family_tier2_baseline"
BUILD_SCRIPT = FIXTURE_ROOT / "build.ps1"
DLL_NAME = "s05_full_family_tier2_baseline.dll"


def _has_msvc_toolchain() -> bool:
    if sys.platform != "win32":
        return False
    vswhere = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
    if vswhere.exists():
        return True
    return any(
        Path(path).exists()
        for path in (
            r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat",
            r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
            r"C:\Program Files\Microsoft Visual Studio\2022\Professional\Common7\Tools\VsDevCmd.bat",
            r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\Tools\VsDevCmd.bat",
        )
    )


@pytest.fixture(scope="module")
def s05_family_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not _has_msvc_toolchain():
        pytest.skip("MSVC toolchain not available")
    output_root = tmp_path_factory.mktemp("s05-full-family-tier2")
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
    dll_path = output_root / "bin" / DLL_NAME
    assert dll_path.exists(), completed.stdout + completed.stderr
    return dll_path


def _invocable(name: str, dll_path: Path, parameters: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "name": name,
        "type": "function",
        "return_type": "int",
        "parameters": parameters or [],
        "execution": {
            "method": "dll_import",
            "dll_path": str(dll_path),
            "function_name": name,
        },
    }


def _param(name: str, type_name: str = "int", **extra: object) -> dict[str, object]:
    row: dict[str, object] = {"name": name, "type": type_name, "json_type": "integer"}
    row.update(extra)
    return row


def _install_s05_status(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    persisted: list[dict[str, object]] = []
    monkeypatch.setattr(s05_status, "_get_job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(s05_status, "_persist_job_status", lambda _job_id, payload: persisted.append(payload))
    monkeypatch.setattr(s05_status, "_set_explore_status", lambda *args, **kwargs: None)
    return persisted


def test_s05a_remaining_tier2_schema_boundaries_and_s04_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    uploads: dict[str, object] = {}
    snapshots: list[str] = []
    persisted = _install_s05_status(monkeypatch)

    def upload(_container: str, path: str, payload: bytes | str) -> None:
        raw = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
        uploads[path] = json.loads(raw)

    monkeypatch.setattr(
        backfill_mod,
        "_backfill_schema_from_synthesis",
        lambda *_args, **_kwargs: {
            "patches_requested": 4,
            "patches_applied": 2,
            "patched_functions": ["S05A_ReadSupported", "S05A_WriteWeakProse"],
        },
    )
    monkeypatch.setattr(backfill_mod, "_upload_to_blob", upload)
    monkeypatch.setattr(backfill_mod, "_snapshot_schema_stage", lambda _job_id, name: snapshots.append(name))
    monkeypatch.setattr(backfill_mod, "_set_explore_status", lambda *args, **kwargs: None)

    ctx = SimpleNamespace(
        job_id="job-s05a-full-family",
        total=4,
        client=object(),
        model="unit-model",
        invocables=[
            {"name": "S05A_ReadSupported", "description": "existing read", "parameters": []},
            {"name": "S05A_WriteWeakProse", "description": "", "parameters": [{"name": "customer_id"}]},
            {"name": "S05A_UnsupportedNoEvidence", "description": "", "parameters": []},
            {"name": "S05A_CompatExistingSchema", "description": "do not corrupt", "parameters": [{"name": "amount"}]},
        ],
        explored_count=lambda: 4,
    )
    report = (
        "S-04 synthesis says S05A_ReadSupported is observed. "
        "S05A_WriteWeakProse is plausible prose only. "
        "S05A_UnsupportedNoEvidence has no proof."
    )

    schema_backfill.run_schema_backfill(ctx, report)

    result = uploads["job-s05a-full-family/backfill_result.json"]
    provenance = result["provenance"]
    rows = {row["function"]: row for row in provenance["rows"]}
    assert result["patches_requested"] == 4
    assert result["patches_applied"] == 2
    assert provenance["function_count"] == 4
    assert provenance["proof_boundary"] == "schema_enrichment_not_verification"
    assert all(row["verification"] == "not_verified_by_s05a" for row in rows.values())
    assert all(row["proof_boundary"] == "schema_enrichment_not_verification" for row in rows.values())
    assert rows["S05A_ReadSupported"]["patch_applied"] is True
    assert rows["S05A_WriteWeakProse"]["patch_applied"] is True
    assert rows["S05A_UnsupportedNoEvidence"]["patch_applied"] is False
    assert rows["S05A_CompatExistingSchema"]["patch_applied"] is False
    assert rows["S05A_ReadSupported"]["source"] == "s04_synthesis_report"
    assert rows["S05A_CompatExistingSchema"]["source"] == "schema_only"
    assert [inv["name"] for inv in ctx.invocables] == [
        "S05A_ReadSupported",
        "S05A_WriteWeakProse",
        "S05A_UnsupportedNoEvidence",
        "S05A_CompatExistingSchema",
    ]
    assert set(snapshots) == {"mcp_schema_post_discovery.json", "mcp_schema_pre_gap_resolution.json"}
    assert any(
        row.get("s05_stage_status", {}).get("s05_schema_backfill", {}).get("state") == "done"
        for row in persisted
    )


def test_s05a_s05b_tier2_boundary_does_not_launder_enrichment_into_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploads: dict[str, object] = {}
    findings = [
        {
            "function": "S05A_ReadSupported",
            "status": "success",
            "verification": "",
            "working_call": None,
        },
        {
            "function": "S05A_WriteWeakProse",
            "status": "partial",
            "verification": "inferred",
            "working_call": None,
        },
    ]

    def upload(_container: str, path: str, payload: bytes | str) -> None:
        raw = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
        uploads[path] = json.loads(raw)

    monkeypatch.setattr(
        backfill_mod,
        "_backfill_schema_from_synthesis",
        lambda *_args, **_kwargs: {
            "patches_requested": 2,
            "patches_applied": 2,
            "patched_functions": ["S05A_ReadSupported", "S05A_WriteWeakProse"],
        },
    )
    monkeypatch.setattr(backfill_mod, "_upload_to_blob", upload)
    monkeypatch.setattr(backfill_mod, "_snapshot_schema_stage", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(backfill_mod, "_set_explore_status", lambda *args, **kwargs: None)
    verify_uploads, patches, _persisted = _install_verify_storage(monkeypatch, findings, [])

    ctx = SimpleNamespace(
        job_id="job-s05a-s05b-boundary",
        total=2,
        client=object(),
        model="unit-model",
        invocables=[
            {"name": "S05A_ReadSupported", "parameters": []},
            {"name": "S05A_WriteWeakProse", "parameters": []},
        ],
        inv_map={},
        init_invocables=[],
        sentinels={},
        _state={"explored": 2},
        explored_count=lambda: 2,
    )

    schema_backfill.run_schema_backfill(ctx, "S04 prose confidently describes both functions.")
    verification_replay.run_verification_replay(ctx)

    provenance = uploads["job-s05a-s05b-boundary/backfill_result.json"]["provenance"]
    assert all(row["verification"] == "not_verified_by_s05a" for row in provenance["rows"])
    report = verify_uploads["job-s05a-s05b-boundary/verification-report.json"]
    assert report["total_checked"] == 0
    assert report["verified_count"] == 0
    assert patches == []


def _install_verify_storage(
    monkeypatch: pytest.MonkeyPatch,
    findings: list[dict[str, object]],
    probe_log: list[dict[str, object]] | None = None,
) -> tuple[dict[str, object], list[tuple[str, dict[str, object]]], list[dict[str, object]]]:
    uploads: dict[str, object] = {}
    patches: list[tuple[str, dict[str, object]]] = []
    persisted = _install_s05_status(monkeypatch)

    def upload(_container: str, path: str, payload: bytes | str) -> None:
        raw = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
        uploads[path] = json.loads(raw)

    def patch(_job_id: str, function: str, payload: dict[str, object]) -> None:
        patches.append((function, payload))
        for row in findings:
            if row.get("function") == function:
                row.update(payload)
                return

    monkeypatch.setattr(verify_mod, "_load_findings", lambda _job_id: findings)
    monkeypatch.setattr(verify_mod, "_download_blob", lambda _container, _path: json.dumps(probe_log or []).encode())
    monkeypatch.setattr(verify_mod, "_upload_to_blob", upload)
    monkeypatch.setattr(verify_mod, "_patch_finding", patch)
    monkeypatch.setattr(verify_mod, "_get_job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(verify_mod, "_persist_job_status", lambda _job_id, payload: persisted.append(payload))
    monkeypatch.setattr(verify_mod, "_set_explore_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(executor, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(executor, "GUI_BRIDGE_SECRET", "")
    return uploads, patches, persisted


def test_s05b_remaining_tier2_replay_patch_and_partial_coverage_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    s05_family_dll: Path,
) -> None:
    findings: list[dict[str, object]] = [
        {"function": "S05BASE_ReplayOk", "status": "success", "working_call": {"args": {}}},
        {"function": "S05BASE_StateDrift", "status": "success", "working_call": {"args": {}}},
        {"function": "S05BASE_EchoInt", "status": "success", "working_call": {"args": {"value": 42}}},
        {"function": "S05BASE_Unsupported", "status": "success", "working_call": {"args": {}}},
        {"function": "S05BASE_MissingWorkingCall", "status": "success", "working_call": None},
        {"function": "S05FAM_create", "status": "success", "working_call": {"args": {}}},
        {"function": "S05FAM_read", "status": "success", "working_call": {"args": {"handle": 0}}},
        {"function": "S05FAM_write", "status": "failure", "working_call": None},
    ]
    probe_log: list[dict[str, object]] = [
        {
            "function": "S05FAM_write",
            "phase": "deterministic_fallback",
            "probe_id": "S05FAM_write:deterministic_fallback",
            "args": {"handle": 0, "value": 123},
            "result_excerpt": "Returned: 77",
            "classification": {"has_return": True, "format_guess": "integer"},
        }
    ]
    uploads, patches, persisted = _install_verify_storage(monkeypatch, findings, probe_log)
    inv_map = {
        "S05BASE_ReplayOk": _invocable("S05BASE_ReplayOk", s05_family_dll),
        "S05BASE_StateDrift": _invocable("S05BASE_StateDrift", s05_family_dll),
        "S05BASE_EchoInt": _invocable("S05BASE_EchoInt", s05_family_dll, [_param("value")]),
        "S05FAM_create": _invocable("S05FAM_create", s05_family_dll),
        "S05FAM_write": _invocable("S05FAM_write", s05_family_dll, [_param("handle"), _param("value")]),
        "S05FAM_read": _invocable("S05FAM_read", s05_family_dll, [_param("handle")]),
    }
    ctx = SimpleNamespace(
        job_id="job-s05b-full-family",
        _state={"explored": len(findings)},
        total=len(findings),
        init_invocables=[],
        sentinels={0xFFFFFFFD: "not initialized"},
        inv_map=inv_map,
        invocables=list(inv_map.values()),
        explored_count=lambda: len(findings),
    )

    verification_replay.run_verification_replay(ctx)

    report = uploads["job-s05b-full-family/verification-report.json"]
    entries = {entry["function"]: entry for entry in report["entries"]}
    patches_by_fn = {fn: patch for fn, patch in patches}
    assert "S05BASE_Unsupported" not in entries
    assert "S05BASE_MissingWorkingCall" not in entries
    assert entries["S05BASE_ReplayOk"]["verification"] == "verified"
    assert entries["S05BASE_StateDrift"]["verification"] == "state_drift"
    assert entries["S05BASE_EchoInt"]["args"] == {"value": 42}
    assert patches_by_fn["S05BASE_ReplayOk"]["status_canonical"] == "verified_success"
    assert patches_by_fn["S05BASE_ReplayOk"]["direct_target_truth"]["source"] == "s05_finding"
    assert patches_by_fn["S05BASE_StateDrift"]["direct_target_truth"]["rejected_by_verification"] is True
    assert patches_by_fn["S05BASE_EchoInt"]["working_call"]["value"] == 42
    assert entries["S05FAM_write"]["verification_mode"] == "stateful_mutator"
    assert entries["S05FAM_write"]["promotion_decision"] == "not_promoted"
    assert entries["S05FAM_write"]["custom_return_semantics"]["requires_effect_evidence"] is True
    assert "S05FAM_write" not in patches_by_fn
    assert report["total_checked"] == len(entries)
    assert report["total_checked"] < len(findings)
    assert any(
        row.get("s05_stage_status", {}).get("s05_verification_replay", {}).get("state") == "done"
        for row in persisted
    )


@pytest.mark.xfail(strict=True, reason="blocked_at_tier2: local DLL replay does not preserve same-session state effects")
def test_s05b_state_effect_verification_tier2_attempt_exposes_session_state_blocker(
    monkeypatch: pytest.MonkeyPatch,
    s05_family_dll: Path,
) -> None:
    findings: list[dict[str, object]] = [
        {"function": "S05FAM_create", "status": "success", "working_call": {"args": {}}},
        {"function": "S05FAM_read", "status": "success", "working_call": {"args": {"handle": 0}}},
        {"function": "S05FAM_write", "status": "failure", "working_call": None},
    ]
    probe_log: list[dict[str, object]] = [
        {
            "function": "S05FAM_write",
            "phase": "deterministic_fallback",
            "probe_id": "S05FAM_write:deterministic_fallback",
            "args": {"handle": 0, "value": 123},
            "result_excerpt": "Returned: 77",
            "classification": {"has_return": True, "format_guess": "integer"},
        }
    ]
    uploads, _patches, _persisted = _install_verify_storage(monkeypatch, findings, probe_log)
    inv_map = {
        "S05FAM_create": _invocable("S05FAM_create", s05_family_dll),
        "S05FAM_write": _invocable("S05FAM_write", s05_family_dll, [_param("handle"), _param("value")]),
        "S05FAM_read": _invocable("S05FAM_read", s05_family_dll, [_param("handle")]),
    }
    ctx = SimpleNamespace(
        job_id="job-s05b-state-effect-blocker",
        _state={"explored": len(findings)},
        total=len(findings),
        init_invocables=[],
        sentinels={0xFFFFFFFD: "not initialized"},
        inv_map=inv_map,
        invocables=list(inv_map.values()),
        explored_count=lambda: len(findings),
    )

    verification_replay.run_verification_replay(ctx)

    entry = {
        row["function"]: row
        for row in uploads["job-s05b-state-effect-blocker/verification-report.json"]["entries"]
    }["S05FAM_write"]
    assert entry["promotion_decision"] == "promoted"


def _install_mc5_storage(
    monkeypatch: pytest.MonkeyPatch,
    findings: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    decisions: list[dict[str, object]] = []
    persisted = _install_s05_status(monkeypatch)
    monkeypatch.setattr(mc5_chain_reads, "_load_findings", lambda _job_id: findings)
    monkeypatch.setattr(mc5_chain_reads, "_load_s03_retry_surface", lambda _ctx: {})
    monkeypatch.setattr(mc5_chain_reads, "_targeted_unlock_attempt", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(mc5_chain_reads, "_persist_mc_decision", lambda _ctx, _name, decision: decisions.append(decision))
    return decisions, persisted


def _mc5_ctx(job_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        job_id=job_id,
        total=5,
        unlock_result={},
        vocab={"id_formats": ["CUST-\\d+", "ORD-\\d+"]},
        invocables=[
            {
                "name": "S05C_WriteCustomer",
                "parameters": [
                    {"name": "customer_id", "type": "const char *", "json_type": "string"},
                    {"name": "amount", "type": "int", "json_type": "integer"},
                ],
            },
            {
                "name": "S05C_WriteAuditDistractor",
                "parameters": [{"name": "audit_id", "type": "const char *", "json_type": "string"}],
            },
        ],
        evidence_candidates=None,
        _lock=None,
        live_findings=[],
        explored_count=lambda: 5,
    )


def test_s05c_remaining_tier2_decision_durability_and_deferral(monkeypatch: pytest.MonkeyPatch) -> None:
    findings = [
        {
            "function": "S05C_ReadVerifiedCustomer",
            "status": "verified_success",
            "verification": "verified",
            "working_call": {"customer_id": "CUST-200", "amount": 25},
        },
        {
            "function": "S05C_ReadWeakCustomer",
            "status": "success",
            "verification": "inferred",
            "working_call": {"customer_id": "CUST-999"},
        },
        {
            "function": "S05C_WriteCustomer",
            "status": "unresolved",
            "working_call": None,
        },
    ]
    decisions, persisted = _install_mc5_storage(monkeypatch, findings)

    read_to_write_chaining.run_read_to_write_chaining(_mc5_ctx("job-s05c-full-family"))

    decision = decisions[0]
    analysis = decision["analysis"]
    assert analysis["verified_read_count"] == 1
    assert analysis["extracted_ids"] == ["CUST-200"]
    assert "CUST-999" not in analysis["extracted_ids"]
    assert analysis["retry_plan"]
    assert decision["action"] == "chain_read_outputs_to_write_inputs"
    assert "still blocked" in str(decision["result"])
    assert analysis["retry_rationale"]["verified_read_count"] == 1
    assert analysis["candidate_examples"]
    assert analysis["candidate_selection"]
    assert any(
        row.get("s05_stage_status", {}).get("s05_read_to_write_chaining", {}).get("state") == "done"
        for row in persisted
    )


@pytest.mark.xfail(strict=True, reason="blocked_at_tier2: MC-5 retry planning still includes write distractors")
def test_s05c_retry_containment_tier2_attempt_exposes_widening_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    findings = [
        {
            "function": "S05C_ReadVerifiedCustomer",
            "status": "verified_success",
            "verification": "verified",
            "working_call": {"customer_id": "CUST-200"},
        },
        {"function": "S05C_WriteCustomer", "status": "unresolved", "working_call": None},
    ]
    decisions, _persisted = _install_mc5_storage(monkeypatch, findings)

    read_to_write_chaining.run_read_to_write_chaining(_mc5_ctx("job-s05c-retry-containment"))

    retryable = decisions[0]["analysis"]["retryable_functions"]
    assert retryable == ["S05C_WriteCustomer"]


@pytest.mark.xfail(strict=True, reason="blocked_at_tier2: no explicit S-05C decision consumer in S-06 handoff yet")
def test_s05c_s06_deferral_handoff_requires_explicit_consumer_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    findings = [
        {"function": "S05C_WriteCustomer", "status": "unresolved", "working_call": None},
    ]
    decisions, _persisted = _install_mc5_storage(monkeypatch, findings)

    read_to_write_chaining.run_read_to_write_chaining(_mc5_ctx("job-s05c-s06-handoff"))

    decision = decisions[0]
    assert decision["analysis"].get("s06_handoff_boundary") == "explicit_unresolved_deferral"


def test_s05a_s05b_s05c_bottom_up_window_keeps_enrichment_verification_and_chaining_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    s05_family_dll: Path,
) -> None:
    uploads: dict[str, object] = {}
    findings = [
        {
            "function": "S05BU_ReadCustomer",
            "status": "success",
            "verification": "",
            "working_call": {"args": {"out_customer_id": "", "out_customer_id_size": 32}},
        },
        {
            "function": "S05C_ReadInferredCustomer",
            "status": "success",
            "verification": "inferred",
            "working_call": {"customer_id": "CUST-999"},
        },
        {"function": "S05C_WriteCustomer", "status": "unresolved", "working_call": None},
    ]
    decisions, _persisted = _install_mc5_storage(monkeypatch, findings)

    def upload(_container: str, path: str, payload: bytes | str) -> None:
        raw = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
        uploads[path] = json.loads(raw)

    monkeypatch.setattr(
        backfill_mod,
        "_backfill_schema_from_synthesis",
        lambda *_args, **_kwargs: {
            "patches_requested": 2,
            "patches_applied": 1,
            "patched_functions": ["S05C_ReadVerifiedCustomer"],
        },
    )
    monkeypatch.setattr(backfill_mod, "_upload_to_blob", upload)
    monkeypatch.setattr(backfill_mod, "_snapshot_schema_stage", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(backfill_mod, "_set_explore_status", lambda *args, **kwargs: None)
    verify_uploads, _patches, _verify_persisted = _install_verify_storage(monkeypatch, findings, [])

    ctx = SimpleNamespace(
        job_id="job-s05-bottom-up",
        total=3,
        client=object(),
        model="unit-model",
        invocables=[
            {"name": "S05BU_ReadCustomer", "parameters": []},
            {"name": "S05C_ReadInferredCustomer", "parameters": []},
            {"name": "S05C_WriteCustomer", "parameters": [{"name": "customer_id"}]},
        ],
        inv_map={
            "S05BU_ReadCustomer": _invocable(
                "S05BU_ReadCustomer",
                s05_family_dll,
                [
                    {
                        "name": "out_customer_id",
                        "type": "char *",
                        "direction": "out",
                        "resolved_type": "LPSTR",
                        "description": "output customer id",
                    },
                    {"name": "out_customer_id_size", "type": "unsigned int"},
                ],
            ),
        },
        init_invocables=[],
        sentinels={0xFFFFFFFD: "not initialized"},
        _state={"explored": 3},
        explored_count=lambda: 3,
    )
    schema_backfill.run_schema_backfill(ctx, "Synthesis mentions S05BU_ReadCustomer only.")
    verification_replay.run_verification_replay(ctx)
    read_to_write_chaining.run_read_to_write_chaining(_mc5_ctx("job-s05-bottom-up"))

    provenance = uploads["job-s05-bottom-up/backfill_result.json"]["provenance"]
    rows = {row["function"]: row for row in provenance["rows"]}
    assert rows["S05BU_ReadCustomer"]["proof_boundary"] == "schema_enrichment_not_verification"
    assert rows["S05C_ReadInferredCustomer"]["patch_applied"] is False
    report = verify_uploads["job-s05-bottom-up/verification-report.json"]
    assert report["verified_count"] == 1
    assert findings[0]["status"] == "verified_success"
    assert findings[0]["working_call"]["out_customer_id"] == "CUST-300"
    assert decisions[0]["analysis"]["extracted_ids"] == ["CUST-300"]
    assert decisions[0]["analysis"]["verified_read_count"] == 1
