from api.pipeline.core.init_group_inference import infer_initialization_groups


def _merge_output_with_init_groups() -> dict:
    return {
        "package_id": "contoso-suite",
        "graph_epoch": "epoch-1",
        "candidate_initialization_groups": [
            {
                "lifecycle": {
                    "id": "init_group_candidate::contoso-suite::abc123",
                    "contradiction_state": "none",
                },
                "member_dlls": ("contoso_config.dll", "contoso_reporting.dll"),
                "details": {
                    "member_functions": ["CFG_OpenLicensedWindow", "RP_PrepareReservationReport"],
                    "exported_state_artifacts": ["ticket", "report_id"],
                    "likely_downstream_consumers": ["CFG_RunCustomerSync"],
                },
                "confidence_score": 0.2,
            }
        ],
    }


def test_infer_initialization_groups_builds_bounded_cross_dll_group() -> None:
    result = infer_initialization_groups(_merge_output_with_init_groups(), max_member_dlls=4)

    group = result["initialization_groups"][0]
    assert group["member_dlls"] == ("contoso_config.dll", "contoso_reporting.dll")
    assert group["exported_state_artifacts"] == ("ticket", "report_id")
    assert result["cross_dll_group_count"] == 1


def test_infer_initialization_groups_prevents_package_wide_blob_expansion() -> None:
    payload = _merge_output_with_init_groups()
    payload["candidate_initialization_groups"][0]["member_dlls"] = tuple(
        f"contoso_{index}.dll" for index in range(6)
    )

    result = infer_initialization_groups(payload, max_member_dlls=4)

    observer = result["init_group_observer_summaries"][0]
    assert observer["status"] == "fail"
    assert "oversized_group" in observer["warnings"]
    assert result["oversized_group_count"] == 1


def test_infer_initialization_groups_preserves_contradicted_candidates() -> None:
    payload = _merge_output_with_init_groups()
    payload["candidate_initialization_groups"][0]["lifecycle"]["contradiction_state"] = "contradicted"

    result = infer_initialization_groups(payload)

    group = result["initialization_groups"][0]
    observer = result["init_group_observer_summaries"][0]
    assert group["contradiction_state"] == "contradicted"
    assert observer["status"] == "fail"
    assert "contradiction_state_blocks_group" in observer["warnings"]


def test_infer_initialization_groups_warns_when_exported_state_or_consumers_missing() -> None:
    payload = _merge_output_with_init_groups()
    payload["candidate_initialization_groups"][0]["details"]["exported_state_artifacts"] = []

    result = infer_initialization_groups(payload)

    observer = result["init_group_observer_summaries"][0]
    assert observer["status"] == "warn"
    assert observer["exported_state_explicit"] is False
