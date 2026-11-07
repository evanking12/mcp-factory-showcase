from __future__ import annotations

import argparse
import json
import os
import subprocess
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
    evaluate_lane_trust_output,
    load_gate_config,
)
from scripts.ops.nightly_groundtruth import write_json  # noqa: E402
from scripts.runs.run_spectrum_compiled_easy01 import run_spectrum_compiled_easy01  # noqa: E402
from scripts.runs.run_spectrum_compiled_easy01_product import (  # noqa: E402
    run_spectrum_compiled_easy01_product,
)
from scripts.runs.run_spectrum_compiled_medium01 import run_spectrum_compiled_medium01  # noqa: E402
from scripts.runs.run_spectrum_compiled_medium01_product import (  # noqa: E402
    run_spectrum_compiled_medium01_product,
)
from scripts.runs.run_spectrum_compiled_medium02_product import (  # noqa: E402
    run_spectrum_compiled_medium02_product,
)
from scripts.runs.run_spectrum_compiled_hard01_product import (  # noqa: E402
    run_spectrum_compiled_hard01_product,
)


def _timestamp_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _read_repo_env_value(name: str) -> str:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return ""
    prefix = f"{name}="
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        return stripped[len(prefix):].strip()
    return ""


def _run_lane_validator(
    script_path: Path,
    output_root: Path,
    *,
    no_reload: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-OutputRoot",
        str(output_root),
    ]
    if no_reload:
        command.append("-NoReload")
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _execute_suite(
    *,
    runner: Callable[..., dict[str, Any]],
    case_id: str,
    compare_mode: str,
    baseline_output_root: Path,
    candidate_output_root: Path,
    accepted_additive_invocables: bool,
    summary_case_id: str,
    report_case_id: str,
    required_summary_fields: dict[str, Any],
    required_report_fields: dict[str, Any],
    api_url: str,
    api_key: str,
    bridge_url: str,
    bridge_key: str,
    fail_fast: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "surface": case_id,
        "baseline_output_root": str(baseline_output_root),
        "candidate_output_root": str(candidate_output_root),
    }
    try:
        runner_result = runner(
            api_url=api_url,
            api_key=api_key,
            bridge_url=bridge_url,
            bridge_key=bridge_key,
            output_root=candidate_output_root,
            **(
                {"stop_after_first_failure": True}
                if case_id in {"medium-01", "medium-02", "hard-01"} and fail_fast
                else {}
            ),
        )
        payload["runner_result"] = {
            "output_dir": str(runner_result.get("output_dir") or ""),
        }
        comparison = compare_compiled_suite_to_baseline(
            case_id=case_id,
            baseline_output_root=baseline_output_root,
            candidate_output_root=candidate_output_root,
            accepted_additive_invocables=accepted_additive_invocables,
            summary_case_id=summary_case_id,
            report_case_id=report_case_id,
            required_summary_fields=required_summary_fields,
            required_report_fields=required_report_fields,
        )
        payload["comparison"] = comparison
        payload["verdict"] = comparison["verdict"]
        payload["reasons"] = list(comparison.get("reasons") or [])
        payload["accepted_differences"] = list(comparison.get("accepted_differences") or [])
        payload["compare_mode"] = compare_mode
        return payload
    except Exception as exc:
        payload["runner_exception"] = {
            "type": exc.__class__.__name__,
            "message": str(exc),
        }
        payload["comparison"] = None
        payload["accepted_differences"] = []
        payload["reasons"] = [f"runner_exception:{exc.__class__.__name__}"]
        payload["verdict"] = "fail"
        return payload


def _normalize_requested_surfaces(config: dict[str, Any], raw_value: str) -> list[str]:
    available = ["lane_trust"] + [
        str(item.get("case_id") or "").strip()
        for item in list(config.get("suites") or [])
        if str(item.get("case_id") or "").strip()
    ]
    requested = [
        item.strip()
        for item in str(raw_value or "").split(",")
        if str(item or "").strip()
    ]
    if not requested:
        return available
    unknown = [item for item in requested if item not in available]
    if unknown:
        raise ValueError(f"unknown_surfaces:{','.join(unknown)}")
    return [surface for surface in available if surface in requested]


