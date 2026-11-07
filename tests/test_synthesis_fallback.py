from __future__ import annotations

from types import SimpleNamespace

from api.pipeline.s04_synthesis import synthesize


def test_run_phase_6_synthesize_writes_fallback_api_reference_when_llm_is_empty(monkeypatch) -> None:
    uploaded: dict[str, bytes] = {}

    monkeypatch.setattr(
        synthesize,
        "_load_findings",
        lambda job_id: [
            {
                "function": "CP_Initialize",
                "status": "success",
                "finding": "Returns 0 on success.",
                "working_call": {},
            },
            {
                "function": "CP_CheckStock",
                "status": "success",
                "finding": "Returns 0 when called with SKU.",
                "working_call": {"param_1": "PRO-SVC-ANNUAL"},
            },
        ],
    )
    monkeypatch.setattr(synthesize, "_set_explore_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(synthesize, "_save_stage_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(synthesize, "_snapshot_schema_stage", lambda *args, **kwargs: None)
    monkeypatch.setattr(synthesize, "_get_current_invocables", lambda job_id: [])
    monkeypatch.setattr(synthesize, "_synthesize", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        synthesize,
        "_upload_to_blob",
        lambda container, blob_name, data: uploaded.setdefault(blob_name, data) or blob_name,
    )

    ctx = SimpleNamespace(
        job_id="job-fallback",
        invocables=[
            {"name": "CP_Initialize", "parameters": []},
            {
                "name": "CP_CheckStock",
                "parameters": [{"name": "param_1", "json_type": "string", "description": "SKU input"}],
            },
        ],
        inv_map={},
        vocab={
            "id_formats": ["CUST-001", "PRO-SVC-ANNUAL"],
            "error_codes": {"0xFFFFFFFF": "not found / invalid input"},
            "value_semantics": {"status_values": ["ACTIVE"]},
        },
        sentinels={},
        client=object(),
        model="test-model",
        total=2,
        _state={"explored": 2},
    )

    report = synthesize._run_phase_6_synthesize(ctx)  # noqa: SLF001

    assert report is not None
    assert "## Function Reference" in report
    assert "CP_Initialize" in report
    assert "CP_CheckStock" in report
    assert "job-fallback/api_reference.md" in uploaded
    assert "job-fallback/evidence/stage-04-synthesis/synthesis-fallback.json" in uploaded


def test_run_phase_6_synthesize_supplements_missing_function_coverage(monkeypatch) -> None:
    uploaded: dict[str, bytes] = {}

    monkeypatch.setattr(
        synthesize,
        "_load_findings",
        lambda job_id: [
            {
                "function": "CP_Initialize",
                "status": "success",
                "finding": "Returns 0 on success.",
                "working_call": {},
            },
            {
                "function": "CP_CheckStock",
                "status": "success",
                "finding": "Returns 0 when called with SKU.",
                "working_call": {"sku": "PRO-SVC-ANNUAL"},
            },
        ],
    )
    monkeypatch.setattr(synthesize, "_set_explore_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(synthesize, "_save_stage_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(synthesize, "_snapshot_schema_stage", lambda *args, **kwargs: None)
    monkeypatch.setattr(synthesize, "_get_current_invocables", lambda job_id: [])
    monkeypatch.setattr(
        synthesize,
        "_synthesize",
        lambda *args, **kwargs: "# API Reference\n\n## Function Reference\n\n### CP_Initialize\n- Status: `success`\n",
    )
    monkeypatch.setattr(
        synthesize,
        "_upload_to_blob",
        lambda container, blob_name, data: uploaded.setdefault(blob_name, data) or blob_name,
    )

    ctx = SimpleNamespace(
        job_id="job-partial",
        invocables=[
            {"name": "CP_Initialize", "parameters": []},
            {
                "name": "CP_CheckStock",
                "parameters": [{"name": "sku", "json_type": "string", "description": "SKU input"}],
            },
        ],
        inv_map={},
        vocab={},
        sentinels={},
        client=object(),
        model="test-model",
        total=2,
        _state={"explored": 2},
    )

    report = synthesize._run_phase_6_synthesize(ctx)  # noqa: SLF001

    assert report is not None
    assert "Supplemental Function Coverage" in report
    assert "CP_CheckStock" in report
    assert "job-partial/api_reference.md" in uploaded
