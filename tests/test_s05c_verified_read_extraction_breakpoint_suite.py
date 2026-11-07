from __future__ import annotations

from types import SimpleNamespace

from api.pipeline.s05_enrichment import mc5_chain_reads
from api.pipeline.s05_enrichment import read_to_write_chaining
from api.pipeline.s05_enrichment import status as s05_status


def test_s05c_tier2_extracts_only_verified_read_evidence_for_chaining(monkeypatch) -> None:
    decisions: list[dict[str, object]] = []
    persisted: list[dict[str, object]] = []
    retry_inputs: list[dict[str, object]] = []

    findings = [
        {
            "function": "S05C_ReadVerifiedCustomer",
            "status": "verified_success",
            "verification": "verified",
            "working_call": {"customer_id": "CUST-100", "amount": 25},
        },
        {
            "function": "S05C_ReadInheritedSuccess",
            "status": "success",
            "verification": "inferred",
            "working_call": {"customer_id": "CUST-999", "amount": 75},
        },
        {
            "function": "S05C_ReadLegacyNoVerification",
            "status": "success",
            "working_call": {"customer_id": "CUST-LEGACY", "amount": 50},
        },
        {
            "function": "S05C_ReadPartial",
            "status": "partial",
            "verification": "inferred",
            "working_call": {"customer_id": "CUST-PARTIAL"},
        },
        {
            "function": "S05C_ReadFailure",
            "status": "failure",
            "verification": "error",
            "working_call": {"customer_id": "CUST-FAIL"},
        },
        {
            "function": "S05C_WriteCustomer",
            "status": "verified_success",
            "verification": "verified",
            "working_call": {"customer_id": "CUST-WRITE"},
        },
    ]

    def build_retry_plan(_selection, *, extracted_ids, evidence_ids, id_formats, available_id_kinds_override):
        retry_inputs.append(
            {
                "extracted_ids": list(extracted_ids),
                "evidence_ids": list(evidence_ids),
                "id_formats": list(id_formats),
                "available_id_kinds_override": set(available_id_kinds_override),
            }
        )
        return [
            {
                "function": "S05C_WriteCustomer",
                "fallback": "retry_ranked_candidates",
                "priority": 10,
                "cluster": "write",
            }
        ]

    monkeypatch.setattr(mc5_chain_reads, "_load_findings", lambda _job_id: findings)
    monkeypatch.setattr(mc5_chain_reads, "_load_s03_retry_surface", lambda _ctx: {})
    monkeypatch.setattr(
        mc5_chain_reads,
        "_build_write_arg_candidates",
        lambda _ctx: ({"S05C_WriteCustomer": [{"customer_id": "CUST-100"}]}, {"S05C_WriteCustomer": [{"source": "unit"}]}),
    )
    monkeypatch.setattr(mc5_chain_reads, "_build_write_retry_plan", build_retry_plan)
    monkeypatch.setattr(mc5_chain_reads, "_targeted_unlock_attempt", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(mc5_chain_reads, "_persist_mc_decision", lambda _ctx, _name, decision: decisions.append(decision))
    monkeypatch.setattr(s05_status, "_get_job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(s05_status, "_persist_job_status", lambda _job_id, payload: persisted.append(payload))
    monkeypatch.setattr(s05_status, "_set_explore_status", lambda *args, **kwargs: None)

    ctx = SimpleNamespace(
        job_id="job-s05c-verified-read",
        total=6,
        unlock_result={},
        vocab={"id_formats": ["CUST-\\d+"]},
        invocables=[{"name": "S05C_WriteCustomer"}],
        evidence_candidates=None,
        _lock=None,
        live_findings=[],
        explored_count=lambda: 6,
    )

    read_to_write_chaining.run_read_to_write_chaining(ctx)

    assert retry_inputs == [
        {
            "extracted_ids": ["CUST-100"],
            "evidence_ids": [],
            "id_formats": ["CUST-\\d+"],
            "available_id_kinds_override": set(),
        }
    ]
    decision = decisions[0]
    analysis = decision["analysis"]
    assert analysis["verified_read_count"] == 1
    assert analysis["extracted_ids"] == ["CUST-100"]
    assert analysis["extracted_amounts"] == [25]
    assert "CUST-999" not in analysis["extracted_ids"]
    assert "CUST-LEGACY" not in analysis["extracted_ids"]
    assert decision["action"] == "chain_read_outputs_to_write_inputs"
    assert "still blocked" in str(decision["result"])
    states = [
        row.get("s05_stage_status", {}).get("s05_read_to_write_chaining", {}).get("state")
        for row in persisted
    ]
    assert "start" in states
    assert "done" in states
