from __future__ import annotations

from api.pipeline.core.types import ExploreContext, ExploreRuntime
from api.pipeline.core import vocab
from api.pipeline.s02_probe import probe_loop


def _ctx(*, focus: list[str] | None = None, skip_documented: bool = False) -> ExploreContext:
    runtime = ExploreRuntime(
        skip_documented=skip_documented,
        focus_functions=list(focus or []),
    )
    ctx = ExploreContext(
        job_id="job-probe",
        runtime=runtime,
        client=object(),
        model="gpt-test",
    )
    ctx.inv_map = {"CP_Target": {"name": "CP_Target"}}
    ctx.unlock_result = {"unlocked": False, "sequence": []}
    return ctx


def test_prepare_explore_one_snapshots_static_ids(monkeypatch) -> None:
    ctx = _ctx()
    ctx.static_analysis_result = {"binary_strings": {"ids_found": ["CUST-001", "ORD-100"]}}

    monkeypatch.setattr(probe_loop, "_cancel_requested", lambda _job_id: False)
    monkeypatch.setattr(probe_loop, "_set_explore_status", lambda *_args, **_kwargs: None)

    prepared = probe_loop._prepare_explore_one({"name": "CP_Target"}, ctx)  # noqa: SLF001

    assert prepared is not None
    fn_name, vocab_snapshot = prepared
    assert fn_name == "CP_Target"
    assert vocab_snapshot["binary_string_ids"] == ["CUST-001", "ORD-100"]


def test_prepare_explore_one_respects_focus_skip(monkeypatch) -> None:
    ctx = _ctx(focus=["CP_Other"], skip_documented=False)

    monkeypatch.setattr(probe_loop, "_cancel_requested", lambda _job_id: False)
    monkeypatch.setattr(probe_loop, "_set_explore_status", lambda *_args, **_kwargs: None)

    prepared = probe_loop._prepare_explore_one({"name": "CP_Target"}, ctx)  # noqa: SLF001

    assert prepared is None
    assert ctx.explored_count() == 1
    assert "CP_Target" in ctx.already_explored


def test_prioritized_probe_id_hints_prefers_prefix_matching_lineage_values() -> None:
    inv = {
        "name": "SP_EmitReleaseAttestation",
        "parameters": [
            {"name": "param_1", "json_type": "string", "description": "generic input"},
            {"name": "param_2", "json_type": "string", "description": "generic input"},
        ],
        "doc_comment": (
            'if (strncmp(param_1, "sp-preview-", 0xb) != 0) return 0xFFFFFFFF; '
            'if (strncmp(param_2, "sp-fee-", 0x7) != 0) return 0xFFFFFFFF;'
        ),
    }

    hints = probe_loop._prioritized_probe_id_hints(  # noqa: SLF001
        inv,
        {
            "id_formats": [
                "ACC-USB-C",
                "CUST-001",
                "sp-preview-ACC-USB-C-gate",
                "sp-fee-ACC-USB-C-quote",
            ]
        },
    )

    assert hints[:2] == [
        "sp-preview-ACC-USB-C-gate",
        "sp-fee-ACC-USB-C-quote",
    ]


def test_assess_prerequisite_replay_admission_rejects_semantically_empty_output() -> None:
    admission = probe_loop._assess_prerequisite_replay_admission(  # noqa: SLF001
        "CFG_OpenLicensedWindow",
        {"pOutTicket": "", "dwBufLen": 64},
        {
            "name": "CFG_OpenLicensedWindow",
            "parameters": [
                {"name": "pOutTicket", "direction": "out", "json_type": "string", "description": "output ticket"},
                {"name": "dwBufLen", "json_type": "integer", "description": "ticket buffer length"},
            ],
        },
    )

    assert admission["admitted"] is False
    assert admission["status"] == "inferred_success"
    assert "pOutTicket_expected_ticket" in admission["reasons"]


