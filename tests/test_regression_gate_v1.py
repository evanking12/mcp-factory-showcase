from __future__ import annotations

import json
from pathlib import Path

from api.analysis.regression_gate_v1 import (
    aggregate_gate_verdict,
    build_medium01_checkpoint_report,
    compare_compiled_suite_to_baseline,
    evaluate_compiled_suite_artifacts,
    evaluate_lane_trust_output,
    load_gate_config,
)
from scripts.regression.run_regression_gate_v1 import run_regression_gate

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _suite_root(
    tmp_path: Path,
    name: str,
    *,
    summary_case_id: str = "easy-01",
    report_case_id: str = "easy-01",
    summary_overrides: dict[str, object] | None = None,
    report_overrides: dict[str, object] | None = None,
) -> Path:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    summary_payload = {
        "suite_id": "spectrum_transaction_release_settlement_suite",
        "case_id": summary_case_id,
        "run_records": [
            {"target": "session_bootstrap", "status": "ok"},
            {"target": "reservation_stage", "status": "ok"},
        ],
    }
    summary_payload.update(summary_overrides or {})
    report_payload = {
        "suite_id": "spectrum_transaction_release_settlement_suite",
        "case_id": report_case_id,
        "compiled_targets": ["a.dll", "b.dll"],
        "expected_execution_flow": ["a.one", "b.two"],
        "expected_symbol_flow": ["A", "B"],
        "binary_ingest_proof_succeeded": True,
        "semantic_checkpoint_alignment_succeeded": True,
        "per_run": [
            {
                "dll_name": "a.dll",
                "expected_exports": ["A"],
                "discovered_invocables": ["A", "entry"],
                "export_contract_match": True,
                "semantic_checkpoint_statuses": {"A": "verified_success"},
                "semantic_checkpoint_match": True,
                "session_artifacts_present": True,
            },
            {
                "dll_name": "b.dll",
                "expected_exports": ["B"],
                "discovered_invocables": ["B", "entry"],
                "export_contract_match": True,
                "semantic_checkpoint_statuses": {"B": "verified_success"},
                "semantic_checkpoint_match": True,
                "session_artifacts_present": True,
            },
        ],
    }
    report_payload.update(report_overrides or {})
    _write_json(root / "compiled-ingest-summary.json", summary_payload)
    _write_json(root / "compiled-ingest-compare-report.json", report_payload)
    (root / "compiled-ingest.log").write_text("ok\n", encoding="utf-8")
    return root


def test_default_pinned_baselines_are_repo_tracked_comparison_surfaces() -> None:
    registry = json.loads(
        (REPO_ROOT / "configs/regression/baseline_registry.json").read_text(encoding="utf-8")
    )
    surfaces = {
        str(row.get("surface_id") or ""): dict(row)
        for row in list(registry.get("surfaces") or [])
    }
    for surface_id in ("easy01", "medium01", "medium02", "hard01"):
        root = Path(str(surfaces[surface_id]["pinned_root"]))
        assert root.parts[:2] == ("configs", "regression")
        for name in (
            "compiled-ingest-summary.json",
            "compiled-ingest-compare-report.json",
            "compiled-ingest.log",
        ):
            assert (REPO_ROOT / root / name).exists()


def test_load_gate_config_resolves_repo_relative_paths(tmp_path: Path) -> None:
    registry_path = tmp_path / "baseline_registry.json"
    _write_json(
        registry_path,
        {
            "version": "1.0",
            "surfaces": [
                {
                    "surface_id": "easy01",
                    "case_id": "easy-01",
                    "ladder_tier": 2,
                    "baseline_type": "pinned_output_root",
                    "active": True,
                    "comparison_mode": "compiled_ingest_report",
                    "pinned_root": "sessions/easy",
                },
                {
                    "surface_id": "medium01",
                    "case_id": "medium-01",
                    "ladder_tier": 3,
                    "baseline_type": "pinned_output_root",
                    "active": True,
                    "comparison_mode": "compiled_ingest_report",
                    "pinned_root": "sessions/medium",
                },
            ],
        },
    )
    config_path = tmp_path / "gate.json"
    _write_json(
        config_path,
        {
            "version": "1.0",
            "gate_id": "gate",
            "baseline_registry_path": "baseline_registry.json",
            "lane_trust": {
                "validator_script_path": "runtime/validate-local-lane.ps1",
                "contract_sources": ["runtime/local-runtime-contract.json"],
                "required_packets": ["lane-trust-packet.json"],
                "pass_verdict": "passed",
            },
            "suites": [
                {"case_id": "easy-01", "baseline_registry_surface_id": "easy01"},
                {"case_id": "medium-01", "baseline_registry_surface_id": "medium01"},
            ],
        },
    )
    loaded = load_gate_config(config_path, repo_root=tmp_path)
    assert Path(loaded["lane_trust"]["validator_script_path"]).parts[-2:] == ("runtime", "validate-local-lane.ps1")
    assert Path(loaded["suites"][0]["baseline_output_root"]).parts[-2:] == ("sessions", "easy")
    assert Path(loaded["baseline_registry"]["path"]).name == "baseline_registry.json"


