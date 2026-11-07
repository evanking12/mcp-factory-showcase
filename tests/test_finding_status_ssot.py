from __future__ import annotations

from api.pipeline.core import finding_status
from api.pipeline.core import helpers


def test_status_rank_ssot_matches_helpers_alias() -> None:
    assert helpers.FINDING_STATUS_RANK == finding_status.STATUS_ORDER


def test_status_normalization_aliases() -> None:
    assert finding_status.normalize_status("success") == "verified_success"
    assert finding_status.normalize_status("partial") == "inferred_success"
    assert finding_status.normalize_status("error") == "failure"
    assert finding_status.normalize_status("functional") == "functional_precondition_unmet"


def test_classification_pattern_detects_functional_precondition() -> None:
    assert finding_status.is_functional_precondition_text("insufficient loyalty points")
    assert finding_status.classify_finding_status(-5, {0xFFFFFFFB: "insufficient points"}) == "functional_precondition_unmet"