def test_rehydratable_success_finding_requires_reusable_truth_when_present() -> None:
    assert probe_loop._is_rehydratable_success_finding(  # noqa: SLF001
        {
            "function": "CFG_OpenLicensedWindow",
            "status": "partial",
            "status_canonical": "inferred_success",
            "working_call": {"pOutTicket": "", "dwBufLen": 64},
            "reusable_truth_eligible": False,
        }
    ) is False


def test_lineage_hint_key_treats_reservation_handle_slot_as_reservation_id() -> None:
    assert probe_loop._lineage_hint_key(  # noqa: SLF001
        "reservation_handle",
        None,
        "string",
        "Workflow handle returned by WF_OpenFulfillment",
    ) == "reservation_id"


def test_lineage_hint_key_emits_auth_token_for_operator_token_slot_and_value() -> None:
    assert probe_loop._lineage_hint_key(  # noqa: SLF001
        "operator_token",
        None,
        "string",
        "Unlock token hex returned by the fixture",
    ) == "auth_token"
    assert probe_loop._lineage_hint_key(  # noqa: SLF001
        "operator_token",
        "sp-operator-ORD-001-session",
        "string",
        "Unlock token hex returned by the fixture",
    ) == "auth_token"


def test_lineage_hint_key_emits_branch_id_families_for_audit_slots() -> None:
    assert probe_loop._lineage_hint_key(  # noqa: SLF001
        "trusted_branch_id",
        "sp-branch-primary",
        "string",
        "Trusted branch id selected after reconciliation.",
    ) == "trusted_branch_id"
    assert probe_loop._lineage_hint_key(  # noqa: SLF001
        "rejected_branch_id",
        "sp-branch-replay",
        "string",
        "Rejected branch id invalidated by audit trace.",
    ) == "rejected_branch_id"


def test_extract_inline_lineage_hints_reads_trusted_and_rejected_branch_ids() -> None:
    hints = probe_loop._extract_inline_lineage_hints(  # noqa: SLF001
        "Returned: 0\n"
        "out_trusted_branch_id='sp-branch-primary'\n"
        "out_rejected_branch_id='sp-branch-replay'\n"
    )

    assert hints["trusted_branch_id"] == "sp-branch-primary"
    assert hints["rejected_branch_id"] == "sp-branch-replay"


class _FakeMessage:
    content = "{}"


class _FakeChoice:
    message = _FakeMessage()


class _FakeResponse:
    choices = [_FakeChoice()]


class _RecordingCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse()


class _RecordingClient:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": _RecordingCompletions()})()


def test_post_probe_llm_enrichment_calls_are_timeout_bounded(monkeypatch) -> None:
    client = _RecordingClient()
    monkeypatch.setattr(vocab, "_VOCAB_UPDATE_TIMEOUT_SECONDS", 11.0)
    monkeypatch.setattr(vocab, "_HYPOTHESIS_TIMEOUT_SECONDS", 13.0)

    vocab._update_vocabulary(client, "gpt-test", {}, {"function": "SP_Test"})
    vocab._generate_hypothesis(client, "gpt-test", "SP_Test", "Returned: 0", {}, [])

    calls = client.chat.completions.calls
    assert calls[0]["timeout"] == 11.0
    assert calls[1]["timeout"] == 13.0


