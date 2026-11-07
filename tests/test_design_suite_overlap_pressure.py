from pathlib import Path

from api.pipeline.core.design_suite_expected_observed import run_northstar_first_slice


ROOT = Path(__file__).resolve().parent.parent


def _manifest_path() -> Path:
    return ROOT / "tests" / "fixtures" / "design_suite" / "northstar_transaction_suite" / "truth_manifest.json"


def test_overlap_pressure_adds_audit_before_other_deferred_modules() -> None:
    bundle = run_northstar_first_slice(_manifest_path(), include_overlap=True)

    report = bundle["northstar-expected-observed-report.json"]

    assert report["slice_id"] == "northstar:first_slice_overlap"
    assert report["module_family"] == ["audit", "billing", "inventory", "session"]
    assert "two_family_overlap_blocker" in report["expected_blockers"]
    assert "audit.commit_receipt" in report["expected_consumers"]
    assert "notifications" not in report["module_family"]


def test_overlap_pressure_keeps_expansion_bounded_to_four_active_modules() -> None:
    bundle = run_northstar_first_slice(_manifest_path(), include_overlap=True)
    report = bundle["northstar-expected-observed-report.json"]

    assert len(report["module_family"]) == 4
    assert report["mismatches"] == []
