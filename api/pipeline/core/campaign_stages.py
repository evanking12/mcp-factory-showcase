"""api.pipeline.core.campaign_stages — Cross-DLL campaign stages.

S-pre: Pre-stage cross-DLL planner (runs before S-00 in multi-DLL campaigns).
S-post: Post-stage knowledge consolidation (runs after S-07 in multi-DLL campaigns).

These stages operate on the EvidenceGraph and produce orchestration artifacts
consumed by the harness and runner.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dataclasses import dataclass, field as dataclass_field

from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry
from api.pipeline.core.evidence_candidates import TIER_RUNTIME
from api.pipeline.core.evidence_graph import EvidenceGraph

logger = logging.getLogger("mcp_factory.api")


@dataclass
class ReplayBudgetPolicy:
    """Limits on re-probe work within a multi-DLL campaign."""
    max_re_probes_per_dll: int = 20
    max_total_re_probes: int = 100
    priority_mode: str = "most_improved_first"  # or "dependency_order", "cheapest_first"

    def apply(self, re_probe_recs: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
        """Trim re-probe recommendations to fit budget constraints."""
        total_budget = self.max_total_re_probes
        trimmed: dict[str, list[dict[str, Any]]] = {}
        total_used = 0

        if self.priority_mode == "dependency_order":
            items = list(re_probe_recs.items())
        elif self.priority_mode == "cheapest_first":
            items = sorted(re_probe_recs.items(), key=lambda kv: len(kv[1]))
        else:
            items = sorted(re_probe_recs.items(), key=lambda kv: -len(kv[1]))

        for dll_fp, recs in items:
            if total_used >= total_budget:
                break
            per_dll_budget = min(self.max_re_probes_per_dll, total_budget - total_used)
            kept = recs[:per_dll_budget]
            if kept:
                trimmed[dll_fp] = kept
                total_used += len(kept)

        return trimmed


def run_s_pre(
    evidence_graph: EvidenceGraph,
    targets: list[dict[str, Any]],
    output_path: Path,
) -> dict[str, Any]:
    """S-pre: Read the evidence graph and produce a campaign execution plan.

    Args:
        evidence_graph: Current shared evidence graph.
        targets: List of {name, dll_path, dll_fingerprint, ...} target descriptors.
        output_path: Where to write campaign_plan.json.

    Returns:
        Campaign plan dict with DLL execution order and per-DLL context slices.
    """
    dll_fingerprints = [t.get("dll_fingerprint", "") for t in targets]

    # Determine execution order from dependency graph
    try:
        full_order = evidence_graph.topological_dll_order()
        execution_order = [fp for fp in full_order if fp in dll_fingerprints]
        unordered = [fp for fp in dll_fingerprints if fp not in execution_order]
        execution_order.extend(unordered)
    except ValueError:
        logger.warning("s_pre: cycle in dependency graph, falling back to input order")
        execution_order = list(dll_fingerprints)

    per_dll_plans: list[dict[str, Any]] = []
    for target in targets:
        dll_fp = target.get("dll_fingerprint", "")
        context_slice = evidence_graph.context_slice(dll_fp)

        from api.pipeline.core.evidence_graph import EDGE_CONFIDENCE_ORDERING_THRESHOLD
        deps = evidence_graph.dependencies_for_dll(dll_fp)
        # Only strong edges (above threshold) force ordering;
        # weak edges inform context but don't block parallelism
        strong_deps = [d for d in deps if d.confidence >= EDGE_CONFIDENCE_ORDERING_THRESHOLD]
        prerequisite_results: list[dict[str, Any]] = []
        for dep in deps:
            producer_fk = evidence_graph.get_function(dep.producer_dll, dep.producer_fn)
            if producer_fk:
                prerequisite_results.append({
                    "producer_dll": dep.producer_dll,
                    "producer_fn": dep.producer_fn,
                    "status": producer_fk.canonical_status,
                    "working_call": producer_fk.working_call,
                    "entity_type": dep.entity_type,
                    "edge_confidence": dep.confidence,
                })

        re_probe = evidence_graph.re_probe_recommendations(dll_fp)
        stale = evidence_graph.stale_functions(dll_fp)

        per_dll_plans.append({
            "target_name": target.get("name", ""),
            "dll_fingerprint": dll_fp,
            "execution_priority": execution_order.index(dll_fp) if dll_fp in execution_order else len(execution_order),
            "context_slice": context_slice,
            "prerequisite_results": prerequisite_results,
            "re_probe_recommendations": re_probe,
            "stale_functions": stale,
            "can_run_parallel": len(strong_deps) == 0,
        })

    plan = {
        "version": "1.0",
        "stage": "S-pre",
        "created_at": time.time(),
        "execution_order": execution_order,
        "target_count": len(targets),
        "edge_count": len(evidence_graph.edges),
        "entity_count": len(evidence_graph.entities),
        "per_dll": sorted(per_dll_plans, key=lambda p: p["execution_priority"]),
        "parallel_groups": _compute_parallel_groups(per_dll_plans),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    logger.info("s_pre: campaign plan written to %s (%d targets, %d edges)",
                output_path, len(targets), len(evidence_graph.edges))
    return plan


def _compute_parallel_groups(per_dll_plans: list[dict[str, Any]]) -> list[list[str]]:
    """Group DLLs that can run in parallel (no dependencies between them)."""
    groups: list[list[str]] = []
    remaining = sorted(per_dll_plans, key=lambda p: p["execution_priority"])

    scheduled: set[str] = set()
    while remaining:
        group: list[str] = []
        next_remaining: list[dict[str, Any]] = []
        for plan in remaining:
            can_parallel = plan["can_run_parallel"] or all(
                pr["producer_dll"] in scheduled
                for pr in plan.get("prerequisite_results", [])
            )
            if can_parallel:
                group.append(plan["dll_fingerprint"])
                scheduled.add(plan["dll_fingerprint"])
            else:
                next_remaining.append(plan)
        if not group:
            group = [p["dll_fingerprint"] for p in next_remaining]
            scheduled.update(group)
            next_remaining = []
        groups.append(group)
        remaining = next_remaining

    return groups


def run_s_post(
    evidence_graph: EvidenceGraph,
    completed_runs: list[dict[str, Any]],
    output_path: Path,
) -> dict[str, Any]:
    """S-post: Merge all per-DLL S-07 outputs into the evidence graph.

    Args:
        evidence_graph: Shared evidence graph to update.
        completed_runs: List of {dll_fingerprint, job_id, findings, invocables, vocab}.
        output_path: Where to write consolidation_report.json.

    Returns:
        Consolidation report with new edges, re-probe recommendations, and stats.
    """
    total_findings_ingested = 0
    total_edges_added = 0
    per_dll_stats: list[dict[str, Any]] = []

    for run in completed_runs:
        dll_fp = run.get("dll_fingerprint", "")
        job_id = run.get("job_id", "")
        findings = run.get("findings", [])
        invocables = run.get("invocables", {})
        vocab = run.get("vocab", {})

        if findings:
            count = evidence_graph.ingest_findings(dll_fp, findings, job_id)
            total_findings_ingested += count

        if invocables:
            edges = evidence_graph.ingest_invocables(dll_fp, invocables, job_id)
            total_edges_added += edges

        if vocab:
            evidence_graph.merge_vocab(vocab, dll_fp, job_id)

        per_dll_stats.append({
            "dll_fingerprint": dll_fp,
            "job_id": job_id,
            "findings_ingested": len(findings),
        })

    # Merge evidence candidate registries from completed runs
    _merged_ecr = EvidenceCandidateRegistry()
    _ecr_merge_count = 0
    for run in completed_runs:
        run_ecr = run.get("evidence_candidates")
        if run_ecr is not None and isinstance(run_ecr, EvidenceCandidateRegistry):
            _ecr_merge_count += _merged_ecr.merge_from(run_ecr, tier_override=4, min_tier=TIER_RUNTIME)
        elif isinstance(run_ecr, dict):
            try:
                _ecr_obj = EvidenceCandidateRegistry.from_dict(run_ecr)
                _ecr_merge_count += _merged_ecr.merge_from(_ecr_obj, tier_override=4, min_tier=TIER_RUNTIME)
            except Exception:
                pass
    if _ecr_merge_count:
        logger.info("s_post: merged %d evidence candidates across %d runs",
                     _ecr_merge_count, len(completed_runs))

    # Detect new cross-DLL dependency edges from entity overlap
    new_cross_edges = evidence_graph.detect_cross_dll_edges()
    total_edges_added += len(new_cross_edges)

    # Collect re-probe recommendations across all DLLs, then apply budget
    all_re_probe: dict[str, list[dict[str, Any]]] = {}
    for run in completed_runs:
        dll_fp = run.get("dll_fingerprint", "")
        recs = evidence_graph.re_probe_recommendations(dll_fp)
        if recs:
            all_re_probe[dll_fp] = recs

    budget = ReplayBudgetPolicy()
    all_re_probe = budget.apply(all_re_probe)

    report = {
        "version": "1.0",
        "schema_version": "1.0.0",
        "stage": "S-post",
        "created_at": time.time(),
        "total_findings_ingested": total_findings_ingested,
        "total_edges_added": total_edges_added,
        "new_cross_dll_edges": [asdict(e) for e in new_cross_edges],
        "re_probe_recommendations": all_re_probe,
        "re_probe_total_functions": sum(len(v) for v in all_re_probe.values()),
        "per_dll": per_dll_stats,
        "graph_summary": {
            "entities": len(evidence_graph.entities),
            "functions": sum(len(fns) for fns in evidence_graph.functions.values()),
            "edges": len(evidence_graph.edges),
            "vocab_keys": len(evidence_graph.vocab_union),
        },
        "evidence_candidates_merged": _ecr_merge_count,
        "evidence_candidates_stats": _merged_ecr.stats() if _ecr_merge_count else {},
        "conflict_count": len(evidence_graph.conflicts),
        "cost_summary": _aggregate_campaign_costs(completed_runs),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(
        "s_post: consolidation complete — %d findings, %d new edges, %d re-probe recs",
        total_findings_ingested, total_edges_added,
        report["re_probe_total_functions"],
    )
    return report


def _aggregate_campaign_costs(completed_runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-DLL cost data into a campaign-level summary."""
    per_dll: list[dict[str, Any]] = []
    totals = {"llm_calls": 0, "llm_tokens_in": 0, "llm_tokens_out": 0, "bridge_calls": 0, "wall_time_s": 0.0}
    verified_upgrades = 0

    for run in completed_runs:
        cost = run.get("cost_summary") or {}
        dll_cost = {
            "dll_fingerprint": run.get("dll_fingerprint", ""),
            "job_id": run.get("job_id", ""),
            **cost,
        }
        per_dll.append(dll_cost)
        for k in ("llm_calls", "llm_tokens_in", "llm_tokens_out", "bridge_calls"):
            totals[k] += int(cost.get(k, 0))
        totals["wall_time_s"] += float(cost.get("wall_time_s", 0.0))

        findings = run.get("findings", [])
        verified_upgrades += sum(
            1 for f in findings
            if str(f.get("status_canonical") or f.get("status", "")).lower()
            in ("verified_success", "success")
        )

    totals["verified_upgrades"] = verified_upgrades
    totals["cost_per_verified_upgrade"] = (
        round(totals["llm_calls"] / verified_upgrades, 2) if verified_upgrades else None
    )
    return {"per_dll": per_dll, "totals": totals}
