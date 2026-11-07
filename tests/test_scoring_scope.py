from __future__ import annotations

from types import SimpleNamespace


def test_target_scope_names_dedupes_required_and_selected() -> None:
    from api.pipeline.core.scoring_scope import target_scope_names

    scope = target_scope_names(
        {
            "required_semantic_checkpoint": "SP_CommitRelease",
            "selected_invocable_names": ["SP_CommitRelease", "SP_RecordReleaseReceipt", ""],
        }
    )

    assert scope == ["SP_CommitRelease", "SP_RecordReleaseReceipt"]


def test_canonical_status_map_marks_missing_scoped_functions_unknown() -> None:
    from api.pipeline.core.scoring_scope import canonical_status_map

    findings = [
        {"function": "SP_OpenOperatorSession", "status": "success"},
    ]

    status_map = canonical_status_map(findings, ["SP_CommitRelease"])

    assert status_map == {"SP_CommitRelease": "unknown"}


def test_macro_coordinator_coverage_uses_runtime_scope(monkeypatch) -> None:
    import api.pipeline.core.macro_coordinator as macro

    monkeypatch.setattr(
        "api.infra.storage._load_findings",
        lambda job_id: [
            {"function": "SP_OpenOperatorSession", "status": "success"},
        ],
    )

    ctx = SimpleNamespace(
        job_id="job-1",
        runtime=SimpleNamespace(
            required_semantic_checkpoint="SP_CommitRelease",
            selected_invocable_names=["SP_CommitRelease"],
        ),
    )

    coverage = macro._compute_coverage(ctx)

    assert coverage.total == 1
    assert coverage.verified == 0
    assert coverage.unknown == 1
    assert coverage.verified_rate == 0.0
