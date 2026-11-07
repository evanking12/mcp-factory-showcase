from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.pipeline.core import s00_s01_handoff
from api.pipeline.s00_setup import static_analysis as s00_static_analysis
from api.pipeline.s00_setup import static_enrichment as s00_static_enrichment


run_s01_module = importlib.import_module("api.pipeline.s01_unlock.__init__")
REPO_ROOT = Path(__file__).resolve().parents[1]
PRESSURE_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "s00_s01_admission_pressure"
PRESSURE_BUILD_SCRIPT = PRESSURE_FIXTURE_ROOT / "build.ps1"

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


def _install_s01_noop_env(monkeypatch) -> None:
    monkeypatch.setattr(run_s01_module, "_set_explore_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(run_s01_module, "_get_job_status", lambda _job_id: {})
    monkeypatch.setattr(run_s01_module, "_persist_job_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(run_s01_module, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(run_s01_module, "_patch_finding", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(run_s01_module, "_execute_tool", lambda *_args, **_kwargs: "")


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


def _build_pressure_dll(tmp_path: Path) -> Path:
    output_root = tmp_path / "pressure-build"
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


def _export_names_from_dll(dll_path: Path) -> list[str]:
    try:
        import pefile  # type: ignore

        pe = pefile.PE(str(dll_path))
        names = [
            symbol.name.decode("utf-8", errors="replace")
            for symbol in pe.DIRECTORY_ENTRY_EXPORT.symbols
            if symbol.name
        ]
        if names:
            return names
    except Exception:
        pass
    return list(PRESSURE_EXPORTS)


def _base_s01_ctx(*, packet: dict[str, object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-breakpoint",
        total=1,
        invocables=[
            {"name": "CS_LegacyInitialize"},
            {"name": "CS_LegacyProcessPayment"},
            {"name": "CS_TargetInitialize"},
            {"name": "CS_TargetProcessPayment"},
            {"name": "CS_GetVersion"},
        ],
        dll_strings={"ids": ["LEGACY-ID"], "emails": [], "all": ["LEGACY-ID"]},
        vocab={"id_formats": ["LEGACY-ID"]},
        sentinels={},
        unlock_result={"unlocked": False, "sequence": [], "notes": "not attempted"},
        write_unlock_block="",
        init_invocables=[],
        already_explored=set(),
        live_findings=[],
        _prior_session={},
        s00_s01_handoff_packet=packet or {},
    )


def test_breakpoint_strong_admitted_targets_reorder_s01_probe_without_mutating_legacy(monkeypatch) -> None:
    """Breakpoint: strong S-00 target guidance must change bounded S-01 work order."""
    monkeypatch.setattr(s00_s01_handoff, "_upload_to_blob", lambda *_args, **_kwargs: None)
    _install_s01_noop_env(monkeypatch)
    captured: dict[str, object] = {}

    def fake_probe(invocables, dll_strings, vocab):
        captured["invocable_names"] = [inv["name"] for inv in invocables]
        captured["dll_strings"] = dll_strings
        captured["vocab"] = vocab
        return {"unlocked": False, "sequence": [], "write_fn_tested": None, "notes": "fixture"}

    monkeypatch.setattr(run_s01_module, "_probe_write_unlock", fake_probe)

    producer_ctx = SimpleNamespace(
        job_id="job-breakpoint-producer",
        sentinels={0xFFFFFFFB: "write denied"},
        use_cases_text="payments",
        vocab={"id_formats": ["CUST-001"], "error_codes": {"0xFFFFFFFB": "write denied"}},
        dll_strings={"ids": ["CUST-001"], "emails": [], "all": ["CUST-001"]},
        static_analysis_result={"binary_strings": {"ids_found": ["CUST-001"], "emails_found": []}},
        call_graph={},
        ghidra_data_types=[],
        invocables=[
            {"name": "CS_LegacyInitialize"},
            {"name": "CS_LegacyProcessPayment"},
            {"name": "CS_TargetInitialize"},
            {"name": "CS_TargetProcessPayment"},
            {"name": "CS_GetVersion"},
        ],
        static_enrichment={
            "schema_version": 1,
            "prerequisite_hints": {
                "strong_init_candidates": ["CS_TargetInitialize"],
                "strong_write_candidates": ["CS_TargetProcessPayment"],
            },
            "ambiguities": [],
            "admission_recommendation": {
                "usable_for_s01_targets": True,
                "admission_risk": "usable_static_hints",
            },
        },
        s00_s01_handoff_packet={},
    )
    packet = s00_s01_handoff.build_s00_s01_handoff_packet(producer_ctx)
    consumer_ctx = _base_s01_ctx(packet=packet)
    original_order = [inv["name"] for inv in consumer_ctx.invocables]

    run_s01_module.run_s01(consumer_ctx)

    assert packet["s01_targets"]["init_candidates"][0] == "CS_TargetInitialize"
    assert packet["s01_targets"]["write_candidates"][0] == "CS_TargetProcessPayment"
    assert "static_enrichment_targets_admitted" in packet["s01_targets"]["quality"]["quality_flags"]
    assert captured["invocable_names"].index("CS_TargetInitialize") < captured["invocable_names"].index(
        "CS_LegacyInitialize"
    )
    assert captured["invocable_names"].index("CS_TargetProcessPayment") < captured["invocable_names"].index(
        "CS_LegacyProcessPayment"
    )
    assert [inv["name"] for inv in consumer_ctx.invocables] == original_order
    assert captured["dll_strings"]["ids"] == ["CUST-001"]
    assert captured["vocab"]["id_formats"] == ["CUST-001"]


def test_breakpoint_thin_packet_records_ambiguity_and_s01_preserves_legacy_order(monkeypatch) -> None:
    """Breakpoint: thin S-00 guidance must be honest and must not over-narrow S-01."""
    monkeypatch.setattr(s00_s01_handoff, "_upload_to_blob", lambda *_args, **_kwargs: None)
    _install_s01_noop_env(monkeypatch)
    captured: dict[str, object] = {}

    def fake_probe(invocables, dll_strings, vocab):
        captured["invocable_names"] = [inv["name"] for inv in invocables]
        captured["dll_strings"] = dll_strings
        captured["vocab"] = vocab
        return {"unlocked": False, "sequence": [], "write_fn_tested": None, "notes": "fixture"}

    monkeypatch.setattr(run_s01_module, "_probe_write_unlock", fake_probe)

    producer_ctx = SimpleNamespace(
        job_id="job-thin-breakpoint",
        sentinels={},
        use_cases_text="",
        vocab={},
        dll_strings={"ids": [], "emails": [], "all": []},
        static_analysis_result={},
        call_graph={},
        ghidra_data_types=[],
        invocables=[{"name": "CS_GetVersion"}],
        static_enrichment={},
        s00_s01_handoff_packet={},
    )
    packet = s00_s01_handoff.build_s00_s01_handoff_packet(producer_ctx)
    consumer_ctx = _base_s01_ctx(packet=packet)

    run_s01_module.run_s01(consumer_ctx)

    assert "static ids surface is thin" in packet["ambiguity_register"]["notes"]
    assert "no calibrated sentinels available" in packet["ambiguity_register"]["notes"]
    assert "no_init_candidates" in packet["s01_targets"]["quality"]["quality_flags"]
    assert captured["invocable_names"] == [
        "CS_LegacyInitialize",
        "CS_LegacyProcessPayment",
        "CS_TargetInitialize",
        "CS_TargetProcessPayment",
        "CS_GetVersion",
    ]
    assert captured["dll_strings"]["ids"] == ["LEGACY-ID"]
    assert captured["vocab"]["id_formats"] == ["LEGACY-ID"]


def test_breakpoint_malformed_packet_falls_back_to_legacy_context(monkeypatch) -> None:
    """Breakpoint: malformed packet storage must not break the S-01 legacy path."""
    _install_s01_noop_env(monkeypatch)
    monkeypatch.setattr(s00_s01_handoff, "_download_blob", lambda *_args, **_kwargs: b"{not-json")
    captured: dict[str, object] = {}

    def fake_probe(invocables, dll_strings, vocab):
        captured["invocable_names"] = [inv["name"] for inv in invocables]
        captured["dll_strings"] = dll_strings
        captured["vocab"] = vocab
        return {"unlocked": False, "sequence": [], "write_fn_tested": None, "notes": "fixture"}

    monkeypatch.setattr(run_s01_module, "_probe_write_unlock", fake_probe)

    ctx = _base_s01_ctx()

    run_s01_module.run_s01(ctx)

    assert captured["invocable_names"] == [
        "CS_LegacyInitialize",
        "CS_LegacyProcessPayment",
        "CS_TargetInitialize",
        "CS_TargetProcessPayment",
        "CS_GetVersion",
    ]
    assert captured["dll_strings"]["ids"] == ["LEGACY-ID"]
    assert captured["vocab"]["id_formats"] == ["LEGACY-ID"]


def test_breakpoint_target_cap_keeps_packet_reviewable(monkeypatch) -> None:
    """Breakpoint: rich target sets must remain bounded before S-01 sees them."""
    monkeypatch.setattr(s00_s01_handoff, "_upload_to_blob", lambda *_args, **_kwargs: None)
    ctx = SimpleNamespace(
        job_id="job-rich-breakpoint",
        sentinels={0xFFFFFFFB: "write denied"},
        use_cases_text="payments",
        vocab={},
        dll_strings={"ids": ["CUST-001"], "emails": [], "all": ["CUST-001"]},
        static_analysis_result={"binary_strings": {"ids_found": ["CUST-001"], "emails_found": []}},
        call_graph={},
        ghidra_data_types=[],
        invocables=(
            [{"name": f"CS_Initialize_{idx}"} for idx in range(20)]
            + [{"name": f"CS_ProcessPayment_{idx}"} for idx in range(20)]
        ),
        static_enrichment={},
        s00_s01_handoff_packet={},
    )

    packet = s00_s01_handoff.build_s00_s01_handoff_packet(ctx)

    assert len(packet["s01_targets"]["init_candidates"]) == 12
    assert len(packet["s01_targets"]["write_candidates"]) == 12
    assert packet["s01_targets"]["quality"]["raw_init_candidate_count"] == 20
    assert packet["s01_targets"]["quality"]["raw_write_candidate_count"] == 20
    assert packet["s01_targets"]["quality"]["target_cap_applied"] is True
    assert "target_cap_applied" in packet["s01_targets"]["quality"]["quality_flags"]
    assert (
        packet["coordination_decision"]["admission_quality"]["coordinator_review_seed"]["categories"][
            "admission_precision"
        ]
        == "cap_applied_review_breadth"
    )


@pytest.mark.skipif(not _has_msvc_toolchain(), reason="MSVC toolchain not available")
def test_compiled_pressure_dll_caps_admission_and_preserves_s01_fallback(monkeypatch, tmp_path: Path) -> None:
    """Pressure pattern: one compiled DLL stresses admission breadth without hard semantics."""
    dll_path = _build_pressure_dll(tmp_path)
    exported_names = set(_export_names_from_dll(dll_path))
    missing_exports = set(PRESSURE_EXPORTS) - exported_names
    assert missing_exports == set()

    monkeypatch.setattr(s00_static_analysis, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(s00_static_enrichment, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(s00_s01_handoff, "_upload_to_blob", lambda *_args, **_kwargs: None)
    _install_s01_noop_env(monkeypatch)

    invocables = [
        {
            "name": name,
            "execution": {"dll_path": str(dll_path)},
            "parameters": [
                {"name": "account_id", "type": "char *", "direction": "in"},
                {"name": "out_value", "type": "char *", "direction": "out"},
            ],
        }
        for name in PRESSURE_EXPORTS
    ]
    ctx = SimpleNamespace(
        job_id="job-compiled-pressure",
        invocables=invocables,
        vocab={},
        sentinels={},
        use_cases_text="compiled pressure admission",
        static_hints_block="",
        dll_strings={},
        static_analysis_result={},
        static_enrichment={},
        call_graph={},
        ghidra_data_types=[],
        s00_s01_handoff_packet={},
    )

    s00_static_analysis._run_phase_0_static(ctx)
    s00_static_enrichment.write_static_enrichment(ctx)
    packet = s00_s01_handoff.build_s00_s01_handoff_packet(ctx)

    assert ctx.static_analysis_result["dll_name"] == "s00_s01_admission_pressure.dll"
    assert "PRESS-ACCOUNT-001" in ctx.dll_strings["ids"]
    assert ctx.static_enrichment["callable_inventory"]["total"] == len(PRESSURE_EXPORTS)
    assert "ghidra_extras_absent" in ctx.static_enrichment["ambiguities"]
    assert "no_prerequisite_hints" in ctx.static_enrichment["ambiguities"]

    quality = packet["s01_targets"]["quality"]
    assert quality["raw_write_candidate_count"] > quality["target_cap"]
    assert len(packet["s01_targets"]["init_candidates"]) > 0
    assert len(packet["s01_targets"]["write_candidates"]) == quality["target_cap"]
    assert quality["target_cap_applied"] is True
    assert "target_cap_applied" in quality["quality_flags"]
    assert "static_enrichment_targets_admitted" in quality["quality_flags"]
    assert packet["deferred_static"]["static_enrichment"]["available"] is True
    assert (
        packet["coordination_decision"]["admission_quality"]["coordinator_review_seed"]["categories"][
            "admission_precision"
        ]
        == "cap_applied_review_breadth"
    )

    captured: dict[str, object] = {}

    def fake_probe(invocables, dll_strings, vocab):
        captured["invocable_names"] = [inv["name"] for inv in invocables]
        captured["dll_strings"] = dll_strings
        captured["vocab"] = vocab
        return {"unlocked": False, "sequence": [], "write_fn_tested": None, "notes": "compiled-pressure"}

    monkeypatch.setattr(run_s01_module, "_probe_write_unlock", fake_probe)
    consumer_ctx = SimpleNamespace(
        job_id="job-compiled-pressure",
        total=1,
        invocables=list(invocables),
        dll_strings={"ids": ["LEGACY-ID"], "emails": [], "all": ["LEGACY-ID"]},
        vocab={"id_formats": ["LEGACY-ID"]},
        sentinels={},
        unlock_result={"unlocked": False, "sequence": [], "notes": "not attempted"},
        write_unlock_block="",
        init_invocables=[],
        already_explored=set(),
        live_findings=[],
        _prior_session={},
        s00_s01_handoff_packet=packet,
    )
    original_order = [inv["name"] for inv in consumer_ctx.invocables]

    run_s01_module.run_s01(consumer_ctx)

    observed_order = captured["invocable_names"]
    assert observed_order.index(packet["s01_targets"]["init_candidates"][0]) < observed_order.index(
        PRESSURE_DISTRACTOR_EXPORTS[0]
    )
    assert observed_order.index(packet["s01_targets"]["write_candidates"][0]) < observed_order.index(
        PRESSURE_DISTRACTOR_EXPORTS[0]
    )
    assert [inv["name"] for inv in consumer_ctx.invocables] == original_order
    assert captured["dll_strings"]["ids"] == ctx.dll_strings["ids"]
    assert captured["vocab"]["id_formats"] == ctx.dll_strings["ids"][:20]
