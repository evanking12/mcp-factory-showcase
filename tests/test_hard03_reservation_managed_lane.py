from __future__ import annotations

import json
from pathlib import Path

import scripts.regression.replay_hard03_reservation_managed_lane as managed


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _source_root(tmp_path: Path, dll_path: Path, target_name: str = "reservation_stage") -> Path:
    source = tmp_path / "source"
    ordinal = {
        "reservation_stage": "02",
        "dispatch_preview": "03",
        "fee_quote": "04",
        "attestation_stage": "05",
        "invoice_sync": "06",
    }.get(target_name, "02")
    target = source / "runs" / f"{ordinal}-{target_name}"
    _write_json(
        target / "run_result.json",
        {
            "target": target_name,
            "target_dll": str(dll_path),
            "variant": "compiled_hard03",
            "explore_settings": {
                "analysis_profile": "strict_dll",
                "ghidra_required": True,
                "selected_invocable_names": ["SP_IssueReleaseHold"],
            },
        },
    )
    _write_json(
        target / "measurement-terminalization.json",
        {"reason_code": "analyzer_timeout"},
    )
    _write_json(
        target / "analyzer-runtime-authority.json",
        {
            "phase_history": [
                {"phase": "worker_before_discovery"},
                {"phase": "discovery_child_wait_start"},
            ],
            "child_runtime_diagnostic": {
                "phase": "bootstrap_main_returned",
                "last_observation": {"returncode": 0},
            },
        },
    )
    return source


def test_missing_source_root_fails_closed(tmp_path: Path) -> None:
    result = managed.replay_hard03_reservation_managed_lane(
        source_proof_root=tmp_path / "missing",
        output_root=tmp_path / "out",
    )

    assert result["classification"] == "trusted_predecessor_boundary_unavailable"
    assert result["claim_ceiling"] == "managed_lane_target_local_only"
    assert result["product_green_claimed"] is False


def test_missing_dll_fails_closed_without_mutating_source(tmp_path: Path) -> None:
    source = _source_root(tmp_path, tmp_path / "missing.dll")
    before = sorted(str(path.relative_to(source)) for path in source.rglob("*"))

    result = managed.replay_hard03_reservation_managed_lane(
        source_proof_root=source,
        output_root=tmp_path / "out",
    )

    after = sorted(str(path.relative_to(source)) for path in source.rglob("*"))
    assert after == before
    assert result["classification"] == "trusted_predecessor_boundary_unavailable"
    assert result["source_root_mutated"] is False
    assert result["product_green_claimed"] is False


def test_managed_lane_replay_classifies_recovered_authority(monkeypatch, tmp_path: Path) -> None:
    dll_path = tmp_path / "reservation.dll"
    dll_path.write_bytes(b"dll")
    source = _source_root(tmp_path, dll_path)
    before = sorted(str(path.relative_to(source)) for path in source.rglob("*"))
    monkeypatch.setattr(managed, "resolve_api_url", lambda _url, _key, **_kwargs: ("http://api", "ok", "test"))
    monkeypatch.setattr(managed, "ApiClient", lambda _url, _key: object())
    monkeypatch.setattr(
        managed,
        "summarize_product_proof_artifacts",
        lambda proof_root, target, output: _write_json(output, {"diagnostic_only": True}) or {},
    )

    def fake_run_one(_client, _repo_root, run_dir, *_args, **_kwargs):
        _write_json(
            run_dir / "analyzer-runtime-authority.json",
            {
                "phase_history": [
                    {"phase": "worker_before_discovery"},
                    {"phase": "run_discovery_entered"},
                    {"phase": "discovery_child_wait_start"},
                    {"phase": "discovery_child_wait_returned"},
                    {"phase": "discovery_child_returncode_observed"},
                    {"phase": "discovery_output_scan_started"},
                    {"phase": "discovery_output_scan_completed"},
                ],
                "child_returncode": 0,
                "output_file_count": 1,
            },
        )
        _write_json(run_dir / "measurement-terminalization.json", {"reason_code": ""})
        return {"job_id": "job-managed", "status": "failed", "phase": "analyze"}

    monkeypatch.setattr(managed, "run_one", fake_run_one)

    result = managed.replay_hard03_reservation_managed_lane(
        source_proof_root=source,
        output_root=tmp_path / "out",
    )

    after = sorted(str(path.relative_to(source)) for path in source.rglob("*"))
    assert after == before
    assert result["classification"] == "managed_lane_parent_wait_authority_recovered"
    assert result["parent_wait_returned"] is True
    assert result["returncode_observed"] is True
    assert result["output_scan_completed"] is True
    assert result["claim_ceiling"] == "managed_lane_target_local_only"
    assert result["product_green_claimed"] is False
    assert result["source_root_mutated"] is False


