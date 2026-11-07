"""Audit trace module for anchor and hard cases."""


def record_release_receipt(commit_receipt: str, operator_token: str) -> dict[str, str]:
    """Emit the anchor case audit receipt."""

    if not all((str(commit_receipt or "").strip(), str(operator_token or "").strip())):
        raise ValueError("commit receipt and operator token are required")

    return {
        "audit_receipt": f"AUDIT-{commit_receipt}",
        "operator_token": str(operator_token).strip(),
    }


def invalidate_untrusted_branch(trusted_branch_id: str, rejected_branch_id: str) -> dict[str, str]:
    """Emit the late hard-case invalidation of the rejected replay branch."""

    if not all((str(trusted_branch_id or "").strip(), str(rejected_branch_id or "").strip())):
        raise ValueError("trusted and rejected branch ids are required")

    return {
        "audit_invalidation_token": f"INVALID-{rejected_branch_id}",
        "trusted_branch_id": str(trusted_branch_id).strip(),
    }


def record_stale_attestation_invalidation(stale_attestation_token: str, stale_reason: str) -> dict[str, str]:
    """Emit the late audit record for stale attestation invalidation."""

    if not all((str(stale_attestation_token or "").strip(), str(stale_reason or "").strip())):
        raise ValueError("stale attestation token and stale reason are required")

    return {
        "audit_stale_receipt": f"AUDIT-{stale_attestation_token}",
        "stale_reason": str(stale_reason).strip(),
    }
