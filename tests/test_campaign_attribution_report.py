from __future__ import annotations


def test_emit_campaign_attribution_report_classifies_same_dll_vs_cross_dll(monkeypatch) -> None:
    from api.analysis import cohesion

    uploads: dict[str, dict] = {}
    monkeypatch.setattr(cohesion, "_read_run_ledger_rows", lambda: [])

    monkeypatch.setattr(
        cohesion,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, __import__("json").loads(data.decode("utf-8"))),
    )
    monkeypatch.setattr(
        cohesion,
        "_get_job_status",
        lambda job_id: {
            "analysis_entrypoint": "analyze",
            "binary_origin": "upload",
            "analysis_profile": "strict_dll",
            "discovery_meta": {"cache_state": "cold", "bridge_reachable": True},
            "explore_runtime": {
                "analysis_profile": "strict_dll",
                "graph_epoch": "none",
                "prior_job_id": "same-dll-source" if job_id == "job-same" else "",
                "cross_dll_prior_job_ids": ["job-a", "job-b"] if job_id == "job-cross" else [],
            },
        },
    )
    monkeypatch.setattr(
        cohesion,
        "_load_findings",
        lambda _job_id: [
            {"function": "FnA", "status": "verified_success"},
            {"function": "FnB", "status": "failure"},
        ],
    )

    report = cohesion.emit_campaign_attribution_report(
        "camp-attr",
        {
            "campaign_id": "camp-attr",
            "phase": "executing",
            "package_id": "pkg-soundtouch",
            "package_label": "SoundTouch bundle",
            "doc_visibility": "unknown",
            "dependency_context": "curated_subset",
            "dll_entries": [
                {
                    "dll_id": "dll-same",
                    "job_id": "job-same",
                    "filename": "same.dll",
                    "status": "done",
                    "lane_id": "lane-1",
                    "selection_reason": "top_candidate",
                },
                {
                    "dll_id": "dll-cross",
                    "job_id": "job-cross",
                    "filename": "cross.dll",
                    "status": "done",
                    "lane_id": "lane-1",
                    "selection_reason": "dependency_pair",
                },
            ],
        },
    )

    assert report["attribution_mode_counts"]["same_dll"] == 1
    assert report["attribution_mode_counts"]["cross_dll"] == 1
    assert report["same_dll_comparison_ready"] == ["job-same"]
    assert report["cross_dll_comparison_ready"] == ["job-cross"]
    assert "architect_summary" in report
    assert "function_matrix" in report
    assert "blocker_family_summary" in report
    assert "system_opportunity_summary" in report
    assert len(report["function_matrix"]) == 4
    assert report["package_id"] == "pkg-soundtouch"
    assert report["package_label"] == "SoundTouch bundle"
    assert "campaigns/camp-attr/campaign-attribution-report.json" in uploads


