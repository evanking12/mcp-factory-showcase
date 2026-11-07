from __future__ import annotations

from types import SimpleNamespace

from api.pipeline.core.checkpoint import (
    ClusterSeedPlan,
    FunctionCheckpoint,
    PipelineCheckpoint,
    load_checkpoint,
    resolve_cluster_seed_plan,
    save_checkpoint,
    seed_context_from_checkpoint,
    update_checkpoint_from_context,
)
from api.pipeline.core.cluster_checkpoint import build_cluster_checkpoint_snapshot
from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry, TIER_RUNTIME
from api.pipeline.core.prerequisite_state_groups import build_prerequisite_state_group_snapshot


def test_update_checkpoint_from_context_persists_evidence_snapshot() -> None:
    checkpoint = PipelineCheckpoint(
        job_id="job-1",
        functions={
            "WF_CreateReservation": FunctionCheckpoint(
                name="WF_CreateReservation",
                status="success",
                working_call={"pOutReservationId": "RSV-001"},
                verified=True,
            )
        },
    )
    ecr = EvidenceCandidateRegistry()
    ecr.seed_tier0()
    ecr.add("CUST-001", TIER_RUNTIME, "runtime:Init", "customer_id", 0.95, "Init")
    ecr.mark_init_satisfied("CP_Initialize")
    ctx = SimpleNamespace(
        sentinels={},
        vocab={},
        unlock_result={},
        write_unlock_block="",
        dll_strings={},
        static_hints_block="",
        evidence_candidates=ecr,
    )

    update_checkpoint_from_context(checkpoint, ctx)

    snapshot = checkpoint.evidence_candidates_snapshot
    assert snapshot["init_satisfied"] == ["CP_Initialize"]
    assert any(
        entry["value"] == "CUST-001"
        for entry in snapshot["candidates"]["customer_id"]
    )
    workflow = checkpoint.cluster_checkpoints["workflow_reservation_open_state"]
    assert workflow["active_seam"]
    assert workflow["gate_color"] == "amber"
    assert workflow["latest_trusted_proof_jobs"] == ["job-1"]
    assert workflow["expected_next_move"]


def test_seed_context_from_checkpoint_restores_evidence_candidates() -> None:
    restored = EvidenceCandidateRegistry()
    restored.add("CUST-001", TIER_RUNTIME, "runtime:Init", "customer_id", 0.95, "Init")
    restored.mark_init_satisfied("CP_Initialize")
    checkpoint = PipelineCheckpoint(
        job_id="job-1",
        evidence_candidates_snapshot=restored.to_dict(),
    )

    ctx = SimpleNamespace(
        job_id="job-2",
        sentinels={},
        vocab={},
        unlock_result={},
        write_unlock_block="",
        dll_strings={},
        static_hints_block="",
        already_explored=set(),
        evidence_candidates=EvidenceCandidateRegistry(),
        inv_map={
            "CFG_OpenLicensedWindow": {
                "name": "CFG_OpenLicensedWindow",
                "parameters": [
                    {"name": "pOutTicket", "direction": "out", "json_type": "string"},
                ],
            },
            "CFG_GetLicenseNonce": {
                "name": "CFG_GetLicenseNonce",
                "parameters": [
                    {"name": "pOutNonce", "direction": "out", "json_type": "string"},
                ],
            },
        },
    )

    seeded = seed_context_from_checkpoint(ctx, checkpoint)

    assert seeded == 0
    customer_entries = ctx.evidence_candidates.query("customer_id")
    assert any(entry.value == "CUST-001" for entry in customer_entries)
    assert ctx.evidence_candidates.is_init_satisfied()


