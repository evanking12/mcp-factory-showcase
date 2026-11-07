from __future__ import annotations

import json
from pathlib import Path

import api.services.discovery as discovery
from scripts.regression.replay_hard03_reservation_discovery_live import (
    replay_hard03_reservation_discovery_live,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _source_root(tmp_path: Path, dll_path: Path) -> Path:
    source = tmp_path / "source"
    target = source / "runs" / "02-reservation_stage"
    _write_json(target / "run_result.json", {"target_dll": str(dll_path)})
    return source


def test_missing_reservation_stage_fails_closed(tmp_path: Path) -> None:
    result = replay_hard03_reservation_discovery_live(
        source_proof_root=tmp_path / "source",
        output_root=tmp_path / "out",
    )

    assert result["classification"] == "trusted_predecessor_boundary_unavailable"
    assert result["product_green_claimed"] is False
    assert result["claim_ceiling"] == "target_local_live_discovery_only"


def test_live_discovery_classifies_parent_wait_recovered_without_mutating_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dll_path = tmp_path / "reservation.dll"
    dll_path.write_bytes(b"dll")
    source = _source_root(tmp_path, dll_path)
    statuses: dict[str, dict] = {}
    monkeypatch.setattr(discovery, "_get_job_status", lambda job_id: statuses.get(job_id))

    def fake_run(_dll, job_id, **_kwargs):
        statuses[job_id] = {
            "analyzer_runtime_authority": {
                "phase_history": [
                    {"phase": "discovery_child_wait_start"},
                    {"phase": "discovery_child_wait_returned"},
                    {"phase": "discovery_child_returncode_observed"},
                    {"phase": "discovery_output_scan_started"},
                    {"phase": "discovery_output_scan_completed"},
                ],
                "child_returncode": 0,
                "output_file_count": 1,
            }
        }
        raise RuntimeError("Ghidra-backed discovery required")

    monkeypatch.setattr(discovery, "_run_discovery", fake_run)

    before = sorted(str(path.relative_to(source)) for path in source.rglob("*"))
    result = replay_hard03_reservation_discovery_live(
        source_proof_root=source,
        output_root=tmp_path / "out",
    )
    after = sorted(str(path.relative_to(source)) for path in source.rglob("*"))

    assert after == before
    assert result["classification"] == "parent_wait_authority_recovered_live_downstream_blocked"
    assert result["parent_wait_returned"] is True
    assert result["returncode_observed"] is True
    assert result["output_scan_completed"] is True
    assert result["product_green_claimed"] is False
    assert result["source_root_mutated"] is False


def test_live_discovery_preserves_wait_return_missing_when_parent_never_returns(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dll_path = tmp_path / "reservation.dll"
    dll_path.write_bytes(b"dll")
    source = _source_root(tmp_path, dll_path)
    statuses: dict[str, dict] = {}
    monkeypatch.setattr(discovery, "_get_job_status", lambda job_id: statuses.get(job_id))

    def fake_run(_dll, job_id, **_kwargs):
        statuses[job_id] = {
            "analyzer_runtime_authority": {
                "phase_history": [{"phase": "discovery_child_wait_start"}],
                "child_returncode": None,
            }
        }
        raise TimeoutError("wrapper wait timed out")

    monkeypatch.setattr(discovery, "_run_discovery", fake_run)

    result = replay_hard03_reservation_discovery_live(
        source_proof_root=source,
        output_root=tmp_path / "out",
    )

    assert result["classification"] == "child_wrapper_wait_return_missing"
    assert result["parent_wait_started"] is True
    assert result["parent_wait_returned"] is False
    assert result["product_green_claimed"] is False


def test_call_gui_bridge_returns_empty_pair_when_unconfigured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(discovery, "GUI_BRIDGE_URL", "")
    monkeypatch.setattr(discovery, "GUI_BRIDGE_SECRET", "")
    monkeypatch.setattr(discovery, "_emit_bridge_analyzer_authority", lambda *_args, **_kwargs: None)

    result = discovery._call_gui_bridge(tmp_path / "sample.dll", "job-bridge")

    assert result == ([], "")
