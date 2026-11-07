from __future__ import annotations

import json
from pathlib import Path

from scripts.regression import replay_s07_contract_artifacts as replay


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_missing_job_artifact_root_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(replay, "LOCAL_ARTIFACTS_ROOT", tmp_path / "artifacts")

    result = replay.replay_s07_contract_artifacts(job_id="missing", output_root=tmp_path / "out")

    assert result["blocking_signal"] == "checkpoint_artifact_root_missing"
    assert result["claim_ceiling"] == "s07_contract_artifact_replay_only"
    assert result["product_green_claimed"] is False
    assert (tmp_path / "out" / "s07-contract-artifact-replay-result.json").exists()


def test_replay_green_when_required_contract_artifacts_exist_after_emit(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "artifacts"
    job_dir = root / "job-1"
    _write_json(job_dir / "status.json", {"status": "done", "explore_phase": "done"})
    _write_json(job_dir / "checkpoints" / "s07_finalize.json", {"completed": True, "phase": "done"})
    monkeypatch.setattr(replay, "LOCAL_ARTIFACTS_ROOT", root)

    def fake_emit(_job_id: str, _timeout_sec: float) -> dict[str, object]:
        for name in replay.REQUIRED_CONTRACT_ARTIFACTS:
            _write_json(job_dir / name, {"name": name})
        return {"status": "ok", "exit_code": 0, "elapsed_sec": 0.01}

    monkeypatch.setattr(replay, "_emit_contract_artifacts_subprocess", fake_emit)

    result = replay.replay_s07_contract_artifacts(job_id="job-1", output_root=tmp_path / "out")

    assert result["blocking_signal"] == "s07_contract_artifact_replay_green"
    assert result["checkpoint_first_result"] == "used"
    assert result["safe_to_compare"] is False
    assert result["product_green_claimed"] is False
    assert result["missing_required_after"] == []


def test_replay_reports_missing_contract_outputs(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "artifacts"
    job_dir = root / "job-1"
    job_dir.mkdir(parents=True)
    monkeypatch.setattr(replay, "LOCAL_ARTIFACTS_ROOT", root)
    monkeypatch.setattr(
        replay,
        "_emit_contract_artifacts_subprocess",
        lambda _job_id, _timeout_sec: {"status": "ok", "exit_code": 0, "elapsed_sec": 0.01},
    )

    result = replay.replay_s07_contract_artifacts(job_id="job-1", output_root=tmp_path / "out")

    assert result["blocking_signal"] == "s07_contract_artifact_missing_outputs"
    assert set(result["missing_required_after"]) == set(replay.REQUIRED_CONTRACT_ARTIFACTS)
    assert result["product_green_claimed"] is False


def test_replay_reports_checkpoint_closeout_missing_after_artifact_green(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "artifacts"
    job_dir = root / "job-1"
    _write_json(job_dir / "status.json", {"status": "running", "explore_phase": "exploring"})
    monkeypatch.setattr(replay, "LOCAL_ARTIFACTS_ROOT", root)

    def fake_emit(_job_id: str, _timeout_sec: float) -> dict[str, object]:
        for name in replay.REQUIRED_CONTRACT_ARTIFACTS:
            _write_json(job_dir / name, {"name": name})
        return {"status": "ok", "exit_code": 0, "elapsed_sec": 0.01}

    monkeypatch.setattr(replay, "_emit_contract_artifacts_subprocess", fake_emit)

    result = replay.replay_s07_contract_artifacts(job_id="job-1", output_root=tmp_path / "out")

    assert result["blocking_signal"] == "s07_checkpoint_closeout_missing"
    assert result["classification"] == "family_blocker"
    assert result["product_green_claimed"] is False


def test_replay_reports_terminal_status_missing_after_checkpoint_green(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "artifacts"
    job_dir = root / "job-1"
    _write_json(job_dir / "status.json", {"status": "running", "explore_phase": "exploring"})
    _write_json(job_dir / "checkpoints" / "s07_finalize.json", {"completed": True, "phase": "done"})
    monkeypatch.setattr(replay, "LOCAL_ARTIFACTS_ROOT", root)

    def fake_emit(_job_id: str, _timeout_sec: float) -> dict[str, object]:
        for name in replay.REQUIRED_CONTRACT_ARTIFACTS:
            _write_json(job_dir / name, {"name": name})
        return {"status": "ok", "exit_code": 0, "elapsed_sec": 0.01}

    monkeypatch.setattr(replay, "_emit_contract_artifacts_subprocess", fake_emit)

    result = replay.replay_s07_contract_artifacts(job_id="job-1", output_root=tmp_path / "out")

    assert result["blocking_signal"] == "s07_terminal_status_closeout_missing"
    assert result["classification"] == "family_blocker"
    assert result["product_green_claimed"] is False


def test_replay_reports_emit_timeout(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "artifacts"
    (root / "job-1").mkdir(parents=True)
    monkeypatch.setattr(replay, "LOCAL_ARTIFACTS_ROOT", root)
    monkeypatch.setattr(
        replay,
        "_emit_contract_artifacts_subprocess",
        lambda _job_id, _timeout_sec: {"status": "timeout", "exit_code": None, "elapsed_sec": 1.0},
    )

    result = replay.replay_s07_contract_artifacts(job_id="job-1", output_root=tmp_path / "out")

    assert result["blocking_signal"] == "s07_contract_artifact_emit_timeout"
    assert result["classification"] == "family_blocker"


def test_replay_reports_emit_failure(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "artifacts"
    (root / "job-1").mkdir(parents=True)
    monkeypatch.setattr(replay, "LOCAL_ARTIFACTS_ROOT", root)
    monkeypatch.setattr(
        replay,
        "_emit_contract_artifacts_subprocess",
        lambda _job_id, _timeout_sec: {"status": "failed", "exit_code": 2, "elapsed_sec": 0.1},
    )

    result = replay.replay_s07_contract_artifacts(job_id="job-1", output_root=tmp_path / "out")

    assert result["blocking_signal"] == "s07_contract_artifact_emit_failed"
    assert result["claim_ceiling"] == "s07_contract_artifact_replay_only"
