from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.analysis.regression_gate_v1 import (  # noqa: E402
    aggregate_gate_verdict,
    build_medium01_checkpoint_report,
    compare_compiled_suite_to_baseline,
    load_gate_config,
)
from api.pipeline.core.spectrum_compiled_ingest import (  # noqa: E402
    SPECTRUM_COMPILED_EASY01_CHAIN_PLAN,
    SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN,
    SPECTRUM_COMPILED_SUITE_ID,
    build_spectrum_compiled_easy01_report,
    build_spectrum_compiled_medium01_report,
    load_spectrum_authored_easy_manifest,
    load_spectrum_authored_medium01_manifest,
    load_spectrum_authored_truth_manifest,
    load_spectrum_compiled_package_manifest,
    load_spectrum_compiled_truth_manifest,
    ordered_spectrum_compiled_easy01_targets,
    ordered_spectrum_compiled_medium01_targets,
)
from scripts.ops.nightly_groundtruth import write_json  # noqa: E402


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _suite_alias(case_id: str) -> str:
    return str(case_id or "").replace("-", "")


def _builder_bundle(case_id: str) -> tuple[
    tuple[dict[str, Any], ...],
    Callable[[dict[str, Any]], list[dict[str, Any]]],
    Callable[..., dict[str, Any]],
    Callable[[], dict[str, Any]],
]:
    if case_id == "easy-01":
        return (
            SPECTRUM_COMPILED_EASY01_CHAIN_PLAN,
            ordered_spectrum_compiled_easy01_targets,
            build_spectrum_compiled_easy01_report,
            load_spectrum_authored_easy_manifest,
        )
    if case_id == "medium-01":
        return (
            SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN,
            ordered_spectrum_compiled_medium01_targets,
            build_spectrum_compiled_medium01_report,
            load_spectrum_authored_medium01_manifest,
        )
    raise ValueError(f"unsupported_checkpoint_case:{case_id}")


def _load_checkpoint_packets(root: Path, case_id: str) -> dict[str, dict[str, Any]]:
    packets: dict[str, dict[str, Any]] = {}
    for packet_path in root.rglob("checkpoint-result.json"):
        packet = _read_json(packet_path)
        if str(packet.get("case_id") or "").strip() != case_id:
            continue
        target_name = str(packet.get("target_name") or "").strip()
        if not target_name:
            continue
        packet["_packet_dir"] = str(packet_path.parent)
        packets[target_name] = packet
    return packets


def _checkpoint_run_record(packet: dict[str, Any]) -> dict[str, Any]:
    packet_dir = Path(str(packet.get("_packet_dir") or "")).resolve()
    run_record = dict(packet.get("run_record") or {})
    if not run_record:
        record_path = packet_dir / "run-record.json"
        if record_path.exists():
            run_record = _read_json(record_path)
    if not run_record:
        return {}
    run_dir_relative = str(packet.get("run_dir_relative") or "").strip()
    if run_dir_relative:
        run_record["run_dir"] = str((packet_dir / run_dir_relative).resolve())
    else:
        run_dirs = [item for item in (packet_dir / "runs").glob("*") if item.is_dir()]
        if run_dirs:
            run_record["run_dir"] = str(run_dirs[0].resolve())
    return run_record


def _write_aggregate_log(
    suite_dir: Path,
    chain_plan: tuple[dict[str, Any], ...],
    packets_by_target: dict[str, dict[str, Any]],
) -> Path:
    lines: list[str] = []
    for step in chain_plan:
        target_name = str(step.get("target_name") or "").strip()
        packet = dict(packets_by_target.get(target_name) or {})
        if not packet:
            lines.append(f"[missing] {target_name}")
            continue
        lines.append(
            f"[{packet.get('verdict')}] {target_name} "
            f"phase={packet.get('phase') or ''} "
            f"failure_kind={packet.get('failure_kind') or ''} "
            f"message={packet.get('message') or ''}"
        )
    log_path = suite_dir / "compiled-ingest.log"
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


