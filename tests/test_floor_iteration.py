from __future__ import annotations

from types import SimpleNamespace

from api.analysis import cohesion
from api.pipeline.core.checkpoint import FunctionCheckpoint, PipelineCheckpoint
from api.pipeline.core.cluster_checkpoint import build_cluster_checkpoint_snapshot
from api.pipeline.core.floor_iteration import (
    build_floor_iteration_state,
    build_floor_plan,
    classify_package_floor_evidence,
    evaluate_floor_broadening_gate,
)
from api.pipeline import runner
from api.pipeline.core.macro_coordinator import RunVerdict, evaluate_run, persist_verdict
from api.pipeline.core.prerequisite_state_groups import build_prerequisite_state_group_snapshot
from api.routes.main import _normalize_explore_runtime_settings


def _config_checkpoint() -> PipelineCheckpoint:
    checkpoint = PipelineCheckpoint(
        job_id="job-config",
        functions={
            "CFG_OpenLicensedWindow": FunctionCheckpoint(
                name="CFG_OpenLicensedWindow",
                status="success",
                working_call={"pOutTicket": "TICK-001"},
                verified=True,
            ),
            "CFG_GetLicenseNonce": FunctionCheckpoint(
                name="CFG_GetLicenseNonce",
                status="success",
                working_call={"pOutNonce": "NONCE-001"},
                verified=True,
            ),
            "CFG_ApproveLicensedCall": FunctionCheckpoint(
                name="CFG_ApproveLicensedCall",
                status="success",
                working_call={"param_1": "TICK-001", "param_2": "NONCE-001"},
                verified=True,
            ),
        },
        cluster_checkpoints={
            row["cluster_id"]: row
            for row in build_cluster_checkpoint_snapshot(source_job_id="job-config")
        },
        prerequisite_state_groups={
            row["group_id"]: row
            for row in build_prerequisite_state_group_snapshot(source_job_id="job-config")
        },
    )
    return checkpoint


def _reporting_checkpoint() -> PipelineCheckpoint:
    return PipelineCheckpoint(
        job_id="job-reporting",
        functions={
            "RP_PrepareReservationReport": FunctionCheckpoint(
                name="RP_PrepareReservationReport",
                status="success",
                working_call={"lpszSku": "GDG-SM-RED", "pOutReportId": "RPT-CUST-004-02"},
                verified=True,
            ),
            "RP_GetReportNonce": FunctionCheckpoint(
                name="RP_GetReportNonce",
                status="success",
                working_call={"lpszReportId": "RPT-CUST-004-02", "pdwNonceOut": 3918019495},
                verified=True,
            ),
            "RP_ExportLedger": FunctionCheckpoint(
                name="RP_ExportLedger",
                status="success",
                working_call={"lpszReportId": "RPT-CUST-004-02", "dwNonce": 3918019495},
                verified=True,
            ),
            "RP_CloseReport": FunctionCheckpoint(
                name="RP_CloseReport",
                status="success",
                working_call={"lpszReportId": "RPT-CUST-004-02"},
                verified=True,
            ),
        },
        cluster_checkpoints={
            row["cluster_id"]: row
            for row in build_cluster_checkpoint_snapshot(source_job_id="job-reporting")
        },
        prerequisite_state_groups={
            row["group_id"]: row
            for row in build_prerequisite_state_group_snapshot(source_job_id="job-reporting")
        },
    )


def test_normalize_explore_runtime_settings_accepts_floor_iteration_fields() -> None:
    config = _normalize_explore_runtime_settings(
        {
            "explore_settings": {
                "iteration_mode": "floor_to_ceiling",
                "iteration_index": "2",
                "floor_scope": "composition",
                "ceiling_functions": ["CFG_RunCustomerSync"],
                "ceiling_origin_functions": ["CFG_RunCustomerSync"],
                "prerequisite_state_group_ids": ["config_licensed_ticket_bootstrap"],
                "max_iteration_cycles": "4",
            }
        }
    )

    assert config["iteration_mode"] == "floor_to_ceiling"
    assert config["iteration_index"] == 2
    assert config["floor_scope"] == "composition"
    assert config["ceiling_functions"] == ["CFG_RunCustomerSync"]
    assert config["ceiling_origin_functions"] == ["CFG_RunCustomerSync"]
    assert config["prerequisite_state_group_ids"] == ["config_licensed_ticket_bootstrap"]
    assert config["max_iteration_cycles"] == 4


