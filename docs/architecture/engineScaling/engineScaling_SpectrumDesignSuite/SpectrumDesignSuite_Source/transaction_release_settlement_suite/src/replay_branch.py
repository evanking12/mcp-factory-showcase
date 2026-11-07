"""Replay branch module for the hard case."""


def replay_release_branch(reservation_handle: str, hold_token: str) -> dict[str, str]:
    """Emit a locally plausible replay branch that can look valid in isolation."""

    if not all((str(reservation_handle or "").strip(), str(hold_token or "").strip())):
        raise ValueError("reservation handle and hold token are required")

    normalized_handle = str(reservation_handle).strip()
    normalized_hold = str(hold_token).strip()
    return {
        "replay_branch_id": f"REPLAY-{normalized_handle}",
        "replay_commit_receipt": f"REPLAY-COMMIT-{normalized_handle}",
        "replay_attestation_packet": f"REPLAY-ATTEST-{normalized_hold}",
    }
