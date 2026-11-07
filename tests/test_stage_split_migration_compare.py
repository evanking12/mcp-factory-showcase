from __future__ import annotations

import json
from pathlib import Path

from api.analysis.stage_split_migration_compare import compare_phase1_migration


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_stage_index(status_s04r: str = "skipped") -> dict:
    return {
        "stages": [
            {"id": "S-00", "status": "completed", "skip_reason": ""},
            {"id": "S-01", "status": "completed", "skip_reason": ""},
            {"id": "S-02", "status": "completed", "skip_reason": ""},
            {"id": "S-04R", "status": status_s04r, "skip_reason": "floor_broadening_blocked"},
            {"id": "S-07", "status": "completed", "skip_reason": ""},
        ]
    }


def _make_transition_index() -> dict:
    return {
        "transitions": [
            {"id": "T-04", "status": "pass"},
            {"id": "T-05", "status": "pass"},
            {"id": "T-14", "status": "pass"},
            {"id": "T-15", "status": "pass"},
        ]
    }


def _make_reader_checks(pass_all: bool = True) -> dict:
    return {
        "checks": [
            {"id": "route_session_packaging", "pass": pass_all},
            {"id": "operator_cohesion", "pass": pass_all},
            {"id": "harness_collector", "pass": pass_all},
            {"id": "morning_report", "pass": pass_all},
        ]
    }


def _make_root_summary(pass_all: bool = True) -> dict:
    return {
        "clean_root_or_not": "pass" if pass_all else "fail",
        "stale_or_mixed_root": "pass" if pass_all else "fail",
    }


def _seed_session(
    root: Path,
    *,
    with_candidate_outputs: bool = False,
    reader_pass: bool = True,
    root_pass: bool = True,
    s04r_status: str = "skipped",
) -> None:
    _write_json(root / "stage-index.json", _make_stage_index(status_s04r=s04r_status))
    _write_json(root / "transition-index.json", _make_transition_index())
    _write_text(root / "evidence/stage-02-probe-loop/probe-log.json", "legacy probe log")
    _write_text(root / "evidence/stage-02-probe-loop/findings.json", "legacy findings")
    _write_text(root / "evidence/stage-02-probe-loop/probe-strategy-summary.json", "legacy strategy")
    _write_text(root / "evidence/stage-02-probe-loop/probe-round-reasoning.json", "legacy reasoning")
    _write_text(root / "diagnostics/probe-log.json", "diag")
    _write_text(root / "stage-01-probe-loop/schema-before.json", "{}")
    _write_text(root / "stage-01-probe-loop/schema-after.json", "{}")
    _write_text(root / "explore_probe_log.json", "compat")
    _write_json(root / "reader-compatibility.json", _make_reader_checks(pass_all=reader_pass))
    _write_json(root / "root_integrity_validation/validation-summary.json", _make_root_summary(pass_all=root_pass))
    if with_candidate_outputs:
        _write_text(root / "evidence/stage-03-surface-inventory/surface-inventory.json", "surface inventory")
        _write_text(root / "evidence/stage-03-surface-inventory/stage-context.txt", "stage context")
        _write_text(root / "evidence/stage-04-frontier-ranking/frontier-ranking.json", "frontier ranking")
        _write_text(root / "evidence/stage-04-frontier-ranking/probe-strategy-summary.json", "new strategy")
        _write_text(root / "evidence/stage-06-bounded-local-probe/probe-log.json", "new probe log")
        _write_text(root / "evidence/stage-06-bounded-local-probe/findings.json", "new findings")
        _write_text(root / "evidence/stage-06-bounded-local-probe/probe-user-message-sample.txt", "sample")
        _write_text(root / "evidence/stage-06-bounded-local-probe/probe-round-reasoning.json", "new reasoning")
        _write_text(root / "evidence/stage-06-bounded-local-probe/probe-stop-reasons.json", "stop")
        _write_text(root / "evidence/stage-06-bounded-local-probe/param-rename-decisions.json", "params")


