from __future__ import annotations

from scripts.ops.measurement_control_plane import (
    DEFAULT_DEPENDENCY_POLICY,
    apply_control_plane_to_run_record,
    build_bridge_candidate_registry_packet,
    build_bridge_candidates_from_config,
    build_hard01_baseline_readiness_packet,
    build_measurement_control_plane_packet,
    build_single_bridge_candidate_registry_packet,
    bridge_stream_health_from_run_record,
    hard_family_bridge_stream_health_for_target,
    write_control_plane_blocked_result,
)


def _bridge_identity() -> dict:
    return {
        "component": "bridge",
        "git_sha": "abc123",
        "capabilities": ["analyze", "execute"],
    }


def _bridge_readiness(**overrides) -> dict:
    payload = {
        "component": "bridge",
        "ready": True,
        "capabilities": ["analyze", "execute"],
        "blocking_reasons": [],
    }
    payload.update(overrides)
    return payload


def _lane_readiness(**overrides) -> dict:
    payload = {
        "ready": True,
        "lane_comparable": True,
        "blocking_reasons": [],
    }
    payload.update(overrides)
    return payload


def _bridge_stream_health(**overrides) -> dict:
    payload = {
        "source": "test",
        "status": "coherent",
        "reason_code": "bridge_stream_health_coherent",
        "stream_health_known": True,
        "recent_signals": [],
    }
    payload.update(overrides)
    return payload


def test_green_lane_when_bridge_and_lane_are_comparable() -> None:
    packet = build_measurement_control_plane_packet(
        target="session_bootstrap",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        lane_readiness=_lane_readiness(),
        bridge_url="http://127.0.0.1:8090",
        created_at="2026-04-22T00:00:00+00:00",
    )

    assert packet["light"] == "green"
    assert packet["source"] == "measurement_control_plane"
    assert packet["reason_code"] == "green_lane_admitted"
    assert packet["safe_to_run"] is True
    assert packet["safe_to_compare"] is True
    assert packet["semantic_proof_satisfied"] is False
    assert packet["selected_bridge"]["url"] == "http://127.0.0.1:8090"
    assert packet["lease"]["granted"] is True


def test_green_lane_when_bridge_stream_health_is_coherent() -> None:
    packet = build_measurement_control_plane_packet(
        target="session_bootstrap",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        bridge_stream_health=_bridge_stream_health(),
        lane_readiness=_lane_readiness(),
    )

    assert packet["light"] == "green"
    assert packet["reason_code"] == "green_lane_admitted"
    assert packet["safe_to_compare"] is True
    assert packet["inputs"]["bridge_stream_health"]["reason_code"] == "bridge_stream_health_coherent"


def test_yellow_lane_when_bridge_stream_health_is_unproven() -> None:
    packet = build_measurement_control_plane_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        bridge_stream_health=_bridge_stream_health(
            status="unproven",
            reason_code="bridge_stream_health_unproven",
            stream_health_known=False,
        ),
        lane_readiness=_lane_readiness(),
    )

    assert packet["light"] == "yellow"
    assert packet["reason_code"] == "bridge_stream_health_unproven"
    assert packet["safe_to_run"] is True
    assert packet["safe_to_compare"] is False
    assert packet["semantic_proof_satisfied"] is False


def test_yellow_lane_when_bridge_recently_had_no_heartbeat_stall() -> None:
    packet = build_measurement_control_plane_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        bridge_stream_health=_bridge_stream_health(
            status="recent_stall",
            reason_code="bridge_recent_no_heartbeat_stall",
            recent_signals=["bridge_stream_no_heartbeat"],
        ),
        lane_readiness=_lane_readiness(),
    )

    assert packet["light"] == "yellow"
    assert packet["reason_code"] == "bridge_recent_no_heartbeat_stall"
    assert packet["safe_to_run"] is True
    assert packet["safe_to_compare"] is False
    assert "bridge_stream_no_heartbeat" in packet["blocking_reasons"]


def test_hard_family_reservation_stage_does_not_force_static_stall() -> None:
    health = hard_family_bridge_stream_health_for_target("reservation_stage", "strict_dll")

    assert health["status"] == "historical_signal_only"
    assert health["reason_code"] == "bridge_stream_health_historical_context"
    assert health["current_run_authority"] is False
    assert health["recent_signals"] == []
    assert "bridge_stream_no_heartbeat" in health["historical_signals"]