def test_load_gate_config_rejects_inactive_registry_surface(tmp_path: Path) -> None:
    registry_path = tmp_path / "baseline_registry.json"
    _write_json(
        registry_path,
        {
            "version": "1.0",
            "surfaces": [
                {
                    "surface_id": "easy01",
                    "case_id": "easy-01",
                    "ladder_tier": 2,
                    "baseline_type": "pinned_output_root",
                    "active": False,
                    "comparison_mode": "compiled_ingest_report",
                    "pinned_root": None,
                },
                {
                    "surface_id": "medium01",
                    "case_id": "medium-01",
                    "ladder_tier": 3,
                    "baseline_type": "pinned_output_root",
                    "active": True,
                    "comparison_mode": "compiled_ingest_report",
                    "pinned_root": "sessions/medium",
                },
            ],
        },
    )
    config_path = tmp_path / "gate.json"
    _write_json(
        config_path,
        {
            "version": "1.0",
            "gate_id": "gate",
            "baseline_registry_path": "baseline_registry.json",
            "lane_trust": {
                "validator_script_path": "runtime/validate-local-lane.ps1",
                "contract_sources": ["runtime/local-runtime-contract.json"],
                "required_packets": ["lane-trust-packet.json"],
                "pass_verdict": "passed",
            },
            "suites": [
                {"case_id": "easy-01", "baseline_registry_surface_id": "easy01"},
                {"case_id": "medium-01", "baseline_registry_surface_id": "medium01"},
            ],
        },
    )
    try:
        load_gate_config(config_path, repo_root=tmp_path)
    except ValueError as exc:
        assert str(exc) == "baseline_registry_surface_inactive:easy01"
    else:
        raise AssertionError("expected inactive registry surface failure")


def test_evaluate_lane_trust_output_fails_when_required_packet_missing(tmp_path: Path) -> None:
    lane_root = tmp_path / "lane"
    lane_root.mkdir(parents=True, exist_ok=True)
    _write_json(lane_root / "lane-trust-packet.json", {"canary_verdict": "passed"})
    result = evaluate_lane_trust_output(
        lane_root,
        required_packets=["lane-identity.json", "lane-trust-packet.json"],
        pass_verdict="passed",
    )
    assert result["verdict"] == "fail"
    assert "missing_required_lane_packets" in result["reasons"]


def test_evaluate_lane_trust_output_surfaces_validator_failure_without_duplicate_packet(tmp_path: Path) -> None:
    lane_root = tmp_path / "lane"
    lane_root.mkdir(parents=True, exist_ok=True)
    _write_json(
        lane_root / "lane-validator-failure.json",
        {
            "stage": "proving_lane_canary",
            "failure_kind": "proving_lane_canary_failed",
            "message": "Proving lane canary failed before lane packet completion.",
            "details": {
                "freshness_mode": "observe_only",
                "restart_suppressed": True,
            },
        },
    )
    result = evaluate_lane_trust_output(
        lane_root,
        required_packets=["lane-identity.json", "lane-trust-packet.json"],
        pass_verdict="passed",
    )
    assert result["verdict"] == "fail"
    assert result["reasons"][0] == "proving_lane_canary_failed"
    assert result["reasons"][1] == "missing_required_lane_packets"
    assert result["missing_packets"] == ["lane-identity.json", "lane-trust-packet.json"]
    assert result["validator_failure"]["stage"] == "proving_lane_canary"
    assert result["freshness_mode"] == "observe_only"
    assert result["restart_suppressed"] is True
    assert result["packet_completeness"] == "incomplete"


