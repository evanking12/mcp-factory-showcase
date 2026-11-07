from __future__ import annotations

import json
from pathlib import Path

from scripts.regression.classify_s07_managed_closeout import (
    REQUIRED_CONTRACT_ARTIFACTS,
    classify_s07_managed_closeout,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_required_artifacts(root: Path) -> None:
    for name in REQUIRED_CONTRACT_ARTIFACTS:
        (root / name).write_text(f"{name}\n", encoding="utf-8")


def _source_root(tmp_path: Path, *, job_id: str = "job-s07", target: str = "fee_quote") -> tuple[Path, Path]:
    source_root = tmp_path / "proof"
    run_dir = source_root / "runs" / f"04-{target}"
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "run_result.json",
        {
            "job_id": job_id,
            "target": target,
            "status": "failed",
            "failure_domain": "pipeline",
        },
    )
    return source_root, run_dir


def _classify(tmp_path: Path, source_root: Path, **kwargs):
    return classify_s07_managed_closeout(
        source_proof_root=source_root,
        target=kwargs.pop("target", "fee_quote"),
        output_root=tmp_path / "out",
        **kwargs,
    )


def test_classifier_marks_artifact_child_return_missing(tmp_path: Path) -> None:
    source_root, run_dir = _source_root(tmp_path)
    _write_json(run_dir / "status.json", {"status": "running"})

    result = _classify(tmp_path, source_root)

    assert result["sharp_signal"] == "s07_contract_artifact_child_return_missing"
    assert result["artifact_child_return"]["state"] == "missing"
    assert result["safe_to_compare"] is False


def test_classifier_marks_checkpoint_save_missing_after_artifacts(tmp_path: Path) -> None:
    source_root, run_dir = _source_root(tmp_path)
    _write_required_artifacts(run_dir)
    _write_json(run_dir / "status.json", {"status": "running"})

    result = _classify(tmp_path, source_root)

    assert result["sharp_signal"] == "s07_checkpoint_closeout_missing"
    assert result["artifact_child_return"]["state"] == "present"
    assert result["checkpoint_save_return"]["state"] == "missing"


def test_classifier_marks_macro_verdict_missing_after_checkpoint(tmp_path: Path) -> None:
    source_root, run_dir = _source_root(tmp_path)
    _write_required_artifacts(run_dir)
    _write_json(run_dir / "session" / "checkpoints" / "s07_finalize.json", {"completed": True})
    _write_json(run_dir / "status.json", {"status": "running"})

    result = _classify(tmp_path, source_root)

    assert result["sharp_signal"] == "s07_macro_verdict_persist_missing"
    assert result["checkpoint_save_return"]["state"] == "returned"
    assert result["macro_verdict_persist"]["state"] == "missing"


def test_classifier_uses_checkpoint_save_authority_packet(tmp_path: Path) -> None:
    source_root, run_dir = _source_root(tmp_path)
    _write_required_artifacts(run_dir)
    _write_json(
        run_dir / "checkpoints" / "s07_finalize_save_authority.json",
        {
            "state": "returned",
            "checkpoint_blob": "job-s07/checkpoints/s07_finalize.json",
            "checkpoint_sha256": "abc123",
            "checkpoint_bytes": 42,
        },
    )
    _write_json(run_dir / "status.json", {"status": "running"})

    result = _classify(tmp_path, source_root)

    assert result["sharp_signal"] == "s07_macro_verdict_persist_missing"
    assert result["checkpoint_save_return"]["state"] == "returned"
    assert result["checkpoint_save_return"]["authority_returned"] is True
    assert result["checkpoint_save_return"]["evidence"]["authority_checkpoint_sha256"] == "abc123"


def test_classifier_marks_checkpoint_save_failed_from_authority_packet(tmp_path: Path) -> None:
    source_root, run_dir = _source_root(tmp_path)
    _write_required_artifacts(run_dir)
    _write_json(
        run_dir / "checkpoints" / "s07_finalize_save_authority.json",
        {
            "state": "failed",
            "error": "s07_checkpoint_save_missing_or_incomplete",
        },
    )
    _write_json(run_dir / "status.json", {"status": "running"})

    result = _classify(tmp_path, source_root)

    assert result["sharp_signal"] == "s07_checkpoint_closeout_missing"
    assert result["checkpoint_save_return"]["state"] == "failed_or_timeout"
    assert result["checkpoint_save_return"]["trace_failed_or_timed_out"] is True


def test_classifier_marks_terminal_status_nonterminal_after_verdict(tmp_path: Path) -> None:
    source_root, run_dir = _source_root(tmp_path)
    _write_required_artifacts(run_dir)
    _write_json(run_dir / "session" / "checkpoints" / "s07_finalize.json", {"completed": True})
    _write_json(run_dir / "macro_verdict.json", {"status": "done"})
    _write_json(run_dir / "status.json", {"status": "running", "explore_stage": "s07_finalize"})

    result = _classify(tmp_path, source_root)

    assert result["sharp_signal"] == "s07_terminal_status_closeout_missing"
    assert result["macro_verdict_persist"]["state"] == "persisted"
    assert result["terminal_status_persist"]["state"] == "nonterminal"


