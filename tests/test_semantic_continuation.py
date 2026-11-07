from __future__ import annotations

import json
from pathlib import Path

from api.pipeline.core.semantic_continuation import (
    append_semantic_continuation_ledger,
    derive_spectrum_medium01_continuation_packet,
    emit_spectrum_medium01_semantic_continuation,
)


def _medium_summary(tmp_path: Path) -> tuple[Path, dict]:
    output_dir = tmp_path / "medium"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_records = [
        {
            "dll_name": "spectrum_session_bootstrap.dll",
            "job_id": "job-session",
            "run_dir": str(output_dir / "runs" / "01-session_bootstrap"),
            "binary_hash": "hash-session",
            "chain_context": {
                "target_name": "session_bootstrap",
                "required_semantic_checkpoint": "SP_OpenOperatorSession",
            },
        },
        {
            "dll_name": "spectrum_reservation_stage.dll",
            "job_id": "job-reservation",
            "run_dir": str(output_dir / "runs" / "02-reservation_stage"),
            "binary_hash": "hash-reservation",
            "chain_context": {
                "target_name": "reservation_stage",
                "required_semantic_checkpoint": "SP_IssueReleaseHold",
            },
        },
        {
            "dll_name": "spectrum_dispatch_preview.dll",
            "job_id": "job-preview",
            "run_dir": str(output_dir / "runs" / "03-dispatch_preview"),
            "binary_hash": "hash-preview",
            "chain_context": {
                "target_name": "dispatch_preview",
                "required_semantic_checkpoint": "SP_PrepareReleasePreview",
            },
        },
        {
            "dll_name": "spectrum_fee_quote.dll",
            "job_id": "job-fee",
            "run_dir": str(output_dir / "runs" / "04-fee_quote"),
            "binary_hash": "hash-fee",
            "chain_context": {
                "target_name": "fee_quote",
                "required_semantic_checkpoint": "SP_StageReleaseFeeQuote",
            },
        },
        {
            "dll_name": "spectrum_settlement_reconcile.dll",
            "job_id": "job-settlement",
            "run_dir": str(output_dir / "runs" / "05-settlement_reconcile"),
            "binary_hash": "hash-settlement",
            "chain_context": {
                "target_name": "settlement_reconcile",
                "required_semantic_checkpoint": "SP_VerifyReservedRelease",
            },
        },
    ]
    return output_dir, {
        "suite_id": "spectrum_transaction_release_settlement_suite",
        "case_id": "medium-01",
        "entry_surface": "upload",
        "run_records": run_records,
    }


def _medium_report() -> dict:
    return {
        "suite_id": "spectrum_transaction_release_settlement_suite",
        "case_id": "medium-01",
        "proof_class": "compiled_local_binary",
        "entry_surface": "upload",
        "binary_ingest_proof_succeeded": True,
        "semantic_checkpoint_alignment_succeeded": False,
        "expected_symbol_flow": [
            "SP_OpenOperatorSession",
            "SP_IssueReleaseHold",
            "SP_PrepareReleasePreview",
            "SP_StageReleaseFeeQuote",
            "SP_VerifyReservedRelease",
        ],
        "semantic_symbol_flow": [
            "SP_OpenOperatorSession",
            "SP_IssueReleaseHold",
        ],
        "semantic_checkpoint_gap": [
            "SP_PrepareReleasePreview",
            "SP_StageReleaseFeeQuote",
            "SP_VerifyReservedRelease",
        ],
        "per_run": [
            {
                "dll_name": "spectrum_session_bootstrap.dll",
                "semantic_checkpoint_match": True,
            },
            {
                "dll_name": "spectrum_reservation_stage.dll",
                "semantic_checkpoint_match": True,
            },
            {
                "dll_name": "spectrum_dispatch_preview.dll",
                "semantic_checkpoint_match": False,
            },
            {
                "dll_name": "spectrum_fee_quote.dll",
                "semantic_checkpoint_match": False,
            },
            {
                "dll_name": "spectrum_settlement_reconcile.dll",
                "semantic_checkpoint_match": False,
            },
        ],
    }


