from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path


def test_choose_external_targets_prefers_core_over_noise():
    from scripts.runs.run_blocker_harvest_waves import choose_external_targets

    dlls = [
        Path("MCIcons.dll"),
        Path("DriverDll.dll"),
        Path("ClientTool.dll"),
    ]
    chosen = [path.name for path in choose_external_targets(dlls, limit=2)]

    assert "DriverDll.dll" in chosen
    assert "ClientTool.dll" in chosen
    assert "MCIcons.dll" not in chosen


def test_build_external_manifest_limits_targets_and_tracks_deferred(tmp_path: Path):
    from scripts.runs.run_blocker_harvest_waves import build_external_manifest

    for name in ("DriverDll.dll", "ClientTool.dll", "KMSCNSET.dll", "NoiseHelper.dll"):
        (tmp_path / name).write_bytes(b"stub")

    manifest = build_external_manifest(tmp_path)

    assert manifest["package_id"].startswith("external-")
    assert len(manifest["selected_runtime_targets"]) == 3
    assert "NoiseHelper.dll" in manifest["deferred_dlls"]


def test_decide_wave_verdict_blocks_measurement_and_plateau():
    from scripts.runs.run_blocker_harvest_waves import decide_wave_verdict

    measurement_summary = {
        "dominant_blocker_families": [{"family": "measurement", "dll_count": 4}],
        "lane_gate_status": "trusted",
        "runtime_path_mismatch_count": 0,
        "ledger_missing_count": 0,
        "package_summary_legible": True,
        "new_primary_families": [],
        "stable_primary_families": [],
        "trustworthy_for_architecture_count": 4,
        "measured_dlls": 4,
        "blocker_classified_ratio": 1.0,
    }
    verdict, streak = decide_wave_verdict(summary=measurement_summary, previous_summary={"wave_id": "wave-0"}, no_signal_streak=0)
    assert verdict["verdict"] == "harden trust/measurement"
    assert streak == 1

    plateau_summary = {
        "dominant_blocker_families": [{"family": "struct/payload shaping", "dll_count": 2}],
        "lane_gate_status": "trusted",
        "runtime_path_mismatch_count": 0,
        "ledger_missing_count": 0,
        "package_summary_legible": True,
        "new_primary_families": [],
        "stable_primary_families": ["struct/payload shaping"],
        "trustworthy_for_architecture_count": 4,
        "measured_dlls": 4,
        "blocker_classified_ratio": 1.0,
    }
    verdict, streak = decide_wave_verdict(summary=plateau_summary, previous_summary={"wave_id": "wave-1"}, no_signal_streak=1)
    assert verdict["verdict"] == "stop and roadblock"
    assert "two_consecutive_no_signal_rounds" in verdict["stop_reasons"]
    assert streak == 2


def test_poll_campaign_retries_transient_disconnect(monkeypatch, tmp_path: Path):
    import requests

    from scripts.runs.run_blocker_harvest_waves import poll_campaign

    class FakeSession:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise requests.ConnectionError("transient disconnect")
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {"campaign_id": "camp-1", "phase": "done"},
            )

    monkeypatch.setattr("scripts.runs.run_blocker_harvest_waves.time.sleep", lambda _seconds: None)

    payload = poll_campaign(FakeSession(), "http://127.0.0.1:8201", "", "camp-1", tmp_path)

    assert payload["phase"] == "done"
    assert (tmp_path / "campaign-poll-errors.json").exists()


def test_choose_control_slice_primary_family_uses_architectural_priority():
    from scripts.runs.run_blocker_harvest_waves import choose_control_slice_primary_family

    family = choose_control_slice_primary_family(
        [
            {"family": "discovery opacity", "dll_count": 1},
            {"family": "opaque handle routing", "dll_count": 1},
            {"family": "sequencing/state machine", "dll_count": 1},
        ]
    )

    assert family == "opaque handle routing"


def test_decide_wave_verdict_does_not_treat_mixed_tie_as_measurement():
    from scripts.runs.run_blocker_harvest_waves import decide_wave_verdict

    summary = {
        "dominant_blocker_families": [
            {"family": "discovery opacity", "dll_count": 1},
            {"family": "opaque handle routing", "dll_count": 1},
        ],
        "lane_gate_status": "trusted",
        "runtime_path_mismatch_count": 0,
        "ledger_missing_count": 0,
        "package_summary_legible": True,
        "new_primary_families": ["opaque handle routing"],
        "stable_primary_families": [],
        "trustworthy_for_architecture_count": 4,
        "measured_dlls": 4,
        "blocker_classified_ratio": 1.0,
    }

    verdict, _streak = decide_wave_verdict(summary=summary, previous_summary=None, no_signal_streak=0)

    assert verdict["verdict"] == "expand"


