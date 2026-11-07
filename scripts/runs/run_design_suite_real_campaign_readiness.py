from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.design_suite_real_campaign_readiness import write_real_campaign_readiness  # noqa: E402
from scripts.runs.run_design_suite_real_campaign import ADAPTERS  # noqa: E402


def run_design_suite_real_campaign_readiness(
    *,
    suite: str,
    mode: str,
    output_root: str | Path | None = None,
) -> dict[str, object]:
    suite_id = str(suite or "").strip()
    adapter = ADAPTERS.get(suite_id)
    if adapter is None:
        raise ValueError(f"unknown design-suite real campaign target: {suite!r}")
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    resolved_output_root = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT / "sessions" / "design_suite" / "campaign_readiness" / suite_id / timestamp
    )
    resolved_output_root.mkdir(parents=True, exist_ok=True)
    suite_inputs = adapter.prepare_inputs(resolved_output_root, mode)
    path = write_real_campaign_readiness(
        resolved_output_root,
        suite_inputs.readiness_alias_name,
        suite_inputs.readiness,
    )
    return {
        "output_dir": str(resolved_output_root),
        "artifact_path": str(path),
        "readiness": suite_inputs.readiness,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit a design-suite real campaign readiness artifact.")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    result = run_design_suite_real_campaign_readiness(
        suite=str(args.suite or "").strip(),
        mode=str(args.mode or "").strip(),
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
    )
    print(json.dumps({"output_dir": result["output_dir"], "ready": result["readiness"]["ready_for_first_bounded_campaign"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