def test_current_run_decision_bearing_authority_clears_historical_bridge_stall() -> None:
    health = bridge_stream_health_from_run_record(
        {
            "phase": "done",
            "authoritative_proving": True,
            "job_terminalization": {
                "terminal": True,
                "terminalization_kind": "done",
            },
            "run_authority": {
                "authority_level": "decision_bearing",
                "authoritative_proving": True,
            },
        }
    )

    assert health["status"] == "coherent"
    assert health["reason_code"] == "bridge_stream_health_coherent"
    assert health["current_run_authority"] is True
    assert health["current_run_decision_bearing"] is True


def test_terminal_current_run_without_decision_bearing_still_clears_bridge_health() -> None:
    health = bridge_stream_health_from_run_record(
        {
            "phase": "done",
            "authoritative_proving": False,
            "job_terminalization": {
                "terminal": True,
                "terminalization_kind": "done",
            },
            "run_authority": {
                "authority_level": "non_authoritative",
                "authoritative_proving": False,
            },
        }
    )

    assert health["status"] == "coherent"
    assert health["reason_code"] == "bridge_stream_health_coherent"
    assert health["current_run_authority"] is True
    assert health["current_run_decision_bearing"] is False


def test_current_run_bridge_no_heartbeat_authority_still_fails_closed() -> None:
    health = bridge_stream_health_from_run_record(
        {
            "phase": "analyze",
            "failure_domain": "bridge_stream_no_heartbeat",
            "analyzer_authority": {
                "bridge_analyzer_authority": {
                    "reason_code": "bridge_stream_no_heartbeat",
                    "blocking_reasons": ["bridge_stream_no_heartbeat"],
                }
            },
        }
    )

    assert health["status"] == "recent_stall"
    assert health["reason_code"] == "bridge_recent_no_heartbeat_stall"
    assert health["current_run_authority"] is True
    assert "bridge_stream_no_heartbeat" in health["recent_signals"]


def test_missing_current_run_authority_remains_unproven() -> None:
    health = bridge_stream_health_from_run_record({"phase": "analyze"})

    assert health["status"] == "unproven"
    assert health["reason_code"] == "bridge_stream_health_unproven"
    assert health["current_run_authority"] is False


def test_current_run_terminalization_timeout_is_not_reclassified_as_bridge_unproven() -> None:
    health = bridge_stream_health_from_run_record(
        {
            "phase": "exploring",
            "job_terminalization": {
                "terminal": True,
                "terminalization_kind": "timeout",
                "reason": {"code": "runner_observed_nonterminal_timeout"},
            },
        }
    )

    assert health["source"] == "current_run_terminalization"
    assert health["status"] == "terminalization_blocked"
    assert health["reason_code"] == "runner_observed_nonterminal_timeout"
    assert health["current_run_authority"] is True


def test_control_plane_preserves_current_run_terminalization_reason() -> None:
    packet = build_measurement_control_plane_packet(
        target="invoice_sync",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        bridge_stream_health=_bridge_stream_health(
            source="current_run_terminalization",
            status="terminalization_blocked",
            reason_code="runner_observed_nonterminal_timeout",
            stream_health_known=False,
        ),
        lane_readiness=_lane_readiness(),
    )

    assert packet["light"] == "yellow"
    assert packet["reason_code"] == "runner_observed_nonterminal_timeout"
    assert packet["safe_to_run"] is True
    assert packet["safe_to_compare"] is False
    assert "runner_observed_nonterminal_timeout" in packet["blocking_reasons"]


def test_yellow_lane_when_diagnostics_are_allowed_but_comparability_is_false() -> None:
    packet = build_measurement_control_plane_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        bridge_stream_health=_bridge_stream_health(),
        lane_readiness=_lane_readiness(
            ready=False,
            lane_comparable=False,
            blocking_reasons=["runner_bridge_git_sha_mismatch"],
        ),
        diagnostic_allowed=True,
    )

    assert packet["light"] == "yellow"
    assert packet["reason_code"] == "diagnostic_only_lane"
    assert packet["safe_to_run"] is True
    assert packet["safe_to_compare"] is False
    assert packet["semantic_proof_satisfied"] is False
    assert "runner_bridge_git_sha_mismatch" in packet["blocking_reasons"]


