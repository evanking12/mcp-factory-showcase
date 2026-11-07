from __future__ import annotations

import json
import threading
from types import SimpleNamespace

from api.pipeline.core.helpers import (
    _build_ranked_fallback_probe_args,
    _classify_result_text,
    _merge_result_output_values,
    _ranked_param_candidates,
)
from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry, TIER_PRIOR_VERIFIED, TIER_RUNTIME
from api.pipeline.core.evidence_candidates import TIER_STATIC_DISCOVERY
from api.pipeline.s01_unlock import unlock_helpers
from api.pipeline.s01_unlock.unlock_helpers import _build_write_arg_candidates, _build_write_retry_plan
from api.pipeline.s03_reconcile import mc3_write_analysis as mc3
from api.pipeline.s05_enrichment import mc5_chain_reads as mc5
from api.pipeline.s06_gaps import mc6_final_unlock as mc6


def _payments_ctx() -> SimpleNamespace:
    ecr = EvidenceCandidateRegistry()
    ecr.seed_tier0()
    ecr.add("CUST-001", TIER_RUNTIME, "runtime:history", "customer_id", 0.99, "CP_GetTransactionHistory")
    ecr.add("PRO-SVC-ANNUAL", TIER_RUNTIME, "runtime:lookup", "sku", 0.99, "CP_LookupProduct")
    ecr.add("TXN-00000001-0000", TIER_RUNTIME, "runtime:void", "transaction_id", 0.99, "CP_VoidTransaction")
    return SimpleNamespace(
        job_id="job-1",
        vocab={"id_formats": ["CUST-001"], "binary_string_ids": ["PRO-SVC-ANNUAL"]},
        invocables=[
            {"name": "CP_Initialize", "parameters": []},
            {
                "name": "CP_ProcessPurchase",
                "parameters": [
                    {"name": "param_1", "json_type": "string", "description": "customer ID"},
                    {"name": "param_2", "json_type": "string", "description": "SKU string"},
                    {"name": "param_3", "json_type": "integer", "description": "quantity"},
                    {"name": "param_4", "json_type": "integer", "description": "discount in basis points"},
                    {"name": "param_5", "json_type": "integer", "direction": "out", "description": "authorization code output"},
                ],
            },
            {
                "name": "CP_ReserveStock",
                "parameters": [
                    {"name": "param_1", "json_type": "string", "description": "customer ID"},
                    {"name": "param_2", "json_type": "string", "description": "SKU string"},
                    {"name": "param_3", "json_type": "integer", "description": "quantity"},
                    {"name": "param_4", "json_type": "integer", "description": "hold minutes"},
                    {"name": "param_5", "json_type": "string", "direction": "out", "description": "reservation id output"},
                    {"name": "param_6", "json_type": "integer", "description": "buffer size"},
                ],
            },
        ],
        evidence_candidates=ecr,
        unlock_result={"unlocked": False},
        write_unlock_block="",
        sentinels={},
        dll_strings={},
        _state={},
        _lock=threading.Lock(),
        live_findings=[],
    )


def test_build_write_arg_candidates_uses_ranked_param_context() -> None:
    ctx = _payments_ctx()

    write_args, write_selection = _build_write_arg_candidates(ctx, max_attempts=2)

    purchase_args = write_args["CP_ProcessPurchase"][0]
    assert purchase_args["param_1"] == "CUST-001"
    assert purchase_args["param_2"] == "PRO-SVC-ANNUAL"
    assert purchase_args["param_3"] == 1
    assert write_selection["CP_ProcessPurchase"][0]["param_1"]["source"].startswith("evidence.")
    assert write_selection["CP_ProcessPurchase"][0]["param_2"]["source"].startswith("evidence.")


