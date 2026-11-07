from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return _read_json(path)


def _target_dir(proof_root: Path, target: str) -> Path | None:
    runs_root = proof_root / "runs"
    if not runs_root.exists():
        return None
    for candidate in sorted(runs_root.iterdir()):
        if candidate.is_dir() and candidate.name.endswith(f"-{target}"):
            return candidate
    direct = runs_root / target
    return direct if direct.exists() and direct.is_dir() else None


def _first_non_comparable_target(survivability: dict[str, Any]) -> dict[str, Any]:
    for row in list(survivability.get("targets") or []):
        if not bool(row.get("safe_to_compare")) or str(row.get("state") or "") == "non_comparable":
            return {
                "target": str(row.get("target") or ""),
                "state": str(row.get("state") or ""),
                "reason_code": str(row.get("reason_code") or ""),
                "phase": str(row.get("phase") or ""),
                "job_id": str(row.get("job_id") or ""),
            }
    return {}


def _final_finding(findings: Any) -> dict[str, Any]:
    rows = findings if isinstance(findings, list) else []
    if not rows:
        return {}
    row = rows[-1] if isinstance(rows[-1], dict) else {}
    return {
        "function": str(row.get("function") or ""),
        "status": str(row.get("status") or ""),
        "status_canonical": str(row.get("status_canonical") or ""),
        "working_call_present": bool(row.get("working_call")),
    }


def _finding_blocker(final_finding: dict[str, Any]) -> str:
    status = str(final_finding.get("status_canonical") or final_finding.get("status") or "")
    if not status or status in {"success", "verified_success"}:
        return ""
    return status


def _analyzer_runtime_summary(target_dir: Path | None) -> dict[str, Any]:
    if not target_dir:
        return {}
    runtime = _read_json_if_exists(target_dir / "analyzer-runtime-authority.json") or {}
    measurement = _read_json_if_exists(target_dir / "measurement-terminalization.json") or {}
    run_result = _read_json_if_exists(target_dir / "run_result.json") or {}
    job_status = _read_json_if_exists(target_dir / "job-status-analyze.json") or {}
    if not runtime:
        runtime = (
            ((run_result.get("status_payload") or {}).get("analyzer_runtime_authority") or {})
            or ((job_status or {}).get("analyzer_runtime_authority") or {})
            or {}
        )
    if not runtime and not measurement:
        return {}
    phase_history = runtime.get("phase_history") or []
    child_diagnostic = runtime.get("child_runtime_diagnostic") or {}
    if not child_diagnostic:
        status_payload = measurement.get("status_payload") or {}
        analyzer_runtime = status_payload.get("analyzer_runtime_authority") or {}
        child_diagnostic = analyzer_runtime.get("child_runtime_diagnostic") or {}
    phases = [str(row.get("phase") or "") for row in phase_history if isinstance(row, dict)]
    child_phase_history = child_diagnostic.get("phase_history") or []
    child_phases = [str(row.get("phase") or "") for row in child_phase_history if isinstance(row, dict)]
    reason_code = str(runtime.get("reason_code") or "")
    parent_signal = str(measurement.get("reason_code") or "")
    return {
        "status": str(runtime.get("status") or ""),
        "parent_signal": parent_signal,
        "sharpened_signal": reason_code if reason_code and reason_code != parent_signal else "",
        "reason_code": reason_code,
        "runtime_phase": str(runtime.get("runtime_phase") or runtime.get("phase") or ""),
        "parent_wait_started": "discovery_child_wait_start" in phases,
        "parent_wait_returned": "discovery_child_wait_returned" in phases,
        "child_runtime_phase": str(runtime.get("child_runtime_phase") or child_diagnostic.get("phase") or ""),
        "child_bootstrap_returned": "bootstrap_main_returned" in child_phases
        or str(child_diagnostic.get("phase") or "") == "bootstrap_main_returned",
        "child_returncode": (child_diagnostic.get("last_observation") or {}).get("returncode"),
        "bridge_attempted": bool(runtime.get("bridge_attempted")),
    }


def _discovery_output_summary(target_dir: Path | None) -> dict[str, Any]:
    if not target_dir:
        return {}
    authority = _read_json_if_exists(target_dir / "discovery-output-authority.json") or {}
    if not isinstance(authority, dict) or not authority:
        run_result = _read_json_if_exists(target_dir / "run_result.json") or {}
        status_payload = run_result.get("status_payload") or {}
        authority = status_payload.get("discovery_output_authority") or {}
    if not isinstance(authority, dict) or not authority:
        return {}
    diagnostics = authority.get("subprocess_interrupt_diagnostics") or {}
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    branch_steering_authority = bool(
        str(authority.get("reason_code") or "") == "child_python_startup_interrupt"
        and str(diagnostics.get("subreason_code") or "") == "child_python_startup_interrupt"
        and str(diagnostics.get("source_reason_code") or "") == "child_bootstrap_entry_missing"
        and str(diagnostics.get("classification_precision") or "") == "precise"
        and authority.get("subprocess_returncode") == 3221225786
        and bool(authority.get("subprocess_keyboard_interrupt"))
        and int(authority.get("discovery_file_count") or 0) == 0
        and int(authority.get("invocable_count") or 0) == 0
        and not bool(authority.get("ghidra_entered"))
    )
    return {
        "status": str(authority.get("status") or ""),
        "reason_code": str(authority.get("reason_code") or ""),
        "owner": str(authority.get("owner") or ""),
        "safe_to_compare": bool(authority.get("safe_to_compare")),
        "route_policy": str(authority.get("route_policy") or ""),
        "ghidra_entered": bool(authority.get("ghidra_entered")),
        "bridge_attempted": bool(authority.get("bridge_attempted")),
        "subprocess_returncode": authority.get("subprocess_returncode"),
        "subreason_code": str(diagnostics.get("subreason_code") or ""),
        "source_reason_code": str(diagnostics.get("source_reason_code") or ""),
        "classification_precision": str(diagnostics.get("classification_precision") or ""),
        "branch_steering_authority": branch_steering_authority,
        "authority_scope": (
            "blocker_repair_routing_only_not_product_proof"
            if branch_steering_authority
            else "diagnostic_only"
        ),
        "diagnostic_only": not branch_steering_authority,
    }


