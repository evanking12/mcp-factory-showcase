"""Dispatch preview consumer for medium fanout pressure."""


def prepare_release_preview(reservation_handle: str, operator_token: str) -> dict[str, str]:
    """Stage a dispatch preview from the shared reservation handle."""

    if not all((str(reservation_handle or "").strip(), str(operator_token or "").strip())):
        raise ValueError("reservation handle and operator token are required")

    return {
        "preview_ticket": f"PREVIEW-{reservation_handle}",
        "operator_token": str(operator_token).strip(),
    }
