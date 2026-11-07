"""Local artifact storage, status, and dispatch helpers."""

from __future__ import annotations

import copy
import json
import logging
import os
import re as _re
import threading
import time
from pathlib import Path
from typing import Any

from api.infra.config import (
    ARTIFACT_CONTAINER,
    ANALYSIS_QUEUE,
    LOCAL_DATA_ROOT,
    STORAGE_BACKEND,
    UPLOAD_CONTAINER,
)
from api.pipeline.core.finding_status import (
    is_functional_precondition_text,
    normalize_status,
)
from api.pipeline.core.reusable_truth import assess_reusable_truth

logger = logging.getLogger("mcp_factory.api")

# â”€â”€ Per-job invocable registries â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Backed by both in-memory cache and Blob Storage so state survives container
# recycles (scale-to-zero, deployments, crashes).  P7.
# Structure: {job_id: {tool_name: invocable_dict}}
_JOB_INVOCABLE_MAPS: dict[str, dict[str, Any]] = {}
_JOB_MAP_LOCK = threading.Lock()
_APPEND_JSON_LIST_LOCK = threading.Lock()

# â”€â”€ Async job status store (P3) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# status schema: {status, progress, message, result, error, created_at, updated_at}
_JOB_STATUS: dict[str, dict[str, Any]] = {}
_JOB_STATUS_LOCK = threading.Lock()
_JOB_STATUS_WRITE_LOCKS: dict[str, threading.Lock] = {}
_JOB_STATUS_SEQUENCE: dict[str, int] = {}
_JOB_STATUS_WRITE_STATE_LOCK = threading.Lock()
_DEFAULT_SYNC_STATUS_WRITE_LOCK_TIMEOUT_SEC = 30.0

_FINAL_EXPLORE_PHASES = frozenset(
    {
        "done",
        "awaiting_clarification",
        "error",
        "canceled",
        "cancelled",
        "cancel_requested",
    }
)

# -- Campaign status store (multi-DLL support) ----------------------------
_CAMPAIGN_STATUS: dict[str, dict[str, Any]] = {}
_CAMPAIGN_STATUS_LOCK = threading.Lock()


def _sync_status_write_lock_timeout_sec() -> float:
    raw = os.getenv(
        "MCP_STATUS_SYNC_WRITE_LOCK_TIMEOUT_SEC",
        str(_DEFAULT_SYNC_STATUS_WRITE_LOCK_TIMEOUT_SEC),
    )
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_SYNC_STATUS_WRITE_LOCK_TIMEOUT_SEC
    return max(0.0, value)


def _use_local_storage() -> bool:
    return True


def _local_container_root(container: str) -> Path:
    root = LOCAL_DATA_ROOT / container
    root.mkdir(parents=True, exist_ok=True)
    return root


def _local_blob_path(container: str, blob_name: str) -> Path:
    safe_rel = Path(*[part for part in Path(str(blob_name)).parts if part not in ("", ".", "..")])
    return _local_container_root(container) / safe_rel