def test_repair_target_scalar_args_prefers_live_reservation_and_operator_lineage() -> None:
    inv = {
        "name": "SP_PrepareReleasePreview",
        "doc_comment": (
            'Required preconditions: SP_OpenOperatorSession, SP_IssueReleaseHold | '
            'Canonical args: {"operator_token": "sp-operator-ORD-001-session", '
            '"out_len": 256, "out_preview_ticket": "", '
            '"reservation_handle": "sp-resv-ORD-001-64"}'
        ),
        "parameters": [
            {
                "name": "reservation_handle",
                "json_type": "string",
                "description": "Workflow handle returned by WF_OpenFulfillment",
                "resolved_type": "const char*",
            },
            {
                "name": "operator_token",
                "json_type": "string",
                "description": "Unlock token hex returned by the fixture",
                "resolved_type": "const char*",
            },
            {
                "name": "out_preview_ticket",
                "json_type": "string",
                "direction": "out",
                "resolved_type": "char*",
            },
            {
                "name": "out_len",
                "json_type": "integer",
                "description": "Buffer size",
                "resolved_type": "DWORD",
            },
        ],
    }

    repaired_args, repaired_selection = probe_loop._repair_target_scalar_args(  # noqa: SLF001
        inv,
        {
            "reservation_handle": "ACC-USB-C",
            "operator_token": "CUST-001",
            "out_preview_ticket": "",
            "out_len": 64,
        },
        {},
        {},
        None,
        lineage_hints={
            "reservation_id": "sp-resv-ORD-001-64",
            "auth_token": "sp-operator-ORD-001-session",
        },
        prefer_lineage=True,
    )

    assert repaired_args["reservation_handle"] == "sp-resv-ORD-001-64"
    assert repaired_args["operator_token"] == "sp-operator-ORD-001-session"
    assert repaired_selection["reservation_handle"]["expected_family"] == "reservation_id"
    assert repaired_selection["operator_token"]["expected_family"] == "auth_token"


def test_repair_target_scalar_args_prefers_verified_branch_lineage_for_audit_trace() -> None:
    inv = {
        "name": "SP_InvalidateUntrustedBranch",
        "doc_comment": (
            'Required preconditions: SP_SelectTrustedBranch | '
            'Canonical args: {"trusted_branch_id": "sp-branch-primary", '
            '"rejected_branch_id": "sp-branch-replay", '
            '"out_audit_token": "", "out_len": 64}'
        ),
        "parameters": [
            {
                "name": "trusted_branch_id",
                "json_type": "string",
                "description": "Trusted branch id selected after reconciliation.",
                "resolved_type": "const char*",
            },
            {
                "name": "rejected_branch_id",
                "json_type": "string",
                "description": "Rejected branch id invalidated by audit trace.",
                "resolved_type": "const char*",
            },
            {
                "name": "out_audit_token",
                "json_type": "string",
                "direction": "out",
                "resolved_type": "char*",
            },
            {
                "name": "out_len",
                "json_type": "integer",
                "description": "Buffer size",
                "resolved_type": "DWORD",
            },
        ],
    }

    repaired_args, repaired_selection = probe_loop._repair_target_scalar_args(  # noqa: SLF001
        inv,
        {
            "trusted_branch_id": "ACC-USB-C",
            "rejected_branch_id": "CUST-001",
            "out_audit_token": "",
            "out_len": 64,
        },
        {},
        {},
        None,
        lineage_hints={
            "trusted_branch_id": "sp-branch-primary",
            "rejected_branch_id": "sp-branch-replay",
        },
        prefer_lineage=True,
    )

    assert repaired_args["trusted_branch_id"] == "sp-branch-primary"
    assert repaired_args["rejected_branch_id"] == "sp-branch-replay"
    assert repaired_selection["trusted_branch_id"]["expected_family"] == "trusted_branch_id"
    assert repaired_selection["rejected_branch_id"]["expected_family"] == "rejected_branch_id"


def test_align_prerequisite_args_prefers_auth_token_lineage_hint_over_static_id() -> None:
    admission_trace: dict[str, object] = {}
    aligned = probe_loop._align_prerequisite_args(  # noqa: SLF001
        {
            "name": "SP_IssueReleaseHold",
            "parameters": [
                {
                    "name": "operator_token",
                    "json_type": "string",
                    "description": "Unlock token hex returned by the fixture",
                    "resolved_type": "const char*",
                },
                {
                    "name": "order_id",
                    "json_type": "string",
                    "description": "SP_IssueReleaseHold parameter",
                    "resolved_type": "const char*",
                },
            ],
            "doc_comment": (
                'Required preconditions: SP_OpenOperatorSession | Canonical args: '
                '{"operator_token": "sp-operator-ORD-001-session", "order_id": "ORD-001"}'
            ),
        },
        {"operator_token": "ACC-USB-C", "order_id": "ORD-001"},
        {"auth_token": "sp-operator-ORD-001-session"},
        {},
        admission_trace=admission_trace,
    )

    assert aligned["operator_token"] == "sp-operator-ORD-001-session"
    assert admission_trace["operator_token"]["source_lineage"] == "lineage_hint.auth_token"
    assert admission_trace["operator_token"]["admission_decision"] == "admitted_same_family_hint"


