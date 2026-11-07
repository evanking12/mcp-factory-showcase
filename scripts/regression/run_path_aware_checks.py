from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.regression.change_admission_check import (  # noqa: E402
    DEFAULT_REGISTRY,
    evaluate_change_admission,
    load_json,
    load_paths,
    normalize_path,
)


DEFAULT_TRIGGER_CONFIG = REPO_ROOT / "configs" / "regression" / "observability_promotion_triggers.json"
RESULT_NAME = "path-aware-check-result.json"
SUMMARY_NAME = "path-aware-check-summary.md"
TAIL_LIMIT = 4000
TIER_ORDER = {
    "none": -1,
    "tier0": 0,
    "tier1": 1,
    "tier0_and_tier1": 1,
    "tier1_or_higher": 1,
    "tier2": 2,
    "tier3": 3,
}


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, str(pattern)) for pattern in patterns)


def _affected_ids(admission: dict[str, Any]) -> set[str]:
    return {str(system.get("system_id") or "") for system in admission.get("affected_systems") or []}


def _select_checks(registry: dict[str, Any], affected_system_ids: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_commands: dict[str, dict[str, Any]] = {}

    for check in registry.get("checks") or []:
        system_id = str(check.get("system_id") or "")
        if system_id not in affected_system_ids:
            continue
        check_id = str(check.get("check_id") or "")
        command = str(check.get("command") or "").strip()
        blocking = bool(check.get("blocking"))
        if not blocking:
            skipped.append(
                {
                    "check_id": check_id,
                    "system_id": system_id,
                    "reason": "nonblocking_check",
                    "command": command,
                }
            )
            continue
        if not command or command.lower().startswith("manual "):
            skipped.append(
                {
                    "check_id": check_id,
                    "system_id": system_id,
                    "reason": "manual_or_missing_command",
                    "command": command,
                }
            )
            continue

        existing = seen_commands.get(command)
        if existing is not None:
            existing["check_ids"].append(check_id)
            existing["system_ids"] = sorted(set([*existing["system_ids"], system_id]))
            continue

        row = {
            "check_ids": [check_id],
            "system_ids": [system_id],
            "category": check.get("category"),
            "command": command,
            "expected_runtime_seconds": check.get("expected_runtime_seconds"),
            "when_required": check.get("when_required"),
        }
        seen_commands[command] = row
        selected.append(row)

    return selected, skipped


def _run_command(command: str, *, timeout_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        duration = round(time.monotonic() - started, 3)
        return {
            "verdict": "pass" if completed.returncode == 0 else "fail",
            "exit_code": completed.returncode,
            "duration_seconds": duration,
            "stdout_tail": completed.stdout[-TAIL_LIMIT:],
            "stderr_tail": completed.stderr[-TAIL_LIMIT:],
        }
    except subprocess.TimeoutExpired as exc:
        duration = round(time.monotonic() - started, 3)
        return {
            "verdict": "fail",
            "exit_code": None,
            "duration_seconds": duration,
            "stdout_tail": str(exc.stdout or "")[-TAIL_LIMIT:],
            "stderr_tail": str(exc.stderr or "")[-TAIL_LIMIT:],
            "failure_class": "timeout",
        }


def _tier_value(tier: str) -> int:
    return TIER_ORDER.get(str(tier or "none"), -1)


def _promotion_triggers(
    *,
    config: dict[str, Any],
    checked_paths: list[str],
    affected_system_ids: set[str],
    required_tier: str,
    failed_executions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    triggers: list[dict[str, Any]] = []
    has_failures = bool(failed_executions)
    higher_than_tier0 = _tier_value(required_tier) > 0

    for trigger in config.get("triggers") or []:
        trigger_id = str(trigger.get("trigger_id") or "")
        path_patterns = list(trigger.get("path_patterns") or [])
        system_ids = {str(system_id) for system_id in trigger.get("system_ids") or []}
        tier_threshold = str(trigger.get("required_tier_at_or_above") or "")
        path_hit = any(_matches_any(path, path_patterns) for path in checked_paths)
        system_hit = bool(system_ids.intersection(affected_system_ids))
        tier_hit = bool(tier_threshold) and _tier_value(required_tier) >= _tier_value(tier_threshold)

        state = "not_fired"
        reason = "No matching changed surface or tier pressure."
        if trigger_id == "lane_runtime_reliability_classification":
            if (path_hit or system_hit or tier_hit) and has_failures:
                state = "fired"
                reason = "A lane/runtime/runner-adjacent surface failed and needs infrastructure-vs-product classification."
            elif path_hit or system_hit or tier_hit:
                state = "watch"
                reason = "Lane/runtime/runner-adjacent surface changed; classification may be needed if red appears."
        elif trigger_id == "baseline_breakage_map_generation":
            if (path_hit or system_hit) and has_failures:
                state = "fired"
                reason = "Migration-shaped surface failed; baseline-relative ownership may need a generated breakage map."
            elif path_hit or system_hit:
                state = "watch"
                reason = "Migration-shaped surface changed; grow breakage-map output if ownership becomes manual."
        elif trigger_id == "scheduled_or_manual_heavier_baselines":
            if higher_than_tier0 or tier_hit:
                state = "watch"
                reason = "Required tier exceeds Tier 0; stronger claims need lane or baseline-suite evidence."

        triggers.append(
            {
                "trigger_id": trigger_id,
                "state": state,
                "reason": reason,
                "recommended_next_system": trigger.get("recommended_next_system"),
                "claim_effect": trigger.get("claim_effect"),
            }
        )
    return triggers


def run_path_aware_checks(
    *,
    paths_file: Path | None,
    output_root: Path,
    registry_path: Path = DEFAULT_REGISTRY,
    trigger_config_path: Path = DEFAULT_TRIGGER_CONFIG,
    mode: str = "local",
    execute: bool = False,
    timeout_seconds: int = 300,
) -> tuple[dict[str, Any], int]:
    output_root.mkdir(parents=True, exist_ok=True)
    registry = load_json(registry_path)
    trigger_config = load_json(trigger_config_path) if trigger_config_path.exists() else {"triggers": []}
    checked_paths = [normalize_path(path) for path in load_paths(paths_file)]
    admission = evaluate_change_admission(registry_path=registry_path, changed_paths=checked_paths)
    affected_ids = _affected_ids(admission)
    selected, skipped = _select_checks(registry, affected_ids)
    executions: list[dict[str, Any]] = []

    for check in selected:
        execution = {
            "check_ids": check["check_ids"],
            "system_ids": check["system_ids"],
            "command": check["command"],
            "verdict": "not_run",
            "exit_code": None,
            "duration_seconds": 0,
            "stdout_tail": "",
            "stderr_tail": "",
        }
        if execute:
            execution.update(_run_command(check["command"], timeout_seconds=timeout_seconds))
        executions.append(execution)

    failed_executions = [row for row in executions if row.get("verdict") == "fail"]
    promotion_triggers = _promotion_triggers(
        config=trigger_config,
        checked_paths=checked_paths,
        affected_system_ids=affected_ids,
        required_tier=str(admission.get("required_regression_tier") or "none"),
        failed_executions=failed_executions,
    )
    verdict = "fail" if admission.get("verdict") == "fail" or failed_executions else "pass"
    result = {
        "verdict": verdict,
        "mode": mode,
        "execute": execute,
        "checked_paths": checked_paths,
        "affected_systems": admission.get("affected_systems") or [],
        "selected_checks": selected,
        "skipped_checks": skipped,
        "executions": executions,
        "required_regression_tier": admission.get("required_regression_tier"),
        "claim_ceiling": "tier0 contract/governance/artifact compatibility only",
        "promotion_triggers": promotion_triggers,
        "change_admission_failures": admission.get("failures") or [],
        "next_blocker": "resolve_path_aware_check_failures" if verdict == "fail" else "none",
    }
    write_outputs(result, output_root=output_root)
    return result, 1 if verdict == "fail" else 0


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Path-Aware Checks",
        "",
        f"- Verdict: `{result.get('verdict')}`",
        f"- Required regression tier: `{result.get('required_regression_tier')}`",
        f"- Claim ceiling: `{result.get('claim_ceiling')}`",
        f"- Affected systems: `{len(result.get('affected_systems') or [])}`",
        f"- Selected checks: `{len(result.get('selected_checks') or [])}`",
        f"- Executed: `{'yes' if result.get('execute') else 'no'}`",
        f"- Next blocker: `{result.get('next_blocker')}`",
        "",
        "## Affected Systems",
        "",
    ]
    if result.get("affected_systems"):
        for system in result["affected_systems"]:
            lines.append(f"- `{system.get('system_id')}` tier=`{system.get('required_regression_tier')}`")
    else:
        lines.append("- `none`")

    lines.extend(["", "## Selected Checks", ""])
    if result.get("selected_checks"):
        for check in result["selected_checks"]:
            lines.append(f"- `{', '.join(check.get('check_ids') or [])}`: `{check.get('command')}`")
    else:
        lines.append("- `none`")

    lines.extend(["", "## Executions", ""])
    if result.get("executions"):
        for execution in result["executions"]:
            lines.append(
                f"- `{', '.join(execution.get('check_ids') or [])}`: "
                f"`{execution.get('verdict')}` exit=`{execution.get('exit_code')}`"
            )
    else:
        lines.append("- `none`")

    lines.extend(["", "## Skipped Checks", ""])
    if result.get("skipped_checks"):
        for skipped in result["skipped_checks"]:
            lines.append(f"- `{skipped.get('check_id')}`: `{skipped.get('reason')}`")
    else:
        lines.append("- `none`")

    lines.extend(["", "## Promotion Triggers", ""])
    if result.get("promotion_triggers"):
        for trigger in result["promotion_triggers"]:
            lines.append(
                f"- `{trigger.get('trigger_id')}`: `{trigger.get('state')}` - {trigger.get('reason')}"
            )
    else:
        lines.append("- `none`")

    if result.get("change_admission_failures"):
        lines.extend(["", "## Change Admission Failures", ""])
        for failure in result["change_admission_failures"]:
            lines.append(f"- `{failure.get('code')}`: {failure.get('message')}")

    return "\n".join(lines) + "\n"


def write_outputs(result: dict[str, Any], *, output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / RESULT_NAME).write_text(json.dumps(result, indent=2), encoding="utf-8")
    (output_root / SUMMARY_NAME).write_text(render_markdown(result), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run path-aware checks selected from check_registry.json.")
    parser.add_argument("--paths-file", type=Path, default=None)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--trigger-config", type=Path, default=DEFAULT_TRIGGER_CONFIG)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("local", "ci"), default="local")
    parser.add_argument("--execute", dest="execute", action="store_true")
    parser.add_argument("--no-execute", dest="execute", action="store_false")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.set_defaults(execute=False)
    args = parser.parse_args(argv)

    result, exit_code = run_path_aware_checks(
        paths_file=args.paths_file,
        output_root=args.output_root,
        registry_path=args.registry,
        trigger_config_path=args.trigger_config,
        mode=args.mode,
        execute=args.execute,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
