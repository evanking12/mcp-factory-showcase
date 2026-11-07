"""S-06 context: gap resolution + MC-6 context.

This stage has the RICHEST context in the pipeline because it runs
after everything else. MC-6 sees all prior MC decisions, all findings,
all verification results, and decompiled C for remaining failures.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class S06Context:
    """Default context for gap resolution."""
    # Gap resolution uses LLM agents like S-02 but with richer context
    system_message_components: list[str] = field(default_factory=lambda: [
        "all_accumulated_findings",
        "all_mc_decisions",
        "verification_results",
        "sentinel_table",
        "vocabulary",
        "write_unlock_block",
        "user_hints",
    ])

    # MC-6 comprehensive unlock phases
    mc6_phases: list[str] = field(default_factory=lambda: [
        "llm_code_reasoning",      # analyze decompiled C for all failures
        "xor_checksum_solving",    # pattern-based unlock attempts
        "dependency_chain_replay", # try function sequences from code analysis
        "brute_force_fallback",    # exhaustive init mode + arg sweep
    ])

    # Clarification question generation
    generate_clarification_questions: bool = True


def build_stage_context(ctx, user_overrides: dict[str, Any] | None = None) -> S06Context:
    """Build S-06 context."""
    sc = S06Context()
    if user_overrides and "generate_questions" in user_overrides:
        sc.generate_clarification_questions = user_overrides["generate_questions"]
    return sc