def test_allow_seeded_external_success_for_fresh_lineage_admits_trusted_runtime_prereq() -> None:
    assert probe_loop._allow_seeded_external_success_for_fresh_lineage(  # noqa: SLF001
        "SP_SelectTrustedBranch",
        runtime_prereqs=["SP_SelectTrustedBranch"],
        seeded_external_successes={"SP_SelectTrustedBranch"},
        fresh_replayed_successes=set(),
        trusted_checkpoint_seed_successes={"SP_SelectTrustedBranch"},
    )


def test_allow_seeded_external_success_for_fresh_lineage_blocks_untrusted_seed() -> None:
    assert not probe_loop._allow_seeded_external_success_for_fresh_lineage(  # noqa: SLF001
        "SP_SelectTrustedBranch",
        runtime_prereqs=["SP_SelectTrustedBranch"],
        seeded_external_successes={"SP_SelectTrustedBranch"},
        fresh_replayed_successes=set(),
        trusted_checkpoint_seed_successes=set(),
    )


def test_requires_fresh_runtime_lineage_for_branch_invalidation_consumer() -> None:
    inv = {
        "name": "SP_InvalidateUntrustedBranch",
        "doc_comment": (
            'Required preconditions: SP_SelectTrustedBranch | Canonical args: '
            '{"trusted_branch_id": "sp-branch-primary", "rejected_branch_id": "sp-branch-replay"}'
        ),
        "parameters": [
            {
                "name": "trusted_branch_id",
                "json_type": "string",
                "direction": "in",
                "description": "SP_InvalidateUntrustedBranch parameter",
                "resolved_type": "const char*",
            },
            {
                "name": "rejected_branch_id",
                "json_type": "string",
                "direction": "in",
                "description": "SP_InvalidateUntrustedBranch parameter",
                "resolved_type": "const char*",
            },
        ],
    }

    assert probe_loop._requires_fresh_runtime_lineage(inv)  # noqa: SLF001


def test_requires_fresh_runtime_lineage_for_stale_attestation_record_consumer() -> None:
    inv = {
        "name": "SP_RecordStaleAttestationInvalidation",
        "doc_comment": "Required preconditions: SP_InvalidateStaleAttestedRelease",
        "parameters": [
            {"name": "stale_attestation_token", "json_type": "string", "direction": "in"},
            {"name": "stale_reason", "json_type": "string", "direction": "in"},
            {"name": "out_audit_token", "json_type": "string", "direction": "out"},
            {"name": "out_len", "json_type": "integer", "direction": "in"},
        ],
    }

    assert probe_loop._requires_fresh_runtime_lineage(inv)  # noqa: SLF001


def test_branch_lineage_key_does_not_treat_untrusted_as_trusted() -> None:
    rejected_kind = probe_loop._lineage_hint_key(  # noqa: SLF001
        "rejected_branch_id",
        None,
        "string",
        "SP_InvalidateUntrustedBranch parameter",
    )
    trusted_kind = probe_loop._lineage_hint_key(  # noqa: SLF001
        "trusted_branch_id",
        None,
        "string",
        "SP_InvalidateUntrustedBranch parameter",
    )

    assert rejected_kind == "rejected_branch_id"
    assert trusted_kind == "trusted_branch_id"


def test_commit_receipt_lineage_hints_preserve_primary_and_replay_roles() -> None:
    hints = probe_loop._structured_target_hints(  # noqa: SLF001
        {
            "out_commit_receipt": "sp-commit-ORD-001-4200-receipt",
            "out_replay_receipt": "sp-branch-replay-ORD-001-4200-receipt",
        }
    )

    assert hints["primary_commit_receipt"] == "sp-commit-ORD-001-4200-receipt"
    assert hints["replay_commit_receipt"] == "sp-branch-replay-ORD-001-4200-receipt"
    assert hints["commit_receipt"] == "sp-commit-ORD-001-4200-receipt"