def test_normalize_explore_runtime_settings_accepts_package_floor_scope() -> None:
    config = _normalize_explore_runtime_settings(
        {
            "explore_settings": {
                "iteration_mode": "floor_to_ceiling",
                "floor_scope": "package",
            }
        }
    )

    assert config["floor_scope"] == "package"


def test_classify_package_floor_evidence_distinguishes_rehearsal_vs_confirmation() -> None:
    assert classify_package_floor_evidence(
        baseline_contract_present=False,
        active_frontier_defined=True,
        imported_lower_floor_truth_recorded=True,
        comparable_profile_consistent=False,
        run_valid_green=True,
    ) == "valid_frontier_rehearsal"

    assert classify_package_floor_evidence(
        baseline_contract_present=True,
        active_frontier_defined=True,
        imported_lower_floor_truth_recorded=True,
        comparable_profile_consistent=True,
        run_valid_green=True,
    ) == "overlap_comparable_confirmation"

    assert classify_package_floor_evidence(
        baseline_contract_present=True,
        active_frontier_defined=False,
        imported_lower_floor_truth_recorded=True,
        comparable_profile_consistent=True,
        run_valid_green=True,
    ) == "non_comparable_package_run"


def test_build_floor_plan_targets_config_ceiling_and_preserves_lower_truth() -> None:
    checkpoint = _config_checkpoint()
    runtime = SimpleNamespace(
        iteration_mode="floor_to_ceiling",
        iteration_index=1,
        floor_scope="cluster",
        cluster_checkpoint_id="config_approval_license",
        prerequisite_state_group_ids=[],
        ceiling_functions=[],
        focus_functions=[],
        cross_dll_prior_job_ids=[],
    )

    plan = build_floor_plan(runtime, checkpoint)

    assert plan is not None
    assert plan.cluster_checkpoint_id == "config_approval_license"
    assert plan.prerequisite_state_group_ids == ("config_licensed_ticket_bootstrap",)
    assert plan.ceiling_functions == ("CFG_RunCustomerSync",)
    assert plan.root_ceiling_functions == ("CFG_RunCustomerSync",)
    assert "CFG_OpenLicensedWindow" in plan.preserved_lower_floor_functions
    assert "CFG_GetLicenseNonce" in plan.preserved_lower_floor_functions
    assert "CFG_ApproveLicensedCall" in plan.preserved_lower_floor_functions


def test_build_floor_plan_preserves_config_setup_truth_from_prerequisite_group() -> None:
    checkpoint = _config_checkpoint()
    runtime = SimpleNamespace(
        iteration_mode="floor_to_ceiling",
        iteration_index=1,
        floor_scope="cluster",
        cluster_checkpoint_id="config_approval_license",
        prerequisite_state_group_ids=[],
        ceiling_functions=["CFG_RunCustomerSync"],
        focus_functions=["CFG_RunCustomerSync"],
        cross_dll_prior_job_ids=[],
    )

    plan = build_floor_plan(
        runtime,
        checkpoint,
        current_findings=[
            {
                "function": "CFG_BindCustomer",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszCustId": "CUST-001"},
            }
        ],
    )

    assert plan is not None
    assert "CFG_BindCustomer" in plan.preserved_lower_floor_functions


