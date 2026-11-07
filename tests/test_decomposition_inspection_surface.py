from api.pipeline.core.decomposition_inspection_surface import build_decomposition_inspection_surface
from api.pipeline.core.dependency_class_inference import infer_dependency_classes
from api.pipeline.core.init_group_inference import infer_initialization_groups
from api.pipeline.core.package_frontier_slice_planner import build_package_frontier_slices
from api.pipeline.core.package_intake_shard_runner import build_package_intake_shards
from api.pipeline.core.shard_inventory_emitter import emit_shard_inventory_artifacts
from api.pipeline.core.shard_merge_coordinator import build_shard_merge_candidates
from api.pipeline.core.slice_execution_coordinator import build_slice_execution_map


def _package_input() -> dict:
    return {
        "package_id": "contoso-suite",
        "package_label": "Contoso Suite",
        "graph_epoch": "epoch-1",
        "dll_entries": [
            {"dll_id": "dll-c", "filename": "contoso_config.dll", "job_id": "job-c"},
            {"dll_id": "dll-r", "filename": "contoso_reporting.dll", "job_id": "job-r"},
            {"dll_id": "dll-p", "filename": "contoso_pricing.dll", "job_id": "job-p"},
            {"dll_id": "dll-g", "filename": "contoso_gateway.dll", "job_id": "job-g"},
            {"dll_id": "dll-e", "filename": "contoso_events.dll", "job_id": "job-e"},
        ],
    }


def _decomposition_chain() -> dict:
    shard_plan = build_package_intake_shards(_package_input(), target_shard_width=2)
    shard_inventory = emit_shard_inventory_artifacts(shard_plan)
    shard_inventory["shard_inventory_artifacts"][0]["candidate_hints"] = [
        {
            "hint_type": "init_group",
            "key": "licensed_bootstrap",
            "label": "Licensed Bootstrap",
            "member_dlls": ["contoso_config.dll", "contoso_reporting.dll"],
            "member_functions": ["CFG_OpenLicensedWindow", "RP_PrepareReservationReport"],
            "exported_state_artifacts": ["ticket"],
            "likely_downstream_consumers": ["CFG_RunCustomerSync"],
        },
        {
            "hint_type": "dependency_class",
            "key": "reporting_family",
            "label": "Reporting Family",
            "member_dlls": ["contoso_config.dll", "contoso_reporting.dll", "contoso_pricing.dll"],
            "member_clusters": ["cluster-config", "cluster-reporting"],
            "member_init_groups": ["init_group_candidate::contoso-suite::licensed_bootstrap"],
            "evidence_edges": ["workflow_handle->report_id", "quote_id->bundle_override"],
            "dependency_kind": "reporting_family",
        },
        {
            "hint_type": "frontier",
            "key": "frontier-a",
            "label": "Frontier A",
            "member_dlls": ["contoso_config.dll"],
        },
    ]
    shard_inventory["shard_inventory_artifacts"][1]["candidate_hints"] = [
        {
            "hint_type": "dependency_class",
            "key": "reporting_family",
            "label": "Reporting Family",
            "member_dlls": ["contoso_pricing.dll"],
            "member_clusters": ["cluster-pricing"],
            "member_init_groups": ["init_group_candidate::contoso-suite::licensed_bootstrap"],
            "evidence_edges": ["quote_id->bundle_override"],
            "dependency_kind": "reporting_family",
        }
    ]
    merge_output = build_shard_merge_candidates(shard_inventory)
    init_group_output = infer_initialization_groups(merge_output)
    dependency_class_output = infer_dependency_classes(
        merge_output,
        init_group_output=init_group_output,
    )
    frontier_slice_plan = build_package_frontier_slices(
        _package_input(),
        merge_output,
        init_group_output,
        dependency_class_output,
        max_slice_dlls=3,
    )
    execution_map = build_slice_execution_map(frontier_slice_plan)
    return {
        "shard_plan": shard_plan,
        "shard_inventory": shard_inventory,
        "merge_output": merge_output,
        "init_group_output": init_group_output,
        "dependency_class_output": dependency_class_output,
        "frontier_slice_plan": frontier_slice_plan,
        "execution_map": execution_map,
    }


def test_build_decomposition_inspection_surface_emits_dashboard_and_links_to_canonical_sources() -> None:
    chain = _decomposition_chain()

    result = build_decomposition_inspection_surface(**chain)

    dashboard = result["decomposition_dashboard"]
    assert dashboard["shard_count"] == 3
    assert dashboard["canonical_sources"]["frontier_slice_plan"] == "frontier_slices"
    assert dashboard["observer_verdict_summary"]["frontier_slice_boundedness"]["pass"] == 1


def test_build_decomposition_inspection_surface_reports_imported_to_active_ratio() -> None:
    chain = _decomposition_chain()

    result = build_decomposition_inspection_surface(**chain)

    dashboard = result["decomposition_dashboard"]
    assert dashboard["imported_truth_ids"] == ("contoso_events.dll", "contoso_gateway.dll")
    assert dashboard["imported_to_active_ratio"] == 0.67


def test_build_decomposition_inspection_surface_reports_contradiction_hotspots() -> None:
    chain = _decomposition_chain()
    chain["frontier_slice_plan"]["frontier_slices"][0]["observer_summary"]["status"] = "warn"
    chain["frontier_slice_plan"]["frontier_slices"][0]["observer_summary"]["warnings"] = [
        "bounded_expansion_deferred"
    ]
    chain["frontier_slice_plan"]["frontier_slice_observer_summaries"][0]["status"] = "warn"
    chain["frontier_slice_plan"]["frontier_slice_observer_summaries"][0]["warnings"] = [
        "bounded_expansion_deferred"
    ]

    result = build_decomposition_inspection_surface(**chain)

    ambiguity = result["merge_ambiguity_report"]["ambiguity_hotspots"]
    assert any(item["source"] == "frontier_slice_observer_summaries" for item in ambiguity)
    assert result["decomposition_dashboard"]["contradiction_hotspot_count"] >= 1


def test_build_decomposition_inspection_surface_respects_retention_boundaries() -> None:
    chain = _decomposition_chain()

    result = build_decomposition_inspection_surface(**chain)

    assert result["retention_boundaries"]["decomposition_dashboard"] == "summary_only"
    assert result["retention_boundaries"]["merge_ambiguity_report"] == "summary_only"
    assert result["retention_boundaries"]["slice_inspection_report"] == "summary_only"
    assert result["retention_boundaries"]["candidate_clusters"] == "canonical"
    assert result["retention_boundaries"]["frontier_slices"] == "canonical"
