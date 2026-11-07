from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.pipeline import s01_unlock
from api.pipeline.s04_synthesis import synthesize


PIPELINE_BASELINE_ROWS = {
    "tier2": {
        "S-00A sentinel/vocab baseline",
        "S-00B callable inventory richness",
        "S-00C admission capping",
        "S-01 unlock target prioritization",
        "S-01 fallback under weak guidance",
        "S-04 evidence-grounded synthesis",
        "S-04 missing-evidence honesty",
    },
    "tier1": {
        "S-00C -> S-01 admission pressure",
    },
    "failed_tier2": {
        "S-03 contradictory evidence handling",
        "S-07 close-path reliability",
    },
    "blocked_at_tier2": {
        "S-03 repeated unresolved status",
        "S-06 repeated gap-family recognition",
        "S-06 unresolved S-05C caveat consumption",
        "S-05C -> S-06 chaining-to-gaps deferral",
    },
    "deferred_as_tier3_shaped": {
        "S-00A thin setup evidence",
        "S-00B static string thinness",
        "S-00B raw-overread prevention",
        "S-00C weak-target non-overtrust",
        "S-00C cross-DLL hint deferral",
        "S-01 overtrust prevention",
        "S-01 bad-unlock containment",
        "S-03 false repair prevention",
        "S-03 wrong blocker attribution",
        "S-04 overconfident documentation prevention",
        "S-06 architecture-gap classification",
    },
    "planned_unimplemented": {
        "post-S-00 coordinator",
    },
}


def test_pipeline_full_baseline_row_state_taxonomy_is_explicit() -> None:
    known_states = set(PIPELINE_BASELINE_ROWS)
    assert known_states == {
        "tier2",
        "tier1",
        "failed_tier2",
        "blocked_at_tier2",
        "deferred_as_tier3_shaped",
        "planned_unimplemented",
    }
    assert sum(len(rows) for rows in PIPELINE_BASELINE_ROWS.values()) >= 25
    assert "S-07 close-path reliability" in PIPELINE_BASELINE_ROWS["failed_tier2"]
    assert "post-S-00 coordinator" in PIPELINE_BASELINE_ROWS["planned_unimplemented"]


def test_s01_unlock_tier2_prioritization_preserves_fallback_candidates() -> None:
    invocables = [
        {"name": "Legacy_InitFallback"},
        {"name": "Target_WriteAdmitted"},
        {"name": "Distractor_ReadOnly"},
        {"name": "Target_InitAdmitted"},
    ]

    ordered = s01_unlock._prioritize_invocables_for_s01_targets(
        invocables,
        {
            "init_candidates": ["Target_InitAdmitted"],
            "write_candidates": ["Target_WriteAdmitted"],
        },
    )

    assert [row["name"] for row in ordered] == [
        "Target_InitAdmitted",
        "Target_WriteAdmitted",
        "Legacy_InitFallback",
        "Distractor_ReadOnly",
    ]


def test_s01_unlock_tier2_weak_guidance_falls_back_without_widening() -> None:
    invocables = [
        {"name": "Legacy_InitFallback"},
        {"name": "Legacy_WriteFallback"},
    ]

    ordered = s01_unlock._prioritize_invocables_for_s01_targets(
        invocables,
        {
            "init_candidates": ["Missing_InitCandidate"],
            "write_candidates": ["Missing_WriteCandidate"],
        },
    )

    assert ordered == invocables


def test_s04_synthesis_tier2_fallback_preserves_evidence_and_missing_boundaries() -> None:
    ctx = SimpleNamespace(
        vocab={"id_formats": ["CUST-\\d+"]},
        invocables=[
            {
                "name": "S04_ReadCustomer",
                "parameters": [{"name": "customer_id", "json_type": "string"}],
            },
            {
                "name": "S04_UpdateCustomer",
                "parameters": [{"name": "customer_id", "json_type": "string"}],
            },
        ],
    )
    findings = [
        {
            "function": "S04_ReadCustomer",
            "status": "success",
            "finding": "Verified read returned customer data.",
            "working_call": {"customer_id": "CUST-200"},
        },
        {
            "function": "S04_UpdateCustomer",
            "status": "unresolved",
            "finding": "Missing write confirmation; preserve caveat.",
            "working_call": None,
        },
    ]

    report = synthesize._build_fallback_api_reference(ctx, findings)

    assert "S04_ReadCustomer" in report
    assert "Working example" in report
    assert "S04_UpdateCustomer" in report
    assert "Known Limitations" in report
    assert "Missing write confirmation" in report
    assert "unresolved" in report


@pytest.mark.xfail(strict=True, reason="failed_tier2: S-03 lacks a local contradiction classification surface")
def test_s03_contradictory_evidence_tier2_attempt_exposes_missing_local_surface() -> None:
    reconcile_result = {
        "function": "S03_Contradiction",
        "probe": "returned 0",
        "static": "write requires init",
        "finding": "error",
    }

    assert reconcile_result.get("contradiction_status") == "bounded_contradiction"


@pytest.mark.xfail(strict=True, reason="blocked_at_tier2: S-06 has no explicit repeated gap-family register")
def test_s06_gap_family_tier2_attempt_requires_explicit_gap_register() -> None:
    gap_packet = {
        "unresolved": ["S06_WriteCustomer", "S06_WriteCustomerRetry"],
        "family_hint": "customer write blocked",
    }

    assert gap_packet.get("gap_family_id") == "customer_write_blocked"


@pytest.mark.xfail(strict=True, reason="failed_tier2: S-07 close-path reliability still lacks a local terminal close marker")
def test_s07_close_path_tier2_attempt_records_no_close_baseline_signal() -> None:
    finalization_status = {
        "s07_finalize": "done",
        "artifact_emission": "deferred",
    }

    assert finalization_status.get("terminal_close_marker") == "closed"

