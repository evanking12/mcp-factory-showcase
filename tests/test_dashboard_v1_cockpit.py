from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from dashboard import main


def _bundle(**overrides):
    job = {
        "job_id": "job-123",
        "component_name": "contoso_workflow",
        "status": "done",
        "explore_phase": "done",
        "verified_count": 9,
        "total_count": 12,
        "explore_runtime": {"selected_invocable_names": ["WF_CreateReservation"]},
    }
    verdict = {"verdict": "review"}
    findings = [
        {
            "function": "WF_CommitReservation",
            "status_canonical": "failure",
            "finding": "Missing prerequisite handle lineage",
            "first_blocking_stage": "s04",
            "blocker_family": "cross-dll lineage",
        },
        {
            "function": "WF_CreateReservation",
            "status_canonical": "verified_success",
            "working_call": {"pOutReservationId": "RSV-001"},
        },
        {
            "function": "WF_ListAuditTrail",
            "status_canonical": "inferred_success",
            "summary": "Additional export discovered outside the selected proof surface",
        },
    ]
    bundle = {
        "job": job,
        "verdict": verdict,
        "findings": findings,
        "report_text": "Checked: 3\nValidation complete.",
        "recent_jobs": [],
        "native_verdict_hierarchy": {},
        "native_validation_status": {},
        "native_causal_summary": {},
        "native_diagnostics": {},
        "native_artifacts": {},
    }
    bundle["verdict_layers"] = main._build_verdict_layers(job, verdict, findings, bundle["report_text"])
    bundle.update(overrides)
    if "job" in overrides or "verdict" in overrides or "findings" in overrides or "report_text" in overrides:
        bundle["verdict_layers"] = main._build_verdict_layers(
            bundle["job"], bundle["verdict"], bundle["findings"], bundle["report_text"]
        )
    return bundle


def test_dashboard_root_uses_split_template_shell() -> None:
    client = TestClient(main.app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Diagnostic operator cockpit" in response.text
    assert "/static/dashboard.css" in response.text
    assert 'id="diagnoses"' in response.text
    assert 'id="stage-track"' in response.text
    assert 'id="restart-lab"' in response.text
    assert "Lab offline or degraded" in response.text
    assert "Package Intake" in response.text
    assert "Investigation Focus" in response.text
    assert "Artifact Tiers" in response.text
    assert "Decision Cluster" in response.text
    assert "Ranked Evidence" in response.text
    assert "Decision Basis" in response.text
    assert "Chain Steps" in response.text
    assert "Current Context" in response.text
    assert "Chain Context" in response.text
    assert "Reading Order" in response.text
    assert 'id="recent-jobs-filter"' in response.text
    assert 'id="fixture-select"' in response.text
    assert "Artifact Priority Filters" in response.text
    assert "Proof Summary" in response.text
    assert "Iteration Summary" in response.text
    assert "Family Blockers" in response.text
    assert 'id="iteration-selector"' in response.text


def test_build_diagnoses_emits_required_contract_fields() -> None:
    bundle = _bundle()
    diagnoses = main._build_diagnoses(bundle)
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
    }
    assert diagnoses
    assert required.issubset(diagnoses[0])
    assert diagnoses[0]["primary_evidence"]["url"] == "/api/findings/job-123"


def test_verdict_layers_do_not_collapse_validity_and_validation() -> None:
    bundle = _bundle(
        job={
            "job_id": "job-321",
            "status": "done",
            "explore_phase": "awaiting_clarification",
            "verified_count": 0,
            "total_count": 12,
        },
        findings=[{"function": "WF_CreateReservation", "status_canonical": "verified_success"}],
        report_text="Checked: 0\nOptional is not defined",
    )
    layers = main._build_verdict_layers(bundle["job"], bundle["verdict"], bundle["findings"], bundle["report_text"])
    assert layers["ingest_success"]["status"] == "pass"
    assert layers["run_validity"]["status"] == "warn"
    assert layers["validation_completeness"]["status"] == "invalid"
    assert layers["semantic_success"]["status"] == "pass"


