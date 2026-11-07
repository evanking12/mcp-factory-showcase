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

RESULT_NAME = "stage-breakpoint-result.json"
SUMMARY_NAME = "stage-breakpoint-summary.md"
TAIL_LIMIT = 4000
STAGE_BREAKPOINT_CATEGORY = "stage_breakpoint"
CLAIM_CEILING = "stage/seam breakpoint evidence only; not broad pipeline non-regression"
BREAKPOINT_METADATA_FIELDS = (
    "breakpoint_scope",
    "ownership_type",
    "breakpoint_family",
    "current_tier",
    "target_tier",
    "claim_ceiling",
)


def _breakpoint_metadata(check: dict[str, Any]) -> dict[str, Any]:
    return {
        field: check[field]
        for field in BREAKPOINT_METADATA_FIELDS
        if check.get(field) is not None
    }


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, str(pattern)) for pattern in patterns)


def _affected_ids(admission: dict[str, Any]) -> set[str]:
    return {str(system.get("system_id") or "") for system in admission.get("affected_systems") or []}


def _select_stage_breakpoint_checks(
    registry: dict[str, Any],
    affected_system_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_commands: dict[str, dict[str, Any]] = {}

    for check in registry.get("checks") or []:
        check_id = str(check.get("check_id") or "")
        system_id = str(check.get("system_id") or "")
        category = str(check.get("category") or "")
        command = str(check.get("command") or "").strip()

        if system_id not in affected_system_ids:
            continue
        if category != STAGE_BREAKPOINT_CATEGORY:
            skipped.append(
                {
                    "check_id": check_id,
                    "system_id": system_id,
                    "reason": "not_stage_breakpoint_category",
                    "category": category,
                    "command": command,
                }
            )
            continue
        if not bool(check.get("blocking")):
            skipped.append(
                {
                    "check_id": check_id,
                    "system_id": system_id,
                    "reason": "nonblocking_check",
                    "category": category,
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
                    "category": category,
                    "command": command,
                }
            )
            continue

        existing = seen_commands.get(command)
        if existing is not None:
            existing["check_ids"].append(check_id)
            existing["system_ids"] = sorted(set([*existing["system_ids"], system_id]))
            metadata = _breakpoint_metadata(check)
            if metadata:
                existing.setdefault("breakpoint_metadata", []).append(metadata)
            continue

        metadata = _breakpoint_metadata(check)
        row = {
            "check_ids": [check_id],
            "system_ids": [system_id],
            "category": category,
            "command": command,
            "expected_runtime_seconds": check.get("expected_runtime_seconds"),
            "when_required": check.get("when_required"),
        }
        if metadata:
            row["breakpoint_metadata"] = [metadata]
            row.update(metadata)
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


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Stage Breakpoint Checks",
        "",
        f"- Verdict: `{result.get('verdict')}`",
        f"- Claim ceiling: `{result.get('claim_ceiling')}`",
        f"- Selected stage breakpoint checks: `{len(result.get('selected_checks') or [])}`",
        f"- Skipped checks: `{len(result.get('skipped_checks') or [])}`",
        "",
        "## Changed Paths",
    ]
    for path in result.get("checked_paths") or []:
        lines.append(f"- `{path}`")
    if not result.get("checked_paths"):
        lines.append("- none")

    lines.extend(["", "## Selected Checks"])
    for check in result.get("selected_checks") or []:
        ids = ", ".join(f"`{check_id}`" for check_id in check.get("check_ids") or [])
        metadata_chunks = []
        for metadata in check.get("breakpoint_metadata") or []:
            scope = metadata.get("breakpoint_scope", "unknown_scope")
            owner = metadata.get("ownership_type", "unknown_owner")
            family = metadata.get("breakpoint_family", "unknown_family")
            current_tier = metadata.get("current_tier", "unknown_current")
            target_tier = metadata.get("target_tier", "unknown_target")
            claim_ceiling = metadata.get("claim_ceiling", "unknown_claim")
            metadata_chunks.append(
                f"scope=`{scope}` owner=`{owner}` family=`{family}` "
                f"tier=`{current_tier}->{target_tier}` claim=`{claim_ceiling}`"
            )
        if not metadata_chunks:
            metadata = []
            for field in BREAKPOINT_METADATA_FIELDS:
                if check.get(field) is not None:
                    metadata.append(f"{field}=`{check.get(field)}`")
            metadata_chunks = metadata
        suffix = f" ({'; '.join(metadata_chunks)})" if metadata_chunks else ""
        lines.append(f"- {ids}: `{check.get('command')}`{suffix}")
    if not result.get("selected_checks"):
        lines.append("- none selected")

    lines.extend(["", "## Executions"])
    for execution in result.get("executions") or []:
        ids = ", ".join(f"`{check_id}`" for check_id in execution.get("check_ids") or [])
        lines.append(
            f"- {ids}: `{execution.get('verdict')}` "
            f"exit=`{execution.get('exit_code')}` duration=`{execution.get('duration_seconds')}`"
        )
    if not result.get("executions"):
        lines.append("- none")

    return "\n".join(lines) + "\n"


def write_outputs(result: dict[str, Any], *, output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / RESULT_NAME).write_text(json.dumps(result, indent=2), encoding="utf-8")
    (output_root / SUMMARY_NAME).write_text(render_markdown(result), encoding="utf-8")


def run_stage_breakpoint_checks(
    *,
    paths_file: Path | None,
    output_root: Path,
    registry_path: Path = DEFAULT_REGISTRY,
    mode: str = "local",
    execute: bool = False,
    timeout_seconds: int = 600,
) -> tuple[dict[str, Any], int]:
    registry = load_json(registry_path)
    checked_paths = [normalize_path(path) for path in load_paths(paths_file)]
    admission = evaluate_change_admission(registry_path=registry_path, changed_paths=checked_paths)
    affected_ids = _affected_ids(admission)
    selected, skipped = _select_stage_breakpoint_checks(registry, affected_ids)
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

    failed = [execution for execution in executions if execution.get("verdict") == "fail"]
    verdict = "fail" if failed else "pass"
    result = {
        "verdict": verdict,
        "mode": mode,
        "execute": execute,
        "checked_paths": checked_paths,
        "affected_systems": admission.get("affected_systems") or [],
        "selected_checks": selected,
        "skipped_checks": skipped,
        "executions": executions,
        "claim_ceiling": CLAIM_CEILING,
        "change_admission_failures": admission.get("failures") or [],
        "next_blocker": "resolve_stage_breakpoint_failures" if verdict == "fail" else "none",
    }
    write_outputs(result, output_root=output_root)
    return result, 1 if verdict == "fail" else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run changed-path-selected stage breakpoint checks.")
    parser.add_argument("--paths-file", type=Path, default=None)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("local", "ci"), default="local")
    parser.add_argument("--execute", dest="execute", action="store_true")
    parser.add_argument("--no-execute", dest="execute", action="store_false")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.set_defaults(execute=False)
    args = parser.parse_args(argv)

    result, exit_code = run_stage_breakpoint_checks(
        paths_file=args.paths_file,
        output_root=args.output_root,
        registry_path=args.registry,
        mode=args.mode,
        execute=args.execute,
        timeout_seconds=args.timeout_seconds,
    )
    sys.stdout.write(render_markdown(result))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
