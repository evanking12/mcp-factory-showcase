from api.pipeline.core.design_suite_observers import (
    DESIGN_SUITE_OBSERVER_NAMES,
    build_family_blocker_plausibility_observer,
    build_forked_state_visibility_observer,
    build_late_confirmation_visibility_observer,
    build_shared_state_carrier_plausibility_observer,
)


def test_family_blocker_observer_passes_for_bounded_bootstrap_family() -> None:
    observer = build_family_blocker_plausibility_observer(
        subject_ids=("session.bootstrap_session", "inventory.reserve_item", "billing.authorize_charge"),
        blocker_family="bootstrap_family_blocker",
        contradiction_state="none",
        expected_behavior="One family blocker should explain more than one downstream pressure site.",
        observed_behavior="Observed one bounded bootstrap family covering inventory and billing.",
        confidence=0.88,
        canonical_sources=("northstar-family-blocker-report.json",),
    )

    assert observer["observer_name"] == "family_blocker_plausibility"
    assert observer["status"] == "pass"
    assert "family_blocker_bounded" in observer["review_notes"]


def test_shared_state_carrier_observer_warns_when_reuse_is_too_narrow() -> None:
    observer = build_shared_state_carrier_plausibility_observer(
        subject_ids=("audit.commit_receipt",),
        blocker_family="two_family_overlap_blocker",
        contradiction_state="none",
        expected_behavior="Carrier should remain explicit across multiple consumers.",
        observed_behavior="Observed the carrier only at one overlap seam so far.",
        confidence=0.72,
        canonical_sources=("northstar-shared-state-report.json",),
        downstream_consumer_count=1,
    )

    assert set(DESIGN_SUITE_OBSERVER_NAMES) >= {
        "family_blocker_plausibility",
        "shared_state_carrier_plausibility",
    }
    assert observer["observer_name"] == "shared_state_carrier_plausibility"
    assert observer["status"] == "warn"
    assert "shared_state_not_yet_reused_across_multiple_consumers" in observer["review_notes"]


def test_late_confirmation_observer_passes_when_downstream_confirmer_is_explicit() -> None:
    observer = build_late_confirmation_visibility_observer(
        subject_ids=("inventory.reserve_item", "billing.authorize_charge", "audit.commit_receipt"),
        blocker_family="late_confirmation_blocker",
        contradiction_state="none",
        expected_behavior="Upstream work stays provisional until audit confirms it.",
        observed_behavior="Observed audit.commit_receipt as the downstream confirmer for both provisional subjects.",
        confidence=0.86,
        canonical_sources=("northstar-family-blocker-report.json",),
        provisional_subject_count=2,
        confirmation_site_count=1,
    )

    assert "late_confirmation_visibility" in DESIGN_SUITE_OBSERVER_NAMES
    assert observer["observer_name"] == "late_confirmation_visibility"
    assert observer["status"] == "pass"
    assert "late_confirmation_visible" in observer["review_notes"]


def test_forked_state_observer_passes_when_branch_choice_is_explicit() -> None:
    observer = build_forked_state_visibility_observer(
        subject_ids=("billing.authorize_charge", "audit.commit_receipt"),
        blocker_family="forked_state_blocker",
        contradiction_state="none",
        expected_behavior="Exactly one accepted authorization branch should survive into audit.",
        observed_behavior="Observed primary authorization branch accepted and shadow branch rejected.",
        confidence=0.85,
        canonical_sources=("northstar-family-blocker-report.json",),
        lineage_branch_count=2,
        accepted_branch_present=True,
        rejected_branch_count=1,
    )

    assert "forked_state_visibility" in DESIGN_SUITE_OBSERVER_NAMES
    assert observer["observer_name"] == "forked_state_visibility"
    assert observer["status"] == "pass"
    assert "forked_state_visible" in observer["review_notes"]
