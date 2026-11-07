"""Northstar notifications module reserved as the noisy side consumer."""


def send_receipt(audit_commit_id: str) -> dict[str, str]:
    """Deferred noisy side-consumer kept last to preserve early grouping clarity."""

    return {
        "notification_id": f"NTF-{audit_commit_id}",
    }
