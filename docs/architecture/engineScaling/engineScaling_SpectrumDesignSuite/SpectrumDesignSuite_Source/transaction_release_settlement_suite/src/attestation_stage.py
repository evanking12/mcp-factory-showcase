"""Attestation-producing module for medium and hard stale-state cases."""


def emit_release_attestation(
    reservation_handle: str,
    hold_token: str,
    session_nonce: str | None = None,
) -> dict[str, str]:
    """Emit a downstream attestation packet reused by later consumers."""

    if not all((str(reservation_handle or "").strip(), str(hold_token or "").strip())):
        raise ValueError("reservation handle and hold token are required")

    normalized_handle = str(reservation_handle).strip()
    normalized_hold = str(hold_token).strip()
    normalized_session = str(session_nonce or "session-unknown").strip()
    return {
        "attestation_packet": f"ATTEST-{normalized_handle}",
        "attestation_nonce": f"ATN-{normalized_hold}",
        "attestation_epoch": f"EPOCH-{normalized_session}",
        "attestation_lineage_key": f"LINEAGE-{normalized_handle}",
        "attestation_freshness_window": "current-session",
    }
