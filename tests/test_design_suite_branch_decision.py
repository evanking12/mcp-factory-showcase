from __future__ import annotations

from pathlib import Path

from api.pipeline.core.design_suite_branch_decision import build_successor_suite_branch_decision
from scripts.runs.run_successor_suite_branch_decision import run_successor_suite_branch_decision


def test_branch_decision_prefers_genericization_when_successor_ready_but_real_runner_is_suite_specific() -> None:
    decision = build_successor_suite_branch_decision(
        {
            "ready_for_first_bounded_campaign": True,
        },
        suite_id="atlas_reconciliation_suite",
        suite_name="Atlas Reconciliation Suite",
        real_campaign_runtime_reusable=False,
        remaining_real_campaign_glue=["Northstar-specific real campaign runner"],
    )

    assert decision["local_campaign_ready"] is True
    assert decision["real_campaign_runtime_reusable"] is False
    assert decision["recommended_next_branch"] == "generic design-suite campaign seam tightening"
    assert "real_campaign_runtime_still_suite_specific" in decision["blocking_reasons"]


def test_branch_decision_prefers_real_campaign_gate_when_ready_and_reusable() -> None:
    decision = build_successor_suite_branch_decision(
        {
            "ready_for_first_bounded_campaign": True,
        },
        suite_id="atlas_reconciliation_suite",
        suite_name="Atlas Reconciliation Suite",
        real_campaign_runtime_reusable=True,
        remaining_real_campaign_glue=[],
    )

    assert decision["recommended_next_branch"] == "successor real bounded campaign gate"
    assert decision["blocking_reasons"] == []


def test_successor_branch_decision_runner_emits_artifact(tmp_path: Path) -> None:
    readiness_path = tmp_path / "atlas-campaign-readiness.json"
    readiness_path.write_text('{"ready_for_first_bounded_campaign": true}', encoding="utf-8")

    result = run_successor_suite_branch_decision(
        readiness_path=readiness_path,
        output_root=tmp_path / "decision_output",
    )

    assert Path(result["artifact_path"]).exists()
    assert result["decision"]["recommended_next_branch"] == "generic design-suite campaign seam tightening"
