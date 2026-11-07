"""Ablation matrix runner — execute targets x cache_states x seeding_modes x variants.

Reads a matrix config JSON, serializes runs respecting bridge constraints (one run
at a time), and produces a matrix_report.json with cross-DLL gain analysis.

Usage:
    python -m scripts.runs.run_ablation_matrix --config configs/harness/matrix_contoso.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ops.nightly_groundtruth import (
    ApiClient,
    log_line,
    run_one,
    utc_iso,
    verify_api_identity,
    verify_bridge_identity,
    write_json,
)
from runtime.runtime_contract import local_api_base_url, local_bridge_base_url


def _build_matrix_cells(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the config cross-product into individual run cells."""
    cells: list[dict[str, Any]] = []
    targets = config["targets"]
    cache_states = config["cache_states"]
    seeding_modes = config["seeding_modes"]
    variants = config["variants"]

    for target, cache, seed_mode, variant in product(targets, cache_states, seeding_modes, variants):
        variant_id = variant["variant_id"]
        run_id = f"{target['name']}-{cache}-{seed_mode}-{variant_id}"
        cells.append({
            "run_id": run_id,
            "target_name": target["name"],
            "dll_path": target["dll_path"],
            "hints_file": target.get("hints_file", ""),
            "cache_state": cache,
            "seeding_mode": seed_mode,
            "variant_id": variant_id,
            "explore_settings": dict(variant.get("explore_settings") or {}),
        })
    return cells


def run_matrix(config_path: Path, output_dir: Path | None = None) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    execution = config.get("execution", {})
    api_url = execution.get("api_url") or os.getenv("MCP_FACTORY_API_URL") or local_api_base_url()
    api_key = os.getenv("MCP_FACTORY_API_KEY", "")
    bridge_url = execution.get("bridge_url") or os.getenv("GUI_BRIDGE_URL", local_bridge_base_url())
    bridge_key = os.getenv("GUI_BRIDGE_SECRET", "")
    poll_sec = execution.get("poll_sec", 10)
    analyze_timeout = execution.get("analyze_timeout_sec", 1800)
    explore_timeout = execution.get("explore_timeout_sec", 5400)
    stuck_seconds = execution.get("stuck_seconds", 900)
    snapshot_profile = execution.get("snapshot_profile", "full")
    analysis_profile = execution.get("analysis_profile", "strict_dll")

    if output_dir is None:
        slug = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = REPO_ROOT / "sessions" / "matrix" / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    campaign_log = output_dir / "matrix.log"
    heartbeat_path = output_dir / "heartbeats.json"

    cells = _build_matrix_cells(config)
    log_line(f"matrix-start cells={len(cells)} output={output_dir}", campaign_log)
    write_json(output_dir / "matrix_config.json", config)

    api_ok, api_msg = verify_api_identity(api_url, api_key)
    if not api_ok:
        return {"error": f"api_identity_failed: {api_msg}"}
    bridge_ok, bridge_msg = verify_bridge_identity(bridge_url, bridge_key)
    if not bridge_ok:
        return {"error": f"bridge_identity_failed: {bridge_msg}"}

    client = ApiClient(api_url, api_key)
    last_job_by_target: dict[str, str] = {}
    results: list[dict[str, Any]] = []

    for cell in cells:
        run_dir = output_dir / "runs" / cell["run_id"]
        settings = dict(cell["explore_settings"])
        settings["variant_id"] = cell["variant_id"]
        settings["analysis_profile"] = analysis_profile
        settings["lane_id"] = "lane-matrix"

        # Cache control
        is_cold = cell["cache_state"] == "cold"
        if is_cold:
            try:
                _headers = {"X-Bridge-Key": bridge_key} if bridge_key else {}
                requests.post(f"{bridge_url.rstrip('/')}/flush-dll-cache", headers=_headers, timeout=10)
            except Exception:
                pass

        # Seeding mode
        seed_mode = cell["seeding_mode"]
        if seed_mode == "warm" and last_job_by_target.get(cell["target_name"]):
            settings["prior_job_id"] = last_job_by_target[cell["target_name"]]
        elif seed_mode == "cross_dll":
            _cross = [jid for tgt, jid in last_job_by_target.items() if tgt != cell["target_name"] and jid]
            settings["cross_dll_prior_job_ids"] = _cross
            if last_job_by_target.get(cell["target_name"]):
                settings["prior_job_id"] = last_job_by_target[cell["target_name"]]
        else:
            settings["prior_job_id"] = ""

        dll_path = Path(cell["dll_path"])
        if not dll_path.is_absolute():
            dll_path = REPO_ROOT / dll_path

        log_line(
            f"cell-start {cell['run_id']} target={cell['target_name']} "
            f"cache={cell['cache_state']} seed={seed_mode}",
            campaign_log,
        )

        rec: dict[str, Any] | None = None
        try:
            rec = run_one(
                client, REPO_ROOT, run_dir, api_url, api_key,
                cell["target_name"], dll_path, cell["variant_id"], settings,
                poll_sec, analyze_timeout, explore_timeout, stuck_seconds,
                snapshot_profile, heartbeat_path, campaign_log,
            )
        except Exception as exc:
            rec = {
                "run_id": cell["run_id"],
                "status": "failed",
                "error": str(exc),
            }

        rec["matrix_cell"] = cell
        results.append(rec)
        if rec.get("job_id"):
            last_job_by_target[cell["target_name"]] = str(rec["job_id"])

    # Build matrix report
    report = _build_matrix_report(results)
    write_json(output_dir / "matrix_report.json", report)
    log_line(f"matrix-end cells={len(results)}", campaign_log)
    return report


