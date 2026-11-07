from __future__ import annotations

from api.pipeline.core.evidence_candidates import EvidenceCandidateRegistry
from api.pipeline.core.evidence_candidates import TIER_RUNTIME
from api.pipeline.core.evidence_candidates import classify_value_kind
from api.pipeline.core.evidence_candidates import infer_expected_identifier_family
from api.pipeline.core.evidence_candidates import infer_identifier_family_from_value


def test_seed_tier1_ghidra_accepts_dict_style_enum_members() -> None:
    ecr = EvidenceCandidateRegistry()

    added = ecr.seed_tier1_ghidra(
        invocables=[],
        ghidra_data_types=[
            {
                "kind": "enum",
                "name": "CP_STATUS",
                "members": {
                    "CP_OK": 0,
                    "CP_ERR_NOSTOCK": -4,
                },
            }
        ],
    )

    assert added == 2
    values = [entry.value for entry in ecr.query("flag", max_results=10)]
    assert 0 in values
    assert -4 in values


def test_seed_tier1_ghidra_ignores_struct_and_typedef_value_seeds() -> None:
    ecr = EvidenceCandidateRegistry()

    added = ecr.seed_tier1_ghidra(
        invocables=[],
        ghidra_data_types=[
            {
                "kind": "struct",
                "name": "CS_RECORD",
                "fields": [
                    {"name": "customer_id", "type": "char *"},
                    {"name": "points", "type": "uint"},
                ],
            },
            {
                "kind": "typedef",
                "name": "CS_HANDLE",
                "base_type": "void *",
            },
        ],
    )

    assert added == 0
    assert ecr.query("type_hint", max_results=10) == []


def test_seed_tier1_ghidra_ignores_decompiler_param_type_records_as_values() -> None:
    ecr = EvidenceCandidateRegistry()

    added = ecr.seed_tier1_ghidra(
        invocables=[
            {
                "name": "CP_ProcessPurchase",
                "parameters": [
                    {
                        "name": "param_1",
                        "json_type": "string",
                    },
                    {
                        "name": "param_2",
                        "json_type": "integer",
                    },
                ],
                "_ghidra_provenance": {
                    "params": {
                        "param_1": {
                            "param_type": {
                                "value": "char *",
                                "source_method": "decompiler",
                                "trust_level": "medium",
                                "confidence": 0.75,
                            },
                            "direction": {
                                "value": "in",
                                "source_method": "heuristic",
                                "trust_level": "low",
                                "confidence": 0.35,
                            },
                        },
                        "param_2": {
                            "param_type": {
                                "value": "uint",
                                "source_method": "decompiler",
                                "trust_level": "medium",
                                "confidence": 0.75,
                            },
                            "direction": {
                                "value": "in",
                                "source_method": "heuristic",
                                "trust_level": "low",
                                "confidence": 0.35,
                            },
                        },
                    }
                },
            }
        ],
        ghidra_data_types=[],
    )

    assert added == 0
    assert ecr.query("string_id", max_results=10) == []
    assert ecr.query("integer", max_results=10) == []


def test_merge_from_can_filter_out_generic_and_static_carry_forward_noise() -> None:
    source = EvidenceCandidateRegistry()
    source.add("TEST", 0, "generic", "generic_string", 0.7, "seed")
    source.add("CUST-001", 1, "vocab.id_formats", "customer_id", 0.9, "seed")
    source.add("WFH-OPEN-001", TIER_RUNTIME, "runtime:WF_OpenFulfillment", "handle", 1.0, "probe")

    dest = EvidenceCandidateRegistry()
    merged = dest.merge_from(source, tier_override=3, min_tier=TIER_RUNTIME)

    assert merged == 1
    handle = dest.query("handle", max_results=5)
    assert len(handle) == 1
    assert handle[0].value == "WFH-OPEN-001"
    assert dest.query("customer_id", max_results=5) == []