def test_build_floor_plan_does_not_preserve_downstream_consumers_from_same_cluster() -> None:
    checkpoint = _reporting_checkpoint()
    runtime = SimpleNamespace(
        iteration_mode="floor_to_ceiling",
        iteration_index=1,
        floor_scope="cluster",
        cluster_checkpoint_id="reporting_preview_render_export",
        prerequisite_state_group_ids=[],
        ceiling_functions=["RP_SelectFormat"],
        focus_functions=["RP_SelectFormat"],
        cross_dll_prior_job_ids=[],
    )

    plan = build_floor_plan(runtime, checkpoint)

    assert plan is not None
    assert "RP_GetReportNonce" in plan.preserved_lower_floor_functions
    assert "RP_PrepareReservationReport" in plan.preserved_lower_floor_functions
    assert "RP_ExportLedger" not in plan.preserved_lower_floor_functions
    assert "RP_CloseReport" not in plan.preserved_lower_floor_functions


def test_build_floor_plan_excludes_non_reusable_bootstrap_success_from_preserved_truth() -> None:
    checkpoint = _reporting_checkpoint()
    runtime = SimpleNamespace(
        iteration_mode="floor_to_ceiling",
        iteration_index=1,
        floor_scope="cluster",
        cluster_checkpoint_id="reporting_preview_render_export",
        prerequisite_state_group_ids=[],
        ceiling_functions=["RP_SelectFormat"],
        focus_functions=["RP_SelectFormat"],
        cross_dll_prior_job_ids=[],
    )

    plan = build_floor_plan(
        runtime,
        checkpoint,
        current_findings=[
            {
                "function": "RP_PrepareReservationReport",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszSku": "GDG-SM-RED", "pOutReportId": ""},
                "reusable_truth_eligible": False,
            },
            {
                "function": "RP_GetReportNonce",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszReportId": "RPT-CUST-004-02", "pdwNonceOut": 3918019495},
                "reusable_truth_eligible": True,
            },
        ],
    )

    assert plan is not None
    assert "RP_PrepareReservationReport" not in plan.preserved_lower_floor_functions
    assert "RP_GetReportNonce" in plan.preserved_lower_floor_functions


def test_build_floor_iteration_state_shrinks_ceiling_when_target_succeeds() -> None:
    checkpoint = _config_checkpoint()
    runtime = SimpleNamespace(
        iteration_mode="floor_to_ceiling",
        iteration_index=1,
        floor_scope="cluster",
        cluster_checkpoint_id="config_approval_license",
        prerequisite_state_group_ids=[],
        ceiling_functions=[],
        focus_functions=[],
        cross_dll_prior_job_ids=[],
    )
    plan = build_floor_plan(runtime, checkpoint)

    state = build_floor_iteration_state(
        plan,
        checkpoint,
        current_findings=[
            {
                "function": "CFG_RunCustomerSync",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"param_1": "TICK-001"},
            }
        ],
    )

    assert state.status == "done"
    assert state.next_ceiling_functions == ()
    assert state.ceiling_shrank is True


def test_build_floor_iteration_state_localizes_to_first_broken_handoff() -> None:
    checkpoint = _config_checkpoint()
    runtime = SimpleNamespace(
        iteration_mode="floor_to_ceiling",
        iteration_index=1,
        floor_scope="cluster",
        cluster_checkpoint_id="config_approval_license",
        prerequisite_state_group_ids=[],
        ceiling_functions=["CFG_RunCustomerSync"],
        focus_functions=["CFG_RunCustomerSync"],
        cross_dll_prior_job_ids=[],
    )

    plan = build_floor_plan(
        runtime,
        checkpoint,
        current_findings=[
            {
                "function": "CFG_SetupEnvironment",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"dwMode": 2},
            },
            {
                "function": "CFG_BindCustomer",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszCustId": "CUST-001"},
            },
            {
                "function": "CFG_OpenLicensedWindow",
                "status": "partial",
                "status_canonical": "inferred_success",
                "working_call": {"pOutTicket": "", "dwBufLen": 64},
            }
        ],
    )
    state = build_floor_iteration_state(
        plan,
        checkpoint,
        current_findings=[
            {
                "function": "CFG_SetupEnvironment",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"dwMode": 2},
            },
            {
                "function": "CFG_BindCustomer",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszCustId": "CUST-001"},
            },
            {
                "function": "CFG_OpenLicensedWindow",
                "status": "partial",
                "status_canonical": "inferred_success",
                "working_call": {"pOutTicket": "", "dwBufLen": 64},
            }
        ],
    )

    assert state.status == "loop_again"
    assert state.localized_more is True
    assert state.next_ceiling_functions == ("CFG_OpenLicensedWindow",)
    assert state.observer_verdicts["first_broken_handoff_group"] == "config_licensed_ticket_bootstrap"


