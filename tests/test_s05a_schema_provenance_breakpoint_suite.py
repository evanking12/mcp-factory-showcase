from __future__ import annotations

import json
from types import SimpleNamespace

from api.pipeline.s05_enrichment import backfill as backfill_mod
from api.pipeline.s05_enrichment import schema_backfill
from api.pipeline.s05_enrichment import status as s05_status


def test_s05a_tier2_records_schema_backfill_provenance_without_proof_laundering(monkeypatch) -> None:
    uploads: dict[str, object] = {}
    persisted: list[dict[str, object]] = []
    snapshots: list[str] = []

    def upload(_container: str, path: str, payload: bytes | str) -> None:
        raw = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
        uploads[path] = json.loads(raw)

    monkeypatch.setattr(
        backfill_mod,
        "_backfill_schema_from_synthesis",
        lambda *_args, **_kwargs: {
            "patches_requested": 3,
            "patches_applied": 2,
            "patched_functions": ["S05A_ReadCustomer", "S05A_WriteCustomer"],
        },
    )
    monkeypatch.setattr(backfill_mod, "_upload_to_blob", upload)
    monkeypatch.setattr(backfill_mod, "_snapshot_schema_stage", lambda _job_id, name: snapshots.append(name))
    monkeypatch.setattr(backfill_mod, "_set_explore_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(s05_status, "_get_job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(s05_status, "_persist_job_status", lambda _job_id, payload: persisted.append(payload))
    monkeypatch.setattr(s05_status, "_set_explore_status", lambda *args, **kwargs: None)

    ctx = SimpleNamespace(
        job_id="job-s05a-provenance",
        total=3,
        client=object(),
        model="unit-model",
        invocables=[
            {"name": "S05A_ReadCustomer", "parameters": []},
            {"name": "S05A_WriteCustomer", "parameters": []},
            {"name": "S05A_UnsupportedUtility", "parameters": []},
        ],
        explored_count=lambda: 3,
    )
    report = (
        "Synthesis: S05A_ReadCustomer has observed read evidence. "
        "S05A_WriteCustomer has weak write prose. Unsupported utility has no proof."
    )

    schema_backfill.run_schema_backfill(ctx, report)

    result = uploads["job-s05a-provenance/backfill_result.json"]
    provenance = result["provenance"]
    assert result["patches_requested"] == 3
    assert result["patches_applied"] == 2
    assert provenance["stage_id"] == "s05_schema_backfill"
    assert provenance["source_stage"] == "s04_synthesis"
    assert provenance["proof_boundary"] == "schema_enrichment_not_verification"
    assert provenance["patched_functions"] == ["S05A_ReadCustomer", "S05A_WriteCustomer"]
    rows = {row["function"]: row for row in provenance["rows"]}
    assert rows["S05A_ReadCustomer"]["patch_applied"] is True
    assert rows["S05A_ReadCustomer"]["source"] == "s04_synthesis_report"
    assert rows["S05A_ReadCustomer"]["verification"] == "not_verified_by_s05a"
    assert rows["S05A_WriteCustomer"]["patch_applied"] is True
    assert rows["S05A_UnsupportedUtility"]["patch_applied"] is False
    assert rows["S05A_UnsupportedUtility"]["proof_boundary"] == "schema_enrichment_not_verification"
    assert set(snapshots) == {"mcp_schema_post_discovery.json", "mcp_schema_pre_gap_resolution.json"}
    states = [
        row.get("s05_stage_status", {}).get("s05_schema_backfill", {}).get("state")
        for row in persisted
    ]
    assert "start" in states
    assert "done" in states
