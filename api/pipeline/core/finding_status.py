from __future__ import annotations

import re
from typing import Any

# Canonical status hierarchy used across probe, collector, and KPI paths.
# Higher rank means "better" outcome.
STATUS_ORDER: dict[str, int] = {
    "verified_success": 5,
    "functional_precondition_unmet": 4,
    "inferred_success": 3,
    "failure": 2,
    "unknown": 1,
}

CANONICAL_DISCOVERED_STATUSES = frozenset(
    {
        "verified_success",
        "functional_precondition_unmet",
        "inferred_success",
    }
)
CANONICAL_VERIFIED_STATUSES = frozenset({"verified_success"})

# Include legacy aliases so mixed-epoch captures remain comparable.
DISCOVERED_STATUSES = frozenset(CANONICAL_DISCOVERED_STATUSES | {"success", "partial"})
VERIFIED_STATUSES = frozenset(CANONICAL_VERIFIED_STATUSES | {"success"})

STATUS_ALIASES: dict[str, str] = {
    "success": "verified_success",
    "verified_success": "verified_success",
    "functional": "functional_precondition_unmet",
    "functional_precondition_unmet": "functional_precondition_unmet",
    "partial": "inferred_success",
    "inferred_success": "inferred_success",
    "error": "failure",
    "failure": "failure",
    "pending_refinement": "unknown",
    "unknown": "unknown",
    "": "unknown",
}

# Single classification pattern shared by forced-findings, verify paths, and
# gap resolution so drift cannot create status flip regressions.
FUNCTIONAL_CLASSIFICATION_PATTERN = re.compile(
    r"insufficient|not enough|balance|points|quota|limit|depleted|"
    r"write.*denied|account.*locked|not initialized|locked|suspended|"
    r"permission denied|not found|invalid|precondition",
    re.I,
)


def normalize_status(status: Any) -> str:
    raw = str(status or "").strip().lower()
    normalized = STATUS_ALIASES.get(raw, raw)
    return normalized if normalized in STATUS_ORDER else "unknown"


def is_functional_precondition_text(text: str) -> bool:
    return bool(FUNCTIONAL_CLASSIFICATION_PATTERN.search(str(text or "")))


def classify_finding_status(
    return_value: int,
    sentinels: dict[int, Any] | dict[Any, Any],
    sentinel_meaning: str = "",
) -> str:
    """Classify probe outcomes into canonical status taxonomy."""
    if return_value == 0:
        return "verified_success"

    unsigned = return_value & 0xFFFFFFFF
    meaning = str(sentinel_meaning or "")
    if not meaning:
        try:
            meaning = str((sentinels or {}).get(unsigned) or "")
        except Exception:
            meaning = ""

    if is_functional_precondition_text(meaning):
        return "functional_precondition_unmet"
    return "failure"