def test_red_lane_when_bridge_readiness_is_missing() -> None:
    packet = build_measurement_control_plane_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        bridge_identity=_bridge_identity(),
        bridge_readiness=None,
        lane_readiness=_lane_readiness(),
    )

    assert packet["light"] == "red"
    assert packet["reason_code"] == "bridge_readiness_unavailable"
    assert packet["safe_to_run"] is False
    assert packet["safe_to_compare"] is False
    assert packet["lease"]["granted"] is False


def test_red_lane_when_no_green_bridge_is_available() -> None:
    packet = build_measurement_control_plane_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        lane_readiness=_lane_readiness(),
        no_green_bridge_available=True,
    )

    assert packet["light"] == "red"
    assert packet["reason_code"] == "no_green_bridge_available"
    assert packet["safe_to_run"] is False
    assert packet["safe_to_compare"] is False


def test_red_lane_when_required_bridge_capability_is_missing() -> None:
    packet = build_measurement_control_plane_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        required_capabilities=["ghidra"],
        bridge_identity={"component": "bridge", "capabilities": ["analyze"]},
        bridge_readiness=_bridge_readiness(capabilities=["analyze"]),
        lane_readiness=_lane_readiness(),
    )

    assert packet["light"] == "red"
    assert packet["reason_code"] == "bridge_capability_mismatch"
    assert "missing_capability:ghidra" in packet["blocking_reasons"]
    assert packet["semantic_proof_satisfied"] is False


def test_quarantined_bridge_blocks_scheduling() -> None:
    packet = build_measurement_control_plane_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        bridge_stream_health=_bridge_stream_health(
            status="coherent",
            reason_code="bridge_stream_health_coherent",
        ),
        lane_readiness=_lane_readiness(),
        bridge_quarantined=True,
        quarantine_reason="bridge_stream_no_heartbeat",
    )

    assert packet["light"] == "quarantined"
    assert packet["reason_code"] == "bridge_lane_quarantined"
    assert packet["safe_to_run"] is False
    assert packet["safe_to_compare"] is False
    assert packet["semantic_proof_satisfied"] is False
    assert packet["blocking_reasons"] == ["bridge_stream_no_heartbeat"]


def test_dependency_policy_preserves_non_comparable_chain_stop() -> None:
    packet = build_measurement_control_plane_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        bridge_readiness=None,
        lane_readiness=_lane_readiness(),
    )

    assert packet["dependency_policy"] == DEFAULT_DEPENDENCY_POLICY
    assert packet["dependency_policy"] == "stop_dependent_chain_on_non_comparable_target"


def test_blocked_control_plane_writes_non_comparable_packets(tmp_path) -> None:
    packet = build_measurement_control_plane_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        required_capabilities=["ghidra"],
        bridge_identity={"component": "bridge", "capabilities": ["analyze"]},
        bridge_readiness=_bridge_readiness(capabilities=["analyze"]),
        lane_readiness=_lane_readiness(),
    )

    record = write_control_plane_blocked_result(
        run_dir=tmp_path,
        control_plane=packet,
        dll_name="spectrum_reservation_stage.dll",
        dll_path=str(tmp_path / "spectrum_reservation_stage.dll"),
        binary_hash="abc",
        entry_surface="upload",
    )

    assert record["status"] == "failed"
    assert record["phase"] == "control_plane_admission"
    assert record["authoritative_proving"] is False
    assert record["run_authority"]["authority_level"] == "non_authoritative"
    assert record["measurement_terminalization"]["safe_to_compare"] is False
    assert (tmp_path / "measurement-terminalization.json").exists()
    assert (tmp_path / "run-authority.json").exists()
    assert (tmp_path / "run_result.json").exists()


def test_yellow_control_plane_forces_diagnostic_record_non_comparable(tmp_path) -> None:
    packet = build_measurement_control_plane_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        bridge_stream_health=_bridge_stream_health(
            status="recent_stall",
            reason_code="bridge_recent_no_heartbeat_stall",
            recent_signals=["bridge_stream_no_heartbeat"],
        ),
        lane_readiness=_lane_readiness(),
    )
    raw_record = {
        "run_id": "run-1",
        "job_id": "job-1",
        "status": "ok",
        "phase": "done",
        "valid_run": True,
        "run_authority": {
            "authority_level": "decision_bearing",
            "authoritative_proving": True,
            "safe_to_steer_next_prompt": True,
        },
        "authoritative_proving": True,
    }

    record = apply_control_plane_to_run_record(
        run_dir=tmp_path,
        record=raw_record,
        control_plane=packet,
    )

    assert record["status"] == "ok"
    assert record["authoritative_proving"] is False
    assert record["safe_to_compare"] is False
    assert record["run_authority"]["authority_level"] == "non_authoritative"
    assert record["measurement_terminalization"]["reason_code"] == "bridge_recent_no_heartbeat_stall"
    assert (tmp_path / "measurement-terminalization.json").exists()
    assert (tmp_path / "run-authority.json").exists()


