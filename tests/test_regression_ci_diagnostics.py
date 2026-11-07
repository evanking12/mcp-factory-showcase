from __future__ import annotations

import json
from pathlib import Path

import scripts.regression.regression_ci_diagnostics as diagnostics


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_checkpoint_start_writes_started_packet(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RUNNER_LABEL", "regression-a")
    monkeypatch.setenv("API_PORT", "18201")
    monkeypatch.setenv("BRIDGE_PORT", "18090")

    packet = diagnostics.checkpoint_start(
        case_id="easy-01",
        target_name="session_bootstrap",
        checkpoint_root=tmp_path / "checkpoint",
        checkpoint_output_root=tmp_path / "checkpoint" / "easy01",
        commit="abc123",
    )

    written = _read_json(tmp_path / "checkpoint" / "checkpoint-job-started.json")
    assert written == packet
    assert written["case_id"] == "easy-01"
    assert written["target_name"] == "session_bootstrap"
    assert written["runner"] == "regression-a"
    assert written["api_port"] == "18201"
    assert written["bridge_port"] == "18090"


def test_checkpoint_finalize_writes_fallback_when_packet_missing(tmp_path: Path) -> None:
    checkpoint_root = tmp_path / "checkpoint"
    output_root = checkpoint_root / "medium01"

    status = diagnostics.checkpoint_finalize(
        case_id="medium-01",
        target_name="session_bootstrap",
        checkpoint_root=checkpoint_root,
        checkpoint_output_root=output_root,
        commit="abc123",
    )

    packet = _read_json(output_root / "checkpoint-result.json")
    assert packet["verdict"] == "fail"
    assert packet["failure_kind"] == "missing_checkpoint_packet_after_failure"
    assert status["checkpoint_packet_present"] is True
    assert (checkpoint_root / "checkpoint-artifact-status.json").exists()
    assert (output_root / "checkpoint-artifact-status.json").exists()


def test_checkpoint_finalize_preserves_existing_packet_and_writes_status(tmp_path: Path) -> None:
    checkpoint_root = tmp_path / "checkpoint"
    output_root = checkpoint_root / "easy01"
    existing = {
        "case_id": "easy-01",
        "target_name": "reservation_stage",
        "verdict": "pass",
        "job_id": "job-1",
    }
    _write_json(output_root / "checkpoint-result.json", existing)
    _write_json(output_root / "run-record.json", {"job_id": "job-1"})
    _write_json(
        output_root / "heartbeats.json",
        {
            "lane-1": {
                "details": {
                    "last_observation": {
                        "stage": "s07_finalize",
                        "span": "s07_harmonize_promote_findings",
                        "message": "Finalizing harmonized state...",
                        "soft_stall_hint": "s07_harmonize_promote_findings_no_close",
                    }
                }
            }
        },
    )
    _write_json(checkpoint_root / "lane_startup" / "lane-startup.json", {"verdict": "pass"})
    (output_root / "runs" / "01-reservation").mkdir(parents=True)

    status = diagnostics.checkpoint_finalize(
        case_id="easy-01",
        target_name="reservation_stage",
        checkpoint_root=checkpoint_root,
        checkpoint_output_root=output_root,
        commit="abc123",
    )

    assert _read_json(output_root / "checkpoint-result.json") == existing
    assert status["run_record_present"] is True
    assert status["heartbeat_present"] is True
    assert status["startup_packet_present"] is True
    assert status["run_directory_present"] is True
    assert status["last_observation"]["stage"] == "s07_finalize"
    assert status["last_observation"]["span"] == "s07_harmonize_promote_findings"


def test_baseline_precheck_passes_when_required_files_exist(tmp_path: Path, monkeypatch) -> None:
    baseline_root = tmp_path / "baseline"
    for name in diagnostics.REQUIRED_BASELINE_FILES:
        (baseline_root / name).parent.mkdir(parents=True, exist_ok=True)
        (baseline_root / name).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        diagnostics,
        "load_gate_config",
        lambda config_path, repo_root: {
            "suites": [{"case_id": "easy-01", "baseline_output_root": str(baseline_root)}]
        },
    )

    packet = diagnostics.baseline_precheck(
        config_path=tmp_path / "gate.json",
        case_id="easy-01",
        output_root=tmp_path / "out",
    )

    assert packet["verdict"] == "pass"
    assert packet["missing_files"] == []


def test_baseline_precheck_reports_unavailable_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        diagnostics,
        "load_gate_config",
        lambda config_path, repo_root: {
            "suites": [{"case_id": "medium-01", "baseline_output_root": str(tmp_path / "missing")}]
        },
    )

    packet = diagnostics.baseline_precheck(
        config_path=tmp_path / "gate.json",
        case_id="medium-01",
        output_root=tmp_path / "out",
    )

    assert packet["verdict"] == "fail"
    assert packet["reasons"] == ["baseline_unavailable_in_summary_job"]


def test_baseline_precheck_lists_missing_required_files(tmp_path: Path, monkeypatch) -> None:
    baseline_root = tmp_path / "baseline"
    baseline_root.mkdir()
    (baseline_root / "compiled-ingest-summary.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        diagnostics,
        "load_gate_config",
        lambda config_path, repo_root: {
            "suites": [{"case_id": "easy-01", "baseline_output_root": str(baseline_root)}]
        },
    )

    packet = diagnostics.baseline_precheck(
        config_path=tmp_path / "gate.json",
        case_id="easy-01",
        output_root=tmp_path / "out",
    )

    assert packet["verdict"] == "fail"
    assert packet["reasons"] == ["baseline_required_files_missing"]
    assert "compiled-ingest-compare-report.json" in packet["missing_files"]
    assert "compiled-ingest.log" in packet["missing_files"]


