from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from harness_lib import collector
from harness_lib.capture import run_capture


REPO_ROOT = Path(__file__).resolve().parents[1]


def _python_exe() -> str:
    venv_py = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable or "python"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _run_subprocess(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
    return int(proc.returncode)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _build_runner_from_config(
    config: dict[str, Any],
    profile_override: str = "",
) -> tuple[str, list[str]]:
    campaign = config.get("campaign") if isinstance(config.get("campaign"), dict) else {}
    api = config.get("api") if isinstance(config.get("api"), dict) else {}
    bridge = config.get("bridge") if isinstance(config.get("bridge"), dict) else {}
    targets = config.get("targets") if isinstance(config.get("targets"), dict) else {}
    explore_defaults = (
        config.get("explore_defaults")
        if isinstance(config.get("explore_defaults"), dict)
        else {}
    )
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}

    profile = (
        profile_override
        or str(campaign.get("mode") or campaign.get("type") or "nightly").strip().lower()
    )

    args: list[str] = []
    api_url = str(api.get("url") or "").strip()
    api_key = str(api.get("key") or "").strip()
    bridge_url = str(bridge.get("url") or "").strip()
    bridge_key = str(bridge.get("key") or "").strip()
    analysis_profile = str(
        explore_defaults.get("analysis_profile")
        or execution.get("analysis_profile")
        or "strict_dll"
    ).strip()
    snapshot_profile = str(
        execution.get("snapshot_profile")
        or (config.get("capture") or {}).get("snapshot_profile")
        or "full"
    ).strip()
    model = str(
        explore_defaults.get("model")
        or execution.get("model")
        or "gpt-4o"
    ).strip()
    target_values = targets.get("names") or targets.get("targets") or []
    if isinstance(target_values, str):
        target_csv = target_values
    elif isinstance(target_values, list):
        target_csv = ",".join(str(x) for x in target_values if str(x).strip())
    else:
        target_csv = ""

    if profile == "nightly":
        args.extend(["--hours", str(campaign.get("hours", 8.0))])
        args.extend(["--max-runs", str(campaign.get("max_runs", 20))])
        if api_url:
            args.extend(["--api-url", api_url])
        if api_key:
            args.extend(["--api-key", api_key])
        if bridge_url:
            args.extend(["--bridge-url", bridge_url])
        if bridge_key:
            args.extend(["--bridge-key", bridge_key])
        args.extend(["--analysis-profile", analysis_profile])
        args.extend(["--snapshot-profile", snapshot_profile])
        if target_csv:
            args.extend(["--targets", target_csv])
        script = REPO_ROOT / "scripts" / "ops" / "nightly_groundtruth.py"
        return str(script), args

    if profile == "ab":
        if api_url:
            args.extend(["--api-url", api_url])
        if api_key:
            args.extend(["--api-key", api_key])
        dll = str(targets.get("dll") or "tests/fixtures/contoso_legacy/contoso_cs.dll")
        hints_file = str(targets.get("hints_file") or "sessions/contoso_cs/contoso_cs.txt")
        args.extend(["--dll", dll, "--hints-file", hints_file])
        args.extend(["--mode", str(execution.get("mode") or "dev")])
        args.extend(["--model", model])
        args.extend(["--max-rounds", str(execution.get("max_rounds", 2))])
        args.extend(["--max-tool-calls", str(execution.get("max_tool_calls", 5))])
        script = REPO_ROOT / "scripts" / "runs" / "run_ab_parallel.py"
        return str(script), args

    if profile == "batch":
        if api_url:
            args.extend(["--api-url", api_url])
        if api_key:
            args.extend(["--api-key", api_key])
        dll = str(targets.get("dll") or "tests/fixtures/contoso_legacy/contoso_cs.dll")
        hints_file = str(targets.get("hints_file") or "sessions/contoso_cs/contoso_cs.txt")
        args.extend(["--dll", dll, "--hints-file", hints_file])
        args.extend(["--mode", str(execution.get("mode") or "dev")])
        args.extend(["--model", model])
        args.extend(["--max-rounds", str(execution.get("max_rounds", 2))])
        args.extend(["--max-tool-calls", str(execution.get("max_tool_calls", 5))])
        args.extend(["--runs", str(campaign.get("runs", campaign.get("max_runs", 4)))])
        args.extend(["--max-parallel", str(campaign.get("max_parallel", 4))])
        script = REPO_ROOT / "scripts" / "runs" / "run_batch_parallel.py"
        return str(script), args

    if profile == "matrix":
        if api_url:
            args.extend(["--api-url", api_url])
        if api_key:
            args.extend(["--api-key", api_key])
        args.extend(["--model", model])
        args.extend(["--max-workers", str(campaign.get("max_workers", 4))])
        max_cases = campaign.get("max_cases")
        if max_cases is not None:
            args.extend(["--max-cases", str(max_cases)])
        script = REPO_ROOT / "scripts" / "runs" / "run_transition_isolation_matrix.py"
        return str(script), args

    if profile == "set":
        run_set_def = str(campaign.get("run_set_def") or "")
        if not run_set_def:
            raise ValueError("campaign.run_set_def is required for profile=set")
        args.extend(["--run-set-def", run_set_def])
        if api_key:
            args.extend(["--api-key", api_key])
        profiles_path = str(campaign.get("profiles") or "scripts/prompt_profiles.json")
        args.extend(["--profiles", profiles_path])
        script = REPO_ROOT / "scripts" / "runs" / "run_set_orchestrator.py"
        return str(script), args

    if profile == "coordinator":
        if api_url:
            args.extend(["--api-url", api_url])
        if api_key:
            args.extend(["--api-key", api_key])
        args.extend(["--max-cycles", str(campaign.get("max_cycles", 10))])
        component = str(campaign.get("component") or "contoso_cs")
        args.extend(["--component", component])
        script = REPO_ROOT / "scripts" / "runs" / "run_coordinator.py"
        return str(script), args

    raise ValueError(f"Unsupported run profile '{profile}'")


