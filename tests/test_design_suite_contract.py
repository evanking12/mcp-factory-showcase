from api.pipeline.core.design_suite_artifacts import (
    DEFAULT_NORTHSTAR_ARTIFACT_PLACEMENT,
    NORTHSTAR_CANONICAL_ARTIFACTS,
    NORTHSTAR_SUMMARY_ONLY_ARTIFACTS,
)
from api.pipeline.core.design_suite_observers import DESIGN_SUITE_OBSERVER_NAMES
from api.pipeline.core.design_suite_taxonomy import (
    DEFAULT_NORTHSTAR_CONTRACT,
    DESIGN_SUITE_ACTIVE_MODULES,
    DESIGN_SUITE_BLOCKER_TAXONOMY,
    DESIGN_SUITE_BOUNDARY_REFERENCE,
)


def test_northstar_contract_defaults_lock_first_slice_and_thresholds() -> None:
    contract = DEFAULT_NORTHSTAR_CONTRACT

    assert contract.suite_id == "northstar_transaction_suite"
    assert contract.suite_name == "Northstar Transaction Suite"
    assert contract.active_modules == DESIGN_SUITE_ACTIVE_MODULES
    assert contract.deferred_modules == ("audit", "fulfillment", "notifications")
    assert contract.primary_blocker_family == "bootstrap_family_blocker"
    assert contract.supporting_blocker_pressure == "shared_state_carrier_blocker"
    assert contract.artifact_scope == "session_only"
    assert contract.compare_boundary == "architecture_proof_only"
    assert contract.max_active_modules == 3
    assert contract.max_canonical_artifacts == 5
    assert contract.max_primary_blocker_families == 1
    assert contract.max_supporting_pressures == 1
    assert contract.acceptable_deferred_major_explanations == 1


def test_design_suite_blocker_taxonomy_keeps_boundaries_explicit() -> None:
    bootstrap = DESIGN_SUITE_BLOCKER_TAXONOMY["bootstrap_family_blocker"]
    overlap = DESIGN_SUITE_BLOCKER_TAXONOMY["two_family_overlap_blocker"]

    assert set(bootstrap.not_equivalent_to) == set(DESIGN_SUITE_BOUNDARY_REFERENCE)
    assert set(overlap.not_equivalent_to) == set(DESIGN_SUITE_BOUNDARY_REFERENCE)


def test_design_suite_artifact_and_observer_defaults_remain_session_scoped() -> None:
    assert set(NORTHSTAR_CANONICAL_ARTIFACTS) == {
        "northstar-producer-consumer-report.json",
        "northstar-shared-state-report.json",
        "northstar-family-blocker-report.json",
        "northstar-expected-observed-report.json",
    }
    assert NORTHSTAR_SUMMARY_ONLY_ARTIFACTS == ("northstar-interwoven-observer-summary.json",)
    assert DEFAULT_NORTHSTAR_ARTIFACT_PLACEMENT["canonical_scope"] == "session_only"
    assert DEFAULT_NORTHSTAR_ARTIFACT_PLACEMENT["campaign_projection"] is False
    assert DEFAULT_NORTHSTAR_ARTIFACT_PLACEMENT["ledger_projection"] is False
    assert DEFAULT_NORTHSTAR_ARTIFACT_PLACEMENT["collector_projection"] is False
    assert set(DESIGN_SUITE_OBSERVER_NAMES) >= {
        "family_blocker_plausibility",
        "shared_state_carrier_plausibility",
    }
