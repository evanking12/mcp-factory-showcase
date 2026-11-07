from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.regression.replay_hard03_reservation_managed_lane import (
    replay_hard03_managed_lane_target,
)


TARGET = "attestation_stage"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay Hard03 attestation_stage through the managed API/worker lane only."
    )
    parser.add_argument("--source-proof-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--mode", default="strict", choices=["strict"])
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--poll-sec", default=2, type=int)
    parser.add_argument("--analyze-timeout-sec", default=240, type=int)
    parser.add_argument("--explore-timeout-sec", default=360, type=int)
    parser.add_argument("--stuck-seconds", default=120, type=int)
    args = parser.parse_args(argv)
    result = replay_hard03_managed_lane_target(
        source_proof_root=args.source_proof_root,
        output_root=args.output_root,
        target=TARGET,
        mode=args.mode,
        api_url=args.api_url,
        api_key=args.api_key,
        poll_sec=args.poll_sec,
        analyze_timeout_sec=args.analyze_timeout_sec,
        explore_timeout_sec=args.explore_timeout_sec,
        stuck_seconds=args.stuck_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("classification") != "trusted_predecessor_boundary_unavailable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
