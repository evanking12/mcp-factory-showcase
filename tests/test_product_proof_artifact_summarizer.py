from __future__ import annotations

import json
from pathlib import Path

from scripts.regression.summarize_product_proof_artifacts import summarize_product_proof_artifacts


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_missing_proof_root_fails_closed(tmp_path: Path) -> None:
    output = tmp_path / "summary.json"

    summary = summarize_product_proof_artifacts(
        proof_root=tmp_path / "missing",
        target="audit_trace",
        output=output,
    )

    assert summary["blocking_signal"] == "proof_root_missing"
    assert summary["product_green_claimed"] is False
    assert summary["safe_to_compare"] is False
    assert json.loads(output.read_text(encoding="utf-8"))["blocking_signal"] == "proof_root_missing"


def test_summary_extracts_first_non_comparable_target(tmp_path: Path) -> None:
    root = tmp_path / "proof"
    _write_json(
        root / "enterprise-survivability-summary.json",
        {
            "case_id": "hard-02",
            "claim_ceiling": "enterprise_survivability_only",
            "target_counts": {"comparable": 8, "non_comparable": 1},
            "targets": [
                {"target": "settlement_reconcile", "state": "comparable", "safe_to_compare": True},
                {
                    "target": "audit_trace",
                    "state": "non_comparable",
                    "safe_to_compare": False,
                    "reason_code": "stale_attestation_invalidation_precondition_unmet",
                    "phase": "done",
                    "job_id": "job-audit",
                },
            ],
        },
    )

    summary = summarize_product_proof_artifacts(proof_root=root, target="audit_trace")

    assert summary["first_blocker"]["target"] == "audit_trace"
    assert summary["blocking_signal"] == "stale_attestation_invalidation_precondition_unmet"
    assert summary["target_counts"]["non_comparable"] == 1


def test_summary_extracts_target_finding_and_authority(tmp_path: Path) -> None:
    root = tmp_path / "proof"
    target_dir = root / "runs" / "09-audit_trace"
    _write_json(root / "enterprise-survivability-summary.json", {"targets": []})
    _write_json(target_dir / "run-authority.json", {"authority_level": "non_authoritative", "authoritative_proving": False})
    _write_json(target_dir / "run_result.json", {"phase": "done", "status": "failed"})
    _write_json(
        target_dir / "findings.json",
        [
            {"function": "SP_OpenOperatorSession", "status_canonical": "verified_success", "working_call": {}},
            {
                "function": "SP_RecordStaleAttestationInvalidation",
                "status": "functional_precondition_unmet",
                "status_canonical": "functional_precondition_unmet",
                "working_call": None,
            },
        ],
    )

    summary = summarize_product_proof_artifacts(proof_root=root, target="audit_trace")

    assert summary["target_status"]["authority_level"] == "non_authoritative"
    assert summary["target_status"]["status"] == "failed"
    assert summary["final_function_status"]["function"] == "SP_RecordStaleAttestationInvalidation"
    assert summary["blocking_signal"] == "functional_precondition_unmet"


def test_successful_final_finding_is_not_a_blocking_signal(tmp_path: Path) -> None:
    root = tmp_path / "proof"
    target_dir = root / "runs" / "09-audit_trace"
    _write_json(root / "enterprise-survivability-summary.json", {"safe_to_compare": True, "targets": []})
    _write_json(target_dir / "run-authority.json", {"authority_level": "decision_bearing", "authoritative_proving": True})
    _write_json(target_dir / "run_result.json", {"phase": "done", "status": "ok"})
    _write_json(
        target_dir / "findings.json",
        [{"function": "SP_RecordStaleAttestationInvalidation", "status_canonical": "verified_success"}],
    )

    summary = summarize_product_proof_artifacts(proof_root=root, target="audit_trace")

    assert summary["blocking_signal"] == ""
    assert summary["safe_to_compare"] is True


def test_summary_never_claims_product_green(tmp_path: Path) -> None:
    root = tmp_path / "proof"
    _write_json(root / "compiled-ingest-summary.json", {"green_contract_level": "product_green", "blocking_signal": ""})
    _write_json(root / "enterprise-survivability-summary.json", {"safe_to_compare": True, "targets": []})

    summary = summarize_product_proof_artifacts(proof_root=root, target="audit_trace")

    assert summary["diagnostic_only"] is True
    assert summary["product_green_claimed"] is False


