from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from api.pipeline.core.design_suite_campaign_readiness import (
    build_design_suite_campaign_readiness,
    write_design_suite_campaign_readiness,
)
from api.pipeline.core.design_suite_campaign_runtime import (
    DESIGN_SUITE_REUSABLE_CAMPAIGN_SEAM_ARTIFACT,
    build_design_suite_campaign_attribution_review,
    build_design_suite_campaign_cohesion,
    build_design_suite_campaign_snapshot,
    build_design_suite_campaign_truth,
    build_design_suite_reusable_campaign_seam,
    write_json,
)
from api.pipeline.core.design_suite_expected_observed import write_design_suite_artifact


DESIGN_SUITE_CAMPAIGN_ATTRIBUTION_REVIEW_ARTIFACT = "design-suite-campaign-attribution-review.json"
DESIGN_SUITE_REAL_CAMPAIGN_READINESS_ARTIFACT = "design-suite-real-campaign-readiness.json"


@dataclass(frozen=True)
class DesignSuiteRealCampaignInputs:
    suite_id: str
    suite_name: str
    pressure_mode: str
    campaign_plan: dict[str, Any]
    campaign_truth: dict[str, Any]
    campaign_cohesion: dict[str, Any]
    scaling_projection: dict[str, Any]
    scaling_cohesion: dict[str, Any]
    readiness: dict[str, Any]
    attribution_alias_name: str
    readiness_alias_name: str
    campaign_kind: str = "design_suite_architecture_proof"


@dataclass(frozen=True)
class DesignSuiteRealCampaignAdapter:
    suite_id: str
    suite_name: str
    prepare_inputs: Callable[[Path, str], DesignSuiteRealCampaignInputs]


def build_design_suite_real_campaign_artifacts(
    *,
    campaign_id: str,
    suite_inputs: DesignSuiteRealCampaignInputs,
) -> dict[str, dict[str, Any]]:
    campaign_snapshot = build_design_suite_campaign_snapshot(
        campaign_id=campaign_id,
        suite_id=suite_inputs.suite_id,
        pressure_mode=suite_inputs.pressure_mode,
        active_modules=list(suite_inputs.campaign_plan.get("active_modules") or []),
        deferred_modules=list(suite_inputs.campaign_plan.get("deferred_modules") or []),
        campaign_kind=suite_inputs.campaign_kind,
    )
    campaign_truth = build_design_suite_campaign_truth(
        campaign_id,
        suite_inputs.campaign_plan,
        suite_inputs.campaign_truth,
    )
    campaign_cohesion = build_design_suite_campaign_cohesion(
        campaign_id,
        suite_inputs.campaign_plan,
        suite_inputs.scaling_cohesion,
    )
    attribution_review = build_design_suite_campaign_attribution_review(
        campaign_id,
        campaign_truth,
        campaign_cohesion,
        expected_suite_id=suite_inputs.suite_id,
        expected_active_module_count=len(list(suite_inputs.campaign_plan.get("active_modules") or [])),
    )
    reusable_campaign_seam = build_design_suite_reusable_campaign_seam(
        suite_inputs.campaign_plan,
        campaign_truth,
        campaign_cohesion,
        attribution_review,
    )
    return {
        "campaign_snapshot": campaign_snapshot,
        "campaign_truth": campaign_truth,
        "campaign_cohesion": campaign_cohesion,
        "attribution_review": attribution_review,
        "reusable_campaign_seam": reusable_campaign_seam,
    }


def write_design_suite_real_campaign_output(
    output_root: Path,
    *,
    campaign_id: str,
    suite_inputs: DesignSuiteRealCampaignInputs,
    artifacts: dict[str, dict[str, Any]],
) -> None:
    campaign_snapshot = artifacts["campaign_snapshot"]
    campaign_truth = artifacts["campaign_truth"]
    campaign_cohesion = artifacts["campaign_cohesion"]
    attribution_review = artifacts["attribution_review"]
    reusable_campaign_seam = artifacts["reusable_campaign_seam"]

    write_json(
        output_root / "campaign" / "session-manifest.json",
        {
            "campaign_id": campaign_id,
            "suite_id": suite_inputs.suite_id,
            "pressure_mode": suite_inputs.pressure_mode,
            "active_modules": campaign_snapshot["active_modules"],
        },
    )
    write_json(output_root / "campaign" / "campaign.json", campaign_snapshot)
    write_json(output_root / "shared" / "plans" / "campaign_plan.json", dict(suite_inputs.campaign_plan))
    write_json(
        output_root / "shared" / "evidence-graph" / "evidence_graph.json",
        {
            "campaign_id": campaign_id,
            "suite_id": suite_inputs.suite_id,
            "blocker_family_ids": campaign_truth["family_blocker_ids"],
        },
    )
    write_json(
        output_root / "campaign" / "checkpoints" / "campaign_checkpoint.json",
        {
            "campaign_id": campaign_id,
            "status": "completed",
            "suite_id": suite_inputs.suite_id,
            "pressure_mode": suite_inputs.pressure_mode,
        },
    )
    write_json(output_root / "campaign" / "campaign-truth.json", campaign_truth)
    write_json(output_root / "audits" / "campaign-cohesion-report.json", campaign_cohesion)
    write_json(output_root / "audits" / DESIGN_SUITE_CAMPAIGN_ATTRIBUTION_REVIEW_ARTIFACT, attribution_review)
    write_json(output_root / "audits" / suite_inputs.attribution_alias_name, attribution_review)
    write_json(output_root / DESIGN_SUITE_REUSABLE_CAMPAIGN_SEAM_ARTIFACT, reusable_campaign_seam)
    write_design_suite_artifact(output_root, DESIGN_SUITE_REAL_CAMPAIGN_READINESS_ARTIFACT, suite_inputs.readiness)
    write_design_suite_artifact(output_root, suite_inputs.readiness_alias_name, suite_inputs.readiness)


def finalize_design_suite_real_campaign(
    *,
    output_root: Path,
    campaign_id: str,
    suite_inputs: DesignSuiteRealCampaignInputs,
) -> dict[str, Any]:
    artifacts = build_design_suite_real_campaign_artifacts(
        campaign_id=campaign_id,
        suite_inputs=suite_inputs,
    )
    write_design_suite_real_campaign_output(
        output_root,
        campaign_id=campaign_id,
        suite_inputs=suite_inputs,
        artifacts=artifacts,
    )
    return artifacts
