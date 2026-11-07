"""Tests for Save-Session v2 helpers in scripts/ops/collect_session.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

# Import module under test (scripts package is not always on path as 'scripts.ops')
_COLLECT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "ops" / "collect_session.py"
_SPEC = importlib.util.spec_from_file_location("collect_session_v2_test_harness", _COLLECT_PATH)
assert _SPEC and _SPEC.loader
collect_session = importlib.util.module_from_spec(_SPEC)
sys.modules["collect_session_v2_test_harness"] = collect_session
_SPEC.loader.exec_module(collect_session)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _minimal_contract(dir_path: Path) -> None:
    """Four required JSON files with version 1.0 (cohesion gates soft)."""
    _write_json(
        dir_path / "session-meta.json",
        {
            "job_id": "j1",
            "component": "contoso_cs",
            "functions_total": 3,
            "analysis_profile": "strict_dll",
        },
    )
    _write_json(
        dir_path / "stage-index.json",
        {"version": "1.0", "stages": []},
    )
    _write_json(
        dir_path / "transition-index.json",
        {"version": "1.0", "transitions": []},
    )
    _write_json(
        dir_path / "cohesion-report.json",
        {
            "version": "1.0",
            "gates": {"hard_fail": False},
            "summary": {},
            "totals": {},
        },
    )


def test_validate_contract_strict_passes_with_minimal_files(tmp_path: Path) -> None:
    d = tmp_path / "sess"
    d.mkdir()
    _minimal_contract(d)
    result = collect_session._validate_contract(d, "strict")
    assert result.valid is True
    assert result.missing == []
    assert result.parse_errors == []


def test_validate_contract_fails_when_cohesion_missing(tmp_path: Path) -> None:
    d = tmp_path / "sess"
    d.mkdir()
    _write_json(d / "session-meta.json", {"job_id": "j1"})
    _write_json(d / "stage-index.json", {"version": "1.0", "stages": []})
    _write_json(d / "transition-index.json", {"version": "1.0", "transitions": []})
    result = collect_session._validate_contract(d, "strict")
    assert result.valid is False
    assert "cohesion-report.json" in result.missing


def test_run_validity_invalid_when_contract_invalid(tmp_path: Path) -> None:
    from api.pipeline.core.handoff_contract import AUDITOR_VERSION, CONTRACT_VERSION

    d = tmp_path / "sess"
    d.mkdir()
    bad = collect_session.ContractResult(
        valid=False,
        missing=["cohesion-report.json"],
        parse_errors=[],
        hard_fail=False,
        parsed={},
    )
    status_counts = {
        "total": 2,
        "verified_rate": 0.5,
        "discovered_rate": 1.0,
        "counts": {},
        "verified": 1,
        "discovered": 2,
    }
    rv = collect_session._build_run_validity(
        contract=bad,
        component="contoso_cs",
        analysis_profile="strict_dll",
        status_counts=status_counts,
        invocable_count=12,
    )
    assert rv["valid"] is False
    assert rv["contract_version"] == CONTRACT_VERSION
    assert rv["auditor_version"] == AUDITOR_VERSION
    assert "contract.invalid" in rv["reasons"]
    assert "contract.missing:cohesion-report.json" in rv["reasons"]


def test_run_validity_invalid_on_hard_fail(tmp_path: Path) -> None:
    good_parse = {
        "session-meta.json": {"analysis_profile": "strict_dll"},
        "stage-index.json": {"version": "1.0", "stages": []},
        "transition-index.json": {"version": "1.0", "transitions": []},
        "cohesion-report.json": {"version": "1.0", "gates": {"hard_fail": True}},
    }
    contract = collect_session.ContractResult(
        valid=True,
        missing=[],
        parse_errors=[],
        hard_fail=True,
        parsed=good_parse,
    )
    status_counts = {
        "total": 5,
        "verified_rate": 0.2,
        "discovered_rate": 0.4,
        "counts": {},
        "verified": 1,
        "discovered": 2,
    }
    rv = collect_session._build_run_validity(
        contract=contract,
        component="contoso_cs",
        analysis_profile="strict_dll",
        status_counts=status_counts,
        invocable_count=12,
    )
    assert rv["valid"] is False
    assert "cohesion.hard_fail" in rv["reasons"]


def test_run_validity_surfaces_contract_parse_errors() -> None:
    bad = collect_session.ContractResult(
        valid=False,
        missing=[],
        parse_errors=["stage-index.json: invalid JSON"],
        hard_fail=False,
        parsed={},
    )
    status_counts = {
        "total": 2,
        "verified_rate": 0.0,
        "discovered_rate": 0.0,
        "counts": {},
        "verified": 0,
        "discovered": 0,
    }
    rv = collect_session._build_run_validity(
        contract=bad,
        component="contoso_cs",
        analysis_profile="strict_dll",
        status_counts=status_counts,
        invocable_count=12,
    )
    assert rv["valid"] is False
    assert "contract.parse_error:stage-index.json:_invalid_JSON" in rv["reasons"]


def test_status_normalization_maps_legacy_success(tmp_path: Path) -> None:
    findings = [
        {"function": "A", "status": "success"},
        {"function": "B", "status": "error"},
    ]
    counts = collect_session._compute_status_counts(findings)
    assert counts["counts"]["verified_success"] == 1
    assert counts["counts"]["failure"] == 1


def test_status_counts_scope_to_required_semantic_checkpoint() -> None:
    findings = [
        {"function": "SP_OpenOperatorSession", "status": "success"},
    ]

    counts = collect_session._compute_status_counts(
        findings,
        {"required_semantic_checkpoint": "SP_CommitRelease"},
    )

    assert counts["total"] == 1
    assert counts["counts"]["verified_success"] == 0
    assert counts["counts"]["unknown"] == 1
    assert counts["function_statuses"] == {"SP_CommitRelease": "unknown"}


def test_fixture_rejects_full_surface_profile(tmp_path: Path) -> None:
    ok = collect_session.ContractResult(
        valid=True,
        missing=[],
        parse_errors=[],
        hard_fail=False,
        parsed={"session-meta.json": {}},
    )
    status_counts = {"total": 3, "verified_rate": 0, "discovered_rate": 0, "counts": {}, "verified": 0, "discovered": 0}
    rv = collect_session._build_run_validity(
        contract=ok,
        component="contoso_cs",
        analysis_profile="full_surface",
        status_counts=status_counts,
        invocable_count=10,
    )
    assert rv["valid"] is False
    assert "analysis_profile.full_surface_for_fixture" in rv["reasons"]
