from __future__ import annotations

import json
from pathlib import Path

from scripts.regression import write_checkpoint_job_summary, write_ci_job_summary


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_job_summary_writes_startup_failure_without_result(
    monkeypatch, tmp_path: Path
) -> None:
    startup_root = tmp_path / "lane_startup"
    _write_json(
        startup_root / "lane-startup-failure.json",
        {
            "status": "failed",
            "stage": "api_contract",
            "failure_kind": "api_contract_failed",
            "message": "API runtime contract check failed.",
        },
    )
    summary_path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))

    exit_code = write_ci_job_summary.main(
        [
            "--result",
            str(tmp_path / "missing-result.json"),
            "--startup-root",
            str(startup_root),
        ]
    )

    assert exit_code == 0
    markdown = summary_path.read_text(encoding="utf-8")
    assert "## Managed Lane Startup" in markdown
    assert "api_contract_failed" in markdown
    assert "API runtime contract check failed." in markdown


def test_job_summary_includes_startup_and_suite_failure(
    monkeypatch, tmp_path: Path
) -> None:
    startup_root = tmp_path / "lane_startup"
    _write_json(
        startup_root / "lane-startup.json",
        {
            "status": "passed",
            "promotion_safe": True,
            "lab_status": {"status": "valid"},
        },
    )
    result_path = tmp_path / "easy01-result.json"
    _write_json(
        result_path,
        {
            "surface": "easy-01",
            "verdict": "fail",
            "reasons": ["runner_exception:RuntimeError"],
            "runner_exception": {
                "type": "RuntimeError",
                "message": "api_identity_failed:api_openapi_unavailable",
            },
        },
    )
    summary_path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))

    exit_code = write_ci_job_summary.main(
        [
            "--result",
            str(result_path),
            "--startup-root",
            str(startup_root),
        ]
    )

    assert exit_code == 0
    markdown = summary_path.read_text(encoding="utf-8")
    assert "## Managed Lane Startup" in markdown
    assert "- Verdict: `pass`" in markdown
    assert "## easy-01" in markdown
    assert "api_identity_failed:api_openapi_unavailable" in markdown


def test_checkpoint_job_summary_includes_last_observation(monkeypatch, tmp_path: Path) -> None:
    packet_path = tmp_path / "checkpoint-result.json"
    _write_json(
        packet_path,
        {
            "target_name": "session_bootstrap",
            "verdict": "fail",
            "job_id": "job-1",
            "phase": "exploring",
            "failure_kind": "explore_timeout",
            "message": "Runner observed a non-terminal timeout while polling job status.",
            "last_observation": {
                "stage": "s07_finalize",
                "span": "s07_harmonize_promote_findings",
                "explore_phase": "exploring",
                "progress": "1/1",
                "signature_stable_seconds": 90.0,
                "soft_stall_hint": "s07_harmonize_promote_findings_no_close",
            },
        },
    )
    summary_path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))

    exit_code = write_checkpoint_job_summary.main(["--packet", str(packet_path)])

    assert exit_code == 0
    markdown = summary_path.read_text(encoding="utf-8")
    assert "Last observation" in markdown
    assert "stage=s07_finalize" in markdown
    assert "span=s07_harmonize_promote_findings" in markdown
    assert "Suspected stall: `s07_harmonize_promote_findings_no_close`" in markdown
