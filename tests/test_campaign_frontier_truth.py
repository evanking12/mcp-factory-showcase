from __future__ import annotations

from api.pipeline.runner import _build_campaign_truth


def test_build_campaign_truth_preserves_imported_lower_floor_rows(monkeypatch) -> None:
    statuses = {
        "job-config": {
            "component_name": "contoso_config",
            "analysis_entrypoint": "upload",
            "binary_origin": "temp_upload",
            "graph_epoch": "campaign-frontier",
            "discovery_meta": {"cache_state": "warm", "bridge_reachable": True},
            "explore_runtime": {
                "analysis_profile": "strict_dll",
                "cross_dll_prior_job_ids": [],
                "prior_job_id": "",
                "overlap_baseline_job_id": "",
            },
        },
        "job-workflow": {
            "component_name": "contoso_workflow",
            "analysis_entrypoint": "upload",
            "binary_origin": "temp_upload",
            "graph_epoch": "campaign-frontier",
            "discovery_meta": {"cache_state": "warm", "bridge_reachable": True},
            "explore_runtime": {
                "analysis_profile": "strict_dll",
                "cross_dll_prior_job_ids": [],
                "prior_job_id": "",
                "overlap_baseline_job_id": "",
            },
        },
    }
    findings = {
        "job-config": [
            {
                "function": "CFG_RunCustomerSync",
                "status": "verified_success",
                "status_canonical": "verified_success",
                "working_call": {"lpszTicket": "TICK-001"},
            }
        ],
        "job-workflow": [],
    }

    monkeypatch.setattr("api.pipeline.runner._get_job_status", lambda job_id: statuses[job_id])
    monkeypatch.setattr("api.pipeline.runner._load_findings", lambda job_id: findings[job_id])

    truth = _build_campaign_truth(
        "camp-frontier",
        {
            "package_id": "suite",
            "package_label": "Suite",
            "package_context": {},
            "dll_entries": [
                {"job_id": "job-config", "dll_id": "dll-config", "filename": "contoso_config.dll", "status": "done", "lane_id": "lane-1"},
                {"job_id": "job-workflow", "dll_id": "dll-workflow", "filename": "contoso_workflow.dll", "status": "skipped", "lane_id": "lane-1"},
            ],
            "floor_to_ceiling_plan": {
                "package_floor": {
                    "floor_scope": "package",
                    "confirmation_gate": "package_confirmation_required",
                },
                "active_frontier_dlls": ["contoso_config.dll"],
                "imported_lower_floor_dlls": ["contoso_workflow.dll"],
                "imported_lower_floor_rows": [
                    {
                        "dll": "contoso_workflow.dll",
                        "component": "contoso_workflow",
                        "source_job_id": "baseline-workflow",
                        "verified_count": 12,
                        "total_functions": 12,
                    }
                ],
            },
        },
    )

    workflow = next(row for row in truth["per_dll"] if row["filename"] == "contoso_workflow.dll")
    assert workflow["imported_lower_floor"] is True
    assert workflow["imported_from_job_id"] == "baseline-workflow"
    assert workflow["verified_count"] == 12
    assert workflow["total_functions"] == 12
    assert truth["total_verified"] == 13
    assert truth["package_floor"]["floor_scope"] == "package"
    assert "contoso_workflow.dll" in truth["imported_lower_floor_dlls"]


