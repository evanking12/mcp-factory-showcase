"""Shared explore runtime configuration defaults.

This module centralizes environment-driven defaults used by runtime parsing
and fallback behavior. Keep it dependency-light so core types can import it
without pulling in helper/storage modules.
"""

from __future__ import annotations

import os

CAP_PROFILES = {
    "dev": {"rounds": 3, "tool_calls": 5},
    "stabilize": {"rounds": 4, "tool_calls": 8},
    "deploy": {"rounds": 5, "tool_calls": 8},
}


def resolve_cap_profile() -> str:
    profile = os.getenv("EXPLORE_CAP_PROFILE", "deploy").strip().lower()
    if profile not in CAP_PROFILES:
        return "deploy"
    return profile


CAP_PROFILE = resolve_cap_profile()
MAX_EXPLORE_ROUNDS_PER_FUNCTION = int(
    os.getenv("EXPLORE_MAX_ROUNDS", str(CAP_PROFILES[CAP_PROFILE]["rounds"]))
)
MAX_TOOL_CALLS_PER_FUNCTION = int(
    os.getenv("EXPLORE_MAX_TOOL_CALLS", str(CAP_PROFILES[CAP_PROFILE]["tool_calls"]))
)
MAX_FUNCTIONS_PER_SESSION = int(os.getenv("EXPLORE_MAX_FUNCTIONS", "50"))
GAP_RESOLUTION_ENABLED = os.getenv("EXPLORE_ENABLE_GAP_RESOLUTION", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
