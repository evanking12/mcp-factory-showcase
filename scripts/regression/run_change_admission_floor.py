from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.regression.change_admission_check import (  # noqa: E402
    DEFAULT_REGISTRY,
    evaluate_change_admission,
    load_paths,
    render_markdown,
)


CLI_SMOKES = (
    ("aggregate_checkpoint_suite", ("scripts/regression/aggregate_checkpoint_suite.py", "--help")),
    ("write_ci_job_summary", ("scripts/regression/write_ci_job_summary.py", "--help")),
    ("write_checkpoint_job_summary", ("scripts/regression/write_checkpoint_job_summary.py", "--help")),
    ("run_regression_gate_v1", ("scripts/regression/run_regression_gate_v1.py", "--help")),
    ("run_stage_breakpoint_checks", ("scripts/regression/run_stage_breakpoint_checks.py", "--help")),
    ("run_spectrum_compiled_easy01", ("scripts/runs/run_spectrum_compiled_easy01.py", "--help")),
    ("run_spectrum_compiled_medium01", ("scripts/runs/run_spectrum_compiled_medium01.py", "--help")),
)

WORKFLOW_FILES = (
    ".github/workflows/fast-checks.yml",
    ".github/workflows/stage-breakpoint-checks.yml",
    ".github/workflows/required-regression-gates.yml",
    ".github/workflows/easy01-diagnostic-checkpoints.yml",
    ".github/workflows/medium01-checkpoints.yml",
)


def _result(name: str, verdict: str, message: str = "", **extra: Any) -> dict[str, Any]:
    payload = {"name": name, "verdict": verdict, "message": message}
    payload.update(extra)
    return payload


def run_cli_smokes(repo_root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name, command in CLI_SMOKES:
        completed = subprocess.run(
            [sys.executable, *command],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            results.append(_result(name, "pass"))
            continue
        results.append(
            _result(
                name,
                "fail",
                f"CLI smoke failed with exit code {completed.returncode}.",
                exit_code=completed.returncode,
                stdout_tail=completed.stdout[-1000:],
                stderr_tail=completed.stderr[-1000:],
            )
        )
    return results


def parse_workflows(repo_root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for relative in WORKFLOW_FILES:
        path = repo_root / relative
        if not path.exists():
            results.append(_result(relative, "fail", "Workflow file is missing."))
            continue
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - exact parser error is not stable
            results.append(_result(relative, "fail", f"Workflow YAML parse failed: {exc}"))
            continue
        results.append(_result(relative, "pass"))
    return results


def run_floor(
    *,
    paths_file: Path | None,
    output_root: Path,
    registry: Path,
    packet: Path | None,
    mode: str,
) -> tuple[dict[str, Any], int]:
    output_root.mkdir(parents=True, exist_ok=True)
    changed_paths = load_paths(paths_file)
    admission = evaluate_change_admission(
        registry_path=registry,
        changed_paths=changed_paths,
        packet_path=packet,
        strict=False,
    )
    cli_results = run_cli_smokes()
    workflow_results = parse_workflows()
    meta_failures = [
        row
        for row in [*cli_results, *workflow_results]
        if str(row.get("verdict") or "") == "fail"
    ]

    result = dict(admission)
    result.update(
        {
            "mode": mode,
            "meta_check_results": {
                "cli_smokes": cli_results,
                "workflow_yaml_parse": workflow_results,
            },
        }
    )
    if meta_failures:
        failures = list(result.get("failures") or [])
        for failure in meta_failures:
            failures.append(
                {
                    "code": "meta_check_failed",
                    "message": failure.get("message") or f"{failure.get('name')} failed.",
                    "check": failure.get("name"),
                }
            )
        result["failures"] = failures
        result["verdict"] = "fail"
        result["next_blocker"] = "resolve_change_admission_meta_check_failures"

    result_path = output_root / "change-admission-result.json"
    summary_path = output_root / "change-admission-summary.md"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    summary = render_markdown(result)
    summary += "\n## Floor Meta-Checks\n\n"
    for row in cli_results:
        summary += f"- CLI `{row['name']}`: `{row['verdict']}`\n"
    for row in workflow_results:
        summary += f"- Workflow `{row['name']}`: `{row['verdict']}`\n"
    summary_path.write_text(summary, encoding="utf-8")
    return result, 1 if result["verdict"] == "fail" else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the cheap change-admission floor.")
    parser.add_argument("--paths-file", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--packet", type=Path, default=None)
    parser.add_argument("--mode", choices=("local", "ci"), default="local")
    args = parser.parse_args(argv)

    result, exit_code = run_floor(
        paths_file=args.paths_file,
        output_root=args.output_root,
        registry=args.registry,
        packet=args.packet,
        mode=args.mode,
    )
    print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
