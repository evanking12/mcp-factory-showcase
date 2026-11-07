from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ARTIFACT_SCHEMA_VERSION = "1.0.0"
FRONTIER_SEAM_AUDIT_ARTIFACT = "config-frontier-seam-audit.json"
BASELINE_DELTA_ARTIFACT = "config-frontier-baseline-delta-map.json"
LINEAGE_HANDOFF_ARTIFACT = "config-prerequisite-lineage-handoff-audit.json"
SURVIVOR_MAP_ARTIFACT = "config-working-call-survivor-map.json"
FAILURE_CLUSTER_ARTIFACT = "config-failure-cluster-shape-audit.json"
ENV_ASSUMPTION_ARTIFACT = "config-env-assumption-surface-audit.json"
TRUST_SEPARATION_ARTIFACT = "config-frontier-trust-vs-result-trust-separation.json"
MINIMAL_REPRODUCER_ARTIFACT = "config-minimal-reproducer.json"
REPORTING_SNAPSHOT_ARTIFACT = "reporting-frontier-deferred-snapshot.json"
SCOPE_ARTIFACT = "config-frontier-evidence-scope.json"
COMPARISON_NOTE_ARTIFACT = "config-frontier-overlap-comparison-note.md"
PROMPT_25_NOTE_ARTIFACT = "prompt-25-construction-note.md"
FIXTURE_ANALOGY_ARTIFACT = "config-live-vs-fixture-analogy-note.md"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(values: Any) -> list[dict[str, Any]]:
    return [dict(value) for value in list(values or []) if isinstance(value, dict)]


def _finding_map(findings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in findings:
        fn = _text(row.get("function"))
        if not fn:
            continue
        result.setdefault(fn, []).append(dict(row))
    return result


def _primary_finding(row_group: list[dict[str, Any]]) -> dict[str, Any]:
    if not row_group:
        return {}
    ordered = sorted(
        row_group,
        key=lambda row: (
            0 if _text(row.get("status_canonical")) == "verified_success" else 1,
            0 if bool(row.get("direct_target_truth")) else 1,
            -float(row.get("reusable_truth_score") or 0.0),
        ),
    )
    return dict(ordered[0])


def _extract_sentinel_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for marker in ("4294962292", "4294962293", "4294962294", "4294962295", "access violation"):
        if marker in text and marker not in tokens:
            tokens.append(marker)
    return tokens


def _config_row(campaign_truth: dict[str, Any], filename: str = "contoso_config.dll") -> dict[str, Any]:
    for row in _rows(campaign_truth.get("per_dll")):
        if _text(row.get("filename")) == filename:
            return row
    return {}


def _baseline_entry(campaign_truth: dict[str, Any], filename: str = "contoso_config.dll") -> dict[str, Any]:
    baseline_contract = dict(campaign_truth.get("baseline_contract") or {})
    for row in _rows(baseline_contract.get("entries")):
        if _text(row.get("filename")) == filename:
            return row
    return {}


def build_config_frontier_baseline_delta_map(
    *,
    campaign_truth: dict[str, Any],
    blocker_classification: dict[str, Any] | None = None,
    filename: str = "contoso_config.dll",
) -> dict[str, Any]:
    current = _config_row(campaign_truth, filename)
    baseline = _baseline_entry(campaign_truth, filename)
    current_verified = int(current.get("verified_count") or 0)
    baseline_verified = int(baseline.get("baseline_verified_count") or 0)
    unresolved = []
    blocker_classification = dict(blocker_classification or current.get("blocker_classification") or {})
    for row in _rows(blocker_classification.get("function_rows")):
        if _text(row.get("status")).lower() != "success":
            unresolved.append(_text(row.get("function")))
    if not unresolved:
        unresolved = [_text(row.get("function")) for row in _rows(current.get("function_rows")) if _text(row.get("status")).lower() != "success"]
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "campaign_id": _text(campaign_truth.get("campaign_id")),
        "filename": filename,
        "baseline_job_id": _text(baseline.get("baseline_job_id")),
        "current_job_id": _text(current.get("job_id")),
        "analysis_entrypoint": _text(current.get("analysis_entrypoint") or baseline.get("analysis_entrypoint")),
        "binary_origin": _text(current.get("binary_origin") or baseline.get("binary_origin")),
        "baseline_verified_count": baseline_verified,
        "baseline_total_functions": int(baseline.get("baseline_total_functions") or 0),
        "current_verified_count": current_verified,
        "current_total_functions": int(current.get("total_functions") or 0),
        "verified_delta": current_verified - baseline_verified,
        "current_primary_blocker_family": _text(current.get("blocker_family_primary") or current.get("primary_blocker_family")),
        "candidate_next_system": _text(current.get("candidate_next_system")),
        "unresolved_functions": [name for name in unresolved if name],
    }