def _upload_to_blob(container: str, blob_name: str, data: bytes) -> str:
    path = _local_blob_path(container, blob_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp_path.write_bytes(data)
    last_exc: Exception | None = None
    for attempt in range(10):
        try:
            os.replace(tmp_path, path)
            last_exc = None
            break
        except OSError as exc:
            last_exc = exc
            if attempt == 9:
                break
            time.sleep(0.05 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    logger.info("Wrote local artifact %s/%s", container, blob_name)
    return blob_name


def _download_blob(container: str, blob_name: str) -> bytes:
    path = _local_blob_path(container, blob_name)
    return path.read_bytes()


def _recover_local_status_tmp_blob(container: str, blob_name: str) -> bytes | None:
    """Return a newer valid orphan temp status when atomic replace was interrupted."""
    if Path(str(blob_name)).name != "status.json":
        return None
    path = _local_blob_path(container, blob_name)
    status_mtime = path.stat().st_mtime if path.exists() else -1.0
    newest: tuple[float, bytes] | None = None
    for tmp_path in path.parent.glob(f".{path.name}.*.tmp"):
        if not tmp_path.is_file():
            continue
        try:
            tmp_mtime = tmp_path.stat().st_mtime
            if tmp_mtime <= status_mtime:
                continue
            data = tmp_path.read_bytes()
            json.loads(data)
        except Exception:
            continue
        if newest is None or tmp_mtime > newest[0]:
            newest = (tmp_mtime, data)
    if newest is None:
        return None
    logger.warning(
        "Recovered newer valid local status temp for %s/%s after interrupted atomic replace",
        container,
        blob_name,
    )
    return newest[1]


def _list_blob_names(container: str, prefix: str) -> list[str]:
    root = _local_container_root(container)
    prefix_norm = str(prefix).replace("\\", "/").strip("/")
    results: list[str] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(root).as_posix()
        if not prefix_norm or rel.startswith(prefix_norm):
            results.append(rel)
    return sorted(results)


def _append_json_list(job_id: str, blob_name: str, entries: list) -> None:
    """Generic read-modify-write helper: append *entries* to a JSON-list blob.

    All four public append functions below delegate here so the read-modify-write
    pattern lives in exactly one place.  Non-fatal on any storage error.
    """
    if not entries:
        return
    try:
        with _APPEND_JSON_LIST_LOCK:
            full_blob = f"{job_id}/{blob_name}"
            try:
                existing = json.loads(
                    _download_blob(ARTIFACT_CONTAINER, full_blob).decode("utf-8", errors="replace")
                )
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
            existing.extend(entries)
            _upload_to_blob(
                ARTIFACT_CONTAINER, full_blob,
                json.dumps(existing, indent=2, default=str).encode("utf-8"),
            )
    except Exception as exc:
        logger.warning("[%s] _append_json_list(%s) failed: %s", job_id, blob_name, exc)


def _append_transcript(job_id: str, user_text: str, assistant_text: str,
                       tool_log: list | None = None,
                       transcript_blob: str = "chat_transcript.txt") -> None:
    """Append a user/assistant exchange to {job_id}/{transcript_blob} in blob.

    transcript_blob defaults to 'chat_transcript.txt' for normal chat sessions.
    Pass 'mini_session_transcript.txt' for autonomous pipeline mini-sessions so
    they don't clutter the user-facing chat transcript.

    If tool_log is provided (list of {"call", "args", "result"} dicts) it is
    formatted between the user turn and the assistant turn so the full agentic
    trace is captured.

    Read-modify-write: safe for single-threaded chat sessions (one active
    stream_chat per job_id at a time).  Non-fatal on any error.
    """
    try:
        blob_name = f"{job_id}/{transcript_blob}"
        if tool_log:
            lines = []
            for entry in tool_log:
                if entry.get("reasoning"):
                    lines.append(f"[REASONING]\n{entry['reasoning']}\n")
                args_str = json.dumps(entry.get("args") or {}, separators=(",", ":"))
                result = entry.get("result") or ""
                lines.append(f"🔧 {entry['call']}({args_str})\n   ↳ {result}")
            tool_section = "[TOOL CALLS]\n" + "\n".join(lines) + "\n\n---\n\n"
        else:
            tool_section = ""
        text_entry = (
            f"[USER]\n{user_text}\n\n---\n\n"
            f"{tool_section}"
            f"[ASSISTANT]\n{assistant_text}\n\n---\n\n"
        )
        try:
            existing = _download_blob(ARTIFACT_CONTAINER, blob_name).decode("utf-8", errors="replace")
        except Exception:
            existing = ""
        _upload_to_blob(ARTIFACT_CONTAINER, blob_name, (existing + text_entry).encode("utf-8"))
    except Exception as exc:
        logger.warning("[%s] _append_transcript failed: %s", job_id, exc)


def _append_diagnosis_raw(job_id: str, record: dict) -> None:
    """Append one diagnosis record to {job_id}/diagnosis_raw.json in blob."""
    _append_json_list(job_id, "diagnosis_raw.json", [record])


def _append_executor_trace(job_id: str, entries: list) -> None:
    """Append tool-call trace entries to {job_id}/executor_trace.json in blob."""
    _append_json_list(job_id, "executor_trace.json", entries)


def _append_explore_probe_log(job_id: str, entries: list) -> None:
    """Append explore-phase probe entries to {job_id}/explore_probe_log.json.

    Each entry records one tool call made by the autonomous discovery loop:
    phase, function being explored, round number, tool called, args, result
    excerpt, reasoning text, and the low-level executor trace.  This is the
    diagnostic record for 'what did the explore loop actually probe?'
    """
    _append_json_list(job_id, "explore_probe_log.json", entries)


def _append_job_debug_event(job_id: str, artifact_name: str, entry: dict[str, Any]) -> None:
    """Append one structured debug event to a per-job JSON list artifact."""
    payload = dict(entry or {})
    payload.setdefault("job_id", job_id)
    payload.setdefault("recorded_at", time.time())
    _append_json_list(job_id, artifact_name, [payload])


def _persist_job_status(job_id: str, payload: dict, *, sync: bool = False) -> bool:
    """Write job status to in-memory cache and persist to Blob.

    - Always updates in-memory immediately.
    - If sync=True: blocking, retrying Blob write (for worker threads).
    - If sync=False: run the retrying write in a daemon thread so async
      request handlers never block the event loop.
    """
    with _JOB_STATUS_LOCK:
        current = _JOB_STATUS.get(job_id) or {}
        current_status = str(current.get("status") or "")
        next_status = str(payload.get("status") or "")
        current_explore_phase = str(current.get("explore_phase") or "").strip().lower()
        current_is_final_explore_terminal = (
            current_status in {"done", "error"}
            and current_explore_phase in _FINAL_EXPLORE_PHASES
        )
        if current_is_final_explore_terminal and next_status not in {"done", "error"}:
            logger.debug("[%s] skipped stale nonterminal status after terminal close", job_id)
            return True
        _JOB_STATUS[job_id] = payload

    with _JOB_STATUS_WRITE_STATE_LOCK:
        sequence = _JOB_STATUS_SEQUENCE.get(job_id, 0) + 1
        _JOB_STATUS_SEQUENCE[job_id] = sequence
        write_lock = _JOB_STATUS_WRITE_LOCKS.setdefault(job_id, threading.Lock())

    def _upload_with_retry() -> bool:
        # Use more retries and a longer delay for blocking (sync) callers such
        # as the final "done" persist in the worker, where durability matters most.
        _MAX_RETRIES = 5 if sync else 3
        _RETRY_DELAY = 3 if sync else 2
        acquired = False
        try:
            if sync:
                timeout_sec = _sync_status_write_lock_timeout_sec()
                acquired = write_lock.acquire(timeout=timeout_sec)
                if not acquired:
                    logger.error(
                        "[%s] Timed out after %.3fs waiting for status persist lock; status sequence %s remains in memory only.",
                        job_id,
                        timeout_sec,
                        sequence,
                    )
                    return False
            else:
                write_lock.acquire()
                acquired = True
            data = json.dumps(payload).encode()
            for attempt in range(_MAX_RETRIES):
                with _JOB_STATUS_WRITE_STATE_LOCK:
                    latest_sequence = _JOB_STATUS_SEQUENCE.get(job_id, 0)
                if sequence < latest_sequence:
                    logger.debug(
                        "[%s] skipped stale status persist sequence %s < %s",
                        job_id,
                        sequence,
                        latest_sequence,
                    )
                    return True
                try:
                    _upload_to_blob(ARTIFACT_CONTAINER, f"{job_id}/status.json", data)
                    return True
                except Exception as exc:
                    if attempt < _MAX_RETRIES - 1:
                        logger.warning(
                            "[%s] Failed to persist status to Blob (attempt %d/%d): %s — retrying in %ds",
                            job_id, attempt + 1, _MAX_RETRIES, exc, _RETRY_DELAY,
                        )
                        time.sleep(_RETRY_DELAY)
                    else:
                        logger.error(
                            "[%s] Failed to persist status to Blob after %d attempts: %s — job visible only on this pod until Blob storage is restored.",
                            job_id, _MAX_RETRIES, exc,
                        )
        finally:
            if acquired:
                write_lock.release()
        return False

    if sync:
        return _upload_with_retry()

    threading.Thread(
        target=_upload_with_retry,
        daemon=True,
        name=f"persist-{job_id}",
    ).start()
    return True


def _get_job_status(job_id: str) -> dict | None:
    """Return job status; always reads from Blob for non-terminal states.

    Non-terminal states (anything other than 'done'/'error') are never cached
    in memory across pods — otherwise a pod that saw 'running' will serve that
    stale value forever even after the worker pod writes 'done' to Blob.
    """
    with _JOB_STATUS_LOCK:
        result = _JOB_STATUS.get(job_id)
    # Only trust the in-memory entry when it is a terminal state; for running/
    # pending states always go to Blob so cross-pod reads see the latest write.
    if result is not None and result.get("status") in ("done", "error"):
        return result
    try:
        blob_name = f"{job_id}/status.json"
        raw = _recover_local_status_tmp_blob(ARTIFACT_CONTAINER, blob_name)
        if raw is None:
            raw = _download_blob(ARTIFACT_CONTAINER, blob_name)
        data = json.loads(raw)
        with _JOB_STATUS_LOCK:
            _JOB_STATUS[job_id] = data
        return data
    except Exception as exc:
        # Blob miss is normal during the first seconds before the first persist;
        # return the in-memory value (which may be 'running') as a fallback.
        if result is not None:
            return result
        logger.warning("[%s] get_job_status blob miss: %s", job_id, exc)
        return None


# -- Campaign persistence helpers ------------------------------------------

def _persist_campaign_status(campaign_id: str, payload: dict, *, sync: bool = False) -> bool:
    """Write campaign status to in-memory cache and persist to Blob.

    Campaign status is control-plane state shared across create/attach/finalize/
    explore requests. Persist it synchronously so later requests never observe
    an older campaign view from Blob, even if they hit another worker.
    """
    payload = copy.deepcopy(payload)
    payload.setdefault("schema_version", "1.0.0")
    with _CAMPAIGN_STATUS_LOCK:
        _CAMPAIGN_STATUS[campaign_id] = payload

    def _upload():
        data = json.dumps(payload).encode()
        for attempt in range(3):
            try:
                _upload_to_blob(
                    ARTIFACT_CONTAINER,
                    f"campaigns/{campaign_id}/campaign.json",
                    data,
                )
                return True
            except Exception as exc:
                logger.warning(
                    "[campaign:%s] persist attempt %d failed: %s",
                    campaign_id, attempt + 1, exc,
                )
                time.sleep(2)
        return False

    return _upload()


def _get_campaign_status(campaign_id: str) -> dict | None:
    """Return campaign status from cache or Blob."""
    with _CAMPAIGN_STATUS_LOCK:
        result = _CAMPAIGN_STATUS.get(campaign_id)
    if result is not None:
        return result
    try:
        data = json.loads(
            _download_blob(ARTIFACT_CONTAINER, f"campaigns/{campaign_id}/campaign.json")
        )
        with _CAMPAIGN_STATUS_LOCK:
            _CAMPAIGN_STATUS[campaign_id] = data
        return data
    except Exception:
        return result


def _is_generic_description(desc: Any) -> bool:
    text = str(desc or "").strip().lower()
    if not text:
        return True
    return (
        text.startswith("parameter ")
        or text.startswith("input ")
        or text.startswith("output ")
        or text.startswith("recovered by ghidra")
        or text in {"unknown", "n/a"}
    )


def _prefer_text(existing: Any, incoming: Any) -> Any:
    old = str(existing or "").strip()
    new = str(incoming or "").strip()
    if not new:
        return existing
    if not old:
        return incoming
    if not _is_generic_description(old) and _is_generic_description(new):
        return existing
    if len(new) >= len(old):
        return incoming
    return existing


_GENERIC_PARAM_NAME_RE = _re.compile(r"^param_\d+$")


def _is_generic_param_name(name: Any) -> bool:
    return bool(_GENERIC_PARAM_NAME_RE.match(str(name or "").strip()))


def _normalize_semantic_name_tokens(
    raw_value: str,
    *,
    suffix: str = "",
    preserve_tokens: set[str] | None = None,
) -> str | None:
    text = str(raw_value or "").strip().lower()
    if not text:
        return None
    text = text.replace("-", " ").replace("/", " ")
    text = _re.sub(r"[^a-z0-9_ ]+", " ", text)
    tokens = [tok for tok in text.split() if tok]
    if not tokens:
        return None

    generic_only = {
        "a", "an", "the", "for", "of", "to", "by", "from", "with", "and",
        "or", "expected", "be", "string", "integer", "number", "value",
        "parameter", "input", "output", "argument", "field", "data",
        "buffer", "result",
        "representing", "indicating", "identifier",
    }
    preserve = {str(tok).strip().lower() for tok in (preserve_tokens or set()) if str(tok).strip()}
    semantic_tokens = [tok for tok in tokens if tok not in generic_only or tok in preserve]
    if not semantic_tokens:
        return None
    if (
        len(semantic_tokens) == 1
        and semantic_tokens[0] in {"id", "session", "buffer", "length", "size"}
        and semantic_tokens[0] not in preserve
    ):
        return None

    collapsed = "_".join(semantic_tokens)
    collapsed = _re.sub(r"_+", "_", collapsed).strip("_")
    if not collapsed:
        return None
    if suffix:
        suffix_norm = suffix.strip("_")
        if suffix_norm and not collapsed.endswith(f"_{suffix_norm}") and collapsed != suffix_norm:
            collapsed = f"{collapsed}_{suffix_norm}"
    return collapsed


def _derive_semantic_param_name(description: Any) -> str | None:
    desc = str(description or "").strip()
    if not desc or _is_generic_description(desc):
        return None
    desc_lower = desc.lower()

    patterns: list[tuple[str, str | None]] = [
        (r"\brepresenting\s+the\s+([a-z][a-z0-9 _-]*?session id)\b", None),
        (r"\brepresenting\s+the\s+([a-z][a-z0-9 _-]*? id)\b", None),
        (r"\b(length|size)\s+of\s+(?:the\s+)?([a-z][a-z0-9 _-]*?identifier)\b", "len_identifier"),
        (r"\b(length|size)\s+of\s+(?:the\s+)?([a-z][a-z0-9 _-]*?buffer)\b", "len"),
        (r"\b([a-z][a-z0-9 _-]*?)\s+identifier\b", "id_phrase"),
        (r"\b([a-z][a-z0-9 _-]*?)\s+token\s+for\s+(?:the\s+)?([a-z][a-z0-9 _-]+?)\s*(?:[.,;:]|\(|$)", "token_for"),
        (r"\b([a-z][a-z0-9 _-]*?)\s+identifier\s+for\s+(?:the\s+)?([a-z][a-z0-9 _-]+?)\b", "composed_id"),
        (r"\bidentifier\s+for\s+(?:the\s+)?([a-z][a-z0-9 _-]+?)\b", "id"),
    ]

    for pattern, mode in patterns:
        match = _re.search(pattern, desc_lower)
        if not match:
            continue
        if mode == "len":
            return _normalize_semantic_name_tokens(
                match.group(2),
                suffix="len",
                preserve_tokens={"buffer"},
            )
        if mode == "len_identifier":
            identifier_name = _re.sub(r"\bidentifier\b", "id", match.group(2))
            return _normalize_semantic_name_tokens(
                identifier_name,
                suffix="len",
                preserve_tokens={"id"},
            )
        if mode == "id_phrase":
            return _normalize_semantic_name_tokens(
                match.group(1),
                suffix="id",
                preserve_tokens={"id"},
            )
        if mode == "token_for":
            token_kind = _normalize_semantic_name_tokens(match.group(1), preserve_tokens={"session"})
            owner = _normalize_semantic_name_tokens(match.group(2))
            if token_kind and owner:
                return _normalize_semantic_name_tokens(f"{owner}_{token_kind}", suffix="token")
            continue
        if mode == "composed_id":
            prefix = _normalize_semantic_name_tokens(match.group(1))
            target = _normalize_semantic_name_tokens(match.group(2))
            if prefix and target:
                return _normalize_semantic_name_tokens(f"{target}_{prefix}", suffix="id")
            continue
        normalized = _normalize_semantic_name_tokens(match.group(1))
        if normalized:
            return normalized

    legacy_match = _re.search(
        r"\b(customer[_ ]?id|order[_ ]?id|account[_ ]?id|"
        r"payment[_ ]?amount|refund[_ ]?amount|amount|balance|"
        r"loyalty[_ ]?points|points|interest[_ ]?rate|rate|"
        r"principal|period|months|buffer[_ ]?size|buf[_ ]?size|"
        r"output[_ ]?buffer|result[_ ]?buffer|unlock[_ ]?code|"
        r"status[_ ]?code|error[_ ]?code|return[_ ]?code|"
        r"diagnostic[_ ]?buffer|diag[_ ]?buffer|"
        r"customer[_ ]?name|order[_ ]?status|"
        r"tier[_ ]?label|email|phone|address)",
        desc_lower,
    )
    if legacy_match:
        return _normalize_semantic_name_tokens(legacy_match.group(0))
    return None


def _ensure_unique_parameter_names(
    parameters: list[Any],
    *,
    fallback_names: list[str] | None = None,
    renames: list[str] | None = None,
) -> list[Any]:
    """Preserve one schema property per recovered parameter.

    Semantic enrichment is allowed to rename generic ``param_N`` values, but it
    must not collapse two low-level parameters into one JSON-schema property.
    When a proposed semantic name collides, prefer the original positional name
    for the later parameter; that keeps the run honest without fabricating
    meaning.
    """
    used: set[str] = set()
    for index, param in enumerate(parameters):
        if not isinstance(param, dict):
            continue
        current = str(param.get("name") or f"arg_{index + 1}").strip()
        if current and current not in used:
            used.add(current)
            continue

        fallback = ""
        if fallback_names and index < len(fallback_names):
            fallback = str(fallback_names[index] or "").strip()
        candidates = [
            fallback,
            f"{current}_{index + 1}" if current else "",
            f"arg_{index + 1}",
        ]
        replacement = ""
        for candidate in candidates:
            if candidate and candidate not in used:
                replacement = candidate
                break
        if not replacement:
            base = current or fallback or "arg"
            suffix = 2
            while f"{base}_{suffix}" in used:
                suffix += 1
            replacement = f"{base}_{suffix}"

        param["name"] = replacement
        used.add(replacement)
        if renames is not None and replacement != current:
            renames.append(f"{current or '<blank>'} -> {replacement} (duplicate avoided)")
    return parameters


def _merge_parameter_lists(existing_params: list[Any], incoming_params: list[Any]) -> list[Any]:
    if not existing_params:
        return [dict(p) if isinstance(p, dict) else p for p in incoming_params]
    if not incoming_params:
        return [dict(p) if isinstance(p, dict) else p for p in existing_params]

    def _is_generic_param(param: dict[str, Any]) -> bool:
        name = str(param.get("name") or "").strip()
        desc = str(param.get("description") or "").strip().lower()
        return _is_generic_param_name(name) and (
            not desc
            or desc.startswith("parameter ")
            or desc.startswith("input ")
            or desc.startswith("output ")
        )

    existing_dicts = [p for p in existing_params if isinstance(p, dict)]
    incoming_dicts = [p for p in incoming_params if isinstance(p, dict)]
    if len(existing_dicts) == len(incoming_dicts) and existing_dicts and incoming_dicts:
        existing_names = [str(p.get("name") or "").strip() for p in existing_dicts]
        incoming_names = [str(p.get("name") or "").strip() for p in incoming_dicts]
        if existing_names != incoming_names:
            existing_generic = sum(1 for p in existing_dicts if _is_generic_param(p))
            incoming_generic = sum(1 for p in incoming_dicts if _is_generic_param(p))
            if existing_generic != incoming_generic:
                positional: list[Any] = []
                prefer_incoming = incoming_generic < existing_generic
                for old, new in zip(existing_dicts, incoming_dicts):
                    if prefer_incoming:
                        row = {**old, **new}
                        row["description"] = _prefer_text(old.get("description"), new.get("description"))
                        if _is_generic_param(old) and not _is_generic_param(new):
                            row["name"] = new.get("name")
                    else:
                        row = {**new, **old}
                        row["description"] = _prefer_text(new.get("description"), old.get("description"))
                        if _is_generic_param(new) and not _is_generic_param(old):
                            row["name"] = old.get("name")
                    positional.append(row)
                return positional

    by_name_existing: dict[str, dict] = {}
    for param in existing_params:
        if not isinstance(param, dict):
            continue
        name = str(param.get("name") or "").strip()
        if name:
            by_name_existing[name] = dict(param)

    merged: list[Any] = []
    seen: set[str] = set()
    for param in incoming_params:
        if not isinstance(param, dict):
            merged.append(param)
            continue
        name = str(param.get("name") or "").strip()
        if not name:
            merged.append(dict(param))
            continue
        old = by_name_existing.get(name)
        if old is None:
            merged.append(dict(param))
            seen.add(name)
            continue
        row = {**old, **param}
        row["description"] = _prefer_text(old.get("description"), param.get("description"))
        merged.append(row)
        seen.add(name)

    for param in existing_params:
        if not isinstance(param, dict):
            continue
        name = str(param.get("name") or "").strip()
        if name and name not in seen:
            merged.append(dict(param))

    return merged


def _merge_invocable_union(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        return dict(incoming)

    out = dict(existing)
    for key, value in incoming.items():
        if key == "parameters":
            continue
        if key == "execution":
            old_exec = out.get("execution")
            if isinstance(old_exec, dict) and isinstance(value, dict):
                merged_exec = dict(old_exec)
                for ek, ev in value.items():
                    if ev in ("", None):
                        continue
                    merged_exec[ek] = ev
                out["execution"] = merged_exec
            elif value not in ("", None):
                out["execution"] = value
            continue

        if key in {"description", "doc"}:
            out[key] = _prefer_text(out.get(key), value)
            continue

        if value not in ("", None):
            out[key] = value
        elif key not in out:
            out[key] = value

    existing_params = out.get("parameters")
    incoming_params = incoming.get("parameters")
    out["parameters"] = _merge_parameter_lists(
        existing_params if isinstance(existing_params, list) else [],
        incoming_params if isinstance(incoming_params, list) else [],
    )
    if not out.get("doc") and out.get("description"):
        out["doc"] = out.get("description")
    if not out.get("description") and out.get("doc"):
        out["description"] = out.get("doc")
    return out


def _register_invocables(job_id: str, invocables: list[dict]) -> None:
    with _JOB_MAP_LOCK:
        existing = dict(_JOB_INVOCABLE_MAPS.get(job_id, {}))
        inv_map: dict[str, dict[str, Any]] = {}
        for inv in invocables:
            if not isinstance(inv, dict):
                continue
            name = str(inv.get("name") or "").strip()
            if not name:
                continue
            prior = existing.get(name)
            inv_map[name] = _merge_invocable_union(prior, inv) if prior else dict(inv)
        _JOB_INVOCABLE_MAPS[job_id] = inv_map
    with _JOB_MAP_LOCK:
        persisted = dict(_JOB_INVOCABLE_MAPS.get(job_id, {}))
    # Persist to Blob so state survives container recycles (P7)
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/invocables_map.json",
            json.dumps(persisted).encode(),
        )
    except Exception as exc:
        logger.warning("[%s] Failed to persist invocables to Blob: %s", job_id, exc)


def _prime_invocables_cache(job_id: str, invocables_map: dict[str, dict[str, Any]]) -> None:
    """Populate the in-memory invocable cache without persisting.

    This keeps blob-backed read paths from turning into write paths while still
    making later in-process reads observe the recovered invocables.
    """
    normalized: dict[str, dict[str, Any]] = {}
    for name, inv in invocables_map.items():
        if not isinstance(inv, dict):
            continue
        inv_name = str(inv.get("name") or name).strip()
        if not inv_name:
            continue
        normalized[inv_name] = dict(inv)
    if not normalized:
        return
    with _JOB_MAP_LOCK:
        current = _JOB_INVOCABLE_MAPS.setdefault(job_id, {})
        for name, inv in normalized.items():
            current[name] = _merge_invocable_union(current.get(name), inv)


def _merge_invocables(job_id: str, invocables: list[dict]) -> None:
    """Merge (update) invocables into the registry without removing existing entries.

    Unlike _register_invocables (which replaces the entire map), this function
    only adds or updates the provided entries.  Use this whenever you have a
    SUBSET of functions to refresh — e.g. during backfill or gap mini-sessions —
    so that functions not covered by the current batch are preserved.
    """
    with _JOB_MAP_LOCK:
        current = _JOB_INVOCABLE_MAPS.setdefault(job_id, {})
        for inv in invocables:
            if not isinstance(inv, dict):
                continue
            name = str(inv.get("name") or "").strip()
            if not name:
                continue
            current[name] = _merge_invocable_union(current.get(name), inv)
        merged = dict(current)
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/invocables_map.json",
            json.dumps(merged).encode(),
        )
    except Exception as exc:
        logger.warning("[%s] _merge_invocables: failed to persist to Blob: %s", job_id, exc)


# ── Per-job LLM findings (probe-and-learn memory) ─────────────────────────
# The LLM writes entries here via the record_finding synthetic tool.
# Entries survive session end and are injected into the system prompt on the
# next session so the model starts informed instead of probing from scratch.
_JOB_FINDINGS: dict[str, list] = {}
_JOB_FINDINGS_LOCK = threading.Lock()

def _normalize_finding_status(
    entry: dict,
    *,
    job_id: str = "",
    invocable: dict[str, Any] | None = None,
) -> dict:
    """Normalize finding statuses while keeping legacy compatibility fields."""
    raw_status = str(entry.get("status") or "").strip().lower()
    finding_text = str(entry.get("finding") or "")
    notes_text = str(entry.get("notes") or "")
    combined = f"{finding_text} {notes_text}"

    canonical = normalize_status(raw_status)
    if canonical == "failure" and raw_status in {"error", "failure"}:
        if is_functional_precondition_text(combined):
            canonical = "functional_precondition_unmet"

    if job_id and invocable is None:
        invocable = _get_invocable(job_id, str(entry.get("function") or "").strip())
    assessment_entry = dict(entry)
    assessment_entry["status_canonical"] = canonical
    truth_assessment = assess_reusable_truth(assessment_entry, invocable=invocable)
    entry["reusable_truth_eligible"] = bool(truth_assessment.get("seed_eligible"))
    entry["reusable_truth_score"] = float(truth_assessment.get("score") or 0.0)
    entry["reusable_truth_reasons"] = list(truth_assessment.get("reasons") or [])
    entry["expected_observed_alignment"] = (
        "aligned" if entry["reusable_truth_eligible"] else "rejected"
    )
    direct_truth = entry.get("direct_target_truth")
    direct_return_value = None
    if isinstance(direct_truth, dict):
        try:
            direct_return_value = int(direct_truth.get("return_value"))
        except (TypeError, ValueError):
            direct_return_value = None
    direct_truth_verified = (
        isinstance(direct_truth, dict)
        and str(direct_truth.get("verification") or "").strip().lower() == "verified"
        and direct_return_value == 0
    )
    if (
        canonical == "verified_success"
        and truth_assessment.get("demote_success")
        and not direct_truth_verified
    ):
        canonical = "inferred_success"

    entry["status_canonical"] = canonical

    # Preserve legacy status values for existing consumers while allowing
    # taxonomy-specific upgrades (functional_precondition_unmet).
    if raw_status in {"success", "error", "partial"}:
        entry["status_legacy"] = raw_status
        if canonical == "verified_success":
            entry["status"] = "success"
        elif canonical == "inferred_success":
            entry["status"] = "partial"
        elif canonical == "failure":
            entry["status"] = "error"
        else:
            entry["status"] = canonical
    else:
        if canonical == "verified_success":
            entry["status"] = "success"
            entry["status_legacy"] = "success"
        elif canonical == "inferred_success":
            entry["status"] = "partial"
            entry["status_legacy"] = "partial"
        elif canonical == "failure":
            entry["status"] = "error"
            entry["status_legacy"] = "error"
        else:
            entry["status"] = canonical

    return entry


def _is_verified_success_status(status: str) -> bool:
    status = str(status or "").strip().lower()
    return status in {"success", "verified_success"}


def _save_finding(job_id: str, entry: dict) -> None:
    """Append a single finding dict to in-memory cache and blob.

    The findings list is **append-only by design** — consumers must
    deduplicate to the latest entry per function (see chat.py COH-3).
    Keeping the full history preserves the confidence back-fill logic
    which derives attempt/success ratios across all past entries.

    Also tracks per-function attempt/success counts and derives a
    confidence label ("high" / "medium" / "low") from the history.
    """
    import datetime
    entry.setdefault("recorded_at", datetime.datetime.utcnow().isoformat() + "Z")
    entry.setdefault("source_dll", "")
    entry.setdefault("source_job", job_id)
    entry.setdefault("campaign_id", "")
    _normalize_finding_status(entry, job_id=job_id)
    with _JOB_FINDINGS_LOCK:
        _JOB_FINDINGS.setdefault(job_id, []).append(entry)
        findings = list(_JOB_FINDINGS[job_id])

    # Compute confidence over all entries for this function
    fn_name = entry.get("function", "")
    fn_entries = [f for f in findings if f.get("function") == fn_name]
    attempts = len(fn_entries)
    successes = sum(
        1 for f in fn_entries
        if _is_verified_success_status(f.get("status")) or _is_verified_success_status(f.get("status_canonical"))
    )
    ratio = successes / attempts if attempts else 0.0
    confidence = "high" if ratio >= 0.75 else ("medium" if ratio >= 0.40 else "low")
    # Back-fill the confidence fields into all entries for this function
    with _JOB_FINDINGS_LOCK:
        all_f = _JOB_FINDINGS.get(job_id, [])
        for f in all_f:
            if f.get("function") == fn_name:
                f["attempts"] = attempts
                f["successes"] = successes
                f["confidence"] = confidence
        findings = list(all_f)

    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/findings.json",
            json.dumps(findings, indent=2).encode(),
        )
    except Exception as exc:
        logger.warning("[%s] Failed to persist finding to Blob: %s", job_id, exc)