def test_build_floor_iteration_state_prefers_non_reusable_reporting_bootstrap_break() -> None:
    checkpoint = _reporting_checkpoint()
    runtime = SimpleNamespace(
        iteration_mode="floor_to_ceiling",
        iteration_index=1,
        floor_scope="cluster",
        cluster_checkpoint_id="reporting_preview_render_export",
        prerequisite_state_group_ids=[],
        ceiling_functions=["RP_SelectFormat"],
        focus_functions=["RP_SelectFormat"],
        cross_dll_prior_job_ids=[],
    )

    plan = build_floor_plan(
        runtime,
        checkpoint,
        current_findings=[
            {
                "function": "RP_PrepareReservationReport",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszSku": "GDG-SM-RED", "pOutReportId": ""},
                "reusable_truth_eligible": False,
            },
            {
                "function": "RP_GetReportNonce",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszReportId": "RPT-CUST-004-02", "pdwNonceOut": 3918019495},
                "reusable_truth_eligible": True,
            },
        ],
    )

    state = build_floor_iteration_state(
        plan,
        checkpoint,
        current_findings=[
            {
                "function": "RP_PrepareReservationReport",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszSku": "GDG-SM-RED", "pOutReportId": ""},
                "reusable_truth_eligible": False,
            },
            {
                "function": "RP_GetReportNonce",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszReportId": "RPT-CUST-004-02", "pdwNonceOut": 3918019495},
                "reusable_truth_eligible": True,
            },
        ],
    )

    assert state.status == "loop_again"
    assert state.next_ceiling_functions == ("RP_PrepareReservationReport",)
    assert state.observer_verdicts["first_broken_handoff_group"] == "reporting_report_bootstrap"
    assert state.observer_verdicts["first_broken_handoff_by_function"]["RP_PrepareReservationReport"]["layer"] == "prerequisite_state"


def test_build_floor_iteration_state_resumes_root_ceiling_after_localized_handoff_clears() -> None:
    checkpoint = _config_checkpoint()
    runtime = SimpleNamespace(
        iteration_mode="floor_to_ceiling",
        iteration_index=2,
        floor_scope="cluster",
        cluster_checkpoint_id="config_approval_license",
        prerequisite_state_group_ids=["config_licensed_ticket_bootstrap"],
        ceiling_functions=["CFG_OpenLicensedWindow"],
        ceiling_origin_functions=["CFG_RunCustomerSync"],
        focus_functions=["CFG_OpenLicensedWindow"],
        cross_dll_prior_job_ids=[],
    )

    plan = build_floor_plan(
        runtime,
        checkpoint,
        current_findings=[
            {
                "function": "CFG_SetupEnvironment",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"dwMode": 2},
            },
            {
                "function": "CFG_BindCustomer",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszCustId": "CUST-001"},
            },
            {
                "function": "CFG_OpenLicensedWindow",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"dwBufLen": 64},
            },
            {
                "function": "CFG_RunCustomerSync",
                "status": "error",
                "status_canonical": "failure",
                "working_call": None,
            },
        ],
    )

    state = build_floor_iteration_state(
        plan,
        checkpoint,
        current_findings=[
            {
                "function": "CFG_SetupEnvironment",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"dwMode": 2},
            },
            {
                "function": "CFG_BindCustomer",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszCustId": "CUST-001"},
            },
            {
                "function": "CFG_OpenLicensedWindow",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"dwBufLen": 64},
            },
            {
                "function": "CFG_RunCustomerSync",
                "status": "error",
                "status_canonical": "failure",
                "working_call": None,
            },
        ],
    )

    assert state.status == "loop_again"
    assert state.next_ceiling_functions == ("CFG_RunCustomerSync",)
    assert state.next_cycle_recommendation["status"] == "resume_root_ceiling"
    assert state.next_cycle_recommendation["ceiling_origin_functions"] == ["CFG_RunCustomerSync"]


