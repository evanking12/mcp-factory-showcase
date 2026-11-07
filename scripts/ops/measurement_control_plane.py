from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTROL_PLANE_SCHEMA_VERSION = "1.0.0"
DEFAULT_DEPENDENCY_POLICY = "stop_dependent_chain_on_non_comparable_target"
HARD01_BASELINE_READINESS_SCHEMA_VERSION = "1.0.0"
HARD01_BASELINE_READY_VERDICT = "ready_for_bounded_hard01_baseline_attempt"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)]


def split_configured_bridge_urls(
    raw_urls: str | Sequence[str] | None = None,
    *,
    default_bridge_url: str = "",
) -> list[str]:
    """Normalize configured bridge URLs while preserving operator order."""

    values: list[str] = []
    if isinstance(raw_urls, str):
        values.extend(re.split(r"[,\s;]+", raw_urls))
    else:
        values.extend(str(item or "") for item in (raw_urls or []))
    if default_bridge_url:
        values.append(default_bridge_url)
    urls: list[str] = []
    for item in values:
        url = str(item or "").strip().rstrip("/")
        if url and url not in urls:
            urls.append(url)
    return urls


def selected_bridge_url_from_registry(packet: Mapping[str, Any]) -> str:
    selected = packet.get("selected_bridge")
    return str((selected or {}).get("url") or "").strip() if isinstance(selected, Mapping) else ""


def _normalize_bridge_url(value: Any) -> str:
    return str(value or "").strip().rstrip("/")


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _bridge_quarantine_rows(raw_registry: Any) -> list[dict[str, Any]]:
    if not raw_registry:
        return []
    parsed = raw_registry
    if isinstance(raw_registry, str):
        try:
            parsed = json.loads(raw_registry)
        except json.JSONDecodeError:
            return [
                {
                    "bridge_url": _normalize_bridge_url(raw_registry),
                    "state": "active",
                    "reason_code": "configured_bridge_quarantine",
                }
            ]
    if isinstance(parsed, Mapping):
        if isinstance(parsed.get("entries"), Sequence) and not isinstance(parsed.get("entries"), str):
            values = parsed.get("entries") or []
        else:
            values = []
            for bridge_url, row in parsed.items():
                if isinstance(row, Mapping):
                    item = dict(row)
                    item.setdefault("bridge_url", bridge_url)
                    values.append(item)
                elif row:
                    values.append(
                        {
                            "bridge_url": bridge_url,
                            "state": "active",
                            "reason_code": "configured_bridge_quarantine",
                        }
                    )
    elif isinstance(parsed, Sequence) and not isinstance(parsed, str):
        values = parsed
    else:
        values = []

    rows: list[dict[str, Any]] = []
    for raw_row in values:
        if not isinstance(raw_row, Mapping):
            continue
        row = dict(raw_row)
        row["bridge_url"] = _normalize_bridge_url(row.get("bridge_url") or row.get("url"))
        row["target"] = str(row.get("target") or "").strip()
        row["analysis_profile"] = str(row.get("analysis_profile") or "").strip()
        row["state"] = str(row.get("state") or "active").strip().lower()
        row["reason_code"] = str(row.get("reason_code") or "configured_bridge_quarantine").strip()
        row["evidence_paths"] = _as_list(row.get("evidence_paths"))
        row["next_action"] = str(row.get("next_action") or "inspect or clear the quarantined bridge lane").strip()
        if row["bridge_url"]:
            rows.append(row)
    return rows


