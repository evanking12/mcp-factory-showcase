from __future__ import annotations

from api.pipeline.core.design_suite_campaign_runtime import (
    build_design_suite_campaign_attribution_review,
    build_design_suite_campaign_cohesion,
    build_design_suite_campaign_truth,
    build_design_suite_reusable_campaign_seam,
)


def test_design_suite_campaign_projection_preserves_late_confirmation_semantics() -> None:
    plan = {
        "suite_id": "northstar_transaction_suite",
        "pressure_mode": "late_confirmation",
        "active_modules": ["session", "inventory", "billing", "audit"],
        "deferred_modules": ["fulfillment", "notifications"],
        "blocker_family_ids": ["bootstrap_family_blocker", "late_confirmation_blocker"],
    }
    local_truth = {
        "blocker_family_ids": ["bootstrap_family_blocker", "late_confirmation_blocker"],
        "provisional_subject_ids": ["inventory.reserve_item", "billing.authorize_charge"],
        "confirmation_sites": ["audit.commit_receipt"],
        "lineage_branches": [],
        "accepted_branches": [],
        "rejected_branches": [],
    }
    scaling_cohesion = {
        "provisional_subject_ids": ["inventory.reserve_item", "billing.authorize_charge"],
        "confirmation_sites": ["audit.commit_receipt"],
        "lineage_branches": [],
        "accepted_branches": [],
        "rejected_branches": [],
        "readable": True,
        "complete": True,
    }

    campaign_truth = build_design_suite_campaign_truth("test-campaign", plan, local_truth)
    campaign_cohesion = build_design_suite_campaign_cohesion("test-campaign", plan, scaling_cohesion)
    attribution = build_design_suite_campaign_attribution_review("test-campaign", campaign_truth, campaign_cohesion)
    seam = build_design_suite_reusable_campaign_seam(plan, campaign_truth, campaign_cohesion, attribution)

    assert campaign_truth["provisional_subject_ids"] == ["inventory.reserve_item", "billing.authorize_charge"]
    assert campaign_truth["confirmation_sites"] == ["audit.commit_receipt"]
    assert campaign_truth["compare_ready"] is False
    assert campaign_cohesion["compare_ready"] is False
    assert attribution["compare_overclaim_detected"] is False
    assert seam["reusable_truth_projection_present"] is True
    assert seam["reusable_cohesion_projection_present"] is True
    assert seam["reusable_attribution_projection_present"] is True


def test_design_suite_campaign_projection_preserves_forked_state_semantics() -> None:
    plan = {
        "suite_id": "northstar_transaction_suite",
        "pressure_mode": "forked_state",
        "active_modules": ["session", "inventory", "billing", "audit"],
        "deferred_modules": ["fulfillment", "notifications"],
        "blocker_family_ids": ["bootstrap_family_blocker", "forked_state_blocker"],
    }
    local_truth = {
        "blocker_family_ids": ["bootstrap_family_blocker", "forked_state_blocker"],
        "provisional_subject_ids": [],
        "confirmation_sites": [],
        "lineage_branches": ["authorization_receipt_primary", "authorization_receipt_shadow"],
        "accepted_branches": ["authorization_receipt_primary"],
        "rejected_branches": ["authorization_receipt_shadow"],
    }
    scaling_cohesion = {
        "provisional_subject_ids": [],
        "confirmation_sites": [],
        "lineage_branches": ["authorization_receipt_primary", "authorization_receipt_shadow"],
        "accepted_branches": ["authorization_receipt_primary"],
        "rejected_branches": ["authorization_receipt_shadow"],
        "readable": True,
        "complete": True,
    }

    campaign_truth = build_design_suite_campaign_truth("test-campaign", plan, local_truth)
    campaign_cohesion = build_design_suite_campaign_cohesion("test-campaign", plan, scaling_cohesion)
    attribution = build_design_suite_campaign_attribution_review("test-campaign", campaign_truth, campaign_cohesion)
    seam = build_design_suite_reusable_campaign_seam(plan, campaign_truth, campaign_cohesion, attribution)

    assert campaign_truth["accepted_branches"] == ["authorization_receipt_primary"]
    assert campaign_truth["rejected_branches"] == ["authorization_receipt_shadow"]
    assert campaign_cohesion["forked_state_semantics_preserved"] is True
    assert attribution["accepted_branch_preserved"] is True
    assert attribution["rejected_branch_preserved"] is True
    assert attribution["branch_overclaim_detected"] is False
    assert "campaign truth projection" in seam["successor_suite_inherits"]
    assert "generic design-suite campaign runner" in seam["successor_suite_does_not_yet_inherit"]