def test_seed_context_from_checkpoint_seeds_findings_into_resumed_job(monkeypatch) -> None:
    checkpoint = PipelineCheckpoint(job_id="job-1")
    from api.pipeline.core.checkpoint import record_function_checkpoint
    record_function_checkpoint(
        checkpoint,
        "CP_ProcessPurchase",
        "success",
        working_call={"param_1": "CUST-001"},
        finding="verified purchase path",
        verified=True,
        stage="s02",
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "api.infra.storage._seed_findings",
        lambda job_id, rows: captured.setdefault("seed", (job_id, rows)),
    )

    ctx = SimpleNamespace(
        job_id="job-2",
        sentinels={},
        vocab={},
        unlock_result={},
        write_unlock_block="",
        dll_strings={},
        static_hints_block="",
        already_explored=set(),
        evidence_candidates=EvidenceCandidateRegistry(),
    )

    seed_context_from_checkpoint(ctx, checkpoint)

    assert "seed" in captured
    seeded_job, rows = captured["seed"]
    assert seeded_job == "job-2"
    assert rows[0]["function"] == "CP_ProcessPurchase"
    assert rows[0]["source"] == "checkpoint_resume"


def test_seed_context_from_checkpoint_skips_weaker_or_duplicate_rows(monkeypatch) -> None:
    checkpoint = PipelineCheckpoint(
        job_id="job-1",
        functions={
            "CP_ProcessPurchase": FunctionCheckpoint(
                name="CP_ProcessPurchase",
                status="unknown",
                working_call=None,
            ),
            "CP_ReserveStock": FunctionCheckpoint(
                name="CP_ReserveStock",
                status="success",
                working_call={"param_1": "CUST-001"},
                finding="checkpoint success",
                verified=True,
            ),
        },
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "api.infra.storage._seed_findings",
        lambda job_id, rows: captured.setdefault("seed", (job_id, rows)),
    )
    monkeypatch.setattr(
        "api.infra.storage._load_findings",
        lambda _job_id: [
            {
                "function": "CP_ProcessPurchase",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"param_1": "CUST-001"},
            },
            {
                "function": "CP_ReserveStock",
                "status": "success",
                "status_canonical": "verified_success",
                "working_call": {"param_1": "CUST-001"},
            },
        ],
    )

    ctx = SimpleNamespace(
        job_id="job-2",
        sentinels={},
        vocab={},
        unlock_result={},
        write_unlock_block="",
        dll_strings={},
        static_hints_block="",
        already_explored=set(),
        evidence_candidates=EvidenceCandidateRegistry(),
    )

    seed_context_from_checkpoint(ctx, checkpoint)

    assert "seed" not in captured


def test_seed_context_from_checkpoint_treats_verified_success_as_skippable(monkeypatch) -> None:
    checkpoint = PipelineCheckpoint(
        job_id="job-1",
        functions={
            "CP_CheckStock": FunctionCheckpoint(
                name="CP_CheckStock",
                status="verified_success",
                working_call={"param_1": "PRO-SVC-ANNUAL"},
            )
        },
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "api.infra.storage._seed_findings",
        lambda job_id, rows: captured.setdefault("seed", (job_id, rows)),
    )
    monkeypatch.setattr(
        "api.pipeline.core.checkpoint.assess_reusable_truth",
        lambda _row, invocable=None: {"seed_eligible": True, "score": 1.0, "reasons": ["test"]},
    )
    monkeypatch.setattr("api.infra.storage._load_findings", lambda _job_id: [])
    ctx = SimpleNamespace(
        job_id="job-2",
        sentinels={},
        vocab={},
        unlock_result={},
        write_unlock_block="",
        dll_strings={},
        static_hints_block="",
        already_explored=set(),
        evidence_candidates=EvidenceCandidateRegistry(),
    )

    seeded = seed_context_from_checkpoint(ctx, checkpoint)

    assert seeded == 1
    assert "CP_CheckStock" in ctx.already_explored
    _, rows = captured["seed"]
    assert rows[0]["status"] == "success"
    assert rows[0]["verification"] == "verified"