def test_mc5_post_verification_chains_success_findings_with_nonverified_labels(monkeypatch) -> None:
    ctx = _payments_ctx()
    findings = [
        {
            "function": "CP_GetTransactionHistory",
            "status": "success",
            "verification": "inferred",
            "working_call": {"param_1": "CUST-001", "param_3": 64},
        },
        {
            "function": "CP_LookupProduct",
            "status": "success",
            "verification": "inferred",
            "working_call": {"param_1": "PRO-SVC-ANNUAL", "param_3": 64},
        },
    ]
    captured: dict[str, object] = {}

    monkeypatch.setattr(mc5, "_load_findings", lambda _job_id: findings)

    def _fake_attempt(_ctx, _init_seqs, write_args, _label):
        captured["write_args"] = write_args
        return False

    monkeypatch.setattr(mc5, "_targeted_unlock_attempt", _fake_attempt)
    monkeypatch.setattr(mc5, "_persist_mc_decision", lambda _ctx, _mc_id, decision: captured.setdefault("decision", decision))

    mc5._mc5_post_verification(ctx)

    decision = captured["decision"]
    purchase_args = captured["write_args"]["CP_ProcessPurchase"][0]
    assert decision["action"] == "chain_read_outputs_to_write_inputs"
    assert "CP_ProcessPurchase" in decision["analysis"]["retryable_functions"]
    assert {row["function"] for row in decision["analysis"]["retry_plan"][:2]} == {
        "CP_ProcessPurchase",
        "CP_ReserveStock",
    }
    assert max(row["evidence_param_count"] for row in decision["analysis"]["retry_plan"]) >= 2
    assert decision["analysis"]["prerequisite_clusters"]["payment"] >= 1
    assert decision["analysis"]["prerequisite_clusters"]["inventory"] >= 1
    assert purchase_args["param_1"] == "CUST-001"
    assert purchase_args["param_2"] == "PRO-SVC-ANNUAL"


