from api.pipeline.core.stress_package_decomposition_proof import StressScenario, run_stress_package_decomposition_proof


def _base_package_input() -> dict:
    return {
        "package_id": "enterprise-suite",
        "package_label": "Enterprise Suite",
        "graph_epoch": "epoch-enterprise",
        "dll_entries": [
            {"dll_id": "dll-a", "filename": "alpha.dll", "estimated_runtime_minutes": 4.0},
            {"dll_id": "dll-b", "filename": "beta.dll", "estimated_runtime_minutes": 4.0},
            {"dll_id": "dll-c", "filename": "gamma.dll", "estimated_runtime_minutes": 4.0},
            {"dll_id": "dll-d", "filename": "delta.dll", "estimated_runtime_minutes": 4.0},
            {"dll_id": "dll-e", "filename": "epsilon.dll", "estimated_runtime_minutes": 4.0},
            {"dll_id": "dll-f", "filename": "zeta.dll", "estimated_runtime_minutes": 4.0},
        ],
    }


def test_stress_proof_suite_surfaces_contradiction_and_overlap_pressure() -> None:
    contradiction_scenario = StressScenario(
        label="contradictory-merge",
        package_input=_base_package_input(),
        candidate_hints_by_shard={
            0: [
                {
                    "hint_type": "init_group",
                    "key": "licensing_bootstrap",
                    "label": "Licensing Bootstrap",
                    "member_dlls": ["alpha.dll", "beta.dll"],
                    "member_functions": ["ALPHA_Init", "BETA_Read"],
                    "exported_state_artifacts": ["license_ticket"],
                    "likely_downstream_consumers": ["ALPHA_Execute"],
                },
                {
                    "hint_type": "dependency_class",
                    "key": "reporting_family",
                    "label": "Reporting Family",
                    "member_dlls": ["alpha.dll", "beta.dll", "gamma.dll"],
                    "member_clusters": ["cluster-alpha", "cluster-beta"],
                    "member_init_groups": ["licensing_bootstrap"],
                    "evidence_edges": ["alpha->beta"],
                    "dependency_kind": "reporting_family",
                },
                {
                    "hint_type": "frontier",
                    "key": "frontier-a",
                    "label": "Frontier A",
                    "member_dlls": ["alpha.dll"],
                },
            ],
            1: [
                {
                    "hint_type": "init_group",
                    "key": "licensing_bootstrap",
                    "label": "Bootstrap Divergence",
                    "member_dlls": ["alpha.dll", "beta.dll", "gamma.dll"],
                    "member_functions": ["ALPHA_Init"],
                    "exported_state_artifacts": ["license_ticket"],
                    "likely_downstream_consumers": ["GAMMA_Execute"],
                }
            ],
        },
        expected_proof_status="pass",
        expected_contradiction_hotspots_min=1,
    )
    overlap_scenario = StressScenario(
        label="overlapping-groups-and-slices",
        package_input=_base_package_input(),
        candidate_hints_by_shard={
            0: [
                {
                    "hint_type": "init_group",
                    "key": "session_bootstrap",
                    "label": "Session Bootstrap",
                    "member_dlls": ["alpha.dll", "beta.dll"],
                    "member_functions": ["ALPHA_Open", "BETA_Read"],
                    "exported_state_artifacts": ["session_ticket"],
                    "likely_downstream_consumers": ["ALPHA_Commit"],
                },
                {
                    "hint_type": "dependency_class",
                    "key": "cross-cutting-state",
                    "label": "Cross Cutting State",
                    "member_dlls": ["alpha.dll", "beta.dll", "gamma.dll"],
                    "member_clusters": ["cluster-alpha", "cluster-beta", "cluster-gamma"],
                    "member_init_groups": ["session_bootstrap"],
                    "evidence_edges": ["alpha->gamma", "beta->gamma"],
                    "dependency_kind": "state_family",
                },
                {"hint_type": "frontier", "key": "frontier-a", "label": "Frontier A", "member_dlls": ["alpha.dll"]},
                {"hint_type": "frontier", "key": "frontier-b", "label": "Frontier B", "member_dlls": ["beta.dll"]},
                {"hint_type": "frontier", "key": "frontier-c", "label": "Frontier C", "member_dlls": ["gamma.dll"]},
            ]
        },
        max_slice_dlls=2,
        expected_proof_status="pass",
        expected_deferred_groups_min=1,
        expected_slice_count_min=3,
    )

    result = run_stress_package_decomposition_proof(
        scenarios=[contradiction_scenario, overlap_scenario],
    )

    assert result["status"] == "pass"
    by_label = {row["label"]: row for row in result["scenario_reports"]}
    assert by_label["contradictory-merge"]["contradiction_hotspot_count"] >= 1
    assert by_label["overlapping-groups-and-slices"]["checks"]["deferred_groups_min"]["ok"] is True


def test_stress_proof_suite_can_expect_budget_breach_failure() -> None:
    stressed_package = _base_package_input()
    for row in stressed_package["dll_entries"]:
        row["estimated_runtime_minutes"] = 11.0

    result = run_stress_package_decomposition_proof(
        scenarios=[
            StressScenario(
                label="uneven-economics",
                package_input=stressed_package,
                candidate_hints_by_shard={
                    0: [
                        {"hint_type": "frontier", "key": "frontier-a", "label": "Frontier A", "member_dlls": ["alpha.dll"]},
                    ]
                },
                target_shard_width=2,
                expected_proof_status="fail",
                expected_budget_breach_count_min=1,
            )
        ]
    )

    assert result["status"] == "pass"
    scenario = result["scenario_reports"][0]
    assert scenario["proof_summary"]["cheap_shard_economics_enforced"] is False
    assert scenario["checks"]["budget_breach_count_min"]["ok"] is True