def test_seed_context_from_checkpoint_honors_seed_function_allowlist(monkeypatch) -> None:
    checkpoint = PipelineCheckpoint(
        job_id="job-1",
        functions={
            "CFG_OpenLicensedWindow": FunctionCheckpoint(
                name="CFG_OpenLicensedWindow",
                status="success",
                working_call={"pOutTicket": "TICK-001"},
            ),
            "CFG_GetLicenseNonce": FunctionCheckpoint(
                name="CFG_GetLicenseNonce",
                status="success",
                working_call={"pOutNonce": "NONCE-001"},
            ),
        },
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "api.infra.storage._seed_findings",
        lambda job_id, rows: captured.setdefault("seed", (job_id, rows)),
    )
    monkeypatch.setattr(
        "api.pipeline.core.checkpoint.assess_reusable_truth",
        lambda _row, invocable=None: {"seed_eligible": True, "score": 1.0, "reasons": ["test"]},
    )
    monkeypatch.setattr("api.infra.storage._load_findings", lambda _job_id: [])
    ctx = SimpleNamespace(
        job_id="job-2",
        sentinels={},
        vocab={},
        unlock_result={},
        write_unlock_block="",
        dll_strings={},
        static_hints_block="",
        already_explored=set(),
        evidence_candidates=EvidenceCandidateRegistry(),
        inv_map={
            "CFG_OpenLicensedWindow": {
                "name": "CFG_OpenLicensedWindow",
                "parameters": [
                    {"name": "pOutTicket", "direction": "out", "json_type": "string"},
                ],
            },
            "CFG_GetLicenseNonce": {
                "name": "CFG_GetLicenseNonce",
                "parameters": [
                    {"name": "pOutNonce", "direction": "out", "json_type": "string"},
                ],
            },
        },
    )

    seeded = seed_context_from_checkpoint(
        ctx,
        checkpoint,
        seed_function_allowlist={"CFG_OpenLicensedWindow"},
    )

    assert seeded == 1
    assert "CFG_OpenLicensedWindow" in ctx.already_explored
    assert "CFG_GetLicenseNonce" not in ctx.already_explored
    _, rows = captured["seed"]
    assert [row["function"] for row in rows] == ["CFG_OpenLicensedWindow"]


def test_seed_context_from_checkpoint_rejects_semantically_implausible_success(monkeypatch) -> None:
    checkpoint = PipelineCheckpoint(
        job_id="job-1",
        functions={
            "CP_ProcessPurchase": FunctionCheckpoint(
                name="CP_ProcessPurchase",
                status="success",
                working_call={"lpszCustomerId": "ACC-USB-C", "dwQuantity": 1},
                finding="returned 0",
            )
        },
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "api.infra.storage._seed_findings",
        lambda job_id, rows: captured.setdefault("seed", (job_id, rows)),
    )
    ctx = SimpleNamespace(
        job_id="job-2",
        sentinels={},
        vocab={},
        unlock_result={},
        write_unlock_block="",
        dll_strings={},
        static_hints_block="",
        already_explored=set(),
        evidence_candidates=EvidenceCandidateRegistry(),
        inv_map={
            "CP_ProcessPurchase": {
                "name": "CP_ProcessPurchase",
                "parameters": [
                    {"name": "lpszCustomerId", "json_type": "string", "resolved_type": "char*", "description": "Customer identifier"},
                    {"name": "dwQuantity", "json_type": "integer", "description": "Quantity to purchase"},
                ],
            }
        },
    )

    seeded = seed_context_from_checkpoint(ctx, checkpoint)

    assert seeded == 0
    assert "seed" not in captured
    assert "CP_ProcessPurchase" not in ctx.already_explored


def test_load_checkpoint_uses_source_id_when_source_job_id_is_blank(monkeypatch) -> None:
    payload = {
        "job_id": "source-job",
        "source_job_id": "",
        "created_at": 0,
        "updated_at": 0,
        "sentinels": {},
        "vocab": {},
        "unlock_result": {},
        "write_unlock_block": "",
        "winning_init_sequence": [],
        "dll_strings": {},
        "static_hints_block": "",
        "cross_dll_context": {},
        "evidence_candidates": {},
        "stages": {},
        "functions": {},
    }
    monkeypatch.setattr(
        "api.pipeline.core.checkpoint._download_blob",
        lambda *_args, **_kwargs: __import__("json").dumps(payload).encode("utf-8"),
    )

    loaded = load_checkpoint("resume-job", checkpoint_id="source-job", checkpoint_stage="s02_probe")

    assert loaded is not None
    assert loaded.source_job_id == "source-job"


