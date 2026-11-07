from api.pipeline.core.shard_merge_coordinator import build_shard_merge_candidates


def _inventory_with_hints() -> dict:
    return {
        "package_id": "contoso-suite",
        "graph_epoch": "epoch-1",
        "shard_inventory_artifacts": [
            {
                "shard_id": "shard::contoso-suite::epoch-1::0",
                "dll_entries": [
                    {"dll_id": "dll-c", "filename": "contoso_config.dll", "job_id": "job-c"},
                    {"dll_id": "dll-r", "filename": "contoso_reporting.dll", "job_id": "job-r"},
                ],
                "candidate_hints": [
                    {
                        "hint_type": "init_group",
                        "key": "licensed_bootstrap",
                        "label": "Licensed Bootstrap",
                        "member_dlls": ["contoso_config.dll", "contoso_reporting.dll"],
                    },
                    {
                        "hint_type": "dependency_class",
                        "key": "reporting_family",
                        "label": "Reporting Family",
                        "member_dlls": ["contoso_reporting.dll"],
                        "member_clusters": ["cluster-reporting"],
                        "member_init_groups": ["init_group_candidate::contoso-suite::licensed"],
                        "evidence_edges": ["workflow_handle->report_id"],
                        "dependency_kind": "reporting_family",
                    },
                    {
                        "hint_type": "frontier",
                        "key": "frontier-a",
                        "label": "Frontier A",
                        "member_dlls": ["contoso_config.dll"],
                    },
                ],
            },
            {
                "shard_id": "shard::contoso-suite::epoch-1::1",
                "dll_entries": [
                    {"dll_id": "dll-p", "filename": "contoso_pricing.dll", "job_id": "job-p"},
                ],
                "candidate_hints": [
                    {
                        "hint_type": "init_group",
                        "key": "licensed_bootstrap",
                        "label": "Licensed Bootstrap Alt",
                        "member_dlls": ["contoso_pricing.dll"],
                    },
                    {
                        "hint_type": "dependency_class",
                        "key": "reporting_family",
                        "label": "Reporting Family",
                        "member_dlls": ["contoso_pricing.dll"],
                        "member_clusters": ["cluster-pricing"],
                        "member_init_groups": ["init_group_candidate::contoso-suite::licensed"],
                        "evidence_edges": ["quote_id->bundle_override"],
                        "dependency_kind": "reporting_family",
                        "supersedes_id": "dependency_class::contoso-suite::old",
                        "supersedes_reason": "merged_forward",
                    },
                ],
            },
        ],
    }


def test_build_shard_merge_candidates_emits_cluster_candidates_per_dll() -> None:
    merged = build_shard_merge_candidates(_inventory_with_hints())

    names = {row["key"] for row in merged["candidate_clusters"]}
    assert "contoso_config.dll" in names
    assert "contoso_reporting.dll" in names
    assert "contoso_pricing.dll" in names


def test_build_shard_merge_candidates_preserves_contradictions_for_divergent_init_group_labels() -> None:
    merged = build_shard_merge_candidates(_inventory_with_hints())

    init_group = merged["candidate_initialization_groups"][0]
    assert init_group["lifecycle"]["contradiction_state"] == "tentative"
    assert "label_divergence" in init_group["contradiction_notes"]
    assert merged["merge_contradiction_registry"][0]["reason"] == "label_divergence"


def test_build_shard_merge_candidates_preserves_supersedes_metadata_on_dependency_candidates() -> None:
    merged = build_shard_merge_candidates(_inventory_with_hints())

    dependency = merged["candidate_dependency_classes"][0]
    assert dependency["lifecycle"]["supersedes_id"] == "dependency_class::contoso-suite::old"
    assert dependency["lifecycle"]["supersedes_reason"] == "merged_forward"
    assert dependency["details"]["member_clusters"] == ["cluster-pricing", "cluster-reporting"]
    assert dependency["details"]["member_init_groups"] == ["init_group_candidate::contoso-suite::licensed"]
    assert dependency["details"]["evidence_edges"] == [
        "quote_id->bundle_override",
        "workflow_handle->report_id",
    ]
    assert dependency["details"]["dependency_kind"] == "reporting_family"


def test_build_shard_merge_candidates_emits_frontier_candidates_from_hints() -> None:
    merged = build_shard_merge_candidates(_inventory_with_hints())

    frontier = merged["initial_frontier_candidates"][0]
    assert frontier["key"] == "frontier-a"
    assert frontier["member_dlls"] == ("contoso_config.dll",)


def test_build_shard_merge_candidates_emits_merge_observers() -> None:
    merged = build_shard_merge_candidates(_inventory_with_hints())

    observer = merged["merge_observer_summaries"][0]
    assert observer["observer_name"] == "merge_coherence"
    assert observer["stable_identity_present"] is True
