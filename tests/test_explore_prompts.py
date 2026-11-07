from __future__ import annotations

from api.pipeline.core.prompts import _build_explore_system_message


def test_build_explore_system_message_requires_available_init_function_only() -> None:
    msg = _build_explore_system_message(
        [
            {"name": "CP_Initialize"},
            {"name": "CP_ProcessPurchase"},
        ],
        [],
    )

    content = msg["content"]
    assert "recognized init functions are: CP_Initialize" in content
    assert "Do NOT invent, search for, or spend tool calls on an unavailable init call." not in content


def test_build_explore_system_message_skips_missing_init_guidance() -> None:
    msg = _build_explore_system_message(
        [
            {"name": "SP_CommitRelease"},
        ],
        [],
    )

    content = msg["content"]
    assert "AVAILABLE FUNCTIONS: SP_CommitRelease" in content
    assert "No init-like function is available in AVAILABLE FUNCTIONS for this session." in content
    assert "Do NOT invent, search for, or spend tool calls on an unavailable init call." in content
    assert "recognized init functions are:" not in content
