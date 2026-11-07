from __future__ import annotations

import json
from pathlib import Path

from api.pipeline.core.spectrum_runtime_adoption import (
    SPECTRUM_CASE_IDS,
    SPECTRUM_EXPECTED_OBSERVED_ARTIFACT,
    SPECTRUM_OBSERVER_SUMMARY_ARTIFACT,
    load_spectrum_case_manifest,
    run_spectrum_runtime_adoption,
)
from api.pipeline.core.design_suite_runtime_bridge import (
    DESIGN_SUITE_COHESION_REPORT_ARTIFACT,
    DESIGN_SUITE_EXECUTION_TRACE_ARTIFACT,
    DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT,
    DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT,
)


def test_load_spectrum_case_manifest_supports_all_authored_cases() -> None:
    loaded = {load_spectrum_case_manifest(case_id)["case_id"] for case_id in SPECTRUM_CASE_IDS}
    assert loaded == set(SPECTRUM_CASE_IDS)


def test_run_spectrum_runtime_adoption_emits_expected_artifacts_for_easy_case(tmp_path: Path) -> None:
    result = run_spectrum_runtime_adoption(case_id="easy-01", output_root=tmp_path / "easy")
    output_dir = Path(result["output_dir"])

    assert (output_dir / DESIGN_SUITE_EXECUTION_TRACE_ARTIFACT).exists()
    assert (output_dir / DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT).exists()
    assert (output_dir / DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT).exists()
    assert (output_dir / DESIGN_SUITE_COHESION_REPORT_ARTIFACT).exists()
    assert (output_dir / SPECTRUM_EXPECTED_OBSERVED_ARTIFACT).exists()
    assert (output_dir / SPECTRUM_OBSERVER_SUMMARY_ARTIFACT).exists()
    assert result["expected_observed"]["observed_consumers"] == [
        "reservation_stage.issue_release_hold",
        "release_commit.commit_release",
        "audit_trace.record_release_receipt",
    ]


def test_spectrum_runtime_adoption_preserves_medium_differentiation(tmp_path: Path) -> None:
    medium_01 = run_spectrum_runtime_adoption(case_id="medium-01", output_root=tmp_path / "medium_01")
    medium_02 = run_spectrum_runtime_adoption(case_id="medium-02", output_root=tmp_path / "medium_02")

    report_01 = medium_01["expected_observed"]
    report_02 = medium_02["expected_observed"]
    assert report_01["observed_shared_state"] == ["operator_token", "reservation_handle"]
    assert report_02["observed_shared_state"] == ["operator_token", "attestation_packet"]
    assert report_01["deferred"] != report_02["deferred"]

    blocker_runtime = json.loads((Path(medium_02["output_dir"]) / SPECTRUM_OBSERVER_SUMMARY_ARTIFACT).read_text(encoding="utf-8"))
    stability_rows = [row for row in blocker_runtime["observer_results"] if row["observer_name"] == "blocker_stability"]
    assert stability_rows
    assert stability_rows[0]["runtime_output"]["same_family_confidence"] == "medium"


def test_spectrum_runtime_adoption_preserves_hard_01_branch_semantics(tmp_path: Path) -> None:
    result = run_spectrum_runtime_adoption(case_id="hard-01", output_root=tmp_path / "hard_01")

    report = result["expected_observed"]
    assert report["observed_lineage_branches"] == ["primary", "replay"]
    assert report["observed_accepted_branches"] == ["primary"]
    assert "replay_branch.replay_release_branch" in report["overclaims"][0]["path"]
    assert result["runtime_plan"]["accepted_branches"] == ["primary"]
    observer_summary = result["observer_summary"]
    branch_rows = [
        row for row in observer_summary["observer_results"] if row["observer_name"] == "branch_trust_observer"
    ]
    assert branch_rows
    assert branch_rows[0]["status"] == "pass"
    assert branch_rows[0]["runtime_output"]["candidate_branch_ids"] == ["primary", "replay"]
    assert branch_rows[0]["runtime_output"]["trusted_branch_id"] == "primary"
    assert branch_rows[0]["runtime_output"]["rejected_branch_ids"] == ["replay"]


def test_spectrum_runtime_adoption_preserves_hard_02_stale_state_semantics(tmp_path: Path) -> None:
    result = run_spectrum_runtime_adoption(case_id="hard-02", output_root=tmp_path / "hard_02")

    report = result["expected_observed"]
    assert report["observed_shared_state"] == [
        "operator_token",
        "attestation_packet",
        "attestation_nonce",
        "attestation_epoch",
    ]
    assert report["overclaims"][0]["path"] == "invoice_sync.stage_release_invoice"
    observer_summary = result["observer_summary"]
    false_green_rows = [row for row in observer_summary["observer_results"] if row["observer_name"] == "false_green"]
    assert false_green_rows
    assert false_green_rows[0]["runtime_output"]["affected_paths"] == [
        "invoice_sync.stage_release_invoice",
        "entitlement_sync.stage_customer_entitlement_update",
    ]
