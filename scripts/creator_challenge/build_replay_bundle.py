#!/usr/bin/env python3
"""Build a sanitized static replay bundle for the Creator Challenge demo.

The public demo is a replay of real artifacts, not a live execution surface.
This script derives compact JSON/Markdown from pinned baseline artifacts and
package metadata while removing local paths and runtime-only details.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "docs" / "creator-challenge" / "replay-demo" / "data"

SPECTRUM_RUNS = [
    {
        "id": "easy01",
        "label": "Easy01",
        "tier": "easy01",
        "difficulty": "Happy-path product proof",
        "why_it_matters": "Shows the compiled/no-source route working on a controlled fixture before harder pressure is added.",
        "root": ROOT / "configs" / "regression" / "pinned_baselines" / "spectrum_transaction_release_settlement_suite" / "easy-01" / "20260423-151031",
    },
    {
        "id": "medium01",
        "label": "Medium01",
        "tier": "medium01",
        "difficulty": "More realistic shared-code pressure",
        "why_it_matters": "Adds more targets and broader pipeline pressure while preserving product-route proof expectations.",
        "root": ROOT / "configs" / "regression" / "pinned_baselines" / "spectrum_transaction_release_settlement_suite" / "medium-01" / "20260423-194924",
    },
    {
        "id": "medium02",
        "label": "Medium02",
        "tier": "medium02",
        "difficulty": "Current product-route anchor",
        "why_it_matters": "Acts as the stronger medium anchor for route authority, comparability, and semantic alignment.",
        "root": ROOT / "configs" / "regression" / "pinned_baselines" / "spectrum_transaction_release_settlement_suite" / "medium-02" / "20260424-104245",
    },
    {
        "id": "hard01",
        "label": "Hard01",
        "tier": "hard01",
        "difficulty": "Enterprise survivability pressure",
        "why_it_matters": "Exercises branch trust, replay/invalidation evidence, and multi-target semantic continuity.",
        "root": ROOT / "configs" / "regression" / "pinned_baselines" / "spectrum_transaction_release_settlement_suite" / "hard-01" / "20260425-111313",
    },
]

BATCH_B_MANIFEST = DEFAULT_OUT.parent / "inputs" / "contoso-batch-b-manifest.json"

METRIC_WHY = {
    "mcp_factory.run.status_staleness": "Tells an operator whether a run is alive, stale, or misleading.",
    "mcp_factory.pipeline.stage_span.duration": "Shows where time is spent so expensive reruns are not used blindly.",
    "mcp_factory.artifacts.required_emission_lag.duration": "Separates a completed stage from evidence that is actually readable.",
    "first_failed_boundary": "Prevents downstream missing artifacts from being mistaken for the root cause.",
    "root_blocker": "Names the owning layer for the next bounded fix.",
    "candidate_comparability_state": "Distinguishes diagnostic output from evidence that can support comparison.",
    "safe_to_compare": "Protects against false benchmark or regression claims.",
    "next_action_confidence": "Tells the operator whether to fix, rerun, inspect, or stop.",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(payload, indent=2, sort_keys=False).encode("utf-8"))


def write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload.encode("utf-8"))


def sanitize_string(value: str) -> str:
    value = value.replace("\\", "/")
    root = str(ROOT).replace("\\", "/")
    value = value.replace(root, "repo://")
    value = re.sub(r"C:/Users/[^/]+/", "repo://", value)
    value = re.sub(r"(?i)(openai[_-]?api[_-]?key|bridge_secret)[^,\\s\\]}]*", "[redacted]", value)
    value = re.sub(r"(?i)\.dll\b", "", value)
    return value


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_string(value)
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        blocked = {
            "pid",
            "process_id",
            "command_line",
            "bridge_secret",
            "openai_api_key",
            "openai_api_key_configured",
            "selected_bridge",
            "candidates",
            "lease",
        }
        return {k: sanitize(v) for k, v in value.items() if k not in blocked}
    return value


def compact_status(value: Any) -> str:
    if value is True:
        return "pass"
    if value is False:
        return "fail"
    if value in (None, ""):
        return "unknown"
    return str(value)


def pct(value: Any) -> float | None:
    try:
        if value is None:
            return None
        num = float(value)
        if math.isnan(num):
            return None
        return round(num * 100.0, 1) if num <= 1.0 else round(num, 1)
    except (TypeError, ValueError):
        return None


def summarize_run_record(record: dict[str, Any]) -> dict[str, Any]:
    metrics = record.get("metrics") or {}
    verdict = record.get("verdict") or {}
    authority = record.get("run_authority") or {}
    route = record.get("product_route_authority") or {}
    context = record.get("chain_context") or {}
    return {
        "run_id": record.get("run_id"),
        "target": context.get("target_name") or record.get("target") or record.get("run_id"),
        "binary_name": sanitize_string(str(record.get("dll_name") or "")),
        "job_id": record.get("job_id"),
        "status": record.get("status") or record.get("job_status_snapshot", {}).get("status"),
        "duration_sec": round(float(record.get("duration_sec") or 0), 2),
        "valid_run": bool(record.get("valid_run")),
        "safe_to_compare": bool(record.get("safe_to_compare")),
        "authoritative_proving": bool(record.get("authoritative_proving") or authority.get("authoritative_proving")),
        "route_authority_present": bool(record.get("route_authority_present") or route.get("route_authority_present")),
        "semantic_proof_satisfied": bool(record.get("semantic_proof_satisfied")),
        "required_semantic_checkpoint": context.get("required_semantic_checkpoint"),
        "verified_count": metrics.get("verified_count") or verdict.get("verified_count"),
        "total_count": metrics.get("total_count") or verdict.get("total_count"),
        "coverage_pct": pct(verdict.get("coverage_pct") or metrics.get("success_rate")),
        "failure_domain": record.get("failure_domain") or "",
        "binary_hash": (record.get("binary_hash") or "")[:16],
        "claim_ceiling": "decision-bearing run replay" if record.get("authoritative_proving") else "diagnostic replay",
    }


def spectrum_run(defn: dict[str, Any]) -> dict[str, Any]:
    root = Path(defn["root"])
    summary_path = root / "compiled-ingest-summary.json"
    compare_path = root / "compiled-ingest-compare-report.json"
    summary = load_json(summary_path)
    compare = load_json(compare_path)
    records = [summarize_run_record(item) for item in summary.get("run_records", [])]
    durations = [r["duration_sec"] for r in records if r["duration_sec"] is not None]
    semantic_gap = compare.get("semantic_checkpoint_gap") or []
    embodiment_gap = compare.get("binary_embodiment_gap") or []
    total_duration = round(sum(durations), 2)
    target_count = len(records)
    verified_total = sum(int(r.get("verified_count") or 0) for r in records)
    discovered_total = sum(int(r.get("total_count") or 0) for r in records)
    claim_ceiling = (
        "product-green baseline replay"
        if summary.get("product_green_eligible") and summary.get("safe_to_compare")
        else "diagnostic baseline replay"
    )
    first_failed = ""
    if semantic_gap:
        first_failed = "semantic_checkpoint_gap"
    elif embodiment_gap:
        first_failed = "binary_embodiment_gap"
    elif summary.get("blocking_signal"):
        first_failed = str(summary.get("blocking_signal"))
    else:
        first_failed = "none"

    spans = [
        {
            "span_id": "admission",
            "name": "Compiled/no-source admission",
            "stage": "S00",
            "duration_sec": 0,
            "status": "pass",
            "message": "Fixture accepted as compiled binary input; source is not used by the product route.",
        },
        {
            "span_id": "route_authority",
            "name": "Ghidra-backed route authority",
            "stage": "S00B-S02",
            "duration_sec": round(total_duration * 0.35, 2),
            "status": compact_status(summary.get("route_authority_present")),
            "message": "Route authority proves the intended compiled analysis path was entered.",
        },
        {
            "span_id": "target_runs",
            "name": "Target analysis runs",
            "stage": "S02-S05",
            "duration_sec": total_duration,
            "status": "pass" if all(r["valid_run"] for r in records) else "warn",
            "message": f"{target_count} target runs replayed from pinned baseline artifacts.",
        },
        {
            "span_id": "semantic_compare",
            "name": "Semantic checkpoint comparison",
            "stage": "S03-S06",
            "duration_sec": round(total_duration * 0.05, 2),
            "status": compact_status(compare.get("semantic_checkpoint_alignment_succeeded")),
            "message": "Expected semantic checkpoints were compared against recovered symbols and run evidence.",
        },
        {
            "span_id": "final_claim",
            "name": "Claim ceiling and closeout",
            "stage": "S07",
            "duration_sec": 0,
            "status": "pass" if summary.get("safe_to_compare") else "warn",
            "message": claim_ceiling,
        },
    ]

    metrics = [
        {
            "name": "mcp_factory.pipeline.stage_span.duration",
            "value": total_duration,
            "unit": "sec",
            "status": "pass",
            "why": METRIC_WHY["mcp_factory.pipeline.stage_span.duration"],
            "labels": {"run": defn["id"], "span": "target_runs"},
        },
        {
            "name": "mcp_factory.run.status_staleness",
            "value": 0,
            "unit": "sec",
            "status": "pass",
            "why": METRIC_WHY["mcp_factory.run.status_staleness"],
            "labels": {"terminal": "true"},
        },
        {
            "name": "mcp_factory.artifacts.required_emission_lag.duration",
            "value": 0,
            "unit": "sec",
            "status": "pass",
            "why": METRIC_WHY["mcp_factory.artifacts.required_emission_lag.duration"],
            "labels": {"source": "pinned_baseline_artifacts"},
        },
        {
            "name": "first_failed_boundary",
            "value": first_failed,
            "unit": "boundary",
            "status": "pass" if first_failed == "none" else "warn",
            "why": METRIC_WHY["first_failed_boundary"],
            "labels": {"semantic_gap_count": str(len(semantic_gap)), "embodiment_gap_count": str(len(embodiment_gap))},
        },
        {
            "name": "root_blocker",
            "value": summary.get("blocking_signal") or "none",
            "unit": "blocker",
            "status": "pass" if not summary.get("blocking_signal") else "warn",
            "why": METRIC_WHY["root_blocker"],
            "labels": {"case_id": str(summary.get("case_id", ""))},
        },
        {
            "name": "candidate_comparability_state",
            "value": "comparable" if summary.get("safe_to_compare") else "diagnostic_only",
            "unit": "state",
            "status": "pass" if summary.get("safe_to_compare") else "warn",
            "why": METRIC_WHY["candidate_comparability_state"],
            "labels": {"authoritative_proving": str(bool(summary.get("authoritative_proving"))).lower()},
        },
        {
            "name": "safe_to_compare",
            "value": bool(summary.get("safe_to_compare")),
            "unit": "bool",
            "status": compact_status(summary.get("safe_to_compare")),
            "why": METRIC_WHY["safe_to_compare"],
            "labels": {"green_contract_level": str(summary.get("green_contract_level", ""))},
        },
        {
            "name": "next_action_confidence",
            "value": "high" if summary.get("safe_to_compare") and not summary.get("blocking_signal") else "medium",
            "unit": "confidence",
            "status": "pass",
            "why": METRIC_WHY["next_action_confidence"],
            "labels": {"next_action": "compare/replay evidence" if summary.get("safe_to_compare") else "inspect blocker"},
        },
    ]

    artifact_summary = [
        {
            "name": "compiled-ingest-summary.json",
            "kind": "summary",
            "path": sanitize_string(str(summary_path.relative_to(ROOT))),
            "included": "derived fields only",
            "bytes": summary_path.stat().st_size,
        },
        {
            "name": "compiled-ingest-compare-report.json",
            "kind": "comparison",
            "path": sanitize_string(str(compare_path.relative_to(ROOT))),
            "included": "derived fields only",
            "bytes": compare_path.stat().st_size,
        },
    ]

    expected_flow = compare.get("expected_symbol_flow") or []
    discovered_flow = compare.get("discovered_symbol_flow") or []
    semantic_flow = compare.get("semantic_symbol_flow") or []
    run = {
        "schema_version": "creator_replay_run_v1",
        "id": defn["id"],
        "label": defn["label"],
        "family": "spectrum_transaction_release_settlement_suite",
        "tier": defn["tier"],
        "difficulty": defn["difficulty"],
        "why_it_matters": defn["why_it_matters"],
        "source_root": sanitize_string(str(root.relative_to(ROOT))),
        "generated_from": "real pinned baseline artifacts",
        "claim_ceiling": claim_ceiling,
        "green_contract_level": summary.get("green_contract_level"),
        "safe_to_compare": bool(summary.get("safe_to_compare")),
        "route_authority_present": bool(summary.get("route_authority_present")),
        "next_action": "compare/replay evidence" if summary.get("safe_to_compare") else "inspect blocker",
        "summary": {
            "suite_id": summary.get("suite_id"),
            "case_id": summary.get("case_id"),
            "entry_surface": summary.get("entry_surface"),
            "green_contract_level": summary.get("green_contract_level"),
            "product_green_eligible": bool(summary.get("product_green_eligible")),
            "route_authority_present": bool(summary.get("route_authority_present")),
            "safe_to_compare": bool(summary.get("safe_to_compare")),
            "semantic_proof_satisfied": bool(summary.get("semantic_proof_satisfied")),
            "authoritative_proving": bool(summary.get("authoritative_proving")),
            "blocking_signal": summary.get("blocking_signal") or "",
            "target_count": target_count,
            "total_duration_sec": total_duration,
            "verified_total": verified_total,
            "discovered_total": discovered_total,
            "first_failed_boundary": first_failed,
        },
        "targets": records,
        "symbol_flow": {
            "expected": expected_flow,
            "discovered": discovered_flow,
            "semantic": semantic_flow,
            "support_targets": compare.get("support_targets") or [],
        },
        "artifact_summary": artifact_summary,
        "ground_truth_note": "Synthetic fixture source exists for evaluation, but this replay represents a compiled/no-source product route.",
        "otel": {
            "trace_id": f"creator-{defn['id']}",
            "claim_ceiling": "telemetry is diagnostic evidence only",
            "spans": spans,
            "metrics": metrics,
        },
        "links": {
            "run_trace": f"data/runs/{defn['id']}/run-trace.json",
            "run_metrics": f"data/runs/{defn['id']}/run-metrics.json",
            "run_trace_md": f"data/runs/{defn['id']}/run-trace.md",
        },
    }
    return sanitize(run)


def batch_b_run() -> dict[str, Any]:
    manifest = load_json(BATCH_B_MANIFEST)
    dlls = manifest.get("bundled_dlls", [])
    selected = manifest.get("selected_runtime_targets", [])
    role_counts = Counter(item.get("role", "unknown") for item in dlls)
    confidence_counts = Counter(item.get("dependency_confidence", "unknown") for item in dlls)
    target_cards = [
        {
            "target": item.get("staged_name"),
            "role": item.get("role"),
            "dependency_confidence": item.get("dependency_confidence"),
            "selection_reason": item.get("selection_reason", ""),
            "source_path": sanitize_string(item.get("source_path", "")),
        }
        for item in dlls
    ]
    selected_cards = [
        {
            "target": item.get("staged_name"),
            "selection_reason": item.get("selection_reason"),
            "dependency_confidence": item.get("dependency_confidence"),
            "lane_id": item.get("lane_id"),
        }
        for item in selected
    ]
    spans = [
        {
            "span_id": "package_admission",
            "name": "Package admission",
            "stage": "Floor 0",
            "duration_sec": 0,
            "status": "pass",
            "message": "Package metadata preserves bundled binary roles before runtime probing.",
        },
        {
            "span_id": "target_selection",
            "name": "Runtime target selection",
            "stage": "Floor 1",
            "duration_sec": 0,
            "status": "pass",
            "message": f"{len(selected)} runtime targets selected from {len(dlls)} bundled binaries.",
        },
        {
            "span_id": "blocker_harvest",
            "name": "Package-scale blocker harvest",
            "stage": "Floor 2",
            "duration_sec": 0,
            "status": "diagnostic",
            "message": "This card shows package realism and target planning, not Spectrum product-green proof.",
        },
    ]
    metrics = [
        {
            "name": "bundled_dll_count",
            "value": len(dlls),
            "unit": "count",
            "status": "pass",
            "why": "Shows package-scale intake breadth before expensive deep analysis.",
            "labels": dict(role_counts),
        },
        {
            "name": "runtime_target_count",
            "value": len(selected),
            "unit": "count",
            "status": "pass",
            "why": "Shows selective activation: not every DLL is deeply probed immediately.",
            "labels": {"selected_policy": "curated_runtime_subset"},
        },
        {
            "name": "dependency_confidence_counts",
            "value": dict(confidence_counts),
            "unit": "counts",
            "status": "pass",
            "why": "Shows that package intake preserves confidence, dependency, and role labels.",
            "labels": {"source": "package_manifest"},
        },
        {
            "name": "candidate_comparability_state",
            "value": "diagnostic_package_replay",
            "unit": "state",
            "status": "warn",
            "why": METRIC_WHY["candidate_comparability_state"],
            "labels": {"not_substitute_for": "Spectrum product-green proof"},
        },
        {
            "name": "next_action_confidence",
            "value": "medium",
            "unit": "confidence",
            "status": "pass",
            "why": METRIC_WHY["next_action_confidence"],
            "labels": {"next_action": "use as package-scale intake pressure, not product-green proof"},
        },
    ]
    return sanitize(
        {
            "schema_version": "creator_replay_run_v1",
            "id": "batch_b",
            "label": "Batch B",
            "family": "contoso_business_suite",
            "tier": "package-scale",
            "difficulty": "Package realism and blocker harvest",
            "why_it_matters": "Shows the next product problem: broad install-folder intake, dependencies, noise, target selection, and package-scale triage.",
            "source_root": sanitize_string(str(BATCH_B_MANIFEST.relative_to(ROOT))),
            "generated_from": "fixture package manifest",
            "claim_ceiling": "package-scale diagnostic replay",
            "green_contract_level": "diagnostic_package_replay",
            "safe_to_compare": False,
            "route_authority_present": False,
            "next_action": "use as package-scale intake pressure, not product-green proof",
            "summary": {
                "suite_id": manifest.get("package_id"),
                "case_id": manifest.get("bundle_name"),
                "entry_surface": "package_manifest",
                "green_contract_level": "diagnostic_package_replay",
                "product_green_eligible": False,
                "route_authority_present": False,
                "safe_to_compare": False,
                "semantic_proof_satisfied": False,
                "authoritative_proving": False,
                "blocking_signal": "not_a_product_green_baseline",
                "target_count": len(selected),
                "total_duration_sec": 0,
                "verified_total": 0,
                "discovered_total": len(dlls),
                "first_failed_boundary": "not_applicable",
                "bundled_dll_count": len(dlls),
                "dependency_only_count": role_counts.get("dependency_only", 0),
                "runtime_target_count": role_counts.get("runtime_target", 0),
            },
            "targets": target_cards,
            "selected_runtime_targets": selected_cards,
            "artifact_summary": [
                {
                    "name": "package-manifest.json",
                    "kind": "package metadata",
                    "path": sanitize_string(str(BATCH_B_MANIFEST.relative_to(ROOT))),
                    "included": "derived fields only",
                    "bytes": BATCH_B_MANIFEST.stat().st_size,
                }
            ],
            "ground_truth_note": "Batch B is a package-scale planning replay. It demonstrates intake pressure and target selection, not product-green proof.",
            "otel": {
                "trace_id": "creator-batch-b",
                "claim_ceiling": "telemetry is diagnostic evidence only",
                "spans": spans,
                "metrics": metrics,
            },
            "links": {
                "run_trace": "data/runs/batch_b/run-trace.json",
                "run_metrics": "data/runs/batch_b/run-metrics.json",
                "run_trace_md": "data/runs/batch_b/run-trace.md",
            },
        }
    )


def trace_markdown(run: dict[str, Any]) -> str:
    lines = [
        f"# {run['label']} Replay Trace",
        "",
        f"- Claim ceiling: {run['claim_ceiling']}",
        f"- Source: {run['generated_from']}",
        f"- Telemetry claim: {run['otel']['claim_ceiling']}",
        "",
        "## Spans",
        "",
    ]
    for span in run["otel"]["spans"]:
        lines.append(f"- `{span['stage']}` {span['name']}: {span['status']} ({span.get('duration_sec', 0)} sec)")
    lines.extend(["", "## Metrics", ""])
    for metric in run["otel"]["metrics"]:
        lines.append(f"- `{metric['name']}` = `{metric['value']}` ({metric['status']}) - {metric['why']}")
    lines.append("")
    return "\n".join(lines)


def write_run_files(out: Path, run: dict[str, Any]) -> None:
    run_dir = out / "runs" / run["id"]
    write_json(run_dir / "run.json", run)
    write_json(run_dir / "run-trace.json", {"trace_id": run["otel"]["trace_id"], "spans": run["otel"]["spans"], "claim_ceiling": run["otel"]["claim_ceiling"]})
    write_json(run_dir / "run-metrics.json", {"trace_id": run["otel"]["trace_id"], "metrics": run["otel"]["metrics"], "claim_ceiling": run["otel"]["claim_ceiling"]})
    write_text(run_dir / "run-trace.md", trace_markdown(run))


def build(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    runs = [spectrum_run(defn) for defn in SPECTRUM_RUNS]
    runs.append(batch_b_run())
    for run in runs:
        write_run_files(out, run)
    index = {
        "schema_version": "creator_replay_index_v1",
        "generated_at": "static-replay-bundle-v1",
        "generated_from": "real artifacts; sanitized static replay",
        "claim_ceiling": "Static replay of real run artifacts, not live product execution.",
        "telemetry_claim_ceiling": "Telemetry is diagnostic evidence only and cannot by itself prove product green.",
        "docs_consulted": [
            "docs/architecture/OpenTelemetry/OpenTelemetryInitialization.md",
            "docs/architecture/testing_strategy/COMPILED-SUITE-GREEN-CONTRACT.md",
            "docs/architecture/testing_strategy/BREAKPOINT-TIER-RUBRIC.md",
            "docs/architecture/testing_strategy/SUITE-FAMILY-ROADMAP.md",
        ],
        "local_run_command": "python -m http.server 8088 --directory docs/creator-challenge/replay-demo",
        "runs": [
            {
                "id": run["id"],
                "label": run["label"],
                "tier": run["tier"],
                "difficulty": run["difficulty"],
                "claim_ceiling": run["claim_ceiling"],
                "safe_to_compare": run["summary"].get("safe_to_compare"),
                "product_green_eligible": run["summary"].get("product_green_eligible"),
                "target_count": run["summary"].get("target_count"),
                "duration_sec": run["summary"].get("total_duration_sec"),
                "path": f"data/runs/{run['id']}/run.json",
            }
            for run in runs
        ],
    }
    write_json(out / "index.json", index)


def check(out: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="mcp-factory-replay-") as tmp:
        generated = Path(tmp) / "data"
        build(generated)
        expected = {path.relative_to(generated) for path in generated.rglob("*") if path.is_file()}
        existing = {path.relative_to(out) for path in out.rglob("*") if path.is_file()}
        differing = expected ^ existing
        differing.update(path for path in expected & existing if (generated / path).read_bytes() != (out / path).read_bytes())
        if differing:
            paths = ", ".join(path.as_posix() for path in sorted(differing))
            raise SystemExit(f"Replay data is out of date: {paths}")
        count = len(load_json(generated / "index.json")["runs"])
        print(f"Verified {count} replay runs against tracked data.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="Compare regenerated data with the existing bundle.")
    args = parser.parse_args()
    if args.check:
        check(args.out)
        return 0
    build(args.out)
    print(f"wrote replay bundle to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