def build_config_working_call_survivor_map(
    *, findings: list[dict[str, Any]], blocker_classification: dict[str, Any]
) -> dict[str, Any]:
    failing = {_text(row.get("function")) for row in _rows(blocker_classification.get("function_rows"))}
    survivors: list[dict[str, Any]] = []
    finding_groups = _finding_map(findings)
    for function, rows in sorted(finding_groups.items()):
        primary = _primary_finding(rows)
        if _text(primary.get("status_canonical")) != "verified_success":
            continue
        survivors.append(
            {
                "function": function,
                "working_call": primary.get("working_call"),
                "reusable_truth_eligible": bool(primary.get("reusable_truth_eligible")),
                "reusable_truth_reasons": list(primary.get("reusable_truth_reasons") or []),
                "phase": _text((primary.get("direct_target_truth") or {}).get("phase")),
                "is_active_frontier_failure_dependency": function in failing
                or function in {"CFG_OpenLicensedWindow", "CFG_BindCustomer", "CFG_SetupEnvironment", "CFG_Initialize"},
            }
        )
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "survivor_count": len(survivors),
        "survivors": survivors,
    }


def build_config_failure_cluster_shape_audit(
    *,
    findings: list[dict[str, Any]],
    blocker_classification: dict[str, Any],
    probe_stop_reasons: list[dict[str, Any]],
) -> dict[str, Any]:
    finding_groups = _finding_map(findings)
    stop_by_function = {
        _text(row.get("function")): {
            "stop_reason": _text(row.get("stop_reason")),
            "tool_calls_used": int(row.get("tool_calls_used") or 0),
            "rounds_used": int(row.get("rounds_used") or 0),
        }
        for row in _rows(probe_stop_reasons)
        if _text(row.get("function"))
    }
    clusters: list[dict[str, Any]] = []
    for function_row in _rows(blocker_classification.get("function_rows")):
        function = _text(function_row.get("function"))
        primary = _primary_finding(finding_groups.get(function, []))
        finding_text = _text(primary.get("finding"))
        clusters.append(
            {
                "function": function,
                "first_blocking_stage": _text(function_row.get("first_blocking_stage")),
                "stop_reason": stop_by_function.get(function, {}).get("stop_reason", ""),
                "tool_calls_used": stop_by_function.get(function, {}).get("tool_calls_used", 0),
                "rounds_used": stop_by_function.get(function, {}).get("rounds_used", 0),
                "sentinel_markers": _extract_sentinel_tokens(finding_text),
                "candidate_family": _text(function_row.get("blocker_family")),
            }
        )
    shared_stage = sorted({_text(row.get("first_blocking_stage")) for row in clusters if _text(row.get("first_blocking_stage"))})
    shared_stop_reasons = sorted({_text(row.get("stop_reason")) for row in clusters if _text(row.get("stop_reason"))})
    shared_markers = sorted({marker for row in clusters for marker in list(row.get("sentinel_markers") or [])})
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "cluster_count": len(clusters),
        "shared_first_blocking_stages": shared_stage,
        "shared_stop_reasons": shared_stop_reasons,
        "shared_sentinel_markers": shared_markers,
        "supports_single_family_blocker": len(shared_stage) == 1 and bool(shared_stop_reasons),
        "clusters": clusters,
    }


