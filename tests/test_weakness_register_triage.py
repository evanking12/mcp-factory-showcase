from __future__ import annotations

import json
from pathlib import Path

from api.pipeline.core.weakness_register_triage import (
    ARTIFACT_NAME,
    NEXT_PROMPT,
    build_weakness_register_triage,
    parse_weakness_entries,
)
from scripts.runs.run_weakness_register_triage import REPO_ROOT, run_weakness_register_triage


def test_parse_weakness_entries_reads_current_register() -> None:
    register = (REPO_ROOT / ".agents" / "ARCHITECTURAL-WEAKNESSES.md").read_text(encoding="utf-8")
    entries = parse_weakness_entries(register)

    assert len(entries) >= 20
    assert any(entry.title.startswith("24.") for entry in entries)
    assert any(entry.title.startswith("34.") for entry in entries)


def test_build_weakness_register_triage_produces_smaller_active_shortlist() -> None:
    register = (REPO_ROOT / ".agents" / "ARCHITECTURAL-WEAKNESSES.md").read_text(encoding="utf-8")
    payload = build_weakness_register_triage(
        register_text=register,
        worktree_status_lines=[
            " D docs/architecture/README.md",
            "?? docs/architecture/oldstuff/",
            "?? docs/architecture/engineScaling/engineScaling_General/",
        ],
    )

    assert payload["artifact_type"] == ARTIFACT_NAME
    assert payload["entry_counts"]["active"] < payload["entry_counts"]["total"]
    assert len(payload["top_active_shortlist"]) == 5
    assert payload["top_active_shortlist"][0]["id"].startswith("25-")
    assert payload["next_prompt"]["filename"] == NEXT_PROMPT["filename"]
    assert any(
        surface["path"] == "docs/architecture/oldstuff/"
        for surface in payload["deprecated_or_orphaned_surfaces"]
    )


def test_weakness_register_runner_emits_artifact(tmp_path: Path) -> None:
    result = run_weakness_register_triage(output_root=tmp_path)

    artifact_path = Path(result["artifact_path"])
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["artifact_type"] == ARTIFACT_NAME
    assert payload["next_prompt"]["filename"] == NEXT_PROMPT["filename"]