def _matching_bridge_quarantine(
    *,
    quarantine_registry: Any,
    bridge_url: str,
    target: str,
    analysis_profile: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    url = _normalize_bridge_url(bridge_url)
    target_name = str(target or "").strip()
    profile = str(analysis_profile or "").strip()
    visible_rows: list[dict[str, Any]] = []
    for row in _bridge_quarantine_rows(quarantine_registry):
        if _normalize_bridge_url(row.get("bridge_url")) != url:
            continue
        row_target = str(row.get("target") or "").strip()
        row_profile = str(row.get("analysis_profile") or "").strip()
        if row_target and row_target != target_name:
            continue
        if row_profile and row_profile != profile:
            continue

        state = str(row.get("state") or "active").strip().lower()
        expires_at = _parse_iso_datetime(row.get("expires_at"))
        effective_state = state
        active = state == "active"
        if active and expires_at is not None and expires_at <= now:
            active = False
            effective_state = "expired"
        if state in {"cleared", "expired"}:
            active = False
            effective_state = state
        visible = dict(row)
        visible["effective_state"] = effective_state
        visible["active"] = active
        visible_rows.append(visible)

    active_rows = [row for row in visible_rows if bool(row.get("active"))]
    selected = active_rows[0] if active_rows else (visible_rows[0] if visible_rows else {})
    return {
        "active": bool(active_rows),
        "matched": bool(visible_rows),
        "selected": selected,
        "rows": visible_rows,
    }


def _capabilities(*payloads: Mapping[str, Any]) -> set[str]:
    found: set[str] = set()
    for payload in payloads:
        for item in _as_list(payload.get("capabilities")):
            found.add(item)
    return found


def build_measurement_control_plane_packet(
    *,
    target: str,
    analysis_profile: str,
    required_capabilities: Sequence[str] | None = None,
    runner_identity: Mapping[str, Any] | None = None,
    api_identity: Mapping[str, Any] | None = None,
    bridge_identity: Mapping[str, Any] | None = None,
    api_readiness: Mapping[str, Any] | None = None,
    bridge_readiness: Mapping[str, Any] | None = None,
    bridge_stream_health: Mapping[str, Any] | None = None,
    lane_readiness: Mapping[str, Any] | None = None,
    bridge_url: str = "",
    no_green_bridge_available: bool = False,
    bridge_quarantined: bool = False,
    quarantine_reason: str = "",
    quarantine_record: Mapping[str, Any] | None = None,
    diagnostic_allowed: bool = True,
    evidence_paths: Sequence[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a traffic-light admission packet without mutating runner state.

    This helper classifies whether a target may use a lane/bridge.
    It does not run the target and never satisfies semantic proof by itself.
    """

    runner = _as_dict(runner_identity)
    api = _as_dict(api_identity)
    bridge = _as_dict(bridge_identity)
    api_ready = _as_dict(api_readiness)
    bridge_ready = _as_dict(bridge_readiness)
    bridge_health = _as_dict(bridge_stream_health)
    lane_ready = _as_dict(lane_readiness)
    required = list(required_capabilities or ("analyze",))
    available_caps = _capabilities(bridge, bridge_ready)
    missing_caps = [cap for cap in required if cap not in available_caps]
    lane_comparable = lane_ready.get("lane_comparable")
    lane_ready_flag = lane_ready.get("ready")
    bridge_health_status = str(bridge_health.get("status") or bridge_health.get("state") or "").strip().lower()
    bridge_health_reason = str(bridge_health.get("reason_code") or "").strip()
    bridge_health_known = bridge_health.get("stream_health_known")
    bridge_health_signals = _as_list(bridge_health.get("recent_signals") or bridge_health.get("known_signals"))
    bridge_health_historical = bridge_health_status == "historical_signal_only" or (
        bridge_health_reason == "bridge_stream_health_historical_context"
    )
    quarantine = _as_dict(quarantine_record)
    blocking_reasons: list[str] = []

    if bridge_quarantined:
        light = "quarantined"
        reason_code = "bridge_lane_quarantined"
        blocking_reasons.append(quarantine_reason or "bridge_lane_quarantined")
        safe_to_run = False
        safe_to_compare = False
        next_action = (
            str(quarantine.get("next_action") or "").strip()
            or "inspect or clear the quarantined bridge lane before scheduling hard-family targets"
        )
    elif no_green_bridge_available:
        light = "red"
        reason_code = "no_green_bridge_available"
        blocking_reasons.append("no_green_bridge_available")
        safe_to_run = False
        safe_to_compare = False
        next_action = "select a green bridge lane or emit non-comparable baseline data without scheduling analyze"
    elif not bridge_ready:
        light = "red"
        reason_code = "bridge_readiness_unavailable"
        blocking_reasons.append("bridge_readiness_unavailable")
        safe_to_run = False
        safe_to_compare = False
        next_action = "collect bridge readiness before scheduling analyzer work"
    elif not bool(bridge_ready.get("ready")):
        light = "red"
        reason_code = "bridge_readiness_unavailable"
        blocking_reasons.extend(_as_list(bridge_ready.get("blocking_reasons")) or ["bridge_not_ready"])
        safe_to_run = False
        safe_to_compare = False
        next_action = "repair bridge readiness before scheduling analyzer work"
    elif missing_caps:
        light = "red"
        reason_code = "bridge_capability_mismatch"
        blocking_reasons.extend([f"missing_capability:{cap}" for cap in missing_caps])
        safe_to_run = False
        safe_to_compare = False
        next_action = "route to a bridge with the required analyzer capabilities"
    elif lane_ready and (lane_ready_flag is False or lane_comparable is False):
        lane_reasons = _as_list(lane_ready.get("blocking_reasons")) or ["lane_identity_not_comparable"]
        if diagnostic_allowed:
            light = "yellow"
            reason_code = "diagnostic_only_lane"
            blocking_reasons.extend(lane_reasons)
            safe_to_run = True
            safe_to_compare = False
            next_action = "run only for non-comparable diagnostics or repair lane identity before semantic comparison"
        else:
            light = "red"
            reason_code = "lane_identity_not_comparable"
            blocking_reasons.extend(lane_reasons)
            safe_to_run = False
            safe_to_compare = False
            next_action = "repair lane identity comparability before scheduling this target"
    elif bridge_health and not bridge_health_historical and (
        bridge_health_reason in {"bridge_recent_no_heartbeat_stall", "bridge_stream_no_heartbeat"}
        or "bridge_stream_no_heartbeat" in bridge_health_signals
        or bridge_health_status in {"stalled", "recent_stall"}
    ):
        light = "yellow"
        reason_code = "bridge_recent_no_heartbeat_stall"
        blocking_reasons.extend(bridge_health_signals or [bridge_health_reason or "bridge_recent_no_heartbeat_stall"])
        safe_to_run = True
        safe_to_compare = False
        next_action = "run only for diagnostics until bridge stream health is repaired or explicitly cleared"
    elif bridge_health and not bridge_health_historical and (
        bridge_health_reason == "bridge_stream_health_degraded"
        or bridge_health_status == "degraded"
    ):
        light = "yellow"
        reason_code = "bridge_stream_health_degraded"
        blocking_reasons.append(bridge_health_reason or "bridge_stream_health_degraded")
        safe_to_run = True
        safe_to_compare = False
        next_action = "run only for diagnostics until bridge stream health is coherent"
    elif bridge_health and not bridge_health_historical and bridge_health_status == "terminalization_blocked":
        light = "yellow"
        reason_code = bridge_health_reason or "current_run_terminalization_blocked"
        blocking_reasons.append(reason_code)
        safe_to_run = True
        safe_to_compare = False
        next_action = (
            str(bridge_health.get("next_action") or "").strip()
            or "repair current-run terminalization before semantic comparison"
        )
    elif bridge_health and not bridge_health_historical and (
        bridge_health_known is False
        or bridge_health_reason == "bridge_stream_health_unproven"
        or bridge_health_status in {"", "unknown", "unproven"}
    ):
        light = "yellow"
        reason_code = "bridge_stream_health_unproven"
        blocking_reasons.append("bridge_stream_health_unproven")
        safe_to_run = True
        safe_to_compare = False
        next_action = "run only for diagnostics until bridge stream health has a coherent passive proof"
    else:
        light = "green"
        reason_code = "green_lane_admitted"
        safe_to_run = True
        safe_to_compare = True
        next_action = "schedule target; control-plane admission is green"

    status = {
        "green": "admitted",
        "yellow": "diagnostic_only",
        "red": "blocked",
        "quarantined": "quarantined",
    }[light]
    selected_bridge = {
        "url": str(bridge_url or ""),
        "component": str(bridge.get("component") or bridge_ready.get("component") or "bridge"),
        "git_sha": str(bridge.get("git_sha") or bridge.get("git", {}).get("sha") or ""),
        "capabilities": sorted(available_caps),
    }
    lease = {
        "mode": "single_bridge_v1",
        "lease_id": f"single-bridge:{target}:{analysis_profile}",
        "exclusive": False,
        "granted": bool(light in {"green", "yellow"}),
    }
    return {
        "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "source": "measurement_control_plane",
        "target": str(target or ""),
        "analysis_profile": str(analysis_profile or ""),
        "required_capabilities": required,
        "light": light,
        "status": status,
        "reason_code": reason_code,
        "blocking_reasons": blocking_reasons,
        "safe_to_run": safe_to_run,
        "safe_to_compare": safe_to_compare,
        "semantic_proof_satisfied": False,
        "selected_bridge": selected_bridge,
        "lease": lease,
        "quarantine": quarantine,
        "dependency_policy": DEFAULT_DEPENDENCY_POLICY,
        "evidence_paths": list(evidence_paths or ["measurement-control-plane.json"]),
        "next_action": next_action,
        "created_at": created_at or _utc_iso(),
        "inputs": {
            "runner_identity": runner,
            "api_identity": api,
            "bridge_identity": bridge,
            "api_readiness": api_ready,
            "bridge_readiness": bridge_ready,
            "bridge_stream_health": bridge_health,
            "lane_readiness": lane_ready,
        },
    }


def _bridge_candidate_id(candidate: Mapping[str, Any], index: int) -> str:
    return str(candidate.get("candidate_id") or candidate.get("id") or candidate.get("url") or f"bridge-{index}").strip()


def _bridge_candidate_identity(candidate: Mapping[str, Any]) -> dict[str, Any]:
    identity = candidate.get("identity")
    if isinstance(identity, Mapping):
        return dict(identity)
    return {
        "component": "bridge",
        "git_sha": str(candidate.get("git_sha") or ""),
        "capabilities": _as_list(candidate.get("capabilities")),
    }


def _bridge_candidate_readiness(candidate: Mapping[str, Any]) -> dict[str, Any]:
    readiness = candidate.get("readiness")
    if isinstance(readiness, Mapping):
        return dict(readiness)
    if "ready" in candidate or "capabilities" in candidate:
        return {
            "component": "bridge",
            "ready": bool(candidate.get("ready")),
            "capabilities": _as_list(candidate.get("capabilities")),
            "blocking_reasons": _as_list(candidate.get("blocking_reasons")),
        }
    return {}


def _bridge_candidate_health(candidate: Mapping[str, Any]) -> dict[str, Any]:
    health = candidate.get("bridge_stream_health") or candidate.get("stream_health") or candidate.get("health")
    return dict(health) if isinstance(health, Mapping) else {}


def build_bridge_candidates_from_config(
    *,
    bridge_urls: Sequence[str] | None = None,
    default_bridge_url: str = "",
    target: str = "",
    analysis_profile: str = "",
    bridge_identities: Mapping[str, Mapping[str, Any]] | None = None,
    bridge_readiness: Mapping[str, Mapping[str, Any]] | None = None,
    bridge_lane_readiness: Mapping[str, Mapping[str, Any]] | None = None,
    bridge_stream_health: Mapping[str, Mapping[str, Any]] | None = None,
    quarantined_bridge_urls: Sequence[str] | None = None,
    quarantine_registry: Any = None,
) -> list[dict[str, Any]]:
    """Normalize configured bridge URLs into candidate rows.

    This is discovery, not scheduling. It builds a reviewable candidate list for
    the registry helper without contacting bridges or granting leases.
    """

    urls: list[str] = []
    for raw_url in [*(bridge_urls or []), default_bridge_url]:
        url = str(raw_url or "").strip()
        if url and url not in urls:
            urls.append(url)

    identities = dict(bridge_identities or {})
    readiness = dict(bridge_readiness or {})
    lane_readiness_by_url = dict(bridge_lane_readiness or {})
    health = dict(bridge_stream_health or {})
    quarantined = set(_as_list(quarantined_bridge_urls))
    candidates: list[dict[str, Any]] = []
    for index, url in enumerate(urls, start=1):
        quarantine_match = _matching_bridge_quarantine(
            quarantine_registry=quarantine_registry,
            bridge_url=url,
            target=target,
            analysis_profile=analysis_profile,
        )
        quarantine_selected = dict(quarantine_match.get("selected") or {})
        is_quarantined = url in quarantined or bool(quarantine_match.get("active"))
        candidates.append(
            {
                "id": "configured-local-bridge" if len(urls) == 1 else f"configured-bridge-{index}",
                "url": url,
                "identity": dict(identities.get(url) or {}),
                "readiness": dict(readiness.get(url) or {}),
                "lane_readiness": dict(lane_readiness_by_url.get(url) or {}),
                "stream_health": dict(health.get(url) or {}),
                "quarantined": is_quarantined,
                "quarantine_reason": (
                    str(quarantine_selected.get("reason_code") or "").strip()
                    or ("configured_bridge_quarantine" if url in quarantined else "")
                ),
                "quarantine": {
                    "active": bool(quarantine_match.get("active") or url in quarantined),
                    "matched": bool(quarantine_match.get("matched") or url in quarantined),
                    "selected": quarantine_selected
                    or (
                        {
                            "bridge_url": url,
                            "state": "active",
                            "effective_state": "active",
                            "reason_code": "configured_bridge_quarantine",
                        }
                        if url in quarantined
                        else {}
                    ),
                    "rows": list(quarantine_match.get("rows") or []),
                },
            }
        )
    return candidates


def build_bridge_candidate_registry_packet(
    *,
    target: str,
    analysis_profile: str,
    bridge_candidates: Sequence[Mapping[str, Any]] | None,
    required_capabilities: Sequence[str] | None = None,
    runner_identity: Mapping[str, Any] | None = None,
    api_identity: Mapping[str, Any] | None = None,
    api_readiness: Mapping[str, Any] | None = None,
    lane_readiness: Mapping[str, Any] | None = None,
    diagnostic_allowed: bool = True,
    evidence_paths: Sequence[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Evaluate multiple bridge candidates without scheduling work.

    Tier 3 starts here: candidate selection is explicit and reviewable, but this
    helper remains a pure packet builder. Runner enforcement can consume it in a
    later campaign.
    """

    candidates = list(bridge_candidates or [])
    evaluated: list[dict[str, Any]] = []
    required = list(required_capabilities or ("analyze",))
    for index, raw_candidate in enumerate(candidates):
        candidate = dict(raw_candidate or {})
        candidate_id = _bridge_candidate_id(candidate, index)
        identity = _bridge_candidate_identity(candidate)
        readiness = _bridge_candidate_readiness(candidate)
        packet = build_measurement_control_plane_packet(
            target=target,
            analysis_profile=analysis_profile,
            required_capabilities=required,
            runner_identity=runner_identity,
            api_identity=api_identity,
            bridge_identity=identity,
            api_readiness=api_readiness,
            bridge_readiness=readiness,
            bridge_stream_health=_bridge_candidate_health(candidate),
            lane_readiness=(
                dict(candidate.get("lane_readiness"))
                if isinstance(candidate.get("lane_readiness"), Mapping)
                else lane_readiness
            ),
            bridge_url=str(candidate.get("url") or candidate.get("bridge_url") or ""),
            bridge_quarantined=bool(candidate.get("quarantined")),
            quarantine_reason=str(candidate.get("quarantine_reason") or ""),
            quarantine_record=(
                dict(candidate.get("quarantine"))
                if isinstance(candidate.get("quarantine"), Mapping)
                else {}
            ),
            diagnostic_allowed=diagnostic_allowed,
            evidence_paths=evidence_paths,
            created_at=created_at,
        )
        evaluated.append(
            {
                "candidate_id": candidate_id,
                "url": str(candidate.get("url") or candidate.get("bridge_url") or ""),
                "light": str(packet.get("light") or ""),
                "status": str(packet.get("status") or ""),
                "reason_code": str(packet.get("reason_code") or ""),
                "safe_to_run": bool(packet.get("safe_to_run")),
                "safe_to_compare": bool(packet.get("safe_to_compare")),
                "blocking_reasons": list(packet.get("blocking_reasons") or []),
                "quarantine": dict(packet.get("quarantine") or {}),
                "packet": packet,
            }
        )

    selected = next((item for item in evaluated if item["light"] == "green"), None)
    selection_reason = "selected_first_green"
    if selected is None:
        selected = next((item for item in evaluated if item["light"] == "yellow"), None)
        selection_reason = "selected_first_diagnostic_yellow" if selected else selection_reason
    if selected is None and evaluated:
        selected = evaluated[0]
        if all(item["light"] == "quarantined" for item in evaluated):
            selection_reason = "no_non_quarantined_bridge_available"
        else:
            selection_reason = "no_runnable_candidate"

    if selected is None:
        packet = build_measurement_control_plane_packet(
            target=target,
            analysis_profile=analysis_profile,
            required_capabilities=required,
            runner_identity=runner_identity,
            api_identity=api_identity,
            api_readiness=api_readiness,
            lane_readiness=lane_readiness,
            no_green_bridge_available=True,
            diagnostic_allowed=diagnostic_allowed,
            evidence_paths=evidence_paths,
            created_at=created_at,
        )
        selected_packet = packet
        selection_reason = "no_bridge_candidates"
        selected_candidate_id = ""
    else:
        selected_packet = dict(selected["packet"])
        selected_candidate_id = str(selected["candidate_id"])

    light = str(selected_packet.get("light") or "")
    lease = dict(selected_packet.get("lease") or {})
    lease.update(
        {
            "mode": "bridge_candidate_registry_v1",
            "lease_id": f"candidate-registry:{selected_candidate_id or 'none'}:{target}:{analysis_profile}",
            "selected_candidate_id": selected_candidate_id,
        }
    )
    return {
        "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "source": "measurement_control_plane",
        "registry_schema": "bridge_candidate_registry_v1",
        "target": str(target or ""),
        "analysis_profile": str(analysis_profile or ""),
        "required_capabilities": required,
        "candidate_count": len(evaluated),
        "selection_policy": "first_green_else_first_yellow_else_blocked",
        "selection_reason": selection_reason,
        "selected_candidate_id": selected_candidate_id,
        "selected_bridge": dict(selected_packet.get("selected_bridge") or {}),
        "lease": lease,
        "light": light,
        "status": str(selected_packet.get("status") or ""),
        "reason_code": str(selected_packet.get("reason_code") or ""),
        "blocking_reasons": list(selected_packet.get("blocking_reasons") or []),
        "safe_to_run": bool(selected_packet.get("safe_to_run")),
        "safe_to_compare": bool(selected_packet.get("safe_to_compare")),
        "semantic_proof_satisfied": False,
        "dependency_policy": DEFAULT_DEPENDENCY_POLICY,
        "evidence_paths": list(evidence_paths or ["measurement-control-plane.json"]),
        "next_action": str(selected_packet.get("next_action") or ""),
        "created_at": created_at or _utc_iso(),
        "candidates": evaluated,
    }


def build_single_bridge_candidate_registry_packet(
    *,
    target: str,
    analysis_profile: str,
    bridge_url: str,
    bridge_identity: Mapping[str, Any] | None = None,
    bridge_readiness: Mapping[str, Any] | None = None,
    bridge_stream_health: Mapping[str, Any] | None = None,
    required_capabilities: Sequence[str] | None = None,
    runner_identity: Mapping[str, Any] | None = None,
    api_identity: Mapping[str, Any] | None = None,
    api_readiness: Mapping[str, Any] | None = None,
    lane_readiness: Mapping[str, Any] | None = None,
    diagnostic_allowed: bool = True,
    evidence_paths: Sequence[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a registry packet for the currently configured bridge.

    This is the runner-consumption bridge between single-bridge v1 and true
    multi-bridge selection. It keeps the runtime surface narrow while making
    candidate selection explicit in emitted packets.
    """

    return build_bridge_candidate_registry_packet(
        target=target,
        analysis_profile=analysis_profile,
        required_capabilities=required_capabilities,
        runner_identity=runner_identity,
        api_identity=api_identity,
        api_readiness=api_readiness,
        lane_readiness=lane_readiness,
        diagnostic_allowed=diagnostic_allowed,
        evidence_paths=evidence_paths,
        created_at=created_at,
        bridge_candidates=[
            {
                "id": "configured-local-bridge",
                "url": bridge_url,
                "identity": dict(bridge_identity or {}),
                "readiness": dict(bridge_readiness or {}),
                "stream_health": dict(bridge_stream_health or {}),
            }
        ],
    )


def hard_family_bridge_stream_health_for_target(target_name: str, analysis_profile: str) -> dict[str, Any]:
    target_key = str(target_name or "").strip()
    profile = str(analysis_profile or "").strip()
    if target_key == "session_bootstrap" and profile == "strict_dll":
        return {
            "source": "hard_family_measurement_control_plane",
            "status": "coherent",
            "reason_code": "bridge_stream_health_coherent",
            "stream_health_known": True,
            "recent_signals": [],
            "next_action": "allow green control-plane admission if lane and bridge readiness remain compatible",
        }
    if target_key == "reservation_stage" and profile == "strict_dll":
        return {
            "source": "hard_family_failure_signal_map",
            "status": "historical_signal_only",
            "reason_code": "bridge_stream_health_historical_context",
            "stream_health_known": False,
            "historical_signals": [
                "control_plane_green_but_bridge_stalled",
                "bridge_stream_no_heartbeat",
            ],
            "recent_signals": [],
            "current_run_authority": False,
            "next_action": "derive bridge stream health from current-run analyzer authority before semantic comparison",
        }
    return {
        "source": "hard_family_measurement_control_plane",
        "status": "unproven",
        "reason_code": "bridge_stream_health_unproven",
        "stream_health_known": False,
        "recent_signals": [],
        "next_action": "collect passive bridge stream health before semantic comparability",
    }


def bridge_stream_health_from_run_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Derive bridge stream health from the current run, not historical target memory."""

    rec = dict(record or {})
    terminalization = rec.get("job_terminalization")
    terminalization = dict(terminalization) if isinstance(terminalization, Mapping) else {}
    authority = rec.get("run_authority")
    authority = dict(authority) if isinstance(authority, Mapping) else {}
    analyzer_authority = rec.get("analyzer_authority")
    analyzer_authority = dict(analyzer_authority) if isinstance(analyzer_authority, Mapping) else {}
    bridge_authority = analyzer_authority.get("bridge_analyzer_authority")
    bridge_authority = dict(bridge_authority) if isinstance(bridge_authority, Mapping) else {}
    if not bridge_authority:
        status_snapshot = rec.get("job_status_snapshot")
        status_snapshot = dict(status_snapshot) if isinstance(status_snapshot, Mapping) else {}
        embedded = status_snapshot.get("bridge_analyzer_authority")
        bridge_authority = dict(embedded) if isinstance(embedded, Mapping) else {}

    bridge_reason = str(
        bridge_authority.get("reason_code")
        or analyzer_authority.get("bridge_reason_code")
        or rec.get("failure_domain")
        or ""
    ).strip()
    bridge_blockers = _as_list(bridge_authority.get("blocking_reasons")) or _as_list(
        analyzer_authority.get("blocking_reasons")
    )
    if bridge_reason in {"bridge_stream_no_heartbeat", "bridge_recent_no_heartbeat_stall"}:
        return {
            "source": "current_run_bridge_analyzer_authority",
            "status": "recent_stall",
            "reason_code": "bridge_recent_no_heartbeat_stall",
            "stream_health_known": True,
            "recent_signals": bridge_blockers or [bridge_reason],
            "current_run_authority": True,
            "next_action": "repair current bridge stream heartbeat/result emission before semantic comparison",
        }

    terminal_done = bool(terminalization.get("terminal")) or str(rec.get("phase") or "").strip().lower() == "done"
    terminal_kind = str(terminalization.get("terminalization_kind") or terminalization.get("kind") or "").strip()
    if terminal_done and terminal_kind in {"", "done"}:
        decision_bearing = (
            bool(rec.get("authoritative_proving"))
            or bool(authority.get("authoritative_proving"))
            or str(authority.get("authority_level") or "").strip() == "decision_bearing"
        )
        return {
            "source": "current_run_authority",
            "status": "coherent",
            "reason_code": "bridge_stream_health_coherent",
            "stream_health_known": True,
            "recent_signals": [],
            "current_run_authority": True,
            "current_run_decision_bearing": decision_bearing,
            "next_action": "allow product authority to classify terminal current-run evidence",
        }
    if terminalization and terminal_kind not in {"", "done"}:
        reason = terminalization.get("reason")
        reason = dict(reason) if isinstance(reason, Mapping) else {}
        reason_code = str(
            terminalization.get("reason_code")
            or reason.get("code")
            or terminal_kind
            or "current_run_terminalization_blocked"
        ).strip()
        return {
            "source": "current_run_terminalization",
            "status": "terminalization_blocked",
            "reason_code": reason_code,
            "stream_health_known": False,
            "recent_signals": [reason_code],
            "current_run_authority": True,
            "terminalization_kind": terminal_kind,
            "next_action": "repair current-run terminalization before semantic comparison",
        }

    return {
        "source": "current_run_authority",
        "status": "unproven",
        "reason_code": "bridge_stream_health_unproven",
        "stream_health_known": False,
        "recent_signals": [],
        "current_run_authority": False,
        "next_action": "collect current-run bridge analyzer authority before semantic comparison",
    }


def control_plane_allows_run(packet: Mapping[str, Any]) -> bool:
    return str(packet.get("light") or "").strip().lower() in {"green", "yellow"} and bool(
        packet.get("safe_to_run")
    )


def control_plane_allows_comparable_result(packet: Mapping[str, Any]) -> bool:
    return str(packet.get("light") or "").strip().lower() == "green" and bool(packet.get("safe_to_compare"))


def _failure_domain_for_reason(reason_code: str) -> str:
    reason = str(reason_code or "").strip()
    if reason.startswith("bridge_") or reason in {"no_green_bridge_available"}:
        return "bridge"
    if reason.startswith("lane_"):
        return "runner"
    if reason.startswith("runner_observed_") or reason.startswith("s07_"):
        return "pipeline"
    return "unknown"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_control_plane_terminalization_packet(
    *,
    control_plane: Mapping[str, Any],
    run_id: str,
    job_id: str = "",
    status: str = "non_comparable",
    phase: str = "control_plane_admission",
) -> dict[str, Any]:
    reason_code = str(control_plane.get("reason_code") or "unknown_control_plane_block").strip()
    return {
        "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "target": str(control_plane.get("target") or ""),
        "case_id": str(control_plane.get("target") or ""),
        "phase": phase,
        "status": status,
        "reason_code": reason_code,
        "owner": "measurement_control_plane",
        "safe_to_compare": False,
        "evidence_paths": [
            "measurement-control-plane.json",
            "measurement-terminalization.json",
            "run-authority.json",
            "run_result.json",
        ],
        "last_observation": {
            "control_plane_light": str(control_plane.get("light") or ""),
            "control_plane_status": str(control_plane.get("status") or ""),
            "safe_to_run": bool(control_plane.get("safe_to_run")),
            "safe_to_compare": bool(control_plane.get("safe_to_compare")),
        },
        "next_action": str(control_plane.get("next_action") or ""),
        "job_id": str(job_id or ""),
        "run_id": str(run_id or ""),
        "created_at": _utc_iso(),
        "control_plane": dict(control_plane),
    }


def build_control_plane_run_authority_packet(
    *,
    control_plane: Mapping[str, Any],
    run_id: str,
    job_id: str = "",
) -> dict[str, Any]:
    reason_code = str(control_plane.get("reason_code") or "unknown_control_plane_block").strip()
    light = str(control_plane.get("light") or "").strip()
    return {
        "contract_version": "trust_contract_v1",
        "run_id": str(run_id or ""),
        "job_id": str(job_id or ""),
        "authoritative_proving": False,
        "authority_level": "non_authoritative",
        "checked_at": _utc_iso(),
        "reasons": [],
        "blocking_reasons": [
            f"control_plane_light_{light}",
            reason_code,
        ],
        "failure_domain": _failure_domain_for_reason(reason_code),
        "safe_to_steer_next_prompt": False,
        "terminalization_kind": "control_plane_non_comparable",
        "lane_ready": None,
    }


def write_control_plane_blocked_result(
    *,
    run_dir: Path,
    control_plane: Mapping[str, Any],
    dll_name: str,
    dll_path: str,
    binary_hash: str,
    entry_surface: str,
) -> dict[str, Any]:
    run_id = run_dir.name
    terminalization = build_control_plane_terminalization_packet(
        control_plane=control_plane,
        run_id=run_id,
        phase="control_plane_admission",
    )
    authority = build_control_plane_run_authority_packet(
        control_plane=control_plane,
        run_id=run_id,
    )
    record = {
        "run_id": run_id,
        "job_id": "",
        "status": "failed",
        "phase": "control_plane_admission",
        "valid_run": False,
        "measurement_terminalization": terminalization,
        "run_authority": authority,
        "failure_domain": str(authority.get("failure_domain") or ""),
        "authoritative_proving": False,
        "safe_to_compare": False,
        "measurement_control_plane": dict(control_plane),
        "control_plane_enforcement": {
            "enforced": True,
            "policy": "block_before_analyze",
            "light": str(control_plane.get("light") or ""),
            "reason_code": str(control_plane.get("reason_code") or ""),
        },
        "dll_name": str(dll_name or ""),
        "dll_path": str(dll_path or ""),
        "binary_hash": str(binary_hash or ""),
        "entry_surface": str(entry_surface or ""),
    }
    _write_json(run_dir / "measurement-terminalization.json", terminalization)
    _write_json(run_dir / "run-authority.json", authority)
    _write_json(run_dir / "run_result.json", record)
    return record


def apply_control_plane_to_run_record(
    *,
    run_dir: Path,
    record: Mapping[str, Any],
    control_plane: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(record)
    result["measurement_control_plane"] = dict(control_plane)
    result["control_plane_enforcement"] = {
        "enforced": True,
        "policy": "allow_comparable" if control_plane_allows_comparable_result(control_plane) else "diagnostic_only",
        "light": str(control_plane.get("light") or ""),
        "reason_code": str(control_plane.get("reason_code") or ""),
    }
    if control_plane_allows_comparable_result(control_plane):
        return result

    terminalization = dict(result.get("measurement_terminalization") or {})
    if not terminalization:
        terminalization = build_control_plane_terminalization_packet(
            control_plane=control_plane,
            run_id=str(result.get("run_id") or run_dir.name),
            job_id=str(result.get("job_id") or ""),
            phase="control_plane_diagnostic",
        )
        result["measurement_terminalization"] = terminalization
        _write_json(run_dir / "measurement-terminalization.json", terminalization)

    authority = build_control_plane_run_authority_packet(
        control_plane=control_plane,
        run_id=str(result.get("run_id") or run_dir.name),
        job_id=str(result.get("job_id") or ""),
    )
    result["run_authority"] = authority
    result["failure_domain"] = str(authority.get("failure_domain") or "")
    result["authoritative_proving"] = False
    result["safe_to_compare"] = False
    _write_json(run_dir / "run-authority.json", authority)
    _write_json(run_dir / "run_result.json", result)
    return result


def _bool_contract(contracts: Mapping[str, Any], key: str) -> bool:
    return bool(contracts.get(key))


def _record_target(record: Mapping[str, Any]) -> str:
    chain_context = record.get("chain_context")
    if isinstance(chain_context, Mapping):
        target = str(chain_context.get("target_name") or "").strip()
        if target:
            return target
    return str(record.get("target") or record.get("target_name") or record.get("dll_name") or "").strip()


def _record_control_plane(record: Mapping[str, Any]) -> dict[str, Any]:
    control_plane = record.get("measurement_control_plane")
    return dict(control_plane) if isinstance(control_plane, Mapping) else {}


def _record_authority(record: Mapping[str, Any]) -> dict[str, Any]:
    authority = record.get("run_authority")
    return dict(authority) if isinstance(authority, Mapping) else {}


def _record_terminalization(record: Mapping[str, Any]) -> dict[str, Any]:
    terminalization = record.get("measurement_terminalization")
    return dict(terminalization) if isinstance(terminalization, Mapping) else {}


def _record_is_dependency_blocked(record: Mapping[str, Any]) -> bool:
    terminalization = _record_terminalization(record)
    reason_code = str(terminalization.get("reason_code") or record.get("reason_code") or "").strip()
    phase = str(record.get("phase") or "").strip()
    status = str(record.get("status") or "").strip()
    return "dependency_blocked" in {reason_code, phase, status}


def _control_plane_forces_non_comparable(record: Mapping[str, Any]) -> bool:
    control_plane = _record_control_plane(record)
    light = str(control_plane.get("light") or "").strip().lower()
    if light in {"yellow", "red", "quarantined"}:
        return True
    return bool(record.get("measurement_terminalization")) or bool(record.get("safe_to_compare") is False)


def _record_is_decision_bearing(record: Mapping[str, Any]) -> bool:
    authority = _record_authority(record)
    if bool(record.get("authoritative_proving")):
        return True
    if bool(authority.get("authoritative_proving")):
        return True
    return str(authority.get("authority_level") or "").strip() == "decision_bearing"


def _record_selected_bridge_url(record: Mapping[str, Any]) -> str:
    control_plane_url = selected_bridge_url_from_registry(_record_control_plane(record))
    if not control_plane_url:
        return ""
    settings = record.get("explore_settings")
    routed_url = str((settings or {}).get("selected_bridge_url") or "").strip() if isinstance(settings, Mapping) else ""
    return control_plane_url if routed_url == control_plane_url else ""


def build_hard01_baseline_readiness_packet(
    *,
    case_id: str,
    lane_readiness: Mapping[str, Any] | None,
    suite_control_plane: Mapping[str, Any] | None,
    run_records: Sequence[Mapping[str, Any]] | None,
    control_plane_contracts: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Return the machine-readable gate for attempting a bounded hard01 baseline.

    This gate evaluates measurement readiness only. It does not decide whether
    hard01 is semantically correct or mature.
    """

    records = [dict(record) for record in (run_records or [])]
    contracts = dict(control_plane_contracts or {})
    lane = dict(lane_readiness or {})
    suite_plane = dict(suite_control_plane or {})

    checks: dict[str, dict[str, Any]] = {}
    blocking_reasons: list[str] = []

    lane_ok = bool(lane.get("ready")) and bool(lane.get("lane_comparable"))
    checks["lane_identity_comparability"] = {
        "passed": lane_ok,
        "evidence": {
            "ready": bool(lane.get("ready")),
            "lane_comparable": bool(lane.get("lane_comparable")),
            "blocking_reasons": _as_list(lane.get("blocking_reasons")),
        },
    }
    if not lane_ok:
        blocking_reasons.append("lane_identity_not_comparable")

    contract_keys = {
        "tier2_traffic_light_enforcement": "Tier 2 traffic-light enforcement exists",
        "tier3_selected_bridge_routing": "Tier 3 selected bridge routing exists",
        "tier4_quarantine_recovery_selection": "Tier 4 quarantine/recovery selection exists",
    }
    missing_contracts = [key for key in contract_keys if not _bool_contract(contracts, key)]
    checks["control_plane_contracts"] = {
        "passed": not missing_contracts,
        "required": contract_keys,
        "missing": missing_contracts,
    }
    blocking_reasons.extend(missing_contracts)

    checks["run_records_present"] = {
        "passed": bool(records),
        "record_count": len(records),
    }
    if not records:
        blocking_reasons.append("missing_run_records")

    semantic_violations: list[dict[str, str]] = []
    packet_gaps: list[dict[str, str]] = []
    selected_bridge_gaps: list[dict[str, str]] = []
    dependency_gaps: list[dict[str, str]] = []
    non_comparable_indexes: list[int] = []

    for index, record in enumerate(records):
        target = _record_target(record)
        control_plane = _record_control_plane(record)
        light = str(control_plane.get("light") or "").strip().lower()
        terminalization = _record_terminalization(record)
        authority = _record_authority(record)

        if light in {"green", "yellow"} and bool(control_plane.get("safe_to_run")):
            if not _record_selected_bridge_url(record):
                selected_bridge_gaps.append(
                    {
                        "target": target,
                        "reason": "selected_bridge_not_routed_to_run_record",
                    }
                )

        if light in {"red", "quarantined"} and bool(control_plane.get("safe_to_run")):
            semantic_violations.append(
                {
                    "target": target,
                    "reason": "blocked_light_marked_safe_to_run",
                }
            )

        if light in {"yellow", "red", "quarantined"}:
            if bool(control_plane.get("safe_to_compare")) or _record_is_decision_bearing(record):
                semantic_violations.append(
                    {
                        "target": target,
                        "reason": "non_green_control_plane_record_can_satisfy_proof",
                    }
                )

        if _control_plane_forces_non_comparable(record):
            non_comparable_indexes.append(index)
            if not terminalization:
                packet_gaps.append(
                    {
                        "target": target,
                        "reason": "missing_measurement_terminalization",
                    }
                )
            if not authority:
                packet_gaps.append(
                    {
                        "target": target,
                        "reason": "missing_run_authority",
                    }
                )
            elif _record_is_decision_bearing(record):
                semantic_violations.append(
                    {
                        "target": target,
                        "reason": "non_comparable_record_is_decision_bearing",
                    }
                )

    if suite_plane:
        if not selected_bridge_url_from_registry(suite_plane) and str(suite_plane.get("light") or "") in {
            "green",
            "yellow",
        }:
            selected_bridge_gaps.append(
                {
                    "target": str(suite_plane.get("target") or case_id),
                    "reason": "suite_control_plane_missing_selected_bridge",
                }
            )
    else:
        blocking_reasons.append("missing_suite_control_plane")

    if non_comparable_indexes:
        first_non_comparable = min(non_comparable_indexes)
        first_record = records[first_non_comparable]
        downstream = records[first_non_comparable + 1 :]
        if downstream:
            unblocked_downstream = [
                _record_target(record) for record in downstream if not _record_is_dependency_blocked(record)
            ]
            if unblocked_downstream:
                dependency_gaps.append(
                    {
                        "target": _record_target(first_record),
                        "reason": "non_comparable_predecessor_has_unblocked_downstream_targets",
                        "downstream": ",".join(unblocked_downstream),
                    }
                )
        elif str(first_record.get("dependent_chain_policy") or "").strip() != DEFAULT_DEPENDENCY_POLICY:
            dependency_gaps.append(
                {
                    "target": _record_target(first_record),
                    "reason": "non_comparable_chain_stop_policy_missing",
                }
            )

    checks["selected_bridge_routing"] = {
        "passed": not selected_bridge_gaps,
        "gaps": selected_bridge_gaps,
    }
    checks["non_comparable_packet_terminalization"] = {
        "passed": not packet_gaps,
        "gaps": packet_gaps,
    }
    checks["dependency_blocking"] = {
        "passed": not dependency_gaps,
        "gaps": dependency_gaps,
        "policy": DEFAULT_DEPENDENCY_POLICY,
    }
    checks["semantic_proof_containment"] = {
        "passed": not semantic_violations,
        "gaps": semantic_violations,
    }

    if selected_bridge_gaps:
        blocking_reasons.append("selected_bridge_routing_gap")
    if semantic_violations or missing_contracts:
        blocking_reasons.append("control_plane_gap")
    if packet_gaps:
        blocking_reasons.append("packet_terminalization_gap")
    if dependency_gaps:
        blocking_reasons.append("dependency_blocking_gap")

    verdict = HARD01_BASELINE_READY_VERDICT
    if not lane_ok:
        verdict = "not_ready_lane_identity_gap"
    elif selected_bridge_gaps:
        verdict = "not_ready_selected_bridge_routing_gap"
    elif semantic_violations or missing_contracts or not records:
        verdict = "not_ready_control_plane_gap"
    elif packet_gaps:
        verdict = "not_ready_packet_terminalization_gap"
    elif dependency_gaps:
        verdict = "not_ready_dependency_blocking_gap"

    ready = verdict == HARD01_BASELINE_READY_VERDICT
    return {
        "schema_version": HARD01_BASELINE_READINESS_SCHEMA_VERSION,
        "source": "measurement_control_plane",
        "case_id": str(case_id or "hard-01"),
        "verdict": verdict,
        "ready_for_bounded_baseline_attempt": ready,
        "claim_ceiling": "hard01 baseline readiness only; no hard01 maturity or semantic pipeline claim",
        "checks": checks,
        "blocking_reasons": sorted(set(blocking_reasons)),
        "record_count": len(records),
        "next_action": (
            "run hard01_bounded_baseline_attempt_v1 with short explicit budgets"
            if ready
            else "route to the readiness gap named by verdict before hard01 baseline attempt"
        ),
        "created_at": created_at or _utc_iso(),
    }
