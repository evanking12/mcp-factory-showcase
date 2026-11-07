from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.design_suite_expected_observed import (  # noqa: E402
    load_design_suite_manifest,
    run_northstar_first_slice,
    write_design_suite_artifact,
)
from api.pipeline.core.design_suite_runtime_bridge import (  # noqa: E402
    DESIGN_SUITE_COHESION_REPORT_ARTIFACT,
    DESIGN_SUITE_EXECUTION_TRACE_ARTIFACT,
    DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT,
    DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT,
    build_design_suite_cohesion_report,
    build_design_suite_package_truth,
    build_design_suite_runtime_projection,
    resolve_design_suite_pressure_mode,
)
from api.pipeline.core.design_suite_taxonomy import DEFAULT_NORTHSTAR_CONTRACT  # noqa: E402


def _load_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load design-suite module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _suite_root_for_name(suite_name: str) -> Path:
    return REPO_ROOT / "tests" / "fixtures" / "design_suite" / suite_name


def _load_suite_modules(manifest: dict[str, Any]) -> dict[str, ModuleType]:
    modules: dict[str, ModuleType] = {}
    for module_name, relative_path in dict(manifest.get("module_sources") or {}).items():
        path = REPO_ROOT / str(relative_path or "").strip()
        modules[str(module_name).strip()] = _load_module(str(module_name).strip(), path)
    return modules


def _append_step(
    steps: list[dict[str, Any]],
    *,
    module: str,
    function: str,
    status: str,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    branch: str = "",
    error: str = "",
) -> None:
    steps.append(
        {
            "step_id": f"{module}.{function}" + (f":{branch}" if branch else ""),
            "module": module,
            "function": function,
            "status": status,
            "branch": branch,
            "input_keys": sorted(str(key).strip() for key in dict(inputs or {}).keys()),
            "output_keys": sorted(str(key).strip() for key in dict(outputs or {}).keys()),
            "error": str(error or "").strip(),
        }
    )


