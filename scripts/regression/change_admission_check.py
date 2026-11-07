from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.regression.ci_gate_eligibility import is_heavy_gate_path  # noqa: E402


DEFAULT_REGISTRY = REPO_ROOT / "configs" / "regression" / "check_registry.json"
VALID_CHECK_CATEGORIES = {"durable_contract", "allowed_to_churn", "meta_check", "stage_breakpoint"}
REQUIRED_PACKET_FIELDS = (
    "durable_contracts",
    "allowed_churn",
    "meta_checks",
    "regression_posture",
    "change_admission_result",
    "unexpected_blast_radius",
    "classification_updates_required",
    "next_blocker",
)


def normalize_path(path: str) -> str:
    return str(path or "").lstrip("\ufeff").strip().replace("\\", "/")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_paths(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    return [normalize_path(line) for line in path.read_text(encoding="utf-8").splitlines() if normalize_path(line)]


def _failure(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"code": code, "message": message}
    payload.update(extra)
    return payload


def validate_registry(registry: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    systems = list(registry.get("systems") or [])
    checks = list(registry.get("checks") or [])
    system_ids = {str(system.get("system_id") or "").strip() for system in systems}

    if not registry.get("schema_version"):
        failures.append(_failure("missing_schema_version", "Registry is missing schema_version."))
    if not systems:
        failures.append(_failure("missing_systems", "Registry must define at least one system."))
    if not checks:
        failures.append(_failure("missing_checks", "Registry must define at least one check."))

    for system in systems:
        system_id = str(system.get("system_id") or "").strip()
        if not system_id:
            failures.append(_failure("missing_system_id", "A registry system is missing system_id."))
            continue
        for field in (
            "path_patterns",
            "durable_contracts",
            "allowed_to_churn",
            "unrelated_surfaces_expected_stable",
        ):
            if not list(system.get(field) or []):
                failures.append(
                    _failure(
                        "incomplete_system",
                        f"System {system_id} is missing non-empty {field}.",
                        system_id=system_id,
                        field=field,
                    )
                )

    checks_by_system: dict[str, list[dict[str, Any]]] = {}
    for check in checks:
        check_id = str(check.get("check_id") or "").strip()
        system_id = str(check.get("system_id") or "").strip()
        category = str(check.get("category") or "").strip()
        if not check_id:
            failures.append(_failure("missing_check_id", "A registry check is missing check_id."))
        if system_id not in system_ids:
            failures.append(
                _failure(
                    "unknown_check_system",
                    f"Check {check_id or '<missing>'} references unknown system {system_id or '<missing>'}.",
                    check_id=check_id,
                    system_id=system_id,
                )
            )
        if category not in VALID_CHECK_CATEGORIES:
            failures.append(
                _failure(
                    "invalid_check_category",
                    f"Check {check_id or '<missing>'} has invalid category {category or '<missing>'}.",
                    check_id=check_id,
                    category=category,
                )
            )
        if not str(check.get("command") or "").strip():
            failures.append(
                _failure(
                    "missing_check_command",
                    f"Check {check_id or '<missing>'} is missing command.",
                    check_id=check_id,
                )
            )
        checks_by_system.setdefault(system_id, []).append(check)

    for system_id in sorted(system_ids):
        if not system_id:
            continue
        owned_checks = checks_by_system.get(system_id) or []
        if not owned_checks:
            failures.append(
                _failure(
                    "missing_system_check",
                    f"System {system_id} has no mapped check.",
                    system_id=system_id,
                )
            )
            continue
        if not any(str(check.get("category") or "") == "meta_check" for check in owned_checks):
            failures.append(
                _failure(
                    "missing_system_meta_check",
                    f"System {system_id} has no mapped meta_check.",
                    system_id=system_id,
                )
            )
        if not any(bool(check.get("blocking")) for check in owned_checks):
            warnings.append(
                _failure(
                    "nonblocking_system_checks",
                    f"System {system_id} has no blocking checks.",
                    system_id=system_id,
                )
            )

    return failures, warnings


def _system_matches_path(system: dict[str, Any], path: str) -> bool:
    return any(fnmatch.fnmatch(path, str(pattern)) for pattern in list(system.get("path_patterns") or []))


def _affected_systems(registry: dict[str, Any], changed_paths: Iterable[str]) -> list[dict[str, Any]]:
    affected: list[dict[str, Any]] = []
    for system in list(registry.get("systems") or []):
        matched = sorted({path for path in changed_paths if _system_matches_path(system, path)})
        if not matched:
            continue
        affected.append(
            {
                "system_id": system.get("system_id"),
                "description": system.get("description"),
                "matched_paths": matched,
                "required_regression_tier": system.get("required_regression_tier"),
            }
        )
    return affected


def _checks_for_systems(registry: dict[str, Any], system_ids: set[str]) -> list[dict[str, Any]]:
    return [
        check
        for check in list(registry.get("checks") or [])
        if str(check.get("system_id") or "").strip() in system_ids
    ]


def _validate_packet(packet: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if not packet.get("system_changed") and not packet.get("systems_changed"):
        failures.append(
            _failure(
                "missing_packet_field",
                "Change-admission packet is missing system_changed or systems_changed.",
                field="system_changed",
            )
        )
    for field in REQUIRED_PACKET_FIELDS:
        value = packet.get(field)
        if value is None or value == "" or value == []:
            failures.append(
                _failure(
                    "missing_packet_field",
                    f"Change-admission packet is missing {field}.",
                    field=field,
                )
            )
    return failures


def evaluate_change_admission(
    *,
    registry_path: Path = DEFAULT_REGISTRY,
    changed_paths: Iterable[str] = (),
    packet_path: Path | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    registry = load_json(registry_path)
    normalized_paths = [normalize_path(path) for path in changed_paths if normalize_path(path)]
    failures, warnings = validate_registry(registry)
    affected = _affected_systems(registry, normalized_paths)
    affected_ids = {str(system.get("system_id") or "") for system in affected}
    affected_checks = _checks_for_systems(registry, affected_ids)

    matched_paths = {path for system in affected for path in list(system.get("matched_paths") or [])}
    for path in normalized_paths:
        if path in matched_paths:
            continue
        if is_heavy_gate_path(path):
            failures.append(
                _failure(
                    "unmapped_changed_path",
                    f"Regression-bearing path {path} is not mapped to a check-registry system.",
                    path=path,
                )
            )

    if packet_path is not None:
        if not packet_path.exists():
            failures.append(
                _failure(
                    "missing_packet",
                    f"Change-admission packet does not exist: {packet_path}",
                    packet=str(packet_path),
                )
            )
        else:
            failures.extend(_validate_packet(load_json(packet_path)))

    required_meta_checks = [
        {
            "check_id": check.get("check_id"),
            "system_id": check.get("system_id"),
            "command": check.get("command"),
            "blocking": check.get("blocking"),
            "when_required": check.get("when_required"),
        }
        for check in affected_checks
        if str(check.get("category") or "") == "meta_check"
    ]
    durable_contracts = []
    allowed_churn = []
    for system in list(registry.get("systems") or []):
        if str(system.get("system_id") or "") not in affected_ids:
            continue
        durable_contracts.extend(str(item) for item in list(system.get("durable_contracts") or []))
        allowed_churn.extend(str(item) for item in list(system.get("allowed_to_churn") or []))

    tier_order = {
        "tier0": 0,
        "tier1": 1,
        "tier1_or_higher": 1,
        "tier0_and_tier1": 1,
        "tier2": 2,
        "tier3": 3,
    }
    tiers = [str(system.get("required_regression_tier") or "") for system in affected]
    required_tier = "none"
    if tiers:
        required_tier = max(tiers, key=lambda tier: tier_order.get(tier, -1))

    if strict and normalized_paths and not affected and not failures:
        failures.append(
            _failure(
                "no_affected_system",
                "Strict mode requires at least one affected system for changed paths.",
            )
        )

    verdict = "fail" if failures else "pass"
    return {
        "verdict": verdict,
        "schema_version": registry.get("schema_version"),
        "checked_paths": normalized_paths,
        "affected_systems": affected,
        "durable_contracts_expected_stable": sorted(set(durable_contracts)),
        "allowed_churn": sorted(set(allowed_churn)),
        "required_meta_checks": required_meta_checks,
        "required_regression_tier": required_tier,
        "failures": failures,
        "warnings": warnings,
        "next_blocker": "resolve_change_admission_failures" if failures else "none",
    }


def render_markdown(result: dict[str, Any]) -> str:
    affected = list(result.get("affected_systems") or [])
    failures = list(result.get("failures") or [])
    warnings = list(result.get("warnings") or [])
    lines = [
        "# Change Admission",
        "",
        f"- Verdict: `{result.get('verdict')}`",
        f"- Required regression tier: `{result.get('required_regression_tier')}`",
        f"- Affected systems: `{len(affected)}`",
        f"- Next blocker: `{result.get('next_blocker')}`",
        "",
        "## Affected Systems",
        "",
    ]
    if affected:
        for system in affected:
            lines.append(
                f"- `{system.get('system_id')}` tier=`{system.get('required_regression_tier')}` "
                f"paths=`{', '.join(str(path) for path in list(system.get('matched_paths') or []))}`"
            )
    else:
        lines.append("- `none`")

    lines.extend(["", "## Required Meta-Checks", ""])
    meta_checks = list(result.get("required_meta_checks") or [])
    if meta_checks:
        for check in meta_checks:
            lines.append(f"- `{check.get('check_id')}`: `{check.get('command')}`")
    else:
        lines.append("- `none`")

    lines.extend(["", "## Failures", ""])
    if failures:
        for failure in failures:
            lines.append(f"- `{failure.get('code')}`: {failure.get('message')}")
    else:
        lines.append("- `none`")

    lines.extend(["", "## Warnings", ""])
    if warnings:
        for warning in warnings:
            lines.append(f"- `{warning.get('code')}`: {warning.get('message')}")
    else:
        lines.append("- `none`")
    return "\n".join(lines) + "\n"


def write_outputs(
    result: dict[str, Any],
    *,
    output_json: Path | None = None,
    output_md: Path | None = None,
    github_output: Path | None = None,
) -> None:
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if output_md is not None:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_markdown(result), encoding="utf-8")
    if github_output is not None:
        github_output.parent.mkdir(parents=True, exist_ok=True)
        with github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"change_admission_verdict={result.get('verdict')}\n")
            handle.write(f"affected_system_count={len(list(result.get('affected_systems') or []))}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate change-admission coverage for changed paths.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--paths-file", type=Path, default=None)
    parser.add_argument("--packet", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    parser.add_argument("--github-output", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    result = evaluate_change_admission(
        registry_path=args.registry,
        changed_paths=load_paths(args.paths_file),
        packet_path=args.packet,
        strict=args.strict,
    )
    write_outputs(
        result,
        output_json=args.output_json,
        output_md=args.output_md,
        github_output=args.github_output,
    )
    print(json.dumps(result, indent=2))
    return 1 if result["verdict"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
