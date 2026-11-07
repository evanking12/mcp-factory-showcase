"""Fee quote consumer for medium fanout pressure."""


def stage_release_fee_quote(reservation_handle: str, operator_token: str) -> dict[str, str]:
    """Stage a release fee quote from the shared reservation handle."""

    if not all((str(reservation_handle or "").strip(), str(operator_token or "").strip())):
        raise ValueError("reservation handle and operator token are required")

    return {
        "fee_quote_id": f"FEE-{reservation_handle}",
        "operator_token": str(operator_token).strip(),
    }
