from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.pipeline.core import s00_s01_handoff
from api.pipeline.s00_setup import admission_handoff
from api.pipeline.s00_setup import baseline_truth
from api.pipeline.s00_setup import setup_baseline
from api.pipeline.s00_setup import static_analysis
from api.pipeline.s00_setup import static_enrichment
from api.pipeline.s00_setup import static_evidence
from api.pipeline.s00_setup import status as s00_status
from api.pipeline.s00_setup import vocab_seed


REPO_ROOT = Path(__file__).resolve().parents[1]
PRESSURE_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s00_s01_admission_pressure"
PRESSURE_BUILD_SCRIPT = PRESSURE_FIXTURE_ROOT / "build.ps1"
MEDIUM_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s00_substage_medium_pressure"
MEDIUM_BUILD_SCRIPT = MEDIUM_FIXTURE_ROOT / "build.ps1"

PRESSURE_DISTRACTOR_EXPORTS = [
    "S00P_QueryPressureVersion",
    "S00P_CheckPressureStatus",
    "S00P_ListPressureFamilies",
    "S00P_GetPressureCatalog",
    "S00P_GetPressureCatalogCount",
]
PRESSURE_INIT_EXPORTS = [
    "S00P_InitAccountSession01",
    "S00P_InitAccountSession02",
    "S00P_InitializeLedgerWindow03",
    "S00P_OpenTenantBridge04",
    "S00P_ConnectPressureLane05",
    "S00P_LoginPressureOperator06",
    "S00P_AuthorizePressureAccount07",
    "S00P_StartPressureSession08",
    "S00P_UnlockPressureWorkspace09",
    "S00P_OpenPressureBatch10",
    "S00P_ConnectPressureBatch11",
    "S00P_InitializePressureBatch12",
    "S00P_StartPressureBatch13",
    "S00P_AuthorizePressureBatch14",
    "S00P_LoginPressureBatch15",
]
PRESSURE_WRITE_EXPORTS = [
    "S00P_ProcessPressurePayment01",
    "S00P_WritePressureLedger02",
    "S00P_CommitPressureLedger03",
    "S00P_UpdatePressureAccount04",
    "S00P_SetPressureStatus05",
    "S00P_CreatePressureRecord06",
    "S00P_DeletePressureDraft07",
    "S00P_TransferPressureCredit08",
    "S00P_DebitPressureBalance09",
    "S00P_CreditPressureBalance10",
    "S00P_PayPressureInvoice11",
    "S00P_RedeemPressureCredit12",
    "S00P_ProcessPressureAdjustment13",
    "S00P_WritePressureAudit14",
    "S00P_CommitPressureAudit15",
]
PRESSURE_EXPORTS = PRESSURE_DISTRACTOR_EXPORTS + PRESSURE_WRITE_EXPORTS + PRESSURE_INIT_EXPORTS

