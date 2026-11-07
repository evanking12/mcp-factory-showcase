from __future__ import annotations

import json


def test_build_business_object_contract_surface_marks_pass_for_verified_entity_handoff() -> None:
    from api.pipeline.core.cross_dll_contracts import build_business_object_contract_surface

    surface = build_business_object_contract_surface(
        campaign_id="camp-contract",
        campaign_graph_epoch="camp-contract",
        per_dll_rows=[
            {
                "job_id": "job-workflow",
                "dll_id": "wf",
                "filename": "contoso_workflow.dll",
                "dll_fingerprint": "wf-fp",
                "graph_epoch": "camp-contract",
                "cross_dll_prior_job_ids": [],
            },
            {
                "job_id": "job-reporting",
                "dll_id": "rp",
                "filename": "contoso_reporting.dll",
                "dll_fingerprint": "rp-fp",
                "graph_epoch": "camp-contract",
                "cross_dll_prior_job_ids": ["job-workflow"],
            },
        ],
        latest_findings_by_job={
            "job-workflow": {
                "WF_CreateReservation": {
                    "function": "WF_CreateReservation",
                    "status_canonical": "verified_success",
                    "working_call": {"lpszResvId": "RESV-001"},
                }
            },
            "job-reporting": {
                "RP_CreatePreview": {
                    "function": "RP_CreatePreview",
                    "status_canonical": "verified_success",
                    "working_call": {"lpszResvId": "RESV-001"},
                }
            },
        },
        evidence_graph={
            "edges": [
                {
                    "producer_dll": "wf-fp",
                    "producer_fn": "WF_CreateReservation",
                    "consumer_dll": "rp-fp",
                    "consumer_fn": "RP_CreatePreview",
                    "entity_type": "RESV-001",
                    "evidence_job": "job-reporting",
                    "confidence": 0.9,
                }
            ]
        },
    )

    assert surface["dependency_class"] == "business_object_continuity"
    assert surface["contract_count"] == 1
    assert surface["summary"]["pass"] == 1
    contract = surface["contracts"][0]
    assert contract["exported_truth"]["entity_value"] == "RESV-001"
    assert contract["boundary_observer"]["status"] == "pass"
    assert contract["import_expectations"]["required_cross_dll_source_job_id"] == "job-workflow"


def test_build_business_object_contract_surface_marks_fail_when_consumer_handoff_breaks() -> None:
    from api.pipeline.core.cross_dll_contracts import build_business_object_contract_surface

    surface = build_business_object_contract_surface(
        campaign_id="camp-contract",
        campaign_graph_epoch="camp-contract",
        per_dll_rows=[
            {
                "job_id": "job-workflow",
                "dll_id": "wf",
                "filename": "contoso_workflow.dll",
                "dll_fingerprint": "wf-fp",
                "graph_epoch": "camp-contract",
                "cross_dll_prior_job_ids": [],
            },
            {
                "job_id": "job-reporting",
                "dll_id": "rp",
                "filename": "contoso_reporting.dll",
                "dll_fingerprint": "rp-fp",
                "graph_epoch": "camp-contract",
                "cross_dll_prior_job_ids": [],
            },
        ],
        latest_findings_by_job={
            "job-workflow": {
                "WF_CreateReservation": {
                    "function": "WF_CreateReservation",
                    "status_canonical": "verified_success",
                    "working_call": {"lpszResvId": "RESV-001"},
                }
            },
            "job-reporting": {
                "RP_CreatePreview": {
                    "function": "RP_CreatePreview",
                    "status_canonical": "failure",
                    "finding": "No working call found.",
                }
            },
        },
        evidence_graph={
            "edges": [
                {
                    "producer_dll": "wf-fp",
                    "producer_fn": "WF_CreateReservation",
                    "consumer_dll": "rp-fp",
                    "consumer_fn": "RP_CreatePreview",
                    "entity_type": "RESV-001",
                    "evidence_job": "job-reporting",
                    "confidence": 0.9,
                }
            ]
        },
    )

    assert surface["summary"]["fail"] == 1
    contract = surface["contracts"][0]
    assert contract["boundary_observer"]["status"] == "fail"
    assert "consumer_missing_source_job_seed" in contract["boundary_observer"]["reasons"]
    assert "consumer_missing_import_observation" in contract["boundary_observer"]["reasons"]


