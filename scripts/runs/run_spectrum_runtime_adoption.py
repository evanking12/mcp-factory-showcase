from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.spectrum_runtime_adoption import (  # noqa: E402
    SPECTRUM_CASE_IDS,
    SPECTRUM_SUITE_ID,
    run_spectrum_runtime_adoption,
    spectrum_suite_root,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the spectrum local runtime/package proof for one case.")
    parser.add_argument("--case-id", default="easy-01", choices=SPECTRUM_CASE_IDS)
    parser.add_argument("--suite-root", default="")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_root = (
        Path(args.output_root)
        if str(args.output_root or "").strip()
        else REPO_ROOT / "sessions" / "design_suite" / "runtime_adoption" / SPECTRUM_SUITE_ID / str(args.case_id or "").strip() / timestamp
    )
    result = run_spectrum_runtime_adoption(
        case_id=str(args.case_id or "").strip(),
        suite_root=Path(args.suite_root) if str(args.suite_root or "").strip() else spectrum_suite_root(),
        output_root=output_root,
    )
    print(json.dumps({"output_dir": result["output_dir"], "case_id": args.case_id}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
