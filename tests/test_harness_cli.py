from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


_HARNESS_PATH = Path(__file__).resolve().parent.parent / "scripts" / "harness.py"
_SPEC = importlib.util.spec_from_file_location("harness_test_module", _HARNESS_PATH)
assert _SPEC and _SPEC.loader
harness = importlib.util.module_from_spec(_SPEC)
sys.modules["harness_test_module"] = harness
_SPEC.loader.exec_module(harness)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _minimal_contract(session_dir: Path) -> None:
    _write_json(session_dir / "session-meta.json", {"job_id": "j1", "component": "contoso_cs"})
    _write_json(session_dir / "stage-index.json", {"version": "1.0", "stages": []})
    _write_json(session_dir / "transition-index.json", {"version": "1.0", "transitions": [{"id": "T-01"}]})
    _write_json(session_dir / "cohesion-report.json", {"version": "1.0", "gates": {"hard_fail": False}})


def test_run_dry_run_uses_config_contract(tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "cfg.json"
    _write_json(
        cfg,
        {
            "campaign": {"mode": "nightly", "hours": 1, "max_runs": 1},
            "api": {"url": "http://localhost:8001", "key": ""},
            "bridge": {"url": "http://localhost:8090", "key": ""},
            "targets": {"names": ["contoso_cs"]},
            "explore_defaults": {"analysis_profile": "strict_dll"},
            "execution": {"snapshot_profile": "compact"},
        },
    )
    code = harness.main(["run", "--config", str(cfg), "--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "dry_run_command=" in out
    assert "nightly_groundtruth.py" in out


def test_verify_fails_when_knob_contract_artifact_missing(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    _minimal_contract(session_dir)
    cfg = tmp_path / "cfg.json"
    _write_json(
        cfg,
        {
            "knob_contract": {
                "context_density": {
                    "affects_transitions": ["T-01"],
                    "required_artifacts": ["evidence/stage-02-probe-loop/probe-round-reasoning.json"],
                }
            }
        },
    )
    code = harness.main(["verify", "--session-dir", str(session_dir), "--config", str(cfg)])
    assert code == 1
    report = json.loads((session_dir / "human" / "verify-report.json").read_text(encoding="utf-8"))
    assert report["knob_failures"]
