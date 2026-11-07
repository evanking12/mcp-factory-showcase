from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.pipeline.core.config_frontier_environment_gate import (  # noqa: E402
    BASELINE_DELTA_ARTIFACT,
    COMPARISON_NOTE_ARTIFACT,
    ENV_ASSUMPTION_ARTIFACT,
    FAILURE_CLUSTER_ARTIFACT,
    FRONTIER_SEAM_AUDIT_ARTIFACT,
    LINEAGE_HANDOFF_ARTIFACT,
    MINIMAL_REPRODUCER_ARTIFACT,
    PROMPT_25_NOTE_ARTIFACT,
    SURVIVOR_MAP_ARTIFACT,
    TRUST_SEPARATION_ARTIFACT,
    build_config_env_assumption_surface_audit,
    build_config_failure_cluster_shape_audit,
    build_config_frontier_baseline_delta_map,
    build_config_prerequisite_lineage_handoff_audit,
)
from scripts.runs.run_config_frontier_environment_gate import main as config_prompt_24_main  # noqa: E402


def _sample_campaign_truth() -> dict:
    return {
        "campaign_id": "46fe7b2f",
        "package_internal_truth_ready": True,
        "baseline_contract": {
            "entries": [
                {
                    "filename": "contoso_config.dll",
                    "baseline_job_id": "baseline-config",
                    "baseline_verified_count": 12,
                    "baseline_total_functions": 12,
                    "analysis_entrypoint": "upload",
                    "binary_origin": "temp_upload",
                }
            ]
        },
        "per_dll": [
            {
                "filename": "contoso_config.dll",
                "job_id": "job-config",
                "verified_count": 9,
                "total_functions": 12,
                "analysis_entrypoint": "upload",
                "binary_origin": "temp_upload",
                "lane_trust_status": "trusted",
                "runtime_path_trust": "echoed",
                "blocker_family_primary": "environment gating",
                "candidate_next_system": "environment dependency classifier",
            },
            {
                "filename": "contoso_reporting.dll",
                "job_id": "job-reporting",
                "verified_count": 9,
                "total_functions": 12,
                "analysis_entrypoint": "upload",
                "binary_origin": "temp_upload",
                "lane_trust_status": "trusted",
                "runtime_path_trust": "echoed",
                "blocker_family_primary": "opaque handle routing",
                "candidate_next_system": "generalized runtime artifact materializer",
                "active_frontier": True,
            },
        ],
    }


def _sample_findings() -> list[dict]:
    return [
        {
            "function": "CFG_SetupEnvironment",
            "status_canonical": "verified_success",
            "working_call": {"dwMode": 2},
            "reusable_truth_eligible": True,
            "direct_target_truth": {"phase": "structured_preflight_prereq"},
        },
        {
            "function": "CFG_Initialize",
            "status_canonical": "verified_success",
            "working_call": {"param_1": "GDG-SM-RED", "handle": 4294962295},
            "reusable_truth_eligible": True,
            "direct_target_truth": {"phase": "structured_preflight_prereq"},
        },
        {
            "function": "CFG_BindCustomer",
            "status_canonical": "verified_success",
            "working_call": {"lpszCustId": "CUST-001"},
            "reusable_truth_eligible": True,
            "direct_target_truth": {"phase": "structured_preflight_prereq"},
        },
        {
            "function": "CFG_OpenLicensedWindow",
            "status_canonical": "verified_success",
            "working_call": {"dwBufLen": 64, "pOutTicket": ""},
            "reusable_truth_eligible": False,
            "reusable_truth_reasons": ["pOutTicket_expected_ticket"],
            "direct_target_truth": {"phase": "lineage_preflight"},
        },
        {
            "function": "CFG_ApproveLicensedCall",
            "status_canonical": "failure",
            "finding": "All 9 probes returned sentinel codes: 4294962292. No working call found.",
        },
        {
            "function": "CFG_GetLicenseNonce",
            "status_canonical": "failure",
            "finding": "All 8 probes returned sentinel codes: 4294962292. No working call found.",
        },
        {
            "function": "CFG_RunCustomerSync",
            "status_canonical": "failure",
            "finding": "All 8 probes returned sentinel codes: 4294962292, 4294962293. No working call found.",
        },
    ]


