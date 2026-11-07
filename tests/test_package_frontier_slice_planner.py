from api.pipeline.core.package_frontier_slice_planner import build_package_frontier_slices


def _package_input() -> dict:
    return {
        "package_id": "contoso-suite",
        "package_label": "Contoso Suite",
        "graph_epoch": "epoch-1",
        "dll_entries": [
            {"dll_id": "dll-c", "filename": "contoso_config.dll"},
            {"dll_id": "dll-r", "filename": "contoso_reporting.dll"},
            {"dll_id": "dll-p", "filename": "contoso_pricing.dll"},
            {"dll_id": "dll-g", "filename": "contoso_gateway.dll"},
            {"dll_id": "dll-e", "filename": "contoso_events.dll"},
        ],
    }


def _merge_output() -> dict:
    return {
        "package_id": "contoso-suite",
        "graph_epoch": "epoch-1",
        "candidate_clusters": [
            {
                "lifecycle": {"id": "cluster_candidate::contoso-suite::cfg"},
                "key": "contoso_config.dll",
            },
            {
                "lifecycle": {"id": "cluster_candidate::contoso-suite::rpt"},
                "key": "contoso_reporting.dll",
            },
            {
                "lifecycle": {"id": "cluster_candidate::contoso-suite::prc"},
                "key": "contoso_pricing.dll",
            },
        ],
        "initial_frontier_candidates": [
            {
                "lifecycle": {
                    "id": "frontier_slice::contoso-suite::epoch-1::0",
                    "object_type": "frontier_slice",
                    "package_id": "contoso-suite",
                    "graph_epoch": "epoch-1",
                    "source_ids": ("shard::contoso-suite::epoch-1::0",),
                    "contradiction_state": "none",
                },
                "key": "frontier-a",
                "label": "Frontier A",
                "member_dlls": ("contoso_config.dll",),
            }
        ],
    }


def _init_group_output() -> dict:
    return {
        "package_id": "contoso-suite",
        "graph_epoch": "epoch-1",
        "initialization_groups": [
            {
                "group_id": "init_group_candidate::contoso-suite::licensed",
                "member_dlls": ("contoso_config.dll", "contoso_reporting.dll"),
                "observer_summary": {"status": "pass"},
            }
        ],
    }


def _dependency_class_output() -> dict:
    return {
        "package_id": "contoso-suite",
        "graph_epoch": "epoch-1",
        "dependency_classes": [
            {
                "class_id": "dependency_class::contoso-suite::reporting",
                "member_dlls": (
                    "contoso_config.dll",
                    "contoso_reporting.dll",
                    "contoso_pricing.dll",
                ),
                "observer_summary": {"status": "pass"},
            }
        ],
    }


def test_build_package_frontier_slices_emits_narrow_slice_with_imported_truth() -> None:
    result = build_package_frontier_slices(
        _package_input(),
        _merge_output(),
        _init_group_output(),
        _dependency_class_output(),
        max_slice_dlls=3,
    )

    frontier_slice = result["frontier_slices"][0]
    observer = frontier_slice["observer_summary"]

    assert frontier_slice["active_dlls"] == (
        "contoso_config.dll",
        "contoso_pricing.dll",
        "contoso_reporting.dll",
    )
    assert frontier_slice["required_initialization_group_ids"] == (
        "init_group_candidate::contoso-suite::licensed",
    )
    assert frontier_slice["related_dependency_class_ids"] == (
        "dependency_class::contoso-suite::reporting",
    )
    assert result["imported_lower_floor_dlls"] == ("contoso_events.dll", "contoso_gateway.dll")
    assert observer["status"] == "pass"


def test_build_package_frontier_slices_defers_expansion_when_boundedness_would_break() -> None:
    result = build_package_frontier_slices(
        _package_input(),
        _merge_output(),
        _init_group_output(),
        _dependency_class_output(),
        max_slice_dlls=2,
    )

    frontier_slice = result["frontier_slices"][0]
    observer = frontier_slice["observer_summary"]

    assert frontier_slice["active_dlls"] == ("contoso_config.dll", "contoso_reporting.dll")
    assert frontier_slice["deferred_dependency_class_ids"] == (
        "dependency_class::contoso-suite::reporting",
    )
    assert observer["status"] == "warn"
    assert "bounded_expansion_deferred" in observer["warnings"]
    assert result["deferred_dependency_class_ids"] == (
        "dependency_class::contoso-suite::reporting",
    )


def test_build_package_frontier_slices_keeps_slice_semantics_distinct_from_groups() -> None:
    result = build_package_frontier_slices(
        _package_input(),
        _merge_output(),
        _init_group_output(),
        _dependency_class_output(),
        max_slice_dlls=3,
    )

    frontier_slice = result["frontier_slices"][0]
    assert frontier_slice["active_frontier_ids"] == ("frontier_slice::contoso-suite::epoch-1::0",)
    assert frontier_slice["required_cluster_ids"] == (
        "cluster_candidate::contoso-suite::cfg",
        "cluster_candidate::contoso-suite::prc",
        "cluster_candidate::contoso-suite::rpt",
    )
    assert frontier_slice["required_initialization_group_ids"] != frontier_slice["related_dependency_class_ids"]


def test_build_package_frontier_slices_fails_empty_frontier_candidate() -> None:
    merge_output = _merge_output()
    merge_output["initial_frontier_candidates"][0]["member_dlls"] = ()

    result = build_package_frontier_slices(
        _package_input(),
        merge_output,
        _init_group_output(),
        _dependency_class_output(),
        max_slice_dlls=3,
    )

    observer = result["frontier_slice_observer_summaries"][0]
    assert observer["status"] == "fail"
    assert "empty_slice" in observer["warnings"]


def test_build_package_frontier_slices_projects_interwoven_subjects_without_replacing_groups() -> None:
    result = build_package_frontier_slices(
        _package_input(),
        _merge_output(),
        _init_group_output(),
        _dependency_class_output(),
        max_slice_dlls=3,
        interwoven_projection={
            "interwoven_subjects": [
                {
                    "subject_id": "config_ticket_nonce_to_reporting_export",
                    "subject_kind": "producer_consumer",
                    "related_dlls": ("contoso_config.dll", "contoso_reporting.dll"),
                    "contradiction_state": "tentative",
                },
                {
                    "subject_id": "workflow_handle_nonce_commit_chain",
                    "subject_kind": "staged_chain",
                    "related_dlls": ("contoso_pricing.dll",),
                    "contradiction_state": "none",
                },
            ]
        },
    )

    frontier_slice = result["frontier_slices"][0]
    assert frontier_slice["interwoven_subject_ids"] == (
        "config_ticket_nonce_to_reporting_export",
        "workflow_handle_nonce_commit_chain",
    )
    assert frontier_slice["interwoven_attribution_present"] is True
    assert frontier_slice["interwoven_contradiction_summary"]["tentative"] == 1
