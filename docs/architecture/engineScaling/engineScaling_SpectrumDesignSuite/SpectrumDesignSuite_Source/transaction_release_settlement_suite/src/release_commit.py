"""Release commit module for anchor and hard cases."""


def commit_release(reservation_handle: str, hold_token: str) -> dict[str, str]:
    """Commit a staged release."""

    if not all((str(reservation_handle or "").strip(), str(hold_token or "").strip())):
        raise ValueError("reservation handle and hold token are required")

    return {
        "commit_receipt": f"COMMIT-{reservation_handle}",
        "hold_token": str(hold_token).strip(),
    }
