from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
SEMANTIC_CONTINUATION_LEDGER = REPO_ROOT / "sessions" / "ledger" / "semantic_continuation.jsonl"
SPECTRUM_MEDIUM01_CONTINUATION_ROADBLOCK = (
    REPO_ROOT / "bugs" / "RB-2026-04-09-spectrum-medium01-lineage-materialization-continuation.json"
)

SPECTRUM_MEDIUM01_BLOCKER_FAMILY = "lineage_materialization"
SPECTRUM_MEDIUM01_RETRY_SCOPE_TARGETS: tuple[str, ...] = (
    "dispatch_preview",
    "fee_quote",
    "settlement_reconcile",
)


def _hash_payload(payload: Any) -> str:
    return __import__("hashlib").sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_semantic_continuation_packet(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    return json.loads(resolved.read_text(encoding="utf-8"))


def derive_spectrum_medium01_continuation_packet(
    *,
    output_dir: Path,
    summary_path: Path,
    report_path: Path,
    summary: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any] | None:
    case_id = str(report.get("case_id") or summary.get("case_id") or "").strip()
    binary_ok = bool(report.get("binary_ingest_proof_succeeded"))
    semantic_ok = bool(report.get("semantic_checkpoint_alignment_succeeded"))
    if case_id != "medium-01" or not binary_ok or semantic_ok:
        return None

    expected_symbol_flow = [str(item) for item in list(report.get("expected_symbol_flow") or []) if str(item).strip()]
    semantic_symbol_flow = [str(item) for item in list(report.get("semantic_symbol_flow") or []) if str(item).strip()]
    semantic_checkpoint_gap = [str(item) for item in list(report.get("semantic_checkpoint_gap") or []) if str(item).strip()]
    if not semantic_checkpoint_gap:
        return None

    first_failed_checkpoint = semantic_checkpoint_gap[0]
    first_failed_index = expected_symbol_flow.index(first_failed_checkpoint)
    last_success_checkpoint = expected_symbol_flow[first_failed_index - 1] if first_failed_index > 0 else ""

    report_rows = {
        str(row.get("dll_name") or "").strip(): dict(row)
        for row in list(report.get("per_run") or [])
        if str(row.get("dll_name") or "").strip()
    }
    trusted_predecessor_targets: list[str] = []
    trusted_predecessor_job_ids: list[str] = []
    trusted_run_dirs: list[str] = []
    comparable_target_hashes: dict[str, str] = {}

    for run_record in list(summary.get("run_records") or []):
        dll_name = str(run_record.get("dll_name") or "").strip()
        target_name = str((run_record.get("chain_context") or {}).get("target_name") or "").strip()
        required_checkpoint = str((run_record.get("chain_context") or {}).get("required_semantic_checkpoint") or "").strip()
        if target_name in SPECTRUM_MEDIUM01_RETRY_SCOPE_TARGETS:
            comparable_target_hashes[target_name] = str(run_record.get("binary_hash") or "").strip()
        if not target_name or not required_checkpoint:
            continue
        if expected_symbol_flow.index(required_checkpoint) >= first_failed_index:
            continue
        report_row = report_rows.get(dll_name, {})
        if not bool(report_row.get("semantic_checkpoint_match")):
            continue
        trusted_predecessor_targets.append(target_name)
        trusted_predecessor_job_ids.append(str(run_record.get("job_id") or "").strip())
        trusted_run_dirs.append(str(run_record.get("run_dir") or "").strip())

    comparison_baseline_hash = _hash_payload(
        {
            "suite_id": str(report.get("suite_id") or ""),
            "case_id": case_id,
            "blocker_family_primary": SPECTRUM_MEDIUM01_BLOCKER_FAMILY,
            "semantic_checkpoint_gap": semantic_checkpoint_gap,
            "comparable_target_hashes": comparable_target_hashes,
        }
    )
    continuation_id = f"sc-{_hash_payload({'baseline': comparison_baseline_hash, 'trusted_predecessors': trusted_predecessor_targets, 'trusted_predecessor_job_ids': trusted_predecessor_job_ids})[:12]}"

    packet = {
        "schema_version": "1.0.0",
        "continuation_id": continuation_id,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "suite_id": str(report.get("suite_id") or summary.get("suite_id") or "").strip(),
        "case_id": case_id,
        "proof_class": str(report.get("proof_class") or "").strip(),
        "entry_surface": str(report.get("entry_surface") or summary.get("entry_surface") or "").strip(),
        "source_output_dir": str(output_dir),
        "source_compare_report": str(report_path),
        "blocker_family_primary": SPECTRUM_MEDIUM01_BLOCKER_FAMILY,
        "blocker_confidence": "medium",
        "continuation_reason": "semantic_checkpoint_alignment_failed",
        "expected_symbol_flow": expected_symbol_flow,
        "semantic_symbol_flow": semantic_symbol_flow,
        "semantic_checkpoint_gap": semantic_checkpoint_gap,
        "first_failed_checkpoint": first_failed_checkpoint,
        "last_success_checkpoint": last_success_checkpoint,
        "trusted_predecessor_targets": trusted_predecessor_targets,
        "trusted_predecessor_job_ids": trusted_predecessor_job_ids,
        "retry_scope_targets": list(SPECTRUM_MEDIUM01_RETRY_SCOPE_TARGETS),
        "next_retry_target": "dispatch_preview",
        "trusted_artifact_refs": {
            "summary_path": str(summary_path),
            "compare_report_path": str(report_path),
            "trusted_run_dirs": trusted_run_dirs,
        },
        "allowed_next_actions": [
            "rerun only the retry_scope_targets with preserved trusted predecessors",
            "tighten compiled medium-01 fanout lineage embodiment",
            "compare the continued semantic gap against the original semantic gap",
        ],
        "disallowed_next_actions": [
            "full-suite rerun before the medium fanout seam is narrowed",
            "medium-02 expansion before medium-01 continuation evidence exists",
            "generic semantic invention outside the authored case contract",
        ],
        "exit_criteria": [
            "semantic checkpoint gap narrows from the original packet baseline",
            "dispatch_preview, fee_quote, or settlement_reconcile gains a success-like semantic checkpoint",
            "the next continuation decision is evidence-bearing rather than restart-from-zero",
        ],
        "status": "pending_retry",
        "comparison_baseline_hash": comparison_baseline_hash,
    }
    return packet


def append_semantic_continuation_ledger(packet: dict[str, Any]) -> dict[str, Any]:
    SEMANTIC_CONTINUATION_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    existing_rows = _read_jsonl_rows(SEMANTIC_CONTINUATION_LEDGER)
    content_hash = _hash_payload(
        {
            "comparison_baseline_hash": str(packet.get("comparison_baseline_hash") or ""),
            "trusted_predecessor_targets": list(packet.get("trusted_predecessor_targets") or []),
            "trusted_predecessor_job_ids": list(packet.get("trusted_predecessor_job_ids") or []),
            "semantic_checkpoint_gap": list(packet.get("semantic_checkpoint_gap") or []),
        }
    )
    for row in existing_rows:
        if str(row.get("content_hash") or "") == content_hash:
            return {
                "ledger_path": str(SEMANTIC_CONTINUATION_LEDGER),
                "appended": False,
                "reason": "duplicate_content_hash_noop",
                "content_hash": content_hash,
                "row_hash": str(row.get("row_hash") or ""),
            }

    latest_same_id = [
        row for row in existing_rows if str(row.get("continuation_id") or "") == str(packet.get("continuation_id") or "")
    ]
    capture_seq = max((int(row.get("capture_seq") or 0) for row in latest_same_id), default=-1) + 1
    ledger_row = {
        **packet,
        "capture_seq": capture_seq,
        "content_hash": content_hash,
    }
    ledger_row["row_hash"] = _hash_payload({k: v for k, v in ledger_row.items() if k != "row_hash"})

    with SEMANTIC_CONTINUATION_LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ledger_row, sort_keys=True) + "\n")

    return {
        "ledger_path": str(SEMANTIC_CONTINUATION_LEDGER),
        "appended": True,
        "reason": "ok",
        "capture_seq": capture_seq,
        "content_hash": content_hash,
        "row_hash": ledger_row["row_hash"],
    }