def _cmd_capture(args: argparse.Namespace) -> int:
    result = run_capture(
        job_id=args.job_id,
        api_url=args.api_url,
        note=args.note,
        sessions_root=args.sessions_root,
        api_key=args.api_key,
        transcript_path=args.transcript_path,
        out_dir=args.out_dir,
        snapshot_profile=args.snapshot_profile,
        compatibility_mode=bool(args.compatibility_mode),
        enforce_hard_fail=bool(args.enforce_hard_fail),
    )
    contract = (result.summary or {}).get("contract") or {}
    run_validity = (result.summary or {}).get("run_validity") or {}
    print(f"session_dir={result.session_dir}")
    print(f"contract_valid={bool(contract.get('valid'))}")
    print(f"hard_fail={bool(contract.get('hard_fail'))}")
    print(f"run_valid={bool(run_validity.get('valid'))}")
    return int(result.collect_exit)


def _cmd_run(args: argparse.Namespace) -> int:
    output_root = Path(args.output_dir or (REPO_ROOT / "sessions" / "harness-runs"))
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    campaign_dir = output_root / stamp
    campaign_dir.mkdir(parents=True, exist_ok=True)
    lifecycle_path = campaign_dir / "harness_lifecycle.json"
    state_path = campaign_dir / "harness_state.json"
    manifest_path = campaign_dir / "harness_manifest.json"

    config: dict[str, Any] = {}
    if args.config:
        config = _read_json(Path(args.config))
    runtime_ref = ""
    if config and args.runtime_config:
        runtime_path = Path(args.runtime_config)
        if runtime_path.exists():
            runtime_overlay = _read_json(runtime_path)
            config = _deep_merge(config, runtime_overlay)
            runtime_ref = str(runtime_path)
    script_path: str
    runner_args: list[str]
    if config:
        script_path, runner_args = _build_runner_from_config(config, args.profile)
        profile = args.profile or str(
            (config.get("campaign") or {}).get("mode")
            or (config.get("campaign") or {}).get("type")
            or "nightly"
        )
    else:
        if not args.profile:
            raise ValueError("run requires --profile when --config is not provided")
        profile_map = {
            "nightly": REPO_ROOT / "scripts" / "ops" / "nightly_groundtruth.py",
            "ab": REPO_ROOT / "scripts" / "runs" / "run_ab_parallel.py",
            "batch": REPO_ROOT / "scripts" / "runs" / "run_batch_parallel.py",
            "matrix": REPO_ROOT / "scripts" / "runs" / "run_transition_isolation_matrix.py",
            "set": REPO_ROOT / "scripts" / "runs" / "run_set_orchestrator.py",
            "coordinator": REPO_ROOT / "scripts" / "runs" / "run_coordinator.py",
        }
        script = profile_map.get(args.profile)
        if script is None:
            raise ValueError(f"Unsupported run profile '{args.profile}'")
        script_path = str(script)
        runner_args = []
        profile = args.profile

    passthrough = list(args.extra or [])
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    full_cmd = [_python_exe(), script_path, *runner_args, *passthrough]

    manifest = {
        "version": "1.0",
        "started_at": datetime.now().astimezone().isoformat(),
        "profile": profile,
        "script": script_path,
        "args": full_cmd[2:],
        "config_ref": str(args.config) if args.config else "",
        "runtime_config_ref": runtime_ref,
    }
    _write_json(manifest_path, manifest)
    _write_json(state_path, {"state": "launch", "updated_at": datetime.now().astimezone().isoformat()})
    _write_json(
        lifecycle_path,
        [{"state": "launch", "updated_at": datetime.now().astimezone().isoformat()}],
    )

    if args.dry_run:
        print("dry_run_command=" + " ".join(full_cmd))
        return 0

    exit_code = _run_subprocess(full_cmd)
    _write_json(
        state_path,
        {
            "state": "teardown",
            "updated_at": datetime.now().astimezone().isoformat(),
            "exit_code": exit_code,
        },
    )
    _write_json(
        campaign_dir / "run-index.json",
        {
            "profile": profile,
            "script": script_path,
            "args": full_cmd[2:],
            "exit_code": exit_code,
            "finished_at": datetime.now().astimezone().isoformat(),
        },
    )
    return exit_code


