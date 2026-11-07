"""Reservation staging module for the spectrum transaction release suite."""


def issue_release_hold(operator_token: str, order_id: str, amount_cents: int) -> dict[str, str | int]:
    """Emit the reservation handle and hold token used across the family."""

    if not all((str(operator_token or "").strip(), str(order_id or "").strip())):
        raise ValueError("operator token and order id are required")
    if int(amount_cents) <= 0:
        raise ValueError("amount_cents must be positive")

    return {
        "reservation_handle": f"RES-{order_id}",
        "hold_token": f"HOLD-{order_id}",
        "release_nonce": f"REL-{order_id}",
        "amount_cents": int(amount_cents),
        "operator_token": str(operator_token).strip(),
    }
