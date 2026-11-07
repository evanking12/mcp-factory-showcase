from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable
import fnmatch


GATE_PATTERNS = (
    "api/**",
    "runtime/**",
    "scripts/regression/**",
    "scripts/runs/**",
    "scripts/ops/**",
    "configs/regression/**",
    ".github/workflows/required-regression-gates.yml",
    ".github/workflows/medium01-checkpoints.yml",
    ".github/workflows/stage-breakpoint-checks.yml",
    "tests/test_regression_gate_v1.py",
    "docs/architecture/testing_strategy/**",
    "AGENTS.md",
    ".agents/skills/regression-governor/**",
    ".agents/skills/baseline-promoter/**",
    ".agents/skills/system-contract-tracer/**",
    ".codex/agents/proving-authority-reviewer.toml",
    "docs/architecture/agentic_ecosystem/**",
)

RISK_ORDER = {
    "green": 0,
    "grey": 1,
    "yellow": 2,
    "red": 3,
}

RED_PATTERNS = (
    "api/**",
    "runtime/start-managed-lane.ps1",
    "runtime/_managed_lane_startup.ps1",
    "scripts/regression/run_regression_gate_v1.py",
    "scripts/regression/ci_gate_eligibility.py",
    "scripts/regression/run_change_admission_floor.py",
    "scripts/regression/run_path_aware_checks.py",
    "scripts/ops/check_api_identity.py",
    "scripts/ops/check_bridge_identity.py",
    "configs/regression/**",
    ".github/workflows/required-regression-gates.yml",
    "tests/test_regression_gate_v1.py",
    "docs/architecture/testing_strategy/COMPILED-SUITE-GREEN-CONTRACT.md",
    "docs/architecture/testing_strategy/PIPELINE-PROVING-BASELINE-SNAPSHOTS.md",
    "docs/architecture/testing_strategy/REGRESSION-GATE-V1.md",
    "docs/architecture/testing_strategy/REGRESSION-GATE-CI-V1.md",
    "docs/architecture/testing_strategy/REGRESSION-POLICY.md",
)

YELLOW_PATTERNS = (
    "runtime/run-local-product-suite.ps1",
    "runtime/run_local_product_suite.py",
    "scripts/runs/**",
    "scripts/ops/**",
    ".github/workflows/medium01-checkpoints.yml",
    ".github/workflows/stage-breakpoint-checks.yml",
    "tests/test_spectrum_compiled_ingest.py",
    "tests/test_local_product_suite_entrypoint.py",
)

GREY_PATTERNS = (
    "AGENTS.md",
    "dynamic_campaigns/**",
    "docs/architecture/testing_strategy/**",
    "docs/architecture/agentic_ecosystem/**",
    ".agents/skills/**",
)

FAST_FLOOR_ONLY_PATTERNS = (
    "configs/regression/check_registry.json",
    "docs/architecture/testing_strategy/SYSTEM-MAP.md",
    "docs/architecture/testing_strategy/CHANGE-ADMISSION-PACKET-TEMPLATE.md",
)


def _normalize_path(path: str) -> str:
    return str(path or "").strip().replace("\\", "/")


def _matches_any(path: str, patterns: Iterable[str]) -> list[str]:
    return [pattern for pattern in patterns if fnmatch.fnmatch(path, pattern)]


def is_fast_floor_only_path(path: str) -> bool:
    normalized = _normalize_path(path)
    return bool(_matches_any(normalized, FAST_FLOOR_ONLY_PATTERNS))


def is_heavy_gate_path(path: str) -> bool:
    normalized = _normalize_path(path)
    return bool(_matches_any(normalized, GATE_PATTERNS)) and not is_fast_floor_only_path(normalized)