def test_blast_radius_separates_expected_from_extra_surface() -> None:
    bundle = _bundle()
    diagnoses = main._build_diagnoses(bundle)
    blast = main._build_blast_radius(bundle, diagnoses)
    assert blast["expected_surface"] == ["WF_CreateReservation"]
    assert "WF_ListAuditTrail" in blast["additional_discovered_surface"]


def test_overview_and_run_diff_keep_placeholder_metadata_explicit() -> None:
    bundle = _bundle(recent_jobs=[])
    diagnoses = main._build_diagnoses(bundle)
    overview = main._build_overview(bundle, diagnoses)
    run_diff = main._build_run_diff(bundle)
    assert overview["placeholder"] is True
    assert "artifact-index" in overview["missing_hooks"]
    assert "current_context" in overview
    assert overview["layout_mode"] == "multi_blocker"
    assert "proof_summary" in overview
    assert run_diff["placeholder"] is True
    assert "campaign-summary" in run_diff["missing_hooks"]


def test_iteration_summary_includes_verdict_layers_and_delta() -> None:
    bundle = _bundle()
    summary = main._build_iteration_summary(bundle)
    assert summary["iteration_id"] == "job-123"
    assert "semantic_success" in summary["verdict_layers"]
    assert "run_status" in summary["groups"]
    assert "verdict_layers" in summary["groups"]
    assert "delta" in summary["groups"]
    assert "delta_vs_previous" in summary
    assert "chain_context" in summary
    assert summary["pipeline_stage_label"]
    assert summary["placeholder"] is True


def test_chain_context_separates_chain_step_from_pipeline_stage_with_human_labels() -> None:
    bundle = _bundle(
        job={
            "job_id": "job-medium",
            "component_name": "reservation_stage",
            "playbook_step": "02-reservation_stage",
            "status": "error",
            "explore_phase": "error",
            "verified_count": 0,
            "total_count": 0,
            "lane_id": "spectrum-medium01-r2",
            "prior_job_id": "job-bootstrap",
        },
        findings=[],
        report_text="# MCP Factory - DLL Documentation Report\n\n**Functions documented:** 0\n",
    )
    chain = main._chain_context(bundle)
    assert chain["current_step_label"] == "02 Reservation Stage"
    assert chain["predecessor_step_label"] == "Job Bootstrap"
    assert chain["pipeline_stage_id"] == "analysis-entry"
    assert chain["pipeline_stage_label"] == "Analysis Entry"
    assert chain["chain_steps"][0]["label"] == "01 Session Bootstrap"
    assert chain["chain_steps"][0]["status"] == "pass"
    assert chain["chain_steps"][1]["label"] == "02 Reservation Stage"
    assert chain["chain_steps"][1]["status"] == "fail"
    assert chain["chain_steps"][2]["label"] == "03 Dispatch Preview"
    assert chain["chain_steps"][2]["status"] == "pending"


def test_family_blockers_group_diagnoses_with_evidence() -> None:
    bundle = _bundle()
    diagnoses = main._build_diagnoses(bundle)
    families = main._build_family_blockers(bundle, diagnoses)
    assert families
    assert "representative_evidence" in families[0]
    assert "affected_stage_ids" in families[0]
    assert families[0]["source"] == "derived"


