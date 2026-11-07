from __future__ import annotations

import json
from pathlib import Path

from scripts.runs.run_northstar_campaign import main as _unused_main  # noqa: F401
from scripts.runs.run_northstar_campaign import REPO_ROOT
import subprocess
import sys


def test_northstar_campaign_emits_bounded_campaign_artifacts(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "runs" / "run_northstar_campaign.py"),
            "--suite",
            "northstar_transaction_suite",
            "--mode",
            "late_confirmation",
            "--output-root",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    output_dir = Path(payload["output_dir"])

    assert (output_dir / "campaign" / "session-manifest.json").exists()
    assert (output_dir / "campaign" / "campaign.json").exists()
    assert (output_dir / "shared" / "plans" / "campaign_plan.json").exists()
    assert (output_dir / "shared" / "evidence-graph" / "evidence_graph.json").exists()
    assert (output_dir / "campaign" / "checkpoints" / "campaign_checkpoint.json").exists()
    assert (output_dir / "campaign" / "campaign-truth.json").exists()
    assert (output_dir / "audits" / "campaign-cohesion-report.json").exists()
    assert (output_dir / "audits" / "northstar-campaign-attribution-review.json").exists()
    assert (output_dir / "design-suite-reusable-campaign-seam.json").exists()


def test_northstar_campaign_preserves_semantics_and_blocks_compare_overclaim(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "runs" / "run_northstar_campaign.py"),
            "--suite",
            "northstar_transaction_suite",
            "--mode",
            "late_confirmation",
            "--output-root",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    truth = json.loads((tmp_path / "campaign" / "campaign-truth.json").read_text(encoding="utf-8"))
    cohesion = json.loads((tmp_path / "audits" / "campaign-cohesion-report.json").read_text(encoding="utf-8"))
    attribution = json.loads((tmp_path / "audits" / "northstar-campaign-attribution-review.json").read_text(encoding="utf-8"))
    seam = json.loads((tmp_path / "design-suite-reusable-campaign-seam.json").read_text(encoding="utf-8"))

    assert truth["suite_id"] == "northstar_transaction_suite"
    assert truth["pressure_mode"] == "late_confirmation"
    assert set(truth["active_modules"]) == {"session", "inventory", "billing", "audit"}
    assert set(truth["deferred_modules"]) == {"fulfillment", "notifications"}
    assert set(truth["provisional_subject_ids"]) == {"inventory.reserve_item", "billing.authorize_charge"}
    assert truth["confirmation_sites"] == ["audit.commit_receipt"]
    assert truth["compare_ready"] is False
    assert truth["promotion_ready"] is False
    assert cohesion["compare_ready"] is False
    assert cohesion["promotion_ready"] is False
    assert attribution["suite_used"] is True
    assert attribution["active_modules_bounded"] is True
    assert attribution["compare_overclaim_detected"] is False
    assert attribution["promotion_overclaim_detected"] is False
    assert seam["reusable_truth_projection_present"] is True
    assert seam["reusable_cohesion_projection_present"] is True
    assert seam["reusable_attribution_projection_present"] is True
    assert "campaign truth projection" in seam["successor_suite_inherits"]


def test_northstar_campaign_preserves_forked_state_branch_semantics(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "runs" / "run_northstar_campaign.py"),
            "--suite",
            "northstar_transaction_suite",
            "--mode",
            "forked_state",
            "--output-root",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    truth = json.loads((tmp_path / "campaign" / "campaign-truth.json").read_text(encoding="utf-8"))
    cohesion = json.loads((tmp_path / "audits" / "campaign-cohesion-report.json").read_text(encoding="utf-8"))
    attribution = json.loads((tmp_path / "audits" / "northstar-campaign-attribution-review.json").read_text(encoding="utf-8"))
    seam = json.loads((tmp_path / "design-suite-reusable-campaign-seam.json").read_text(encoding="utf-8"))

    assert truth["suite_id"] == "northstar_transaction_suite"
    assert truth["pressure_mode"] == "forked_state"
    assert set(truth["active_modules"]) == {"session", "inventory", "billing", "audit"}
    assert set(truth["deferred_modules"]) == {"fulfillment", "notifications"}
    assert truth["lineage_branches"]
    assert truth["accepted_branches"] == ["authorization_receipt_primary"]
    assert truth["rejected_branches"] == ["authorization_receipt_shadow"]
    assert cohesion["lineage_branches"]
    assert cohesion["accepted_branches"] == ["authorization_receipt_primary"]
    assert cohesion["rejected_branches"] == ["authorization_receipt_shadow"]
    assert cohesion["forked_state_semantics_preserved"] is True
    assert attribution["forked_state_mode_used"] is True
    assert attribution["accepted_branch_preserved"] is True
    assert attribution["rejected_branch_preserved"] is True
    assert attribution["branch_overclaim_detected"] is False
    assert attribution["compare_overclaim_detected"] is False
    assert attribution["promotion_overclaim_detected"] is False
    assert "suite-specific branch review wording" in seam["remaining_northstar_specific_glue"]
    assert seam["glue_resolution_plan"]["suite-specific branch review wording"] == "supersede in next prompt"
