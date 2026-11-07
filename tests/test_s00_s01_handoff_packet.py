from __future__ import annotations

import json
import importlib
from types import SimpleNamespace

from api.pipeline.core import s00_s01_handoff

run_s00_module = importlib.import_module("api.pipeline.s00_setup")
s00_admission_handoff_module = importlib.import_module("api.pipeline.s00_setup.admission_handoff")
s00_baseline_truth_module = importlib.import_module("api.pipeline.s00_setup.baseline_truth")
s00_setup_baseline_module = importlib.import_module("api.pipeline.s00_setup.setup_baseline")
s00_status_module = importlib.import_module("api.pipeline.s00_setup.status")
s00_static_evidence_module = importlib.import_module("api.pipeline.s00_setup.static_evidence")
s00_static_enrichment_module = importlib.import_module("api.pipeline.s00_setup.static_enrichment")
s00_packet_module = importlib.import_module("api.pipeline.s00_setup.s01_handoff_packet")
s00_static_surface_module = importlib.import_module("api.pipeline.s00_setup.static_surface_extraction")
s00_vocab_prior_hints_module = importlib.import_module("api.pipeline.s00_setup.vocab_prior_hints")
run_s01_module = importlib.import_module("api.pipeline.s01_unlock.__init__")


def _install_s01_noop_env(monkeypatch) -> None:
    monkeypatch.setattr(run_s01_module, "_set_explore_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(run_s01_module, "_get_job_status", lambda _job_id: {})
    monkeypatch.setattr(run_s01_module, "_persist_job_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(run_s01_module, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(run_s01_module, "_patch_finding", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(run_s01_module, "_execute_tool", lambda *_args, **_kwargs: "")


def test_build_s00_s01_handoff_packet_persists_additive_packet(monkeypatch) -> None:
    uploaded: dict[str, bytes] = {}

    monkeypatch.setattr(
        s00_s01_handoff,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploaded.setdefault(blob_name, data),
    )

    ctx = SimpleNamespace(
        job_id="job-handoff",
        sentinels={0xFFFFFFFB: "write denied"},
        use_cases_text="contoso payments local replay control",
        vocab={
            "id_formats": ["CUST-001"],
            "error_codes": {"0xFFFFFFFB": "write denied"},
            "value_semantics": {"amount_cents": "payment amount in cents"},
        },
        dll_strings={"ids": ["CUST-001"], "emails": [], "all": ["CUST-001"]},
        static_analysis_result={
            "binary_strings": {"ids_found": ["CUST-001"], "emails_found": []},
            "iat_capabilities": {"categories": {"crypto": ["CryptAcquireContext"]}},
        },
        call_graph={"CS_Initialize": ["CS_ProcessPayment"]},
        ghidra_data_types=[{"name": "PAYMENT_RECORD"}],
        invocables=[
            {"name": "CS_Initialize"},
            {"name": "CS_ProcessPayment"},
            {"name": "CS_GetVersion"},
        ],
        s00_s01_handoff_packet={},
    )

    packet = s00_s01_handoff.build_s00_s01_handoff_packet(ctx)

    assert "job-handoff/s01_handoff_packet.json" in uploaded
    payload = json.loads(uploaded["job-handoff/s01_handoff_packet.json"].decode("utf-8"))
    assert payload["baseline_truth"]["sentinels"]["0xFFFFFFFB"] == "write denied"
    assert payload["coordination_decision"]["flow_outcome"] == "advance"
    assert payload["coordination_decision"]["admitted_forward"]["surface_inventory"]["dll_strings"]["ids"] == ["CUST-001"]
    assert "prior_hints" in payload["coordination_decision"]["admitted_forward"]
    assert packet["s01_targets"]["write_candidates"] == ["CS_ProcessPayment"]
    assert packet["s01_targets"]["quality"]["emitted_write_candidate_count"] == 1
    assert packet["coordination_decision"]["admission_quality"]["s01_target_quality"]["quality_flags"] == []
    assert (
        packet["coordination_decision"]["admission_quality"]["coordinator_review_seed"]["categories"]["target_narrowing"]
        == "usable_targets_present"
    )
    assert (
        packet["coordination_decision"]["admission_quality"]["coordinator_review_seed"]["categories"][
            "non_ownership_discipline"
        ]
        == "admission_guidance_only_not_semantic_truth"
    )


def test_handoff_packet_admits_selected_static_enrichment_fields(monkeypatch) -> None:
    uploaded: dict[str, bytes] = {}

    monkeypatch.setattr(
        s00_s01_handoff,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploaded.setdefault(blob_name, data),
    )

    ctx = SimpleNamespace(
        job_id="job-enrichment-packet",
        sentinels={0xFFFFFFFB: "write denied"},
        use_cases_text="payments",
        vocab={},
        dll_strings={"ids": [], "emails": [], "all": []},
        static_analysis_result={"binary_strings": {"ids_found": [], "emails_found": []}},
        call_graph={},
        ghidra_data_types=[],
        invocables=[
            {"name": "CS_Bootstrap"},
            {"name": "CS_ChargeCard"},
            {"name": "CS_ProcessPayment"},
        ],
        static_enrichment={
            "schema_version": 1,
            "source_status": {
                "static_analysis": "available",
                "ghidra_extras": "available",
                "headlessability": "unknown",
                "fallback_safe": True,
            },
            "callable_inventory": {
                "total": 3,
                "emitted": 3,
                "role_hints": [
                    {"name": "CS_Bootstrap", "role": "init", "confidence": 0.7},
                    {"name": "CS_ChargeCard", "role": "write", "confidence": 0.72},
                ],
            },
            "prerequisite_hints": {
                "entries": [
                    {
                        "function": "CS_ChargeCard",
                        "prerequisite_or_related": "CS_Bootstrap",
                        "kind": "preconditions",
                    }
                ],
                "strong_init_candidates": ["CS_Bootstrap"],
                "strong_write_candidates": ["CS_ChargeCard"],
            },
            "deferred_static": {
                "bounded_decompile_snippets": [
                    {
                        "function": "CS_ChargeCard",
                        "excerpt": "requires session",
                        "policy": "deferred_static_not_s01_truth",
                    }
                ],
                "xref_notes": [{"function": "CS_ChargeCard", "count": 1}],
                "data_type_preview": [{"name": "PAYMENT_RECORD", "kind": "struct"}],
            },
            "ambiguities": ["ghidra_headlessability_not_proven"],
            "admission_recommendation": {
                "usable_for_s01_targets": True,
                "admission_risk": "usable_static_hints",
            },
        },
        s00_s01_handoff_packet={},
    )

    packet = s00_s01_handoff.build_s00_s01_handoff_packet(ctx)

    summary = packet["surface_inventory"]["static_enrichment_summary"]
    assert summary["available"] is True
    assert summary["callable_total"] == 3
    assert summary["role_hint_count"] == 2
    assert summary["prerequisite_hint_count"] == 1
    assert summary["usable_for_s01_targets"] is True
    assert packet["deferred_static"]["static_enrichment"]["policy"] == "deferred_static_not_s01_truth"
    assert packet["deferred_static"]["static_enrichment"]["bounded_decompile_snippets"][0]["function"] == "CS_ChargeCard"
    assert "static enrichment: ghidra_headlessability_not_proven" in packet["ambiguity_register"]["notes"]
    assert packet["s01_targets"]["init_candidates"][0] == "CS_Bootstrap"
    assert packet["s01_targets"]["write_candidates"][0] == "CS_ChargeCard"
    assert "CS_ProcessPayment" in packet["s01_targets"]["write_candidates"]
    assert packet["s01_targets"]["quality"]["static_enrichment_init_candidate_count"] == 1
    assert packet["s01_targets"]["quality"]["static_enrichment_write_candidate_count"] == 1
    assert "static_enrichment_targets_admitted" in packet["s01_targets"]["quality"]["quality_flags"]
    admitted = packet["coordination_decision"]["admitted_forward"]
    assert admitted["surface_inventory"]["static_enrichment_summary"]["available"] is True
    assert "bounded_decompile_snippets" not in admitted["surface_inventory"]["static_enrichment_summary"]
    payload = json.loads(uploaded["job-enrichment-packet/s01_handoff_packet.json"].decode("utf-8"))
    assert payload["surface_inventory"]["static_enrichment_summary"]["available"] is True


def test_handoff_packet_ignores_unmatched_static_enrichment_targets(monkeypatch) -> None:
    monkeypatch.setattr(s00_s01_handoff, "_upload_to_blob", lambda *_args, **_kwargs: None)
    ctx = SimpleNamespace(
        job_id="job-enrichment-unmatched",
        sentinels={},
        use_cases_text="",
        vocab={},
        dll_strings={"ids": ["CUST-001"], "emails": [], "all": ["CUST-001"]},
        static_analysis_result={},
        call_graph={},
        ghidra_data_types=[],
        invocables=[{"name": "CS_ProcessPayment"}],
        static_enrichment={
            "prerequisite_hints": {
                "strong_init_candidates": ["CS_MissingInit"],
                "strong_write_candidates": ["CS_MissingWrite"],
            },
            "ambiguities": [],
        },
        s00_s01_handoff_packet={},
    )

    packet = s00_s01_handoff.build_s00_s01_handoff_packet(ctx)

    assert packet["s01_targets"]["write_candidates"] == ["CS_ProcessPayment"]
    assert packet["s01_targets"]["quality"]["unmatched_targets"] == ["CS_MissingInit", "CS_MissingWrite"]
    assert "static_enrichment_targets_unmatched" in packet["s01_targets"]["quality"]["quality_flags"]


def test_run_s00_parent_stage_stops_before_static_evidence(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(run_s00_module, "run_setup_baseline", lambda _ctx: calls.append("setup_baseline"))
    monkeypatch.setattr(run_s00_module, "run_static_evidence", lambda _ctx: calls.append("static_evidence"))
    monkeypatch.setattr(run_s00_module, "run_admission_handoff", lambda _ctx: calls.append("admission_handoff"))

    run_s00_module.run_s00(SimpleNamespace(job_id="job-s00"))

    assert calls == ["setup_baseline"]


def test_s00_substage_status_preserves_parent_stage(monkeypatch) -> None:
    status_updates: list[dict[str, object]] = []
    persisted: dict[str, object] = {}

    monkeypatch.setattr(
        s00_status_module,
        "_set_explore_status",
        lambda job_id, explored, total, message, *, stage="": status_updates.append(
            {
                "job_id": job_id,
                "explored": explored,
                "total": total,
                "message": message,
                "stage": stage,
            }
        ),
    )
    monkeypatch.setattr(
        s00_status_module,
        "_get_job_status",
        lambda _job_id: {"s00_substage_status": {}},
    )

    def fake_persist(_job_id, payload, **_kwargs):
        persisted.update(payload)
        return True

    monkeypatch.setattr(s00_status_module, "_persist_job_status", fake_persist)

    ctx = SimpleNamespace(job_id="job-status", total=7)

    s00_status_module.emit_s00_substage_status(
        ctx,
        "s00_static_evidence",
        "S-00B: Extracting static evidence...",
        state="start",
    )

    assert status_updates == [
        {
            "job_id": "job-status",
            "explored": 0,
            "total": 7,
            "message": "S-00B: Extracting static evidence...",
            "stage": "s00_static_evidence",
        }
    ]
    assert persisted["explore_parent_stage"] == "s00_setup"
    assert persisted["explore_substage"] == "s00_static_evidence"
    assert persisted["explore_substage_state"] == "start"
    assert persisted["explore_substage_label"] == "S-00B static_evidence"
    assert persisted["s00_substage_status"]["s00_static_evidence"]["parent_stage"] == "s00_setup"


def test_setup_baseline_boundary_delegates_to_baseline_and_vocab(monkeypatch) -> None:
    ctx = SimpleNamespace(job_id="job-setup-baseline")
    calls: list[str] = []

    monkeypatch.setattr(s00_setup_baseline_module, "emit_s00_substage_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        s00_setup_baseline_module,
        "run_baseline_truth",
        lambda arg: calls.append("baseline") if arg is ctx else None,
    )
    monkeypatch.setattr(
        s00_setup_baseline_module,
        "run_vocab_prior_hints",
        lambda arg: calls.append("vocab") if arg is ctx else None,
    )

    s00_setup_baseline_module.run_setup_baseline(ctx)

    assert calls == ["baseline", "vocab"]


def test_stage_owned_baseline_truth_preserves_sentinel_artifact(monkeypatch) -> None:
    uploaded: dict[str, bytes] = {}

    monkeypatch.setattr(s00_baseline_truth_module, "_set_explore_status", lambda *_args: None)
    monkeypatch.setattr(
        s00_baseline_truth_module,
        "_get_job_status",
        lambda _job_id: {"hints": "0xFFFFFFFB = write denied"},
    )
    monkeypatch.setattr(
        s00_baseline_truth_module,
        "_calibrate_sentinels",
        lambda invocables, client, model, job_id="", hints="": {0xFFFFFFFB: "write denied"},
    )
    monkeypatch.setattr(
        s00_baseline_truth_module,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploaded.setdefault(blob_name, data),
    )

    ctx = SimpleNamespace(
        job_id="job-baseline",
        total=1,
        invocables=[{"name": "CS_ProcessPayment"}],
        client=object(),
        model="test-model",
        sentinels={},
        sentinel_new_codes_this_run=0,
    )

    s00_baseline_truth_module.run_baseline_truth(ctx)

    assert ctx.sentinels == {0xFFFFFFFB: "write denied"}
    assert ctx.sentinel_new_codes_this_run == 1
    payload = json.loads(uploaded["job-baseline/sentinel_calibration.json"].decode("utf-8"))
    assert payload == {"0xFFFFFFFB": "write denied"}


def test_stage_owned_vocab_prior_hints_delegates_to_current_vocab_seed(monkeypatch) -> None:
    ctx = SimpleNamespace(job_id="job-vocab-wrapper")
    observed: dict[str, object] = {}

    def fake_vocab_seed(arg):
        observed["ctx"] = arg

    monkeypatch.setattr(s00_vocab_prior_hints_module, "_run_phase_0_vocab_seed", fake_vocab_seed)

    s00_vocab_prior_hints_module.run_vocab_prior_hints(ctx)

    assert observed["ctx"] is ctx


def test_static_evidence_boundary_delegates_to_static_and_enrichment(monkeypatch) -> None:
    ctx = SimpleNamespace(job_id="job-static-wrapper")
    calls: list[str] = []

    def fake_static(arg):
        assert arg is ctx
        calls.append("static")

    monkeypatch.setattr(s00_static_evidence_module, "emit_s00_substage_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(s00_static_evidence_module, "_run_phase_0_static", fake_static)
    monkeypatch.setattr(
        s00_static_evidence_module,
        "write_static_enrichment",
        lambda arg: calls.append("enrichment") if arg is ctx else None,
    )

    s00_static_evidence_module.run_static_evidence(ctx)

    assert calls == ["static", "enrichment"]


def test_legacy_static_surface_extraction_routes_through_static_evidence(monkeypatch) -> None:
    ctx = SimpleNamespace(job_id="job-static-legacy-wrapper")
    calls: list[str] = []

    monkeypatch.setattr(
        s00_static_surface_module,
        "run_static_evidence",
        lambda arg: calls.append("static_evidence") if arg is ctx else None,
    )

    s00_static_surface_module.run_static_surface_extraction(ctx)

    assert calls == ["static_evidence"]


def test_static_enrichment_artifact_serializes_with_missing_ghidra(monkeypatch) -> None:
    uploaded: dict[str, bytes] = {}
    monkeypatch.setattr(
        s00_static_enrichment_module,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploaded.setdefault(blob_name, data),
    )
    ctx = SimpleNamespace(
        job_id="job-static-enrichment-fallback",
        invocables=[
            {"name": "CS_GetVersion", "parameters": []},
            {"name": "CS_ProcessPayment", "parameters": [{"name": "customer_id", "direction": "in"}]},
        ],
        static_analysis_result={},
        call_graph={},
        ghidra_data_types=[],
    )

    artifact = s00_static_enrichment_module.write_static_enrichment(ctx)

    assert ctx.static_enrichment is artifact
    payload = json.loads(uploaded["job-static-enrichment-fallback/static_enrichment.json"].decode("utf-8"))
    assert payload["schema_version"] == 1
    assert payload["source_status"]["ghidra_extras"] == "absent"
    assert payload["source_status"]["fallback_safe"] is True
    assert "ghidra_extras_absent" in payload["ambiguities"]
    assert payload["callable_inventory"]["total"] == 2
    assert payload["admission_recommendation"]["usable_for_s01_targets"] is True
    assert payload["admission_recommendation"]["admitted_target_names"] == ["CS_ProcessPayment"]


def test_static_enrichment_records_callable_inventory_and_prerequisites(monkeypatch) -> None:
    uploaded: dict[str, bytes] = {}
    monkeypatch.setattr(
        s00_static_enrichment_module,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploaded.setdefault(blob_name, data),
    )
    ctx = SimpleNamespace(
        job_id="job-static-enrichment-rich",
        invocables=[
            {
                "name": "CS_OpenSession",
                "parameters": [
                    {
                        "name": "session",
                        "direction": "out",
                        "_ghidra_provenance": {"direction": {"confidence": 0.8}},
                    }
                ],
                "call_graph_callees": ["CS_ProcessPayment"],
                "_ghidra_extras": {
                    "preconditions": ["operator session must be open"],
                    "xrefs": ["CALL CS_OpenSession -> CS_ProcessPayment"],
                    "decompile": "int CS_OpenSession(void) { /* initialize session handle */ return 0; }",
                },
            },
            {
                "name": "CS_ProcessPayment",
                "parameters": [{"name": "amount_cents", "direction": "in"}],
                "_ghidra_extras": {"references": ["uses g_session_ready"]},
            },
        ],
        static_analysis_result={"binary_strings": {"ids_found": ["CUST-001"]}},
        call_graph={"CS_OpenSession": ["CS_ProcessPayment"]},
        ghidra_data_types=[{"name": "PAYMENT_RECORD", "kind": "struct"}],
    )

    artifact = s00_static_enrichment_module.write_static_enrichment(ctx)

    assert "job-static-enrichment-rich/static_enrichment.json" in uploaded
    assert artifact["source_status"]["ghidra_extras"] == "available"
    assert artifact["source_status"]["ghidra_provenance_invocables"] == 1
    assert artifact["callable_inventory"]["provenance"]["call_graph_functions"] == 1
    assert artifact["callable_inventory"]["role_hints"][0]["name"] == "CS_OpenSession"
    assert "CS_OpenSession" in artifact["prerequisite_hints"]["strong_init_candidates"]
    assert "CS_ProcessPayment" in artifact["prerequisite_hints"]["strong_write_candidates"]
    prereq_kinds = {entry["kind"] for entry in artifact["prerequisite_hints"]["entries"]}
    assert {"call_graph_edge", "preconditions"}.issubset(prereq_kinds)
    assert artifact["deferred_static"]["bounded_decompile_snippets"][0]["policy"] == "deferred_static_not_s01_truth"
    assert artifact["deferred_static"]["data_type_preview"] == [{"name": "PAYMENT_RECORD", "kind": "struct"}]
    assert "ghidra_headlessability_not_proven" in artifact["ambiguities"]


def test_admission_handoff_boundary_delegates_to_shared_builder(monkeypatch) -> None:
    ctx = SimpleNamespace(job_id="job-wrapper")
    observed: dict[str, object] = {}

    def fake_builder(arg):
        observed["ctx"] = arg
        return {"packet_version": "test"}

    monkeypatch.setattr(s00_admission_handoff_module, "emit_s00_substage_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(s00_admission_handoff_module, "build_s00_s01_handoff_packet", fake_builder)

    assert s00_admission_handoff_module.run_admission_handoff(ctx) == {"packet_version": "test"}
    assert observed["ctx"] is ctx


def test_legacy_packet_producer_routes_through_admission_handoff(monkeypatch) -> None:
    ctx = SimpleNamespace(job_id="job-legacy-wrapper")
    observed: dict[str, object] = {}

    def fake_admission_handoff(arg):
        observed["ctx"] = arg
        return {"packet_version": "legacy-test"}

    monkeypatch.setattr(s00_packet_module, "run_admission_handoff", fake_admission_handoff)

    assert s00_packet_module.build_s01_handoff_packet(ctx) == {"packet_version": "legacy-test"}
    assert observed["ctx"] is ctx


def test_run_s01_consumes_admitted_slice_before_probe(monkeypatch) -> None:
    packet = {
        "coordination_decision": {
            "admitted_forward": {
                "baseline_truth": {
                    "sentinels": {"0xFFFFFFFB": "write denied"},
                },
                "surface_inventory": {
                    "dll_strings": {"ids": ["CUST-PACKET"], "emails": [], "all": ["CUST-PACKET"]},
                },
                "prior_hints": {
                    "id_formats": ["CUST-PACKET"],
                    "error_codes": {"0xFFFFFFFB": "write denied"},
                },
                "s01_targets": {
                    "write_candidates": ["CS_ProcessPayment"],
                },
            },
        },
        "s01_targets": {"write_candidates": ["CS_ProcessPayment"]},
    }

    _install_s01_noop_env(monkeypatch)
    monkeypatch.setattr(
        run_s01_module,
        "admit_s00_s01_handoff",
        lambda ctx: {
            "packet": packet,
            "vocab": {"id_formats": ["CUST-PACKET"], "error_codes": {"0xFFFFFFFB": "write denied"}},
            "dll_strings": {"ids": ["CUST-PACKET"], "emails": [], "all": ["CUST-PACKET"]},
            "sentinels": {0xFFFFFFFB: "write denied"},
            "s01_targets": {"write_candidates": ["CS_ProcessPayment"]},
        },
    )

    captured: dict[str, object] = {}

    def fake_probe(invocables, dll_strings, vocab):
        captured["invocables"] = invocables
        captured["dll_strings"] = dll_strings
        captured["vocab"] = vocab
        return {
            "unlocked": False,
            "sequence": [],
            "write_fn_tested": None,
            "notes": "fixture",
        }

    monkeypatch.setattr(run_s01_module, "_probe_write_unlock", fake_probe)

    ctx = SimpleNamespace(
        job_id="job-s01",
        total=1,
        invocables=[
            {"name": "CS_ProcessPayment"},
            {"name": "CS_Initialize"},
        ],
        dll_strings={"ids": ["LEGACY-ID"], "emails": [], "all": ["LEGACY-ID"]},
        vocab={"id_formats": ["LEGACY-ID"]},
        sentinels={},
        unlock_result={"unlocked": False, "sequence": [], "notes": "not attempted"},
        write_unlock_block="",
        init_invocables=[],
        already_explored=set(),
        live_findings=[],
        _prior_session={},
        s00_s01_handoff_packet={},
    )

    run_s01_module.run_s01(ctx)

    assert captured["dll_strings"] == {"ids": ["CUST-PACKET"], "emails": [], "all": ["CUST-PACKET"]}
    assert captured["vocab"] == {
        "id_formats": ["CUST-PACKET"],
        "error_codes": {"0xFFFFFFFB": "write denied"},
    }
    assert ctx.sentinels[0xFFFFFFFB] == "write denied"


def test_run_s01_prioritizes_admitted_targets_before_probe(monkeypatch) -> None:
    _install_s01_noop_env(monkeypatch)
    monkeypatch.setattr(
        run_s01_module,
        "admit_s00_s01_handoff",
        lambda ctx: {
            "packet": {"packet_version": "1.0.0"},
            "vocab": ctx.vocab,
            "dll_strings": ctx.dll_strings,
            "sentinels": ctx.sentinels,
            "s01_targets": {
                "init_candidates": ["CS_TargetInitialize"],
                "write_candidates": ["CS_TargetProcessPayment"],
            },
        },
    )

    captured: dict[str, object] = {}

    def fake_probe(invocables, dll_strings, vocab):
        captured["invocable_names"] = [inv["name"] for inv in invocables]
        return {
            "unlocked": False,
            "sequence": [],
            "write_fn_tested": None,
            "notes": "fixture",
        }

    monkeypatch.setattr(run_s01_module, "_probe_write_unlock", fake_probe)

    ctx = SimpleNamespace(
        job_id="job-target-order",
        total=1,
        invocables=[
            {"name": "CS_LegacyInitialize"},
            {"name": "CS_LegacyProcessPayment"},
            {"name": "CS_TargetInitialize"},
            {"name": "CS_TargetProcessPayment"},
            {"name": "CS_GetVersion"},
        ],
        dll_strings={"ids": ["LEGACY-ID"], "emails": [], "all": ["LEGACY-ID"]},
        vocab={"id_formats": ["LEGACY-ID"]},
        sentinels={},
        unlock_result={"unlocked": False, "sequence": [], "notes": "not attempted"},
        write_unlock_block="",
        init_invocables=[],
        already_explored=set(),
        live_findings=[],
        _prior_session={},
        s00_s01_handoff_packet={},
    )

    run_s01_module.run_s01(ctx)

    assert captured["invocable_names"] == [
        "CS_TargetInitialize",
        "CS_TargetProcessPayment",
        "CS_LegacyInitialize",
        "CS_LegacyProcessPayment",
        "CS_GetVersion",
    ]
    assert [inv["name"] for inv in ctx.invocables] == [
        "CS_LegacyInitialize",
        "CS_LegacyProcessPayment",
        "CS_TargetInitialize",
        "CS_TargetProcessPayment",
        "CS_GetVersion",
    ]


def test_s01_target_prioritization_ignores_unmatched_and_empty_targets() -> None:
    invocables = [
        {"name": "CS_LegacyInitialize"},
        {"name": "CS_TargetProcessPayment"},
        {"name": "CS_GetVersion"},
    ]

    unmatched = run_s01_module._prioritize_invocables_for_s01_targets(
        invocables,
        {
            "init_candidates": ["CS_DoesNotExist"],
            "write_candidates": ["CS_AlsoMissing"],
        },
    )
    empty = run_s01_module._prioritize_invocables_for_s01_targets(invocables, {})

    assert [inv["name"] for inv in unmatched] == [
        "CS_LegacyInitialize",
        "CS_TargetProcessPayment",
        "CS_GetVersion",
    ]
    assert [inv["name"] for inv in empty] == [
        "CS_LegacyInitialize",
        "CS_TargetProcessPayment",
        "CS_GetVersion",
    ]


def test_run_s01_falls_back_cleanly_when_packet_blob_missing(monkeypatch) -> None:
    _install_s01_noop_env(monkeypatch)
    monkeypatch.setattr(
        s00_s01_handoff,
        "_download_blob",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    captured: dict[str, object] = {}

    def fake_probe(invocables, dll_strings, vocab):
        captured["invocable_names"] = [inv["name"] for inv in invocables]
        captured["dll_strings"] = dll_strings
        captured["vocab"] = vocab
        return {
            "unlocked": False,
            "sequence": [],
            "write_fn_tested": None,
            "notes": "fixture",
        }

    monkeypatch.setattr(run_s01_module, "_probe_write_unlock", fake_probe)

    ctx = SimpleNamespace(
        job_id="job-missing",
        total=1,
        invocables=[{"name": "CS_ProcessPayment"}],
        dll_strings={"ids": ["LEGACY-ID"], "emails": [], "all": ["LEGACY-ID"]},
        vocab={"id_formats": ["LEGACY-ID"], "value_semantics": {"amount_cents": "legacy"}},
        sentinels={0xFFFFFFFF: "legacy fail"},
        unlock_result={"unlocked": False, "sequence": [], "notes": "not attempted"},
        write_unlock_block="",
        init_invocables=[],
        already_explored=set(),
        live_findings=[],
        _prior_session={},
        s00_s01_handoff_packet={},
    )

    run_s01_module.run_s01(ctx)

    assert captured["dll_strings"] == {"ids": ["LEGACY-ID"], "emails": [], "all": ["LEGACY-ID"]}
    assert captured["vocab"] == {
        "id_formats": ["LEGACY-ID"],
        "value_semantics": {"amount_cents": "legacy"},
    }
    assert captured["invocable_names"] == ["CS_ProcessPayment"]
    assert ctx.sentinels == {0xFFFFFFFF: "legacy fail"}


def test_run_s01_falls_back_cleanly_when_packet_blob_is_malformed(monkeypatch) -> None:
    _install_s01_noop_env(monkeypatch)
    monkeypatch.setattr(
        s00_s01_handoff,
        "_download_blob",
        lambda *_args, **_kwargs: b"{not-json",
    )

    captured: dict[str, object] = {}

    def fake_probe(invocables, dll_strings, vocab):
        captured["invocable_names"] = [inv["name"] for inv in invocables]
        captured["dll_strings"] = dll_strings
        captured["vocab"] = vocab
        return {
            "unlocked": False,
            "sequence": [],
            "write_fn_tested": None,
            "notes": "fixture",
        }

    monkeypatch.setattr(run_s01_module, "_probe_write_unlock", fake_probe)

    ctx = SimpleNamespace(
        job_id="job-malformed",
        total=1,
        invocables=[{"name": "CS_ProcessPayment"}],
        dll_strings={"ids": ["LEGACY-ID"], "emails": [], "all": ["LEGACY-ID"]},
        vocab={"id_formats": ["LEGACY-ID"], "value_semantics": {"amount_cents": "legacy"}},
        sentinels={0xFFFFFFFF: "legacy fail"},
        unlock_result={"unlocked": False, "sequence": [], "notes": "not attempted"},
        write_unlock_block="",
        init_invocables=[],
        already_explored=set(),
        live_findings=[],
        _prior_session={},
        s00_s01_handoff_packet={},
    )

    run_s01_module.run_s01(ctx)

    assert captured["dll_strings"] == {"ids": ["LEGACY-ID"], "emails": [], "all": ["LEGACY-ID"]}
    assert captured["vocab"] == {
        "id_formats": ["LEGACY-ID"],
        "value_semantics": {"amount_cents": "legacy"},
    }
    assert captured["invocable_names"] == ["CS_ProcessPayment"]
    assert ctx.sentinels == {0xFFFFFFFF: "legacy fail"}


def test_admitted_slice_merges_partial_packet_without_clobbering_legacy_state() -> None:
    ctx = SimpleNamespace(
        job_id="job-merge",
        s00_s01_handoff_packet={
            "coordination_decision": {
                "admitted_forward": {
                    "baseline_truth": {
                        "sentinels": {"0xFFFFFFFB": "write denied"},
                    },
                    "prior_hints": {
                        "error_codes": {"0xFFFFFFFB": "write denied"},
                    },
                },
            },
        },
        vocab={
            "id_formats": ["LEGACY-ID"],
            "value_semantics": {"amount_cents": "legacy semantic"},
            "error_codes": {"0xFFFFFFFF": "legacy fail"},
        },
        dll_strings={"ids": ["LEGACY-ID"], "emails": [], "all": ["LEGACY-ID"]},
        sentinels={0xFFFFFFFF: "legacy fail"},
    )

    admitted = s00_s01_handoff.admit_s00_s01_handoff(ctx)

    assert admitted["vocab"]["id_formats"] == ["LEGACY-ID"]
    assert admitted["vocab"]["value_semantics"] == {"amount_cents": "legacy semantic"}
    assert admitted["vocab"]["error_codes"] == {"0xFFFFFFFB": "write denied"}
    assert admitted["sentinels"][0xFFFFFFFF] == "legacy fail"
    assert admitted["sentinels"][0xFFFFFFFB] == "write denied"


def test_build_thin_packet_still_serializes_structurally(monkeypatch) -> None:
    uploaded: dict[str, bytes] = {}

    monkeypatch.setattr(
        s00_s01_handoff,
        "_upload_to_blob",
        lambda _container, blob_name, data: uploaded.setdefault(blob_name, data),
    )

    ctx = SimpleNamespace(
        job_id="job-thin",
        sentinels={},
        use_cases_text="",
        vocab={},
        dll_strings={},
        static_analysis_result={},
        call_graph={},
        ghidra_data_types=[],
        invocables=[],
        s00_s01_handoff_packet={},
    )

    packet = s00_s01_handoff.build_s00_s01_handoff_packet(ctx)

    assert "review_verdict" in packet
    assert "coordination_decision" in packet
    assert "ambiguity_register" in packet
    assert packet["review_verdict"]["contract_met"] is False
    assert "static ids surface is thin" in packet["coordination_decision"]["admission_risk"]
    assert "no calibrated sentinels available" in packet["coordination_decision"]["admission_risk"]
    assert "static analysis result unavailable" in packet["coordination_decision"]["admission_risk"]
    assert "s01 target quality flag: no_init_candidates" in packet["coordination_decision"]["admission_risk"]
    assert "s01 target quality flag: no_write_candidates" in packet["coordination_decision"]["admission_risk"]
    assert packet["coordination_decision"]["admission_quality"]["s01_target_quality"]["quality_flags"] == [
        "no_init_candidates",
        "no_write_candidates",
        "no_focus_ids",
    ]
    assert (
        packet["coordination_decision"]["admission_quality"]["coordinator_review_seed"]["categories"]["target_narrowing"]
        == "target_set_thin"
    )
    assert "job-thin/s01_handoff_packet.json" in uploaded


def test_packet_target_classification_remains_bounded(monkeypatch) -> None:
    monkeypatch.setattr(s00_s01_handoff, "_upload_to_blob", lambda *_args, **_kwargs: None)

    ctx = SimpleNamespace(
        job_id="job-bounded",
        sentinels={0xFFFFFFFB: "write denied"},
        use_cases_text="contoso",
        vocab={},
        dll_strings={"ids": ["CUST-001"], "emails": [], "all": ["CUST-001"]},
        static_analysis_result={"binary_strings": {"ids_found": ["CUST-001"], "emails_found": []}},
        call_graph={},
        ghidra_data_types=[],
        invocables=(
            [{"name": f"CS_Initialize_{idx}"} for idx in range(30)]
            + [{"name": f"CS_ProcessPayment_{idx}"} for idx in range(30)]
        ),
        s00_s01_handoff_packet={},
    )

    packet = s00_s01_handoff.build_s00_s01_handoff_packet(ctx)

    assert len(packet["s01_targets"]["init_candidates"]) == 12
    assert len(packet["s01_targets"]["write_candidates"]) == 12
    assert packet["s01_targets"]["quality"]["raw_init_candidate_count"] == 30
    assert packet["s01_targets"]["quality"]["raw_write_candidate_count"] == 30
    assert packet["s01_targets"]["quality"]["target_cap_applied"] is True
    assert "target_cap_applied" in packet["s01_targets"]["quality"]["quality_flags"]
    assert (
        packet["coordination_decision"]["admission_quality"]["coordinator_review_seed"]["categories"][
            "admission_precision"
        ]
        == "cap_applied_review_breadth"
    )
