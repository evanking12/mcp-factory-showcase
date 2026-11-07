from __future__ import annotations

import json
from types import SimpleNamespace

from api.pipeline.s05_enrichment import verify as verify_mod


def _make_ctx() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-stateful",
        _state={"explored": 7},
        total=7,
        init_invocables=[],
        sentinels={},
        inv_map={
            "soundtouch_createInstance": {"name": "soundtouch_createInstance", "parameters": []},
            "soundtouch_setChannels": {"name": "soundtouch_setChannels", "parameters": [{"name": "param_1"}, {"name": "param_2"}]},
            "soundtouch_setSampleRate": {"name": "soundtouch_setSampleRate", "parameters": [{"name": "param_1"}, {"name": "param_2"}]},
            "soundtouch_putSamples_i16": {"name": "soundtouch_putSamples_i16", "parameters": [{"name": "param_1"}, {"name": "param_2"}, {"name": "param_3"}]},
            "soundtouch_numUnprocessedSamples": {"name": "soundtouch_numUnprocessedSamples", "parameters": [{"name": "param_1"}]},
            "soundtouch_flush": {"name": "soundtouch_flush", "parameters": [{"name": "param_1"}]},
            "soundtouch_getVersionId": {"name": "soundtouch_getVersionId", "parameters": []},
        },
    )


def _soundtouch_findings() -> list[dict]:
    return [
        {
            "function": "soundtouch_createInstance",
            "status": "success",
            "working_call": {},
        },
        {
            "function": "soundtouch_putSamples_i16",
            "status": "success",
            "working_call": {
                "param_1": 111111,
                "param_2": [0, 512, -512, 1024],
                "param_3": 2,
            },
        },
        {
            "function": "soundtouch_numUnprocessedSamples",
            "status": "success",
            "working_call": {
                "param_1": 0,
            },
        },
        {
            "function": "soundtouch_setSampleRate",
            "status": "error",
            "working_call": None,
        },
    ]


def _soundtouch_probe_log() -> list[dict]:
    return [
        {
            "phase": "lineage_preflight",
            "function": "soundtouch_setSampleRate",
            "args": {"param_1": 222222, "param_2": 44100},
            "result_excerpt": "Returned: 2867",
            "probe_id": "soundtouch_setSampleRate:lineage_preflight",
            "classification": {
                "has_return": True,
                "signed": 2867,
                "format_guess": "custom_positive_status_or_data",
            },
        },
        {
            "phase": "deterministic_fallback",
            "function": "soundtouch_setSampleRate",
            "args": {"param_1": 333333, "param_2": 48000},
            "result_excerpt": "Returned: 3120",
            "probe_id": "soundtouch_setSampleRate:fb:1",
            "classification": {
                "has_return": True,
                "signed": 3120,
                "format_guess": "custom_positive_status_or_data",
            },
        },
        {
            "phase": "structured_preflight_prereq",
            "function": "soundtouch_createInstance",
            "args": {},
            "result_excerpt": "Returned: 111111",
            "probe_id": "soundtouch_putSamples_i16:structured_preflight:prereq:soundtouch_createInstance",
            "classification": {
                "has_return": True,
                "signed": 111111,
                "format_guess": "custom_positive_status_or_data",
            },
        },
        {
            "phase": "structured_preflight_prereq",
            "function": "soundtouch_setChannels",
            "args": {"param_1": 111111, "param_2": 2},
            "result_excerpt": "Returned: 1",
            "probe_id": "soundtouch_putSamples_i16:structured_preflight:prereq:soundtouch_setChannels",
            "classification": {
                "has_return": True,
                "signed": 1,
                "format_guess": "custom_positive_status_or_data",
            },
        },
        {
            "phase": "structured_preflight_prereq",
            "function": "soundtouch_setSampleRate",
            "args": {"param_1": 111111, "param_2": 44100},
            "result_excerpt": "Returned: 2867",
            "probe_id": "soundtouch_putSamples_i16:structured_preflight:prereq:soundtouch_setSampleRate",
            "classification": {
                "has_return": True,
                "signed": 2867,
                "format_guess": "custom_positive_status_or_data",
            },
        },
    ]


def test_build_stateful_candidates_prefers_lineage_probe() -> None:
    ctx = _make_ctx()
    findings = _soundtouch_findings()
    probe_log = _soundtouch_probe_log()

    candidates = verify_mod._build_stateful_candidates(ctx, findings, probe_log)  # noqa: SLF001

    assert candidates
    candidate = next(c for c in candidates if c["function"] == "soundtouch_setSampleRate")
    assert candidate["source_row"]["phase"] == "lineage_preflight"
    assert candidate["candidate_source"] == "probe_log"