def _seed_findings(job_id: str, entries: list[dict]) -> None:
    """Append multiple seed findings atomically and persist one blob write."""
    if not entries:
        return
    import datetime

    normalized: list[dict] = []
    for entry in entries:
        row = dict(entry)
        row.setdefault("recorded_at", datetime.datetime.utcnow().isoformat() + "Z")
        _normalize_finding_status(row, job_id=job_id)
        normalized.append(row)

    with _JOB_FINDINGS_LOCK:
        findings = list(_JOB_FINDINGS.get(job_id, []))
        findings.extend(normalized)
        _JOB_FINDINGS[job_id] = findings

        touched = {str(row.get("function") or "") for row in normalized if row.get("function")}
        for fn_name in touched:
            fn_entries = [f for f in findings if f.get("function") == fn_name]
            attempts = len(fn_entries)
            successes = sum(
                1 for f in fn_entries
                if _is_verified_success_status(f.get("status"))
                or _is_verified_success_status(f.get("status_canonical"))
            )
            ratio = successes / attempts if attempts else 0.0
            confidence = "high" if ratio >= 0.75 else ("medium" if ratio >= 0.40 else "low")
            for f in findings:
                if f.get("function") == fn_name:
                    f["attempts"] = attempts
                    f["successes"] = successes
                    f["confidence"] = confidence

        persisted = list(findings)

    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/findings.json",
            json.dumps(persisted, indent=2).encode(),
        )
    except Exception as exc:
        logger.warning("[%s] Failed to persist seeded findings to Blob: %s", job_id, exc)


