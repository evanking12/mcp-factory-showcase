from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_span_id() -> str:
    return uuid.uuid4().hex[:16]


def append_trace_event(
    *,
    trace_path: str | Path | None,
    trace_id: str,
    span_name: str,
    event_name: str,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> str:
    resolved_span_id = span_id or new_span_id()
    if not trace_path or not str(trace_id or "").strip():
        return resolved_span_id
    try:
        path = Path(trace_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "diagnostic_jsonl_v1",
            "trace_id": str(trace_id),
            "span_id": resolved_span_id,
            "parent_span_id": str(parent_span_id or ""),
            "span_name": str(span_name),
            "event_name": str(event_name),
            "timestamp_unix_ms": int(time.time() * 1000),
            "attributes": dict(attributes or {}),
            "diagnostic_only": True,
            "proof_authority": "none",
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except Exception:
        return resolved_span_id
    return resolved_span_id


@contextmanager
def trace_span(
    *,
    trace_path: str | Path | None,
    trace_id: str,
    span_name: str,
    parent_span_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Iterator[str]:
    span_id = append_trace_event(
        trace_path=trace_path,
        trace_id=trace_id,
        span_name=span_name,
        event_name="start",
        parent_span_id=parent_span_id,
        attributes=attributes,
    )
    started = time.perf_counter()
    try:
        yield span_id
    finally:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        end_attributes = dict(attributes or {})
        end_attributes["duration_ms"] = elapsed_ms
        append_trace_event(
            trace_path=trace_path,
            trace_id=trace_id,
            span_name=span_name,
            event_name="end",
            span_id=span_id,
            parent_span_id=parent_span_id,
            attributes=end_attributes,
        )
