from __future__ import annotations

import json
import subprocess
import ctypes
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "spectrum_transaction_release_settlement_suite"
PACKAGE_MANIFEST_PATH = FIXTURE_ROOT / "package_manifest.json"
TRUTH_MANIFEST_PATH = FIXTURE_ROOT / "truth_manifest.json"
BUILD_SCRIPT_PATH = FIXTURE_ROOT / "build-package.ps1"
HEADER_PATH = FIXTURE_ROOT / "include" / "spectrum_suite.h"

EXPECTED_SOURCES = {
    "spectrum_session_bootstrap.c",
    "spectrum_reservation_stage.c",
    "spectrum_dispatch_preview.c",
    "spectrum_fee_quote.c",
    "spectrum_attestation_stage.c",
    "spectrum_invoice_sync.c",
    "spectrum_entitlement_sync.c",
    "spectrum_release_commit.c",
    "spectrum_replay_branch.c",
    "spectrum_settlement_reconcile.c",
    "spectrum_audit_trace.c",
    "spectrum_quarantine_gate.c",
    "spectrum_quarantine_audit.c",
}

EXPECTED_DLLS = {
    "spectrum_session_bootstrap.dll",
    "spectrum_reservation_stage.dll",
    "spectrum_dispatch_preview.dll",
    "spectrum_fee_quote.dll",
    "spectrum_attestation_stage.dll",
    "spectrum_invoice_sync.dll",
    "spectrum_entitlement_sync.dll",
    "spectrum_release_commit.dll",
    "spectrum_replay_branch.dll",
    "spectrum_settlement_reconcile.dll",
    "spectrum_audit_trace.dll",
    "spectrum_quarantine_gate.dll",
    "spectrum_quarantine_audit.dll",
}

EXPECTED_SELECTED_TARGETS = [
    "spectrum_session_bootstrap.dll",
    "spectrum_reservation_stage.dll",
    "spectrum_release_commit.dll",
    "spectrum_audit_trace.dll",
]


def _has_msvc_toolchain() -> bool:
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


def test_spectrum_compiled_fixture_layout_and_selected_targets() -> None:
    assert FIXTURE_ROOT.exists()
    assert BUILD_SCRIPT_PATH.exists()
    assert PACKAGE_MANIFEST_PATH.exists()
    assert TRUTH_MANIFEST_PATH.exists()
    assert HEADER_PATH.exists()

    sources = {path.name for path in (FIXTURE_ROOT / "src").glob("*.c")}
    assert sources == EXPECTED_SOURCES

    manifest = json.loads(PACKAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    selected_targets = [row["staged_name"] for row in manifest["selected_runtime_targets"]]
    assert selected_targets == EXPECTED_SELECTED_TARGETS
    assert {row["staged_name"] for row in manifest["bundled_dlls"]} == EXPECTED_DLLS


@pytest.mark.skipif(not _has_msvc_toolchain(), reason="MSVC toolchain not available")
def test_spectrum_compiled_fixture_builds_and_stages_package(tmp_path: Path) -> None:
    manifest = json.loads(PACKAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["stage_root"] = f".tmp/pytest-spectrum/{tmp_path.name}/stage"
    manifest["zip_path"] = f".tmp/pytest-spectrum/{tmp_path.name}/stage.zip"
    manifest_path = tmp_path / "package_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD_SCRIPT_PATH),
            "-ManifestPath",
            str(manifest_path),
        ],
        cwd=str(REPO_ROOT),
        check=True,
    )

    bin_dir = FIXTURE_ROOT / "bin"
    stage_root = REPO_ROOT / manifest["stage_root"]
    zip_path = REPO_ROOT / manifest["zip_path"]
    attach_plan_path = stage_root / "attach-plan.json"
    campaign_request_path = stage_root / "campaign-request.json"

    assert {path.name for path in bin_dir.glob("*.dll")} == EXPECTED_DLLS
    assert {path.name for path in (stage_root / "bin").glob("*.dll")} == EXPECTED_DLLS
    assert zip_path.exists()
    assert attach_plan_path.exists()
    assert campaign_request_path.exists()

    attach_plan = json.loads(attach_plan_path.read_text(encoding="utf-8-sig"))
    assert [row["staged_name"] for row in attach_plan] == EXPECTED_SELECTED_TARGETS


@pytest.mark.skipif(not hasattr(ctypes, "WinDLL"), reason="ctypes WinDLL is Windows-only")
def test_audit_trace_fixture_emits_rejected_bound_invalidation_token() -> None:
    audit_dll = FIXTURE_ROOT / "bin" / "spectrum_audit_trace.dll"
    if not audit_dll.exists():
        pytest.skip("compiled Spectrum audit fixture DLL is not available")

    dll = ctypes.WinDLL(str(audit_dll))
    fn = dll.SP_InvalidateUntrustedBranch
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
    fn.restype = ctypes.c_int

    observed: set[str] = set()
    for _ in range(5):
        output = ctypes.create_string_buffer(64)
        result = fn(b"sp-branch-primary", b"sp-branch-replay", output, 64)
        assert result == 0
        observed.add(output.value.decode("utf-8"))

    assert observed == {"sp-audit-replay-branch-invalidated"}


@pytest.mark.skipif(not hasattr(ctypes, "WinDLL"), reason="ctypes WinDLL is Windows-only")
def test_hard03_quarantine_fixture_emits_object_bound_audit_tokens() -> None:
    gate_dll = FIXTURE_ROOT / "bin" / "spectrum_quarantine_gate.dll"
    audit_dll = FIXTURE_ROOT / "bin" / "spectrum_quarantine_audit.dll"
    if not gate_dll.exists() or not audit_dll.exists():
        pytest.skip("compiled Spectrum quarantine fixture DLLs are not available")

    gate = ctypes.WinDLL(str(gate_dll))
    gate_fn = gate.SP_QuarantineUnsupportedTarget
    gate_fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
    gate_fn.restype = ctypes.c_int

    quarantine_token = ctypes.create_string_buffer(96)
    result = gate_fn(
        b"sp-operator-hard03-operator-session",
        b"sp-resv-ORD-001-4200",
        b"sp-unsupported-target-wire-override",
        quarantine_token,
        96,
    )
    assert result == 0
    assert quarantine_token.value.decode("utf-8") == "sp-quarantine-wire-override-denied"

    audit = ctypes.WinDLL(str(audit_dll))
    audit_fn = audit.SP_RecordUnsupportedTargetQuarantine
    audit_fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
    audit_fn.restype = ctypes.c_int

    audit_token = ctypes.create_string_buffer(96)
    result = audit_fn(
        b"sp-unsupported-target-wire-override",
        quarantine_token.value,
        audit_token,
        96,
    )
    assert result == 0
    assert audit_token.value.decode("utf-8") == "sp-audit-wire-override-quarantined"
