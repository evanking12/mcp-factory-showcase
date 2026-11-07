from __future__ import annotations


def test_blocker_classification_prefers_semantic_family_when_lane_trusted() -> None:
    from api.analysis.blocker_harvest import build_blocker_classification_report

    report = build_blocker_classification_report(
        campaign={"campaign_id": "camp-1", "package_id": "pkg-1", "package_label": "Pkg 1"},
        entry={"job_id": "job-1", "dll_id": "dll-1", "filename": "soundtouch.dll"},
        findings=[
            {
                "function": "soundtouch_putSamples_i16",
                "status": "failure",
                "finding": "Sample buffer payload still ambiguous",
                "source_stage": "s02_probe",
            },
            {
                "function": "soundtouch_getVersionString",
                "status": "failure",
                "finding": "Output buffer observer still unresolved",
                "source_stage": "s05_enrichment",
            },
        ],
        lane_trust={"trust_status": "trusted", "runtime_path_trust": "matched", "trustworthy_for_architecture": True},
    )

    assert report["primary_blocker_family"] in {"struct/payload shaping", "output/readback"}
    assert report["candidate_next_system"] != ""
    assert report["trustworthy_for_architecture"] is True
    assert report["unresolved_function_count"] == 2


def test_blocker_classification_uses_measurement_when_lane_blocked() -> None:
    from api.analysis.blocker_harvest import build_blocker_classification_report

    report = build_blocker_classification_report(
        campaign={"campaign_id": "camp-2"},
        entry={"job_id": "job-2", "dll_id": "dll-2", "filename": "mystery.dll"},
        findings=[
            {"function": "FnA", "status": "failure", "finding": "looks semantic but trust is broken"},
        ],
        lane_trust={"trust_status": "blocked", "runtime_path_trust": "mismatch", "trustworthy_for_architecture": False},
    )

    assert report["primary_blocker_family"] == "measurement"
    assert report["secondary_blocker_families"] == ["state"]
    assert report["architecture_relevance"] == "low"
    assert report["trustworthy_for_architecture"] is False


def test_campaign_lane_gate_rejects_missing_execute_route(monkeypatch) -> None:
    from api.analysis import blocker_harvest

    monkeypatch.setattr(
        blocker_harvest,
        "verify_bridge_identity",
        lambda _url, _secret="": (False, "bridge_missing_execute_route"),
    )

    gate = blocker_harvest.build_campaign_lane_gate(
        campaign={"campaign_id": "camp-3", "package_id": "pkg-3", "package_label": "Pkg 3"},
        runtime_settings={"lane_id": "lane-1", "parallel_runs": 1},
        job_statuses=[{"discovery_meta": {"bridge_reachable": True}}],
    )

    assert gate["trust_status"] == "blocked"
    assert "bridge_missing_execute_route" in gate["reasons"]

