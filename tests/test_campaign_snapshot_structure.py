from __future__ import annotations

from pathlib import Path


def test_campaign_snapshot_declares_canonical_roots_and_manifest() -> None:
    src = (Path(__file__).resolve().parent.parent / "api" / "routes" / "main.py").read_text(encoding="utf-8")
    assert '"campaign/session-manifest.json"' in src
    assert '"campaign/campaign.json"' in src
    assert '"shared/plans/campaign_plan.json"' in src
    assert '"shared/evidence-graph/evidence_graph.json"' in src
    assert '"campaign/checkpoints/campaign_checkpoint.json"' in src
    assert '"campaign/campaign-truth.json"' in src
    assert '"audits/campaign-cohesion-report.json"' in src
    assert '"audits/campaign-attribution-report.json"' in src
    assert '"audits/sensitivity_warnings.txt"' in src


def test_campaign_orchestrator_emits_campaign_cohesion_report() -> None:
    src = (Path(__file__).resolve().parent.parent / "api" / "pipeline" / "runner.py").read_text(encoding="utf-8")
    assert "emit_campaign_cohesion_report" in src
    assert "emit_campaign_attribution_report" in src
    assert "campaign-truth.json" in src