MEDIUM_INIT_EXPORTS = [
    "S00M_InitTenantSession01",
    "S00M_InitializeAccountWindow02",
    "S00M_OpenLedgerBridge03",
    "S00M_ConnectOperatorLane04",
    "S00M_LoginBatchWorkspace05",
    "S00M_AuthorizeMediumAccount06",
    "S00M_StartSettlementSession07",
    "S00M_UnlockMediumWorkspace08",
    "S00M_OpenReviewBatch09",
    "S00M_ConnectAuditContext10",
    "S00M_SetupDeferredLedger11",
    "S00M_StartAmbiguityReview12",
    "S00M_OpenNoiseControlledContext13",
    "S00M_InitializeMediumRoute14",
    "S00M_LoginMediumOperator15",
    "S00M_AuthorizeMediumBatch16",
    "S00M_StartMediumCatalog17",
    "S00M_OpenMediumFallback18",
]
MEDIUM_WRITE_EXPORTS = [
    "S00M_ProcessMediumPayment01",
    "S00M_WriteMediumLedger02",
    "S00M_CommitMediumLedger03",
    "S00M_UpdateMediumAccount04",
    "S00M_SetMediumStatus05",
    "S00M_CreateMediumRecord06",
    "S00M_DeleteMediumDraft07",
    "S00M_TransferMediumCredit08",
    "S00M_DebitMediumBalance09",
    "S00M_CreditMediumBalance10",
    "S00M_PayMediumInvoice11",
    "S00M_RedeemMediumCredit12",
    "S00M_ProcessMediumAdjustment13",
    "S00M_WriteMediumAudit14",
    "S00M_CommitMediumAudit15",
    "S00M_UpdateDeferredTarget16",
    "S00M_SetAmbiguousTarget17",
    "S00M_CreateNoisyCandidate18",
    "S00M_ProcessFallbackRecord19",
    "S00M_WriteReviewOutcome20",
    "S00M_CommitReviewOutcome21",
    "S00M_TransferReviewCredit22",
    "S00M_UpdateAuditRoute23",
    "S00M_SetAuditStatus24",
    "S00M_CreateAuditRecord25",
    "S00M_DeleteAuditDraft26",
]
MEDIUM_DISTRACTOR_EXPORTS = [
    "S00M_QueryMediumVersion01",
    "S00M_CheckMediumStatus02",
    "S00M_ListMediumFamilies03",
    "S00M_GetMediumCatalog04",
    "S00M_ReadMediumAudit05",
    "S00M_VerifyMediumRoute06",
    "S00M_ValidateMediumAccount07",
    "S00M_LookupMediumTarget08",
    "S00M_CountMediumCandidates09",
    "S00M_FetchMediumDeferred10",
    "S00M_CalculateMediumPreview11",
    "S00M_MirrorMediumNoise12",
    "S00M_FormatMediumReceipt13",
    "S00M_RenderMediumTemplate14",
    "S00M_ArchiveMediumSnapshot15",
    "S00M_DescribeMediumFamily16",
    "S00M_GetMediumFixtureCatalogCount",
    "S00M_GetMediumFixtureString",
]
MEDIUM_EXPORTS = MEDIUM_INIT_EXPORTS + MEDIUM_WRITE_EXPORTS + MEDIUM_DISTRACTOR_EXPORTS


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
def pressure_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not _has_msvc_toolchain():
        pytest.skip("MSVC toolchain not available")
    output_root = tmp_path_factory.mktemp("s00-substage-pressure")
    completed = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PRESSURE_BUILD_SCRIPT),
            "-OutputRoot",
            str(output_root),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    dll_path = output_root / "bin" / "s00_s01_admission_pressure.dll"
    assert dll_path.exists(), completed.stdout + completed.stderr
    return dll_path


