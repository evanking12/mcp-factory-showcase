from __future__ import annotations

from api.pipeline.core.handoff_contract import AUDITOR_VERSION, CONTRACT_VERSION

# Explicit matrix: auditor -> accepted contract versions.
# Expand only on intentional version bumps.
COMPATIBILITY_MATRIX: dict[str, frozenset[str]] = {
    AUDITOR_VERSION: frozenset({CONTRACT_VERSION}),
}


def is_capture_compatible(auditor_version: str, contract_version: str) -> bool:
    # Legacy captures may not carry version metadata yet; keep transition additive.
    if not str(auditor_version or "").strip() or not str(contract_version or "").strip():
        return True
    accepted = COMPATIBILITY_MATRIX.get(str(auditor_version), frozenset())
    return str(contract_version) in accepted

