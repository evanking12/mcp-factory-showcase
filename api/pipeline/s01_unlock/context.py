"""S-01 context: write-unlock discovery context."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class S01Context:
    """Default context for write-unlock probing."""
    # Patterns that identify write functions (regex-ready)
    write_fn_patterns: list[str] = field(default_factory=lambda: [
        "pay", "redeem", "unlock", "process", "write", "commit",
        "transfer", "debit", "credit", "update", "set", "create",
        "delete", "submit", "send",
    ])

    # Init mode values to try during unlock sweep
    init_modes_to_try: list[int] = field(default_factory=lambda: [
        0, 1, 2, 3, 4, 5, 6, 7, 8, 16, 32, 64,
    ])

    # Code reasoning instruction for the LLM
    code_reasoning_instruction: str = (
        "Analyze this decompiled C code. What unlock mechanism does it use? "
        "XOR checksums? Magic values? Required call sequences? "
        "Generate specific inputs that would satisfy the conditions."
    )

    # Whether to replay winning sequence from prior run
    replay_prior_sequence: bool = True


def build_stage_context(ctx, user_overrides: dict[str, Any] | None = None) -> S01Context:
    """Build S-01 context from defaults + prior winning sequence."""
    sc = S01Context()
    if user_overrides and "init_modes" in user_overrides:
        sc.init_modes_to_try = user_overrides["init_modes"]
    return sc
