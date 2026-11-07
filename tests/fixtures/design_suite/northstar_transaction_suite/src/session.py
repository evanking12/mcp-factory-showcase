"""Northstar session module for the first bounded design-suite slice."""


def bootstrap_session(customer_id: str) -> dict[str, str]:
    """Emit the first session token and customer context."""

    return {
        "session_token": f"NST-{customer_id}",
        "customer_context": customer_id,
        "sequence_nonce": "SEQ-0001",
    }