def test_evidence_stack_prefers_preview_text_and_tiering() -> None:
    bundle = _bundle(
        job={
            "job_id": "job-err",
            "component_name": "spectrum_reservation_stage",
            "status": "error",
            "explore_phase": "error",
            "verified_count": 0,
            "total_count": 0,
            "message": "Analysis failed",
            "error": "Discovery produced no output files.\nreturncode=3221225786",
        },
        findings=[],
        report_text="# MCP Factory - DLL Documentation Report\n\n**Functions documented:** 0\n",
    )
    diagnoses = main._build_diagnoses(bundle)
    evidence = main._build_evidence_stack_payload(bundle, diagnoses)
    assert evidence["items"][0]["label"] == "Current job status"
    assert evidence["items"][0]["preview_text"].startswith("status: error")
    assert evidence["items"][0]["tier"] == "tier1"
    assert evidence["visible_default_count"] == 3
    assert evidence["has_more_tier1"] is True
    assert any(item["label"] == "Verdict hierarchy" and "run validity: fail" in item["preview_text"] for item in evidence["items"])
    assert any(item["label"] == "Causal summary" and "Blocked chain:" in item["preview_text"] for item in evidence["items"])
    assert any(item["label"] == "Validation status" and item["tier"] == "tier2" for item in evidence["items"])
    assert any(item["label"] == "Findings" and item["evidence_type"] == "empty evidence" for item in evidence["items"])
    assert any(item["label"] == "Report" and item["preview_text"] == "0 functions documented." for item in evidence["items"])
    assert any(item["label"] == "Artifacts" and item["tier"] == "tier2" for item in evidence["items"])


def test_decision_basis_demotes_validation_when_analysis_entry_failed() -> None:
    bundle = _bundle(
        job={
            "job_id": "job-err",
            "component_name": "spectrum_reservation_stage",
            "status": "error",
            "explore_phase": "error",
            "verified_count": 0,
            "total_count": 0,
            "message": "Analysis failed",
            "error": "Discovery produced no output files.\nreturncode=3221225786",
        },
        findings=[],
        report_text="# MCP Factory - DLL Documentation Report\n\n**Functions documented:** 0\n",
        native_validation_status={
            "status": "unknown",
            "operator_summary": "Validation status is missing.",
        },
    )
    diagnoses = main._build_diagnoses(bundle)
    basis = main._build_decision_basis(bundle, diagnoses)
    assert basis["alignment_status"] == "aligned"
    assert "job status is error" in basis["promoted_because"]
    assert any("Validation status was not promoted" in item for item in basis["demoted_candidates"])
    assert "chain_context" in basis


def test_overview_current_context_exposes_chain_step_and_pipeline_stage_labels() -> None:
    bundle = _bundle(
        job={
            "job_id": "job-ctx",
            "component_name": "reservation_stage",
            "playbook_step": "02-reservation_stage",
            "status": "error",
            "explore_phase": "error",
            "verified_count": 0,
            "total_count": 0,
            "lane_id": "spectrum-medium01-r2",
        },
        findings=[],
        report_text="# MCP Factory - DLL Documentation Report\n\n**Functions documented:** 0\n",
    )
    diagnoses = main._build_diagnoses(bundle)
    overview = main._build_overview(bundle, diagnoses)
    assert overview["current_context"]["chain_step_label"] == "02 Reservation Stage"
    assert overview["current_context"]["pipeline_stage_label"] == "Analysis Entry"


def test_dashboard_routes_expose_decision_basis_and_evidence_stack() -> None:
    client = TestClient(main.app)

    async def fake_collect(job_id: str):
        bundle = _bundle(
            job={
                "job_id": job_id,
                "component_name": "spectrum_reservation_stage",
                "status": "error",
                "explore_phase": "error",
                "verified_count": 0,
                "total_count": 0,
                "message": "Analysis failed",
                "error": "Discovery produced no output files.\nreturncode=3221225786",
            },
            findings=[],
            report_text="# MCP Factory - DLL Documentation Report\n\n**Functions documented:** 0\n",
            native_validation_status={"status": "unknown", "operator_summary": "Validation status is missing."},
        )
        bundle["errors"] = []
        return bundle

    original = main._collect_job_bundle
    main._collect_job_bundle = fake_collect
    try:
        decision = client.get("/api/dashboard/jobs/job-err/decision-basis")
        evidence = client.get("/api/dashboard/jobs/job-err/evidence-stack")
    finally:
        main._collect_job_bundle = original
    assert decision.status_code == 200
    assert evidence.status_code == 200
    assert decision.json()["decision_basis"]["alignment_status"] == "aligned"
    assert evidence.json()["evidence_stack"]["items"][0]["raw_url"] == "/api/jobs/job-err"
    assert evidence.json()["evidence_stack"]["visible_default_count"] == 3