def test_load_checkpoint_backfills_cluster_snapshots_for_older_checkpoints(monkeypatch) -> None:
    payload = {
        "job_id": "source-job",
        "source_job_id": "",
        "created_at": 0,
        "updated_at": 0,
        "sentinels": {},
        "vocab": {},
        "unlock_result": {},
        "write_unlock_block": "",
        "winning_init_sequence": [],
        "dll_strings": {},
        "static_hints_block": "",
        "cross_dll_context": {},
        "evidence_candidates": {},
        "stages": {},
        "functions": {
            "WF_CreateReservation": {
                "name": "WF_CreateReservation",
                "status": "success",
                "working_call": {"pOutReservationId": "RSV-001"},
                "finding": "",
                "verified": True,
                "stage": "s02",
                "timestamp": 0,
            }
        },
    }
    monkeypatch.setattr(
        "api.pipeline.core.checkpoint._download_blob",
        lambda *_args, **_kwargs: __import__("json").dumps(payload).encode("utf-8"),
    )

    loaded = load_checkpoint("resume-job", checkpoint_id="source-job", checkpoint_stage="s02_probe")

    assert loaded is not None
    workflow = loaded.cluster_checkpoints["workflow_reservation_open_state"]
    assert workflow["active_seam"]
    assert workflow["gate_color"] == "amber"
    assert workflow["latest_trusted_proof_jobs"] == ["source-job"]
    assert workflow["expected_next_move"]


def test_save_checkpoint_persists_backfilled_cluster_snapshots(monkeypatch) -> None:
    checkpoint = PipelineCheckpoint(
        job_id="job-save",
        functions={
            "WF_CreateReservation": FunctionCheckpoint(
                name="WF_CreateReservation",
                status="success",
                working_call={"pOutReservationId": "RSV-001"},
                verified=True,
            )
        },
        cluster_checkpoints={
            "workflow_reservation_open_state": {
                "cluster_id": "workflow_reservation_open_state",
                "latest_trusted_proof_jobs": ["older-job"],
            }
        },
        prerequisite_state_groups={
            "workflow_reservation_bootstrap": {
                "group_id": "workflow_reservation_bootstrap",
                "latest_trusted_proof_jobs": ["older-job"],
            }
        },
    )
    uploads: dict[str, dict] = {}

    def _capture_upload(_container: str, blob_path: str, data: bytes) -> None:
        uploads[blob_path] = __import__("json").loads(data.decode("utf-8"))

    monkeypatch.setattr("api.pipeline.core.checkpoint._upload_to_blob", _capture_upload)

    save_checkpoint(checkpoint)

    payload = uploads["job-save/checkpoints/latest.json"]
    workflow = payload["cluster_checkpoints"]["workflow_reservation_open_state"]
    workflow_bootstrap = payload["prerequisite_state_groups"]["workflow_reservation_bootstrap"]
    assert workflow["active_seam"]
    assert workflow["gate_color"] == "amber"
    assert workflow["latest_trusted_proof_jobs"] == ["older-job", "job-save"]
    assert workflow_bootstrap["bounded_purpose"]
    assert workflow_bootstrap["gate_color"] == "amber"
    assert workflow_bootstrap["latest_trusted_proof_jobs"] == ["older-job", "job-save"]
    assert workflow["expected_next_move"]


def test_pipeline_checkpoint_can_carry_cluster_checkpoint_snapshots() -> None:
    snapshot = build_cluster_checkpoint_snapshot()
    checkpoint = PipelineCheckpoint(
        job_id="job-clusters",
        cluster_checkpoints={row["cluster_id"]: row for row in snapshot},
    )

    assert "workflow_reservation_open_state" in checkpoint.cluster_checkpoints
    assert checkpoint.cluster_checkpoints["pricing_quote_lifecycle"]["live_artifact_families"] == [
        "quote_id",
        "nonce",
    ]


