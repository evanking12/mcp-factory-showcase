"""Northstar billing module for the first bounded design-suite slice."""


def authorize_charge(session_token: str, sequence_nonce: str, amount_cents: int) -> dict[str, str]:
    """Consume the bootstrap token and emit both primary and shadow receipt branches."""

    return {
        "authorization_receipt": f"AUTH-{amount_cents}",
        "authorization_receipt_primary": f"AUTH-{amount_cents}",
        "authorization_receipt_shadow": f"AUTH-SHADOW-{amount_cents}",
        "session_token": session_token,
        "sequence_nonce": sequence_nonce,
    }