def _cmd_report(args: argparse.Namespace) -> int:
    if args.session_dir:
        session_dir = Path(args.session_dir)
        run_validity = _read_json(session_dir / "run-validity.json") if (session_dir / "run-validity.json").exists() else {}
        kpi_run = _read_json(session_dir / "kpi_run.json") if (session_dir / "kpi_run.json").exists() else {}
        report = {
            "session_dir": str(session_dir),
            "run_validity": run_validity,
            "kpi_run": kpi_run,
        }
        out_path = Path(args.out or (session_dir / "human" / "harness-report.json"))
        _write_json(out_path, report)
        print(str(out_path))
        return 0

    if args.campaign_dir:
        campaign_dir = Path(args.campaign_dir)
        summary_path = campaign_dir / "kpi_nightly_summary.json"
        if not summary_path.exists():
            raise FileNotFoundError(f"Missing campaign summary: {summary_path}")
        summary = _read_json(summary_path)
        out_md = Path(args.out or (campaign_dir / "harness-campaign-report.md"))
        lines = [
            "# Harness Campaign Report",
            "",
            f"- Campaign: `{summary.get('campaign_id', '')}`",
            f"- Runs total: {summary.get('runs_total', 0)}",
            f"- Runs ok: {summary.get('runs_ok', 0)}",
            f"- Runs failed: {summary.get('runs_failed', 0)}",
            f"- Runs valid: {summary.get('runs_valid', 0)}",
            f"- Runs invalid: {summary.get('runs_invalid', 0)}",
            f"- Success rate avg: {summary.get('success_rate_avg', 0.0)}",
            f"- Flake rate: {summary.get('flake_rate')}",
        ]
        out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(str(out_md))
        return 0

    raise ValueError("report requires --session-dir or --campaign-dir")


