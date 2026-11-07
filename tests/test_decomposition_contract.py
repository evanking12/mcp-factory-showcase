from api.pipeline.core.decomposition_contract import (
    CONTRADICTION_STATES,
    DECOMPOSITION_OBSERVER_NAMES,
    DEFAULT_DECOMPOSITION_RETENTION_POLICY,
    DecompositionLifecycle,
    ShardEconomics,
    build_decomposition_object_id,
    build_frontier_slice_boundedness_observer,
    build_merge_coherence_observer,
    build_shard_validity_observer,
    normalize_closure_reason,
    normalize_contradiction_state,
)


def test_decomposition_lifecycle_round_trips_with_phase0_defaults() -> None:
    lifecycle = DecompositionLifecycle(
        id=build_decomposition_object_id("shard", "suite", graph_epoch="g1", ordinal=2),
        object_type="shard",
        package_id="suite",
        graph_epoch="g1",
        source_ids=("job-a", "job-b"),
        contradiction_state="tentative",
    )

    restored = DecompositionLifecycle.from_dict(lifecycle.to_dict())

    assert restored == lifecycle


def test_decomposition_lifecycle_requires_closure_reason_with_closed_at() -> None:
    try:
        DecompositionLifecycle(
            id=build_decomposition_object_id("cluster_candidate", "suite", stable_hash="abc123"),
            object_type="cluster_candidate",
            package_id="suite",
            closed_at="2026-04-07T10:30:00Z",
            active=False,
        )
    except ValueError as exc:
        assert "closed_at and closure_reason" in str(exc)
    else:
        raise AssertionError("expected lifecycle closure validation to fail")


def test_build_decomposition_object_id_uses_documented_phase0_formats() -> None:
    assert build_decomposition_object_id("shard", "pkg", graph_epoch="epoch-1", ordinal=4) == (
        "shard::pkg::epoch-1::4"
    )
    assert build_decomposition_object_id("frontier_slice", "pkg", graph_epoch="epoch-1", ordinal=1) == (
        "frontier_slice::pkg::epoch-1::1"
    )
    assert build_decomposition_object_id("cluster_candidate", "pkg", stable_hash="deadbeef") == (
        "cluster_candidate::pkg::deadbeef"
    )
    assert build_decomposition_object_id("init_group_candidate", "pkg", stable_hash="cafe") == (
        "init_group_candidate::pkg::cafe"
    )
    assert build_decomposition_object_id("dependency_class", "pkg", stable_hash="feed") == (
        "dependency_class::pkg::feed"
    )


def test_normalizers_fall_back_to_safe_phase0_defaults() -> None:
    assert normalize_contradiction_state("unsupported") == "none"
    assert normalize_closure_reason("unsupported") == ""
    assert set(CONTRADICTION_STATES) >= {"tentative", "blocked", "confirmed"}


def test_shard_economics_reports_budget_breached_when_limits_are_exceeded() -> None:
    economics = ShardEconomics(
        actual_shard_width=18,
        actual_runtime_minutes=22.5,
        actual_deep_follow_up_count=1,
    )

    payload = economics.to_dict()

    assert payload["budget_breached"] is True
    assert payload["runtime_budget_ok"] is False
    assert payload["shard_width_ok"] is False
    assert payload["deep_follow_up_budget_ok"] is False
    assert payload["intake_mode"] == "intake_only"


def test_observer_builders_emit_documented_phase0_shapes() -> None:
    shard = build_shard_validity_observer(
        object_id="shard::suite::epoch::0",
        status="pass",
        capture_valid=True,
        runtime_budget_ok=True,
        required_artifacts_present=True,
        hidden_variable_state_recorded=True,
        reasons=("bounded",),
        warnings=(),
    )
    merge = build_merge_coherence_observer(
        object_id="cluster_candidate::suite::abc",
        status="warn",
        provenance_complete=True,
        stable_identity_present=True,
        contradictions_visible=True,
        ambiguity_score=0.4,
        reasons=("candidate_only",),
        warnings=("contradiction_open",),
    )
    boundedness = build_frontier_slice_boundedness_observer(
        object_id="frontier_slice::suite::epoch::0",
        status="pass",
        imported_truth_explicit=True,
        active_work_explicit=True,
        slice_width=3,
        dll_count=2,
        cluster_count=2,
        init_group_count=1,
        reopened_imported_truth=False,
        reasons=("narrow",),
        warnings=(),
    )

    assert shard["observer_name"] == "shard_validity"
    assert shard["capture_valid"] is True
    assert shard["runtime_budget_ok"] is True
    assert merge["observer_name"] == "merge_coherence"
    assert merge["contradictions_visible"] is True
    assert "ambiguity_score" in merge
    assert boundedness["observer_name"] == "frontier_slice_boundedness"
    assert boundedness["slice_width"] == 3
    assert set(DECOMPOSITION_OBSERVER_NAMES) >= {
        "initialization_group_plausibility",
        "dependency_class_plausibility",
    }


def test_retention_policy_classifies_phase0_artifacts() -> None:
    policy = DEFAULT_DECOMPOSITION_RETENTION_POLICY

    assert policy.classify_artifact("shard_summary") == "canonical"
    assert policy.classify_artifact("temporary_scoring_detail") == "summary_only"
    assert policy.classify_artifact("prior_candidate_versions") == "superseded_or_compacted"
    assert policy.classify_artifact("unlisted_artifact") == "canonical"
