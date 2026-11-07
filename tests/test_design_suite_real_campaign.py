from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.runs.run_design_suite_real_campaign import REPO_ROOT
from scripts.runs.run_design_suite_real_campaign_readiness import run_design_suite_real_campaign_readiness
from scripts.runs.run_successor_suite_branch_decision import run_successor_suite_branch_decision


def test_northstar_campaign_wrapper_still_passes_through_generic_runtime(tmp_path: Path) -> None:
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

    assert (output_dir / "audits" / "design-suite-campaign-attribution-review.json").exists()
    assert (output_dir / "audits" / "northstar-campaign-attribution-review.json").exists()
    truth = json.loads((output_dir / "campaign" / "campaign-truth.json").read_text(encoding="utf-8"))
    assert truth["suite_id"] == "northstar_transaction_suite"


def test_atlas_real_campaign_readiness_runner_emits_real_readiness_alias(tmp_path: Path) -> None:
    result = run_design_suite_real_campaign_readiness(
        suite="atlas_reconciliation_suite",
        mode="mutual_pressure",
        output_root=tmp_path / "atlas_readiness",
    )

    assert Path(result["artifact_path"]).exists()
    assert result["readiness"]["ready_for_first_bounded_campaign"] is True
    assert Path(result["artifact_path"]).name == "atlas-real-campaign-readiness.json"


def test_atlas_real_campaign_runs_through_generic_runtime(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "runs" / "run_atlas_campaign.py"),
            "--suite",
            "atlas_reconciliation_suite",
            "--mode",
            "mutual_pressure",
            "--output-root",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    output_dir = Path(payload["output_dir"])

    assert (output_dir / "campaign" / "campaign.json").exists()
    assert (output_dir / "campaign" / "campaign-truth.json").exists()
    assert (output_dir / "audits" / "design-suite-campaign-attribution-review.json").exists()
    assert (output_dir / "audits" / "atlas-campaign-attribution-review.json").exists()
    truth = json.loads((output_dir / "campaign" / "campaign-truth.json").read_text(encoding="utf-8"))
    cohesion = json.loads((output_dir / "audits" / "campaign-cohesion-report.json").read_text(encoding="utf-8"))

    assert truth["suite_id"] == "atlas_reconciliation_suite"
    assert truth["pressure_mode"] == "mutual_pressure"
    assert set(truth["provisional_subject_ids"]) == {"identity.bind_party", "ledger.stage_transfer"}
    assert truth["confirmation_sites"] == ["reconcile.confirm_alignment"]
    assert cohesion["compare_ready"] is False
    assert cohesion["promotion_ready"] is False


def test_post_campaign_review_defers_weakness_triage_when_stronger_blocker_remains(tmp_path: Path) -> None:
    branch = run_successor_suite_branch_decision(output_root=tmp_path / "branch")
    campaign = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "runs" / "run_atlas_campaign.py"),
            "--suite",
            "atlas_reconciliation_suite",
            "--mode",
            "mutual_pressure",
            "--output-root",
            str(tmp_path / "campaign"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    campaign_payload = json.loads(campaign.stdout)
    review = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "runs" / "run_design_suite_post_campaign_review.py"),
            "--branch-decision-path",
            branch["artifact_path"],
            "--campaign-dir",
            campaign_payload["output_dir"],
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    review_payload = json.loads(review.stdout)
    artifact = json.loads((Path(review_payload["output_dir"]) / "design-suite-post-campaign-review.json").read_text(encoding="utf-8"))

    assert artifact["campaign_truth_present"] is True
    assert artifact["campaign_attribution_present"] is True
    assert artifact["recommended_next_branch"] == "weakness-register triage and reduction"
    assert artifact["weakness_register_triage_eligible"] is True