def _build_matrix_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Produce a structured matrix report with cross-DLL gain analysis."""
    pivot: dict[str, dict[str, str]] = {}

    for rec in results:
        cell = rec.get("matrix_cell") or {}
        col_key = f"{cell.get('cache_state', '?')}/{cell.get('seeding_mode', '?')}/{cell.get('variant_id', '?')}"
        status_map = rec.get("latest_status_map") or {}
        for fn, status in status_map.items():
            pivot.setdefault(fn, {})[col_key] = str(status)

    cross_dll_gains: list[dict[str, Any]] = []
    for fn, col_statuses in pivot.items():
        no_seed = [s for k, s in col_statuses.items() if "/none/" in k]
        cross_seed = [s for k, s in col_statuses.items() if "/cross_dll/" in k]
        _upgraded_statuses = {"verified_success", "functional_precondition_unmet", "inferred_success", "success"}
        _base_statuses = {"failure", "unknown", "absent"}
        if any(s in _base_statuses for s in no_seed) and any(s in _upgraded_statuses for s in cross_seed):
            cross_dll_gains.append({
                "function": fn,
                "no_seed_statuses": no_seed,
                "cross_dll_statuses": cross_seed,
            })

    ok_results = [r for r in results if r.get("status") == "ok"]
    return {
        "total_cells": len(results),
        "ok_cells": len(ok_results),
        "failed_cells": len(results) - len(ok_results),
        "function_pivot": pivot,
        "cross_dll_gains": cross_dll_gains,
        "cross_dll_gain_count": len(cross_dll_gains),
        "per_cell_summary": [
            {
                "run_id": r.get("run_id"),
                "target": (r.get("matrix_cell") or {}).get("target_name"),
                "cache": (r.get("matrix_cell") or {}).get("cache_state"),
                "seed": (r.get("matrix_cell") or {}).get("seeding_mode"),
                "variant": (r.get("matrix_cell") or {}).get("variant_id"),
                "status": r.get("status"),
                "success_rate": (r.get("metrics") or {}).get("success_rate"),
                "verified_count": (r.get("metrics") or {}).get("verified_count"),
                "total_count": (r.get("metrics") or {}).get("total_count"),
            }
            for r in results
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ablation matrix experiment.")
    parser.add_argument("--config", type=Path, required=True, help="Matrix config JSON path")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory")
    args = parser.parse_args()

    report = run_matrix(args.config, args.output_dir)
    if "error" in report:
        print(f"matrix-error: {report['error']}", file=sys.stderr)
        return 1
    print(f"Matrix complete: {report['ok_cells']}/{report['total_cells']} cells ok, "
          f"{report['cross_dll_gain_count']} cross-DLL gains")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
