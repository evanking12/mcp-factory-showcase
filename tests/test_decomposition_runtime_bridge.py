from api.pipeline.core.decomposition_runtime_bridge import build_decomposition_campaign_plan
from api.pipeline.core.package_frontier_planner import build_package_frontier_plan


def _wave_summary() -> dict:
    return {
        "wave_id": "wave-2-batch-b",
        "campaign_id": "camp-b",
        "package_id": "contoso-business-suite",
        "package_label": "Contoso Business Suite",
        "runtime_targets": [
            "contoso_config.dll",
            "contoso_reporting.dll",
            "contoso_pricing.dll",
            "contoso_workflow.dll",
            "contoso_gateway.dll",
        ],
        "cohesion_summary": {
            "per_dll": [
                {"filename": "contoso_config.dll", "job_id": "job-config", "component": "contoso_config", "verified_count": 11, "total_functions": 12},
                {"filename": "contoso_reporting.dll", "job_id": "job-reporting", "component": "contoso_reporting", "verified_count": 10, "total_functions": 12},
                {"filename": "contoso_pricing.dll", "job_id": "job-pricing", "component": "contoso_pricing", "verified_count": 10, "total_functions": 12},
                {"filename": "contoso_workflow.dll", "job_id": "job-workflow", "component": "contoso_workflow", "verified_count": 12, "total_functions": 12},
                {"filename": "contoso_gateway.dll", "job_id": "job-gateway", "component": "contoso_gateway", "verified_count": 12, "total_functions": 12},
            ]
        },
        "attribution_summary": {
            "baseline_contract": {
                "source_wave_id": "wave-2-batch-a",
                "overlap_dll_set": [
                    "contoso_config.dll",
                    "contoso_reporting.dll",
                    "contoso_pricing.dll",
                ],
                "dll_entries": [
                    {"filename": "contoso_config.dll", "dll_id": "cfg", "component": "contoso_config", "baseline_job_id": "job-config-base"},
                    {"filename": "contoso_reporting.dll", "dll_id": "rpt", "component": "contoso_reporting", "baseline_job_id": "job-reporting-base"},
                    {"filename": "contoso_pricing.dll", "dll_id": "prc", "component": "contoso_pricing", "baseline_job_id": "job-pricing-base"},
                ],
            },
            "per_dll": [
                {"filename": "contoso_config.dll", "component": "contoso_config"},
                {"filename": "contoso_reporting.dll", "component": "contoso_reporting"},
                {"filename": "contoso_pricing.dll", "component": "contoso_pricing"},
                {"filename": "contoso_workflow.dll", "component": "contoso_workflow"},
                {"filename": "contoso_gateway.dll", "component": "contoso_gateway"},
            ],
        },
        "overlap_regression_summary": [
            {"dll": "contoso_config.dll", "function": "CFG_RunCustomerSync", "likely_regression_cause": "unknown", "follow_up_class": "immediate_follow_up"},
            {"dll": "contoso_reporting.dll", "function": "RP_SelectFormat", "likely_regression_cause": "unknown", "follow_up_class": "immediate_follow_up"},
            {"dll": "contoso_pricing.dll", "function": "PR_ApplyBundleOverride", "likely_regression_cause": "unknown", "follow_up_class": "immediate_follow_up"},
        ],
    }


def _campaign_input() -> dict:
    return {
        "package_id": "contoso-business-suite",
        "package_label": "Contoso Business Suite",
        "graph_epoch": "camp-b",
        "dll_entries": [
            {"dll_id": "cfg", "filename": "contoso_config.dll", "job_id": "job-config"},
            {"dll_id": "rpt", "filename": "contoso_reporting.dll", "job_id": "job-reporting"},
            {"dll_id": "prc", "filename": "contoso_pricing.dll", "job_id": "job-pricing"},
            {"dll_id": "wf", "filename": "contoso_workflow.dll", "job_id": "job-workflow"},
            {"dll_id": "gtw", "filename": "contoso_gateway.dll", "job_id": "job-gateway"},
        ],
    }


