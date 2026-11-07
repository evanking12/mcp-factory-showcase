from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness_lib.validation_report import emit_validation_report
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.handoff_contract import (  # noqa: E402
    AUDITOR_VERSION,
    CONTRACT_VERSION,
    FORWARD_GAP_KPI_ARTIFACTS,
    REQUIRED_CONTRACT_FILES,
    SCHEMA_HANDOFF_SNAPSHOTS,
    STAGE_CONTRACTS,
    TRANSITION_CONTRACT_BY_ID,
    TRANSITION_ORDER,
    stage_skip_reason_is_allowed,
    strict_required_context_evidence,
    strict_required_stage_evidence,
)
from api.pipeline.core.compatibility import is_capture_compatible  # noqa: E402
from api.pipeline.core.finding_status import (  # noqa: E402
    DISCOVERED_STATUSES as _DISCOVERED_STATUSES,
    STATUS_ORDER as _STATUS_ORDER,
    normalize_status,
)


SUPPORTED_VERSION = {"1.0"}
STRICT_REQUIRED_STAGE_EVIDENCE = strict_required_stage_evidence()
STRICT_REQUIRED_CONTEXT_EVIDENCE = strict_required_context_evidence()
STRICT_EVIDENCE_ALIASES: dict[str, tuple[str, ...]] = {}
for _stage in STAGE_CONTRACTS:
    for _req in (*_stage.required_outputs, *_stage.required_reasoning, *_stage.required_context):
        STRICT_EVIDENCE_ALIASES.setdefault(_req.canonical_path, _req.blob_candidates)
FIXTURE_COMPONENT_HINTS = (
    "contoso",
    "interwoven",
    "state_machine",
    "precondition_trap",
    "adversarial",
    "race_sensitive",
)

CANONICAL_STATUS_ORDER = dict(_STATUS_ORDER)
DISCOVERED_STATUSES = set(_DISCOVERED_STATUSES)
ENTRY_POINT_RE = re.compile(r"^(entry|_?DllMain|_?DllEntryPoint|_?CRT|_?wmain|_?main)$", re.I)
NON_DELIVERABLE_SCHEMA_FUNCTIONS = frozenset({"record_finding", "enrich_invocable"})
_ARTIFACT_PRODUCER_STAGES: dict[str, tuple[str, ...]] = {}
for _stage in STAGE_CONTRACTS:
    for _req in (*_stage.required_outputs, *_stage.required_reasoning, *_stage.required_context):
        current = list(_ARTIFACT_PRODUCER_STAGES.get(_req.canonical_path, ()))
        if _stage.id not in current:
            current.append(_stage.id)
        _ARTIFACT_PRODUCER_STAGES[_req.canonical_path] = tuple(current)


@dataclass
class ContractResult:
    valid: bool
    missing: list[str]
    parse_errors: list[str]
    hard_fail: bool
    parsed: dict[str, Any]


@dataclass
class CollectResult:
    contract: ContractResult
    dashboard_row: dict[str, Any]
    session_save_meta: dict[str, Any]
    run_validity: dict[str, Any]
    kpi_run: dict[str, Any]
    schema_handoff_audit: dict[str, Any]
    stage_handoff_audit: dict[str, Any]
    transition_contract_audit: dict[str, Any]
    validation_report: dict[str, Any]
    artifact_index: dict[str, Any]
    ledger: dict[str, Any] | None = None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _path_exists_any(session_dir: Path, rel_paths: tuple[str, ...] | list[str]) -> bool:
    for rel in rel_paths:
        if (session_dir / rel).exists():
            return True
    return False


def _resolve_existing_path(session_dir: Path, canonical_path: str, aliases: tuple[str, ...] | list[str]) -> str | None:
    candidates = [canonical_path, *list(aliases)]
    for rel in candidates:
        if (session_dir / rel).exists():
            return rel
    return None


def _status_to_canonical(status: Any) -> str:
    return normalize_status(status)


def _validate_contract(session_dir: Path, mode: str) -> ContractResult:
    missing: list[str] = []
    parse_errors: list[str] = []
    parsed: dict[str, Any] = {}

    for name in REQUIRED_CONTRACT_FILES:
        path = session_dir / name
        if not path.exists():
            missing.append(name)
            continue
        try:
            parsed[name] = _read_json(path)
        except Exception:
            parse_errors.append(f"{name}: invalid JSON")

    if "stage-index.json" in parsed:
        version = str((parsed["stage-index.json"] or {}).get("version") or "")
        if version and version not in SUPPORTED_VERSION:
            parse_errors.append(f"stage-index.json: unsupported version '{version}'")
    if "transition-index.json" in parsed:
        version = str((parsed["transition-index.json"] or {}).get("version") or "")
        if version and version not in SUPPORTED_VERSION:
            parse_errors.append(f"transition-index.json: unsupported version '{version}'")
    if "cohesion-report.json" in parsed:
        version = str((parsed["cohesion-report.json"] or {}).get("version") or "")
        if version and version not in SUPPORTED_VERSION:
            parse_errors.append(f"cohesion-report.json: unsupported version '{version}'")

    hard_fail = False
    if "cohesion-report.json" in parsed:
        try:
            hard_fail = bool(parsed["cohesion-report.json"]["gates"]["hard_fail"])
        except Exception:
            hard_fail = False

    parallel_runs = 1
    variant_configs_count = 0
    contract_version = ""
    if "session-meta.json" in parsed and isinstance(parsed["session-meta.json"], dict):
        sm = parsed["session-meta.json"]
        parallel_runs = _safe_int(sm.get("parallel_runs"), 1)
        variant_configs_count = _safe_int(sm.get("variant_configs_count"), 0)
        contract_version = str(sm.get("contract_version") or "").strip()

    if mode == "strict" and contract_version:
        if not is_capture_compatible(AUDITOR_VERSION, contract_version):
            parse_errors.append(
                f"contract.compatibility_mismatch:{contract_version}->{AUDITOR_VERSION}"
            )

    if mode == "strict":
        stage_rows = []
        transition_rows = []
        if "stage-index.json" in parsed and isinstance(parsed["stage-index.json"], dict):
            stage_rows = list(parsed["stage-index.json"].get("stages") or [])
        if "transition-index.json" in parsed and isinstance(parsed["transition-index.json"], dict):
            transition_rows = list(parsed["transition-index.json"].get("transitions") or [])
        enforce_strict_evidence = bool(stage_rows or transition_rows)

        strict_missing: list[str] = []
        stage_rows_by_id = {
            str((row or {}).get("id") or "").strip(): dict(row)
            for row in stage_rows
            if isinstance(row, dict) and str((row or {}).get("id") or "").strip()
        }
        gap_triggered = bool(
            ((stage_rows_by_id.get("S-06") or {}).get("checks") or {}).get("answer_gaps_triggered")
        )
        if enforce_strict_evidence:
            for stage in STAGE_CONTRACTS:
                stage_row = stage_rows_by_id.get(stage.id) or {}
                skip_reason = str(stage_row.get("skip_reason") or "").strip()
                floor_broadening_blocked = skip_reason.split(":", 1)[0] == "floor_broadening_blocked"
                stage_optional_skip = (
                    str(stage_row.get("status") or "").strip().lower() == "skipped"
                    and stage_skip_reason_is_allowed(
                        stage,
                        skip_reason,
                        gap_triggered=gap_triggered,
                        floor_broadening_blocked=floor_broadening_blocked,
                    )
                )
                if stage_optional_skip:
                    continue
                for req in (*stage.required_outputs, *stage.required_reasoning):
                    aliases = STRICT_EVIDENCE_ALIASES.get(req.canonical_path, (req.canonical_path,))
                    if not _path_exists_any(session_dir, aliases):
                        strict_missing.append(req.canonical_path)
        # Context evidence may be intentionally dropped for compact captures.
        snapshot_profile = "full"
        profile_path = session_dir / "snapshot-profile.json"
        if profile_path.exists():
            try:
                profile = _read_json(profile_path)
                snapshot_profile = str((profile or {}).get("profile") or "full").strip().lower()
            except Exception:
                snapshot_profile = "full"
        if enforce_strict_evidence and snapshot_profile != "compact":
            for stage in STAGE_CONTRACTS:
                stage_row = stage_rows_by_id.get(stage.id) or {}
                skip_reason = str(stage_row.get("skip_reason") or "").strip()
                floor_broadening_blocked = skip_reason.split(":", 1)[0] == "floor_broadening_blocked"
                stage_optional_skip = (
                    str(stage_row.get("status") or "").strip().lower() == "skipped"
                    and stage_skip_reason_is_allowed(
                        stage,
                        skip_reason,
                        gap_triggered=gap_triggered,
                        floor_broadening_blocked=floor_broadening_blocked,
                    )
                )
                if stage_optional_skip:
                    continue
                for req in stage.required_context:
                    aliases = STRICT_EVIDENCE_ALIASES.get(req.canonical_path, (req.canonical_path,))
                    if not _path_exists_any(session_dir, aliases):
                        strict_missing.append(req.canonical_path)
        for rel in strict_missing:
            parse_errors.append(f"strict_evidence_missing:{rel}")

        if parallel_runs > 1 or variant_configs_count > 0:
            variants_dir = session_dir / "stages" / "s02_probe" / "variants"
            merged_dir = session_dir / "stages" / "s02_probe" / "merged"
            has_variant = variants_dir.exists() and any(variants_dir.rglob("*"))
            has_merged = merged_dir.exists() and any(merged_dir.rglob("*"))
            if not (has_variant and has_merged):
                parse_errors.append(
                    "strict_evidence_missing:stages/s02_probe/variants_or_merged"
                )
        if stage_rows:
            stage_ids = {str((row or {}).get("id") or "").strip() for row in stage_rows}
            for stage in STAGE_CONTRACTS:
                if stage.id not in stage_ids:
                    parse_errors.append(f"strict_stage_missing:{stage.id}")
        if transition_rows:
            transition_ids = {str((row or {}).get("id") or "").strip() for row in transition_rows}
            for tid in TRANSITION_ORDER:
                if tid not in transition_ids:
                    parse_errors.append(f"strict_transition_missing:{tid}")

    valid = not missing and not parse_errors
    if mode == "compatibility":
        # Compatibility mode is permissive: it records contract issues but
        # allows collector output generation for degraded captures.
        valid = True

    return ContractResult(
        valid=valid,
        missing=missing,
        parse_errors=parse_errors,
        hard_fail=hard_fail,
        parsed=parsed,
    )


