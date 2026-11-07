from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.pipeline.core.spectrum_compiled_ingest import (
    SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return {}
    return _read_json(path)


def _check_required_fields(
    payload: dict[str, Any],
    *,
    required_fields: dict[str, Any],
    prefix: str,
) -> list[str]:
    reasons: list[str] = []
    for field_name, expected_value in required_fields.items():
        observed = payload.get(field_name)
        if observed != expected_value:
            reasons.append(
                f"{prefix}_field_mismatch:{field_name}:expected={expected_value!r}:observed={observed!r}"
            )
    return reasons


def _resolve_repo_path(repo_root: Path, raw: str | None) -> Path:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("path_value_missing")
    path = Path(value)
    return path if path.is_absolute() else (repo_root / path)


def _load_baseline_registry(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if str(payload.get("version") or "").strip() != "1.0":
        raise ValueError("unsupported_baseline_registry_version")
    surfaces = list(payload.get("surfaces") or [])
    if not surfaces:
        raise ValueError("baseline_registry_surfaces_missing")
    return payload


def load_gate_config(config_path: str | Path, *, repo_root: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    root = Path(repo_root)
    payload = _read_json(path)
    if str(payload.get("version") or "").strip() != "1.0":
        raise ValueError("unsupported_gate_config_version")
    if str(payload.get("gate_id") or "").strip() == "":
        raise ValueError("gate_id_missing")

    lane = dict(payload.get("lane_trust") or {})
    suites = list(payload.get("suites") or [])
    if not lane:
        raise ValueError("lane_trust_config_missing")
    if len(suites) < 2:
        raise ValueError("suite_configs_missing")

    registry_path_value = str(payload.get("baseline_registry_path") or "").strip()
    registry_by_surface_id: dict[str, dict[str, Any]] = {}
    if registry_path_value:
        registry_path = _resolve_repo_path(root, registry_path_value)
        registry = _load_baseline_registry(registry_path)
        payload["baseline_registry_path"] = str(registry_path)
        for row in list(registry.get("surfaces") or []):
            item = dict(row or {})
            surface_id = str(item.get("surface_id") or "").strip()
            if not surface_id:
                continue
            pinned_root = item.get("pinned_root")
            if pinned_root:
                item["pinned_root"] = str(_resolve_repo_path(root, str(pinned_root)))
            contract_sources = list(item.get("contract_sources") or [])
            if contract_sources:
                item["contract_sources"] = [
                    str(_resolve_repo_path(root, entry))
                    for entry in contract_sources
                ]
            registry_by_surface_id[surface_id] = item
        payload["baseline_registry"] = {
            "path": str(registry_path),
            "surfaces": list(registry_by_surface_id.values()),
        }

    lane["validator_script_path"] = str(
        _resolve_repo_path(root, lane.get("validator_script_path"))
    )
    lane["contract_sources"] = [
        str(_resolve_repo_path(root, item))
        for item in list(lane.get("contract_sources") or [])
    ]

    normalized_suites: list[dict[str, Any]] = []
    for suite in suites:
        row = dict(suite or {})
        if str(row.get("case_id") or "").strip() == "":
            raise ValueError("suite_case_id_missing")
        surface_id = str(row.get("baseline_registry_surface_id") or "").strip()
        if surface_id:
            registry_row = dict(registry_by_surface_id.get(surface_id) or {})
            if not registry_row:
                raise ValueError(f"baseline_registry_surface_missing:{surface_id}")
            if not bool(registry_row.get("active")):
                raise ValueError(f"baseline_registry_surface_inactive:{surface_id}")
            pinned_root = str(registry_row.get("pinned_root") or "").strip()
            if not pinned_root:
                raise ValueError(f"baseline_registry_surface_unpinned:{surface_id}")
            row["baseline_output_root"] = pinned_root
            row["baseline_registry_entry"] = registry_row
        else:
            row["baseline_output_root"] = str(
                _resolve_repo_path(root, row.get("baseline_output_root"))
            )
        normalized_suites.append(row)

    payload["lane_trust"] = lane
    payload["suites"] = normalized_suites
    return payload


def evaluate_lane_trust_output(
    output_root: str | Path,
    *,
    required_packets: list[str],
    pass_verdict: str,
) -> dict[str, Any]:
    root = Path(output_root)
    missing_packets = [packet for packet in required_packets if not (root / packet).exists()]
    packet_path = root / "lane-trust-packet.json"
    failure_packet = _read_json_if_exists(root / "lane-validator-failure.json")
    if missing_packets or not packet_path.exists():
        missing_with_packet = list(missing_packets)
        if not packet_path.exists() and "lane-trust-packet.json" not in missing_with_packet:
            missing_with_packet.append("lane-trust-packet.json")
        reasons = ["missing_required_lane_packets"]
        failure_kind = str((failure_packet or {}).get("failure_kind") or "").strip()
        failure_details = dict((failure_packet or {}).get("details") or {})
        if failure_kind:
            reasons.insert(0, failure_kind)
        return {
            "surface": "lane_trust",
            "candidate_output_root": str(root),
            "required_packets": required_packets,
            "missing_packets": missing_with_packet,
            "packet_completeness": "incomplete",
            "verdict": "fail",
            "reasons": reasons,
            "validator_failure": failure_packet if isinstance(failure_packet, dict) and failure_packet else {},
            "freshness_mode": str(failure_details.get("freshness_mode") or "").strip(),
            "restart_suppressed": bool(failure_details.get("restart_suppressed")),
        }

    packet = _read_json(packet_path)
    observed = str(packet.get("canary_verdict") or "").strip()
    reasons: list[str] = []
    if observed != str(pass_verdict or "").strip():
        reasons.append(f"unexpected_canary_verdict:{observed}")
    failure_kind = str((failure_packet or {}).get("failure_kind") or "").strip()
    if failure_kind and failure_kind not in reasons:
        reasons.insert(0, failure_kind)
    return {
        "surface": "lane_trust",
        "candidate_output_root": str(root),
        "lane_trust_packet_path": str(packet_path),
        "required_packets": required_packets,
        "missing_packets": [],
        "packet_completeness": "complete",
        "expected_canary_verdict": str(pass_verdict or "").strip(),
        "observed_canary_verdict": observed,
        "freshness_mode": str(packet.get("freshness_mode") or "").strip(),
        "restart_suppressed": bool(
            (packet.get("api_freshness") or {}).get("restart_suppressed")
            or (packet.get("bridge_freshness") or {}).get("restart_suppressed")
        ),
        "verdict": "pass" if not reasons else "fail",
        "reasons": reasons,
        "validator_failure": failure_packet if isinstance(failure_packet, dict) and failure_packet else {},
        "packet": packet,
    }


def evaluate_compiled_suite_artifacts(
    case_id: str,
    output_root: str | Path,
    *,
    summary_case_id: str | None = None,
    report_case_id: str | None = None,
    required_summary_fields: dict[str, Any] | None = None,
    required_report_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(output_root)
    required_files = [
        "compiled-ingest-summary.json",
        "compiled-ingest-compare-report.json",
        "compiled-ingest.log",
    ]
    missing_files = [name for name in required_files if not (root / name).exists()]
    result: dict[str, Any] = {
        "case_id": str(case_id or "").strip(),
        "candidate_output_root": str(root),
        "required_files": required_files,
        "missing_files": missing_files,
        "reasons": [],
    }
    if missing_files:
        result["reasons"].append("missing_required_suite_files")
        result["verdict"] = "fail"
        return result

    summary = _read_json(root / "compiled-ingest-summary.json")
    report = _read_json(root / "compiled-ingest-compare-report.json")
    expected_summary_case_id = str(summary_case_id or case_id or "").strip()
    expected_report_case_id = str(report_case_id or case_id or "").strip()
    if str(summary.get("case_id") or "").strip() != expected_summary_case_id:
        result["reasons"].append("summary_case_id_mismatch")
    if str(report.get("case_id") or "").strip() != expected_report_case_id:
        result["reasons"].append("report_case_id_mismatch")
    result["expected_summary_case_id"] = expected_summary_case_id
    result["expected_report_case_id"] = expected_report_case_id
    result["required_summary_fields"] = dict(required_summary_fields or {})
    result["required_report_fields"] = dict(required_report_fields or {})

    run_records = list(summary.get("run_records") or [])
    if not run_records:
        result["reasons"].append("run_records_missing")
    non_ok = [
        str(item.get("target") or item.get("run_id") or "")
        for item in run_records
        if str(item.get("status") or "").strip().lower() != "ok"
    ]
    if non_ok:
        result["reasons"].append(f"non_ok_run_records:{','.join(non_ok)}")

    per_run = list(report.get("per_run") or [])
    if not per_run:
        result["reasons"].append("report_per_run_missing")
    missing_sessions = [
        str(item.get("dll_name") or "")
        for item in per_run
        if not bool(item.get("session_artifacts_present"))
    ]
    if missing_sessions:
        result["reasons"].append(f"session_artifacts_missing:{','.join(missing_sessions)}")

    if required_summary_fields:
        result["reasons"].extend(
            _check_required_fields(
                summary,
                required_fields=dict(required_summary_fields),
                prefix="summary",
            )
        )
    if required_report_fields:
        result["reasons"].extend(
            _check_required_fields(
                report,
                required_fields=dict(required_report_fields),
                prefix="report",
            )
        )

    result["summary"] = summary
    result["report"] = report
    result["summary_path"] = str(root / "compiled-ingest-summary.json")
    result["report_path"] = str(root / "compiled-ingest-compare-report.json")
    result["verdict"] = "pass" if not result["reasons"] else "fail"
    return result


def _medium01_failure_kind(
    run_record: dict[str, Any],
    report_row: dict[str, Any],
) -> str:
    terminalization = dict(run_record.get("job_terminalization") or {})
    terminal_kind = str(
        terminalization.get("terminalization_kind") or terminalization.get("kind") or ""
    ).strip()
    phase = str(run_record.get("phase") or report_row.get("run_phase") or "").strip().lower()

    if terminal_kind == "timeout":
        if phase.startswith("analy"):
            return "analyze_timeout"
        if phase.startswith("explor"):
            return "explore_timeout"
        return "timeout"
    if terminal_kind and terminal_kind != "done":
        return f"runner_{terminal_kind}"
    if not bool(report_row.get("export_contract_match", True)):
        return "artifact_regression"
    if not bool(report_row.get("semantic_checkpoint_match", True)):
        return "semantic_regression"
    if not bool(report_row.get("session_artifacts_present", True)):
        return "session_artifacts_missing"
    if str(run_record.get("failure_domain") or "").strip():
        return str(run_record.get("failure_domain") or "").strip()
    if str(run_record.get("error") or "").strip():
        return "runner_error"
    return "unknown_failure"


def _medium01_failure_message(
    run_record: dict[str, Any],
    report_row: dict[str, Any],
) -> str:
    terminalization = dict(run_record.get("job_terminalization") or {})
    reason = dict(terminalization.get("reason") or {})
    if str(reason.get("message") or "").strip():
        return str(reason.get("message") or "").strip()
    if str(run_record.get("error") or "").strip():
        return str(run_record.get("error") or "").strip()
    blocking = list((run_record.get("run_authority") or {}).get("blocking_reasons") or [])
    if blocking:
        return ", ".join(str(item) for item in blocking if str(item).strip())
    if not bool(report_row.get("export_contract_match", True)):
        return "Expected export contract did not hold for this checkpoint."
    if not bool(report_row.get("semantic_checkpoint_match", True)):
        return "Required semantic checkpoint did not complete successfully."
    if not bool(report_row.get("session_artifacts_present", True)):
        return "Session artifacts were not captured for this checkpoint."
    return ""


def build_medium01_checkpoint_report(output_root: str | Path) -> dict[str, Any]:
    root = Path(output_root)
    summary = _read_json_if_exists(root / "compiled-ingest-summary.json")
    report = _read_json_if_exists(root / "compiled-ingest-compare-report.json")
    run_records = list(summary.get("run_records") or [])
    report_rows = list(report.get("per_run") or [])

    target_by_dll_name = {
        str(step.get("staged_name") or "").strip(): str(step.get("target_name") or "").strip()
        for step in SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN
    }
    run_record_by_target = {
        str(item.get("target") or "").strip(): dict(item)
        for item in run_records
        if str(item.get("target") or "").strip()
    }
    report_row_by_target = {
        target_by_dll_name.get(str(item.get("dll_name") or "").strip(), ""): dict(item)
        for item in report_rows
        if target_by_dll_name.get(str(item.get("dll_name") or "").strip(), "")
    }

    checkpoints: list[dict[str, Any]] = []
    first_failed_checkpoint = ""
    checkpoint_counts = {"pass": 0, "fail": 0, "skipped": 0}

    for step in SPECTRUM_COMPILED_MEDIUM01_CHAIN_PLAN:
        target_name = str(step.get("target_name") or "").strip()
        required_semantic_checkpoint = str(step.get("required_semantic_checkpoint") or "").strip()
        predecessor_targets = list(step.get("predecessor_targets") or [])
        run_record = run_record_by_target.get(target_name, {})
        report_row = report_row_by_target.get(target_name, {})
        skipped = False

        if not run_record and first_failed_checkpoint:
            verdict = "skipped"
            skipped = True
            failure_kind = "skipped_due_to_prior_failure"
            message = f"Skipped because earlier checkpoint {first_failed_checkpoint} failed."
            phase = ""
            job_id = ""
            duration_sec = None
        elif not run_record:
            verdict = "fail"
            failure_kind = "missing_checkpoint_run"
            message = "No run record was produced for this checkpoint."
            phase = ""
            job_id = ""
            duration_sec = None
        else:
            job_id = str(run_record.get("job_id") or report_row.get("job_id") or "").strip()
            phase = str(run_record.get("phase") or report_row.get("run_phase") or "").strip()
            duration_sec = run_record.get("duration_sec")
            run_status = str(run_record.get("status") or "").strip().lower()
            if (
                run_status == "ok"
                and bool(report_row.get("export_contract_match", True))
                and bool(report_row.get("semantic_checkpoint_match", True))
                and bool(report_row.get("session_artifacts_present", True))
            ):
                verdict = "pass"
                failure_kind = ""
                message = ""
            else:
                verdict = "fail"
                failure_kind = _medium01_failure_kind(run_record, report_row)
                message = _medium01_failure_message(run_record, report_row)

        checkpoint_counts[verdict] = checkpoint_counts.get(verdict, 0) + 1
        if verdict == "fail" and not first_failed_checkpoint:
            first_failed_checkpoint = target_name

        checkpoints.append(
            {
                "target_name": target_name,
                "required_semantic_checkpoint": required_semantic_checkpoint,
                "predecessor_targets": predecessor_targets,
                "verdict": verdict,
                "phase": phase,
                "job_id": job_id,
                "duration_sec": duration_sec,
                "failure_kind": failure_kind,
                "message": message,
                "skipped": skipped,
            }
        )

    return {
        "case_id": "medium-01",
        "candidate_output_root": str(root),
        "overall_verdict": "fail" if checkpoint_counts.get("fail", 0) else "pass",
        "first_failed_checkpoint": first_failed_checkpoint,
        "passed_checkpoint_count": checkpoint_counts.get("pass", 0),
        "total_checkpoint_count": len(checkpoints),
        "checkpoint_verdict_summary": checkpoint_counts,
        "checkpoints": checkpoints,
    }


def compare_compiled_suite_to_baseline(
    *,
    case_id: str,
    baseline_output_root: str | Path,
    candidate_output_root: str | Path,
    accepted_additive_invocables: bool = False,
    summary_case_id: str | None = None,
    report_case_id: str | None = None,
    required_summary_fields: dict[str, Any] | None = None,
    required_report_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline_eval = evaluate_compiled_suite_artifacts(
        case_id,
        baseline_output_root,
        summary_case_id=summary_case_id,
        report_case_id=report_case_id,
        required_summary_fields=required_summary_fields,
        required_report_fields=required_report_fields,
    )
    candidate_eval = evaluate_compiled_suite_artifacts(
        case_id,
        candidate_output_root,
        summary_case_id=summary_case_id,
        report_case_id=report_case_id,
        required_summary_fields=required_summary_fields,
        required_report_fields=required_report_fields,
    )
    failures: list[str] = []
    accepted_differences: list[str] = []

    if baseline_eval["verdict"] != "pass":
        failures.append("baseline_artifacts_invalid")
    if candidate_eval["verdict"] != "pass":
        failures.append("candidate_artifacts_invalid")

    if failures:
        return {
            "surface": str(case_id or "").strip(),
            "baseline_output_root": str(Path(baseline_output_root)),
            "candidate_output_root": str(Path(candidate_output_root)),
            "baseline_artifact_result": baseline_eval,
            "candidate_artifact_result": candidate_eval,
            "accepted_differences": accepted_differences,
            "reasons": failures,
            "verdict": "fail",
        }

    baseline_report = dict(baseline_eval["report"] or {})
    candidate_report = dict(candidate_eval["report"] or {})

    for key in ("expected_execution_flow", "expected_symbol_flow", "compiled_targets"):
        if list(baseline_report.get(key) or []) != list(candidate_report.get(key) or []):
            failures.append(f"{key}_mismatch")

    if bool(baseline_report.get("binary_ingest_proof_succeeded")) and not bool(
        candidate_report.get("binary_ingest_proof_succeeded")
    ):
        failures.append("binary_ingest_proof_regressed")
    if bool(baseline_report.get("semantic_checkpoint_alignment_succeeded")) and not bool(
        candidate_report.get("semantic_checkpoint_alignment_succeeded")
    ):
        failures.append("semantic_checkpoint_alignment_regressed")

    baseline_runs = {
        str(item.get("dll_name") or ""): dict(item)
        for item in list(baseline_report.get("per_run") or [])
        if str(item.get("dll_name") or "")
    }
    candidate_runs = {
        str(item.get("dll_name") or ""): dict(item)
        for item in list(candidate_report.get("per_run") or [])
        if str(item.get("dll_name") or "")
    }

    for dll_name, baseline_row in baseline_runs.items():
        candidate_row = candidate_runs.get(dll_name)
        if not candidate_row:
            failures.append(f"missing_candidate_row:{dll_name}")
            continue
        if bool(baseline_row.get("export_contract_match")) and not bool(candidate_row.get("export_contract_match")):
            failures.append(f"export_contract_regressed:{dll_name}")
        if bool(baseline_row.get("semantic_checkpoint_match")) and not bool(
            candidate_row.get("semantic_checkpoint_match")
        ):
            failures.append(f"semantic_checkpoint_match_regressed:{dll_name}")
        if bool(baseline_row.get("session_artifacts_present")) and not bool(
            candidate_row.get("session_artifacts_present")
        ):
            failures.append(f"session_artifacts_regressed:{dll_name}")
        if list(baseline_row.get("expected_exports") or []) != list(candidate_row.get("expected_exports") or []):
            failures.append(f"expected_exports_mismatch:{dll_name}")

        baseline_statuses = dict(baseline_row.get("semantic_checkpoint_statuses") or {})
        candidate_statuses = dict(candidate_row.get("semantic_checkpoint_statuses") or {})
        for checkpoint, status in baseline_statuses.items():
            if not str(status or "").strip():
                continue
            if str(candidate_statuses.get(checkpoint) or "").strip() != str(status).strip():
                failures.append(f"semantic_checkpoint_status_regressed:{dll_name}:{checkpoint}")

        extra_invocables = sorted(
            set(candidate_row.get("discovered_invocables") or [])
            - set(baseline_row.get("discovered_invocables") or [])
        )
        if extra_invocables and accepted_additive_invocables:
            accepted_differences.append(f"{dll_name}:additional_discovered_invocables={extra_invocables}")

    verdict = "fail"
    if not failures:
        verdict = "pass_with_accepted_difference" if accepted_differences else "pass"

    return {
        "surface": str(case_id or "").strip(),
        "baseline_output_root": str(Path(baseline_output_root)),
        "candidate_output_root": str(Path(candidate_output_root)),
        "baseline_artifact_result": baseline_eval,
        "candidate_artifact_result": candidate_eval,
        "accepted_differences": accepted_differences,
        "reasons": failures,
        "verdict": verdict,
    }


def aggregate_gate_verdict(results: list[dict[str, Any]]) -> str:
    verdicts = [str(item.get("verdict") or "").strip() for item in results]
    if any(verdict == "fail" for verdict in verdicts):
        return "fail"
    if any(verdict == "pass_with_accepted_difference" for verdict in verdicts):
        return "pass_with_accepted_difference"
    return "pass"