def test_build_decomposition_campaign_plan_preserves_frontier_and_imported_truth() -> None:
    package_frontier_plan = build_package_frontier_plan(_wave_summary())

    result = build_decomposition_campaign_plan(
        _campaign_input(),
        package_frontier_plan,
        target_shard_width=2,
        max_slice_dlls=3,
    )

    assert result["active_frontier_dlls"] == [
        "contoso_config.dll",
        "contoso_reporting.dll",
        "contoso_pricing.dll",
    ]
    assert "contoso_workflow.dll" in result["imported_lower_floor_dlls"]
    assert result["baseline_contract"]["source_wave_id"] == "wave-2-batch-a"
    assert result["slice_execution_attribution_present"] is True


def test_build_decomposition_campaign_plan_emits_runtime_overrides_by_target_dll() -> None:
    package_frontier_plan = build_package_frontier_plan(_wave_summary())

    result = build_decomposition_campaign_plan(
        _campaign_input(),
        package_frontier_plan,
        target_shard_width=2,
        max_slice_dlls=3,
    )

    config_runtime = result["per_dll_runtime_settings"]["contoso_config.dll"]
    assert config_runtime["iteration_mode"] == "floor_to_ceiling"
    assert config_runtime["floor_scope"] == "package"
    assert config_runtime["source_frontier_slice_id"].startswith("frontier_slice::contoso-business-suite")
    assert config_runtime["decomposition_execution_unit_id"].startswith("slice_exec::")
    assert sorted(result["active_dll_targets"]) == [
        "contoso_config.dll",
        "contoso_pricing.dll",
        "contoso_reporting.dll",
    ]


def test_build_decomposition_campaign_plan_projects_interwoven_artifacts_into_runtime_summary() -> None:
    package_frontier_plan = build_package_frontier_plan(_wave_summary())

    result = build_decomposition_campaign_plan(
        _campaign_input(),
        package_frontier_plan,
        target_shard_width=2,
        max_slice_dlls=3,
        interwoven_context={
            "producer_consumer_reports": [
                {
                    "family": "config_ticket_nonce_to_reporting_export",
                    "producer_id": "config_approval_license:CFG_ApproveLicensedCall",
                    "producer_kind": "producer",
                    "consumer_id": "reporting_preview_render_export:RP_ExportLedger",
                    "consumer_kind": "consumer",
                    "state_tokens": ("ticket", "nonce"),
                    "evidence_edges": ("CFG_ApproveLicensedCall->RP_ExportLedger",),
                    "dependency_mode": "shared_state_mediated",
                    "confidence": 0.84,
                    "contradiction_state": "tentative",
                }
            ],
            "shared_state_reports": [
                {
                    "carrier_id": "events_session_mask",
                    "carrier_kind": "shared_state_carrier",
                    "state_tokens": ("dwEventSession", "dwEventMask"),
                    "downstream_consumers": ("EV_RegisterMask", "EV_ReplayMask"),
                    "exporting_seams": ("EV_OpenEventSession",),
                    "importing_seams": ("EV_RegisterMask", "EV_ReplayMask"),
                    "staleness_risk": "medium",
                    "confidence": 0.72,
                    "contradiction_state": "tentative",
                }
            ],
            "subject_dll_hints": {
                "config_ticket_nonce_to_reporting_export": [
                    "contoso_config.dll",
                    "contoso_reporting.dll",
                ],
                "events_session_mask": ["contoso_config.dll", "contoso_reporting.dll"],
            },
        },
    )

    assert result["interwoven_artifact_presence"] is True
    assert "config_ticket_nonce_to_reporting_export" in result["interwoven_subject_ids"]
    assert result["interwoven_contradiction_summary"]["tentative"] == 2
    assert result["per_dll_runtime_settings"]["contoso_config.dll"]["interwoven_attribution_present"] is True
