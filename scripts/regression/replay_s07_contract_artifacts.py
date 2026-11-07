from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_ARTIFACTS_ROOT = REPO_ROOT / "local-data" / "artifacts"
REQUIRED_CONTRACT_ARTIFACTS = (
    "session-meta.json",
    "stage-index.json",
    "transition-index.json",
    "cohesion-report.json",
)
CLAIM_CEILING = "s07_contract_artifact_replay_only"


def _read_json_or_none(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _file_packet(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"exists": False, "bytes": 0, "sha256": ""}
    data = path.read_bytes()
    return {
        "exists": True,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mtime": path.stat().st_mtime,
    }


def _artifact_snapshot(job_dir: Path) -> dict[str, dict[str, Any]]:
    return {name: _file_packet(job_dir / name) for name in REQUIRED_CONTRACT_ARTIFACTS}


def _missing_required(snapshot: dict[str, dict[str, Any]]) -> list[str]:
    return [name for name, packet in snapshot.items() if not bool(packet.get("exists"))]


def _emit_contract_artifacts_subprocess(job_id: str, timeout_sec: float) -> dict[str, Any]:
    # Keep the executable payload constructed in one place so tests can
    # monkeypatch this function without invoking a subprocess.
    code = (
        "import json\n"
        "from api.analysis.cohesion import emit_contract_artifacts\n"
        f"result = emit_contract_artifacts({job_id!r})\n"
        "print(json.dumps({'ok': True, 'keys': sorted(result.keys())}))\n"
    )
    started = time.time()
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "exit_code": None,
            "elapsed_sec": round(max(0.0, time.time() - started), 3),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    payload = _read_json_line(completed.stdout)
    return {
        "status": "ok" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "elapsed_sec": round(max(0.0, time.time() - started), 3),
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "payload": payload,
    }


def _read_json_line(text: str) -> Any | None:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except Exception:
            continue
    return None


def _classify_emit_result(
    emit: dict[str, Any],
    after: dict[str, dict[str, Any]],
    status: dict[str, Any],
    checkpoint: dict[str, Any],
) -> str:
    if emit.get("status") == "timeout":
        return "s07_contract_artifact_emit_timeout"
    if emit.get("status") != "ok":
        return "s07_contract_artifact_emit_failed"
    if _missing_required(after):
        return "s07_contract_artifact_missing_outputs"
    if not bool(checkpoint.get("completed")):
        return "s07_checkpoint_closeout_missing"
    if str(status.get("status") or "").strip().lower() != "done":
        return "s07_terminal_status_closeout_missing"
    return "s07_contract_artifact_replay_green"


def replay_s07_contract_artifacts(
    *,
    job_id: str,
    output_root: Path,
    mode: str = "strict",
    timeout_sec: float = 30.0,
) -> dict[str, Any]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    job_id = str(job_id or "").strip()
    job_dir = LOCAL_ARTIFACTS_ROOT / job_id
    result_path = output_root / "s07-contract-artifact-replay-result.json"

    if not job_id or not job_dir.exists() or not job_dir.is_dir():
        result = {
            "schema_version": "1.0.0",
            "mode": mode,
            "claim_ceiling": CLAIM_CEILING,
            "product_green_claimed": False,
            "safe_to_compare": False,
            "checkpoint_first_result": "unavailable",
            "last_trusted_boundary": "09-audit_trace job artifact root",
            "changed_seam": "s07.contract_artifact_emission",
            "source_job_id": job_id,
            "source_job_artifact_root": str(job_dir),
            "blocking_signal": "checkpoint_artifact_root_missing",
            "classification": "missing_system",
            "reason": "source job artifact root is unavailable",
        }
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result

    before = _artifact_snapshot(job_dir)
    emit = _emit_contract_artifacts_subprocess(job_id, timeout_sec)
    after = _artifact_snapshot(job_dir)
    status = _read_json_or_none(job_dir / "status.json") or {}
    checkpoint = _read_json_or_none(job_dir / "checkpoints" / "s07_finalize.json") or {}
    blocking_signal = _classify_emit_result(emit, after, status, checkpoint)
    classification = (
        "local_bug"
        if blocking_signal == "s07_contract_artifact_replay_green"
        else "family_blocker"
    )
    if blocking_signal in {
        "s07_checkpoint_closeout_missing",
        "s07_terminal_status_closeout_missing",
    }:
        next_action = "repair live S-07 checkpoint/status closeout integration before full Hard03 confirmation"
    elif blocking_signal == "s07_contract_artifact_replay_green":
        next_action = "S-07 contract artifact and closeout replay is green; use full suite only for confirmation"
    else:
        next_action = "repair contract artifact emission before full Hard03 confirmation"
    result = {
        "schema_version": "1.0.0",
        "mode": mode,
        "claim_ceiling": CLAIM_CEILING,
        "product_green_claimed": False,
        "safe_to_compare": False,
        "checkpoint_first_result": "used",
        "last_trusted_boundary": "09-audit_trace job artifact root",
        "changed_seam": "s07.contract_artifact_emission",
        "source_job_id": job_id,
        "source_job_artifact_root": str(job_dir),
        "source_job_status": {
            "status": status.get("status"),
            "explore_phase": status.get("explore_phase"),
            "explore_stage": status.get("explore_stage"),
            "explore_span": status.get("explore_span"),
            "explore_span_state": status.get("explore_span_state"),
        },
        "source_s07_checkpoint": {
            "completed": bool(checkpoint.get("completed")),
            "phase": checkpoint.get("phase"),
        },
        "before": before,
        "after": after,
        "missing_required_after": _missing_required(after),
        "emit": emit,
        "blocking_signal": blocking_signal,
        "classification": classification,
        "next_action_hint": next_action,
    }
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay only S-07 contract artifact emission for a frozen job artifact root.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--mode", choices=["strict"], default="strict")
    parser.add_argument("--timeout-sec", type=float, default=30.0)
    args = parser.parse_args(argv)
    result = replay_s07_contract_artifacts(
        job_id=args.job_id,
        output_root=args.output_root,
        mode=args.mode,
        timeout_sec=args.timeout_sec,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("blocking_signal") != "checkpoint_artifact_root_missing" else 1


if __name__ == "__main__":
    raise SystemExit(main())