def _risk_for_path(path: str) -> tuple[str, list[str]]:
    if is_fast_floor_only_path(path):
        return "grey", ["fast_floor_only"]
    if _matches_any(path, RED_PATTERNS):
        return "red", ["full_product_gate_surface"]
    if _matches_any(path, YELLOW_PATTERNS):
        return "yellow", ["targeted_product_or_runner_surface"]
    if _matches_any(path, GREY_PATTERNS):
        return "grey", ["governance_or_diagnostic_surface"]
    return "green", ["static_or_unrelated_surface"]


def _recommend_local_proof(risk_level: str) -> str:
    if risk_level == "red":
        return (
            "Prefer the narrowest checkpoint/replay or seam proof first; "
            "CI/promotion should run the full product baseline gate."
        )
    if risk_level == "yellow":
        return (
            "Use Medium02 or the touched suite as the local proving surface; "
            "do not rerun Easy01/Medium01 E2E by default."
        )
    if risk_level == "grey":
        return "Run fast checks, sticky docs, and change-admission checks; no product E2E by default."
    return "Static checks are sufficient unless review finds hidden runtime coupling."


def evaluate_gate_eligibility(paths: Iterable[str]) -> dict[str, object]:
    normalized_paths = [_normalize_path(path) for path in paths if _normalize_path(path)]
    matched_patterns: list[str] = []
    matched_paths: list[str] = []
    fast_floor_only_paths: list[str] = []
    reason_codes: list[str] = []
    path_risks: list[dict[str, object]] = []
    proof_risk_level = "green"

    for path in normalized_paths:
        path_risk, path_reasons = _risk_for_path(path)
        if RISK_ORDER[path_risk] > RISK_ORDER[proof_risk_level]:
            proof_risk_level = path_risk
        reason_codes.extend(path_reasons)
        path_risks.append(
            {
                "path": path,
                "risk_level": path_risk,
                "reason_codes": path_reasons,
            }
        )
        if is_fast_floor_only_path(path):
            fast_floor_only_paths.append(path)
            continue
        path_matched = False
        for pattern in _matches_any(path, GATE_PATTERNS):
            matched_patterns.append(pattern)
            path_matched = True
        if path_matched:
            matched_paths.append(path)

    return {
        "should_run_gate": bool(matched_paths),
        "matched_paths": sorted(set(matched_paths)),
        "matched_patterns": sorted(set(matched_patterns)),
        "fast_floor_only_paths": sorted(set(fast_floor_only_paths)),
        "checked_paths": normalized_paths,
        "proof_risk_level": proof_risk_level,
        "requires_full_product_gate": proof_risk_level == "red",
        "recommended_local_proof": _recommend_local_proof(proof_risk_level),
        "reason_codes": sorted(set(reason_codes)),
        "path_risks": path_risks,
    }


def _write_github_output(path: Path, payload: dict[str, object]) -> None:
    lines = [
        f"should_run_gate={'true' if bool(payload['should_run_gate']) else 'false'}",
        f"matched_count={len(list(payload.get('matched_paths') or []))}",
        f"proof_risk_level={payload.get('proof_risk_level', 'green')}",
        f"requires_full_product_gate={'true' if bool(payload.get('requires_full_product_gate')) else 'false'}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Decide whether Regression Gate V1 should run for changed paths.")
    parser.add_argument("paths", nargs="*", help="Changed repo-relative paths to evaluate.")
    parser.add_argument("--paths-file", type=Path, default=None, help="Optional file containing one changed path per line.")
    parser.add_argument(
        "--github-output",
        type=Path,
        default=None,
        help="Optional GitHub Actions output file to append should_run_gate to.",
    )
    args = parser.parse_args()

    raw_paths: list[str] = list(args.paths)
    if args.paths_file is not None and args.paths_file.exists():
        raw_paths.extend(args.paths_file.read_text(encoding="utf-8").splitlines())

    payload = evaluate_gate_eligibility(raw_paths)
    print(json.dumps(payload, indent=2))
    if args.github_output is not None:
        _write_github_output(args.github_output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
