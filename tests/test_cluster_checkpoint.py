from api.pipeline.core.cluster_checkpoint import (
    CLUSTER_CHECKPOINTS_BY_ID,
    CLUSTER_CHECKPOINT_SCHEMA_VERSION,
    CLUSTER_FORMATION_RULES,
    FIRST_CLUSTER_CHECKPOINTS,
    backfill_cluster_checkpoint_rows,
    build_cluster_checkpoint_snapshot,
    infer_cluster_checkpoint_id,
    validate_cluster_checkpoints,
)


def test_cluster_checkpoint_registry_covers_first_scaling_clusters() -> None:
    validate_cluster_checkpoints(FIRST_CLUSTER_CHECKPOINTS)

    assert "workflow_reservation_open_state" in CLUSTER_CHECKPOINTS_BY_ID
    assert "pricing_quote_lifecycle" in CLUSTER_CHECKPOINTS_BY_ID
    assert "config_approval_license" in CLUSTER_CHECKPOINTS_BY_ID
    assert "reporting_preview_render_export" in CLUSTER_CHECKPOINTS_BY_ID


def test_cluster_checkpoint_snapshot_preserves_compact_reuse_surface() -> None:
    snapshot = build_cluster_checkpoint_snapshot()

    assert snapshot
    pricing = next(row for row in snapshot if row["cluster_id"] == "pricing_quote_lifecycle")
    assert pricing["schema_version"] == CLUSTER_CHECKPOINT_SCHEMA_VERSION
    assert pricing["adjacent_prerequisite_state_groups"] == ["pricing_quote_bootstrap"]
    assert pricing["live_artifact_families"] == ["quote_id", "nonce"]
    assert pricing["active_seam"]
    assert pricing["gate_color"] == "red"
    assert pricing["latest_trusted_proof_jobs"] == []
    assert pricing["expected_next_move"]
    assert "business-rule and approval classifier" in pricing["observer_contracts"]
    assert pricing["formation_rules"] == list(CLUSTER_FORMATION_RULES)
    reporting = next(row for row in snapshot if row["cluster_id"] == "reporting_preview_render_export")
    assert "RP_SelectFormat" in reporting["consumer_functions"]
    assert "format_code" in reporting["live_artifact_families"]


def test_backfill_cluster_checkpoint_rows_refreshes_dynamic_fields() -> None:
    rows = {
        "workflow_reservation_open_state": {
            "cluster_id": "workflow_reservation_open_state",
            "gate_color": "red",
            "latest_trusted_proof_jobs": ["older-job"],
        }
    }

    merged = backfill_cluster_checkpoint_rows(
        rows,
        function_states={
            "WF_CreateReservation": {
                "status": "success",
                "working_call": {"pOutReservationId": "RSV-001"},
            }
        },
        source_job_id="current-job",
    )

    workflow = merged["workflow_reservation_open_state"]
    assert workflow["active_seam"]
    assert workflow["gate_color"] == "amber"
    assert workflow["latest_trusted_proof_jobs"] == ["older-job", "current-job"]
    assert workflow["expected_next_move"]


def test_infer_cluster_checkpoint_id_requires_unique_subset_match() -> None:
    assert infer_cluster_checkpoint_id(["PR_GetQuoteState", "PR_SealQuote"]) == "pricing_quote_lifecycle"
    assert infer_cluster_checkpoint_id(["RP_SelectFormat"]) == "reporting_preview_render_export"
    assert infer_cluster_checkpoint_id(["PR_GetQuoteState", "WF_GetWorkflowState"]) == ""
    assert infer_cluster_checkpoint_id([]) == ""