def test_classifier_uses_macro_verdict_authority_packet(tmp_path: Path) -> None:
    source_root, run_dir = _source_root(tmp_path)
    _write_required_artifacts(run_dir)
    _write_json(run_dir / "session" / "checkpoints" / "s07_finalize.json", {"completed": True})
    _write_json(
        run_dir / "macro_verdict_persist_authority.json",
        {
            "state": "returned",
            "verdict_blob": "job-s07/macro_verdict.json",
            "verdict_sha256": "def456",
            "verdict_bytes": 54,
            "verdict_status": "done",
        },
    )
    _write_json(run_dir / "status.json", {"status": "running", "explore_stage": "s07_finalize"})

    result = _classify(tmp_path, source_root)

    assert result["sharp_signal"] == "s07_terminal_status_closeout_missing"
    assert result["macro_verdict_persist"]["state"] == "persisted"
    assert result["macro_verdict_persist"]["authority_returned"] is True
    assert result["macro_verdict_persist"]["evidence"]["authority_verdict_sha256"] == "def456"


def test_classifier_marks_macro_verdict_failed_from_authority_packet(tmp_path: Path) -> None:
    source_root, run_dir = _source_root(tmp_path)
    _write_required_artifacts(run_dir)
    _write_json(run_dir / "session" / "checkpoints" / "s07_finalize.json", {"completed": True})
    _write_json(
        run_dir / "macro_verdict_persist_authority.json",
        {
            "state": "failed",
            "error": "macro_verdict_persist_missing_or_mismatched",
        },
    )
    _write_json(run_dir / "status.json", {"status": "running", "explore_stage": "s07_finalize"})

    result = _classify(tmp_path, source_root)

    assert result["sharp_signal"] == "s07_macro_verdict_persist_missing"
    assert result["macro_verdict_persist"]["state"] == "failed_or_timeout"
    assert result["macro_verdict_persist"]["trace_failed_or_timed_out"] is True


def test_classifier_marks_green_when_all_boundaries_present(tmp_path: Path) -> None:
    source_root, run_dir = _source_root(tmp_path)
    _write_required_artifacts(run_dir)
    _write_json(run_dir / "session" / "checkpoints" / "s07_finalize.json", {"completed": True})
    _write_json(run_dir / "macro_verdict.json", {"status": "done"})
    _write_json(run_dir / "status.json", {"status": "done", "explore_phase": "done", "explore_stage": "done"})

    result = _classify(tmp_path, source_root)

    assert result["sharp_signal"] == "s07_managed_closeout_green"
    assert result["classification"] == "local_bug"
    assert result["product_green_claimed"] is False


def test_classifier_uses_final_status_authority_packet(tmp_path: Path) -> None:
    source_root, run_dir = _source_root(tmp_path)
    _write_required_artifacts(run_dir)
    _write_json(run_dir / "session" / "checkpoints" / "s07_finalize.json", {"completed": True})
    _write_json(run_dir / "macro_verdict.json", {"status": "done"})
    _write_json(
        run_dir / "final_status_persist_authority.json",
        {
            "state": "returned",
            "status_blob": "job-s07/status.json",
            "status_sha256": "fed789",
            "status_bytes": 112,
            "terminal_status": "done",
            "predecessor_verdict_blob": "job-s07/macro_verdict.json",
            "predecessor_verdict_sha256": "def456",
            "predecessor_authority_blob": "job-s07/macro_verdict_persist_authority.json",
            "predecessor_authority_sha256": "abc123",
        },
    )
    _write_json(run_dir / "status.json", {"status": "running", "explore_stage": "s07_finalize"})

    result = _classify(tmp_path, source_root)

    assert result["sharp_signal"] == "s07_managed_closeout_green"
    assert result["terminal_status_persist"]["state"] == "terminal"
    assert result["terminal_status_persist"]["authority_returned"] is True
    assert result["terminal_status_persist"]["evidence"]["authority_status_sha256"] == "fed789"
    assert result["terminal_status_persist"]["evidence"]["authority_predecessor_verdict_sha256"] == "def456"


def test_classifier_marks_final_status_failed_from_authority_packet(tmp_path: Path) -> None:
    source_root, run_dir = _source_root(tmp_path)
    _write_required_artifacts(run_dir)
    _write_json(run_dir / "session" / "checkpoints" / "s07_finalize.json", {"completed": True})
    _write_json(run_dir / "macro_verdict.json", {"status": "done"})
    _write_json(
        run_dir / "final_status_persist_authority.json",
        {
            "state": "failed",
            "error": "final_status_persist_missing_or_nonterminal",
        },
    )
    _write_json(run_dir / "status.json", {"status": "running", "explore_stage": "s07_finalize"})

    result = _classify(tmp_path, source_root)

    assert result["sharp_signal"] == "s07_terminal_status_closeout_missing"
    assert result["terminal_status_persist"]["state"] == "failed_or_timeout"
    assert result["terminal_status_persist"]["trace_failed_or_timed_out"] is True


def test_classifier_uses_replay_recovery_for_child_return(tmp_path: Path) -> None:
    source_root, run_dir = _source_root(tmp_path)
    _write_required_artifacts(run_dir)
    replay_path = tmp_path / "replay.json"
    _write_json(
        replay_path,
        {
            "after": {name: {"exists": True} for name in REQUIRED_CONTRACT_ARTIFACTS},
            "emit": {"status": "ok", "recovered_without_child_return": True},
        },
    )

    result = _classify(tmp_path, source_root, s07_replay_result=replay_path)

    assert result["artifact_child_return"]["state"] == "recovered_without_child_return"
    assert result["artifact_child_return"]["recovered_without_child_return"] is True