def test_select_trusted_branch_lineage_uses_distinct_primary_and_replay_receipts() -> None:
    inv = {
        "name": "SP_SelectTrustedBranch",
        "parameters": [
            {
                "name": "primary_commit_receipt",
                "json_type": "string",
                "direction": "in",
                "description": "Primary commit receipt selected from the trusted release path.",
                "resolved_type": "const char*",
            },
            {
                "name": "replay_commit_receipt",
                "json_type": "string",
                "direction": "in",
                "description": "Replay commit receipt selected from the rejected branch path.",
                "resolved_type": "const char*",
            },
            {
                "name": "out_trusted_branch_id",
                "json_type": "string",
                "direction": "out",
                "resolved_type": "char*",
            },
            {
                "name": "out_rejected_branch_id",
                "json_type": "string",
                "direction": "out",
                "resolved_type": "char*",
            },
            {
                "name": "out_len",
                "json_type": "integer",
                "direction": "in",
                "description": "output buffer size",
                "resolved_type": "DWORD",
            },
        ],
    }

    args, selection = probe_loop._repair_target_scalar_args(  # noqa: SLF001
        inv,
        {
            "primary_commit_receipt": "sp-branch-replay-ORD-001-4200-receipt",
            "replay_commit_receipt": "sp-branch-replay-ORD-001-4200-receipt",
            "out_trusted_branch_id": "sp-branch-replay-ORD-001-4200-receipt",
            "out_rejected_branch_id": "sp-branch-replay-ORD-001-4200-receipt",
            "out_len": 1,
        },
        {},
        {},
        None,
        lineage_hints={
            "commit_receipt": "sp-branch-replay-ORD-001-4200-receipt",
            "primary_commit_receipt": "sp-commit-ORD-001-4200-receipt",
            "replay_commit_receipt": "sp-branch-replay-ORD-001-4200-receipt",
        },
        prefer_lineage=True,
    )
    args, selection = probe_loop._normalize_true_output_scalar_args(inv, args, selection)  # noqa: SLF001

    assert args["primary_commit_receipt"] == "sp-commit-ORD-001-4200-receipt"
    assert args["replay_commit_receipt"] == "sp-branch-replay-ORD-001-4200-receipt"
    assert args["primary_commit_receipt"] != args["replay_commit_receipt"]
    assert args["out_trusted_branch_id"] == ""
    assert args["out_rejected_branch_id"] == ""
    assert selection["primary_commit_receipt"]["source_lineage"] == "lineage_hint.primary_commit_receipt"
    assert selection["replay_commit_receipt"]["source_lineage"] == "lineage_hint.replay_commit_receipt"
    assert selection["out_trusted_branch_id"]["source"] == "output.bridge_slot"