def test_managed_lane_target_replays_dispatch_preview(monkeypatch, tmp_path: Path) -> None:
    dll_path = tmp_path / "dispatch.dll"
    dll_path.write_bytes(b"dll")
    source = _source_root(tmp_path, dll_path, "dispatch_preview")
    monkeypatch.setattr(managed, "resolve_api_url", lambda _url, _key, **_kwargs: ("http://api", "ok", "test"))
    monkeypatch.setattr(managed, "ApiClient", lambda _url, _key: object())
    monkeypatch.setattr(
        managed,
        "summarize_product_proof_artifacts",
        lambda proof_root, target, output: _write_json(output, {"diagnostic_only": True}) or {},
    )

    def fake_run_one(_client, _repo_root, run_dir, _api_url, _api_key, target_name, _dll, _variant, settings, *_args):
        assert target_name == "dispatch_preview"
        assert run_dir.name == "03-dispatch_preview"
        assert settings["skip_cache"] is True
        assert settings["chain_step_target"] == "dispatch_preview"
        assert settings["lane_id"] == "hard03-managed-lane-replay-dispatch_preview"
        _write_json(
            run_dir / "analyzer-runtime-authority.json",
            {
                "phase_history": [
                    {"phase": "worker_before_discovery"},
                    {"phase": "run_discovery_entered"},
                    {"phase": "discovery_child_wait_start"},
                    {"phase": "discovery_child_wait_returned"},
                    {"phase": "discovery_child_returncode_observed"},
                    {"phase": "discovery_output_scan_completed"},
                ],
                "child_returncode": 0,
                "output_file_count": 1,
            },
        )
        return {"job_id": "job-managed", "status": "failed", "phase": "analyze"}

    monkeypatch.setattr(managed, "run_one", fake_run_one)

    result = managed.replay_hard03_managed_lane_target(
        source_proof_root=source,
        output_root=tmp_path / "out",
        target="dispatch_preview",
    )

    assert result["target"] == "dispatch_preview"
    assert result["classification"] == "managed_lane_parent_wait_authority_recovered"
    assert result["claim_ceiling"] == "managed_lane_target_local_only"
    assert result["product_green_claimed"] is False


def test_managed_lane_target_replays_fee_quote(monkeypatch, tmp_path: Path) -> None:
    dll_path = tmp_path / "fee.dll"
    dll_path.write_bytes(b"dll")
    source = _source_root(tmp_path, dll_path, "fee_quote")
    monkeypatch.setattr(managed, "resolve_api_url", lambda _url, _key, **_kwargs: ("http://api", "ok", "test"))
    monkeypatch.setattr(managed, "ApiClient", lambda _url, _key: object())
    monkeypatch.setattr(
        managed,
        "summarize_product_proof_artifacts",
        lambda proof_root, target, output: _write_json(output, {"diagnostic_only": True}) or {},
    )

    def fake_run_one(_client, _repo_root, run_dir, _api_url, _api_key, target_name, _dll, _variant, settings, *_args):
        assert target_name == "fee_quote"
        assert run_dir.name == "04-fee_quote"
        assert settings["skip_cache"] is True
        assert settings["chain_step_target"] == "fee_quote"
        assert settings["lane_id"] == "hard03-managed-lane-replay-fee_quote"
        assert _args[4] == "compact"
        _write_json(
            run_dir / "analyzer-runtime-authority.json",
            {
                "phase_history": [
                    {"phase": "worker_before_discovery"},
                    {"phase": "run_discovery_entered"},
                    {"phase": "discovery_child_wait_returned"},
                    {"phase": "discovery_child_returncode_observed"},
                    {"phase": "discovery_output_scan_completed"},
                ],
                "child_returncode": 0,
                "output_file_count": 1,
            },
        )
        return {"job_id": "fee-job"}

    monkeypatch.setattr(managed, "run_one", fake_run_one)

    result = managed.replay_hard03_managed_lane_target(
        source_proof_root=source,
        output_root=tmp_path / "out",
        target="fee_quote",
    )

    assert result["target"] == "fee_quote"
    assert result["classification"] == "managed_lane_parent_wait_authority_recovered"
    assert result["claim_ceiling"] == "managed_lane_target_local_only"
    assert result["product_green_claimed"] is False


