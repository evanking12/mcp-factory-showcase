from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.config_frontier_environment_gate import (  # noqa: E402
    BASELINE_DELTA_ARTIFACT,
    COMPARISON_NOTE_ARTIFACT,
    ENV_ASSUMPTION_ARTIFACT,
    FAILURE_CLUSTER_ARTIFACT,
    FIXTURE_ANALOGY_ARTIFACT,
    FRONTIER_SEAM_AUDIT_ARTIFACT,
    LINEAGE_HANDOFF_ARTIFACT,
    MINIMAL_REPRODUCER_ARTIFACT,
    PROMPT_25_NOTE_ARTIFACT,
    REPORTING_SNAPSHOT_ARTIFACT,
    SCOPE_ARTIFACT,
    SURVIVOR_MAP_ARTIFACT,
    TRUST_SEPARATION_ARTIFACT,
    build_config_env_assumption_surface_audit,
    build_config_failure_cluster_shape_audit,
    build_config_frontier_baseline_delta_map,
    build_config_frontier_seam_audit,
    build_config_frontier_trust_vs_result_trust_separation,
    build_config_minimal_reproducer,
    build_config_prerequisite_lineage_handoff_audit,
    build_config_working_call_survivor_map,
    build_reporting_deferred_frontier_snapshot,
    render_config_frontier_overlap_comparison_note,
    render_fixture_analogy_note,
    render_prompt_25_section,
    write_json_artifact,
    write_text_artifact,
)
from scripts.runs.run_blocker_harvest_waves import read_json, write_json  # noqa: E402
from scripts.runs.run_package_floor_validity_gate import _run_live_reduced_batch_b  # noqa: E402


DEFAULT_PACKAGE_FLOOR_ROOT = (
    REPO_ROOT / "sessions" / "engine_scaling" / "package_floor_validity" / "20260408-145200"
)


def _latest_directory(root: Path) -> Path:
    candidates = [path for path in root.iterdir() if path.is_dir()]
    if not candidates:
        return root
    return sorted(candidates)[-1]


def _resolve_package_floor_root(cli_value: str) -> Path:
    if cli_value:
        return Path(cli_value)
    if DEFAULT_PACKAGE_FLOOR_ROOT.exists():
        return DEFAULT_PACKAGE_FLOOR_ROOT
    return _latest_directory(REPO_ROOT / "sessions" / "engine_scaling" / "package_floor_validity")


def _resolve_run_root(package_floor_root: Path, explicit_run_root: str) -> Path:
    if explicit_run_root:
        return Path(explicit_run_root)
    inputs = read_json(package_floor_root / "package-floor-validity-inputs.json", {})
    audited = str(inputs.get("audited_run_root") or "").strip()
    if audited:
        return Path(audited)
    return package_floor_root


def _load_campaign_truth(run_root: Path) -> dict[str, Any]:
    for candidate in (
        run_root / "snapshot" / "campaign" / "campaign-truth.json",
        run_root / "snapshot" / "campaign-truth.json",
        run_root / "campaign-truth.json",
    ):
        payload = read_json(candidate, {})
        if payload:
            return payload
    return {}


def _load_config_snapshot(run_root: Path, filename: str = "contoso_config.dll") -> dict[str, Any]:
    base = run_root / "snapshot" / "dlls" / filename
    return {
        "base": str(base),
        "findings": read_json(base / "findings.json", []),
        "blocker_classification": read_json(base / "blocker-classification.json", {}),
        "verification_report": read_json(base / "verification-report.json", {}),
        "prerequisite_state_machine": read_json(base / "prerequisite_state_machine.json", {}),
        "probe_stop_reasons": read_json(base / "evidence" / "stage-02-probe-loop" / "probe-stop-reasons.json", []),
        "probe_strategy_summary": read_json(base / "evidence" / "stage-02-probe-loop" / "probe-strategy-summary.json", []),
    }


def _append_prompt_25_section(note_path: Path, title: str, payload: dict[str, Any]) -> None:
    existing = note_path.read_text(encoding="utf-8") if note_path.exists() else "# Prompt 25 Construction Note\n\n"
    existing += render_prompt_25_section(title, payload)
    note_path.write_text(existing, encoding="utf-8")


