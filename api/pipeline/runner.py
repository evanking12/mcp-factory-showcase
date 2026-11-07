"""api.pipeline.runner -- Thin pipeline driver.

Single public entry point: _explore_worker(job_id, invocables).
Delegates to run_sXX() functions in each stage package.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re as _re
import hashlib
import threading
import time
from dataclasses import replace
from typing import Any

from api.infra.config import (
    OPENAI_API_KEY, OPENAI_EXPLORE_MODEL, OPENAI_MODEL, ARTIFACT_CONTAINER,
)
from api.infra.storage_api import (
    append_job_debug_event as _append_job_debug_event,
    download_blob as _download_blob,
    get_current_invocables as _get_current_invocables,
    get_job_status as _get_job_status,
    load_findings as _load_findings,
    merge_invocable_union as _merge_invocable_union,
    merge_invocables as _merge_invocables,
    patch_finding as _patch_finding,
    persist_job_status as _persist_job_status,
    seed_findings as _seed_findings,
    upload_to_blob as _upload_to_blob,
)
from api.infra.telemetry import _openai_client
from api.analysis.blocker_harvest import (
    build_blocker_classification_report,
    build_lane_trust_report,
    build_package_context_artifact,
    read_run_ledger_rows,
    summarize_campaign_blocker_harvest,
)
from api.pipeline.core.helpers import (
    _SENTINEL_DEFAULTS, _INIT_RE, FINDING_VERIFIED_STATUSES,
)
from api.pipeline.core.runtime_api import (
    build_tool_schemas as _build_tool_schemas,
    cancel_requested as _cancel_requested,
    has_job_lifecycle_inconsistency as _has_job_lifecycle_inconsistency,
    normalize_tool_schema_invocables as _normalize_tool_schema_invocables,
    is_terminal_job_record as _is_terminal_job_record,
    save_stage_context as _save_stage_context,
    set_explore_status as _set_explore_status,
    snapshot_schema_stage as _snapshot_schema_stage,
)
from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry
from api.pipeline.core.evidence_candidates import TIER_RUNTIME
from api.pipeline.core.cluster_checkpoint import CLUSTER_CHECKPOINTS_BY_ID, build_cluster_checkpoint_snapshot
from api.pipeline.core.cross_dll_contracts import (
    build_business_object_contract_surface,
    latest_findings_by_job as _latest_findings_by_job,
)
from api.pipeline.core.floor_iteration import (
    FloorPlan,
    FloorIterationState,
    build_floor_iteration_state,
    build_floor_plan,
    classify_package_floor_evidence,
    evaluate_floor_broadening_gate,
)
from api.pipeline.core.macro_coordinator import (
    RunVerdict,
    evaluate_run as _evaluate_run,
    persist_verdict as _persist_verdict,
)
from api.pipeline.core.package_frontier_planner import resolve_campaign_package_baseline_contract
from api.pipeline.core.pass_scope import describe_pass_scope_bucket
from api.pipeline.core.prerequisite_state_groups import build_prerequisite_state_group_snapshot
from api.pipeline.core.reusable_truth import assess_reusable_truth
from api.pipeline.core.types import ExploreContext, ExploreRuntime
from api.pipeline.core.checkpoint import (
    PipelineCheckpoint,
    load_checkpoint,
    apply_resume_boundary,
    resolve_cluster_seed_plan,
    save_checkpoint,
    seed_context_from_checkpoint,
    update_checkpoint_from_context,
    mark_stage_complete,
    is_stage_complete,
)

logger = logging.getLogger("mcp_factory.api")

_MACRO_VERDICT_TIMEOUT_SECONDS = max(
    1.0,
    float(os.getenv("MCP_MACRO_VERDICT_TIMEOUT_SECONDS", "20") or "20"),
)
_MACRO_VERDICT_PERSIST_TIMEOUT_SECONDS = max(
    1.0,
    float(os.getenv("MCP_MACRO_VERDICT_PERSIST_TIMEOUT_SECONDS", "10") or "10"),
)
_FINAL_WORKER_VERDICT_PERSIST_TIMEOUT_SECONDS = max(
    1.0,
    float(os.getenv("MCP_FINAL_WORKER_VERDICT_PERSIST_TIMEOUT_SECONDS", "10") or "10"),
)
_FINAL_WORKER_STATUS_AUTHORITY_BLOB = "final_status_persist_authority.json"
_S07_CHECKPOINT_SAVE_TIMEOUT_SECONDS = max(
    1.0,
    float(os.getenv("MCP_S07_CHECKPOINT_SAVE_TIMEOUT_SECONDS", "10") or "10"),
)
_S07_CHECKPOINT_STAGE_ID = "s07_finalize"
_S07_CHECKPOINT_AUTHORITY_BLOB = "checkpoints/s07_finalize_save_authority.json"
_MACRO_VERDICT_AUTHORITY_BLOB = "macro_verdict_persist_authority.json"


def _augment_runtime_focus_from_cluster_seed(job_id: str, runtime: ExploreRuntime) -> None:
    """Preload focus functions from a trusted cluster checkpoint when requested."""
    cluster_id = str(runtime.cluster_checkpoint_id or "").strip()
    checkpoint_id = str(runtime.checkpoint_id or "").strip()
    if not cluster_id or not checkpoint_id:
        return

    checkpoint = load_checkpoint(
        job_id,
        checkpoint_id,
        checkpoint_stage=runtime.checkpoint_stage,
    )
    if checkpoint is None:
        return

    seed_plan = resolve_cluster_seed_plan(
        checkpoint,
        cluster_id,
        adjacent_cluster_id=runtime.adjacent_cluster_id,
        min_confidence=float(runtime.cluster_confidence_floor or 0.5),
    )
    if seed_plan is None:
        return

    merged_focus: list[str] = []
    for fn_name in list(runtime.focus_functions or []) + list(seed_plan.focus_functions):
        name = str(fn_name or "").strip()
        if name and name not in merged_focus:
            merged_focus.append(name)
    runtime.focus_functions = merged_focus


def _latest_mc_decision(ctx, mc_id: str) -> dict[str, Any]:
    if hasattr(ctx, "latest_mc_decision"):
        try:
            latest = ctx.latest_mc_decision(mc_id)
            if isinstance(latest, dict):
                return latest
        except Exception:
            pass
    state = getattr(ctx, "_state", None)
    if isinstance(state, dict):
        mc_state = state.get("mc_decisions") or {}
        if isinstance(mc_state, dict):
            latest = mc_state.get(mc_id)
            if isinstance(latest, dict):
                return latest
    return {}


def _stage_retry_surface(ctx, mc_id: str) -> dict[str, Any]:
    latest = _latest_mc_decision(ctx, mc_id)
    if not latest:
        return {}
    analysis = latest.get("analysis") if isinstance(latest.get("analysis"), dict) else {}
    retry_plan = list(analysis.get("retry_plan") or [])
    return {
        "mc_decision_id": mc_id,
        "mc_decision": latest,
        "retryable_functions": list(analysis.get("retryable_functions") or [])[:8],
        "prerequisite_clusters": dict(analysis.get("prerequisite_clusters") or {}),
        "cluster_hints": list(analysis.get("cluster_hints") or [])[:8],
        "retry_plan": retry_plan[:8],
        "checkpoint_recommended_boundary": str(
            analysis.get("checkpoint_recommended_boundary")
            or ((analysis.get("retry_rationale") or {}).get("checkpoint_recommended_boundary") if isinstance(analysis.get("retry_rationale"), dict) else "")
            or ""
        ),
        "cost_summary": ctx.cost_summary(),
    }


def _persist_stage_kpis(job_id: str, checkpoint: PipelineCheckpoint, ctx) -> None:
    stage_rows: dict[str, Any] = {}
    for stage_id, stage_checkpoint in (checkpoint.stages or {}).items():
        if not stage_checkpoint or not getattr(stage_checkpoint, "completed", False):
            continue
        stage_rows[stage_id] = {
            "completed": bool(stage_checkpoint.completed),
            "timestamp": float(stage_checkpoint.timestamp or 0.0),
            "data": stage_checkpoint.data if isinstance(stage_checkpoint.data, dict) else {},
        }
    payload = {
        "job_id": job_id,
        "generated_at": time.time(),
        "cost_summary": ctx.cost_summary(),
        "stages": stage_rows,
    }
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/stage_kpis.json",
            json.dumps(payload, indent=2).encode("utf-8"),
        )
    except Exception as exc:
        logger.debug("[%s] stage KPI write failed: %s", job_id, exc)


def _record_stage_skip_reason(job_id: str, stage_id: str, reason: str, detail: str = "") -> None:
    current = _get_job_status(job_id) or {}
    reasons = dict(current.get("stage_skip_reasons") or {})
    reasons[str(stage_id)] = {
        "reason": str(reason or "").strip(),
        "detail": str(detail or "").strip(),
    }
    _persist_job_status(
        job_id,
        {
            **current,
            "stage_skip_reasons": reasons,
            "updated_at": time.time(),
        },
        sync=True,
    )


def _clear_stage_skip_reason(job_id: str, stage_id: str) -> None:
    current = _get_job_status(job_id) or {}
    reasons = dict(current.get("stage_skip_reasons") or {})
    if str(stage_id) not in reasons:
        return
    reasons.pop(str(stage_id), None)
    _persist_job_status(
        job_id,
        {
            **current,
            "stage_skip_reasons": reasons,
            "updated_at": time.time(),
        },
        sync=True,
    )


def _load_json_artifact(job_id: str, filename: str) -> Any:
    source_job_id = str(job_id or "").strip()
    if not source_job_id:
        return None
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, f"{source_job_id}/{filename}")
        return json.loads(raw)
    except Exception:
        return None


def _finding_state_map(rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    from api.pipeline.core.finding_status import STATUS_ORDER, normalize_status

    best: dict[str, tuple[int, bool, dict[str, Any]]] = {}
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        fn_name = str(row.get("function") or "").strip()
        if not fn_name:
            continue
        normalized = normalize_status(row.get("status_canonical") or row.get("status"))
        rank = STATUS_ORDER.get(normalized, 0)
        has_working_call = bool(row.get("working_call"))
        current = best.get(fn_name)
        if current is None or rank > current[0] or (rank == current[0] and has_working_call and not current[1]):
            best[fn_name] = (rank, has_working_call, dict(row))
    return {fn_name: row for fn_name, (_rank, _has_working_call, row) in best.items()}


def _cluster_gate_color(cluster_id: str, states: dict[str, dict[str, Any]]) -> str:
    for row in build_cluster_checkpoint_snapshot(function_states=states):
        if str(row.get("cluster_id") or "").strip() == cluster_id:
            return str(row.get("gate_color") or "red")
    return "red"


def _cluster_consumer_coverage(cluster_id: str, states: dict[str, dict[str, Any]]) -> dict[str, Any]:
    canonical = CLUSTER_CHECKPOINTS_BY_ID.get(cluster_id)
    if canonical is None:
        return {
            "consumer_functions": [],
            "executed_consumers": [],
            "successful_consumers": [],
            "coverage_ratio": 0.0,
        }
    executed = [fn_name for fn_name in canonical.consumer_functions if fn_name in states]
    successful = [
        fn_name for fn_name in canonical.consumer_functions
        if str((states.get(fn_name) or {}).get("status_canonical") or (states.get(fn_name) or {}).get("status") or "").strip().lower()
        in {"success", "verified_success"}
    ]
    return {
        "consumer_functions": list(canonical.consumer_functions),
        "executed_consumers": executed,
        "successful_consumers": successful,
        "coverage_ratio": round(len(executed) / max(1, len(canonical.consumer_functions)), 2),
    }


def _cluster_remaining_blocker(cluster_id: str, states: dict[str, dict[str, Any]]) -> str:
    canonical = CLUSTER_CHECKPOINTS_BY_ID.get(cluster_id)
    if canonical is None:
        return ""
    missing = [fn_name for fn_name in canonical.consumer_functions if fn_name not in states]
    if missing:
        return f"missing_consumer_coverage:{','.join(missing[:3])}"
    unresolved = [
        fn_name for fn_name in canonical.consumer_functions
        if str((states.get(fn_name) or {}).get("status_canonical") or (states.get(fn_name) or {}).get("status") or "").strip().lower()
        not in {"success", "verified_success"}
    ]
    if unresolved:
        return f"consumer_not_verified:{','.join(unresolved[:3])}"
    return ""


def _surface_function_count(config: dict[str, Any] | None, rows: list[dict[str, Any]] | None) -> int:
    focus_functions = [
        str(fn_name or "").strip()
        for fn_name in list((config or {}).get("focus_functions") or [])
        if str(fn_name or "").strip()
    ]
    if focus_functions:
        return len(focus_functions)
    return len(
        {
            str((row or {}).get("function") or "").strip()
            for row in list(rows or [])
            if str((row or {}).get("function") or "").strip()
        }
    )


def _reused_truth_count(cluster_id: str, states: dict[str, dict[str, Any]]) -> int:
    canonical = CLUSTER_CHECKPOINTS_BY_ID.get(cluster_id)
    if canonical is None:
        return 0
    count = 0
    for fn_name in canonical.producer_functions:
        row = states.get(fn_name) or {}
        source = str(row.get("source") or "").strip().lower()
        if source in {"checkpoint_resume", "prior_session"}:
            count += 1
    return count


def _gate_rank(color: str) -> int:
    return {"red": 0, "amber": 1, "green": 2}.get(str(color or "").strip().lower(), 0)


def _persist_convergence_summary(job_id: str, ctx) -> None:
    cluster_id = str(ctx.runtime.cluster_checkpoint_id or "").strip()
    source_job_id = str(ctx.runtime.checkpoint_id or ctx.runtime.prior_job_id or "").strip()
    if not cluster_id or not source_job_id:
        return

    current_rows = _load_findings(job_id)
    current_states = _finding_state_map(current_rows)
    source_rows = _load_json_artifact(source_job_id, "findings.json")
    source_states = _finding_state_map(source_rows if isinstance(source_rows, list) else [])
    current_config = _load_json_artifact(job_id, "explore_config.json")
    source_config = _load_json_artifact(source_job_id, "explore_config.json")
    current_stage_kpis = _load_json_artifact(job_id, "stage_kpis.json")
    source_stage_kpis = _load_json_artifact(source_job_id, "stage_kpis.json")

    current_consumer_coverage = _cluster_consumer_coverage(cluster_id, current_states)
    source_consumer_coverage = _cluster_consumer_coverage(cluster_id, source_states)
    current_gate = _cluster_gate_color(cluster_id, current_states)
    source_gate = _cluster_gate_color(cluster_id, source_states)
    current_time = float(((current_stage_kpis or {}).get("cost_summary") or {}).get("wall_time_s") or 0.0)
    source_time = float(((source_stage_kpis or {}).get("cost_summary") or {}).get("wall_time_s") or 0.0)
    current_surface = _surface_function_count(current_config if isinstance(current_config, dict) else {}, current_rows)
    source_surface = _surface_function_count(source_config if isinstance(source_config, dict) else {}, source_rows if isinstance(source_rows, list) else [])
    reasons: list[str] = []
    if source_time > 0 and current_time > 0 and current_time < source_time:
        reasons.append("cheaper")
    if source_surface > 0 and current_surface > 0 and current_surface < source_surface:
        reasons.append("narrower")
    if (
        _gate_rank(current_gate) > _gate_rank(source_gate)
        or len(current_consumer_coverage["successful_consumers"]) > len(source_consumer_coverage["successful_consumers"])
        or current_consumer_coverage["coverage_ratio"] > source_consumer_coverage["coverage_ratio"]
    ):
        reasons.append("more_decisive")

    payload = {
        "job_id": job_id,
        "cluster_id": cluster_id,
        "generated_at": time.time(),
        "seed_strategy": str(ctx.runtime.seed_strategy or "").strip() or "cold_start",
        "seed_default_applied": bool(ctx.runtime.seed_default_applied),
        "seed_default_reason": str(ctx.runtime.seed_default_reason or "").strip(),
        "current": {
            "job_id": job_id,
            "proof_time_s": round(current_time, 2),
            "gate_color": current_gate,
            "pass_count": int(getattr(ctx.runtime, "pass_index", 1) or 1),
            "pass_scope_profile": str(getattr(ctx.runtime, "pass_scope_profile", "foundation") or "foundation"),
            "surface_function_count": current_surface,
            "focus_functions": list(ctx.runtime.focus_functions or []),
            "reused_truths": _reused_truth_count(cluster_id, current_states),
            "consumer_coverage": current_consumer_coverage,
            "remaining_blocker": _cluster_remaining_blocker(cluster_id, current_states),
        },
        "baseline": {
            "job_id": source_job_id,
            "proof_time_s": round(source_time, 2),
            "gate_color": source_gate,
            "pass_count": int(((source_config or {}).get("pass_index") or 1) if isinstance(source_config, dict) else 1),
            "pass_scope_profile": str(((source_config or {}).get("pass_scope_profile") or "foundation") if isinstance(source_config, dict) else "foundation"),
            "surface_function_count": source_surface,
            "focus_functions": list(((source_config or {}).get("focus_functions") or []) if isinstance(source_config, dict) else []),
            "reused_truths": _reused_truth_count(cluster_id, source_states),
            "consumer_coverage": source_consumer_coverage,
            "remaining_blocker": _cluster_remaining_blocker(cluster_id, source_states),
        },
        "movement": {
            "proof_time_delta_s": round(current_time - source_time, 2) if source_time > 0 and current_time > 0 else None,
            "gate_color_movement": f"{source_gate}->{current_gate}",
            "surface_function_delta": current_surface - source_surface if source_surface > 0 and current_surface > 0 else None,
            "compressed": bool(reasons),
            "compression_reasons": reasons,
        },
    }
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/convergence_summary.json",
            json.dumps(payload, indent=2).encode("utf-8"),
        )
    except Exception as exc:
        logger.debug("[%s] convergence summary write failed: %s", job_id, exc)


def _persist_floor_iteration_artifacts(
    job_id: str,
    plan: FloorPlan | None,
    state: FloorIterationState | None = None,
) -> None:
    if plan is None:
        return
    artifacts = {
        "floor_plan.json": plan.to_dict(),
        "prerequisite_state_groups.json": {
            "schema_version": plan.schema_version,
            "cluster_checkpoint_id": plan.cluster_checkpoint_id,
            "prerequisite_state_groups": list(plan.prerequisite_state_groups),
        },
        "ceiling_frontier.json": {
            "schema_version": plan.schema_version,
            "iteration_index": plan.iteration_index,
            "floor_scope": plan.floor_scope,
            "current_ceiling_functions": list(plan.ceiling_functions),
            "next_ceiling_functions": list(plan.ceiling_functions),
            "preserved_lower_floor_functions": list(plan.preserved_lower_floor_functions),
            "reopened_preserved_functions": [],
            "ceiling_shrank": False,
            "ceiling_localized": False,
            "ceiling_dependency_map": dict(plan.ceiling_dependency_map),
        },
    }
    if state is not None:
        artifacts["floor_iteration_state.json"] = state.to_dict()
        artifacts["ceiling_frontier.json"] = {
            "schema_version": plan.schema_version,
            "iteration_index": state.iteration_index,
            "floor_scope": state.floor_scope,
            "current_ceiling_functions": list(state.previous_ceiling_functions),
            "next_ceiling_functions": list(state.next_ceiling_functions),
            "preserved_lower_floor_functions": list(state.preserved_lower_floor_functions),
            "reopened_preserved_functions": list(state.reopened_functions),
            "ceiling_shrank": bool(state.ceiling_shrank),
            "ceiling_localized": bool(state.localized_more),
            "ceiling_dependency_map": dict(plan.ceiling_dependency_map),
        }
    for filename, payload in artifacts.items():
        try:
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{job_id}/{filename}",
                json.dumps(payload, indent=2).encode("utf-8"),
            )
        except Exception as exc:
            logger.debug("[%s] floor iteration artifact write failed for %s: %s", job_id, filename, exc)


def _current_contradiction_count(ctx) -> int:
    current = _get_job_status(getattr(ctx, "job_id", "")) or {}
    try:
        return max(0, int(current.get("contradiction_count") or 0))
    except Exception:
        return 0


def _initialize_floor_iteration_plan(
    job_id: str,
    ctx,
    checkpoint: PipelineCheckpoint,
) -> FloorPlan | None:
    plan = build_floor_plan(
        ctx.runtime,
        checkpoint,
        current_findings=_load_findings(job_id),
    )
    if plan is None:
        return None
    ctx.floor_plan = plan
    ctx.runtime.ceiling_functions = list(plan.ceiling_functions)
    ctx.runtime.ceiling_origin_functions = list(plan.root_ceiling_functions)
    if plan.cycle_focus_functions:
        ctx.runtime.focus_functions = list(plan.cycle_focus_functions)
    if plan.prerequisite_state_group_ids:
        ctx.runtime.prerequisite_state_group_ids = list(plan.prerequisite_state_group_ids)
    _persist_floor_iteration_artifacts(job_id, plan)
    return plan


def _next_floor_iteration_runtime(
    job_id: str,
    runtime: ExploreRuntime,
    state: FloorIterationState,
) -> ExploreRuntime:
    return replace(
        runtime,
        iteration_index=int(state.iteration_index or 1) + 1,
        focus_functions=list(state.next_cycle_recommendation.get("focus_functions") or []),
        ceiling_functions=list(state.next_ceiling_functions or []),
        ceiling_origin_functions=list(
            state.next_cycle_recommendation.get("ceiling_origin_functions")
            or getattr(runtime, "ceiling_origin_functions", [])
            or getattr(runtime, "ceiling_functions", [])
            or []
        ),
        floor_scope=str(state.next_cycle_recommendation.get("floor_scope") or state.floor_scope or "cluster"),
        checkpoint_id=job_id,
        checkpoint_stage="s02_probe",
        skip_to_stage=str(state.next_cycle_recommendation.get("skip_to_stage") or ""),
        skip_to_stage_reason=str(state.next_cycle_recommendation.get("skip_to_stage_reason") or ""),
        seed_strategy="floor_to_ceiling_resume",
    )


def _validate_explore_worker_env(job_id: str) -> bool:
    if OPENAI_API_KEY:
        return True
    message = "Exploration aborted: OPENAI_API_KEY is not configured"
    logger.warning("[%s] explore_worker: %s", job_id, message)
    current = _get_job_status(job_id) or {}
    _persist_job_status(job_id, {
        **current,
        "status": current.get("status") or "error",
        "error": message,
        "explore_phase": "error",
        "explore_progress": "0/0",
        "explore_message": message,
        "updated_at": time.time(),
    })
    return False


def _flush_bridge_cache(job_id: str) -> None:
    try:
        from api.infra.config import GUI_BRIDGE_URL, GUI_BRIDGE_SECRET
        if GUI_BRIDGE_URL and GUI_BRIDGE_SECRET:
            import httpx
            _br = httpx.Client(
                base_url=GUI_BRIDGE_URL,
                headers={"X-Bridge-Key": GUI_BRIDGE_SECRET},
                timeout=5.0,
            )
            _br.post("/flush-dll-cache")
            _br.close()
            logger.info("[%s] bridge DLL cache flushed for fresh session", job_id)
    except Exception as exc:
        logger.debug("[%s] bridge DLL cache flush failed (non-fatal): %s", job_id, exc)


def _bootstrap_schema_bytes(job_id: str, ctx) -> bytes:
    try:
        return _download_blob(ARTIFACT_CONTAINER, f"{job_id}/mcp_schema.json")
    except Exception:
        return _runtime_bootstrap_schema_bytes(job_id, ctx)


def _runtime_bootstrap_schema_bytes(job_id: str, ctx) -> bytes:
    component = str(
        ((_get_job_status(job_id) or {}).get("component_name"))
        or ((_get_job_status(job_id) or {}).get("component"))
        or "mcp-component"
    ).strip() or "mcp-component"
    schema_payload = {
        "job_id": job_id,
        "mcp_version": "1.0",
        "component": component,
        "tools": _build_tool_schemas(ctx.invocables),
    }
    return json.dumps(schema_payload, indent=2).encode("utf-8")


def _persist_explore_bootstrap_artifacts(job_id: str, ctx) -> int:
    prior_seeded = sum(
        1 for f in (getattr(ctx, "_prior_session", {}) or {}).get("findings", [])
        if str(f.get("status") or f.get("status_canonical") or "").lower() in FINDING_VERIFIED_STATUSES
    )
    if ctx.runtime.prior_job_id or ctx.runtime.overlap_baseline_job_id or prior_seeded:
        try:
            cur = _get_job_status(job_id) or {}
            _persist_job_status(job_id, {
                **cur,
                "prior_job_id": ctx.runtime.prior_job_id,
                "overlap_baseline_job_id": ctx.runtime.overlap_baseline_job_id,
                "prior_findings_seeded": prior_seeded,
            })
        except Exception:
            pass

    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/explore_config.json",
            json.dumps({
                "mode": ((_get_job_status(job_id) or {}).get("explore_runtime") or {}).get("mode") or "normal",
                "cap_profile": ctx.runtime.cap_profile,
                "max_rounds_per_function": ctx.runtime.max_rounds,
                "max_tool_calls_per_function": ctx.runtime.max_tool_calls,
                "write_fn_tool_calls": 14,
                "max_functions_per_session": ctx.runtime.max_functions,
                "min_direct_probes_per_function": ctx.runtime.min_direct_probes,
                "skip_documented": ctx.runtime.skip_documented,
                "deterministic_fallback_enabled": ctx.runtime.deterministic_fallback_enabled,
                "gap_resolution_enabled": ctx.runtime.gap_resolution_enabled,
                "clarification_questions_enabled": ctx.runtime.clarification_enabled,
                "analysis_profile": ctx.runtime.analysis_profile,
                "variant_configs": ctx.runtime.variant_configs,
                "parallel_runs": ctx.runtime.parallel_runs,
                "lane_id": ctx.runtime.lane_id,
                "variant_id": ctx.runtime.variant_id,
                "checkpoint_id": ctx.runtime.checkpoint_id,
                "checkpoint_stage": ctx.runtime.checkpoint_stage,
                "cluster_checkpoint_id": ctx.runtime.cluster_checkpoint_id,
                "adjacent_cluster_id": ctx.runtime.adjacent_cluster_id,
                "cluster_confidence_floor": ctx.runtime.cluster_confidence_floor,
                "focus_functions": list(ctx.runtime.focus_functions or []),
                "pass_index": getattr(ctx.runtime, "pass_index", 1),
                "pass_scope_profile": getattr(ctx.runtime, "pass_scope_profile", "foundation"),
                "iteration_mode": getattr(ctx.runtime, "iteration_mode", "single_pass"),
                "iteration_index": getattr(ctx.runtime, "iteration_index", 1),
                "floor_scope": getattr(ctx.runtime, "floor_scope", "cluster"),
                "ceiling_functions": list(getattr(ctx.runtime, "ceiling_functions", []) or []),
                "ceiling_origin_functions": list(getattr(ctx.runtime, "ceiling_origin_functions", []) or []),
                "prerequisite_state_group_ids": list(getattr(ctx.runtime, "prerequisite_state_group_ids", []) or []),
                "max_iteration_cycles": getattr(ctx.runtime, "max_iteration_cycles", 1),
                "skip_to_stage": ctx.runtime.skip_to_stage,
                "skip_to_stage_reason": ctx.runtime.skip_to_stage_reason,
                "prior_job_id": ctx.runtime.prior_job_id,
                "overlap_baseline_job_id": ctx.runtime.overlap_baseline_job_id,
                "cross_dll_prior_job_ids": ctx.runtime.cross_dll_prior_job_ids,
                "seed_strategy": ctx.runtime.seed_strategy,
                "seed_default_applied": bool(ctx.runtime.seed_default_applied),
                "seed_default_reason": ctx.runtime.seed_default_reason,
                "cross_dll_seeded": getattr(ctx, "_cross_dll_seeded_count", 0),
                "prior_findings_seeded": prior_seeded,
            }, indent=2).encode(),
        )
    except Exception as exc:
        logger.debug("[%s] explore_worker: explore_config upload failed: %s", job_id, exc)

    try:
        raw_schema = _bootstrap_schema_bytes(job_id, ctx)
        runtime_schema = _runtime_bootstrap_schema_bytes(job_id, ctx)
        try:
            _download_blob(ARTIFACT_CONTAINER, f"{job_id}/mcp_schema.json")
        except Exception:
            _upload_to_blob(ARTIFACT_CONTAINER, f"{job_id}/mcp_schema.json", raw_schema)
        _upload_to_blob(ARTIFACT_CONTAINER, f"{job_id}/mcp_schema_t0.json", runtime_schema)
        logger.info("[%s] explore_worker: pre-enrichment schema snapshot saved", job_id)
    except Exception as exc:
        logger.debug("[%s] explore_worker: schema snapshot failed: %s", job_id, exc)
    return prior_seeded


def _load_evidence_graph_for_context(job_id: str, ctx) -> tuple[Any, str]:
    evidence_graph = None
    dll_fingerprint_for_graph = ""
    try:
        from api.pipeline.core.evidence_graph import EvidenceGraph
        evidence_graph = EvidenceGraph.load_blob(ARTIFACT_CONTAINER)
        dll_fp_raw = str(
            ((_get_job_status(job_id) or {}).get("dll_fingerprint"))
            or ((_get_job_status(job_id) or {}).get("dll_sha256"))
            or job_id
        )
        import hashlib as _hashlib
        dll_fingerprint_for_graph = _hashlib.sha256(dll_fp_raw.encode()).hexdigest()
        if evidence_graph.entities or evidence_graph.functions:
            slice_data = evidence_graph.context_slice(dll_fingerprint_for_graph)
            graph_vocab = slice_data.get("vocab") or {}
            if graph_vocab:
                for key, value in graph_vocab.items():
                    if key not in ctx.vocab:
                        ctx.vocab[key] = value
            logger.info(
                "[%s] evidence_graph loaded: %d entities, %d known functions for this DLL",
                job_id,
                len(evidence_graph.entities),
                len(slice_data.get("known_functions", {})),
            )
    except Exception as exc:
        logger.debug("[%s] evidence_graph load skipped: %s", job_id, exc)
    return evidence_graph, dll_fingerprint_for_graph


def _apply_evidence_based_focus(ctx, evidence_graph, dll_fingerprint_for_graph: str, job_id: str) -> None:
    if (
        ctx.runtime.skip_to_stage_reason == "new_cross_dll_evidence"
        and evidence_graph is not None
        and dll_fingerprint_for_graph
        and not ctx.runtime.focus_functions
    ):
        recs = evidence_graph.re_probe_recommendations(dll_fingerprint_for_graph)
        if recs:
            ctx.runtime.focus_functions.extend(r["function"] for r in recs)
            logger.info(
                "[%s] evidence-based focus: %d functions from re-probe recommendations",
                job_id,
                len(recs),
            )


def _finalize_worker_verdict(job_id: str, ctx, coverage_status: str, coverage_pct: int) -> None:
    current = _get_job_status(job_id) or {}
    _persist_job_status(
        job_id,
        {
            **current,
            "status": "done",
            "explore_phase": "done",
            "explore_stage": "done",
            "explore_progress": f"{ctx.total}/{ctx.total}",
            "explore_message": f"Complete — {coverage_status} ({coverage_pct}% coverage)",
            "updated_at": time.time(),
        },
        sync=True,
    )


def _final_status_blob_name(job_id: str) -> str:
    return f"{job_id}/status.json"


def _persist_final_status_authority(
    job_id: str,
    *,
    state: str,
    status_blob: str = "",
    status_sha256: str = "",
    status_bytes: int = 0,
    terminal_status: str = "",
    predecessor_verdict_blob: str = "",
    predecessor_verdict_sha256: str = "",
    predecessor_verdict_status: str = "",
    predecessor_authority_blob: str = "",
    predecessor_authority_sha256: str = "",
    error: str = "",
) -> None:
    payload = {
        "schema_version": "1.0.0",
        "state": state,
        "status_blob": status_blob,
        "status_sha256": status_sha256,
        "status_bytes": status_bytes,
        "terminal_status": terminal_status,
        "predecessor_verdict_blob": predecessor_verdict_blob,
        "predecessor_verdict_sha256": predecessor_verdict_sha256,
        "predecessor_verdict_status": predecessor_verdict_status,
        "predecessor_authority_blob": predecessor_authority_blob,
        "predecessor_authority_sha256": predecessor_authority_sha256,
        "error": error,
        "recorded_at": time.time(),
    }
    _upload_to_blob(
        ARTIFACT_CONTAINER,
        f"{job_id}/{_FINAL_WORKER_STATUS_AUTHORITY_BLOB}",
        json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
    )


def _final_status_predecessor_packet(job_id: str) -> dict[str, str]:
    verdict_blob = _macro_verdict_blob_name(job_id)
    verdict_raw = _download_blob(ARTIFACT_CONTAINER, verdict_blob)
    verdict = json.loads(verdict_raw.decode("utf-8-sig"))
    verdict_status = str(verdict.get("status") or "").strip() if isinstance(verdict, dict) else ""
    if not verdict_status:
        raise RuntimeError("final_status_predecessor_verdict_missing")
    authority_blob = f"{job_id}/{_MACRO_VERDICT_AUTHORITY_BLOB}"
    try:
        authority_raw = _download_blob(ARTIFACT_CONTAINER, authority_blob)
        authority_sha256 = hashlib.sha256(authority_raw).hexdigest()
    except Exception:
        authority_blob = ""
        authority_sha256 = ""
    return {
        "predecessor_verdict_blob": verdict_blob,
        "predecessor_verdict_sha256": hashlib.sha256(verdict_raw).hexdigest(),
        "predecessor_verdict_status": verdict_status,
        "predecessor_authority_blob": authority_blob,
        "predecessor_authority_sha256": authority_sha256,
    }


def _verify_final_worker_status_persisted(job_id: str) -> dict[str, Any]:
    if not str(job_id or "").strip():
        raise RuntimeError("final_status_job_id_missing")
    blob_name = _final_status_blob_name(job_id)
    raw = _download_blob(ARTIFACT_CONTAINER, blob_name)
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict) or not _is_terminal_job_record(payload):
        raise RuntimeError("final_status_persist_missing_or_nonterminal")
    terminal_status = str(payload.get("status") or "").strip()
    return {
        "status_blob": blob_name,
        "status_sha256": hashlib.sha256(raw).hexdigest(),
        "status_bytes": len(raw),
        "terminal_status": terminal_status,
        **_final_status_predecessor_packet(job_id),
    }


def _finalize_worker_verdict_bounded(job_id: str, ctx, coverage_status: str, coverage_pct: int) -> dict[str, Any] | None:
    current = _get_job_status(job_id) or {}
    payload = {
        **current,
        "status": "done",
        "explore_phase": "done",
        "explore_stage": "done",
        "explore_progress": f"{ctx.total}/{ctx.total}",
        "explore_message": f"Complete â€” {coverage_status} ({coverage_pct}% coverage)",
        "updated_at": time.time(),
    }
    result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def _persist_final_status() -> None:
        try:
            result_queue.put(("ok", _persist_job_status(job_id, payload, sync=True)))
        except Exception as exc:  # pragma: no cover - defensive trace path
            result_queue.put(("error", exc))

    worker = threading.Thread(target=_persist_final_status, name=f"final-worker-verdict-{job_id}", daemon=True)
    worker.start()
    worker.join(_FINAL_WORKER_VERDICT_PERSIST_TIMEOUT_SECONDS)
    if worker.is_alive():
        logger.warning("[%s] final worker verdict status persist timed out; deferring terminal status write", job_id)
        _record_worker_close_step_sync(job_id, "final_worker_verdict_persist_timeout")
        try:
            _persist_final_status_authority(
                job_id,
                state="timeout",
                terminal_status="done",
                error="final_worker_verdict_persist_timeout",
            )
        except Exception as exc:
            logger.debug("[%s] final status timeout authority persist failed: %s", job_id, exc)
        _persist_job_status(job_id, payload, sync=False)
        return None

    state, value = result_queue.get() if not result_queue.empty() else (
        "error",
        RuntimeError("final_worker_verdict_persist_no_result"),
    )
    if state == "error":
        logger.warning("[%s] final worker verdict status persist failed; deferring terminal status write: %s", job_id, value)
        _record_worker_close_step_sync(job_id, "final_worker_verdict_persist_failed", error=str(value))
        try:
            _persist_final_status_authority(
                job_id,
                state="failed",
                terminal_status="done",
                error=str(value),
            )
        except Exception as exc:
            logger.debug("[%s] final status failure authority persist failed: %s", job_id, exc)
        _persist_job_status(job_id, payload, sync=False)
        return None
    if not value:
        try:
            _persist_final_status_authority(
                job_id,
                state="failed",
                terminal_status="done",
                error="final_worker_verdict_persist_false",
            )
        except Exception as exc:
            logger.debug("[%s] final status false authority persist failed: %s", job_id, exc)
        return None
    try:
        authority = _verify_final_worker_status_persisted(job_id)
        _persist_final_status_authority(job_id, state="returned", **authority)
        return authority
    except Exception as exc:
        logger.warning("[%s] final worker verdict status verification failed: %s", job_id, exc)
        _record_worker_close_step_sync(job_id, "final_worker_verdict_persist_failed", error=str(exc))
        try:
            _persist_final_status_authority(
                job_id,
                state="failed",
                terminal_status="done",
                error=str(exc),
            )
        except Exception as authority_exc:
            logger.debug("[%s] final status verification authority persist failed: %s", job_id, authority_exc)
        return None


def _s07_checkpoint_blob_name(job_id: str) -> str:
    return f"{job_id}/checkpoints/{_S07_CHECKPOINT_STAGE_ID}.json"


def _persist_s07_checkpoint_save_authority(
    job_id: str,
    *,
    state: str,
    checkpoint_blob: str = "",
    checkpoint_sha256: str = "",
    checkpoint_bytes: int = 0,
    error: str = "",
) -> None:
    payload = {
        "schema_version": "1.0.0",
        "stage_id": _S07_CHECKPOINT_STAGE_ID,
        "state": state,
        "checkpoint_blob": checkpoint_blob,
        "checkpoint_sha256": checkpoint_sha256,
        "checkpoint_bytes": checkpoint_bytes,
        "error": error,
        "recorded_at": time.time(),
    }
    _upload_to_blob(
        ARTIFACT_CONTAINER,
        f"{job_id}/{_S07_CHECKPOINT_AUTHORITY_BLOB}",
        json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
    )


def _verify_s07_checkpoint_save_returned(job_id: str) -> dict[str, Any]:
    blob_name = _s07_checkpoint_blob_name(job_id)
    raw = _download_blob(ARTIFACT_CONTAINER, blob_name)
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("stage_id") != _S07_CHECKPOINT_STAGE_ID or not payload.get("completed"):
        raise RuntimeError("s07_checkpoint_save_missing_or_incomplete")
    return {
        "checkpoint_blob": blob_name,
        "checkpoint_sha256": hashlib.sha256(raw).hexdigest(),
        "checkpoint_bytes": len(raw),
    }


def _save_s07_checkpoint_bounded(job_id: str, checkpoint) -> dict[str, Any] | None:
    result_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def _save() -> None:
        try:
            save_checkpoint(checkpoint, write_stage_snapshots=False)
            result_queue.put(("ok", _verify_s07_checkpoint_save_returned(job_id)))
        except Exception as exc:
            result_queue.put(("error", exc))

    worker = threading.Thread(target=_save, name=f"s07-checkpoint-save-{job_id}", daemon=True)
    worker.start()
    worker.join(_S07_CHECKPOINT_SAVE_TIMEOUT_SECONDS)
    if worker.is_alive():
        try:
            _persist_s07_checkpoint_save_authority(job_id, state="timeout", error="s07_checkpoint_save_timeout")
        except Exception as exc:
            logger.debug("[%s] S-07 checkpoint timeout authority persist failed: %s", job_id, exc)
        _record_worker_close_step_sync(job_id, "s07_checkpoint_save_timeout")
        _persist_worker_close_progress(
            job_id,
            "S-07 checkpoint save timed out",
            span="s07_checkpoint_save",
            span_state="timeout",
            span_message="S-07 close: checkpoint save timed out before worker close.",
        )
        return None

    state, value = result_queue.get() if not result_queue.empty() else ("ok", True)
    if state == "error":
        try:
            _persist_s07_checkpoint_save_authority(job_id, state="failed", error=str(value))
        except Exception as exc:
            logger.debug("[%s] S-07 checkpoint failure authority persist failed: %s", job_id, exc)
        _record_worker_close_step_sync(job_id, "s07_checkpoint_save_failed", error=str(value))
        _persist_worker_close_progress(
            job_id,
            "S-07 checkpoint save failed",
            span="s07_checkpoint_save",
            span_state="fail",
            span_message=f"S-07 close: checkpoint save failed: {value}",
        )
        return None
    if isinstance(value, dict):
        try:
            _persist_s07_checkpoint_save_authority(job_id, state="returned", **value)
        except Exception as exc:
            _record_worker_close_step_sync(job_id, "s07_checkpoint_save_failed", error=str(exc))
            _persist_worker_close_progress(
                job_id,
                "S-07 checkpoint save authority failed",
                span="s07_checkpoint_save",
                span_state="fail",
                span_message=f"S-07 close: checkpoint save authority failed: {exc}",
            )
            return None
        return value
    return None


def _persist_worker_close_progress(
    job_id: str,
    message: str,
    *,
    span: str | None = None,
    span_state: str | None = None,
    span_message: str | None = None,
) -> None:
    current = _get_job_status(job_id) or {}
    span_payload: dict[str, Any] = {}
    if span:
        span_payload = {
            "explore_span": span,
            "explore_span_state": span_state or "start",
            "explore_span_message": span_message or message,
            "explore_span_updated_at": time.time(),
        }
    _persist_job_status(
        job_id,
        {
            **current,
            "status": "running",
            "explore_phase": "exploring",
            "explore_stage": "s07_finalize",
            "explore_message": message,
            **span_payload,
            "updated_at": time.time(),
        },
        # Close-path progress is diagnostic only. Terminal status persistence
        # remains synchronous in _finalize_worker_verdict; breadcrumbs must not
        # block worker close if a runner filesystem or status surface stalls.
        sync=False,
    )


def _record_worker_close_step_sync(job_id: str, step: str, **fields: Any) -> None:
    try:
        _append_job_debug_event(
            job_id,
            "worker_close_trace.json",
            {
                "step": str(step or "").strip(),
                "fields": dict(fields or {}),
            },
        )
    except Exception as exc:
        logger.debug("[%s] worker close trace sync append failed (%s): %s", job_id, step, exc)


def _record_worker_close_step(job_id: str, step: str, **fields: Any) -> None:
    def _write_trace() -> None:
        _record_worker_close_step_sync(job_id, step, **fields)

    threading.Thread(
        target=_write_trace,
        daemon=True,
        name=f"worker-close-trace-{job_id}-{str(step or '').strip()}",
    ).start()


def _fallback_macro_verdict(ctx, reason: str) -> RunVerdict:
    job_id = str(getattr(ctx, "job_id", "") or "")
    status = _get_job_status(job_id) or {}
    total = int(getattr(ctx, "total", 0) or 0)
    explored = 0
    try:
        explored = int(ctx.explored_count())
    except Exception:
        explored = total
    coverage = round((100.0 * explored / total), 1) if total > 0 else 0.0
    final_suggestion = str(status.get("final_phase_suggestion") or "").strip().lower()
    verdict_status = "awaiting_clarification" if final_suggestion == "awaiting_clarification" else "done"
    return RunVerdict(
        status=verdict_status,
        coverage_pct=coverage,
        verified_count=explored,
        total_count=total,
        verified_rate=coverage,
        discovered_rate=coverage,
        reasoning=(
            "Macro coordinator close-path fallback used because verdict evaluation "
            f"did not complete in time: {reason}"
        ),
    )


def _evaluate_macro_verdict_bounded(ctx, *, timeout_s: float | None = None) -> tuple[RunVerdict, bool]:
    timeout = float(timeout_s if timeout_s is not None else _MACRO_VERDICT_TIMEOUT_SECONDS)
    result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def _target() -> None:
        try:
            result_queue.put(("ok", _evaluate_run(ctx)), block=False)
        except Exception as exc:  # pragma: no cover - defensive close-path guard
            result_queue.put(("error", exc), block=False)

    thread = threading.Thread(
        target=_target,
        daemon=True,
        name=f"macro-verdict-evaluate-{getattr(ctx, 'job_id', 'unknown')}",
    )
    thread.start()
    try:
        kind, value = result_queue.get(timeout=timeout)
    except queue.Empty:
        logger.warning(
            "[%s] macro verdict evaluation timed out after %.1fs; using close-path fallback",
            getattr(ctx, "job_id", "?"),
            timeout,
        )
        return _fallback_macro_verdict(ctx, f"evaluate_timeout_{timeout:.1f}s"), True
    if kind == "error":
        logger.warning("[%s] macro verdict evaluation failed; using fallback: %s", getattr(ctx, "job_id", "?"), value)
        return _fallback_macro_verdict(ctx, f"evaluate_error_{value}"), True
    return value, False


def _macro_verdict_blob_name(job_id: str) -> str:
    return f"{job_id}/macro_verdict.json"


def _persist_macro_verdict_authority(
    job_id: str,
    *,
    state: str,
    verdict_blob: str = "",
    verdict_sha256: str = "",
    verdict_bytes: int = 0,
    verdict_status: str = "",
    error: str = "",
) -> None:
    payload = {
        "schema_version": "1.0.0",
        "state": state,
        "verdict_blob": verdict_blob,
        "verdict_sha256": verdict_sha256,
        "verdict_bytes": verdict_bytes,
        "verdict_status": verdict_status,
        "error": error,
        "recorded_at": time.time(),
    }
    _upload_to_blob(
        ARTIFACT_CONTAINER,
        f"{job_id}/{_MACRO_VERDICT_AUTHORITY_BLOB}",
        json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
    )


def _verify_macro_verdict_persisted(ctx, verdict: RunVerdict) -> dict[str, Any]:
    job_id = str(getattr(ctx, "job_id", "") or "")
    if not job_id:
        raise RuntimeError("macro_verdict_job_id_missing")
    blob_name = _macro_verdict_blob_name(job_id)
    raw = _download_blob(ARTIFACT_CONTAINER, blob_name)
    payload = json.loads(raw.decode("utf-8-sig"))
    expected_status = str(verdict.status or "").strip()
    actual_status = str(payload.get("status") or "").strip() if isinstance(payload, dict) else ""
    if not isinstance(payload, dict) or not actual_status or actual_status != expected_status:
        raise RuntimeError("macro_verdict_persist_missing_or_mismatched")
    return {
        "verdict_blob": blob_name,
        "verdict_sha256": hashlib.sha256(raw).hexdigest(),
        "verdict_bytes": len(raw),
        "verdict_status": actual_status,
    }


def _persist_macro_verdict_bounded(
    ctx,
    verdict: RunVerdict,
    *,
    timeout_s: float | None = None,
) -> dict[str, Any] | None:
    timeout = float(timeout_s if timeout_s is not None else _MACRO_VERDICT_PERSIST_TIMEOUT_SECONDS)
    result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
    job_id = str(getattr(ctx, "job_id", "") or "")

    def _target() -> None:
        try:
            _persist_verdict(ctx, verdict)
            result_queue.put(("ok", _verify_macro_verdict_persisted(ctx, verdict)), block=False)
        except Exception as exc:  # pragma: no cover - defensive close-path guard
            result_queue.put(("error", exc), block=False)

    thread = threading.Thread(
        target=_target,
        daemon=True,
        name=f"macro-verdict-persist-{getattr(ctx, 'job_id', 'unknown')}",
    )
    thread.start()
    try:
        kind, value = result_queue.get(timeout=timeout)
    except queue.Empty:
        logger.warning(
            "[%s] macro verdict persistence timed out after %.1fs; worker close continues",
            getattr(ctx, "job_id", "?"),
            timeout,
        )
        if job_id:
            try:
                _persist_macro_verdict_authority(
                    job_id,
                    state="timeout",
                    verdict_status=str(verdict.status or ""),
                    error="macro_verdict_persist_timeout",
                )
            except Exception as exc:
                logger.debug("[%s] macro verdict timeout authority persist failed: %s", job_id, exc)
        return None
    if kind == "error":
        logger.warning("[%s] macro verdict persistence failed; worker close continues: %s", getattr(ctx, "job_id", "?"), value)
        if job_id:
            try:
                _persist_macro_verdict_authority(
                    job_id,
                    state="failed",
                    verdict_status=str(verdict.status or ""),
                    error=str(value),
                )
            except Exception as exc:
                logger.debug("[%s] macro verdict failure authority persist failed: %s", job_id, exc)
        return None
    if isinstance(value, dict):
        if job_id:
            try:
                _persist_macro_verdict_authority(job_id, state="returned", **value)
            except Exception as exc:
                logger.warning("[%s] macro verdict authority persist failed; worker close continues: %s", job_id, exc)
                return None
        return value
    return None


def _run_postclose_writebacks(
    job_id: str,
    ctx,
    checkpoint: PipelineCheckpoint,
    evidence_graph: Any,
    dll_fingerprint_for_graph: str,
) -> None:
    _record_worker_close_step(job_id, "postclose_start")
    try:
        _persist_stage_kpis(job_id, checkpoint, ctx)
        _record_worker_close_step(job_id, "stage_kpis_persisted")
    except Exception as exc:
        logger.debug("[%s] postclose stage KPI write failed: %s", job_id, exc)
        _record_worker_close_step(job_id, "stage_kpis_failed", error=str(exc))

    try:
        _persist_convergence_summary(job_id, ctx)
        _record_worker_close_step(job_id, "convergence_summary_persisted")
    except Exception as exc:
        logger.debug("[%s] postclose convergence summary failed: %s", job_id, exc)
        _record_worker_close_step(job_id, "convergence_summary_failed", error=str(exc))

    if evidence_graph is not None and dll_fingerprint_for_graph:
        try:
            final_findings = _load_findings(job_id)
            evidence_graph.ingest_findings(
                dll_fingerprint_for_graph,
                final_findings,
                job_id,
            )
            evidence_graph.merge_vocab(ctx.vocab, dll_fingerprint_for_graph, job_id)
            try:
                inv_raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/invocables_map.json")
                inv_data = json.loads(inv_raw)
                evidence_graph.ingest_invocables(dll_fingerprint_for_graph, inv_data, job_id)
            except Exception:
                pass
            evidence_graph.detect_cross_dll_edges()
            evidence_graph.save_blob(ARTIFACT_CONTAINER)
            logger.info("[%s] evidence_graph: saved after worker close", job_id)
            _record_worker_close_step(job_id, "evidence_graph_persisted")
        except Exception as exc:
            logger.debug("[%s] postclose evidence graph write failed: %s", job_id, exc)
            _record_worker_close_step(job_id, "evidence_graph_failed", error=str(exc))

    try:
        from api.analysis.cohesion import emit_contract_artifacts

        emit_contract_artifacts(job_id)
        _record_worker_close_step(job_id, "contract_artifacts_emitted")
    except Exception as exc:
        logger.debug("[%s] postclose contract artifact write failed: %s", job_id, exc)
        _record_worker_close_step(job_id, "contract_artifacts_failed", error=str(exc))

    _record_worker_close_step(job_id, "postclose_complete")


def _dispatch_postclose_writebacks(
    job_id: str,
    ctx,
    checkpoint: PipelineCheckpoint,
    evidence_graph: Any,
    dll_fingerprint_for_graph: str,
) -> None:
    iteration_mode = str(getattr(ctx.runtime, "iteration_mode", "single_pass") or "single_pass")
    if iteration_mode == "floor_to_ceiling":
        _record_worker_close_step(job_id, "postclose_mode", mode="sync", iteration_mode=iteration_mode)
        _run_postclose_writebacks(job_id, ctx, checkpoint, evidence_graph, dll_fingerprint_for_graph)
        return

    _record_worker_close_step(job_id, "postclose_mode", mode="deferred", iteration_mode=iteration_mode)
    threading.Thread(
        target=_run_postclose_writebacks,
        args=(job_id, ctx, checkpoint, evidence_graph, dll_fingerprint_for_graph),
        daemon=True,
        name=f"postclose-{job_id}",
    ).start()


def _campaign_child_terminal_view(job_status: dict[str, Any] | None) -> dict[str, Any]:
    job_status = job_status if isinstance(job_status, dict) else {}
    raw_status = str(job_status.get("status") or "").strip().lower()
    raw_phase = str(job_status.get("explore_phase") or "").strip().lower()
    if _has_job_lifecycle_inconsistency(job_status):
        return {
            "is_terminal": True,
            "dll_status": "failed",
            "job_status": raw_status,
            "explore_phase": raw_phase,
            "reason": "lifecycle_inconsistency",
            "error": (
                "Lifecycle inconsistency: child job reached status=done while "
                "explore_phase remained exploring"
            ),
        }
    if not _is_terminal_job_record(job_status):
        return {
            "is_terminal": False,
            "dll_status": "exploring",
            "job_status": raw_status,
            "explore_phase": raw_phase,
            "reason": "non_terminal",
            "error": "",
        }
    if raw_status == "error":
        return {
            "is_terminal": True,
            "dll_status": "failed",
            "job_status": raw_status,
            "explore_phase": raw_phase,
            "reason": "worker_error",
            "error": str(job_status.get("explore_error") or job_status.get("error") or "").strip(),
        }
    return {
        "is_terminal": True,
        "dll_status": "done",
        "job_status": raw_status,
        "explore_phase": raw_phase,
        "reason": "terminal",
        "error": "",
    }


def _persist_worker_error(job_id: str, exc: Exception) -> None:
    logger.error("[%s] explore_worker: fatal error: %s", job_id, exc)
    try:
        from api.analysis.cohesion import emit_contract_artifacts

        emit_contract_artifacts(job_id)
    except Exception as coh_err:
        logger.debug(
            "[%s] explore_worker: emit_contract_artifacts after error failed: %s",
            job_id,
            coh_err,
        )
    current = _get_job_status(job_id) or {}
    _persist_job_status(
        job_id,
        {
            **current,
            "status": "error",
            "explore_phase": "error",
            "explore_error": str(exc),
            "updated_at": time.time(),
        },
        sync=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Context construction
# ═══════════════════════════════════════════════════════════════════════════════

def _load_prior_session_artifacts(prior_job_id: str) -> dict:
    """Load artifacts from a prior pipeline run for circular feedback."""
    artifacts: dict = {}
    if not prior_job_id:
        return artifacts

    logger.info("[circular-feedback] loading artifacts from prior job %s", prior_job_id)

    for blob_name, key, parser in (
        ("findings.json",              "findings",             json.loads),
        ("sentinel_calibration.json",  "sentinels",            None),
        ("vocab.json",                 "vocab",                json.loads),
        ("api_reference.md",           "api_reference",        None),
        ("winning_init_sequence.json", "winning_init_sequence", json.loads),
    ):
        try:
            raw = _download_blob(ARTIFACT_CONTAINER, f"{prior_job_id}/{blob_name}")
            if key == "sentinels":
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    sentinel_table = {}
                    for k, v in parsed.items():
                        try:
                            sentinel_table[int(k, 16) if isinstance(k, str) else int(k)] = str(v)
                        except (ValueError, TypeError):
                            pass
                    if sentinel_table:
                        artifacts[key] = sentinel_table
                        logger.info("[circular-feedback] loaded %d prior sentinel codes",
                                    len(sentinel_table))
            elif key == "api_reference":
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                artifacts[key] = raw
                logger.info("[circular-feedback] loaded prior api_reference (%d chars)", len(raw))
            else:
                artifacts[key] = parser(raw)
                logger.info("[circular-feedback] loaded %d prior %s",
                            len(artifacts[key]) if isinstance(artifacts[key], (list, dict)) else 1,
                            key)
        except Exception:
            pass

    return artifacts


def _load_prior_invocables(prior_job_id: str) -> list[dict[str, Any]]:
    """Load enriched invocables from a prior job when available."""
    if not prior_job_id:
        return []
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, f"{prior_job_id}/invocables_map.json")
        parsed = json.loads(raw)
    except Exception:
        return []
    if isinstance(parsed, dict):
        return [inv for inv in parsed.values() if isinstance(inv, dict)]
    if isinstance(parsed, list):
        return [inv for inv in parsed if isinstance(inv, dict)]
    return []


def _merge_invocables_from_prior(
    invocables: list[dict[str, Any]],
    prior_job_id: str,
) -> list[dict[str, Any]]:
    """Preserve richer prior parameter layouts without seeding prior findings."""
    if not prior_job_id:
        return invocables
    prior_invocables = _load_prior_invocables(prior_job_id)
    if not prior_invocables:
        return invocables
    prior_map = {
        str(inv.get("name") or "").strip(): inv
        for inv in prior_invocables
        if isinstance(inv, dict) and str(inv.get("name") or "").strip()
    }
    merged_invocables: list[dict[str, Any]] = []
    for inv in invocables:
        name = str(inv.get("name") or "").strip()
        if not name:
            continue
        prior = prior_map.get(name)
        if prior:
            merged = _merge_invocable_union(prior, inv)
            merged = _prefer_prior_parameter_layout(merged, prior, inv)
            merged_invocables.append(merged)
        else:
            merged_invocables.append(dict(inv))
    return merged_invocables


def _prefer_prior_parameter_layout(
    merged: dict[str, Any],
    prior: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """Use prior parameter layout when current rerun metadata is still generic."""
    prior_params = [p for p in (prior or {}).get("parameters") or [] if isinstance(p, dict)]
    current_params = [p for p in current.get("parameters") or [] if isinstance(p, dict)]
    if not prior_params or len(prior_params) != len(current_params):
        return merged

    def _is_generic(param: dict[str, Any]) -> bool:
        name = str(param.get("name") or "").strip()
        desc = str(param.get("description") or "").strip().lower()
        return bool(_re.match(r"^param_\d+$", name)) and (
            not desc or desc.startswith("parameter ") or desc.startswith("input ") or desc.startswith("output ")
        )

    prior_has_richer = any(not _is_generic(param) for param in prior_params)
    current_all_generic = all(_is_generic(param) for param in current_params)
    if not (prior_has_richer and current_all_generic):
        return merged

    out = dict(merged)
    out["parameters"] = [dict(p) for p in prior_params]
    return out


def _seed_prior_verified_findings(
    *,
    job_id: str,
    prior_job_id: str,
    current_findings: list[dict[str, Any]],
    prior_findings: list[dict[str, Any]],
    invocables_by_name: dict[str, dict[str, Any]] | None = None,
) -> set[str]:
    seeded_functions: set[str] = set()
    seeded_entries: list[dict[str, Any]] = []
    existing_functions = {
        str(f.get("function") or "").strip()
        for f in current_findings
        if str(f.get("function") or "").strip()
    }
    for pf in prior_findings:
        fn = str(pf.get("function") or "").strip()
        pf_status = str(pf.get("status") or pf.get("status_canonical") or "").lower()
        if not fn or pf_status not in FINDING_VERIFIED_STATUSES:
            continue
        truth_assessment = assess_reusable_truth(
            pf,
            invocable=(invocables_by_name or {}).get(fn),
        )
        if not truth_assessment.get("seed_eligible"):
            continue
        try:
            if fn in existing_functions:
                _patch_finding(job_id, fn, {
                    "status": "success",
                    "finding": pf.get("finding", ""),
                    "working_call": pf.get("working_call"),
                    "notes": f"Seeded from prior session {prior_job_id}",
                    "source": "prior_session",
                    "reusable_truth_eligible": True,
                    "reusable_truth_score": float(truth_assessment.get("score") or 0.0),
                    "reusable_truth_reasons": list(truth_assessment.get("reasons") or []),
                })
            else:
                seeded_entries.append({
                    **pf,
                    "function": fn,
                    "status": "success",
                    "finding": pf.get("finding", ""),
                    "working_call": pf.get("working_call"),
                    "notes": f"Seeded from prior session {prior_job_id}",
                    "source": "prior_session",
                    "reusable_truth_eligible": True,
                    "reusable_truth_score": float(truth_assessment.get("score") or 0.0),
                    "reusable_truth_reasons": list(truth_assessment.get("reasons") or []),
                })
                existing_functions.add(fn)
            seeded_functions.add(fn)
        except Exception:
            pass
    if seeded_entries:
        _seed_findings(job_id, seeded_entries)
    return seeded_functions


def _build_explore_context(
    job_id: str,
    invocables: list[dict],
    runtime_override: ExploreRuntime | None = None,
) -> ExploreContext:
    """Build a fully-initialised ExploreContext from a job ID and invocable list."""
    if runtime_override is None:
        _job_runtime = (_get_job_status(job_id) or {}).get("explore_runtime") or {}
        runtime = ExploreRuntime.from_job_runtime(_job_runtime)
    else:
        runtime = runtime_override
    _augment_runtime_focus_from_cluster_seed(job_id, runtime)
    if runtime.iteration_mode == "floor_to_ceiling" and runtime.ceiling_functions and not runtime.focus_functions:
        runtime.focus_functions = list(runtime.ceiling_functions)
    overlap_baseline_job_id = (
        runtime.overlap_baseline_job_id
        if runtime.overlap_baseline_job_id != runtime.prior_job_id
        else ""
    )

    if runtime.prior_job_id:
        invocables = _merge_invocables_from_prior(invocables, runtime.prior_job_id)
    if overlap_baseline_job_id:
        invocables = _merge_invocables_from_prior(invocables, overlap_baseline_job_id)

    focus_functions = {str(fn).strip() for fn in (runtime.focus_functions or []) if str(fn).strip()}
    if focus_functions:
        prioritized: list[dict] = []
        seen: set[str] = set()
        for inv in invocables:
            name = str(inv.get("name") or "").strip()
            if not name or name in seen:
                continue
            if _INIT_RE.search(name) or name in focus_functions:
                prioritized.append(inv)
                seen.add(name)
        remaining = [
            inv for inv in invocables
            if str(inv.get("name") or "").strip() and str(inv.get("name") or "").strip() not in seen
        ]
        budget = max(runtime.max_functions, len(prioritized))
        invocables = prioritized + remaining[: max(0, budget - len(prioritized))]
        total = len(invocables)
    else:
        ranked_invocables = [
            (
                describe_pass_scope_bucket(
                    inv,
                    pass_index=runtime.pass_index,
                    pass_scope_profile=runtime.pass_scope_profile,
                )[0],
                idx,
                inv,
            )
            for idx, inv in enumerate(invocables)
        ]
        ranked_invocables.sort(key=lambda item: (item[0], item[1]))
        invocables = [item[2] for item in ranked_invocables]
        total = min(len(invocables), runtime.max_functions)
        invocables = invocables[:total]

    _normalize_tool_schema_invocables(invocables)

    inv_map: dict[str, dict] = {inv["name"]: inv for inv in invocables}
    _merge_invocables(job_id, invocables)

    inv_map["enrich_invocable"] = {
        "name": "enrich_invocable", "source_type": "enrich",
        "_job_id": job_id,
        "_lane_id": runtime.lane_id,
        "_variant_id": runtime.variant_id,
        "execution": {"method": "enrich"},
        "parameters": [],
    }
    inv_map["record_finding"] = {
        "name": "record_finding", "source_type": "findings",
        "_job_id": job_id,
        "_lane_id": runtime.lane_id,
        "_variant_id": runtime.variant_id,
        "execution": {"method": "findings"},
        "parameters": [],
    }

    tool_schemas = _build_tool_schemas(invocables)

    client = _openai_client()
    model = runtime.model_override or OPENAI_EXPLORE_MODEL or OPENAI_MODEL

    prior_findings = _load_findings(job_id)
    already_explored = {f.get("function") for f in prior_findings if f.get("function")}

    _prior = _load_prior_session_artifacts(runtime.prior_job_id)
    _prior_sentinels = _prior.get("sentinels", {})
    _prior_vocab = _prior.get("vocab", {})
    _prior_findings = _prior.get("findings", [])
    _overlap_baseline = _load_prior_session_artifacts(overlap_baseline_job_id)
    _overlap_baseline_sentinels = _overlap_baseline.get("sentinels", {})
    _overlap_baseline_vocab = _overlap_baseline.get("vocab", {})
    seeded_functions: set[str] = set()

    # Persist the merged prior-context as a replayable snapshot
    if _prior and runtime.prior_job_id:
        try:
            _normalized_prior = {
                "source_job_id": runtime.prior_job_id,
                "sentinels": {
                    (f"0x{k:08X}" if isinstance(k, int) else str(k)): v
                    for k, v in _prior_sentinels.items()
                } if _prior_sentinels else {},
                "findings": {
                    str(f.get("function") or ""): f
                    for f in _prior_findings if isinstance(f, dict) and f.get("function")
                } if _prior_findings else {},
                "vocab": _prior_vocab or {},
                "init_sequence": _prior.get("winning_init_sequence") or [],
            }
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{job_id}/prior_context.json",
                json.dumps(_normalized_prior, indent=2).encode(),
            )
            logger.info("[circular-feedback] persisted prior_context.json for job %s", job_id)
        except Exception as _persist_exc:
            logger.debug("[circular-feedback] prior_context.json persist failed: %s", _persist_exc)
    if _overlap_baseline and overlap_baseline_job_id:
        try:
            _normalized_baseline = {
                "source_job_id": overlap_baseline_job_id,
                "sentinels": {
                    (f"0x{k:08X}" if isinstance(k, int) else str(k)): v
                    for k, v in _overlap_baseline_sentinels.items()
                } if _overlap_baseline_sentinels else {},
                "findings": {
                    str(f.get("function") or ""): f
                    for f in (_overlap_baseline.get("findings") or [])
                    if isinstance(f, dict) and f.get("function")
                },
                "vocab": _overlap_baseline_vocab or {},
                "init_sequence": _overlap_baseline.get("winning_init_sequence") or [],
            }
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{job_id}/overlap_baseline_context.json",
                json.dumps(_normalized_baseline, indent=2).encode(),
            )
        except Exception as _persist_exc:
            logger.debug(
                "[overlap-baseline] overlap_baseline_context.json persist failed: %s",
                _persist_exc,
            )

    if _prior_findings:
        seeded_functions = _seed_prior_verified_findings(
            job_id=job_id,
            prior_job_id=runtime.prior_job_id,
            current_findings=prior_findings,
            prior_findings=_prior_findings,
            invocables_by_name=inv_map,
        )
        already_explored.update(seeded_functions)
        logger.info("[circular-feedback] seeded %d success findings from prior session",
                    len(seeded_functions))

    # Cross-DLL prior seeding: load entity-relevant findings from other DLLs
    _cross_dll_seeded = 0
    for _xdll_job_id in (runtime.cross_dll_prior_job_ids or []):
        if not _xdll_job_id or _xdll_job_id == runtime.prior_job_id:
            continue
        try:
            _xdll_artifacts = _load_prior_session_artifacts(_xdll_job_id)
            _xdll_findings = _xdll_artifacts.get("findings", [])
            _xdll_vocab = _xdll_artifacts.get("vocab", {})
            if not _xdll_findings:
                continue
            _current_id_formats = set()
            for fmt in (_prior_vocab.get("id_formats") or []):
                if isinstance(fmt, str):
                    _current_id_formats.add(fmt.strip().lower())

            _relevant: list[dict[str, Any]] = []
            for _xf in _xdll_findings:
                _xf_status = str(_xf.get("status") or _xf.get("status_canonical") or "").lower()
                if _xf_status not in FINDING_VERIFIED_STATUSES:
                    continue
                _truth_assessment = assess_reusable_truth(
                    _xf,
                    invocable=inv_map.get(str(_xf.get("function") or "").strip()),
                )
                if not _truth_assessment.get("seed_eligible"):
                    continue
                _wc = _xf.get("working_call")
                if not isinstance(_wc, dict):
                    continue
                _wc_str = json.dumps(_wc).lower()
                _entity_match = any(fmt in _wc_str for fmt in _current_id_formats) if _current_id_formats else False
                if _entity_match:
                    _relevant.append({
                        **_xf,
                        "source": "cross_dll_prior",
                        "source_dll_job_id": _xdll_job_id,
                        "notes": f"Cross-DLL seeded from {_xdll_job_id} (entity overlap)",
                        "reusable_truth_eligible": True,
                        "reusable_truth_score": float(_truth_assessment.get("score") or 0.0),
                        "reusable_truth_reasons": list(_truth_assessment.get("reasons") or []),
                    })
            if _relevant:
                _seed_findings(job_id, _relevant)
                _cross_dll_seeded += len(_relevant)
                logger.info(
                    "[cross-dll-seed] seeded %d entity-relevant findings from %s",
                    len(_relevant), _xdll_job_id,
                )
        except Exception as _xdll_exc:
            logger.debug("[cross-dll-seed] failed for %s: %s", _xdll_job_id, _xdll_exc)
    if _cross_dll_seeded:
        logger.info("[cross-dll-seed] total cross-DLL seeded: %d from %d jobs",
                    _cross_dll_seeded, len(runtime.cross_dll_prior_job_ids))

    _run_started_at = float((_get_job_status(job_id) or {}).get("explore_started_at") or time.time())

    # Store cross-DLL seeding count for explore_config persistence
    _cross_dll_seeded_count = _cross_dll_seeded

    _initial_sentinels = dict(_SENTINEL_DEFAULTS)
    if _overlap_baseline_sentinels:
        _initial_sentinels.update(_overlap_baseline_sentinels)
    if _prior_sentinels:
        _initial_sentinels.update(_prior_sentinels)

    ctx = ExploreContext(
        job_id=job_id,
        runtime=runtime,
        client=client,
        model=model,
        run_started_at=_run_started_at,
        lane_id=runtime.lane_id,
        variant_id=runtime.variant_id,
        invocables=invocables,
        inv_map=inv_map,
        tool_schemas=tool_schemas,
        total=total,
        sentinels=_initial_sentinels,
        already_explored=already_explored,
    )
    if seeded_functions:
        ctx.live_findings.extend(_load_findings(job_id))

    ctx._prior_session = _prior  # type: ignore[attr-defined]
    ctx._overlap_baseline_session = _overlap_baseline  # type: ignore[attr-defined]
    ctx._cross_dll_seeded_count = _cross_dll_seeded_count  # type: ignore[attr-defined]
    seed_vocab: dict[str, Any] = {}
    if _overlap_baseline_vocab:
        seed_vocab.update(_overlap_baseline_vocab)
    if _prior_vocab:
        seed_vocab.update(_prior_vocab)
    if seed_vocab:
        ctx.vocab = dict(seed_vocab)

    ecr = EvidenceCandidateRegistry()
    ecr.seed_tier0()
    if seed_vocab:
        ecr.seed_tier1(seed_vocab)

    if overlap_baseline_job_id:
        try:
            _baseline_ecr_raw = _download_blob(
                ARTIFACT_CONTAINER,
                f"{overlap_baseline_job_id}/evidence_candidates.json",
            )
            _baseline_ecr_data = json.loads(_baseline_ecr_raw)
            _baseline_ecr = EvidenceCandidateRegistry.from_dict(_baseline_ecr_data)
            _baseline_merged = ecr.merge_from(
                _baseline_ecr,
                tier_override=3,
                min_tier=TIER_RUNTIME,
                source_prefix="overlap_baseline:",
                source_job=overlap_baseline_job_id,
                campaign_id=runtime.campaign_id,
            )
            logger.info(
                "[overlap-baseline] loaded ECR from %s: merged %d candidates at tier 3",
                overlap_baseline_job_id,
                _baseline_merged,
            )
        except Exception as _baseline_ecr_err:
            logger.debug("[overlap-baseline] ECR load failed: %s", _baseline_ecr_err)

    if runtime.prior_job_id:
        try:
            _prior_ecr_raw = _download_blob(
                ARTIFACT_CONTAINER,
                f"{runtime.prior_job_id}/evidence_candidates.json",
            )
            _prior_ecr_data = json.loads(_prior_ecr_raw)
            _prior_ecr = EvidenceCandidateRegistry.from_dict(_prior_ecr_data)
            _promoted = _prior_ecr.promote_to_tier(
                from_tier=2, to_tier=3, source_suffix=f"prior:{runtime.prior_job_id}",
            )
            _merged = ecr.merge_from(
                _prior_ecr,
                tier_override=3,
                min_tier=TIER_RUNTIME,
                source_job=runtime.prior_job_id,
                campaign_id=runtime.campaign_id,
            )
            logger.info(
                "[circular-feedback] loaded ECR from prior job %s: promoted %d, merged %d",
                runtime.prior_job_id, _promoted, _merged,
            )
        except Exception as _ecr_load_err:
            logger.debug("[circular-feedback] ECR prior load failed: %s", _ecr_load_err)

    for _xdll_job_id in (runtime.cross_dll_prior_job_ids or []):
        if not _xdll_job_id or _xdll_job_id == runtime.prior_job_id:
            continue
        try:
            _xdll_ecr_raw = _download_blob(
                ARTIFACT_CONTAINER,
                f"{_xdll_job_id}/evidence_candidates.json",
            )
            _xdll_ecr_data = json.loads(_xdll_ecr_raw)
            _xdll_ecr = EvidenceCandidateRegistry.from_dict(_xdll_ecr_data)
            _xdll_merged = ecr.merge_from(
                _xdll_ecr,
                tier_override=4,
                min_tier=TIER_RUNTIME,
                source_prefix="cross_dll:",
                source_job=_xdll_job_id,
                campaign_id=runtime.campaign_id,
            )
            logger.info(
                "[cross-dll-seed] loaded ECR from cross-DLL job %s: merged %d candidates at tier 4",
                _xdll_job_id, _xdll_merged,
            )
        except Exception as _xecr_err:
            logger.debug("[cross-dll-seed] ECR cross-DLL load failed for %s: %s",
                         _xdll_job_id, _xecr_err)

    ctx.evidence_candidates = ecr

    return ctx


# ═══════════════════════════════════════════════════════════════════════════════
#  Pipeline driver
# ═══════════════════════════════════════════════════════════════════════════════

def _run_single_explore_cycle(job_id: str, invocables: list[dict], runtime_override: ExploreRuntime | None = None) -> tuple[ExploreContext | None, Any]:
    """Background worker: drive the S-00 → S-07 pipeline."""
    if not _validate_explore_worker_env(job_id):
        return None, None

    try:
        try:
            ctx = _build_explore_context(job_id, invocables, runtime_override=runtime_override)
        except TypeError as exc:
            if runtime_override is None or "runtime_override" not in str(exc):
                raise
            ctx = _build_explore_context(job_id, invocables)
        _set_explore_status(job_id, 0, ctx.total, "Starting exploration...")
        _persist_explore_bootstrap_artifacts(job_id, ctx)

        # ── Checkpoint loading ─────────────────────────────────────────────
        _checkpoint: PipelineCheckpoint | None = None
        _cluster_seed_plan = None
        if ctx.runtime.checkpoint_id:
            _checkpoint = load_checkpoint(
                job_id,
                ctx.runtime.checkpoint_id,
                checkpoint_stage=ctx.runtime.checkpoint_stage,
            )
            if _checkpoint:
                _checkpoint = apply_resume_boundary(
                    _checkpoint,
                    ctx.runtime.checkpoint_stage,
                )
                if ctx.runtime.cluster_checkpoint_id:
                    _cluster_seed_plan = resolve_cluster_seed_plan(
                        _checkpoint,
                        ctx.runtime.cluster_checkpoint_id,
                        adjacent_cluster_id=ctx.runtime.adjacent_cluster_id,
                        min_confidence=float(ctx.runtime.cluster_confidence_floor or 0.5),
                    )
                    if _cluster_seed_plan is None:
                        try:
                            _upload_to_blob(
                                ARTIFACT_CONTAINER,
                                f"{job_id}/cluster_seed_plan_rejected.json",
                                json.dumps(
                                    {
                                        "cluster_checkpoint_id": ctx.runtime.cluster_checkpoint_id,
                                        "adjacent_cluster_id": ctx.runtime.adjacent_cluster_id,
                                        "checkpoint_id": ctx.runtime.checkpoint_id,
                                        "checkpoint_stage": ctx.runtime.checkpoint_stage,
                                        "cluster_confidence_floor": ctx.runtime.cluster_confidence_floor,
                                        "status": "rejected",
                                        "reason": (
                                            "cluster checkpoint reuse failed lineage/schema/confidence validation"
                                        ),
                                    },
                                    indent=2,
                                ).encode("utf-8"),
                            )
                        except Exception:
                            pass
                        logger.info(
                            "[%s] cluster-bounded checkpoint reuse rejected for %s",
                            job_id,
                            ctx.runtime.cluster_checkpoint_id,
                        )
                        _checkpoint = None
                    else:
                        merged_focus: list[str] = []
                        for fn_name in list(ctx.runtime.focus_functions or []) + list(_cluster_seed_plan.focus_functions):
                            name = str(fn_name or "").strip()
                            if name and name not in merged_focus:
                                merged_focus.append(name)
                        ctx.runtime.focus_functions = merged_focus
                        try:
                            _upload_to_blob(
                                ARTIFACT_CONTAINER,
                                f"{job_id}/cluster_seed_plan.json",
                                json.dumps(_cluster_seed_plan.to_dict(), indent=2).encode("utf-8"),
                            )
                        except Exception:
                            pass
                if _checkpoint is not None:
                    _floor_plan = _initialize_floor_iteration_plan(job_id, ctx, _checkpoint)
                    _seeded = seed_context_from_checkpoint(
                        ctx,
                        _checkpoint,
                        cluster_seed_plan=_cluster_seed_plan,
                        seed_function_allowlist=(
                            set(_floor_plan.seed_function_allowlist)
                            if _floor_plan is not None
                            else None
                        ),
                    )
                    logger.info("[%s] checkpoint loaded: %d functions seeded", job_id, _seeded)
        if _checkpoint is None:
            _checkpoint = PipelineCheckpoint(
                job_id=job_id,
                cluster_checkpoints={
                    row["cluster_id"]: row for row in build_cluster_checkpoint_snapshot()
                },
                prerequisite_state_groups={
                    row["group_id"]: row for row in build_prerequisite_state_group_snapshot()
                },
            )
        if getattr(ctx, "floor_plan", None) is None:
            _initialize_floor_iteration_plan(job_id, ctx, _checkpoint)

        ctx._checkpoint = _checkpoint

        # ── skip_to_stage support ──────────────────────────────────────────
        _STAGE_ORDER = [
            "s00", "s01", "s02", "s03", "s04", "s05", "s06", "s07",
        ]
        _skip_target = ctx.runtime.skip_to_stage.lower().replace("_", "")[:3] if ctx.runtime.skip_to_stage else ""

        def _should_skip(stage_short: str) -> bool:
            """True if this stage should be skipped — either by checkpoint or by skip_to_stage."""
            if _skip_target and stage_short in _STAGE_ORDER:
                try:
                    if _STAGE_ORDER.index(stage_short) < _STAGE_ORDER.index(_skip_target):
                        return True
                except ValueError:
                    pass
            return False

        if _skip_target:
            logger.info("[%s] skip_to_stage=%s reason=%s — stages before %s will be skipped",
                        job_id, ctx.runtime.skip_to_stage,
                        ctx.runtime.skip_to_stage_reason or "manual", _skip_target)

        _evidence_graph, _dll_fingerprint_for_graph = _load_evidence_graph_for_context(job_id, ctx)
        _apply_evidence_based_focus(ctx, _evidence_graph, _dll_fingerprint_for_graph, job_id)
        _floor_broadening_gate = {
            "allow_broadening": True,
            "reason": "single_pass",
            "blocked_groups": [],
            "group_gates": {},
            "preserved_lower_floor_functions": [],
        }

        # ── Stage imports (lazy to avoid circular deps) ────────────────────
        from api.pipeline.s00_setup import run_s00  # noqa: F401 - legacy stage dispatch surface
        from api.pipeline.s00_setup import run_admission_handoff
        from api.pipeline.s00_setup import run_setup_baseline
        from api.pipeline.s00_setup import run_static_evidence
        from api.pipeline.s01_unlock import run_s01
        from api.pipeline.s02_probe import run_s02  # noqa: F401 - legacy sync/dispatch surface
        from api.pipeline.s02_probe import run_evidence_capture
        from api.pipeline.s02_probe import run_invocation_execution
        from api.pipeline.s02_probe import run_probe_ordering
        from api.pipeline.s03_reconcile import run_s03
        from api.pipeline.s04_synthesis import run_s04
        from api.pipeline.s05_enrichment import run_s05  # noqa: F401 - legacy sync/dispatch surface
        from api.pipeline.s05_enrichment import (
            run_read_to_write_chaining,
            run_schema_backfill,
            run_verification_replay,
        )
        from api.pipeline.s06_gaps import run_s06
        from api.pipeline.s07_finalize import run_s07

        def _emit_s02_variant_namespace() -> None:
            if ctx.runtime.parallel_runs <= 1 and len(ctx.runtime.variant_configs) <= 1:
                return

            stage_prefix = f"{ctx.job_id}/stages/s02_probe"
            variant_id = ctx.variant_id or "variant-a"

            try:
                findings = _load_findings(ctx.job_id)
            except Exception:
                findings = []

            try:
                _upload_to_blob(
                    ARTIFACT_CONTAINER,
                    f"{stage_prefix}/variants/{variant_id}/findings.json",
                    json.dumps(findings, indent=2).encode(),
                )
            except Exception as exc:
                logger.debug("[%s] s02 variant findings write failed: %s", ctx.job_id, exc)

            probe_log_raw = b"[]"
            try:
                probe_log_raw = _download_blob(ARTIFACT_CONTAINER, f"{ctx.job_id}/explore_probe_log.json")
            except Exception:
                pass
            try:
                _upload_to_blob(
                    ARTIFACT_CONTAINER,
                    f"{stage_prefix}/variants/{variant_id}/probe_log.json",
                    probe_log_raw,
                )
            except Exception as exc:
                logger.debug("[%s] s02 variant probe log write failed: %s", ctx.job_id, exc)

            try:
                from api.pipeline.core.helpers import _deduplicate_findings_latest, FINDING_DISCOVERED_STATUSES

                merged_findings = _deduplicate_findings_latest(findings)
                for row in merged_findings:
                    row.setdefault("source_variant_id", variant_id)
                    row.setdefault("source_lane_id", ctx.lane_id)

                discovered_functions = sorted({
                    str(row.get("function") or "")
                    for row in merged_findings
                    if (str(row.get("status") or "") in FINDING_DISCOVERED_STATUSES
                        or str(row.get("status_canonical") or "") in FINDING_DISCOVERED_STATUSES)
                    and row.get("function")
                })
                variant_contributions = {
                    "variant_id": variant_id,
                    "lane_id": ctx.lane_id,
                    "discovered_functions": discovered_functions,
                    "discovered_count": len(discovered_functions),
                    "timestamp": time.time(),
                }
                _upload_to_blob(
                    ARTIFACT_CONTAINER,
                    f"{stage_prefix}/merged/findings.json",
                    json.dumps(merged_findings, indent=2).encode(),
                )
                _upload_to_blob(
                    ARTIFACT_CONTAINER,
                    f"{stage_prefix}/merged/probe_log.json",
                    probe_log_raw,
                )
                _upload_to_blob(
                    ARTIFACT_CONTAINER,
                    f"{stage_prefix}/merged/variant_contributions.json",
                    json.dumps(variant_contributions, indent=2).encode(),
                )
            except Exception as exc:
                logger.debug("[%s] s02 merged namespace write failed: %s", ctx.job_id, exc)

        # ── Pipeline ──────────────────────────────────────────────────────
        def _s00_blob_exists(blob_name: str) -> bool:
            try:
                _download_blob(ARTIFACT_CONTAINER, f"{job_id}/{blob_name}")
                return True
            except Exception:
                return False

        _requested_checkpoint_stage = str(getattr(ctx.runtime, "checkpoint_stage", "") or "").strip()
        _s00_setup_was_complete = is_stage_complete(_checkpoint, "s00_setup")
        if _should_skip("s00") or is_stage_complete(_checkpoint, "s00_setup_baseline"):
            logger.info("[%s] S-00A skipped (checkpoint/skip_to_stage)", job_id)
        elif _s00_setup_was_complete and _requested_checkpoint_stage != "s00_setup_baseline":
            logger.info("[%s] S-00A backfilled from existing s00_setup parent checkpoint", job_id)
            update_checkpoint_from_context(_checkpoint, ctx)
            mark_stage_complete(_checkpoint, "s00_setup_baseline", {
                "sentinel_count": len(ctx.sentinels),
                "vocab_keys": list(ctx.vocab.keys())[:10],
                "compatibility_backfilled": True,
            })
            save_checkpoint(_checkpoint)
        else:
            _set_explore_status(job_id, 0, ctx.total,
                                "S-00A: Setup baseline - calibration + vocab...",
                                stage="s00_setup_baseline")
            run_setup_baseline(ctx)
            update_checkpoint_from_context(_checkpoint, ctx)
            mark_stage_complete(_checkpoint, "s00_setup_baseline", {
                "sentinel_count": len(ctx.sentinels),
                "vocab_keys": list(ctx.vocab.keys())[:10],
            })
            mark_stage_complete(_checkpoint, "s00_setup", {
                "sentinel_count": len(ctx.sentinels),
                "vocab_keys": list(ctx.vocab.keys())[:10],
                "compatibility_parent": True,
                "derived_from": "s00_setup_baseline",
            })
            save_checkpoint(_checkpoint)

        _s00_setup_was_complete = is_stage_complete(_checkpoint, "s00_setup")
        if _should_skip("s00") or is_stage_complete(_checkpoint, "s00_static_evidence"):
            logger.info("[%s] S-00B skipped (checkpoint/skip_to_stage)", job_id)
        elif _s00_setup_was_complete and _s00_blob_exists("static_analysis.json"):
            logger.info("[%s] S-00B backfilled from existing static analysis artifact", job_id)
            update_checkpoint_from_context(_checkpoint, ctx)
            mark_stage_complete(_checkpoint, "s00_static_evidence", {
                "static_analysis_present": True,
                "compatibility_backfilled": True,
            })
            save_checkpoint(_checkpoint)
        else:
            _set_explore_status(job_id, 0, ctx.total,
                                "S-00B: Static evidence...",
                                stage="s00_static_evidence")
            run_static_evidence(ctx)
            if ctx.evidence_candidates is not None and ctx.vocab:
                ctx.evidence_candidates.seed_tier1(ctx.vocab, ctx.static_analysis_result)
                _ghidra_seeded = ctx.evidence_candidates.seed_tier1_ghidra(
                    ctx.invocables,
                    ghidra_data_types=getattr(ctx, "ghidra_data_types", None),
                )
                logger.info("[%s] ECR: seeded tier 1 from post-S00 static evidence + ghidra (%d ghidra, %s)",
                            job_id, _ghidra_seeded, ctx.evidence_candidates.stats())
            update_checkpoint_from_context(_checkpoint, ctx)
            mark_stage_complete(_checkpoint, "s00_static_evidence", {
                "static_analysis_present": bool(getattr(ctx, "static_analysis_result", None)),
                "static_enrichment_present": bool(getattr(ctx, "static_enrichment", None)),
            })
            save_checkpoint(_checkpoint)

        if _should_skip("s00") or is_stage_complete(_checkpoint, "s00_admission_handoff"):
            logger.info("[%s] S-00C skipped (checkpoint/skip_to_stage)", job_id)
        elif _s00_setup_was_complete and _s00_blob_exists("s01_handoff_packet.json"):
            logger.info("[%s] S-00C backfilled from existing handoff packet", job_id)
            update_checkpoint_from_context(_checkpoint, ctx)
            mark_stage_complete(_checkpoint, "s00_admission_handoff", {
                "packet_present": True,
                "compatibility_backfilled": True,
            })
            save_checkpoint(_checkpoint)
        else:
            _set_explore_status(job_id, 0, ctx.total,
                                "S-00C: Admission handoff...",
                                stage="s00_admission_handoff")
            run_admission_handoff(ctx)
            update_checkpoint_from_context(_checkpoint, ctx)
            mark_stage_complete(_checkpoint, "s00_admission_handoff", {
                "packet_present": bool(getattr(ctx, "s00_s01_handoff_packet", None)),
            })
            save_checkpoint(_checkpoint)

        if _should_skip("s01") or is_stage_complete(_checkpoint, "s01_unlock"):
            logger.info("[%s] S-01 skipped (checkpoint/skip_to_stage)", job_id)
        else:
            _set_explore_status(job_id, 0, ctx.total,
                                "S-01: Write-unlock probe...",
                                stage="s01_unlock")
            run_s01(ctx)
            update_checkpoint_from_context(_checkpoint, ctx)
            mark_stage_complete(_checkpoint, "s01_unlock", {
                "unlocked": ctx.unlock_result.get("unlocked", False),
            })
            save_checkpoint(_checkpoint)

        _s02_substage_order = {
            "s02_probe": 0,
            "s02_probe_ordering": 0,
            "s02_invocation_execution": 1,
            "s02_evidence_capture": 2,
        }
        _requested_s02_stage = (
            _requested_checkpoint_stage
            if _requested_checkpoint_stage in _s02_substage_order
            else ""
        )
        _s02_probe_was_complete = is_stage_complete(_checkpoint, "s02_probe")

        def _s02_should_backfill(substage_id: str) -> bool:
            if not _s02_probe_was_complete or not _requested_s02_stage:
                return False
            return _s02_substage_order[_requested_s02_stage] > _s02_substage_order[substage_id]

        if _should_skip("s02"):
            logger.info("[%s] S-02 skipped (skip_to_stage)", job_id)
        elif _s02_probe_was_complete and not _requested_s02_stage:
            logger.info("[%s] S-02 skipped (checkpoint/compatibility parent)", job_id)
        else:
            if is_stage_complete(_checkpoint, "s02_probe_ordering"):
                logger.info("[%s] S-02A skipped (checkpoint/skip_to_stage)", job_id)
            elif _s02_should_backfill("s02_probe_ordering"):
                logger.info("[%s] S-02A backfilled from existing s02_probe parent checkpoint", job_id)
                update_checkpoint_from_context(_checkpoint, ctx)
                mark_stage_complete(_checkpoint, "s02_probe_ordering", {
                    "compatibility_backfilled": True,
                    "derived_from": "s02_probe",
                })
                save_checkpoint(_checkpoint)
            else:
                _set_explore_status(job_id, 0, ctx.total,
                                    "S-02A: Probe ordering...",
                                    stage="s02_probe_ordering")
                run_probe_ordering(ctx)
                update_checkpoint_from_context(_checkpoint, ctx)
                mark_stage_complete(_checkpoint, "s02_probe_ordering", {
                    "invocable_count": len(ctx.invocables),
                    "prerequisite_state_machine": "prerequisite_state_machine.json",
                })
                save_checkpoint(_checkpoint)

            if is_stage_complete(_checkpoint, "s02_invocation_execution"):
                logger.info("[%s] S-02B skipped (checkpoint/skip_to_stage)", job_id)
            elif _s02_should_backfill("s02_invocation_execution"):
                logger.info("[%s] S-02B backfilled from existing s02_probe parent checkpoint", job_id)
                update_checkpoint_from_context(_checkpoint, ctx)
                mark_stage_complete(_checkpoint, "s02_invocation_execution", {
                    "compatibility_backfilled": True,
                    "derived_from": "s02_probe",
                })
                save_checkpoint(_checkpoint)
            else:
                _set_explore_status(job_id, 0, ctx.total,
                                    "S-02B: Invocation execution...",
                                    stage="s02_invocation_execution")
                run_invocation_execution(ctx)
                update_checkpoint_from_context(_checkpoint, ctx)
                mark_stage_complete(_checkpoint, "s02_invocation_execution", {
                    "explored_count": ctx.explored_count(),
                    "total": ctx.total,
                })
                save_checkpoint(_checkpoint)

            if is_stage_complete(_checkpoint, "s02_evidence_capture"):
                logger.info("[%s] S-02C skipped (checkpoint/skip_to_stage)", job_id)
            else:
                _set_explore_status(job_id, ctx.explored_count(), ctx.total,
                                    "S-02C: Evidence capture...",
                                    stage="s02_evidence_capture")
                run_evidence_capture(ctx)
                _emit_s02_variant_namespace()

                update_checkpoint_from_context(_checkpoint, ctx)
                mark_stage_complete(_checkpoint, "s02_evidence_capture", {
                    "sentinel_count": len(ctx.sentinels),
                    "unlock_resolved": bool(ctx.unlock_result.get("unlocked")),
                })
                mark_stage_complete(_checkpoint, "s02_probe", {
                    "compatibility_parent": True,
                    "derived_from": "s02_evidence_capture",
                })
                save_checkpoint(_checkpoint)
            if getattr(ctx, "floor_plan", None) is not None:
                refreshed_plan = build_floor_plan(
                    ctx.runtime,
                    _checkpoint,
                    current_findings=_load_findings(job_id),
                )
                if refreshed_plan is not None:
                    ctx.floor_plan = refreshed_plan
                    _persist_floor_iteration_artifacts(job_id, refreshed_plan)
                    _floor_broadening_gate = evaluate_floor_broadening_gate(
                        refreshed_plan,
                        _checkpoint,
                        current_findings=_load_findings(job_id),
                    )
                    logger.info(
                        "[%s] floor-to-ceiling broadening gate: allow=%s reason=%s blocked_groups=%s",
                        job_id,
                        _floor_broadening_gate["allow_broadening"],
                        _floor_broadening_gate["reason"],
                        ",".join(_floor_broadening_gate["blocked_groups"]) or "-",
                    )

        if ctx.evidence_candidates is not None:
            try:
                _ecr_data = ctx.evidence_candidates.to_dict()
                _upload_to_blob(
                    ARTIFACT_CONTAINER,
                    f"{job_id}/evidence_candidates.json",
                    json.dumps(_ecr_data, indent=2, default=str).encode("utf-8"),
                )
                logger.info("[%s] ECR: persisted %d candidates to blob",
                            job_id, _ecr_data.get("candidates", {}).get("total_candidates",
                                    sum(len(v) for v in _ecr_data.get("candidates", {}).values())))
            except Exception as _ecr_err:
                logger.debug("[%s] ECR persist failed: %s", job_id, _ecr_err)

        # Evidence graph: write probe findings after S-02
        if _evidence_graph is not None and _dll_fingerprint_for_graph:
            try:
                _s02_findings = _load_findings(job_id)
                _eg_updated = _evidence_graph.ingest_findings(
                    _dll_fingerprint_for_graph, _s02_findings, job_id,
                )
                logger.info("[%s] evidence_graph: ingested %d findings after S-02", job_id, _eg_updated)
            except Exception as _eg_err:
                logger.debug("[%s] evidence_graph S-02 ingest failed: %s", job_id, _eg_err)

        if is_stage_complete(_checkpoint, "s03_reconcile"):
            logger.info("[%s] S-03 skipped (checkpoint/skip_to_stage)", job_id)
        else:
            _set_explore_status(job_id, ctx.total, ctx.total,
                                "S-03: Reconciliation + MC-3...",
                                stage="s03_reconcile")
            run_s03(ctx)

            update_checkpoint_from_context(_checkpoint, ctx)
            mark_stage_complete(_checkpoint, "s03_reconcile", _stage_retry_surface(ctx, "mc3-post-reconcile"))
            save_checkpoint(_checkpoint)

        report = ""
        if not _cancel_requested(job_id):
            if not _floor_broadening_gate["allow_broadening"]:
                _record_stage_skip_reason(
                    job_id,
                    "S-04",
                    "floor_broadening_blocked",
                    _floor_broadening_gate["reason"],
                )
                _record_stage_skip_reason(
                    job_id,
                    "S-05",
                    "floor_broadening_blocked",
                    _floor_broadening_gate["reason"],
                )
                logger.info(
                    "[%s] S-04 skipped (floor_to_ceiling gate: %s)",
                    job_id,
                    _floor_broadening_gate["reason"],
                )
                report = ""
            elif is_stage_complete(_checkpoint, "s04_synthesis"):
                _clear_stage_skip_reason(job_id, "S-04")
                logger.info("[%s] S-04 skipped (checkpoint/skip_to_stage)", job_id)
                try:
                    _report_raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/api_reference.md")
                    report = _report_raw.decode("utf-8", errors="replace") if isinstance(_report_raw, bytes) else str(_report_raw)
                except Exception:
                    report = ""
            else:
                _clear_stage_skip_reason(job_id, "S-04")
                _set_explore_status(job_id, ctx.total, ctx.total,
                                    "S-04: Synthesis + MC-4...",
                                    stage="s04_synthesis")
                report = run_s04(ctx) or ""

                mark_stage_complete(_checkpoint, "s04_synthesis")
                save_checkpoint(_checkpoint)

            if report:
                _s05_stage_order = {
                    "s05_schema_backfill": 0,
                    "s05_verification_replay": 1,
                    "s05_read_to_write_chaining": 2,
                }
                _requested_s05_stage = (
                    _requested_checkpoint_stage
                    if _requested_checkpoint_stage in _s05_stage_order
                    else ""
                )
                _s05_enrichment_was_complete = is_stage_complete(_checkpoint, "s05_enrichment")

                def _s05_should_backfill(stage_id: str) -> bool:
                    if not _s05_enrichment_was_complete or not _requested_s05_stage:
                        return False
                    return _s05_stage_order[_requested_s05_stage] > _s05_stage_order[stage_id]

                if _s05_enrichment_was_complete and not _requested_s05_stage:
                    _clear_stage_skip_reason(job_id, "S-05")
                    logger.info("[%s] S-05 skipped (checkpoint/compatibility parent)", job_id)
                else:
                    _clear_stage_skip_reason(job_id, "S-05")
                    if is_stage_complete(_checkpoint, "s05_schema_backfill"):
                        logger.info("[%s] S-05A skipped (checkpoint/skip_to_stage)", job_id)
                    elif _s05_should_backfill("s05_schema_backfill"):
                        logger.info("[%s] S-05A backfilled from existing s05_enrichment parent checkpoint", job_id)
                        update_checkpoint_from_context(_checkpoint, ctx)
                        mark_stage_complete(_checkpoint, "s05_schema_backfill", {
                            "compatibility_backfilled": True,
                            "derived_from": "s05_enrichment",
                        })
                        save_checkpoint(_checkpoint)
                    else:
                        _set_explore_status(job_id, ctx.total, ctx.total,
                                            "S-05A: Schema backfill...",
                                            stage="s05_schema_backfill")
                        run_schema_backfill(ctx, report)
                        update_checkpoint_from_context(_checkpoint, ctx)
                        mark_stage_complete(_checkpoint, "s05_schema_backfill", {
                            "backfill_result": "backfill_result.json",
                            "schema_snapshot": "mcp_schema_post_discovery.json",
                        })
                        save_checkpoint(_checkpoint)

                    if is_stage_complete(_checkpoint, "s05_verification_replay"):
                        logger.info("[%s] S-05B skipped (checkpoint/skip_to_stage)", job_id)
                    elif _s05_should_backfill("s05_verification_replay"):
                        logger.info("[%s] S-05B backfilled from existing s05_enrichment parent checkpoint", job_id)
                        update_checkpoint_from_context(_checkpoint, ctx)
                        mark_stage_complete(_checkpoint, "s05_verification_replay", {
                            "compatibility_backfilled": True,
                            "derived_from": "s05_enrichment",
                        })
                        save_checkpoint(_checkpoint)
                    else:
                        _set_explore_status(job_id, ctx.total, ctx.total,
                                            "S-05B: Verification replay...",
                                            stage="s05_verification_replay")
                        run_verification_replay(ctx)
                        update_checkpoint_from_context(_checkpoint, ctx)
                        mark_stage_complete(_checkpoint, "s05_verification_replay", {
                            "verification_report": "verification-report.json",
                        })
                        save_checkpoint(_checkpoint)

                    if is_stage_complete(_checkpoint, "s05_read_to_write_chaining"):
                        logger.info("[%s] S-05C skipped (checkpoint/skip_to_stage)", job_id)
                    else:
                        _set_explore_status(job_id, ctx.total, ctx.total,
                                            "S-05C: Read-to-write chaining...",
                                            stage="s05_read_to_write_chaining")
                        run_read_to_write_chaining(ctx)
                        update_checkpoint_from_context(_checkpoint, ctx)
                        mark_stage_complete(
                            _checkpoint,
                            "s05_read_to_write_chaining",
                            _stage_retry_surface(ctx, "mc5-post-verification"),
                        )
                        mark_stage_complete(_checkpoint, "s05_enrichment", {
                            "compatibility_parent": True,
                            "derived_from": "s05_read_to_write_chaining",
                        })
                        save_checkpoint(_checkpoint)
            else:
                logger.info("[%s] S-04 synthesis returned empty — skipping S-05 backfill", job_id)

            if not _cancel_requested(job_id):
                if not _floor_broadening_gate["allow_broadening"]:
                    _record_stage_skip_reason(
                        job_id,
                        "S-06",
                        "floor_broadening_blocked",
                        _floor_broadening_gate["reason"],
                    )
                    _record_stage_skip_reason(
                        job_id,
                        "S-04R",
                        "floor_broadening_blocked",
                        _floor_broadening_gate["reason"],
                    )
                    logger.info(
                        "[%s] S-06 skipped (floor_to_ceiling gate: %s)",
                        job_id,
                        _floor_broadening_gate["reason"],
                    )
                elif is_stage_complete(_checkpoint, "s06_gaps"):
                    _clear_stage_skip_reason(job_id, "S-06")
                    logger.info("[%s] S-06 skipped (checkpoint/skip_to_stage)", job_id)
                else:
                    _clear_stage_skip_reason(job_id, "S-06")
                    _set_explore_status(job_id, ctx.total, ctx.total,
                                        "S-06: Gap resolution + MC-6...",
                                        stage="s06_gaps")
                    run_s06(ctx)

                    update_checkpoint_from_context(_checkpoint, ctx)
                    mark_stage_complete(_checkpoint, "s06_gaps")
                    save_checkpoint(_checkpoint)

                # Regenerate synthesis after gap resolution to capture MC-6 findings
                try:
                    if not _floor_broadening_gate["allow_broadening"]:
                        logger.info(
                            "[%s] S-04R skipped (floor_to_ceiling gate: %s)",
                            job_id,
                            _floor_broadening_gate["reason"],
                        )
                    elif not is_stage_complete(_checkpoint, "s06_gaps"):
                        _clear_stage_skip_reason(job_id, "S-04R")
                        _set_explore_status(job_id, ctx.total, ctx.total,
                                            "S-04R: Refreshing synthesis with post-gap findings...",
                                            stage="s04_synthesis_refresh")
                        report = run_s04(ctx) or ""
                        logger.info("[%s] post-gap synthesis refresh complete", job_id)
                except Exception as _refresh_e:
                    logger.debug("[%s] post-gap synthesis refresh failed: %s", job_id, _refresh_e)

                if report:
                    from api.pipeline.s07_finalize.behavioral_spec import _run_phase_9_behavioral_spec
                    _run_phase_9_behavioral_spec(ctx, report)

        if is_stage_complete(_checkpoint, "s07_finalize"):
            logger.info("[%s] S-07 skipped (checkpoint/skip_to_stage)", job_id)
        else:
            _set_explore_status(job_id, ctx.total, ctx.total,
                                "S-07: Harmonize + finalize...",
                                stage="s07_finalize")
            run_s07(ctx)
            _record_worker_close_step_sync(job_id, "s07_run_returned")
            mark_stage_complete(_checkpoint, "s07_finalize", {"cost_summary": ctx.cost_summary()})
            _record_worker_close_step_sync(job_id, "s07_checkpoint_save_start")
            checkpoint_save_authority = _save_s07_checkpoint_bounded(job_id, _checkpoint)
            if not checkpoint_save_authority:
                raise TimeoutError("s07_checkpoint_save_failed_or_timeout")
            _record_worker_close_step_sync(job_id, "s07_checkpoint_save_returned", **checkpoint_save_authority)
        _record_worker_close_step(job_id, "s07_finalize_complete")

        # ── Macro coordinator verdict ──────────────────────────────────────
        if getattr(ctx, "floor_plan", None) is not None:
            _record_worker_close_step(job_id, "floor_iteration_state_start")
            ctx.floor_iteration_state = build_floor_iteration_state(
                ctx.floor_plan,
                _checkpoint,
                current_findings=_load_findings(job_id),
                previous_contradiction_count=_current_contradiction_count(ctx),
            )
            _persist_floor_iteration_artifacts(job_id, ctx.floor_plan, ctx.floor_iteration_state)
            _record_worker_close_step(
                job_id,
                "floor_iteration_state_done",
                status=str(getattr(ctx.floor_iteration_state, "status", "") or ""),
            )

        _persist_worker_close_progress(
            job_id,
            "Finalize complete — computing macro verdict",
            span="s07_macro_verdict_evaluate",
            span_state="start",
            span_message="S-07 close: evaluating macro verdict.",
        )
        _record_worker_close_step_sync(job_id, "macro_verdict_start")
        verdict, verdict_fallback = _evaluate_macro_verdict_bounded(ctx)
        _persist_worker_close_progress(
            job_id,
            "Macro verdict computed — persisting verdict",
            span="s07_macro_verdict_persist",
            span_state="start",
            span_message="S-07 close: persisting macro verdict.",
        )
        _record_worker_close_step_sync(
            job_id,
            "macro_verdict_computed",
            verdict_status=str(verdict.status or ""),
            fallback=verdict_fallback,
        )
        verdict_persist_authority = _persist_macro_verdict_bounded(ctx, verdict)
        verdict_persist_fields = verdict_persist_authority if isinstance(verdict_persist_authority, dict) else {}
        _record_worker_close_step_sync(
            job_id,
            "macro_verdict_persisted" if verdict_persist_authority else "macro_verdict_persist_deferred",
            verdict_status=str(verdict.status or ""),
            verdict_blob=str(verdict_persist_fields.get("verdict_blob") or ""),
            verdict_sha256=str(verdict_persist_fields.get("verdict_sha256") or ""),
            verdict_bytes=int(verdict_persist_fields.get("verdict_bytes") or 0),
        )
        floor_state = getattr(ctx, "floor_iteration_state", None)
        if floor_state is not None and str(getattr(floor_state, "status", "") or "") == "loop_again":
            current = _get_job_status(job_id) or {}
            _persist_job_status(
                job_id,
                {
                    **current,
                    "status": "exploring",
                    "explore_phase": "exploring",
                    "explore_stage": "floor_to_ceiling",
                    "explore_progress": f"{ctx.total}/{ctx.total}",
                    "explore_message": (
                        f"Continuing floor-to-ceiling iteration "
                        f"{getattr(floor_state, 'iteration_index', 1)}"
                    ),
                    "updated_at": time.time(),
                },
                sync=True,
            )
            _record_worker_close_step(job_id, "worker_close_loop_again")
        else:
            final_status_authority = _finalize_worker_verdict_bounded(
                job_id,
                ctx,
                verdict.status,
                verdict.coverage_pct,
            )
            final_status_fields = final_status_authority if isinstance(final_status_authority, dict) else {}
            _record_worker_close_step(
                job_id,
                "worker_close_done" if final_status_authority else "worker_close_done_deferred",
                verdict_status=str(verdict.status or ""),
                status_blob=str(final_status_fields.get("status_blob") or ""),
                status_sha256=str(final_status_fields.get("status_sha256") or ""),
                status_bytes=int(final_status_fields.get("status_bytes") or 0),
                terminal_status=str(final_status_fields.get("terminal_status") or ""),
            )
        _dispatch_postclose_writebacks(
            job_id,
            ctx,
            _checkpoint,
            _evidence_graph,
            _dll_fingerprint_for_graph,
        )
        return ctx, verdict

    except Exception as exc:
        _persist_worker_error(job_id, exc)
        return None, None


# ═══════════════════════════════════════════════════════════════════════════════
def _explore_worker(job_id: str, invocables: list[dict]) -> None:
    """Background worker: drive the S-00 → S-07 pipeline."""
    logger.info("[%s] explore_worker: starting, %d functions to explore", job_id, len(invocables))
    _flush_bridge_cache(job_id)

    runtime = ExploreRuntime.from_job_runtime(((_get_job_status(job_id) or {}).get("explore_runtime") or {}))
    max_cycles = runtime.max_iteration_cycles if runtime.iteration_mode == "floor_to_ceiling" else 1
    current_runtime = runtime

    for cycle_index in range(1, max_cycles + 1):
        current_runtime = replace(current_runtime, iteration_index=cycle_index)
        ctx, verdict = _run_single_explore_cycle(
            job_id,
            invocables,
            runtime_override=current_runtime,
        )
        if ctx is None or verdict is None:
            return
        floor_state = getattr(ctx, "floor_iteration_state", None)
        if current_runtime.iteration_mode != "floor_to_ceiling":
            return
        if floor_state is None or floor_state.status != "loop_again":
            return
        if cycle_index >= max_cycles:
            current = _get_job_status(job_id) or {}
            _persist_job_status(
                job_id,
                {
                    **current,
                    "status": "done",
                    "explore_phase": "done",
                    "explore_stage": "done",
                    "explore_message": "Complete — floor-to-ceiling iteration limit reached",
                    "updated_at": time.time(),
                },
                sync=True,
            )
            return
        current_runtime = _next_floor_iteration_runtime(job_id, current_runtime, floor_state)


#  Campaign orchestration (multi-DLL support)
# ═══════════════════════════════════════════════════════════════════════════════

def _campaign_discovery_merge(campaign_id: str, camp: dict) -> dict:
    """Merge discovery results from all DLLs into a shared evidence graph + plan.

    Called by POST /api/campaigns/{campaign_id}/finalize-discovery.
    Returns the campaign plan summary dict.
    """
    from api.pipeline.core.evidence_graph import EvidenceGraph
    from api.pipeline.core.campaign_stages import run_s_pre
    from api.infra.storage import _persist_campaign_status
    from pathlib import Path
    import tempfile

    try:
        evidence_graph = EvidenceGraph.load_blob(ARTIFACT_CONTAINER)
    except Exception:
        evidence_graph = EvidenceGraph()

    targets: list[dict] = []
    for entry in camp.get("dll_entries", []):
        if entry.get("status") == "failed":
            continue
        jid = entry.get("job_id", "")
        if not jid:
            continue

        dll_fp = entry.get("dll_fingerprint", "")

        # Ingest invocables
        try:
            inv_raw = json.loads(_download_blob(ARTIFACT_CONTAINER, f"{jid}/invocables_map.json"))
            evidence_graph.ingest_invocables(dll_fp, inv_raw, jid)
        except Exception as exc:
            logger.debug("[campaign:%s] skip invocables for %s: %s", campaign_id, jid, exc)

        # Merge vocab
        try:
            vocab = json.loads(_download_blob(ARTIFACT_CONTAINER, f"{jid}/vocab.json"))
            evidence_graph.merge_vocab(vocab, dll_fp, jid)
        except Exception:
            pass

        targets.append({
            "name": entry.get("filename", ""),
            "dll_path": entry.get("dll_path", ""),
            "dll_fingerprint": dll_fp,
            "job_id": jid,
        })

    evidence_graph.detect_cross_dll_edges()

    # Save the updated graph under the campaign namespace
    try:
        graph_blob = f"campaigns/{campaign_id}/evidence_graph.json"
        _upload_to_blob(
            ARTIFACT_CONTAINER, graph_blob,
            json.dumps(evidence_graph.to_dict(), indent=2).encode(),
        )
    except Exception as exc:
        logger.warning("[campaign:%s] evidence_graph save failed: %s", campaign_id, exc)

    # Produce campaign plan
    plan_path = Path(tempfile.mkdtemp()) / "campaign_plan.json"
    plan = run_s_pre(evidence_graph, targets, plan_path)

    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"campaigns/{campaign_id}/campaign_plan.json",
            plan_path.read_bytes(),
        )
    except Exception as exc:
        logger.warning("[campaign:%s] campaign_plan save failed: %s", campaign_id, exc)

    camp["graph_epoch"] = campaign_id
    camp["updated_at"] = time.time()
    _persist_campaign_status(campaign_id, camp, sync=True)

    # Save campaign checkpoint at plan_built resume point
    from api.pipeline.core.checkpoint import CampaignCheckpoint, save_campaign_checkpoint
    ckpt = CampaignCheckpoint(
        campaign_id=campaign_id,
        phase="planning",
        evidence_graph_epoch=campaign_id,
    )
    ckpt.mark_resume_point("discovery_complete")
    ckpt.mark_resume_point("plan_built")
    save_campaign_checkpoint(ckpt)

    return {
        "target_count": plan.get("target_count", 0),
        "edge_count": plan.get("edge_count", 0),
        "parallel_groups": plan.get("parallel_groups", []),
    }


def _campaign_verified_count(latest: dict[str, dict[str, Any]]) -> int:
    return sum(
        1
        for row in latest.values()
        if str((row or {}).get("status") or (row or {}).get("status_canonical") or "")
        in FINDING_VERIFIED_STATUSES
    )


def _try_job_json(job_id: str, blob_name: str) -> dict[str, Any]:
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/{blob_name}")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _try_campaign_json(campaign_id: str, blob_name: str) -> dict[str, Any]:
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, f"campaigns/{campaign_id}/{blob_name}")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _load_campaign_frontier_plan(
    campaign_id: str,
    campaign: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(campaign, dict):
        in_memory = (
            campaign.get("package_frontier_plan")
            or campaign.get("floor_to_ceiling_plan")
            or {}
        )
        if isinstance(in_memory, dict) and in_memory:
            return dict(in_memory)
    plan = _try_campaign_json(campaign_id, "package-frontier-plan.json")
    if plan:
        return plan
    return _try_campaign_json(campaign_id, "batch-b-ceiling-plan.json")


def _load_campaign_decomposition_plan(
    campaign_id: str,
    campaign: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(campaign, dict):
        in_memory = campaign.get("decomposition_campaign_plan") or {}
        if isinstance(in_memory, dict) and in_memory:
            return dict(in_memory)
    return _try_campaign_json(campaign_id, "decomposition-campaign-plan.json")


def _persist_campaign_child_job_context(
    campaign_id: str,
    camp: dict[str, Any],
    entry: dict[str, Any],
    runtime_settings: dict[str, Any],
) -> dict[str, Any]:
    jid = str(entry.get("job_id", "") or "").strip()
    status = _get_job_status(jid) or {}
    merged_status = {
        **status,
        "campaign_id": campaign_id,
        "package_id": str(camp.get("package_id") or ""),
        "package_label": str(camp.get("package_label") or ""),
        "doc_visibility": str(camp.get("doc_visibility") or ""),
        "dependency_context": str(camp.get("dependency_context") or ""),
        "selection_reason": str(entry.get("selection_reason") or ""),
        "dependency_confidence": str(entry.get("dependency_confidence") or ""),
        "lane_id": str(entry.get("lane_id") or runtime_settings.get("lane_id") or "lane-1"),
        "source_frontier_slice_id": str(runtime_settings.get("source_frontier_slice_id") or ""),
        "decomposition_execution_unit_id": str(runtime_settings.get("decomposition_execution_unit_id") or ""),
        "required_dependency_class_ids": list(runtime_settings.get("required_dependency_class_ids") or []),
        "protected_imported_truth_ids": list(runtime_settings.get("protected_imported_truth_ids") or []),
        "interwoven_subject_ids": list(runtime_settings.get("interwoven_subject_ids") or []),
        "interwoven_contradiction_summary": dict(runtime_settings.get("interwoven_contradiction_summary") or {}),
        "interwoven_attribution_present": bool(runtime_settings.get("interwoven_attribution_present")),
    }
    _persist_job_status(jid, merged_status, sync=True)
    return merged_status


def _campaign_runtime_identity_keys(
    entry: dict[str, Any],
    job_status: dict[str, Any] | None = None,
) -> set[str]:
    status = job_status or {}
    keys = {
        str(entry.get("job_id") or "").strip(),
        str(entry.get("dll_id") or "").strip(),
        str(entry.get("filename") or "").strip(),
        str(status.get("component_name") or entry.get("filename") or "").rsplit(".", 1)[0],
    }
    return {key for key in keys if key}


def _resolve_campaign_entry_runtime(
    runtime_settings: dict[str, Any],
    per_dll_runtime_settings: dict[str, dict[str, Any]] | None,
    entry: dict[str, Any],
    job_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = dict(runtime_settings or {})
    overrides = dict(per_dll_runtime_settings or {})
    identity_keys = _campaign_runtime_identity_keys(entry, job_status)
    for key in identity_keys:
        override = overrides.get(key)
        if isinstance(override, dict):
            resolved.update(override)
            break
    return resolved


def _campaign_entry_matches_targets(
    entry: dict[str, Any],
    active_dll_targets: list[str] | tuple[str, ...] | None,
    job_status: dict[str, Any] | None = None,
) -> bool:
    targets = {
        str(value or "").strip()
        for value in list(active_dll_targets or [])
        if str(value or "").strip()
    }
    if not targets:
        return True
    return bool(_campaign_runtime_identity_keys(entry, job_status) & targets)


def _prime_campaign_child_job_for_explore(
    jid: str,
    *,
    explore_runtime: dict[str, Any],
) -> dict[str, Any]:
    current = _get_job_status(jid) or {}
    primed_status = {
        **current,
        "status": "running",
        "explore_phase": "queued",
        "explore_progress": "0/0",
        "explore_message": "Exploration queued",
        "explore_runtime": explore_runtime,
        "explore_cancel_requested": False,
        "explore_started_at": time.time(),
        "updated_at": time.time(),
    }
    _persist_job_status(jid, primed_status, sync=True)
    return primed_status


def _capture_campaign_child_job(
    campaign_id: str,
    job_id: str,
    *,
    fresh: bool,
) -> dict[str, Any]:
    from pathlib import Path
    import shutil
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    scripts_root = repo_root / "scripts"
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))

    from harness_lib.capture import run_capture

    session_dir = repo_root / "sessions" / "campaign-captures" / campaign_id / job_id
    if fresh and session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)
    result = run_capture(
        job_id=job_id,
        api_url="http://127.0.0.1:1",
        out_dir=str(session_dir),
        snapshot_profile="full",
        compatibility_mode=False,
        enforce_hard_fail=False,
    )
    return {
        "session_dir": str(result.session_dir),
        "collect_exit": int(result.collect_exit),
        "summary": result.summary,
    }


def _emit_blocker_harvest_artifacts(
    campaign_id: str,
    camp: dict[str, Any],
    entry: dict[str, Any],
    runtime_settings: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    jid = str(entry.get("job_id", "") or "").strip()
    status = _get_job_status(jid) or {}
    findings = _load_findings(jid)
    ledger_rows = read_run_ledger_rows()
    lane_trust = build_lane_trust_report(
        campaign=camp,
        entry=entry,
        status=status,
        ledger_rows=ledger_rows,
        runtime_settings=runtime_settings,
    )
    package_context = build_package_context_artifact(camp, entry)
    blocker_classification = build_blocker_classification_report(
        campaign=camp,
        entry=entry,
        findings=findings,
        lane_trust=lane_trust,
    )
    for blob_name, payload in (
        ("lane-trust.json", lane_trust),
        ("package-context.json", package_context),
        ("blocker-classification.json", blocker_classification),
    ):
        try:
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"{jid}/{blob_name}",
                json.dumps(payload, indent=2).encode("utf-8"),
            )
        except Exception as exc:
            logger.warning("[campaign:%s] %s emit failed for %s: %s", campaign_id, blob_name, jid, exc)

    _persist_job_status(
        jid,
        {
            **status,
            "package_id": package_context.get("package_id", ""),
            "package_label": package_context.get("package_label", ""),
            "doc_visibility": package_context.get("doc_visibility", ""),
            "dependency_context": package_context.get("dependency_context", ""),
            "selection_reason": str(entry.get("selection_reason") or ""),
            "dependency_confidence": str(entry.get("dependency_confidence") or ""),
            "lane_id": str(entry.get("lane_id") or runtime_settings.get("lane_id") or ""),
            "lane_trust_status": lane_trust.get("trust_status", ""),
            "runtime_path_trust": lane_trust.get("runtime_path_trust", ""),
            "blocker_family_primary": blocker_classification.get("primary_blocker_family", ""),
            "blocker_family_secondary": blocker_classification.get("secondary_blocker_families", []),
            "blocker_confidence": blocker_classification.get("blocker_confidence", ""),
            "architecture_relevance": blocker_classification.get("architecture_relevance", ""),
        },
    )
    entry["lane_id"] = str(entry.get("lane_id") or runtime_settings.get("lane_id") or "lane-1")
    entry["selection_reason"] = str(entry.get("selection_reason") or "")
    entry["dependency_confidence"] = str(entry.get("dependency_confidence") or "")
    entry["lane_trust_status"] = str(lane_trust.get("trust_status") or "")
    entry["runtime_path_trust"] = str(lane_trust.get("runtime_path_trust") or "")
    entry["blocker_family_primary"] = str(blocker_classification.get("primary_blocker_family") or "")
    entry["blocker_family_secondary"] = list(blocker_classification.get("secondary_blocker_families") or [])
    entry["blocker_confidence"] = str(blocker_classification.get("blocker_confidence") or "")
    entry["architecture_relevance"] = str(blocker_classification.get("architecture_relevance") or "")
    return lane_trust, package_context, blocker_classification


def _build_campaign_truth(campaign_id: str, camp: dict) -> dict[str, Any]:
    entries = list(camp.get("dll_entries", []) or [])
    floor_plan = _load_campaign_frontier_plan(campaign_id, camp)
    decomposition_plan = _load_campaign_decomposition_plan(campaign_id, camp)
    imported_rows = {
        str(row.get("dll") or "").strip(): dict(row)
        for row in list(floor_plan.get("imported_lower_floor_rows") or [])
        if isinstance(row, dict) and str(row.get("dll") or "").strip()
    }
    active_frontier_dlls = [
        str(name or "").strip()
        for name in list(floor_plan.get("active_frontier_dlls") or [])
        if str(name or "").strip()
    ]
    imported_lower_floor_dlls = [
        str(name or "").strip()
        for name in list(floor_plan.get("imported_lower_floor_dlls") or [])
        if str(name or "").strip()
    ]
    active_frontier_slice_ids = [
        str(name or "").strip()
        for name in list(decomposition_plan.get("active_frontier_slice_ids") or [])
        if str(name or "").strip()
    ]
    deferred_initialization_group_ids = [
        str(name or "").strip()
        for name in list(decomposition_plan.get("deferred_initialization_group_ids") or [])
        if str(name or "").strip()
    ]
    deferred_dependency_class_ids = [
        str(name or "").strip()
        for name in list(decomposition_plan.get("deferred_dependency_class_ids") or [])
        if str(name or "").strip()
    ]
    execution_units = [
        dict(row)
        for row in list(dict(decomposition_plan.get("execution_map") or {}).get("execution_units") or [])
        if isinstance(row, dict)
    ]
    execution_units_by_dll: dict[str, list[dict[str, Any]]] = {}
    for row in execution_units:
        dll_name = str(row.get("target_dll") or "").strip()
        if dll_name:
            execution_units_by_dll.setdefault(dll_name, []).append(row)
    per_dll: list[dict[str, Any]] = []
    findings_by_job: dict[str, list[dict[str, Any]]] = {}
    attribution_mode_counts = {"none": 0, "same_dll": 0, "cross_dll": 0, "overlap_baseline": 0}
    hidden_variable_warnings: list[str] = []
    total_verified = 0
    total_functions = 0
    baseline_contract = resolve_campaign_package_baseline_contract(
        camp,
        package_frontier_plan=floor_plan,
    )
    overlap_set = {
        str(item).strip()
        for item in list(baseline_contract.get("overlap_dll_set") or [])
        if str(item).strip()
    }
    no_baseline_required_set = {
        str(item).strip()
        for item in list(baseline_contract.get("no_baseline_required_dlls") or [])
        if str(item).strip()
    }

    for entry in entries:
        jid = str(entry.get("job_id", "") or "").strip()
        if not jid:
            continue
        status = _get_job_status(jid) or {}
        runtime = status.get("explore_runtime") or {}
        discovery_meta = status.get("discovery_meta") or {}
        findings = _load_findings(jid)
        findings_by_job[jid] = findings
        latest = {
            str(row.get("function") or "").strip(): row
            for row in findings
            if isinstance(row, dict) and str(row.get("function") or "").strip()
        }
        prior_job_id = str(runtime.get("prior_job_id") or "").strip()
        overlap_baseline_job_id = str(runtime.get("overlap_baseline_job_id") or "").strip()
        cross_dll_prior_job_ids = list(runtime.get("cross_dll_prior_job_ids") or [])
        attribution_mode = "none"
        if cross_dll_prior_job_ids:
            attribution_mode = "cross_dll"
        elif prior_job_id:
            attribution_mode = "same_dll"
        elif overlap_baseline_job_id:
            attribution_mode = "overlap_baseline"
        attribution_mode_counts[attribution_mode] += 1

        analysis_entrypoint = str(status.get("analysis_entrypoint") or "")
        binary_origin = str(status.get("binary_origin") or "")
        analysis_profile = str(runtime.get("analysis_profile") or status.get("analysis_profile") or "")
        cache_state = str(discovery_meta.get("cache_state") or "")
        graph_epoch = str(runtime.get("graph_epoch") or status.get("graph_epoch") or "none")
        blocker_classification = _try_job_json(jid, "blocker-classification.json")
        lane_trust = _try_job_json(jid, "lane-trust.json")
        comparable_surface_ready = all(
            [analysis_entrypoint, binary_origin, analysis_profile, cache_state, graph_epoch]
        )
        identity_candidates = {
            str(entry.get("dll_id") or "").strip(),
            str(entry.get("filename") or "").strip(),
            str(status.get("component_name") or entry.get("filename") or "").rsplit(".", 1)[0],
        }
        baseline_required = bool(identity_candidates & overlap_set)
        no_baseline_required = bool(identity_candidates & no_baseline_required_set)
        if not comparable_surface_ready:
            hidden_variable_warnings.append(
                f"{jid}: missing comparison fields "
                f"(analysis_entrypoint={bool(analysis_entrypoint)}, "
                f"binary_origin={bool(binary_origin)}, "
                f"analysis_profile={bool(analysis_profile)}, "
                f"cache_state={bool(cache_state)}, graph_epoch={bool(graph_epoch)})"
            )

        verified_count = _campaign_verified_count(latest)
        total_count = len(latest)
        imported = imported_rows.get(str(entry.get("filename") or "").strip())
        if imported and entry.get("status") == "skipped":
            verified_count = int(imported.get("verified_count") or 0)
            total_count = int(imported.get("total_functions") or 0)
        total_verified += verified_count
        total_functions += total_count
        per_dll.append(
            {
                "job_id": jid,
                "dll_id": entry.get("dll_id", ""),
                "filename": entry.get("filename", ""),
                "status": entry.get("status", ""),
                "package_id": str(camp.get("package_id") or ""),
                "package_label": str(camp.get("package_label") or ""),
                "selection_reason": str(entry.get("selection_reason") or status.get("selection_reason") or ""),
                "dependency_confidence": str(entry.get("dependency_confidence") or status.get("dependency_confidence") or ""),
                "lane_id": str(entry.get("lane_id") or status.get("lane_id") or "lane-1"),
                "dll_fingerprint": str(entry.get("dll_fingerprint") or status.get("dll_fingerprint") or ""),
                "analysis_entrypoint": analysis_entrypoint,
                "binary_origin": binary_origin,
                "analysis_profile": analysis_profile,
                "cache_state": cache_state,
                "bridge_reachable": discovery_meta.get("bridge_reachable"),
                "graph_epoch": graph_epoch,
                "prior_job_id": prior_job_id,
                "overlap_baseline_job_id": overlap_baseline_job_id,
                "cross_dll_prior_job_ids": cross_dll_prior_job_ids,
                "cross_dll_prior_job_count": len(cross_dll_prior_job_ids),
                "attribution_mode": attribution_mode,
                "comparable_surface_ready": comparable_surface_ready,
                "baseline_required": baseline_required,
                "no_baseline_required": no_baseline_required,
                "verified_count": verified_count,
                "total_functions": total_count,
                "active_frontier": str(entry.get("filename") or "").strip() in active_frontier_dlls,
                "imported_lower_floor": str(entry.get("filename") or "").strip() in imported_lower_floor_dlls,
                "imported_from_job_id": str((imported or {}).get("source_job_id") or ""),
                "source_frontier_slice_id": str(status.get("source_frontier_slice_id") or ""),
                "decomposition_execution_unit_id": str(status.get("decomposition_execution_unit_id") or ""),
                "required_dependency_class_ids": list(status.get("required_dependency_class_ids") or []),
                "protected_imported_truth_ids": list(status.get("protected_imported_truth_ids") or []),
                "interwoven_subject_ids": list(status.get("interwoven_subject_ids") or []),
                "interwoven_contradiction_summary": dict(status.get("interwoven_contradiction_summary") or {}),
                "interwoven_attribution_present": bool(
                    status.get("interwoven_attribution_present")
                    or any(bool(unit.get("interwoven_attribution_present")) for unit in execution_units_by_dll.get(str(entry.get("filename") or "").strip(), []))
                ),
                "slice_execution_attribution_present": bool(
                    execution_units_by_dll.get(str(entry.get("filename") or "").strip())
                ),
                "lane_trust_status": str(
                    lane_trust.get("trust_status")
                    or status.get("lane_trust_status")
                    or entry.get("lane_trust_status")
                    or ""
                ),
                "runtime_path_trust": str(
                    lane_trust.get("runtime_path_trust")
                    or status.get("runtime_path_trust")
                    or entry.get("runtime_path_trust")
                    or ""
                ),
                "blocker_family_primary": str(
                    blocker_classification.get("primary_blocker_family")
                    or status.get("blocker_family_primary")
                    or entry.get("blocker_family_primary")
                    or ""
                ),
                "blocker_family_secondary": list(
                    blocker_classification.get("secondary_blocker_families")
                    or status.get("blocker_family_secondary")
                    or entry.get("blocker_family_secondary")
                    or []
                ),
                "blocker_confidence": str(
                    blocker_classification.get("blocker_confidence")
                    or status.get("blocker_confidence")
                    or entry.get("blocker_confidence")
                    or ""
                ),
                "architecture_relevance": str(
                    blocker_classification.get("architecture_relevance")
                    or status.get("architecture_relevance")
                    or entry.get("architecture_relevance")
                    or ""
                ),
                "candidate_next_system": str(blocker_classification.get("candidate_next_system") or ""),
            }
        )

    has_same = attribution_mode_counts["same_dll"] > 0
    has_cross = attribution_mode_counts["cross_dll"] > 0
    if has_same and has_cross:
        seeding_mode = "mixed"
    elif has_cross:
        seeding_mode = "cross_dll_prior"
    elif has_same:
        seeding_mode = "same_dll_prior"
    else:
        seeding_mode = "none"

    blocker_harvest_summary = summarize_campaign_blocker_harvest(per_dll)
    overlap_rows = [row for row in per_dll if bool(row.get("baseline_required"))]
    overlap_baseline_comparable = bool(overlap_rows) and all(
        bool(row.get("comparable_surface_ready")) for row in overlap_rows
    )
    package_internal_truth_ready = bool(per_dll) and len(per_dll) == len(entries)
    active_frontier_defined = bool(active_frontier_dlls)
    imported_lower_floor_truth_recorded = (
        (not imported_lower_floor_dlls or any(bool(row.get("imported_lower_floor")) for row in per_dll))
        and bool(per_dll)
    )
    package_floor_evidence_class = classify_package_floor_evidence(
        baseline_contract_present=bool(baseline_contract),
        active_frontier_defined=active_frontier_defined,
        imported_lower_floor_truth_recorded=imported_lower_floor_truth_recorded,
        comparable_profile_consistent=overlap_baseline_comparable,
        run_valid_green=package_internal_truth_ready,
    )
    package_floor_confirmation_ready = package_floor_evidence_class == "overlap_comparable_confirmation"
    evidence_graph = _try_campaign_json(campaign_id, "evidence_graph.json") or {}
    cross_dll_contracts = build_business_object_contract_surface(
        campaign_id=campaign_id,
        campaign_graph_epoch=str(camp.get("graph_epoch") or campaign_id),
        per_dll_rows=per_dll,
        latest_findings_by_job=_latest_findings_by_job(findings_by_job),
        evidence_graph=evidence_graph if isinstance(evidence_graph, dict) else {},
    )
    return {
        "schema_version": "1.0.0",
        "campaign_id": campaign_id,
        "package_id": str(camp.get("package_id") or ""),
        "package_label": str(camp.get("package_label") or ""),
        "package_context": dict(camp.get("package_context", {}) or {}),
        "source_origin": str(camp.get("source_origin") or ""),
        "package_purpose": str(camp.get("package_purpose") or ""),
        "doc_visibility": str(camp.get("doc_visibility") or ""),
        "dependency_context": str(camp.get("dependency_context") or ""),
        "operator_notes": str(camp.get("operator_notes") or ""),
        "phase": camp.get("phase", ""),
        "dll_count": len(entries),
        "package_floor": dict(floor_plan.get("package_floor") or {}),
        "floor_to_ceiling_plan_present": bool(floor_plan),
        "package_frontier_plan_present": bool(floor_plan),
        "decomposition_plan_present": bool(decomposition_plan),
        "active_frontier_dlls": active_frontier_dlls,
        "imported_lower_floor_dlls": imported_lower_floor_dlls,
        "active_frontier_slice_ids": active_frontier_slice_ids,
        "imported_to_active_ratio": decomposition_plan.get("imported_to_active_ratio", 0.0),
        "deferred_initialization_group_ids": deferred_initialization_group_ids,
        "deferred_dependency_class_ids": deferred_dependency_class_ids,
        "interwoven_artifact_presence": bool(decomposition_plan.get("interwoven_artifact_presence")),
        "interwoven_subject_ids": list(decomposition_plan.get("interwoven_subject_ids") or []),
        "interwoven_contradiction_summary": dict(decomposition_plan.get("interwoven_contradiction_summary") or {}),
        "interwoven_attribution_present": bool(decomposition_plan.get("interwoven_attribution_present")),
        "slice_execution_attribution_present": bool(execution_units),
        "graph_epoch": camp.get("graph_epoch") or campaign_id,
        "seeding_mode": seeding_mode,
        "total_verified": total_verified,
        "total_functions": total_functions,
        "verified_rate": (total_verified / total_functions) if total_functions else 0.0,
        "attribution_mode_counts": attribution_mode_counts,
        "hidden_variable_warnings": hidden_variable_warnings,
        "package_internal_truth_ready": package_internal_truth_ready,
        "baseline_contract_present": bool(baseline_contract),
        "package_floor_evidence_class": package_floor_evidence_class,
        "package_floor_confirmation_ready": package_floor_confirmation_ready,
        "overlap_baseline_comparable": overlap_baseline_comparable,
        "overlap_dll_count": len(overlap_rows),
        "package_wide_comparable": overlap_baseline_comparable and not no_baseline_required_set and bool(per_dll),
        "lane_gate": dict(camp.get("lane_gate") or {}),
        "blocker_harvest_summary": blocker_harvest_summary,
        "cross_dll_contracts": cross_dll_contracts,
        "per_dll": per_dll,
        "baseline_contract": baseline_contract,
        "created_at": time.time(),
    }


def _campaign_explore_orchestrator(
    campaign_id: str,
    camp: dict,
    runtime_settings: dict,
    per_dll_runtime_settings: dict[str, dict[str, Any]] | None = None,
    active_dll_targets: list[str] | None = None,
) -> None:
    """Background worker: run explore for each DLL in dependency order, then consolidate.

    Respects campaign cancellation and partial-failure semantics.
    """
    from api.pipeline.core.types import CampaignPhase, DllStatus
    from api.pipeline.core.campaign_stages import run_s_post
    from api.pipeline.core.evidence_graph import EvidenceGraph
    from api.analysis.cohesion import (
        emit_campaign_attribution_report,
        emit_campaign_cohesion_report,
    )
    from api.infra.storage import _persist_campaign_status, _get_campaign_status
    from pathlib import Path
    import tempfile

    from api.pipeline.core.checkpoint import (
        CampaignCheckpoint, save_campaign_checkpoint, load_campaign_checkpoint,
    )

    logger.info("[campaign:%s] explore orchestrator started", campaign_id)

    # Load or create campaign checkpoint for resumability
    campaign_ckpt = load_campaign_checkpoint(campaign_id) or CampaignCheckpoint(
        campaign_id=campaign_id, evidence_graph_epoch=campaign_id,
    )

    # Load campaign plan for execution order
    try:
        plan_raw = json.loads(
            _download_blob(ARTIFACT_CONTAINER, f"campaigns/{campaign_id}/campaign_plan.json")
        )
        execution_order = plan_raw.get("execution_order", [])
    except Exception:
        execution_order = []

    entries = camp.get("dll_entries", [])
    entry_by_fp = {e.get("dll_fingerprint", ""): e for e in entries}
    entry_by_job = {e.get("job_id", ""): e for e in entries}

    # Build ordered list of DLLs to explore
    ordered_entries = []
    if execution_order:
        for fp in execution_order:
            e = entry_by_fp.get(fp)
            if e and e.get("status") not in ("failed", "skipped"):
                ordered_entries.append(e)
    # Add any entries not in the execution order
    seen_jobs = {e.get("job_id") for e in ordered_entries}
    for e in entries:
        if e.get("job_id") not in seen_jobs and e.get("status") not in ("failed", "skipped"):
            ordered_entries.append(e)

    completed_runs: list[dict] = []
    cross_job_ids: list[str] = [e.get("job_id", "") for e in entries if e.get("job_id")]
    stop_after_lifecycle_inconsistency = False

    for entry in ordered_entries:
        # Check for cancellation
        fresh_camp = _get_campaign_status(campaign_id) or camp
        if fresh_camp.get("cancel_requested"):
            entry["status"] = DllStatus.SKIPPED.value
            logger.info("[campaign:%s] skipping %s due to cancellation", campaign_id, entry.get("filename"))
            continue

        jid = entry.get("job_id", "")
        dll_id = entry.get("dll_id", jid)
        if not jid:
            continue

        # Skip DLLs already completed in a prior run (checkpoint resume)
        if campaign_ckpt.is_dll_complete(dll_id):
            entry["status"] = DllStatus.DONE.value
            logger.info("[campaign:%s] skipping %s (already complete per checkpoint)", campaign_id, dll_id)
            continue

        job_status = _get_job_status(jid) or {}
        if not _campaign_entry_matches_targets(entry, active_dll_targets, job_status):
            entry["status"] = DllStatus.SKIPPED.value
            entry["imported_lower_floor"] = True
            logger.info(
                "[campaign:%s] importing lower-floor DLL %s from plan instead of live explore",
                campaign_id,
                entry.get("filename") or jid,
            )
            continue

        entry["status"] = DllStatus.EXPLORING.value
        camp["dll_entries"] = entries
        camp["updated_at"] = time.time()
        _persist_campaign_status(campaign_id, camp)

        # Load invocables for this DLL
        try:
            inv_raw = _download_blob(ARTIFACT_CONTAINER, f"{jid}/invocables_map.json")
            inv_map = json.loads(inv_raw)
            invocables = list(inv_map.values()) if isinstance(inv_map, dict) else inv_map
        except Exception as exc:
            logger.error("[campaign:%s] failed to load invocables for %s: %s", campaign_id, jid, exc)
            entry["status"] = DllStatus.FAILED.value
            entry["error"] = f"No invocables: {exc}"
            continue

        # Set up runtime for this DLL with cross-DLL context
        other_job_ids = [j for j in cross_job_ids if j != jid]
        explore_runtime = _resolve_campaign_entry_runtime(
            runtime_settings,
            per_dll_runtime_settings,
            entry,
            job_status,
        )
        overlap_baseline_job_id = ""
        for baseline_entry in list((camp.get("baseline_contract") or {}).get("dll_entries") or []):
            if not isinstance(baseline_entry, dict):
                continue
            identity_candidates = _campaign_runtime_identity_keys(entry, job_status)
            baseline_identity = {
                str(baseline_entry.get("dll_id") or "").strip(),
                str(baseline_entry.get("filename") or "").strip(),
                str(baseline_entry.get("component") or "").strip(),
            }
            if identity_candidates & baseline_identity:
                overlap_baseline_job_id = str(baseline_entry.get("baseline_job_id") or "").strip()
                break
        if overlap_baseline_job_id:
            explore_runtime["overlap_baseline_job_id"] = overlap_baseline_job_id
        explore_runtime["cross_dll_prior_job_ids"] = other_job_ids
        explore_runtime["graph_epoch"] = campaign_id
        explore_runtime["campaign_id"] = campaign_id
        explore_runtime["lane_id"] = entry.get("lane_id", "")
        _prime_campaign_child_job_for_explore(jid, explore_runtime=explore_runtime)

        # Run explore for this DLL (blocking — serialized per bridge constraint)
        try:
            _explore_worker(jid, invocables)
            terminal_view = _campaign_child_terminal_view(_get_job_status(jid) or {})
            entry["job_status"] = terminal_view["job_status"]
            entry["explore_phase"] = terminal_view["explore_phase"]
            entry["status"] = terminal_view["dll_status"]
            if terminal_view["error"]:
                entry["error"] = str(terminal_view["error"])[:500]
            if not terminal_view["is_terminal"]:
                entry["status"] = DllStatus.FAILED.value
                entry["error"] = (
                    "Lifecycle inconsistency: explore worker returned before child "
                    "job reached a terminal status/phase pair"
                )
            if terminal_view["reason"] == "lifecycle_inconsistency":
                stop_after_lifecycle_inconsistency = True
            _persist_campaign_child_job_context(campaign_id, camp, entry, explore_runtime)
            camp["dll_entries"] = entries
            camp["updated_at"] = time.time()
            _persist_campaign_status(campaign_id, camp)
            try:
                capture_result = _capture_campaign_child_job(campaign_id, jid, fresh=True)
                logger.info(
                    "[campaign:%s] child capture complete for %s (collect_exit=%s)",
                    campaign_id,
                    jid,
                    capture_result.get("collect_exit"),
                )
            except Exception as exc:
                logger.error("[campaign:%s] child capture failed for %s: %s", campaign_id, jid, exc)

            # Collect results for S-post consolidation
            run_result: dict = {"dll_fingerprint": entry.get("dll_fingerprint", ""), "job_id": jid}
            try:
                run_result["findings"] = _load_findings(jid)
            except Exception:
                run_result["findings"] = []
            try:
                run_result["invocables"] = json.loads(
                    _download_blob(ARTIFACT_CONTAINER, f"{jid}/invocables_map.json")
                )
            except Exception:
                run_result["invocables"] = {}
            try:
                run_result["vocab"] = json.loads(
                    _download_blob(ARTIFACT_CONTAINER, f"{jid}/vocab.json")
                )
            except Exception:
                run_result["vocab"] = {}
            # Collect cost metrics from job status
            job_st = _get_job_status(jid) or {}
            run_result["cost_summary"] = job_st.get("cost_summary", {})
            if entry["status"] == DllStatus.DONE.value:
                completed_runs.append(run_result)
                campaign_ckpt.mark_dll_complete(dll_id)
                campaign_ckpt.phase = CampaignPhase.EXECUTING.value
                save_campaign_checkpoint(campaign_ckpt)
        except Exception as exc:
            logger.error("[campaign:%s] explore failed for %s: %s", campaign_id, jid, exc)
            entry["status"] = DllStatus.FAILED.value
            entry["error"] = str(exc)[:500]
            _persist_campaign_child_job_context(campaign_id, camp, entry, explore_runtime)
            try:
                _capture_campaign_child_job(campaign_id, jid, fresh=True)
            except Exception as capture_exc:
                logger.error(
                    "[campaign:%s] failed-run capture failed for %s: %s",
                    campaign_id,
                    jid,
                    capture_exc,
                )
        finally:
            if entry.get("status") in {DllStatus.DONE.value, DllStatus.FAILED.value}:
                try:
                    _persist_campaign_child_job_context(campaign_id, camp, entry, explore_runtime)
                    _emit_blocker_harvest_artifacts(campaign_id, camp, entry, explore_runtime)
                    _capture_campaign_child_job(campaign_id, jid, fresh=False)
                except Exception as exc:
                    logger.error(
                        "[campaign:%s] blocker-harvest emit failed for %s: %s",
                        campaign_id,
                        jid,
                        exc,
                    )
                camp["dll_entries"] = entries
                camp["updated_at"] = time.time()
                _persist_campaign_status(campaign_id, camp)
        if stop_after_lifecycle_inconsistency:
            logger.error(
                "[campaign:%s] stopping after lifecycle inconsistency on %s",
                campaign_id,
                jid,
            )
            break

    # ── Consolidation (S-post) ────────────────────────────────────────────
    camp["phase"] = CampaignPhase.CONSOLIDATING.value
    camp["dll_entries"] = entries
    camp["updated_at"] = time.time()
    _persist_campaign_status(campaign_id, camp, sync=True)

    if completed_runs:
        evidence_graph = EvidenceGraph()
        try:
            graph_raw = _download_blob(ARTIFACT_CONTAINER, f"campaigns/{campaign_id}/evidence_graph.json")
            evidence_graph = EvidenceGraph.from_dict(json.loads(graph_raw))
        except Exception:
            pass

        consolidation_path = Path(tempfile.mkdtemp()) / "consolidation_report.json"
        try:
            report = run_s_post(evidence_graph, completed_runs, consolidation_path)
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"campaigns/{campaign_id}/consolidation_report.json",
                json.dumps(report, indent=2).encode(),
            )
            _upload_to_blob(
                ARTIFACT_CONTAINER,
                f"campaigns/{campaign_id}/evidence_graph.json",
                json.dumps(evidence_graph.to_dict(), indent=2).encode(),
            )
        except Exception as exc:
            logger.error("[campaign:%s] S-post consolidation failed: %s", campaign_id, exc)

    campaign_truth: dict[str, Any] | None = None
    try:
        campaign_truth = _build_campaign_truth(campaign_id, camp)
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"campaigns/{campaign_id}/campaign-truth.json",
            json.dumps(campaign_truth, indent=2).encode(),
        )
    except Exception as exc:
        logger.error("[campaign:%s] campaign truth emit failed: %s", campaign_id, exc)

    try:
        emit_campaign_cohesion_report(campaign_id, camp)
    except Exception as exc:
        logger.error("[campaign:%s] campaign cohesion emit failed: %s", campaign_id, exc)
    try:
        emit_campaign_attribution_report(campaign_id, camp)
    except Exception as exc:
        logger.error("[campaign:%s] campaign attribution emit failed: %s", campaign_id, exc)

    campaign_ckpt.mark_resume_point("consolidation_complete")
    campaign_ckpt.phase = CampaignPhase.CONSOLIDATING.value
    save_campaign_checkpoint(campaign_ckpt)

    # Determine final phase
    any_done = any(e.get("status") == DllStatus.DONE.value for e in entries)
    any_failed = any(e.get("status") == DllStatus.FAILED.value for e in entries)
    was_cancelled = camp.get("cancel_requested", False)

    if was_cancelled:
        camp["phase"] = CampaignPhase.CANCELLED_PARTIAL.value
    elif any_failed and any_done:
        camp["phase"] = CampaignPhase.PARTIAL_FAILURE.value
    elif any_done:
        camp["phase"] = CampaignPhase.DONE.value
    else:
        camp["phase"] = CampaignPhase.PARTIAL_FAILURE.value

    camp["dll_entries"] = entries
    camp["updated_at"] = time.time()
    _persist_campaign_status(campaign_id, camp, sync=True)
    try:
        campaign_truth = _build_campaign_truth(campaign_id, camp)
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"campaigns/{campaign_id}/campaign-truth.json",
            json.dumps(campaign_truth, indent=2).encode(),
        )
    except Exception as exc:
        logger.error("[campaign:%s] final campaign truth emit failed: %s", campaign_id, exc)
    try:
        emit_campaign_cohesion_report(campaign_id, camp)
    except Exception as exc:
        logger.error("[campaign:%s] final campaign cohesion emit failed: %s", campaign_id, exc)
    try:
        emit_campaign_attribution_report(campaign_id, camp)
    except Exception as exc:
        logger.error("[campaign:%s] final campaign attribution emit failed: %s", campaign_id, exc)
    campaign_ckpt.phase = camp["phase"]
    save_campaign_checkpoint(campaign_ckpt)
    logger.info("[campaign:%s] explore orchestrator finished — phase=%s", campaign_id, camp["phase"])
