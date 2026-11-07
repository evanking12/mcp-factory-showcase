"""Northstar inventory module for the first bounded design-suite slice."""


def reserve_item(session_token: str, sku: str) -> dict[str, str]:
    """Consume the bootstrap token and emit a reservation id."""

    return {
        "reservation_id": f"RSV-{sku}",
        "session_token": session_token,
    }