def _sample_blocker_classification() -> dict:
    return {
        "primary_blocker_family": "environment gating",
        "unresolved_function_count": 3,
        "function_rows": [
            {"function": "CFG_ApproveLicensedCall", "blocker_family": "environment gating", "first_blocking_stage": "s02_probe"},
            {"function": "CFG_GetLicenseNonce", "blocker_family": "environment gating", "first_blocking_stage": "s02_probe"},
            {"function": "CFG_RunCustomerSync", "blocker_family": "environment gating", "first_blocking_stage": "s02_probe"},
        ],
    }


def _sample_verification_report() -> dict:
    return {
        "entries": [
            {
                "function": "CFG_GetConfigState",
                "verification": "verified",
                "args": {"dwBufLen": 64, "pOutBuf": "", "mode": "licensed|cust=CUST-001|approved=0"},
                "prerequisite_chain": [
                    {"function": "CFG_Initialize"},
                    {"function": "CFG_SetupEnvironment"},
                    {"function": "CFG_Initialize"},
                    {"function": "CFG_BindCustomer"},
                    {"function": "CFG_OpenLicensedWindow"},
                    {"function": "CFG_GetLicenseNonce"},
                    {"function": "CFG_ApproveLicensedCall"},
                ],
            }
        ]
    }


def _sample_prerequisite_state_machine() -> dict:
    return {
        "roles": [
            {"name": "CFG_SetupEnvironment", "sequence_role": "gate", "prerequisites": [], "input_kinds": ["integer"], "output_kinds": []},
            {"name": "CFG_Initialize", "sequence_role": "gate", "prerequisites": ["CFG_SetupEnvironment"], "input_kinds": [], "output_kinds": []},
            {"name": "CFG_BindCustomer", "sequence_role": "lifecycle_transition", "prerequisites": ["CFG_Initialize", "CFG_SetupEnvironment"], "input_kinds": ["customer_id"], "output_kinds": []},
            {"name": "CFG_OpenLicensedWindow", "sequence_role": "lifecycle_transition", "prerequisites": ["CFG_BindCustomer"], "input_kinds": ["ticket"], "output_kinds": []},
            {"name": "CFG_GetLicenseNonce", "sequence_role": "state_consumer", "prerequisites": ["CFG_OpenLicensedWindow", "CFG_BindCustomer"], "input_kinds": ["ticket"], "output_kinds": ["nonce"]},
            {"name": "CFG_ApproveLicensedCall", "sequence_role": "lifecycle_transition", "prerequisites": ["CFG_GetLicenseNonce"], "input_kinds": ["ticket", "nonce"], "output_kinds": []},
            {"name": "CFG_RunCustomerSync", "sequence_role": "gate", "prerequisites": ["CFG_ApproveLicensedCall"], "input_kinds": ["ticket"], "output_kinds": []},
        ]
    }


def _sample_probe_stop_reasons() -> list[dict]:
    return [
        {"function": "CFG_ApproveLicensedCall", "stop_reason": "cap_hit_tool_calls", "tool_calls_used": 9, "rounds_used": 0},
        {"function": "CFG_GetLicenseNonce", "stop_reason": "cap_hit_tool_calls", "tool_calls_used": 8, "rounds_used": 0},
        {"function": "CFG_RunCustomerSync", "stop_reason": "cap_hit_tool_calls", "tool_calls_used": 8, "rounds_used": 2},
    ]


def test_lineage_handoff_audit_narrows_blocker_family() -> None:
    audit = build_config_prerequisite_lineage_handoff_audit(
        findings=_sample_findings(),
        verification_report=_sample_verification_report(),
        prerequisite_state_machine=_sample_prerequisite_state_machine(),
        blocker_classification=_sample_blocker_classification(),
    )
    assert audit["broad_environment_gate_supported"] is False
    assert audit["narrowed_blocker_family"] == "lineage artifact materialization"
    assert audit["narrow_proof_green"] is True