def test_derive_spectrum_medium01_continuation_packet(tmp_path: Path) -> None:
    output_dir, summary = _medium_summary(tmp_path)
    report = _medium_report()
    summary_path = output_dir / "compiled-ingest-summary.json"
    report_path = output_dir / "compiled-ingest-compare-report.json"

    packet = derive_spectrum_medium01_continuation_packet(
        output_dir=output_dir,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
        report=report,
    )

    assert packet is not None
    assert packet["first_failed_checkpoint"] == "SP_PrepareReleasePreview"
    assert packet["last_success_checkpoint"] == "SP_IssueReleaseHold"
    assert packet["retry_scope_targets"] == [
        "dispatch_preview",
        "fee_quote",
        "settlement_reconcile",
    ]
    assert packet["trusted_predecessor_targets"] == [
        "session_bootstrap",
        "reservation_stage",
    ]
    assert packet["trusted_predecessor_job_ids"] == [
        "job-session",
        "job-reservation",
    ]


def test_derive_spectrum_medium01_continuation_packet_requires_binary_green_and_semantic_red(
    tmp_path: Path,
) -> None:
    output_dir, summary = _medium_summary(tmp_path)
    report = _medium_report()
    report["semantic_checkpoint_alignment_succeeded"] = True
    assert (
        derive_spectrum_medium01_continuation_packet(
            output_dir=output_dir,
            summary_path=output_dir / "compiled-ingest-summary.json",
            report_path=output_dir / "compiled-ingest-compare-report.json",
            summary=summary,
            report=report,
        )
        is None
    )
    report["semantic_checkpoint_alignment_succeeded"] = False
    report["binary_ingest_proof_succeeded"] = False
    assert (
        derive_spectrum_medium01_continuation_packet(
            output_dir=output_dir,
            summary_path=output_dir / "compiled-ingest-summary.json",
            report_path=output_dir / "compiled-ingest-compare-report.json",
            summary=summary,
            report=report,
        )
        is None
    )


def test_append_semantic_continuation_ledger_dedupes_on_same_gap_and_trusted_predecessors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir, summary = _medium_summary(tmp_path)
    report = _medium_report()
    summary_path = output_dir / "compiled-ingest-summary.json"
    report_path = output_dir / "compiled-ingest-compare-report.json"
    packet = derive_spectrum_medium01_continuation_packet(
        output_dir=output_dir,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
        report=report,
    )
    assert packet is not None

    ledger_path = tmp_path / "sessions" / "ledger" / "semantic_continuation.jsonl"
    monkeypatch.setattr(
        "api.pipeline.core.semantic_continuation.SEMANTIC_CONTINUATION_LEDGER",
        ledger_path,
    )

    first = append_semantic_continuation_ledger(packet)
    second = append_semantic_continuation_ledger(packet)

    assert first["appended"] is True
    assert second["appended"] is False
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1


def test_emit_spectrum_medium01_semantic_continuation_writes_artifacts(tmp_path: Path, monkeypatch) -> None:
    output_dir, summary = _medium_summary(tmp_path)
    report = _medium_report()
    summary_path = output_dir / "compiled-ingest-summary.json"
    report_path = output_dir / "compiled-ingest-compare-report.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    report_path.write_text(json.dumps(report), encoding="utf-8")

    ledger_path = tmp_path / "sessions" / "ledger" / "semantic_continuation.jsonl"
    roadblock_path = tmp_path / "bugs" / "RB-test.json"
    monkeypatch.setattr(
        "api.pipeline.core.semantic_continuation.SEMANTIC_CONTINUATION_LEDGER",
        ledger_path,
    )
    monkeypatch.setattr(
        "api.pipeline.core.semantic_continuation.SPECTRUM_MEDIUM01_CONTINUATION_ROADBLOCK",
        roadblock_path,
    )

    emitted = emit_spectrum_medium01_semantic_continuation(
        output_dir=output_dir,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
        report=report,
    )

    assert emitted is not None
    assert Path(emitted["packet_path"]).exists()
    assert Path(emitted["ledger_row_path"]).exists()
    assert Path(emitted["roadblock_path"]).exists()