def test_campaign_truth_and_attribution_report_include_cross_dll_contracts(monkeypatch) -> None:
    from api.pipeline import runner
    from api.analysis import cohesion

    evidence_graph = {
        "edges": [
            {
                "producer_dll": "wf-fp",
                "producer_fn": "WF_CreateReservation",
                "consumer_dll": "rp-fp",
                "consumer_fn": "RP_CreatePreview",
                "entity_type": "RESV-001",
                "evidence_job": "job-reporting",
                "confidence": 0.9,
            }
        ]
    }

    def _status(job_id: str) -> dict:
        component = "contoso_workflow" if "workflow" in job_id else "contoso_reporting"
        fingerprint = "wf-fp" if "workflow" in job_id else "rp-fp"
        runtime = {
            "analysis_profile": "strict_dll",
            "graph_epoch": "camp-contract",
            "prior_job_id": "",
            "cross_dll_prior_job_ids": ["job-workflow"] if job_id == "job-reporting" else [],
        }
        return {
            "component_name": component,
            "dll_fingerprint": fingerprint,
            "analysis_entrypoint": "upload",
            "binary_origin": "temp_upload",
            "analysis_profile": "strict_dll",
            "discovery_meta": {"cache_state": "warm", "bridge_reachable": True},
            "explore_runtime": runtime,
        }

    def _findings(job_id: str) -> list[dict]:
        if job_id == "job-workflow":
            return [
                {
                    "function": "WF_CreateReservation",
                    "status_canonical": "verified_success",
                    "working_call": {"lpszResvId": "RESV-001"},
                }
            ]
        return [
            {
                "function": "RP_CreatePreview",
                "status_canonical": "verified_success",
                "working_call": {"lpszResvId": "RESV-001"},
            }
        ]

    def _download_runner(_container, blob_name):
        if blob_name == "campaigns/camp-contract/evidence_graph.json":
            return json.dumps(evidence_graph).encode("utf-8")
        return json.dumps({}).encode("utf-8")

    monkeypatch.setattr(runner, "_get_job_status", _status)
    monkeypatch.setattr(runner, "_load_findings", _findings)
    monkeypatch.setattr(runner, "_download_blob", _download_runner)

    campaign = {
        "campaign_id": "camp-contract",
        "phase": "done",
        "graph_epoch": "camp-contract",
        "dll_entries": [
            {"dll_id": "wf", "job_id": "job-workflow", "filename": "contoso_workflow.dll", "status": "done", "dll_fingerprint": "wf-fp"},
            {"dll_id": "rp", "job_id": "job-reporting", "filename": "contoso_reporting.dll", "status": "done", "dll_fingerprint": "rp-fp"},
        ],
    }

    truth = runner._build_campaign_truth("camp-contract", campaign)  # noqa: SLF001

    assert truth["cross_dll_contracts"]["summary"]["pass"] == 1
    assert truth["cross_dll_contracts"]["contracts"][0]["boundary_observer"]["status"] == "pass"

    uploads: dict[str, dict] = {}
    monkeypatch.setattr(cohesion, "_read_run_ledger_rows", lambda: [])
    monkeypatch.setattr(cohesion, "_get_job_status", _status)
    monkeypatch.setattr(cohesion, "_load_findings", _findings)
    monkeypatch.setattr(
        cohesion,
        "_download_blob",
        lambda _container, blob_name: (
            json.dumps(truth).encode("utf-8")
            if blob_name == "campaigns/camp-contract/campaign-truth.json"
            else json.dumps(evidence_graph).encode("utf-8")
            if blob_name == "campaigns/camp-contract/evidence_graph.json"
            else json.dumps({}).encode("utf-8")
        ),
    )
    monkeypatch.setattr(
        cohesion,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploads.setdefault(blob_name, json.loads(data.decode("utf-8"))),
    )

    report = cohesion.emit_campaign_attribution_report("camp-contract", campaign)

    assert report["cross_dll_contracts"]["summary"]["pass"] == 1
    assert report["cross_dll_contracts"]["contracts"][0]["consumer"]["function"] == "RP_CreatePreview"
    assert uploads["campaigns/camp-contract/campaign-attribution-report.json"]["cross_dll_contracts"]["summary"]["pass"] == 1