def test_bridge_candidate_registry_selects_first_green_candidate() -> None:
    packet = build_bridge_candidate_registry_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        lane_readiness=_lane_readiness(),
        bridge_candidates=[
            {
                "id": "degraded",
                "url": "http://127.0.0.1:8091",
                "identity": _bridge_identity(),
                "readiness": _bridge_readiness(),
                "stream_health": _bridge_stream_health(
                    status="recent_stall",
                    reason_code="bridge_recent_no_heartbeat_stall",
                    recent_signals=["bridge_stream_no_heartbeat"],
                ),
            },
            {
                "id": "healthy",
                "url": "http://127.0.0.1:8092",
                "identity": _bridge_identity(),
                "readiness": _bridge_readiness(),
                "stream_health": _bridge_stream_health(),
            },
        ],
        created_at="2026-04-22T00:00:00+00:00",
    )

    assert packet["registry_schema"] == "bridge_candidate_registry_v1"
    assert packet["selected_candidate_id"] == "healthy"
    assert packet["selection_reason"] == "selected_first_green"
    assert packet["light"] == "green"
    assert packet["safe_to_compare"] is True
    assert packet["lease"]["mode"] == "bridge_candidate_registry_v1"
    assert packet["candidates"][0]["light"] == "yellow"
    assert packet["candidates"][1]["light"] == "green"


def test_bridge_candidate_registry_uses_candidate_lane_readiness() -> None:
    packet = build_bridge_candidate_registry_packet(
        target="session_bootstrap",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        lane_readiness=_lane_readiness(),
        bridge_candidates=[
            {
                "id": "mismatched",
                "url": "http://127.0.0.1:8091",
                "identity": _bridge_identity(),
                "readiness": _bridge_readiness(),
                "lane_readiness": _lane_readiness(
                    lane_comparable=False,
                    blocking_reasons=["runner_bridge_git_sha_mismatch"],
                ),
                "stream_health": _bridge_stream_health(),
            },
            {
                "id": "compatible",
                "url": "http://127.0.0.1:8092",
                "identity": _bridge_identity(),
                "readiness": _bridge_readiness(),
                "lane_readiness": _lane_readiness(),
                "stream_health": _bridge_stream_health(),
            },
        ],
    )

    assert packet["selected_candidate_id"] == "compatible"
    assert packet["candidates"][0]["light"] == "yellow"
    assert packet["candidates"][0]["reason_code"] == "diagnostic_only_lane"
    assert packet["candidates"][1]["light"] == "green"


def test_bridge_candidate_registry_selects_yellow_when_no_green_exists() -> None:
    packet = build_bridge_candidate_registry_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        lane_readiness=_lane_readiness(),
        bridge_candidates=[
            {
                "id": "recent-stall",
                "url": "http://127.0.0.1:8091",
                "identity": _bridge_identity(),
                "readiness": _bridge_readiness(),
                "stream_health": _bridge_stream_health(
                    status="recent_stall",
                    reason_code="bridge_recent_no_heartbeat_stall",
                    recent_signals=["bridge_stream_no_heartbeat"],
                ),
            },
            {
                "id": "missing-capability",
                "url": "http://127.0.0.1:8092",
                "identity": {"component": "bridge", "capabilities": ["execute"]},
                "readiness": _bridge_readiness(capabilities=["execute"]),
            },
        ],
    )

    assert packet["selected_candidate_id"] == "recent-stall"
    assert packet["selection_reason"] == "selected_first_diagnostic_yellow"
    assert packet["light"] == "yellow"
    assert packet["safe_to_run"] is True
    assert packet["safe_to_compare"] is False
    assert packet["semantic_proof_satisfied"] is False


