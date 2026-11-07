"""S-02 context: per-function probe loop context."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class S02Context:
    """Default context for the probe loop."""
    # Curriculum ordering: simpler functions first
    curriculum_order: str = "uncertainty_ascending"

    # What the LLM sees in the system message
    system_message_components: list[str] = field(default_factory=lambda: [
        "invocable_registry",      # all function signatures
        "prior_findings",          # what's been discovered so far
        "sentinel_table",          # named error codes
        "vocabulary",              # domain terms, ID formats
        "static_analysis_hints",   # binary strings, IAT imports
        "write_unlock_block",      # unlock status from S-01
        "user_hints",              # user-provided context
    ])

    # Per-function context (unique to each function being probed)
    per_function_components: list[str] = field(default_factory=lambda: [
        "function_signature",          # name, params, return type
        "decompiled_c_code",           # Ghidra output from doc_comment
        "parameter_descriptions",      # semantic names from static analysis
        "criticality_classification",  # read/write/utility/required_first
        "deterministic_fallback_args", # heuristic-generated probe args
    ])

    # Probe budget per function
    max_rounds_per_function: int = 5
    max_tool_calls_per_function: int = 8


def build_stage_context(ctx, user_overrides: dict[str, Any] | None = None) -> S02Context:
    """Build S-02 context. User can override probe budgets."""
    sc = S02Context()
    if user_overrides:
        if "max_rounds" in user_overrides:
            sc.max_rounds_per_function = user_overrides["max_rounds"]
        if "max_tool_calls" in user_overrides:
            sc.max_tool_calls_per_function = user_overrides["max_tool_calls"]
    return sc