def test_campaign_reports_prefer_campaign_truth_when_present(monkeypatch) -> None:
    from api.analysis import cohesion

    uploads: dict[str, dict] = {}
    monkeypatch.setattr(cohesion, "_read_run_ledger_rows", lambda: [])
    truth_payload = {
        "campaign_id": "camp-truth",
        "package_floor_evidence_class": "overlap_comparable_confirmation",
        "package_floor_confirmation_ready": True,
        "per_dll": [
            {
                "job_id": "job-1",
                "dll_id": "dll-1",
                "filename": "one.dll",
                "status": "done",
                "package_id": "pkg-1",
                "package_label": "Package 1",
                "selection_reason": "top_runtime_candidate",
                "dependency_confidence": "high",
                "lane_id": "lane-1",
                "analysis_entrypoint": "analyze",
                "binary_origin": "upload",
                "analysis_profile": "strict_dll",
                "cache_state": "cold",
                "bridge_reachable": True,
                "graph_epoch": "camp-truth",
                "prior_job_id": "",
                "cross_dll_prior_job_ids": [],
                "cross_dll_prior_job_count": 0,
                "attribution_mode": "none",
                "comparable_surface_ready": True,
                "verified_count": 2,
                "total_functions": 3,
                "lane_trust_status": "trusted",
                "runtime_path_trust": "matched",
                "blocker_family_primary": "struct/payload shaping",
                "blocker_family_secondary": ["sequencing/state machine"],
                "blocker_confidence": "high",
                "architecture_relevance": "high",
            }
        ],
        "blocker_harvest_summary": {
            "dominant_blocker_families": [{"family": "struct/payload shaping", "dll_count": 1}],
            "lane_trust_summary": {"trusted": 1},
            "architecture_relevance_summary": {"high": 1},
        },
    }

    monkeypatch.setattr(
        cohesion,
        "_download_blob",
        lambda _container, blob_name: __import__("json").dumps(truth_payload).encode("utf-8")
        if blob_name == "campaigns/camp-truth/campaign-truth.json"
        else b"{}",
    )
    monkeypatch.setattr(
        cohesion,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, __import__("json").loads(data.decode("utf-8"))),
    )
    monkeypatch.setattr(cohesion, "_load_findings", lambda _job_id: [])
    monkeypatch.setattr(cohesion, "_get_job_status", lambda _job_id: {})

    attribution = cohesion.emit_campaign_attribution_report(
        "camp-truth",
        {"phase": "done", "dll_entries": [{"dll_id": "dll-1", "job_id": "job-1", "filename": "one.dll", "status": "done"}]},
    )
    cohesion_report = cohesion.emit_campaign_cohesion_report(
        "camp-truth",
        {"phase": "done", "dll_entries": [{"dll_id": "dll-1", "job_id": "job-1", "filename": "one.dll", "status": "done"}]},
    )

    assert attribution["campaign_truth_present"] is True
    assert attribution["package_floor_evidence_class"] == "overlap_comparable_confirmation"
    assert attribution["package_floor_confirmation_ready"] is True
    assert attribution["per_dll"][0]["verified_count"] == 2
    assert cohesion_report["campaign_truth_present"] is True
    assert cohesion_report["package_floor_evidence_class"] == "overlap_comparable_confirmation"
    assert cohesion_report["package_floor_confirmation_ready"] is True
    assert cohesion_report["per_dll"][0]["verified_count"] == 2
    assert attribution["per_dll"][0]["component"] == "one"
    assert attribution["per_dll"][0]["lane_trust_status"] == "trusted"
    assert attribution["blocker_harvest_summary"]["lane_trust_summary"]["trusted"] == 1
    assert cohesion_report["blocker_harvest_summary"]["dominant_blocker_families"][0]["family"] == "struct/payload shaping"
    assert "campaigns/camp-truth/campaign-attribution-report.json" in uploads
    assert "campaigns/camp-truth/campaign-cohesion-report.json" in uploads


