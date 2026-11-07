"""Atlas ledger module for the successor design-suite first slice."""


def stage_transfer(batch_token: str, sequence_window: str, amount_cents: int) -> dict[str, str]:
    """Stage the transfer into the ledger but remain provisional until reconcile."""

    if not str(batch_token or "").strip() or not str(sequence_window or "").strip():
        raise ValueError("batch token and sequence window required before staging transfer")

    return {
        "staged_transfer_id": f"STAGED-{amount_cents}",
        "batch_token": batch_token,
        "ledger_window": sequence_window,
    }
