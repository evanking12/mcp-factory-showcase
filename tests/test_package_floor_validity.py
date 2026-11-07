from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.package_floor_validity import (  # noqa: E402
    PACKAGE_FLOOR_GATE_ARTIFACT,
    PACKAGE_FLOOR_REPLAY_AUDIT_ARTIFACT,
    build_package_floor_validity_gate,
    resolve_package_floor_entry_surface,
)
from scripts.runs.run_package_floor_validity_gate import main as package_floor_gate_main  # noqa: E402


def _sample_campaign_truth() -> dict:
    return {
        "campaign_id": "59affa8e",
        "package_id": "contoso-business-suite",
        "package_label": "Contoso Business Suite",
        "phase": "done",
        "package_internal_truth_ready": True,
        "overlap_baseline_comparable": True,
        "package_floor_evidence_class": "overlap_comparable_confirmation",
        "active_frontier_dlls": [
            "contoso_config.dll",
            "contoso_reporting.dll",
            "contoso_pricing.dll",
        ],
        "imported_lower_floor_dlls": [
            "contoso_gateway.dll",
            "contoso_transport.dll",
        ],
        "baseline_contract": {
            "entries": [
                {
                    "filename": "contoso_config.dll",
                    "baseline_job_id": "baseline-config",
                    "analysis_entrypoint": "upload",
                    "binary_origin": "temp_upload",
                },
                {
                    "filename": "contoso_reporting.dll",
                    "baseline_job_id": "baseline-reporting",
                    "analysis_entrypoint": "upload",
                    "binary_origin": "temp_upload",
                },
                {
                    "filename": "contoso_pricing.dll",
                    "baseline_job_id": "baseline-pricing",
                    "analysis_entrypoint": "upload",
                    "binary_origin": "temp_upload",
                },
            ]
        },
        "per_dll": [
            {
                "job_id": "job-config",
                "filename": "contoso_config.dll",
                "active_frontier": True,
                "imported_lower_floor": False,
                "analysis_entrypoint": "upload",
                "binary_origin": "temp_upload",
                "runtime_path_trust": "echoed",
                "lane_trust_status": "trusted",
                "cross_dll_prior_job_ids": ["older-a"],
            },
            {
                "job_id": "job-reporting",
                "filename": "contoso_reporting.dll",
                "active_frontier": True,
                "imported_lower_floor": False,
                "analysis_entrypoint": "upload",
                "binary_origin": "temp_upload",
                "runtime_path_trust": "echoed",
                "lane_trust_status": "trusted",
                "cross_dll_prior_job_ids": ["older-b"],
            },
            {
                "job_id": "job-pricing",
                "filename": "contoso_pricing.dll",
                "active_frontier": True,
                "imported_lower_floor": False,
                "analysis_entrypoint": "upload",
                "binary_origin": "temp_upload",
                "runtime_path_trust": "echoed",
                "lane_trust_status": "trusted",
                "cross_dll_prior_job_ids": ["older-c"],
            },
            {
                "job_id": "imported-gateway",
                "filename": "contoso_gateway.dll",
                "active_frontier": False,
                "imported_lower_floor": True,
                "imported_from_job_id": "lower-gateway",
                "analysis_entrypoint": "upload",
                "binary_origin": "temp_upload",
            },
            {
                "job_id": "imported-transport",
                "filename": "contoso_transport.dll",
                "active_frontier": False,
                "imported_lower_floor": True,
                "imported_from_job_id": "lower-transport",
                "analysis_entrypoint": "upload",
                "binary_origin": "temp_upload",
            },
        ],
    }


def _sample_final_status() -> dict:
    return {
        "phase": "done",
        "dll_entries": [
            {"filename": "contoso_config.dll", "job_status": "done", "explore_phase": "done"},
            {"filename": "contoso_reporting.dll", "job_status": "done", "explore_phase": "done"},
            {"filename": "contoso_pricing.dll", "job_status": "done", "explore_phase": "done"},
        ],
    }


def test_resolve_package_floor_entry_surface_prefers_baseline_contract() -> None:
    surface = resolve_package_floor_entry_surface(
        baseline_contract=_sample_campaign_truth()["baseline_contract"],
        active_frontier_rows=list(_sample_campaign_truth()["per_dll"][:3]),
    )
    assert surface == "upload"


def test_build_package_floor_validity_gate_turns_green_for_fresh_upload_frontier() -> None:
    gate = build_package_floor_validity_gate(
        campaign_truth=_sample_campaign_truth(),
        final_status=_sample_final_status(),
    )
    assert gate["canonical_entry_surface"] == "upload"
    assert gate["claim_scope"] == "overlap_comparable_confirmation"
    assert gate["valid_for_package_floor_claim"] is True
    assert gate["valid_for_comparable_policy"] is True
    assert gate["disqualifiers"] == []


def test_build_package_floor_validity_gate_rejects_stale_replay_and_wrong_surface() -> None:
    campaign_truth = _sample_campaign_truth()
    campaign_truth["per_dll"][0]["analysis_entrypoint"] = "analyze_path"
    campaign_truth["per_dll"][1]["job_id"] = "baseline-reporting"
    gate = build_package_floor_validity_gate(
        campaign_truth=campaign_truth,
        final_status=_sample_final_status(),
    )
    assert gate["valid_for_package_floor_claim"] is False
    assert "entry_surface_mismatch" in gate["disqualifiers"]
    assert "stale_replay_reuse_detected" in gate["disqualifiers"]


def test_package_floor_gate_runner_emits_artifacts(tmp_path: Path, monkeypatch) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "reduced-batch-b-decomposition-audit.json").write_text(
        json.dumps({"active_dll_targets": ["contoso_config.dll"], "frontier_matches_expected": True}, indent=2),
        encoding="utf-8",
    )
    (run_root / "campaign-poll.json").write_text(
        json.dumps({"campaign_id": "59affa8e"}, indent=2),
        encoding="utf-8",
    )
    snapshot_dir = run_root / "snapshot" / "campaign"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "campaign-truth.json").write_text(
        json.dumps(_sample_campaign_truth(), indent=2),
        encoding="utf-8",
    )
    (run_root / "campaign-final-status.json").write_text(
        json.dumps(_sample_final_status(), indent=2),
        encoding="utf-8",
    )
    output_root = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["run_package_floor_validity_gate.py", "--run-root", str(run_root), "--output-root", str(output_root)])
    assert package_floor_gate_main() == 0
    assert (output_root / PACKAGE_FLOOR_GATE_ARTIFACT).exists()
    assert (output_root / PACKAGE_FLOOR_REPLAY_AUDIT_ARTIFACT).exists()