def _cmd_verify(args: argparse.Namespace) -> int:
    session_dir = Path(args.session_dir)
    contract = collector._validate_contract(session_dir, args.mode)  # noqa: SLF001
    transition_index = {}
    ti_path = session_dir / "transition-index.json"
    if ti_path.exists():
        transition_index = _read_json(ti_path)
    transitions = {
        str(item.get("id"))
        for item in (transition_index.get("transitions") or [])
        if isinstance(item, dict)
    }
    schema_handoff = {}
    schema_handoff_path = session_dir / "schema-handoff-audit.json"
    if schema_handoff_path.exists():
        schema_handoff = _read_json(schema_handoff_path)
    summary = (schema_handoff.get("summary") or {}) if isinstance(schema_handoff, dict) else {}
    drop_to_zero = int(summary.get("drop_to_zero_count") or 0)
    handoff_regressions = int(summary.get("regression_count") or 0)
    handoff_silent_loss = int(summary.get("silent_function_loss_count") or 0)

    stage_handoff = {}
    stage_handoff_path = session_dir / "stage-handoff-audit.json"
    if stage_handoff_path.exists():
        stage_handoff = _read_json(stage_handoff_path)
    stage_handoff_summary = (stage_handoff.get("summary") or {}) if isinstance(stage_handoff, dict) else {}
    stage_handoff_fail_count = int(stage_handoff_summary.get("fail_count") or 0)

    transition_contract = {}
    transition_contract_path = session_dir / "transition-contract-audit.json"
    if transition_contract_path.exists():
        transition_contract = _read_json(transition_contract_path)
    transition_contract_summary = (
        (transition_contract.get("summary") or {}) if isinstance(transition_contract, dict) else {}
    )
    transition_contract_fail_count = int(transition_contract_summary.get("fail_count") or 0)

    knob_failures: list[dict[str, Any]] = []
    config = _read_json(Path(args.config)) if args.config else {}
    knob_contract = config.get("knob_contract") if isinstance(config.get("knob_contract"), dict) else {}
    for knob, rule in knob_contract.items():
        if not isinstance(rule, dict):
            continue
        missing_artifacts: list[str] = []
        for rel in (rule.get("required_artifacts") or []):
            rel_str = str(rel)
            if rel_str and not (session_dir / rel_str).exists():
                missing_artifacts.append(rel_str)
        missing_transitions = [
            tid
            for tid in (rule.get("affects_transitions") or [])
            if str(tid) not in transitions
        ]
        if missing_artifacts or missing_transitions:
            knob_failures.append(
                {
                    "knob": knob,
                    "missing_artifacts": missing_artifacts,
                    "missing_transitions": missing_transitions,
                }
            )

    payload = {
        "session_dir": str(session_dir),
        "mode": args.mode,
        "contract_valid": bool(contract.valid),
        "contract_missing": list(contract.missing),
        "contract_parse_errors": list(contract.parse_errors),
        "schema_handoff_drop_to_zero": drop_to_zero,
        "schema_handoff_regressions": handoff_regressions,
        "schema_handoff_silent_loss": handoff_silent_loss,
        "stage_handoff_fail_count": stage_handoff_fail_count,
        "transition_contract_fail_count": transition_contract_fail_count,
        "knob_failures": knob_failures,
    }
    out_path = Path(args.out or (session_dir / "human" / "verify-report.json"))
    _write_json(out_path, payload)
    print(str(out_path))
    if args.mode == "strict" and not contract.valid:
        return 1
    if handoff_regressions > 0:
        return 1
    if handoff_silent_loss > 0:
        return 1
    if drop_to_zero > 0:
        return 1
    if stage_handoff_fail_count > 0:
        return 1
    if transition_contract_fail_count > 0:
        return 1
    if knob_failures:
        return 1
    return 0


def _cmd_test(args: argparse.Namespace) -> int:
    pytest_args = list(args.pytest_args or [])
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    if not pytest_args:
        pytest_args = ["tests/"]
    cmd = [_python_exe(), "-m", "pytest", *pytest_args]
    return _run_subprocess(cmd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified harness control plane")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run campaign/orchestration profile")
    run.add_argument("--profile", choices=("nightly", "ab", "batch", "matrix", "set", "coordinator"), default="")
    run.add_argument("--config", default="")
    run.add_argument("--runtime-config", default=str(REPO_ROOT / "configs" / "harness" / "local.runtime.json"))
    run.add_argument("--output-dir", default=str(REPO_ROOT / "sessions" / "harness-runs"))
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("extra", nargs=argparse.REMAINDER)

    capture = sub.add_parser("capture", help="Capture session snapshot and collect artifacts")
    capture.add_argument("--job-id", required=True)
    capture.add_argument("--api-url", required=True)
    capture.add_argument("--note", default="")
    capture.add_argument("--sessions-root", default=str(REPO_ROOT / "sessions"))
    capture.add_argument("--api-key", default="")
    capture.add_argument("--transcript-path", default="")
    capture.add_argument("--out-dir", default="")
    capture.add_argument("--snapshot-profile", choices=("full", "compact"), default="full")
    capture.add_argument("--compatibility-mode", action="store_true")
    capture.add_argument("--enforce-hard-fail", action="store_true")

    report = sub.add_parser("report", help="Generate report outputs")
    report.add_argument("--campaign-dir", default="")
    report.add_argument("--session-dir", default="")
    report.add_argument("--out", default="")

    verify = sub.add_parser("verify", help="Verify contract and knob-impact evidence")
    verify.add_argument("--session-dir", required=True)
    verify.add_argument("--config", default="")
    verify.add_argument("--mode", choices=("strict", "compatibility"), default="strict")
    verify.add_argument("--out", default="")

    test = sub.add_parser("test", help="Unified test entrypoint")
    test.add_argument("pytest_args", nargs=argparse.REMAINDER)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "capture":
        return _cmd_capture(args)
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "report":
        return _cmd_report(args)
    if args.command == "verify":
        return _cmd_verify(args)
    if args.command == "test":
        return _cmd_test(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