def _load_latest_findings(session_dir: Path) -> list[dict[str, Any]]:
    candidates = (
        session_dir / "stage-05-finalization" / "findings.json",
        session_dir / "stage-02-synthesis" / "findings.json",
        session_dir / "findings.json",
        session_dir / "evidence" / "stage-02-probe-loop" / "findings.json",
    )
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = _read_json(path)
        except Exception:
            continue
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
    return []


def _latest_per_function(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in findings:
        fn = str(row.get("function") or "").strip()
        if fn:
            latest[fn] = row
    return latest


def _resolve_scoring_scope(session_meta: dict[str, Any] | None) -> list[str]:
    from api.pipeline.core.scoring_scope import target_scope_names

    return target_scope_names(session_meta or {})


def _compute_status_counts(
    findings: list[dict[str, Any]],
    session_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from api.pipeline.core.scoring_scope import canonical_status_map

    latest = _latest_per_function(findings)
    scoring_scope = _resolve_scoring_scope(session_meta)
    scoped_status_map = canonical_status_map(list(latest.values()), scoring_scope)
    counts = {
        "verified_success": 0,
        "functional_precondition_unmet": 0,
        "inferred_success": 0,
        "failure": 0,
        "unknown": 0,
    }
    function_statuses: dict[str, str] = {}

    if not scoring_scope:
        scoped_status_map = {}
        for fn, row in latest.items():
            if ENTRY_POINT_RE.match(fn):
                continue
            canonical = _status_to_canonical(row.get("status_canonical") or row.get("status"))
            scoped_status_map[fn] = canonical

    for fn, canonical in scoped_status_map.items():
        if ENTRY_POINT_RE.match(fn):
            continue
        counts[canonical] += 1
        function_statuses[fn] = canonical

    total = len(function_statuses)
    verified = counts["verified_success"]
    discovered = (
        counts["verified_success"]
        + counts["functional_precondition_unmet"]
        + counts["inferred_success"]
    )
    verified_rate = round((verified / total), 4) if total else 0.0
    discovered_rate = round((discovered / total), 4) if total else 0.0

    return {
        "counts": counts,
        "function_statuses": function_statuses,
        "total": total,
        "verified": verified,
        "discovered": discovered,
        "verified_rate": verified_rate,
        "discovered_rate": discovered_rate,
    }


def _build_stage_handoff_audit(session_dir: Path) -> dict[str, Any]:
    stage_index_path = session_dir / "stage-index.json"
    stage_status_map: dict[str, str] = {}
    stage_skip_reason_map: dict[str, str] = {}
    gap_triggered = False
    if stage_index_path.exists():
        try:
            stage_index_payload = _read_json(stage_index_path)
            for row in list((stage_index_payload or {}).get("stages") or []):
                sid = str((row or {}).get("id") or "").strip()
                if sid:
                    stage_status_map[sid] = str((row or {}).get("status") or "").strip().lower()
                    stage_skip_reason_map[sid] = str((row or {}).get("skip_reason") or "").strip()
                    if sid == "S-06":
                        gap_triggered = bool(((row or {}).get("checks") or {}).get("answer_gaps_triggered"))
        except Exception:
            stage_status_map = {}
            stage_skip_reason_map = {}
            gap_triggered = False

    rows: list[dict[str, Any]] = []
    fail_count = 0
    skipped_count = 0

    def _stage_optional_skip(stage_id: str) -> bool:
        stage = next((candidate for candidate in STAGE_CONTRACTS if candidate.id == stage_id), None)
        if stage is None:
            return False
        skip_reason = stage_skip_reason_map.get(stage_id, "")
        floor_broadening_blocked = skip_reason.split(":", 1)[0] == "floor_broadening_blocked"
        return stage_skip_reason_is_allowed(
            stage,
            skip_reason,
            gap_triggered=gap_triggered,
            floor_broadening_blocked=floor_broadening_blocked,
        )

    def _check_requirements(
        requirements: list[Any],
        *,
        allow_optional_upstream_skip: bool = False,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        evidence_rows: list[dict[str, Any]] = []
        missing_paths: list[str] = []
        for req in requirements:
            aliases = tuple(req.blob_candidates or ())
            existing = _resolve_existing_path(session_dir, req.canonical_path, aliases)
            waived = False
            if not existing and allow_optional_upstream_skip:
                producer_stages = _ARTIFACT_PRODUCER_STAGES.get(req.canonical_path, ())
                waived = any(_stage_optional_skip(stage_id) for stage_id in producer_stages)
            ok = bool(existing) or waived
            evidence_rows.append(
                {
                    "canonical_path": req.canonical_path,
                    "resolved_path": existing or ("waived_by_optional_skip" if waived else None),
                    "ok": ok,
                }
            )
            if not ok:
                missing_paths.append(req.canonical_path)
        return evidence_rows, missing_paths

    for stage in STAGE_CONTRACTS:
        runtime_status = stage_status_map.get(stage.id, "")
        stage_skipped = runtime_status == "skipped"
        skip_reason = stage_skip_reason_map.get(stage.id, "")
        floor_broadening_blocked = skip_reason.split(":", 1)[0] == "floor_broadening_blocked"
        optional_skip = stage_skipped and stage_skip_reason_is_allowed(
            stage,
            skip_reason,
            gap_triggered=gap_triggered,
            floor_broadening_blocked=floor_broadening_blocked,
        )

        input_rows, missing_inputs = _check_requirements(
            list(stage.required_inputs),
            allow_optional_upstream_skip=True,
        )
        output_rows, missing_outputs = _check_requirements(list(stage.required_outputs))
        context_rows, missing_context = _check_requirements(list(stage.required_context))
        reasoning_rows, missing_reasoning = _check_requirements(list(stage.required_reasoning))

        missing = missing_inputs + missing_outputs + missing_context + missing_reasoning
        if optional_skip:
            status = "skipped"
            missing = []
            skipped_count += 1
        else:
            status = "pass" if not missing else "fail"
            if missing:
                fail_count += 1

        rows.append(
            {
                "stage_id": stage.id,
                "stage_name": stage.name,
                "runtime_status": runtime_status or "unknown",
                "status": status,
                "missing": missing,
                "required_inputs": input_rows,
                "required_outputs": output_rows,
                "required_context": context_rows,
                "required_reasoning": reasoning_rows,
            }
        )

    return {
        "version": "1.0",
        "contract_version": CONTRACT_VERSION,
        "auditor_version": AUDITOR_VERSION,
        "source_of_truth": "api/pipeline/core/handoff_contract.py",
        "summary": {
            "stage_count": len(rows),
            "pass_count": sum(1 for row in rows if row.get("status") == "pass"),
            "fail_count": fail_count,
            "skipped_count": skipped_count,
            "valid": fail_count == 0,
        },
        "stages": rows,
    }


_TRANSITION_EVIDENCE_ALIASES: dict[str, tuple[str, ...]] = {
    "diagnostics/transcript.txt": ("diagnostics/chat_transcript.txt",),
    "diagnostics/executor-trace.json": ("diagnostics/executor_trace.json",),
    "diagnostics/chat-system-context-turn0.txt": ("diagnostics/chat-system-context.txt",),
}

_TRANSITION_OPTIONAL_EVIDENCE_ON_WARN: dict[str, dict[str, tuple[str, ...]]] = {
    "T-21": {
        "consumer": ("evidence/mc-decisions/winning-init-sequence.json",),
    },
}


def _build_transition_contract_audit(session_dir: Path) -> dict[str, Any]:
    stage_index_path = session_dir / "stage-index.json"
    stage_skip_reason_map: dict[str, str] = {}
    gap_triggered = False
    if stage_index_path.exists():
        try:
            payload = _read_json(stage_index_path)
            for row in list((payload or {}).get("stages") or []):
                sid = str((row or {}).get("id") or "").strip()
                if sid:
                    stage_skip_reason_map[sid] = str((row or {}).get("skip_reason") or "").strip()
                    if sid == "S-06":
                        gap_triggered = bool(((row or {}).get("checks") or {}).get("answer_gaps_triggered"))
        except Exception:
            stage_skip_reason_map = {}
            gap_triggered = False

    transition_index_path = session_dir / "transition-index.json"
    transitions: list[dict[str, Any]] = []
    if transition_index_path.exists():
        try:
            payload = _read_json(transition_index_path)
            transitions = [row for row in list((payload or {}).get("transitions") or []) if isinstance(row, dict)]
        except Exception:
            transitions = []

    by_id = {str(row.get("id") or "").strip(): row for row in transitions if str(row.get("id") or "").strip()}
    rows: list[dict[str, Any]] = []
    fail_count = 0

    def _verify_evidence(expected: tuple[str, ...], actual: list[str]) -> tuple[list[str], list[str]]:
        missing_in_row = [path for path in expected if path not in actual]
        missing_on_disk: list[str] = []
        for path in expected:
            aliases = _TRANSITION_EVIDENCE_ALIASES.get(path, ())
            resolved = _resolve_existing_path(session_dir, path, aliases)
            if not resolved:
                missing_on_disk.append(path)
        return missing_in_row, missing_on_disk

    def _artifact_waived_by_optional_skip(path: str) -> bool:
        for stage_id in _ARTIFACT_PRODUCER_STAGES.get(path, ()):
            stage = next((candidate for candidate in STAGE_CONTRACTS if candidate.id == stage_id), None)
            if stage is None:
                continue
            skip_reason = stage_skip_reason_map.get(stage_id, "")
            floor_broadening_blocked = skip_reason.split(":", 1)[0] == "floor_broadening_blocked"
            if stage_skip_reason_is_allowed(
                stage,
                skip_reason,
                gap_triggered=gap_triggered,
                floor_broadening_blocked=floor_broadening_blocked,
            ):
                return True
        return False

    for tid in TRANSITION_ORDER:
        contract = TRANSITION_CONTRACT_BY_ID[tid]
        row = by_id.get(tid)
        if row is None:
            fail_count += 1
            rows.append(
                {
                    "transition_id": tid,
                    "name": contract.name,
                    "status": "fail",
                    "issues": [f"missing_transition_row:{tid}"],
                }
            )
            continue

        issues: list[str] = []
        actual_name = str(row.get("name") or "")
        if actual_name != contract.name:
            issues.append(f"name_mismatch:{actual_name}->{contract.name}")
        actual_producer_stage = str(row.get("producer_stage") or "")
        actual_consumer_stage = str(row.get("consumer_stage") or "")
        if actual_producer_stage != contract.producer_stage:
            issues.append(
                f"producer_stage_mismatch:{actual_producer_stage}->{contract.producer_stage}"
            )
        if actual_consumer_stage != contract.consumer_stage:
            issues.append(
                f"consumer_stage_mismatch:{actual_consumer_stage}->{contract.consumer_stage}"
            )

        producer_actual = [str(x) for x in list(row.get("producer_evidence") or [])]
        consumer_actual = [str(x) for x in list(row.get("consumer_evidence") or [])]
        effect_actual = [str(x) for x in list(row.get("effect_evidence") or [])]

        prod_missing_row, prod_missing_disk = _verify_evidence(contract.producer_evidence, producer_actual)
        cons_missing_row, cons_missing_disk = _verify_evidence(contract.consumer_evidence, consumer_actual)
        eff_missing_row, eff_missing_disk = _verify_evidence(contract.effect_evidence, effect_actual)

        transition_status = str(row.get("status") or "").strip().lower()
        allow_missing_disk = transition_status == "not_applicable"
        optional_on_warn = _TRANSITION_OPTIONAL_EVIDENCE_ON_WARN.get(tid, {}) if transition_status == "warn" else {}
        optional_producer = set(optional_on_warn.get("producer", ()))
        optional_consumer = set(optional_on_warn.get("consumer", ()))
        optional_effect = set(optional_on_warn.get("effect", ()))

        if prod_missing_row:
            issues.append(f"producer_evidence_missing_in_row:{','.join(prod_missing_row)}")
        if cons_missing_row:
            issues.append(f"consumer_evidence_missing_in_row:{','.join(cons_missing_row)}")
        if eff_missing_row:
            issues.append(f"effect_evidence_missing_in_row:{','.join(eff_missing_row)}")
        if prod_missing_disk and not allow_missing_disk:
            prod_missing_disk = [path for path in prod_missing_disk if path not in optional_producer]
            prod_missing_disk = [path for path in prod_missing_disk if not _artifact_waived_by_optional_skip(path)]
        if cons_missing_disk and not allow_missing_disk:
            cons_missing_disk = [path for path in cons_missing_disk if path not in optional_consumer]
            cons_missing_disk = [path for path in cons_missing_disk if not _artifact_waived_by_optional_skip(path)]
        if eff_missing_disk and not allow_missing_disk:
            eff_missing_disk = [path for path in eff_missing_disk if path not in optional_effect]
            eff_missing_disk = [path for path in eff_missing_disk if not _artifact_waived_by_optional_skip(path)]
        if prod_missing_disk and not allow_missing_disk:
            issues.append(f"producer_evidence_missing_on_disk:{','.join(prod_missing_disk)}")
        if cons_missing_disk and not allow_missing_disk:
            issues.append(f"consumer_evidence_missing_on_disk:{','.join(cons_missing_disk)}")
        if eff_missing_disk and not allow_missing_disk:
            issues.append(f"effect_evidence_missing_on_disk:{','.join(eff_missing_disk)}")
        if transition_status == "fail":
            issues.append("transition_status_fail")

        status = "pass" if not issues else "fail"
        if status == "fail":
            fail_count += 1
        rows.append(
            {
                "transition_id": tid,
                "name": contract.name,
                "status": status,
                "transition_status": transition_status,
                "issues": issues,
            }
        )

    return {
        "version": "1.0",
        "contract_version": CONTRACT_VERSION,
        "auditor_version": AUDITOR_VERSION,
        "source_of_truth": "api/pipeline/core/handoff_contract.py",
        "summary": {
            "transition_count": len(rows),
            "pass_count": sum(1 for row in rows if row.get("status") == "pass"),
            "fail_count": fail_count,
            "valid": fail_count == 0,
        },
        "transitions": rows,
    }


def _is_fixture_component(component: str) -> bool:
    lower = str(component or "").lower()
    return any(token in lower for token in FIXTURE_COMPONENT_HINTS)


def _build_run_validity(
    contract: ContractResult,
    component: str,
    analysis_profile: str,
    status_counts: dict[str, Any],
    invocable_count: int,
    mode: str = "strict",
    session_dir: Path | None = None,
    schema_handoff_audit: dict[str, Any] | None = None,
    stage_handoff_audit: dict[str, Any] | None = None,
    transition_contract_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = str(analysis_profile or "strict_dll").strip().lower()
    if profile not in {"strict_dll", "greybox_dll", "full_surface"}:
        profile = "strict_dll"

    gate_results: dict[str, bool] = {
        "contract_valid": True if mode == "compatibility" else bool(contract.valid),
        "hard_fail_clear": not bool(contract.hard_fail),
        "invocable_band": invocable_count > 0 and invocable_count <= 2500,
        "profile_allowed_for_fixture": True,
        "status_payload_present": _safe_int(status_counts.get("total"), 0) > 0,
        "schema_handoff_consistent": True,
        "stage_handoff_valid": True,
        "transition_contract_valid": True,
    }
    schema_drop_to_zero_count = 0
    schema_regression_count = 0
    schema_silent_loss_count = 0
    stage_handoff_fail_count = 0
    transition_contract_fail_count = 0

    if _is_fixture_component(component):
        gate_results["profile_allowed_for_fixture"] = profile != "full_surface"
    if isinstance(schema_handoff_audit, dict):
        summary = schema_handoff_audit.get("summary") or {}
        schema_drop_to_zero_count = _safe_int(summary.get("drop_to_zero_count"), 0)
        schema_regression_count = _safe_int(summary.get("regression_count"), 0)
        schema_silent_loss_count = _safe_int(summary.get("silent_function_loss_count"), 0)
        gate_results["schema_handoff_consistent"] = (
            schema_drop_to_zero_count == 0
            and schema_regression_count == 0
            and schema_silent_loss_count == 0
        )
    if isinstance(stage_handoff_audit, dict):
        summary = stage_handoff_audit.get("summary") or {}
        stage_handoff_fail_count = _safe_int(summary.get("fail_count"), 0)
        gate_results["stage_handoff_valid"] = bool(summary.get("valid", stage_handoff_fail_count == 0))
    if isinstance(transition_contract_audit, dict):
        summary = transition_contract_audit.get("summary") or {}
        transition_contract_fail_count = _safe_int(summary.get("fail_count"), 0)
        gate_results["transition_contract_valid"] = bool(
            summary.get("valid", transition_contract_fail_count == 0)
        )

    reasons: list[str] = []
    if not gate_results["contract_valid"]:
        reasons.append("contract.invalid")
        for missing_name in contract.missing:
            reasons.append(f"contract.missing:{missing_name}")
        for parse_error in contract.parse_errors:
            normalized = str(parse_error).strip().replace(" ", "_")
            reasons.append(f"contract.parse_error:{normalized}")
    elif mode == "compatibility" and (contract.missing or contract.parse_errors):
        reasons.append("contract.degraded_compatibility_mode")
        for missing_name in contract.missing:
            reasons.append(f"contract.missing_compat:{missing_name}")
        for parse_error in contract.parse_errors:
            normalized = str(parse_error).strip().replace(" ", "_")
            reasons.append(f"contract.parse_error_compat:{normalized}")
    if not gate_results["hard_fail_clear"]:
        reasons.append("cohesion.hard_fail")
    if not gate_results["invocable_band"]:
        reasons.append(f"invocables.out_of_band:{invocable_count}")
    if not gate_results["profile_allowed_for_fixture"]:
        reasons.append("analysis_profile.full_surface_for_fixture")
    if not gate_results["status_payload_present"]:
        reasons.append("missing.findings_status_payload")
    if not gate_results["schema_handoff_consistent"]:
        if schema_drop_to_zero_count > 0:
            reasons.append("schema.handoff_drop_to_zero")
        if schema_regression_count > 0:
            reasons.append("schema.handoff_regression")
        if schema_silent_loss_count > 0:
            reasons.append("schema.handoff_function_loss")
    if not gate_results["stage_handoff_valid"]:
        reasons.append(f"stage_handoff.fail_count:{stage_handoff_fail_count}")
    if not gate_results["transition_contract_valid"]:
        reasons.append(f"transition_contract.fail_count:{transition_contract_fail_count}")

    valid = all(gate_results.values())
    return {
        "version": "1.0",
        "contract_version": CONTRACT_VERSION,
        "auditor_version": AUDITOR_VERSION,
        "valid": valid,
        "reasons": reasons,
        "profile": profile,
        "component": component,
        "invocable_count": invocable_count,
        "gate_results": gate_results,
        "verified_rate": status_counts.get("verified_rate", 0.0),
        "discovered_rate": status_counts.get("discovered_rate", 0.0),
        "schema_handoff_drop_to_zero_count": schema_drop_to_zero_count,
        "schema_handoff_regression_count": schema_regression_count,
        "schema_handoff_silent_loss_count": schema_silent_loss_count,
        "stage_handoff_fail_count": stage_handoff_fail_count,
        "transition_contract_fail_count": transition_contract_fail_count,
        "forward_gap_kpi_artifacts": {
            rel: (session_dir / rel).exists() if session_dir else False
            for rel in FORWARD_GAP_KPI_ARTIFACTS
        },
    }


def _write_summary(human_dir: Path, contract: ContractResult, mode: str) -> None:
    lines = [
        "# Contract Compliance Summary",
        "",
        f"Mode: {mode}",
        f"Valid: {contract.valid}",
        f"Hard Fail: {contract.hard_fail}",
        "",
        "## Missing Required Files",
    ]
    if contract.missing:
        lines.extend(f"- {x}" for x in contract.missing)
    else:
        lines.append("(none)")

    lines.extend(["", "## Parse Errors"])
    if contract.parse_errors:
        lines.extend(f"- {x}" for x in contract.parse_errors)
    else:
        lines.append("(none)")

    (human_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_dashboard_row(
    contract: ContractResult,
    date: str,
    folder: str,
    job_id: str,
    component: str,
    commit: str,
    note: str,
    saved_at: str,
    analysis_profile: str,
    snapshot_profile: str,
    run_validity: dict[str, Any],
    status_counts: dict[str, Any],
) -> dict[str, Any]:
    cohesion = contract.parsed.get("cohesion-report.json") if contract.parsed else None
    session_meta = contract.parsed.get("session-meta.json") if contract.parsed else None

    transition_fail_count = None
    stage_fail_count = None
    pipeline_verdict = "UNKNOWN"
    failed_transitions: list[str] = []
    failed_stages: list[str] = []

    if isinstance(cohesion, dict):
        totals = cohesion.get("totals") or {}
        transition_fail_count = totals.get("transition_fail")
        stage_fail_count = totals.get("stage_fail")
        failed_transitions = list(cohesion.get("failed_transitions") or [])
        failed_stages = list(cohesion.get("failed_stages") or [])

        summary = cohesion.get("summary") or {}
        if summary.get("pipeline_verdict"):
            pipeline_verdict = str(summary.get("pipeline_verdict"))
        elif bool((cohesion.get("gates") or {}).get("hard_fail")):
            pipeline_verdict = "DEGRADED"

    session_meta_fields = {
        "prompt_profile_id": None,
        "layer": None,
        "ablation_variable": None,
        "ablation_value": None,
        "run_set_id": None,
        "coordinator_cycle": None,
            "playbook_step": None,
            "chain_step_target": None,
            "required_semantic_checkpoint": None,
            "selected_invocable_names": [],
            "write_unlock_outcome": None,
        "write_unlock_sentinel": None,
        "write_unlock_resolved_at": None,
        "sentinel_new_codes_this_run": 0,
        "functions_total": 0,
        "functions_success": 0,
        "functions_error": 0,
        "prior_job_id": None,
        "prior_findings_seeded": 0,
        "verification_verified": 0,
        "verification_inferred": 0,
        "verification_error": 0,
        "analysis_profile": analysis_profile,
        "snapshot_profile": snapshot_profile,
        "package_id": None,
        "package_label": None,
        "lane_id": None,
        "lane_trust_status": None,
        "selection_reason": None,
        "doc_visibility": None,
        "dependency_context": None,
        "blocker_family_primary": None,
        "blocker_family_secondary": [],
        "blocker_confidence": None,
        "architecture_relevance": None,
        "runtime_path_trust": None,
    }

    if isinstance(session_meta, dict):
        for key in session_meta_fields:
            val = session_meta.get(key)
            if val is not None:
                session_meta_fields[key] = val

    return {
        "contract_version": CONTRACT_VERSION,
        "auditor_version": AUDITOR_VERSION,
        "date": date,
        "folder": folder,
        "job_id": job_id,
        "component": component,
        "commit": commit,
        "note": note,
        "saved_at": saved_at,
        "contract_valid": bool(contract.valid),
        "hard_fail": bool(contract.hard_fail),
        "pipeline_verdict": pipeline_verdict,
        "transition_fail_count": transition_fail_count,
        "stage_fail_count": stage_fail_count,
        "failed_transitions": failed_transitions,
        "failed_stages": failed_stages,
        "run_valid": bool(run_validity.get("valid")),
        "verified_rate": status_counts.get("verified_rate", 0.0),
        "discovered_rate": status_counts.get("discovered_rate", 0.0),
        **session_meta_fields,
    }


def _build_session_save_meta(
    contract: ContractResult,
    mode: str,
    capture_quality: str,
    job_id: str,
    folder: str,
    commit: str,
    commit_msg: str,
    note: str,
    saved_at: str,
    snapshot_profile: str,
    run_validity: dict[str, Any],
    status_counts: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "auditor_version": AUDITOR_VERSION,
        "job_id": job_id,
        "folder": folder,
        "commit": commit,
        "commit_msg": commit_msg,
        "note": note,
        "saved_at": saved_at,
        "compatibility_mode": mode == "compatibility",
        "contract_valid": bool(contract.valid),
        "missing_contract_files": list(contract.missing),
        "parse_errors": list(contract.parse_errors),
        "hard_fail": bool(contract.hard_fail),
        "capture_quality": capture_quality,
        "snapshot_profile": snapshot_profile,
        "run_valid": bool(run_validity.get("valid")),
        "run_validity_reasons": list(run_validity.get("reasons") or []),
        "finding_count": _safe_int(status_counts.get("total"), 0),
        "gap_count": _safe_int(status_counts.get("total"), 0) - _safe_int(status_counts.get("discovered"), 0),
    }


def _build_kpi_run(
    folder: str,
    job_id: str,
    component: str,
    date: str,
    saved_at: str,
    status_counts: dict[str, Any],
    session_meta: dict[str, Any],
    run_validity: dict[str, Any],
) -> dict[str, Any]:
    counts = status_counts.get("counts") or {}
    total = _safe_int(status_counts.get("total"), 0)
    verified = _safe_int(status_counts.get("verified"), 0)
    discovered = _safe_int(status_counts.get("discovered"), 0)

    verification_verified = _safe_int(session_meta.get("verification_verified"), 0)
    verification_inferred = _safe_int(session_meta.get("verification_inferred"), 0)
    verification_error = _safe_int(session_meta.get("verification_error"), 0)

    verified_rate = _safe_float(status_counts.get("verified_rate"), 0.0)
    discovered_rate = _safe_float(status_counts.get("discovered_rate"), 0.0)
    verified_vs_inferred = (
        round(verification_verified / (verification_verified + verification_inferred), 4)
        if (verification_verified + verification_inferred)
        else 0.0
    )

    return {
        "version": "1.0",
        "contract_version": CONTRACT_VERSION,
        "auditor_version": AUDITOR_VERSION,
        "date": date,
        "saved_at": saved_at,
        "folder": folder,
        "job_id": job_id,
        "component": component,
        "valid_run": bool(run_validity.get("valid")),
        "analysis_profile": run_validity.get("profile", "unknown"),
        "totals": {
            "total_functions": total,
            "verified_success": _safe_int(counts.get("verified_success"), 0),
            "functional_precondition_unmet": _safe_int(counts.get("functional_precondition_unmet"), 0),
            "inferred_success": _safe_int(counts.get("inferred_success"), 0),
            "failure": _safe_int(counts.get("failure"), 0),
            "unknown": _safe_int(counts.get("unknown"), 0),
            "discovered": discovered,
        },
        "rates": {
            "verified_rate": verified_rate,
            "discovered_rate": discovered_rate,
            "verified_vs_inferred": verified_vs_inferred,
        },
        "verification": {
            "verified": verification_verified,
            "inferred": verification_inferred,
            "error": verification_error,
        },
        "runtime": {
            "total_sec": None,
            "stage_p95_sec": None,
        },
        "cost": {
            "run_usd": None,
            "per_verified_function_usd": None,
        },
        "flake_inputs": {
            "function_statuses": status_counts.get("function_statuses") or {},
        },
        "gaps": {
            "stage_runtime": "not_available",
            "cost_run": "not_available",
        },
    }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fingerprint_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _find_sessions_root(session_dir: Path) -> Path:
    for candidate in [session_dir, *session_dir.parents]:
        if candidate.name.lower() == "sessions":
            return candidate
    return session_dir.parent


def _infer_seeding_mode(session_meta: dict[str, Any]) -> str:
    """Derive explicit seeding_mode from session metadata."""
    prior_id = session_meta.get("prior_job_id") or ""
    cross_dll_ids = session_meta.get("cross_dll_prior_job_ids") or []
    has_same = bool(prior_id)
    has_cross = bool(cross_dll_ids)
    if has_same and has_cross:
        return "mixed"
    if has_cross:
        return "cross_dll_prior"
    if has_same:
        return "same_dll_prior"
    return "none"


def _build_comparable_profile_key(
    run_validity: dict[str, Any],
    snapshot_profile: str,
    session_meta: dict[str, Any],
) -> str:
    profile = str(run_validity.get("profile") or "strict_dll").strip().lower()
    prompt_profile = str(session_meta.get("prompt_profile_id") or "default").strip().lower()
    layer = str(session_meta.get("layer") or "none").strip().lower()
    seeding_mode = _infer_seeding_mode(session_meta)
    graph_epoch = str(session_meta.get("graph_epoch") or "none").strip().lower()
    return (
        f"{profile}|snapshot={snapshot_profile}|prompt={prompt_profile}"
        f"|layer={layer}|seed={seeding_mode}|graph={graph_epoch}"
    )


def _parse_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _safe_metric(row: dict[str, Any], *path: str) -> float:
    cur: Any = row
    for part in path:
        if not isinstance(cur, dict):
            return 0.0
        cur = cur.get(part)
    try:
        return float(cur or 0.0)
    except Exception:
        return 0.0


def _compute_delta(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if not previous:
        return {"baseline": True}
    return {
        "baseline": False,
        "total_functions": int(_safe_metric(current, "metrics", "total_functions") - _safe_metric(previous, "metrics", "total_functions")),
        "verified_success": int(_safe_metric(current, "metrics", "verified_success") - _safe_metric(previous, "metrics", "verified_success")),
        "discovered": int(_safe_metric(current, "metrics", "discovered") - _safe_metric(previous, "metrics", "discovered")),
        "failure": int(_safe_metric(current, "metrics", "failure") - _safe_metric(previous, "metrics", "failure")),
        "verified_rate": round(_safe_metric(current, "metrics", "verified_rate") - _safe_metric(previous, "metrics", "verified_rate"), 6),
        "discovered_rate": round(_safe_metric(current, "metrics", "discovered_rate") - _safe_metric(previous, "metrics", "discovered_rate"), 6),
    }


def _extract_entity_namespace(
    findings: list[dict[str, Any]],
    vocab: dict[str, Any],
) -> list[str]:
    """Extract entity ID patterns from vocab id_formats and working_call args."""
    patterns: set[str] = set()
    for fmt in vocab.get("id_formats", []):
        if isinstance(fmt, str) and fmt.strip():
            patterns.add(fmt.strip())
    id_re = re.compile(r"[A-Z]{2,}[-_][A-Z0-9]{2,}[-_]?[A-Z0-9]*", re.I)
    for row in findings:
        wc = row.get("working_call") if isinstance(row, dict) else None
        if not isinstance(wc, dict):
            continue
        for v in wc.values():
            if isinstance(v, str):
                for m in id_re.findall(v):
                    patterns.add(m)
    return sorted(patterns)


def _count_function_dependencies(session_dir: Path) -> int:
    """Count functions with a 'depends_on' field in the invocables map."""
    inv_path = session_dir / "stage-05-finalization" / "invocables_map.json"
    if not inv_path.exists():
        inv_path = session_dir / "invocables_map.json"
    if not inv_path.exists():
        return 0
    try:
        data = _read_json(inv_path)
    except Exception:
        return 0
    if isinstance(data, dict):
        return sum(1 for v in data.values() if isinstance(v, dict) and v.get("depends_on"))
    return 0


def _compute_cross_dll_entity_overlap(
    entity_namespace: list[str],
    dll_fingerprint: str,
    existing_rows: list[dict[str, Any]],
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute cross-DLL entity overlap split into pattern/value/type.

    Returns dict with:
      - entity_pattern_overlap: ID format patterns shared (e.g. CUST-*)
      - entity_value_overlap: specific observed IDs shared across DLLs
      - entity_type_overlap: entity type categories shared (customer, sku, etc.)
    """
    if not entity_namespace:
        return {"entity_pattern_overlap": [], "entity_value_overlap": [], "entity_type_overlap": []}

    other_namespaces: set[str] = set()
    other_values: set[str] = set()
    for row in existing_rows:
        if str(row.get("dll_fingerprint") or "") == dll_fingerprint:
            continue
        for eid in (row.get("entity_namespace") or []):
            if isinstance(eid, str):
                other_namespaces.add(eid)
        for val in (row.get("entity_observed_values") or []):
            if isinstance(val, str):
                other_values.add(val)

    pattern_overlap = sorted(set(entity_namespace) & other_namespaces)

    observed_values: set[str] = set()
    id_re = re.compile(r"[A-Z]{2,}[-_][A-Z0-9]{2,}[-_]?[A-Z0-9]*", re.I)
    for f in (findings or []):
        wc = f.get("working_call") if isinstance(f, dict) else None
        if not isinstance(wc, dict):
            continue
        for v in wc.values():
            if isinstance(v, str):
                for m in id_re.findall(v):
                    observed_values.add(m)
    value_overlap = sorted(observed_values & other_values) if other_values else []

    _TYPE_HINTS = {
        "CUST": "customer", "ORD": "order", "TXN": "transaction",
        "SKU": "sku", "WDG": "sku", "PRO": "sku", "ACC": "sku",
        "RESV": "reservation", "INV": "invoice",
    }
    current_types: set[str] = set()
    for pat in entity_namespace:
        prefix = pat.split("-")[0].upper() if "-" in pat else pat[:4].upper()
        if prefix in _TYPE_HINTS:
            current_types.add(_TYPE_HINTS[prefix])
    other_types: set[str] = set()
    for pat in other_namespaces:
        prefix = pat.split("-")[0].upper() if "-" in pat else pat[:4].upper()
        if prefix in _TYPE_HINTS:
            other_types.add(_TYPE_HINTS[prefix])
    type_overlap = sorted(current_types & other_types)

    return {
        "entity_pattern_overlap": pattern_overlap,
        "entity_value_overlap": value_overlap,
        "entity_type_overlap": type_overlap,
    }


def _classify_bridge_result_fidelity(discovery_meta: dict[str, Any]) -> str:
    """Classify bridge result quality: rich_ghidra, export_only, or none."""
    if not discovery_meta:
        return "none"
    fidelity = discovery_meta.get("param_fidelity") or {}
    bridge_reachable = discovery_meta.get("bridge_reachable")
    if bridge_reachable is False:
        return "none"
    param_coverage = fidelity.get("param_coverage", 0.0)
    with_params = fidelity.get("with_params_count", 0)
    if param_coverage > 0.3 and with_params > 0:
        return "rich_ghidra"
    fn_count = fidelity.get("function_count", 0)
    if fn_count > 0:
        return "export_only"
    return "none"


def _infer_analysis_entrypoint(session_dir: Path, session_meta: dict[str, Any]) -> str:
    """Infer whether the run used analyze-path or /api/analyze (upload).

    Heuristic: if dll_path is a real filesystem path, it was analyze-path.
    If dll_path is None or a temp path, it was an upload.
    """
    explicit = str(session_meta.get("analysis_entrypoint") or "").strip().lower()
    if explicit:
        return explicit
    dll_path = session_meta.get("dll_path") or ""
    if not dll_path:
        return "unknown"
    dll_lower = str(dll_path).lower().replace("\\", "/")
    if "/tmp/" in dll_lower or "/temp/" in dll_lower or "appdata" in dll_lower:
        return "upload"
    if "fixtures" in dll_lower or "tests/" in dll_lower:
        return "analyze_path"
    return "analyze_path" if Path(dll_path).suffix.lower() == ".dll" else "unknown"


def _infer_binary_origin(session_dir: Path, session_meta: dict[str, Any]) -> str:
    """Classify how the DLL reached the analysis pipeline."""
    explicit = str(session_meta.get("binary_origin") or "").strip().lower()
    if explicit:
        return explicit
    dll_path = str(session_meta.get("dll_path") or "")
    if not dll_path:
        return "unknown"
    dll_lower = dll_path.lower().replace("\\", "/")
    if "fixtures" in dll_lower or "tests/" in dll_lower:
        return "repo_fixture"
    if "/tmp/" in dll_lower or "/temp/" in dll_lower:
        return "temp_upload"
    if "bridge" in dll_lower or "cache" in dll_lower:
        return "bridge_cache"
    return "filesystem_path"


def _compute_context_sizes(session_dir: Path) -> dict[str, int]:
    """Compute byte sizes of prior_context and cross-DLL context artifacts."""
    sizes: dict[str, int] = {"prior_context_size": 0, "cross_dll_context_size": 0}
    prior_ctx = session_dir / "prior_context.json"
    if prior_ctx.exists():
        try:
            sizes["prior_context_size"] = prior_ctx.stat().st_size
        except Exception:
            pass
    for p in session_dir.glob("cross_dll_context*.json"):
        try:
            sizes["cross_dll_context_size"] += p.stat().st_size
        except Exception:
            pass
    return sizes


def _compute_parity_delta(
    dll_fingerprint: str,
    cache_state: str | None,
    status_counts: dict[str, Any],
    existing_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Compute function-level diff vs the most recent row with opposite cache temperature."""
    if not cache_state:
        return None
    is_warm = "warm" in str(cache_state).lower()
    opposite_keyword = "cold" if is_warm else "warm"
    candidates = [
        row for row in existing_rows
        if str(row.get("dll_fingerprint") or "") == dll_fingerprint
        and opposite_keyword in str((row.get("discovery") or {}).get("cache_state") or "").lower()
    ]
    if not candidates:
        return None
    other = candidates[-1]
    other_metrics = other.get("metrics") or {}
    current_vr = _safe_float(status_counts.get("verified_rate"), 0.0)
    other_vr = _safe_float(other_metrics.get("verified_rate"), 0.0)
    current_dr = _safe_float(status_counts.get("discovered_rate"), 0.0)
    other_dr = _safe_float(other_metrics.get("discovered_rate"), 0.0)
    return {
        "compared_to_run_id": str(other.get("run_id") or ""),
        "compared_cache_state": str((other.get("discovery") or {}).get("cache_state") or ""),
        "verified_rate_delta": round(current_vr - other_vr, 6),
        "discovered_rate_delta": round(current_dr - other_dr, 6),
        "verified_success_delta": int(
            _safe_metric({"metrics": status_counts}, "metrics", "verified")
            - _safe_metric(other, "metrics", "verified_success")
        ),
    }


def _append_run_ledger(
    session_dir: Path,
    *,
    job_id: str,
    folder: str,
    component: str,
    commit: str,
    saved_at: str,
    snapshot_profile: str,
    session_meta: dict[str, Any],
    run_validity: dict[str, Any],
    kpi_run: dict[str, Any],
    findings: list[dict[str, Any]] | None = None,
    vocab: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sessions_root = _find_sessions_root(session_dir)
    ledger_path = sessions_root / "ledger" / "run_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    existing_rows = _parse_jsonl_rows(ledger_path)
    run_id = str(folder or job_id or session_dir.name).strip() or session_dir.name
    comparable_profile_key = _build_comparable_profile_key(run_validity, snapshot_profile, session_meta)

    dll_ref = str(
        session_meta.get("dll_fingerprint")
        or session_meta.get("dll_sha256")
        or session_meta.get("dll_path")
        or component
        or "unknown_dll"
    )
    dll_fingerprint = _fingerprint_text(dll_ref)

    config_ref = json.dumps(
        {
            "analysis_profile": run_validity.get("profile"),
            "snapshot_profile": snapshot_profile,
            "prompt_profile_id": session_meta.get("prompt_profile_id"),
            "layer": session_meta.get("layer"),
            "ablation_variable": session_meta.get("ablation_variable"),
            "ablation_value": session_meta.get("ablation_value"),
        },
        sort_keys=True,
    )
    config_fingerprint = _fingerprint_text(config_ref)

    discovery_meta_path = session_dir / "discovery_meta.json"
    discovery_meta: dict[str, Any] = {}
    if discovery_meta_path.exists():
        try:
            discovery_meta = json.loads(discovery_meta_path.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    _findings = findings if findings is not None else _load_latest_findings(session_dir)
    _vocab = vocab if vocab is not None else {}
    if not _vocab:
        vocab_path = session_dir / "vocab.json"
        if vocab_path.exists():
            try:
                _vocab = _read_json(vocab_path)
            except Exception:
                _vocab = {}

    entity_namespace = _extract_entity_namespace(_findings, _vocab)
    function_dependencies_declared = _count_function_dependencies(session_dir)

    cache_state = discovery_meta.get("cache_state") if discovery_meta else None
    analysis_entrypoint = _infer_analysis_entrypoint(session_dir, session_meta)
    binary_origin = _infer_binary_origin(session_dir, session_meta)
    bridge_fidelity = _classify_bridge_result_fidelity(discovery_meta)
    seeding_mode = _infer_seeding_mode(session_meta)
    graph_epoch = str(session_meta.get("graph_epoch") or "none").strip().lower() or "none"
    context_sizes = _compute_context_sizes(session_dir)

    # Collect observed entity values for cross-DLL value overlap
    _observed_values: list[str] = []
    _id_re_ledger = re.compile(r"[A-Z]{2,}[-_][A-Z0-9]{2,}[-_]?[A-Z0-9]*", re.I)
    for _f in _findings:
        _wc = _f.get("working_call") if isinstance(_f, dict) else None
        if not isinstance(_wc, dict):
            continue
        for _v in _wc.values():
            if isinstance(_v, str):
                _observed_values.extend(_id_re_ledger.findall(_v))
    entity_observed_values = sorted(set(_observed_values))

    core_payload = {
        "run_id": run_id,
        "job_id": job_id,
        "component": component,
        "git_sha": str(commit or session_meta.get("code_commit") or "unknown"),
        "contract_version": CONTRACT_VERSION,
        "auditor_version": AUDITOR_VERSION,
        "dll_fingerprint": dll_fingerprint,
        "config_fingerprint": config_fingerprint,
        "harness_profile": str(run_validity.get("profile") or "strict_dll"),
        "comparable_profile_key": comparable_profile_key,
        "model_ids": {
            "explore_model": session_meta.get("model"),
            "synthesis_model": session_meta.get("synthesis_model"),
        },
        "discovery": {
            "cache_state": cache_state,
            "bridge_reachable": discovery_meta.get("bridge_reachable"),
            "param_fidelity": discovery_meta.get("param_fidelity"),
            "analysis_profile": discovery_meta.get("analysis_profile"),
            "bridge_result_fidelity": bridge_fidelity,
        } if discovery_meta else None,
        "metrics": {
            "total_functions": int(_safe_int((kpi_run.get("totals") or {}).get("total_functions"), 0)),
            "verified_success": int(_safe_int((kpi_run.get("totals") or {}).get("verified_success"), 0)),
            "discovered": int(
                _safe_int((kpi_run.get("totals") or {}).get("functional_precondition_unmet"), 0)
                + _safe_int((kpi_run.get("totals") or {}).get("inferred_success"), 0)
            ),
            "failure": int(_safe_int((kpi_run.get("totals") or {}).get("failure"), 0)),
            "verified_rate": float(_safe_float((kpi_run.get("rates") or {}).get("verified_rate"), 0.0)),
            "discovered_rate": float(_safe_float((kpi_run.get("rates") or {}).get("discovered_rate"), 0.0)),
            "valid_run": bool(run_validity.get("valid")),
        },
        "analysis_entrypoint": analysis_entrypoint,
        "binary_origin": binary_origin,
        "seeding_mode": seeding_mode,
        "graph_epoch": graph_epoch,
        "bridge_result_fidelity": bridge_fidelity,
        "entity_namespace": entity_namespace,
        "entity_observed_values": entity_observed_values,
        "function_dependencies_declared": function_dependencies_declared,
        "prior_context_size": context_sizes["prior_context_size"],
        "cross_dll_context_size": context_sizes["cross_dll_context_size"],
        "campaign_id": str(session_meta.get("campaign_id") or ""),
        "package_id": str(session_meta.get("package_id") or ""),
        "package_label": str(session_meta.get("package_label") or ""),
        "lane_id": str(session_meta.get("lane_id") or ""),
        "lane_trust_status": str(session_meta.get("lane_trust_status") or ""),
        "selection_reason": str(session_meta.get("selection_reason") or ""),
        "doc_visibility": str(session_meta.get("doc_visibility") or ""),
        "dependency_context": str(session_meta.get("dependency_context") or ""),
        "blocker_family_primary": str(session_meta.get("blocker_family_primary") or ""),
        "blocker_family_secondary": list(session_meta.get("blocker_family_secondary") or []),
        "blocker_confidence": str(session_meta.get("blocker_confidence") or ""),
        "architecture_relevance": str(session_meta.get("architecture_relevance") or ""),
        "runtime_path_trust": str(session_meta.get("runtime_path_trust") or ""),
    }
    content_hash = _hash_payload(core_payload)

    same_run_rows = [row for row in existing_rows if str(row.get("run_id") or "") == run_id]
    if any(str(row.get("content_hash") or "") == content_hash for row in same_run_rows):
        return {
            "ledger_path": str(ledger_path),
            "appended": False,
            "reason": "duplicate_content_hash_noop",
            "run_id": run_id,
        }

    latest_same_run = max(same_run_rows, key=lambda row: int(row.get("capture_seq") or 0), default=None)
    capture_seq = int(latest_same_run.get("capture_seq") or 0) + 1 if latest_same_run else 0
    supersedes = str(latest_same_run.get("row_hash") or "") if latest_same_run else ""

    comparator_rows = [
        row
        for row in existing_rows
        if str(row.get("dll_fingerprint") or "") == dll_fingerprint
        and str(row.get("comparable_profile_key") or "") == comparable_profile_key
        and str(row.get("contract_version") or "") == CONTRACT_VERSION
    ]
    previous = comparator_rows[-1] if comparator_rows else None

    cross_dll_overlap = _compute_cross_dll_entity_overlap(
        entity_namespace, dll_fingerprint, existing_rows, _findings,
    )
    status_counts_for_parity = {
        "verified_rate": core_payload["metrics"]["verified_rate"],
        "discovered_rate": core_payload["metrics"]["discovered_rate"],
        "verified": core_payload["metrics"]["verified_success"],
    }
    parity_delta = _compute_parity_delta(
        dll_fingerprint, cache_state, status_counts_for_parity, existing_rows,
    )

    row = {
        "version": "1.0",
        "recorded_at": str(saved_at or dt.datetime.now(dt.timezone.utc).isoformat()),
        **core_payload,
        "cross_dll_entity_overlap": cross_dll_overlap if any(cross_dll_overlap.values()) else None,
        "parity_delta": parity_delta,
        "capture_seq": capture_seq,
        "supersedes": supersedes or None,
        "content_hash": content_hash,
    }
    row["delta"] = _compute_delta(row, previous)
    row["row_hash"] = _hash_payload({k: v for k, v in row.items() if k != "row_hash"})

    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")

    return {
        "ledger_path": str(ledger_path),
        "appended": True,
        "reason": "ok",
        "run_id": run_id,
        "capture_seq": capture_seq,
        "row_hash": row["row_hash"],
    }


def _build_artifact_index(session_dir: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    total_size = 0

    for path in sorted(session_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(session_dir).as_posix()
        size = _safe_int(path.stat().st_size, 0)
        total_size += size
        files.append(
            {
                "path": rel,
                "size": size,
                "sha256": _sha256_file(path),
            }
        )

    by_hash: dict[str, list[dict[str, Any]]] = {}
    for row in files:
        by_hash.setdefault(str(row["sha256"]), []).append(row)

    canonical_map: list[dict[str, Any]] = []
    for digest, rows in sorted(by_hash.items()):
        ordered = sorted(
            rows,
            key=lambda item: (
                0 if item["path"].startswith("evidence/") else 1,
                0 if not item["path"].startswith("human/") else 1,
                len(item["path"]),
            ),
        )
        canonical = ordered[0]["path"]
        aliases = [row["path"] for row in ordered[1:]]
        canonical_map.append({"sha256": digest, "canonical": canonical, "aliases": aliases})

    return {
        "version": "1.0",
        "policy": "canonical_artifact_plus_alias_index",
        "file_count": len(files),
        "total_size_bytes": total_size,
        "files": files,
        "canonical_map": canonical_map,
    }


def _count_params_from_tool(tool: dict[str, Any]) -> tuple[str, int] | None:
    fn = tool.get("function")
    if isinstance(fn, dict):
        name = str(fn.get("name") or "").strip()
        params = fn.get("parameters")
        count = 0
        if isinstance(params, dict):
            props = params.get("properties")
            if isinstance(props, dict):
                count = len(props)
            elif isinstance(params.get("required"), list):
                count = len(params.get("required") or [])
        elif isinstance(params, list):
            count = len(params)
        if name:
            return name, count
    name = str(tool.get("name") or "").strip()
    if not name:
        return None
    params = tool.get("parameters")
    if isinstance(params, list):
        return name, len(params)
    if isinstance(params, dict):
        props = params.get("properties")
        if isinstance(props, dict):
            return name, len(props)
    return name, 0


def _extract_schema_param_counts(payload: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    if isinstance(payload, dict):
        tools = payload.get("tools")
        if isinstance(tools, list):
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                parsed = _count_params_from_tool(tool)
                if parsed is None:
                    continue
                name, count = parsed
                if str(name or "").strip() in NON_DELIVERABLE_SCHEMA_FUNCTIONS:
                    continue
                counts[name] = max(counts.get(name, 0), count)
            return counts

        # Fallback for invocables-map style payloads
        if all(isinstance(v, dict) for v in payload.values()):
            for name, inv in payload.items():
                if str(name or "").strip() in NON_DELIVERABLE_SCHEMA_FUNCTIONS:
                    continue
                params = inv.get("parameters") if isinstance(inv, dict) else None
                count = len(params) if isinstance(params, list) else 0
                counts[str(name)] = max(counts.get(str(name), 0), count)
            return counts
    return counts


def _build_schema_handoff_audit(session_dir: Path) -> dict[str, Any]:
    stage_skip_reason_map: dict[str, str] = {}
    gap_triggered = False
    stage_index_path = session_dir / "stage-index.json"
    if stage_index_path.exists():
        try:
            payload = _read_json(stage_index_path)
            for row in list((payload or {}).get("stages") or []):
                sid = str((row or {}).get("id") or "").strip()
                if sid:
                    stage_skip_reason_map[sid] = str((row or {}).get("skip_reason") or "").strip()
                    if sid == "S-06":
                        gap_triggered = bool(((row or {}).get("checks") or {}).get("answer_gaps_triggered"))
        except Exception:
            stage_skip_reason_map = {}
            gap_triggered = False

    def _snapshot_owned_by_optional_skip(snap) -> bool:
        for stage_id in tuple(getattr(snap, "owner_stage_ids", ()) or ()):
            stage = next((candidate for candidate in STAGE_CONTRACTS if candidate.id == stage_id), None)
            if stage is None:
                continue
            skip_reason = stage_skip_reason_map.get(stage_id, "")
            floor_broadening_blocked = skip_reason.split(":", 1)[0] == "floor_broadening_blocked"
            if stage_skip_reason_is_allowed(
                stage,
                skip_reason,
                gap_triggered=gap_triggered,
                floor_broadening_blocked=floor_broadening_blocked,
            ):
                return True
        return False

    snapshots: list[dict[str, Any]] = []
    for snap in SCHEMA_HANDOFF_SNAPSHOTS:
        if _snapshot_owned_by_optional_skip(snap):
            continue
        resolved = _resolve_existing_path(session_dir, snap.canonical_path, snap.aliases)
        if not resolved:
            continue
        try:
            payload = _read_json(session_dir / resolved)
        except Exception:
            continue
        fn_counts = _extract_schema_param_counts(payload)
        snapshots.append(
            {
                "path": snap.canonical_path,
                "resolved_path": resolved,
                "function_count": len(fn_counts),
                "with_params_count": sum(1 for n in fn_counts.values() if n > 0),
                "total_param_count": sum(int(n) for n in fn_counts.values()),
                "function_param_counts": fn_counts,
            }
        )

    handoffs: list[dict[str, Any]] = []
    drop_to_zero: list[dict[str, Any]] = []
    silent_function_loss: list[dict[str, Any]] = []
    regression_count = 0
    improvement_count = 0
    for idx in range(1, len(snapshots)):
        prev = snapshots[idx - 1]
        curr = snapshots[idx]
        prev_map = prev.get("function_param_counts") or {}
        curr_map = curr.get("function_param_counts") or {}

        regressions: list[dict[str, Any]] = []
        improvements: list[dict[str, Any]] = []
        unchanged = 0
        for fn, prev_count in prev_map.items():
            if fn not in curr_map:
                row = {"function": fn, "from": int(prev_count or 0), "to": None}
                regressions.append(row)
                silent_function_loss.append(
                    {
                        "function": fn,
                        "from_path": prev["path"],
                        "to_path": curr["path"],
                        "from": int(prev_count or 0),
                        "to": None,
                    }
                )
                continue
            curr_count = int(curr_map.get(fn) or 0)
            prev_count_i = int(prev_count or 0)
            if curr_count < prev_count_i:
                row = {"function": fn, "from": prev_count_i, "to": curr_count}
                regressions.append(row)
                if prev_count_i > 0 and curr_count == 0:
                    drop_to_zero.append(
                        {
                            "function": fn,
                            "from_path": prev["path"],
                            "to_path": curr["path"],
                            "from": prev_count_i,
                            "to": curr_count,
                        }
                    )
            elif curr_count > prev_count_i:
                improvements.append({"function": fn, "from": prev_count_i, "to": curr_count})
            else:
                unchanged += 1

        regression_count += len(regressions)
        improvement_count += len(improvements)
        handoffs.append(
            {
                "from_path": prev["path"],
                "to_path": curr["path"],
                "regressions": regressions,
                "improvements": improvements,
                "unchanged_count": unchanged,
            }
        )

    return {
        "version": "1.0",
        "snapshots": snapshots,
        "handoffs": handoffs,
            "summary": {
                "snapshot_count": len(snapshots),
                "handoff_count": len(handoffs),
                "drop_to_zero_count": len(drop_to_zero),
                "silent_function_loss_count": len(silent_function_loss),
                "regression_count": regression_count,
                "improvement_count": improvement_count,
            },
        "drop_to_zero": drop_to_zero,
        "silent_function_loss": silent_function_loss,
    }


def _build_l1_markdown(kpi_run: dict[str, Any], run_validity: dict[str, Any], contract: ContractResult) -> str:
    totals = kpi_run.get("totals") or {}
    rates = kpi_run.get("rates") or {}

    reason_lines = [f"- {reason}" for reason in (run_validity.get("reasons") or [])]
    if not reason_lines:
        reason_lines = ["- none"]

    lines = [
        "# L1 Executive Summary",
        "",
        f"- Valid run: {run_validity.get('valid', False)}",
        f"- Contract valid: {contract.valid}",
        f"- Hard fail: {contract.hard_fail}",
        f"- Verified: {totals.get('verified_success', 0)}/{totals.get('total_functions', 0)}",
        f"- Discovered: {totals.get('discovered', 0)}/{totals.get('total_functions', 0)}",
        f"- Verified rate: {rates.get('verified_rate', 0.0):.2%}",
        f"- Discovered rate: {rates.get('discovered_rate', 0.0):.2%}",
        f"- Analysis profile: {run_validity.get('profile', 'unknown')}",
        "",
        "## Validity Reasons",
    ]
    lines.extend(reason_lines)
    return "\n".join(lines)


def _build_l2_markdown(kpi_run: dict[str, Any], run_validity: dict[str, Any], status_counts: dict[str, Any]) -> str:
    counts = status_counts.get("counts") or {}
    verification = kpi_run.get("verification") or {}
    gate_results = run_validity.get("gate_results") or {}

    lines = [
        "# L2 Engineering Deltas",
        "",
        "## Status Breakdown",
        f"- verified_success: {counts.get('verified_success', 0)}",
        f"- functional_precondition_unmet: {counts.get('functional_precondition_unmet', 0)}",
        f"- inferred_success: {counts.get('inferred_success', 0)}",
        f"- failure: {counts.get('failure', 0)}",
        f"- unknown: {counts.get('unknown', 0)}",
        "",
        "## Verification",
        f"- verified: {verification.get('verified', 0)}",
        f"- inferred: {verification.get('inferred', 0)}",
        f"- error: {verification.get('error', 0)}",
        "",
        "## Gate Results",
    ]
    for gate, passed in gate_results.items():
        lines.append(f"- {gate}: {bool(passed)}")

    return "\n".join(lines)


def _build_l3_index(kpi_run: dict[str, Any], artifact_index: dict[str, Any], session_dir: Path) -> dict[str, Any]:
    key_artifacts = (
        "cohesion-report.json",
        "stage-index.json",
        "transition-index.json",
        "session-meta.json",
        "stage-00-setup/s01-handoff-packet.json",
        "evidence/stage-00-setup/s01-handoff-packet.json",
        "stage-00-setup/static-enrichment.json",
        "evidence/stage-00-setup/static-enrichment.json",
        "evidence/stage-00a-setup-baseline/sentinel-calibration.json",
        "evidence/stage-00a-setup-baseline/vocab.json",
        "evidence/stage-00b-static-evidence/static-analysis.json",
        "evidence/stage-00b-static-evidence/static-enrichment.json",
        "evidence/stage-00c-admission-handoff/s01-handoff-packet.json",
        "stage-02-synthesis/findings.json",
        "stage-05-finalization/findings.json",
        "evidence/stage-02-probe-loop/probe-log.json",
        "diagnostics/executor_trace.json",
        "schema-handoff-audit.json",
        "stage-handoff-audit.json",
        "transition-contract-audit.json",
        "validation-report.json",
    )
    available = [p for p in key_artifacts if (session_dir / p).exists()]
    return {
        "version": "1.0",
        "job_id": kpi_run.get("job_id"),
        "folder": kpi_run.get("folder"),
        "valid_run": kpi_run.get("valid_run"),
        "key_artifacts": available,
        "artifact_index_ref": "artifact-index.json",
        "status_signature_ref": "kpi_run.json",
        "artifact_count": artifact_index.get("file_count", 0),
    }


def _json_default(value: Any) -> Any:
    return value.__dict__ if hasattr(value, "__dict__") else str(value)


def collect_session(
    session_dir: str | Path,
    mode: str = "strict",
    enforce_hard_fail: bool = False,
    job_id: str = "",
    folder: str = "",
    component: str = "unknown",
    commit: str = "unknown",
    commit_msg: str = "",
    note: str = "",
    date: str = "",
    saved_at: str = "",
    snapshot_profile: str = "full",
) -> int:
    session_dir = Path(session_dir)
    human_dir = session_dir / "human"
    human_dir.mkdir(parents=True, exist_ok=True)

    contract = _validate_contract(session_dir, mode)
    _write_summary(human_dir, contract, mode)

    capture_quality = "complete" if contract.valid else "degraded"

    session_meta = contract.parsed.get("session-meta.json") if contract.parsed else {}
    if not isinstance(session_meta, dict):
        session_meta = {}

    analysis_profile = str(session_meta.get("analysis_profile") or "strict_dll").strip().lower()
    if analysis_profile not in {"strict_dll", "greybox_dll", "full_surface"}:
        analysis_profile = "strict_dll"

    findings = _load_latest_findings(session_dir)
    status_counts = _compute_status_counts(findings, session_meta)

    invocable_count = 0
    inv_map_path = session_dir / "stage-05-finalization" / "invocables_map.json"
    if inv_map_path.exists():
        try:
            inv_map = _read_json(inv_map_path)
            if isinstance(inv_map, dict):
                invocable_count = len(inv_map)
            elif isinstance(inv_map, list):
                invocable_count = len(inv_map)
        except Exception:
            invocable_count = 0
    if invocable_count <= 0:
        invocable_count = _safe_int(session_meta.get("functions_total"), 0)
    if invocable_count <= 0:
        invocable_count = _safe_int(status_counts.get("total"), 0)

    schema_handoff_audit = _build_schema_handoff_audit(session_dir)
    (session_dir / "schema-handoff-audit.json").write_text(
        json.dumps(schema_handoff_audit, indent=2),
        encoding="utf-8",
    )
    stage_handoff_audit = _build_stage_handoff_audit(session_dir)
    (session_dir / "stage-handoff-audit.json").write_text(
        json.dumps(stage_handoff_audit, indent=2),
        encoding="utf-8",
    )
    transition_contract_audit = _build_transition_contract_audit(session_dir)
    (session_dir / "transition-contract-audit.json").write_text(
        json.dumps(transition_contract_audit, indent=2),
        encoding="utf-8",
    )

    run_validity = _build_run_validity(
        contract=contract,
        component=component,
        analysis_profile=analysis_profile,
        status_counts=status_counts,
        invocable_count=invocable_count,
        mode=mode,
        session_dir=session_dir,
        schema_handoff_audit=schema_handoff_audit,
        stage_handoff_audit=stage_handoff_audit,
        transition_contract_audit=transition_contract_audit,
    )

    kpi_run = _build_kpi_run(
        folder=folder,
        job_id=job_id,
        component=component,
        date=date,
        saved_at=saved_at,
        status_counts=status_counts,
        session_meta=session_meta,
        run_validity=run_validity,
    )

    validation_report = emit_validation_report(session_dir)
    artifact_index = _build_artifact_index(session_dir)

    snapshot_profile = str(snapshot_profile or "full").strip().lower()
    if snapshot_profile not in {"full", "compact"}:
        snapshot_profile = "full"

    dashboard_row = _build_dashboard_row(
        contract=contract,
        date=date,
        folder=folder,
        job_id=job_id,
        component=component,
        commit=commit,
        note=note,
        saved_at=saved_at,
        analysis_profile=analysis_profile,
        snapshot_profile=snapshot_profile,
        run_validity=run_validity,
        status_counts=status_counts,
    )

    session_save_meta = _build_session_save_meta(
        contract=contract,
        mode=mode,
        capture_quality=capture_quality,
        job_id=job_id,
        folder=folder,
        commit=commit,
        commit_msg=commit_msg,
        note=note,
        saved_at=saved_at,
        snapshot_profile=snapshot_profile,
        run_validity=run_validity,
        status_counts=status_counts,
    )

    (human_dir / "dashboard-row.json").write_text(
        json.dumps(dashboard_row, indent=2),
        encoding="utf-8",
    )
    (human_dir / "session-save-meta.json").write_text(
        json.dumps(session_save_meta, indent=2),
        encoding="utf-8",
    )

    (session_dir / "run-validity.json").write_text(
        json.dumps(run_validity, indent=2),
        encoding="utf-8",
    )
    (session_dir / "kpi_run.json").write_text(
        json.dumps(kpi_run, indent=2),
        encoding="utf-8",
    )
    (session_dir / "artifact-index.json").write_text(
        json.dumps(artifact_index, indent=2),
        encoding="utf-8",
    )

    (human_dir / "l1-executive.md").write_text(
        _build_l1_markdown(kpi_run, run_validity, contract) + "\n",
        encoding="utf-8",
    )
    (human_dir / "l2-engineering-deltas.md").write_text(
        _build_l2_markdown(kpi_run, run_validity, status_counts) + "\n",
        encoding="utf-8",
    )

    l3_index = _build_l3_index(kpi_run, artifact_index, session_dir)
    (human_dir / "l3-forensics-index.json").write_text(
        json.dumps(l3_index, indent=2),
        encoding="utf-8",
    )

    _vocab_for_ledger: dict[str, Any] = {}
    vocab_path = session_dir / "vocab.json"
    if vocab_path.exists():
        try:
            _vocab_for_ledger = _read_json(vocab_path)
        except Exception:
            pass

    ledger_result: dict[str, Any] | None = None
    try:
        ledger_result = _append_run_ledger(
            session_dir=session_dir,
            job_id=job_id,
            folder=folder,
            component=component,
            commit=commit,
            saved_at=saved_at,
            snapshot_profile=snapshot_profile,
            session_meta=session_meta,
            run_validity=run_validity,
            kpi_run=kpi_run,
            findings=findings,
            vocab=_vocab_for_ledger,
        )
    except Exception as exc:
        ledger_result = {
            "appended": False,
            "reason": f"error:{exc}",
            "run_id": str(folder or job_id or session_dir.name),
        }

    result = CollectResult(
        contract=contract,
        dashboard_row=dashboard_row,
        session_save_meta=session_save_meta,
        run_validity=run_validity,
        kpi_run=kpi_run,
        schema_handoff_audit=schema_handoff_audit,
        stage_handoff_audit=stage_handoff_audit,
        transition_contract_audit=transition_contract_audit,
        validation_report=validation_report,
        artifact_index=artifact_index,
        ledger=ledger_result,
    )
    (human_dir / "collect-session-result.json").write_text(
        json.dumps(result, indent=2, default=_json_default),
        encoding="utf-8",
    )

    if mode == "strict" and (not contract.valid or not bool(run_validity.get("valid"))):
        return 1
    if enforce_hard_fail and contract.valid and contract.hard_fail:
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect and validate session contract artifacts")
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--mode", choices=("strict", "compatibility"), default="strict")
    parser.add_argument("--enforce-hard-fail", action="store_true")
    parser.add_argument("--job-id", default="")
    parser.add_argument("--folder", default="")
    parser.add_argument("--component", default="unknown")
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--commit-msg", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--saved-at", default="")
    parser.add_argument("--snapshot-profile", default="full")
    args = parser.parse_args()

    return collect_session(
        session_dir=args.session_dir,
        mode=args.mode,
        enforce_hard_fail=bool(args.enforce_hard_fail),
        job_id=args.job_id,
        folder=args.folder,
        component=args.component,
        commit=args.commit,
        commit_msg=args.commit_msg,
        note=args.note,
        date=args.date,
        saved_at=args.saved_at,
        snapshot_profile=args.snapshot_profile,
    )


def append_campaign_summary_ledger(
    sessions_root: Path,
    *,
    campaign_id: str,
    dll_fingerprints: list[str],
    contract_version: str,
    analysis_profile: str,
    seeding_mode: str,
    graph_epoch: str,
    per_dll_metrics: list[dict[str, Any]],
    edge_count: int = 0,
    conflict_count: int = 0,
    re_probe_total: int = 0,
) -> dict[str, Any]:
    """Append a campaign-level summary row to the run ledger."""
    import datetime as _dt
    ledger_path = sessions_root / "ledger" / "run_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    sorted_fps = sorted(dll_fingerprints)
    campaign_profile_key = _fingerprint_text(
        f"{','.join(sorted_fps)}|{contract_version}|{analysis_profile}|{seeding_mode}|{graph_epoch}"
    )

    total_verified = sum(m.get("verified_success", 0) for m in per_dll_metrics)
    total_functions = sum(m.get("total_functions", 0) for m in per_dll_metrics)

    row = {
        "version": "1.0",
        "row_type": "campaign_summary",
        "recorded_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "campaign_id": campaign_id,
        "campaign_profile_key": campaign_profile_key,
        "dll_count": len(dll_fingerprints),
        "dll_fingerprints": sorted_fps,
        "contract_version": contract_version,
        "analysis_profile": analysis_profile,
        "seeding_mode": seeding_mode,
        "graph_epoch": graph_epoch,
        "metrics": {
            "total_functions": total_functions,
            "total_verified": total_verified,
            "verified_rate": total_verified / total_functions if total_functions else 0.0,
            "per_dll": per_dll_metrics,
        },
        "edge_count": edge_count,
        "conflict_count": conflict_count,
        "re_probe_total": re_probe_total,
        "schema_version": "1.0.0",
    }
    row["row_hash"] = _hash_payload({k: v for k, v in row.items() if k != "row_hash"})

    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")

    return {
        "ledger_path": str(ledger_path),
        "appended": True,
        "campaign_id": campaign_id,
        "campaign_profile_key": campaign_profile_key,
    }


if __name__ == "__main__":
    raise SystemExit(main())
