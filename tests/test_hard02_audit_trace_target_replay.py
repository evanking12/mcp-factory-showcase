from __future__ import annotations

import json
from pathlib import Path

from scripts.regression import replay_hard02_audit_trace_target as replay


PREDECESSORS = [
    "session_bootstrap",
    "reservation_stage",
    "attestation_stage",
    "invoice_sync",
    "entitlement_sync",
    "settlement_reconcile",
]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _source_proof_root(tmp_path: Path) -> Path:
    root = tmp_path / "source-proof"
    records = []
    for index, target in enumerate(PREDECESSORS, start=1):
        run_dir = root / "runs" / f"{index:02d}-{target}"
        findings = []
        if target == "settlement_reconcile":
            findings = [
                {
                    "function": "SP_InvalidateStaleAttestedRelease",
                    "status_canonical": "verified_success",
                    "working_call": {
                        "attestation_packet": "sp-att-ORD-20040301-0042-2500-gate-packet",
                        "attestation_epoch": 20260408,
                        "out_stale_attestation_token": "sp-att-stale-35",
                        "out_stale_reason": "freshness_gap|epoch=20260408|packet=sp-att-ORD-20040301-0042-25",
                    },
                }
            ]
        _write_json(run_dir / "run_result.json", {"target": target, "status": "ok"})
        _write_json(run_dir / "findings.json", findings)
        records.append(
            {
                "target": target,
                "job_id": f"job-{target}",
                "status": "ok",
                "phase": "done",
                "authoritative_proving": True,
                "run_dir": str(run_dir),
                "valid_run": True,
                "measurement_control_plane": {"safe_to_compare": True},
            }
        )
    _write_json(root / "compiled-ingest-summary.json", {"run_records": records})
    return root


def test_missing_source_proof_root_fails_closed(tmp_path: Path) -> None:
    result = replay.replay_hard02_audit_trace_target(
        source_proof_root=tmp_path / "missing",
        output_root=tmp_path / "out",
    )

    assert result["blocking_signal"] == "trusted_predecessor_boundary_unavailable"
    assert result["claim_ceiling"] == "target_local_replay_only"
    assert result["product_green_claimed"] is False
    assert (tmp_path / "out" / "target-local-replay-result.json").exists()


def test_trusted_predecessor_extraction_finds_settlement_boundary(tmp_path: Path) -> None:
    root = _source_proof_root(tmp_path)

    boundary = replay.extract_trusted_predecessor_boundary(root)

    assert boundary["valid"] is True
    assert boundary["last_trusted_boundary"] == "08-settlement_reconcile"
    assert boundary["prior_job_id"] == "job-settlement_reconcile"
    assert boundary["job_ids_by_target"]["settlement_reconcile"] == "job-settlement_reconcile"
    assert boundary["settlement_stale_outputs"]["stale_attestation_token"] == "sp-att-stale-35"