def build_config_prerequisite_lineage_handoff_audit(
    *,
    findings: list[dict[str, Any]],
    verification_report: dict[str, Any],
    prerequisite_state_machine: dict[str, Any],
    blocker_classification: dict[str, Any],
) -> dict[str, Any]:
    finding_groups = _finding_map(findings)
    roles = { _text(row.get("name")): dict(row) for row in _rows(prerequisite_state_machine.get("roles")) if _text(row.get("name"))}

    stable_prereqs: list[dict[str, Any]] = []
    ephemeral_successes: list[dict[str, Any]] = []
    for function in ("CFG_SetupEnvironment", "CFG_Initialize", "CFG_BindCustomer", "CFG_OpenLicensedWindow"):
        primary = _primary_finding(finding_groups.get(function, []))
        if not primary:
            continue
        entry = {
            "function": function,
            "status_canonical": _text(primary.get("status_canonical")),
            "working_call": primary.get("working_call"),
            "phase": _text((primary.get("direct_target_truth") or {}).get("phase")),
            "reusable_truth_eligible": bool(primary.get("reusable_truth_eligible")),
            "reusable_truth_reasons": list(primary.get("reusable_truth_reasons") or []),
        }
        if function == "CFG_OpenLicensedWindow" or list(primary.get("reusable_truth_reasons") or []):
            ephemeral_successes.append(entry)
        else:
            stable_prereqs.append(entry)

    same_run_chains: list[dict[str, Any]] = []
    for row in _rows(verification_report.get("entries")):
        chain = _rows(row.get("prerequisite_chain"))
        names = [_text(item.get("function")) for item in chain]
        if "CFG_GetLicenseNonce" in names or "CFG_ApproveLicensedCall" in names:
            same_run_chains.append(
                {
                    "function": _text(row.get("function")),
                    "verification": _text(row.get("verification")),
                    "chain_functions": names,
                    "args": row.get("args"),
                }
            )

    unresolved = [_text(row.get("function")) for row in _rows(blocker_classification.get("function_rows"))]
    broad_env_supported = not all(
        any(item["function"] == fn and item["status_canonical"] == "verified_success" for item in stable_prereqs)
        for fn in ("CFG_SetupEnvironment", "CFG_Initialize", "CFG_BindCustomer")
    )
    narrowed = (
        bool(same_run_chains)
        and any(not item.get("reusable_truth_eligible") for item in ephemeral_successes)
        and not broad_env_supported
    )
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "primary_blocker_family_before": _text(blocker_classification.get("primary_blocker_family")),
        "narrowed_blocker_family": "lineage artifact materialization" if narrowed else _text(blocker_classification.get("primary_blocker_family")),
        "broad_environment_gate_supported": broad_env_supported,
        "stable_prerequisites": stable_prereqs,
        "ephemeral_lineage_successes": ephemeral_successes,
        "successful_same_run_lineage_chains": same_run_chains,
        "unresolved_functions": unresolved,
        "lineage_sensitive_roles": {
            name: {
                "sequence_role": _text(row.get("sequence_role")),
                "prerequisites": list(row.get("prerequisites") or []),
                "input_kinds": list(row.get("input_kinds") or []),
                "output_kinds": list(row.get("output_kinds") or []),
            }
            for name, row in roles.items()
            if name in {"CFG_OpenLicensedWindow", "CFG_GetLicenseNonce", "CFG_ApproveLicensedCall", "CFG_RunCustomerSync"}
        },
        "narrow_proof_green": narrowed,
    }


