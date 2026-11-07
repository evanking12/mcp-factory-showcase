"""Session bootstrap module for the spectrum transaction release suite."""


def open_operator_session(operator_id: str) -> dict[str, str]:
    """Emit the operator session state used by every later case."""

    if not str(operator_id or "").strip():
        raise ValueError("operator_id is required")

    normalized = str(operator_id).strip()
    return {
        "operator_token": f"OPS-{normalized}",
        "session_nonce": f"NONCE-{normalized}",
        "operator_context": normalized,
    }
