from __future__ import annotations

import json
from pathlib import Path

from api.pipeline.core.checkpoint import (
    PipelineCheckpoint,
    apply_resume_boundary,
    load_checkpoint,
    mark_stage_complete,
    record_function_checkpoint,
    save_checkpoint,
)
from api.routes.main import _normalize_explore_runtime_settings


def test_save_and_load_checkpoint_stage_snapshot(monkeypatch) -> None:
    storage: dict[str, bytes] = {}

    def fake_upload(_container: str, blob_path: str, data: bytes) -> None:
        storage[blob_path] = data

    def fake_download(_container: str, blob_path: str) -> bytes:
        if blob_path not in storage:
            raise FileNotFoundError(blob_path)
        return storage[blob_path]

    monkeypatch.setattr("api.pipeline.core.checkpoint._upload_to_blob", fake_upload)
    monkeypatch.setattr("api.pipeline.core.checkpoint._download_blob", fake_download)

    checkpoint = PipelineCheckpoint(
        job_id="job-stage",
        sentinels={0xFFFFFFFC: "resource unavailable"},
        vocab={"customer_id": ["CUST-001"]},
        unlock_result={"unlocked": True},
        write_unlock_block="WRITE MODE ACTIVE",
        cluster_checkpoints={
            "workflow_reservation_open_state": {
                "cluster_id": "workflow_reservation_open_state",
                "state_story": "workflow state story",
            }
        },
    )
    record_function_checkpoint(
        checkpoint,
        "CP_ProcessPurchase",
        "success",
        working_call={"param_1": "CUST-001", "param_2": "PRO-SVC-ANNUAL"},
        stage="s02",
        verified=True,
    )
    mark_stage_complete(checkpoint, "s03_reconcile", {"reinterpreted": ["CP_ReserveStock"]})

    save_checkpoint(checkpoint)

    stage_blob = "job-stage/checkpoints/stage_snapshots/s03_reconcile.json"
    assert stage_blob in storage
    saved = json.loads(storage[stage_blob])
    assert saved["checkpoint_kind"] == "pipeline_stage_snapshot"
    assert saved["stage_snapshot_id"] == "s03_reconcile"
    assert saved["stages"]["s03_reconcile"]["completed"] is True

    loaded = load_checkpoint("job-resume", "job-stage", checkpoint_stage="s03_reconcile")
    assert loaded is not None
    assert loaded.vocab["customer_id"] == ["CUST-001"]
    assert "workflow_reservation_open_state" in loaded.cluster_checkpoints
    assert "s03_reconcile" not in loaded.stages
    assert loaded.functions["CP_ProcessPurchase"].status == "success"


def test_stage_snapshots_are_archival_boundaries_not_overwritten(monkeypatch) -> None:
    storage: dict[str, bytes] = {}

    def fake_upload(_container: str, blob_path: str, data: bytes) -> None:
        storage[blob_path] = data

    def fake_download(_container: str, blob_path: str) -> bytes:
        if blob_path not in storage:
            raise FileNotFoundError(blob_path)
        return storage[blob_path]

    monkeypatch.setattr("api.pipeline.core.checkpoint._upload_to_blob", fake_upload)
    monkeypatch.setattr("api.pipeline.core.checkpoint._download_blob", fake_download)

    checkpoint = PipelineCheckpoint(job_id="job-stage")
    mark_stage_complete(checkpoint, "s02_probe", {"checkpoint_boundary": "pre-reconcile"})
    save_checkpoint(checkpoint)
    first_snapshot = json.loads(storage["job-stage/checkpoints/stage_snapshots/s02_probe.json"])

    mark_stage_complete(checkpoint, "s03_reconcile", {"checkpoint_boundary": "post-reconcile"})
    save_checkpoint(checkpoint)
    second_snapshot = json.loads(storage["job-stage/checkpoints/stage_snapshots/s02_probe.json"])

    assert first_snapshot["stages"].keys() == second_snapshot["stages"].keys()
    assert "s03_reconcile" not in second_snapshot["stages"]


