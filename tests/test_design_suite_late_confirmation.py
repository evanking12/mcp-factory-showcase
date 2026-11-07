from pathlib import Path

import pytest

from api.pipeline.core.design_suite_expected_observed import run_northstar_first_slice


ROOT = Path(__file__).resolve().parent.parent


def _manifest_path() -> Path:
    return ROOT / "tests" / "fixtures" / "design_suite" / "northstar_transaction_suite" / "truth_manifest.json"


def test_late_confirmation_pressure_adds_audit_as_downstream_confirmer() -> None:
    bundle = run_northstar_first_slice(_manifest_path(), include_late_confirmation=True)

    report = bundle["northstar-expected-observed-report.json"]

    assert report["slice_id"] == "northstar:first_slice_late_confirmation"
    assert report["module_family"] == ["audit", "billing", "inventory", "session"]
    assert "late_confirmation_blocker" in report["expected_blockers"]
    assert report["expected_confirmation_sites"] == ["audit.commit_receipt"]
    assert report["observed_confirmation_sites"] == ["audit.commit_receipt"]
    assert "audit.commit_receipt" in report["observed_consumers"]
    assert "late_confirmation_match" in report["notes"]
    assert report["mismatches"] == []


def test_late_confirmation_and_overlap_cannot_be_applied_in_one_bounded_run() -> None:
    with pytest.raises(ValueError, match="one pressure at a time"):
        run_northstar_first_slice(
            _manifest_path(),
            include_overlap=True,
            include_late_confirmation=True,
        )
