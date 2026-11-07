from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.decomposition_runtime_bridge import build_decomposition_campaign_plan  # noqa: E402
from api.pipeline.core.package_frontier_planner import build_package_frontier_plan  # noqa: E402
from scripts.runs.run_blocker_harvest_waves import (  # noqa: E402
    DEFAULT_API_KEY,
    DEFAULT_API_URL,
    DEFAULT_BRIDGE_KEY,
    DEFAULT_BRIDGE_URL,
    FIXTURE_MANIFESTS,
    TERMINAL_CAMPAIGN_PHASES,
    api_headers,
    attach_campaign_dll,
    build_fixture_package,
    create_campaign,
    download_snapshot,
    finalize_campaign_discovery,
    powershell_file,
    read_json,
    utc_iso,
    wait_for_lane_health,
    write_json,
    write_text,
)


WAVE_SUMMARY_PATH = (
    REPO_ROOT
    / "sessions"
    / "campaigns"
    / "blocker_harvest"
    / "20260406-104644"
    / "wave-2-batch-b"
    / "wave-summary.json"
)
DEFAULT_FRONTIER_DLLS = (
    "contoso_config.dll",
    "contoso_reporting.dll",
    "contoso_pricing.dll",
)


def _load_campaign_input(stage_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    campaign_request = read_json(stage_root / "campaign-request.json", {})
    attach_plan = list(read_json(stage_root / "attach-plan.json", []) or [])
    package_input = {
        "package_id": str(campaign_request.get("package_id") or "").strip(),
        "package_label": str(campaign_request.get("package_label") or "").strip(),
        "graph_epoch": "reduced-batch-b-decomposition",
        "package_context": dict(campaign_request.get("package_context") or {}),
        "dll_entries": [
            {
                "dll_id": str(row.get("staged_name") or "").strip(),
                "filename": str(row.get("staged_name") or "").strip(),
            }
            for row in attach_plan
            if str(row.get("staged_name") or "").strip()
        ],
    }
    return package_input, attach_plan


def _start_campaign_explore(
    session: requests.Session,
    *,
    api_url: str,
    api_key: str,
    campaign_id: str,
    decomposition_plan: dict[str, Any],
) -> dict[str, Any]:
    body = {
        "explore_settings": {
            "mode": "normal",
            "analysis_profile": "strict_dll",
            "lane_id": "lane-1",
            "parallel_runs": 1,
        },
        "decomposition_campaign_plan": decomposition_plan,
    }
    response = session.post(
        f"{api_url}/api/campaigns/{campaign_id}/explore",
        headers=api_headers(api_key),
        json=body,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def _poll_campaign(
    session: requests.Session,
    *,
    api_url: str,
    api_key: str,
    campaign_id: str,
    output_dir: Path,
    timeout_minutes: int = 90,
) -> dict[str, Any]:
    poll_path = output_dir / "campaign-poll.json"
    errors_path = output_dir / "campaign-poll-errors.json"
    deadline = time.time() + max(1, int(timeout_minutes)) * 60
    transient_errors: list[dict[str, Any]] = []
    while time.time() < deadline:
        try:
            response = session.get(
                f"{api_url}/api/campaigns/{campaign_id}",
                headers=api_headers(api_key),
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            write_json(poll_path, payload)
            if str(payload.get("phase") or "").lower() in TERMINAL_CAMPAIGN_PHASES:
                if transient_errors:
                    write_json(errors_path, transient_errors[-20:])
                return payload
        except requests.RequestException as exc:
            transient_errors.append({"checked_at": utc_iso(), "error": str(exc)})
            write_json(errors_path, transient_errors[-20:])
        time.sleep(5)
    raise RuntimeError(f"campaign {campaign_id} did not reach a terminal phase before poll timeout")


def _read_snapshot_json(snapshot_dir: Path, relative_path: str) -> dict[str, Any]:
    path = snapshot_dir / relative_path
    if not path.exists():
        return {}
    return read_json(path, {})


def _read_campaign_artifact_json(
    *,
    snapshot_dir: Path,
    campaign_id: str,
    filename: str,
) -> dict[str, Any]:
    relative_path = f"campaigns/{campaign_id}/{filename}"
    payload = _read_snapshot_json(snapshot_dir, relative_path)
    if payload:
        return payload
    fallback_path = REPO_ROOT / "local-data" / "artifacts" / "campaigns" / campaign_id / filename
    if fallback_path.exists():
        return read_json(fallback_path, {})
    return {}


def _build_live_audit(
    *,
    campaign_id: str,
    decomposition_plan: dict[str, Any],
    final_status: dict[str, Any],
    snapshot_dir: Path,
) -> dict[str, Any]:
    campaign_truth = _read_campaign_artifact_json(
        snapshot_dir=snapshot_dir,
        campaign_id=campaign_id,
        filename="campaign-truth.json",
    )
    cohesion_report = _read_campaign_artifact_json(
        snapshot_dir=snapshot_dir,
        campaign_id=campaign_id,
        filename="campaign-cohesion-report.json",
    )
    attribution_report = _read_campaign_artifact_json(
        snapshot_dir=snapshot_dir,
        campaign_id=campaign_id,
        filename="campaign-attribution-report.json",
    )

    expected_frontier = list(DEFAULT_FRONTIER_DLLS)
    actual_targets = list(decomposition_plan.get("active_dll_targets") or [])
    child_rows = [
        dict(row)
        for row in list(campaign_truth.get("per_dll") or [])
        if str(row.get("filename") or "").strip() in actual_targets
    ]
    imported_rows = [
        dict(row)
        for row in list(campaign_truth.get("per_dll") or [])
        if bool(row.get("imported_lower_floor"))
    ]
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_iso(),
        "campaign_id": campaign_id,
        "expected_frontier_dlls": expected_frontier,
        "active_dll_targets": actual_targets,
        "frontier_matches_expected": sorted(actual_targets) == sorted(expected_frontier),
        "phase": str(final_status.get("phase") or ""),
        "decomposition_plan_present": bool(campaign_truth.get("decomposition_plan_present")),
        "package_frontier_plan_present": bool(campaign_truth.get("package_frontier_plan_present")),
        "active_frontier_slice_ids": list(campaign_truth.get("active_frontier_slice_ids") or []),
        "imported_to_active_ratio": campaign_truth.get("imported_to_active_ratio", 0.0),
        "slice_execution_attribution_present": bool(campaign_truth.get("slice_execution_attribution_present")),
        "campaign_truth_present": bool(campaign_truth),
        "cohesion_decomposition_plan_present": bool(cohesion_report.get("decomposition_plan_present")),
        "attribution_decomposition_plan_present": bool(attribution_report.get("decomposition_plan_present")),
        "child_frontier_rows": child_rows,
        "imported_lower_floor_rows": imported_rows,
        "preserved_lower_floor_count": len(imported_rows),
        "preserved_lower_floor_reopened": any(
            str(row.get("filename") or "").strip() not in list(campaign_truth.get("imported_lower_floor_dlls") or [])
            for row in imported_rows
        ),
    }


def _render_note(audit: dict[str, Any]) -> str:
    lines = [
        "# Reduced Batch B Decomposition Run",
        "",
        f"- campaign id: `{audit['campaign_id']}`",
        f"- phase: `{audit['phase']}`",
        f"- active dll targets: {', '.join(audit.get('active_dll_targets') or []) or 'none'}",
        f"- frontier matches expected config/reporting/pricing: `{bool(audit.get('frontier_matches_expected'))}`",
        f"- decomposition plan present in campaign truth: `{bool(audit.get('decomposition_plan_present'))}`",
        f"- active frontier slice ids: {', '.join(audit.get('active_frontier_slice_ids') or []) or 'none'}",
        f"- imported-to-active ratio: `{audit.get('imported_to_active_ratio')}`",
        f"- slice execution attribution present: `{bool(audit.get('slice_execution_attribution_present'))}`",
        f"- preserved lower-floor count: `{int(audit.get('preserved_lower_floor_count') or 0)}`",
        f"- preserved lower-floor reopened: `{bool(audit.get('preserved_lower_floor_reopened'))}`",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one reduced Batch B campaign using decomposition-native slices.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--bridge-key", default=DEFAULT_BRIDGE_KEY)
    parser.add_argument("--wave-summary", default=str(WAVE_SUMMARY_PATH))
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_root = (
        Path(args.output_root)
        if args.output_root
        else REPO_ROOT / "sessions" / "engine_scaling" / "reduced_batch_b_decomposition" / timestamp
    )
    output_root.mkdir(parents=True, exist_ok=True)

    restart = powershell_file(REPO_ROOT / "sessions" / "restart_local_services.ps1", timeout_sec=180)
    write_json(
        output_root / "restart-local-services.json",
        {
            "returncode": restart.returncode,
            "stdout": restart.stdout[-4000:],
            "stderr": restart.stderr[-4000:],
            "completed_at": utc_iso(),
        },
    )
    if restart.returncode != 0:
        raise RuntimeError("local lane restart failed")

    lane_health = wait_for_lane_health(
        args.api_url,
        args.api_key,
        args.bridge_url,
        args.bridge_key,
    )
    write_json(output_root / "lane-health.json", lane_health)
    if not (lane_health.get("api_ok") and lane_health.get("bridge_ok") and lane_health.get("execute_ok")):
        raise RuntimeError(f"lane health failed: {lane_health}")

    manifest, campaign_request_path, attach_plan_path = build_fixture_package(FIXTURE_MANIFESTS[2], output_root)
    stage_root = campaign_request_path.parent
    package_input, attach_plan = _load_campaign_input(stage_root)
    wave_summary = read_json(Path(args.wave_summary), {})
    package_frontier_plan = build_package_frontier_plan(wave_summary)
    decomposition_plan = build_decomposition_campaign_plan(
        package_input,
        package_frontier_plan,
        target_shard_width=2,
        max_slice_dlls=3,
    )
    write_json(output_root / "package-frontier-plan.json", package_frontier_plan)
    write_json(output_root / "decomposition-campaign-plan.json", decomposition_plan)

    active_targets = list(decomposition_plan.get("active_dll_targets") or [])
    if sorted(active_targets) != sorted(DEFAULT_FRONTIER_DLLS):
        raise RuntimeError(f"unexpected active_dll_targets: {active_targets}")

    session = requests.Session()
    campaign_request = read_json(campaign_request_path, {})
    campaign_request["baseline_contract"] = dict(package_frontier_plan.get("baseline_contract") or {})
    campaign_id = create_campaign(session, args.api_url, campaign_request, args.api_key)
    write_json(output_root / "campaign-created.json", {"campaign_id": campaign_id, "request": campaign_request})

    attach_results: list[dict[str, Any]] = []
    for entry in attach_plan:
        attach_results.append(attach_campaign_dll(session, args.api_url, args.api_key, campaign_id, entry))
    write_json(output_root / "attach-results.json", attach_results)

    finalize_payload = finalize_campaign_discovery(session, args.api_url, args.api_key, campaign_id)
    write_json(output_root / "finalize-discovery.json", finalize_payload)

    explore_payload = _start_campaign_explore(
        session,
        api_url=args.api_url,
        api_key=args.api_key,
        campaign_id=campaign_id,
        decomposition_plan=decomposition_plan,
    )
    write_json(output_root / "explore-start.json", explore_payload)

    final_status = _poll_campaign(
        session,
        api_url=args.api_url,
        api_key=args.api_key,
        campaign_id=campaign_id,
        output_dir=output_root,
    )
    write_json(output_root / "campaign-final-status.json", final_status)

    snapshot_dir = download_snapshot(session, args.api_url, args.api_key, campaign_id, output_root)
    audit = _build_live_audit(
        campaign_id=campaign_id,
        decomposition_plan=decomposition_plan,
        final_status=final_status,
        snapshot_dir=snapshot_dir,
    )
    write_json(output_root / "reduced-batch-b-decomposition-audit.json", audit)
    write_text(output_root / "reduced-batch-b-decomposition-note.md", _render_note(audit))

    print(json.dumps({"campaign_id": campaign_id, "phase": final_status.get("phase"), "output_root": str(output_root)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