def test_apply_resume_boundary_clears_boundary_and_later_stages() -> None:
    checkpoint = PipelineCheckpoint(job_id="job-stage")
    mark_stage_complete(checkpoint, "s00_setup")
    mark_stage_complete(checkpoint, "s00_setup_baseline")
    mark_stage_complete(checkpoint, "s00_static_evidence")
    mark_stage_complete(checkpoint, "s00_admission_handoff")
    mark_stage_complete(checkpoint, "s01_unlock")
    mark_stage_complete(checkpoint, "s02_probe")
    mark_stage_complete(checkpoint, "s02_probe_ordering")
    mark_stage_complete(checkpoint, "s02_invocation_execution")
    mark_stage_complete(checkpoint, "s02_evidence_capture")
    mark_stage_complete(checkpoint, "s03_reconcile")

    resumed = apply_resume_boundary(checkpoint, "s02_probe")

    assert resumed is checkpoint
    assert "s00_setup" in checkpoint.stages
    assert "s00_setup_baseline" in checkpoint.stages
    assert "s00_static_evidence" in checkpoint.stages
    assert "s00_admission_handoff" in checkpoint.stages
    assert "s01_unlock" in checkpoint.stages
    assert "s02_probe" not in checkpoint.stages
    assert "s02_probe_ordering" not in checkpoint.stages
    assert "s02_invocation_execution" not in checkpoint.stages
    assert "s02_evidence_capture" not in checkpoint.stages
    assert "s03_reconcile" not in checkpoint.stages


def test_apply_resume_boundary_can_target_s02_substage() -> None:
    checkpoint = PipelineCheckpoint(job_id="job-stage")
    mark_stage_complete(checkpoint, "s01_unlock")
    mark_stage_complete(checkpoint, "s02_probe")
    mark_stage_complete(checkpoint, "s02_probe_ordering")
    mark_stage_complete(checkpoint, "s02_invocation_execution")
    mark_stage_complete(checkpoint, "s02_evidence_capture")
    mark_stage_complete(checkpoint, "s03_reconcile")

    resumed = apply_resume_boundary(checkpoint, "s02_invocation_execution")

    assert resumed is checkpoint
    assert "s01_unlock" in checkpoint.stages
    assert "s02_probe" in checkpoint.stages
    assert "s02_probe_ordering" in checkpoint.stages
    assert "s02_invocation_execution" not in checkpoint.stages
    assert "s02_evidence_capture" not in checkpoint.stages
    assert "s03_reconcile" not in checkpoint.stages


def test_apply_resume_boundary_can_target_s00_admission_handoff() -> None:
    checkpoint = PipelineCheckpoint(job_id="job-stage")
    mark_stage_complete(checkpoint, "s00_setup")
    mark_stage_complete(checkpoint, "s00_setup_baseline")
    mark_stage_complete(checkpoint, "s00_static_evidence")
    mark_stage_complete(checkpoint, "s00_admission_handoff")
    mark_stage_complete(checkpoint, "s01_unlock")

    resumed = apply_resume_boundary(checkpoint, "s00_admission_handoff")

    assert resumed is checkpoint
    assert "s00_setup" in checkpoint.stages
    assert "s00_setup_baseline" in checkpoint.stages
    assert "s00_static_evidence" in checkpoint.stages
    assert "s00_admission_handoff" not in checkpoint.stages
    assert "s01_unlock" not in checkpoint.stages


def test_apply_resume_boundary_can_target_s00_static_evidence() -> None:
    checkpoint = PipelineCheckpoint(job_id="job-stage")
    mark_stage_complete(checkpoint, "s00_setup")
    mark_stage_complete(checkpoint, "s00_setup_baseline")
    mark_stage_complete(checkpoint, "s00_static_evidence")
    mark_stage_complete(checkpoint, "s00_admission_handoff")

    resumed = apply_resume_boundary(checkpoint, "s00_static_evidence")

    assert resumed is checkpoint
    assert "s00_setup" in checkpoint.stages
    assert "s00_setup_baseline" in checkpoint.stages
    assert "s00_static_evidence" not in checkpoint.stages
    assert "s00_admission_handoff" not in checkpoint.stages


def test_apply_resume_boundary_can_target_s00_setup_baseline() -> None:
    checkpoint = PipelineCheckpoint(job_id="job-stage")
    mark_stage_complete(checkpoint, "s00_setup")
    mark_stage_complete(checkpoint, "s00_setup_baseline")
    mark_stage_complete(checkpoint, "s00_static_evidence")
    mark_stage_complete(checkpoint, "s00_admission_handoff")

    resumed = apply_resume_boundary(checkpoint, "s00_setup_baseline")

    assert resumed is checkpoint
    assert "s00_setup" in checkpoint.stages
    assert "s00_setup_baseline" not in checkpoint.stages
    assert "s00_static_evidence" not in checkpoint.stages
    assert "s00_admission_handoff" not in checkpoint.stages