def test_control_slice_decision_requires_bounded_tranche_before_wave_2():
    from scripts.runs.run_blocker_harvest_waves import build_control_slice_decision

    summary = {
        "wave_id": "wave-1",
        "campaign_id": "camp-1",
        "package_id": "pkg-1",
        "package_label": "Pkg",
        "dominant_blocker_families": [
            {"family": "discovery opacity", "dll_count": 1},
            {"family": "opaque handle routing", "dll_count": 1},
        ],
        "secondary_blocker_families": [],
        "candidate_next_systems": [{"system": "discovery opacity augmenter", "count": 1}],
        "lane_gate_status": "trusted",
        "trustworthy_for_architecture_count": 4,
        "measured_dlls": 4,
        "blocker_classified_ratio": 1.0,
        "attribution_summary": {
            "architect_summary": {
                "leading_candidate_system": "generalized runtime artifact materializer",
            }
        },
    }
    verdict = {"verdict": "expand", "architecture_signal": "strengthens", "stop_reasons": []}

    decision = build_control_slice_decision(summary, verdict)

    assert decision["dominant_blocker_family"] == "opaque handle routing"
    assert decision["candidate_next_system"] == "generalized runtime artifact materializer"
    assert decision["bounded_tranche_required"] is True
    assert decision["wave_2_allowed"] is False
    assert decision["next_step_verdict"] == "build bounded system"


def test_control_slice_decision_allows_wave_2_after_successful_reproof():
    from scripts.runs.run_blocker_harvest_waves import build_control_slice_decision

    summary = {
        "wave_id": "wave-1",
        "campaign_id": "camp-2",
        "package_id": "pkg-1",
        "package_label": "Pkg",
        "dominant_blocker_families": [
            {"family": "sequencing/state machine", "dll_count": 1},
            {"family": "discovery opacity", "dll_count": 1},
        ],
        "secondary_blocker_families": [],
        "candidate_next_systems": [{"system": "discovery opacity augmenter", "count": 1}],
        "lane_gate_status": "trusted",
        "trustworthy_for_architecture_count": 4,
        "measured_dlls": 4,
        "blocker_classified_ratio": 0.75,
        "control_slice_reproved_after_system": True,
        "attribution_summary": {
            "architect_summary": {
                "leading_candidate_system": "discovery opacity augmenter",
            }
        },
    }
    verdict = {"verdict": "expand", "architecture_signal": "leaves_unchanged", "stop_reasons": []}

    decision = build_control_slice_decision(summary, verdict)

    assert decision["candidate_next_system"] == "prerequisite and state-machine classifier"
    assert decision["wave_2_allowed"] is True
    assert decision["next_step_verdict"] == "expand"


def test_decide_wave_verdict_allows_improved_reproof_without_blocker_ratio_gate():
    from scripts.runs.run_blocker_harvest_waves import decide_wave_verdict

    summary = {
        "dominant_blocker_families": [
            {"family": "discovery opacity", "dll_count": 1},
            {"family": "sequencing/state machine", "dll_count": 1},
        ],
        "lane_gate_status": "trusted",
        "runtime_path_mismatch_count": 0,
        "ledger_missing_count": 0,
        "package_summary_legible": True,
        "new_primary_families": [],
        "stable_primary_families": ["discovery opacity", "sequencing/state machine"],
        "trustworthy_for_architecture_count": 4,
        "measured_dlls": 4,
        "blocker_classified_ratio": 0.75,
        "control_slice_reproved_after_system": True,
        "verified_delta": 4,
    }

    verdict, streak = decide_wave_verdict(summary=summary, previous_summary={"wave_id": "wave-1"}, no_signal_streak=0)

    assert verdict["verdict"] == "expand"
    assert streak == 1