def test_singleton_overview_exposes_layout_mode_and_proof_summary() -> None:
    bundle = _bundle(
        job={
            "job_id": "job-single",
            "component_name": "spectrum_reservation_stage",
            "status": "error",
            "explore_phase": "error",
            "verified_count": 0,
            "total_count": 0,
            "message": "Analysis failed",
            "error": "Discovery produced no output files.\nreturncode=3221225786",
        },
        findings=[],
        report_text="# MCP Factory - DLL Documentation Report\n\n**Functions documented:** 0\n",
    )
    diagnoses = main._build_diagnoses(bundle)
    overview = main._build_overview(bundle, diagnoses)
    assert overview["layout_mode"] == "singleton"
    assert overview["proof_summary"]["visible_tier1_count"] >= 1
    assert overview["proof_summary"]["proof_posture"]
    assert overview["proof_summary"]["present_proof"]
    assert "Artifacts" in overview["proof_summary"]["missing_proof"]
    assert overview["active_counts"]["family_count"] == 1


def test_diagnoses_are_severity_first_not_raw_stage_order_first() -> None:
    bundle = _bundle(
        job={
            "job_id": "job-focus",
            "component_name": "reservation_stage",
            "status": "done",
            "explore_phase": "s06",
            "verified_count": 1,
            "total_count": 3,
        },
        findings=[
            {
                "function": "WF_LateValidation",
                "status_canonical": "failure",
                "finding": "Late-stage regression",
                "first_blocking_stage": "s06",
                "blocker_family": "validation failure",
            },
            {
                "function": "WF_EarlyCapture",
                "status_canonical": "warning",
                "summary": "Early-stage warning should not outrank a critical failure.",
                "first_blocking_stage": "s00",
            },
        ],
    )
    diagnoses = main._build_diagnoses(bundle)
    assert diagnoses[0]["severity"] in {"critical", "high"}
    assert diagnoses[0]["first_failing_stage"] == "s06"


def test_stage_detail_prefers_readable_analysis_and_bounded_stage_evidence() -> None:
    bundle = _bundle(
        job={
            "job_id": "job-stage",
            "component_name": "spectrum_reservation_stage",
            "status": "error",
            "explore_phase": "error",
            "verified_count": 0,
            "total_count": 0,
            "message": "Analysis failed",
            "error": "Discovery produced no output files.\nreturncode=3221225786",
        },
        findings=[],
        report_text="# MCP Factory - DLL Documentation Report\n\n**Functions documented:** 0\n",
    )
    diagnoses = main._build_diagnoses(bundle)
    detail = main._build_stage_detail(bundle, "analysis-entry", diagnoses)
    assert detail["analysis_view"]["causal_summary_text"] == "Discovery produced no output files."
    assert detail["analysis_view"]["error_excerpt"] == "Discovery produced no output files."
    assert detail["analysis_view"]["readable_analysis_rows"]
    assert detail["evidence"]["visible_default_count"] == 1


def test_hook_catalog_groups_recovery_and_proof_surfaces() -> None:
    payload = main._hook_catalog()
    group_names = {item["name"] for item in payload["groups"]}
    assert "health_and_recovery" in group_names
    assert "evidence_and_review" in group_names
    assert "/api/dashboard/lab/restart" in payload["groups"][0]["hooks"]
    assert "/api/jobs/{job_id}/verdict-hierarchy" in payload["ready_now"]