def test_branch_invalidation_lineage_prefers_rejected_branch_for_rejected_slot() -> None:
    inv = {
        "name": "SP_InvalidateUntrustedBranch",
        "doc_comment": (
            'Required preconditions: SP_SelectTrustedBranch | Canonical args: '
            '{"trusted_branch_id": "sp-branch-primary", "rejected_branch_id": "sp-branch-replay"}'
        ),
        "parameters": [
            {
                "name": "trusted_branch_id",
                "json_type": "string",
                "direction": "in",
                "description": "SP_InvalidateUntrustedBranch parameter",
                "resolved_type": "const char*",
            },
            {
                "name": "rejected_branch_id",
                "json_type": "string",
                "direction": "in",
                "description": "SP_InvalidateUntrustedBranch parameter",
                "resolved_type": "const char*",
            },
            {
                "name": "out_audit_token",
                "json_type": "string",
                "direction": "out",
                "description": "SP_InvalidateUntrustedBranch output token",
                "resolved_type": "char*",
            },
            {
                "name": "out_len",
                "json_type": "integer",
                "direction": "in",
                "description": "output buffer size",
                "resolved_type": "DWORD",
            },
        ],
    }

    args, selection = probe_loop._repair_target_scalar_args(  # noqa: SLF001
        inv,
        {
            "trusted_branch_id": "sp-branch-primary",
            "rejected_branch_id": "sp-branch-primary",
            "out_audit_token": "sp-branch-primary",
            "out_len": 64,
        },
        {},
        {},
        None,
        lineage_hints={
            "trusted_branch_id": "sp-branch-primary",
            "rejected_branch_id": "sp-branch-replay",
        },
        prefer_lineage=True,
    )
    args, selection = probe_loop._normalize_true_output_scalar_args(inv, args, selection)  # noqa: SLF001

    assert args["trusted_branch_id"] == "sp-branch-primary"
    assert args["rejected_branch_id"] == "sp-branch-replay"
    assert args["out_audit_token"] == ""
    assert selection["trusted_branch_id"]["source_lineage"] == "lineage_hint.trusted_branch_id"
    assert selection["rejected_branch_id"]["source_lineage"] == "lineage_hint.rejected_branch_id"
    assert selection["out_audit_token"]["source"] == "output.bridge_slot"


def test_out_prefixed_char_buffer_is_normalized_before_lineage_selection() -> None:
    inv = {
        "name": "SP_InvalidateUntrustedBranch",
        "parameters": [
            {"name": "trusted_branch_id", "json_type": "string", "direction": "in", "resolved_type": "const char*"},
            {"name": "rejected_branch_id", "json_type": "string", "direction": "in", "resolved_type": "const char*"},
            {"name": "out_audit_token", "json_type": "string", "direction": "in", "resolved_type": "char*"},
            {"name": "out_len", "json_type": "integer", "direction": "in", "resolved_type": "DWORD"},
        ],
    }

    args, selection = probe_loop._normalize_true_output_scalar_args(  # noqa: SLF001
        inv,
        {"out_audit_token": "sp-branch-primary", "out_len": 1},
        {},
    )

    assert args["out_audit_token"] == ""
    assert args["out_len"] == 64
    assert selection["out_audit_token"]["source"] == "output.bridge_slot"
    assert selection["out_len"]["source"] == "output.buffer_size_default"


def test_medium02_stage_outputs_promote_to_consumer_ready_lineage() -> None:
    hints = probe_loop._collect_live_lineage_hints(  # noqa: SLF001
        {
            "out_invoice_stage_id": "sp-invoice-stage-ORD-20040301-0042-2500-gate-packet-bill",
            "out_entitlement_stage_id": "sp-entitlement-stage-ORD-001-64-gate-packet-grant",
            "out_confirmation_id": "sp-confirm-ACC-USB-C-attested",
        },
        "Returned: 0\nout_attestation_packet='sp-att-ORD-20040301-0042-2500-gate-packet'",
    )

    assert hints["attestation_packet"] == "sp-att-ORD-20040301-0042-2500-gate-packet"
    assert hints["invoice_stage_id"] == "sp-invoice-stage-ORD-20040301-0042-2500-gate-packet-bill"
    assert hints["entitlement_stage_id"] == "sp-entitlement-stage-ORD-001-64-gate-packet-grant"
    assert hints["confirmation_id"] == "sp-confirm-ACC-USB-C-attested"


def test_medium02_stage_ids_reject_generic_operator_token_lineage() -> None:
    assert not probe_loop._is_live_lineage_hint_value(  # noqa: SLF001
        "invoice_stage_id",
        "out_operator_token",
    )
    assert not probe_loop._is_live_lineage_hint_value(  # noqa: SLF001
        "entitlement_stage_id",
        "sp-operator-ORD-001-session",
    )


