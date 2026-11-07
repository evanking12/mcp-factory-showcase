from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from harness_lib import collector
from api.pipeline.core.handoff_contract import TRANSITION_CONTRACT_BY_ID, TRANSITION_ORDER


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_stage_handoff_audit_reports_missing_required_artifacts(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir(parents=True, exist_ok=True)
    _write_json(
        session / "stage-index.json",
        {
            "version": "1.0",
            "stages": [{"id": "S-06", "status": "skipped"}],
        },
    )

    audit = collector._build_stage_handoff_audit(session)  # noqa: SLF001
    summary = audit.get("summary") or {}
    assert int(summary.get("fail_count") or 0) > 0
    missing_paths = []
    for stage_row in audit.get("stages") or []:
        missing_paths.extend(stage_row.get("missing") or [])
    assert "evidence/stage-02-probe-loop/probe-log.json" in missing_paths


def test_transition_contract_audit_reports_missing_transition_rows(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir(parents=True, exist_ok=True)
    _write_json(
        session / "transition-index.json",
        {
            "version": "1.0",
            "transitions": [
                {
                    "id": "T-01",
                    "name": "hints_to_vocab",
                    "status": "pass",
                    "producer_stage": "S-01",
                    "consumer_stage": "S-02",
                    "producer_evidence": ["evidence/stage-01-pre-probe/hints.txt"],
                    "consumer_evidence": ["evidence/stage-01-pre-probe/vocab.json"],
                    "effect_evidence": ["evidence/stage-02-probe-loop/stage-context.txt"],
                }
            ],
        },
    )

    audit = collector._build_transition_contract_audit(session)  # noqa: SLF001
    summary = audit.get("summary") or {}
    assert int(summary.get("fail_count") or 0) > 0
    rows = audit.get("transitions") or []
    assert any("missing_transition_row:T-02" in (row.get("issues") or []) for row in rows)


def test_run_validity_fails_when_handoff_audits_fail(tmp_path: Path) -> None:
    contract = collector.ContractResult(  # noqa: SLF001
        valid=True,
        missing=[],
        parse_errors=[],
        hard_fail=False,
        parsed={},
    )
    validity = collector._build_run_validity(  # noqa: SLF001
        contract=contract,
        component="contoso_cs",
        analysis_profile="strict_dll",
        status_counts={"total": 1, "verified_rate": 0.0, "discovered_rate": 0.0},
        invocable_count=12,
        mode="strict",
        session_dir=tmp_path / "session",
        schema_handoff_audit={"summary": {"drop_to_zero_count": 0, "regression_count": 0}},
        stage_handoff_audit={"summary": {"fail_count": 1, "valid": False}},
        transition_contract_audit={"summary": {"fail_count": 0, "valid": True}},
    )
    assert validity["valid"] is False
    assert "stage_handoff.fail_count:1" in (validity.get("reasons") or [])


def test_transition_contract_audit_allows_t21_missing_winning_init_sequence_on_warn(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir(parents=True, exist_ok=True)

    transitions = []
    for tid in TRANSITION_ORDER:
        contract = TRANSITION_CONTRACT_BY_ID[tid]
        row_status = "pass"
        if tid == "T-21":
            row_status = "warn"
        transitions.append(
            {
                "id": tid,
                "name": contract.name,
                "status": row_status,
                "producer_stage": contract.producer_stage,
                "consumer_stage": contract.consumer_stage,
                "producer_evidence": list(contract.producer_evidence),
                "consumer_evidence": list(contract.consumer_evidence),
                "effect_evidence": list(contract.effect_evidence),
                "reason": (
                    "write-unlock remained blocked; no winning init sequence exists yet"
                    if tid == "T-21"
                    else "fixture pass"
                ),
            }
        )
        for rel in (*contract.producer_evidence, *contract.consumer_evidence, *contract.effect_evidence):
            if tid == "T-21" and rel == "evidence/mc-decisions/winning-init-sequence.json":
                continue
            path = session / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == ".json":
                path.write_text("{}", encoding="utf-8")
            else:
                path.write_text("fixture", encoding="utf-8")

    _write_json(
        session / "transition-index.json",
        {
            "version": "1.0",
            "transitions": transitions,
        },
    )

    audit = collector._build_transition_contract_audit(session)  # noqa: SLF001
    summary = audit.get("summary") or {}
    assert int(summary.get("fail_count") or 0) == 0
    row = next(row for row in (audit.get("transitions") or []) if row.get("transition_id") == "T-21")
    assert row["status"] == "pass"
    assert row["transition_status"] == "warn"