def summarize_product_proof_artifacts(*, proof_root: Path, target: str, output: Path | None = None) -> dict[str, Any]:
    proof_root = proof_root.resolve()
    target = str(target or "").strip()
    if not proof_root.exists() or not proof_root.is_dir():
        summary = {
            "schema_version": "1.0.0",
            "diagnostic_only": True,
            "product_green_claimed": False,
            "safe_to_compare": False,
            "blocking_signal": "proof_root_missing",
            "proof_root": str(proof_root),
            "target": target,
            "next_action": "provide an existing proof root before summarizing artifacts",
        }
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        return summary

    target_dir = _target_dir(proof_root, target)
    compiled_summary = _read_json_if_exists(proof_root / "compiled-ingest-summary.json") or {}
    compare_report = _read_json_if_exists(proof_root / "compiled-ingest-compare-report.json") or {}
    survivability = _read_json_if_exists(proof_root / "enterprise-survivability-summary.json") or {}
    run_authority = _read_json_if_exists(target_dir / "run-authority.json") if target_dir else {}
    run_result = _read_json_if_exists(target_dir / "run_result.json") if target_dir else {}
    findings = _read_json_if_exists(target_dir / "findings.json") if target_dir else []
    analyzer_runtime = _analyzer_runtime_summary(target_dir)
    discovery_output = _discovery_output_summary(target_dir)

    first_blocker = _first_non_comparable_target(survivability)
    target_counts = dict(survivability.get("target_counts") or {})
    final_finding = _final_finding(findings)
    target_status = {
        "target_dir": str(target_dir) if target_dir else "",
        "target_dir_present": bool(target_dir),
        "phase": str((run_result or {}).get("phase") or ""),
        "status": str((run_result or {}).get("status") or ""),
        "authority_level": str((run_authority or {}).get("authority_level") or ""),
        "authoritative_proving": bool((run_authority or {}).get("authoritative_proving")),
    }
    blocking_signal = str(
        (compiled_summary or {}).get("blocking_signal")
        or (compare_report or {}).get("blocking_signal")
        or first_blocker.get("reason_code")
        or _finding_blocker(final_finding)
        or ""
    )
    summary = {
        "schema_version": "1.0.0",
        "diagnostic_only": True,
        "product_green_claimed": False,
        "proof_root": str(proof_root),
        "target": target,
        "case_id": str(compiled_summary.get("case_id") or compare_report.get("case_id") or survivability.get("case_id") or ""),
        "claim_ceiling": str(survivability.get("claim_ceiling") or compare_report.get("claim_ceiling") or ""),
        "compiled": {
            "binary_ingest_proof_succeeded": bool(compare_report.get("binary_ingest_proof_succeeded")),
            "semantic_checkpoint_alignment_succeeded": bool(
                compare_report.get("semantic_checkpoint_alignment_succeeded")
            ),
            "comparison_note": str(compare_report.get("comparison_note") or ""),
        },
        "target_counts": target_counts,
        "first_blocker": first_blocker,
        "target_status": target_status,
        "final_function_status": final_finding,
        "analyzer_runtime": analyzer_runtime,
        "discovery_output": discovery_output,
        "sharpened_blocking_signal": str(analyzer_runtime.get("sharpened_signal") or ""),
        "diagnostic_subreason_signal": str(discovery_output.get("subreason_code") or ""),
        "blocking_signal": blocking_signal,
        "safe_to_compare": not bool(blocking_signal) and bool(survivability.get("safe_to_compare")),
        "next_action": (
            f"route {analyzer_runtime.get('sharpened_signal')} as the lower-level analyzer-runtime blocker before full rerun"
            if analyzer_runtime.get("sharpened_signal")
            else "inspect the target-local blocker and prefer checkpoint/target replay before full rerun"
            if blocking_signal
            else "no blocker summarized; use authoritative proof only if claim ceiling requires it"
        ),
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize product proof artifacts without claiming product green.")
    parser.add_argument("--proof-root", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    summary = summarize_product_proof_artifacts(proof_root=args.proof_root, target=args.target, output=args.output)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("blocking_signal") != "proof_root_missing" else 1


if __name__ == "__main__":
    raise SystemExit(main())