def test_build_campaign_truth_inherits_baseline_contract_from_package_frontier_plan(monkeypatch) -> None:
    statuses = {
        "job-config": {
            "component_name": "contoso_config",
            "analysis_entrypoint": "upload",
            "binary_origin": "temp_upload",
            "graph_epoch": "campaign-frontier",
            "discovery_meta": {"cache_state": "warm", "bridge_reachable": True},
            "explore_runtime": {
                "analysis_profile": "strict_dll",
                "cross_dll_prior_job_ids": [],
                "prior_job_id": "",
                "overlap_baseline_job_id": "job-config-base",
            },
        },
        "job-workflow": {
            "component_name": "contoso_workflow",
            "analysis_entrypoint": "upload",
            "binary_origin": "temp_upload",
            "graph_epoch": "campaign-frontier",
            "discovery_meta": {"cache_state": "warm", "bridge_reachable": True},
            "explore_runtime": {
                "analysis_profile": "strict_dll",
                "cross_dll_prior_job_ids": [],
                "prior_job_id": "",
                "overlap_baseline_job_id": "",
            },
        },
    }
    findings = {
        "job-config": [
            {
                "function": "CFG_RunCustomerSync",
                "status": "verified_success",
                "status_canonical": "verified_success",
                "working_call": {"lpszTicket": "TICK-001"},
            }
        ],
        "job-workflow": [],
    }

    monkeypatch.setattr("api.pipeline.runner._get_job_status", lambda job_id: statuses[job_id])
    monkeypatch.setattr("api.pipeline.runner._load_findings", lambda job_id: findings[job_id])
    monkeypatch.setattr("api.pipeline.runner._try_campaign_json", lambda *_args, **_kwargs: {})

    truth = _build_campaign_truth(
        "camp-frontier",
        {
            "package_id": "suite",
            "package_label": "Suite",
            "package_context": {},
            "dll_entries": [
                {"job_id": "job-config", "dll_id": "dll-config", "filename": "contoso_config.dll", "status": "done", "lane_id": "lane-1"},
                {"job_id": "job-workflow", "dll_id": "dll-workflow", "filename": "contoso_workflow.dll", "status": "skipped", "lane_id": "lane-1"},
            ],
            "floor_to_ceiling_plan": {
                "package_floor": {
                    "floor_scope": "package",
                    "confirmation_gate": "package_confirmation_required",
                },
                "baseline_contract": {
                    "source_wave_id": "wave-batch-a",
                    "dll_entries": [
                        {
                            "component": "contoso_config",
                            "dll_id": "dll-config",
                            "filename": "contoso_config.dll",
                            "baseline_job_id": "job-config-base",
                            "baseline_verified_count": 0,
                        }
                    ],
                    "overlap_dll_set": ["contoso_config.dll"],
                },
                "active_frontier_dlls": ["contoso_config.dll"],
                "imported_lower_floor_dlls": ["contoso_workflow.dll"],
                "imported_lower_floor_rows": [
                    {
                        "dll": "contoso_workflow.dll",
                        "component": "contoso_workflow",
                        "source_job_id": "baseline-workflow",
                        "verified_count": 12,
                        "total_functions": 12,
                    }
                ],
            },
        },
    )

    assert truth["baseline_contract_present"] is True
    assert truth["baseline_contract"]["source_wave_id"] == "wave-batch-a"
    assert truth["package_floor_evidence_class"] == "overlap_comparable_confirmation"
    assert truth["package_floor_confirmation_ready"] is True


