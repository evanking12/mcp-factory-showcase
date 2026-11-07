"""S-03 context: reconciliation + MC-3 write analysis context."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class S03Context:
    """Default context for post-probe reconciliation."""
    # No LLM calls in this stage — all deterministic
    uses_llm: bool = False

    # Reconciliation rules
    upgrade_error_to_success_when: str = "probe_log shows return=0 for direct self-call"
    never_downgrade_success: bool = True

    # MC-3 failure classification thresholds
    mc3_uniform_sentinel_action: str = "targeted_init_sweep"
    mc3_mixed_sentinel_action: str = "defer_to_per_function_strategy"


def build_stage_context(ctx, user_overrides: dict[str, Any] | None = None) -> S03Context:
    """Build S-03 context. Mostly deterministic, few user overrides."""
    return S03Context()
