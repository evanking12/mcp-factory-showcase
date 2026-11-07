"""S-00 context: foundational context for the entire pipeline.

This is the LARGEST context module because S-00 sets the baseline
that every subsequent stage inherits. Generic defaults work for any DLL;
user hints and prior-run data override/augment them.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class S00Context:
    """Default context for sentinel calibration + vocab seeding."""
    # Sentinel defaults — universal DLL error patterns
    sentinel_defaults: dict[int, str] = field(default_factory=lambda: {
        0x00000000: "success",
        0xFFFFFFFF: "general failure / not found",
        0xFFFFFFFE: "null or invalid argument",
        0xFFFFFFFD: "not initialized",
        0xFFFFFFFC: "access denied / locked",
        0xFFFFFFFB: "write denied / insufficient privilege",
    })

    # Vocab seed keys — what we try to discover for every DLL
    vocab_seed_keys: list[str] = field(default_factory=lambda: [
        "id_formats",       # e.g. CUST-###, ORD-###
        "value_semantics",  # e.g. amount_cents, balance
        "error_codes",      # sentinel meanings
        "notes",            # user-provided description
        "user_context",     # use cases from job creation
    ])

    # Static analysis capabilities to attempt
    static_analysis_features: list[str] = field(default_factory=lambda: [
        "binary_strings",      # embedded string literals
        "iat_imports",         # Windows API imports
        "pe_metadata",         # version info, timestamps
        "sentinel_constants",  # Capstone disassembly for cmp instructions
    ])

    # LLM prompt template for sentinel naming
    sentinel_naming_instruction: str = (
        "Assign a SHORT plain-English meaning (3-8 words) to each of these "
        "32-bit return codes based on the function names that produced them."
    )


def build_stage_context(ctx, user_overrides: dict[str, Any] | None = None) -> S00Context:
    """Build S-00 context, merging defaults with user hints and prior-run data.

    User overrides can set:
      - additional sentinel_defaults (custom error codes the user knows)
      - additional vocab_seed_keys (domain-specific vocab to look for)
    """
    sc = S00Context()

    # Merge user-known error codes
    if user_overrides and "error_codes" in user_overrides:
        sc.sentinel_defaults.update(user_overrides["error_codes"])

    # Merge prior-run sentinels (circular enrichment)
    prior = getattr(ctx, '_prior_session', {}) or {}
    if prior.get("sentinels"):
        sc.sentinel_defaults.update(prior["sentinels"])

    return sc
