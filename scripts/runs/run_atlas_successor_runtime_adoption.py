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
    atlas_manifest_path,
    build_atlas_semantic_bundle,
    execute_atlas_first_slice,
    run_atlas_first_slice,
)
from api.pipeline.core.design_suite_expected_observed import write_design_suite_artifact  # noqa: E402
from api.pipeline.core.design_suite_runtime_bridge import (  # noqa: E402
    DESIGN_SUITE_COHESION_REPORT_ARTIFACT,
    DESIGN_SUITE_EXECUTION_TRACE_ARTIFACT,
    DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT,
    DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT,
    build_design_suite_cohesion_report,
    build_design_suite_package_truth,
    build_design_suite_runtime_projection,
)
from api.pipeline.core.design_suite_successor_contract import DEFAULT_SUCCESSOR_SUITE_CONTRACT  # noqa: E402


def run_atlas_successor_runtime_adoption(*, output_root: str | Path | None = None) -> dict[str, object]:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT / "sessions" / "design_suite" / "runtime_adoption" / "atlas_reconciliation_suite" / timestamp
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    artifact_bundle = run_atlas_first_slice(atlas_manifest_path(), output_dir=output_dir)
    semantic_bundle = build_atlas_semantic_bundle(artifact_bundle)
    execution_trace = execute_atlas_first_slice()
    manifest = json.loads(atlas_manifest_path().read_text(encoding="utf-8"))
    runtime_projection = build_design_suite_runtime_projection(
        DEFAULT_SUCCESSOR_SUITE_CONTRACT.to_dict(),
        manifest,
        semantic_bundle,
        execution_trace,
        "mutual_pressure",
    )
    package_truth = build_design_suite_package_truth(runtime_projection, execution_trace)
    cohesion_report = build_design_suite_cohesion_report(runtime_projection, package_truth)

    write_design_suite_artifact(output_dir, DESIGN_SUITE_EXECUTION_TRACE_ARTIFACT, execution_trace)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT, runtime_projection)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT, package_truth)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_COHESION_REPORT_ARTIFACT, cohesion_report)
    return {
        "output_dir": str(output_dir),
        "artifact_bundle": artifact_bundle,
        "semantic_bundle": semantic_bundle,
        "execution_trace": execution_trace,
        "runtime_projection": runtime_projection,
        "package_truth": package_truth,
        "cohesion_report": cohesion_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Atlas successor-suite local runtime/package proof.")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()
    result = run_atlas_successor_runtime_adoption(
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None
    )
    print(json.dumps({"output_dir": result["output_dir"], "pressure_mode": "mutual_pressure"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