def _claims_payload(*, include_all_claims: bool = True) -> dict:
    payload = {
        "required_classification_surfaces": [
            "evidence/stage-03-surface-inventory/surface-inventory.json",
            "evidence/stage-04-frontier-ranking/frontier-ranking.json",
            "evidence/stage-06-bounded-local-probe/probe-log.json",
        ],
        "preserved_contract_checks": [
            {
                "check_id": "aliases",
                "surface": "legacy_s02_aliases",
                "bucket": "must_remain_equivalent",
                "expected_contract": "aliases still readable",
                "compare_mode": "all_candidate_paths_exist",
                "candidate_paths": [
                    "evidence/stage-02-probe-loop/probe-log.json",
                    "evidence/stage-02-probe-loop/findings.json",
                    "diagnostics/probe-log.json",
                    "stage-01-probe-loop/schema-before.json",
                    "stage-01-probe-loop/schema-after.json",
                    "explore_probe_log.json",
                ],
            },
            {
                "check_id": "stage-index",
                "surface": "stage-index.json",
                "bucket": "must_remain_equivalent",
                "baseline_source": "stage-index.json",
                "candidate_source": "stage-index.json",
                "expected_contract": "7-stage truth remains canonical",
                "compare_mode": "stage_index_equivalent",
            },
            {
                "check_id": "transition-index",
                "surface": "transition-index.json",
                "bucket": "must_remain_equivalent",
                "baseline_source": "transition-index.json",
                "candidate_source": "transition-index.json",
                "expected_contract": "transition truth remains canonical",
                "compare_mode": "transition_index_equivalent",
            },
            {
                "check_id": "s04r",
                "surface": "S-04R",
                "bucket": "must_remain_equivalent",
                "baseline_source": "stage-index.json",
                "candidate_source": "stage-index.json",
                "expected_contract": "S-04R semantics unchanged",
                "compare_mode": "stage_row_equivalent",
                "row_id": "S-04R",
            },
            {
                "check_id": "reader-checks",
                "surface": "reader_checks",
                "bucket": "must_remain_equivalent",
                "candidate_source": "reader-compatibility.json",
                "expected_contract": "reader checks green",
                "compare_mode": "reader_checks_all_pass",
                "required_reader_ids": [
                    "route_session_packaging",
                    "operator_cohesion",
                    "harness_collector",
                    "morning_report",
                ],
            },
            {
                "check_id": "root-integrity",
                "surface": "root_integrity",
                "bucket": "must_remain_equivalent",
                "candidate_source": "root_integrity_validation/validation-summary.json",
                "expected_contract": "root integrity pass",
                "compare_mode": "root_integrity_pass",
            },
        ],
        "difference_claims": [
            {
                "difference_claim_id": "strategy-diff",
                "check_id": "strategy-diff",
                "surface": "evidence/stage-04-frontier-ranking/probe-strategy-summary.json",
                "bucket": "allowed_to_differ_only_with_explicit_claim",
                "baseline_source": "evidence/stage-02-probe-loop/probe-strategy-summary.json",
                "candidate_source": "evidence/stage-04-frontier-ranking/probe-strategy-summary.json",
                "expected_contract": "decomposed strategy output",
                "compare_mode": "file_diff_exists",
                "justification": "strategy output moved to N-04 owner",
            }
        ],
        "improvement_claims": [
            {
                "check_id": "n03-out",
                "surface": "evidence/stage-03-surface-inventory/surface-inventory.json",
                "bucket": "allowed_to_improve",
                "candidate_source": "evidence/stage-03-surface-inventory/surface-inventory.json",
                "expected_contract": "new additive N-03 output exists",
                "compare_mode": "candidate_exists",
            },
            {
                "check_id": "n04-out",
                "surface": "evidence/stage-04-frontier-ranking/frontier-ranking.json",
                "bucket": "allowed_to_improve",
                "candidate_source": "evidence/stage-04-frontier-ranking/frontier-ranking.json",
                "expected_contract": "new additive N-04 output exists",
                "compare_mode": "candidate_exists",
            },
            {
                "check_id": "n06-out",
                "surface": "evidence/stage-06-bounded-local-probe/probe-log.json",
                "bucket": "allowed_to_improve",
                "candidate_source": "evidence/stage-06-bounded-local-probe/probe-log.json",
                "expected_contract": "new additive N-06 output exists",
                "compare_mode": "candidate_exists",
            },
        ],
    }
    if not include_all_claims:
        payload["improvement_claims"] = payload["improvement_claims"][:2]
    return payload


def test_compare_phase1_migration_confirms_additive_improvement(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    claims = tmp_path / "claims.json"
    _seed_session(baseline)
    _seed_session(candidate, with_candidate_outputs=True)
    _write_json(claims, _claims_payload())

    result = compare_phase1_migration(baseline, candidate, claims)

    assert result["overall_verdict"] == "improvement_confirmed"
    assert result["blocked_regressions"] == []
    assert result["unclassified_differences"] == []


def test_compare_phase1_migration_blocks_unclassified_difference(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    claims = tmp_path / "claims.json"
    _seed_session(baseline)
    _seed_session(candidate, with_candidate_outputs=True)
    _write_json(claims, _claims_payload(include_all_claims=False))

    result = compare_phase1_migration(baseline, candidate, claims)

    assert result["overall_verdict"] == "unclassified_difference"
    assert any(item["surface"] == "evidence/stage-06-bounded-local-probe/probe-log.json" for item in result["unclassified_differences"])


def test_compare_phase1_migration_blocks_preserved_contract_break(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    claims = tmp_path / "claims.json"
    _seed_session(baseline)
    _seed_session(candidate, with_candidate_outputs=True, reader_pass=False)
    _write_json(claims, _claims_payload())

    result = compare_phase1_migration(baseline, candidate, claims)

    assert result["overall_verdict"] == "blocked_regression"
    assert any(item["surface"] == "reader_checks" for item in result["blocked_regressions"])


def test_compare_phase1_migration_blocks_missing_named_reader_check(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    claims = tmp_path / "claims.json"
    _seed_session(baseline)
    _seed_session(candidate, with_candidate_outputs=True)
    _write_json(candidate / "reader-compatibility.json", {"checks": [{"id": "route_session_packaging", "pass": True}]})
    _write_json(claims, _claims_payload())

    result = compare_phase1_migration(baseline, candidate, claims)

    assert result["overall_verdict"] == "blocked_regression"
    assert any("required reader ids missing" in " ".join(item["notes"]) for item in result["blocked_regressions"])


def test_compare_phase1_migration_blocks_s04r_semantic_drift(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    claims = tmp_path / "claims.json"
    _seed_session(baseline)
    _seed_session(candidate, with_candidate_outputs=True, s04r_status="completed")
    _write_json(claims, _claims_payload())

    result = compare_phase1_migration(baseline, candidate, claims)

    assert result["overall_verdict"] == "blocked_regression"
    assert any(item["surface"] == "S-04R" for item in result["blocked_regressions"])
