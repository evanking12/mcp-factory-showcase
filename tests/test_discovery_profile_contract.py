from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


DISCOVERY_DIR = Path(__file__).resolve().parents[1] / "src" / "discovery"
if str(DISCOVERY_DIR) not in sys.path:
    sys.path.insert(0, str(DISCOVERY_DIR))

DISCOVERY_MAIN_PATH = DISCOVERY_DIR / "main.py"
SPEC = importlib.util.spec_from_file_location("discovery_profile_contract_main", DISCOVERY_MAIN_PATH)
assert SPEC and SPEC.loader
discovery_main = importlib.util.module_from_spec(SPEC)
sys.modules["discovery_profile_contract_main"] = discovery_main
SPEC.loader.exec_module(discovery_main)


def test_strict_dll_keeps_quarantined_analyzers_out_of_required_path() -> None:
    assert discovery_main._profile_allows_analyzer("strict_dll", "dotnet") is True
    assert discovery_main._profile_allows_analyzer("strict_dll", "com") is False
    assert discovery_main._profile_allows_analyzer("strict_dll", "registry") is False
    assert discovery_main._profile_allows_analyzer("strict_dll", "cli") is False


def test_greybox_and_full_surface_preserve_explicit_nondefault_routes() -> None:
    assert discovery_main._profile_allows_analyzer("greybox_dll", "cli") is True
    assert discovery_main._profile_allows_analyzer("greybox_dll", "gui") is False
    assert discovery_main._profile_allows_analyzer("full_surface", "com") is True
    assert discovery_main._profile_allows_analyzer("full_surface", "registry") is True


def test_nonbinary_surfaces_are_quarantined_outside_full_surface() -> None:
    assert discovery_main._profile_supports_file_type("strict_dll", discovery_main.FileType.PYTHON_SCRIPT) is False
    assert discovery_main._profile_supports_file_type("greybox_dll", discovery_main.FileType.OPENAPI_SPEC) is False
    assert discovery_main._profile_supports_file_type("full_surface", discovery_main.FileType.PYTHON_SCRIPT) is True


def test_pe_dll_com_scan_only_runs_under_full_surface() -> None:
    assert discovery_main._should_run_com_analysis(discovery_main.FileType.PE_DLL, "strict_dll") is False
    assert discovery_main._should_run_com_analysis(discovery_main.FileType.PE_DLL, "greybox_dll") is False
    assert discovery_main._should_run_com_analysis(discovery_main.FileType.PE_DLL, "full_surface") is True