def test_summary_extracts_sharper_analyzer_runtime_signal(tmp_path: Path) -> None:
    root = tmp_path / "proof"
    target_dir = root / "runs" / "02-reservation_stage"
    _write_json(
        root / "enterprise-survivability-summary.json",
        {
            "safe_to_compare": False,
            "targets": [
                {
                    "target": "reservation_stage",
                    "state": "non_comparable",
                    "safe_to_compare": False,
                    "reason_code": "analyzer_timeout",
                    "phase": "analyze",
                    "job_id": "job-reservation",
                }
            ],
        },
    )
    _write_json(
        target_dir / "measurement-terminalization.json",
        {"reason_code": "analyzer_timeout"},
    )
    _write_json(
        target_dir / "analyzer-runtime-authority.json",
        {
            "status": "non_comparable_analyzer_runtime_stall",
            "reason_code": "child_wrapper_wait_return_missing",
            "runtime_phase": "discovery_child_wait_start",
            "phase_history": [
                {"phase": "discovery_child_started"},
                {"phase": "discovery_child_wait_start"},
            ],
            "child_runtime_phase": "bootstrap_main_returned",
            "child_runtime_diagnostic": {
                "phase": "bootstrap_main_returned",
                "last_observation": {"returncode": 0},
                "phase_history": [{"phase": "bootstrap_main_returned"}],
            },
            "bridge_attempted": False,
        },
    )

    summary = summarize_product_proof_artifacts(proof_root=root, target="reservation_stage")

    assert summary["blocking_signal"] == "analyzer_timeout"
    assert summary["sharpened_blocking_signal"] == "child_wrapper_wait_return_missing"
    assert summary["analyzer_runtime"]["parent_wait_started"] is True
    assert summary["analyzer_runtime"]["parent_wait_returned"] is False
    assert summary["analyzer_runtime"]["child_bootstrap_returned"] is True
    assert summary["analyzer_runtime"]["bridge_attempted"] is False


def test_summary_extracts_diagnostic_discovery_output_subreason(tmp_path: Path) -> None:
    root = tmp_path / "proof"
    target_dir = root / "runs" / "02-reservation_stage"
    _write_json(
        root / "enterprise-survivability-summary.json",
        {
            "safe_to_compare": False,
            "targets": [
                {
                    "target": "reservation_stage",
                    "state": "non_comparable",
                    "safe_to_compare": False,
                    "reason_code": "discovery_empty",
                    "phase": "analyze",
                    "job_id": "job-reservation",
                }
            ],
        },
    )
    _write_json(
        target_dir / "run_result.json",
        {
            "status_payload": {
                "analyzer_runtime_authority": {
                    "phase_history": [
                        {"phase": "discovery_child_wait_start"},
                        {"phase": "discovery_child_wait_returned"},
                        {"phase": "discovery_child_returncode_observed"},
                        {"phase": "discovery_output_scan_completed"},
                    ],
                    "child_returncode": 3221225786,
                }
            }
        },
    )
    _write_json(target_dir / "measurement-terminalization.json", {"reason_code": "discovery_empty"})
    _write_json(
        target_dir / "discovery-output-authority.json",
        {
            "status": "non_comparable_discovery_failure",
            "reason_code": "child_python_startup_interrupt",
            "owner": "discovery_child_python_startup",
            "safe_to_compare": False,
            "subprocess_returncode": 3221225786,
            "subprocess_keyboard_interrupt": True,
            "discovery_file_count": 0,
            "invocable_count": 0,
            "ghidra_entered": False,
            "subprocess_interrupt_diagnostics": {
                "subreason_code": "child_python_startup_interrupt",
                "source_reason_code": "child_bootstrap_entry_missing",
                "classification_precision": "precise",
            },
        },
    )

    summary = summarize_product_proof_artifacts(proof_root=root, target="reservation_stage")

    assert summary["blocking_signal"] == "discovery_empty"
    assert summary["diagnostic_subreason_signal"] == "child_python_startup_interrupt"
    assert summary["discovery_output"]["source_reason_code"] == "child_bootstrap_entry_missing"
    assert summary["discovery_output"]["branch_steering_authority"] is True
    assert summary["discovery_output"]["authority_scope"] == "blocker_repair_routing_only_not_product_proof"
    assert summary["discovery_output"]["diagnostic_only"] is False
    assert summary["analyzer_runtime"]["parent_wait_returned"] is True
