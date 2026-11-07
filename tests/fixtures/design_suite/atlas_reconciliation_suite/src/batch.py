"""Atlas batch module for the successor design-suite first slice."""


def open_batch(tenant_id: str) -> dict[str, str]:
    """Emit the shared batch window used by both provisional upstream families."""

    return {
        "batch_token": f"ATLAS-BATCH-{tenant_id}",
        "sequence_window": "WINDOW-7300",
        "tenant_context": tenant_id,
    }
