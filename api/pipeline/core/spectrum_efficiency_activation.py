from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
SPECTRUM_EFFICIENCY_SUITE_ID = "spectrum_efficiency_activation_suite"
SPECTRUM_EFFICIENCY_CASE_ID = "activation-v1"
SPECTRUM_EFFICIENCY_FIXTURE_ROOT = (
    REPO_ROOT / "tests" / "fixtures" / "spectrum_efficiency_activation_suite"
)
SPECTRUM_EFFICIENCY_PACKAGE_MANIFEST = (
    SPECTRUM_EFFICIENCY_FIXTURE_ROOT / "package_manifest.json"
)
SPECTRUM_EFFICIENCY_TRUTH_MANIFEST = (
    SPECTRUM_EFFICIENCY_FIXTURE_ROOT / "truth_manifest.json"
)
SPECTRUM_EFFICIENCY_BENCHMARK_PROTOCOL = (
    SPECTRUM_EFFICIENCY_FIXTURE_ROOT / "benchmark_protocol.json"
)

SUCCESS_LIKE_STATUSES = {
    "success",
    "verified_success",
    "functional",
    "functional_precondition_unmet",
    "inferred_success",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compiled_spectrum_efficiency_fixture_root() -> Path:
    return SPECTRUM_EFFICIENCY_FIXTURE_ROOT


def load_spectrum_efficiency_package_manifest() -> dict[str, Any]:
    return _load_json(SPECTRUM_EFFICIENCY_PACKAGE_MANIFEST)


def load_spectrum_efficiency_truth_manifest() -> dict[str, Any]:
    return _load_json(SPECTRUM_EFFICIENCY_TRUTH_MANIFEST)


def load_spectrum_efficiency_benchmark_protocol() -> dict[str, Any]:
    return _load_json(SPECTRUM_EFFICIENCY_BENCHMARK_PROTOCOL)


def _resolve_repo_path(relative_path: str) -> Path:
    return (REPO_ROOT / str(relative_path or "").strip()).resolve()


def ensure_spectrum_efficiency_package_built() -> dict[str, Any]:
    manifest = load_spectrum_efficiency_package_manifest()
    bundled = list(manifest.get("bundled_dlls") or [])
    if bundled and all(_resolve_repo_path(str(item.get("source_path") or "")).exists() for item in bundled):
        return manifest

    build_script = compiled_spectrum_efficiency_fixture_root() / "build-package.ps1"
    subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(build_script)],
        cwd=str(REPO_ROOT),
        check=True,
    )
    return load_spectrum_efficiency_package_manifest()