def _load_findings(job_id: str) -> list:
    """Return all findings for a job; reads from blob on cache miss."""
    with _JOB_FINDINGS_LOCK:
        cached = _JOB_FINDINGS.get(job_id)
    if cached is not None:
        return cached
    try:
        data = json.loads(_download_blob(ARTIFACT_CONTAINER, f"{job_id}/findings.json"))
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    _normalize_finding_status(row, job_id=job_id)
        with _JOB_FINDINGS_LOCK:
            _JOB_FINDINGS[job_id] = data
        return data
    except Exception:
        return []


def _patch_finding(job_id: str, function_name: str, patch: dict) -> None:
    """Update the most recent finding for function_name in-place.

    Used by the consistency-enforcement step in explore_worker to override
    the LLM's classification with ground-truth observed DLL return values.
    """
    def _normalize_direct_target_truth(truth: Any) -> dict[str, Any] | None:
        if not isinstance(truth, dict):
            return None
        normalized = dict(truth)
        working_call = normalized.get("working_call")
        if isinstance(working_call, dict):
            normalized["working_call"] = dict(working_call)
        else:
            normalized.pop("working_call", None)
        return normalized

    def _direct_target_truth_rank(truth: dict[str, Any] | None) -> tuple[int, int]:
        if not isinstance(truth, dict):
            return (0, 0)
        verification = str(truth.get("verification") or "").strip().lower()
        if verification == "verified":
            return (4, len(dict(truth.get("working_call") or {})))
        if truth.get("rejected_by_verification"):
            return (3, len(dict(truth.get("working_call") or {})))
        if int(truth.get("return_value") or 1) == 0:
            return (2, len(dict(truth.get("working_call") or {})))
        return (1, len(dict(truth.get("working_call") or {})))

    def _merge_direct_target_truth(existing: Any, incoming: Any) -> dict[str, Any] | None:
        existing_truth = _normalize_direct_target_truth(existing)
        incoming_truth = _normalize_direct_target_truth(incoming)
        if existing_truth is None:
            return incoming_truth
        if incoming_truth is None:
            return existing_truth
        preferred = incoming_truth
        fallback = existing_truth
        if _direct_target_truth_rank(existing_truth) > _direct_target_truth_rank(incoming_truth):
            preferred, fallback = existing_truth, incoming_truth
        merged_truth = dict(fallback)
        merged_truth.update(preferred)
        if isinstance(existing_truth.get("working_call"), dict) and not isinstance(merged_truth.get("working_call"), dict):
            merged_truth["working_call"] = dict(existing_truth["working_call"])
        if isinstance(incoming_truth.get("working_call"), dict) and not isinstance(merged_truth.get("working_call"), dict):
            merged_truth["working_call"] = dict(incoming_truth["working_call"])
        return merged_truth

    def _merge_finding_patch(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing)
        merged.update(incoming)
        incoming_status = normalize_status(incoming.get("status"))
        if incoming.get("working_call") is not None and incoming_status in {
            "verified_success",
            "inferred_success",
            "functional_precondition_unmet",
        }:
            for key in (
                "direct_target_tool_calls",
                "no_tool_call_rounds",
                "write_policy_events",
            ):
                if key not in incoming:
                    merged.pop(key, None)
        merged_truth = _merge_direct_target_truth(
            existing.get("direct_target_truth"),
            incoming.get("direct_target_truth"),
        )
        if merged_truth is not None:
            merged["direct_target_truth"] = merged_truth
        return merged

    with _JOB_FINDINGS_LOCK:
        findings = _JOB_FINDINGS.get(job_id, [])
        updated = False
        for i in range(len(findings) - 1, -1, -1):
            if findings[i].get("function") == function_name:
                findings[i] = _merge_finding_patch(findings[i], patch)
                _normalize_finding_status(findings[i], job_id=job_id)
                updated = True
                break
        all_findings = list(findings)
    if not updated:
        return

    # When status is patched, recompute successes/attempts/confidence and
    # back-fill all entries for this function so the counts stay accurate.
    if "status" in patch:
        fn_entries = [f for f in all_findings if f.get("function") == function_name]
        attempts = len(fn_entries)
        successes = sum(
            1 for f in fn_entries
            if _is_verified_success_status(f.get("status")) or _is_verified_success_status(f.get("status_canonical"))
        )
        ratio = successes / attempts if attempts else 0.0
        confidence = "high" if ratio >= 0.75 else ("medium" if ratio >= 0.40 else "low")
        with _JOB_FINDINGS_LOCK:
            all_f = _JOB_FINDINGS.get(job_id, [])
            for f in all_f:
                if f.get("function") == function_name:
                    _normalize_finding_status(f, job_id=job_id)
                    f["attempts"] = attempts
                    f["successes"] = successes
                    f["confidence"] = confidence
            all_findings = list(all_f)

    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/findings.json",
            json.dumps(all_findings, indent=2).encode(),
        )
    except Exception as exc:
        logger.warning("[%s] Failed to persist patched finding to Blob: %s", job_id, exc)


