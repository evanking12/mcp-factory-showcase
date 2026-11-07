from __future__ import annotations

from pathlib import Path

from api.pipeline.core.atlas_successor_suite import (
    ATLAS_CAMPAIGN_READINESS_ARTIFACT,
    ATLAS_EXPECTED_OBSERVED_ARTIFACT,
    ATLAS_FAMILY_BLOCKER_ARTIFACT,
    atlas_manifest_path,
    run_atlas_first_slice,
)
from api.pipeline.core.design_suite_runtime_bridge import DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT, resolve_design_suite_pressure_mode
from scripts.runs.run_atlas_successor_campaign_local import run_atlas_successor_campaign_local
from scripts.runs.run_atlas_successor_runtime_adoption import run_atlas_successor_runtime_adoption


def test_resolve_design_suite_pressure_mode_supports_mutual_pressure() -> None:
    assert resolve_design_suite_pressure_mode("mutual_pressure") == "mutual_pressure"


def test_atlas_first_slice_expected_observed_surface_is_authored_and_matches() -> None:
    bundle = run_atlas_first_slice(atlas_manifest_path())
    report = bundle[ATLAS_EXPECTED_OBSERVED_ARTIFACT]

    assert report["slice_id"] == "atlas:first_slice_mutual_pressure"
    assert "mutual_pressure_blocker" in report["expected_blockers"]
    assert "reconcile.confirm_alignment" in report["expected_confirmation_sites"]
    assert report["mismatches"] == []
    assert "first_slice_match" in report["notes"]
    assert bundle[ATLAS_FAMILY_BLOCKER_ARTIFACT][0]["artifact_type"] == ATLAS_FAMILY_BLOCKER_ARTIFACT


def test_atlas_successor_runtime_adoption_emits_local_package_artifacts(tmp_path: Path) -> None:
    result = run_atlas_successor_runtime_adoption(output_root=tmp_path / "atlas_runtime")

    output_dir = Path(result["output_dir"])
    assert (output_dir / DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT).exists()
    assert result["runtime_projection"]["pressure_mode"] == "mutual_pressure"
    assert set(result["runtime_projection"]["provisional_subject_ids"]) == {
        "identity.bind_party",
        "ledger.stage_transfer",
    }
    assert result["runtime_projection"]["confirmation_sites"] == ["reconcile.confirm_alignment"]
    assert result["package_truth"]["compare_ready"] is False
    assert result["package_truth"]["promotion_ready"] is False


def test_atlas_successor_campaign_local_reaches_bounded_readiness(tmp_path: Path) -> None:
    result = run_atlas_successor_campaign_local(output_root=tmp_path / "atlas_campaign_local")

    output_dir = Path(result["output_dir"])
    assert (output_dir / ATLAS_CAMPAIGN_READINESS_ARTIFACT).exists()
    assert result["campaign_plan"]["pressure_mode"] == "mutual_pressure"
    assert result["campaign_truth"]["compare_ready"] is False
    assert result["campaign_truth"]["promotion_ready"] is False
    assert result["readiness"]["target_mode"] == "mutual_pressure"
    assert result["readiness"]["ready_for_first_bounded_campaign"] is True