def test_mc5_prefers_mc3_retry_order_when_available(monkeypatch) -> None:
    ctx = _payments_ctx()
    findings = [
        {
            "function": "CP_GetTransactionHistory",
            "status": "success",
            "verification": "verified",
            "working_call": {"param_1": "CUST-001", "param_3": 64},
        },
    ]
    ctx._state["mc_decisions"] = {
        "mc3-post-reconcile": {
            "analysis": {
                "retry_plan": [
                    {"function": "CP_ReserveStock", "cluster": "inventory", "priority": 60},
                    {"function": "CP_ProcessPurchase", "cluster": "payment", "priority": 50},
                ],
                "cluster_hints": [
                    {"function": "CP_ReserveStock", "cluster": "inventory"},
                    {"function": "CP_ProcessPurchase", "cluster": "payment"},
                ],
            }
        }
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(mc5, "_load_findings", lambda _job_id: findings)
    monkeypatch.setattr(mc5, "_targeted_unlock_attempt", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(mc5, "_persist_mc_decision", lambda _ctx, _mc_id, decision: captured.setdefault("decision", decision))

    mc5._mc5_post_verification(ctx)

    decision = captured["decision"]
    retry_plan = decision["analysis"]["retry_plan"]
    assert retry_plan[0]["function"] == "CP_ReserveStock"
    assert decision["analysis"]["micro_coordinator_source"] == "live_mc3"
    assert decision["analysis"]["retry_rationale"]["checkpoint_recommended_boundary"] == "s02_probe"


def test_write_retry_plan_defers_cancel_reservation_without_reservation_id() -> None:
    plan = _build_write_retry_plan(
        {
            "CP_CancelReservation": [
                {"param_1": {"source": "function_context.id", "reason": "cancel-reservation style function"}}
            ],
            "CP_VoidTransaction": [
                {"transaction_id": {"source": "evidence.tier2.working_call:CP_VoidTransaction", "reason": "runtime txn id"}}
            ],
        },
        evidence_ids=["CUST-001", "TXN-00000001-0000"],
        id_formats=["CUST-001"],
    )

    by_fn = {row["function"]: row for row in plan}
    assert by_fn["CP_CancelReservation"]["required_runtime_id_kind"] == "reservation_id"
    assert by_fn["CP_CancelReservation"]["matching_runtime_id_available"] is False
    assert by_fn["CP_CancelReservation"]["fallback"] == "defer_to_gap_resolution"
    assert by_fn["CP_VoidTransaction"]["required_runtime_id_kind"] == "transaction_id"
    assert by_fn["CP_VoidTransaction"]["matching_runtime_id_available"] is True
    assert by_fn["CP_VoidTransaction"]["fallback"] == "retry_ranked_candidates"


def test_write_retry_plan_accepts_reservation_id_from_available_kind_override() -> None:
    plan = _build_write_retry_plan(
        {
            "CP_CancelReservation": [
                {"param_1": {"source": "evidence.tier2.runtime:CP_ReserveStock", "reason": "runtime reservation id"}}
            ],
        },
        evidence_ids=["CUST-001"],
        id_formats=["CUST-001"],
        available_id_kinds_override={"reservation_id", "customer_id"},
    )

    by_fn = {row["function"]: row for row in plan}
    assert by_fn["CP_CancelReservation"]["required_runtime_id_kind"] == "reservation_id"
    assert by_fn["CP_CancelReservation"]["matching_runtime_id_available"] is True
    assert by_fn["CP_CancelReservation"]["fallback"] == "retry_ranked_candidates"


def test_ranked_param_candidates_demote_generic_defaults_when_runtime_evidence_exists() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.seed_tier0()
    ecr.add("CUST-001", TIER_RUNTIME, "runtime:lookup_customer", "customer_id", 0.99, "CS_GetCustomerStatus")

    ranked = _ranked_param_candidates(
        "param_1",
        "string",
        "customer ID",
        {"id_formats": ["CUST-001"]},
        fn_name="CS_LookupCustomer",
        evidence=ecr,
    )

    assert ranked[0]["source"].startswith("evidence.")
    default_candidates = [row for row in ranked if str(row["source"]).startswith("default.")]
    assert default_candidates
    assert all(row["score"] <= 0.18 for row in default_candidates)
    assert any("stronger runtime evidence exists" in row["reason"] for row in default_candidates)


def test_ranked_param_candidates_skip_structured_integer_metadata_and_use_purchase_slot_heuristics() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.seed_tier0()
    ecr.add(
        {"param_name": "param_2", "ghidra_type": "ushort", "function": "CP_CalculateTotal"},
        TIER_RUNTIME,
        "ghidra.decompiler",
        "integer",
        0.99,
        "seed",
    )

    ranked = _ranked_param_candidates(
        "param_3",
        "integer",
        "integer input parameter",
        {"id_formats": ["CUST-001"]},
        fn_name="CP_ProcessPurchase",
        integer_slot_index=0,
        integer_slot_count=2,
        evidence=ecr,
    )

    assert ranked[0]["value"] == 1
    assert ranked[0]["source"] == "function_context.quantity"
    assert all(not isinstance(row["value"], dict) for row in ranked)


def test_build_ranked_fallback_probe_args_prefers_reserve_duration_for_second_integer_slot() -> None:
    invocable = {
        "name": "CP_ReserveStock",
        "parameters": [
            {"name": "param_1", "json_type": "string", "description": "input string parameter"},
            {"name": "param_2", "json_type": "string", "description": "input string parameter"},
            {"name": "param_3", "json_type": "integer", "description": "integer input parameter"},
            {"name": "param_4", "json_type": "integer", "description": "integer input parameter"},
            {"name": "param_5", "json_type": "string", "direction": "out", "description": "reservation id output"},
            {"name": "param_6", "json_type": "integer", "description": "buffer size"},
        ],
    }

    args, selection = _build_ranked_fallback_probe_args(
        invocable,
        {"id_formats": ["CUST-001"], "binary_string_ids": ["WDG-XL-BLU"]},
    )

    assert args["param_3"] == 1
    assert args["param_4"] == 30
    assert selection["param_3"]["source"] == "function_context.quantity"
    assert selection["param_4"]["source"] == "function_context.duration"


def test_build_ranked_fallback_probe_args_detects_discount_auth_token_from_decompiled_doc() -> None:
    invocable = {
        "name": "CP_ApplyBulkDiscount",
        "doc_comment": (
            "undefined8 CP_ApplyBulkDiscount(byte *param_1,uint param_2,byte *param_3)\n"
            "{\n"
            "  if ((param_1 != (byte *)0x0) && (param_3 != (byte *)0x0)) {\n"
            "    iVar2 = lstrlenA((LPCSTR)param_3);\n"
            "    if ((3 < iVar2) && (param_2 != 0)) {\n"
            "      bVar1 = *param_3;\n"
            "      bVar4 = 0;\n"
            "      do {\n"
            "        bVar4 = bVar4 ^ bVar1;\n"
            "        param_3 = param_3 + 1;\n"
            "        bVar1 = *param_3;\n"
            "      } while (bVar1 != 0);\n"
            "      if (bVar4 == 0xa5) {\n"
            "        uVar3 = FUN_180001f10(param_1);\n"
            "        *(uint *)(table + slot) = param_2;\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "}\n"
        ),
        "parameters": [
            {"name": "param_1", "json_type": "string", "description": "Input string parameter"},
            {"name": "param_2", "json_type": "integer", "description": "Integer input parameter"},
            {"name": "param_3", "json_type": "string", "description": "Input string parameter"},
        ],
    }

    args, selection = _build_ranked_fallback_probe_args(
        invocable,
        {"id_formats": ["CUST-001"], "binary_string_ids": ["ACC-USB-C", "WDG-XL-BLU"]},
    )

    xor_value = 0
    for b in args["param_3"].encode("utf-8"):
        xor_value ^= b

    assert args["param_1"] == "ACC-USB-C"
    assert selection["param_1"]["source"] == "function_context.sku"
    assert args["param_2"] == 5000
    assert selection["param_2"]["source"] == "function_context.amount"
    assert selection["param_3"]["source"] == "function_context.auth_token"
    assert xor_value == 0xA5


def test_ranked_param_candidates_demote_ghidra_enum_for_generic_numeric_slots() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.seed_tier0()
    ecr.add(1, TIER_STATIC_DISCOVERY, "ghidra.enum", "integer", 0.75, "seed")
    ecr.add(2, TIER_STATIC_DISCOVERY, "ghidra.enum", "integer", 0.7, "seed")

    ranked = _ranked_param_candidates(
        "param_4",
        "integer",
        "integer input parameter",
        {"id_formats": ["CUST-001"]},
        fn_name="CP_ReserveStock",
        integer_slot_index=1,
        integer_slot_count=3,
        evidence=ecr,
    )

    assert ranked[0]["value"] == 30
    assert ranked[0]["source"] == "function_context.duration"


def test_ranked_param_candidates_promote_prefix_matching_runtime_evidence_from_doc_hint() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.seed_tier0()
    ecr.add(
        "sp-preview-sp-operator-0-session-3644191560-gate",
        TIER_RUNTIME,
        "runtime:SP_PrepareReleasePreview",
        "order_id",
        0.99,
        "SP_PrepareReleasePreview",
    )
    ecr.add(
        "ACC-USB-C",
        TIER_RUNTIME,
        "runtime:static_id",
        "sku",
        0.99,
        "seed",
    )

    ranked = _ranked_param_candidates(
        "param_1",
        "string",
        "input string parameter",
        {"id_formats": ["ACC-USB-C"]},
        fn_name="SP_EmitReleaseAttestation",
        evidence=ecr,
        function_doc='if (strncmp(param_1,"sp-preview-",0xb) != 0) return -1;',
    )

    assert ranked[0]["value"] == "sp-preview-sp-operator-0-session-3644191560-gate"
    assert "required prefix sp-preview-" in ranked[0]["reason"]
    nonmatching = [
        row for row in ranked
        if isinstance(row["value"], str) and not row["value"].startswith("sp-preview-")
    ]
    assert nonmatching
    assert nonmatching[0]["score"] <= 0.34
    assert "does not satisfy required prefix sp-preview-" in nonmatching[0]["reason"]


def test_ranked_param_candidates_promote_canonical_auth_token_prefix_when_doc_has_no_strncmp_hint() -> None:
    ranked = _ranked_param_candidates(
        "operator_token",
        "string",
        "Unlock token hex returned by the fixture",
        {"id_formats": ["ACC-USB-C"], "binary_string_ids": ["ACC-USB-C"]},
        fn_name="SP_IssueReleaseHold",
        function_doc=(
            'Required preconditions: SP_OpenOperatorSession | Canonical args: '
            '{"amount_cents": 4200, "hold_len": 256, '
            '"operator_token": "sp-operator-ORD-001-session", '
            '"order_id": "ORD-001", "out_hold_token": "", '
            '"out_reservation_handle": "", "reservation_len": 256}'
        ),
    )

    assert ranked[0]["value"].startswith("sp-operator-")
    assert ranked[0]["source"] == "function_context.prefix"
    assert "required prefix sp-operator-" in ranked[0]["reason"]
    nonmatching = [
        row for row in ranked
        if isinstance(row["value"], str) and not row["value"].startswith("sp-operator-")
    ]
    assert nonmatching
    assert nonmatching[0]["score"] <= 0.16
    assert "does not satisfy required prefix sp-operator-" in nonmatching[0]["reason"]


def test_ranked_param_candidates_demote_generic_prior_evidence_when_discount_slot_has_stronger_context() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.seed_tier0()
    ecr.add(1, TIER_PRIOR_VERIFIED, "generic", "integer", 0.99, "seed")

    ranked = _ranked_param_candidates(
        "param_2",
        "integer",
        "integer input parameter",
        {"id_formats": ["CUST-001"], "binary_string_ids": ["ACC-USB-C"]},
        fn_name="CP_ApplyBulkDiscount",
        integer_slot_index=0,
        integer_slot_count=1,
        evidence=ecr,
    )

    assert ranked[0]["value"] == 5000
    assert ranked[0]["source"] == "function_context.amount"
    assert all(
        row["source"] != "evidence.tier3.generic"
        for row in ranked[:3]
    )


def test_mc3_post_reconcile_records_retry_candidates_for_uniform_sentinel(monkeypatch) -> None:
    ctx = _payments_ctx()
    probe_log = [
        {
            "function": "CP_ProcessPurchase",
            "tool": "CP_ProcessPurchase",
            "phase": "explore",
            "classification": {"has_return": True, "signed": -4},
        },
        {
            "function": "CP_ReserveStock",
            "tool": "CP_ReserveStock",
            "phase": "explore",
            "classification": {"has_return": True, "signed": -4},
        },
    ]
    captured: dict[str, object] = {}

    monkeypatch.setattr(mc3, "_download_blob", lambda *_args, **_kwargs: json.dumps(probe_log))

    def _fake_attempt(_ctx, _init_seqs, write_args, _label):
        captured["write_args"] = write_args
        return False

    monkeypatch.setattr(mc3, "_targeted_unlock_attempt", _fake_attempt)
    monkeypatch.setattr(mc3, "_persist_mc_decision", lambda _ctx, _mc_id, decision: captured.setdefault("decision", decision))

    mc3._mc3_post_reconcile(ctx)

    decision = captured["decision"]
    assert decision["analysis"]["mode"] == "uniform_sentinel"
    assert "CP_ProcessPurchase" in decision["analysis"]["retryable_functions"]
    assert decision["analysis"]["retry_plan"][0]["sentinel_codes"] == ["0xFFFFFFFC"]
    assert decision["analysis"]["prerequisite_clusters"]["inventory"] >= 1
    assert decision["analysis"]["candidate_examples"]["CP_ProcessPurchase"][0]["param_2"] == "PRO-SVC-ANNUAL"


def test_mc3_post_reconcile_coalesces_success_rows_and_preserves_merged_output_values(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-settlement",
        invocables=[
            {
                "name": "SP_VerifyReservedRelease",
                "parameters": [
                    {"name": "reservation_handle", "direction": "in", "type": "const char*"},
                    {"name": "preview_ticket", "direction": "in", "type": "const char*"},
                    {"name": "fee_quote_id", "direction": "in", "type": "const char*"},
                    {"name": "out_verification_ticket", "direction": "out", "type": "char*"},
                    {"name": "out_len", "direction": "in", "type": "DWORD"},
                ],
            },
        ],
        unlock_result={"unlocked": False},
        sentinels={},
        dll_strings={},
        vocab={},
        _lock=threading.Lock(),
        live_findings=[],
    )
    probe_log = [
        {
            "function": "SP_VerifyReservedRelease",
            "tool": "SP_VerifyReservedRelease",
            "phase": "explore",
            "args": {
                "reservation_handle": "sp-resv-ORD-001-64",
                "preview_ticket": "sp-preview-ORD-001-64-gate",
                "fee_quote_id": "sp-fee-ORD-001-64-quote",
                "out_verification_ticket": "",
                "out_len": 256,
            },
            "result_excerpt": "Returned: 0\nout_verification_ticket='sp-verify-ORD-001-64-reserved'",
            "classification": {"has_return": True, "signed": 0},
        },
        {
            "function": "SP_VerifyReservedRelease",
            "tool": "SP_VerifyReservedRelease",
            "phase": "explore",
            "args": {
                "reservation_handle": "sp-resv-ORD-001-64",
                "preview_ticket": "sp-preview-ORD-001-64-gate",
                "fee_quote_id": "sp-fee-ORD-001-64-quote",
                "out_verification_ticket": "sp-att-stale-100|packet=sp-att-stale-100",
                "out_len": 256,
            },
            "result_excerpt": "Returned: 0\nout_verification_ticket='sp-verify-ORD-001-64-reserved'",
            "classification": {"has_return": True, "signed": 0},
        },
    ]
    patched: list[tuple[str, dict]] = []
    captured: dict[str, object] = {}

    monkeypatch.setattr(mc3, "_download_blob", lambda *_args, **_kwargs: json.dumps(probe_log))
    monkeypatch.setattr(mc3, "_patch_finding", lambda _job_id, fn_name, patch: patched.append((fn_name, patch)))
    monkeypatch.setattr(mc3, "_persist_mc_decision", lambda _ctx, _mc_id, decision: captured.setdefault("decision", decision))

    mc3._mc3_post_reconcile(ctx)

    assert len(patched) == 1
    assert patched[0][0] == "SP_VerifyReservedRelease"
    assert patched[0][1]["working_call"]["out_verification_ticket"] == "sp-verify-ORD-001-64-reserved"
    assert "accidental success" not in patched[0][1]["finding"]
    assert len(ctx.live_findings) == 1
    assert ctx.live_findings[0]["working_call"]["out_verification_ticket"] == "sp-verify-ORD-001-64-reserved"
    assert captured["decision"]["analysis"]["functions"] == ["SP_VerifyReservedRelease"]


def test_mc3_post_reconcile_does_not_merge_output_values_from_truncated_result_excerpt(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-settlement",
        invocables=[
            {
                "name": "SP_VerifyReservedRelease",
                "parameters": [
                    {"name": "reservation_handle", "direction": "in", "type": "const char*"},
                    {"name": "preview_ticket", "direction": "in", "type": "const char*"},
                    {"name": "fee_quote_id", "direction": "in", "type": "const char*"},
                    {"name": "out_verification_ticket", "direction": "out", "type": "char*"},
                    {"name": "out_len", "direction": "in", "type": "DWORD"},
                ],
            },
        ],
        unlock_result={"unlocked": False},
        sentinels={},
        dll_strings={},
        vocab={},
        _lock=threading.Lock(),
        live_findings=[],
    )
    probe_log = [
        {
            "function": "SP_VerifyReservedRelease",
            "tool": "SP_VerifyReservedRelease",
            "phase": "explore",
            "args": {
                "reservation_handle": "sp-resv-ORD-001-64",
                "preview_ticket": "sp-preview-ORD-001-64-gate",
                "fee_quote_id": "sp-fee-ORD-001-64-quote",
                "out_verification_ticket": "",
                "out_len": 256,
            },
            "result_excerpt": "Returned: 0\nout_verification_ticket='sp-verify-ORD-001-64-reserved",
            "result_truncated": True,
            "classification": {"has_return": True, "signed": 0},
        },
    ]
    patched: list[tuple[str, dict]] = []
    captured: dict[str, object] = {}

    monkeypatch.setattr(mc3, "_download_blob", lambda *_args, **_kwargs: json.dumps(probe_log))
    monkeypatch.setattr(mc3, "_patch_finding", lambda _job_id, fn_name, patch: patched.append((fn_name, patch)))
    monkeypatch.setattr(mc3, "_persist_mc_decision", lambda _ctx, _mc_id, decision: captured.setdefault("decision", decision))

    mc3._mc3_post_reconcile(ctx)

    assert len(patched) == 1
    assert patched[0][0] == "SP_VerifyReservedRelease"
    assert patched[0][1]["working_call"]["out_verification_ticket"] == ""
    assert len(ctx.live_findings) == 1
    assert ctx.live_findings[0]["working_call"]["out_verification_ticket"] == ""
    assert captured["decision"]["analysis"]["functions"] == ["SP_VerifyReservedRelease"]


def test_classify_result_text_prefers_dll_specific_sentinel_meaning() -> None:
    classification = _classify_result_text(
        "Returned: -4 (= 0xFFFFFFFC)",
        sentinels={0xFFFFFFFC: "no stock available"},
    )

    assert classification["meaning"] == "no stock available"


def test_ranked_candidates_prefer_customer_evidence_for_lookup_customer_shape() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.seed_tier0()
    ecr.add("PRO-SVC-ANNUAL", TIER_RUNTIME, "runtime:lookup_product", "sku", 0.99, "CP_LookupProduct")
    ecr.add("CUST-001", TIER_RUNTIME, "runtime:lookup_customer", "customer_id", 0.99, "CS_GetCustomerStatus")

    invocable = {
        "name": "CS_LookupCustomer",
        "parameters": [
            {"name": "param_1", "json_type": "string", "description": "input string parameter"},
            {"name": "param_2", "json_type": "string", "direction": "out", "description": "customer record output"},
            {"name": "param_3", "json_type": "integer", "description": "buffer size"},
        ],
    }
    vocab = {
        "id_formats": ["CUST-001"],
        "binary_string_ids": ["PRO-SVC-ANNUAL"],
    }

    args, selection = _build_ranked_fallback_probe_args(invocable, vocab, evidence=ecr)

    assert args["param_1"] == "CUST-001"
    assert selection["param_1"]["source"].startswith("evidence.")
    assert selection["param_1"]["candidate_count"] >= 2


def test_mark_unlock_resolved_seeds_success_when_no_existing_finding(monkeypatch) -> None:
    ctx = _payments_ctx()
    ctx.unlock_result = {
        "unlocked": True,
        "sequence": [{"fn": "CP_Initialize", "args": {"param_1": 0}}],
        "write_fn_tested": "CP_ProcessPurchase",
        "write_fn_args": {
            "param_1": "CUST-001",
            "param_2": "PRO-SVC-ANNUAL",
            "param_3": 1,
            "param_4": 0,
        },
    }
    saved: list[dict] = []
    patched: list[tuple[str, dict]] = []

    monkeypatch.setattr(unlock_helpers, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(unlock_helpers, "_get_job_status", lambda _job_id: {})
    monkeypatch.setattr(unlock_helpers, "_persist_job_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(unlock_helpers, "_load_findings", lambda _job_id: [])
    monkeypatch.setattr(unlock_helpers, "_save_finding", lambda _job_id, entry: saved.append(entry))
    monkeypatch.setattr(unlock_helpers, "_patch_finding", lambda _job_id, fn_name, patch: patched.append((fn_name, patch)))
    monkeypatch.setattr(unlock_helpers, "_reprobe_write_functions_after_unlock", lambda *_args, **_kwargs: None)

    unlock_helpers._mark_unlock_resolved(ctx, "mc5-post-verification", "proof note")

    assert not patched
    assert saved
    assert saved[0]["function"] == "CP_ProcessPurchase"
    assert saved[0]["status"] == "success"
    assert saved[0]["verification"] == "verified"
    assert ctx.live_findings[-1]["function"] == "CP_ProcessPurchase"


def test_mark_unlock_resolved_patches_existing_finding(monkeypatch) -> None:
    ctx = _payments_ctx()
    ctx.unlock_result = {
        "unlocked": True,
        "sequence": [{"fn": "CP_Initialize", "args": {"param_1": 0}}],
        "write_fn_tested": "CP_ProcessPurchase",
        "write_fn_args": {
            "param_1": "CUST-001",
            "param_2": "PRO-SVC-ANNUAL",
            "param_3": 1,
            "param_4": 0,
        },
    }
    saved: list[dict] = []
    patched: list[tuple[str, dict]] = []

    monkeypatch.setattr(unlock_helpers, "_upload_to_blob", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(unlock_helpers, "_get_job_status", lambda _job_id: {})
    monkeypatch.setattr(unlock_helpers, "_persist_job_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        unlock_helpers,
        "_load_findings",
        lambda _job_id: [{"function": "CP_ProcessPurchase", "status": "error"}],
    )
    monkeypatch.setattr(unlock_helpers, "_save_finding", lambda _job_id, entry: saved.append(entry))
    monkeypatch.setattr(unlock_helpers, "_patch_finding", lambda _job_id, fn_name, patch: patched.append((fn_name, patch)))
    monkeypatch.setattr(unlock_helpers, "_reprobe_write_functions_after_unlock", lambda *_args, **_kwargs: None)

    unlock_helpers._mark_unlock_resolved(ctx, "mc5-post-verification", "proof note")

    assert not saved
    assert patched
    assert patched[0][0] == "CP_ProcessPurchase"
    assert patched[0][1]["status"] == "success"


def test_mc6_llm_unlock_sets_winning_sequence_before_persist(monkeypatch) -> None:
    ctx = _payments_ctx()
    captured: dict[str, object] = {}

    monkeypatch.setattr(mc6, "_load_findings", lambda _job_id: [])
    monkeypatch.setattr(mc6, "_llm_analyze_decompiled_code", lambda _invocables: [{"target_function": "CP_ProcessPurchase"}])
    monkeypatch.setattr(
        mc6,
        "_execute_llm_strategies",
        lambda *_args, **_kwargs: {
            "sequence": [{"fn": "CP_Initialize", "args": {}}],
            "write_fn_tested": "CP_ProcessPurchase",
            "write_fn_args": {
                "param_1": "CUST-001",
                "param_2": "PRO-SVC-ANNUAL",
                "param_3": 1,
                "param_4": 0,
            },
            "notes": "llm cracked write unlock",
        },
    )

    def _fake_mark_unlock_resolved(inner_ctx, trigger, notes):
        captured["trigger"] = trigger
        captured["notes"] = notes
        captured["sequence_at_mark"] = list(inner_ctx.unlock_result.get("sequence") or [])
        captured["write_fn_tested_at_mark"] = inner_ctx.unlock_result.get("write_fn_tested")
        captured["write_fn_args_at_mark"] = dict(inner_ctx.unlock_result.get("write_fn_args") or {})

    monkeypatch.setattr(mc6, "_mark_unlock_resolved", _fake_mark_unlock_resolved)
    monkeypatch.setattr(mc6, "_persist_mc_decision", lambda *_args, **_kwargs: None)

    mc6._mc6_post_gap_resolution(ctx)

    assert captured["trigger"] == "mc6-llm-code-reasoning"
    assert captured["notes"] == "llm cracked write unlock"
    assert captured["sequence_at_mark"] == [{"fn": "CP_Initialize", "args": {}}]
    assert captured["write_fn_tested_at_mark"] == "CP_ProcessPurchase"
    assert captured["write_fn_args_at_mark"]["param_1"] == "CUST-001"
    assert ctx.unlock_result["sequence"] == [{"fn": "CP_Initialize", "args": {}}]
    assert ctx.unlock_result["write_fn_tested"] == "CP_ProcessPurchase"


def test_merge_result_output_values_preserves_output_buffer_results() -> None:
    merged = _merge_result_output_values(
        {"param_1": "CUST-001", "param_2": "ACC-USB-C", "param_3": 1, "param_4": 1, "param_6": 50},
        "Returned: 0\nparam_5='RESV-12345678-0001'\nparam_7=2",
        {
            "param_5": {"name": "param_5", "type": "char *", "direction": "out"},
            "param_7": {"name": "param_7", "type": "DWORD *", "direction": "out"},
        },
    )

    assert merged["param_5"] == "RESV-12345678-0001"
    assert merged["param_7"] == 2
    assert merged["param_1"] == "CUST-001"


def test_merge_result_output_values_normalizes_annotated_numeric_outputs() -> None:
    merged = _merge_result_output_values(
        {"dwSessionHandle": "WFH-CUST-001-02", "pdwNonceOut": ""},
        "Returned: 0\npdwNonceOut=3911728039 (large uint — may be packed/float data or wrong buffer type)",
        {
            "pdwNonceOut": {"name": "pdwNonceOut", "type": "DWORD *", "direction": "out"},
        },
    )

    assert merged["pdwNonceOut"] == 3911728039


def test_merge_result_output_values_preserves_duplicate_output_labels() -> None:
    merged = _merge_result_output_values(
        {"session_handle": "WFH-CUST-001-02"},
        "Returned: 0\noutput_buffer='sp-hold-CUST-001-0001'\noutput_buffer__2='sp-resv-CUST-001-0001'",
        {
            "output_buffer": {"name": "output_buffer", "type": "char *", "direction": "out"},
        },
    )

    assert merged["output_buffer"] == "sp-hold-CUST-001-0001"
    assert merged["output_buffer__2"] == "sp-resv-CUST-001-0001"


def test_merge_result_output_values_treats_out_prefixed_slot_as_output_when_direction_is_wrong() -> None:
    merged = _merge_result_output_values(
        {"out_fee_quote_id": "sp-preview-ORD-001-64-gate", "out_len": 256},
        "Returned: 0\nout_fee_quote_id='sp-fee-ORD-001-64-quote'",
        {
            "out_fee_quote_id": {
                "name": "out_fee_quote_id",
                "type": "char*",
                "direction": "in",
                "description": "Fee quote identifier for the release, populated with a string value.",
            },
        },
    )

    assert merged["out_fee_quote_id"] == "sp-fee-ORD-001-64-quote"


def test_merge_result_output_values_flattens_single_field_numeric_output_structs() -> None:
    merged = _merge_result_output_values(
        {"out_attestation_nonce": "", "out_attestation_epoch": ""},
        'Returned: 0\nout_attestation_nonce={"field_0": 2809135136}\nout_attestation_epoch={"field_0": 20260408}',
        {
            "out_attestation_nonce": {
                "name": "out_attestation_nonce",
                "type": "uint32_t*",
                "resolved_type": "uint32_t*",
                "direction": "out",
                "json_type": "integer",
            },
            "out_attestation_epoch": {
                "name": "out_attestation_epoch",
                "type": "uint32_t*",
                "resolved_type": "uint32_t*",
                "direction": "out",
                "json_type": "integer",
            },
        },
    )

    assert merged["out_attestation_nonce"] == 2809135136
    assert merged["out_attestation_epoch"] == 20260408