def test_evaluate_floor_broadening_gate_blocks_when_prerequisite_group_is_not_green() -> None:
    checkpoint = _config_checkpoint()
    runtime = SimpleNamespace(
        iteration_mode="floor_to_ceiling",
        iteration_index=1,
        floor_scope="cluster",
        cluster_checkpoint_id="config_approval_license",
        prerequisite_state_group_ids=[],
        ceiling_functions=["CFG_RunCustomerSync"],
        focus_functions=["CFG_RunCustomerSync"],
        cross_dll_prior_job_ids=[],
    )

    plan = build_floor_plan(
        runtime,
        checkpoint,
        current_findings=[
            {
                "function": "CFG_OpenLicensedWindow",
                "status": "partial",
                "status_canonical": "inferred_success",
                "working_call": {"pOutTicket": "", "dwBufLen": 64},
            }
        ],
    )
    gate = evaluate_floor_broadening_gate(
        plan,
        checkpoint,
        current_findings=[
            {
                "function": "CFG_OpenLicensedWindow",
                "status": "partial",
                "status_canonical": "inferred_success",
                "working_call": {"pOutTicket": "", "dwBufLen": 64},
            }
        ],
    )

    assert gate["allow_broadening"] is False
    assert gate["reason"] == "prerequisite_state_groups_untrusted"
    assert gate["blocked_groups"] == ["config_licensed_ticket_bootstrap"]


def test_macro_coordinator_uses_floor_iteration_state(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.infra.storage._load_findings",
        lambda _job_id: [
            {"function": "CFG_RunCustomerSync", "status": "error"},
        ],
    )
    monkeypatch.setattr("api.infra.storage._get_job_status", lambda _job_id: {})
    ctx = SimpleNamespace(
        job_id="job-1",
        floor_iteration_state=SimpleNamespace(
            status="loop_again",
            iteration_index=2,
            floor_scope="cluster",
            previous_ceiling_functions=("CFG_ApproveLicensedCall", "CFG_RunCustomerSync"),
            next_ceiling_functions=("CFG_RunCustomerSync",),
            reopened_functions=(),
            carryover_status="warn",
            ceiling_shrank=True,
            localized_more=True,
            next_cycle_recommendation={
                "focus_functions": ["CFG_RunCustomerSync"],
                "skip_to_stage": "s02_probe",
                "skip_to_stage_reason": "floor_to_ceiling_iteration",
                "floor_scope": "cluster",
            },
        ),
    )

    verdict = evaluate_run(ctx)

    assert verdict.status == "loop_again"
    assert verdict.floor_verdict["ceiling_shrank"] is True
    assert verdict.strategy_adjustments["focus_functions"] == ["CFG_RunCustomerSync"]