def test_bridge_candidate_registry_blocks_when_no_candidate_is_runnable() -> None:
    packet = build_bridge_candidate_registry_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        lane_readiness=_lane_readiness(),
        bridge_candidates=[
            {
                "id": "missing-capability",
                "url": "http://127.0.0.1:8092",
                "identity": {"component": "bridge", "capabilities": ["execute"]},
                "readiness": _bridge_readiness(capabilities=["execute"]),
            }
        ],
    )

    assert packet["selected_candidate_id"] == "missing-capability"
    assert packet["selection_reason"] == "no_runnable_candidate"
    assert packet["light"] == "red"
    assert packet["reason_code"] == "bridge_capability_mismatch"
    assert packet["safe_to_run"] is False
    assert packet["safe_to_compare"] is False


def test_bridge_candidate_registry_reports_no_candidates() -> None:
    packet = build_bridge_candidate_registry_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        required_capabilities=["analyze"],
        lane_readiness=_lane_readiness(),
        bridge_candidates=[],
    )

    assert packet["candidate_count"] == 0
    assert packet["selected_candidate_id"] == ""
    assert packet["selection_reason"] == "no_bridge_candidates"
    assert packet["light"] == "red"
    assert packet["reason_code"] == "no_green_bridge_available"
    assert packet["safe_to_run"] is False


def test_single_bridge_candidate_registry_wraps_configured_bridge() -> None:
    packet = build_single_bridge_candidate_registry_packet(
        target="session_bootstrap",
        analysis_profile="strict_dll",
        bridge_url="http://127.0.0.1:8090",
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        bridge_stream_health=_bridge_stream_health(),
        lane_readiness=_lane_readiness(),
    )

    assert packet["registry_schema"] == "bridge_candidate_registry_v1"
    assert packet["candidate_count"] == 1
    assert packet["selected_candidate_id"] == "configured-local-bridge"
    assert packet["selected_bridge"]["url"] == "http://127.0.0.1:8090"
    assert packet["light"] == "green"
    assert packet["safe_to_compare"] is True


def test_bridge_candidates_from_config_normalizes_unique_urls() -> None:
    candidates = build_bridge_candidates_from_config(
        bridge_urls=["http://127.0.0.1:8091", "http://127.0.0.1:8092"],
        default_bridge_url="http://127.0.0.1:8091",
        bridge_identities={
            "http://127.0.0.1:8091": _bridge_identity(),
            "http://127.0.0.1:8092": {"component": "bridge", "capabilities": ["execute"]},
        },
        bridge_readiness={
            "http://127.0.0.1:8091": _bridge_readiness(),
            "http://127.0.0.1:8092": _bridge_readiness(capabilities=["execute"]),
        },
        bridge_stream_health={
            "http://127.0.0.1:8091": _bridge_stream_health(),
            "http://127.0.0.1:8092": _bridge_stream_health(status="degraded", reason_code="bridge_stream_health_degraded"),
        },
        quarantined_bridge_urls=["http://127.0.0.1:8092"],
    )

    assert [candidate["id"] for candidate in candidates] == ["configured-bridge-1", "configured-bridge-2"]
    assert [candidate["url"] for candidate in candidates] == ["http://127.0.0.1:8091", "http://127.0.0.1:8092"]
    assert candidates[0]["identity"]["component"] == "bridge"
    assert candidates[0]["readiness"]["ready"] is True
    assert candidates[0]["stream_health"]["reason_code"] == "bridge_stream_health_coherent"
    assert candidates[1]["quarantined"] is True
    assert candidates[1]["quarantine_reason"] == "configured_bridge_quarantine"


def test_quarantine_registry_blocks_exact_target_profile_candidate() -> None:
    candidates = build_bridge_candidates_from_config(
        bridge_urls=["http://127.0.0.1:8091", "http://127.0.0.1:8092"],
        target="reservation_stage",
        analysis_profile="strict_dll",
        bridge_identities={
            "http://127.0.0.1:8091": _bridge_identity(),
            "http://127.0.0.1:8092": _bridge_identity(),
        },
        bridge_readiness={
            "http://127.0.0.1:8091": _bridge_readiness(),
            "http://127.0.0.1:8092": _bridge_readiness(),
        },
        bridge_stream_health={
            "http://127.0.0.1:8091": _bridge_stream_health(),
            "http://127.0.0.1:8092": _bridge_stream_health(),
        },
        quarantine_registry=[
            {
                "bridge_url": "http://127.0.0.1:8091",
                "target": "reservation_stage",
                "analysis_profile": "strict_dll",
                "state": "active",
                "reason_code": "bridge_recent_no_heartbeat_stall",
                "next_action": "use another bridge for this target/profile",
            }
        ],
    )

    packet = build_bridge_candidate_registry_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        bridge_candidates=candidates,
        lane_readiness=_lane_readiness(),
    )

    assert packet["selected_candidate_id"] == "configured-bridge-2"
    assert packet["candidates"][0]["light"] == "quarantined"
    assert packet["candidates"][0]["reason_code"] == "bridge_lane_quarantined"
    assert packet["candidates"][0]["quarantine"]["selected"]["reason_code"] == "bridge_recent_no_heartbeat_stall"
    assert packet["candidates"][1]["light"] == "green"