def test_campaign_attribution_report_builds_function_deltas_and_regression_summary(monkeypatch) -> None:
    from api.analysis import cohesion

    uploads: dict[str, dict] = {}
    monkeypatch.setattr(
        cohesion,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, __import__("json").loads(data.decode("utf-8"))),
    )
    monkeypatch.setattr(
        cohesion,
        "_read_run_ledger_rows",
        lambda: [
            {
                "job_id": "job-base",
                "capture_seq": 0,
                "component": "contoso_reporting",
                "dll_fingerprint": "dll-fp-1",
                "comparable_profile_key": "strict",
            },
            {
                "job_id": "job-new",
                "capture_seq": 1,
                "component": "contoso_reporting",
                "dll_fingerprint": "dll-fp-1",
                "comparable_profile_key": "strict",
            },
        ],
    )
    monkeypatch.setattr(
        cohesion,
        "_get_job_status",
        lambda _job_id: {
            "component_name": "contoso_reporting",
            "analysis_entrypoint": "analyze_path",
            "binary_origin": "repo_fixture",
            "analysis_profile": "strict_dll",
            "discovery_meta": {"cache_state": "cold", "bridge_reachable": True},
            "explore_runtime": {"analysis_profile": "strict_dll", "graph_epoch": "none", "prior_job_id": "", "cross_dll_prior_job_ids": []},
        },
    )
    monkeypatch.setattr(
        cohesion,
        "_load_findings",
        lambda job_id: (
            [
                {"function": "RP_Initialize", "status_canonical": "verified_success", "working_call": {}, "source_stage": "s02_probe"},
                {"function": "RP_ExportLedger", "status_canonical": "failure", "finding": "All probes returned sentinel -4004"},
            ]
            if job_id == "job-new"
            else [
                {"function": "RP_Initialize", "status_canonical": "verified_success", "working_call": {}, "source_stage": "s02_probe"},
                {"function": "RP_ExportLedger", "status_canonical": "verified_success", "working_call": {"lpszReportId": "RPT-CUST-001"}},
            ]
        ),
    )
    monkeypatch.setattr(
        cohesion,
        "_download_blob",
        lambda _container, blob_name: (
            __import__("json").dumps(
                {
                    "entries": [
                        {"function": "RP_Initialize", "verification": "verified"},
                    ]
                }
            ).encode("utf-8")
            if blob_name == "job-new/verification-report.json"
            else b"{}"
        ),
    )

    report = cohesion.emit_campaign_attribution_report(
        "camp-delta",
        {
            "campaign_id": "camp-delta",
            "phase": "done",
            "dll_entries": [
                {"dll_id": "dll-1", "job_id": "job-new", "filename": "contoso_reporting.dll", "status": "done"},
            ],
        },
    )

    by_function = {row["function"]: row for row in report["function_matrix"]}
    assert by_function["RP_ExportLedger"]["baseline_job_id"] == "job-base"
    assert by_function["RP_ExportLedger"]["delta_vs_baseline"] == "regressed"
    assert by_function["RP_ExportLedger"]["likely_missing_system"] in {
        "generalized runtime artifact materializer",
        "prerequisite and state-machine classifier",
    }
    assert report["regression_summary"][0]["function"] == "RP_ExportLedger"
    assert report["system_opportunity_summary"]
    assert report["architect_summary"]["regressed_functions"] == 1