def test_build_campaign_truth_surfaces_decomposition_plan_fields(monkeypatch) -> None:
    statuses = {
        "job-config": {
            "component_name": "contoso_config",
            "analysis_entrypoint": "upload",
            "binary_origin": "temp_upload",
            "graph_epoch": "campaign-frontier",
            "source_frontier_slice_id": "frontier_slice::suite::campaign-frontier::0",
            "decomposition_execution_unit_id": "slice_exec::frontier_slice::suite::campaign-frontier::0::0",
            "required_dependency_class_ids": ["business_object_continuity"],
            "protected_imported_truth_ids": ["contoso_workflow.dll"],
            "discovery_meta": {"cache_state": "warm", "bridge_reachable": True},
            "explore_runtime": {
                "analysis_profile": "strict_dll",
                "cross_dll_prior_job_ids": [],
                "prior_job_id": "",
                "overlap_baseline_job_id": "job-config-base",
            },
        },
        "job-workflow": {
            "component_name": "contoso_workflow",
            "analysis_entrypoint": "upload",
            "binary_origin": "temp_upload",
            "graph_epoch": "campaign-frontier",
            "discovery_meta": {"cache_state": "warm", "bridge_reachable": True},
            "explore_runtime": {
                "analysis_profile": "strict_dll",
                "cross_dll_prior_job_ids": [],
                "prior_job_id": "",
                "overlap_baseline_job_id": "",
            },
        },
    }
    findings = {
        "job-config": [
            {
                "function": "CFG_RunCustomerSync",
                "status": "verified_success",
                "status_canonical": "verified_success",
                "working_call": {"lpszTicket": "TICK-001"},
            }
        ],
        "job-workflow": [],
    }

    monkeypatch.setattr("api.pipeline.runner._get_job_status", lambda job_id: statuses[job_id])
    monkeypatch.setattr("api.pipeline.runner._load_findings", lambda job_id: findings[job_id])

    truth = _build_campaign_truth(
        "camp-frontier",
        {
            "package_id": "suite",
            "package_label": "Suite",
            "package_context": {},
            "dll_entries": [
                {"job_id": "job-config", "dll_id": "dll-config", "filename": "contoso_config.dll", "status": "done", "lane_id": "lane-1"},
                {"job_id": "job-workflow", "dll_id": "dll-workflow", "filename": "contoso_workflow.dll", "status": "skipped", "lane_id": "lane-1"},
            ],
            "floor_to_ceiling_plan": {
                "package_floor": {"floor_scope": "package", "confirmation_gate": "package_confirmation_required"},
                "baseline_contract": {
                    "source_wave_id": "wave-batch-a",
                    "dll_entries": [
                        {
                            "component": "contoso_config",
                            "dll_id": "dll-config",
                            "filename": "contoso_config.dll",
                            "baseline_job_id": "job-config-base",
                            "baseline_verified_count": 0,
                        }
                    ],
                    "overlap_dll_set": ["contoso_config.dll"],
                },
                "active_frontier_dlls": ["contoso_config.dll"],
                "imported_lower_floor_dlls": ["contoso_workflow.dll"],
                "imported_lower_floor_rows": [
                    {
                        "dll": "contoso_workflow.dll",
                        "component": "contoso_workflow",
                        "source_job_id": "baseline-workflow",
                        "verified_count": 12,
                        "total_functions": 12,
                    }
                ],
            },
            "decomposition_campaign_plan": {
                "active_frontier_slice_ids": ["frontier_slice::suite::campaign-frontier::0"],
                "imported_to_active_ratio": 1.0,
                "deferred_initialization_group_ids": ["group-deferred"],
                "deferred_dependency_class_ids": ["class-deferred"],
                "interwoven_artifact_presence": True,
                "interwoven_subject_ids": ["config_ticket_nonce_to_reporting_export"],
                "interwoven_contradiction_summary": {"tentative": 1},
                "interwoven_attribution_present": True,
                "slice_execution_attribution_present": True,
                "execution_map": {
                    "execution_units": [
                        {
                            "target_dll": "contoso_config.dll",
                            "source_frontier_slice_id": "frontier_slice::suite::campaign-frontier::0",
                            "execution_unit_id": "slice_exec::frontier_slice::suite::campaign-frontier::0::0",
                        }
                    ]
                },
            },
        },
    )

    assert truth["decomposition_plan_present"] is True
    assert truth["active_frontier_slice_ids"] == ["frontier_slice::suite::campaign-frontier::0"]
    assert truth["imported_to_active_ratio"] == 1.0
    assert truth["interwoven_artifact_presence"] is True
    assert truth["interwoven_subject_ids"] == ["config_ticket_nonce_to_reporting_export"]
    assert truth["interwoven_attribution_present"] is True
    assert truth["slice_execution_attribution_present"] is True
    config = next(row for row in truth["per_dll"] if row["filename"] == "contoso_config.dll")
    assert config["source_frontier_slice_id"] == "frontier_slice::suite::campaign-frontier::0"
    assert config["decomposition_execution_unit_id"].startswith("slice_exec::")
