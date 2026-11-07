from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from api.pipeline.core.reduced_package_decomposition_proof import run_reduced_package_decomposition_proof


STRESS_PACKAGE_DECOMPOSITION_PROOF_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class StressScenario:
    label: str
    package_input: dict[str, Any]
    candidate_hints_by_shard: dict[int | str, list[dict[str, Any]]] | None = None
    target_shard_width: int = 2
    max_slice_dlls: int = 3
    expected_proof_status: str = "pass"
    expected_contradiction_hotspots_min: int = 0
    expected_deferred_groups_min: int = 0
    expected_slice_count_min: int = 1
    expected_budget_breach_count_min: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _write_json(output_dir: Path, name: str, payload: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_stress_package_decomposition_proof(
    *,
    scenarios: list[StressScenario],
    output_dir: str | None = None,
) -> dict[str, Any]:
    scenario_reports: list[dict[str, Any]] = []

    for scenario in scenarios:
        proof_output = run_reduced_package_decomposition_proof(
            scenario.package_input,
            candidate_hints_by_shard=scenario.candidate_hints_by_shard,
            target_shard_width=scenario.target_shard_width,
            max_slice_dlls=scenario.max_slice_dlls,
            output_dir=None,
        )
        proof_summary = dict(proof_output.get("proof_summary") or {})
        inspection_surface = dict(proof_output.get("inspection_surface") or {})
        dashboard = dict(inspection_surface.get("decomposition_dashboard") or {})
        merge_ambiguity = dict(inspection_surface.get("merge_ambiguity_report") or {})
        frontier_slice_plan = dict(proof_output.get("frontier_slice_plan") or {})
        shard_plan = dict(proof_output.get("shard_plan") or {})

        contradiction_hotspots = list(merge_ambiguity.get("ambiguity_hotspots") or [])
        deferred_group_count = len(list(frontier_slice_plan.get("deferred_initialization_group_ids") or [])) + len(
            list(frontier_slice_plan.get("deferred_dependency_class_ids") or [])
        )
        slice_count = int(len(list(frontier_slice_plan.get("frontier_slices") or [])))
        budget_breach_count = int(shard_plan.get("budget_breach_count") or 0)

        checks = {
            "proof_status_expected": {
                "expected": scenario.expected_proof_status,
                "actual": str(proof_summary.get("status") or ""),
                "ok": str(proof_summary.get("status") or "") == scenario.expected_proof_status,
            },
            "contradiction_hotspots_min": {
                "expected": int(scenario.expected_contradiction_hotspots_min),
                "actual": len(contradiction_hotspots),
                "ok": len(contradiction_hotspots) >= int(scenario.expected_contradiction_hotspots_min),
            },
            "deferred_groups_min": {
                "expected": int(scenario.expected_deferred_groups_min),
                "actual": deferred_group_count,
                "ok": deferred_group_count >= int(scenario.expected_deferred_groups_min),
            },
            "slice_count_min": {
                "expected": int(scenario.expected_slice_count_min),
                "actual": slice_count,
                "ok": slice_count >= int(scenario.expected_slice_count_min),
            },
            "budget_breach_count_min": {
                "expected": int(scenario.expected_budget_breach_count_min),
                "actual": budget_breach_count,
                "ok": budget_breach_count >= int(scenario.expected_budget_breach_count_min),
            },
        }

        scenario_reports.append(
            {
                "label": scenario.label,
                "proof_summary": proof_summary,
                "observer_verdict_summary": dict(dashboard.get("observer_verdict_summary") or {}),
                "contradiction_hotspots": contradiction_hotspots,
                "contradiction_hotspot_count": len(contradiction_hotspots),
                "deferred_initialization_group_ids": list(frontier_slice_plan.get("deferred_initialization_group_ids") or []),
                "deferred_dependency_class_ids": list(frontier_slice_plan.get("deferred_dependency_class_ids") or []),
                "budget_breach_count": budget_breach_count,
                "slice_count": slice_count,
                "checks": checks,
                "scenario_passed": all(bool(item.get("ok")) for item in checks.values()),
            }
        )

    result = {
        "schema_version": STRESS_PACKAGE_DECOMPOSITION_PROOF_SCHEMA_VERSION,
        "scenario_count": len(scenarios),
        "scenario_reports": scenario_reports,
        "status": "pass" if all(report["scenario_passed"] for report in scenario_reports) else "fail",
    }

    if output_dir:
        output_path = Path(output_dir)
        _write_json(output_path, "stress-proof-suite.json", result)
        for report in scenario_reports:
            _write_json(output_path, f"stress-scenario-{report['label']}.json", report)

    return result