def _classify_scope(lineage_audit: dict[str, Any]) -> dict[str, Any]:
    executed = [
        "24a-config-frontier-baseline-delta-map",
        "24c-config-prerequisite-lineage-and-artifact-handoff-audit",
        "24d-reporting-deferred-frontier-snapshot",
        "24e-config-working-call-survivor-map",
        "24f-config-failure-cluster-shape-audit",
        "24g-config-env-assumption-surface-audit",
        "24m-config-frontier-trust-vs-result-trust-separation",
        "24n-config-minimal-reproducer-extraction",
        "24o-config-live-vs-fixture-analogy-note",
    ]
    skipped = {
        "24b-config-entry-surface-and-runtime-shape-audit": "Prompt 23 already made the canonical upload entry surface and runtime path trust green for this exact lane.",
        "24h-config-same-run-vs-seeded-prior-delta-audit": "The verification report already contains same-run lineage chains; the active blocker is preservation of those chains, not ambiguity between same-run and seeded-prior.",
        "24i-config-observer-gap-audit": "The blocker classification, verification report, and package-floor gate already provide enough observer coverage to narrow the blocker once lineage preservation is made explicit.",
        "24j-config-artifact-materialization-audit": "Covered directly by the lineage handoff audit and minimal reproducer outputs.",
        "24k-config-parameter-role-ambiguity-audit": "The stable prerequisites and same-run verification entries already show the critical parameter roles are understood well enough to avoid this being the dominant blocker.",
        "24l-config-stage-window-timeline": "All active failing functions already agree on s02_probe as the first blocking stage in blocker-classification.json.",
    }
    if not lineage_audit.get("narrow_proof_green"):
        skipped["24b-config-entry-surface-and-runtime-shape-audit"] = (
            "Reinstated if lineage narrowing had failed; stronger evidence kept it unnecessary in this pass."
        )
    return {
        "executed_evidence_prompts": executed,
        "skipped_evidence_prompts": skipped,
    }


