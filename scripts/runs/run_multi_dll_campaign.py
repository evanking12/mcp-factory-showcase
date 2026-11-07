"""Multi-DLL campaign orchestrator — DAG-ordered scheduling across DLL targets.

Uses the evidence graph to determine execution order and parallelism.
DLLs with no cross-DLL dependencies run in parallel; dependent DLLs
wait for their producers to complete S-07.

Usage:
    python -m scripts.runs.run_multi_dll_campaign \
        --config configs/harness/matrix_contoso.json \
        --evidence-graph sessions/evidence_graph.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.campaign_stages import run_s_post, run_s_pre
from api.pipeline.core.evidence_graph import EvidenceGraph
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


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def run_campaign(
    config_path: Path,
    evidence_graph_path: Path | None = None,
    output_dir: Path | None = None,
    max_parallel: int = 1,
) -> dict[str, Any]:
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
        output_dir = REPO_ROOT / "sessions" / "campaigns" / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    campaign_log = output_dir / "campaign.log"
    heartbeat_path = output_dir / "heartbeats.json"

    # Load or create evidence graph
    if evidence_graph_path and evidence_graph_path.exists():
        graph = EvidenceGraph.load_json(evidence_graph_path)
    else:
        graph = EvidenceGraph()

    # Build target descriptors with fingerprints
    raw_targets = config.get("targets", [])
    targets: list[dict[str, Any]] = []
    for t in raw_targets:
        dll_path = Path(t["dll_path"])
        if not dll_path.is_absolute():
            dll_path = REPO_ROOT / dll_path
        fp = _fingerprint(str(dll_path))
        targets.append({
            "name": t["name"],
            "dll_path": str(dll_path),
            "dll_fingerprint": fp,
            "hints_file": t.get("hints_file", ""),
        })

    log_line(f"campaign-start targets={len(targets)} output={output_dir}", campaign_log)

    # Preflight
    api_ok, api_msg = verify_api_identity(api_url, api_key)
    if not api_ok:
        return {"error": f"api_identity_failed: {api_msg}"}
    bridge_ok, bridge_msg = verify_bridge_identity(bridge_url, bridge_key)
    if not bridge_ok:
        return {"error": f"bridge_identity_failed: {bridge_msg}"}

    # S-pre: cross-DLL planner
    plan = run_s_pre(graph, targets, output_dir / "campaign_plan.json")
    parallel_groups = plan.get("parallel_groups", [[t["dll_fingerprint"] for t in targets]])

    client = ApiClient(api_url, api_key)
    all_results: list[dict[str, Any]] = []
    completed_runs: list[dict[str, Any]] = []

    control_settings = {
        "mode": "normal",
        "cap_profile": "deploy",
        "max_rounds": 5,
        "max_tool_calls": 8,
        "gap_resolution_enabled": True,
        "skip_documented": True,
        "deterministic_fallback_enabled": True,
        "context_density": "full",
        "analysis_profile": analysis_profile,
        "parallel_runs": 1,
    }

    # Merge variant settings from config if present
    variants = config.get("variants", [])
    if variants:
        variant_settings = variants[0].get("explore_settings", {})
        control_settings.update(variant_settings)

    fp_to_target = {t["dll_fingerprint"]: t for t in targets}

    # Execute groups in order; within each group, run in parallel up to max_parallel
    for group_idx, group_fps in enumerate(parallel_groups):
        group_targets = [fp_to_target[fp] for fp in group_fps if fp in fp_to_target]
        if not group_targets:
            continue

        log_line(
            f"group-{group_idx} start: {len(group_targets)} DLLs "
            f"({', '.join(t['name'] for t in group_targets)})",
            campaign_log,
        )

        def _run_target(target: dict[str, Any]) -> dict[str, Any]:
            run_dir = output_dir / "runs" / target["name"]
            settings = dict(control_settings)
            settings["variant_id"] = "control"
            settings["lane_id"] = f"lane-{target['name']}"

            # Wire cross-DLL prior seeding from completed runs in earlier groups
            _cross_ids = [
                r["job_id"] for r in completed_runs
                if r.get("dll_fingerprint") != target["dll_fingerprint"]
                and r.get("job_id")
            ]
            if _cross_ids:
                settings["cross_dll_prior_job_ids"] = _cross_ids

            # Evidence-based focus_functions for re-probe targets
            recs = graph.re_probe_recommendations(target["dll_fingerprint"])
            if recs:
                settings["focus_functions"] = [r["function"] for r in recs]
                settings["skip_to_stage"] = "s02"
                settings["skip_to_stage_reason"] = "new_cross_dll_evidence"

            dll_path = Path(target["dll_path"])
            try:
                rec = run_one(
                    client, REPO_ROOT, run_dir, api_url, api_key,
                    target["name"], dll_path, "control", settings,
                    poll_sec, analyze_timeout, explore_timeout, stuck_seconds,
                    snapshot_profile, heartbeat_path, campaign_log,
                )
            except Exception as exc:
                rec = {
                    "run_id": target["name"],
                    "status": "failed",
                    "error": str(exc),
                }
            rec["dll_fingerprint"] = target["dll_fingerprint"]
            return rec

        if max_parallel > 1 and len(group_targets) > 1:
            with ThreadPoolExecutor(max_workers=min(max_parallel, len(group_targets))) as pool:
                futures = {pool.submit(_run_target, t): t for t in group_targets}
                for future in as_completed(futures):
                    rec = future.result()
                    all_results.append(rec)
                    if rec.get("status") == "ok" and rec.get("job_id"):
                        completed_runs.append(rec)
        else:
            for target in group_targets:
                rec = _run_target(target)
                all_results.append(rec)
                if rec.get("status") == "ok" and rec.get("job_id"):
                    completed_runs.append(rec)

    # S-post: knowledge consolidation
    s_post_inputs: list[dict[str, Any]] = []
    for rec in completed_runs:
        s_post_inputs.append({
            "dll_fingerprint": rec.get("dll_fingerprint", ""),
            "job_id": rec.get("job_id", ""),
            "findings": list((rec.get("latest_status_map") or {}).keys()),
            "vocab": {},
        })

    consolidation = run_s_post(graph, s_post_inputs, output_dir / "consolidation_report.json")

    # Save updated evidence graph
    graph_out = output_dir / "evidence_graph.json"
    graph.save_json(graph_out)
    if evidence_graph_path:
        graph.save_json(evidence_graph_path)

    summary = {
        "campaign_complete": True,
        "targets": len(targets),
        "total_runs": len(all_results),
        "ok_runs": sum(1 for r in all_results if r.get("status") == "ok"),
        "failed_runs": sum(1 for r in all_results if r.get("status") != "ok"),
        "parallel_groups": len(parallel_groups),
        "consolidation_summary": {
            "findings_ingested": consolidation.get("total_findings_ingested", 0),
            "new_edges": consolidation.get("total_edges_added", 0),
            "re_probe_functions": consolidation.get("re_probe_total_functions", 0),
        },
        "evidence_graph_path": str(graph_out),
    }
    write_json(output_dir / "campaign_summary.json", summary)
    log_line(
        f"campaign-end ok={summary['ok_runs']}/{summary['total_runs']} "
        f"groups={summary['parallel_groups']}",
        campaign_log,
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run multi-DLL campaign with DAG scheduling.")
    parser.add_argument("--config", type=Path, required=True, help="Campaign config JSON")
    parser.add_argument("--evidence-graph", type=Path, default=None, help="Evidence graph JSON path")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory")
    parser.add_argument("--max-parallel", type=int, default=1, help="Max parallel DLL runs per group")
    args = parser.parse_args()

    result = run_campaign(
        args.config,
        evidence_graph_path=args.evidence_graph,
        output_dir=args.output_dir,
        max_parallel=args.max_parallel,
    )
    if "error" in result:
        print(f"campaign-error: {result['error']}", file=sys.stderr)
        return 1
    print(f"Campaign complete: {result['ok_runs']}/{result['total_runs']} runs ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
