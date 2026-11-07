from __future__ import annotations

import json

from fastapi.testclient import TestClient

from api.routes import main


def _artifact_map() -> dict[str, bytes]:
    return {
        "job-abc/run-validity.json": json.dumps(
            {
                "valid": False,
                "reasons": ["cohesion.hard_fail"],
                "gate_results": {"hard_fail_clear": False},
            }
        ).encode("utf-8"),
        "job-abc/kpi_run.json": json.dumps(
            {
                "totals": {
                    "verified_success": 8,
                    "failure": 0,
                    "unknown": 4,
                }
            }
        ).encode("utf-8"),
        "job-abc/cohesion-report.json": json.dumps(
            {
                "gates": {"hard_fail": True},
                "failed_stages": ["S-00", "S-02", "S-07"],
                "failed_transitions": ["T-04", "T-16"],
            }
        ).encode("utf-8"),
        "job-abc/macro_verdict.json": json.dumps({"verdict": "review"}).encode("utf-8"),
        "job-abc/validation-report.json": json.dumps(
            {
                "summary": {
                    "checked": 8,
                    "verified_1to1": 0,
                    "mismatch": 0,
                    "wrapper_unavailable": 6,
                    "direct_error": 2,
                    "wrapper_error": 0,
                    "skipped": 5,
                },
                "wrapper_source": "behavioral-spec.py",
                "wrapper_load_error": "wrapper_class_not_found",
                "entries": [{"function": "CP_GetVersion"}],
            }
        ).encode("utf-8"),
        "job-abc/stage-index.json": json.dumps(
            {
                "stages": [
                    {"id": "S-00", "status": "failed", "errors": ["missing schema-t0"]},
                    {"id": "S-03", "status": "completed", "errors": []},
                ]
            }
        ).encode("utf-8"),
        "job-abc/transition-index.json": json.dumps(
            {
                "transitions": [
                    {"id": "T-04", "status": "fail", "producer_stage": "S-00", "consumer_stage": "S-02", "reason": "static hints missing"},
                    {"id": "T-16", "status": "fail", "producer_stage": "S-00", "consumer_stage": "S-07", "reason": "schema evolution missing"},
                ]
            }
        ).encode("utf-8"),
        "job-abc/artifact-index.json": json.dumps(
            {
                "file_count": 71,
                "canonical_map": [{"canonical": "validation-report.json", "aliases": []}],
            }
        ).encode("utf-8"),
        "job-abc/human/l3-forensics-index.json": json.dumps(
            {
                "key_artifacts": [
                    "cohesion-report.json",
                    "stage-index.json",
                    "transition-index.json",
                    "validation-report.json",
                ]
            }
        ).encode("utf-8"),
        "job-abc/session-manifest.json": json.dumps({"version": "1.0"}).encode("utf-8"),
    }


def _install_artifacts(
    monkeypatch,
    *,
    artifacts: dict[str, bytes] | None = None,
    findings: list[dict[str, object]] | None = None,
    job_status: dict[str, object] | None = None,
) -> None:
    artifact_store = dict(artifacts or _artifact_map())

    def fake_download(_container: str, blob_name: str):
        if blob_name in artifact_store:
            return artifact_store[blob_name]
        raise FileNotFoundError(blob_name)

    monkeypatch.setattr(main, "_download_blob", fake_download)
    monkeypatch.setattr(
        main,
        "_load_findings",
        lambda _job_id: findings if findings is not None else [
            {
                "function": "CP_ReserveStock",
                "status_canonical": "failure",
                "finding": "Missing prerequisite handle lineage",
                "first_blocking_stage": "S-02",
                "blocker_family": "state lineage",
            }
        ],
    )
    monkeypatch.setattr(
        main,
        "_get_job_status",
        lambda _job_id: job_status if job_status is not None else {
            "job_id": "job-abc",
            "component_name": "contoso_payments",
            "explore_phase": "done",
            "status": "done",
        },
    )
    monkeypatch.setattr(main, "_find_saved_session_dir", lambda _job_id: None)


def test_verdict_hierarchy_route_returns_side_by_side_contract(monkeypatch) -> None:
    _install_artifacts(monkeypatch)
    client = TestClient(main.app)
    response = client.get("/api/jobs/job-abc/verdict-hierarchy")
    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-abc"
    assert "operator_view" in payload
    assert "analysis_view" in payload
    assert "source_artifacts" in payload
    assert "derived_from" in payload
    assert "validation_completeness" in payload["layers"]
    assert payload["conflicts"]


