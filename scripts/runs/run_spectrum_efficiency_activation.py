from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.spectrum_efficiency_activation import (  # noqa: E402
    SPECTRUM_EFFICIENCY_CASE_ID,
    SPECTRUM_EFFICIENCY_SUITE_ID,
    build_activation_plan,
    build_operator_useful_map,
    build_package_inventory,
    build_pass_two_reuse_report,
    build_spectrum_efficiency_activation_report,
    ensure_spectrum_efficiency_package_built,
    load_spectrum_efficiency_benchmark_protocol,
    load_spectrum_efficiency_package_manifest,
    load_spectrum_efficiency_truth_manifest,
    ordered_spectrum_efficiency_pass_one_targets,
    ordered_spectrum_efficiency_pass_two_targets,
)
from scripts.ops.nightly_groundtruth import (  # noqa: E402
    ApiClient,
    log_line,
    run_one,
    verify_api_identity,
    verify_bridge_identity,
    write_json,
)
from runtime.runtime_contract import local_api_base_url, local_bridge_base_url  # noqa: E402


def _fingerprint_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_target_group(
    *,
    client: ApiClient,
    output_dir: Path,
    heartbeat_path: Path,
    campaign_log: Path,
    resolved_api_url: str,
    resolved_api_key: str,
    targets: list[dict[str, Any]],
    variant_id: str,
    phase_name: str,
    successful_job_by_target: dict[str, str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, target in enumerate(targets, start=1):
        dll_path = (REPO_ROOT / str(target.get("source_path") or "")).resolve()
        target_name = str(target.get("target_name") or Path(dll_path).stem).strip()
        predecessor_targets = list(target.get("predecessor_targets") or [])
        prior_job_id = ""
        if predecessor_targets:
            prior_job_id = str(successful_job_by_target.get(predecessor_targets[-1]) or "").strip()
        cross_dll_prior_job_ids = [
            str(successful_job_by_target.get(name) or "").strip()
            for name in predecessor_targets
            if str(successful_job_by_target.get(name) or "").strip()
        ]
        run_dir = output_dir / phase_name / f"{index:02d}-{target_name}"
        log_line(
            f"efficiency-activation-start phase={phase_name} target={target_name} dll={dll_path.name}",
            campaign_log,
        )
        explore_settings = {
            "mode": "normal",
            "cap_profile": "deploy",
            "max_rounds": 4,
            "max_tool_calls": 10,
            "gap_resolution_enabled": True,
            "skip_documented": True,
            "deterministic_fallback_enabled": True,
            "context_density": "full",
            "analysis_profile": "strict_dll",
            "parallel_runs": 1,
            "variant_id": variant_id,
            "lane_id": f"{SPECTRUM_EFFICIENCY_SUITE_ID}-{phase_name}-{index}",
            "binary_fixture_suite": SPECTRUM_EFFICIENCY_SUITE_ID,
            "entry_surface": "upload",
            "prior_job_id": prior_job_id,
            "chain_step_target": target_name,
            "required_semantic_checkpoint": str(target.get("primary_export") or ""),
            "selected_invocable_names": [str(target.get("primary_export") or "")],
            "activation_phase": phase_name,
        }
        if cross_dll_prior_job_ids:
            explore_settings["cross_dll_prior_job_ids"] = cross_dll_prior_job_ids
        record = run_one(
            client,
            REPO_ROOT,
            run_dir,
            resolved_api_url,
            resolved_api_key,
            target_name,
            dll_path,
            variant_id,
            explore_settings,
            poll_sec=10,
            analyze_timeout_sec=1800,
            explore_timeout_sec=5400,
            stuck_seconds=900,
            snapshot_profile="full",
            heartbeat_path=heartbeat_path,
            campaign_log=campaign_log,
        )
        record["dll_name"] = dll_path.name
        record["dll_path"] = str(dll_path)
        record["run_dir"] = str(run_dir)
        record["binary_hash"] = _fingerprint_bytes(dll_path)
        record["entry_surface"] = "upload"
        record["chain_context"] = {
            "target_name": target_name,
            "predecessor_targets": predecessor_targets,
            "prior_job_id": prior_job_id,
            "cross_dll_prior_job_ids": cross_dll_prior_job_ids,
            "required_semantic_checkpoint": str(target.get("primary_export") or ""),
        }
        records.append(record)
        job_id = str(record.get("job_id") or "").strip()
        if job_id and str(record.get("status") or "").strip().lower() == "ok":
            successful_job_by_target[target_name] = job_id
    return records


def run_spectrum_efficiency_activation(
    *,
    api_url: str = "",
    api_key: str = "",
    bridge_url: str = "",
    bridge_key: str = "",
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    manifest = ensure_spectrum_efficiency_package_built()
    truth_manifest = load_spectrum_efficiency_truth_manifest()
    protocol = load_spectrum_efficiency_benchmark_protocol()

    resolved_api_url = str(api_url or os.getenv("MCP_FACTORY_API_URL") or local_api_base_url()).strip()
    resolved_api_key = str(api_key or os.getenv("MCP_FACTORY_API_KEY", "")).strip()
    resolved_bridge_url = str(bridge_url or os.getenv("GUI_BRIDGE_URL", local_bridge_base_url())).strip()
    resolved_bridge_key = str(bridge_key or os.getenv("GUI_BRIDGE_SECRET", "")).strip()

    api_ok, api_msg = verify_api_identity(resolved_api_url, resolved_api_key)
    if not api_ok:
        raise RuntimeError(f"api_identity_failed:{api_msg}")
    bridge_ok, bridge_msg = verify_bridge_identity(resolved_bridge_url, resolved_bridge_key)
    if not bridge_ok:
        raise RuntimeError(f"bridge_identity_failed:{bridge_msg}")

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT
        / "sessions"
        / "design_suite"
        / "compiled_ingest"
        / SPECTRUM_EFFICIENCY_SUITE_ID
        / SPECTRUM_EFFICIENCY_CASE_ID
        / timestamp
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    campaign_log = output_dir / "efficiency-activation.log"
    heartbeat_path = output_dir / "heartbeats.json"
    client = ApiClient(resolved_api_url, resolved_api_key)

    package_inventory = build_package_inventory(manifest=manifest, truth_manifest=truth_manifest)
    write_json(output_dir / "package-inventory.json", package_inventory)

    pass_one_targets = ordered_spectrum_efficiency_pass_one_targets(manifest, protocol)
    pass_two_targets = ordered_spectrum_efficiency_pass_two_targets(manifest, protocol)
    pass_one_plan = build_activation_plan(protocol=protocol, phase="pass_one", targets=pass_one_targets)
    pass_two_plan = build_activation_plan(protocol=protocol, phase="pass_two", targets=pass_two_targets)
    pass_one_plan_path = output_dir / "activation-plan-pass-one.json"
    pass_two_plan_path = output_dir / "activation-plan-pass-two.json"
    write_json(pass_one_plan_path, pass_one_plan)
    write_json(pass_two_plan_path, pass_two_plan)

    successful_job_by_target: dict[str, str] = {}
    pass_one_records = _run_target_group(
        client=client,
        output_dir=output_dir,
        heartbeat_path=heartbeat_path,
        campaign_log=campaign_log,
        resolved_api_url=resolved_api_url,
        resolved_api_key=resolved_api_key,
        targets=pass_one_targets,
        variant_id="efficiency_activation_pass_one",
        phase_name="pass_one",
        successful_job_by_target=successful_job_by_target,
    )

    operator_useful_map = build_operator_useful_map(protocol=protocol, pass_one_records=pass_one_records)
    operator_useful_map_path = output_dir / "operator-useful-map.json"
    write_json(operator_useful_map_path, operator_useful_map)

    pass_two_records = _run_target_group(
        client=client,
        output_dir=output_dir,
        heartbeat_path=heartbeat_path,
        campaign_log=campaign_log,
        resolved_api_url=resolved_api_url,
        resolved_api_key=resolved_api_key,
        targets=pass_two_targets,
        variant_id="efficiency_activation_pass_two",
        phase_name="pass_two",
        successful_job_by_target=successful_job_by_target,
    )

    pass_two_reuse_report = build_pass_two_reuse_report(
        pass_one_plan_path=pass_one_plan_path,
        operator_useful_map_path=operator_useful_map_path,
        pass_one_records=pass_one_records,
        pass_two_records=pass_two_records,
    )
    pass_two_reuse_path = output_dir / "pass-two-reuse-report.json"
    write_json(pass_two_reuse_path, pass_two_reuse_report)

    report = build_spectrum_efficiency_activation_report(
        output_dir=output_dir,
        package_manifest=load_spectrum_efficiency_package_manifest(),
        truth_manifest=truth_manifest,
        protocol=protocol,
        pass_one_records=pass_one_records,
        pass_two_records=pass_two_records,
    )
    report_path = output_dir / "efficiency-activation-report.json"
    write_json(report_path, report)

    summary = {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_EFFICIENCY_SUITE_ID,
        "case_id": SPECTRUM_EFFICIENCY_CASE_ID,
        "entry_surface": "upload",
        "api_identity": api_msg,
        "bridge_identity": bridge_msg,
        "package_inventory_path": str(output_dir / "package-inventory.json"),
        "pass_one_plan_path": str(pass_one_plan_path),
        "pass_two_plan_path": str(pass_two_plan_path),
        "operator_useful_map_path": str(operator_useful_map_path),
        "pass_two_reuse_report_path": str(pass_two_reuse_path),
        "report_path": str(report_path),
        "pass_one_run_count": len(pass_one_records),
        "pass_two_run_count": len(pass_two_records),
    }
    write_json(output_dir / "efficiency-activation-summary.json", summary)
    return {
        "output_dir": str(output_dir),
        "summary": summary,
        "report": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the compiled Spectrum efficiency activation benchmark through the upload lane."
    )
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--bridge-url", default="")
    parser.add_argument("--bridge-key", default="")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    result = run_spectrum_efficiency_activation(
        api_url=str(args.api_url or "").strip(),
        api_key=str(args.api_key or "").strip(),
        bridge_url=str(args.bridge_url or "").strip(),
        bridge_key=str(args.bridge_key or "").strip(),
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
    )
    print(
        json.dumps(
            {
                "output_dir": result["output_dir"],
                "operator_useful_map_ready": result["report"]["operator_useful_map_ready"],
                "pass_two_reuse_not_restart": result["report"]["pass_two_reuse_not_restart"],
                "false_positive_frontier_respected": result["report"]["false_positive_frontier_respected"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
