"""
api/routes/body_parsers.py – Request body parsing and normalization helpers.

Extracted from api/routes/main.py to keep the endpoint handlers file focused on
HTTP routing logic.  All functions here are pure (no I/O, no FastAPI imports).
"""

from __future__ import annotations

from typing import Any

from api.pipeline.core.cluster_checkpoint import infer_cluster_checkpoint_id
from api.pipeline.core.floor_iteration import normalize_floor_scope, normalize_iteration_mode


# ── Primitive coercions ────────────────────────────────────────────────────

def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _as_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


# ── Explore-runtime normalization ──────────────────────────────────────────

def _normalize_explore_runtime_settings(body: dict[str, Any] | None) -> dict[str, Any]:
    body = body or {}
    raw = body.get("explore_settings") or {}
    if not isinstance(raw, dict):
        raw = {}
    if not raw:
        raw = {
            key: value
            for key, value in body.items()
            if key != "invocables"
        }

    mode = str(raw.get("mode") or "normal").strip().lower()
    if mode not in {"dev", "normal", "extended"}:
        mode = "normal"

    mode_defaults = {
        "dev": {
            "cap_profile": "dev",
            "max_rounds": 2,
            "max_tool_calls": 5,
            "gap_resolution_enabled": False,
            "clarification_questions_enabled": True,
        },
        "normal": {
            "cap_profile": "deploy",
            "max_rounds": 5,
            "max_tool_calls": 8,
            "gap_resolution_enabled": True,
            "clarification_questions_enabled": True,
        },
        "extended": {
            "cap_profile": "deploy",
            "max_rounds": 7,
            "max_tool_calls": 14,
            "gap_resolution_enabled": True,
            "clarification_questions_enabled": True,
        },
    }

    defaults = mode_defaults[mode]
    cap_profile = str(raw.get("cap_profile") or defaults["cap_profile"]).strip().lower()
    if cap_profile not in {"dev", "stabilize", "deploy"}:
        cap_profile = defaults["cap_profile"]

    # Allow per-request model override for A/B model comparison.
    # Must be a known deployment name; empty string means use env-var default.
    _model_override = str(raw.get("model") or "").strip()

    _instruction_fragment = str(raw.get("instruction_fragment") or "").strip()
    _context_density = str(raw.get("context_density") or "full").strip().lower()
    if _context_density not in {"full", "minimal", "none"}:
        _context_density = "full"
    _analysis_profile = str(raw.get("analysis_profile") or "strict_dll").strip().lower()
    if _analysis_profile not in {"strict_dll", "greybox_dll", "full_surface"}:
        _analysis_profile = "strict_dll"

    _variant_configs = raw.get("variant_configs") or []
    if not isinstance(_variant_configs, list):
        _variant_configs = []

    _parallel_runs = _as_int(raw.get("parallel_runs"), 1, 1, 16)
    _lane_id = str(raw.get("lane_id") or "").strip()
    _variant_id = str(raw.get("variant_id") or "").strip()
    _iteration_mode = normalize_iteration_mode(str(raw.get("iteration_mode") or ""))
    _floor_scope = normalize_floor_scope(str(raw.get("floor_scope") or ""))

    return {
        "mode": mode,
        "cap_profile": cap_profile,
        "max_rounds": _as_int(raw.get("max_rounds"), int(defaults["max_rounds"]), 1, 12),
        "max_tool_calls": _as_int(raw.get("max_tool_calls"), int(defaults["max_tool_calls"]), 1, 24),
        "max_functions": _as_int(raw.get("max_functions"), 50, 1, 500),
        "min_direct_probes_per_function": _as_int(raw.get("min_direct_probes_per_function"), 1, 1, 5),
        "skip_documented": _as_bool(raw.get("skip_documented"), True),
        "deterministic_fallback_enabled": _as_bool(raw.get("deterministic_fallback_enabled"), True),
        "gap_resolution_enabled": _as_bool(raw.get("gap_resolution_enabled"), bool(defaults["gap_resolution_enabled"])),
        "clarification_questions_enabled": _as_bool(
            raw.get("clarification_questions_enabled"),
            bool(defaults["clarification_questions_enabled"]),
        ),
        "model": _model_override,
        "instruction_fragment": _instruction_fragment,
        "context_density": _context_density,
        "analysis_profile": _analysis_profile,
        "variant_configs": _variant_configs,
        "parallel_runs": _parallel_runs,
        "lane_id": _lane_id,
        "variant_id": _variant_id,
        "prior_job_id": str(raw.get("prior_job_id") or "").strip(),
        "overlap_baseline_job_id": str(raw.get("overlap_baseline_job_id") or "").strip(),
        "cross_dll_prior_job_ids": [
            str(x).strip() for x in (raw.get("cross_dll_prior_job_ids") or [])
            if str(x).strip()
        ],
        "chain_step_target": str(raw.get("chain_step_target") or "").strip(),
        "required_semantic_checkpoint": str(raw.get("required_semantic_checkpoint") or "").strip(),
        "selected_invocable_names": [
            str(x).strip() for x in (raw.get("selected_invocable_names") or [])
            if str(x).strip()
        ],
        "graph_epoch": str(raw.get("graph_epoch") or "").strip(),
        "checkpoint_id": str(raw.get("checkpoint_id") or "").strip(),
        "checkpoint_stage": str(raw.get("checkpoint_stage") or "").strip(),
        "cluster_checkpoint_id": str(raw.get("cluster_checkpoint_id") or "").strip(),
        "adjacent_cluster_id": str(raw.get("adjacent_cluster_id") or "").strip(),
        "cluster_confidence_floor": _as_float(raw.get("cluster_confidence_floor"), 0.5, 0.0, 1.0),
        "focus_functions": list(raw.get("focus_functions") or []),
        "skip_to_stage": str(raw.get("skip_to_stage") or "").strip(),
        "iteration_mode": _iteration_mode,
        "iteration_index": _as_int(raw.get("iteration_index"), 1, 1, 32),
        "floor_scope": _floor_scope,
        "ceiling_functions": list(raw.get("ceiling_functions") or []),
        "ceiling_origin_functions": list(raw.get("ceiling_origin_functions") or []),
        "prerequisite_state_group_ids": list(raw.get("prerequisite_state_group_ids") or []),
        "max_iteration_cycles": _as_int(raw.get("max_iteration_cycles"), 1, 1, 8),
        "seed_strategy": str(raw.get("seed_strategy") or "").strip(),
        "seed_default_applied": _as_bool(raw.get("seed_default_applied"), False),
        "seed_default_reason": str(raw.get("seed_default_reason") or "").strip(),
    }