def test_evaluate_lane_trust_output_surfaces_validator_failure_when_packet_is_complete(tmp_path: Path) -> None:
    lane_root = tmp_path / "lane"
    lane_root.mkdir(parents=True, exist_ok=True)
    _write_json(lane_root / "lane-identity.json", {"contract_version": "trust_contract_v1"})
    _write_json(
        lane_root / "lane-trust-packet.json",
        {
            "canary_verdict": "failed",
            "freshness_mode": "observe_only",
            "api_freshness": {"restart_suppressed": True},
            "bridge_freshness": {"restart_suppressed": True},
        },
    )
    _write_json(
        lane_root / "lane-validator-failure.json",
        {
            "stage": "lane_verdict",
            "failure_kind": "unexpected_canary_verdict",
            "message": "Lane canary verdict did not match expected pass verdict.",
            "details": {
                "freshness_mode": "observe_only",
                "restart_suppressed": True,
            },
        },
    )

    result = evaluate_lane_trust_output(
        lane_root,
        required_packets=["lane-identity.json", "lane-trust-packet.json"],
        pass_verdict="passed",
    )

    assert result["verdict"] == "fail"
    assert result["reasons"][0] == "unexpected_canary_verdict"
    assert result["reasons"][1] == "unexpected_canary_verdict:failed"
    assert result["validator_failure"]["stage"] == "lane_verdict"
    assert result["freshness_mode"] == "observe_only"
    assert result["restart_suppressed"] is True
    assert result["packet_completeness"] == "complete"


def test_evaluate_compiled_suite_artifacts_fails_on_non_ok_run_records(tmp_path: Path) -> None:
    root = _suite_root(tmp_path, "candidate")
    payload = json.loads((root / "compiled-ingest-summary.json").read_text(encoding="utf-8"))
    payload["run_records"][1]["status"] = "error"
    _write_json(root / "compiled-ingest-summary.json", payload)
    result = evaluate_compiled_suite_artifacts("easy-01", root)
    assert result["verdict"] == "fail"
    assert any(reason.startswith("non_ok_run_records:") for reason in result["reasons"])


