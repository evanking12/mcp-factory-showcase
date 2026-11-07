from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import requests

from harness_lib import collector

REQUIRED_CONTRACT_FILES = (
    "session-meta.json",
    "stage-index.json",
    "transition-index.json",
    "cohesion-report.json",
)
MANIFEST_SCHEMA_VERSION = "1.0.0"
CONTRACT_BARRIER_MAX_ATTEMPTS = 6
CONTRACT_BARRIER_SLEEP_SECONDS = 0.5


def _env_flag(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _should_skip_snapshot(api_url: str) -> bool:
    forced = _env_flag("HARNESS_CAPTURE_BLOB_ONLY")
    if forced is not None:
        return forced
    url = str(api_url or "").lower()
    return "127.0.0.1" in url or "localhost" in url


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def _json_blob_is_parseable(data: bytes | None) -> bool:
    if not data:
        return False
    try:
        json.loads(data.decode("utf-8-sig"))
    except Exception:
        return False
    return True


def _session_meta_overlay(status: dict[str, Any]) -> dict[str, Any]:
    explore_runtime = status.get("explore_runtime") or {}
    return {
        "campaign_id": str(status.get("campaign_id") or explore_runtime.get("campaign_id") or ""),
        "package_id": str(status.get("package_id") or ""),
        "package_label": str(status.get("package_label") or ""),
        "lane_id": str(status.get("lane_id") or explore_runtime.get("lane_id") or ""),
        "lane_trust_status": str(status.get("lane_trust_status") or ""),
        "selection_reason": str(status.get("selection_reason") or ""),
        "doc_visibility": str(status.get("doc_visibility") or ""),
        "dependency_context": str(status.get("dependency_context") or ""),
        "blocker_family_primary": str(status.get("blocker_family_primary") or ""),
        "blocker_family_secondary": list(status.get("blocker_family_secondary") or []),
        "blocker_confidence": str(status.get("blocker_confidence") or ""),
        "architecture_relevance": str(status.get("architecture_relevance") or ""),
        "runtime_path_trust": str(status.get("runtime_path_trust") or ""),
        "analysis_profile": str(explore_runtime.get("analysis_profile") or "strict_dll"),
        "parallel_runs": int(explore_runtime.get("parallel_runs") or 1),
        "variant_configs_count": len(explore_runtime.get("variant_configs") or []),
        "variant_id": str(explore_runtime.get("variant_id") or ""),
        "prior_job_id": str(explore_runtime.get("prior_job_id") or ""),
        "cross_dll_prior_job_ids": list(explore_runtime.get("cross_dll_prior_job_ids") or []),
        "graph_epoch": str(explore_runtime.get("graph_epoch") or "none"),
    }


def _patched_session_meta_bytes(raw: bytes | None, *, status: dict[str, Any]) -> bytes:
    payload: dict[str, Any] = {}
    if raw:
        try:
            parsed = json.loads(raw.decode("utf-8-sig"))
            if isinstance(parsed, dict):
                payload = dict(parsed)
        except Exception:
            payload = {}
    if not payload:
        payload = {
            "job_id": str(status.get("job_id") or ""),
            "component": str(status.get("component_name") or "unknown"),
            "dll_path": status.get("target_path") or status.get("file_path"),
            "dll_sha256": status.get("dll_sha256"),
            "analysis_entrypoint": status.get("analysis_entrypoint"),
            "binary_origin": status.get("binary_origin"),
            "explore_phase": str(status.get("explore_phase") or ""),
            "hints": str(status.get("hints") or ""),
            "use_cases": str(status.get("use_cases") or ""),
            "created_at": status.get("created_at"),
            "updated_at": status.get("updated_at"),
            "verification_verified": int(status.get("verification_verified") or 0),
            "verification_inferred": int(status.get("verification_inferred") or 0),
            "verification_error": int(status.get("verification_error") or 0),
            "snapshot_profile": "full",
        }
    payload.update(_session_meta_overlay(status))
    return _json_bytes(payload)


def _build_hints_text(status: dict[str, Any]) -> str:
    raw_hints = str(status.get("hints") or "")
    clean_hints = " | ".join(
        part.strip()
        for part in raw_hints.split(" | ")
        if part.strip() and not part.strip().startswith("DOMAIN ANSWER")
    )
    lines: list[str] = []
    if clean_hints:
        lines.append("# User Hints\n")
        lines.append(clean_hints)
    use_cases = str(status.get("use_cases") or "").strip()
    if use_cases:
        lines.append("\n\n# Use Cases\n")
        lines.append(use_cases)
    return "\n".join(lines) if lines else "(none)"


def _default_blob_bytes(
    blob_name: str,
    *,
    status: dict[str, Any],
    fetched: dict[str, bytes],
) -> bytes:
    if blob_name in {
        "mc-decisions/mc3-post-reconcile.json",
        "mc-decisions/mc4-post-synthesis.json",
        "mc-decisions/mc5-post-verification.json",
        "mc-decisions/mc6-post-gap-resolution.json",
    }:
        return _json_bytes({})
    if blob_name in {
        "gap_resolution_log.json",
        "executor_trace.json",
        "schema_evolution.json",
    }:
        return _json_bytes([])
    if blob_name in {
        "mcp_schema_pre_mini_session.json",
        "mcp_schema_post_mini_session.json",
    }:
        for candidate in (
            "mcp_schema_post_discovery.json",
            "mcp_schema.json",
            "mcp_schema_t0.json",
        ):
            data = fetched.get(candidate)
            if data:
                return data
        return _json_bytes({})
    if blob_name == "session-meta.json":
        return _patched_session_meta_bytes(None, status=status)
    if blob_name.endswith(".json"):
        return _json_bytes({})
    return b""


def _await_required_contract_blobs(
    *,
    job_id: str,
    download: Any,
    emit_contract_artifacts: Any,
    get_job_status: Any,
) -> dict[str, Any]:
    barrier: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "job_id": str(job_id or ""),
        "ready": False,
        "attempts": 0,
        "max_attempts": CONTRACT_BARRIER_MAX_ATTEMPTS,
        "required_files": list(REQUIRED_CONTRACT_FILES),
        "missing_files": list(REQUIRED_CONTRACT_FILES),
        "invalid_files": [],
        "emit_attempted": False,
        "span_state": "",
    }
    for attempt in range(1, CONTRACT_BARRIER_MAX_ATTEMPTS + 1):
        status = get_job_status(job_id) or {}
        span_state = str(status.get("explore_span_state") or "").strip().lower()
        missing_files: list[str] = []
        invalid_files: list[str] = []
        for rel in REQUIRED_CONTRACT_FILES:
            data = download(rel)
            if data is None:
                missing_files.append(rel)
                continue
            if not _json_blob_is_parseable(data):
                invalid_files.append(rel)
        barrier.update(
            {
                "attempts": attempt,
                "missing_files": missing_files,
                "invalid_files": invalid_files,
                "span_state": span_state,
            }
        )
        if not missing_files and not invalid_files and span_state not in {"start", "deferred"}:
            barrier["ready"] = True
            return barrier
        if not barrier["emit_attempted"] and (missing_files or invalid_files or span_state in {"start", "deferred"}):
            try:
                emit_contract_artifacts(job_id)
                barrier["emit_attempted"] = True
            except Exception as exc:
                barrier["emit_attempt_error"] = str(exc)
        if attempt < CONTRACT_BARRIER_MAX_ATTEMPTS:
            time.sleep(CONTRACT_BARRIER_SLEEP_SECONDS)
    return barrier


