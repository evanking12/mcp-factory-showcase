from api.pipeline.core.package_intake_shard_runner import build_package_intake_shards
from api.pipeline.core.shard_inventory_emitter import (
    ShardContradictionSummary,
    ShardInventoryArtifact,
    emit_shard_inventory_artifacts,
)


def _inventory_source() -> dict:
    return build_package_intake_shards(
        {
            "package_id": "contoso-suite",
            "package_label": "Contoso Suite",
            "graph_epoch": "epoch-1",
            "package_context": {"source_origin": "fixture"},
            "dll_entries": [
                {"dll_id": "dll-c", "filename": "contoso_config.dll", "job_id": "job-c"},
                {"dll_id": "dll-r", "filename": "contoso_reporting.dll", "job_id": "job-r"},
            ],
        },
        target_shard_width=1,
    )


def test_emit_shard_inventory_artifacts_writes_canonical_rows() -> None:
    artifacts = emit_shard_inventory_artifacts(_inventory_source())

    assert artifacts["schema_version"] == "1.0.0"
    assert len(artifacts["shard_inventory_artifacts"]) == 2
    first = artifacts["shard_inventory_artifacts"][0]
    assert first["shard_id"] == "shard::contoso-suite::epoch-1::0"
    assert first["observer_summary_id"] == "shard::contoso-suite::epoch-1::0::observer"
    assert first["contradiction_summary_id"] == "shard::contoso-suite::epoch-1::0::contradictions"
    assert first["confidence_placeholder"]["status"] == "bounded_placeholder"


def test_emit_shard_inventory_artifacts_keeps_contradictions_visible_even_when_empty() -> None:
    artifacts = emit_shard_inventory_artifacts(_inventory_source())

    first = artifacts["shard_contradiction_summaries"][0]
    assert first["contradiction_state"] == "none"
    assert first["contradiction_count"] == 0
    assert first["contradictions"] == ()


def test_emit_shard_inventory_artifacts_carries_observer_payloads_forward() -> None:
    artifacts = emit_shard_inventory_artifacts(_inventory_source())

    first = artifacts["shard_observer_summaries"][0]
    assert first["observer_name"] == "shard_validity"
    assert first["observer_summary_id"] == "shard::contoso-suite::epoch-1::0::observer"
    assert first["capture_valid"] is True


def test_emit_shard_inventory_artifacts_preserves_dll_entries_without_job_ids() -> None:
    shard_plan = build_package_intake_shards(
        {
            "package_id": "contoso-suite",
            "package_label": "Contoso Suite",
            "graph_epoch": "epoch-2",
            "dll_entries": [
                {"dll_id": "dll-c", "filename": "contoso_config.dll"},
                {"dll_id": "dll-r", "filename": "contoso_reporting.dll"},
            ],
        },
        target_shard_width=2,
    )

    artifacts = emit_shard_inventory_artifacts(shard_plan)

    entries = artifacts["shard_inventory_artifacts"][0]["dll_entries"]
    assert [row["filename"] for row in entries] == [
        "contoso_config.dll",
        "contoso_reporting.dll",
    ]
    assert all(row["job_id"] == "" for row in entries)


def test_shard_inventory_artifact_reader_is_backward_tolerant_for_legacy_dlls_field() -> None:
    restored = ShardInventoryArtifact.from_dict(
        {
            "shard_id": "shard::contoso-suite::epoch-1::0",
            "package_id": "contoso-suite",
            "graph_epoch": "epoch-1",
            "dlls": [{"dll_id": "dll-c", "filename": "contoso_config.dll", "job_id": "job-c"}],
            "intake_mode": "intake_only",
            "observer_summary_id": "obs-1",
            "contradiction_summary_id": "con-1",
            "confidence_placeholder": {"status": "tentative", "score": 0.2, "reason": "legacy"},
        }
    )

    assert restored.dll_count == 1
    assert restored.confidence_placeholder.status == "tentative"


def test_shard_contradiction_summary_reader_is_backward_tolerant_for_legacy_items_field() -> None:
    restored = ShardContradictionSummary.from_dict(
        {
            "shard_id": "shard::contoso-suite::epoch-1::0",
            "contradiction_state": "blocked",
            "items": [{"kind": "foreign-family"}],
        }
    )

    assert restored.contradiction_count == 1
    assert restored.contradictions == ({"kind": "foreign-family"},)
