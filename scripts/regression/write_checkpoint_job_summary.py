from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a GitHub job summary for a single compiled checkpoint.")
    parser.add_argument("--packet", required=True, type=Path)
    args = parser.parse_args(argv)

    packet = _read_json(args.packet) if args.packet.exists() else {}
    last_observation = packet.get("last_observation")
    if not isinstance(last_observation, dict):
        last_observation = (packet.get("run_record") or {}).get("last_observation")
    if not isinstance(last_observation, dict):
        last_observation = {}
    lines = [
        f"## {packet.get('target_name') or 'checkpoint'}",
        "",
        f"- Verdict: `{packet.get('verdict') or 'unknown'}`",
        f"- Job id: `{packet.get('job_id') or ''}`",
        f"- Phase: `{packet.get('phase') or ''}`",
        f"- Failure class: `{packet.get('failure_kind') or ''}`",
    ]
    if str(packet.get("message") or "").strip():
        lines.append(f"- First concrete cause: `{packet.get('message')}`")
    if last_observation:
        span = str(last_observation.get("span") or "").strip()
        span_part = f"span={span}; " if span else ""
        lines.extend(
            [
                "- Last observation: "
                f"`stage={last_observation.get('stage') or ''}; "
                f"{span_part}"
                f"phase={last_observation.get('explore_phase') or last_observation.get('phase') or ''}; "
                f"progress={last_observation.get('progress') or ''}; "
                f"signature_stable={last_observation.get('signature_stable_seconds')}s`",
            ]
        )
        if str(last_observation.get("soft_stall_hint") or "").strip():
            lines.append(f"- Suspected stall: `{last_observation.get('soft_stall_hint')}`")
    summary_path = str(os.getenv("GITHUB_STEP_SUMMARY") or "").strip()
    markdown = "\n".join(lines) + "\n"
    if summary_path:
        Path(summary_path).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