def test_classification_detects_forwarding_missing(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    _write_json(
        audit_dir / "findings.json",
        [{"function": "SP_RecordStaleAttestationInvalidation", "status_canonical": "functional_precondition_unmet"}],
    )

    result = replay.classify_audit_trace_result(
        audit_run_dir=audit_dir,
        boundary={
            "settlement_stale_outputs": {
                "stale_attestation_token": "sp-att-stale-35",
                "stale_reason": "freshness_gap|epoch=20260408",
            }
        },
        record={"authoritative_proving": False},
    )

    assert result["blocking_signal"] == "stale_attestation_forwarding_missing"
    assert result["classification"] == "family_blocker"


def test_classification_detects_object_state_precondition(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    _write_json(
        audit_dir / "findings.json",
        [
            {
                "function": "SP_RecordStaleAttestationInvalidation",
                "status_canonical": "functional_precondition_unmet",
                "working_call": {
                    "stale_attestation_token": "sp-att-stale-35",
                    "stale_reason": "freshness_gap|epoch=20260408",
                },
            }
        ],
    )

    result = replay.classify_audit_trace_result(
        audit_run_dir=audit_dir,
        boundary={
            "settlement_stale_outputs": {
                "stale_attestation_token": "sp-att-stale-35",
                "stale_reason": "freshness_gap|epoch=20260408",
            }
        },
        record={"authoritative_proving": False},
    )

    assert result["blocking_signal"] == "stale_attestation_object_state_precondition_unmet"


def test_classification_accepts_verified_recovered_s07_artifacts(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    _write_json(
        audit_dir / "findings.json",
        [
            {
                "function": "SP_RecordStaleAttestationInvalidation",
                "status_canonical": "verified_success",
                "working_call": {
                    "stale_attestation_token": "sp-att-stale-35",
                    "stale_reason": "freshness_gap|epoch=20260408",
                    "out_audit_token": "sp-audit-stale-attestation",
                },
            }
        ],
    )

    result = replay.classify_audit_trace_result(
        audit_run_dir=audit_dir,
        boundary={
            "settlement_stale_outputs": {
                "stale_attestation_token": "sp-att-stale-35",
                "stale_reason": "freshness_gap|epoch=20260408",
            }
        },
        record={"authoritative_proving": False},
        artifact_recovery={"s07_finalize_completed": True, "findings_recovered": True, "source": "local_job_artifact_store"},
    )

    assert result["blocking_signal"] == "checkpoint_target_replay_green"
    assert result["terminalization_recovered"] is True
    assert result["authority_present"] is True


def test_recover_target_local_artifacts_from_job_store(tmp_path: Path, monkeypatch) -> None:
    job_store = tmp_path / "job-store" / "job-1"
    _write_json(
        job_store / "findings.json",
        [
            {
                "function": "SP_RecordStaleAttestationInvalidation",
                "status_canonical": "verified_success",
                "working_call": {"stale_attestation_token": "sp-att-stale-35"},
            }
        ],
    )
    _write_json(job_store / "checkpoints" / "s07_finalize.json", {"completed": True})
    _write_json(job_store / "evidence" / "stage-02c-evidence-capture" / "probe-log.json", {"args": {}})
    monkeypatch.setattr(replay, "_job_artifact_dir", lambda job_id: job_store)

    run_dir = tmp_path / "run"
    recovery = replay.recover_target_local_artifacts_from_job_store(run_dir=run_dir, job_id="job-1")

    assert recovery["recovered"] is True
    assert recovery["s07_finalize_completed"] is True
    assert recovery["findings_recovered"] is True
    assert (run_dir / "findings.json").exists()
    assert (run_dir / "target-local-artifact-recovery.json").exists()


def test_target_local_replay_writes_diagnostic_result_without_mutating_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _source_proof_root(tmp_path)
    before = (root / "compiled-ingest-summary.json").read_text(encoding="utf-8")
    dll = tmp_path / "spectrum_audit_trace.dll"
    dll.write_bytes(b"dll")

    monkeypatch.setattr(replay, "ensure_spectrum_compiled_package_built", lambda: {})
    monkeypatch.setattr(
        replay,
        "ordered_spectrum_compiled_hard02_targets",
        lambda manifest: [{"target_name": "audit_trace", "source_path": str(dll)}],
    )
    monkeypatch.setattr(replay, "resolve_api_url", lambda *args, **kwargs: ("http://api.test", "api_ok:test", "explicit"))
    monkeypatch.setattr(replay, "ensure_local_bridge_freshness", lambda *args, **kwargs: {"freshness_verdict": "fresh"})
    monkeypatch.setattr(
        replay,
        "ensure_local_api_freshness",
        lambda *args, **kwargs: {"freshness_verdict": "fresh", "restart_performed": False},
    )
    monkeypatch.setattr(replay, "verify_bridge_identity", lambda *args, **kwargs: (True, "bridge_ok:test"))
    monkeypatch.setattr(replay, "ensure_strict_local_lane_preflight", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(replay, "collect_runner_identity", lambda **kwargs: {"runner_name": kwargs["runner_name"]})
    monkeypatch.setattr(replay, "collect_api_identity", lambda *args, **kwargs: {"component": "api"})
    monkeypatch.setattr(replay, "collect_bridge_identity", lambda *args, **kwargs: {"component": "bridge"})
    monkeypatch.setattr(replay, "fetch_api_readiness", lambda *args, **kwargs: {"ready": True})
    monkeypatch.setattr(replay, "fetch_bridge_readiness", lambda *args, **kwargs: {"ready": True, "capabilities": ["analyze"]})
    monkeypatch.setattr(replay, "build_bridge_candidates_from_config", lambda **kwargs: [{"candidate_id": "bridge-1"}])
    monkeypatch.setattr(
        replay,
        "build_bridge_candidate_registry_packet",
        lambda **kwargs: {"light": "green", "reason_code": "green_lane_admitted", "selected_candidate_id": "bridge-1"},
    )
    monkeypatch.setattr(replay, "selected_bridge_url_from_registry", lambda packet: "http://bridge.test")
    monkeypatch.setattr(replay, "control_plane_allows_run", lambda packet: True)
    monkeypatch.setattr(replay, "bridge_stream_health_from_run_record", lambda record: {"status": "coherent"})
    monkeypatch.setattr(replay, "apply_control_plane_to_run_record", lambda run_dir, record, control_plane: record)
    monkeypatch.setattr(
        replay,
        "write_enterprise_survivability_summary",
        lambda **kwargs: {
            "case_id": "hard-02",
            "claim_ceiling": "enterprise_survivability_only",
            "safe_to_compare": False,
            "targets": [{"target": "audit_trace", "state": "non_comparable", "safe_to_compare": False}],
        },
    )

    def fake_run_one(*args, **kwargs):
        run_dir = Path(args[2])
        _write_json(
            run_dir / "findings.json",
            [{"function": "SP_RecordStaleAttestationInvalidation", "status_canonical": "functional_precondition_unmet"}],
        )
        _write_json(run_dir / "run_result.json", {"target": "audit_trace", "status": "failed", "phase": "done"})
        _write_json(run_dir / "run-authority.json", {"authority_level": "non_authoritative", "authoritative_proving": False})
        return {
            "target": "audit_trace",
            "job_id": "job-audit-replay",
            "status": "failed",
            "phase": "done",
            "authoritative_proving": False,
        }

    monkeypatch.setattr(replay, "run_one", fake_run_one)

    result = replay.replay_hard02_audit_trace_target(
        source_proof_root=root,
        output_root=tmp_path / "out",
    )

    assert (root / "compiled-ingest-summary.json").read_text(encoding="utf-8") == before
    assert result["claim_ceiling"] == "target_local_replay_only"
    assert result["product_green_claimed"] is False
    assert result["blocking_signal"] == "stale_attestation_forwarding_missing"
    assert (tmp_path / "out" / "proof-artifact-summary.json").exists()
    assert json.loads((tmp_path / "out" / "proof-artifact-summary.json").read_text(encoding="utf-8"))[
        "product_green_claimed"
    ] is False
