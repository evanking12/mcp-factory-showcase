"""Public executor interface."""

from __future__ import annotations

from typing import Any

from api.services.executor import _execute_tool, _execute_tool_traced


def execute_tool(invocable: dict[str, Any], args: dict[str, Any], extra_sentinels: dict | None = None) -> str:
    return _execute_tool(invocable, args, extra_sentinels)


def execute_tool_traced(
    invocable: dict[str, Any],
    args: dict[str, Any],
    extra_sentinels: dict | None = None,
) -> dict[str, Any]:
    return _execute_tool_traced(invocable, args, extra_sentinels)
