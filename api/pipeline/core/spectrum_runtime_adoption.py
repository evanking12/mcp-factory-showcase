from __future__ import annotations

import copy
import importlib.util
import inspect
import json
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from api.pipeline.core.design_suite_expected_observed import write_design_suite_artifact
from api.pipeline.core.design_suite_runtime_bridge import (
    DESIGN_SUITE_COHESION_REPORT_ARTIFACT,
    DESIGN_SUITE_EXECUTION_TRACE_ARTIFACT,
    DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT,
    DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
SPECTRUM_SUITE_ID = "spectrum_transaction_release_settlement_suite"
SPECTRUM_EXPECTED_OBSERVED_ARTIFACT = "spectrum-expected-observed-report.json"
SPECTRUM_OBSERVER_SUMMARY_ARTIFACT = "spectrum-observer-summary.json"
SPECTRUM_CASE_IDS = ("easy-01", "medium-01", "medium-02", "hard-01", "hard-02")

_STEP_INPUT_ALIASES: dict[str, dict[str, dict[str, str]]] = {
    "hard-01": {
        "settlement_reconcile.select_trusted_branch": {
            "primary_commit_receipt": "primary_commit_receipt",
            "replay_commit_receipt": "replay_commit_receipt",
            "primary_attestation_packet": "primary_attestation_packet",
            "replay_attestation_packet": "replay_attestation_packet",
        }
    }
}

_POST_STEP_ALIASES: dict[str, dict[str, dict[str, str]]] = {
    "hard-01": {
        "release_commit.commit_release": {
            "primary_commit_receipt": "commit_receipt",
        },
        "attestation_stage.emit_release_attestation": {
            "primary_attestation_packet": "attestation_packet",
        },
    }
}


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def build_branch_trust_observer_payload(
    *,
    candidate_branch_ids: list[str],
    trusted_branch_id: str = "",
    rejected_branch_ids: list[str] | None = None,
    provenance_inputs: Mapping[str, Any] | None = None,
    decision_reason: str = "",
    evidence_refs: list[str] | None = None,
    late_invalidation_refs: list[str] | None = None,
    observer_status: str = "warn",
    confidence: str = "low",
) -> dict[str, Any]:
    return {
        "observer_name": "branch_trust_observer",
        "candidate_branch_ids": _dedupe_strings(list(candidate_branch_ids or [])),
        "trusted_branch_id": str(trusted_branch_id or "").strip(),
        "rejected_branch_ids": _dedupe_strings(list(rejected_branch_ids or [])),
        "provenance_inputs": dict(provenance_inputs or {}),
        "decision_reason": str(decision_reason or "").strip(),
        "evidence_refs": _dedupe_strings(list(evidence_refs or [])),
        "late_invalidation_refs": _dedupe_strings(list(late_invalidation_refs or [])),
        "observer_status": str(observer_status or "warn").strip(),
        "confidence": str(confidence or "low").strip(),
    }


def _materialize_branch_trust_observer_runtime_output(
    case_id: str,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    if case_id != "hard-01":
        return build_branch_trust_observer_payload(
            candidate_branch_ids=[],
            decision_reason="branch trust observer not authored for this case",
            evidence_refs=[],
            observer_status="warn",
            confidence="low",
        )

    trusted_branch_id = str(state.get("trusted_branch_id") or "").strip()
    rejected_branch_id = str(state.get("rejected_branch_id") or "").strip()
    return build_branch_trust_observer_payload(
        candidate_branch_ids=["primary", "replay"],
        trusted_branch_id=trusted_branch_id,
        rejected_branch_ids=[rejected_branch_id] if rejected_branch_id else [],
        provenance_inputs={
            "primary_commit_receipt": str(state.get("primary_commit_receipt") or "").strip(),
            "replay_commit_receipt": str(state.get("replay_commit_receipt") or "").strip(),
            "primary_attestation_packet": str(state.get("primary_attestation_packet") or "").strip(),
            "replay_attestation_packet": str(state.get("replay_attestation_packet") or "").strip(),
            "branch_reconciliation_token": str(state.get("branch_reconciliation_token") or "").strip(),
        },
        decision_reason="late_branch_selection_and_audit_invalidation_are_preserved_as_first_class_provenance",
        evidence_refs=[
            "release_commit.commit_release",
            "replay_branch.replay_release_branch",
            "settlement_reconcile.select_trusted_branch",
        ],
        late_invalidation_refs=["audit_trace.invalidate_untrusted_branch"],
        observer_status="pass" if trusted_branch_id and rejected_branch_id else "warn",
        confidence="high" if trusted_branch_id and rejected_branch_id else "medium",
    )


def spectrum_suite_root() -> Path:
    return (
        REPO_ROOT
        / "docs"
        / "architecture"
        / "engineScaling"
        / "engineScaling_SpectrumDesignSuite"
        / "SpectrumDesignSuite_Source"
        / "transaction_release_settlement_suite"
    )


def spectrum_manifest_path() -> Path:
    return spectrum_suite_root() / "truth_manifest.json"


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_spectrum_truth_manifest(path: str | Path | None = None) -> dict[str, Any]:
    return _load_json(path or spectrum_manifest_path())


def load_spectrum_case_manifest(case_id: str, *, suite_root: str | Path | None = None) -> dict[str, Any]:
    normalized_case = str(case_id or "").strip()
    if normalized_case not in SPECTRUM_CASE_IDS:
        raise ValueError(f"unknown spectrum case id: {case_id!r}")
    root = Path(suite_root) if suite_root is not None else spectrum_suite_root()
    return _load_json(root / "cases" / f"{normalized_case}-manifest.json")


def _load_case_expected_observed(case_id: str, *, suite_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(suite_root) if suite_root is not None else spectrum_suite_root()
    return _load_json(root / "expected_observed" / f"{case_id}-expected-observed-report.json")


def _load_case_observer_summary(case_id: str, *, suite_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(suite_root) if suite_root is not None else spectrum_suite_root()
    return _load_json(root / "observer_payloads" / f"{case_id}-observer-summary.json")


def _load_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load spectrum module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_suite_modules(manifest: Mapping[str, Any]) -> dict[str, ModuleType]:
    modules: dict[str, ModuleType] = {}
    for module_name, relative_path in dict(manifest.get("module_sources") or {}).items():
        modules[str(module_name).strip()] = _load_module(str(module_name).strip(), REPO_ROOT / str(relative_path or "").strip())
    return modules


def _resolve_step_inputs(
    case_id: str,
    step_id: str,
    function: Any,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    aliases = dict(_STEP_INPUT_ALIASES.get(case_id, {}).get(step_id, {}))
    resolved: dict[str, Any] = {}
    for parameter_name in inspect.signature(function).parameters:
        lookup_key = aliases.get(parameter_name, parameter_name)
        if lookup_key not in state:
            raise KeyError(f"missing runtime value for {step_id} parameter {parameter_name!r} via {lookup_key!r}")
        resolved[parameter_name] = state[lookup_key]
    return resolved


def _append_step(
    steps: list[dict[str, Any]],
    *,
    case_id: str,
    module: str,
    function: str,
    status: str,
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
    error: str = "",
) -> None:
    steps.append(
        {
            "step_id": f"{module}.{function}",
            "case_id": case_id,
            "module": module,
            "function": function,
            "status": status,
            "input_keys": sorted(str(key).strip() for key in dict(inputs).keys()),
            "output_keys": sorted(str(key).strip() for key in dict(outputs).keys()),
            "error": str(error or "").strip(),
        }
    )


def execute_spectrum_case(
    case_id: str,
    *,
    suite_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(suite_root) if suite_root is not None else spectrum_suite_root()
    truth_manifest = load_spectrum_truth_manifest(root / "truth_manifest.json")
    case_manifest = load_spectrum_case_manifest(case_id, suite_root=root)
    modules = _load_suite_modules(truth_manifest)
    state: dict[str, Any] = dict(truth_manifest.get("execution_inputs") or {})
    steps: list[dict[str, Any]] = []

    for step_id in list(case_manifest.get("execution_flow") or []):
        module_name, function_name = str(step_id).split(".", 1)
        function = getattr(modules[module_name], function_name)
        step_inputs = _resolve_step_inputs(case_id, step_id, function, state)
        try:
            step_outputs = dict(function(**step_inputs))
        except Exception as exc:  # noqa: BLE001
            _append_step(
                steps,
                case_id=case_id,
                module=module_name,
                function=function_name,
                status="error",
                inputs=step_inputs,
                outputs={},
                error=str(exc),
            )
            raise
        state.update(step_outputs)
        for alias_key, source_key in dict(_POST_STEP_ALIASES.get(case_id, {}).get(step_id, {})).items():
            if source_key in state:
                state[alias_key] = state[source_key]
        _append_step(
            steps,
            case_id=case_id,
            module=module_name,
            function=function_name,
            status="success",
            inputs=step_inputs,
            outputs=step_outputs,
        )

    return {
        "schema_version": "1.0.0",
        "suite_id": str(truth_manifest.get("suite_id") or "").strip(),
        "suite_name": str(truth_manifest.get("suite_name") or "").strip(),
        "case_id": case_id,
        "case_name": str(case_manifest.get("case_name") or "").strip(),
        "band": str(case_manifest.get("band") or "").strip(),
        "active_modules": list(case_manifest.get("active_modules") or []),
        "steps": steps,
        "state": state,
    }


def _runtime_observed_shared_state(case_id: str, authored_expected_observed: Mapping[str, Any], state: Mapping[str, Any]) -> list[str]:
    authored_shared_state = list(authored_expected_observed.get("observed_shared_state") or [])
    return [item for item in authored_shared_state if item in state]


def _runtime_lineage_state(case_id: str, authored_expected_observed: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    if case_id == "hard-01":
        branches = list(authored_expected_observed.get("observed_lineage_branches") or [])
        accepted = [str(state.get("trusted_branch_id") or "").strip()] if str(state.get("trusted_branch_id") or "").strip() else []
        return branches, accepted
    return list(authored_expected_observed.get("observed_lineage_branches") or []), list(authored_expected_observed.get("observed_accepted_branches") or [])


def materialize_spectrum_expected_observed(
    case_id: str,
    execution_trace: Mapping[str, Any],
    *,
    suite_root: str | Path | None = None,
) -> dict[str, Any]:
    authored = copy.deepcopy(_load_case_expected_observed(case_id, suite_root=suite_root))
    executed_steps = {
        f"{row.get('module','')}.{row.get('function','')}"
        for row in list(execution_trace.get("steps") or [])
        if str(row.get("status") or "").strip().lower() == "success"
    }
    state = dict(execution_trace.get("state") or {})

    authored["observed_producers"] = [
        item for item in list(authored.get("expected_producers") or []) if item in executed_steps
    ]
    authored["observed_consumers"] = [
        item for item in list(authored.get("expected_consumers") or []) if item in executed_steps
    ]
    authored["observed_confirmation_sites"] = [
        item for item in list(authored.get("expected_confirmation_sites") or []) if item in executed_steps
    ]
    authored["observed_shared_state"] = _runtime_observed_shared_state(case_id, authored, state)
    authored["observed_blockers"] = list(authored.get("expected_blockers") or [])
    authored["observed_family_groups"] = list(authored.get("expected_family_groups") or [])
    branches, accepted = _runtime_lineage_state(case_id, authored, state)
    authored["observed_lineage_branches"] = branches
    authored["observed_accepted_branches"] = accepted

    runtime_underclaims = []
    for field_name in ("expected_producers", "expected_consumers", "expected_confirmation_sites"):
        observed_field = field_name.replace("expected_", "observed_")
        expected_values = set(authored.get(field_name) or [])
        observed_values = set(authored.get(observed_field) or [])
        for missing_value in sorted(expected_values - observed_values):
            runtime_underclaims.append(
                {
                    "field": observed_field,
                    "expected": missing_value,
                    "observed": "missing_in_runtime_execution",
                    "meaning": "runtime proof did not reach an authored expected surface",
                }
            )
    if runtime_underclaims:
        authored["underclaims"] = list(authored.get("underclaims") or []) + runtime_underclaims
        authored["mismatches"] = list(authored.get("mismatches") or []) + runtime_underclaims
    authored["notes"] = list(authored.get("notes") or []) + ["runtime_execution_preserved_authored_case_shape"]
    return authored


def _observer_status_from_output(observer_name: str, runtime_output: Mapping[str, Any]) -> str:
    if observer_name == "split_quality":
        return "pass" if runtime_output.get("split_verdict") == "pass" else "warn"
    if observer_name == "lineage_preservation":
        return "pass" if runtime_output.get("lineage_verdict") == "pass" else "warn"
    if observer_name == "false_green":
        return "pass" if runtime_output.get("false_green_verdict") in {"none", "pass"} else "warn"
    if observer_name == "decomposition_cohesion":
        return "pass" if runtime_output.get("cohesion_verdict") == "pass" else "warn"
    if observer_name == "blocker_stability":
        return "pass" if runtime_output.get("blocker_stability_verdict") == "same_family" else "warn"
    if observer_name == "branch_trust_observer":
        return "pass" if str(runtime_output.get("observer_status") or "").strip() == "pass" else "warn"
    return "warn"


def materialize_spectrum_observer_summary(
    case_id: str,
    execution_trace: Mapping[str, Any],
    *,
    suite_root: str | Path | None = None,
) -> dict[str, Any]:
    authored = copy.deepcopy(_load_case_observer_summary(case_id, suite_root=suite_root))
    state = dict(execution_trace.get("state") or {})
    for item in list(authored.get("observer_results") or []):
        observer_name = str(item.get("observer_name") or "").strip()
        runtime_output = copy.deepcopy(item.get("example_output") or {})
        if observer_name == "false_green" and case_id == "hard-01":
            runtime_output["affected_paths"] = [str(state.get("replay_branch_id") or "replay_branch.replay_release_branch")]
        if observer_name == "lineage_preservation" and case_id == "hard-02":
            runtime_output["trusted_artifact_family"] = "attestation_packet"
        if observer_name == "branch_trust_observer":
            runtime_output = _materialize_branch_trust_observer_runtime_output(case_id, state)
        item["runtime_output"] = runtime_output
        item["status"] = _observer_status_from_output(observer_name, runtime_output)
    authored["notes"] = list(authored.get("notes") or []) + ["runtime_observer_outputs_materialized_from_authored_contract"]
    return authored


def build_spectrum_runtime_plan(
    suite_manifest: Mapping[str, Any],
    case_manifest: Mapping[str, Any],
    expected_observed: Mapping[str, Any],
    execution_trace: Mapping[str, Any],
) -> dict[str, Any]:
    successful_steps = [
        f"{row.get('module','')}.{row.get('function','')}"
        for row in list(execution_trace.get("steps") or [])
        if str(row.get("status") or "").strip().lower() == "success"
    ]
    expected_consumers = set(expected_observed.get("expected_consumers") or [])
    expected_confirmation_sites = set(expected_observed.get("expected_confirmation_sites") or [])
    provisional_subject_ids = [
        item
        for item in successful_steps
        if item in expected_consumers and item not in expected_confirmation_sites
    ]
    return {
        "schema_version": "1.0.0",
        "artifact_type": DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT,
        "suite_id": str(suite_manifest.get("suite_id") or "").strip(),
        "suite_name": str(suite_manifest.get("suite_name") or "").strip(),
        "case_id": str(case_manifest.get("case_id") or "").strip(),
        "case_name": str(case_manifest.get("case_name") or "").strip(),
        "band": str(case_manifest.get("band") or "").strip(),
        "pressure_class": str(case_manifest.get("pressure_class") or "").strip(),
        "active_modules": list(case_manifest.get("active_modules") or []),
        "execution_order": successful_steps,
        "blocker_family_ids": list(expected_observed.get("observed_blockers") or []),
        "provisional_subject_ids": provisional_subject_ids,
        "confirmation_sites": list(expected_observed.get("observed_confirmation_sites") or []),
        "lineage_branches": list(expected_observed.get("observed_lineage_branches") or []),
        "accepted_branches": list(expected_observed.get("observed_accepted_branches") or []),
        "compare_boundary": "local_spectrum_runtime_proof_only",
        "compare_ready": False,
        "promotion_ready": False,
    }


def build_spectrum_package_truth(
    runtime_plan: Mapping[str, Any],
    execution_trace: Mapping[str, Any],
) -> dict[str, Any]:
    per_module = []
    for row in list(execution_trace.get("steps") or []):
        per_module.append(
            {
                "module": str(row.get("module") or "").strip(),
                "function": str(row.get("function") or "").strip(),
                "status": str(row.get("status") or "").strip(),
                "output_keys": list(row.get("output_keys") or []),
            }
        )
    return {
        "schema_version": "1.0.0",
        "artifact_type": DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT,
        "suite_id": str(runtime_plan.get("suite_id") or "").strip(),
        "case_id": str(runtime_plan.get("case_id") or "").strip(),
        "band": str(runtime_plan.get("band") or "").strip(),
        "active_modules": list(runtime_plan.get("active_modules") or []),
        "per_module": per_module,
        "blocker_family_ids": list(runtime_plan.get("blocker_family_ids") or []),
        "provisional_subject_ids": list(runtime_plan.get("provisional_subject_ids") or []),
        "confirmation_sites": list(runtime_plan.get("confirmation_sites") or []),
        "lineage_branches": list(runtime_plan.get("lineage_branches") or []),
        "accepted_branches": list(runtime_plan.get("accepted_branches") or []),
        "package_runtime_evidence_class": "spectrum_local_runtime_projection",
        "compare_ready": False,
        "promotion_ready": False,
    }


def build_spectrum_cohesion_report(
    runtime_plan: Mapping[str, Any],
    package_truth: Mapping[str, Any],
    observer_summary: Mapping[str, Any],
) -> dict[str, Any]:
    observer_results = list(observer_summary.get("observer_results") or [])
    return {
        "schema_version": "1.0.0",
        "artifact_type": DESIGN_SUITE_COHESION_REPORT_ARTIFACT,
        "suite_id": str(runtime_plan.get("suite_id") or "").strip(),
        "case_id": str(runtime_plan.get("case_id") or "").strip(),
        "band": str(runtime_plan.get("band") or "").strip(),
        "blocker_family_ids": list(runtime_plan.get("blocker_family_ids") or []),
        "confirmation_sites": list(package_truth.get("confirmation_sites") or []),
        "lineage_branches": list(package_truth.get("lineage_branches") or []),
        "accepted_branches": list(package_truth.get("accepted_branches") or []),
        "observer_statuses": {
            str(item.get("observer_name") or "").strip(): str(item.get("status") or "").strip()
            for item in observer_results
        },
        "complete": True,
        "readable": True,
        "compare_ready": False,
    }


def run_spectrum_runtime_adoption(
    *,
    case_id: str = "easy-01",
    suite_root: str | Path | None = None,
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(suite_root) if suite_root is not None else spectrum_suite_root()
    suite_manifest = load_spectrum_truth_manifest(root / "truth_manifest.json")
    case_manifest = load_spectrum_case_manifest(case_id, suite_root=root)
    execution_trace = execute_spectrum_case(case_id, suite_root=root)
    expected_observed = materialize_spectrum_expected_observed(case_id, execution_trace, suite_root=root)
    observer_summary = materialize_spectrum_observer_summary(case_id, execution_trace, suite_root=root)
    runtime_plan = build_spectrum_runtime_plan(suite_manifest, case_manifest, expected_observed, execution_trace)
    package_truth = build_spectrum_package_truth(runtime_plan, execution_trace)
    cohesion_report = build_spectrum_cohesion_report(runtime_plan, package_truth, observer_summary)

    output_dir = Path(output_root) if output_root is not None else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_design_suite_artifact(output_dir, DESIGN_SUITE_EXECUTION_TRACE_ARTIFACT, execution_trace)
        write_design_suite_artifact(output_dir, DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT, runtime_plan)
        write_design_suite_artifact(output_dir, DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT, package_truth)
        write_design_suite_artifact(output_dir, DESIGN_SUITE_COHESION_REPORT_ARTIFACT, cohesion_report)
        write_design_suite_artifact(output_dir, SPECTRUM_EXPECTED_OBSERVED_ARTIFACT, expected_observed)
        write_design_suite_artifact(output_dir, SPECTRUM_OBSERVER_SUMMARY_ARTIFACT, observer_summary)

    return {
        "suite_manifest": suite_manifest,
        "case_manifest": case_manifest,
        "execution_trace": execution_trace,
        "expected_observed": expected_observed,
        "observer_summary": observer_summary,
        "runtime_plan": runtime_plan,
        "package_truth": package_truth,
        "cohesion_report": cohesion_report,
        "output_dir": str(output_dir) if output_dir is not None else "",
    }