def build_config_env_assumption_surface_audit(
    *, findings: list[dict[str, Any]], prerequisite_state_machine: dict[str, Any]
) -> dict[str, Any]:
    finding_groups = _finding_map(findings)
    satisfied: list[dict[str, Any]] = []
    unknowns: list[str] = []
    for function in ("CFG_SetupEnvironment", "CFG_Initialize", "CFG_BindCustomer"):
        primary = _primary_finding(finding_groups.get(function, []))
        if _text(primary.get("status_canonical")) == "verified_success":
            satisfied.append(
                {
                    "function": function,
                    "phase": _text((primary.get("direct_target_truth") or {}).get("phase")),
                    "working_call": primary.get("working_call"),
                }
            )
        else:
            unknowns.append(function)

    lineage_sensitive = []
    for row in _rows(prerequisite_state_machine.get("roles")):
        if _text(row.get("name")) in {"CFG_OpenLicensedWindow", "CFG_GetLicenseNonce", "CFG_ApproveLicensedCall", "CFG_RunCustomerSync"}:
            lineage_sensitive.append(
                {
                    "function": _text(row.get("name")),
                    "prerequisites": list(row.get("prerequisites") or []),
                    "input_kinds": list(row.get("input_kinds") or []),
                    "output_kinds": list(row.get("output_kinds") or []),
                }
            )

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "broad_environment_prereqs_satisfied": satisfied,
        "remaining_broad_environment_unknowns": unknowns,
        "lineage_sensitive_functions": lineage_sensitive,
        "supports_generic_environment_missing": not bool(satisfied) or bool(unknowns),
        "supports_lineage_specific_gate": bool(satisfied) and not bool(unknowns),
    }


def build_config_frontier_trust_vs_result_trust_separation(
    *, campaign_truth: dict[str, Any], blocker_classification: dict[str, Any]
) -> dict[str, Any]:
    current = _config_row(campaign_truth)
    unresolved_count = int(blocker_classification.get("unresolved_function_count") or len(_rows(blocker_classification.get("function_rows"))))
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "campaign_id": _text(campaign_truth.get("campaign_id")),
        "filename": _text(current.get("filename")),
        "lane_trust_status": _text(current.get("lane_trust_status")),
        "runtime_path_trust": _text(current.get("runtime_path_trust")),
        "package_floor_trusted": bool(campaign_truth.get("package_internal_truth_ready")),
        "config_result_trusted_for_narrowing": unresolved_count > 0,
        "config_result_green": unresolved_count == 0,
        "unresolved_function_count": unresolved_count,
        "separation_summary": (
            "The lane is trusted enough to steer from, but the config results remain red; "
            "this is a blocker-narrowing surface, not a success surface."
        ),
    }


def build_config_minimal_reproducer(
    *, verification_report: dict[str, Any], lineage_handoff_audit: dict[str, Any]
) -> dict[str, Any]:
    chosen_chain: dict[str, Any] = {}
    for row in _rows(verification_report.get("entries")):
        names = [_text(item.get("function")) for item in _rows(row.get("prerequisite_chain"))]
        if names[:4] == ["CFG_Initialize", "CFG_SetupEnvironment", "CFG_Initialize", "CFG_BindCustomer"] and "CFG_GetLicenseNonce" in names:
            chosen_chain = {
                "target_function": _text(row.get("function")),
                "prerequisite_chain": _rows(row.get("prerequisite_chain")),
                "args": row.get("args"),
                "verification": _text(row.get("verification")),
            }
            break
    if not chosen_chain:
        chosen_chain = {
            "target_function": "CFG_GetLicenseNonce",
            "prerequisite_chain": [],
            "args": {},
            "verification": "unknown",
        }
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "reproducer_focus": "licensed ticket and nonce lineage",
        "narrowed_blocker_family": _text(lineage_handoff_audit.get("narrowed_blocker_family")),
        "minimal_chain": chosen_chain,
        "why_minimal": (
            "This chain is the smallest observed same-run sequence that reaches the ticket/nonce handoff boundary "
            "before the active failing targets diverge."
        ),
    }


def build_reporting_deferred_frontier_snapshot(campaign_truth: dict[str, Any]) -> dict[str, Any]:
    for row in _rows(campaign_truth.get("per_dll")):
        if _text(row.get("filename")) == "contoso_reporting.dll":
            return {
                "schema_version": ARTIFACT_SCHEMA_VERSION,
                "filename": "contoso_reporting.dll",
                "job_id": _text(row.get("job_id")),
                "verified_count": int(row.get("verified_count") or 0),
                "total_functions": int(row.get("total_functions") or 0),
                "primary_blocker_family": _text(row.get("blocker_family_primary")),
                "candidate_next_system": _text(row.get("candidate_next_system")),
                "active_frontier": bool(row.get("active_frontier")),
                "why_deferred": "Config remains the stronger blocker because package-floor validity is green and config is the largest trusted frontier loss.",
            }
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "filename": "contoso_reporting.dll",
        "why_deferred": "reporting row missing from campaign truth",
    }