def test_macro_verdict_persistence_does_not_touch_job_status(monkeypatch) -> None:
    uploads: dict[str, bytes] = {}

    def fake_upload(_container: str, name: str, data: bytes) -> None:
        uploads[name] = data

    def fail_status_access(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("macro verdict persistence must not touch job status")

    monkeypatch.setattr("api.infra.storage._upload_to_blob", fake_upload)
    monkeypatch.setattr("api.infra.storage._get_job_status", fail_status_access)
    monkeypatch.setattr("api.infra.storage._persist_job_status", fail_status_access)

    persist_verdict(
        SimpleNamespace(job_id="job-1"),
        RunVerdict(status="done", coverage_pct=100.0, verified_count=1, total_count=1),
    )

    assert "job-1/macro_verdict.json" in uploads


def test_emit_contract_artifacts_includes_floor_iteration_surface(monkeypatch) -> None:
    uploads: dict[str, bytes] = {}
    monkeypatch.setattr(
        cohesion,
        "_get_job_status",
        lambda _job_id: {
            "component_name": "contoso_config",
            "explore_phase": "done",
            "created_at": 0,
            "updated_at": 1,
            "explore_runtime": {},
        },
    )
    monkeypatch.setattr(
        cohesion,
        "_load_findings",
        lambda _job_id: [
            {"function": "CFG_OpenLicensedWindow", "status": "success", "working_call": {"pOutTicket": "TICK-001"}},
            {"function": "CFG_RunCustomerSync", "status": "error"},
        ],
    )
    monkeypatch.setattr(
        cohesion,
        "_try_json",
        lambda _job_id, blob_name: {
            "explore_config.json": {
                "iteration_mode": "floor_to_ceiling",
                "floor_scope": "cluster",
            },
            "floor_plan.json": {
                "floor_scope": "cluster",
                "cluster_checkpoint_id": "config_approval_license",
                "prerequisite_state_group_ids": ["config_licensed_ticket_bootstrap"],
                "ceiling_functions": ["CFG_RunCustomerSync"],
                "preserved_lower_floor_functions": ["CFG_OpenLicensedWindow"],
                "ceiling_dependency_map": {"CFG_RunCustomerSync": ["config_licensed_ticket_bootstrap"]},
            },
            "floor_iteration_state.json": {
                "previous_ceiling_functions": ["CFG_RunCustomerSync"],
                "next_ceiling_functions": ["CFG_RunCustomerSync"],
                "reopened_functions": [],
                "ceiling_shrank": False,
                "localized_more": True,
                "carryover_status": "warn",
            },
        }.get(blob_name, {}),
    )
    monkeypatch.setattr(cohesion, "_try_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cohesion, "_upload_to_blob", lambda _c, path, data: uploads.setdefault(path, data))

    report = cohesion.emit_contract_artifacts("job-floor")

    floor = report["cohesion_report"]["floor_iteration"]
    assert floor["iteration_mode"] == "floor_to_ceiling"
    assert floor["cluster_checkpoint_id"] == "config_approval_license"
    assert floor["prerequisite_state_group_ids"] == ["config_licensed_ticket_bootstrap"]
    assert floor["ceiling_dependency_map"]["CFG_RunCustomerSync"] == ["config_licensed_ticket_bootstrap"]


def test_persist_floor_iteration_artifacts_emits_contract_field_names(monkeypatch) -> None:
    uploads: dict[str, dict] = {}

    monkeypatch.setattr(
        runner,
        "_upload_to_blob",
        lambda _container, path, data: uploads.setdefault(path, __import__("json").loads(data.decode("utf-8"))),
    )

    checkpoint = _config_checkpoint()
    runtime = SimpleNamespace(
        iteration_mode="floor_to_ceiling",
        iteration_index=1,
        floor_scope="cluster",
        cluster_checkpoint_id="config_approval_license",
        prerequisite_state_group_ids=[],
        ceiling_functions=["CFG_RunCustomerSync"],
        focus_functions=["CFG_RunCustomerSync"],
        cross_dll_prior_job_ids=[],
    )
    plan = build_floor_plan(runtime, checkpoint)
    state = build_floor_iteration_state(
        plan,
        checkpoint,
        current_findings=[
            {
                "function": "CFG_SetupEnvironment",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"dwMode": 2},
            },
            {
                "function": "CFG_BindCustomer",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"lpszCustId": "CUST-001"},
            },
            {
                "function": "CFG_OpenLicensedWindow",
                "status": "partial",
                "status_canonical": "inferred_success",
                "working_call": {"pOutTicket": "", "dwBufLen": 64},
            }
        ],
    )

    runner._persist_floor_iteration_artifacts("job-floor-artifacts", plan, state)

    frontier = uploads["job-floor-artifacts/ceiling_frontier.json"]
    assert frontier["current_ceiling_functions"] == ["CFG_RunCustomerSync"]
    assert frontier["next_ceiling_functions"] == ["CFG_OpenLicensedWindow"]
    assert "preserved_lower_floor_functions" in frontier
    assert "reopened_preserved_functions" in frontier
    assert "ceiling_dependency_map" in frontier
