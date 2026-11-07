from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.weakness_register_triage import (  # noqa: E402
    WEAKNESS_REGISTER_PATH,
    build_weakness_register_triage,
    write_weakness_register_triage,
)


def _git_status_lines() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.rstrip() for line in result.stdout.splitlines() if line.strip()]


def run_weakness_register_triage(*, output_root: str | Path | None = None) -> dict[str, object]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    resolved_output_root = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT / "sessions" / "architecture" / "weakness_register_triage" / timestamp
    )
    register_text = WEAKNESS_REGISTER_PATH.read_text(encoding="utf-8")
    payload = build_weakness_register_triage(
        register_text=register_text,
        worktree_status_lines=_git_status_lines(),
    )
    artifact_path = write_weakness_register_triage(resolved_output_root, payload)
    return {
        "output_dir": str(resolved_output_root),
        "artifact_path": str(artifact_path),
        "triage": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit a weakness register triage artifact.")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    result = run_weakness_register_triage(
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None
    )
    print(
        json.dumps(
            {
                "output_dir": result["output_dir"],
                "artifact_path": result["artifact_path"],
                "next_prompt": result["triage"]["next_prompt"]["filename"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
