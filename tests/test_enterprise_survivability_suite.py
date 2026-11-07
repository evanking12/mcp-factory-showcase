from __future__ import annotations

import json

from api.pipeline.core.enterprise_survivability import (
    build_enterprise_survivability_summary,
    write_enterprise_survivability_summary,
)


def test_tier1_one_target_non_comparable_closes_with_packet_boundary() -> None:
    summary = build_enterprise_survivability_summary(
        suite_id="enterprise_survivability",
        case_id="tier1_measurement_terminalization",
        records=[
            {
                "target": "reservation_stage",
                "job_id": "job-timeout",
                "phase": "analyze",
                "measurement_terminalization": {
                    "status": "non_comparable_failure",
                    "reason_code": "analyzer_timeout",
                    "owner": "hard_family_analyze_discovery",
                    "safe_to_compare": False,
                    "evidence_paths": ["measurement-terminalization.json", "run_result.json"],
                },
            }
        ],
        dependency_graph={"reservation_stage": []},
    )

    assert summary["status"] == "non_comparable_failure"
    assert summary["safe_to_compare"] is False
    assert summary["semantic_proof_satisfied"] is False
    assert summary["target_counts"]["non_comparable"] == 1
    assert summary["targets"][0]["target"] == "reservation_stage"
    assert summary["targets"][0]["reason_code"] == "analyzer_timeout"
    assert "measurement-terminalization.json" in summary["targets"][0]["evidence_paths"]


def test_tier2_dependency_blocked_target_is_skipped_not_run_blindly() -> None:
    summary = build_enterprise_survivability_summary(
        suite_id="enterprise_survivability",
        case_id="tier2_dependency_blocked",
        records=[
            {
                "target": "session_bootstrap",
                "job_id": "job-ok",
                "phase": "done",
                "run_authority": {
                    "authority_level": "decision_bearing",
                    "safe_to_steer_next_prompt": True,
                },
            },
            {
                "target": "reservation_stage",
                "job_id": "job-timeout",
                "phase": "analyze",
                "measurement_terminalization": {
                    "status": "non_comparable_failure",
                    "reason_code": "analyzer_timeout",
                    "owner": "hard_family_analyze_discovery",
                    "safe_to_compare": False,
                    "evidence_paths": ["measurement-terminalization.json"],
                },
            },
        ],
        dependency_graph={
            "session_bootstrap": [],
            "reservation_stage": ["session_bootstrap"],
            "release_commit": ["session_bootstrap", "reservation_stage"],
        },
    )

    rows_by_target = {row["target"]: row for row in summary["targets"]}
    assert summary["status"] == "partial_result_with_warnings"
    assert summary["safe_to_compare"] is False
    assert rows_by_target["session_bootstrap"]["state"] == "comparable"
    assert rows_by_target["reservation_stage"]["state"] == "non_comparable"
    assert rows_by_target["release_commit"]["state"] == "skipped_dependency_blocked"
    assert rows_by_target["release_commit"]["reason_code"] == "dependency_blocked"
    assert rows_by_target["release_commit"]["blocked_by"] == ["reservation_stage"]
    assert summary["semantic_proof_satisfied"] is False


def test_support_only_warning_remains_diagnostic_not_semantic_proof() -> None:
    summary = build_enterprise_survivability_summary(
        suite_id="enterprise_survivability",
        case_id="tier2_warning_boundary",
        records=[
            {
                "target": "dispatch_preview",
                "phase": "done",
                "run_authority": {
                    "authority_level": "decision_bearing",
                    "safe_to_steer_next_prompt": True,
                },
                "critical_warnings": [
                    {
                        "code": "support_only_evidence",
                        "message": "support-only result cannot satisfy primary semantic proof",
                    }
                ],
            }
        ],
        dependency_graph={"dispatch_preview": []},
    )

    assert summary["status"] == "comparable_success"
    assert summary["targets"][0]["state"] == "comparable_with_warnings"
    assert summary["targets"][0]["critical_warnings"][0]["code"] == "support_only_evidence"
    assert summary["semantic_proof_satisfied"] is False


def test_branch_invalidation_authority_missing_is_canonical_survivability_blocker() -> None:
    summary = build_enterprise_survivability_summary(
        suite_id="enterprise_survivability",
        case_id="hard01_branch_invalidation",
        records=[
            {
                "target": "audit_trace",
                "phase": "done",
                "run_authority": {
                    "authority_level": "non_authoritative",
                    "safe_to_steer_next_prompt": False,
                },
                "enterprise_survivability_authority": {
                    "authority_name": "enterprise_branch_invalidation_authority",
                    "authority_present": False,
                    "safe_to_compare": False,
                    "blocking_signal": "branch_invalidation_authority_missing",
                    "reason_code": "branch_invalidation_not_verified",
                    "evidence_refs": ["runs/09-audit_trace/findings.json"],
                },
            }
        ],
        dependency_graph={"audit_trace": []},
    )

    row = summary["targets"][0]
    assert summary["status"] == "non_comparable_failure"
    assert row["state"] == "non_comparable"
    assert row["reason_code"] == "branch_invalidation_authority_missing"
    assert row["owner"] == "enterprise_branch_invalidation_authority"
    assert row["evidence_paths"] == ["runs/09-audit_trace/findings.json"]


def test_runner_writer_persists_survivability_summary_from_run_records(tmp_path) -> None:
    summary = write_enterprise_survivability_summary(
        output_dir=tmp_path,
        suite_id="compiled_enterprise_survivability",
        case_id="runner_integration_tier1",
        run_records=[
            {
                "target": "target_a",
                "phase": "done",
                "run_authority": {
                    "authority_level": "decision_bearing",
                    "safe_to_steer_next_prompt": True,
                },
            },
            {
                "target": "target_b",
                "phase": "analyze",
                "measurement_terminalization": {
                    "reason_code": "discovery_empty",
                    "owner": "hard_family_analyze_discovery",
                    "safe_to_compare": False,
                    "evidence_paths": ["measurement-terminalization.json", "run_result.json"],
                },
            },
        ],
        chain_plan=[
            {"target_name": "target_a", "predecessor_targets": []},
            {"target_name": "target_b", "predecessor_targets": ["target_a"]},
            {"target_name": "target_c", "predecessor_targets": ["target_b"]},
        ],
    )

    persisted = json.loads((tmp_path / "enterprise-survivability-summary.json").read_text(encoding="utf-8"))
    rows_by_target = {row["target"]: row for row in persisted["targets"]}
    assert persisted == summary
    assert rows_by_target["target_a"]["state"] == "comparable"
    assert rows_by_target["target_b"]["state"] == "non_comparable"
    assert rows_by_target["target_c"]["state"] == "skipped_dependency_blocked"
    assert persisted["semantic_proof_satisfied"] is False