def aggregate_checkpoint_suite(
    *,
    config_path: Path,
    case_id: str,
    checkpoint_artifacts_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_gate_config(config_path, repo_root=REPO_ROOT)
    suite_cfg = next(
        dict(item)
        for item in list(config.get("suites") or [])
        if str(item.get("case_id") or "").strip() == case_id
    )
    chain_plan, ordered_targets_fn, builder, authored_manifest_loader = _builder_bundle(case_id)
    package_manifest = load_spectrum_compiled_package_manifest()
    selected_targets = ordered_targets_fn(package_manifest)
    packets_by_target = _load_checkpoint_packets(checkpoint_artifacts_root, case_id)

    run_records: list[dict[str, Any]] = []
    for step in chain_plan:
        target_name = str(step.get("target_name") or "").strip()
        packet = packets_by_target.get(target_name)
        if not packet:
            continue
        run_record = _checkpoint_run_record(packet)
        if run_record:
            run_records.append(run_record)

    suite_dir = output_root / _suite_alias(case_id)
    suite_dir.mkdir(parents=True, exist_ok=True)
    common_kwargs = {
        "output_dir": suite_dir,
        "package_manifest": package_manifest,
        "compiled_truth_manifest": load_spectrum_compiled_truth_manifest(),
        "authored_truth_manifest": load_spectrum_authored_truth_manifest(),
        "run_records": run_records,
    }
    if case_id == "easy-01":
        report = builder(
            **common_kwargs,
            authored_easy_manifest=authored_manifest_loader(),
        )
    else:
        report = builder(
            **common_kwargs,
            authored_medium_manifest=authored_manifest_loader(),
        )
    _write_aggregate_log(suite_dir, chain_plan, packets_by_target)

    compiled_targets = [
        {
            "staged_name": str(item.get("staged_name") or ""),
            "source_path": str(item.get("source_path") or ""),
            "target_name": str(item.get("target_name") or ""),
            "required_semantic_checkpoint": str(item.get("required_semantic_checkpoint") or ""),
        }
        for item in selected_targets
    ]
    first_packet = next(iter(packets_by_target.values()), {})
    summary = {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_COMPILED_SUITE_ID,
        "case_id": case_id,
        "entry_surface": "upload",
        "api_identity": str(first_packet.get("api_identity") or ""),
        "bridge_identity": str(first_packet.get("bridge_identity") or ""),
        "compiled_targets": compiled_targets,
        "run_records": run_records,
        "comparison_report": report,
        "checkpoint_packets": {
            target_name: {
                "verdict": str(packet.get("verdict") or ""),
                "phase": str(packet.get("phase") or ""),
                "failure_kind": str(packet.get("failure_kind") or ""),
                "message": str(packet.get("message") or ""),
            }
            for target_name, packet in packets_by_target.items()
        },
    }
    write_json(suite_dir / "compiled-ingest-summary.json", summary)
    write_json(suite_dir / "compiled-ingest-compare-report.json", report)

    baseline_access_path = output_root / "baseline-access.json"
    baseline_access = _read_json(baseline_access_path) if baseline_access_path.exists() else {}
    baseline_available = str(baseline_access.get("verdict") or "pass") == "pass"
    if baseline_available:
        comparison = compare_compiled_suite_to_baseline(
            case_id=case_id,
            baseline_output_root=Path(str(suite_cfg["baseline_output_root"])),
            candidate_output_root=suite_dir,
            accepted_additive_invocables=bool(suite_cfg.get("accepted_additive_invocables")),
        )
    else:
        comparison = {
            "surface": case_id,
            "baseline_output_root": str(Path(str(suite_cfg["baseline_output_root"]))),
            "candidate_output_root": str(suite_dir),
            "baseline_access": baseline_access,
            "accepted_differences": [],
            "reasons": ["baseline_unavailable_in_summary_job"],
            "verdict": "fail",
        }
    result = {
        "surface": case_id,
        "baseline_output_root": str(Path(str(suite_cfg["baseline_output_root"]))),
        "candidate_output_root": str(suite_dir),
        "runner_result": {
            "checkpoint_artifacts_root": str(checkpoint_artifacts_root),
            "checkpoint_targets": [str(step.get("target_name") or "") for step in chain_plan],
            "executed_checkpoint_targets": [record.get("chain_context", {}).get("target_name", "") for record in run_records],
        },
        "comparison": comparison,
        "verdict": comparison["verdict"],
        "reasons": list(comparison.get("reasons") or []),
        "accepted_differences": list(comparison.get("accepted_differences") or []),
    }
    result_path = output_root / f"{_suite_alias(case_id)}-result.json"
    write_json(result_path, result)

    surface_results = [result]
    overall_verdict = aggregate_gate_verdict(surface_results)
    summary_payload = {
        "version": "1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "gate_id": str(config.get("gate_id") or ""),
        "config_path": str(config_path),
        "output_root": str(output_root),
        "baseline_policy": "pinned_roots",
        "baseline_registry_path": str(config.get("baseline_registry_path") or ""),
        "requested_surfaces": [case_id],
        "active_surfaces": [case_id],
        "executed_surfaces": [case_id],
        "surface_results": surface_results,
        "overall_verdict": overall_verdict,
    }
    verdict_payload = {
        "gate_id": str(config.get("gate_id") or ""),
        "output_root": str(output_root),
        "overall_verdict": overall_verdict,
        "surface_verdicts": {case_id: str(result.get("verdict") or "")},
        "requested_surfaces": [case_id],
        "active_surfaces": [case_id],
        "executed_surfaces": [case_id],
        "baseline_roots": {case_id: str(suite_cfg["baseline_output_root"])},
        "baseline_registry_entries": {case_id: dict(suite_cfg.get("baseline_registry_entry") or {})},
        "candidate_roots": {case_id: str(suite_dir)},
    }
    write_json(output_root / "gate-summary.json", summary_payload)
    write_json(output_root / "gate-verdict.json", verdict_payload)

    if case_id == "medium-01":
        checkpoint_report = build_medium01_checkpoint_report(suite_dir)
        write_json(output_root / "medium01-checkpoints.json", checkpoint_report)

    return result, verdict_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate checkpoint artifacts into suite-level regression artifacts.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--checkpoint-artifacts-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()

    result, verdict = aggregate_checkpoint_suite(
        config_path=args.config,
        case_id=str(args.case_id or "").strip(),
        checkpoint_artifacts_root=args.checkpoint_artifacts_root,
        output_root=args.output_root,
    )
    print(
        json.dumps(
            {
                "surface": result["surface"],
                "verdict": result["verdict"],
                "output_root": verdict["output_root"],
            },
            indent=2,
        )
    )
    return 1 if str(result.get("verdict") or "").strip() == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