def test_quarantine_registry_target_scope_does_not_poison_other_targets() -> None:
    candidates = build_bridge_candidates_from_config(
        bridge_urls=["http://127.0.0.1:8091"],
        target="session_bootstrap",
        analysis_profile="strict_dll",
        bridge_identities={"http://127.0.0.1:8091": _bridge_identity()},
        bridge_readiness={"http://127.0.0.1:8091": _bridge_readiness()},
        bridge_stream_health={"http://127.0.0.1:8091": _bridge_stream_health()},
        quarantine_registry=[
            {
                "bridge_url": "http://127.0.0.1:8091",
                "target": "reservation_stage",
                "analysis_profile": "strict_dll",
                "state": "active",
                "reason_code": "bridge_recent_no_heartbeat_stall",
            }
        ],
    )
    packet = build_bridge_candidate_registry_packet(
        target="session_bootstrap",
        analysis_profile="strict_dll",
        bridge_candidates=candidates,
        lane_readiness=_lane_readiness(),
    )

    assert candidates[0]["quarantined"] is False
    assert packet["light"] == "green"
    assert packet["reason_code"] == "green_lane_admitted"


def test_expired_and_cleared_quarantine_rows_remain_visible_but_do_not_block() -> None:
    for state in ("expired", "cleared"):
        candidates = build_bridge_candidates_from_config(
            bridge_urls=["http://127.0.0.1:8091"],
            target="reservation_stage",
            analysis_profile="strict_dll",
            bridge_identities={"http://127.0.0.1:8091": _bridge_identity()},
            bridge_readiness={"http://127.0.0.1:8091": _bridge_readiness()},
            bridge_stream_health={"http://127.0.0.1:8091": _bridge_stream_health()},
            quarantine_registry=[
                {
                    "bridge_url": "http://127.0.0.1:8091",
                    "target": "reservation_stage",
                    "analysis_profile": "strict_dll",
                    "state": state,
                    "reason_code": "bridge_recent_no_heartbeat_stall",
                }
            ],
        )
        packet = build_bridge_candidate_registry_packet(
            target="reservation_stage",
            analysis_profile="strict_dll",
            bridge_candidates=candidates,
            lane_readiness=_lane_readiness(),
        )

        assert candidates[0]["quarantined"] is False
        assert candidates[0]["quarantine"]["matched"] is True
        assert candidates[0]["quarantine"]["selected"]["effective_state"] == state
        assert packet["light"] == "green"


def test_registry_reports_no_non_quarantined_bridge_available() -> None:
    candidates = build_bridge_candidates_from_config(
        bridge_urls=["http://127.0.0.1:8091"],
        target="reservation_stage",
        analysis_profile="strict_dll",
        bridge_identities={"http://127.0.0.1:8091": _bridge_identity()},
        bridge_readiness={"http://127.0.0.1:8091": _bridge_readiness()},
        bridge_stream_health={"http://127.0.0.1:8091": _bridge_stream_health()},
        quarantine_registry=[
            {
                "bridge_url": "http://127.0.0.1:8091",
                "state": "active",
                "reason_code": "bridge_lane_quarantined",
            }
        ],
    )
    packet = build_bridge_candidate_registry_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        bridge_candidates=candidates,
        lane_readiness=_lane_readiness(),
    )

    assert packet["selection_reason"] == "no_non_quarantined_bridge_available"
    assert packet["light"] == "quarantined"
    assert packet["safe_to_run"] is False
    assert packet["safe_to_compare"] is False


def _readiness_contracts(**overrides) -> dict:
    payload = {
        "tier2_traffic_light_enforcement": True,
        "tier3_selected_bridge_routing": True,
        "tier4_quarantine_recovery_selection": True,
    }
    payload.update(overrides)
    return payload


