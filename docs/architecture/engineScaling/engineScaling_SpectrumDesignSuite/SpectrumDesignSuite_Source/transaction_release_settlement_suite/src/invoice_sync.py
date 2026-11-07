"""Invoice sync consumer for attestation-driven cases."""


def stage_release_invoice(
    attestation_packet: str,
    operator_token: str,
    attestation_epoch: str | None = None,
) -> dict[str, str]:
    """Stage invoice sync from an attestation packet."""

    if not all((str(attestation_packet or "").strip(), str(operator_token or "").strip())):
        raise ValueError("attestation packet and operator token are required")

    normalized_packet = str(attestation_packet).strip()
    return {
        "invoice_stage_id": f"INV-{normalized_packet}",
        "operator_token": str(operator_token).strip(),
        "consumed_attestation_packet": normalized_packet,
        "consumed_attestation_epoch": str(attestation_epoch or "epoch-unknown").strip(),
    }
