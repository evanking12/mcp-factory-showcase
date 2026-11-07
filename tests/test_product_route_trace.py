from __future__ import annotations

import json
from pathlib import Path

from scripts.runs.product_route_trace import append_trace_event, new_trace_id, trace_span


def test_product_route_trace_emits_diagnostic_jsonl(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace_id = new_trace_id()

    span_id = append_trace_event(
        trace_path=trace_path,
        trace_id=trace_id,
        span_name="runner",
        event_name="start",
        attributes={"suite": "hard01"},
    )

    payload = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert span_id == payload["span_id"]
    assert payload["trace_id"] == trace_id
    assert payload["span_name"] == "runner"
    assert payload["event_name"] == "start"
    assert payload["diagnostic_only"] is True
    assert payload["proof_authority"] == "none"


def test_product_route_trace_span_records_start_and_end(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace_id = new_trace_id()

    with trace_span(
        trace_path=trace_path,
        trace_id=trace_id,
        span_name="hard01.target",
        attributes={"target": "session_bootstrap"},
    ):
        pass

    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [event["event_name"] for event in events] == ["start", "end"]
    assert events[0]["span_id"] == events[1]["span_id"]
    assert "duration_ms" in events[1]["attributes"]


def test_product_route_trace_fails_open_for_empty_path() -> None:
    span_id = append_trace_event(
        trace_path="",
        trace_id=new_trace_id(),
        span_name="runner",
        event_name="start",
    )
    assert isinstance(span_id, str)
    assert span_id
