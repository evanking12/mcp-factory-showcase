from api.pipeline.core.dependency_class_inference import infer_dependency_classes


def _merge_output_with_dependency_classes() -> dict:
    return {
        "package_id": "contoso-suite",
        "graph_epoch": "epoch-1",
        "candidate_dependency_classes": [
            {
                "lifecycle": {
                    "id": "dependency_class::contoso-suite::dep123",
                    "contradiction_state": "none",
                },
                "key": "reporting_family",
                "member_dlls": (
                    "contoso_config.dll",
                    "contoso_reporting.dll",
                    "contoso_pricing.dll",
                ),
                "details": {
                    "dependency_kind": "reporting_family",
                    "member_clusters": ["cluster-reporting", "cluster-pricing"],
                    "member_init_groups": ["init_group_candidate::contoso-suite::licensed"],
                    "member_functions": ["RP_PrepareReservationReport", "PR_ApplyBundleOverride"],
                    "evidence_edges": ["workflow_handle->report_id", "quote_id->bundle_override"],
                },
                "confidence_score": 0.2,
            }
        ],
    }


def _init_group_output() -> dict:
    return {
        "initialization_groups": [
            {
                "group_id": "init_group_candidate::contoso-suite::licensed",
                "member_dlls": ("contoso_config.dll", "contoso_reporting.dll"),
            }
        ]
    }


def test_infer_dependency_classes_builds_distinct_cross_dll_class() -> None:
    result = infer_dependency_classes(
        _merge_output_with_dependency_classes(),
        init_group_output=_init_group_output(),
        max_member_dlls=6,
    )

    dependency_class = result["dependency_classes"][0]
    observer = result["dependency_class_observer_summaries"][0]

    assert dependency_class["dependency_kind"] == "reporting_family"
    assert dependency_class["member_init_groups"] == ("init_group_candidate::contoso-suite::licensed",)
    assert dependency_class["evidence_edges"] == ("workflow_handle->report_id", "quote_id->bundle_override")
    assert observer["status"] == "pass"
    assert result["cross_dll_class_count"] == 1


def test_infer_dependency_classes_fails_when_candidate_collapses_into_init_group() -> None:
    payload = _merge_output_with_dependency_classes()
    payload["candidate_dependency_classes"][0]["member_dlls"] = (
        "contoso_config.dll",
        "contoso_reporting.dll",
    )
    payload["candidate_dependency_classes"][0]["details"] = {
        "dependency_kind": "licensed_bootstrap",
        "member_clusters": [],
        "member_init_groups": [],
        "member_functions": ["CFG_OpenLicensedWindow"],
        "evidence_edges": [],
    }

    result = infer_dependency_classes(
        payload,
        init_group_output=_init_group_output(),
    )

    observer = result["dependency_class_observer_summaries"][0]
    assert observer["status"] == "fail"
    assert "collapses_into_init_group" in observer["warnings"]
    assert result["collapsed_init_group_count"] == 1


def test_infer_dependency_classes_fails_when_candidate_collapses_into_cluster() -> None:
    payload = _merge_output_with_dependency_classes()
    payload["candidate_dependency_classes"][0]["member_dlls"] = ("contoso_reporting.dll",)
    payload["candidate_dependency_classes"][0]["details"] = {
        "dependency_kind": "reporting_cluster",
        "member_clusters": ["cluster-reporting"],
        "member_init_groups": [],
        "member_functions": ["RP_PrepareReservationReport"],
        "evidence_edges": [],
    }

    result = infer_dependency_classes(
        payload,
        init_group_output=_init_group_output(),
    )

    observer = result["dependency_class_observer_summaries"][0]
    assert observer["status"] == "fail"
    assert "collapses_into_cluster" in observer["warnings"]
    assert result["collapsed_cluster_count"] == 1


def test_infer_dependency_classes_prevents_package_wide_blob_expansion() -> None:
    payload = _merge_output_with_dependency_classes()
    payload["candidate_dependency_classes"][0]["member_dlls"] = tuple(
        f"contoso_{index}.dll" for index in range(8)
    )

    result = infer_dependency_classes(payload, max_member_dlls=6)

    observer = result["dependency_class_observer_summaries"][0]
    assert observer["status"] == "fail"
    assert "oversized_dependency_class" in observer["warnings"]
    assert result["oversized_class_count"] == 1


def test_infer_dependency_classes_preserves_contradicted_candidates() -> None:
    payload = _merge_output_with_dependency_classes()
    payload["candidate_dependency_classes"][0]["lifecycle"]["contradiction_state"] = "contradicted"

    result = infer_dependency_classes(payload, init_group_output=_init_group_output())

    dependency_class = result["dependency_classes"][0]
    observer = result["dependency_class_observer_summaries"][0]
    assert dependency_class["contradiction_state"] == "contradicted"
    assert observer["status"] == "fail"
    assert "contradiction_state_blocks_class" in observer["warnings"]
