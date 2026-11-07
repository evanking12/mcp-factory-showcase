"""S-05 context: enrichment + verification context."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class S05Context:
    """Default context for backfill + verification."""
    # No LLM calls — deterministic execution
    uses_llm: bool = False

    # Verification thresholds
    verification_categories: dict[str, str] = field(default_factory=lambda: {
        "return_0": "verified",
        "return_non_sentinel_positive": "verified",
        "return_sentinel": "state_drift",
        "no_return_parsed": "inferred",
        "exception": "error",
    })

    # MC-5 chaining strategy
    mc5_chain_read_to_write: bool = True
    mc5_id_extraction_patterns: list[str] = field(default_factory=lambda: [
        r"^[A-Z]+-\d+",   # CUST-001, ORD-001
        r"^ORD-",          # order IDs
        r"^ACCT-",         # account IDs
    ])


def build_stage_context(ctx, user_overrides: dict[str, Any] | None = None) -> S05Context:
    """Build S-05 context."""
    return S05Context()