def upsert_spectrum_medium01_continuation_roadblock(packet: dict[str, Any]) -> Path:
    packet_path = Path(str(packet.get("source_output_dir") or "")) / "semantic-continuation.json"
    payload = {
        "id": "RB-2026-04-09-spectrum-medium01-lineage-materialization-continuation",
        "title": "Compiled Spectrum medium-01 requires semantic continuation for lineage materialization",
        "class": "architecture",
        "layer": "compiled spectrum medium-01 continuation",
        "symptom": (
            "Compiled medium-01 binary ingest succeeds, but semantic checkpoint alignment still fails "
            f"at {', '.join(list(packet.get('semantic_checkpoint_gap') or []))}."
        ),
        "smallest_reproducer": str(packet.get("source_output_dir") or ""),
        "trust_impact": (
            "The pipeline can identify the medium fanout blocker honestly, but cannot yet preserve that "
            "semantic obligation as a retryable continuation unit."
        ),
        "allowed_next_actions": list(packet.get("allowed_next_actions") or []),
        "disallowed_next_actions": list(packet.get("disallowed_next_actions") or []),
        "exit_criteria": list(packet.get("exit_criteria") or []),
        "next_move": "escalate",
        "continuation_id": str(packet.get("continuation_id") or ""),
        "continuation_packet": str(packet_path),
        "blocker_family_primary": str(packet.get("blocker_family_primary") or ""),
    }
    _write_json(SPECTRUM_MEDIUM01_CONTINUATION_ROADBLOCK, payload)
    return SPECTRUM_MEDIUM01_CONTINUATION_ROADBLOCK


def emit_spectrum_medium01_semantic_continuation(
    *,
    output_dir: Path,
    summary_path: Path,
    report_path: Path,
    summary: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any] | None:
    packet = derive_spectrum_medium01_continuation_packet(
        output_dir=output_dir,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
        report=report,
    )
    if packet is None:
        return None

    packet_path = output_dir / "semantic-continuation.json"
    _write_json(packet_path, packet)
    ledger_result = append_semantic_continuation_ledger(packet)
    ledger_row_payload = {
        **ledger_result,
        "continuation_id": str(packet.get("continuation_id") or ""),
        "continuation_path": str(packet_path),
    }
    ledger_row_path = output_dir / "semantic-continuation-ledger-row.json"
    _write_json(ledger_row_path, ledger_row_payload)
    roadblock_path = upsert_spectrum_medium01_continuation_roadblock(packet)

    return {
        "packet": packet,
        "packet_path": str(packet_path),
        "ledger_row": ledger_row_payload,
        "ledger_row_path": str(ledger_row_path),
        "roadblock_path": str(roadblock_path),
    }