def test_managed_lane_target_replays_attestation_stage(monkeypatch, tmp_path: Path) -> None:
    dll_path = tmp_path / "attestation.dll"
    dll_path.write_bytes(b"dll")
    source = _source_root(tmp_path, dll_path, "attestation_stage")
    monkeypatch.setattr(managed, "resolve_api_url", lambda _url, _key, **_kwargs: ("http://api", "ok", "test"))
    monkeypatch.setattr(managed, "ApiClient", lambda _url, _key: object())
    monkeypatch.setattr(
        managed,
        "summarize_product_proof_artifacts",
        lambda proof_root, target, output: _write_json(output, {"diagnostic_only": True}) or {},
    )

    def fake_run_one(_client, _repo_root, run_dir, _api_url, _api_key, target_name, _dll, _variant, settings, *_args):
        assert target_name == "attestation_stage"
        assert run_dir.name == "05-attestation_stage"
        assert settings["skip_cache"] is True
        assert settings["chain_step_target"] == "attestation_stage"
        assert settings["lane_id"] == "hard03-managed-lane-replay-attestation_stage"
        _write_json(
            run_dir / "analyzer-runtime-authority.json",
            {
                "phase_history": [
                    {"phase": "worker_before_discovery"},
                    {"phase": "run_discovery_entered"},
                    {"phase": "discovery_child_wait_returned"},
                    {"phase": "discovery_child_returncode_observed"},
                    {"phase": "discovery_output_scan_completed"},
                ],
                "child_returncode": 0,
                "output_file_count": 1,
            },
        )
        return {"job_id": "attestation-job"}

    monkeypatch.setattr(managed, "run_one", fake_run_one)

    result = managed.replay_hard03_managed_lane_target(
        source_proof_root=source,
        output_root=tmp_path / "out",
        target="attestation_stage",
    )

    assert result["target"] == "attestation_stage"
    assert result["classification"] == "managed_lane_parent_wait_authority_recovered"
    assert result["claim_ceiling"] == "managed_lane_target_local_only"
    assert result["product_green_claimed"] is False


def test_managed_lane_target_replays_invoice_sync(monkeypatch, tmp_path: Path) -> None:
    dll_path = tmp_path / "invoice.dll"
    dll_path.write_bytes(b"dll")
    source = _source_root(tmp_path, dll_path, "invoice_sync")
    monkeypatch.setattr(managed, "resolve_api_url", lambda _url, _key, **_kwargs: ("http://api", "ok", "test"))
    monkeypatch.setattr(managed, "ApiClient", lambda _url, _key: object())
    monkeypatch.setattr(
        managed,
        "summarize_product_proof_artifacts",
        lambda proof_root, target, output: _write_json(output, {"diagnostic_only": True}) or {},
    )

    def fake_run_one(_client, _repo_root, run_dir, _api_url, _api_key, target_name, _dll, _variant, settings, *_args):
        assert target_name == "invoice_sync"
        assert run_dir.name == "06-invoice_sync"
        assert settings["skip_cache"] is True
        assert settings["chain_step_target"] == "invoice_sync"
        assert settings["lane_id"] == "hard03-managed-lane-replay-invoice_sync"
        _write_json(
            run_dir / "analyzer-runtime-authority.json",
            {
                "phase_history": [
                    {"phase": "worker_before_discovery"},
                    {"phase": "run_discovery_entered"},
                    {"phase": "discovery_child_wait_returned"},
                    {"phase": "discovery_child_returncode_observed"},
                    {"phase": "discovery_output_scan_completed"},
                ],
                "child_returncode": 0,
                "output_file_count": 1,
            },
        )
        return {"job_id": "invoice-job"}

    monkeypatch.setattr(managed, "run_one", fake_run_one)

    result = managed.replay_hard03_managed_lane_target(
        source_proof_root=source,
        output_root=tmp_path / "out",
        target="invoice_sync",
    )

    assert result["target"] == "invoice_sync"
    assert result["classification"] == "managed_lane_parent_wait_authority_recovered"
    assert result["claim_ceiling"] == "managed_lane_target_local_only"
    assert result["product_green_claimed"] is False


