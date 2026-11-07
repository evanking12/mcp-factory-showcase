from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


DESIGN_SUITE_REAL_CAMPAIGN_CONTRACT_ARTIFACT = "design-suite-real-campaign-contract.json"


@dataclass(frozen=True)
class DesignSuiteRealCampaignContract:
    contract_name: str = "Design Suite Real Campaign Contract"
    owner_module: str = "api/pipeline/core/design_suite_real_campaign_runtime.py"
    entry_runner: str = "scripts/runs/run_design_suite_real_campaign.py"
    campaign_surface: str = "design_suite_bounded_campaign"
    compare_ready: bool = False
    promotion_ready: bool = False
    inherited_artifacts: tuple[str, ...] = (
        "campaign/campaign.json",
        "campaign/campaign-truth.json",
        "audits/campaign-cohesion-report.json",
        "audits/design-suite-campaign-attribution-review.json",
        "design-suite-reusable-campaign-seam.json",
    )
    suite_specific_wrapper_role: tuple[str, ...] = (
        "suite selection and default mode",
        "suite-specific attribution alias naming",
        "suite-specific readiness artifact alias naming",
    )
    still_not_generic: tuple[str, ...] = (
        "compare or promotion policy",
        "collector or ledger integration",
        "multi-suite orchestration",
    )
    artifact_type: str = DESIGN_SUITE_REAL_CAMPAIGN_CONTRACT_ARTIFACT
    schema_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if self.compare_ready or self.promotion_ready:
            raise ValueError("real campaign contract must remain non-compare and non-promotion ready")
        if not self.owner_module or not self.entry_runner:
            raise ValueError("owner_module and entry_runner must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_DESIGN_SUITE_REAL_CAMPAIGN_CONTRACT = DesignSuiteRealCampaignContract()