def _green_control_plane(target: str = "session_bootstrap") -> dict:
    return build_single_bridge_candidate_registry_packet(
        target=target,
        analysis_profile="strict_dll",
        bridge_url="http://127.0.0.1:8090",
        required_capabilities=["analyze"],
        runner_identity={"git_sha": "abc123"},
        api_identity={"git_sha": "abc123"},
        api_readiness={"ready": True},
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        lane_readiness=_lane_readiness(),
    )


def test_hard01_readiness_gate_passes_for_comparable_green_record() -> None:
    record = {
        "authoritative_proving": True,
        "safe_to_compare": True,
        "measurement_control_plane": _green_control_plane(),
        "explore_settings": {"selected_bridge_url": "http://127.0.0.1:8090"},
        "chain_context": {"target_name": "session_bootstrap"},
    }

    packet = build_hard01_baseline_readiness_packet(
        case_id="hard-01",
        lane_readiness=_lane_readiness(),
        suite_control_plane=_green_control_plane("hard-01"),
        run_records=[record],
        control_plane_contracts=_readiness_contracts(),
    )

    assert packet["verdict"] == "ready_for_bounded_hard01_baseline_attempt"
    assert packet["ready_for_bounded_baseline_attempt"] is True


def test_hard01_readiness_gate_rejects_yellow_semantic_proof() -> None:
    control_plane = build_measurement_control_plane_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        bridge_url="http://127.0.0.1:8090",
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        lane_readiness=_lane_readiness(),
        bridge_stream_health={"status": "unproven", "reason_code": "bridge_stream_health_unproven"},
    )
    record = {
        "authoritative_proving": True,
        "safe_to_compare": True,
        "measurement_control_plane": control_plane,
        "explore_settings": {"selected_bridge_url": "http://127.0.0.1:8090"},
        "measurement_terminalization": {"reason_code": "bridge_stream_health_unproven"},
        "run_authority": {"authoritative_proving": True, "authority_level": "decision_bearing"},
        "dependent_chain_policy": DEFAULT_DEPENDENCY_POLICY,
        "chain_context": {"target_name": "reservation_stage"},
    }

    packet = build_hard01_baseline_readiness_packet(
        case_id="hard-01",
        lane_readiness=_lane_readiness(),
        suite_control_plane=_green_control_plane("hard-01"),
        run_records=[record],
        control_plane_contracts=_readiness_contracts(),
    )

    assert packet["verdict"] == "not_ready_control_plane_gap"
    assert packet["checks"]["semantic_proof_containment"]["passed"] is False


def test_hard01_readiness_gate_requires_dependency_policy_after_non_comparable() -> None:
    control_plane = build_measurement_control_plane_packet(
        target="reservation_stage",
        analysis_profile="strict_dll",
        bridge_url="http://127.0.0.1:8090",
        bridge_identity=_bridge_identity(),
        bridge_readiness=_bridge_readiness(),
        lane_readiness=_lane_readiness(),
        bridge_stream_health={"status": "unproven", "reason_code": "bridge_stream_health_unproven"},
    )
    record = {
        "authoritative_proving": False,
        "safe_to_compare": False,
        "measurement_control_plane": control_plane,
        "explore_settings": {"selected_bridge_url": "http://127.0.0.1:8090"},
        "measurement_terminalization": {"reason_code": "bridge_stream_health_unproven"},
        "run_authority": {"authoritative_proving": False, "authority_level": "non_authoritative"},
        "chain_context": {"target_name": "reservation_stage"},
    }

    packet = build_hard01_baseline_readiness_packet(
        case_id="hard-01",
        lane_readiness=_lane_readiness(),
        suite_control_plane=_green_control_plane("hard-01"),
        run_records=[record],
        control_plane_contracts=_readiness_contracts(),
    )

    assert packet["verdict"] == "not_ready_dependency_blocking_gap"
    assert packet["checks"]["dependency_blocking"]["passed"] is False


def test_hard01_readiness_gate_rejects_missing_selected_bridge_route() -> None:
    record = {
        "authoritative_proving": True,
        "safe_to_compare": True,
        "measurement_control_plane": _green_control_plane(),
        "explore_settings": {},
        "chain_context": {"target_name": "session_bootstrap"},
    }

    packet = build_hard01_baseline_readiness_packet(
        case_id="hard-01",
        lane_readiness=_lane_readiness(),
        suite_control_plane=_green_control_plane("hard-01"),
        run_records=[record],
        control_plane_contracts=_readiness_contracts(),
    )

    assert packet["verdict"] == "not_ready_selected_bridge_routing_gap"
