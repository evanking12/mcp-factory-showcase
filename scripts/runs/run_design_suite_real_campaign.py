from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.atlas_successor_suite import ATLAS_CAMPAIGN_READINESS_ARTIFACT  # noqa: E402
from api.pipeline.core.design_suite_campaign_readiness import DESIGN_SUITE_CAMPAIGN_READINESS_ARTIFACT  # noqa: E402
from api.pipeline.core.design_suite_campaign_readiness import build_design_suite_campaign_readiness  # noqa: E402
from api.pipeline.core.design_suite_real_campaign_runtime import (  # noqa: E402
    DesignSuiteRealCampaignAdapter,
    DesignSuiteRealCampaignInputs,
    finalize_design_suite_real_campaign,
)
from scripts.runs.run_atlas_successor_campaign_local import run_atlas_successor_campaign_local  # noqa: E402
from scripts.runs.run_design_suite_campaign_local import run_design_suite_campaign_local  # noqa: E402
from scripts.runs.run_design_suite_scaling_projection import run_design_suite_scaling_projection  # noqa: E402


def _prepare_northstar_inputs(output_root: Path, mode: str) -> DesignSuiteRealCampaignInputs:
    local_result = run_design_suite_campaign_local(
        suite="northstar_transaction_suite",
        mode=mode,
        output_root=output_root,
    )
    scaling_result = run_design_suite_scaling_projection(output_root)
    if mode == "forked_state":
        forked_guard = local_result["campaign_truth"]
    else:
        forked_guard = run_design_suite_campaign_local(
            suite="northstar_transaction_suite",
            mode="forked_state",
            output_root=output_root / "forked_state_guard",
        )["campaign_truth"]
    readiness = build_design_suite_campaign_readiness(
        local_result["campaign_plan"],
        local_result["campaign_truth"],
        local_result["campaign_cohesion"],
        scaling_result["scaling_projection"],
        scaling_result["scaling_cohesion"],
        target_mode=mode,
        forked_state_guard=forked_guard,
    )
    return DesignSuiteRealCampaignInputs(
        suite_id="northstar_transaction_suite",
        suite_name="Northstar Transaction Suite",
        pressure_mode=mode,
        campaign_plan=dict(local_result["campaign_plan"]),
        campaign_truth=dict(local_result["campaign_truth"]),
        campaign_cohesion=dict(local_result["campaign_cohesion"]),
        scaling_projection=dict(scaling_result["scaling_projection"]),
        scaling_cohesion=dict(scaling_result["scaling_cohesion"]),
        readiness=readiness,
        attribution_alias_name="northstar-campaign-attribution-review.json",
        readiness_alias_name=DESIGN_SUITE_CAMPAIGN_READINESS_ARTIFACT,
    )


def _prepare_atlas_inputs(output_root: Path, mode: str) -> DesignSuiteRealCampaignInputs:
    if mode != "mutual_pressure":
        raise ValueError("Atlas currently supports only mutual_pressure for real campaign admission")
    local_result = run_atlas_successor_campaign_local(output_root=output_root)
    return DesignSuiteRealCampaignInputs(
        suite_id="atlas_reconciliation_suite",
        suite_name="Atlas Reconciliation Suite",
        pressure_mode="mutual_pressure",
        campaign_plan=dict(local_result["campaign_plan"]),
        campaign_truth=dict(local_result["campaign_truth"]),
        campaign_cohesion=dict(local_result["campaign_cohesion"]),
        scaling_projection=dict(local_result["scaling_projection"]),
        scaling_cohesion=dict(local_result["scaling_cohesion"]),
        readiness=dict(local_result["readiness"]),
        attribution_alias_name="atlas-campaign-attribution-review.json",
        readiness_alias_name=ATLAS_CAMPAIGN_READINESS_ARTIFACT.replace("campaign", "real-campaign"),
    )


ADAPTERS: dict[str, DesignSuiteRealCampaignAdapter] = {
    "northstar_transaction_suite": DesignSuiteRealCampaignAdapter(
        suite_id="northstar_transaction_suite",
        suite_name="Northstar Transaction Suite",
        prepare_inputs=_prepare_northstar_inputs,
    ),
    "atlas_reconciliation_suite": DesignSuiteRealCampaignAdapter(
        suite_id="atlas_reconciliation_suite",
        suite_name="Atlas Reconciliation Suite",
        prepare_inputs=_prepare_atlas_inputs,
    ),
}


def run_design_suite_real_campaign(
    *,
    suite: str,
    mode: str,
    output_root: str | Path | None = None,
) -> dict[str, object]:
    suite_id = str(suite or "").strip()
    adapter = ADAPTERS.get(suite_id)
    if adapter is None:
        raise ValueError(f"unknown design-suite real campaign target: {suite!r}")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    campaign_id = f"{suite_id}-{timestamp}-{mode}"
    resolved_output_root = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT / "sessions" / "campaigns" / campaign_id
    )
    resolved_output_root.mkdir(parents=True, exist_ok=True)

    suite_inputs = adapter.prepare_inputs(resolved_output_root, mode)
    if not suite_inputs.readiness.get("ready_for_first_bounded_campaign"):
        raise RuntimeError(
            f"{suite_id} campaign readiness failed: {suite_inputs.readiness.get('blocking_reasons')}"
        )
    artifacts = finalize_design_suite_real_campaign(
        output_root=resolved_output_root,
        campaign_id=campaign_id,
        suite_inputs=suite_inputs,
    )
    return {
        "campaign_id": campaign_id,
        "output_dir": str(resolved_output_root),
        "suite_id": suite_id,
        "pressure_mode": suite_inputs.pressure_mode,
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a design-suite real bounded campaign.")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    result = run_design_suite_real_campaign(
        suite=str(args.suite or "").strip(),
        mode=str(args.mode or "").strip(),
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
    )
    print(json.dumps({"campaign_id": result["campaign_id"], "output_dir": result["output_dir"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
