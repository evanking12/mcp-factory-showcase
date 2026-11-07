import pytest

from api.pipeline.core.package_frontier_slice_planner import build_package_frontier_slices
from api.pipeline.core.slice_execution_coordinator import build_slice_execution_map


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
        ],
    }


def _merge_output() -> dict:
    return {
        "package_id": "contoso-suite",
        "graph_epoch": "epoch-1",
        "candidate_clusters": [
            {"lifecycle": {"id": "cluster_candidate::contoso-suite::cfg"}, "key": "contoso_config.dll"},
            {"lifecycle": {"id": "cluster_candidate::contoso-suite::rpt"}, "key": "contoso_reporting.dll"},
            {"lifecycle": {"id": "cluster_candidate::contoso-suite::prc"}, "key": "contoso_pricing.dll"},
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
                "label": "Frontier A",
                "member_dlls": ("contoso_config.dll",),
            }
        ],
    }


def _init_group_output() -> dict:
    return {
        "initialization_groups": [
            {
                "group_id": "init_group_candidate::contoso-suite::licensed",
                "member_dlls": ("contoso_config.dll", "contoso_reporting.dll"),
                "observer_summary": {"status": "pass"},
            }
        ]
    }


def _dependency_class_output() -> dict:
    return {
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
        ]
    }


def _frontier_slice_plan() -> dict:
    return build_package_frontier_slices(
        _package_input(),
        _merge_output(),
        _init_group_output(),
        _dependency_class_output(),
        max_slice_dlls=3,
    )


def test_build_slice_execution_map_maps_frontier_slice_into_serialized_execution_units() -> None:
    result = build_slice_execution_map(_frontier_slice_plan(), base_lane_id="lane-primary")

    assert result["execution_unit_count"] == 3
    assert [row["sequence_index"] for row in result["execution_units"]] == [0, 1, 2]
    assert {row["lane_id"] for row in result["execution_units"]} == {"lane-primary"}


def test_build_slice_execution_map_preserves_slice_attribution_and_runtime_shape() -> None:
    result = build_slice_execution_map(_frontier_slice_plan())

    unit = result["execution_units"][0]
    assert unit["source_frontier_slice_id"] == "frontier_slice::contoso-suite::epoch-1::0"
    assert unit["required_initialization_group_ids"] == (
        "init_group_candidate::contoso-suite::licensed",
    )
    assert unit["related_dependency_class_ids"] == (
        "dependency_class::contoso-suite::reporting",
    )
    assert unit["runtime_overrides"]["iteration_mode"] == "floor_to_ceiling"
    assert unit["runtime_overrides"]["floor_scope"] == "package"


def test_build_slice_execution_map_refuses_unsafe_live_parallelism() -> None:
    with pytest.raises(ValueError, match="does not permit unsafe live parallelism"):
        build_slice_execution_map(_frontier_slice_plan(), allow_live_parallelism=True)


def test_build_slice_execution_map_marks_multi_dll_slice_as_serialized_not_parallel() -> None:
    result = build_slice_execution_map(_frontier_slice_plan())

    observer = result["coordinator_observer_summaries"][0]
    assert observer["status"] == "pass"
    assert observer["serialized_lane_safe"] is True
    assert observer["live_parallelism_enabled"] is False
    assert "multi_dll_slice_serialized" in observer["warnings"]


def test_build_slice_execution_map_propagates_interwoven_attribution_to_units() -> None:
    plan = _frontier_slice_plan()
    plan["frontier_slices"][0]["interwoven_subject_ids"] = [
        "config_ticket_nonce_to_reporting_export",
        "workflow_handle_nonce_commit_chain",
    ]
    plan["frontier_slices"][0]["interwoven_contradiction_summary"] = {"tentative": 1, "none": 1}
    plan["frontier_slices"][0]["interwoven_attribution_present"] = True

    result = build_slice_execution_map(plan)

    unit = result["execution_units"][0]
    assert unit["interwoven_subject_ids"] == (
        "config_ticket_nonce_to_reporting_export",
        "workflow_handle_nonce_commit_chain",
    )
    assert unit["interwoven_attribution_present"] is True
    assert unit["runtime_overrides"]["interwoven_contradiction_summary"]["tentative"] == 1
