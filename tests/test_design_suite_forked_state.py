from pathlib import Path

import pytest

from api.pipeline.core.design_suite_expected_observed import run_northstar_first_slice


ROOT = Path(__file__).resolve().parent.parent


def _manifest_path() -> Path:
    return ROOT / "tests" / "fixtures" / "design_suite" / "northstar_transaction_suite" / "truth_manifest.json"


def test_forked_state_pressure_adds_branch_selection_to_expected_vs_observed_surface() -> None:
    bundle = run_northstar_first_slice(_manifest_path(), include_forked_state=True)

    report = bundle["northstar-expected-observed-report.json"]

    assert report["slice_id"] == "northstar:first_slice_forked_state"
    assert report["module_family"] == ["audit", "billing", "inventory", "session"]
    assert "forked_state_blocker" in report["expected_blockers"]
    assert set(report["expected_lineage_branches"]) == {
        "authorization_receipt_primary",
        "authorization_receipt_shadow",
    }
    assert report["expected_accepted_branches"] == ["authorization_receipt_primary"]
    assert set(report["observed_lineage_branches"]) == {
        "authorization_receipt_primary",
        "authorization_receipt_shadow",
    }
    assert report["observed_accepted_branches"] == ["authorization_receipt_primary"]
    assert "forked_state_match" in report["notes"]
    assert report["mismatches"] == []


def test_forked_state_cannot_be_combined_with_other_bounded_pressures() -> None:
    with pytest.raises(ValueError, match="one pressure at a time"):
        run_northstar_first_slice(
            _manifest_path(),
            include_late_confirmation=True,
            include_forked_state=True,
        )
