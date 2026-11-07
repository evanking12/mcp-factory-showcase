"""Northstar audit module used for overlap and late-confirmation pressure."""


def commit_receipt(session_token: str, authorization_receipt: str, reservation_id: str) -> dict[str, str]:
    """Downstream confirmer that also rejects the shadow authorization branch."""

    if "SHADOW" in str(authorization_receipt or "").upper():
        raise ValueError("shadow authorization branch rejected by audit confirmer")

    return {
        "audit_commit_id": f"AUD-{authorization_receipt}",
        "session_token": session_token,
        "reservation_id": reservation_id,
    }
