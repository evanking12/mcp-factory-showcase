from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.runtime_contract import local_api_base_url, local_bridge_base_url
from scripts.runs.product_route_trace import append_trace_event, new_trace_id, trace_span

RUNTIME_ROOT = REPO_ROOT / "runtime"

SUITE_RUNNERS: dict[str, Path] = {
    "easy01": REPO_ROOT / "scripts" / "runs" / "run_spectrum_compiled_easy01_product.py",
    "medium01": REPO_ROOT / "scripts" / "runs" / "run_spectrum_compiled_medium01_product.py",
    "medium02": REPO_ROOT / "scripts" / "runs" / "run_spectrum_compiled_medium02_product.py",
    "hard01": REPO_ROOT / "scripts" / "runs" / "run_spectrum_compiled_hard01_product.py",
}


def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def resolve_suite_runner(suite: str) -> Path:
    key = str(suite or "").strip().lower()
    try:
        return SUITE_RUNNERS[key]
    except KeyError as exc:
        raise ValueError(f"unknown_local_product_suite:{suite}") from exc


def default_output_root(suite: str) -> Path:
    return REPO_ROOT / ".tmp" / "local-product-suite" / str(suite).strip().lower() / _timestamp()


def find_python_executable() -> str:
    venv_python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable or "python"


def build_lane_startup_command(*, output_root: Path) -> list[str]:
    return build_lane_startup_command_with_mode(output_root=output_root, no_reload=False)


def build_lane_startup_command_with_mode(*, output_root: Path, no_reload: bool) -> list[str]:
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(RUNTIME_ROOT / "start-managed-lane.ps1"),
        "-OutputRoot",
        str(output_root),
    ]
    if no_reload:
        command.append("-NoReload")
    return command


def build_runner_command(
    *,
    suite: str,
    output_root: Path,
    stop_after_first_failure: bool,
    poll_sec: int,
    analyze_timeout_sec: int,
    explore_timeout_sec: int,
    stuck_seconds: int,
    target_names: str = "",
    prior_job_id: str = "",
    cross_dll_prior_job_ids: str = "",
) -> list[str]:
    command = [
        find_python_executable(),
        str(resolve_suite_runner(suite)),
        "--output-root",
        str(output_root),
        "--api-url",
        local_api_base_url(),
        "--bridge-url",
        local_bridge_base_url(),
        "--poll-sec",
        str(int(poll_sec)),
        "--analyze-timeout-sec",
        str(int(analyze_timeout_sec)),
        "--explore-timeout-sec",
        str(int(explore_timeout_sec)),
        "--stuck-seconds",
        str(int(stuck_seconds)),
    ]
    if stop_after_first_failure:
        command.append("--stop-after-first-failure")
    if str(target_names or "").strip():
        command.extend(["--target-names", str(target_names).strip()])
    if str(prior_job_id or "").strip():
        command.extend(["--prior-job-id", str(prior_job_id).strip()])
    if str(cross_dll_prior_job_ids or "").strip():
        command.extend(["--cross-dll-prior-job-ids", str(cross_dll_prior_job_ids).strip()])
    return command


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.stdout:
        sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    return completed


@contextmanager
def _temporary_env(values: dict[str, str]):
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            os.environ[key] = str(value)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def build_entrypoint_packet(
    *,
    suite: str,
    lane_startup_attempted: bool,
    lane_startup_passed: bool,
    lane_startup_packet_path: str,
    runner_invoked: bool,
    runner_command: list[str],
    runner_output_root: str,
    blocking_signal: str,
    safe_to_compare: bool,
    product_green_eligible: bool,
    runner_exit_code: int | None,
    startup_exit_code: int | None,
    trace_id: str = "",
    trace_path: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "suite": str(suite).strip().lower(),
        "entrypoint": "runtime/run-local-product-suite.ps1",
        "entrypoint_impl": "runtime/run_local_product_suite.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lane_startup_attempted": bool(lane_startup_attempted),
        "lane_startup_passed": bool(lane_startup_passed),
        "lane_startup_packet_path": lane_startup_packet_path,
        "runner_invoked": bool(runner_invoked),
        "runner_command": runner_command,
        "runner_output_root": runner_output_root,
        "api_base_url": local_api_base_url(),
        "bridge_base_url": local_bridge_base_url(),
        "blocking_signal": str(blocking_signal or "").strip(),
        "safe_to_compare": bool(safe_to_compare),
        "product_green_eligible": bool(product_green_eligible),
        "startup_exit_code": startup_exit_code,
        "runner_exit_code": runner_exit_code,
        "trace_id": trace_id,
        "trace_path": trace_path,
        "telemetry_diagnostic_only": True,
    }