def _selected_targets_by_name(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for item in list(manifest.get("selected_runtime_targets") or []):
        target_name = str(item.get("target_name") or "").strip()
        if target_name:
            lookup[target_name] = dict(item)
    return lookup


def _resolve_targets(
    manifest: dict[str, Any],
    protocol_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected_lookup = _selected_targets_by_name(manifest)
    resolved: list[dict[str, Any]] = []
    for entry in protocol_entries:
        target_name = str(entry.get("target_name") or "").strip()
        manifest_item = dict(selected_lookup.get(target_name) or {})
        merged = dict(manifest_item)
        merged.update(dict(entry))
        resolved.append(merged)
    return resolved


def ordered_spectrum_efficiency_pass_one_targets(
    manifest: dict[str, Any] | None = None,
    protocol: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return _resolve_targets(
        manifest or load_spectrum_efficiency_package_manifest(),
        list((protocol or load_spectrum_efficiency_benchmark_protocol()).get("pass_one_targets") or []),
    )


def ordered_spectrum_efficiency_pass_two_targets(
    manifest: dict[str, Any] | None = None,
    protocol: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return _resolve_targets(
        manifest or load_spectrum_efficiency_package_manifest(),
        list((protocol or load_spectrum_efficiency_benchmark_protocol()).get("pass_two_targets") or []),
    )


def ordered_spectrum_efficiency_false_positive_targets(
    manifest: dict[str, Any] | None = None,
    protocol: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return _resolve_targets(
        manifest or load_spectrum_efficiency_package_manifest(),
        list((protocol or load_spectrum_efficiency_benchmark_protocol()).get("false_positive_frontier") or []),
    )


def build_activation_plan(
    *,
    protocol: dict[str, Any],
    phase: str,
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    deferred_targets = [str(item) for item in list(protocol.get("deferred_targets") or []) if str(item).strip()]
    false_positive = [
        str(item.get("target_name") or "").strip()
        for item in list(protocol.get("false_positive_frontier") or [])
        if str(item.get("target_name") or "").strip()
    ]
    return {
        "suite_id": SPECTRUM_EFFICIENCY_SUITE_ID,
        "case_id": SPECTRUM_EFFICIENCY_CASE_ID,
        "phase": phase,
        "active_floor": "Floor 2: Selective Deepening" if phase == "pass_one" else "Floor 3: Second-Pass Reuse",
        "chosen_frontier": [
            {
                "target_name": str(item.get("target_name") or ""),
                "staged_name": str(item.get("staged_name") or ""),
                "primary_export": str(item.get("primary_export") or ""),
                "predecessor_targets": list(item.get("predecessor_targets") or []),
            }
            for item in targets
        ],
        "deferred_surfaces": deferred_targets if phase == "pass_one" else [],
        "visible_false_positive_frontier": false_positive,
        "rationale": (
            "Pass one is bounded to the minimum frontier that can produce a useful operational map."
            if phase == "pass_one"
            else "Pass two expands only to newly justified surfaces using pass-one outputs and trusted predecessor jobs."
        ),
    }


def build_package_inventory(
    *,
    manifest: dict[str, Any],
    truth_manifest: dict[str, Any],
) -> dict[str, Any]:
    roles_by_name = {
        str(item.get("dll_name") or "").strip(): str(item.get("role") or "").strip()
        for item in list(truth_manifest.get("dlls") or [])
    }
    return {
        "suite_id": SPECTRUM_EFFICIENCY_SUITE_ID,
        "case_id": SPECTRUM_EFFICIENCY_CASE_ID,
        "admitted_modules": [
            {
                "staged_name": str(item.get("staged_name") or ""),
                "target_name": str(item.get("target_name") or ""),
                "role": roles_by_name.get(str(item.get("staged_name") or "").strip(), str(item.get("benchmark_group") or "")),
                "primary_export": str(item.get("primary_export") or ""),
            }
            for item in list(manifest.get("selected_runtime_targets") or [])
        ],
        "rejected_noise_items": [],
    }


def build_operator_useful_map(
    *,
    protocol: dict[str, Any],
    pass_one_records: list[dict[str, Any]],
) -> dict[str, Any]:
    completed_targets = [
        {
            "target_name": str(record.get("target") or ""),
            "job_id": str(record.get("job_id") or ""),
            "status": str(record.get("status") or ""),
            "primary_export": str((record.get("chain_context") or {}).get("required_semantic_checkpoint") or ""),
        }
        for record in pass_one_records
    ]
    successful = [
        item["target_name"]
        for item in completed_targets
        if str(item.get("status") or "").strip().lower() == "ok"
    ]
    return {
        "suite_id": SPECTRUM_EFFICIENCY_SUITE_ID,
        "case_id": SPECTRUM_EFFICIENCY_CASE_ID,
        "operator_useful_map_ready": len(successful) == len(list(protocol.get("pass_one_targets") or [])),
        "what_matters_now": successful,
        "next_frontier": [str(item) for item in list(protocol.get("deferred_targets") or []) if str(item).strip()],
        "false_positive_frontier": [
            str(item.get("target_name") or "").strip()
            for item in list(protocol.get("false_positive_frontier") or [])
            if str(item.get("target_name") or "").strip()
        ],
        "late_truth_targets": [str(item) for item in list(protocol.get("late_truth_targets") or []) if str(item).strip()],
        "completed_frontier": completed_targets,
    }


def build_pass_two_reuse_report(
    *,
    pass_one_plan_path: Path,
    operator_useful_map_path: Path,
    pass_one_records: list[dict[str, Any]],
    pass_two_records: list[dict[str, Any]],
) -> dict[str, Any]:
    reused_job_ids = []
    for record in pass_two_records:
        chain_context = dict(record.get("chain_context") or {})
        reused_job_ids.append(
            {
                "target_name": str(record.get("target") or ""),
                "prior_job_id": str(chain_context.get("prior_job_id") or ""),
                "cross_dll_prior_job_ids": list(chain_context.get("cross_dll_prior_job_ids") or []),
            }
        )

    return {
        "suite_id": SPECTRUM_EFFICIENCY_SUITE_ID,
        "case_id": SPECTRUM_EFFICIENCY_CASE_ID,
        "reused_outputs": [
            {
                "artifact": "activation-plan-pass-one.json",
                "path": str(pass_one_plan_path),
                "trust_basis": "compiled protocol and first-pass bounded frontier",
            },
            {
                "artifact": "operator-useful-map.json",
                "path": str(operator_useful_map_path),
                "trust_basis": "first-pass machine-readable map emitted before pass-two expansion",
            },
        ],
        "reused_prior_jobs": reused_job_ids,
        "what_was_reused_unchanged": [
            "admitted package inventory",
            "frontier ranking",
            "explicit deferrals",
        ],
        "what_was_invalidated": [],
        "pass_one_job_count": len(pass_one_records),
        "pass_two_job_count": len(pass_two_records),
    }


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_invocable_names(run_dir: Path) -> list[str]:
    analyze_status = _read_json(run_dir / "job-status-analyze.json", {})
    invocables = list((analyze_status.get("result") or {}).get("invocables") or [])
    return sorted(str(item.get("name") or "").strip() for item in invocables if item.get("name"))


def _is_success_like_status(status: Any) -> bool:
    return str(status or "").strip().lower() in SUCCESS_LIKE_STATUSES


def build_spectrum_efficiency_activation_report(
    *,
    output_dir: Path,
    package_manifest: dict[str, Any],
    truth_manifest: dict[str, Any],
    protocol: dict[str, Any],
    pass_one_records: list[dict[str, Any]],
    pass_two_records: list[dict[str, Any]],
) -> dict[str, Any]:
    pass_one_targets = ordered_spectrum_efficiency_pass_one_targets(package_manifest, protocol)
    pass_two_targets = ordered_spectrum_efficiency_pass_two_targets(package_manifest, protocol)
    false_positive_targets = ordered_spectrum_efficiency_false_positive_targets(package_manifest, protocol)

    per_run: list[dict[str, Any]] = []
    discovered_primary_exports: list[str] = []
    semantic_primary_exports: list[str] = []
    false_positive_names = {str(item.get("target_name") or "").strip() for item in false_positive_targets}

    for record in [*pass_one_records, *pass_two_records]:
        run_dir = Path(str(record.get("run_dir") or "")).resolve()
        invocable_names = _read_invocable_names(run_dir)
        chain_context = dict(record.get("chain_context") or {})
        required_export = str(chain_context.get("required_semantic_checkpoint") or "").strip()
        latest_status_map = dict(record.get("latest_status_map") or {})
        export_discovered = required_export in invocable_names
        export_verified = _is_success_like_status(latest_status_map.get(required_export))
        if export_discovered and required_export and required_export not in discovered_primary_exports:
            discovered_primary_exports.append(required_export)
        if export_verified and required_export and required_export not in semantic_primary_exports:
            semantic_primary_exports.append(required_export)
        per_run.append(
            {
                "target_name": str(record.get("target") or ""),
                "dll_name": str(record.get("dll_name") or ""),
                "job_id": str(record.get("job_id") or ""),
                "status": str(record.get("status") or ""),
                "phase": "pass_one"
                if str(record.get("target") or "").strip()
                in {str(item.get("target_name") or "").strip() for item in pass_one_targets}
                else "pass_two",
                "required_primary_export": required_export,
                "discovered_invocables": invocable_names,
                "primary_export_discovered": export_discovered,
                "primary_export_verified": export_verified,
                "cross_dll_prior_job_ids": list(chain_context.get("cross_dll_prior_job_ids") or []),
            }
        )

    pass_one_duration = round(sum(float(record.get("duration_sec") or 0.0) for record in pass_one_records), 2)
    false_positive_probed = [
        str(record.get("target") or "").strip()
        for record in [*pass_one_records, *pass_two_records]
        if str(record.get("target") or "").strip() in false_positive_names
    ]
    pass_two_reused = [
        record
        for record in pass_two_records
        if list((record.get("chain_context") or {}).get("cross_dll_prior_job_ids") or [])
    ]

    metrics = {
        "time_to_useful_map": pass_one_duration,
        "surfaces_deeply_probed_pass_one": len(pass_one_records),
        "surfaces_deeply_probed_pass_two": len(pass_two_records),
        "deferred_surface_count": len(list(protocol.get("deferred_targets") or [])),
        "reuse_success_rate": round(
            (len([record for record in pass_two_reused if str(record.get("status") or "").strip().lower() == "ok"]) / len(pass_two_records))
            if pass_two_records
            else 0.0,
            4,
        ),
        "wasted_deep_probe_count": len(false_positive_probed),
    }

    return {
        "schema_version": "1.0.0",
        "suite_id": SPECTRUM_EFFICIENCY_SUITE_ID,
        "case_id": SPECTRUM_EFFICIENCY_CASE_ID,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "output_dir": str(output_dir),
        "compiled_fixture_root": str(compiled_spectrum_efficiency_fixture_root()),
        "package_manifest": str(SPECTRUM_EFFICIENCY_PACKAGE_MANIFEST),
        "truth_manifest": str(SPECTRUM_EFFICIENCY_TRUTH_MANIFEST),
        "benchmark_protocol": str(SPECTRUM_EFFICIENCY_BENCHMARK_PROTOCOL),
        "pass_one_targets": [str(item.get("target_name") or "") for item in pass_one_targets],
        "pass_two_targets": [str(item.get("target_name") or "") for item in pass_two_targets],
        "deferred_targets": [str(item) for item in list(protocol.get("deferred_targets") or []) if str(item).strip()],
        "false_positive_frontier": [str(item.get("target_name") or "") for item in false_positive_targets],
        "late_truth_targets": [str(item) for item in list(protocol.get("late_truth_targets") or []) if str(item).strip()],
        "operator_useful_map_ready": len(pass_one_records) == len(pass_one_targets)
        and all(str(record.get("status") or "").strip().lower() == "ok" for record in pass_one_records),
        "pass_two_reuse_not_restart": all(
            list((record.get("chain_context") or {}).get("cross_dll_prior_job_ids") or [])
            for record in pass_two_records
        ),
        "false_positive_frontier_respected": not false_positive_probed,
        "late_truth_surface_present": "settlement_reconcile" in [str(item) for item in list(protocol.get("late_truth_targets") or [])],
        "discovered_primary_exports": discovered_primary_exports,
        "semantic_primary_exports": semantic_primary_exports,
        "metrics": metrics,
        "per_run": per_run,
        "comparison_note": (
            "bounded first-pass activation and pass-two reuse executed without probing the false-positive frontier"
            if not false_positive_probed
            else "false-positive frontier was probed and the benchmark lost activation discipline"
        ),
    }
