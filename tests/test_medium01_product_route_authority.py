from __future__ import annotations

import json
from pathlib import Path

from scripts.runs.product_route_contract import (
    canonical_blocking_signal_for_record,
    product_contract_fields_for_record,
    product_contract_summary,
    product_route_authority_for_record,
)


def _base_record(tmp_path: Path, *, target: str = "session_bootstrap") -> dict:
    checkpoint = {
        "session_bootstrap": "SP_OpenOperatorSession",
        "reservation_stage": "SP_IssueReleaseHold",
    }.get(target, "SP_OpenOperatorSession")
    run_dir = tmp_path / target
    (run_dir / "session").mkdir(parents=True, exist_ok=True)
    return {
        "job_id": f"job-{target}",
        "status": "ok",
        "phase": "done",
        "run_dir": str(run_dir),
        "safe_to_compare": True,
        "semantic_proof_satisfied": True,
        "authoritative_proving": True,
        "run_authority": {
            "authority_level": "decision_bearing",
            "authoritative_proving": True,
        },
        "latest_status_map": {checkpoint: "verified_success"},
        "chain_context": {
            "target_name": target,
            "required_semantic_checkpoint": checkpoint,
            "predecessor_targets": [],
        },
    }


def _write_invocables(record: dict, *, source_type: str = "ghidra_export", ghidra: bool = True) -> None:
    session_dir = Path(record["run_dir"]) / "session"
    checkpoint = record["chain_context"]["required_semantic_checkpoint"]
    row = {
        "name": checkpoint,
        "source_type": source_type,
    }
    if ghidra:
        row["_ghidra_provenance"] = {"source_method": "decompiler"}
    (session_dir / "invocables_map.json").write_text(json.dumps({checkpoint: row}), encoding="utf-8")
    (session_dir / "discovery_meta.json").write_text(
        json.dumps({"bridge_reachable": True, "analysis_profile": "strict_dll"}),
        encoding="utf-8",
    )


def test_product_route_authority_harvests_ghidra_invocable_evidence(tmp_path: Path) -> None:
    record = _base_record(tmp_path)
    _write_invocables(record)

    authority = product_route_authority_for_record(record)

    assert authority["route_authority_present"] is True
    assert authority["reason_code"] == "ghidra_route_authority_present"
    assert authority["route_authority_source"] == "session_invocables_ghidra_provenance"
    assert any(path.endswith("invocables_map.json") for path in authority["ghidra_evidence_paths"])


def test_product_route_authority_rejects_pe_only_invocables(tmp_path: Path) -> None:
    record = _base_record(tmp_path)
    _write_invocables(record, source_type="pe_export", ghidra=False)

    authority = product_route_authority_for_record(record)

    assert authority["route_authority_present"] is False
    assert authority["reason_code"] == "ghidra_invocable_evidence_missing"
    assert authority["blocking_signal"] == "product_route_gap"


def test_product_route_authority_rejects_static_only_ghidra_artifact(tmp_path: Path) -> None:
    record = _base_record(tmp_path)
    static_dir = Path(record["run_dir"]) / "session" / "evidence" / "stage-00b-static-evidence"
    static_dir.mkdir(parents=True, exist_ok=True)
    (static_dir / "ghidra-data-types.json").write_text(json.dumps({"types": []}), encoding="utf-8")

    authority = product_route_authority_for_record(record)

    assert authority["route_authority_present"] is False
    assert authority["reason_code"] == "durable_discovery_output_missing"
    assert authority["blocking_signal"] == "product_route_gap"


def test_product_contract_blocks_when_route_authority_missing(tmp_path: Path) -> None:
    record = _base_record(tmp_path)
    _write_invocables(record, source_type="pe_export", ghidra=False)
    record["product_route_authority"] = product_route_authority_for_record(record)

    fields = product_contract_fields_for_record(record)

    assert fields["route_authority_present"] is False
    assert fields["product_green_eligible"] is False
    assert fields["blocking_signal"] == "product_route_gap"


def test_product_contract_blocks_when_enterprise_authority_missing(tmp_path: Path) -> None:
    record = _base_record(tmp_path, target="reservation_stage")
    _write_invocables(record)
    record["product_route_authority"] = product_route_authority_for_record(record)
    record["enterprise_survivability_authority"] = {
        "authority_name": "enterprise_branch_invalidation_authority",
        "authority_present": False,
        "safe_to_compare": False,
        "semantic_proof_satisfied": False,
        "blocking_signal": "branch_invalidation_authority_missing",
        "reason_code": "branch_invalidation_token_not_tied_to_rejected",
    }

    fields = product_contract_fields_for_record(record)

    assert fields["route_authority_present"] is True
    assert fields["safe_to_compare"] is False
    assert fields["semantic_proof_satisfied"] is False
    assert fields["authoritative_proving"] is False
    assert fields["product_green_eligible"] is False
    assert fields["blocking_signal"] == "branch_invalidation_authority_missing"


def test_suite_product_green_requires_all_required_targets(tmp_path: Path) -> None:
    session_record = _base_record(tmp_path, target="session_bootstrap")
    _write_invocables(session_record)
    session_record["product_route_authority"] = product_route_authority_for_record(session_record)
    session_record.update(product_contract_fields_for_record(session_record))

    report = {"semantic_checkpoint_alignment_succeeded": True}
    summary = product_contract_summary([session_record], report, expected_target_count=2)

    assert summary["route_authority_present"] is False
    assert summary["product_green_eligible"] is False
    assert summary["blocking_signal"] == "incomplete_product_chain"


def test_canonical_blocking_signal_prefers_product_route_gap_when_run_finished_non_authoritative(
    tmp_path: Path,
) -> None:
    record = _base_record(tmp_path, target="reservation_stage")
    _write_invocables(record)
    record["safe_to_compare"] = False
    record["authoritative_proving"] = False
    record["product_route_authority"] = {
        "blocking_signal": "product_route_gap",
        "reason_code": "decision_bearing_run_authority_missing",
    }
    record["job_terminalization"] = {
        "terminalization_kind": "done",
        "reason": {"code": "job_completed_done"},
    }

    assert canonical_blocking_signal_for_record(record) == "product_route_gap"