def test_artifact_manifest_reports_zero_downloaded_artifacts(tmp_path: Path) -> None:
    packet = diagnostics.artifact_manifest(
        case_id="easy-01",
        checkpoint_artifacts_root=tmp_path / "missing",
        output_root=tmp_path / "out",
    )

    assert packet["downloaded_artifact_count"] == 0
    assert packet["found_checkpoint_count"] == 0
    assert packet["missing_targets"] == [
        "session_bootstrap",
        "reservation_stage",
        "release_commit",
        "audit_trace",
    ]


def test_artifact_manifest_reports_partial_missing_targets(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _write_json(
        root / "medium01-checkpoint-session-bootstrap" / "medium01" / "checkpoint-result.json",
        {"case_id": "medium-01", "target_name": "session_bootstrap", "verdict": "pass"},
    )
    _write_json(
        root / "medium01-checkpoint-reservation-stage" / "medium01" / "checkpoint-result.json",
        {"case_id": "medium-01", "target_name": "reservation_stage", "verdict": "fail", "failure_kind": "explore_timeout"},
    )

    packet = diagnostics.artifact_manifest(
        case_id="medium-01",
        checkpoint_artifacts_root=root,
        output_root=tmp_path / "out",
    )

    assert packet["downloaded_artifact_count"] == 2
    assert packet["found_checkpoint_count"] == 2
    assert packet["missing_targets"] == ["dispatch_preview", "fee_quote", "settlement_reconcile"]
    failed = [row for row in packet["found_checkpoint_packets"] if row["target_name"] == "reservation_stage"][0]
    assert failed["failure_kind"] == "explore_timeout"


def test_triage_prioritizes_checkpoint_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RUNNER_LABEL", "regression-b")
    monkeypatch.setenv("API_PORT", "18211")
    monkeypatch.setenv("BRIDGE_PORT", "18100")
    output_root = tmp_path / "out"
    _write_json(output_root / "medium01-result.json", {"surface": "medium-01", "reasons": ["compiled_ingest_compare_failed"]})
    _write_json(
        output_root / "medium01-checkpoints.json",
        {
            "first_failed_checkpoint": "session_bootstrap",
            "checkpoints": [
                {
                    "target_name": "session_bootstrap",
                    "verdict": "fail",
                    "failure_kind": "explore_timeout",
                    "failure_domain": "pipeline",
                }
            ],
        },
    )
    _write_json(output_root / "baseline-access.json", {"verdict": "pass"})
    _write_json(output_root / "checkpoint-artifact-manifest.json", {"downloaded_artifact_count": 1, "found_checkpoint_count": 1, "missing_targets": []})

    packet = diagnostics.triage(
        case_id="medium-01",
        output_root=output_root,
        result_path=output_root / "medium01-result.json",
        checkpoints_path=output_root / "medium01-checkpoints.json",
        baseline_access_path=output_root / "baseline-access.json",
        artifact_manifest_path=output_root / "checkpoint-artifact-manifest.json",
        commit="abc123",
    )

    assert packet["first_failed_tier"] == "tier3"
    assert packet["first_failed_checkpoint"] == "session_bootstrap"
    assert packet["failure_kind"] == "explore_timeout"
    assert packet["next_action"] == "investigate_session_bootstrap_explore_timeout"
    assert (output_root / "regression-triage.md").exists()


def test_regression_workflows_include_observability_guardrails() -> None:
    required = (REPO_ROOT / ".github" / "workflows" / "required-regression-gates.yml").read_text(encoding="utf-8")
    easy_diagnostics = (
        REPO_ROOT / ".github" / "workflows" / "easy01-diagnostic-checkpoints.yml"
    ).read_text(encoding="utf-8")
    medium = (REPO_ROOT / ".github" / "workflows" / "medium01-checkpoints.yml").read_text(encoding="utf-8")

    assert "name: Product Baseline Gate" in required
    assert "runs-on: [self-hosted, Windows, regression-a]" in required
    assert "run_regression_gate_v1.py" in required
    assert "--surfaces lane_trust,easy-01,medium-01" in required
    assert "name: Easy01 Summary" not in required
    assert "run_spectrum_compiled_easy01.py" not in required
    assert "medium01-result.json" in required

    assert "name: Easy01 Diagnostic Checkpoints" in easy_diagnostics
    assert "workflow_run:" in easy_diagnostics
    assert "continue-on-error: true" in easy_diagnostics
    assert "runs-on: [self-hosted, Windows, regression-a]" in easy_diagnostics
    assert "scripts\\runs\\run_spectrum_compiled_easy01_product.py" in easy_diagnostics
    assert "run_spectrum_compiled_easy01.py" not in easy_diagnostics
    assert "regression_ci_diagnostics.py checkpoint-start" in easy_diagnostics
    assert "regression_ci_diagnostics.py checkpoint-finalize" in easy_diagnostics
    assert "path: ${{ env.CHECKPOINT_ROOT }}/**" in easy_diagnostics

    assert "name: Medium01 Summary" in medium
    assert "runs-on: [self-hosted, Windows, regression-b]" in medium
    assert medium.count("clean: false") == 7
    assert medium.count("Release self-hosted workspace locks") == 7
    assert medium.count("regression_ci_diagnostics.py checkpoint-start") == 5
    assert medium.count("regression_ci_diagnostics.py checkpoint-finalize") == 5
    assert medium.count("timeout-minutes: 25") == 5
    assert medium.count("path: ${{ env.CHECKPOINT_ROOT }}/**") == 5
    assert "regression_ci_diagnostics.py baseline-precheck" in medium
    assert "regression_ci_diagnostics.py artifact-manifest" in medium
    assert "regression_ci_diagnostics.py triage" in medium
