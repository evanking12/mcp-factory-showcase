from __future__ import annotations

import json
import subprocess
from pathlib import Path
import sys

import pytest

import scripts.regression.aggregate_checkpoint_suite as aggregate_module
from scripts.runs.run_spectrum_compiled_easy01 import run_spectrum_compiled_easy01
from scripts.runs.run_spectrum_compiled_medium01 import run_spectrum_compiled_medium01


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_aggregate_checkpoint_suite_cli_bootstraps_repo_imports() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "regression" / "aggregate_checkpoint_suite.py"
    completed = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        text=True,
        cwd=script_path.parents[2],
        check=False,
    )

    assert completed.returncode == 0
    assert "Aggregate checkpoint artifacts" in completed.stdout


@pytest.mark.parametrize(
    "relative_path",
    [
        "scripts/regression/write_ci_job_summary.py",
        "scripts/regression/write_checkpoint_job_summary.py",
        "scripts/regression/run_regression_gate_v1.py",
        "scripts/runs/run_spectrum_compiled_easy01.py",
        "scripts/runs/run_spectrum_compiled_easy01_product.py",
        "scripts/runs/run_spectrum_compiled_medium01.py",
        "scripts/runs/run_spectrum_compiled_medium01_product.py",
        "scripts/runs/run_spectrum_compiled_medium02_product.py",
        "scripts/runs/run_spectrum_compiled_hard01_product.py",
    ],
)
def test_regression_ci_entrypoints_support_help(relative_path: str) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / relative_path

    completed = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        text=True,
        cwd=repo_root,
        check=False,
    )

    assert completed.returncode == 0
    assert "usage:" in completed.stdout.lower()


def test_required_regression_gates_enforces_product_baseline_gate() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "required-regression-gates.yml"
    ).read_text(encoding="utf-8")

    assert "name: Product Baseline Gate" in workflow
    assert "--surfaces lane_trust,easy-01,medium-01,medium-02,hard-01" in workflow
    assert "scripts/regression/run_regression_gate_v1.py" in workflow
    assert "scripts\\runs\\run_spectrum_compiled_easy01.py" not in workflow
    assert "easy01-session-bootstrap:" not in workflow
    assert "easy01-summary:" not in workflow
    assert "medium01-result.json" in workflow
    assert "medium02-result.json" in workflow
    assert "hard01-result.json" in workflow


def test_easy01_diagnostic_checkpoints_are_product_runner_only() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "easy01-diagnostic-checkpoints.yml"
    ).read_text(encoding="utf-8")

    assert "name: Easy01 Diagnostic Checkpoints" in workflow
    assert "workflow_run:" in workflow
    assert "continue-on-error: true" in workflow
    assert "scripts\\runs\\run_spectrum_compiled_easy01_product.py" in workflow
    assert "scripts\\runs\\run_spectrum_compiled_easy01.py" not in workflow


def _easy_manifest(tmp_path: Path) -> dict:
    fixture_root = tmp_path / "easy-fixtures"
    fixture_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for staged_name, target_name in [
        ("spectrum_session_bootstrap.dll", "session_bootstrap"),
        ("spectrum_reservation_stage.dll", "reservation_stage"),
        ("spectrum_release_commit.dll", "release_commit"),
        ("spectrum_audit_trace.dll", "audit_trace"),
    ]:
        dll_path = fixture_root / staged_name
        dll_path.write_bytes(staged_name.encode("utf-8"))
        rows.append(
            {
                "staged_name": staged_name,
                "source_path": str(dll_path),
                "target_name": target_name,
            }
        )
    return {
        "selected_runtime_targets": rows[:2],
        "bundled_dlls": rows,
    }


def _medium_manifest(tmp_path: Path) -> dict:
    fixture_root = tmp_path / "medium-fixtures"
    fixture_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for staged_name, target_name in [
        ("spectrum_session_bootstrap.dll", "session_bootstrap"),
        ("spectrum_reservation_stage.dll", "reservation_stage"),
        ("spectrum_dispatch_preview.dll", "dispatch_preview"),
        ("spectrum_fee_quote.dll", "fee_quote"),
        ("spectrum_settlement_reconcile.dll", "settlement_reconcile"),
    ]:
        dll_path = fixture_root / staged_name
        dll_path.write_bytes(staged_name.encode("utf-8"))
        rows.append(
            {
                "staged_name": staged_name,
                "source_path": str(dll_path),
                "target_name": target_name,
            }
        )
    return {
        "selected_runtime_targets": rows[:2],
        "bundled_dlls": rows,
    }


