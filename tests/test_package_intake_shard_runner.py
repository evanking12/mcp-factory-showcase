from api.pipeline.core.package_intake_shard_runner import build_package_intake_shards
from api.pipeline.core.types import Campaign, DllEntry


def _package_payload() -> dict:
    return {
        "package_id": "contoso-suite",
        "package_label": "Contoso Suite",
        "graph_epoch": "epoch-1",
        "package_context": {"source_origin": "fixture"},
        "dll_entries": [
            {"dll_id": "dll-c", "filename": "contoso_config.dll", "job_id": "job-c"},
            {"dll_id": "dll-w", "filename": "contoso_workflow.dll", "job_id": "job-w"},
            {"dll_id": "dll-r", "filename": "contoso_reporting.dll", "job_id": "job-r"},
            {"dll_id": "dll-p", "filename": "contoso_pricing.dll", "job_id": "job-p"},
        ],
    }


def test_build_package_intake_shards_is_deterministic() -> None:
    payload = _package_payload()
    payload["dll_entries"] = list(reversed(payload["dll_entries"]))

    first = build_package_intake_shards(payload, target_shard_width=2)
    second = build_package_intake_shards(payload, target_shard_width=2)

    assert first == second
    assert first["shard_count"] == 2
    assert first["shards"][0]["dll_filenames"] == (
        "contoso_config.dll",
        "contoso_pricing.dll",
    )


def test_build_package_intake_shards_emits_stable_ids() -> None:
    result = build_package_intake_shards(_package_payload(), target_shard_width=3)

    assert result["shards"][0]["lifecycle"]["id"] == "shard::contoso-suite::epoch-1::0"
    assert result["shards"][1]["lifecycle"]["id"] == "shard::contoso-suite::epoch-1::1"
    assert all(
        shard["lifecycle"]["object_type"] == "shard" for shard in result["shards"]
    )


def test_build_package_intake_shards_respects_hard_split_threshold() -> None:
    result = build_package_intake_shards(
        _package_payload(),
        target_shard_width=20,
        hard_split_threshold=3,
    )

    assert result["split_strategy"] == "hard_split_threshold"
    assert result["effective_shard_width"] == 3
    assert all(shard["shard_economics"]["actual_shard_width"] <= 3 for shard in result["shards"])
    assert result["shards"][0]["observer_summary"]["warnings"] == (
        "auto_resplit_to_hard_threshold",
    )


def test_build_package_intake_shards_marks_intake_only_metadata() -> None:
    result = build_package_intake_shards(_package_payload(), target_shard_width=2)

    assert result["intake_mode"] == "intake_only"
    assert result["budget_breach_count"] == 0
    assert result["package_context_recorded"] is True
    assert all(shard["intake_mode"] == "intake_only" for shard in result["shards"])
    assert all(shard["observer_summary"]["capture_valid"] is True for shard in result["shards"])


def test_build_package_intake_shards_rejects_non_intake_mode() -> None:
    try:
        build_package_intake_shards(_package_payload(), intake_mode="deep_probe")
    except ValueError as exc:
        assert "intake_only" in str(exc)
    else:
        raise AssertionError("expected intake shard runner to reject non-intake mode")


def test_build_package_intake_shards_accepts_campaign_input() -> None:
    campaign = Campaign(
        campaign_id="camp-1",
        package_id="contoso-suite",
        package_label="Contoso Suite",
        graph_epoch="epoch-1",
        package_context={"source_origin": "fixture"},
        dll_entries=[
            DllEntry(dll_id="dll-c", filename="contoso_config.dll", job_id="job-c"),
            DllEntry(dll_id="dll-w", filename="contoso_workflow.dll", job_id="job-w"),
        ],
    )

    result = build_package_intake_shards(campaign, target_shard_width=1)

    assert result["shard_count"] == 2
    assert result["baseline_contract_present"] is False
