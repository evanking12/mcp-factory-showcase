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

from api.pipeline.core.semantic_continuation import (  # noqa: E402
    load_semantic_continuation_packet,
)
from api.pipeline.core.spectrum_compiled_ingest import (  # noqa: E402
    SPECTRUM_COMPILED_MEDIUM01_CASE_ID,
    SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN,
    SPECTRUM_COMPILED_SUITE_ID,
    build_spectrum_compiled_medium01_continuation_report,
    ensure_spectrum_compiled_package_built,
    load_spectrum_authored_medium01_manifest,
    load_spectrum_authored_truth_manifest,
    load_spectrum_compiled_package_manifest,
    load_spectrum_compiled_truth_manifest,
    ordered_spectrum_compiled_medium01_targets,
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


def run_spectrum_compiled_medium01_continuation(
    *,
    continuation_path: str | Path,
    api_url: str = "",
    api_key: str = "",
    bridge_url: str = "",
    bridge_key: str = "",
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    packet = load_semantic_continuation_packet(continuation_path)
    if str(packet.get("suite_id") or "") != SPECTRUM_COMPILED_SUITE_ID:
        raise RuntimeError("continuation_packet_suite_mismatch")
    if str(packet.get("case_id") or "") != SPECTRUM_COMPILED_MEDIUM01_CASE_ID:
        raise RuntimeError("continuation_packet_case_mismatch")

    manifest = ensure_spectrum_compiled_package_built()
    compiled_truth = load_spectrum_compiled_truth_manifest()
    authored_truth = load_spectrum_authored_truth_manifest()
    authored_medium = load_spectrum_authored_medium01_manifest()

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

    continuation_id = str(packet.get("continuation_id") or "").strip()
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT
        / "sessions"
        / "design_suite"
        / "compiled_ingest"
        / SPECTRUM_COMPILED_SUITE_ID
        / SPECTRUM_COMPILED_MEDIUM01_CASE_ID
        / "continuations"
        / continuation_id
        / timestamp
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    campaign_log = output_dir / "compiled-ingest.log"
    heartbeat_path = output_dir / "heartbeats.json"
    client = ApiClient(resolved_api_url, resolved_api_key)

    trusted_predecessor_targets = [
        str(item) for item in list(packet.get("trusted_predecessor_targets") or []) if str(item).strip()
    ]
    trusted_predecessor_job_ids = [
        str(item) for item in list(packet.get("trusted_predecessor_job_ids") or []) if str(item).strip()
    ]
    trusted_job_by_target = dict(zip(trusted_predecessor_targets, trusted_predecessor_job_ids))
    retry_scope_targets = [
        str(item) for item in list(packet.get("retry_scope_targets") or []) if str(item).strip()
    ]

    selected_targets = [
        target
        for target in ordered_spectrum_compiled_medium01_targets(manifest)
        if str(target.get("target_name") or "").strip() in retry_scope_targets
    ]
    chain_step_by_target = {
        str(step["target_name"]): dict(step) for step in SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN
    }

    run_records: list[dict[str, Any]] = []
    successful_job_by_target = dict(trusted_job_by_target)
    for index, target in enumerate(selected_targets, start=1):
        dll_path = (REPO_ROOT / str(target.get("source_path") or "")).resolve()
        target_name = str(target.get("target_name") or Path(dll_path).stem).strip()
        chain_step = chain_step_by_target[target_name]
        predecessor_targets = list(chain_step.get("predecessor_targets") or [])
        prior_job_id = ""
        if predecessor_targets:
            prior_job_id = str(successful_job_by_target.get(predecessor_targets[-1]) or "").strip()
        cross_dll_prior_job_ids = [
            str(successful_job_by_target.get(name) or "").strip()
            for name in predecessor_targets
            if str(successful_job_by_target.get(name) or "").strip()
        ]
        run_dir = output_dir / "runs" / f"{index:02d}-{target_name}"
        log_line(f"spectrum-compiled-continuation-start target={target_name} dll={dll_path.name}", campaign_log)
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
            "variant_id": "compiled_medium01_continuation",
            "lane_id": f"spectrum-medium01-continuation-{index}",
            "binary_fixture_suite": SPECTRUM_COMPILED_SUITE_ID,
            "entry_surface": "upload",
            "prior_job_id": prior_job_id,
            "chain_step_target": target_name,
            "required_semantic_checkpoint": str(chain_step["required_semantic_checkpoint"]),
            "selected_invocable_names": [str(chain_step["required_semantic_checkpoint"])],
            "semantic_continuation_id": continuation_id,
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
            "compiled_medium01_continuation",
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
            "required_semantic_checkpoint": str(chain_step["required_semantic_checkpoint"]),
            "semantic_continuation_id": continuation_id,
        }
        run_records.append(record)
        job_id = str(record.get("job_id") or "").strip()
        if job_id and str(record.get("status") or "").strip().lower() == "ok":
            successful_job_by_target[target_name] = job_id

    report = build_spectrum_compiled_medium01_continuation_report(
        output_dir=output_dir,
        package_manifest=load_spectrum_compiled_package_manifest(),
        compiled_truth_manifest=compiled_truth,
        authored_truth_manifest=authored_truth,
        authored_medium_manifest=authored_medium,
        continuation_packet=packet,
        run_records=run_records,
    )

    original_gap = [str(item) for item in list(packet.get("semantic_checkpoint_gap") or []) if str(item).strip()]
    continued_gap = [str(item) for item in list(report.get("semantic_checkpoint_gap") or []) if str(item).strip()]
    resolved_checkpoints = [item for item in original_gap if item not in continued_gap]
    remaining_checkpoints = [item for item in continued_gap if item in original_gap]
    continuation_result = {
        "continuation_id": continuation_id,
        "source_packet": str(Path(continuation_path).resolve()),
        "original_semantic_checkpoint_gap": original_gap,
        "continued_semantic_checkpoint_gap": continued_gap,
        "gap_narrowed": len(continued_gap) < len(original_gap),
        "resolved_checkpoints": resolved_checkpoints,
        "remaining_checkpoints": remaining_checkpoints,
        "next_action": (
            "continue_medium01_fix_cycle"
            if remaining_checkpoints
            else "compiled_medium01_semantic_alignment_complete"
        ),
    }

    run_bundle = {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": SPECTRUM_COMPILED_MEDIUM01_CASE_ID,
        "entry_surface": "upload",
        "api_identity": api_msg,
        "bridge_identity": bridge_msg,
        "continuation_id": continuation_id,
        "source_packet": str(Path(continuation_path).resolve()),
        "compiled_targets": [
            {
                "staged_name": str(item.get("staged_name") or ""),
                "source_path": str(item.get("source_path") or ""),
                "target_name": str(item.get("target_name") or ""),
                "required_semantic_checkpoint": str(item.get("required_semantic_checkpoint") or ""),
            }
            for item in selected_targets
        ],
        "run_records": run_records,
        "comparison_report": report,
    }
    write_json(output_dir / "compiled-ingest-summary.json", run_bundle)
    write_json(output_dir / "compiled-ingest-compare-report.json", report)
    write_json(output_dir / "semantic-continuation-result.json", continuation_result)

    return {
        "output_dir": str(output_dir),
        "summary": run_bundle,
        "report": report,
        "continuation_result": continuation_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a narrow compiled Spectrum medium-01 continuation retry."
    )
    parser.add_argument("--continuation-path", required=True)
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--bridge-url", default="")
    parser.add_argument("--bridge-key", default="")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    result = run_spectrum_compiled_medium01_continuation(
        continuation_path=str(args.continuation_path).strip(),
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
                "compiled_binary_ingest_success": result["report"]["binary_ingest_proof_succeeded"],
                "semantic_checkpoint_alignment_succeeded": result["report"]["semantic_checkpoint_alignment_succeeded"],
                "gap_narrowed": result["continuation_result"]["gap_narrowed"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
