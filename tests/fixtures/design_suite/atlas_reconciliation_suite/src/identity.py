"""Atlas identity module for the successor design-suite first slice."""


def bind_party(batch_token: str, party_id: str) -> dict[str, str]:
    """Bind party identity into the batch but remain provisional until reconcile."""

    if not str(batch_token or "").strip():
        raise ValueError("batch token required before binding party")

    return {
        "binding_receipt": f"BIND-{party_id}",
        "batch_token": batch_token,
        "identity_window": "IDENTITY-WINDOW",
    }
