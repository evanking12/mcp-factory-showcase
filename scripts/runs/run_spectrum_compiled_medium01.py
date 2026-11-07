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

from api.pipeline.core.spectrum_compiled_ingest import (  # noqa: E402
    SPECTRUM_COMPILED_MEDIUM01_CASE_ID,
    SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN,
    SPECTRUM_COMPILED_SUITE_ID,
    build_spectrum_compiled_medium01_report,
    ensure_spectrum_compiled_package_built,
    load_spectrum_authored_medium01_manifest,
    load_spectrum_authored_truth_manifest,
    load_spectrum_compiled_package_manifest,
    load_spectrum_compiled_truth_manifest,
    ordered_spectrum_compiled_medium01_targets,
)
from api.pipeline.core.semantic_continuation import (  # noqa: E402
    emit_spectrum_medium01_semantic_continuation,
)
from scripts.ops.nightly_groundtruth import (  # noqa: E402
    ApiClient,
    ensure_strict_local_lane_preflight,
    log_line,
    resolve_bridge_secret,
    run_one,
    verify_api_identity,
    verify_bridge_identity,
    write_json,
)
from scripts.runs.product_route_contract import (  # noqa: E402
    product_contract_fields_for_record as _product_contract_fields_for_record,
    product_contract_summary as _product_contract_summary,
    product_route_authority_for_record as _product_route_authority_for_record,
)
from runtime.runtime_contract import local_api_base_url, local_bridge_base_url  # noqa: E402


def _fingerprint_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_target_names(raw: str | None) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if str(item or "").strip()]


def _parse_job_ids(raw: str | None) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if str(item or "").strip()]


def _failure_kind_for_record(record: dict[str, Any]) -> str:
    terminalization = dict(record.get("job_terminalization") or {})
    kind = str(terminalization.get("terminalization_kind") or terminalization.get("kind") or "").strip()
    phase = str(record.get("phase") or "").strip().lower()
    if kind == "timeout":
        if phase.startswith("analy"):
            return "analyze_timeout"
        if phase.startswith("explor"):
            return "explore_timeout"
        return "timeout"
    if kind and kind != "done":
        return f"runner_{kind}"
    if str(record.get("failure_domain") or "").strip():
        return str(record.get("failure_domain") or "").strip()
    if str(record.get("error") or "").strip():
        return "runner_error"
    if str(record.get("status") or "").strip().lower() != "ok":
        return f"status_{str(record.get('status') or '').strip().lower()}"
    return ""


def _failure_message_for_record(record: dict[str, Any]) -> str:
    terminalization = dict(record.get("job_terminalization") or {})
    reason = dict(terminalization.get("reason") or {})
    if str(reason.get("message") or "").strip():
        return str(reason.get("message") or "").strip()
    if str(record.get("error") or "").strip():
        return str(record.get("error") or "").strip()
    blocking = list((record.get("run_authority") or {}).get("blocking_reasons") or [])
    if blocking:
        return ", ".join(str(item) for item in blocking if str(item).strip())
    return ""