def test_evaluate_compiled_suite_artifacts_accepts_product_summary_report_case_ids_and_contract_fields(
    tmp_path: Path,
) -> None:
    root = _suite_root(
        tmp_path,
        "candidate",
        summary_case_id="easy-01-product-route",
        report_case_id="easy-01",
        summary_overrides={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
        report_overrides={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
    )

    result = evaluate_compiled_suite_artifacts(
        "easy-01",
        root,
        summary_case_id="easy-01-product-route",
        report_case_id="easy-01",
        required_summary_fields={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
        required_report_fields={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
    )

    assert result["verdict"] == "pass"


def test_compare_compiled_suite_to_baseline_fails_when_product_green_fields_regress(tmp_path: Path) -> None:
    baseline = _suite_root(
        tmp_path,
        "baseline",
        summary_case_id="easy-01-product-route",
        report_case_id="easy-01",
        summary_overrides={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
        report_overrides={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
    )
    candidate = _suite_root(
        tmp_path,
        "candidate",
        summary_case_id="easy-01-product-route",
        report_case_id="easy-01",
        summary_overrides={
            "green_contract_level": "measurement_green",
            "product_green_eligible": False,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": False,
            "blocking_signal": "session_capture",
        },
        report_overrides={
            "green_contract_level": "measurement_green",
            "product_green_eligible": False,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": False,
            "blocking_signal": "session_capture",
        },
    )
    result = compare_compiled_suite_to_baseline(
        case_id="easy-01",
        baseline_output_root=baseline,
        candidate_output_root=candidate,
        accepted_additive_invocables=False,
        summary_case_id="easy-01-product-route",
        report_case_id="easy-01",
        required_summary_fields={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
        required_report_fields={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
    )
    assert result["verdict"] == "fail"
    assert "candidate_artifacts_invalid" in result["reasons"]


def test_compare_compiled_suite_to_baseline_detects_semantic_regression(tmp_path: Path) -> None:
    baseline = _suite_root(tmp_path, "baseline")
    candidate = _suite_root(tmp_path, "candidate")
    report = json.loads((candidate / "compiled-ingest-compare-report.json").read_text(encoding="utf-8"))
    report["semantic_checkpoint_alignment_succeeded"] = False
    _write_json(candidate / "compiled-ingest-compare-report.json", report)
    result = compare_compiled_suite_to_baseline(
        case_id="easy-01",
        baseline_output_root=baseline,
        candidate_output_root=candidate,
        accepted_additive_invocables=False,
    )
    assert result["verdict"] == "fail"
    assert "semantic_checkpoint_alignment_regressed" in result["reasons"]


def test_compare_compiled_suite_to_baseline_accepts_additive_invocables_when_enabled(tmp_path: Path) -> None:
    baseline = _suite_root(tmp_path, "baseline")
    candidate = _suite_root(tmp_path, "candidate")
    report = json.loads((candidate / "compiled-ingest-compare-report.json").read_text(encoding="utf-8"))
    report["per_run"][0]["discovered_invocables"].append("A_EXTRA")
    _write_json(candidate / "compiled-ingest-compare-report.json", report)
    result = compare_compiled_suite_to_baseline(
        case_id="easy-01",
        baseline_output_root=baseline,
        candidate_output_root=candidate,
        accepted_additive_invocables=True,
    )
    assert result["verdict"] == "pass_with_accepted_difference"
    assert result["accepted_differences"]


def test_aggregate_gate_verdict_prefers_fail_then_pass_with_accepted_difference() -> None:
    assert aggregate_gate_verdict([{"verdict": "pass"}, {"verdict": "fail"}]) == "fail"
    assert (
        aggregate_gate_verdict(
            [{"verdict": "pass"}, {"verdict": "pass_with_accepted_difference"}]
        )
        == "pass_with_accepted_difference"
    )


def test_build_medium01_checkpoint_report_marks_first_failure_and_skips_downstream(tmp_path: Path) -> None:
    output_root = tmp_path / "medium01"
    run_one = output_root / "runs" / "01-session_bootstrap"
    run_two = output_root / "runs" / "02-reservation_stage"
    run_one.mkdir(parents=True, exist_ok=True)
    run_two.mkdir(parents=True, exist_ok=True)

    _write_json(
        output_root / "compiled-ingest-summary.json",
        {
            "case_id": "medium-01",
            "run_records": [
                {
                    "target": "session_bootstrap",
                    "status": "ok",
                    "phase": "done",
                    "job_id": "job-1",
                    "duration_sec": 70.0,
                },
                {
                    "target": "reservation_stage",
                    "status": "failed",
                    "phase": "exploring",
                    "job_id": "job-2",
                    "duration_sec": 901.0,
                    "job_terminalization": {
                        "terminalization_kind": "timeout",
                        "reason": {"message": "Runner observed a non-terminal timeout while polling job status."},
                    },
                    "run_authority": {"blocking_reasons": ["terminalization_kind_timeout"]},
                    "failure_domain": "pipeline",
                },
            ],
        },
    )
    _write_json(
        output_root / "compiled-ingest-compare-report.json",
        {
            "case_id": "medium-01",
            "per_run": [
                {
                    "dll_name": "spectrum_session_bootstrap.dll",
                    "run_phase": "done",
                    "job_id": "job-1",
                    "export_contract_match": True,
                    "semantic_checkpoint_match": True,
                    "session_artifacts_present": True,
                },
                {
                    "dll_name": "spectrum_reservation_stage.dll",
                    "run_phase": "exploring",
                    "job_id": "job-2",
                    "export_contract_match": True,
                    "semantic_checkpoint_match": False,
                    "session_artifacts_present": False,
                },
            ],
        },
    )

    report = build_medium01_checkpoint_report(output_root)
    assert report["overall_verdict"] == "fail"
    assert report["first_failed_checkpoint"] == "reservation_stage"
    assert report["passed_checkpoint_count"] == 1
    assert report["total_checkpoint_count"] == 5
    assert report["checkpoints"][1]["failure_kind"] == "explore_timeout"
    assert report["checkpoints"][2]["verdict"] == "skipped"
    assert report["checkpoints"][2]["skipped"] is True


def test_run_regression_gate_fail_fast_stops_after_lane_trust(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "gate.json"
    _write_json(
        config_path,
        {
            "version": "1.0",
            "gate_id": "gate",
            "lane_trust": {
                "validator_script_path": "runtime/validate-local-lane.ps1",
                "contract_sources": [],
                "required_packets": ["lane-trust-packet.json"],
                "pass_verdict": "passed",
            },
            "suites": [
                {"case_id": "easy-01", "baseline_output_root": str(tmp_path / "baseline-easy")},
                {"case_id": "medium-01", "baseline_output_root": str(tmp_path / "baseline-medium")},
            ],
        },
    )

    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.load_gate_config",
        lambda config_path, repo_root: load_gate_config(config_path, repo_root=repo_root),
    )

    class FakeProcess:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1._run_lane_validator",
        lambda script_path, output_root, no_reload=False: FakeProcess(),
    )
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.evaluate_lane_trust_output",
        lambda output_root, required_packets, pass_verdict: {
            "surface": "lane_trust",
            "candidate_output_root": str(output_root),
            "verdict": "fail",
            "reasons": ["lane_failed"],
        },
    )
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.run_spectrum_compiled_easy01",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("easy01 should not run")),
    )
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.run_spectrum_compiled_easy01_product",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("easy01 product should not run")),
    )
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.run_spectrum_compiled_medium01",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("medium01 should not run")),
    )

    exit_code, summary, verdict = run_regression_gate(
        config_path=config_path,
        output_root_arg=str(tmp_path / "out"),
        api_url="http://127.0.0.1:18201",
        api_key="secret",
        bridge_url="http://127.0.0.1:18090",
        bridge_key="bridge-secret",
        surfaces_arg="lane_trust,easy-01,medium-01",
        fail_fast=True,
    )

    assert exit_code == 1
    assert summary["requested_surfaces"] == ["lane_trust", "easy-01", "medium-01"]
    assert summary["active_surfaces"] == ["lane_trust"]
    assert summary["executed_surfaces"] == ["lane_trust"]
    assert verdict["surface_verdicts"] == {"lane_trust": "fail"}


def test_run_regression_gate_easy01_surface_uses_product_runner(monkeypatch, tmp_path: Path) -> None:
    baseline = _suite_root(
        tmp_path,
        "baseline",
        summary_case_id="easy-01-product-route",
        report_case_id="easy-01",
        summary_overrides={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
        report_overrides={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
    )
    config_path = tmp_path / "gate.json"
    _write_json(
        config_path,
        {
            "version": "1.0",
            "gate_id": "gate",
            "lane_trust": {
                "validator_script_path": "runtime/validate-local-lane.ps1",
                "contract_sources": [],
                "required_packets": ["lane-trust-packet.json"],
                "pass_verdict": "passed",
            },
            "suites": [
                {
                    "case_id": "easy-01",
                    "runner_id": "easy01_product",
                    "baseline_output_root": str(baseline),
                    "compare_mode": "compiled_ingest_report_product_contract",
                    "summary_case_id": "easy-01-product-route",
                    "report_case_id": "easy-01",
                    "required_summary_fields": {
                        "green_contract_level": "product_green",
                        "product_green_eligible": True,
                        "route_authority_present": True,
                        "safe_to_compare": True,
                        "semantic_proof_satisfied": True,
                        "authoritative_proving": True,
                        "blocking_signal": "",
                    },
                    "required_report_fields": {
                        "green_contract_level": "product_green",
                        "product_green_eligible": True,
                        "route_authority_present": True,
                        "safe_to_compare": True,
                        "semantic_proof_satisfied": True,
                        "authoritative_proving": True,
                        "blocking_signal": "",
                    },
                },
                {"case_id": "medium-01", "baseline_output_root": str(tmp_path / "unused-medium")},
            ],
        },
    )

    class FakeProcess:
        returncode = 0
        stdout = ""
        stderr = ""

    lane_validator_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1._run_lane_validator",
        lambda script_path, output_root, no_reload=False: lane_validator_calls.append(
            {"script_path": script_path, "output_root": output_root, "no_reload": no_reload}
        )
        or FakeProcess(),
    )
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.evaluate_lane_trust_output",
        lambda output_root, required_packets, pass_verdict: {
            "surface": "lane_trust",
            "candidate_output_root": str(output_root),
            "verdict": "pass",
            "reasons": [],
        },
    )

    def fake_easy01_product(**kwargs):  # noqa: ANN003
        candidate_root = Path(kwargs["output_root"])
        _suite_root(
            tmp_path,
            "candidate-written",
            summary_case_id="easy-01-product-route",
            report_case_id="easy-01",
            summary_overrides={
                "green_contract_level": "product_green",
                "product_green_eligible": True,
                "route_authority_present": True,
                "safe_to_compare": True,
                "semantic_proof_satisfied": True,
                "authoritative_proving": True,
                "blocking_signal": "",
            },
            report_overrides={
                "green_contract_level": "product_green",
                "product_green_eligible": True,
                "route_authority_present": True,
                "safe_to_compare": True,
                "semantic_proof_satisfied": True,
                "authoritative_proving": True,
                "blocking_signal": "",
            },
        )
        for name in (
            "compiled-ingest-summary.json",
            "compiled-ingest-compare-report.json",
            "compiled-ingest.log",
        ):
            source = tmp_path / "candidate-written" / name
            target = candidate_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        return {"output_dir": str(candidate_root)}

    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.run_spectrum_compiled_easy01_product",
        fake_easy01_product,
    )
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.run_spectrum_compiled_medium01",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("medium01 should not run")),
    )

    exit_code, summary, verdict = run_regression_gate(
        config_path=config_path,
        output_root_arg=str(tmp_path / "out"),
        api_url="http://127.0.0.1:18201",
        api_key="secret",
        bridge_url="http://127.0.0.1:18090",
        bridge_key="bridge-secret",
        surfaces_arg="lane_trust,easy-01",
        fail_fast=True,
    )

    easy_result = next(item for item in summary["surface_results"] if item["surface"] == "easy-01")
    assert exit_code == 0
    assert easy_result["compare_mode"] == "compiled_ingest_report_product_contract"
    assert verdict["surface_verdicts"]["easy-01"] == "pass"
    assert lane_validator_calls[0]["no_reload"] is True


def test_run_regression_gate_medium01_surface_uses_product_runner(monkeypatch, tmp_path: Path) -> None:
    baseline = _suite_root(
        tmp_path,
        "baseline-medium",
        summary_case_id="medium-01-product-route",
        report_case_id="medium-01-product-route",
        summary_overrides={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
        report_overrides={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
    )
    config_path = tmp_path / "gate.json"
    _write_json(
        config_path,
        {
            "version": "1.0",
            "gate_id": "gate",
            "lane_trust": {
                "validator_script_path": "runtime/validate-local-lane.ps1",
                "contract_sources": [],
                "required_packets": ["lane-trust-packet.json"],
                "pass_verdict": "passed",
            },
            "suites": [
                {"case_id": "easy-01", "baseline_output_root": str(tmp_path / "unused-easy")},
                {
                    "case_id": "medium-01",
                    "runner_id": "medium01_product",
                    "baseline_output_root": str(baseline),
                    "compare_mode": "compiled_ingest_report_product_contract",
                    "summary_case_id": "medium-01-product-route",
                    "report_case_id": "medium-01-product-route",
                    "required_summary_fields": {
                        "green_contract_level": "product_green",
                        "product_green_eligible": True,
                        "route_authority_present": True,
                        "safe_to_compare": True,
                        "semantic_proof_satisfied": True,
                        "authoritative_proving": True,
                        "blocking_signal": "",
                    },
                    "required_report_fields": {
                        "green_contract_level": "product_green",
                        "product_green_eligible": True,
                        "route_authority_present": True,
                        "safe_to_compare": True,
                        "semantic_proof_satisfied": True,
                        "authoritative_proving": True,
                        "blocking_signal": "",
                    },
                },
            ],
        },
    )

    class FakeProcess:
        returncode = 0
        stdout = ""
        stderr = ""

    lane_validator_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1._run_lane_validator",
        lambda script_path, output_root, no_reload=False: lane_validator_calls.append(
            {"script_path": script_path, "output_root": output_root, "no_reload": no_reload}
        )
        or FakeProcess(),
    )
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.evaluate_lane_trust_output",
        lambda output_root, required_packets, pass_verdict: {
            "surface": "lane_trust",
            "candidate_output_root": str(output_root),
            "verdict": "pass",
            "reasons": [],
        },
    )

    def fake_medium01_product(**kwargs):  # noqa: ANN003
        candidate_root = Path(kwargs["output_root"])
        _suite_root(
            tmp_path,
            "candidate-medium-written",
            summary_case_id="medium-01-product-route",
            report_case_id="medium-01-product-route",
            summary_overrides={
                "green_contract_level": "product_green",
                "product_green_eligible": True,
                "route_authority_present": True,
                "safe_to_compare": True,
                "semantic_proof_satisfied": True,
                "authoritative_proving": True,
                "blocking_signal": "",
            },
            report_overrides={
                "green_contract_level": "product_green",
                "product_green_eligible": True,
                "route_authority_present": True,
                "safe_to_compare": True,
                "semantic_proof_satisfied": True,
                "authoritative_proving": True,
                "blocking_signal": "",
            },
        )
        for name in (
            "compiled-ingest-summary.json",
            "compiled-ingest-compare-report.json",
            "compiled-ingest.log",
        ):
            source = tmp_path / "candidate-medium-written" / name
            target = candidate_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        return {"output_dir": str(candidate_root)}

    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.run_spectrum_compiled_easy01",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("easy01 should not run")),
    )
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.run_spectrum_compiled_medium01_product",
        fake_medium01_product,
    )

    exit_code, summary, verdict = run_regression_gate(
        config_path=config_path,
        output_root_arg=str(tmp_path / "out"),
        api_url="http://127.0.0.1:18201",
        api_key="secret",
        bridge_url="http://127.0.0.1:18090",
        bridge_key="bridge-secret",
        surfaces_arg="lane_trust,medium-01",
        fail_fast=True,
    )

    medium_result = next(item for item in summary["surface_results"] if item["surface"] == "medium-01")
    assert exit_code == 0
    assert medium_result["compare_mode"] == "compiled_ingest_report_product_contract"
    assert verdict["surface_verdicts"]["medium-01"] == "pass"
    assert lane_validator_calls[0]["no_reload"] is True


