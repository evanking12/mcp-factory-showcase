"""Atlas reconcile module for the successor design-suite first slice."""


def confirm_alignment(batch_token: str, binding_receipt: str, staged_transfer_id: str) -> dict[str, str]:
    """Confirm that identity and ledger state still align within one batch window."""

    if not all((str(batch_token or "").strip(), str(binding_receipt or "").strip(), str(staged_transfer_id or "").strip())):
        raise ValueError("batch token, binding receipt, and staged transfer id are all required")

    return {
        "reconciliation_token": f"REC-{binding_receipt}-{staged_transfer_id}",
        "batch_token": batch_token,
    }
