from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
from api.pipeline.core.design_suite_expected_observed import write_design_suite_artifact  # noqa: E402
from api.pipeline.core.design_suite_runtime_bridge import resolve_design_suite_pressure_mode  # noqa: E402
from scripts.runs.run_design_suite_runtime_adoption import run_design_suite_runtime_adoption  # noqa: E402


def run_design_suite_campaign_local(
    *,
    suite: str = "northstar_transaction_suite",
    mode: str = "late_confirmation",
    output_root: str | Path | None = None,
) -> dict[str, object]:
    normalized_mode = resolve_design_suite_pressure_mode(mode)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT / "sessions" / "design_suite" / "campaign_local" / suite / f"{timestamp}-{normalized_mode}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime_result = run_design_suite_runtime_adoption(
        suite=suite,
        mode=normalized_mode,
        output_root=output_dir,
    )
    runtime_projection = dict(runtime_result["runtime_projection"])
    package_truth = dict(runtime_result["package_truth"])
    cohesion_report = dict(runtime_result["cohesion_report"])
    execution_trace = dict(runtime_result["execution_trace"])

    campaign_plan = build_design_suite_campaign_local_plan(runtime_projection, package_truth)
    campaign_truth = build_design_suite_campaign_local_truth(campaign_plan, package_truth)
    campaign_cohesion = build_design_suite_campaign_local_cohesion(campaign_plan, cohesion_report)
    readiness_input = build_design_suite_campaign_readiness_input(
        campaign_plan,
        campaign_truth,
        campaign_cohesion,
        execution_trace,
    )

    write_design_suite_artifact(output_dir, DESIGN_SUITE_CAMPAIGN_PLAN_ARTIFACT, campaign_plan)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_CAMPAIGN_TRUTH_ARTIFACT, campaign_truth)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_CAMPAIGN_COHESION_ARTIFACT, campaign_cohesion)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_CAMPAIGN_EXECUTION_TRACE_ARTIFACT, execution_trace)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_CAMPAIGN_READINESS_INPUT_ARTIFACT, readiness_input)

    return {
        "output_dir": str(output_dir),
        "pressure_mode": normalized_mode,
        "campaign_plan": campaign_plan,
        "campaign_truth": campaign_truth,
        "campaign_cohesion": campaign_cohesion,
        "campaign_readiness_input": readiness_input,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local design-suite campaign-shaped rehearsal.")
    parser.add_argument("--suite", default="northstar_transaction_suite")
    parser.add_argument("--mode", default="late_confirmation")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    result = run_design_suite_campaign_local(
        suite=str(args.suite or "").strip(),
        mode=str(args.mode or "").strip(),
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
    )
    print(json.dumps({"output_dir": result["output_dir"], "pressure_mode": result["pressure_mode"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