def test_run_regression_gate_medium02_surface_uses_product_runner(monkeypatch, tmp_path: Path) -> None:
    baseline = _suite_root(
        tmp_path,
        "baseline-medium02",
        summary_case_id="medium-02-product-route",
        report_case_id="medium-02-product-route",
        summary_overrides={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
        report_overrides={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
    )
    config_path = tmp_path / "gate.json"
    _write_json(
        config_path,
        {
            "version": "1.0",
            "gate_id": "gate",
            "lane_trust": {
                "validator_script_path": "runtime/validate-local-lane.ps1",
                "contract_sources": [],
                "required_packets": ["lane-trust-packet.json"],
                "pass_verdict": "passed",
            },
            "suites": [
                {"case_id": "easy-01", "baseline_output_root": str(tmp_path / "unused-easy")},
                {"case_id": "medium-01", "baseline_output_root": str(tmp_path / "unused-medium01")},
                {
                    "case_id": "medium-02",
                    "runner_id": "medium02_product",
                    "baseline_output_root": str(baseline),
                    "compare_mode": "compiled_ingest_report_product_contract",
                    "summary_case_id": "medium-02-product-route",
                    "report_case_id": "medium-02-product-route",
                    "required_summary_fields": {
                        "green_contract_level": "product_green",
                        "product_green_eligible": True,
                        "route_authority_present": True,
                        "safe_to_compare": True,
                        "semantic_proof_satisfied": True,
                        "authoritative_proving": True,
                        "blocking_signal": "",
                    },
                    "required_report_fields": {
                        "green_contract_level": "product_green",
                        "product_green_eligible": True,
                        "route_authority_present": True,
                        "safe_to_compare": True,
                        "semantic_proof_satisfied": True,
                        "authoritative_proving": True,
                        "blocking_signal": "",
                    },
                },
            ],
        },
    )

    class FakeProcess:
        returncode = 0
        stdout = ""
        stderr = ""

    lane_validator_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1._run_lane_validator",
        lambda script_path, output_root, no_reload=False: lane_validator_calls.append(
            {"script_path": script_path, "output_root": output_root, "no_reload": no_reload}
        )
        or FakeProcess(),
    )
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.evaluate_lane_trust_output",
        lambda output_root, required_packets, pass_verdict: {
            "surface": "lane_trust",
            "candidate_output_root": str(output_root),
            "verdict": "pass",
            "reasons": [],
        },
    )

    def fake_medium02_product(**kwargs):  # noqa: ANN003
        candidate_root = Path(kwargs["output_root"])
        _suite_root(
            tmp_path,
            "candidate-medium02-written",
            summary_case_id="medium-02-product-route",
            report_case_id="medium-02-product-route",
            summary_overrides={
                "green_contract_level": "product_green",
                "product_green_eligible": True,
                "route_authority_present": True,
                "safe_to_compare": True,
                "semantic_proof_satisfied": True,
                "authoritative_proving": True,
                "blocking_signal": "",
            },
            report_overrides={
                "green_contract_level": "product_green",
                "product_green_eligible": True,
                "route_authority_present": True,
                "safe_to_compare": True,
                "semantic_proof_satisfied": True,
                "authoritative_proving": True,
                "blocking_signal": "",
            },
        )
        for name in (
            "compiled-ingest-summary.json",
            "compiled-ingest-compare-report.json",
            "compiled-ingest.log",
        ):
            source = tmp_path / "candidate-medium02-written" / name
            target = candidate_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        return {"output_dir": str(candidate_root)}

    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.run_spectrum_compiled_easy01",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("easy01 should not run")),
    )
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.run_spectrum_compiled_medium01",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("medium01 should not run")),
    )
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.run_spectrum_compiled_medium02_product",
        fake_medium02_product,
    )

    exit_code, summary, verdict = run_regression_gate(
        config_path=config_path,
        output_root_arg=str(tmp_path / "out"),
        api_url="http://127.0.0.1:18201",
        api_key="secret",
        bridge_url="http://127.0.0.1:18090",
        bridge_key="bridge-secret",
        surfaces_arg="lane_trust,medium-02",
        fail_fast=True,
    )

    medium_result = next(item for item in summary["surface_results"] if item["surface"] == "medium-02")
    assert exit_code == 0
    assert medium_result["compare_mode"] == "compiled_ingest_report_product_contract"
    assert verdict["surface_verdicts"]["medium-02"] == "pass"
    assert lane_validator_calls[0]["no_reload"] is True