def test_campaign_attribution_report_explains_local_green_package_red_carryover(monkeypatch) -> None:
    from api.analysis import cohesion

    uploads: dict[str, dict] = {}
    monkeypatch.setattr(
        cohesion,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, __import__("json").loads(data.decode("utf-8"))),
    )
    monkeypatch.setattr(
        cohesion,
        "_read_run_ledger_rows",
        lambda: [
            {
                "job_id": "job-base",
                "capture_seq": 0,
                "component": "contoso_pricing",
                "dll_fingerprint": "dll-fp-1",
                "comparable_profile_key": "strict",
            },
            {
                "job_id": "job-package",
                "capture_seq": 1,
                "component": "contoso_pricing",
                "dll_fingerprint": "dll-fp-1",
                "comparable_profile_key": "strict",
            },
        ],
    )
    monkeypatch.setattr(
        cohesion,
        "_get_job_status",
        lambda _job_id: {
            "component_name": "contoso_pricing",
            "analysis_entrypoint": "upload",
            "binary_origin": "temp_upload",
            "analysis_profile": "strict_dll",
            "discovery_meta": {"cache_state": "warm", "bridge_reachable": True},
            "explore_runtime": {"analysis_profile": "strict_dll", "graph_epoch": "none", "prior_job_id": "", "cross_dll_prior_job_ids": []},
        },
    )

    def _load_findings(job_id: str) -> list[dict]:
        if job_id == "job-base":
            return [
                {"function": "PR_BeginQuote", "status_canonical": "verified_success", "working_call": {"pOutQuoteId": "PRQ-001"}},
                {"function": "PR_GetQuoteNonce", "status_canonical": "verified_success", "working_call": {"lpszQuoteId": "PRQ-001"}},
                {"function": "PR_ApproveRuleWindow", "status_canonical": "verified_success", "working_call": {"lpszQuoteId": "PRQ-001", "dwNonce": 7}},
                {"function": "PR_GetQuoteState", "status_canonical": "verified_success", "working_call": {"lpszQuoteId": "PRQ-001"}},
            ]
        if job_id == "job-package":
            return [
                {
                    "function": "PR_BeginQuote",
                    "status_canonical": "verified_success",
                    "working_call": {"pOutQuoteId": "PRQ-004"},
                    "finding": "Verified during prerequisite replay for PR_GetQuoteState: returns 0.",
                },
                {
                    "function": "PR_GetQuoteNonce",
                    "status_canonical": "verified_success",
                    "working_call": {"lpszQuoteId": "PRQ-004", "pdwNonceOut": 9},
                    "finding": "Verified during prerequisite replay for PR_GetQuoteState: returns 0.",
                },
                {
                    "function": "PR_ApproveRuleWindow",
                    "status_canonical": "verified_success",
                    "working_call": {"lpszQuoteId": "PRQ-004", "dwNonce": 9},
                    "finding": "Verified during prerequisite replay for PR_GetQuoteState: returns 0.",
                },
                {
                    "function": "PR_GetQuoteState",
                    "status_canonical": "failure",
                    "finding": "All probes returned sentinel codes: unknown. No working call found.",
                },
            ]
        return []

    monkeypatch.setattr(cohesion, "_load_findings", _load_findings)
    monkeypatch.setattr(
        cohesion,
        "_download_blob",
        lambda _container, blob_name: (
            __import__("json").dumps(
                [
                    {"function": "PR_GetQuoteState", "phase": "calibrate_sentinels"},
                ]
            ).encode("utf-8")
            if blob_name == "job-package/explore_probe_log.json"
            else __import__("json").dumps({"entries": []}).encode("utf-8")
        ),
    )
    monkeypatch.setattr(cohesion, "_local_artifact_job_ids", lambda: ["local-proof"])

    def _local_json(job_id: str, filename: str):
        if job_id != "local-proof":
            return None
        payloads = {
            "status.json": {
                "component_name": "contoso_pricing",
                "updated_at": 100.0,
                "explore_runtime": {
                    "cluster_checkpoint_id": "pricing_quote_lifecycle",
                    "focus_functions": ["PR_GetQuoteState"],
                },
            },
            "findings.json": [
                {"function": "PR_GetQuoteState", "status_canonical": "verified_success", "working_call": {"lpszQuoteId": "PRQ-004"}}
            ],
            "verification-report.json": {
                "entries": [
                    {"function": "PR_GetQuoteState", "verification": "verified"}
                ]
            },
            "checkpoints/latest.json": {
                "cluster_checkpoints": {
                    "pricing_quote_lifecycle": {
                        "gate_color": "green",
                    }
                }
            },
        }
        return payloads.get(filename)

    monkeypatch.setattr(cohesion, "_try_local_artifact_json", _local_json)

    report = cohesion.emit_campaign_attribution_report(
        "camp-carry",
        {
            "campaign_id": "camp-carry",
            "phase": "done",
            "dll_entries": [
                {"dll_id": "dll-1", "job_id": "job-package", "filename": "contoso_pricing.dll", "status": "done"},
            ],
        },
    )

    assert report["carryover_audit_summary"]["explained_regressions"] == 1
    audit = report["carryover_audits"][0]
    assert audit["failure_class"] == "package_orchestration_drop"
    assert audit["local_proof_job_id"] == "local-proof"
    assert audit["first_broken_handoff"] == "PR_ApproveRuleWindow -> PR_GetQuoteState"
    regression = report["regression_summary"][0]
    assert regression["likely_regression_cause"] == "carryover_missing_direct_target_persistence"
    assert regression["package_direct_target_calls"] == 0
    assert regression["producer_replay_successes"] == [
        "PR_BeginQuote",
        "PR_GetQuoteNonce",
        "PR_ApproveRuleWindow",
    ]