def test_build_wave_expansion_baseline_contract_uses_overlap_and_marks_new_targets():
    from scripts.runs.run_blocker_harvest_waves import build_wave_expansion_baseline_contract

    previous_summary = {
        "wave_id": "wave-2-batch-a",
        "campaign_id": "camp-a",
        "runtime_targets": [
            "contoso_config.dll",
            "contoso_workflow.dll",
            "contoso_gateway.dll",
        ],
        "cohesion_summary": {
            "graph_epoch": "epoch-a",
            "seeding_mode": "cross_dll_prior",
        },
        "attribution_summary": {
            "per_dll": [
                {
                    "component": "contoso_config",
                    "dll_id": "cfg",
                    "filename": "contoso_config.dll",
                    "job_id": "job-cfg",
                    "verified_count": 12,
                    "total_functions": 12,
                    "analysis_entrypoint": "upload",
                    "binary_origin": "temp_upload",
                    "analysis_profile": "strict_dll",
                    "cache_state": "warm",
                    "graph_epoch": "epoch-a",
                    "lane_id": "lane-1",
                },
                {
                    "component": "contoso_workflow",
                    "dll_id": "wf",
                    "filename": "contoso_workflow.dll",
                    "job_id": "job-wf",
                    "verified_count": 12,
                    "total_functions": 12,
                    "analysis_entrypoint": "upload",
                    "binary_origin": "temp_upload",
                    "analysis_profile": "strict_dll",
                    "cache_state": "warm",
                    "graph_epoch": "epoch-a",
                    "lane_id": "lane-1",
                },
            ]
        },
    }

    contract = build_wave_expansion_baseline_contract(
        wave_id="wave-2-batch-b",
        previous_summary=previous_summary,
        runtime_targets=[
            "contoso_config.dll",
            "contoso_workflow.dll",
            "contoso_events.dll",
        ],
    )

    assert contract["source_wave_id"] == "wave-2-batch-a"
    assert contract["baseline_graph_epoch"] == "epoch-a"
    assert contract["baseline_seeding_mode"] == "cross_dll_prior"
    assert contract["overlap_dll_set"] == ["contoso_config.dll", "contoso_workflow.dll"]
    assert contract["no_baseline_required_dlls"] == ["contoso_events.dll"]
    assert {entry["baseline_job_id"] for entry in contract["dll_entries"]} == {"job-cfg", "job-wf"}


def test_decide_wave_verdict_blocks_expansion_when_overlap_not_comparable():
    from scripts.runs.run_blocker_harvest_waves import decide_wave_verdict

    summary = {
        "dominant_blocker_families": [{"family": "callback/flag-space", "dll_count": 1}],
        "lane_gate_status": "trusted",
        "runtime_path_mismatch_count": 0,
        "ledger_missing_count": 0,
        "package_summary_legible": True,
        "package_internal_truth_ready": True,
        "package_floor_evidence_class": "valid_frontier_rehearsal",
        "baseline_contract_present": True,
        "overlap_baseline_comparable": False,
        "overlap_regression_summary": [],
        "new_primary_families": ["callback/flag-space"],
        "stable_primary_families": [],
        "trustworthy_for_architecture_count": 8,
        "measured_dlls": 8,
        "blocker_classified_ratio": 1.0,
    }

    verdict, _streak = decide_wave_verdict(summary=summary, previous_summary={"wave_id": "wave-2-batch-a"}, no_signal_streak=0)

    assert verdict["verdict"] == "stop and roadblock"
    assert "overlap_baseline_not_comparable" in verdict["stop_reasons"]


def test_decide_wave_verdict_blocks_expansion_when_overlap_regressions_remain():
    from scripts.runs.run_blocker_harvest_waves import decide_wave_verdict

    summary = {
        "dominant_blocker_families": [{"family": "callback/flag-space", "dll_count": 1}],
        "lane_gate_status": "trusted",
        "runtime_path_mismatch_count": 0,
        "ledger_missing_count": 0,
        "package_summary_legible": True,
        "package_internal_truth_ready": True,
        "package_floor_evidence_class": "overlap_comparable_confirmation",
        "baseline_contract_present": True,
        "overlap_baseline_comparable": True,
        "overlap_regression_summary": [{"dll": "contoso_workflow.dll", "function": "WF_GetWorkflowState"}],
        "new_primary_families": ["callback/flag-space"],
        "stable_primary_families": [],
        "trustworthy_for_architecture_count": 8,
        "measured_dlls": 8,
        "blocker_classified_ratio": 1.0,
    }

    verdict, _streak = decide_wave_verdict(summary=summary, previous_summary={"wave_id": "wave-2-batch-a"}, no_signal_streak=0)

    assert verdict["verdict"] == "stop and roadblock"
    assert "overlap_regressions_remain" in verdict["stop_reasons"]
