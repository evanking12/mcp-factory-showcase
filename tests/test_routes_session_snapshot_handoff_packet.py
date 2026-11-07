from __future__ import annotations

import asyncio
import io
import json
import zipfile


def _blob_bytes(obj):
    if isinstance(obj, bytes):
        return obj
    if isinstance(obj, str):
        return obj.encode("utf-8")
    return json.dumps(obj).encode("utf-8")


async def _read_streaming_response(response) -> bytes:
    chunks: list[bytes] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return b"".join(chunks)


def test_session_snapshot_includes_handoff_packet_and_legacy_stage_zero_artifacts(monkeypatch) -> None:
    import api.routes.routes_session as routes_session

    blobs = {
        "job1/s01_handoff_packet.json": _blob_bytes(
            {
                "baseline_truth": {"sentinels": {"0xFFFFFFFB": "write denied"}},
                "surface_inventory": {"dll_strings": {"ids": ["CUST-001"]}},
                "prior_hints": {"id_formats": ["CUST-001"]},
                "s01_targets": {"write_candidates": ["CS_ProcessPayment"]},
                "coordination_decision": {"flow_outcome": "advance"},
            }
        ),
        "job1/vocab.json": _blob_bytes(
            {
                "id_formats": ["CUST-001"],
                "value_semantics": {"amount_cents": "payment amount in cents"},
                "error_codes": {"0xfffffffb": "write denied"},
            }
        ),
        "job1/static_analysis.json": _blob_bytes(
            {
                "static_hints_block_length": 128,
                "binary_strings": {"ids_found": ["CUST-001"]},
            }
        ),
        "job1/static_enrichment.json": _blob_bytes(
            {
                "schema_version": 1,
                "callable_inventory": {"total": 1},
            }
        ),
        "job1/sentinel_calibration.json": _blob_bytes({"0xFFFFFFFB": "write denied"}),
        "job1/explore_config.json": _blob_bytes({"cap_profile": "default"}),
        "job1/mcp_schema_t0.json": _blob_bytes({"version": 1}),
        "job1/invocables_map.json": _blob_bytes({"CS_ProcessPayment": {"name": "CS_ProcessPayment"}}),
        "job1/prerequisite_state_machine.json": _blob_bytes({"layers": [["CS_Init"]]}),
        "job1/explore_probe_log.json": _blob_bytes([{"function": "CS_Init", "result_excerpt": "Returned: 0"}]),
        "job1/findings.json": _blob_bytes([{"function": "CS_Init", "status": "success"}]),
        "job1/model_context_phase_01_probe_loop.txt": _blob_bytes("probe system context"),
        "job1/probe_user_message_sample.txt": _blob_bytes("probe user message"),
        "job1/evidence/stage-02-probe-loop/probe-round-reasoning.json": _blob_bytes([]),
        "job1/evidence/stage-02-probe-loop/probe-stop-reasons.json": _blob_bytes([]),
        "job1/evidence/stage-02-probe-loop/probe-strategy-summary.json": _blob_bytes([]),
        "job1/evidence/stage-02-probe-loop/param-rename-decisions.json": _blob_bytes([]),
    }

    monkeypatch.setattr(
        routes_session,
        "_download_blob",
        lambda _container, blob_name: blobs[blob_name],
    )
    monkeypatch.setattr(routes_session, "_list_blob_names", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(routes_session, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(routes_session, "_load_findings", lambda _job_id: [])
    monkeypatch.setattr(routes_session, "emit_contract_artifacts", lambda _job_id: None)
    monkeypatch.setattr(
        routes_session,
        "_get_job_status",
        lambda _job_id: {
            "explore_phase": "running",
            "status": "running",
            "hints": "Use CUST-001",
            "use_cases": "contoso payments",
        },
    )

    response = asyncio.run(routes_session.session_snapshot("job1"))
    payload = asyncio.run(_read_streaming_response(response))

    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        names = set(archive.namelist())
        assert "stage-00-setup/s01-handoff-packet.json" in names
        assert "evidence/stage-00-setup/s01-handoff-packet.json" in names
        assert "stage-05-finalization/vocab.json" in names
        assert "stage-00-setup/static_analysis.json" in names
        assert "stage-00-setup/sentinel_calibration.json" in names
        assert "evidence/stage-00a-setup-baseline/sentinel-calibration.json" in names
        assert "evidence/stage-00a-setup-baseline/vocab.json" in names
        assert "evidence/stage-00b-static-evidence/static-analysis.json" in names
        assert "evidence/stage-00b-static-evidence/static-enrichment.json" in names
        assert "evidence/stage-00c-admission-handoff/s01-handoff-packet.json" in names
        assert "evidence/stage-02a-probe-ordering/prerequisite-state-machine.json" in names
        assert "evidence/stage-02b-invocation-execution/stage-context.txt" in names
        assert "evidence/stage-02b-invocation-execution/probe-user-message-sample.txt" in names
        assert "evidence/stage-02c-evidence-capture/probe-log.json" in names
        assert "evidence/stage-02c-evidence-capture/findings.json" in names

        assert json.loads(archive.read("stage-00-setup/s01-handoff-packet.json").decode("utf-8")) == json.loads(
            blobs["job1/s01_handoff_packet.json"].decode("utf-8")
        )
        assert json.loads(archive.read("evidence/stage-00-setup/s01-handoff-packet.json").decode("utf-8")) == json.loads(
            blobs["job1/s01_handoff_packet.json"].decode("utf-8")
        )
        assert json.loads(archive.read("stage-05-finalization/vocab.json").decode("utf-8")) == json.loads(
            blobs["job1/vocab.json"].decode("utf-8")
        )
        assert json.loads(archive.read("stage-00-setup/static_analysis.json").decode("utf-8")) == json.loads(
            blobs["job1/static_analysis.json"].decode("utf-8")
        )
        assert json.loads(archive.read("stage-00-setup/sentinel_calibration.json").decode("utf-8")) == json.loads(
            blobs["job1/sentinel_calibration.json"].decode("utf-8")
        )
        assert json.loads(
            archive.read("evidence/stage-00c-admission-handoff/s01-handoff-packet.json").decode("utf-8")
        ) == json.loads(blobs["job1/s01_handoff_packet.json"].decode("utf-8"))
        assert json.loads(
            archive.read("evidence/stage-00b-static-evidence/static-enrichment.json").decode("utf-8")
        ) == json.loads(blobs["job1/static_enrichment.json"].decode("utf-8"))
        assert json.loads(
            archive.read("evidence/stage-02a-probe-ordering/prerequisite-state-machine.json").decode("utf-8")
        ) == json.loads(blobs["job1/prerequisite_state_machine.json"].decode("utf-8"))
        assert json.loads(
            archive.read("evidence/stage-02c-evidence-capture/findings.json").decode("utf-8")
        ) == json.loads(blobs["job1/findings.json"].decode("utf-8"))