def _patch_invocable(job_id: str, function_name: str, patch: dict) -> str:
    """Apply a patch dict to an invocable and re-upload both blob artifacts.

    patch keys:
      - "function_description": str  → replaces inv["description"]
      - "<param_name>": {"name": str, "description": str}  → renames param + sets desc;
        also infers direction ("in"/"out") from description text
      - "parameters": list  → replaces the full parameters list wholesale (backfill path)
      - "criticality": str  → sets criticality label
      - "depends_on": list  → sets dependency list

    Returns a human-readable confirmation string.
    """
    import re as _re
    with _JOB_MAP_LOCK:
        inv_map = _JOB_INVOCABLE_MAPS.get(job_id, {})
        inv = inv_map.get(function_name)
        if inv is None:
            return f"_patch_invocable: function '{function_name}' not found in job '{job_id}'"
        inv = dict(inv)  # shallow copy to avoid mutating shared reference
        inv["parameters"] = [dict(p) for p in (inv.get("parameters") or [])]

    renames: list[str] = []
    original_param_names = [
        str(param.get("name") or "").strip()
        for param in (inv.get("parameters") or [])
        if isinstance(param, dict)
    ]

    # Apply function description
    if "function_description" in patch:
        inv["description"] = patch["function_description"]
        inv["doc"] = patch["function_description"]

    # Apply parameter renames/descriptions
    for param in inv["parameters"]:
        old_name = param.get("name", "")
        if old_name in patch and isinstance(patch[old_name], dict):
            p_patch = patch[old_name]
            new_name = p_patch.get("name") or p_patch.get("semantic_name")
            # D-5: Auto-derive a semantic name from the description when the
            # LLM provides a description but omits the 'name' key.  Only
            # applies to generic param_N names — never overwrites already-
            # enriched names.
            if (
                not new_name
                and _is_generic_param_name(old_name)
                and "description" in p_patch
            ):
                new_name = _derive_semantic_param_name(p_patch["description"])
            if new_name and new_name != old_name:
                param["name"] = new_name
                renames.append(f"{old_name} → {new_name}")
            if "description" in p_patch:
                desc = p_patch["description"]
                param["description"] = desc
                # Infer direction from the description the LLM wrote, so that
                # generate.py correctly includes/excludes params from `required`.
                # Ghidra marks byte* as "out" by default but const char* inputs
                # are also byte* — the LLM's description is the ground truth.
                desc_lower = desc.lower()
                if _re.search(r"\boutput\b.*\bbuffer\b|\bbuffer\b.*\boutput\b|\bout\b.*\bpointer\b|\bauto.allocated\b", desc_lower):
                    param["direction"] = "out"
                elif _re.search(r"\binput\b|\bprovide[sd]?\b|\bpass\b|\bspecif", desc_lower):
                    param["direction"] = "in"

    # Accept a pre-built parameters list (e.g. from backfill) — replaces the
    # current list wholesale, direction already set by the caller.
    if "parameters" in patch and isinstance(patch["parameters"], list):
        # RC-2: Merge wholesale params with existing, preserving enriched descriptions.
        existing_params = {
            p.get("name", ""): p
            for p in (inv.get("parameters") or [])
            if isinstance(p, dict)
        }
        merged_params = []
        for new_p in patch["parameters"]:
            if not isinstance(new_p, dict):
                merged_params.append(new_p)
                continue
            pname = new_p.get("name", "")
            old_p = existing_params.get(pname)
            if old_p:
                old_desc = (old_p.get("description") or "").strip()
                new_desc = (new_p.get("description") or "").strip()
                _old_rich = (
                    "e.g." in old_desc
                    or "observed" in old_desc.lower()
                    or _re.search(r"'[A-Z]{2,6}-[\w-]+'", old_desc)
                )
                _new_generic = (
                    not new_desc
                    or new_desc.lower().startswith("input ")
                    or new_desc.lower().startswith("output ")
                    or new_desc.lower().startswith("parameter ")
                    or (old_desc and len(new_desc) < len(old_desc) * 0.6)
                )
                if _old_rich and _new_generic:
                    new_p = {**new_p, "description": old_desc}
            merged_params.append(new_p)
        inv["parameters"] = merged_params
        wholesale_original_param_names = [
            str(param.get("name") or "").strip()
            for param in inv["parameters"]
            if isinstance(param, dict)
        ]
        # D-5: apply semantic name derivation to the wholesale replacement too.
        # The backfill path supplies updated descriptions but keeps param_N names.
        for param in inv["parameters"]:
            old_name = param.get("name", "")
            desc = param.get("description", "")
            if desc:
                _desc_lower = desc.lower()
                # D-5: auto-derive semantic name from description
                if _is_generic_param_name(old_name):
                    new_name = _derive_semantic_param_name(desc)
                    if new_name:
                        param["name"] = new_name
                        renames.append(f"{old_name} â†’ {new_name}")
                    _name_m = None if new_name else _re.search(
                        r'\b(customer[_ ]?id|order[_ ]?id|account[_ ]?id|'
                        r'payment[_ ]?amount|refund[_ ]?amount|amount|balance|'
                        r'loyalty[_ ]?points|points|interest[_ ]?rate|rate|'
                        r'principal|period|months|buffer[_ ]?size|buf[_ ]?size|'
                        r'output[_ ]?buffer|result[_ ]?buffer|unlock[_ ]?code|'
                        r'status[_ ]?code|error[_ ]?code|return[_ ]?code|'
                        r'diagnostic[_ ]?buffer|diag[_ ]?buffer|'
                        r'customer[_ ]?name|order[_ ]?status|'
                        r'tier[_ ]?label|email|phone|address)',
                        _desc_lower,
                    )
                    if not new_name and _name_m:
                        new_name = _normalize_semantic_name_tokens(_name_m.group(0))
                        if new_name:
                            param["name"] = new_name
                            renames.append(f"{old_name} → {new_name}")
                # Direction inference: override Ghidra's raw direction
                # (byte * defaults to "out" but most byte * params are
                # input strings like customer IDs).
                if _re.search(r"\boutput\b.*\bbuffer\b|\bbuffer\b.*\boutput\b|\bout\b.*\bpointer\b|\bauto.allocated\b", _desc_lower):
                    param["direction"] = "out"
                elif _re.search(r"\binput\b|\bprovide[sd]?\b|\bpass\b|\bspecif|\bidentif|\b[Ii][Dd]\b", _desc_lower):
                    param["direction"] = "in"
        _ensure_unique_parameter_names(
            inv["parameters"],
            fallback_names=wholesale_original_param_names,
            renames=renames,
        )

    _ensure_unique_parameter_names(
        inv["parameters"],
        fallback_names=original_param_names,
        renames=renames,
    )

    # Scalar fields from backfill/refinement
    if "criticality" in patch:
        inv["criticality"] = patch["criticality"]
    if "depends_on" in patch:
        inv["depends_on"] = patch["depends_on"]
    if "description" in patch:
        new_desc = patch["description"]
        existing_desc = (inv.get("description") or inv.get("doc") or "").strip()
        # Guard: only overwrite if the existing description is blank or is a raw
        # Ghidra type-signature (e.g. "undefined8 CS_Foo(byte * param_1, ...)").
        # or the standard "Recovered by Ghidra static analysis" boilerplate.
        # This prevents backfill from downgrading a human-readable enriched description
        # back to a Ghidra annotation when the synthesis doc has incomplete coverage.
        _is_ghidra_sig = bool(_re.match(
            r"^(undefined\d*|void|int\d*|uint\d*|char|byte|BOOL|HRESULT|HANDLE|DWORD|LONG)\b",
            existing_desc, _re.I,
        ))
        _is_ghidra_boilerplate = existing_desc.lower().startswith("recovered by ghidra")
        if not existing_desc or _is_ghidra_sig or _is_ghidra_boilerplate:
            inv["description"] = new_desc
            inv["doc"] = new_desc

    # Write back to in-memory map
    with _JOB_MAP_LOCK:
        _JOB_INVOCABLE_MAPS.setdefault(job_id, {})[function_name] = inv

    # Re-upload invocables_map.json
    with _JOB_MAP_LOCK:
        full_map = dict(_JOB_INVOCABLE_MAPS.get(job_id, {}))
    try:
        _upload_to_blob(
            ARTIFACT_CONTAINER,
            f"{job_id}/invocables_map.json",
            json.dumps(full_map).encode(),
        )
    except Exception as exc:
        logger.warning("[%s] _patch_invocable: failed to re-upload invocables_map: %s", job_id, exc)

    # Regenerate and re-upload mcp_schema.json
    try:
        from api.services.generate import run_generate  # type: ignore
        invocables_list = list(full_map.values())
        # Derive component name from existing schema blob if possible
        component = "mcp-component"
        try:
            existing = json.loads(_download_blob(ARTIFACT_CONTAINER, f"{job_id}/mcp_schema.json"))
            component = existing.get("component", component)
        except Exception:
            pass
        run_generate({"job_id": job_id, "selected": invocables_list, "component_name": component})
    except Exception as exc:
        logger.warning("[%s] _patch_invocable: failed to regenerate schema: %s", job_id, exc)

    rename_str = (", ".join(renames)) if renames else "no param renames"
    logger.info("[%s] _patch_invocable: patched %s (%s)", job_id, function_name, rename_str)
    return f"Schema updated for {function_name}: {rename_str}."