def test_campaign_attribution_report_prefers_explicit_baseline_contract(monkeypatch) -> None:
    from api.analysis import cohesion

    monkeypatch.setattr(
        cohesion,
        "_read_run_ledger_rows",
        lambda: [
            {
                "job_id": "job-ledger-base",
                "capture_seq": 0,
                "component": "contoso_payments",
                "dll_fingerprint": "dll-fp-2",
                "comparable_profile_key": "strict",
            },
            {
                "job_id": "job-current",
                "capture_seq": 1,
                "component": "contoso_payments",
                "dll_fingerprint": "dll-fp-2",
                "comparable_profile_key": "strict",
            },
        ],
    )
    monkeypatch.setattr(
        cohesion,
        "_get_job_status",
        lambda _job_id: {
            "component_name": "contoso_payments",
            "analysis_entrypoint": "upload",
            "binary_origin": "repo_fixture",
            "analysis_profile": "strict_dll",
            "discovery_meta": {"cache_state": "cold", "bridge_reachable": True},
            "explore_runtime": {"analysis_profile": "strict_dll", "graph_epoch": "none", "prior_job_id": "", "cross_dll_prior_job_ids": []},
        },
    )
    monkeypatch.setattr(
        cohesion,
        "_load_findings",
        lambda job_id: (
            [{"function": "CP_ReserveInventory", "status_canonical": "verified_success", "working_call": {}}]
            if job_id == "job-current"
            else ([{"function": "CP_ReserveInventory", "status_canonical": "failure"}] if job_id == "job-explicit-base" else [{"function": "CP_ReserveInventory", "status_canonical": "verified_success"}])
        ),
    )
    monkeypatch.setattr(cohesion, "_download_blob", lambda _container, _blob_name: b"{}")
    uploads: dict[str, dict] = {}
    monkeypatch.setattr(
        cohesion,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, __import__("json").loads(data.decode("utf-8"))),
    )

    report = cohesion.emit_campaign_attribution_report(
        "camp-explicit-base",
        {
            "campaign_id": "camp-explicit-base",
            "phase": "done",
            "baseline_contract": {
                "dll_entries": [
                    {
                        "component": "contoso_payments",
                        "dll_id": "contoso_payments",
                        "filename": "contoso_payments.dll",
                        "baseline_job_id": "job-explicit-base",
                        "source_type": "curated_suite_baseline",
                        "provisional": False,
                        "note": "trusted benchmark baseline",
                    }
                ]
            },
            "dll_entries": [
                {"dll_id": "contoso_payments", "job_id": "job-current", "filename": "contoso_payments.dll", "status": "done"},
            ],
        },
    )

    row = report["function_matrix"][0]
    assert row["baseline_job_id"] == "job-explicit-base"
    assert row["baseline_source"] == "curated_suite_baseline"
    assert row["delta_vs_baseline"] == "improved"
    assert report["baseline_contract_present"] is True
    assert report["baseline_contract"]["dll_count"] == 1
    assert report["baseline_contract"]["entries"][0]["baseline_job_id"] == "job-explicit-base"


def test_campaign_attribution_report_marks_explicit_surface_mismatch_incomparable(monkeypatch) -> None:
    from api.analysis import cohesion

    monkeypatch.setattr(cohesion, "_read_run_ledger_rows", lambda: [])
    monkeypatch.setattr(
        cohesion,
        "_load_findings",
        lambda job_id: (
            [{"function": "CP_ReserveStock", "status_canonical": "failure", "source_stage": "s02_probe"}]
            if job_id == "job-current"
            else [{"function": "CP_ReserveStock", "status_canonical": "verified_success", "working_call": {}}]
        ),
    )

    def _status(job_id: str) -> dict:
        if job_id == "job-current":
            return {
                "component_name": "contoso_payments",
                "analysis_entrypoint": "analyze_path",
                "binary_origin": "repo_fixture",
                "analysis_profile": "strict_dll",
                "discovery_meta": {"cache_state": "cold", "bridge_reachable": True},
                "explore_runtime": {"analysis_profile": "strict_dll", "graph_epoch": "none", "prior_job_id": "", "cross_dll_prior_job_ids": []},
            }
        return {
            "component_name": "contoso_payments",
            "analysis_entrypoint": "upload",
            "binary_origin": "temp_upload",
            "analysis_profile": "strict_dll",
            "discovery_meta": {"cache_state": "cold", "bridge_reachable": True},
            "explore_runtime": {"analysis_profile": "strict_dll", "graph_epoch": "none", "prior_job_id": "", "cross_dll_prior_job_ids": []},
        }

    monkeypatch.setattr(cohesion, "_get_job_status", _status)
    monkeypatch.setattr(cohesion, "_download_blob", lambda _container, _blob_name: b"{}")
    monkeypatch.setattr(cohesion, "_upload_to_blob", lambda *_args, **_kwargs: None)

    report = cohesion.emit_campaign_attribution_report(
        "camp-surface-mismatch",
        {
            "campaign_id": "camp-surface-mismatch",
            "phase": "done",
            "baseline_contract": {
                "dll_entries": [
                    {
                        "component": "contoso_payments",
                        "dll_id": "contoso_payments",
                        "filename": "contoso_payments.dll",
                        "baseline_job_id": "job-upload-base",
                        "source_type": "curated_suite_baseline",
                        "provisional": False,
                        "note": "trusted upload baseline",
                    }
                ]
            },
            "dll_entries": [
                {"dll_id": "contoso_payments", "job_id": "job-current", "filename": "contoso_payments.dll", "status": "done"},
            ],
        },
    )

    row = report["function_matrix"][0]
    assert row["delta_vs_baseline"] == "incomparable"
    assert "analysis_entrypoint:upload->analyze_path" in row["baseline_surface_mismatch"]
    assert "binary_origin:temp_upload->repo_fixture" in row["baseline_surface_mismatch"]
    assert any("explicit baseline surface mismatch" in warning for warning in report["hidden_variable_warnings"])