def test_stateful_verifier_promotes_when_downstream_effect_is_observed(monkeypatch) -> None:
    findings = _soundtouch_findings()
    uploads: dict[str, dict] = {}
    patched: list[tuple[str, dict]] = []
    calls: list[tuple[str, dict]] = []
    create_counter = {"value": 0}
    sessions: dict[int, dict[str, object]] = {}

    def fake_execute(inv: dict, args: dict) -> str:
        fn = inv["name"]
        call_args = dict(args or {})
        calls.append((fn, call_args))
        if fn == "soundtouch_createInstance":
            create_counter["value"] += 1
            handle = 9000 + create_counter["value"]
            sessions[handle] = {"channels": False, "sample_rate": False, "payload": False}
            return f"Returned: {handle}"
        handle = int(call_args.get("param_1") or 0)
        session = sessions.setdefault(handle, {"channels": False, "sample_rate": False, "payload": False})
        if fn == "soundtouch_setChannels":
            session["channels"] = True
            return "Returned: 1"
        if fn == "soundtouch_setSampleRate":
            session["sample_rate"] = True
            return "Returned: 2867"
        if fn == "soundtouch_putSamples_i16":
            ok = bool(session.get("channels")) and bool(session.get("sample_rate"))
            session["payload"] = ok
            return "Returned: 0" if ok else "Returned: 16"
        if fn == "soundtouch_flush":
            return "Returned: 0"
        if fn == "soundtouch_numUnprocessedSamples":
            return "Returned: 4" if session.get("payload") else "Returned: 0"
        raise AssertionError(f"unexpected function {fn}")

    monkeypatch.setattr(verify_mod, "_load_findings", lambda job_id: findings)
    monkeypatch.setattr(
        verify_mod,
        "_download_blob",
        lambda container, path: json.dumps(_soundtouch_probe_log()).encode("utf-8"),
    )
    monkeypatch.setattr(verify_mod, "_execute_tool", fake_execute)
    monkeypatch.setattr(verify_mod, "_set_explore_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(verify_mod, "_get_job_status", lambda job_id: {"status": "done"})
    monkeypatch.setattr(verify_mod, "_persist_job_status", lambda job_id, payload: None)
    monkeypatch.setattr(
        verify_mod,
        "_upload_to_blob",
        lambda container, path, payload: uploads.setdefault(path, json.loads(payload.decode("utf-8"))),
    )
    monkeypatch.setattr(
        verify_mod,
        "_patch_finding",
        lambda job_id, fn_name, patch: patched.append((fn_name, patch)),
    )

    ctx = _make_ctx()
    verify_mod._run_phase_7b_verify_enrichment(ctx)  # noqa: SLF001

    promoted = [patch for fn, patch in patched if fn == "soundtouch_setSampleRate" and patch.get("status") == "success"]
    assert promoted
    assert promoted[0]["working_call"]["param_2"] == 44100
    report = uploads["job-stateful/verification-report.json"]
    stateful_entry = next(entry for entry in report["entries"] if entry["function"] == "soundtouch_setSampleRate")
    assert stateful_entry["verification_mode"] == "stateful_mutator"
    assert stateful_entry["promotion_decision"] == "promoted"
    assert stateful_entry["observed_effects"]
    set_channels_calls = [args for fn, args in calls if fn == "soundtouch_setChannels"]
    set_sample_rate_calls = [args for fn, args in calls if fn == "soundtouch_setSampleRate"]
    assert len(set_channels_calls) == 3
    assert len(set_sample_rate_calls) == 2
    assert set_channels_calls[0]["param_1"] == 111111
    assert set_sample_rate_calls[0]["param_1"] == 111111
    assert set_channels_calls[1]["param_1"] != set_channels_calls[2]["param_1"]
    assert set_sample_rate_calls[1]["param_1"] == set_channels_calls[2]["param_1"]


def test_stateful_verifier_does_not_promote_without_effect_delta(monkeypatch) -> None:
    findings = _soundtouch_findings()
    uploads: dict[str, dict] = {}
    patched: list[tuple[str, dict]] = []
    create_counter = {"value": 0}
    sessions: dict[int, dict[str, object]] = {}

    def fake_execute(inv: dict, args: dict) -> str:
        fn = inv["name"]
        call_args = dict(args or {})
        if fn == "soundtouch_createInstance":
            create_counter["value"] += 1
            handle = 7000 + create_counter["value"]
            sessions[handle] = {"payload": True}
            return f"Returned: {handle}"
        if fn == "soundtouch_setChannels":
            return "Returned: 1"
        if fn == "soundtouch_setSampleRate":
            return "Returned: 2867"
        if fn == "soundtouch_putSamples_i16":
            return "Returned: 0"
        if fn == "soundtouch_flush":
            return "Returned: 0"
        if fn == "soundtouch_numUnprocessedSamples":
            return "Returned: 4"
        raise AssertionError(f"unexpected function {fn}")

    monkeypatch.setattr(verify_mod, "_load_findings", lambda job_id: findings)
    monkeypatch.setattr(
        verify_mod,
        "_download_blob",
        lambda container, path: json.dumps(_soundtouch_probe_log()).encode("utf-8"),
    )
    monkeypatch.setattr(verify_mod, "_execute_tool", fake_execute)
    monkeypatch.setattr(verify_mod, "_set_explore_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(verify_mod, "_get_job_status", lambda job_id: {"status": "done"})
    monkeypatch.setattr(verify_mod, "_persist_job_status", lambda job_id, payload: None)
    monkeypatch.setattr(
        verify_mod,
        "_upload_to_blob",
        lambda container, path, payload: uploads.setdefault(path, json.loads(payload.decode("utf-8"))),
    )
    monkeypatch.setattr(
        verify_mod,
        "_patch_finding",
        lambda job_id, fn_name, patch: patched.append((fn_name, patch)),
    )

    ctx = _make_ctx()
    verify_mod._run_phase_7b_verify_enrichment(ctx)  # noqa: SLF001

    assert not [patch for fn, patch in patched if fn == "soundtouch_setSampleRate" and patch.get("status") == "success"]
    report = uploads["job-stateful/verification-report.json"]
    stateful_entry = next(entry for entry in report["entries"] if entry["function"] == "soundtouch_setSampleRate")
    assert stateful_entry["verification_mode"] == "stateful_mutator"
    assert stateful_entry["promotion_decision"] == "not_promoted"
    assert stateful_entry["observed_effects"] == []


def test_direct_replay_remains_verified_for_existing_success(monkeypatch) -> None:
    uploads: dict[str, dict] = {}
    patched: list[tuple[str, dict]] = []
    findings = [
        {
            "function": "soundtouch_getVersionId",
            "status": "success",
            "working_call": {"args": {}},
        }
    ]

    monkeypatch.setattr(verify_mod, "_load_findings", lambda job_id: findings)
    monkeypatch.setattr(verify_mod, "_download_blob", lambda container, path: b"[]")
    monkeypatch.setattr(verify_mod, "_execute_tool", lambda inv, args: "Returned: 20200")
    monkeypatch.setattr(verify_mod, "_set_explore_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(verify_mod, "_get_job_status", lambda job_id: {"status": "done"})
    monkeypatch.setattr(verify_mod, "_persist_job_status", lambda job_id, payload: None)
    monkeypatch.setattr(
        verify_mod,
        "_upload_to_blob",
        lambda container, path, payload: uploads.setdefault(path, json.loads(payload.decode("utf-8"))),
    )
    monkeypatch.setattr(
        verify_mod,
        "_patch_finding",
        lambda job_id, fn_name, patch: patched.append((fn_name, patch)),
    )

    ctx = _make_ctx()
    verify_mod._run_phase_7b_verify_enrichment(ctx)  # noqa: SLF001

    assert [fn for fn, _ in patched] == ["soundtouch_getVersionId"]
    replay_patch = patched[0][1]
    assert replay_patch["verification"] == "verified"
    assert replay_patch["status_canonical"] == "verified_success"
    assert replay_patch["direct_target_truth"]["verification"] == "verified"
    report = uploads["job-stateful/verification-report.json"]
    assert report["verified_count"] == 1
    assert report["entries"][0]["verification_mode"] == "direct_replay"
    assert report["entries"][0]["verification"] == "verified"


def test_direct_replay_ignores_ntstatus_like_probe_failures_when_success_probe_exists(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-settlement-verify",
        _state={"explored": 1},
        total=1,
        init_invocables=[],
        sentinels={},
        inv_map={
            "SP_VerifyReservedRelease": {
                "name": "SP_VerifyReservedRelease",
                "parameters": [
                    {"name": "reservation_handle"},
                    {"name": "preview_ticket"},
                    {"name": "fee_quote_id"},
                    {"name": "out_verification_ticket"},
                    {"name": "out_len"},
                ],
            },
        },
    )
    finding = {
        "function": "SP_VerifyReservedRelease",
        "status": "success",
        "working_call": {
            "reservation_handle": "sp-resv-ORD-001-64",
            "preview_ticket": "sp-preview-ORD-001-64-gate",
            "fee_quote_id": "sp-fee-ORD-001-64-quote",
            "out_verification_ticket": "",
            "out_len": 64,
        },
    }
    probe_log = [
        {
            "phase": "lineage_preflight",
            "probe_id": "SP_VerifyReservedRelease:lineage_preflight",
            "function": "SP_VerifyReservedRelease",
            "args": {
                "reservation_handle": "sp-resv-ORD-001-100",
                "preview_ticket": "sp-resv-ORD-001-100",
                "fee_quote_id": "sp-resv-ORD-001-100",
                "out_verification_ticket": "sp-resv-ORD-001-100",
                "out_len": 64,
            },
            "result_excerpt": "Returned: -7104",
            "classification": {
                "has_return": True,
                "signed": -7104,
                "format_guess": "custom_negative_status",
            },
        },
        {
            "phase": "explore",
            "probe_id": "SP_VerifyReservedRelease:0:1:SP_VerifyReservedRelease",
            "function": "SP_VerifyReservedRelease",
            "args": {
                "reservation_handle": "sp-resv-ORD-001-64",
                "preview_ticket": "sp-preview-ORD-001-64-gate",
                "fee_quote_id": "sp-fee-ORD-001-64-quote",
                "out_verification_ticket": "",
                "out_len": 64,
            },
            "result_excerpt": "Returned: 0\nout_verification_ticket=sp-verify-ORD-001-64-reserved",
            "classification": {
                "has_return": True,
                "signed": 0,
                "format_guess": "bool_style_success",
            },
        },
    ]
    calls: list[tuple[str, dict]] = []

    def fake_execute(inv: dict, args: dict) -> str:
        call_args = dict(args or {})
        calls.append((inv["name"], call_args))
        assert call_args == {
            "reservation_handle": "sp-resv-ORD-001-64",
            "preview_ticket": "sp-preview-ORD-001-64-gate",
            "fee_quote_id": "sp-fee-ORD-001-64-quote",
            "out_verification_ticket": "",
            "out_len": 64,
        }
        return "Returned: 0\nout_verification_ticket=sp-verify-ORD-001-64-reserved"

    monkeypatch.setattr(verify_mod, "_execute_tool", fake_execute)

    report_entry, patch, bridge_error = verify_mod._run_direct_replay(ctx, finding, probe_log)  # noqa: SLF001

    assert bridge_error == ""
    assert patch["verification"] == "verified"
    assert patch["status_canonical"] == "verified_success"
    assert patch["working_call"] == {
        "reservation_handle": "sp-resv-ORD-001-64",
        "preview_ticket": "sp-preview-ORD-001-64-gate",
        "fee_quote_id": "sp-fee-ORD-001-64-quote",
        "out_verification_ticket": "sp-verify-ORD-001-64-reserved",
        "out_len": 64,
    }
    assert patch["direct_target_truth"]["verification"] == "verified"
    assert patch["direct_target_truth"]["working_call"] == {
        "reservation_handle": "sp-resv-ORD-001-64",
        "preview_ticket": "sp-preview-ORD-001-64-gate",
        "fee_quote_id": "sp-fee-ORD-001-64-quote",
        "out_verification_ticket": "sp-verify-ORD-001-64-reserved",
        "out_len": 64,
    }
    assert report_entry["verification"] == "verified"
    assert report_entry["candidate_source"] == "probe_log"
    assert report_entry["args"] == {
        "reservation_handle": "sp-resv-ORD-001-64",
        "preview_ticket": "sp-preview-ORD-001-64-gate",
        "fee_quote_id": "sp-fee-ORD-001-64-quote",
        "out_verification_ticket": "",
        "out_len": 64,
    }
    assert report_entry["direct_target_truth"]["working_call"] == {
        "reservation_handle": "sp-resv-ORD-001-64",
        "preview_ticket": "sp-preview-ORD-001-64-gate",
        "fee_quote_id": "sp-fee-ORD-001-64-quote",
        "out_verification_ticket": "sp-verify-ORD-001-64-reserved",
        "out_len": 64,
    }
    assert report_entry["preserved_working_call"] == {
        "reservation_handle": "sp-resv-ORD-001-64",
        "preview_ticket": "sp-preview-ORD-001-64-gate",
        "fee_quote_id": "sp-fee-ORD-001-64-quote",
        "out_verification_ticket": "sp-verify-ORD-001-64-reserved",
        "out_len": 64,
    }
    assert calls == [
        (
            "SP_VerifyReservedRelease",
            {
                "reservation_handle": "sp-resv-ORD-001-64",
                "preview_ticket": "sp-preview-ORD-001-64-gate",
                "fee_quote_id": "sp-fee-ORD-001-64-quote",
                "out_verification_ticket": "",
                "out_len": 64,
            },
        )
    ]


def test_direct_replay_reuses_probe_prereqs_and_probe_shaped_args_for_clustered_success(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-pricing-verify",
        _state={"explored": 6},
        total=6,
        init_invocables=[{"name": "PR_Initialize", "parameters": []}],
        sentinels={4294964292: "pricing_state_drift"},
        inv_map={
            "PR_Initialize": {"name": "PR_Initialize", "parameters": []},
            "PR_BindCustomer": {"name": "PR_BindCustomer", "parameters": [{"name": "lpszCustId"}]},
            "PR_LoadSkuContext": {
                "name": "PR_LoadSkuContext",
                "parameters": [{"name": "lpszSku"}, {"name": "wQty"}],
            },
            "PR_BeginQuote": {
                "name": "PR_BeginQuote",
                "parameters": [{"name": "pOutQuoteId"}, {"name": "dwBufLen"}],
            },
            "PR_GetQuoteNonce": {
                "name": "PR_GetQuoteNonce",
                "parameters": [{"name": "lpszQuoteId"}, {"name": "pdwNonceOut"}],
            },
            "PR_ApproveRuleWindow": {
                "name": "PR_ApproveRuleWindow",
                "parameters": [{"name": "lpszQuoteId"}, {"name": "dwNonce"}],
            },
            "PR_ApplyBundleOverride": {
                "name": "PR_ApplyBundleOverride",
                "parameters": [
                    {"name": "lpszQuoteId"},
                    {"name": "dwFormatCode"},
                    {"name": "pdwTotalOut"},
                ],
            },
        },
    )
    finding = {
        "function": "PR_ApplyBundleOverride",
        "status": "success",
        "working_call": {
            "lpszQuoteId": "PRQ-CUST-001-03",
            "dwFormatCode": 1,
            "pdwTotalOut": 15820,
        },
    }
    probe_log = [
        {
            "probe_id": "PR_ApplyBundleOverride:structured_preflight:rehydrate:PR_BindCustomer",
            "function": "PR_BindCustomer",
            "args": {"lpszCustId": "CUST-001"},
        },
        {
            "probe_id": "PR_ApplyBundleOverride:structured_preflight:rehydrate:PR_LoadSkuContext",
            "function": "PR_LoadSkuContext",
            "args": {"lpszSku": "WDG-XL-BLU", "wQty": 3},
        },
        {
            "probe_id": "PR_ApplyBundleOverride:structured_preflight:rehydrate:PR_BeginQuote",
            "function": "PR_BeginQuote",
            "args": {"pOutQuoteId": "", "dwBufLen": 64},
        },
        {
            "probe_id": "PR_ApplyBundleOverride:structured_preflight:rehydrate:PR_GetQuoteNonce",
            "function": "PR_GetQuoteNonce",
            "args": {"lpszQuoteId": "PRQ-CUST-001-03", "pdwNonceOut": ""},
        },
        {
            "probe_id": "PR_ApplyBundleOverride:structured_preflight:rehydrate:PR_ApproveRuleWindow",
            "function": "PR_ApproveRuleWindow",
            "args": {"lpszQuoteId": "PRQ-CUST-001-03", "dwNonce": 1500757424},
        },
        {
            "phase": "deterministic_fallback",
            "probe_id": "PR_ApplyBundleOverride:fb:1",
            "function": "PR_ApplyBundleOverride",
            "args": {
                "lpszQuoteId": "PRQ-CUST-001-03",
                "dwFormatCode": 1,
                "pdwTotalOut": "",
            },
            "result_excerpt": "Returned: 0\npdwTotalOut=15820",
            "classification": {
                "has_return": True,
                "signed": 0,
                "format_guess": "bool_style_success",
            },
        },
    ]
    calls: list[tuple[str, dict]] = []
    state = {"cust": False, "sku": False, "quote_id": None, "nonce": None, "approved": False}

    def fake_execute(inv: dict, args: dict) -> str:
        fn = inv["name"]
        call_args = dict(args or {})
        calls.append((fn, call_args))
        if fn == "PR_Initialize":
            state.update({"cust": False, "sku": False, "quote_id": None, "nonce": None, "approved": False})
            return "Returned: 0"
        if fn == "PR_BindCustomer":
            state["cust"] = call_args.get("lpszCustId") == "CUST-001"
            return "Returned: 0"
        if fn == "PR_LoadSkuContext":
            state["sku"] = call_args.get("lpszSku") == "WDG-XL-BLU" and call_args.get("wQty") == 3
            return "Returned: 0"
        if fn == "PR_BeginQuote":
            if not (state["cust"] and state["sku"]) or call_args.get("pOutQuoteId") != "":
                return "Returned: -3004"
            state["quote_id"] = "PRQ-CUST-001-03"
            return "Returned: 0\nPRQ-CUST-001-03"
        if fn == "PR_GetQuoteNonce":
            if call_args.get("lpszQuoteId") != state["quote_id"] or call_args.get("pdwNonceOut") != "":
                return "Returned: 4294964292"
            state["nonce"] = 1500757424
            return "Returned: 0\npdwNonceOut=1500757424"
        if fn == "PR_ApproveRuleWindow":
            if (
                call_args.get("lpszQuoteId") != state["quote_id"]
                or call_args.get("dwNonce") != state["nonce"]
            ):
                return "Returned: 4294964292"
            state["approved"] = True
            return "Returned: 0"
        if fn == "PR_ApplyBundleOverride":
            if not state["approved"] or call_args.get("pdwTotalOut") != "":
                return "Returned: -3004"
            return "Returned: 0\npdwTotalOut=15820"
        raise AssertionError(f"unexpected function {fn}")

    monkeypatch.setattr(verify_mod, "_execute_tool", fake_execute)

    report_entry, patch, bridge_error = verify_mod._run_direct_replay(ctx, finding, probe_log)  # noqa: SLF001

    assert bridge_error == ""
    assert patch["verification"] == "verified"
    assert patch["status_canonical"] == "verified_success"
    assert patch["direct_target_truth"]["verification"] == "verified"
    assert report_entry["verification"] == "verified"
    assert report_entry["candidate_source"] == "probe_log"
    assert [entry["function"] for entry in report_entry["prerequisite_chain"]] == [
        "PR_BindCustomer",
        "PR_LoadSkuContext",
        "PR_BeginQuote",
        "PR_GetQuoteNonce",
        "PR_ApproveRuleWindow",
    ]
    assert calls == [
        ("PR_Initialize", {}),
        ("PR_BindCustomer", {"lpszCustId": "CUST-001"}),
        ("PR_LoadSkuContext", {"lpszSku": "WDG-XL-BLU", "wQty": 3}),
        ("PR_BeginQuote", {"pOutQuoteId": "", "dwBufLen": 64}),
        ("PR_GetQuoteNonce", {"lpszQuoteId": "PRQ-CUST-001-03", "pdwNonceOut": ""}),
        ("PR_ApproveRuleWindow", {"lpszQuoteId": "PRQ-CUST-001-03", "dwNonce": 1500757424}),
        ("PR_ApplyBundleOverride", {"lpszQuoteId": "PRQ-CUST-001-03", "dwFormatCode": 1, "pdwTotalOut": ""}),
    ]


def test_direct_replay_rebinds_workflow_lineage_from_prereq_results(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-workflow-verify",
        _state={"explored": 5},
        total=5,
        init_invocables=[],
        sentinels={4294965292: "workflow_state_drift", 4294965291: "workflow_bad_handle"},
        inv_map={
            "WF_Initialize": {"name": "WF_Initialize", "parameters": []},
            "WF_BindCustomer": {
                "name": "WF_BindCustomer",
                "parameters": [{"name": "lpszCustId", "json_type": "string"}],
            },
            "WF_CreateReservation": {
                "name": "WF_CreateReservation",
                "parameters": [
                    {"name": "lpszSku", "json_type": "string"},
                    {"name": "wQty", "json_type": "integer"},
                    {"name": "dwHoldMinutes", "json_type": "integer"},
                    {"name": "pOutResvId", "json_type": "string", "description": "Output reservation id"},
                    {"name": "dwBufLen", "json_type": "integer"},
                ],
            },
            "WF_OpenFulfillment": {
                "name": "WF_OpenFulfillment",
                "parameters": [
                    {"name": "lpszResvId", "json_type": "string", "description": "Reservation id returned by WF_CreateReservation"},
                    {"name": "pOutHandle", "json_type": "string", "description": "Output workflow handle"},
                    {"name": "dwBufLen", "json_type": "integer"},
                ],
            },
            "WF_GetWorkflowNonce": {
                "name": "WF_GetWorkflowNonce",
                "parameters": [
                    {"name": "lpszHandle", "json_type": "string", "description": "Workflow handle"},
                    {"name": "pdwNonceOut", "json_type": "integer", "description": "Output nonce"},
                ],
            },
            "WF_GetWorkflowState": {
                "name": "WF_GetWorkflowState",
                "parameters": [
                    {"name": "lpszHandle", "json_type": "string", "description": "Workflow handle"},
                    {"name": "dwBufLen", "json_type": "integer"},
                    {"name": "pOutBuf", "json_type": "string", "description": "Output workflow state text"},
                ],
            },
        },
    )
    finding = {
        "function": "WF_GetWorkflowState",
        "status": "success",
        "working_call": {
            "lpszHandle": "WFH-OLD-0001",
            "dwBufLen": 64,
            "pOutBuf": "",
        },
    }
    probe_log = [
        {
            "phase": "explore",
            "probe_id": "WF_CreateReservation:0:1:WF_Initialize",
            "function": "WF_CreateReservation",
            "args": {},
            "result_excerpt": "Returned: 0",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
        {
            "phase": "explore",
            "probe_id": "WF_CreateReservation:0:2:WF_BindCustomer",
            "function": "WF_CreateReservation",
            "args": {"lpszCustId": "CUST-001"},
            "result_excerpt": "Returned: 0",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
        {
            "phase": "structured_preflight_prereq",
            "probe_id": "WF_GetWorkflowState:structured_preflight:rehydrate:WF_CreateReservation",
            "function": "WF_CreateReservation",
            "args": {
                "lpszSku": "ACC-USB-C",
                "wQty": 2,
                "dwHoldMinutes": 30,
                "pOutResvId": "",
                "dwBufLen": 64,
            },
            "result_excerpt": "Returned: 0\nRESV-NEW-0001",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
        {
            "phase": "structured_preflight_prereq",
            "probe_id": "WF_GetWorkflowState:structured_preflight:rehydrate:WF_OpenFulfillment",
            "function": "WF_OpenFulfillment",
            "args": {
                "lpszResvId": "RESV-OLD-0001",
                "pOutHandle": "",
                "dwBufLen": 64,
            },
            "result_excerpt": "Returned: 0\nWFH-NEW-0001",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
        {
            "phase": "structured_preflight_prereq",
            "probe_id": "WF_GetWorkflowState:structured_preflight:rehydrate:WF_GetWorkflowNonce",
            "function": "WF_GetWorkflowNonce",
            "args": {
                "lpszHandle": "WFH-OLD-0001",
                "pdwNonceOut": "",
            },
            "result_excerpt": "Returned: 0\npdwNonceOut=2511030275",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
        {
            "phase": "deterministic_fallback",
            "probe_id": "WF_GetWorkflowState:fb:1",
            "function": "WF_GetWorkflowState",
            "args": {
                "lpszHandle": "WFH-OLD-0001",
                "dwBufLen": 64,
                "pOutBuf": "",
            },
            "result_excerpt": "Returned: 0\nstate=confirmed",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
    ]
    calls: list[tuple[str, dict]] = []
    state = {"init": False, "bound": False, "reservation_id": None, "workflow_handle": None}

    def fake_execute(inv: dict, args: dict) -> str:
        fn = inv["name"]
        call_args = dict(args or {})
        calls.append((fn, call_args))
        if fn == "WF_Initialize":
            state["init"] = True
            return "Returned: 0"
        if fn == "WF_BindCustomer":
            state["bound"] = state["init"] and call_args.get("lpszCustId") == "CUST-001"
            return "Returned: 0" if state["bound"] else "Returned: -2002"
        if fn == "WF_CreateReservation":
            if not state["bound"]:
                return "Returned: -2004"
            state["reservation_id"] = "RESV-NEW-0001"
            return "Returned: 0\nRESV-NEW-0001"
        if fn == "WF_OpenFulfillment":
            if call_args.get("lpszResvId") != state["reservation_id"]:
                return "Returned: 4294965291"
            state["workflow_handle"] = "WFH-NEW-0001"
            return "Returned: 0\nWFH-NEW-0001"
        if fn == "WF_GetWorkflowNonce":
            if call_args.get("lpszHandle") != state["workflow_handle"]:
                return "Returned: 4294965292\npdwNonceOut=0"
            return "Returned: 0\npdwNonceOut=2511030275"
        if fn == "WF_GetWorkflowState":
            if call_args.get("lpszHandle") != state["workflow_handle"]:
                return "Returned: 4294965292"
            return "Returned: 0\nstate=confirmed"
        raise AssertionError(f"unexpected function {fn}")

    monkeypatch.setattr(verify_mod, "_execute_tool", fake_execute)

    report_entry, patch, bridge_error = verify_mod._run_direct_replay(ctx, finding, probe_log)  # noqa: SLF001

    assert bridge_error == ""
    assert patch["verification"] == "verified"
    assert patch["status_canonical"] == "verified_success"
    assert patch["direct_target_truth"]["verification"] == "verified"
    assert report_entry["verification"] == "verified"
    assert report_entry["args"]["lpszHandle"] == "WFH-NEW-0001"
    assert [entry["function"] for entry in report_entry["prerequisite_chain"]] == [
        "WF_Initialize",
        "WF_BindCustomer",
        "WF_CreateReservation",
        "WF_OpenFulfillment",
        "WF_GetWorkflowNonce",
    ]
    open_call = next(args for fn, args in calls if fn == "WF_OpenFulfillment")
    nonce_call = next(args for fn, args in calls if fn == "WF_GetWorkflowNonce")
    state_call = next(args for fn, args in calls if fn == "WF_GetWorkflowState")
    assert open_call["lpszResvId"] == "RESV-NEW-0001"
    assert nonce_call["lpszHandle"] == "WFH-NEW-0001"
    assert state_call["lpszHandle"] == "WFH-NEW-0001"


def test_extract_prereq_rows_for_target_ignores_tooling_rows() -> None:
    probe_log = [
        {
            "phase": "explore",
            "probe_id": "WF_CreateReservation:0:1:WF_Initialize",
            "function": "WF_CreateReservation",
            "args": {},
        },
        {
            "phase": "explore",
            "probe_id": "WF_CreateReservation:1:2:WF_BindCustomer",
            "function": "WF_CreateReservation",
            "args": {"lpszCustId": "CUST-001"},
        },
        {
            "phase": "explore",
            "probe_id": "WF_CreateReservation:3:4:record_finding",
            "function": "WF_CreateReservation",
            "args": {"function_name": "WF_CreateReservation"},
        },
        {
            "phase": "explore",
            "probe_id": "WF_CreateReservation:3:5:enrich_invocable",
            "function": "WF_CreateReservation",
            "args": {"function_name": "WF_CreateReservation"},
        },
    ]

    rows = verify_mod._extract_prereq_rows_for_target(probe_log, "WF_CreateReservation")  # noqa: SLF001

    assert [verify_mod._probe_row_function_name("WF_CreateReservation", row) for row in rows] == [  # noqa: SLF001
        "WF_Initialize",
        "WF_BindCustomer",
    ]


def test_direct_replay_rebuilds_root_workflow_creator_bootstrap(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-workflow-root-verify",
        _state={"explored": 3},
        total=3,
        init_invocables=[],
        sentinels={4294965292: "workflow_state_drift"},
        inv_map={
            "WF_Initialize": {"name": "WF_Initialize", "parameters": []},
            "WF_BindCustomer": {
                "name": "WF_BindCustomer",
                "parameters": [{"name": "lpszCustId", "json_type": "string"}],
            },
            "WF_CreateReservation": {
                "name": "WF_CreateReservation",
                "parameters": [
                    {"name": "lpszSku", "json_type": "string"},
                    {"name": "wQty", "json_type": "integer"},
                    {"name": "dwHoldMinutes", "json_type": "integer"},
                    {"name": "pOutResvId", "json_type": "string", "description": "Output reservation id"},
                    {"name": "dwBufLen", "json_type": "integer"},
                ],
            },
        },
    )
    bind_finding = {
        "function": "WF_BindCustomer",
        "status": "success",
        "working_call": {"lpszCustId": "CUST-001"},
    }
    finding = {
        "function": "WF_CreateReservation",
        "status": "success",
        "working_call": {
            "lpszSku": "ACC-USB-C",
            "wQty": 2,
            "dwHoldMinutes": 30,
            "pOutResvId": "",
            "dwBufLen": 64,
        },
    }
    probe_log = [
        {
            "phase": "explore",
            "probe_id": "WF_CreateReservation:0:1:WF_Initialize",
            "function": "WF_CreateReservation",
            "args": {},
            "result_excerpt": "Returned: 0",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
        {
            "phase": "explore",
            "probe_id": "WF_CreateReservation:1:2:WF_BindCustomer",
            "function": "WF_CreateReservation",
            "args": {"lpszCustId": "CUST-001"},
            "result_excerpt": "Returned: 0",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
        {
            "phase": "explore",
            "probe_id": "WF_CreateReservation:2:3:WF_CreateReservation",
            "function": "WF_CreateReservation",
            "args": {
                "lpszSku": "ACC-USB-C",
                "wQty": 2,
                "dwHoldMinutes": 30,
                "pOutResvId": "",
                "dwBufLen": 64,
            },
            "result_excerpt": "Returned: 0\nRESV-NEW-0001",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
        {
            "phase": "explore",
            "probe_id": "WF_CreateReservation:3:4:record_finding",
            "function": "WF_CreateReservation",
            "args": {"function_name": "WF_CreateReservation"},
            "result_excerpt": "Finding recorded.",
            "classification": {"has_return": False, "signed": None, "format_guess": "no_return_detected"},
        },
    ]
    calls: list[tuple[str, dict]] = []
    state = {"init": False, "bound": False}

    def fake_execute(inv: dict, args: dict) -> str:
        fn = inv["name"]
        call_args = dict(args or {})
        calls.append((fn, call_args))
        if fn == "WF_Initialize":
            state["init"] = True
            return "Returned: 0"
        if fn == "WF_BindCustomer":
            state["bound"] = state["init"] and call_args.get("lpszCustId") == "CUST-001"
            return "Returned: 0" if state["bound"] else "Returned: -2002"
        if fn == "WF_CreateReservation":
            if not state["bound"]:
                return "Returned: -2004"
            return "Returned: 0\nRESV-NEW-0001"
        raise AssertionError(f"unexpected function {fn}")

    monkeypatch.setattr(verify_mod, "_execute_tool", fake_execute)

    report_entry, patch, bridge_error = verify_mod._run_direct_replay(  # noqa: SLF001
        ctx,
        finding,
        probe_log,
        [bind_finding, finding],
    )

    assert bridge_error == ""
    assert patch["verification"] == "verified"
    assert patch["status_canonical"] == "verified_success"
    assert patch["direct_target_truth"]["verification"] == "verified"
    assert report_entry["verification"] == "verified"
    assert [entry["function"] for entry in report_entry["prerequisite_chain"]] == [
        "WF_Initialize",
        "WF_BindCustomer",
    ]
    assert calls == [
        ("WF_Initialize", {}),
        ("WF_BindCustomer", {"lpszCustId": "CUST-001"}),
        (
            "WF_CreateReservation",
            {
                "lpszSku": "ACC-USB-C",
                "wQty": 2,
                "dwHoldMinutes": 30,
                "pOutResvId": "",
                "dwBufLen": 64,
            },
        ),
    ]


def test_direct_replay_rebinds_config_ticket_and_nonce_from_prereq_results(monkeypatch) -> None:
    ctx = SimpleNamespace(
        job_id="job-config-verify",
        _state={"explored": 4},
        total=4,
        init_invocables=[],
        sentinels={4294962292: "config_state_drift", 4294962291: "config_bad_ticket"},
        inv_map={
            "CFG_Initialize": {"name": "CFG_Initialize", "parameters": []},
            "CFG_SetupEnvironment": {
                "name": "CFG_SetupEnvironment",
                "parameters": [{"name": "dwMode", "json_type": "integer"}],
            },
            "CFG_BindCustomer": {
                "name": "CFG_BindCustomer",
                "parameters": [{"name": "lpszCustId", "json_type": "string"}],
            },
            "CFG_OpenLicensedWindow": {
                "name": "CFG_OpenLicensedWindow",
                "parameters": [
                    {"name": "pOutTicket", "json_type": "string", "description": "Output config ticket"},
                    {"name": "dwBufLen", "json_type": "integer"},
                ],
            },
            "CFG_GetLicenseNonce": {
                "name": "CFG_GetLicenseNonce",
                "parameters": [
                    {"name": "lpszTicket", "json_type": "string", "description": "License ticket"},
                    {"name": "pdwNonceOut", "json_type": "integer", "description": "Output nonce"},
                ],
            },
            "CFG_ApproveLicensedCall": {
                "name": "CFG_ApproveLicensedCall",
                "parameters": [
                    {"name": "lpszTicket", "json_type": "string", "description": "Licensed config ticket"},
                    {"name": "dwNonce", "json_type": "integer", "description": "License nonce"},
                ],
            },
        },
    )
    finding = {
        "function": "CFG_ApproveLicensedCall",
        "status": "success",
        "working_call": {
            "lpszTicket": "CFG-CUST-001-34",
            "dwNonce": 3235774496,
        },
    }
    probe_log = [
        {
            "phase": "structured_preflight_prereq",
            "probe_id": "CFG_ApproveLicensedCall:structured_preflight:rehydrate:CFG_SetupEnvironment",
            "function": "CFG_SetupEnvironment",
            "args": {"dwMode": 2},
            "result_excerpt": "Returned: 0",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
        {
            "phase": "structured_preflight_prereq",
            "probe_id": "CFG_ApproveLicensedCall:structured_preflight:rehydrate:CFG_BindCustomer",
            "function": "CFG_BindCustomer",
            "args": {"lpszCustId": "CUST-001"},
            "result_excerpt": "Returned: 0",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
        {
            "phase": "structured_preflight_prereq",
            "probe_id": "CFG_ApproveLicensedCall:structured_preflight:rehydrate:CFG_OpenLicensedWindow",
            "function": "CFG_OpenLicensedWindow",
            "args": {"pOutTicket": "", "dwBufLen": 64},
            "result_excerpt": "Returned: 0\npOutTicket=CFG-CUST-001-160",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
        {
            "phase": "structured_preflight_prereq",
            "probe_id": "CFG_ApproveLicensedCall:structured_preflight:rehydrate:CFG_GetLicenseNonce",
            "function": "CFG_GetLicenseNonce",
            "args": {"lpszTicket": "CFG-CUST-001-34", "pdwNonceOut": ""},
            "result_excerpt": "Returned: 0\npdwNonceOut=3235774517",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
        {
            "phase": "deterministic_fallback",
            "probe_id": "CFG_ApproveLicensedCall:fb:1",
            "function": "CFG_ApproveLicensedCall",
            "args": {"lpszTicket": "CFG-CUST-001-34", "dwNonce": 3235774496},
            "result_excerpt": "Returned: 0",
            "classification": {"has_return": True, "signed": 0, "format_guess": "bool_style_success"},
        },
    ]
    calls: list[tuple[str, dict]] = []
    state = {"mode": False, "bound": False, "ticket": None, "nonce": None}

    def fake_execute(inv: dict, args: dict) -> str:
        fn = inv["name"]
        call_args = dict(args or {})
        calls.append((fn, call_args))
        if fn == "CFG_SetupEnvironment":
            state["mode"] = call_args.get("dwMode") == 2
            return "Returned: 0"
        if fn == "CFG_BindCustomer":
            state["bound"] = state["mode"] and call_args.get("lpszCustId") == "CUST-001"
            return "Returned: 0" if state["bound"] else "Returned: 4294962291"
        if fn == "CFG_OpenLicensedWindow":
            if not state["bound"] or call_args.get("pOutTicket") != "":
                return "Returned: 4294962291"
            state["ticket"] = "CFG-CUST-001-160"
            return "Returned: 0\npOutTicket=CFG-CUST-001-160"
        if fn == "CFG_GetLicenseNonce":
            if call_args.get("lpszTicket") != state["ticket"] or call_args.get("pdwNonceOut") != "":
                return "Returned: 4294962292"
            state["nonce"] = 3235774517
            return "Returned: 0\npdwNonceOut=3235774517"
        if fn == "CFG_ApproveLicensedCall":
            if call_args.get("lpszTicket") != state["ticket"] or call_args.get("dwNonce") != state["nonce"]:
                return "Returned: 4294962292"
            return "Returned: 0"
        raise AssertionError(f"unexpected function {fn}")

    monkeypatch.setattr(verify_mod, "_execute_tool", fake_execute)

    report_entry, patch, bridge_error = verify_mod._run_direct_replay(  # noqa: SLF001
        ctx,
        finding,
        probe_log,
        [finding],
    )

    assert bridge_error == ""
    assert patch["verification"] == "verified"
    assert patch["status_canonical"] == "verified_success"
    assert patch["direct_target_truth"]["verification"] == "verified"
    assert report_entry["verification"] == "verified"
    assert report_entry["args"] == {"lpszTicket": "CFG-CUST-001-160", "dwNonce": 3235774517}
    assert [entry["function"] for entry in report_entry["prerequisite_chain"]] == [
        "CFG_SetupEnvironment",
        "CFG_BindCustomer",
        "CFG_OpenLicensedWindow",
        "CFG_GetLicenseNonce",
    ]
    approve_call = next(args for fn, args in calls if fn == "CFG_ApproveLicensedCall")
    assert approve_call["lpszTicket"] == "CFG-CUST-001-160"
    assert approve_call["dwNonce"] == 3235774517


def test_expected_family_for_config_nonce_param_mentions_ticket_but_stays_nonce() -> None:
    inv = {
        "name": "CFG_ApproveLicensedCall",
        "parameters": [
            {
                "name": "lpszTicket",
                "json_type": "string",
                "resolved_type": "LPCSTR",
                "description": "Ticket identifier, e.g., 'CFG-CUST-001-55'. This ticket must be valid and previously obtained.",
            },
            {
                "name": "dwNonce",
                "json_type": "integer",
                "resolved_type": "DWORD",
                "description": "Nonce value for the request, which must match the nonce retrieved for the ticket.",
            },
        ],
    }

    assert verify_mod._expected_family_for_param(inv, "CFG_ApproveLicensedCall", "lpszTicket") == "ticket"  # noqa: SLF001
    assert verify_mod._expected_family_for_param(inv, "CFG_ApproveLicensedCall", "dwNonce") == "nonce"  # noqa: SLF001


def test_runtime_lineage_hints_do_not_rebind_workflow_numeric_fields() -> None:
    inv = {
        "name": "WF_CreateReservation",
        "parameters": [
            {"name": "lpszSku", "json_type": "string"},
            {"name": "wQty", "json_type": "integer"},
            {"name": "dwHoldMinutes", "json_type": "integer"},
            {"name": "pOutResvId", "json_type": "string", "description": "Output reservation id"},
        ],
    }
    args = {
        "lpszSku": "ACC-USB-C",
        "wQty": 2,
        "dwHoldMinutes": 30,
        "pOutResvId": "",
    }

    rebound = verify_mod._apply_runtime_lineage_hints(  # noqa: SLF001
        inv,
        "WF_CreateReservation",
        args,
        {"reservation_id": "RESV-NEW-0001"},
    )

    assert rebound["wQty"] == 2
    assert rebound["dwHoldMinutes"] == 30
    assert rebound["pOutResvId"] == ""


def test_expand_prereq_specs_deduplicates_repeated_workflow_bootstrap() -> None:
    ctx = SimpleNamespace(
        inv_map={
            "WF_Initialize": {},
            "WF_BindCustomer": {},
            "WF_CreateReservation": {},
            "WF_OpenFulfillment": {},
        }
    )
    probe_log = [
        {
            "phase": "structured_preflight_prereq",
            "probe_id": "WF_OpenFulfillment:structured_preflight:prereq:WF_Initialize",
            "function": "WF_Initialize",
            "args": {},
        },
        {
            "phase": "structured_preflight_prereq",
            "probe_id": "WF_OpenFulfillment:structured_preflight:rehydrate:WF_BindCustomer",
            "function": "WF_BindCustomer",
            "args": {"lpszCustId": "CUST-001"},
        },
        {
            "phase": "structured_preflight_prereq",
            "probe_id": "WF_OpenFulfillment:structured_preflight:rehydrate:WF_CreateReservation",
            "function": "WF_CreateReservation",
            "args": {"lpszSku": "ACC-USB-C", "wQty": 2, "dwHoldMinutes": 30, "pOutResvId": "", "dwBufLen": 64},
        },
        {
            "phase": "explore",
            "probe_id": "WF_CreateReservation:0:1:WF_Initialize",
            "function": "WF_CreateReservation",
            "args": {},
        },
        {
            "phase": "explore",
            "probe_id": "WF_CreateReservation:1:2:WF_BindCustomer",
            "function": "WF_CreateReservation",
            "args": {"lpszCustId": "CUST-001"},
        },
    ]

    specs = verify_mod._expand_prereq_specs(ctx, probe_log, "WF_OpenFulfillment")  # noqa: SLF001

    assert [spec["function"] for spec in specs] == [
        "WF_Initialize",
        "WF_BindCustomer",
        "WF_CreateReservation",
    ]


def test_coerce_result_value_parses_numeric_prefix_before_annotation() -> None:
    assert verify_mod._coerce_result_value("2511030275 (large uint - may be packed)") == 2511030275  # noqa: SLF001