def _get_current_invocables(job_id: str) -> list[dict]:
    """Return the current invocables list from the in-memory registry.

    Used to refresh stale snapshots before backfill / gap resolution so that
    enrichments applied during discovery are not discarded.
    """
    with _JOB_MAP_LOCK:
        m = _JOB_INVOCABLE_MAPS.get(job_id)
    if m:
        return list(m.values())
    return []


def _get_invocable(job_id: str, name: str) -> dict | None:
    with _JOB_MAP_LOCK:
        result = _JOB_INVOCABLE_MAPS.get(job_id, {}).get(name)
    if result is not None:
        return result
    # Cache miss â€” reload from Blob (handles container restarts, P7)
    try:
        data: dict = json.loads(
            _download_blob(ARTIFACT_CONTAINER, f"{job_id}/invocables_map.json")
        )
        with _JOB_MAP_LOCK:
            _JOB_INVOCABLE_MAPS.setdefault(job_id, {}).update(data)
        return data.get(name)
    except Exception as exc:
        logger.warning("[%s] get_invocable blob miss for '%s': %s", job_id, name, exc)
        return None


def _queue_service_client():
    """The local-first repo does not expose a remote queue service."""
    return None


def _enqueue_analysis(job_id: str, blob_name: str, hints: str, original_name: str,
                      *, skip_cache: bool = False) -> bool:
    """Start one bounded local analysis worker in-process."""
    try:
        from api.infra.worker import _analyze_worker

        content = _download_blob(UPLOAD_CONTAINER, blob_name)
        tmp_dir = Path(os.getenv("TMPDIR") or os.getenv("TEMP") or os.getenv("TMP") or ".").resolve()
        job_tmp_dir = Path(os.path.join(tmp_dir, f"local_queue_{job_id}"))
        job_tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = job_tmp_dir / original_name
        tmp_path.write_bytes(content)

        threading.Thread(
            target=_analyze_worker,
            args=(job_id, tmp_path, hints, original_name, job_tmp_dir, skip_cache),
            daemon=True,
            name=f"local-job-{job_id}",
        ).start()
        logger.info("[%s] Started local analysis worker.", job_id)
        return True
    except Exception as exc:
        logger.warning("[%s] Failed to start local analysis worker: %s", job_id, exc)
        return False