def test_resolve_cluster_seed_plan_accepts_trusted_cluster_checkpoint() -> None:
    snapshot = build_cluster_checkpoint_snapshot()
    checkpoint = PipelineCheckpoint(
        job_id="job-1",
        source_job_id="source-1",
        cluster_checkpoints={row["cluster_id"]: row for row in snapshot},
        functions={
            "WF_CreateReservation": FunctionCheckpoint(
                name="WF_CreateReservation",
                status="success",
                working_call={"lpszCustomerId": "CUST-001", "pOutReservationId": "RSV-001"},
            ),
            "WF_OpenFulfillment": FunctionCheckpoint(
                name="WF_OpenFulfillment",
                status="success",
                working_call={"lpszReservationId": "RSV-001"},
            ),
            "WF_GetWorkflowNonce": FunctionCheckpoint(
                name="WF_GetWorkflowNonce",
                status="success",
                working_call={"lpszHandle": "WFH-CUST-001-02"},
            ),
        },
    )

    plan = resolve_cluster_seed_plan(checkpoint, "workflow_reservation_open_state")

    assert plan is not None
    assert plan.cluster_id == "workflow_reservation_open_state"
    assert plan.allowed_artifact_families == ("reservation_id", "workflow_handle", "nonce")
    assert plan.confidence >= 0.5
    assert "WF_GetWorkflowState" in plan.focus_functions


def test_resolve_cluster_seed_plan_rejects_schema_or_confidence_failures() -> None:
    snapshot = build_cluster_checkpoint_snapshot()
    bad_row = next(row for row in snapshot if row["cluster_id"] == "workflow_reservation_open_state")
    bad_row = dict(bad_row)
    bad_row["schema_version"] = "0.9.0"
    checkpoint = PipelineCheckpoint(
        job_id="job-1",
        source_job_id="source-1",
        cluster_checkpoints={"workflow_reservation_open_state": bad_row},
    )

    assert resolve_cluster_seed_plan(checkpoint, "workflow_reservation_open_state") is None


def test_seed_context_from_checkpoint_filters_evidence_for_cluster_seed_plan() -> None:
    restored = EvidenceCandidateRegistry()
    restored.add("QTE-001", TIER_RUNTIME, "runtime:PR_BeginQuote", "quote_id", 0.95, "PR_BeginQuote")
    restored.add("WFH-CUST-001-02", TIER_RUNTIME, "runtime:WF_OpenFulfillment", "workflow_handle", 0.95, "WF_OpenFulfillment")
    restored.mark_init_satisfied("CP_Initialize")
    checkpoint = PipelineCheckpoint(
        job_id="job-1",
        source_job_id="source-1",
        evidence_candidates_snapshot=restored.to_dict(),
        functions={
            "PR_BeginQuote": FunctionCheckpoint(
                name="PR_BeginQuote",
                status="success",
                working_call={"pOutQuoteId": "QTE-001"},
            ),
            "WF_OpenFulfillment": FunctionCheckpoint(
                name="WF_OpenFulfillment",
                status="success",
                working_call={"lpszHandle": "WFH-CUST-001-02"},
            ),
        },
    )
    captured: dict[str, object] = {}
    monkeypatch_seed = lambda job_id, rows: captured.setdefault("seed", (job_id, rows))

    import api.infra.storage as _storage
    original_seed = _storage._seed_findings
    _storage._seed_findings = monkeypatch_seed
    try:
        ctx = SimpleNamespace(
            job_id="job-2",
            sentinels={},
            vocab={},
            unlock_result={},
            write_unlock_block="",
            dll_strings={},
            static_hints_block="",
            already_explored=set(),
            evidence_candidates=EvidenceCandidateRegistry(),
        )

        plan = ClusterSeedPlan(
            cluster_id="pricing_quote_lifecycle",
            focus_functions=("PR_BeginQuote", "PR_GetQuoteState", "PR_SealQuote"),
            seed_functions=("PR_BeginQuote",),
            allowed_artifact_families=("quote_id", "nonce"),
            lineage_sources=("same-run prerequisite replay",),
            reuse_eligibility=("only reuse when quote_id lineage is trusted",),
            confidence=1.0,
            source_job_id="source-1",
        )

        seeded = seed_context_from_checkpoint(ctx, checkpoint, cluster_seed_plan=plan)
    finally:
        _storage._seed_findings = original_seed

    assert seeded == 1
    assert any(entry.value == "QTE-001" for entry in ctx.evidence_candidates.query("quote_id"))
    assert not ctx.evidence_candidates.query("workflow_handle")
    _, rows = captured["seed"]
    assert rows[0]["function"] == "PR_BeginQuote"