# ── Campaign body helpers ──────────────────────────────────────────────────

def _normalize_campaign_per_dll_explore_settings(body: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    payload = body or {}
    raw = payload.get("per_dll_explore_settings") or {}
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        identity = str(key or "").strip()
        if not identity or not isinstance(value, dict):
            continue
        normalized[identity] = _normalize_explore_runtime_settings({"explore_settings": value})
    return normalized


def _normalize_campaign_active_dll_targets(body: dict[str, Any] | None) -> list[str]:
    payload = body or {}
    raw = payload.get("active_dll_targets") or []
    if not isinstance(raw, list):
        return []
    normalized: list[str] = []
    for value in raw:
        text = str(value or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _extract_campaign_floor_plan(body: dict[str, Any] | None) -> dict[str, Any]:
    payload = body or {}
    raw = (
        payload.get("package_frontier_plan")
        or payload.get("floor_to_ceiling_plan")
        or {}
    )
    return dict(raw) if isinstance(raw, dict) else {}


def _extract_campaign_decomposition_plan(body: dict[str, Any] | None) -> dict[str, Any]:
    payload = body or {}
    raw = payload.get("decomposition_campaign_plan") or payload.get("decomposition_plan") or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _apply_default_repeat_seed(runtime_settings: dict[str, Any]) -> dict[str, Any]:
    runtime = dict(runtime_settings or {})
    prior_job_id = str(runtime.get("prior_job_id") or "").strip()
    checkpoint_id = str(runtime.get("checkpoint_id") or "").strip()
    cluster_checkpoint_id = str(runtime.get("cluster_checkpoint_id") or "").strip()
    seed_strategy = str(runtime.get("seed_strategy") or "").strip()

    if checkpoint_id and cluster_checkpoint_id:
        runtime["seed_strategy"] = seed_strategy or "explicit_cluster_seed"
        return runtime
    if checkpoint_id:
        runtime["seed_strategy"] = seed_strategy or "explicit_checkpoint_seed"
        return runtime
    if not prior_job_id:
        runtime["seed_strategy"] = seed_strategy or "cold_start"
        return runtime

    inferred_cluster_id = infer_cluster_checkpoint_id(runtime.get("focus_functions"))
    if not inferred_cluster_id:
        runtime["seed_strategy"] = seed_strategy or "prior_findings_only"
        return runtime

    runtime["checkpoint_id"] = prior_job_id
    runtime["checkpoint_stage"] = str(runtime.get("checkpoint_stage") or "").strip() or "s02_probe"
    runtime["cluster_checkpoint_id"] = inferred_cluster_id
    runtime["seed_strategy"] = "default_cluster_seed"
    runtime["seed_default_applied"] = True
    runtime["seed_default_reason"] = "prior_job_focus_cluster_inference"
    return runtime


def _normalize_ablation_tags(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}

    def _as_optional_int(value: Any) -> int | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            return int(value)
        except Exception:
            return None

    return {
        "prompt_profile_id": (payload.get("prompt_profile_id") or None),
        "layer": _as_optional_int(payload.get("layer")),
        "ablation_variable": (payload.get("ablation_variable") or None),
        "ablation_value": (payload.get("ablation_value") or None),
        "run_set_id": (payload.get("run_set_id") or None),
        "coordinator_cycle": _as_optional_int(payload.get("coordinator_cycle")),
        "playbook_step": (payload.get("playbook_step") or None),
    }