@pytest.fixture(scope="module")
def medium_dll(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not _has_msvc_toolchain():
        pytest.skip("MSVC toolchain not available")
    output_root = tmp_path_factory.mktemp("s00-substage-medium-pressure")
    completed = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(MEDIUM_BUILD_SCRIPT),
            "-OutputRoot",
            str(output_root),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    dll_path = output_root / "bin" / "s00_substage_medium_pressure.dll"
    assert dll_path.exists(), completed.stdout + completed.stderr
    return dll_path


def _install_noop_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(s00_status, "_set_explore_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(s00_status, "_get_job_status", lambda _job_id: {})
    monkeypatch.setattr(s00_status, "_persist_job_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(baseline_truth, "_set_explore_status", lambda *_args, **_kwargs: None)


def _install_noop_uploads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(baseline_truth, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(vocab_seed, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(static_analysis, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(static_enrichment, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(s00_s01_handoff, "_upload_to_blob", lambda *_args, **_kwargs: None)


def _invocables(dll_path: Path, exports: list[str] | None = None) -> list[dict[str, object]]:
    return [
        {
            "name": name,
            "execution": {"dll_path": str(dll_path)},
            "parameters": [
                {"name": "account_id", "type": "char *", "direction": "in"},
                {"name": "out_value", "type": "char *", "direction": "out"},
            ],
        }
        for name in (exports or PRESSURE_EXPORTS)
    ]


def _ctx(dll_path: Path, exports: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-s00-substage-breakpoint",
        total=1,
        invocables=_invocables(dll_path, exports),
        sentinels={},
        sentinel_new_codes_this_run=0,
        vocab={},
        use_cases_text="",
        client=None,
        model="",
        static_hints_block="",
        dll_strings={},
        static_analysis_result={},
        static_enrichment={},
        call_graph={},
        ghidra_data_types=[],
        s00_s01_handoff_packet={},
    )


def test_s00a_tier1_setup_baseline_preserves_hint_and_sentinel_honesty(
    monkeypatch: pytest.MonkeyPatch,
    pressure_dll: Path,
) -> None:
    """Tier 1 anchor: S-00A preserves setup hints and sentinels without inventing static evidence."""
    _install_noop_status(monkeypatch)
    _install_noop_uploads(monkeypatch)
    monkeypatch.setattr(
        baseline_truth,
        "_get_job_status",
        lambda _job_id: {
            "hints": "Customer IDs look like PRESS-ACCOUNT-001 | error 0xFFFFFFFB means write denied",
            "use_cases": "pressure setup baseline",
        },
    )
    monkeypatch.setattr(
        vocab_seed,
        "_get_job_status",
        lambda _job_id: {
            "hints": "Customer IDs look like PRESS-ACCOUNT-001 | error 0xFFFFFFFB means write denied",
            "use_cases": "pressure setup baseline",
        },
    )
    monkeypatch.setattr(
        baseline_truth,
        "_calibrate_sentinels",
        lambda invocables, *_args, **_kwargs: {0xFFFFFFFB: "write denied"} if invocables else {},
    )
    ctx = _ctx(pressure_dll)

    setup_baseline.run_setup_baseline(ctx)

    assert ctx.sentinels == {0xFFFFFFFB: "write denied"}
    assert ctx.vocab["error_codes"]["0xFFFFFFFB"] == "write denied"
    assert ctx.vocab["id_formats"] == ["PRESS-ACCOUNT-001"]
    assert ctx.vocab["user_context"] == "pressure setup baseline"
    assert ctx.dll_strings == {}
    assert ctx.static_analysis_result == {}


def test_s00b_tier1_static_evidence_extracts_compiled_inventory_and_records_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
    pressure_dll: Path,
) -> None:
    """Tier 1 anchor: S-00B extracts compiled static evidence without claiming Ghidra truth."""
    _install_noop_status(monkeypatch)
    _install_noop_uploads(monkeypatch)
    ctx = _ctx(pressure_dll)

    static_evidence.run_static_evidence(ctx)

    assert ctx.static_analysis_result["dll_name"] == "s00_s01_admission_pressure.dll"
    assert "PRESS-ACCOUNT-001" in ctx.dll_strings["ids"]
    assert ctx.static_enrichment["source_status"]["static_analysis"] == "available"
    assert ctx.static_enrichment["source_status"]["ghidra_extras"] == "absent"
    assert ctx.static_enrichment["callable_inventory"]["total"] == len(PRESSURE_EXPORTS)
    assert ctx.static_enrichment["callable_inventory"]["emitted"] == len(PRESSURE_EXPORTS)
    assert "ghidra_extras_absent" in ctx.static_enrichment["ambiguities"]
    assert "no_prerequisite_hints" in ctx.static_enrichment["ambiguities"]


def test_s00c_tier1_admission_handoff_caps_defers_and_keeps_ambiguity_reviewable(
    monkeypatch: pytest.MonkeyPatch,
    pressure_dll: Path,
) -> None:
    """Tier 1 anchor: S-00C packages broad static guidance without over-admitting it."""
    _install_noop_status(monkeypatch)
    _install_noop_uploads(monkeypatch)
    ctx = _ctx(pressure_dll)
    static_evidence.run_static_evidence(ctx)

    packet = admission_handoff.run_admission_handoff(ctx)

    assert packet is not None
    quality = packet["s01_targets"]["quality"]
    assert quality["raw_write_candidate_count"] > quality["target_cap"]
    assert len(packet["s01_targets"]["write_candidates"]) == quality["target_cap"]
    assert quality["target_cap_applied"] is True
    assert "target_cap_applied" in quality["quality_flags"]
    assert "static_enrichment_targets_admitted" in quality["quality_flags"]
    assert packet["deferred_static"]["static_enrichment"]["available"] is True
    assert "static enrichment: ghidra_extras_absent" in packet["ambiguity_register"]["notes"]
    assert "deferred_static" in packet["coordination_decision"]["kept_deferred"]
    assert (
        packet["coordination_decision"]["admission_quality"]["coordinator_review_seed"]["categories"][
            "admission_precision"
        ]
        == "cap_applied_review_breadth"
    )


def test_s00a_tier2_setup_baseline_handles_noisier_hints_and_multiple_sentinels(
    monkeypatch: pytest.MonkeyPatch,
    medium_dll: Path,
) -> None:
    """Tier 2 anchor: S-00A keeps mixed prior context bounded and explicit."""
    _install_noop_status(monkeypatch)
    _install_noop_uploads(monkeypatch)
    hints = (
        "Medium pressure uses MEDACC-ACCOUNT-001 and MEDLED-LEDGER-003 | "
        "operator email ops.medium@example.com | "
        "error code 0xFFFFFFFA = medium account locked. | "
        "0xFFFFFFF9 = medium route deferred."
    )
    monkeypatch.setattr(
        baseline_truth,
        "_get_job_status",
        lambda _job_id: {"hints": hints, "use_cases": "medium setup baseline pressure"},
    )
    monkeypatch.setattr(
        vocab_seed,
        "_get_job_status",
        lambda _job_id: {"hints": hints, "use_cases": "medium setup baseline pressure"},
    )
    monkeypatch.setattr(
        baseline_truth,
        "_calibrate_sentinels",
        lambda invocables, *_args, **_kwargs: {0xFFFFFFFB: "medium write denied"} if invocables else {},
    )
    ctx = _ctx(medium_dll, MEDIUM_EXPORTS)

    setup_baseline.run_setup_baseline(ctx)

    assert len(ctx.invocables) == len(MEDIUM_EXPORTS)
    assert ctx.vocab["id_formats"] == ["MEDACC-ACCOUNT-001", "MEDLED-LEDGER-003"]
    assert ctx.vocab["error_codes"]["0xFFFFFFFB"] == "medium write denied"
    assert ctx.vocab["error_codes"]["0xFFFFFFFA"] == "medium account locked"
    assert ctx.vocab["error_codes"]["0xFFFFFFF9"] == "medium route deferred"
    assert "ops.medium@example.com" in ctx.vocab["notes"]
    assert ctx.vocab["user_context"] == "medium setup baseline pressure"
    assert ctx.dll_strings == {}
    assert ctx.static_analysis_result == {}


def test_s00b_tier2_static_evidence_handles_medium_inventory_caps_and_richer_strings(
    monkeypatch: pytest.MonkeyPatch,
    medium_dll: Path,
) -> None:
    """Tier 2 anchor: S-00B handles richer static evidence without overclaiming."""
    _install_noop_status(monkeypatch)
    _install_noop_uploads(monkeypatch)
    ctx = _ctx(medium_dll, MEDIUM_EXPORTS)

    static_evidence.run_static_evidence(ctx)

    binary_strings = ctx.static_analysis_result["binary_strings"]
    assert ctx.static_analysis_result["dll_name"] == "s00_substage_medium_pressure.dll"
    assert len(binary_strings["ids_found"]) == 30
    assert "MEDACC-ACCOUNT-001" in binary_strings["ids_found"]
    assert "MEDSPL-SPLIT-030" in binary_strings["ids_found"]
    assert len(binary_strings["emails_found"]) >= 4
    assert "ops.medium@example.com" in binary_strings["emails_found"]
    assert "ACTIVE" in binary_strings["status_tokens"]
    assert len(binary_strings["format_strings"]) >= 5
    assert ctx.static_enrichment["callable_inventory"]["total"] == len(MEDIUM_EXPORTS)
    assert ctx.static_enrichment["callable_inventory"]["emitted"] == ctx.static_enrichment["callable_inventory"]["cap"]
    assert ctx.static_enrichment["callable_inventory"]["cap"] == 50
    assert ctx.static_enrichment["source_status"]["static_analysis"] == "available"
    assert ctx.static_enrichment["source_status"]["ghidra_extras"] == "absent"
    assert "ghidra_extras_absent" in ctx.static_enrichment["ambiguities"]


def test_s00c_tier2_admission_handoff_preserves_caps_and_reviewable_deferred_static(
    monkeypatch: pytest.MonkeyPatch,
    medium_dll: Path,
) -> None:
    """Tier 2 anchor: S-00C admits a bounded slice under medium static pressure."""
    _install_noop_status(monkeypatch)
    _install_noop_uploads(monkeypatch)
    ctx = _ctx(medium_dll, MEDIUM_EXPORTS)
    static_evidence.run_static_evidence(ctx)

    packet = admission_handoff.run_admission_handoff(ctx)

    quality = packet["s01_targets"]["quality"]
    assert quality["target_cap"] == 12
    assert (
        quality["raw_init_candidate_count"] > quality["target_cap"]
        or quality["raw_write_candidate_count"] > quality["target_cap"]
    )
    assert len(packet["s01_targets"]["init_candidates"]) == quality["target_cap"]
    assert len(packet["s01_targets"]["write_candidates"]) == quality["target_cap"]
    assert packet["s01_targets"]["focus_ids"] == ctx.dll_strings["ids"][:12]
    assert "MEDACC-ACCOUNT-001" in packet["s01_targets"]["focus_ids"]
    assert quality["target_cap_applied"] is True
    assert "target_cap_applied" in quality["quality_flags"]
    assert "static_enrichment_targets_admitted" in quality["quality_flags"]
    static_summary = packet["surface_inventory"]["static_enrichment_summary"]
    assert static_summary["callable_total"] == len(MEDIUM_EXPORTS)
    assert static_summary["callable_emitted"] == 50
    assert static_summary["admission_risk"] == "usable_static_hints"
    assert packet["deferred_static"]["static_enrichment"]["available"] is True
    assert "static enrichment: ghidra_extras_absent" in packet["ambiguity_register"]["notes"]
    assert (
        packet["coordination_decision"]["admission_quality"]["coordinator_review_seed"]["categories"][
            "admission_precision"
        ]
        == "cap_applied_review_breadth"
    )