def test_managed_lane_replay_preserves_wait_return_missing(monkeypatch, tmp_path: Path) -> None:
    dll_path = tmp_path / "reservation.dll"
    dll_path.write_bytes(b"dll")
    source = _source_root(tmp_path, dll_path)
    monkeypatch.setattr(managed, "resolve_api_url", lambda _url, _key, **_kwargs: ("http://api", "ok", "test"))
    monkeypatch.setattr(managed, "ApiClient", lambda _url, _key: object())
    monkeypatch.setattr(
        managed,
        "summarize_product_proof_artifacts",
        lambda proof_root, target, output: _write_json(output, {"diagnostic_only": True}) or {},
    )

    def fake_run_one(_client, _repo_root, run_dir, *_args, **_kwargs):
        _write_json(
            run_dir / "analyzer-runtime-authority.json",
            {
                "phase_history": [
                    {"phase": "worker_before_discovery"},
                    {"phase": "run_discovery_entered"},
                    {"phase": "discovery_child_wait_start"},
                ],
                "child_runtime_diagnostic": {
                    "phase": "bootstrap_main_returned",
                    "last_observation": {"returncode": 0},
                },
            },
        )
        _write_json(run_dir / "measurement-terminalization.json", {"reason_code": "analyzer_timeout"})
        return {"job_id": "job-managed", "status": "failed", "phase": "analyze"}

    monkeypatch.setattr(managed, "run_one", fake_run_one)

    result = managed.replay_hard03_reservation_managed_lane(
        source_proof_root=source,
        output_root=tmp_path / "out",
    )

    assert result["classification"] == "child_wrapper_wait_return_missing"
    assert result["parent_wait_started"] is True
    assert result["parent_wait_returned"] is False
    assert result["product_green_claimed"] is False


def test_managed_lane_replay_classifies_pre_discovery_block(monkeypatch, tmp_path: Path) -> None:
    dll_path = tmp_path / "reservation.dll"
    dll_path.write_bytes(b"dll")
    source = _source_root(tmp_path, dll_path)
    monkeypatch.setattr(managed, "resolve_api_url", lambda _url, _key, **_kwargs: ("http://api", "ok", "test"))
    monkeypatch.setattr(managed, "ApiClient", lambda _url, _key: object())
    monkeypatch.setattr(
        managed,
        "summarize_product_proof_artifacts",
        lambda proof_root, target, output: _write_json(output, {"diagnostic_only": True}) or {},
    )

    def fake_run_one(_client, _repo_root, run_dir, *_args, **_kwargs):
        _write_json(
            run_dir / "analyzer-runtime-authority.json",
            {"phase_history": [{"phase": "worker_progress_30_persisted"}]},
        )
        return {"job_id": "job-managed", "status": "failed", "phase": "analyze"}

    monkeypatch.setattr(managed, "run_one", fake_run_one)

    result = managed.replay_hard03_reservation_managed_lane(
        source_proof_root=source,
        output_root=tmp_path / "out",
    )

    assert result["classification"] == "managed_lane_pre_discovery_blocked"
    assert result["product_green_claimed"] is False
