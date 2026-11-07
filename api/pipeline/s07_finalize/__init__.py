"""S-07: Behavioral Spec + Harmonization + Contract Artifacts."""

from __future__ import annotations

import logging
import os
import json
import subprocess
import sys
import time
from pathlib import Path

from api.infra.storage_api import get_job_status as _get_job_status, persist_job_status as _persist_job_status
from api.pipeline.s07_finalize.behavioral_spec import _run_phase_9_behavioral_spec  # noqa: F401
from api.pipeline.s07_finalize.harmonize import (  # noqa: F401
    _run_phase_10_harmonize,
    _run_finalize,
)
# Runtime-owned metadata modules for stage contracts/capture surfaces.
from api.pipeline.s07_finalize import checkpoint_hooks as _checkpoint_hooks  # noqa: F401
from api.pipeline.s07_finalize import context as _stage_context  # noqa: F401
from api.pipeline.s07_finalize import session_artifacts as _session_artifacts  # noqa: F401

logger = logging.getLogger("mcp_factory.api")
REPO_ROOT = Path(__file__).resolve().parents[3]
LOCAL_ARTIFACTS_ROOT = REPO_ROOT / "local-data" / "artifacts"
REQUIRED_CONTRACT_ARTIFACTS = (
    "session-meta.json",
    "stage-index.json",
    "transition-index.json",
    "cohesion-report.json",
)


def _contract_artifact_timeout_sec() -> float:
    raw = os.getenv("MCP_S07_CONTRACT_ARTIFACT_TIMEOUT_SEC", "30")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 30.0
    return max(1.0, value)

def _record_contract_artifact_span(job_id: str, state: str, message: str) -> None:
    current = _get_job_status(job_id) or {}
    _persist_job_status(
        job_id,
        {
            **current,
            "explore_stage": "s07_finalize",
            "explore_span": "s07_emit_contract_artifacts",
            "explore_span_state": state,
            "explore_span_message": message,
            "explore_span_updated_at": time.time(),
            "updated_at": time.time(),
        },
        sync=False,
    )


def _read_json_line(text: str) -> dict:
    for line in reversed((text or "").splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except Exception:
            continue
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _contract_artifact_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


def _contract_artifacts_present(job_id: str) -> bool:
    root = LOCAL_ARTIFACTS_ROOT / str(job_id)
    return all((root / name).is_file() for name in REQUIRED_CONTRACT_ARTIFACTS)


def _start_contract_artifact_subprocess(job_id: str) -> subprocess.Popen[str]:
    code = (
        "import json\n"
        "from api.analysis.cohesion import emit_contract_artifacts\n"
        f"result = emit_contract_artifacts({job_id!r})\n"
        "print(json.dumps({'ok': True, 'keys': sorted(result.keys())}))\n"
    )
    return subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_contract_artifact_creationflags(),
    )


def _stop_contract_artifact_subprocess(proc: subprocess.Popen[str]) -> None:
    try:
        proc.kill()
    except Exception:
        return


def _run_contract_artifact_subprocess(job_id: str, timeout_sec: float) -> dict:
    started_at = time.monotonic()
    deadline = started_at + float(timeout_sec)
    proc = _start_contract_artifact_subprocess(job_id)
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=1)
            return {
                "returncode": proc.returncode,
                "stdout": stdout or "",
                "stderr": stderr or "",
                "recovered_after_timeout": False,
                "recovered_without_child_return": False,
            }
        if time.monotonic() - started_at >= 1.0 and _contract_artifacts_present(job_id):
            _stop_contract_artifact_subprocess(proc)
            return {
                "returncode": 0,
                "stdout": json.dumps({"ok": True, "keys": sorted(REQUIRED_CONTRACT_ARTIFACTS)}) + "\n",
                "stderr": "",
                "recovered_after_timeout": True,
                "recovered_without_child_return": True,
            }
        time.sleep(0.05)

    if _contract_artifacts_present(job_id):
        _stop_contract_artifact_subprocess(proc)
        return {
            "returncode": 0,
            "stdout": json.dumps({"ok": True, "keys": sorted(REQUIRED_CONTRACT_ARTIFACTS)}) + "\n",
            "stderr": "",
            "recovered_after_timeout": True,
            "recovered_without_child_return": True,
        }

    _stop_contract_artifact_subprocess(proc)
    raise TimeoutError("s07_emit_contract_artifacts_timeout")


def _emit_contract_artifacts_with_timeout(job_id: str, timeout_sec: float) -> dict:
    completed = _run_contract_artifact_subprocess(job_id, timeout_sec)
    if completed.get("returncode") != 0:
        stderr = str(completed.get("stderr") or "").strip()
        stdout = str(completed.get("stdout") or "").strip()
        detail = stderr or stdout or f"returncode={completed.get('returncode')}"
        raise RuntimeError(f"s07_emit_contract_artifacts_failed:{detail}")
    stdout = str(completed.get("stdout") or "")
    stderr = str(completed.get("stderr") or "")
    payload = _read_json_line(stdout)
    keys = list(payload.get("keys") or [])
    return {
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
        "returncode": completed.get("returncode"),
        "keys": sorted(str(key) for key in keys),
        "recovered_after_timeout": bool(completed.get("recovered_after_timeout")),
        "recovered_without_child_return": bool(completed.get("recovered_without_child_return")),
    }


def _emit_contract_artifacts_durable(job_id: str) -> None:
    """Emit S-07 contract artifacts with a process boundary so closeout can trust them."""
    started_at = time.time()
    _record_contract_artifact_span(job_id, "start", "S-07 finalize: emitting contract artifacts...")
    result: dict = {}
    try:
        result = _emit_contract_artifacts_with_timeout(job_id, _contract_artifact_timeout_sec())
    except TimeoutError:
        duration_sec = round(max(0.0, time.time() - started_at), 3)
        _record_contract_artifact_span(
            job_id,
            "timeout",
            f"S-07 finalize: contract artifact emission timed out after {duration_sec}s.",
        )
        raise
    except Exception as exc:
        duration_sec = round(max(0.0, time.time() - started_at), 3)
        _record_contract_artifact_span(
            job_id,
            "fail",
            f"S-07 finalize: contract artifact emission failed after {duration_sec}s: {exc}",
        )
        logger.warning("[%s] emit_contract_artifacts (S-07 finally) failed: %s", job_id, exc)
        raise
    duration_sec = round(max(0.0, time.time() - started_at), 3)
    recovery_note = " with child-return recovery" if (result or {}).get("recovered_without_child_return") else ""
    _record_contract_artifact_span(
        job_id,
        "done",
        f"S-07 finalize: contract artifacts emitted{recovery_note} in {duration_sec}s.",
    )


def run_s07(ctx) -> None:
    """S-07 entry point: harmonize + finalize.

    Always attempts ``emit_contract_artifacts`` in a ``finally`` block so session snapshots
    and save-session v2 see ``session-meta`` / ``stage-index`` / ``transition-index`` /
    ``cohesion-report`` even if finalize raises mid-way.
    """
    try:
        _run_phase_10_harmonize(ctx)
        _run_finalize(ctx)
    finally:
        _emit_contract_artifacts_durable(ctx.job_id)