def test_confirm_attested_release_lineage_uses_stage_ids_not_operator_token() -> None:
    inv = {
        "name": "SP_ConfirmAttestedRelease",
        "parameters": [
            {"name": "attestation_packet", "json_type": "string", "direction": "in", "resolved_type": "const char*"},
            {"name": "invoice_stage_id", "json_type": "string", "direction": "in", "resolved_type": "const char*"},
            {"name": "entitlement_stage_id", "json_type": "string", "direction": "in", "resolved_type": "const char*"},
            {"name": "out_confirmation_id", "json_type": "string", "direction": "in", "resolved_type": "char*"},
            {"name": "out_len", "json_type": "integer", "direction": "in", "resolved_type": "DWORD"},
        ],
    }

    admission_trace: dict[str, object] = {}
    aligned = probe_loop._align_prerequisite_args(  # noqa: SLF001
        inv,
        {
            "attestation_packet": "sp-att-ORD-001-64-gate-packet",
            "invoice_stage_id": "out_operator_token",
            "entitlement_stage_id": "out_operator_token",
            "out_confirmation_id": "out_operator_token",
            "out_len": 1,
        },
        {
            "attestation_packet": "sp-att-ORD-20040301-0042-2500-gate-packet",
            "invoice_stage_id": "sp-invoice-stage-ORD-20040301-0042-2500-gate-packet-bill",
            "entitlement_stage_id": "sp-entitlement-stage-ORD-001-64-gate-packet-grant",
            "auth_token": "sp-operator-ORD-001-session",
        },
        {},
        admission_trace,
    )
    aligned, selection = probe_loop._normalize_true_output_scalar_args(inv, aligned, {})  # noqa: SLF001

    assert aligned["attestation_packet"] == "sp-att-ORD-20040301-0042-2500-gate-packet"
    assert aligned["invoice_stage_id"] == "sp-invoice-stage-ORD-20040301-0042-2500-gate-packet-bill"
    assert aligned["entitlement_stage_id"] == "sp-entitlement-stage-ORD-001-64-gate-packet-grant"
    assert aligned["out_confirmation_id"] == ""
    assert aligned["out_len"] == 64
    assert admission_trace["invoice_stage_id"]["source_lineage"] == "lineage_hint.invoice_stage_id"
    assert admission_trace["entitlement_stage_id"]["source_lineage"] == "lineage_hint.entitlement_stage_id"
    assert selection["out_confirmation_id"]["source"] == "output.bridge_slot"


def test_lineage_hint_key_emits_stale_attestation_families() -> None:
    assert probe_loop._lineage_hint_key(  # noqa: SLF001
        "attestation_epoch",
        20260408,
        "integer",
        "Release attestation epoch.",
    ) == "attestation_epoch"
    assert probe_loop._lineage_hint_key(  # noqa: SLF001
        "stale_attestation_token",
        "sp-att-stale-16227",
        "string",
        "Verified stale attestation token.",
    ) == "stale_attestation_token"
    assert probe_loop._lineage_hint_key(  # noqa: SLF001
        "stale_reason",
        "freshness_gap|epoch=20260408|packet=sp-att-ORD-001-64-gate-packet",
        "string",
        "Verified stale reason.",
    ) == "stale_reason"


def test_collect_live_lineage_hints_reads_stale_attestation_outputs() -> None:
    hints = probe_loop._collect_live_lineage_hints(  # noqa: SLF001
        {
            "out_attestation_epoch": 20260408,
            "out_stale_attestation_token": "sp-att-stale-16227",
            "out_stale_reason": "freshness_gap|epoch=20260408|packet=sp-att-ORD-001-64-gate-packet",
        },
        "Returned: 0\n"
        "out_stale_attestation_token='sp-att-stale-16227'\n"
        "out_stale_reason='freshness_gap|epoch=20260408|packet=sp-att-ORD-001-64-gate-packet'\n",
    )

    assert hints["attestation_epoch"] == 20260408
    assert hints["stale_attestation_token"] == "sp-att-stale-16227"
    assert hints["stale_reason"] == "freshness_gap|epoch=20260408|packet=sp-att-ORD-001-64-gate-packet"


