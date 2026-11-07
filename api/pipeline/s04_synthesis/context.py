"""S-04 context: API reference synthesis context."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class S04Context:
    """Default context for synthesis."""
    # What the LLM receives for synthesis
    synthesis_inputs: list[str] = field(default_factory=lambda: [
        "all_findings",     # complete per-function results
        "vocabulary",       # accumulated domain terms
        "sentinel_table",   # all calibrated error codes
    ])

    # Synthesis instruction
    synthesis_instruction: str = (
        "Generate comprehensive API reference documentation. "
        "For each function: purpose, parameters with types and semantics, "
        "return values with sentinel meanings, dependencies, working example."
    )

    # MC-4 parsing: what to look for in synthesis doc
    mc4_search_patterns: list[str] = field(default_factory=lambda: [
        "init mode mentions",
        "function dependency chains",
        "required call sequences",
    ])


def build_stage_context(ctx, user_overrides: dict[str, Any] | None = None) -> S04Context:
    """Build S-04 context."""
    return S04Context()
