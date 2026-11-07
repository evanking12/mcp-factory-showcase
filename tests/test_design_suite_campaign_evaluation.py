from __future__ import annotations

from api.pipeline.core.design_suite_campaign_evaluation import build_design_suite_campaign_seam_evaluation


def test_campaign_seam_evaluation_recommends_successor_suite_when_both_modes_are_green() -> None:
    late_truth = {
        "pressure_mode": "late_confirmation",
        "provisional_subject_ids": ["inventory.reserve_item", "billing.authorize_charge"],
        "confirmation_sites": ["audit.commit_receipt"],
    }
    late_cohesion = {}
    late_attr = {
        "suite_used": True,
        "active_modules_bounded": True,
        "compare_overclaim_detected": False,
        "promotion_overclaim_detected": False,
    }
    late_seam = {
        "reusable_truth_projection_present": True,
        "reusable_cohesion_projection_present": True,
        "reusable_attribution_projection_present": True,
        "remaining_northstar_specific_glue": [
            "suite-specific entrypoint wrapper",
            "suite-specific campaign artifact naming",
        ],
        "successor_suite_inherits": [
            "campaign truth projection",
            "campaign cohesion projection",
            "campaign attribution preservation",
        ],
    }
    forked_truth = {
        "pressure_mode": "forked_state",
        "accepted_branches": ["authorization_receipt_primary"],
        "rejected_branches": ["authorization_receipt_shadow"],
    }
    forked_cohesion = {"forked_state_semantics_preserved": True}
    forked_attr = {
        "suite_used": True,
        "active_modules_bounded": True,
        "accepted_branch_preserved": True,
        "rejected_branch_preserved": True,
        "branch_overclaim_detected": False,
        "compare_overclaim_detected": False,
        "promotion_overclaim_detected": False,
    }
    forked_seam = {
        "reusable_truth_projection_present": True,
        "reusable_cohesion_projection_present": True,
        "reusable_attribution_projection_present": True,
        "remaining_northstar_specific_glue": [
            "suite-specific campaign artifact naming",
            "suite-specific branch review wording",
        ],
        "successor_suite_inherits": [
            "campaign truth projection",
            "campaign cohesion projection",
            "campaign attribution preservation",
        ],
    }

    evaluation = build_design_suite_campaign_seam_evaluation(
        late_truth,
        late_cohesion,
        late_attr,
        late_seam,
        forked_truth,
        forked_cohesion,
        forked_attr,
        forked_seam,
    )

    assert evaluation["late_confirmation_green"] is True
    assert evaluation["forked_state_green"] is True
    assert evaluation["reusable_campaign_seam_present"] is True
    assert evaluation["successor_suite_inheritance_ready"] is True
    assert evaluation["recommended_next_branch"] == "successor-suite contract and inheritance gate"
    assert "campaign truth projection" in evaluation["recommended_inherited_surfaces"]


def test_campaign_seam_evaluation_blocks_successor_suite_when_forked_state_regresses() -> None:
    evaluation = build_design_suite_campaign_seam_evaluation(
        {"pressure_mode": "late_confirmation", "provisional_subject_ids": ["x"], "confirmation_sites": ["y"]},
        {},
        {"suite_used": True, "active_modules_bounded": True, "compare_overclaim_detected": False, "promotion_overclaim_detected": False},
        {
            "reusable_truth_projection_present": True,
            "reusable_cohesion_projection_present": True,
            "reusable_attribution_projection_present": True,
            "remaining_northstar_specific_glue": [],
            "successor_suite_inherits": ["campaign truth projection"],
        },
        {"pressure_mode": "forked_state", "accepted_branches": [], "rejected_branches": []},
        {"forked_state_semantics_preserved": False},
        {
            "suite_used": True,
            "active_modules_bounded": True,
            "accepted_branch_preserved": False,
            "rejected_branch_preserved": False,
            "branch_overclaim_detected": True,
            "compare_overclaim_detected": False,
            "promotion_overclaim_detected": False,
        },
        {
            "reusable_truth_projection_present": True,
            "reusable_cohesion_projection_present": True,
            "reusable_attribution_projection_present": True,
            "remaining_northstar_specific_glue": [],
            "successor_suite_inherits": ["campaign truth projection"],
        },
    )

    assert evaluation["forked_state_green"] is False
    assert evaluation["successor_suite_inheritance_ready"] is False
    assert evaluation["recommended_next_branch"] == "narrower repair prompt"
    assert "forked_state_campaign_regressed" in evaluation["blocking_reasons"]