def test_build_diagnoses_prefers_native_diagnostics() -> None:
    bundle = _bundle(
        native_diagnostics={
            "diagnoses": [
                {
                    "diagnosis_id": "native-1",
                    "title": "Native diagnosis",
                    "class": "blocker",
                    "severity": "high",
                    "trust_impact": "high",
                    "first_failing_stage": "s04",
                    "first_failing_iteration": "job:job-123",
                    "affected_targets": ["WF_CommitReservation"],
                    "primary_evidence": {"url": "/api/jobs/job-123/diagnostics", "summary": "native"},
                    "blast_radius": {"summary": "native"},
                    "recommended_next_action": "Use native diagnostics.",
                    "confidence": 0.9,
                    "owner_layer": "state",
                    "family_id": "state-lineage",
                }
            ]
        }
    )
    diagnoses = main._build_diagnoses(bundle)
    assert diagnoses[0]["diagnosis_id"] == "native-1"


def test_build_diagnoses_promotes_analysis_entry_failure_for_error_without_outputs() -> None:
    bundle = _bundle(
        job={
            "job_id": "job-err",
            "component_name": "spectrum_reservation_stage",
            "status": "error",
            "explore_phase": "error",
            "verified_count": 0,
            "total_count": 0,
            "message": "Analysis failed",
            "error": "Discovery produced no output files.\nreturncode=3221225786",
        },
        findings=[],
        report_text="# MCP Factory — DLL Documentation Report\n\n**Functions documented:** 0\n",
    )
    diagnoses = main._build_diagnoses(bundle)
    assert diagnoses[0]["title"] == "Analysis failed before discovery artifacts were emitted"
    assert diagnoses[0]["first_failing_stage"] == "analysis-entry"
    assert diagnoses[0]["family_id"] == "analysis-entry-failure"


def test_family_blockers_preserve_explicit_analysis_entry_family() -> None:
    bundle = _bundle(
        native_diagnostics={
            "diagnoses": [
                {
                    "diagnosis_id": "native-analysis-entry",
                    "title": "Analysis failed before discovery artifacts were emitted",
                    "class": "analysis entry failure",
                    "severity": "critical",
                    "trust_impact": "high",
                    "first_failing_stage": "analysis-entry",
                    "first_failing_iteration": "job:job-123",
                    "affected_targets": ["spectrum_reservation_stage"],
                    "primary_evidence": {"url": "/api/jobs/job-123", "summary": "Discovery produced no output files."},
                    "blast_radius": {"summary": "Chain stopped before downstream steps."},
                    "recommended_next_action": "Inspect the job error.",
                    "confidence": 0.98,
                    "owner_layer": "capture",
                    "family_id": "analysis-entry-failure",
                }
            ]
        }
    )
    diagnoses = main._build_diagnoses(bundle)
    families = main._build_family_blockers(bundle, diagnoses)
    assert families[0]["family_id"] == "analysis-entry-failure"
    assert families[0]["title"] == "Analysis entry failure"


def test_restart_dashboard_lab_endpoint_queues_script(monkeypatch) -> None:
    calls = []

    class DummyPopen:
        def __init__(self, args, cwd=None, creationflags=0):
            calls.append({"args": args, "cwd": cwd, "creationflags": creationflags})

    monkeypatch.setattr(main, "LAB_RESTART_SCRIPT", main.REPO_ROOT / "sessions" / "restart_dashboard_lab.ps1")
    monkeypatch.setattr(main.subprocess, "Popen", DummyPopen)
    client = TestClient(main.app)
    response = client.post("/api/dashboard/lab/restart")
    assert response.status_code == 202
    payload = response.json()
    assert payload["queued"] is True
    assert payload["status"] == "restart-requested"
    assert calls


def test_proxy_returns_502_when_upstream_disconnects(monkeypatch) -> None:
    async def fake_request(self, *args, **kwargs):
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    client = TestClient(main.app)
    response = client.get("/api/lab/status")
    assert response.status_code == 502
    payload = response.json()
    assert payload["source"] == "dashboard-proxy"
    assert payload["upstream_available"] is False
    assert payload["upstream_path"] == "/api/lab/status"
