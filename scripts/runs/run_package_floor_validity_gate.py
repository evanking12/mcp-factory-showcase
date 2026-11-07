from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.package_floor_validity import (  # noqa: E402
    build_package_floor_validity_gate,
    write_package_floor_validity_artifacts,
)
from scripts.runs.run_blocker_harvest_waves import read_json, write_json, write_text  # noqa: E402


def _load_campaign_truth(run_root: Path) -> dict[str, Any]:
    for candidate in (
        run_root / "snapshot" / "campaign" / "campaign-truth.json",
        run_root / "snapshot" / "campaign-truth.json",
        run_root / "campaign-truth.json",
    ):
        payload = read_json(candidate, {})
        if payload:
            return payload
    return {}


def _run_live_reduced_batch_b(output_root: Path) -> Path:
    live_root = output_root / "reduced_batch_b_live"
    live_root.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "runs" / "run_reduced_batch_b_decomposition.py"),
            "--output-root",
            str(live_root),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=7200,
        check=False,
    )
    write_json(
        output_root / "reduced-batch-b-live-process.json",
        {
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-12000:],
            "stderr_tail": proc.stderr[-12000:],
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "live_output_root": str(live_root),
        },
    )
    if proc.returncode != 0:
        raise RuntimeError("reduced Batch B live proof failed")
    return live_root


def _render_note(gate: dict[str, Any]) -> str:
    lines = [
        "# Package-Floor Validity Gate",
        "",
        f"- campaign id: `{gate.get('campaign_id')}`",
        f"- package floor evidence class: `{gate.get('package_floor_evidence_class')}`",
        f"- claim scope: `{gate.get('claim_scope')}`",
        f"- valid for package-floor claim: `{bool(gate.get('valid_for_package_floor_claim'))}`",
        f"- valid for comparable policy: `{bool(gate.get('valid_for_comparable_policy'))}`",
        f"- canonical entry surface: `{gate.get('canonical_entry_surface') or 'none'}`",
        f"- frontier jobs fresh: `{bool(gate.get('frontier_jobs_fresh'))}`",
        f"- frontier jobs terminal: `{bool(gate.get('frontier_jobs_terminal'))}`",
        f"- runtime path trusted: `{bool(gate.get('runtime_path_trusted'))}`",
        f"- lane trusted: `{bool(gate.get('lane_trusted'))}`",
        f"- disqualifiers: {', '.join(gate.get('disqualifiers') or []) or 'none'}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and audit the reduced Batch B package-floor validity gate.")
    parser.add_argument("--run-root", default="", help="Existing reduced Batch B decomposition run root to audit.")
    parser.add_argument("--output-root", default="", help="Output directory for package-floor validity artifacts.")
    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_root = (
        Path(args.output_root)
        if args.output_root
        else REPO_ROOT / "sessions" / "engine_scaling" / "package_floor_validity" / timestamp
    )
    output_root.mkdir(parents=True, exist_ok=True)

    run_root = Path(args.run_root) if args.run_root else _run_live_reduced_batch_b(output_root)
    audit = read_json(run_root / "reduced-batch-b-decomposition-audit.json", {})
    campaign_truth = _load_campaign_truth(run_root)
    final_status = read_json(run_root / "campaign-final-status.json", {})
    if not audit or not campaign_truth or not final_status:
        raise RuntimeError(f"run root {run_root} is missing reduced Batch B proof artifacts")

    gate = build_package_floor_validity_gate(
        campaign_truth=campaign_truth,
        final_status=final_status,
    )
    write_package_floor_validity_artifacts(output_root, gate)
    write_text(output_root / "package-floor-validity-note.md", _render_note(gate))
    write_json(
        output_root / "package-floor-validity-inputs.json",
        {
            "audited_run_root": str(run_root),
            "campaign_id": gate.get("campaign_id"),
            "package_id": gate.get("package_id"),
            "active_frontier_dlls": audit.get("active_dll_targets") or [],
            "frontier_matches_expected": bool(audit.get("frontier_matches_expected")),
            "prior_audit_path": str(run_root / "reduced-batch-b-decomposition-audit.json"),
        },
    )

    print(
        json.dumps(
            {
                "output_root": str(output_root),
                "campaign_id": gate.get("campaign_id"),
                "valid_for_package_floor_claim": gate.get("valid_for_package_floor_claim"),
                "valid_for_comparable_policy": gate.get("valid_for_comparable_policy"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
