from pathlib import Path

from api.pipeline.core.reduced_package_decomposition_proof import run_reduced_package_decomposition_proof


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


def _candidate_hints_by_shard() -> dict:
    return {
        0: [
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
        ],
        1: [
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
        ],
    }


def test_run_reduced_package_decomposition_proof_passes_with_bounded_contoso_shape(tmp_path: Path) -> None:
    result = run_reduced_package_decomposition_proof(
        _package_input(),
        candidate_hints_by_shard=_candidate_hints_by_shard(),
        target_shard_width=2,
        max_slice_dlls=3,
        output_dir=str(tmp_path),
    )

    summary = result["proof_summary"]
    assert summary["status"] == "pass"
    assert summary["cheap_shard_economics_enforced"] is True
    assert summary["group_distinction_enforced"] is True
    assert summary["slice_boundedness_enforced"] is True
    assert summary["execution_lane_safety_enforced"] is True
    assert summary["observability_links_canonical_truth"] is True
    assert (tmp_path / "reduced-proof-summary.json").exists()
