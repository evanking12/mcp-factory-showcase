from api.pipeline.core.design_suite_runtime_bridge import (
    DESIGN_SUITE_COHESION_REPORT_ARTIFACT,
    DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT,
    DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT,
    build_design_suite_cohesion_report,
    build_design_suite_package_truth,
    build_design_suite_runtime_projection,
    resolve_design_suite_pressure_mode,
)
from api.pipeline.core.design_suite_taxonomy import DEFAULT_NORTHSTAR_CONTRACT


def _observed_bundle() -> dict:
    return {
        "northstar-producer-consumer-report.json": [
            {
                "family": "billing_authorize_primary_branch_to_audit_commit",
                "blocker_family": "forked_state_blocker",
                "producer_module": "billing",
                "producer_step": "authorize_charge",
                "consumer_module": "audit",
                "consumer_step": "commit_receipt",
                "state_tokens": ("session_token", "authorization_receipt_primary", "reservation_id"),
                "evidence_edges": ("billing.authorize_charge->audit.commit_receipt:primary_branch",),
                "dependency_mode": "staged",
                "confidence": 0.84,
                "contradiction_state": "none",
            }
        ],
        "northstar-shared-state-report.json": [
            {
                "carrier_id": "authorization_receipt_branch",
                "carrier_kind": "shared_state_carrier",
                "state_tokens": ("authorization_receipt_primary", "authorization_receipt_shadow"),
                "downstream_consumers": ("audit.commit_receipt",),
                "exporting_seams": ("billing.authorize_charge",),
                "importing_seams": ("audit.commit_receipt",),
                "staleness_risk": "high",
                "confidence": 0.81,
                "contradiction_state": "none",
            }
        ],
        "northstar-family-blocker-report.json": [
            {
                "blocker_family": "forked_state_blocker",
                "subjects": ("billing.authorize_charge", "audit.commit_receipt"),
                "upstream_requirements": ("billing.authorize_charge",),
                "shared_state_carriers": ("authorization_receipt_branch", "reservation_id"),
                "failure_or_pressure_sites": ("audit.commit_receipt",),
                "contradiction_state": "none",
                "explanation": "Shadow branch should be rejected.",
                "confidence": 0.85,
                "lineage_branches": ("authorization_receipt_primary", "authorization_receipt_shadow"),
                "accepted_branch": "authorization_receipt_primary",
                "rejected_branches": ("authorization_receipt_shadow",),
            }
        ],
    }


def _execution_trace() -> dict:
    return {
        "active_modules": ["session", "inventory", "billing", "audit"],
        "steps": [
            {"module": "session", "function": "bootstrap_session", "status": "success", "output_keys": ["session_token", "sequence_nonce"]},
            {"module": "inventory", "function": "reserve_item", "status": "success", "output_keys": ["reservation_id"]},
            {"module": "billing", "function": "authorize_charge", "status": "success", "output_keys": ["authorization_receipt_primary", "authorization_receipt_shadow"]},
            {"module": "audit", "function": "commit_receipt", "status": "success", "branch": "authorization_receipt_primary", "output_keys": ["audit_commit_id"]},
            {"module": "audit", "function": "commit_receipt", "status": "rejected", "branch": "authorization_receipt_shadow", "output_keys": []},
        ],
    }


def _truth_manifest() -> dict:
    return {
        "suite_id": "northstar_transaction_suite",
        "suite_name": "Northstar Transaction Suite",
        "active_modules": ["session", "inventory", "billing"],
        "deferred_modules": [{"module": "audit"}, {"module": "fulfillment"}, {"module": "notifications"}],
    }


def test_resolve_design_suite_pressure_mode_supports_enum_and_legacy_flags() -> None:
    assert resolve_design_suite_pressure_mode("base") == "base"
    assert resolve_design_suite_pressure_mode(include_late_confirmation=True) == "late_confirmation"
    assert resolve_design_suite_pressure_mode(include_forked_state=True) == "forked_state"
    assert resolve_design_suite_pressure_mode("mutual_pressure") == "mutual_pressure"


def test_build_design_suite_runtime_projection_derives_interwoven_and_branch_fields() -> None:
    projection = build_design_suite_runtime_projection(
        DEFAULT_NORTHSTAR_CONTRACT.to_dict(),
        _truth_manifest(),
        _observed_bundle(),
        _execution_trace(),
        "forked_state",
    )

    assert projection["artifact_type"] == DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT
    assert projection["package_surface"] == "local_design_suite"
    assert projection["compare_boundary"] == "architecture_proof_only"
    assert projection["pressure_mode"] == "forked_state"
    assert projection["interwoven_projection"]["interwoven_artifact_presence"] is True
    assert projection["accepted_branches"] == ["authorization_receipt_primary"]
    assert projection["rejected_branches"] == ["authorization_receipt_shadow"]


def test_build_design_suite_package_truth_and_cohesion_report_stay_local_and_non_compare() -> None:
    projection = build_design_suite_runtime_projection(
        DEFAULT_NORTHSTAR_CONTRACT.to_dict(),
        _truth_manifest(),
        _observed_bundle(),
        _execution_trace(),
        "forked_state",
    )
    package_truth = build_design_suite_package_truth(projection, _execution_trace())
    cohesion = build_design_suite_cohesion_report(projection, package_truth)

    assert package_truth["artifact_type"] == DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT
    assert package_truth["package_runtime_evidence_class"] == "design_suite_local_projection"
    assert package_truth["compare_ready"] is False
    assert package_truth["promotion_ready"] is False
    assert cohesion["artifact_type"] == DESIGN_SUITE_COHESION_REPORT_ARTIFACT
    assert cohesion["readable"] is True
    assert cohesion["runtime_attribution_present"] is True