def run_regression_gate(
    *,
    config_path: Path,
    output_root_arg: str,
    api_url: str,
    api_key: str,
    bridge_url: str,
    bridge_key: str,
    surfaces_arg: str,
    fail_fast: bool,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    config = load_gate_config(config_path, repo_root=REPO_ROOT)
    requested_surfaces = _normalize_requested_surfaces(config, surfaces_arg)
    active_surfaces = list(requested_surfaces)
    resolved_api_key = str(api_key or "").strip() or str(_read_repo_env_value("PIPELINE_API_KEY") or "").strip()
    resolved_bridge_url = str(bridge_url or "").strip() or str(_read_repo_env_value("GUI_BRIDGE_URL") or "").strip()
    resolved_bridge_key = (
        str(bridge_key or "").strip()
        or str(_read_repo_env_value("GUI_BRIDGE_SECRET") or "").strip()
        or str(_read_repo_env_value("BRIDGE_SECRET") or "").strip()
    )
    output_root = (
        Path(output_root_arg)
        if str(output_root_arg or "").strip()
        else REPO_ROOT / "sessions" / "regression_gate" / _timestamp_slug()
    )
    output_root.mkdir(parents=True, exist_ok=True)

    suite_runners: dict[str, Callable[..., dict[str, Any]]] = {
        "easy01_product": run_spectrum_compiled_easy01_product,
        "easy-01": run_spectrum_compiled_easy01,
        "medium01_product": run_spectrum_compiled_medium01_product,
        "medium-01": run_spectrum_compiled_medium01,
        "medium02_product": run_spectrum_compiled_medium02_product,
        "hard01_product": run_spectrum_compiled_hard01_product,
    }
    surface_results: list[dict[str, Any]] = []

    if "lane_trust" in active_surfaces:
        lane_root = output_root / "lane_trust"
        lane_root.mkdir(parents=True, exist_ok=True)
        lane_cfg = dict(config.get("lane_trust") or {})
        product_gate_requested = any(
            str(suite_cfg.get("case_id") or "").strip() in active_surfaces
            and str(suite_cfg.get("runner_id") or suite_cfg.get("case_id") or "").strip().endswith("_product")
            for suite_cfg in list(config.get("suites") or [])
        )
        lane_proc = _run_lane_validator(
            Path(lane_cfg["validator_script_path"]),
            lane_root,
            no_reload=product_gate_requested,
        )
        lane_result = evaluate_lane_trust_output(
            lane_root,
            required_packets=list(lane_cfg.get("required_packets") or []),
            pass_verdict=str(lane_cfg.get("pass_verdict") or "passed"),
        )
        lane_result["no_reload_requested"] = bool(product_gate_requested)
        lane_result["validator_script_path"] = str(lane_cfg["validator_script_path"])
        lane_result["contract_sources"] = list(lane_cfg.get("contract_sources") or [])
        lane_result["validator_exit_code"] = int(lane_proc.returncode)
        lane_result["validator_stdout"] = lane_proc.stdout
        lane_result["validator_stderr"] = lane_proc.stderr
        if lane_proc.returncode != 0 and lane_result["verdict"] != "fail":
            lane_result["verdict"] = "fail"
            lane_result.setdefault("reasons", []).append("lane_validator_nonzero_exit")
        write_json(output_root / "lane-trust-result.json", lane_result)
        surface_results.append(lane_result)
        if fail_fast and lane_result["verdict"] == "fail":
            active_surfaces = ["lane_trust"]

    for suite_cfg in list(config.get("suites") or []):
        case_id = str(suite_cfg.get("case_id") or "").strip()
        if case_id not in active_surfaces:
            continue
        candidate_root = output_root / case_id.replace("-", "")
        candidate_root.mkdir(parents=True, exist_ok=True)
        runner_id = str(suite_cfg.get("runner_id") or case_id).strip()
        runner = suite_runners[runner_id]
        result = _execute_suite(
            runner=runner,
            case_id=case_id,
            compare_mode=str(suite_cfg.get("compare_mode") or "compiled_ingest_report"),
            baseline_output_root=Path(str(suite_cfg["baseline_output_root"])),
            candidate_output_root=candidate_root,
            accepted_additive_invocables=bool(suite_cfg.get("accepted_additive_invocables")),
            summary_case_id=str(suite_cfg.get("summary_case_id") or case_id),
            report_case_id=str(suite_cfg.get("report_case_id") or case_id),
            required_summary_fields=dict(suite_cfg.get("required_summary_fields") or {}),
            required_report_fields=dict(suite_cfg.get("required_report_fields") or {}),
            api_url=str(api_url or "").strip(),
            api_key=resolved_api_key,
            bridge_url=resolved_bridge_url,
            bridge_key=resolved_bridge_key,
            fail_fast=fail_fast,
        )
        write_json(output_root / f"{case_id.replace('-', '')}-result.json", result)
        if case_id == "medium-01":
            checkpoint_report = build_medium01_checkpoint_report(candidate_root)
            checkpoint_path = output_root / "medium01-checkpoints.json"
            write_json(checkpoint_path, checkpoint_report)
            result["checkpoint_report_path"] = str(checkpoint_path)
            result["checkpoint_summary"] = checkpoint_report
            write_json(output_root / "medium01-result.json", result)
        surface_results.append(result)
        if fail_fast and result["verdict"] == "fail":
            break

    executed_surfaces = [str(item.get("surface") or "").strip() for item in surface_results]
    overall_verdict = aggregate_gate_verdict(surface_results)
    summary = {
        "version": "1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "gate_id": str(config.get("gate_id") or ""),
        "config_path": str(config_path),
        "output_root": str(output_root),
        "baseline_policy": "pinned_roots",
        "baseline_registry_path": str(config.get("baseline_registry_path") or ""),
        "requested_surfaces": requested_surfaces,
        "active_surfaces": active_surfaces,
        "executed_surfaces": executed_surfaces,
        "surface_results": surface_results,
        "overall_verdict": overall_verdict,
    }
    verdict = {
        "gate_id": str(config.get("gate_id") or ""),
        "output_root": str(output_root),
        "overall_verdict": overall_verdict,
        "surface_verdicts": {
            str(item.get("surface") or ""): str(item.get("verdict") or "")
            for item in surface_results
        },
        "requested_surfaces": requested_surfaces,
        "active_surfaces": active_surfaces,
        "executed_surfaces": executed_surfaces,
        "baseline_roots": {
            str(item.get("case_id") or ""): str(item.get("baseline_output_root") or "")
            for item in list(config.get("suites") or [])
            if str(item.get("case_id") or "").strip() in executed_surfaces
        },
        "baseline_registry_entries": {
            str(item.get("case_id") or ""): dict(item.get("baseline_registry_entry") or {})
            for item in list(config.get("suites") or [])
            if str(item.get("case_id") or "").strip() in executed_surfaces
        },
        "candidate_roots": {
            str(item.get("surface") or ""): str(item.get("candidate_output_root") or output_root)
            for item in surface_results
        },
    }
    write_json(output_root / "gate-summary.json", summary)
    write_json(output_root / "gate-verdict.json", verdict)
    print(json.dumps(verdict, indent=2))
    return (1 if overall_verdict == "fail" else 0), summary, verdict


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local-first Regression Gate v1.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-root", default="")
    parser.add_argument("--api-url", default=str(os.getenv("MCP_FACTORY_API_URL", "")).strip())
    parser.add_argument("--api-key", default=str(os.getenv("MCP_FACTORY_API_KEY", "")).strip())
    parser.add_argument("--bridge-url", default=str(os.getenv("GUI_BRIDGE_URL", "")).strip())
    parser.add_argument("--bridge-key", default=str(os.getenv("GUI_BRIDGE_SECRET", "")).strip())
    parser.add_argument("--surfaces", default="")
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    exit_code, _, _ = run_regression_gate(
        config_path=args.config,
        output_root_arg=str(args.output_root or ""),
        api_url=str(args.api_url or "").strip(),
        api_key=str(args.api_key or "").strip(),
        bridge_url=str(args.bridge_url or "").strip(),
        bridge_key=str(args.bridge_key or "").strip(),
        surfaces_arg=str(args.surfaces or "").strip(),
        fail_fast=bool(args.fail_fast),
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