def test_validation_status_route_classifies_partial_wrapper_runs(monkeypatch) -> None:
    _install_artifacts(monkeypatch)
    client = TestClient(main.app)
    response = client.get("/api/jobs/job-abc/validation-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "warn"
    assert payload["wrapper_load_error"] == "wrapper_class_not_found"
    assert payload["operator_view"]["summary"]


def test_causal_summary_route_collapses_stage_and_transition_failures(monkeypatch) -> None:
    _install_artifacts(monkeypatch)
    client = TestClient(main.app)
    response = client.get("/api/jobs/job-abc/causal-summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["first_failing_stage"] == "S-00"
    assert "T-04" in payload["first_failing_transition_ids"]
    assert payload["affected_stages"]
    assert payload["operator_view"]["next_action"]


def test_diagnostics_route_emits_stable_diagnosis_objects(monkeypatch) -> None:
    _install_artifacts(monkeypatch)
    client = TestClient(main.app)
    response = client.get("/api/jobs/job-abc/diagnostics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["diagnoses"]
    first = payload["diagnoses"][0]
    required = {
        "diagnosis_id",
        "title",
        "class",
        "severity",
        "trust_impact",
        "first_failing_stage",
        "first_failing_iteration",
        "affected_targets",
        "primary_evidence",
        "blast_radius",
        "recommended_next_action",
        "confidence",
        "owner_layer",
        "family_id",
    }
    assert required.issubset(first)


def test_artifacts_route_emits_tiered_operator_and_analysis_bundles(monkeypatch) -> None:
    _install_artifacts(monkeypatch)
    client = TestClient(main.app)
    response = client.get("/api/jobs/job-abc/artifacts")
    assert response.status_code == 200
    payload = response.json()
    assert payload["primary_artifacts"]
    assert payload["operator_bundle"]
    assert payload["analysis_bundle"]["artifact_count"] == 71
    assert payload["canonical_map"]


def test_routes_promote_analysis_entry_failure_over_missing_validation(monkeypatch) -> None:
    def fake_download(_container: str, blob_name: str):
        raise FileNotFoundError(blob_name)

    monkeypatch.setattr(main, "_download_blob", fake_download)
    monkeypatch.setattr(main, "_load_findings", lambda _job_id: [])
    monkeypatch.setattr(
        main,
        "_get_job_status",
        lambda _job_id: {
            "job_id": "job-fail",
            "component_name": "spectrum_reservation_stage",
            "status": "error",
            "message": "Analysis failed",
            "error": "Discovery produced no output files.\nreturncode=3221225786",
            "playbook_step": "02-reservation_stage",
        },
    )
    monkeypatch.setattr(main, "_find_saved_session_dir", lambda _job_id: None)
    client = TestClient(main.app)

    diagnostics = client.get("/api/jobs/job-fail/diagnostics").json()
    first = diagnostics["diagnoses"][0]
    assert first["title"] == "Analysis failed before discovery artifacts were emitted"
    assert first["first_failing_stage"] == "analysis-entry"
    assert first["family_id"] == "analysis-entry-failure"

    causal = client.get("/api/jobs/job-fail/causal-summary").json()
    assert causal["first_failing_stage"] == "analysis-entry"
    assert "downstream chained steps could run" in causal["blast_radius_summary"]


def test_validation_status_route_distinguishes_absence_parse_and_read_failures(monkeypatch) -> None:
    client = TestClient(main.app)
    base_job = {
        "job_id": "job-xyz",
        "component_name": "contoso_payments",
        "explore_phase": "done",
        "status": "done",
    }

    _install_artifacts(monkeypatch, artifacts={}, findings=[], job_status=base_job)
    missing_payload = client.get("/api/jobs/job-xyz/validation-status").json()
    assert missing_payload["status"] == "unknown"
    assert missing_payload["native_status"] == "partial"
    assert missing_payload["artifact_read_issues"] == []

    class ResourceNotFoundError(Exception):
        pass

    def fake_cloud_missing(_container: str, blob_name: str):
        raise ResourceNotFoundError(blob_name)

    monkeypatch.setattr(main, "_download_blob", fake_cloud_missing)
    cloud_missing_payload = client.get("/api/jobs/job-xyz/validation-status").json()
    assert cloud_missing_payload["status"] == "unknown"
    assert cloud_missing_payload["native_status"] == "partial"
    assert cloud_missing_payload["artifact_read_issues"] == []

    def fake_parse_download(_container: str, blob_name: str):
        if blob_name == "job-xyz/validation-report.json":
            return b"{"
        raise FileNotFoundError(blob_name)

    monkeypatch.setattr(main, "_download_blob", fake_parse_download)
    parse_payload = client.get("/api/jobs/job-xyz/validation-status").json()
    assert parse_payload["status"] == "unknown"
    assert parse_payload["native_status"] == "degraded"
    assert parse_payload["artifact_read_issues"][0]["path"] == "validation-report.json"
    assert parse_payload["artifact_read_issues"][0]["issue_kind"] == "parse_error"
    assert "Artifact retrieval degraded for validation-report.json" in parse_payload["operator_view"]["summary"]

    def fake_read_failure(_container: str, blob_name: str):
        if blob_name == "job-xyz/validation-report.json":
            raise OSError("blob unavailable")
        raise FileNotFoundError(blob_name)

    monkeypatch.setattr(main, "_download_blob", fake_read_failure)
    read_payload = client.get("/api/jobs/job-xyz/validation-status").json()
    assert read_payload["status"] == "unknown"
    assert read_payload["native_status"] == "degraded"
    assert read_payload["artifact_read_issues"][0]["path"] == "validation-report.json"
    assert read_payload["artifact_read_issues"][0]["issue_kind"] == "read_error"
    assert "Artifact retrieval degraded for validation-report.json" in read_payload["operator_view"]["summary"]


def test_route_family_surfaces_degraded_artifact_reads_without_payload_shape_drift(monkeypatch) -> None:
    artifacts = _artifact_map()
    artifacts["job-abc/run-validity.json"] = b"{"
    artifacts["job-abc/stage-index.json"] = b"{"
    artifacts["job-abc/artifact-index.json"] = b"{"
    _install_artifacts(monkeypatch, artifacts=artifacts, findings=[])
    client = TestClient(main.app)

    verdict = client.get("/api/jobs/job-abc/verdict-hierarchy").json()
    assert verdict["native_status"] == "degraded"
    assert verdict["artifact_read_issues"]
    assert verdict["layers"]["run_validity"]
    assert any(issue["path"] == "run-validity.json" for issue in verdict["artifact_read_issues"])

    causal = client.get("/api/jobs/job-abc/causal-summary").json()
    assert causal["native_status"] == "degraded"
    assert causal["artifact_read_issues"]
    assert "first_failing_stage" in causal
    assert any(issue["path"] == "stage-index.json" for issue in causal["artifact_read_issues"])

    artifacts_payload = client.get("/api/jobs/job-abc/artifacts").json()
    assert artifacts_payload["native_status"] == "degraded"
    assert artifacts_payload["artifact_read_issues"]
    assert artifacts_payload["analysis_bundle"]["artifact_count"] == 0
    assert "operator_bundle" in artifacts_payload
    assert any(issue["path"] == "artifact-index.json" for issue in artifacts_payload["artifact_read_issues"])


def test_diagnostics_route_inherits_artifact_read_degradation(monkeypatch) -> None:
    artifacts = _artifact_map()

    def fake_download(_container: str, blob_name: str):
        if blob_name == "job-abc/validation-report.json":
            raise OSError("blob unavailable")
        if blob_name in artifacts:
            return artifacts[blob_name]
        raise FileNotFoundError(blob_name)

    monkeypatch.setattr(main, "_download_blob", fake_download)
    monkeypatch.setattr(main, "_load_findings", lambda _job_id: [])
    monkeypatch.setattr(
        main,
        "_get_job_status",
        lambda _job_id: {
            "job_id": "job-abc",
            "component_name": "contoso_payments",
            "explore_phase": "done",
            "status": "done",
        },
    )
    monkeypatch.setattr(main, "_find_saved_session_dir", lambda _job_id: None)

    client = TestClient(main.app)
    payload = client.get("/api/jobs/job-abc/diagnostics").json()
    assert payload["native_status"] == "degraded"
    assert payload["artifact_read_issues"]
    assert payload["analysis_view"]["artifact_read_issues"]
    assert any(item["diagnosis_id"] == "job-abc-artifact-read-degraded" for item in payload["diagnoses"])
