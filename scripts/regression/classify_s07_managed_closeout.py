from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LOCAL_ARTIFACTS_ROOT = REPO_ROOT / "local-data" / "artifacts"
REQUIRED_CONTRACT_ARTIFACTS = (
    "session-meta.json",
    "stage-index.json",
    "transition-index.json",
    "cohesion-report.json",
)
CLAIM_CEILING = "managed_s07_closeout_classifier_only"
S07_CHECKPOINT_AUTHORITY_FILE = "s07_finalize_save_authority.json"
MACRO_VERDICT_AUTHORITY_FILE = "macro_verdict_persist_authority.json"
FINAL_STATUS_AUTHORITY_FILE = "final_status_persist_authority.json"


def _read_json_or_none(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _file_packet(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"exists": False, "bytes": 0, "sha256": "", "path": str(path)}
    data = path.read_bytes()
    return {
        "exists": True,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "path": str(path),
    }


def _target_run_dir(source_proof_root: Path, target: str, job_id: str = "") -> Path | None:
    runs_dir = source_proof_root / "runs"
    if not runs_dir.exists():
        return None
    wanted_target = str(target or "").strip()
    wanted_job = str(job_id or "").strip()
    for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
        record = _read_json_or_none(run_dir / "run_result.json")
        if not isinstance(record, dict):
            continue
        record_target = str(record.get("target") or "").strip()
        record_job_id = str(record.get("job_id") or "").strip()
        if wanted_job and record_job_id == wanted_job:
            return run_dir
        if wanted_target and (record_target == wanted_target or run_dir.name.endswith(wanted_target)):
            return run_dir
    return None


def _load_trace_steps(paths: list[Path]) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    steps: list[str] = []
    events: list[dict[str, Any]] = []
    evidence: list[str] = []
    for path in paths:
        raw = _read_json_or_none(path)
        if raw is None:
            continue
        evidence.append(str(path))
        rows = raw if isinstance(raw, list) else [raw]
        for row in rows:
            if not isinstance(row, dict):
                continue
            step = str(row.get("step") or "").strip()
            if step:
                steps.append(step)
            events.append(row)
    return steps, events, evidence


def _artifact_snapshot(job_id: str, run_dir: Path | None) -> dict[str, dict[str, Any]]:
    roots: list[Path] = []
    if job_id:
        roots.append(LOCAL_ARTIFACTS_ROOT / job_id)
    if run_dir is not None:
        roots.append(run_dir)
    packets: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_CONTRACT_ARTIFACTS:
        chosen = {"exists": False, "bytes": 0, "sha256": "", "path": ""}
        for root in roots:
            packet = _file_packet(root / name)
            if packet["exists"]:
                chosen = packet
                break
            if not chosen["path"]:
                chosen = packet
        packets[name] = chosen
    return packets


def _all_required_present(snapshot: dict[str, dict[str, Any]]) -> bool:
    return all(bool(packet.get("exists")) for packet in snapshot.values())


def _checkpoint_candidates(job_id: str, run_dir: Path | None) -> list[Path]:
    paths: list[Path] = []
    if run_dir is not None:
        paths.extend(
            [
                run_dir / "session" / "checkpoints" / "s07_finalize.json",
                run_dir / "session" / "checkpoints" / "latest.json",
                run_dir / "recovered-artifacts" / "checkpoints" / "s07_finalize.json",
                run_dir / "checkpoints" / "s07_finalize.json",
            ]
        )
    if job_id:
        paths.append(LOCAL_ARTIFACTS_ROOT / job_id / "checkpoints" / "s07_finalize.json")
    return paths


def _checkpoint_authority_candidates(job_id: str, run_dir: Path | None) -> list[Path]:
    paths: list[Path] = []
    if run_dir is not None:
        paths.extend(
            [
                run_dir / "checkpoints" / S07_CHECKPOINT_AUTHORITY_FILE,
                run_dir / "session" / "checkpoints" / S07_CHECKPOINT_AUTHORITY_FILE,
                run_dir / "recovered-artifacts" / "checkpoints" / S07_CHECKPOINT_AUTHORITY_FILE,
            ]
        )
    if job_id:
        paths.append(LOCAL_ARTIFACTS_ROOT / job_id / "checkpoints" / S07_CHECKPOINT_AUTHORITY_FILE)
    return paths


def _macro_verdict_authority_candidates(job_id: str, run_dir: Path | None) -> list[Path]:
    paths: list[Path] = []
    if run_dir is not None:
        paths.extend(
            [
                run_dir / MACRO_VERDICT_AUTHORITY_FILE,
                run_dir / "recovered-artifacts" / MACRO_VERDICT_AUTHORITY_FILE,
                run_dir / "session" / MACRO_VERDICT_AUTHORITY_FILE,
            ]
        )
    if job_id:
        paths.append(LOCAL_ARTIFACTS_ROOT / job_id / MACRO_VERDICT_AUTHORITY_FILE)
    return paths


def _final_status_authority_candidates(job_id: str, run_dir: Path | None) -> list[Path]:
    paths: list[Path] = []
    if run_dir is not None:
        paths.extend(
            [
                run_dir / FINAL_STATUS_AUTHORITY_FILE,
                run_dir / "recovered-artifacts" / FINAL_STATUS_AUTHORITY_FILE,
                run_dir / "session" / FINAL_STATUS_AUTHORITY_FILE,
            ]
        )
    if job_id:
        paths.append(LOCAL_ARTIFACTS_ROOT / job_id / FINAL_STATUS_AUTHORITY_FILE)
    return paths


def _first_json(paths: list[Path]) -> tuple[dict[str, Any], str]:
    for path in paths:
        payload = _read_json_or_none(path)
        if isinstance(payload, dict):
            return payload, str(path)
    return {}, ""


def _load_status(job_id: str, run_dir: Path | None) -> tuple[dict[str, Any], str]:
    paths: list[Path] = []
    if run_dir is not None:
        paths.extend([run_dir / "job-status-final.json", run_dir / "status.json", run_dir / "job-status-analyze.json"])
    if job_id:
        paths.append(LOCAL_ARTIFACTS_ROOT / job_id / "status.json")
    return _first_json(paths)


def _load_verdict(paths: list[Path]) -> tuple[dict[str, Any], str]:
    return _first_json(paths)


def _status_terminal(status: dict[str, Any]) -> bool:
    return str(status.get("status") or "").strip().lower() in {"done", "error", "failed", "cancelled"}


def _classify_artifact_child(
    *,
    artifact_snapshot: dict[str, dict[str, Any]],
    s07_replay: dict[str, Any],
    trace_steps: list[str],
) -> dict[str, Any]:
    replay_emit = s07_replay.get("emit") if isinstance(s07_replay.get("emit"), dict) else {}
    replay_after = s07_replay.get("after") if isinstance(s07_replay.get("after"), dict) else {}
    present = _all_required_present(artifact_snapshot)
    replay_present = _all_required_present(replay_after) if replay_after else False
    recovered_without_return = bool(
        replay_emit.get("recovered_without_child_return")
        or replay_emit.get("recovered_after_timeout")
    )
    emit_ok = str(replay_emit.get("status") or "").strip().lower() == "ok" or replay_emit.get("exit_code") == 0
    if present or replay_present:
        state = "present"
        if recovered_without_return:
            state = "recovered_without_child_return"
    elif emit_ok:
        state = "emit_returned_without_required_artifacts"
    else:
        state = "missing"
    return {
        "state": state,
        "decision_bearing": state in {"missing", "emit_returned_without_required_artifacts"},
        "required_artifacts_present": present,
        "replay_required_artifacts_present": replay_present,
        "recovered_without_child_return": recovered_without_return,
        "trace_returned": "s07_run_returned" in trace_steps,
        "evidence": {
            "required_artifacts": artifact_snapshot,
            "replay_result": str(s07_replay.get("_path") or ""),
        },
    }


def _classify_checkpoint_save(
    *,
    checkpoint: dict[str, Any],
    checkpoint_path: str,
    authority: dict[str, Any],
    authority_path: str,
    trace_steps: list[str],
) -> dict[str, Any]:
    completed = bool(checkpoint.get("completed"))
    authority_state = str(authority.get("state") or "").strip().lower()
    authority_returned = authority_state == "returned"
    authority_failed = authority_state in {"failed", "timeout", "failed_or_timeout"}
    returned = "s07_checkpoint_save_returned" in trace_steps
    failed = any(step in trace_steps for step in ("s07_checkpoint_save_failed", "s07_checkpoint_save_timeout"))
    if completed or authority_returned or returned:
        state = "returned"
    elif authority_failed or failed:
        state = "failed_or_timeout"
    else:
        state = "missing"
    return {
        "state": state,
        "decision_bearing": state != "returned",
        "checkpoint_completed": completed,
        "authority_state": authority.get("state"),
        "authority_returned": authority_returned,
        "trace_returned": returned,
        "trace_failed_or_timed_out": failed or authority_failed,
        "evidence": {
            "checkpoint_path": checkpoint_path,
            "checkpoint_present": bool(checkpoint_path),
            "authority_path": authority_path,
            "authority_present": bool(authority_path),
            "authority_checkpoint_blob": authority.get("checkpoint_blob"),
            "authority_checkpoint_sha256": authority.get("checkpoint_sha256"),
        },
    }


def _classify_macro_verdict(
    *,
    verdict: dict[str, Any],
    verdict_path: str,
    authority: dict[str, Any],
    authority_path: str,
    trace_steps: list[str],
) -> dict[str, Any]:
    authority_state = str(authority.get("state") or "").strip().lower()
    authority_returned = authority_state == "returned"
    authority_failed = authority_state in {"failed", "timeout", "failed_or_timeout"}
    persisted = bool(verdict_path)
    computed = "macro_verdict_computed" in trace_steps
    deferred = "macro_verdict_persist_deferred" in trace_steps
    if persisted or authority_returned:
        state = "persisted"
    elif authority_failed:
        state = "failed_or_timeout"
    elif deferred:
        state = "deferred"
    elif computed:
        state = "computed_not_persisted"
    else:
        state = "missing"
    return {
        "state": state,
        "decision_bearing": state != "persisted",
        "verdict_status": verdict.get("status"),
        "authority_state": authority.get("state"),
        "authority_returned": authority_returned,
        "trace_computed": computed,
        "trace_deferred": deferred,
        "trace_failed_or_timed_out": authority_failed,
        "evidence": {
            "verdict_path": verdict_path,
            "verdict_present": persisted,
            "authority_path": authority_path,
            "authority_present": bool(authority_path),
            "authority_verdict_blob": authority.get("verdict_blob"),
            "authority_verdict_sha256": authority.get("verdict_sha256"),
            "authority_error": authority.get("error"),
        },
    }


def _classify_terminal_status(
    *,
    status: dict[str, Any],
    status_path: str,
    authority: dict[str, Any],
    authority_path: str,
    trace_steps: list[str],
) -> dict[str, Any]:
    authority_state = str(authority.get("state") or "").strip().lower()
    authority_returned = authority_state == "returned"
    authority_failed = authority_state in {"failed", "timeout", "failed_or_timeout"}
    terminal = _status_terminal(status)
    deferred = "worker_close_done_deferred" in trace_steps or "final_worker_verdict_persist_timeout" in trace_steps
    if terminal or authority_returned:
        state = "terminal"
    elif authority_failed:
        state = "failed_or_timeout"
    elif deferred:
        state = "deferred"
    else:
        state = "nonterminal"
    return {
        "state": state,
        "decision_bearing": state != "terminal",
        "status": status.get("status"),
        "explore_phase": status.get("explore_phase"),
        "explore_stage": status.get("explore_stage"),
        "explore_span": status.get("explore_span"),
        "explore_span_state": status.get("explore_span_state"),
        "authority_state": authority.get("state"),
        "authority_returned": authority_returned,
        "trace_deferred": deferred,
        "trace_failed_or_timed_out": authority_failed,
        "evidence": {
            "status_path": status_path,
            "status_present": bool(status_path),
            "authority_path": authority_path,
            "authority_present": bool(authority_path),
            "authority_status_blob": authority.get("status_blob"),
            "authority_status_sha256": authority.get("status_sha256"),
            "authority_predecessor_verdict_blob": authority.get("predecessor_verdict_blob"),
            "authority_predecessor_verdict_sha256": authority.get("predecessor_verdict_sha256"),
            "authority_predecessor_authority_blob": authority.get("predecessor_authority_blob"),
            "authority_predecessor_authority_sha256": authority.get("predecessor_authority_sha256"),
            "authority_error": authority.get("error"),
        },
    }


def _choose_sharp_signal(boundaries: dict[str, dict[str, Any]]) -> str:
    if boundaries["artifact_child_return"]["decision_bearing"]:
        return "s07_contract_artifact_child_return_missing"
    if boundaries["checkpoint_save_return"]["decision_bearing"]:
        return "s07_checkpoint_closeout_missing"
    if boundaries["macro_verdict_persist"]["decision_bearing"]:
        return "s07_macro_verdict_persist_missing"
    if boundaries["terminal_status_persist"]["decision_bearing"]:
        return "s07_terminal_status_closeout_missing"
    return "s07_managed_closeout_green"


def classify_s07_managed_closeout(
    *,
    source_proof_root: Path,
    target: str,
    output_root: Path,
    job_id: str = "",
    s07_replay_result: Path | None = None,
) -> dict[str, Any]:
    source_proof_root = Path(source_proof_root).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = _target_run_dir(source_proof_root, target, job_id=job_id)
    run_result = _read_json_or_none(run_dir / "run_result.json") if run_dir else {}
    if not isinstance(run_result, dict):
        run_result = {}
    resolved_job_id = str(job_id or run_result.get("job_id") or "").strip()

    s07_replay: dict[str, Any] = {}
    if s07_replay_result is not None:
        loaded = _read_json_or_none(Path(s07_replay_result))
        if isinstance(loaded, dict):
            s07_replay = loaded
            s07_replay["_path"] = str(Path(s07_replay_result))

    trace_paths: list[Path] = []
    if run_dir is not None:
        trace_paths.append(run_dir / "worker_close_trace.json")
    if resolved_job_id:
        trace_paths.append(LOCAL_ARTIFACTS_ROOT / resolved_job_id / "worker_close_trace.json")
    trace_steps, trace_events, trace_evidence = _load_trace_steps(trace_paths)

    artifact_snapshot = _artifact_snapshot(resolved_job_id, run_dir)
    checkpoint, checkpoint_path = _first_json(_checkpoint_candidates(resolved_job_id, run_dir))
    checkpoint_authority, checkpoint_authority_path = _first_json(_checkpoint_authority_candidates(resolved_job_id, run_dir))
    macro_verdict_authority, macro_verdict_authority_path = _first_json(
        _macro_verdict_authority_candidates(resolved_job_id, run_dir)
    )
    final_status_authority, final_status_authority_path = _first_json(
        _final_status_authority_candidates(resolved_job_id, run_dir)
    )
    status, status_path = _load_status(resolved_job_id, run_dir)
    verdict_paths: list[Path] = []
    if run_dir is not None:
        verdict_paths.extend([run_dir / "macro_verdict.json", run_dir / "verdict.json"])
    if resolved_job_id:
        verdict_paths.extend([LOCAL_ARTIFACTS_ROOT / resolved_job_id / "macro_verdict.json", LOCAL_ARTIFACTS_ROOT / resolved_job_id / "verdict.json"])
    verdict, verdict_path = _load_verdict(verdict_paths)

    boundaries = {
        "artifact_child_return": _classify_artifact_child(
            artifact_snapshot=artifact_snapshot,
            s07_replay=s07_replay,
            trace_steps=trace_steps,
        ),
        "checkpoint_save_return": _classify_checkpoint_save(
            checkpoint=checkpoint,
            checkpoint_path=checkpoint_path,
            authority=checkpoint_authority,
            authority_path=checkpoint_authority_path,
            trace_steps=trace_steps,
        ),
        "macro_verdict_persist": _classify_macro_verdict(
            verdict=verdict,
            verdict_path=verdict_path,
            authority=macro_verdict_authority,
            authority_path=macro_verdict_authority_path,
            trace_steps=trace_steps,
        ),
        "terminal_status_persist": _classify_terminal_status(
            status=status,
            status_path=status_path,
            authority=final_status_authority,
            authority_path=final_status_authority_path,
            trace_steps=trace_steps,
        ),
    }
    sharp_signal = _choose_sharp_signal(boundaries)
    classification = "local_bug" if sharp_signal == "s07_managed_closeout_green" else "family_blocker"
    if sharp_signal == "s07_managed_closeout_green":
        next_action = "use one full Hard03 confirmation only if lane trust and rerun gates pass"
    elif sharp_signal == "s07_checkpoint_closeout_missing":
        next_action = "repair or instrument S-07 checkpoint-save return before full Hard03 confirmation"
    elif sharp_signal == "s07_macro_verdict_persist_missing":
        next_action = "repair macro verdict persistence before full Hard03 confirmation"
    elif sharp_signal == "s07_terminal_status_closeout_missing":
        next_action = "repair final terminal status persistence before full Hard03 confirmation"
    else:
        next_action = "repair contract artifact child-return authority before full Hard03 confirmation"

    result = {
        "schema_version": "1.0.0",
        "claim_ceiling": CLAIM_CEILING,
        "safe_to_compare": False,
        "product_green_claimed": False,
        "source_proof_root": str(source_proof_root),
        "target": target,
        "target_run_dir": str(run_dir or ""),
        "job_id": resolved_job_id,
        "parent_signal": "runner_observed_nonterminal_timeout",
        "sharp_signal": sharp_signal,
        "classification": classification,
        "next_action": next_action,
        "boundary_order": [
            "artifact_child_return",
            "checkpoint_save_return",
            "macro_verdict_persist",
            "terminal_status_persist",
        ],
        **boundaries,
        "trace": {
            "steps": trace_steps,
            "events": trace_events,
            "evidence_paths": trace_evidence,
        },
        "run_result_hint": {
            "status": run_result.get("status"),
            "failure_domain": run_result.get("failure_domain"),
            "run_validity": run_result.get("run_validity"),
        },
    }
    _write_json(output_root / "s07-managed-closeout-classification.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify managed S-07 closeout boundaries from existing Hard03 artifacts without rerunning or mutating source artifacts."
    )
    parser.add_argument("--source-proof-root", required=True, type=Path)
    parser.add_argument("--target", default="fee_quote")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--job-id", default="")
    parser.add_argument("--s07-replay-result", type=Path, default=None)
    args = parser.parse_args(argv)
    result = classify_s07_managed_closeout(
        source_proof_root=args.source_proof_root,
        target=args.target,
        output_root=args.output_root,
        job_id=args.job_id,
        s07_replay_result=args.s07_replay_result,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("target_run_dir") else 1


if __name__ == "__main__":
    raise SystemExit(main())