def run_local_product_suite(
    *,
    suite: str,
    output_root: Path | None = None,
    stop_after_first_failure: bool = False,
    poll_sec: int = 2,
    analyze_timeout_sec: int = 240,
    explore_timeout_sec: int = 360,
    stuck_seconds: int = 120,
    target_names: str = "",
    prior_job_id: str = "",
    cross_dll_prior_job_ids: str = "",
) -> tuple[int, dict[str, Any], Path]:
    normalized_suite = str(suite or "").strip().lower()
    resolve_suite_runner(normalized_suite)
    resolved_output_root = Path(output_root) if output_root is not None else default_output_root(normalized_suite)
    resolved_output_root.mkdir(parents=True, exist_ok=True)
    entrypoint_packet_path = resolved_output_root / "local-product-suite-entrypoint.json"
    trace_id = new_trace_id()
    trace_path = resolved_output_root / "product-route-trace.jsonl"

    lane_output_root = resolved_output_root / "lane-startup"
    runner_output_root = resolved_output_root / "runner"
    lane_command = build_lane_startup_command_with_mode(
        output_root=lane_output_root,
        no_reload=True,
    )
    entrypoint_span_id = append_trace_event(
        trace_path=trace_path,
        trace_id=trace_id,
        span_name="local_product_suite.entrypoint",
        event_name="start",
        attributes={"suite": normalized_suite},
    )
    entrypoint_started = time.perf_counter()
    with trace_span(
        trace_path=trace_path,
        trace_id=trace_id,
        span_name="local_product_suite.lane_startup",
        attributes={"suite": normalized_suite, "output_root": str(lane_output_root)},
    ):
        startup_completed = _run_command(lane_command)

    lane_packet_path = lane_output_root / "lane-startup.json"
    lane_failure_path = lane_output_root / "lane-startup-failure.json"
    lane_packet = _read_json_if_exists(lane_packet_path)
    lane_failure = _read_json_if_exists(lane_failure_path)
    startup_passed = startup_completed.returncode == 0 and isinstance(lane_packet, dict)
    chosen_lane_packet_path = str(lane_packet_path if startup_passed else lane_failure_path if lane_failure_path.exists() else lane_packet_path)

    if not startup_passed:
        blocking_signal = str((lane_failure or {}).get("failure_kind") or "managed_lane_startup_failed").strip()
        packet = build_entrypoint_packet(
            suite=normalized_suite,
            lane_startup_attempted=True,
            lane_startup_passed=False,
            lane_startup_packet_path=chosen_lane_packet_path,
            runner_invoked=False,
            runner_command=[],
            runner_output_root=str(runner_output_root),
            blocking_signal=blocking_signal,
            safe_to_compare=False,
            product_green_eligible=False,
            runner_exit_code=None,
            startup_exit_code=startup_completed.returncode,
            trace_id=trace_id,
            trace_path=str(trace_path),
        )
        _write_json(entrypoint_packet_path, packet)
        append_trace_event(
            trace_path=trace_path,
            trace_id=trace_id,
            span_name="local_product_suite.entrypoint",
            event_name="end",
            span_id=entrypoint_span_id,
            attributes={
                "suite": normalized_suite,
                "blocking_signal": blocking_signal,
                "runner_exit_code": None,
                "duration_ms": int((time.perf_counter() - entrypoint_started) * 1000),
            },
        )
        return 1, packet, entrypoint_packet_path

    runner_command = build_runner_command(
        suite=normalized_suite,
        output_root=runner_output_root,
        stop_after_first_failure=stop_after_first_failure,
        poll_sec=poll_sec,
        analyze_timeout_sec=analyze_timeout_sec,
        explore_timeout_sec=explore_timeout_sec,
        stuck_seconds=stuck_seconds,
        target_names=target_names,
        prior_job_id=prior_job_id,
        cross_dll_prior_job_ids=cross_dll_prior_job_ids,
    )
    with _temporary_env(
        {
            "MCP_FACTORY_PRODUCT_TRACE_ID": trace_id,
            "MCP_FACTORY_PRODUCT_TRACE_PATH": str(trace_path),
        }
    ):
        with trace_span(
            trace_path=trace_path,
            trace_id=trace_id,
            span_name="local_product_suite.runner",
            attributes={"suite": normalized_suite, "output_root": str(runner_output_root)},
        ):
            runner_completed = _run_command(runner_command)
    summary_path = runner_output_root / "compiled-ingest-summary.json"
    summary = _read_json_if_exists(summary_path) or {}

    blocking_signal = str(summary.get("blocking_signal") or "").strip()
    if not blocking_signal and runner_completed.returncode != 0:
        blocking_signal = "local_product_suite_runner_failed"

    packet = build_entrypoint_packet(
        suite=normalized_suite,
        lane_startup_attempted=True,
        lane_startup_passed=True,
        lane_startup_packet_path=chosen_lane_packet_path,
        runner_invoked=True,
        runner_command=runner_command,
        runner_output_root=str(runner_output_root),
        blocking_signal=blocking_signal,
        safe_to_compare=bool(summary.get("safe_to_compare")),
        product_green_eligible=bool(summary.get("product_green_eligible")),
        runner_exit_code=runner_completed.returncode,
        startup_exit_code=startup_completed.returncode,
        trace_id=trace_id,
        trace_path=str(trace_path),
    )
    append_trace_event(
        trace_path=trace_path,
        trace_id=trace_id,
        span_name="local_product_suite.entrypoint",
        event_name="end",
        span_id=entrypoint_span_id,
        attributes={
            "suite": normalized_suite,
            "blocking_signal": blocking_signal,
            "runner_exit_code": runner_completed.returncode,
            "duration_ms": int((time.perf_counter() - entrypoint_started) * 1000),
        },
    )
    _write_json(entrypoint_packet_path, packet)
    return (0 if runner_completed.returncode == 0 else 1), packet, entrypoint_packet_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ensure the canonical managed local lane exists, then run a product-route suite."
    )
    parser.add_argument("--suite", required=True, choices=sorted(SUITE_RUNNERS))
    parser.add_argument("--output-root", default="")
    parser.add_argument("--stop-after-first-failure", action="store_true")
    parser.add_argument("--poll-sec", type=int, default=2)
    parser.add_argument("--analyze-timeout-sec", type=int, default=240)
    parser.add_argument("--explore-timeout-sec", type=int, default=360)
    parser.add_argument("--stuck-seconds", type=int, default=120)
    parser.add_argument("--target-names", default="")
    parser.add_argument("--prior-job-id", default="")
    parser.add_argument("--cross-dll-prior-job-ids", default="")
    args = parser.parse_args(argv)

    exit_code, packet, packet_path = run_local_product_suite(
        suite=args.suite,
        output_root=Path(args.output_root) if str(args.output_root or "").strip() else None,
        stop_after_first_failure=bool(args.stop_after_first_failure),
        poll_sec=int(args.poll_sec),
        analyze_timeout_sec=int(args.analyze_timeout_sec),
        explore_timeout_sec=int(args.explore_timeout_sec),
        stuck_seconds=int(args.stuck_seconds),
        target_names=str(args.target_names or "").strip(),
        prior_job_id=str(args.prior_job_id or "").strip(),
        cross_dll_prior_job_ids=str(args.cross_dll_prior_job_ids or "").strip(),
    )
    sys.stdout.write(
        json.dumps(
            {
                "entrypoint_packet_path": str(packet_path),
                "suite": packet["suite"],
                "lane_startup_passed": packet["lane_startup_passed"],
                "runner_invoked": packet["runner_invoked"],
                "blocking_signal": packet["blocking_signal"],
                "product_green_eligible": packet["product_green_eligible"],
            },
            indent=2,
        )
        + "\n"
    )
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
