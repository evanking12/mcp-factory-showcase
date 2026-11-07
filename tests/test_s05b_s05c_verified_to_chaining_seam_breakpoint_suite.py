from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.pipeline.s05_enrichment import mc5_chain_reads
from api.pipeline.s05_enrichment import read_to_write_chaining
from api.pipeline.s05_enrichment import status as s05_status
from api.pipeline.s05_enrichment import verification_replay
from api.pipeline.s05_enrichment import verify as verify_mod
from api.services import executor


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s05b_s05c_verified_to_chaining_seam"
BUILD_SCRIPT = FIXTURE_ROOT / "build.ps1"
DLL_NAME = "s05b_s05c_verified_to_chaining_seam.dll"


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
def seam_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not _has_msvc_toolchain():
        pytest.skip("MSVC toolchain not available")
    output_root = tmp_path_factory.mktemp("s05b-s05c-verified-to-chaining-seam")
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


def _ctx(job_id: str, dll_path: Path) -> SimpleNamespace:
    names = [
        "S05_SEAM_ReadVerifiedCustomer",
        "S05_SEAM_ReadInferredWouldPass",
        "S05_SEAM_ReadPartialWouldPass",
        "S05_SEAM_ReadFailedWouldPass",
        "S05_SEAM_ReadStateDrift",
        "S05_SEAM_WriteCustomer",
    ]
    inv_map = {
        name: _invocable(name, dll_path)
        for name in names
        if name != "S05_SEAM_ReadVerifiedCustomer"
    }
    inv_map["S05_SEAM_ReadVerifiedCustomer"] = _invocable(
        "S05_SEAM_ReadVerifiedCustomer",
        dll_path,
        [
            {
                "name": "out_customer_id",
                "type": "char *",
                "direction": "out",
                "resolved_type": "LPSTR",
                "description": "output customer identifier",
            },
            {"name": "out_customer_id_size", "type": "unsigned int"},
        ],
    )
    inv_map["S05_SEAM_WriteCustomer"] = _invocable(
        "S05_SEAM_WriteCustomer",
        dll_path,
        [{"name": "customer_id", "type": "const char *", "json_type": "string"}],
    )
    return SimpleNamespace(
        job_id=job_id,
        _state={"explored": len(names)},
        total=len(names),
        init_invocables=[],
        sentinels={0xFFFFFFFD: "not initialized"},
        inv_map=inv_map,
        invocables=list(inv_map.values()),
        unlock_result={},
        vocab={"id_formats": ["CUST-\\d+"]},
        evidence_candidates=None,
        _lock=None,
        live_findings=[],
        explored_count=lambda: len(names),
    )


def _seed_findings() -> list[dict[str, object]]:
    return [
        {
            "function": "S05_SEAM_ReadVerifiedCustomer",
            "status": "success",
            "verification": "verified",
            "working_call": {"args": {"out_customer_id": "", "out_customer_id_size": 32}},
        },
        {
            "function": "S05_SEAM_ReadInferredWouldPass",
            "status": "success",
            "verification": "inferred",
            "working_call": {"args": {}},
        },
        {
            "function": "S05_SEAM_ReadPartialWouldPass",
            "status": "partial",
            "verification": "inferred",
            "working_call": {"args": {}},
        },
        {
            "function": "S05_SEAM_ReadFailedWouldPass",
            "status": "failure",
            "verification": "error",
            "working_call": {"args": {}},
        },
        {
            "function": "S05_SEAM_ReadStateDrift",
            "status": "verified_success",
            "verification": "verified",
            "working_call": {"args": {}},
        },
        {
            "function": "S05_SEAM_WriteCustomer",
            "status": "unresolved",
            "verification": "",
            "working_call": None,
        },
    ]