def test_easy01_checkpoint_target_selection_preserves_explicit_predecessors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _easy_manifest(tmp_path)
    captured_settings: list[dict[str, object]] = []

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_compiled_truth_manifest",
        lambda: {"dlls": []},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": "suite"},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.load_spectrum_authored_easy_manifest",
        lambda: {"active_modules": []},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.ApiClient",
        lambda api_url, api_key: object(),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_easy01.build_spectrum_compiled_easy01_report",
        lambda **kwargs: {
            "binary_ingest_proof_succeeded": True,
            "semantic_checkpoint_alignment_succeeded": True,
            "per_run": [],
        },
    )

    def fake_run_one(*args, **kwargs):
        captured_settings.append(dict(args[8]))
        return {
            "job_id": "job-release",
            "status": "ok",
            "phase": "done",
            "job_terminalization": {"terminalization_kind": "done"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_easy01.run_one", fake_run_one)

    output_root = tmp_path / "easy-out"
    result = run_spectrum_compiled_easy01(
        api_url="http://api.test",
        bridge_url="http://bridge.test",
        output_root=output_root,
        target_names=["release_commit"],
        prior_job_id="job-reservation",
        cross_dll_prior_job_ids=["job-session", "job-reservation"],
    )

    assert len(captured_settings) == 1
    assert captured_settings[0]["prior_job_id"] == "job-reservation"
    assert captured_settings[0]["cross_dll_prior_job_ids"] == ["job-session", "job-reservation"]
    packet = json.loads((output_root / "checkpoint-result.json").read_text(encoding="utf-8"))
    assert packet["target_name"] == "release_commit"
    assert packet["predecessor_targets"] == ["session_bootstrap", "reservation_stage"]
    assert packet["job_id"] == "job-release"
    assert result["checkpoint_packet"]["verdict"] == "pass"


def test_medium01_checkpoint_target_selection_preserves_explicit_predecessors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = _medium_manifest(tmp_path)
    captured_settings: list[dict[str, object]] = []

    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.ensure_spectrum_compiled_package_built",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_compiled_package_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_compiled_truth_manifest",
        lambda: {"dlls": []},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_authored_truth_manifest",
        lambda: {"suite_id": "suite"},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.load_spectrum_authored_medium01_manifest",
        lambda: {"active_modules": []},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.verify_api_identity",
        lambda api_url, api_key: (True, "api_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.verify_bridge_identity",
        lambda bridge_url, bridge_key: (True, "bridge_ok:test"),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.ensure_strict_local_lane_preflight",
        lambda **kwargs: {"admitted": True},
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.ApiClient",
        lambda api_url, api_key: object(),
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.build_spectrum_compiled_medium01_report",
        lambda **kwargs: {
            "binary_ingest_proof_succeeded": True,
            "semantic_checkpoint_alignment_succeeded": True,
            "per_run": [],
        },
    )
    monkeypatch.setattr(
        "scripts.runs.run_spectrum_compiled_medium01.emit_spectrum_medium01_semantic_continuation",
        lambda **kwargs: None,
    )

    def fake_run_one(*args, **kwargs):
        captured_settings.append(dict(args[8]))
        return {
            "job_id": "job-fee",
            "status": "ok",
            "phase": "done",
            "job_terminalization": {"terminalization_kind": "done"},
        }

    monkeypatch.setattr("scripts.runs.run_spectrum_compiled_medium01.run_one", fake_run_one)

    output_root = tmp_path / "medium-out"
    result = run_spectrum_compiled_medium01(
        api_url="http://api.test",
        bridge_url="http://bridge.test",
        output_root=output_root,
        target_names=["fee_quote"],
        prior_job_id="job-reservation",
        cross_dll_prior_job_ids=["job-session", "job-reservation"],
    )

    assert len(captured_settings) == 1
    assert captured_settings[0]["prior_job_id"] == "job-reservation"
    assert captured_settings[0]["cross_dll_prior_job_ids"] == ["job-session", "job-reservation"]
    packet = json.loads((output_root / "checkpoint-result.json").read_text(encoding="utf-8"))
    assert packet["target_name"] == "fee_quote"
    assert packet["predecessor_targets"] == ["session_bootstrap", "reservation_stage"]
    assert packet["job_id"] == "job-fee"
    assert result["checkpoint_packet"]["verdict"] == "pass"


def test_aggregate_checkpoint_suite_rebuilds_easy01_from_checkpoint_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checkpoint_root = tmp_path / "checkpoint-artifacts"
    output_root = tmp_path / "aggregate-out"
    baseline_root = tmp_path / "baseline"

    chain_plan = (
        {
            "target_name": "session_bootstrap",
            "staged_name": "spectrum_session_bootstrap.dll",
            "required_semantic_checkpoint": "SP_OpenOperatorSession",
            "predecessor_targets": [],
        },
        {
            "target_name": "reservation_stage",
            "staged_name": "spectrum_reservation_stage.dll",
            "required_semantic_checkpoint": "SP_IssueReleaseHold",
            "predecessor_targets": ["session_bootstrap"],
        },
    )

    for index, (target_name, staged_name, job_id) in enumerate(
        [
            ("session_bootstrap", "spectrum_session_bootstrap.dll", "job-session"),
            ("reservation_stage", "spectrum_reservation_stage.dll", "job-reservation"),
        ],
        start=1,
    ):
        packet_dir = checkpoint_root / f"artifact-{index}"
        run_dir = packet_dir / "runs" / f"{index:02d}-{target_name}"
        _write_json(
            packet_dir / "checkpoint-result.json",
            {
                "case_id": "easy-01",
                "suite_id": "suite",
                "target_name": target_name,
                "staged_name": staged_name,
                "required_semantic_checkpoint": chain_plan[index - 1]["required_semantic_checkpoint"],
                "predecessor_targets": chain_plan[index - 1]["predecessor_targets"],
                "verdict": "pass",
                "job_id": job_id,
                "phase": "done",
                "run_dir_relative": f"runs/{index:02d}-{target_name}",
            },
        )
        run_record = {
            "job_id": job_id,
            "status": "ok",
            "phase": "done",
            "dll_name": staged_name,
            "run_dir": str(run_dir),
            "chain_context": {"target_name": target_name},
        }
        _write_json(packet_dir / "run-record.json", run_record)
        _write_json(run_dir / "job-status-analyze.json", {"result": {"invocables": []}})
        _write_json(run_dir / "session" / "session-meta.json", {"job_id": job_id})
        _write_json(run_dir / "session" / "stage-index.json", {"stages": ["discover", "explore"]})

    monkeypatch.setattr(
        aggregate_module,
        "load_gate_config",
        lambda config_path, repo_root: {
            "gate_id": "gate",
            "baseline_registry_path": str(tmp_path / "baseline_registry.json"),
            "suites": [
                {
                    "case_id": "easy-01",
                    "baseline_output_root": str(baseline_root),
                    "baseline_registry_entry": {"surface_id": "easy01"},
                }
            ],
        },
    )
    monkeypatch.setattr(aggregate_module, "load_spectrum_compiled_package_manifest", lambda: {"suite": "manifest"})
    monkeypatch.setattr(aggregate_module, "load_spectrum_compiled_truth_manifest", lambda: {"dlls": []})
    monkeypatch.setattr(aggregate_module, "load_spectrum_authored_truth_manifest", lambda: {"suite": "truth"})
    monkeypatch.setattr(
        aggregate_module,
        "_builder_bundle",
        lambda case_id: (
            chain_plan,
            lambda manifest: [dict(step) for step in chain_plan],
            lambda **kwargs: {
                "case_id": case_id,
                "compiled_targets": [step["staged_name"] for step in chain_plan],
                "expected_execution_flow": ["a", "b"],
                "expected_symbol_flow": ["SP_OpenOperatorSession", "SP_IssueReleaseHold"],
                "binary_ingest_proof_succeeded": True,
                "semantic_checkpoint_alignment_succeeded": True,
                "per_run": [
                    {
                        "dll_name": record["dll_name"],
                        "export_contract_match": True,
                        "semantic_checkpoint_match": True,
                        "session_artifacts_present": True,
                    }
                    for record in kwargs["run_records"]
                ],
            },
            lambda: {"active_modules": []},
        ),
    )
    monkeypatch.setattr(
        aggregate_module,
        "compare_compiled_suite_to_baseline",
        lambda **kwargs: {
            "surface": kwargs["case_id"],
            "verdict": "pass",
            "reasons": [],
            "accepted_differences": [],
        },
    )

    result, verdict = aggregate_module.aggregate_checkpoint_suite(
        config_path=tmp_path / "gate.json",
        case_id="easy-01",
        checkpoint_artifacts_root=checkpoint_root,
        output_root=output_root,
    )

    assert result["verdict"] == "pass"
    assert verdict["overall_verdict"] == "pass"
    summary = json.loads((output_root / "easy01" / "compiled-ingest-summary.json").read_text(encoding="utf-8"))
    assert [row["chain_context"]["target_name"] for row in summary["run_records"]] == [
        "session_bootstrap",
        "reservation_stage",
    ]
    assert summary["run_records"][0]["run_dir"].startswith(str(checkpoint_root))
    assert (output_root / "easy01-result.json").exists()
    assert (output_root / "gate-summary.json").exists()
    assert "session_bootstrap" in (output_root / "easy01" / "compiled-ingest.log").read_text(encoding="utf-8")


def test_aggregate_checkpoint_suite_surfaces_baseline_unavailable_precheck(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checkpoint_root = tmp_path / "checkpoint-artifacts"
    output_root = tmp_path / "aggregate-out"
    baseline_root = tmp_path / "missing-baseline"
    chain_plan = (
        {
            "target_name": "session_bootstrap",
            "staged_name": "spectrum_session_bootstrap.dll",
            "required_semantic_checkpoint": "SP_OpenOperatorSession",
            "predecessor_targets": [],
        },
    )
    packet_dir = checkpoint_root / "artifact-1"
    run_dir = packet_dir / "runs" / "01-session-bootstrap"
    _write_json(
        packet_dir / "checkpoint-result.json",
        {
            "case_id": "easy-01",
            "target_name": "session_bootstrap",
            "staged_name": "spectrum_session_bootstrap.dll",
            "required_semantic_checkpoint": "SP_OpenOperatorSession",
            "predecessor_targets": [],
            "verdict": "pass",
            "job_id": "job-session",
            "phase": "done",
            "run_dir_relative": "runs/01-session-bootstrap",
        },
    )
    _write_json(
        packet_dir / "run-record.json",
        {
            "job_id": "job-session",
            "status": "ok",
            "phase": "done",
            "dll_name": "spectrum_session_bootstrap.dll",
            "chain_context": {"target_name": "session_bootstrap"},
        },
    )
    _write_json(run_dir / "job-status-analyze.json", {"result": {"invocables": []}})
    _write_json(output_root / "baseline-access.json", {"verdict": "fail", "reasons": ["baseline_unavailable_in_summary_job"]})

    monkeypatch.setattr(
        aggregate_module,
        "load_gate_config",
        lambda config_path, repo_root: {
            "gate_id": "gate",
            "baseline_registry_path": str(tmp_path / "baseline_registry.json"),
            "suites": [
                {
                    "case_id": "easy-01",
                    "baseline_output_root": str(baseline_root),
                    "baseline_registry_entry": {"surface_id": "easy01"},
                }
            ],
        },
    )
    monkeypatch.setattr(aggregate_module, "load_spectrum_compiled_package_manifest", lambda: {"suite": "manifest"})
    monkeypatch.setattr(aggregate_module, "load_spectrum_compiled_truth_manifest", lambda: {"dlls": []})
    monkeypatch.setattr(aggregate_module, "load_spectrum_authored_truth_manifest", lambda: {"suite": "truth"})
    monkeypatch.setattr(
        aggregate_module,
        "_builder_bundle",
        lambda case_id: (
            chain_plan,
            lambda manifest: [dict(step) for step in chain_plan],
            lambda **kwargs: {
                "case_id": case_id,
                "binary_ingest_proof_succeeded": True,
                "semantic_checkpoint_alignment_succeeded": True,
                "per_run": [],
            },
            lambda: {"active_modules": []},
        ),
    )

    result, verdict = aggregate_module.aggregate_checkpoint_suite(
        config_path=tmp_path / "gate.json",
        case_id="easy-01",
        checkpoint_artifacts_root=checkpoint_root,
        output_root=output_root,
    )

    assert result["verdict"] == "fail"
    assert result["reasons"] == ["baseline_unavailable_in_summary_job"]
    assert result["comparison"]["baseline_access"]["verdict"] == "fail"
    assert verdict["overall_verdict"] == "fail"
