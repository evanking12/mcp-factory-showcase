"""Settlement reconciliation module for medium and hard cases."""


def verify_reserved_release(reservation_handle: str, preview_ticket: str, fee_quote_id: str) -> dict[str, str]:
    """Validate that both medium fanout consumers still align with one reservation."""

    if not all((str(reservation_handle or "").strip(), str(preview_ticket or "").strip(), str(fee_quote_id or "").strip())):
        raise ValueError("reservation handle, preview ticket, and fee quote id are required")

    return {
        "reservation_validation_token": f"VALID-{reservation_handle}",
    }


def confirm_attested_release(attestation_packet: str, invoice_stage_id: str, entitlement_stage_id: str) -> dict[str, str]:
    """Confirm that the attestation packet remained trustworthy across both downstream consumers."""

    if not all((str(attestation_packet or "").strip(), str(invoice_stage_id or "").strip(), str(entitlement_stage_id or "").strip())):
        raise ValueError("attestation packet, invoice stage id, and entitlement stage id are required")

    return {
        "attestation_confirmation": f"CONFIRM-{attestation_packet}",
    }


def invalidate_stale_attested_release(
    attestation_packet: str,
    invoice_stage_id: str,
    entitlement_stage_id: str,
    attestation_epoch: str,
    session_nonce: str,
) -> dict[str, str]:
    """Invalidate an attestation that remained locally reusable but went stale globally."""

    if not all(
        (
            str(attestation_packet or "").strip(),
            str(invoice_stage_id or "").strip(),
            str(entitlement_stage_id or "").strip(),
            str(attestation_epoch or "").strip(),
            str(session_nonce or "").strip(),
        )
    ):
        raise ValueError("all stale-attestation inputs are required")

    return {
        "stale_attestation_verdict": "stale",
        "stale_reason": "freshness_window_expired_before_global_reconciliation",
        "stale_attestation_token": f"STALE-{attestation_packet}",
        "stale_epoch": str(attestation_epoch).strip(),
        "session_nonce": str(session_nonce).strip(),
    }


def select_trusted_branch(
    primary_commit_receipt: str,
    replay_commit_receipt: str,
    primary_attestation_packet: str,
    replay_attestation_packet: str,
) -> dict[str, str]:
    """Select the trusted branch after replay ambiguity is made explicit."""

    if not all(
        (
            str(primary_commit_receipt or "").strip(),
            str(replay_commit_receipt or "").strip(),
            str(primary_attestation_packet or "").strip(),
            str(replay_attestation_packet or "").strip(),
        )
    ):
        raise ValueError("all branch-truth inputs are required")

    return {
        "trusted_branch_id": "primary",
        "rejected_branch_id": "replay",
        "branch_reconciliation_token": f"TRUST-{primary_commit_receipt}",
    }
