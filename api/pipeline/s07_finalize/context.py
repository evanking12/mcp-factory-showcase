"""S-07 context: finalization context."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class S07Context:
    """Default context for finalization."""
    # Harmonization is deterministic (no LLM)
    harmonization_rule: str = "upgrade error findings with direct-probe success evidence"
    never_downgrade_success: bool = True

    # Behavioral spec generation (LLM)
    behavioral_spec_instruction: str = (
        "Generate a typed Python behavioral specification (dataclasses, "
        "function stubs, return types) from these findings."
    )

    # Description synthesis (small LLM call)
    description_instruction: str = (
        "Write ONE sentence describing what this component does for a "
        "developer integrating it. Be specific — name the business domain, "
        "key entities, and operations. Max 25 words."
    )

    # AC-4 closure gate
    closure_states: list[str] = field(default_factory=lambda: [
        "done",
        "awaiting_clarification",
        "canceled",
    ])


def build_stage_context(ctx, user_overrides: dict[str, Any] | None = None) -> S07Context:
    """Build S-07 context."""
    return S07Context()