def _install_seam_storage(
    monkeypatch: pytest.MonkeyPatch,
    findings: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    uploads: dict[str, object] = {}
    decisions: list[dict[str, object]] = []
    persisted: list[dict[str, object]] = []
    retry_inputs: list[dict[str, object]] = []

    def upload(_container: str, path: str, payload: bytes | str) -> None:
        raw = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
        uploads[path] = json.loads(raw)

    def patch_finding(_job_id: str, function: str, patch: dict[str, object]) -> None:
        for row in findings:
            if row.get("function") == function:
                row.update(patch)
                return
        raise AssertionError(f"patch target not found: {function}")

    def build_retry_plan(_selection, *, extracted_ids, evidence_ids, id_formats, available_id_kinds_override):
        retry_inputs.append(
            {
                "extracted_ids": list(extracted_ids),
                "evidence_ids": list(evidence_ids),
                "id_formats": list(id_formats),
                "available_id_kinds_override": set(available_id_kinds_override),
            }
        )
        return [
            {
                "function": "S05_SEAM_WriteCustomer",
                "fallback": "retry_ranked_candidates",
                "priority": 10,
                "cluster": "write",
            }
        ]

    monkeypatch.setattr(verify_mod, "_load_findings", lambda _job_id: findings)
    monkeypatch.setattr(verify_mod, "_download_blob", lambda _container, _path: b"[]")
    monkeypatch.setattr(verify_mod, "_upload_to_blob", upload)
    monkeypatch.setattr(verify_mod, "_patch_finding", patch_finding)
    monkeypatch.setattr(verify_mod, "_get_job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(verify_mod, "_persist_job_status", lambda _job_id, payload: persisted.append(payload))
    monkeypatch.setattr(verify_mod, "_set_explore_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(mc5_chain_reads, "_load_findings", lambda _job_id: findings)
    monkeypatch.setattr(mc5_chain_reads, "_load_s03_retry_surface", lambda _ctx: {})
    monkeypatch.setattr(
        mc5_chain_reads,
        "_build_write_arg_candidates",
        lambda _ctx: ({"S05_SEAM_WriteCustomer": [{"customer_id": "CUST-100"}]}, {"S05_SEAM_WriteCustomer": [{"source": "unit"}]}),
    )
    monkeypatch.setattr(mc5_chain_reads, "_build_write_retry_plan", build_retry_plan)
    monkeypatch.setattr(mc5_chain_reads, "_targeted_unlock_attempt", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(mc5_chain_reads, "_persist_mc_decision", lambda _ctx, _name, decision: decisions.append(decision))
    monkeypatch.setattr(s05_status, "_get_job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(s05_status, "_persist_job_status", lambda _job_id, payload: persisted.append(payload))
    monkeypatch.setattr(s05_status, "_set_explore_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(executor, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(executor, "GUI_BRIDGE_SECRET", "")
    return uploads, decisions, persisted, retry_inputs


def test_s05b_s05c_tier2_preserves_verified_to_chaining_boundary(
    monkeypatch: pytest.MonkeyPatch,
    seam_dll: Path,
) -> None:
    findings = _seed_findings()
    uploads, decisions, persisted, retry_inputs = _install_seam_storage(monkeypatch, findings)
    ctx = _ctx("job-s05b-s05c-seam", seam_dll)

    verification_replay.run_verification_replay(ctx)
    read_to_write_chaining.run_read_to_write_chaining(ctx)

    report = uploads["job-s05b-s05c-seam/verification-report.json"]
    assert report["verified_count"] == 1
    assert report["state_drift_count"] == 1
    assert report["total_checked"] == 2
    report_entries = {entry["function"]: entry for entry in report["entries"]}
    assert set(report_entries) == {"S05_SEAM_ReadVerifiedCustomer", "S05_SEAM_ReadStateDrift"}
    assert report_entries["S05_SEAM_ReadVerifiedCustomer"]["preserved_working_call"]["out_customer_id"] == "CUST-100"
    assert report_entries["S05_SEAM_ReadStateDrift"]["verification"] == "state_drift"

    by_function = {str(row["function"]): row for row in findings}
    verified_read = by_function["S05_SEAM_ReadVerifiedCustomer"]
    assert verified_read["status"] == "verified_success"
    assert verified_read["verification"] == "verified"
    assert verified_read["working_call"]["out_customer_id"] == "CUST-100"
    assert by_function["S05_SEAM_ReadInferredWouldPass"]["verification"] == "inferred"
    assert by_function["S05_SEAM_ReadPartialWouldPass"]["status"] == "partial"
    assert by_function["S05_SEAM_ReadFailedWouldPass"]["status"] == "failure"
    assert by_function["S05_SEAM_ReadStateDrift"]["verification"] == "state_drift"
    assert by_function["S05_SEAM_ReadStateDrift"]["working_call"] is None

    assert retry_inputs == [
        {
            "extracted_ids": ["CUST-100"],
            "evidence_ids": [],
            "id_formats": ["CUST-\\d+"],
            "available_id_kinds_override": set(),
        }
    ]
    decision = decisions[0]
    analysis = decision["analysis"]
    assert analysis["verified_read_count"] == 1
    assert analysis["extracted_ids"] == ["CUST-100"]
    assert analysis["retryable_functions"] == ["S05_SEAM_WriteCustomer"]
    assert analysis["retry_plan"][0]["function"] == "S05_SEAM_WriteCustomer"
    assert decision["action"] == "chain_read_outputs_to_write_inputs"
    assert "still blocked" in str(decision["result"])

    states = [
        row.get("s05_stage_status", {}).get(stage, {}).get("state")
        for row in persisted
        for stage in ("s05_verification_replay", "s05_read_to_write_chaining")
        if row.get("s05_stage_status", {}).get(stage)
    ]
    assert states.count("start") >= 2
    assert states.count("done") >= 2
