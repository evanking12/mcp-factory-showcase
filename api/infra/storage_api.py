"""Public storage interface.

Prefer importing from this module instead of underscore-prefixed internals in
``api.infra.storage`` from outside the storage package.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from api.infra.config import ARTIFACT_CONTAINER
from api.infra.storage import (
    _append_diagnosis_raw,
    _append_job_debug_event,
    _append_executor_trace,
    _download_blob,
    _enqueue_analysis,
    _get_campaign_status,
    _get_current_invocables,
    _get_invocable,
    _get_job_status,
    _list_blob_names,
    _load_findings,
    _merge_invocables,
    _merge_invocable_union,
    _patch_finding,
    _patch_invocable,
    _persist_campaign_status,
    _persist_job_status,
    _prime_invocables_cache,
    _register_invocables,
    _save_finding,
    _seed_findings,
    _upload_to_blob,
)

logger = logging.getLogger("mcp_factory.api")


def upload_to_blob(container: str, blob_name: str, data: bytes) -> str:
    return _upload_to_blob(container, blob_name, data)


def download_blob(container: str, blob_name: str) -> bytes:
    return _download_blob(container, blob_name)


def list_blob_names(container: str, prefix: str) -> list[str]:
    return _list_blob_names(container, prefix)


def persist_job_status(job_id: str, payload: dict[str, Any], sync: bool = False) -> bool:
    return _persist_job_status(job_id, payload, sync=sync)


def get_job_status(job_id: str) -> dict[str, Any] | None:
    return _get_job_status(job_id)


def register_invocables(job_id: str, invocables: list[dict[str, Any]]) -> None:
    _register_invocables(job_id, invocables)


def get_invocable(job_id: str, fn_name: str) -> dict[str, Any] | None:
    return _get_invocable(job_id, fn_name)


def get_current_invocables(job_id: str) -> list[dict[str, Any]]:
    return _get_current_invocables(job_id)


def prime_invocables_cache(job_id: str, invocables_map: dict[str, dict[str, Any]]) -> None:
    _prime_invocables_cache(job_id, invocables_map)


def get_invocables_map(job_id: str) -> dict[str, dict[str, Any]]:
    invocables = _get_current_invocables(job_id)
    if invocables:
        return {
            str(inv.get("name") or ""): dict(inv)
            for inv in invocables
            if isinstance(inv, dict) and str(inv.get("name") or "").strip()
        }
    blob_name = f"{job_id}/invocables_map.json"
    try:
        raw = _download_blob(ARTIFACT_CONTAINER, blob_name)
        data = json.loads(raw)
    except FileNotFoundError:
        logger.debug("[%s] get_invocables_map: blob not found at %s", job_id, blob_name)
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("[%s] get_invocables_map: invalid JSON in %s: %s", job_id, blob_name, exc)
        return {}
    except Exception as exc:
        logger.warning("[%s] get_invocables_map: blob read failed for %s: %s", job_id, blob_name, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("[%s] get_invocables_map: blob payload in %s was not a dict", job_id, blob_name)
        return {}
    normalized = {
        str(name): dict(inv)
        for name, inv in data.items()
        if isinstance(inv, dict) and str(name).strip()
    }
    return normalized


def merge_invocables(job_id: str, incoming: list[dict[str, Any]]) -> None:
    _merge_invocables(job_id, incoming)


def merge_invocable_union(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _merge_invocable_union(existing, incoming)


def load_findings(job_id: str) -> list[dict[str, Any]]:
    return _load_findings(job_id)


def save_finding(job_id: str, finding: dict[str, Any]) -> None:
    _save_finding(job_id, finding)


def seed_findings(job_id: str, findings: list[dict[str, Any]]) -> None:
    _seed_findings(job_id, findings)


def patch_finding(job_id: str, function_name: str, patch: dict[str, Any]) -> None:
    _patch_finding(job_id, function_name, patch)


def patch_invocable(job_id: str, function_name: str, patch: dict[str, Any]) -> None:
    _patch_invocable(job_id, function_name, patch)


def append_diagnosis_raw(job_id: str, record: dict[str, Any]) -> None:
    _append_diagnosis_raw(job_id, record)


def append_executor_trace(job_id: str, entries: list[dict[str, Any]]) -> None:
    _append_executor_trace(job_id, entries)


def append_job_debug_event(job_id: str, artifact_name: str, entry: dict[str, Any]) -> None:
    _append_job_debug_event(job_id, artifact_name, entry)


def persist_campaign_status(campaign_id: str, payload: dict[str, Any], sync: bool = False) -> bool:
    return _persist_campaign_status(campaign_id, payload, sync=sync)


def get_campaign_status(campaign_id: str) -> dict[str, Any] | None:
    return _get_campaign_status(campaign_id)


def enqueue_analysis(
    job_id: str,
    blob_name: str,
    hints: str,
    original_name: str,
    *,
    skip_cache: bool = False,
) -> bool:
    return _enqueue_analysis(
        job_id,
        blob_name,
        hints,
        original_name,
        skip_cache=skip_cache,
    )