def test_run_regression_gate_hard01_surface_uses_product_runner(monkeypatch, tmp_path: Path) -> None:
    baseline = _suite_root(
        tmp_path,
        "baseline-hard01",
        summary_case_id="hard-01-product-route",
        report_case_id="hard-01-product-route",
        summary_overrides={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
        report_overrides={
            "green_contract_level": "product_green",
            "product_green_eligible": True,
            "route_authority_present": True,
            "safe_to_compare": True,
            "semantic_proof_satisfied": True,
            "authoritative_proving": True,
            "blocking_signal": "",
        },
    )
    config_path = tmp_path / "gate.json"
    _write_json(
        config_path,
        {
            "version": "1.0",
            "gate_id": "gate",
            "lane_trust": {
                "validator_script_path": "runtime/validate-local-lane.ps1",
                "contract_sources": [],
                "required_packets": ["lane-trust-packet.json"],
                "pass_verdict": "passed",
            },
            "suites": [
                {"case_id": "easy-01", "baseline_output_root": str(tmp_path / "unused-easy")},
                {"case_id": "medium-01", "baseline_output_root": str(tmp_path / "unused-medium01")},
                {"case_id": "medium-02", "baseline_output_root": str(tmp_path / "unused-medium02")},
                {
                    "case_id": "hard-01",
                    "runner_id": "hard01_product",
                    "baseline_output_root": str(baseline),
                    "compare_mode": "compiled_ingest_report_product_contract",
                    "summary_case_id": "hard-01-product-route",
                    "report_case_id": "hard-01-product-route",
                    "required_summary_fields": {
                        "green_contract_level": "product_green",
                        "product_green_eligible": True,
                        "route_authority_present": True,
                        "safe_to_compare": True,
                        "semantic_proof_satisfied": True,
                        "authoritative_proving": True,
                        "blocking_signal": "",
                    },
                    "required_report_fields": {
                        "green_contract_level": "product_green",
                        "product_green_eligible": True,
                        "route_authority_present": True,
                        "safe_to_compare": True,
                        "semantic_proof_satisfied": True,
                        "authoritative_proving": True,
                        "blocking_signal": "",
                    },
                },
            ],
        },
    )

    class FakeProcess:
        returncode = 0
        stdout = ""
        stderr = ""

    lane_validator_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1._run_lane_validator",
        lambda script_path, output_root, no_reload=False: lane_validator_calls.append(
            {"script_path": script_path, "output_root": output_root, "no_reload": no_reload}
        )
        or FakeProcess(),
    )
    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.evaluate_lane_trust_output",
        lambda output_root, required_packets, pass_verdict: {
            "surface": "lane_trust",
            "candidate_output_root": str(output_root),
            "verdict": "pass",
            "reasons": [],
        },
    )

    def fake_hard01_product(**kwargs):  # noqa: ANN003
        assert kwargs["stop_after_first_failure"] is True
        candidate_root = Path(kwargs["output_root"])
        written = _suite_root(
            tmp_path,
            "candidate-hard01-written",
            summary_case_id="hard-01-product-route",
            report_case_id="hard-01-product-route",
            summary_overrides={
                "green_contract_level": "product_green",
                "product_green_eligible": True,
                "route_authority_present": True,
                "safe_to_compare": True,
                "semantic_proof_satisfied": True,
                "authoritative_proving": True,
                "blocking_signal": "",
            },
            report_overrides={
                "green_contract_level": "product_green",
                "product_green_eligible": True,
                "route_authority_present": True,
                "safe_to_compare": True,
                "semantic_proof_satisfied": True,
                "authoritative_proving": True,
                "blocking_signal": "",
            },
        )
        for name in (
            "compiled-ingest-summary.json",
            "compiled-ingest-compare-report.json",
            "compiled-ingest.log",
        ):
            source = written / name
            target = candidate_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        return {"output_dir": str(candidate_root)}

    monkeypatch.setattr(
        "scripts.regression.run_regression_gate_v1.run_spectrum_compiled_hard01_product",
        fake_hard01_product,
    )

    exit_code, summary, verdict = run_regression_gate(
        config_path=config_path,
        output_root_arg=str(tmp_path / "out"),
        api_url="http://127.0.0.1:18201",
        api_key="secret",
        bridge_url="http://127.0.0.1:18090",
        bridge_key="bridge-secret",
        surfaces_arg="lane_trust,hard-01",
        fail_fast=True,
    )

    hard_result = next(item for item in summary["surface_results"] if item["surface"] == "hard-01")
    assert exit_code == 0
    assert hard_result["compare_mode"] == "compiled_ingest_report_product_contract"
    assert verdict["surface_verdicts"]["hard-01"] == "pass"
    assert lane_validator_calls[0]["no_reload"] is True