def test_campaign_attribution_report_uses_expansion_overlap_baseline_contract(monkeypatch) -> None:
    from api.analysis import cohesion

    monkeypatch.setattr(cohesion, "_read_run_ledger_rows", lambda: [])

    def _status(job_id: str) -> dict:
        base = {
            "component_name": "contoso_workflow" if "workflow" in job_id else "contoso_events",
            "analysis_entrypoint": "upload",
            "binary_origin": "temp_upload",
            "analysis_profile": "strict_dll",
            "discovery_meta": {"cache_state": "warm", "bridge_reachable": True},
            "explore_runtime": {"analysis_profile": "strict_dll", "graph_epoch": "epoch-new", "prior_job_id": "", "cross_dll_prior_job_ids": ["seed-a"]},
        }
        if job_id == "job-workflow-base":
            base["explore_runtime"] = {"analysis_profile": "strict_dll", "graph_epoch": "epoch-old", "prior_job_id": "", "cross_dll_prior_job_ids": ["seed-a"]}
        return base

    monkeypatch.setattr(cohesion, "_get_job_status", _status)
    monkeypatch.setattr(
        cohesion,
        "_load_findings",
        lambda job_id: (
            [{"function": "WF_GetWorkflowState", "status_canonical": "verified_success", "working_call": {}}]
            if job_id == "job-workflow-current"
            else ([{"function": "WF_GetWorkflowState", "status_canonical": "failure"}] if job_id == "job-workflow-base" else [{"function": "EV_RegisterHandler", "status_canonical": "failure"}])
        ),
    )
    monkeypatch.setattr(cohesion, "_download_blob", lambda _container, _blob_name: b"{}")
    monkeypatch.setattr(cohesion, "_upload_to_blob", lambda *_args, **_kwargs: None)

    report = cohesion.emit_campaign_attribution_report(
        "camp-overlap",
        {
            "campaign_id": "camp-overlap",
            "phase": "done",
            "baseline_contract": {
                "source_wave_id": "wave-2-batch-a",
                "source_campaign_id": "camp-a",
                "baseline_graph_epoch": "epoch-old",
                "baseline_seeding_mode": "cross_dll_prior",
                "baseline_package_dll_set": ["contoso_workflow.dll", "contoso_gateway.dll"],
                "overlap_dll_set": ["contoso_workflow.dll"],
                "no_baseline_required_dlls": ["contoso_events.dll"],
                "dll_entries": [
                    {
                        "component": "contoso_workflow",
                        "dll_id": "wf",
                        "filename": "contoso_workflow.dll",
                        "baseline_job_id": "job-workflow-base",
                        "source_type": "wave_expansion_overlap_baseline",
                        "provisional": False,
                        "note": "trusted overlap baseline",
                        "baseline_verified_count": 0,
                        "baseline_total_functions": 1,
                        "analysis_entrypoint": "upload",
                        "binary_origin": "temp_upload",
                        "analysis_profile": "strict_dll",
                        "cache_state": "warm",
                        "seeding_mode": "cross_dll_prior",
                        "graph_epoch": "epoch-old",
                    }
                ],
            },
            "dll_entries": [
                {"dll_id": "wf", "job_id": "job-workflow-current", "filename": "contoso_workflow.dll", "status": "done"},
                {"dll_id": "ev", "job_id": "job-events-current", "filename": "contoso_events.dll", "status": "done"},
            ],
        },
    )

    rows = {row["function"]: row for row in report["function_matrix"]}
    assert rows["WF_GetWorkflowState"]["delta_vs_baseline"] == "improved"
    assert rows["WF_GetWorkflowState"]["baseline_source"] == "wave_expansion_overlap_baseline"
    assert rows["EV_RegisterHandler"]["baseline_source"] == "not_required_for_expansion"
    assert report["overlap_baseline_comparable"] is True
    assert report["package_wide_comparable"] is False
    assert report["overlap_dll_count"] == 1
    assert report["overlap_verified_delta"] == 1
    assert report["no_baseline_required_dlls"] == ["contoso_events.dll"]


