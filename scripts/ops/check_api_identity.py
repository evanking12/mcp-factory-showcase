from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.runtime_contract import local_api_base_url  # noqa: E402
from scripts.ops.nightly_groundtruth import (  # noqa: E402
    build_api_identity_smoke_packet,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local pipeline API identity/readiness/admission.")
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    api_url = str(args.api_url or local_api_base_url()).strip()
    packet = build_api_identity_smoke_packet(api_url, str(args.api_key or "").strip())
    output = str(args.output or "").strip()
    if output:
        write_json(Path(output), packet)
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0 if str(packet.get("reason_code") or "") == "api_identity_green" else 2


if __name__ == "__main__":
    raise SystemExit(main())
