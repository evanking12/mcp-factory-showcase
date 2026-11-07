from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.atlas_successor_suite import (  # noqa: E402
    ATLAS_CAMPAIGN_READINESS_ARTIFACT,
    atlas_manifest_path,
)
from api.pipeline.core.design_suite_campaign_local import (  # noqa: E402
    DESIGN_SUITE_CAMPAIGN_COHESION_ARTIFACT,
    DESIGN_SUITE_CAMPAIGN_EXECUTION_TRACE_ARTIFACT,
    DESIGN_SUITE_CAMPAIGN_PLAN_ARTIFACT,
    DESIGN_SUITE_CAMPAIGN_READINESS_INPUT_ARTIFACT,
    DESIGN_SUITE_CAMPAIGN_TRUTH_ARTIFACT,
    build_design_suite_campaign_local_cohesion,
    build_design_suite_campaign_local_plan,
    build_design_suite_campaign_local_truth,
    build_design_suite_campaign_readiness_input,
)
from api.pipeline.core.design_suite_campaign_readiness import build_design_suite_campaign_readiness  # noqa: E402
from api.pipeline.core.design_suite_expected_observed import write_design_suite_artifact  # noqa: E402
from api.pipeline.core.design_suite_scaling_projection import (  # noqa: E402
    DESIGN_SUITE_SCALING_COHESION_ARTIFACT,
    DESIGN_SUITE_SCALING_PROJECTION_ARTIFACT,
    DESIGN_SUITE_SLICE_PLAN_ARTIFACT,
    build_design_suite_scaling_cohesion,
    build_design_suite_scaling_projection,
    build_design_suite_slice_plan,
)
from scripts.runs.run_atlas_successor_runtime_adoption import run_atlas_successor_runtime_adoption  # noqa: E402


def run_atlas_successor_campaign_local(*, output_root: str | Path | None = None) -> dict[str, object]:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT / "sessions" / "design_suite" / "campaign_local" / "atlas_reconciliation_suite" / timestamp
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime_result = run_atlas_successor_runtime_adoption(output_root=output_dir)
    runtime_projection = runtime_result["runtime_projection"]
    package_truth = runtime_result["package_truth"]
    cohesion_report = runtime_result["cohesion_report"]
    execution_trace = runtime_result["execution_trace"]
    semantic_bundle = runtime_result["semantic_bundle"]

    campaign_plan = build_design_suite_campaign_local_plan(runtime_projection, package_truth)
    campaign_truth = build_design_suite_campaign_local_truth(campaign_plan, package_truth)
    campaign_cohesion = build_design_suite_campaign_local_cohesion(campaign_plan, cohesion_report)
    readiness_input = build_design_suite_campaign_readiness_input(
        campaign_plan,
        campaign_truth,
        campaign_cohesion,
        execution_trace,
    )
    scaling_projection = build_design_suite_scaling_projection(
        campaign_plan,
        campaign_truth,
        campaign_cohesion,
        semantic_bundle,
    )
    slice_plan = build_design_suite_slice_plan(scaling_projection)
    scaling_cohesion = build_design_suite_scaling_cohesion(scaling_projection, slice_plan)
    readiness = build_design_suite_campaign_readiness(
        campaign_plan,
        campaign_truth,
        campaign_cohesion,
        scaling_projection,
        scaling_cohesion,
        target_mode="mutual_pressure",
        forked_state_guard={},
        require_forked_state_local_guard=False,
        artifact_type=ATLAS_CAMPAIGN_READINESS_ARTIFACT,
    )

    write_design_suite_artifact(output_dir, DESIGN_SUITE_CAMPAIGN_EXECUTION_TRACE_ARTIFACT, execution_trace)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_CAMPAIGN_PLAN_ARTIFACT, campaign_plan)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_CAMPAIGN_TRUTH_ARTIFACT, campaign_truth)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_CAMPAIGN_COHESION_ARTIFACT, campaign_cohesion)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_CAMPAIGN_READINESS_INPUT_ARTIFACT, readiness_input)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_SCALING_PROJECTION_ARTIFACT, scaling_projection)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_SLICE_PLAN_ARTIFACT, slice_plan)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_SCALING_COHESION_ARTIFACT, scaling_cohesion)
    write_design_suite_artifact(output_dir, ATLAS_CAMPAIGN_READINESS_ARTIFACT, readiness)
    return {
        "output_dir": str(output_dir),
        "campaign_plan": campaign_plan,
        "campaign_truth": campaign_truth,
        "campaign_cohesion": campaign_cohesion,
        "readiness_input": readiness_input,
        "scaling_projection": scaling_projection,
        "slice_plan": slice_plan,
        "scaling_cohesion": scaling_cohesion,
        "readiness": readiness,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Atlas successor-suite local campaign-shaped readiness proof.")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()
    result = run_atlas_successor_campaign_local(
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None
    )
    print(json.dumps({"output_dir": result["output_dir"], "ready": result["readiness"]["ready_for_first_bounded_campaign"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
