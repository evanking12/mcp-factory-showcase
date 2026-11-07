from __future__ import annotations

import json
from pathlib import Path

from api.pipeline.core.design_suite_expected_observed import (
    compare_expected_observed,
    initialize_expected_report,
    load_design_suite_manifest,
    run_northstar_first_slice,
    write_design_suite_artifact,
)
from api.pipeline.core.design_suite_observers import build_family_blocker_plausibility_observer


ROOT = Path(__file__).resolve().parent.parent


def _manifest_path() -> Path:
    return ROOT / "tests" / "fixtures" / "design_suite" / "northstar_transaction_suite" / "truth_manifest.json"


def test_initialize_expected_report_authors_expected_half_before_observed_run() -> None:
    manifest = load_design_suite_manifest(_manifest_path())

    report = initialize_expected_report(manifest)

    assert report.slice_id == "northstar:first_slice"
    assert report.observed_blockers == ()
    assert set(report.expected_producers) == {
        "session.bootstrap_session",
    }
    assert set(report.expected_consumers) == {
        "inventory.reserve_item",
        "billing.authorize_charge",
    }


def test_run_northstar_first_slice_emits_bounded_expected_vs_observed_bundle(tmp_path: Path) -> None:
    bundle = run_northstar_first_slice(_manifest_path(), output_dir=tmp_path)

    assert set(bundle) == {
        "northstar-producer-consumer-report.json",
        "northstar-shared-state-report.json",
        "northstar-family-blocker-report.json",
        "northstar-interwoven-observer-summary.json",
        "northstar-expected-observed-report.json",
    }
    report = bundle["northstar-expected-observed-report.json"]
    assert report["module_family"] == ["billing", "inventory", "session"]
    assert report["mismatches"] == []
    assert "first_slice_match" in report["notes"]
    assert (tmp_path / "northstar-expected-observed-report.json").exists()


def test_design_suite_artifact_writes_supersede_prior_current_report(tmp_path: Path) -> None:
    old_payload = {"slice_id": "northstar:first_slice", "version": 1}
    new_payload = {"slice_id": "northstar:first_slice", "version": 2}

    write_design_suite_artifact(tmp_path, "northstar-expected-observed-report.json", old_payload)
    write_design_suite_artifact(tmp_path, "northstar-expected-observed-report.json", new_payload)

    current = json.loads((tmp_path / "northstar-expected-observed-report.json").read_text(encoding="utf-8"))
    superseded = json.loads((tmp_path / "superseded" / "northstar-expected-observed-report.json").read_text(encoding="utf-8"))

    assert current["version"] == 2
    assert superseded["version"] == 1


def test_compare_expected_observed_preserves_misgroup_when_family_observer_warns() -> None:
    manifest = load_design_suite_manifest(_manifest_path())
    expected = initialize_expected_report(manifest)
    bundle = run_northstar_first_slice(_manifest_path())

    warn_observer = build_family_blocker_plausibility_observer(
        subject_ids=("session.bootstrap_session", "inventory.reserve_item"),
        blocker_family="bootstrap_family_blocker",
        contradiction_state="tentative",
        expected_behavior="Family blocker should remain bounded.",
        observed_behavior="Observed blocker stayed visible but still looks tentative.",
        confidence=0.7,
        canonical_sources=("northstar-family-blocker-report.json",),
    )

    report = compare_expected_observed(
        expected,
        producer_consumer=tuple(),
        shared_state=tuple(),
        blocker_reports=tuple(),
        observer_summaries=(warn_observer,),
    )

    assert "bootstrap_family_blocker:observer_warn" in report.misgroups
    assert "family_blocker_plausibility" in report.deferred
    assert report.overclaims == ()
    assert report.underclaims != ()