def test_infer_identifier_family_from_value_recognizes_spectrum_runtime_lineage_tokens() -> None:
    assert infer_identifier_family_from_value("sp-operator-ORD-001-session") == "auth_token"
    assert infer_identifier_family_from_value("sp-resv-easy01-order-211137360") == "reservation_id"
    assert infer_identifier_family_from_value("sp-preview-easy01-order-211137360-gate") == "preview_ticket"
    assert infer_identifier_family_from_value("sp-fee-easy01-order-211137360-quote") == "fee_quote_id"
    assert infer_identifier_family_from_value("sp-att-easy01-order-211137360-gate-packet") == "attestation_packet"
    assert infer_identifier_family_from_value("sp-hold-easy01-order-37360") == "hold_token"
    assert infer_identifier_family_from_value("sp-commit-easy01-order-991") == "commit_receipt"
    assert infer_identifier_family_from_value("sp-branch-replay-ORD-001-4200-receipt") == "commit_receipt"


def test_infer_identifier_family_from_value_does_not_promote_generic_commit_receipt_placeholders() -> None:
    assert classify_value_kind("valid_receipt") == "string_id"
    assert (
        infer_identifier_family_from_value(
            "valid_receipt",
            param_kind="commit_receipt",
            source_function="SP_CommitRelease",
        )
        is None
    )


def test_infer_expected_identifier_family_uses_spectrum_prefix_hints_in_description() -> None:
    assert infer_expected_identifier_family(
        "param_1",
        'Input text parameter (must start with "sp-resv-")',
        "string",
        "SP_CommitRelease",
        [],
        resolved_type="char *",
    ) == "reservation_id"
    assert infer_expected_identifier_family(
        "param_2",
        'Input text parameter (must start with "sp-hold-")',
        "string",
        "SP_CommitRelease",
        [],
        resolved_type="char *",
    ) == "hold_token"
    assert infer_expected_identifier_family(
        "operator_token",
        "Unlock token hex returned by the fixture.",
        "string",
        "SP_IssueReleaseHold",
        [],
        resolved_type="char *",
    ) == "auth_token"
    assert infer_expected_identifier_family(
        "preview_ticket",
        "Preview ticket generated by the release preview stage.",
        "string",
        "SP_EmitReleaseAttestation",
        [],
        resolved_type="char *",
    ) == "preview_ticket"
    assert infer_expected_identifier_family(
        "fee_quote_id",
        "Fee quote identifier produced for the release.",
        "string",
        "SP_EmitReleaseAttestation",
        [],
        resolved_type="char *",
    ) == "fee_quote_id"
    assert infer_expected_identifier_family(
        "out_attestation_packet",
        "Output attestation packet populated by this function.",
        "string",
        "SP_EmitReleaseAttestation",
        [],
        resolved_type="char *",
    ) == "attestation_packet"
    assert infer_expected_identifier_family(
        "trusted_branch_id",
        "Trusted branch id selected after reconciliation.",
        "string",
        "SP_InvalidateUntrustedBranch",
        [],
        resolved_type="char *",
    ) == "trusted_branch_id"
    assert infer_expected_identifier_family(
        "rejected_branch_id",
        "Rejected branch id invalidated by audit trace.",
        "string",
        "SP_InvalidateUntrustedBranch",
        [],
        resolved_type="char *",
    ) == "rejected_branch_id"


def test_query_for_param_prefers_attestation_packet_runtime_candidate() -> None:
    ecr = EvidenceCandidateRegistry()
    ecr.seed_tier0()
    ecr.add(
        "sp-att-ORD-20040301-0042-2500-gate-packet",
        TIER_RUNTIME,
        "working_call:SP_EmitReleaseAttestation",
        "attestation_packet",
        1.0,
        "SP_EmitReleaseAttestation",
    )

    candidates = ecr.get_best_for_param(
        "attestation_packet",
        "string",
        "Attestation packet consumed by the invoice stage.",
        "SP_StageReleaseInvoice",
    )

    assert candidates
    assert candidates[0]["value"] == "sp-att-ORD-20040301-0042-2500-gate-packet"
    assert candidates[0]["expected_family"] == "attestation_packet"
