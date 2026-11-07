from __future__ import annotations

import json
import sys
from pathlib import Path

from api.analysis import cohesion
from api.infra import storage


SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from harness_lib import capture


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_write_session_manifests_writes_checkpoint_and_origin_metadata(tmp_path: Path) -> None:
    session = tmp_path / "session"
    (session / "checkpoints").mkdir(parents=True, exist_ok=True)
    (session / "checkpoints" / "latest.json").write_text("{}", encoding="utf-8")
    (session / "evidence" / "stage-01-pre-probe").mkdir(parents=True, exist_ok=True)
    (session / "evidence" / "stage-01-pre-probe" / "hints.txt").write_text("fixture", encoding="utf-8")

    capture._write_session_manifests(  # noqa: SLF001
        session,
        snapshot_profile="full",
        snapshot_mode="blob_only",
        manifest_entries={
            "session-meta.json": {"origin": "emitted"},
            "hints.txt": {"origin": "synthesized_summary"},
        },
    )

    manifest = json.loads((session / "session-manifest.json").read_text(encoding="utf-8"))
    checkpoints = json.loads((session / "checkpoints" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["snapshot_kind"] == "job"
    assert manifest["snapshot_mode"] == "blob_only"
    assert manifest["entries"]["hints.txt"]["origin"] == "synthesized_summary"
    assert "checkpoints/" in manifest["roots"]
    assert checkpoints["checkpoint_files"] == ["checkpoints/latest.json"]


def test_blob_only_snapshot_preserves_s00_s01_handoff_packet_aliases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    packet = {
        "coordination_decision": {
            "admission_quality": {
                "coordinator_review_seed": {"needs_review": False},
            },
        },
        "s01_targets": {"init_candidates": [], "write_candidates": []},
    }
    static_enrichment = {
        "schema_version": "1.0",
        "callable_inventory": {
            "summary": {"function_count": 1},
            "functions": [{"name": "SP_OpenOperatorSession", "role": "init"}],
        },
        "prerequisite_hints": [
            {
                "function": "SP_CommitRelease",
                "requires": ["SP_OpenOperatorSession"],
                "confidence": "medium",
            }
        ],
    }
    blobs = {
        "session-meta.json": _json_bytes({"job_id": "job-1"}),
        "stage-index.json": _json_bytes({}),
        "transition-index.json": _json_bytes({}),
        "cohesion-report.json": _json_bytes({}),
        "s01_handoff_packet.json": _json_bytes(packet),
        "static_enrichment.json": _json_bytes(static_enrichment),
        "vocab.json": _json_bytes({"error_codes": ["0x80070005"]}),
        "static_analysis.json": _json_bytes({"strings": ["Init"]}),
        "sentinel_calibration.json": _json_bytes({"sentinels": {"0x0": "ok"}}),
        "write_unlock_probe.json": _json_bytes({"attempts": []}),
        "prerequisite_state_machine.json": _json_bytes({"layers": [["SP_OpenOperatorSession"]]}),
        "explore_probe_log.json": _json_bytes({"entries": []}),
        "findings.json": _json_bytes({"findings": []}),
        "model_context_phase_01_probe_loop.txt": b"probe context",
        "probe_user_message_sample.txt": b"probe sample",
    }

    monkeypatch.setattr(storage, "_get_job_status", lambda job_id: {"job_id": job_id})
    monkeypatch.setattr(
        storage,
        "_download_blob",
        lambda container, blob_name: blobs.get(blob_name.removeprefix("job-1/")),
    )
    monkeypatch.setattr(cohesion, "emit_contract_artifacts", lambda job_id: None)

    missing_contract, manifest_entries = capture._materialize_snapshot_from_blobs(
        temp_dir=tmp_path / "session",
        job_id="job-1",
        profile="full",
    )

    session = tmp_path / "session"
    canonical_packet = session / "stage-00-setup" / "s01-handoff-packet.json"
    evidence_packet = session / "evidence" / "stage-00-setup" / "s01-handoff-packet.json"
    canonical_enrichment = session / "stage-00-setup" / "static-enrichment.json"
    evidence_enrichment = session / "evidence" / "stage-00-setup" / "static-enrichment.json"
    future_setup_sentinels = session / "evidence" / "stage-00a-setup-baseline" / "sentinel-calibration.json"
    future_setup_vocab = session / "evidence" / "stage-00a-setup-baseline" / "vocab.json"
    future_static_analysis = session / "evidence" / "stage-00b-static-evidence" / "static-analysis.json"
    future_static_enrichment = session / "evidence" / "stage-00b-static-evidence" / "static-enrichment.json"
    future_handoff_packet = session / "evidence" / "stage-00c-admission-handoff" / "s01-handoff-packet.json"
    future_probe_ordering = session / "evidence" / "stage-02a-probe-ordering" / "prerequisite-state-machine.json"
    future_invocation_context = session / "evidence" / "stage-02b-invocation-execution" / "stage-context.txt"
    future_evidence_findings = session / "evidence" / "stage-02c-evidence-capture" / "findings.json"
    assert missing_contract == []
    assert json.loads(canonical_packet.read_text(encoding="utf-8")) == packet
    assert json.loads(evidence_packet.read_text(encoding="utf-8")) == packet
    assert json.loads(canonical_enrichment.read_text(encoding="utf-8")) == static_enrichment
    assert json.loads(evidence_enrichment.read_text(encoding="utf-8")) == static_enrichment
    assert json.loads(future_setup_sentinels.read_text(encoding="utf-8")) == {"sentinels": {"0x0": "ok"}}
    assert json.loads(future_setup_vocab.read_text(encoding="utf-8")) == {"error_codes": ["0x80070005"]}
    assert json.loads(future_static_analysis.read_text(encoding="utf-8")) == {"strings": ["Init"]}
    assert json.loads(future_static_enrichment.read_text(encoding="utf-8")) == static_enrichment
    assert json.loads(future_handoff_packet.read_text(encoding="utf-8")) == packet
    assert json.loads(future_probe_ordering.read_text(encoding="utf-8")) == {"layers": [["SP_OpenOperatorSession"]]}
    assert future_invocation_context.read_text(encoding="utf-8") == "probe context"
    assert json.loads(future_evidence_findings.read_text(encoding="utf-8")) == {"findings": []}
    assert manifest_entries["stage-00-setup/s01-handoff-packet.json"] == {
        "origin": "emitted",
        "source_blob": "s01_handoff_packet.json",
    }
    assert manifest_entries["evidence/stage-00-setup/s01-handoff-packet.json"] == {
        "origin": "emitted",
        "source_blob": "s01_handoff_packet.json",
    }
    assert manifest_entries["stage-00-setup/static-enrichment.json"] == {
        "origin": "emitted",
        "source_blob": "static_enrichment.json",
    }
    assert manifest_entries["evidence/stage-00-setup/static-enrichment.json"] == {
        "origin": "emitted",
        "source_blob": "static_enrichment.json",
    }
    assert manifest_entries["evidence/stage-00a-setup-baseline/sentinel-calibration.json"]["source_blob"] == (
        "sentinel_calibration.json"
    )
    assert manifest_entries["evidence/stage-00a-setup-baseline/vocab.json"]["source_blob"] == "vocab.json"
    assert manifest_entries["evidence/stage-00b-static-evidence/static-analysis.json"]["source_blob"] == (
        "static_analysis.json"
    )
    assert manifest_entries["evidence/stage-00b-static-evidence/static-enrichment.json"]["source_blob"] == (
        "static_enrichment.json"
    )
    assert manifest_entries["evidence/stage-00c-admission-handoff/s01-handoff-packet.json"]["source_blob"] == (
        "s01_handoff_packet.json"
    )
    assert manifest_entries[
        "evidence/stage-02a-probe-ordering/prerequisite-state-machine.json"
    ]["source_blob"] == "prerequisite_state_machine.json"
    assert manifest_entries[
        "evidence/stage-02b-invocation-execution/stage-context.txt"
    ]["source_blob"] == "model_context_phase_01_probe_loop.txt"
    assert manifest_entries["evidence/stage-02c-evidence-capture/findings.json"]["source_blob"] == "findings.json"
    assert (session / "evidence" / "stage-01-pre-probe" / "vocab.json").exists()
    assert (session / "evidence" / "stage-01-pre-probe" / "static-analysis.json").exists()
    assert (session / "evidence" / "stage-01-pre-probe" / "sentinel-calibration.json").exists()


def test_blob_only_snapshot_waits_for_required_contract_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    blobs: dict[str, bytes] = {}

    def _required_contract_payloads() -> dict[str, bytes]:
        return {
            "session-meta.json": _json_bytes({"job_id": "job-1"}),
            "stage-index.json": _json_bytes({"version": "1.0", "stages": []}),
            "transition-index.json": _json_bytes({"version": "1.0", "transitions": []}),
            "cohesion-report.json": _json_bytes({"version": "1.0", "gates": {"hard_fail": False}}),
        }

    status_states = iter(
        [
            {"job_id": "job-1", "explore_span_state": "deferred"},
            {"job_id": "job-1", "explore_span_state": "done"},
        ]
    )

    monkeypatch.setattr(storage, "_get_job_status", lambda job_id: next(status_states, {"job_id": job_id, "explore_span_state": "done"}))
    def fake_download(_container, blob_name):
        key = blob_name.removeprefix("job-1/")
        if key in blobs:
            return blobs[key]
        raise FileNotFoundError(key)

    monkeypatch.setattr(storage, "_download_blob", fake_download)

    def fake_emit(job_id: str) -> None:
        blobs.update(_required_contract_payloads())

    monkeypatch.setattr(cohesion, "emit_contract_artifacts", fake_emit)
    monkeypatch.setattr(capture.time, "sleep", lambda *_args, **_kwargs: None)

    missing_contract, manifest_entries = capture._materialize_snapshot_from_blobs(
        temp_dir=tmp_path / "session",
        job_id="job-1",
        profile="full",
    )

    session = tmp_path / "session"
    readiness = json.loads(
        (session / "session-capture-contract-readiness.json").read_text(encoding="utf-8")
    )
    assert missing_contract == []
    assert readiness["ready"] is True
    assert readiness["emit_attempted"] is True
    assert manifest_entries["session-capture-contract-readiness.json"]["origin"] == "synthesized_summary"
    assert (session / "session-meta.json").exists()
    assert (session / "stage-index.json").exists()


def test_blob_only_snapshot_fails_closed_when_required_contract_artifacts_never_arrive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    blobs = {
        "session-meta.json": _json_bytes({"job_id": "job-1"}),
    }

    monkeypatch.setattr(
        storage,
        "_get_job_status",
        lambda job_id: {"job_id": job_id, "explore_span_state": "done"},
    )
    def fake_download(_container, blob_name):
        key = blob_name.removeprefix("job-1/")
        if key in blobs:
            return blobs[key]
        raise FileNotFoundError(key)

    monkeypatch.setattr(storage, "_download_blob", fake_download)
    monkeypatch.setattr(cohesion, "emit_contract_artifacts", lambda job_id: None)
    monkeypatch.setattr(capture.time, "sleep", lambda *_args, **_kwargs: None)

    missing_contract, manifest_entries = capture._materialize_snapshot_from_blobs(
        temp_dir=tmp_path / "session",
        job_id="job-1",
        profile="full",
    )

    session = tmp_path / "session"
    readiness = json.loads(
        (session / "session-capture-contract-readiness.json").read_text(encoding="utf-8")
    )
    assert "stage-index.json" in missing_contract
    assert "transition-index.json" in missing_contract
    assert "cohesion-report.json" in missing_contract
    assert readiness["ready"] is False
    assert not (session / "stage-index.json").exists()
    assert not (session / "transition-index.json").exists()
    assert "session-capture-contract-readiness.json" in manifest_entries


def test_blob_only_snapshot_does_not_synthesize_missing_static_enrichment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    packet = {
        "coordination_decision": {"flow_outcome": "advance"},
        "s01_targets": {"init_candidates": [], "write_candidates": []},
    }
    blobs = {
        "session-meta.json": _json_bytes({"job_id": "job-1"}),
        "stage-index.json": _json_bytes({}),
        "transition-index.json": _json_bytes({}),
        "cohesion-report.json": _json_bytes({}),
        "s01_handoff_packet.json": _json_bytes(packet),
    }

    monkeypatch.setattr(storage, "_get_job_status", lambda job_id: {"job_id": job_id})
    monkeypatch.setattr(
        storage,
        "_download_blob",
        lambda container, blob_name: blobs.get(blob_name.removeprefix("job-1/")),
    )
    monkeypatch.setattr(cohesion, "emit_contract_artifacts", lambda job_id: None)

    missing_contract, manifest_entries = capture._materialize_snapshot_from_blobs(
        temp_dir=tmp_path / "session",
        job_id="job-1",
        profile="full",
    )

    session = tmp_path / "session"
    assert missing_contract == []
    assert (session / "stage-00-setup" / "s01-handoff-packet.json").exists()
    assert not (session / "stage-00-setup" / "static-enrichment.json").exists()
    assert not (session / "evidence" / "stage-00-setup" / "static-enrichment.json").exists()
    assert not (session / "evidence" / "stage-00b-static-evidence" / "static-enrichment.json").exists()
    assert "stage-00-setup/static-enrichment.json" not in manifest_entries
    assert "evidence/stage-00-setup/static-enrichment.json" not in manifest_entries
    assert "evidence/stage-00b-static-evidence/static-enrichment.json" not in manifest_entries


def test_blob_only_snapshot_preserves_winning_init_sequence_contract_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    winning_sequence = {
        "resolved_at": "mc6-llm-code-reasoning",
        "sequence": [{"fn": "SP_Init", "args": {}}],
        "write_fn_tested": "SP_CommitRelease",
        "write_fn_args": {"reservation_handle": "RES-001"},
    }
    blobs = {
        "session-meta.json": _json_bytes({"job_id": "job-1"}),
        "stage-index.json": _json_bytes({}),
        "transition-index.json": _json_bytes({}),
        "cohesion-report.json": _json_bytes({}),
        "winning_init_sequence.json": _json_bytes(winning_sequence),
    }

    monkeypatch.setattr(storage, "_get_job_status", lambda job_id: {"job_id": job_id})
    monkeypatch.setattr(
        storage,
        "_download_blob",
        lambda container, blob_name: blobs.get(blob_name.removeprefix("job-1/")),
    )
    monkeypatch.setattr(cohesion, "emit_contract_artifacts", lambda job_id: None)

    missing_contract, manifest_entries = capture._materialize_snapshot_from_blobs(
        temp_dir=tmp_path / "session",
        job_id="job-1",
        profile="full",
    )

    session = tmp_path / "session"
    legacy_path = session / "mc-decisions" / "winning-init-sequence.json"
    contract_path = session / "evidence" / "mc-decisions" / "winning-init-sequence.json"
    assert missing_contract == []
    assert json.loads(legacy_path.read_text(encoding="utf-8")) == winning_sequence
    assert json.loads(contract_path.read_text(encoding="utf-8")) == winning_sequence
    assert manifest_entries["mc-decisions/winning-init-sequence.json"] == {
        "origin": "emitted",
        "source_blob": "winning_init_sequence.json",
    }
    assert manifest_entries["evidence/mc-decisions/winning-init-sequence.json"] == {
        "origin": "emitted",
        "source_blob": "winning_init_sequence.json",
    }