def _run_northstar_execution(
    *,
    manifest: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    normalized_mode = resolve_design_suite_pressure_mode(mode)
    modules = _load_suite_modules(manifest)
    inputs = dict(manifest.get("execution_inputs") or {})
    customer_id = str(inputs.get("customer_id") or "").strip()
    sku = str(inputs.get("sku") or "").strip()
    amount_cents = int(inputs.get("amount_cents") or 0)

    steps: list[dict[str, Any]] = []
    session_output = modules["session"].bootstrap_session(customer_id)
    _append_step(
        steps,
        module="session",
        function="bootstrap_session",
        status="success",
        inputs={"customer_id": customer_id},
        outputs=session_output,
    )

    inventory_output = modules["inventory"].reserve_item(session_output["session_token"], sku)
    _append_step(
        steps,
        module="inventory",
        function="reserve_item",
        status="success",
        inputs={"session_token": session_output["session_token"], "sku": sku},
        outputs=inventory_output,
    )

    billing_output = modules["billing"].authorize_charge(
        session_output["session_token"],
        session_output["sequence_nonce"],
        amount_cents,
    )
    _append_step(
        steps,
        module="billing",
        function="authorize_charge",
        status="success",
        inputs={
            "session_token": session_output["session_token"],
            "sequence_nonce": session_output["sequence_nonce"],
            "amount_cents": amount_cents,
        },
        outputs=billing_output,
    )

    active_modules = ["session", "inventory", "billing"]
    if normalized_mode != "base":
        active_modules.append("audit")

    forked_state = {"accepted": [], "rejected": []}
    if normalized_mode in {"overlap", "late_confirmation"}:
        audit_output = modules["audit"].commit_receipt(
            session_output["session_token"],
            billing_output["authorization_receipt"],
            inventory_output["reservation_id"],
        )
        _append_step(
            steps,
            module="audit",
            function="commit_receipt",
            status="success",
            inputs={
                "session_token": session_output["session_token"],
                "authorization_receipt": billing_output["authorization_receipt"],
                "reservation_id": inventory_output["reservation_id"],
            },
            outputs=audit_output,
        )
    elif normalized_mode == "forked_state":
        for branch_name in ("authorization_receipt_primary", "authorization_receipt_shadow"):
            try:
                audit_output = modules["audit"].commit_receipt(
                    session_output["session_token"],
                    billing_output[branch_name],
                    inventory_output["reservation_id"],
                )
                _append_step(
                    steps,
                    module="audit",
                    function="commit_receipt",
                    status="success",
                    inputs={
                        "session_token": session_output["session_token"],
                        "authorization_receipt": billing_output[branch_name],
                        "reservation_id": inventory_output["reservation_id"],
                    },
                    outputs=audit_output,
                    branch=branch_name,
                )
                forked_state["accepted"].append(branch_name)
            except Exception as exc:  # noqa: BLE001
                _append_step(
                    steps,
                    module="audit",
                    function="commit_receipt",
                    status="rejected",
                    inputs={
                        "session_token": session_output["session_token"],
                        "authorization_receipt": billing_output[branch_name],
                        "reservation_id": inventory_output["reservation_id"],
                    },
                    outputs={},
                    branch=branch_name,
                    error=str(exc),
                )
                forked_state["rejected"].append(branch_name)

    return {
        "schema_version": "1.0.0",
        "suite_id": str(manifest.get("suite_id") or "").strip(),
        "pressure_mode": normalized_mode,
        "active_modules": active_modules,
        "steps": steps,
        "forked_state": forked_state,
    }


def run_design_suite_runtime_adoption(
    *,
    suite: str = "northstar_transaction_suite",
    mode: str = "base",
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    normalized_mode = resolve_design_suite_pressure_mode(mode)
    suite_root = _suite_root_for_name(suite)
    manifest_path = suite_root / "truth_manifest.json"
    manifest = load_design_suite_manifest(manifest_path)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = (
        Path(output_root)
        if output_root is not None
        else REPO_ROOT / "sessions" / "design_suite" / "runtime_adoption" / suite / timestamp
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    observed_bundle = run_northstar_first_slice(manifest_path, output_dir=output_dir, mode=normalized_mode)
    execution_trace = _run_northstar_execution(manifest=manifest, mode=normalized_mode)
    runtime_projection = build_design_suite_runtime_projection(
        DEFAULT_NORTHSTAR_CONTRACT.to_dict(),
        manifest,
        observed_bundle,
        execution_trace,
        normalized_mode,
    )
    package_truth = build_design_suite_package_truth(runtime_projection, execution_trace)
    cohesion_report = build_design_suite_cohesion_report(runtime_projection, package_truth)

    write_design_suite_artifact(output_dir, DESIGN_SUITE_EXECUTION_TRACE_ARTIFACT, execution_trace)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_RUNTIME_PLAN_ARTIFACT, runtime_projection)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_PACKAGE_TRUTH_ARTIFACT, package_truth)
    write_design_suite_artifact(output_dir, DESIGN_SUITE_COHESION_REPORT_ARTIFACT, cohesion_report)

    return {
        "output_dir": str(output_dir),
        "pressure_mode": normalized_mode,
        "runtime_projection": runtime_projection,
        "package_truth": package_truth,
        "cohesion_report": cohesion_report,
        "execution_trace": execution_trace,
        "observed_bundle": observed_bundle,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local design-suite runtime/package adoption.")
    parser.add_argument("--suite", default="northstar_transaction_suite")
    parser.add_argument("--mode", default="base")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    result = run_design_suite_runtime_adoption(
        suite=str(args.suite or "").strip(),
        mode=str(args.mode or "").strip(),
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
    )
    print(json.dumps({"output_dir": result["output_dir"], "pressure_mode": result["pressure_mode"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
