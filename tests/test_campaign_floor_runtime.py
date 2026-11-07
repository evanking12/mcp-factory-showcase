from __future__ import annotations

from api.pipeline.runner import _campaign_entry_matches_targets, _resolve_campaign_entry_runtime
from api.routes.main import (
    _normalize_campaign_active_dll_targets,
    _normalize_campaign_per_dll_explore_settings,
)


def test_normalize_campaign_per_dll_explore_settings_keeps_floor_runtime_fields() -> None:
    normalized = _normalize_campaign_per_dll_explore_settings(
        {
            "per_dll_explore_settings": {
                "contoso_config.dll": {
                    "cluster_checkpoint_id": "config_approval_license",
                    "ceiling_functions": ["CFG_RunCustomerSync"],
                    "prerequisite_state_group_ids": ["config_licensed_ticket_bootstrap"],
                    "iteration_mode": "floor_to_ceiling",
                    "max_iteration_cycles": 3,
                }
            }
        }
    )

    config = normalized["contoso_config.dll"]
    assert config["cluster_checkpoint_id"] == "config_approval_license"
    assert config["ceiling_functions"] == ["CFG_RunCustomerSync"]
    assert config["prerequisite_state_group_ids"] == ["config_licensed_ticket_bootstrap"]
    assert config["iteration_mode"] == "floor_to_ceiling"
    assert config["max_iteration_cycles"] == 3


def test_resolve_campaign_entry_runtime_prefers_matching_dll_override() -> None:
    base_runtime = {
        "analysis_profile": "strict_dll",
        "iteration_mode": "single_pass",
        "cluster_checkpoint_id": "",
    }
    per_dll = {
        "contoso_reporting.dll": {
            "iteration_mode": "floor_to_ceiling",
            "cluster_checkpoint_id": "reporting_preview_render_export",
            "ceiling_functions": ["RP_SelectFormat"],
        }
    }

    resolved = _resolve_campaign_entry_runtime(
        base_runtime,
        per_dll,
        {"job_id": "job-report", "filename": "contoso_reporting.dll", "dll_id": "dll-report"},
        {"component_name": "contoso_reporting"},
    )

    assert resolved["analysis_profile"] == "strict_dll"
    assert resolved["iteration_mode"] == "floor_to_ceiling"
    assert resolved["cluster_checkpoint_id"] == "reporting_preview_render_export"
    assert resolved["ceiling_functions"] == ["RP_SelectFormat"]


def test_campaign_active_dll_targets_match_by_filename_and_component() -> None:
    targets = _normalize_campaign_active_dll_targets(
        {"active_dll_targets": ["contoso_config.dll", "contoso_reporting"]}
    )

    assert _campaign_entry_matches_targets(
        {"job_id": "job-config", "filename": "contoso_config.dll", "dll_id": "dll-config"},
        targets,
        {"component_name": "contoso_config"},
    )
    assert _campaign_entry_matches_targets(
        {"job_id": "job-report", "filename": "contoso_reporting.dll", "dll_id": "dll-report"},
        targets,
        {"component_name": "contoso_reporting"},
    )
    assert not _campaign_entry_matches_targets(
        {"job_id": "job-pricing", "filename": "contoso_pricing.dll", "dll_id": "dll-pricing"},
        targets,
        {"component_name": "contoso_pricing"},
    )
