"""api.pipeline.s02_probe.curriculum -- Phase 2: curriculum ordering.

Evidence-aware ordering: builds a prerequisite DAG from function signatures,
then orders into execution layers (init → producers → consumers → dependents).
Falls back to call-graph topology or uncertainty sort when DAG provides no
additional structure.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict, deque

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import _upload_to_blob
from api.pipeline.core.evidence_candidates import (
    build_prerequisite_dag,
    dag_to_execution_layers,
)
from api.pipeline.core.helpers import _INIT_RE
from api.pipeline.core.pass_scope import describe_pass_scope_bucket
from api.pipeline.core.vocab import _uncertainty_score

logger = logging.getLogger("mcp_factory.api")


def _dedupe_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        clean = str(name or "").strip()
        if clean and clean not in seen:
            ordered.append(clean)
            seen.add(clean)
    return ordered


def _selected_scope_names(ctx) -> list[str]:
    runtime = getattr(ctx, "runtime", None)
    selected = getattr(runtime, "selected_invocable_names", None) if runtime is not None else None
    if not selected:
        return []
    if isinstance(selected, (list, tuple, set)):
        return _dedupe_names([str(name) for name in selected])
    return _dedupe_names([str(selected)])


def _unlock_sequence_names(ctx) -> list[str]:
    unlock_result = getattr(ctx, "unlock_result", {}) or {}
    if not isinstance(unlock_result, dict) or not unlock_result.get("unlocked"):
        return []
    sequence = unlock_result.get("sequence") or []
    names: list[str] = []
    for step in sequence:
        if isinstance(step, str):
            names.append(step)
            continue
        if not isinstance(step, dict):
            continue
        for key in ("function", "tool", "name", "invocable", "target"):
            value = step.get(key)
            if value:
                names.append(str(value))
                break
    return _dedupe_names(names)


def _promote_named_invocables(ordered: list[dict], names: list[str]) -> tuple[list[dict], list[str]]:
    if not names:
        return ordered, []
    rank = {name: idx for idx, name in enumerate(names)}
    matched = [str(inv.get("name") or "") for inv in ordered if str(inv.get("name") or "") in rank]
    if not matched:
        return ordered, []
    original_index = {id(inv): idx for idx, inv in enumerate(ordered)}
    promoted = sorted(
        ordered,
        key=lambda inv: (
            0 if str(inv.get("name") or "") in rank else 1,
            rank.get(str(inv.get("name") or ""), original_index[id(inv)]),
            original_index[id(inv)],
        ),
    )
    return promoted, _dedupe_names(matched)


def _topological_sort(names: list[str], graph: dict[str, list[str]]) -> list[str]:
    """Kahn's algorithm: return names in dependency order (callees before callers).

    If a function calls another, the callee should be probed first so that
    its working_call is available as live context.  Cycles are broken by
    falling back to the original order for cycle participants.
    """
    name_set = set(names)
    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {n: 0 for n in names}
    for caller, callees in graph.items():
        if caller not in name_set:
            continue
        for callee in callees:
            if callee in name_set and callee != caller:
                adj[callee].append(caller)
                in_degree[caller] = in_degree.get(caller, 0) + 1

    queue: deque[str] = deque(n for n in names if in_degree.get(n, 0) == 0)
    ordered: list[str] = []
    while queue:
        node = queue.popleft()
        ordered.append(node)
        for dependent in adj.get(node, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    remaining = [n for n in names if n not in set(ordered)]
    return ordered + remaining


def _run_phase_2_curriculum_order(ctx) -> None:
    """Reorder invocables using evidence-aware DAG layers, then call graph, then uncertainty.

    Priority layers (first probed -> last probed):
    1. Init/version functions — always first
    2. Producers (read-style, zero-input) — second, they generate tier 2 evidence
    3. Consumers (write-style) — third, after producers have populated the registry
    4. Dependents/unknown — last

    Within each layer, topological sort from call_graph applies, then uncertainty.

    READS:  ctx.invocables, ctx.call_graph, ctx.vocab
    WRITES: ctx.invocables (reordered), ctx.init_invocables, ctx._execution_layers
    """
    id_formats = [str(x) for x in (getattr(ctx, "vocab", {}).get("id_formats") or []) if x]

    roles, edges = build_prerequisite_dag(ctx.invocables, id_formats)
    layers = dag_to_execution_layers(roles, edges)

    role_map = {r.name: r for r in roles}
    name_to_inv = {inv["name"]: inv for inv in ctx.invocables}
    sequence_roles = {
        r.name: {
            "role": r.role,
            "sequence_role": r.sequence_role,
            "sequence_confidence": r.sequence_confidence,
            "sequence_reasons": list(r.sequence_reasons),
        }
        for r in roles
    }
    prerequisite_map = {r.name: list(r.prerequisites) for r in roles if r.prerequisites}
    edge_map: dict[str, list[dict]] = defaultdict(list)
    for edge in edges:
        edge_map[edge.consumer].append({
            "producer": edge.producer,
            "shared_kind": edge.shared_kind,
            "confidence": edge.confidence,
        })

    ordered: list[dict] = []
    seen: set[str] = set()

    call_graph = getattr(ctx, "call_graph", {}) or {}

    for layer in layers:
        layer_invs = [name_to_inv[n] for n in layer if n in name_to_inv and n not in seen]
        for inv in layer_invs:
            fn_name = str(inv.get("name") or "")
            prereqs = prerequisite_map.get(fn_name) or []
            role_info = sequence_roles.get(fn_name) or {}
            if prereqs:
                inv["_required_preconditions"] = prereqs
            if role_info:
                inv["_sequence_role"] = role_info.get("sequence_role") or "unknown"
        if call_graph:
            layer_names = [inv["name"] for inv in layer_invs]
            sorted_names = _topological_sort(layer_names, call_graph)
            inv_lookup = {inv["name"]: inv for inv in layer_invs}
            layer_invs = [inv_lookup[n] for n in sorted_names if n in inv_lookup]
        else:
            layer_invs.sort(key=_uncertainty_score)
        if getattr(ctx.runtime, "pass_scope_profile", "foundation") == "foundation":
            scored_layer = []
            for idx, inv in enumerate(layer_invs):
                bucket, reason = describe_pass_scope_bucket(
                    inv,
                    pass_index=int(getattr(ctx.runtime, "pass_index", 1) or 1),
                    pass_scope_profile=str(getattr(ctx.runtime, "pass_scope_profile", "foundation") or "foundation"),
                )
                inv["_pass_scope_bucket"] = bucket
                inv["_pass_scope_reason"] = reason
                scored_layer.append((bucket, idx, inv))
            scored_layer.sort(key=lambda item: (item[0], item[1]))
            layer_invs = [item[2] for item in scored_layer]
        for inv in layer_invs:
            if inv["name"] not in seen:
                ordered.append(inv)
                seen.add(inv["name"])

    for inv in ctx.invocables:
        if inv["name"] not in seen:
            ordered.append(inv)
            seen.add(inv["name"])

    unlock_sequence_names = _unlock_sequence_names(ctx)
    ordered, unlock_matched_names = _promote_named_invocables(ordered, unlock_sequence_names)
    if unlock_sequence_names:
        ctx.unlock_ordering_handoff = {
            "source": "unlock_result.sequence",
            "sequence_names": list(unlock_sequence_names),
            "matched_names": list(unlock_matched_names),
            "unmatched_names": [name for name in unlock_sequence_names if name not in set(unlock_matched_names)],
            "claim_boundary": "ordering_guidance_only",
        }

    selected_scope_names = _selected_scope_names(ctx)
    ordered, selected_matched_names = _promote_named_invocables(ordered, selected_scope_names)
    if selected_scope_names:
        ctx.pass_scope_containment = {
            "source": "runtime.selected_invocable_names",
            "selected_names": list(selected_scope_names),
            "matched_names": list(selected_matched_names),
            "unmatched_names": [name for name in selected_scope_names if name not in set(selected_matched_names)],
            "claim_boundary": "scope_ordering_only",
        }

    for inv in ordered:
        fn_name = str(inv.get("name") or "")
        if not fn_name:
            continue
        role_info = sequence_roles.get(fn_name) or {}
        prereqs = prerequisite_map.get(fn_name) or []
        if prereqs:
            inv["_required_preconditions"] = prereqs
        if role_info:
            inv["_sequence_role"] = role_info.get("sequence_role") or "unknown"
            inv["_sequence_confidence"] = float(role_info.get("sequence_confidence") or 0.0)
            inv["_sequence_reasons"] = list(role_info.get("sequence_reasons") or [])
        if edge_map.get(fn_name):
            inv["_prerequisite_edges"] = list(edge_map.get(fn_name) or [])
        if "_pass_scope_bucket" not in inv:
            bucket, reason = describe_pass_scope_bucket(
                inv,
                pass_index=int(getattr(ctx.runtime, "pass_index", 1) or 1),
                pass_scope_profile=str(getattr(ctx.runtime, "pass_scope_profile", "foundation") or "foundation"),
            )
            inv["_pass_scope_bucket"] = bucket
            inv["_pass_scope_reason"] = reason

    ctx.invocables = ordered
    ctx.init_invocables = [inv for inv in ordered if _INIT_RE.search(inv["name"])]
    ctx.execution_layers = layers
    ctx.prerequisite_map = prerequisite_map
    ctx.sequence_roles = sequence_roles

    try:
        ctx._execution_layers = layers  # type: ignore[attr-defined]
    except Exception:
        pass

    logger.info(
        "[%s] phase2: evidence-aware ordering — %d layers, %d edges, %d init, %d total",
        ctx.job_id, len(layers), len(edges), len(ctx.init_invocables), len(ordered),
    )
    for i, layer in enumerate(layers):
        layer_roles = [role_map.get(n, None) for n in layer]
        layer_role_names = [
            f"{r.role}/{r.sequence_role}" if r and r.sequence_role != "unknown" else (r.role if r else "?")
            for r in layer_roles
        ]
        logger.info("[%s] phase2: layer %d: %s (%s)",
                    ctx.job_id, i, layer, layer_role_names)

    try:
        payload = {
            "roles": [
                {
                    "name": r.name,
                    "role": r.role,
                    "sequence_role": r.sequence_role,
                    "sequence_confidence": r.sequence_confidence,
                    "prerequisites": list(r.prerequisites),
                    "sequence_reasons": list(r.sequence_reasons),
                    "input_kinds": list(r.input_kinds),
                    "output_kinds": list(r.output_kinds),
                }
                for r in roles
            ],
            "edges": [
                {
                    "producer": edge.producer,
                    "consumer": edge.consumer,
                    "shared_kind": edge.shared_kind,
                    "confidence": edge.confidence,
                }
                for edge in edges
            ],
            "layers": layers,
            "pass_index": int(getattr(ctx.runtime, "pass_index", 1) or 1),
            "pass_scope_profile": str(getattr(ctx.runtime, "pass_scope_profile", "foundation") or "foundation"),
            "unlock_ordering_handoff": getattr(ctx, "unlock_ordering_handoff", None),
            "pass_scope_containment": getattr(ctx, "pass_scope_containment", None),
        }
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{ctx.job_id}/prerequisite_state_machine.json",
            json.dumps(payload, indent=2).encode("utf-8"),
        )
    except Exception as exc:
        logger.debug("[%s] phase2: prerequisite_state_machine artifact write failed: %s",
                     ctx.job_id, exc)