def test_stale_attestation_invalidation_prefers_epoch_lineage_over_default() -> None:
    inv = {
        "name": "SP_InvalidateStaleAttestedRelease",
        "parameters": [
            {"name": "attestation_packet", "json_type": "string", "direction": "in", "resolved_type": "const char*"},
            {"name": "attestation_nonce", "json_type": "integer", "direction": "in", "resolved_type": "uint32_t"},
            {"name": "attestation_epoch", "json_type": "integer", "direction": "in", "resolved_type": "uint32_t"},
            {"name": "out_stale_attestation_token", "json_type": "string", "direction": "in", "resolved_type": "char*"},
            {"name": "token_len", "json_type": "integer", "direction": "in", "resolved_type": "DWORD"},
            {"name": "out_stale_reason", "json_type": "string", "direction": "in", "resolved_type": "char*"},
            {"name": "reason_len", "json_type": "integer", "direction": "in", "resolved_type": "DWORD"},
        ],
    }

    args, selection = probe_loop._repair_target_scalar_args(  # noqa: SLF001
        inv,
        {
            "attestation_packet": "sp-att-ORD-001-64-gate-packet",
            "attestation_nonce": 1,
            "attestation_epoch": 1,
            "out_stale_attestation_token": "sp-operator-easy01-operator-session",
            "token_len": 1,
            "out_stale_reason": "out_operator_token",
            "reason_len": 1,
        },
        {},
        {},
        None,
        lineage_hints={
            "attestation_packet": "sp-att-ORD-20040301-0042-2500-gate-packet",
            "nonce": 2809135139,
            "attestation_epoch": 20260408,
        },
        prefer_lineage=True,
    )
    args, selection = probe_loop._normalize_true_output_scalar_args(inv, args, selection)  # noqa: SLF001

    assert args["attestation_packet"] == "sp-att-ORD-20040301-0042-2500-gate-packet"
    assert args["attestation_nonce"] == 2809135139
    assert args["attestation_epoch"] == 20260408
    assert args["out_stale_attestation_token"] == ""
    assert args["out_stale_reason"] == ""
    assert args["token_len"] == 64
    assert selection["attestation_epoch"]["source_lineage"] == "lineage_hint.attestation_epoch"
    assert selection["out_stale_attestation_token"]["source"] == "output.bridge_slot"


def test_record_stale_attestation_uses_verified_stale_outputs_not_operator_token() -> None:
    inv = {
        "name": "SP_RecordStaleAttestationInvalidation",
        "parameters": [
            {"name": "stale_attestation_token", "json_type": "string", "direction": "in", "resolved_type": "const char*"},
            {"name": "stale_reason", "json_type": "string", "direction": "in", "resolved_type": "const char*"},
            {"name": "out_audit_token", "json_type": "string", "direction": "in", "resolved_type": "char*"},
            {"name": "out_len", "json_type": "integer", "direction": "in", "resolved_type": "DWORD"},
        ],
    }

    args, selection = probe_loop._repair_target_scalar_args(  # noqa: SLF001
        inv,
        {
            "stale_attestation_token": "sp-operator-easy01-operator-session",
            "stale_reason": "out_operator_token",
            "out_audit_token": "sp-operator-easy01-operator-session",
            "out_len": 1,
        },
        {},
        {},
        None,
        lineage_hints={
            "stale_attestation_token": "sp-att-stale-16227",
            "stale_reason": "freshness_gap|epoch=20260408|packet=sp-att-ORD-001-64-gate-packet",
        },
        prefer_lineage=True,
    )
    args, selection = probe_loop._normalize_true_output_scalar_args(inv, args, selection)  # noqa: SLF001

    assert args["stale_attestation_token"] == "sp-att-stale-16227"
    assert args["stale_reason"] == "freshness_gap|epoch=20260408|packet=sp-att-ORD-001-64-gate-packet"
    assert args["out_audit_token"] == ""
    assert args["out_len"] == 64
    assert selection["stale_attestation_token"]["source_lineage"] == "lineage_hint.stale_attestation_token"
    assert selection["stale_reason"]["source_lineage"] == "lineage_hint.stale_reason"
    assert selection["out_audit_token"]["source"] == "output.bridge_slot"
