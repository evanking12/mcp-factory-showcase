from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from harness_lib import collector
from api.pipeline.core.handoff_contract import AUDITOR_VERSION, CONTRACT_VERSION, STAGE_CONTRACTS


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_strict_epoch_fixture_collects_and_emits_versions(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "strict_epoch_1_minimal"
    session = tmp_path / "session"
    shutil.copytree(fixture, session)

    rc = collector.collect_session(
        session_dir=session,
        mode="strict",
        enforce_hard_fail=False,
        job_id="fixture-job-001",
        folder="fixture-folder-001",
        component="contoso_cs",
        commit="abc123",
        commit_msg="fixture",
        note="fixture-run",
        date="2026-03-26",
        saved_at="2026-03-26T00:00:00+00:00",
        snapshot_profile="full",
    )
    assert rc == 0

    run_validity = _read_json(session / "run-validity.json")
    kpi_run = _read_json(session / "kpi_run.json")
    stage_audit = _read_json(session / "stage-handoff-audit.json")
    transition_audit = _read_json(session / "transition-contract-audit.json")

    assert run_validity["contract_version"] == CONTRACT_VERSION
    assert run_validity["auditor_version"] == AUDITOR_VERSION
    assert kpi_run["contract_version"] == CONTRACT_VERSION
    assert kpi_run["auditor_version"] == AUDITOR_VERSION
    assert stage_audit["contract_version"] == CONTRACT_VERSION
    assert transition_audit["auditor_version"] == AUDITOR_VERSION
    assert bool((stage_audit.get("summary") or {}).get("valid")) is True
    assert bool((transition_audit.get("summary") or {}).get("valid")) is True


def test_run_ledger_idempotency_and_capture_seq(tmp_path: Path) -> None:
    session = tmp_path / "sessions" / "sample-run"
    session.mkdir(parents=True, exist_ok=True)
    run_validity = {"profile": "strict_dll", "valid": True}
    kpi_run = {
        "totals": {
            "total_functions": 2,
            "verified_success": 1,
            "functional_precondition_unmet": 1,
            "inferred_success": 0,
            "discovered": 2,
            "failure": 0,
        },
        "rates": {"verified_rate": 0.5, "discovered_rate": 1.0},
    }
    session_meta = {
        "prompt_profile_id": "p0",
        "layer": "l1",
        "package_id": "pkg-1",
        "package_label": "Legacy bundle",
        "lane_id": "lane-1",
        "lane_trust_status": "trusted",
        "selection_reason": "top_candidate",
        "doc_visibility": "unknown",
        "dependency_context": "folder_bundle",
        "blocker_family_primary": "struct/payload shaping",
        "blocker_family_secondary": ["sequencing/state machine"],
        "blocker_confidence": "high",
        "architecture_relevance": "high",
        "runtime_path_trust": "matched",
    }

    r1 = collector._append_run_ledger(  # noqa: SLF001
        session_dir=session,
        job_id="job-1",
        folder="run-1",
        component="contoso_cs",
        commit="abc123",
        saved_at="2026-03-26T00:00:00+00:00",
        snapshot_profile="full",
        session_meta=session_meta,
        run_validity=run_validity,
        kpi_run=kpi_run,
    )
    assert r1["appended"] is True
    ledger_rows = [
        json.loads(line)
        for line in (session.parent / "ledger" / "run_ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert ledger_rows[-1]["metrics"]["discovered"] == 1
    assert ledger_rows[-1]["package_id"] == "pkg-1"
    assert ledger_rows[-1]["lane_trust_status"] == "trusted"
    assert ledger_rows[-1]["blocker_family_primary"] == "struct/payload shaping"

    r2 = collector._append_run_ledger(  # noqa: SLF001
        session_dir=session,
        job_id="job-1",
        folder="run-1",
        component="contoso_cs",
        commit="abc123",
        saved_at="2026-03-26T00:00:00+00:00",
        snapshot_profile="full",
        session_meta=session_meta,
        run_validity=run_validity,
        kpi_run=kpi_run,
    )
    assert r2["appended"] is False
    assert r2["reason"] == "duplicate_content_hash_noop"

    r3 = collector._append_run_ledger(  # noqa: SLF001
        session_dir=session,
        job_id="job-1",
        folder="run-1",
        component="contoso_cs",
        commit="def456",
        saved_at="2026-03-26T00:01:00+00:00",
        snapshot_profile="full",
        session_meta=session_meta,
        run_validity=run_validity,
        kpi_run=kpi_run,
    )
    assert r3["appended"] is True
    assert int(r3["capture_seq"]) == 1


def test_floor_gated_skipped_stages_stay_valid_in_strict_collection(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "strict_epoch_1_minimal"
    session = tmp_path / "session"
    shutil.copytree(fixture, session)

    skipped_ids = {"S-04", "S-05", "S-06", "S-04R"}
    for stage in STAGE_CONTRACTS:
        if stage.id not in skipped_ids:
            continue
        for req in (*stage.required_outputs, *stage.required_reasoning, *stage.required_context):
            for rel in (req.canonical_path, *req.blob_candidates):
                path = session / rel
                if path.is_file():
                    path.unlink()

    stage_index = _read_json(session / "stage-index.json")
    for row in stage_index["stages"]:
        if row["id"] in skipped_ids:
            row["status"] = "skipped"
            row["skip_reason"] = "floor_broadening_blocked"
            row["skip_detail"] = "prerequisite_state_groups_untrusted"
            row["errors"] = []
    (session / "stage-index.json").write_text(json.dumps(stage_index, indent=2), encoding="utf-8")

    rc = collector.collect_session(
        session_dir=session,
        mode="strict",
        enforce_hard_fail=False,
        job_id="fixture-job-floor-001",
        folder="fixture-folder-floor-001",
        component="contoso_cs",
        commit="abc123",
        commit_msg="fixture-floor",
        note="fixture-floor-run",
        date="2026-04-07",
        saved_at="2026-04-07T00:00:00+00:00",
        snapshot_profile="full",
    )

    assert rc == 0
    run_validity = _read_json(session / "run-validity.json")
    stage_audit = _read_json(session / "stage-handoff-audit.json")
    assert bool(run_validity["valid"]) is True
    assert bool((stage_audit.get("summary") or {}).get("valid")) is True
    skipped = {
        row["stage_id"]: row
        for row in stage_audit.get("stages") or []
        if row.get("status") == "skipped"
    }
    assert "S-04" in skipped
    assert "S-05" in skipped
    assert "S-06" in skipped


def test_compute_status_counts_excludes_entry_points() -> None:
    counts = collector._compute_status_counts([  # noqa: SLF001
        {"function": "CS_GetVersion", "status_canonical": "verified_success"},
        {"function": "entry", "status_canonical": "failure"},
        {"function": "DllMain", "status_canonical": "failure"},
    ])

    assert counts["total"] == 1
    assert counts["verified"] == 1
    assert counts["counts"]["failure"] == 0
    assert counts["function_statuses"] == {"CS_GetVersion": "verified_success"}