def test_baseline_delta_and_env_audit_reflect_live_gap_shape() -> None:
    baseline = build_config_frontier_baseline_delta_map(
        campaign_truth=_sample_campaign_truth(),
        blocker_classification=_sample_blocker_classification(),
    )
    env_audit = build_config_env_assumption_surface_audit(
        findings=_sample_findings(),
        prerequisite_state_machine=_sample_prerequisite_state_machine(),
    )
    assert baseline["verified_delta"] == -3
    assert baseline["unresolved_functions"] == [
        "CFG_ApproveLicensedCall",
        "CFG_GetLicenseNonce",
        "CFG_RunCustomerSync",
    ]
    assert env_audit["supports_lineage_specific_gate"] is True


def test_failure_cluster_audit_groups_same_s02_probe_blocker() -> None:
    audit = build_config_failure_cluster_shape_audit(
        findings=_sample_findings(),
        blocker_classification=_sample_blocker_classification(),
        probe_stop_reasons=_sample_probe_stop_reasons(),
    )
    assert audit["supports_single_family_blocker"] is True
    assert audit["shared_first_blocking_stages"] == ["s02_probe"]
    assert "4294962292" in audit["shared_sentinel_markers"]


def test_prompt_24_runner_emits_prompt_25_note_and_artifacts(tmp_path: Path, monkeypatch) -> None:
    run_root = tmp_path / "run"
    dll_root = run_root / "snapshot" / "dlls" / "contoso_config.dll"
    dll_root.mkdir(parents=True, exist_ok=True)
    (run_root / "snapshot" / "campaign").mkdir(parents=True, exist_ok=True)
    (run_root / "snapshot" / "campaign" / "campaign-truth.json").write_text(
        json.dumps(_sample_campaign_truth(), indent=2),
        encoding="utf-8",
    )
    (dll_root / "findings.json").write_text(json.dumps(_sample_findings(), indent=2), encoding="utf-8")
    (dll_root / "blocker-classification.json").write_text(
        json.dumps(_sample_blocker_classification(), indent=2),
        encoding="utf-8",
    )
    (dll_root / "verification-report.json").write_text(
        json.dumps(_sample_verification_report(), indent=2),
        encoding="utf-8",
    )
    (dll_root / "prerequisite_state_machine.json").write_text(
        json.dumps(_sample_prerequisite_state_machine(), indent=2),
        encoding="utf-8",
    )
    stage02 = dll_root / "evidence" / "stage-02-probe-loop"
    stage02.mkdir(parents=True, exist_ok=True)
    (stage02 / "probe-stop-reasons.json").write_text(
        json.dumps(_sample_probe_stop_reasons(), indent=2),
        encoding="utf-8",
    )
    (stage02 / "probe-strategy-summary.json").write_text(json.dumps([], indent=2), encoding="utf-8")
    out_root = tmp_path / "out"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_config_frontier_environment_gate.py",
            "--run-root",
            str(run_root),
            "--output-root",
            str(out_root),
            "--skip-live-rerun",
        ],
    )
    assert config_prompt_24_main() == 0
    for filename in (
        BASELINE_DELTA_ARTIFACT,
        LINEAGE_HANDOFF_ARTIFACT,
        SURVIVOR_MAP_ARTIFACT,
        FAILURE_CLUSTER_ARTIFACT,
        ENV_ASSUMPTION_ARTIFACT,
        TRUST_SEPARATION_ARTIFACT,
        MINIMAL_REPRODUCER_ARTIFACT,
        FRONTIER_SEAM_AUDIT_ARTIFACT,
        COMPARISON_NOTE_ARTIFACT,
        PROMPT_25_NOTE_ARTIFACT,
    ):
        assert (out_root / filename).exists()
    note = (out_root / PROMPT_25_NOTE_ARTIFACT).read_text(encoding="utf-8")
    assert "24a Config Frontier Baseline Delta Map" in note
    assert "24n Config Minimal Reproducer Extraction" in note
    prompt_path = REPO_ROOT / "docs" / "architecture" / "engineScaling" / "engineScaling_DesignSuite" / "engineScaling_DesignSuitePrompts" / "25-config-lineage-materialization-repair.md"
    assert prompt_path.exists()