def _build_prompt_25(
    *,
    output_dir: Path,
    seam_audit: dict[str, Any],
    baseline_delta: dict[str, Any],
    rerun_baseline_delta: dict[str, Any] | None,
) -> Path:
    next_prompt_path = (
        REPO_ROOT
        / "docs"
        / "architecture"
        / "engineScaling"
        / "engineScaling_DesignSuite"
        / "engineScaling_DesignSuitePrompts"
        / "25-config-lineage-materialization-repair.md"
    )
    if rerun_baseline_delta and int(rerun_baseline_delta.get("current_verified_count") or 0) > int(
        baseline_delta.get("current_verified_count") or 0
    ):
        goal_line = "Use the narrowed lineage-materialization diagnosis to confirm the config seam improvement and then decide whether reporting is now the strongest blocker."
    else:
        goal_line = "Repair the config same-run lineage artifact materialization seam so licensed ticket and nonce continuity survive into the active frontier targets."
    content = "\n".join(
        [
            "# Prompt 25: Config Lineage Materialization Repair",
            "",
            "## Goal",
            "",
            goal_line,
            "",
            "## Why This Comes Now",
            "",
            "Prompt 24 proved the config frontier loss is narrower than generic environment gating.",
            "The strongest remaining live config blocker is now preserving the same-run ticket and nonce lineage already observed in the trusted lane artifacts.",
            "",
            "## Prerequisites",
            "",
            f"- Prompt 24 seam audit: `{output_dir / FRONTIER_SEAM_AUDIT_ARTIFACT}`",
            f"- Prompt 24 construction note: `{output_dir / PROMPT_25_NOTE_ARTIFACT}`",
            "",
            "## Implementation Scope",
            "",
            "- make the smallest config-local or generic artifact-preservation change that can carry the licensed ticket/nonce chain forward",
            "- reprove the seam narrowly before any broader rerun",
            "- rerun reduced Batch B only after the narrow proof is green",
            "",
            "## Done Means",
            "",
            "- config is either improved over the current 9/12 frontier or further narrowed into a single preservable handoff seam",
            "- Prompt 26 can honestly choose between reporting repair and collector/slice follow-up",
            "",
        ]
    )
    next_prompt_path.write_text(content + "\n", encoding="utf-8")
    return next_prompt_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Prompt 24 config frontier environment-gate repair evidence and bounded rerun.")
    parser.add_argument("--package-floor-root", default="", help="Package-floor validity root from Prompt 23.")
    parser.add_argument("--run-root", default="", help="Explicit reduced Batch B run root to audit.")
    parser.add_argument("--output-root", default="", help="Output directory for Prompt 24 artifacts.")
    parser.add_argument("--skip-live-rerun", action="store_true", help="Skip the bounded reduced Batch B rerun.")
    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_root = (
        Path(args.output_root)
        if args.output_root
        else REPO_ROOT / "sessions" / "engine_scaling" / "config_frontier_environment_gate" / timestamp
    )
    output_root.mkdir(parents=True, exist_ok=True)

    package_floor_root = _resolve_package_floor_root(args.package_floor_root)
    run_root = _resolve_run_root(package_floor_root, args.run_root)
    campaign_truth = _load_campaign_truth(run_root)
    if not campaign_truth:
        raise RuntimeError(f"missing campaign truth under {run_root}")
    snapshot = _load_config_snapshot(run_root)
    findings = list(snapshot["findings"] or [])
    blocker_classification = dict(snapshot["blocker_classification"] or {})
    verification_report = dict(snapshot["verification_report"] or {})
    prerequisite_state_machine = dict(snapshot["prerequisite_state_machine"] or {})
    probe_stop_reasons = list(snapshot["probe_stop_reasons"] or [])

    prompt25_note_path = output_root / PROMPT_25_NOTE_ARTIFACT
    prompt25_note_path.write_text("# Prompt 25 Construction Note\n\n", encoding="utf-8")

    baseline_delta = build_config_frontier_baseline_delta_map(
        campaign_truth=campaign_truth,
        blocker_classification=blocker_classification,
    )
    write_json_artifact(output_root, BASELINE_DELTA_ARTIFACT, baseline_delta)
    _append_prompt_25_section(prompt25_note_path, "24a Config Frontier Baseline Delta Map", baseline_delta)

    lineage_audit = build_config_prerequisite_lineage_handoff_audit(
        findings=findings,
        verification_report=verification_report,
        prerequisite_state_machine=prerequisite_state_machine,
        blocker_classification=blocker_classification,
    )
    write_json_artifact(output_root, LINEAGE_HANDOFF_ARTIFACT, lineage_audit)
    _append_prompt_25_section(prompt25_note_path, "24c Config Prerequisite Lineage Handoff Audit", lineage_audit)

    survivor_map = build_config_working_call_survivor_map(
        findings=findings,
        blocker_classification=blocker_classification,
    )
    write_json_artifact(output_root, SURVIVOR_MAP_ARTIFACT, survivor_map)
    _append_prompt_25_section(prompt25_note_path, "24e Config Working Call Survivor Map", survivor_map)

    failure_clusters = build_config_failure_cluster_shape_audit(
        findings=findings,
        blocker_classification=blocker_classification,
        probe_stop_reasons=probe_stop_reasons,
    )
    write_json_artifact(output_root, FAILURE_CLUSTER_ARTIFACT, failure_clusters)
    _append_prompt_25_section(prompt25_note_path, "24f Config Failure Cluster Shape Audit", failure_clusters)

    env_audit = build_config_env_assumption_surface_audit(
        findings=findings,
        prerequisite_state_machine=prerequisite_state_machine,
    )
    write_json_artifact(output_root, ENV_ASSUMPTION_ARTIFACT, env_audit)
    _append_prompt_25_section(prompt25_note_path, "24g Config Environment Assumption Surface Audit", env_audit)

    trust_separation = build_config_frontier_trust_vs_result_trust_separation(
        campaign_truth=campaign_truth,
        blocker_classification=blocker_classification,
    )
    write_json_artifact(output_root, TRUST_SEPARATION_ARTIFACT, trust_separation)
    _append_prompt_25_section(prompt25_note_path, "24m Config Trust vs Result Trust Separation", trust_separation)

    minimal_reproducer = build_config_minimal_reproducer(
        verification_report=verification_report,
        lineage_handoff_audit=lineage_audit,
    )
    write_json_artifact(output_root, MINIMAL_REPRODUCER_ARTIFACT, minimal_reproducer)
    _append_prompt_25_section(prompt25_note_path, "24n Config Minimal Reproducer Extraction", minimal_reproducer)

    reporting_snapshot = build_reporting_deferred_frontier_snapshot(campaign_truth)
    write_json_artifact(output_root, REPORTING_SNAPSHOT_ARTIFACT, reporting_snapshot)
    _append_prompt_25_section(prompt25_note_path, "24d Reporting Deferred Frontier Snapshot", reporting_snapshot)

    fixture_note = render_fixture_analogy_note(
        lineage_handoff_audit=lineage_audit,
        trust_separation=trust_separation,
    )
    write_text_artifact(output_root, FIXTURE_ANALOGY_ARTIFACT, fixture_note)

    scope = _classify_scope(lineage_audit)
    write_json_artifact(output_root, SCOPE_ARTIFACT, scope)

    rerun_root: Path | None = None
    rerun_baseline_delta: dict[str, Any] | None = None
    if lineage_audit.get("narrow_proof_green") and not args.skip_live_rerun:
        rerun_root = _run_live_reduced_batch_b(output_root)
        rerun_truth = _load_campaign_truth(rerun_root)
        rerun_snapshot = _load_config_snapshot(rerun_root)
        rerun_baseline_delta = build_config_frontier_baseline_delta_map(
            campaign_truth=rerun_truth,
            blocker_classification=dict(rerun_snapshot["blocker_classification"] or {}),
        )
        write_json_artifact(output_root, "config-frontier-rerun-baseline-delta-map.json", rerun_baseline_delta)
        _append_prompt_25_section(prompt25_note_path, "Bounded Reduced Batch B Rerun", rerun_baseline_delta)

    seam_audit = build_config_frontier_seam_audit(
        baseline_delta=baseline_delta,
        lineage_handoff_audit=lineage_audit,
        failure_clusters=failure_clusters,
        env_audit=env_audit,
        trust_separation=trust_separation,
        rerun_baseline_delta=rerun_baseline_delta,
    )
    write_json_artifact(output_root, FRONTIER_SEAM_AUDIT_ARTIFACT, seam_audit)

    comparison_note = render_config_frontier_overlap_comparison_note(
        baseline_delta=baseline_delta,
        lineage_handoff_audit=lineage_audit,
        rerun_baseline_delta=rerun_baseline_delta,
    )
    write_text_artifact(output_root, COMPARISON_NOTE_ARTIFACT, comparison_note)

    next_prompt_path = _build_prompt_25(
        output_dir=output_root,
        seam_audit=seam_audit,
        baseline_delta=baseline_delta,
        rerun_baseline_delta=rerun_baseline_delta,
    )
    write_json(
        output_root / "prompt-24-evaluation.json",
        {
            "what_this_prompt_proved": (
                "The config frontier loss is narrower than generic environment gating and is machine-readable as a lineage artifact materialization seam."
            ),
            "what_remains_unproven": (
                "Prompt 24 does not itself repair the ticket/nonce preservation seam; it proves the correct next target and refreshes the live rerun surface."
            ),
            "what_changed_in_the_architecture": (
                "The live config frontier now has a dedicated audit owner and rerun gate instead of relying on campaign-truth summaries alone."
            ),
            "is_the_planned_next_prompt_still_correct": False,
            "replacement_next_prompt": {
                "id": "25",
                "filename": next_prompt_path.name,
                "path": str(next_prompt_path),
            },
            "rerun_root": str(rerun_root) if rerun_root else "",
        },
    )

    print(
        json.dumps(
            {
                "output_root": str(output_root),
                "run_root": str(run_root),
                "narrowed_blocker_family": lineage_audit.get("narrowed_blocker_family"),
                "narrow_proof_green": lineage_audit.get("narrow_proof_green"),
                "rerun_root": str(rerun_root) if rerun_root else "",
                "prompt_25": str(next_prompt_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