def render_config_frontier_overlap_comparison_note(
    *,
    baseline_delta: dict[str, Any],
    lineage_handoff_audit: dict[str, Any],
    rerun_baseline_delta: dict[str, Any] | None = None,
) -> str:
    lines = [
        "# Config Frontier Overlap Comparison",
        "",
        f"- baseline verified: `{baseline_delta.get('baseline_verified_count')}/{baseline_delta.get('baseline_total_functions')}`",
        f"- current verified: `{baseline_delta.get('current_verified_count')}/{baseline_delta.get('current_total_functions')}`",
        f"- verified delta: `{baseline_delta.get('verified_delta')}`",
        f"- unresolved functions: {', '.join(baseline_delta.get('unresolved_functions') or []) or 'none'}",
        f"- primary blocker before narrowing: `{baseline_delta.get('current_primary_blocker_family')}`",
        f"- narrowed blocker family: `{lineage_handoff_audit.get('narrowed_blocker_family')}`",
    ]
    if rerun_baseline_delta:
        lines.extend(
            [
                f"- rerun verified: `{rerun_baseline_delta.get('current_verified_count')}/{rerun_baseline_delta.get('current_total_functions')}`",
                f"- rerun unresolved functions: {', '.join(rerun_baseline_delta.get('unresolved_functions') or []) or 'none'}",
            ]
        )
    return "\n".join(lines) + "\n"


def render_prompt_25_section(title: str, payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"## {title}",
            "",
            "```json",
            json.dumps(payload, indent=2),
            "```",
            "",
        ]
    )


def render_fixture_analogy_note(
    *,
    lineage_handoff_audit: dict[str, Any],
    trust_separation: dict[str, Any],
) -> str:
    narrowed_family = _text(lineage_handoff_audit.get("narrowed_blocker_family"))
    return "\n".join(
        [
            "# Config Live-vs-Fixture Analogy",
            "",
            "The current Contoso config blocker now resembles the design-suite proving families at the dependency-meaning level, not at the package-shape level.",
            "",
            f"- narrowed blocker family: `{narrowed_family}`",
            "- resemblance to Northstar/Atlas: same-run producer output is observed but not preserved cleanly enough for downstream consumers",
            "- difference from Northstar: this is not branch lineage or confirmation pressure; it is transient runtime artifact carryover on a live DLL lane",
            "- difference from Atlas: this is not mutual pressure between two peers; it is a one-producer-to-many-consumer handoff seam inside one DLL family",
            f"- trust separation: `{trust_separation.get('separation_summary')}`",
            "",
            "This is useful because it means the design-suite work was not wasted. The live blocker can now be described with a more specific dependency-shape diagnosis than generic environment gating.",
            "",
        ]
    )


def build_config_frontier_seam_audit(
    *,
    baseline_delta: dict[str, Any],
    lineage_handoff_audit: dict[str, Any],
    failure_clusters: dict[str, Any],
    env_audit: dict[str, Any],
    trust_separation: dict[str, Any],
    rerun_baseline_delta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "current_primary_blocker_family": baseline_delta.get("current_primary_blocker_family"),
        "narrowed_blocker_family": lineage_handoff_audit.get("narrowed_blocker_family"),
        "supports_single_failure_cluster": bool(failure_clusters.get("supports_single_family_blocker")),
        "supports_lineage_specific_gate": bool(env_audit.get("supports_lineage_specific_gate")),
        "narrow_proof_green": bool(lineage_handoff_audit.get("narrow_proof_green")),
        "lane_trusted": _text(trust_separation.get("lane_trust_status")) == "trusted",
        "rerun_verified_count": (rerun_baseline_delta or {}).get("current_verified_count"),
        "rerun_unresolved_functions": list((rerun_baseline_delta or {}).get("unresolved_functions") or []),
    }


def write_json_artifact(output_dir: Path, filename: str, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_text_artifact(output_dir: Path, filename: str, content: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(content, encoding="utf-8")
    return path