def _dependency_blocked_record(
    *,
    run_dir: Path,
    target_name: str,
    dll_path: Path,
    predecessor_targets: list[str],
    missing_predecessors: list[str],
    chain_step: dict[str, Any],
    resolved_prior_job_id: str,
    resolved_cross_dll_prior_job_ids: list[str],
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    run_authority = {
        "schema_version": "1.0.0",
        "target": target_name,
        "status": "non_decision_bearing",
        "reason_code": "dependency_blocked",
        "failure_domain": "dependency_policy",
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "authoritative_proving": False,
        "decision_bearing": False,
        "blocking_reasons": [f"missing_predecessor:{name}" for name in missing_predecessors],
    }
    terminalization = {
        "schema_version": "1.0.0",
        "target": target_name,
        "terminalization_kind": "dependency_blocked",
        "kind": "dependency_blocked",
        "reason": {
            "code": "dependency_blocked",
            "message": "required predecessor was non-comparable or did not produce a trusted job id",
        },
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "authoritative_proving": False,
        "missing_predecessors": missing_predecessors,
    }
    record = {
        "job_id": "",
        "status": "dependency_blocked",
        "phase": "not_scheduled",
        "target": target_name,
        "dll_name": dll_path.name,
        "dll_path": str(dll_path),
        "run_dir": str(run_dir),
        "binary_hash": _fingerprint_bytes(dll_path),
        "entry_surface": "upload",
        "valid_run": False,
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "authoritative_proving": False,
        "failure_domain": "dependency_policy",
        "run_authority": run_authority,
        "measurement_terminalization": terminalization,
        "chain_context": {
            "target_name": target_name,
            "predecessor_targets": predecessor_targets,
            "prior_job_id": resolved_prior_job_id,
            "cross_dll_prior_job_ids": resolved_cross_dll_prior_job_ids,
            "required_semantic_checkpoint": str(chain_step["required_semantic_checkpoint"]),
        },
    }
    write_json(run_dir / "run-authority.json", run_authority)
    write_json(run_dir / "measurement-terminalization.json", terminalization)
    write_json(run_dir / "run_result.json", record)
    return record


def _write_checkpoint_artifacts(
    *,
    output_dir: Path,
    case_id: str,
    suite_id: str,
    chain_step: dict[str, Any],
    run_record: dict[str, Any],
    api_identity: str,
    bridge_identity: str,
) -> dict[str, Any]:
    run_dir = Path(str(run_record.get("run_dir") or "")).resolve()
    verdict = "pass" if str(run_record.get("status") or "").strip().lower() == "ok" else "fail"
    packet = {
        "schema_version": "1.0.0",
        "suite_id": suite_id,
        "case_id": case_id,
        "target_name": str(chain_step.get("target_name") or "").strip(),
        "staged_name": str(chain_step.get("staged_name") or "").strip(),
        "required_semantic_checkpoint": str(chain_step.get("required_semantic_checkpoint") or "").strip(),
        "predecessor_targets": list(chain_step.get("predecessor_targets") or []),
        "verdict": verdict,
        "job_id": str(run_record.get("job_id") or "").strip(),
        "status": str(run_record.get("status") or "").strip(),
        "phase": str(run_record.get("phase") or "").strip(),
        "failure_kind": _failure_kind_for_record(run_record),
        "message": _failure_message_for_record(run_record),
        "last_observation": dict(run_record.get("last_observation") or {}),
        "api_identity": api_identity,
        "bridge_identity": bridge_identity,
        "run_dir_relative": str(run_dir.relative_to(output_dir)) if run_dir.is_relative_to(output_dir) else "",
        "run_record": run_record,
    }
    write_json(output_dir / "checkpoint-result.json", packet)
    write_json(output_dir / "run-record.json", run_record)
    return packet


def run_spectrum_compiled_medium01(
    *,
    api_url: str = "",
    api_key: str = "",
    bridge_url: str = "",
    bridge_key: str = "",
    output_root: str | Path | None = None,
    stop_after_first_failure: bool = False,
    target_names: list[str] | None = None,
    prior_job_id: str = "",
    cross_dll_prior_job_ids: list[str] | None = None,
    product_route_required: bool = False,
    case_id: str = SPECTRUM_COMPILED_MEDIUM01_CASE_ID,
    variant_id: str = "compiled_medium01",
    poll_sec: int = 10,
    analyze_timeout_sec: int = 1800,
    explore_timeout_sec: int = 5400,
    stuck_seconds: int = 900,
    emit_semantic_continuation_packet: bool = True,
) -> dict[str, Any]:
    manifest = ensure_spectrum_compiled_package_built()
    compiled_truth = load_spectrum_compiled_truth_manifest()
    authored_truth = load_spectrum_authored_truth_manifest()
    authored_medium = load_spectrum_authored_medium01_manifest()

    resolved_api_url = str(api_url or os.getenv("MCP_FACTORY_API_URL") or local_api_base_url()).strip()
    resolved_api_key = str(api_key or os.getenv("MCP_FACTORY_API_KEY", "")).strip()
    resolved_bridge_url = str(bridge_url or os.getenv("GUI_BRIDGE_URL", local_bridge_base_url())).strip()
    resolved_bridge_key = resolve_bridge_secret(bridge_key)

    api_ok, api_msg = verify_api_identity(resolved_api_url, resolved_api_key)
    if not api_ok:
        raise RuntimeError(f"api_identity_failed:{api_msg}")
    bridge_ok, bridge_msg = verify_bridge_identity(resolved_bridge_url, resolved_bridge_key)
    if not bridge_ok:
        raise RuntimeError(f"bridge_identity_failed:{bridge_msg}")
    strict_local_preflight = ensure_strict_local_lane_preflight(
        api_url=resolved_api_url,
        api_key=resolved_api_key,
        bridge_url=resolved_bridge_url,
        bridge_key=resolved_bridge_key,
    )

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT
        / "sessions"
        / "design_suite"
        / "compiled_ingest"
        / SPECTRUM_COMPILED_SUITE_ID
        / case_id
        / timestamp
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    campaign_log = output_dir / "compiled-ingest.log"
    heartbeat_path = output_dir / "heartbeats.json"
    client = ApiClient(resolved_api_url, resolved_api_key)

    selected_targets = ordered_spectrum_compiled_medium01_targets(manifest)
    requested_target_names = [item for item in list(target_names or []) if str(item).strip()]
    if requested_target_names:
        target_lookup = {
            str(item.get("target_name") or "").strip(): dict(item)
            for item in selected_targets
            if str(item.get("target_name") or "").strip()
        }
        unknown = [name for name in requested_target_names if name not in target_lookup]
        if unknown:
            raise ValueError(f"unknown_medium01_targets:{','.join(unknown)}")
        selected_targets = [target_lookup[name] for name in requested_target_names]
    run_records: list[dict[str, Any]] = []
    successful_job_by_target: dict[str, str] = {}
    chain_step_by_target = {
        str(step["target_name"]): dict(step) for step in SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN
    }
    explicit_cross_dll_prior_job_ids = [item for item in list(cross_dll_prior_job_ids or []) if str(item).strip()]
    for index, target in enumerate(selected_targets, start=1):
        dll_path = (REPO_ROOT / str(target.get("source_path") or "")).resolve()
        target_name = str(target.get("target_name") or Path(dll_path).stem).strip()
        chain_step = chain_step_by_target[target_name]
        predecessor_targets = list(chain_step.get("predecessor_targets") or [])
        resolved_prior_job_id = ""
        resolved_cross_dll_prior_job_ids: list[str] = []
        if requested_target_names and index == 1:
            if predecessor_targets and not explicit_cross_dll_prior_job_ids:
                raise ValueError(f"missing_predecessor_job_ids:{target_name}")
            resolved_cross_dll_prior_job_ids = list(explicit_cross_dll_prior_job_ids)
            resolved_prior_job_id = (
                str(prior_job_id or "").strip()
                or (resolved_cross_dll_prior_job_ids[-1] if resolved_cross_dll_prior_job_ids else "")
            )
        else:
            if predecessor_targets:
                resolved_prior_job_id = str(successful_job_by_target.get(predecessor_targets[-1]) or "").strip()
            resolved_cross_dll_prior_job_ids = [
                str(successful_job_by_target.get(name) or "").strip()
                for name in predecessor_targets
                if str(successful_job_by_target.get(name) or "").strip()
            ]
        run_dir = output_dir / "runs" / f"{index:02d}-{target_name}"
        missing_predecessors = [
            name for name in predecessor_targets if not str(successful_job_by_target.get(name) or "").strip()
        ]
        if product_route_required and predecessor_targets and missing_predecessors and not requested_target_names:
            record = _dependency_blocked_record(
                run_dir=run_dir,
                target_name=target_name,
                dll_path=dll_path,
                predecessor_targets=predecessor_targets,
                missing_predecessors=missing_predecessors,
                chain_step=chain_step,
                resolved_prior_job_id=resolved_prior_job_id,
                resolved_cross_dll_prior_job_ids=resolved_cross_dll_prior_job_ids,
            )
            product_route_authority = _product_route_authority_for_record(record)
            record["product_route_authority"] = product_route_authority
            write_json(run_dir / "product-route-authority.json", product_route_authority)
            record.update(_product_contract_fields_for_record(record))
            run_records.append(record)
            continue
        log_line(f"spectrum-compiled-start target={target_name} dll={dll_path.name}", campaign_log)
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
            "lane_id": f"spectrum-medium01-{index}",
            "binary_fixture_suite": SPECTRUM_COMPILED_SUITE_ID,
            "entry_surface": "upload",
            "prior_job_id": resolved_prior_job_id,
            "chain_step_target": target_name,
            "required_semantic_checkpoint": str(chain_step["required_semantic_checkpoint"]),
            "selected_invocable_names": [str(chain_step["required_semantic_checkpoint"])],
        }
        if product_route_required:
            explore_settings.update(
                {
                    "ghidra_required": True,
                    "route_authority_required": True,
                    "green_contract_level_requested": "product_green",
                    "product_route_required": True,
                }
            )
        if resolved_cross_dll_prior_job_ids:
            explore_settings["cross_dll_prior_job_ids"] = resolved_cross_dll_prior_job_ids
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
            poll_sec=poll_sec,
            analyze_timeout_sec=analyze_timeout_sec,
            explore_timeout_sec=explore_timeout_sec,
            stuck_seconds=stuck_seconds,
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
            "prior_job_id": resolved_prior_job_id,
            "cross_dll_prior_job_ids": resolved_cross_dll_prior_job_ids,
            "required_semantic_checkpoint": str(chain_step["required_semantic_checkpoint"]),
        }
        if product_route_required:
            product_route_authority = _product_route_authority_for_record(record)
            record["product_route_authority"] = product_route_authority
            write_json(run_dir / "product-route-authority.json", product_route_authority)
            record.update(_product_contract_fields_for_record(record))
        run_records.append(record)
        job_id = str(record.get("job_id") or "").strip()
        record_trusted = str(record.get("status") or "").strip().lower() == "ok"
        if product_route_required:
            record_trusted = record_trusted and bool(record.get("product_green_eligible"))
        if job_id and record_trusted:
            successful_job_by_target[target_name] = job_id
        elif stop_after_first_failure:
            break

    report = build_spectrum_compiled_medium01_report(
        output_dir=output_dir,
        package_manifest=load_spectrum_compiled_package_manifest(),
        compiled_truth_manifest=compiled_truth,
        authored_truth_manifest=authored_truth,
        authored_medium_manifest=authored_medium,
        run_records=run_records,
    )
    if case_id != SPECTRUM_COMPILED_MEDIUM01_CASE_ID:
        report["case_id"] = case_id
    green_contract = (
        _product_contract_summary(
            run_records,
            report,
            expected_target_count=len(SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN),
            failure_kind_for_record=_failure_kind_for_record,
        )
        if product_route_required
        else {
            "green_contract_level": "compatibility_green",
            "product_green_eligible": False,
            "route_authority_required": False,
            "ghidra_required": False,
            "route_authority_present": False,
            "safe_to_compare": bool(report.get("binary_ingest_proof_succeeded")),
            "semantic_proof_satisfied": bool(report.get("semantic_checkpoint_alignment_succeeded")),
            "authoritative_proving": bool(
                report.get("binary_ingest_proof_succeeded")
                and report.get("semantic_checkpoint_alignment_succeeded")
            ),
            "blocking_signal": "",
        }
    )
    report.update({key: value for key, value in green_contract.items() if key != "per_target_green_contract"})

    run_bundle = {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": case_id,
        "entry_surface": "upload",
        "product_route_required": product_route_required,
        **green_contract,
        "api_identity": api_msg,
        "bridge_identity": bridge_msg,
        "strict_local_preflight": strict_local_preflight,
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
    summary_path = output_dir / "compiled-ingest-summary.json"
    report_path = output_dir / "compiled-ingest-compare-report.json"
    write_json(summary_path, run_bundle)
    write_json(report_path, report)

    continuation_result = None
    if emit_semantic_continuation_packet and not product_route_required:
        continuation_result = emit_spectrum_medium01_semantic_continuation(
            output_dir=output_dir,
            summary_path=summary_path,
            report_path=report_path,
            summary=run_bundle,
            report=report,
        )
    run_bundle["semantic_continuation_emitted"] = bool(continuation_result)
    run_bundle["semantic_continuation_path"] = (
        str(continuation_result["packet_path"]) if continuation_result else ""
    )
    run_bundle["semantic_continuation_id"] = (
        str((continuation_result or {}).get("packet", {}).get("continuation_id") or "")
        if continuation_result
        else ""
    )
    if continuation_result:
        run_bundle["semantic_continuation_ledger_row_path"] = str(
            continuation_result["ledger_row_path"]
        )
        run_bundle["semantic_continuation_roadblock_path"] = str(
            continuation_result["roadblock_path"]
        )
    write_json(summary_path, run_bundle)
    checkpoint_packet = None
    if requested_target_names and len(run_records) == 1:
        checkpoint_packet = _write_checkpoint_artifacts(
            output_dir=output_dir,
            case_id=case_id,
            suite_id=SPECTRUM_COMPILED_SUITE_ID,
            chain_step=chain_step_by_target[str(run_records[0]["chain_context"]["target_name"])],
            run_record=run_records[0],
            api_identity=api_msg,
            bridge_identity=bridge_msg,
        )
    return {
        "output_dir": str(output_dir),
        "summary": run_bundle,
        "report": report,
        "semantic_continuation": continuation_result,
        "checkpoint_packet": checkpoint_packet,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run compiled Spectrum medium-01 through the upload lane.")
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--bridge-url", default="")
    parser.add_argument("--bridge-key", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--stop-after-first-failure", action="store_true")
    parser.add_argument("--target-names", default="")
    parser.add_argument("--prior-job-id", default="")
    parser.add_argument("--cross-dll-prior-job-ids", default="")
    args = parser.parse_args()
    output_root = Path(args.output_root) if str(args.output_root or "").strip() else None
    target_names = _parse_target_names(args.target_names)
    try:
        result = run_spectrum_compiled_medium01(
            api_url=str(args.api_url or "").strip(),
            api_key=str(args.api_key or "").strip(),
            bridge_url=str(args.bridge_url or "").strip(),
            bridge_key=str(args.bridge_key or "").strip(),
            output_root=output_root,
            stop_after_first_failure=bool(args.stop_after_first_failure),
            target_names=target_names,
            prior_job_id=str(args.prior_job_id or "").strip(),
            cross_dll_prior_job_ids=_parse_job_ids(args.cross_dll_prior_job_ids),
        )
    except Exception as exc:
        if output_root is not None and len(target_names) == 1:
            output_root.mkdir(parents=True, exist_ok=True)
            failure_packet = {
                "schema_version": "1.0.0",
                "suite_id": SPECTRUM_COMPILED_SUITE_ID,
                "case_id": SPECTRUM_COMPILED_MEDIUM01_CASE_ID,
                "target_name": target_names[0],
                "verdict": "fail",
                "job_id": "",
                "status": "error",
                "phase": "",
                "failure_kind": "runner_exception",
                "message": str(exc),
                "run_record": {},
            }
            write_json(output_root / "checkpoint-result.json", failure_packet)
            write_json(output_root / "run-record.json", {})
        raise
    print(
        json.dumps(
            {
                "output_dir": result["output_dir"],
                "compiled_binary_ingest_success": result["report"]["binary_ingest_proof_succeeded"],
                "semantic_checkpoint_alignment_succeeded": result["report"]["semantic_checkpoint_alignment_succeeded"],
                "checkpoint_verdict": (
                    result["checkpoint_packet"]["verdict"]
                    if result.get("checkpoint_packet")
                    else ""
                ),
            },
            indent=2,
        )
    )
    if result.get("checkpoint_packet"):
        return 1 if result["checkpoint_packet"]["verdict"] == "fail" else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