def test_apply_resume_boundary_can_target_s05_verification_replay() -> None:
    checkpoint = PipelineCheckpoint(job_id="job-stage")
    mark_stage_complete(checkpoint, "s04_synthesis")
    mark_stage_complete(checkpoint, "s05_enrichment")
    mark_stage_complete(checkpoint, "s05_schema_backfill")
    mark_stage_complete(checkpoint, "s05_verification_replay")
    mark_stage_complete(checkpoint, "s05_read_to_write_chaining")
    mark_stage_complete(checkpoint, "s06_gaps")

    resumed = apply_resume_boundary(checkpoint, "s05_verification_replay")

    assert resumed is checkpoint
    assert "s04_synthesis" in checkpoint.stages
    assert "s05_enrichment" in checkpoint.stages
    assert "s05_schema_backfill" in checkpoint.stages
    assert "s05_verification_replay" not in checkpoint.stages
    assert "s05_read_to_write_chaining" not in checkpoint.stages
    assert "s06_gaps" not in checkpoint.stages


def test_checkpoint_preserves_s00_static_context_for_admission_resume(monkeypatch) -> None:
    storage: dict[str, bytes] = {}

    def fake_upload(_container: str, blob_path: str, data: bytes) -> None:
        storage[blob_path] = data

    def fake_download(_container: str, blob_path: str) -> bytes:
        if blob_path not in storage:
            raise FileNotFoundError(blob_path)
        return storage[blob_path]

    monkeypatch.setattr("api.pipeline.core.checkpoint._upload_to_blob", fake_upload)
    monkeypatch.setattr("api.pipeline.core.checkpoint._download_blob", fake_download)

    checkpoint = PipelineCheckpoint(
        job_id="job-stage",
        static_analysis_result={"binary_strings": {"ids_found": ["CUST-001"]}},
        static_enrichment={"callable_inventory": {"total": 2}},
        call_graph={"CS_Init": ["CS_Write"]},
        ghidra_data_types=[{"name": "PAYMENT_RECORD"}],
    )

    save_checkpoint(checkpoint)

    loaded = load_checkpoint("job-resume", "job-stage")

    assert loaded is not None
    assert loaded.static_analysis_result == {"binary_strings": {"ids_found": ["CUST-001"]}}
    assert loaded.static_enrichment == {"callable_inventory": {"total": 2}}
    assert loaded.call_graph == {"CS_Init": ["CS_Write"]}
    assert loaded.ghidra_data_types == [{"name": "PAYMENT_RECORD"}]


def test_normalize_explore_runtime_settings_preserves_checkpoint_stage() -> None:
    normalized = _normalize_explore_runtime_settings(
        {
            "explore_settings": {
                "checkpoint_id": "job-stage",
                "checkpoint_stage": "s03_reconcile",
            }
        }
    )

    assert normalized["checkpoint_id"] == "job-stage"
    assert normalized["checkpoint_stage"] == "s03_reconcile"


def test_normalize_explore_runtime_settings_preserves_cluster_seed_fields() -> None:
    normalized = _normalize_explore_runtime_settings(
        {
            "explore_settings": {
                "checkpoint_id": "job-stage",
                "checkpoint_stage": "s03_reconcile",
                "cluster_checkpoint_id": "workflow_reservation_open_state",
                "adjacent_cluster_id": "pricing_quote_lifecycle",
                "cluster_confidence_floor": 0.75,
            }
        }
    )

    assert normalized["cluster_checkpoint_id"] == "workflow_reservation_open_state"
    assert normalized["adjacent_cluster_id"] == "pricing_quote_lifecycle"
    assert normalized["cluster_confidence_floor"] == 0.75


def test_session_snapshot_surfaces_stage_snapshot_artifacts() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src = (repo_root / "api" / "routes" / "routes_session.py").read_text(encoding="utf-8")
    capture_src = (repo_root / "scripts" / "harness_lib" / "capture.py").read_text(encoding="utf-8")

    assert '"checkpoints/stage_snapshots/s03_reconcile.json"' in src
    assert '"checkpoints/stage_snapshots/s03_reconcile.json"' in capture_src
    assert '"checkpoints/stage_snapshots/s05_schema_backfill.json"' in src
    assert '"checkpoints/stage_snapshots/s05_schema_backfill.json"' in capture_src
    assert '"checkpoints/stage_snapshots/s05_verification_replay.json"' in src
    assert '"checkpoints/stage_snapshots/s05_verification_replay.json"' in capture_src
    assert '"checkpoints/stage_snapshots/s05_read_to_write_chaining.json"' in src
    assert '"checkpoints/stage_snapshots/s05_read_to_write_chaining.json"' in capture_src
