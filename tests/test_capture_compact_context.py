from __future__ import annotations

import json
import sys
from pathlib import Path

from api.analysis import cohesion
from api.infra import storage


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from harness_lib import capture


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_compact_snapshot_materializes_required_context_aliases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    blobs = {
        "session-meta.json": _json_bytes({"job_id": "job-1"}),
        "stage-index.json": _json_bytes({}),
        "transition-index.json": _json_bytes({}),
        "cohesion-report.json": _json_bytes({}),
        "model_context_phase_01_probe_loop.txt": b"probe context",
        "chat_system_context_turn0.txt": b"system context",
        "checkpoints/stage_snapshots/s07_finalize.json": _json_bytes({"status": "done"}),
    }

    monkeypatch.setattr(storage, "_get_job_status", lambda job_id: {"job_id": job_id})
    monkeypatch.setattr(
        storage,
        "_download_blob",
        lambda container, blob_name: blobs.get(blob_name.removeprefix("job-1/")),
    )
    monkeypatch.setattr(cohesion, "emit_contract_artifacts", lambda job_id: None)

    missing_contract, manifest_entries = capture._materialize_snapshot_from_blobs(
        temp_dir=tmp_path / "session",
        job_id="job-1",
        profile="compact",
    )

    assert missing_contract == []
    assert (tmp_path / "session" / "diagnostics" / "chat-model-context.txt").read_text(encoding="utf-8") == "probe context"
    assert (
        tmp_path / "session" / "diagnostics" / "chat-system-context-turn0.txt"
    ).read_text(encoding="utf-8") == "system context"
    assert "diagnostics/chat-model-context.txt" in manifest_entries
    assert "diagnostics/chat-system-context-turn0.txt" in manifest_entries