def _materialize_snapshot_from_blobs(
    *,
    temp_dir: Path,
    job_id: str,
    profile: str,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    from api.infra.config import ARTIFACT_CONTAINER
    from api.infra.storage import _download_blob, _get_job_status
    from api.analysis.cohesion import emit_contract_artifacts

    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    status = _get_job_status(job_id) or {"job_id": job_id}
    fetched: dict[str, bytes] = {}
    manifest_entries: dict[str, dict[str, Any]] = {}

    def write_materialized(rel_path: str, data: bytes, *, origin: str, source_blob: str = "") -> None:
        _write_bytes(temp_dir / rel_path, data)
        entry: dict[str, Any] = {"origin": origin}
        if source_blob:
            entry["source_blob"] = source_blob
        manifest_entries[rel_path.replace("\\", "/")] = entry

    def download(blob_name: str) -> bytes | None:
        if blob_name in fetched:
            return fetched[blob_name]
        try:
            data = _download_blob(ARTIFACT_CONTAINER, f"{job_id}/{blob_name}")
        except Exception:
            return None
        fetched[blob_name] = data
        return data

    contract_barrier = _await_required_contract_blobs(
        job_id=job_id,
        download=download,
        emit_contract_artifacts=emit_contract_artifacts,
        get_job_status=_get_job_status,
    )
    write_materialized(
        "session-capture-contract-readiness.json",
        _json_bytes(contract_barrier),
        origin="synthesized_summary",
    )

    for rel in REQUIRED_CONTRACT_FILES:
        data = download(rel)
        if data is None or not _json_blob_is_parseable(data):
            continue
        origin = "emitted"
        if rel == "session-meta.json":
            data = _patched_session_meta_bytes(data, status=status)
            origin = "recovered"
        write_materialized(rel, data, origin=origin, source_blob=rel)

    hints_text = _build_hints_text(status)
    write_materialized("hints.txt", hints_text.encode("utf-8"), origin="synthesized_summary")
    write_materialized(
        "snapshot-profile.json",
        _json_bytes({"profile": profile}),
        origin="synthesized_summary",
    )
    discovery_meta = status.get("discovery_meta") or {}
    write_materialized("discovery_meta.json", _json_bytes(discovery_meta), origin="synthesized_summary")

    extra_files: dict[str, tuple[str, ...]] = {
        "findings.json": ("findings.json",),
        "verification-report.json": ("verification-report.json",),
        "vocab.json": ("vocab.json",),
        "invocables_map.json": ("invocables_map.json",),
        "mcp_schema.json": ("mcp_schema.json",),
        "behavioral_spec.py": ("behavioral_spec.py",),
        "stage-00-setup/s01-handoff-packet.json": ("s01_handoff_packet.json",),
        "evidence/stage-00-setup/s01-handoff-packet.json": ("s01_handoff_packet.json",),
        "stage-00-setup/static-enrichment.json": ("static_enrichment.json",),
        "evidence/stage-00-setup/static-enrichment.json": ("static_enrichment.json",),
        "evidence/stage-00a-setup-baseline/sentinel-calibration.json": ("sentinel_calibration.json",),
        "evidence/stage-00a-setup-baseline/vocab.json": ("vocab.json",),
        "evidence/stage-00b-static-evidence/static-analysis.json": ("static_analysis.json",),
        "evidence/stage-00b-static-evidence/static-enrichment.json": ("static_enrichment.json",),
        "evidence/stage-00b-static-evidence/call-graph.json": ("call_graph.json",),
        "evidence/stage-00b-static-evidence/ghidra-data-types.json": ("ghidra_data_types.json",),
        "evidence/stage-00c-admission-handoff/s01-handoff-packet.json": ("s01_handoff_packet.json",),
        "mc-decisions/winning-init-sequence.json": ("winning_init_sequence.json",),
        "evidence/mc-decisions/winning-init-sequence.json": ("winning_init_sequence.json",),
        "stage-02-synthesis/findings.json": ("findings.json",),
        "stage-05-finalization/findings.json": ("findings.json",),
        "evidence/stage-01-pre-probe/hints.txt": (),
        "evidence/stage-02a-probe-ordering/prerequisite-state-machine.json": ("prerequisite_state_machine.json",),
        "evidence/stage-02b-invocation-execution/stage-context.txt": ("model_context_phase_01_probe_loop.txt",),
        "evidence/stage-02b-invocation-execution/probe-user-message-sample.txt": ("probe_user_message_sample.txt",),
        "evidence/stage-02c-evidence-capture/probe-log.json": ("explore_probe_log.json",),
        "evidence/stage-02c-evidence-capture/findings.json": ("findings.json",),
        "evidence/stage-02c-evidence-capture/param-rename-decisions.json": (
            "evidence/stage-02-probe-loop/param-rename-decisions.json",
        ),
        "evidence/stage-02c-evidence-capture/probe-round-reasoning.json": (
            "evidence/stage-02-probe-loop/probe-round-reasoning.json",
        ),
        "evidence/stage-02c-evidence-capture/probe-stop-reasons.json": (
            "evidence/stage-02-probe-loop/probe-stop-reasons.json",
        ),
        "evidence/stage-02c-evidence-capture/probe-strategy-summary.json": (
            "evidence/stage-02-probe-loop/probe-strategy-summary.json",
        ),
        "evidence/stage-02-probe-loop/stage-context.txt": ("model_context_phase_01_probe_loop.txt",),
        "evidence/stage-02-probe-loop/probe-user-message-sample.txt": ("probe_user_message_sample.txt",),
        "evidence/stage-04-synthesis/stage-context.txt": ("model_context_phase_06_synthesis.txt",),
        "evidence/stage-05a-schema-backfill/backfill-report.json": ("backfill_result.json",),
        "evidence/stage-05a-schema-backfill/schema-post-backfill.json": ("mcp_schema_post_discovery.json",),
        "evidence/stage-05b-verification-replay/verification-report.json": ("verification-report.json",),
        "evidence/stage-05c-read-to-write-chaining/mc5-post-verification.json": (
            "mc-decisions/mc5-post-verification.json",
        ),
        "evidence/stage-07-finalize/schema-evolution.json": ("schema_evolution.json",),
        "diagnostics/executor_trace.json": ("executor_trace.json",),
        "diagnostics/executor-trace.json": ("executor_trace.json",),
        "diagnostics/chat-model-context.txt": ("model_context_phase_01_probe_loop.txt",),
        "diagnostics/chat-system-context-turn0.txt": (
            "chat_system_context_turn0.txt",
            "diagnostics/chat-system-context.txt",
            "diagnostics/chat-system-context-turn0.txt",
        ),
        "checkpoints/latest.json": ("checkpoints/latest.json",),
        "checkpoints/stage_snapshots/s00_setup.json": ("checkpoints/stage_snapshots/s00_setup.json",),
        "checkpoints/stage_snapshots/s01_unlock.json": ("checkpoints/stage_snapshots/s01_unlock.json",),
        "checkpoints/stage_snapshots/s02_probe.json": ("checkpoints/stage_snapshots/s02_probe.json",),
        "checkpoints/stage_snapshots/s03_reconcile.json": ("checkpoints/stage_snapshots/s03_reconcile.json",),
        "checkpoints/stage_snapshots/s04_synthesis.json": ("checkpoints/stage_snapshots/s04_synthesis.json",),
        "checkpoints/stage_snapshots/s05_enrichment.json": ("checkpoints/stage_snapshots/s05_enrichment.json",),
        "checkpoints/stage_snapshots/s05_schema_backfill.json": (
            "checkpoints/stage_snapshots/s05_schema_backfill.json",
        ),
        "checkpoints/stage_snapshots/s05_verification_replay.json": (
            "checkpoints/stage_snapshots/s05_verification_replay.json",
        ),
        "checkpoints/stage_snapshots/s05_read_to_write_chaining.json": (
            "checkpoints/stage_snapshots/s05_read_to_write_chaining.json",
        ),
        "checkpoints/stage_snapshots/s06_gaps.json": ("checkpoints/stage_snapshots/s06_gaps.json",),
        "checkpoints/stage_snapshots/s07_finalize.json": ("checkpoints/stage_snapshots/s07_finalize.json",),
    }
    optional_artifact_blobs = {
        "static_enrichment.json",
        "winning_init_sequence.json",
        "call_graph.json",
        "ghidra_data_types.json",
    }

    for rel_path, blob_candidates in extra_files.items():
        origin = "emitted"
        source_blob = ""
        if rel_path == "evidence/stage-01-pre-probe/hints.txt":
            data = hints_text.encode("utf-8")
            origin = "synthesized_summary"
        else:
            data = None
            for blob_name in blob_candidates:
                data = download(blob_name)
                if data is not None:
                    source_blob = blob_name
                    break
            if data is None:
                fallback_name = blob_candidates[0] if blob_candidates else rel_path
                if fallback_name in optional_artifact_blobs:
                    continue
                data = _default_blob_bytes(fallback_name, status=status, fetched=fetched)
                source_blob = fallback_name
                origin = "recovered"
        write_materialized(rel_path, data, origin=origin, source_blob=source_blob)

    # Compact snapshots may omit broad optional context, but they still need the
    # canonical context artifacts the strict validity audits require.
    required_paths = [
        *collector.STRICT_REQUIRED_STAGE_EVIDENCE,
        *collector.STRICT_REQUIRED_CONTEXT_EVIDENCE,
    ]
    for canonical_path in required_paths:
        path = temp_dir / canonical_path
        if path.exists():
            continue
        aliases = collector.STRICT_EVIDENCE_ALIASES.get(canonical_path, (canonical_path,))
        data = None
        source_blob = ""
        for alias in aliases:
            blob_name = alias
            if alias.startswith("evidence/") or alias.startswith("diagnostics/") or alias.startswith("checkpoints/"):
                blob_name = alias
            data = download(blob_name)
            if data is not None:
                source_blob = blob_name
                break
        if data is None:
            data = _default_blob_bytes(str(aliases[0]), status=status, fetched=fetched)
            write_materialized(canonical_path, data, origin="recovered", source_blob=str(aliases[0]))
            continue
        write_materialized(canonical_path, data, origin="emitted", source_blob=source_blob)

    return _missing_contract_files(temp_dir), manifest_entries


@dataclass
class CaptureResult:
    session_dir: Path
    folder: str
    collect_exit: int
    summary: dict[str, Any]


def _git_short_hash(repo_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
        value = (proc.stdout or "").strip()
        return value or "nogit"
    except Exception:
        return "nogit"


def _git_commit_msg(repo_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
        return (proc.stdout or "").strip() or "no-message"
    except Exception:
        return "no-message"


def _slug(value: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in str(value or ""))
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned.lower() if cleaned else fallback


def _load_component(temp_dir: Path) -> str:
    meta_path = temp_dir / "session-meta.json"
    if not meta_path.exists():
        return "unknown"
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return "unknown"
    component = str((payload or {}).get("component") or "").strip()
    return component or "unknown"


def _default_note(job_id: str, component: str, sessions_root: Path) -> str:
    prefix = job_id[: min(6, len(job_id))]
    existing = [
        p
        for p in sessions_root.glob("*")
        if p.is_dir() and prefix and prefix in p.name
    ]
    run_count = len(existing) + 1
    return f"{_slug(component, 'unknown')}-run{run_count}"


def _copy_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _write_snapshot_profile(session_dir: Path, snapshot_profile: str) -> None:
    dropped: list[str] = []
    if snapshot_profile == "compact":
        for rel in (
            "diagnostics/chat_transcript.txt",
            "diagnostics/executor_trace.json",
        ):
            path = session_dir / rel
            if path.exists():
                try:
                    path.unlink()
                    dropped.append(rel)
                except Exception:
                    pass
    payload: dict[str, Any] = {
        "profile": snapshot_profile,
        "dropped": dropped,
        "saved_at": datetime.now().astimezone().isoformat(),
    }
    if snapshot_profile == "compact":
        payload["kept_required"] = [
            "session-meta.json",
            "stage-index.json",
            "transition-index.json",
            "cohesion-report.json",
        ]
    (session_dir / "snapshot-profile.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _write_session_manifests(
    session_dir: Path,
    *,
    snapshot_profile: str,
    snapshot_mode: str,
    manifest_entries: dict[str, dict[str, Any]] | None = None,
) -> None:
    entries = manifest_entries or {}
    all_rel_paths = [
        path.relative_to(session_dir)
        for path in session_dir.rglob("*")
        if path != session_dir
    ]
    roots = sorted(
        {
            f"{rel.parts[0]}/"
            for rel in all_rel_paths
            if len(rel.parts) > 1
        }
    )
    top_level_files = sorted(
        rel.parts[0]
        for rel in all_rel_paths
        if len(rel.parts) == 1
    )
    checkpoints_dir = session_dir / "checkpoints"
    checkpoint_files = sorted(
        str(path.relative_to(session_dir)).replace("\\", "/")
        for path in checkpoints_dir.rglob("*.json")
    ) if checkpoints_dir.exists() else []

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "snapshot_kind": "job",
        "snapshot_profile": snapshot_profile,
        "snapshot_mode": snapshot_mode,
        "roots": roots,
        "top_level_files": top_level_files,
        "origin_semantics": {
            "emitted": "artifact was emitted by the pipeline or downloaded directly from blob storage",
            "recovered": "artifact was reconstructed or defaulted during save-session materialization",
            "synthesized_summary": "artifact was derived by the save-session layer for archival readability",
        },
        "entries": entries,
    }
    (session_dir / "session-manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    checkpoint_manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "snapshot_kind": "job_checkpoint_set",
        "snapshot_profile": snapshot_profile,
        "checkpoint_files": checkpoint_files,
    }
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    (checkpoints_dir / "manifest.json").write_text(
        json.dumps(checkpoint_manifest, indent=2),
        encoding="utf-8",
    )


def _download_snapshot(
    *,
    api_url: str,
    job_id: str,
    profile: str,
    headers: dict[str, str],
) -> bytes:
    timeout_sec = int(
        os.getenv(
            "HARNESS_CAPTURE_SNAPSHOT_TIMEOUT_SEC",
            "30" if "127.0.0.1" in api_url or "localhost" in api_url else "180",
        )
    )
    snapshot_url = (
        f"{api_url.rstrip('/')}/api/jobs/{job_id}/session-snapshot?profile={profile}"
    )
    response = requests.get(snapshot_url, headers=headers, timeout=timeout_sec)
    response.raise_for_status()
    content = response.content or b""
    if len(content) < 2048:
        raise RuntimeError("capture_too_small (zip < 2KB)")
    return content


def _extract_snapshot_zip(zip_bytes: bytes, out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
        zf.extractall(out_dir)


def _missing_contract_files(session_dir: Path) -> list[str]:
    missing: list[str] = []
    for rel in REQUIRED_CONTRACT_FILES:
        path = session_dir / rel
        if not path.exists():
            missing.append(rel)
            continue
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            missing.append(rel)
    return missing


def run_capture(
    *,
    job_id: str,
    api_url: str,
    note: str = "",
    sessions_root: str | Path = "",
    api_key: str = "",
    transcript_path: str = "",
    out_dir: str = "",
    snapshot_profile: str = "full",
    compatibility_mode: bool = False,
    enforce_hard_fail: bool = False,
) -> CaptureResult:
    del transcript_path  # retained for CLI/backward compatibility

    repo_root = Path(__file__).resolve().parents[2]
    sessions_root_path = (
        Path(sessions_root)
        if sessions_root
        else (repo_root / "sessions")
    )
    sessions_root_path.mkdir(parents=True, exist_ok=True)

    effective_key = api_key or os.getenv("MCP_FACTORY_API_KEY", "")
    commit_hash = _git_short_hash(repo_root)
    commit_msg = _git_commit_msg(repo_root)
    date_part = datetime.now().strftime("%Y-%m-%d")

    profile = str(snapshot_profile or "full").strip().lower()
    if profile not in {"full", "compact"}:
        profile = "full"

    contract_retry_limit = max(
        0,
        int(os.getenv("HARNESS_CAPTURE_CONTRACT_RETRIES", "3")),
    )
    retry_delay_sec = max(
        0.0,
        float(os.getenv("HARNESS_CAPTURE_CONTRACT_RETRY_DELAY_SEC", "2")),
    )

    temp_dir: Path | None = sessions_root_path / f"_tmp-{job_id}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    headers = {"X-Pipeline-Key": effective_key} if effective_key else {}
    snapshot_error = ""
    snapshot_mode = "api_snapshot"
    manifest_entries: dict[str, dict[str, Any]] = {}
    if _should_skip_snapshot(api_url):
        snapshot_mode = "blob_only"
        missing_contract, manifest_entries = _materialize_snapshot_from_blobs(
            temp_dir=temp_dir,
            job_id=job_id,
            profile=profile,
        )
    else:
        try:
            initial_snapshot = _download_snapshot(
                api_url=api_url,
                job_id=job_id,
                profile=profile,
                headers=headers,
            )
            _extract_snapshot_zip(initial_snapshot, temp_dir)
            missing_contract = _missing_contract_files(temp_dir)
            if missing_contract:
                fallback_profile = "full" if profile == "compact" else profile
                for attempt in range(1, contract_retry_limit + 1):
                    if retry_delay_sec > 0:
                        time.sleep(retry_delay_sec)
                    try:
                        refreshed_snapshot = _download_snapshot(
                            api_url=api_url,
                            job_id=job_id,
                            profile=fallback_profile,
                            headers=headers,
                        )
                        _extract_snapshot_zip(refreshed_snapshot, temp_dir)
                    except Exception:
                        pass
                    missing_contract = _missing_contract_files(temp_dir)
                    if not missing_contract:
                        break
            if missing_contract:
                missing_contract, manifest_entries = _materialize_snapshot_from_blobs(
                    temp_dir=temp_dir,
                    job_id=job_id,
                    profile=profile,
                )
        except Exception as exc:
            snapshot_error = str(exc)
            missing_contract, manifest_entries = _materialize_snapshot_from_blobs(
                temp_dir=temp_dir,
                job_id=job_id,
                profile=profile,
            )

    component = _load_component(temp_dir)
    effective_note = note or _default_note(job_id, component, sessions_root_path)

    if out_dir:
        session_dir = Path(out_dir)
        folder_name = session_dir.name
        _copy_tree(temp_dir, session_dir)
    else:
        folder_name = f"{date_part}-{commit_hash}-{_slug(effective_note, 'run')}"
        session_dir = sessions_root_path / folder_name
        suffix = 2
        while session_dir.exists():
            session_dir = sessions_root_path / f"{folder_name}-{suffix}"
            suffix += 1
        shutil.move(str(temp_dir), str(session_dir))
        folder_name = session_dir.name
        temp_dir = None

    (session_dir / "human").mkdir(parents=True, exist_ok=True)
    _write_snapshot_profile(session_dir, profile)
    _write_session_manifests(
        session_dir,
        snapshot_profile=profile,
        snapshot_mode=snapshot_mode,
        manifest_entries=manifest_entries,
    )

    saved_at = datetime.now().astimezone().isoformat()
    collect_exit = collector.collect_session(
        session_dir=session_dir,
        mode="compatibility" if compatibility_mode else "strict",
        enforce_hard_fail=enforce_hard_fail,
        job_id=job_id,
        folder=folder_name,
        component=component,
        commit=commit_hash,
        commit_msg=commit_msg,
        note=effective_note,
        date=date_part,
        saved_at=saved_at,
        snapshot_profile=profile,
    )
    collect_path = session_dir / "human" / "collect-session-result.json"
    if not collect_path.exists():
        raise RuntimeError("collect_session did not emit human/collect-session-result.json")
    summary = json.loads(collect_path.read_text(encoding="utf-8-sig"))
    summary["capture_snapshot_mode"] = snapshot_mode
    if missing_contract:
        summary["capture_missing_contract_after_retry"] = list(missing_contract)
    if snapshot_error:
        summary["capture_snapshot_error"] = snapshot_error
    if missing_contract or snapshot_error:
        collect_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if temp_dir is not None and temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)

    return CaptureResult(
        session_dir=session_dir,
        folder=folder_name,
        collect_exit=collect_exit,
        summary=summary,
    )