def test_campaign_reports_inherit_baseline_contract_from_package_frontier_plan(monkeypatch) -> None:
    from api.analysis import cohesion

    uploads: dict[str, dict] = {}
    monkeypatch.setattr(cohesion, "_read_run_ledger_rows", lambda: [])

    def _download(_container, blob_name):
        payloads = {
            "campaigns/camp-frontier/campaign-truth.json": {
                "campaign_id": "camp-frontier",
                "active_frontier_dlls": ["contoso_config.dll"],
                "imported_lower_floor_dlls": ["contoso_workflow.dll"],
                "package_floor": {"floor_scope": "package"},
                "overlap_baseline_comparable": True,
                "per_dll": [
                    {
                        "job_id": "job-config",
                        "dll_id": "dll-config",
                        "filename": "contoso_config.dll",
                        "status": "done",
                        "package_id": "pkg-1",
                        "package_label": "Package 1",
                        "selection_reason": "frontier_only",
                        "dependency_confidence": "high",
                        "lane_id": "lane-1",
                        "analysis_entrypoint": "upload",
                        "binary_origin": "temp_upload",
                        "analysis_profile": "strict_dll",
                        "cache_state": "warm",
                        "bridge_reachable": True,
                        "graph_epoch": "epoch-1",
                        "prior_job_id": "",
                        "cross_dll_prior_job_ids": [],
                        "cross_dll_prior_job_count": 0,
                        "attribution_mode": "none",
                        "comparable_surface_ready": True,
                        "verified_count": 1,
                        "total_functions": 1,
                        "lane_trust_status": "trusted",
                        "runtime_path_trust": "matched",
                        "blocker_family_primary": "",
                        "blocker_family_secondary": [],
                        "blocker_confidence": "",
                        "architecture_relevance": "",
                    },
                    {
                        "job_id": "job-workflow",
                        "dll_id": "dll-workflow",
                        "filename": "contoso_workflow.dll",
                        "status": "skipped",
                        "package_id": "pkg-1",
                        "package_label": "Package 1",
                        "selection_reason": "imported_lower_floor",
                        "dependency_confidence": "high",
                        "lane_id": "lane-1",
                        "analysis_entrypoint": "upload",
                        "binary_origin": "temp_upload",
                        "analysis_profile": "strict_dll",
                        "cache_state": "warm",
                        "bridge_reachable": True,
                        "graph_epoch": "epoch-1",
                        "prior_job_id": "",
                        "cross_dll_prior_job_ids": [],
                        "cross_dll_prior_job_count": 0,
                        "attribution_mode": "none",
                        "comparable_surface_ready": True,
                        "verified_count": 12,
                        "total_functions": 12,
                        "lane_trust_status": "trusted",
                        "runtime_path_trust": "matched",
                        "blocker_family_primary": "",
                        "blocker_family_secondary": [],
                        "blocker_confidence": "",
                        "architecture_relevance": "",
                        "imported_lower_floor": True,
                    },
                ],
            },
            "campaigns/camp-frontier/package-frontier-plan.json": {
                "package_floor": {"floor_scope": "package"},
                "active_frontier_dlls": ["contoso_config.dll"],
                "imported_lower_floor_dlls": ["contoso_workflow.dll"],
                "baseline_contract": {
                    "source_wave_id": "wave-2-batch-a",
                    "overlap_dll_set": ["contoso_config.dll"],
                    "dll_entries": [
                        {
                            "component": "contoso_config",
                            "dll_id": "dll-config",
                            "filename": "contoso_config.dll",
                            "baseline_job_id": "job-config-base",
                            "baseline_verified_count": 0,
                        }
                    ],
                },
            },
            "campaigns/camp-frontier/decomposition-campaign-plan.json": {
                "active_frontier_slice_ids": ["frontier_slice::pkg-1::epoch-1::0"],
                "imported_to_active_ratio": 1.0,
                "deferred_initialization_group_ids": ["group-deferred"],
                "deferred_dependency_class_ids": ["class-deferred"],
                "interwoven_artifact_presence": True,
                "interwoven_subject_ids": ["config_ticket_nonce_to_reporting_export"],
                "interwoven_contradiction_summary": {"tentative": 1},
                "interwoven_attribution_present": True,
                "slice_execution_attribution_present": True,
            },
        }
        return __import__("json").dumps(payloads.get(blob_name, {})).encode("utf-8")

    monkeypatch.setattr(cohesion, "_download_blob", _download)
    monkeypatch.setattr(
        cohesion,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, __import__("json").loads(data.decode("utf-8"))),
    )
    monkeypatch.setattr(cohesion, "_load_findings", lambda _job_id: [{"function": "CFG_RunCustomerSync", "status_canonical": "verified_success", "working_call": {}}])
    monkeypatch.setattr(cohesion, "_get_job_status", lambda _job_id: {})

    attribution = cohesion.emit_campaign_attribution_report(
        "camp-frontier",
        {
            "phase": "done",
            "dll_entries": [
                {"dll_id": "dll-config", "job_id": "job-config", "filename": "contoso_config.dll", "status": "done"},
                {"dll_id": "dll-workflow", "job_id": "job-workflow", "filename": "contoso_workflow.dll", "status": "skipped"},
            ],
        },
    )
    cohesion_report = cohesion.emit_campaign_cohesion_report(
        "camp-frontier",
        {
            "phase": "done",
            "dll_entries": [
                {"dll_id": "dll-config", "job_id": "job-config", "filename": "contoso_config.dll", "status": "done"},
                {"dll_id": "dll-workflow", "job_id": "job-workflow", "filename": "contoso_workflow.dll", "status": "skipped"},
            ],
        },
    )

    assert attribution["baseline_contract_present"] is True
    assert attribution["package_floor_evidence_class"] == "overlap_comparable_confirmation"
    assert attribution["package_floor_confirmation_ready"] is True
    assert attribution["baseline_contract"]["source_wave_id"] == "wave-2-batch-a"
    assert attribution["decomposition_plan_present"] is True
    assert attribution["active_frontier_slice_ids"] == ["frontier_slice::pkg-1::epoch-1::0"]
    assert attribution["interwoven_artifact_presence"] is True
    assert attribution["interwoven_subject_ids"] == ["config_ticket_nonce_to_reporting_export"]
    assert attribution["interwoven_attribution_present"] is True
    assert attribution["slice_execution_attribution_present"] is True
    assert cohesion_report["baseline_contract_present"] is True
    assert cohesion_report["package_floor_evidence_class"] == "overlap_comparable_confirmation"
    assert cohesion_report["decomposition_plan_present"] is True
    assert cohesion_report["interwoven_artifact_presence"] is True
    assert cohesion_report["deferred_initialization_group_ids"] == ["group-deferred"]
